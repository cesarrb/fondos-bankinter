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


def fetch_quefondos(session, isin):
    """Devuelve dict {VL, VLDate, Currency} o None si no lo encuentra.
    Solo el dato diario esencial y fiable; la metadata/rentabilidades vienen del estático."""
    r = session.get(QF_URL.format(isin=isin), timeout=25)
    if r.status_code != 200:
        return None
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text))
    m = re.search(r"Valor liquidativo:\s*([\d.]+,\d+)\s*([A-Z]{3})", t)
    if not m:
        return None
    d = re.search(r"Fecha:\s*(\d{2}/\d{2}/\d{4})", t)
    return {"VL": _num(m.group(1)), "Currency": m.group(2),
            "VLDate": _iso_date(d.group(1)) if d else ""}


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
    import requests, time as _t
    t0 = _t.time()
    if fecha is None:
        fecha = datetime.date.today().isoformat()
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
