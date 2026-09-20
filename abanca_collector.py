#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Colector de los fondos SOLO-ABANCA (no presentes en Bankinter) para la foto diaria.

- Fuente primaria: quefondos.com (VL a precisión completa, público, por ISIN).
- Fuente de respaldo: Financial Times (markets.ft.com) para los que quefondos no tenga.
- Lee la metadata curada de data/abanca_solo.csv (ISIN, nombre, gestora, categoría,
  divisa, SRRI, TER, comisión de gestión, inversión mínima) — eso NO cambia a diario.
- Solo baja de la red el VL + fecha (y, de quefondos, las rentabilidades anuales si están).
- Devuelve filas dict compatibles con el esquema de data/fondos_latest.csv, con
  una columna extra "Fuente" (= "quefondos" / "FT").

Diseñado para ser ADITIVO y AISLADO: si algo falla, lanza excepción o devuelve lo que
tenga; el que lo llama (extract_fondos.py) debe capturarlo para no romper la foto de
Bankinter.
"""
import csv, re, time, sys, os, datetime

QF_URL = "https://www.quefondos.com/es/fondos/ficha/index.html?isin={isin}"
FT_SEARCH = "https://markets.ft.com/data/searchapi/searchsecurities?query={isin}"
FT_TEAR = "https://markets.ft.com/data/funds/tearsheet/summary?s={sym}"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

DIR = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(DIR, "data", "abanca_solo.csv")


def _asset_class(cat):
    """Mapea la categoría (español, ABANCA/VDOS) a GlobalAssetClass (como usa Bankinter),
    para que los filtros de 'Clase de activo' del frontend funcionen con estos fondos."""
    c = (cat or "").upper()
    if "RENTA VARIABLE" in c or "RENT. VARIABLE" in c:
        return "Equity"
    if "RENTA FIJA" in c or "RENT. FIJA" in c:
        return "Fixed Income"
    if "MONETARIO" in c:
        return "Capital Preservation"
    if "MIXTO" in c or "GLOBAL" in c or "MIXTA" in c or "PERFIL" in c:
        return "Allocation"
    if "ALTERNATIV" in c or "RETORNO ABSOLUTO" in c or "RENTABILIDAD ABSOLUTA" in c or "ABSOLUTA" in c:
        return "Alternative Strategies"
    if "MATERIAS PRIMAS" in c or "INMOBILIARI" in c or "MATERIAS" in c or "ORO" in c:
        return "Real Assets"
    if "GARANTIZADO" in c:
        return "Capital Preservation"
    return "Other"


def _num(s):
    """'126,886800' -> 126.8868 ; '1.234,56' -> 1234.56 ; '' -> None"""
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    s = s.replace(".", "").replace(",", ".") if ("," in s and "." in s) else s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _iso_date(dmy):
    """'17/09/2026' -> '2026-09-17' ; 'Sep 18 2026' -> '2026-09-18'"""
    dmy = (dmy or "").strip()
    if re.match(r"\d{2}/\d{2}/\d{4}", dmy):
        d, m, y = dmy[:10].split("/")
        return f"{y}-{m}-{d}"
    m = re.match(r"([A-Z][a-z]{2}) (\d{2}) (\d{4})", dmy)
    if m:
        months = {"Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06",
                  "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"}
        return f"{m.group(3)}-{months.get(m.group(1),'01')}-{m.group(2)}"
    return ""


def _parse_acumuladas(t):
    """Extrae las rentabilidades acumuladas de la ficha de quefondos como
    {'M1':..,'M3':..,'M6':..,'M12':..,'M36':..,'M60':..,'M120':..} (acumuladas, en %).
    Mapea por etiqueta (no por posición) para ser robusto ante fondos jóvenes."""
    blk = re.search(r"Rentabilidades acumuladas .*?Rentabilidades acumuladas (.*?) Ranking y quintil.*?\bFondo\b (.*?) Categor", t)
    if not blk:
        return {}
    labels = re.findall(r"(\d+)\s+(meses|mes|años|año|dias|dia|semanas|semana)", blk.group(1))
    vals = blk.group(2).split()
    unit_map = {("1", "mes"): "M1", ("3", "meses"): "M3", ("6", "meses"): "M6",
                ("1", "año"): "M12", ("3", "años"): "M36", ("5", "años"): "M60",
                ("10", "años"): "M120"}
    out = {}
    for (n, u), v in zip(labels, vals):
        key = unit_map.get((n, u))
        if not key:
            continue
        val = _num(v.replace("%", ""))
        if val is not None:
            out[key] = val
    return out


def _parse_riesgo(t):
    """Volatilidad 1 año, comisiones desglosadas y fecha de constitución de la ficha."""
    def g(pat):
        m = re.search(pat, t)
        return _num(m.group(1)) if m else None
    out = {
        "vol": g(r"Volatilidad:\s*([\d.,]+)%"),
        "mgmt": g(r"\bFija:\s*([\d.,]+)%"),          # comisión de gestión (parte fija)
        "perf": g(r"\bVariable:\s*([\d.,]+)%"),        # comisión sobre resultados (parte variable)
        "custodian": g(r"Dep.sito:\s*([\d.,]+)%"),
        "frontend": g(r"Suscripci.n:\s*(?:Hasta\s*)?([\d.,]+)%"),
        "redemption": g(r"Reembolso:\s*([\d.,]+)%"),
    }
    fc = re.search(r"Fecha de constituci.n:\s*(\d{2}/\d{2}/\d{4})", t)
    out["inception"] = _iso_date(fc.group(1)) if fc else ""
    return out


def fetch_quefondos(session, isin):
    """Devuelve dict {VL, VLDate, Currency, acum:{...}, riesgo:{...}} o None."""
    r = session.get(QF_URL.format(isin=isin), timeout=25)
    if r.status_code != 200:
        return None
    import html as _html
    t = _html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text)))
    m = re.search(r"Valor liquidativo:\s*([\d.]+,\d+)\s*([A-Z]{3})", t)
    if not m:
        return None
    d = re.search(r"Fecha:\s*(\d{2}/\d{2}/\d{4})", t)
    return {"VL": _num(m.group(1)), "Currency": m.group(2),
            "VLDate": _iso_date(d.group(1)) if d else "",
            "acum": _parse_acumuladas(t), "riesgo": _parse_riesgo(t)}


def fetch_ft(session, isin):
    """Respaldo: devuelve dict {VL, VLDate, Currency} o None."""
    j = session.get(FT_SEARCH.format(isin=isin), timeout=20).json()
    sec = j.get("data", {}).get("security", [])
    if not sec:
        return None
    sym = sec[0]["symbol"]
    t = re.sub(r"<[^>]+>", " ", session.get(FT_TEAR.format(sym=sym), timeout=20).text)
    p = re.search(r"Price \(([A-Z]{3})\)\s*([\d.,]+)", t)
    if not p:
        return None
    d = re.search(r"as of\s*([A-Z][a-z]{2} \d{2} \d{4})", t)
    return {"VL": _num(p.group(2)), "Currency": p.group(1),
            "VLDate": _iso_date(d.group(1)) if d else ""}


def collect(fecha=None, delay=0.35, log=print, max_seconds=600):
    """
    Devuelve (rows, stats). rows = lista de dicts en esquema fondos_latest + 'Fuente'.
    stats = {'quefondos':n, 'FT':n, 'miss':[isines], 'aborted':bool}.
    max_seconds: presupuesto total; si se supera, devuelve lo que lleve (nunca se eterniza).
    """
    import requests, time as _t, json as _json
    t0 = _t.time()
    if fecha is None:
        fecha = datetime.date.today().isoformat()
    # Tipo sin riesgo para el Sharpe: €STR de data/euribor.json (fallback 2.5%).
    rf = 2.5
    try:
        rf = float(_json.load(open(os.path.join(DIR, "data", "euribor.json"))).get("estr", rf))
    except Exception:
        pass
    if not os.path.exists(STATIC):
        raise FileNotFoundError(f"No existe {STATIC}")
    meta = list(csv.DictReader(open(STATIC, encoding="utf-8"), delimiter=";"))
    s = requests.Session()
    s.headers["User-Agent"] = UA
    rows = []
    stats = {"quefondos": 0, "FT": 0, "miss": [], "aborted": False}
    for i, m in enumerate(meta, 1):
        if _t.time() - t0 > max_seconds:
            resto = [x["Isin"] for x in meta[i-1:]]
            stats["miss"] += resto
            stats["aborted"] = True
            log(f"  presupuesto de {max_seconds}s agotado en {i-1}/{len(meta)}; "
                f"quedan {len(resto)} sin bajar (se reintentan mañana)")
            break
        isin = m["Isin"]
        data = src = None
        try:
            data = fetch_quefondos(s, isin)
            if data:
                src = "quefondos"
        except Exception as e:
            log(f"  quefondos ERR {isin}: {e}")
        if not data:
            try:
                data = fetch_ft(s, isin)
                if data:
                    src = "FT"
            except Exception as e:
                log(f"  FT ERR {isin}: {e}")
        if not data:
            stats["miss"].append(isin)
            time.sleep(delay)
            continue
        row = {
            "Isin": isin, "Name": m["Name"], "LegalName": m["LegalName"],
            "ProviderCompanyName": m["ProviderCompanyName"], "CategoryName": m["CategoryName"],
            "GlobalCategoryName": m["CategoryName"], "GlobalAssetClass": _asset_class(m["CategoryName"]),
            "Currency": data["Currency"] or m["Currency"], "SRRI": m["SRRI"],
            "TER": m["TER"], "OngoingCostActual": m["TER"], "ManagementFee": m["ManagementFee"],
            "InitialPurchase": m["InitialPurchase"],
            "VL": data["VL"], "VLDate": data["VLDate"],
            "Fuente": src, "fecha": fecha,
        }
        # Rentabilidades curadas del estático (no se scrapean a diario): YTD + años cerrados.
        # YR_ReturnM12_1 = año en curso (YTD), _2 = 2025, _3 = 2024, _4 = 2023, _5 = 2022.
        if m.get("Rent2026YTD") not in (None, ""):
            row["ReturnM0"] = m["Rent2026YTD"]        # YTD
            row["YR_ReturnM12_1"] = m["Rent2026YTD"]
        for k, col in enumerate(["Rent2025", "Rent2024", "Rent2023", "Rent2022"], start=2):
            if m.get(col) not in (None, ""):
                row[f"YR_ReturnM12_{k}"] = m[col]
        if m.get("Volatilidad1A") not in (None, ""):
            row["StandardDeviationM12"] = m["Volatilidad1A"]
        # Rentabilidades acumuladas de quefondos. 1m/3m/6m/1A se dejan tal cual (acumuladas);
        # 3A/5A/10A se ANUALIZAN para igualar el criterio de Bankinter (ReturnM36/60 anualizados).
        acum = data.get("acum") or {}
        def _ann(cum, years):
            if cum is None or cum <= -100:
                return None
            return round(((1 + cum / 100.0) ** (1.0 / years) - 1) * 100, 2)
        for src_k, dst_k in (("M1", "ReturnM1"), ("M3", "ReturnM3"), ("M6", "ReturnM6"), ("M12", "ReturnM12")):
            if src_k in acum:
                row[dst_k] = acum[src_k]
        for src_k, dst_k, yrs in (("M36", "ReturnM36", 3), ("M60", "ReturnM60", 5), ("M120", "ReturnM120", 10)):
            if src_k in acum:
                a = _ann(acum[src_k], yrs)
                if a is not None:
                    row[dst_k] = a
        # Riesgo y comisiones desglosadas de quefondos + Sharpe CALCULADO por nosotros.
        rg = data.get("riesgo") or {}
        vol = rg.get("vol")
        if vol is not None:
            row["StandardDeviationM12"] = vol   # volatilidad 1A directa de quefondos (pisa la curada)
        if rg.get("mgmt") is not None:
            row["ManagementFee"] = rg["mgmt"]   # comisión de gestión oficial (parte fija)
        for src_k, dst_k in (("perf", "PerformanceFeeCharged"), ("custodian", "CustodianFee"),
                             ("frontend", "MaxFrontEndLoad"), ("redemption", "MaxRedemptionFee")):
            if rg.get(src_k) is not None:
                row[dst_k] = rg[src_k]
        if rg.get("inception"):
            row["InceptionDate"] = rg["inception"]
        # Sharpe 1A = (rentabilidad 1A − tipo sin riesgo €STR) / volatilidad 1A
        r12 = row.get("ReturnM12")
        if vol and r12 not in (None, ""):
            try:
                row["SharpeM12"] = round((float(r12) - rf) / float(vol), 2)
            except (ValueError, ZeroDivisionError):
                pass
        rows.append(row)
        stats[src] += 1
        if i % 50 == 0:
            log(f"  ...{i}/{len(meta)} quefondos={stats['quefondos']} FT={stats['FT']} miss={len(stats['miss'])}")
        time.sleep(delay)
    return rows, stats


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/abanca_collector_out.csv"
    rows, stats = collect()
    print(f"\nRESULTADO: quefondos={stats['quefondos']} FT={stats['FT']} "
          f"sin fuente={len(stats['miss'])} -> {stats['miss']}")
    if rows:
        keys = sorted({k for r in rows for k in r})
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys, delimiter=";")
            w.writeheader(); w.writerows(rows)
        print(f"Escrito {len(rows)} filas en {out}")
