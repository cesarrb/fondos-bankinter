#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regeneración MENSUAL del catálogo solo-ABANCA (data/abanca_solo.csv).

Qué hace (alcance "refrescar + podar", decidido con el usuario):
  1. REFRESCA, para cada ISIN del catálogo actual, los campos que quefondos sirve de
     forma fiable: rentabilidades por AÑO NATURAL (Rent<año>), volatilidad 1 año,
     inversión mínima, divisa y comisión de gestión (parte fija).
  2. PRESERVA los campos curados que quefondos NO da (Name, LegalName, gestora,
     CategoryName, SRRI, TER, y las estimaciones Vol3A_est / MaxDD3A_est). Nunca
     los borra ni los pisa con vacío.
  3. PODA (política de 2 avisos) los fondos que ni quefondos ni Financial Times
     sirven ya: a la 1.ª ausencia quedan "en vigilancia"; a la 2.ª ausencia
     consecutiva se dan de BAJA (se mueven a data/abanca_bajas.csv). Así un fallo
     puntual de red no borra un fondo vivo.
  NO descubre fondos NUEVOS (eso necesitaría una lista maestra del universo ABANCA,
  que no existe de forma automática; se decidió dejarlo fuera).

Diseño: aislado y seguro. Respalda el catálogo antes de tocarlo, escribe de forma
atómica, respeta un presupuesto de tiempo (los no procesados NO se penalizan) y deja
un parte de salud en data/abanca_regen_health.json para poder auditarlo.

Pensado para correr en la NUBE (GitHub Actions, mensual) igual que la foto diaria.
"""
import csv, os, re, json, html, time, shutil, datetime, sys

DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(DIR)

STATIC   = os.path.join(DIR, "data", "abanca_solo.csv")
STATE    = os.path.join(DIR, "data", "abanca_regen_state.json")   # {"miss": {isin: n}}
BAJAS    = os.path.join(DIR, "data", "abanca_bajas.csv")
HEALTH   = os.path.join(DIR, "data", "abanca_regen_health.json")
BAK_DIR  = os.path.join(DIR, "data", "backups")
QF_URL   = "https://www.quefondos.com/es/fondos/ficha/index.html?isin={isin}"
UA       = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
PRUNE_AFTER = 2          # nº de ausencias consecutivas para dar de baja
MAX_SECONDS = 1500       # presupuesto total (los que no dé tiempo quedan intactos)


def _num(s):
    if s is None:
        return None
    s = str(s).strip().replace("%", "")
    if not s or s in ("-", "—", "n.d.", "N/D"):
        return None
    s = s.replace(".", "").replace(",", ".") if ("," in s and "." in s) else s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _fmt(v):
    """float -> cadena estilo catálogo (punto decimal, sin ceros sobrantes)."""
    if v is None:
        return None
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return ("%.4f" % v).rstrip("0").rstrip(".")


def fetch_ficha(session, isin):
    """Descarga y parsea la ficha de quefondos. Devuelve dict o None si no hay ficha/VL."""
    r = session.get(QF_URL.format(isin=isin), timeout=25)
    if r.status_code != 200:
        return None
    t = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text)))
    if "Valor liquidativo:" not in t:
        return None
    out = {"live": True}
    m = re.search(r"Valor liquidativo:\s*[\d.]+,\d+\s*([A-Z]{3})", t)
    out["currency"] = m.group(1) if m else None
    m = re.search(r"Fecha:\s*(\d{2}/\d{2}/\d{4})", t)
    out["vldate"] = m.group(1) if m else None
    m = re.search(r"Volatilidad:\s*([\d.,]+)%", t)
    out["vol1a"] = _num(m.group(1)) if m else None
    m = re.search(r"\bFija:\s*([\d.,]+)%", t)
    out["mgmt"] = _num(m.group(1)) if m else None
    m = re.search(r"Inversi.n m.nima(?:\s*inicial)?:?\s*([\d.,]+)", t)
    out["inv_min"] = _num(m.group(1)) if m else None
    # Rentabilidades por AÑO NATURAL: "Rentabilidades anuales <años> Ranking ... Fondo <vals> Categor"
    out["annual"] = {}
    seg = re.search(r"Rentabilidades anuales\s+((?:\d{4}\s+)+)Ranking.*?\bFondo\b\s+(.*?)\s+Categor", t)
    if seg:
        years = [int(y) for y in seg.group(1).split()]
        toks = seg.group(2).split()
        for y, tok in zip(years, toks):
            v = _num(tok)
            if v is not None:
                out["annual"][y] = v
    return out


def fetch_alive_ft(session, isin):
    """Respaldo mínimo de VIVO/MUERTO vía Financial Times (solo confirma que cotiza)."""
    try:
        import abanca_collector
        return abanca_collector.fetch_ft(session, isin) is not None
    except Exception:
        return False


def main(log=print, max_seconds=MAX_SECONDS):
    import requests
    t0 = time.time()
    hoy = datetime.date.today().isoformat()
    year_now = datetime.date.today().year

    if not os.path.exists(STATIC):
        raise FileNotFoundError(STATIC)
    with open(STATIC, encoding="utf-8") as fh:
        rd = csv.DictReader(fh, delimiter=";")
        header = rd.fieldnames
        rows = list(rd)
    log(f"Catálogo: {len(rows)} fondos, {len(header)} columnas")

    # columnas de rentabilidad por año -> {nombre_columna: año}
    year_cols = {}
    for c in header:
        m = re.match(r"Rent(\d{4})(YTD)?$", c)
        if m:
            year_cols[c] = int(m.group(1))
    rollover = (max(year_cols.values(), default=year_now) != year_now)

    state = {"miss": {}}
    if os.path.exists(STATE):
        try:
            state = json.load(open(STATE, encoding="utf-8"))
            state.setdefault("miss", {})
        except Exception:
            pass

    s = requests.Session(); s.headers["User-Agent"] = UA
    refrescados = vivos = sin_fuente = procesados = 0
    nuevas_bajas = []
    keep = []

    for i, row in enumerate(rows, 1):
        isin = (row.get("Isin") or "").strip()
        if time.time() - t0 > max_seconds:
            # presupuesto agotado: el resto se conserva TAL CUAL (no se penaliza ni se poda)
            keep.extend(rows[i-1:])
            log(f"  presupuesto de {max_seconds}s agotado en {i-1}/{len(rows)}; "
                f"{len(rows)-(i-1)} fondos intactos (se revisan el mes que viene)")
            break
        procesados += 1
        data = None
        try:
            data = fetch_ficha(s, isin)
        except Exception as e:
            log(f"  quefondos ERR {isin}: {e}")
        alive = bool(data and data.get("live"))
        if not alive:
            # respaldo: ¿sigue vivo según FT aunque quefondos no lo tenga?
            try:
                alive = fetch_alive_ft(s, isin)
            except Exception:
                alive = False

        if not alive:
            n = state["miss"].get(isin, 0) + 1
            state["miss"][isin] = n
            sin_fuente += 1
            if n >= PRUNE_AFTER:
                nuevas_bajas.append({"fecha": hoy, "isin": isin,
                                     "nombre": row.get("Name", ""),
                                     "motivo": f"sin datos {n} meses (quefondos+FT)"})
                log(f"  BAJA {isin} ({row.get('Name','')}): {n}ª ausencia -> fuera del catálogo")
                continue  # no se conserva
            log(f"  en vigilancia {isin} ({row.get('Name','')}): ausencia {n}/{PRUNE_AFTER}")
            keep.append(row)
            continue

        # vivo: limpiar contador y refrescar lo fiable (sin pisar nunca con vacío)
        state["miss"].pop(isin, None)
        vivos += 1
        if data:
            got = False
            for col, yr in year_cols.items():
                if yr in data["annual"]:
                    row[col] = _fmt(data["annual"][yr]); got = True
            if data.get("vol1a") is not None:
                row["Volatilidad1A"] = _fmt(data["vol1a"]); got = True
            if data.get("inv_min") is not None and "InitialPurchase" in header:
                row["InitialPurchase"] = _fmt(data["inv_min"]); got = True
            if data.get("currency") and "Currency" in header:
                row["Currency"] = data["currency"]
            if data.get("mgmt") is not None and "ManagementFee" in header:
                row["ManagementFee"] = _fmt(data["mgmt"]); got = True
            if got:
                refrescados += 1
        keep.append(row)
        if i % 40 == 0:
            log(f"  ...{i}/{len(rows)} vivos={vivos} refrescados={refrescados} sin_fuente={sin_fuente}")
        time.sleep(0.3)

    # --- escritura segura ---
    os.makedirs(BAK_DIR, exist_ok=True)
    shutil.copy2(STATIC, os.path.join(BAK_DIR, f"abanca_solo_{hoy}.csv"))
    tmp = STATIC + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=header, delimiter=";", extrasaction="ignore")
        w.writeheader(); w.writerows(keep)
    os.replace(tmp, STATIC)

    if nuevas_bajas:
        existe = os.path.exists(BAJAS)
        with open(BAJAS, "a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["fecha", "isin", "nombre", "motivo"], delimiter=";")
            if not existe:
                w.writeheader()
            w.writerows(nuevas_bajas)

    json.dump(state, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=0)

    en_vigilancia = sum(1 for n in state["miss"].values() if n == 1)
    health = {
        "fecha": hoy,
        "total_catalogo": len(keep),
        "procesados": procesados,
        "refrescados": refrescados,
        "vivos": vivos,
        "sin_fuente": sin_fuente,
        "en_vigilancia": en_vigilancia,
        "bajas_aplicadas": len(nuevas_bajas),
        "duracion_s": round(time.time() - t0, 1),
        "rollover_cambio_de_anyo": rollover,
    }
    json.dump(health, open(HEALTH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log("RESUMEN: " + json.dumps(health, ensure_ascii=False))
    if rollover:
        log("::warning::CAMBIO DE AÑO: renombra las columnas Rent<año> del catálogo y "
            "actualiza los años fijos de abanca_collector.py (líneas Rent20xx).")
    return health


if __name__ == "__main__":
    ms = int(sys.argv[1]) if len(sys.argv) > 1 else MAX_SECONDS
    main(max_seconds=ms)
