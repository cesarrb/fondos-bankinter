#!/usr/bin/env python3
"""
Descarga el catalogo completo de fondos del buscador de Bankinter (fuente: Allfunds/Morningstar)
y lo vuelca a CSV. Uso personal. El endpoint es interno/no documentado y podria cambiar.
"""
import time, csv, datetime, os, sys, socket
import requests

BASE = "https://allfunds-bankinter-components-back.webfg.com/v1"
HDRS = {"Accept": "application/json", "User-Agent": "fondos-tracker/1.0 (uso personal)"}
SORTS = ["ReturnM0", "ReturnM12", "ReturnM36", "ReturnM60", "InceptionDate", "ExpenseRatio", "FundTNAV"]
PAGE = 50

# --- Robustez de red: evitar cuelgues indefinidos ---
# timeout de requests = (conectar, leer): si el socket no recibe datos en READ_TIMEOUT s, aborta.
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30
TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)
# Suelo a nivel de socket del SO por si el timeout de requests no dispara (caso del cuelgue de 2h+):
socket.setdefaulttimeout(READ_TIMEOUT + 15)
MAX_RETRIES = 4          # reintentos máximos por petición (límite duro)
MAX_RUN_SECONDS = 210 * 60  # tope de tiempo TOTAL del raspado (3,5 h): permite terminar los ~2.585 fondos
                            # aun en días lentos. Cruzar medianoche ya es seguro (la fecha se fija al inicio).
RUN_START = time.time()

s = requests.Session()
s.headers.update(HDRS)
funds = {}   # clave: SecId


def time_left():
    return MAX_RUN_SECONDS - (time.time() - RUN_START)


def _get(url, params=None, tries=MAX_RETRIES, base_sleep=1.5):
    """GET con timeout (conectar, leer), reintentos limitados y backoff. Devuelve Response 200 o None.
    Nunca puede colgarse indefinidamente: cada intento está acotado por TIMEOUT y por el suelo de socket."""
    for a in range(tries):
        try:
            r = s.get(url, params=params, timeout=TIMEOUT)
            if r.status_code == 200:
                return r
        except (requests.RequestException, socket.timeout, OSError):
            pass
        time.sleep(base_sleep * (a + 1))
    return None


def api(params):
    r = _get(f"{BASE}/fund", params=params)
    if not r:
        return None
    try:
        return r.json()
    except ValueError:
        return None


def ids(endpoint):
    r = _get(f"{BASE}/ms-api/{endpoint}")
    if not r:
        return []
    try:
        return r.json().get("data", [])
    except (ValueError, AttributeError):
        return []


def base(filters):
    return {"page": 1, "pageSize": PAGE, "sortBy": "ReturnM0.desc", **filters}


def snapshot_json(isin):
    """Descarga la ficha MFsnapshot (json) de un fondo, o None."""
    params = {"isin": isin, "viewId": "MFsnapshot", "responseViewFormat": "json",
              "idtype": "isin", "currencyId": "EUR", "languageId": "es-ES"}
    r = _get(f"{BASE}/ms-api/security-detail", params=params, tries=3, base_sleep=0.6)
    if not r:
        return None
    try:
        return r.json()
    except ValueError:
        return None


def parse_alloc(js):
    """Distribucion por activos (posicion Neta). Devuelve (%RV, %RF, %Liquidez, %Otros)."""
    try:
        port = js[0]["Portfolios"][0]
        net = [x for x in port["AssetAllocations"] if x["SalePosition"] == "N"][0]
        m = {b["Type"]: b["Value"] for b in net["BreakdownValues"]}
        return (round(m.get("1", 0), 1), round(m.get("2", 0), 1),
                round(m.get("3", 0), 1), round(m.get("4", 0), 1))
    except Exception:
        return None, None, None, None


def parse_risk(js):
    """Metricas de riesgo por periodo (M12/M36/M60/M120) del bloque RiskStatistics en EUR.
    Devuelve dict {StandardDeviationM36: .., MaxDrawdownM36: .., SharpeM36: .., SortinoM36: ..}."""
    try:
        blk = [b for b in js[0].get("RiskStatistics", [])
               if b.get("CurrencyId") == "EUR" and "StandardDeviations" in b]
        if not blk:
            return {}
        b = blk[0]
        MAP = {"StandardDeviations": "StandardDeviation", "MaxDrawdowns": "MaxDrawdown",
               "SharpeRatios": "Sharpe", "SortinoRatios": "Sortino"}
        out = {}
        for src, dst in MAP.items():
            for x in b.get(src, []):
                p, v = x.get("TimePeriod"), x.get("Value")
                if p and v is not None:
                    try:
                        out[dst + p] = round(float(v), 2)
                    except (TypeError, ValueError):
                        pass
        return out
    except Exception:
        return {}


def parse_sri(js):
    """SRI (indicador de riesgo del KID PRIIPs, 1-7) — el que muestra Bankinter en la ficha.
    Prefiere Mifid.SummaryRiskIndicator (viene con fecha, es el vigente) y cae a KID.SRI.
    NO usa CollectedSRRI (SRRI antiguo de Morningstar por volatilidad, a menudo desactualizado)."""
    try:
        d = js[0]
        for path in (("Mifid", "SummaryRiskIndicator"), ("KID", "SRI")):
            sub = d.get(path[0]) or {}
            v = sub.get(path[1])
            if v is not None:
                iv = int(v)
                if 1 <= iv <= 7:
                    return str(iv)
    except Exception:
        pass
    return None


def parse_vl(js):
    """VL (valor liquidativo) mas reciente en EUR. Devuelve (fecha_iso, vl) o (None, None).
    Usa ClosePrice de TrailingPerformance (convertido a EUR porque pedimos currencyId=EUR)."""
    try:
        d = js[0]
        for b in d.get("TrailingPerformance", []):
            for r in b.get("Return", []):
                if r.get("TimePeriod") == "ClosePrice" and r.get("Value") is not None:
                    return (r.get("Date") or "")[:10], round(float(r["Value"]), 4)
            break
        lp = d.get("LastPrice") or {}   # respaldo: precio en la divisa del fondo
        if lp.get("Value") is not None:
            return (lp.get("Date") or "")[:10], round(float(lp["Value"]), 4)
    except Exception:
        pass
    return None, None


def _tp_returns(blocks):
    """{TimePeriod: Value} del primer bloque de una lista TrailingPerformance."""
    out = {}
    for tp in blocks or []:
        for r in tp.get("Return", []):
            p, v = r.get("TimePeriod"), r.get("Value")
            if p and p != "ClosePrice" and p not in out:
                try:
                    out[p] = float(v)
                except (TypeError, ValueError):
                    pass
        break
    return out


def parse_benchmark(js):
    """Indice de referencia: nombre + exceso (rent. fondo EUR - rent. indice EUR) por periodo.
    Devuelve (nombre, {ExcessM0:.., ExcessM12:.., ExcessM36:.., ExcessM60:..})."""
    try:
        d = js[0]
        b = d.get("Benchmark") or []
        if not b:
            return None, {}
        name = b[0].get("Name")
        idx = _tp_returns(b[0].get("TrailingPerformance"))
        fnd = _tp_returns(d.get("TrailingPerformance"))
        ex = {}
        for p in ("D1", "W1", "M1", "M3", "M6", "M0", "M12", "M36", "M60", "M120"):
            if p in fnd and p in idx:
                ex["Excess" + p] = round(fnd[p] - idx[p], 2)
        return name, ex
    except Exception:
        return None, {}


def build_holdings_changes(new_h, prev_h):
    """Compara carteras nueva vs anterior y guarda los cambios (entradas/salidas/±peso) por fondo."""
    import json as _json
    today = datetime.date.today().isoformat()
    path = os.path.join("data", "holdings_changes.json")
    ch = {}
    if os.path.exists(path):
        try:
            ch = _json.load(open(path, encoding="utf-8"))
        except Exception:
            ch = {}

    def nrm(s):
        return " ".join(str(s).lower().split())

    added = 0
    for isin, newl in new_h.items():
        prevl = prev_h.get(isin)
        if not prevl:
            continue  # sin cartera anterior con la que comparar
        pm = {nrm(x[1]): (float(x[0]), x[1]) for x in prevl}
        nm = {nrm(x[1]): (float(x[0]), x[1]) for x in newl}
        if set(pm) == set(nm) and all(abs(pm[k][0] - nm[k][0]) < 0.01 for k in pm):
            continue  # idéntica
        entered = sorted([{"n": nm[k][1], "w": round(nm[k][0], 2)} for k in nm if k not in pm],
                         key=lambda z: -z["w"])
        exited = sorted([{"n": pm[k][1], "w": round(pm[k][0], 2)} for k in pm if k not in nm],
                        key=lambda z: -z["w"])
        up, down = [], []
        for k in nm:
            if k in pm:
                delta = round(nm[k][0] - pm[k][0], 2)
                if delta >= 0.5:
                    up.append({"n": nm[k][1], "de": round(pm[k][0], 2), "a": round(nm[k][0], 2)})
                elif delta <= -0.5:
                    down.append({"n": nm[k][1], "de": round(pm[k][0], 2), "a": round(nm[k][0], 2)})
        if not (entered or exited or up or down):
            continue
        up.sort(key=lambda z: -(z["a"] - z["de"])); down.sort(key=lambda z: (z["a"] - z["de"]))
        rec = {"date": today, "entered": entered[:15], "exited": exited[:15], "up": up[:15], "down": down[:15]}
        lst = [r for r in ch.get(isin, []) if r.get("date") != today]
        lst.insert(0, rec)
        ch[isin] = lst[:12]  # tope 12 cambios por fondo
        added += 1
    with open(path, "w", encoding="utf-8") as fh:
        _json.dump(ch, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"OK: cambios de cartera -> data/holdings_changes.json ({added} fondos con cambios hoy, {len(ch)} con historial)")


def parse_holdings(js):
    """Todas las posiciones publicadas (nombre + peso %). Devuelve [[peso, nombre], ...] ordenado, o None."""
    try:
        hs = js[0]["Portfolios"][0].get("PortfolioHoldings", [])
        out = []
        for h in hs:
            w = h.get("Weighting")
            nm = h.get("SecurityName") or h.get("ExternalName") or h.get("Name")
            if w and nm:
                try:
                    out.append([round(float(w), 2), str(nm).strip()])
                except (TypeError, ValueError):
                    pass
        out.sort(key=lambda x: (-x[0], x[1]))
        return out or None
    except Exception:
        return None


def update_vl_history(vl_today):
    """Acumula el VL diario en data/vl_history.csv (fecha;Isin;VL_EUR), sin duplicar y con tope de dias."""
    path = os.path.join("data", "vl_history.csv")
    CAP = 1100  # ~3 años de dias habiles por fondo
    hist = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            rd = csv.reader(fh, delimiter=";")
            next(rd, None)
            for row in rd:
                if len(row) >= 3 and row[0] and row[1]:
                    hist.setdefault(row[1], {})[row[0]] = row[2]
    added = 0
    for isin, (dt, vl) in vl_today.items():
        if dt and vl is not None and dt not in hist.get(isin, {}):
            hist.setdefault(isin, {})[dt] = repr(vl)
            added += 1
    total = 0
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["fecha", "Isin", "VL_EUR"])
        for isin in sorted(hist):
            for dt in sorted(hist[isin])[-CAP:]:
                w.writerow([dt, isin, hist[isin][dt]])
                total += 1
    print(f"OK: VL diario -> {path} (+{added} nuevos, {total} filas totales)")
    return hist


def _bizdays(d1, d2):
    """Días hábiles (lun-vie) entre dos fechas ISO 'YYYY-MM-DD' (d1 < d2). Aprox: ignora festivos."""
    try:
        a = datetime.date.fromisoformat(d1[:10])
        b = datetime.date.fromisoformat(d2[:10])
    except Exception:
        return None
    if b <= a:
        return 0
    n, cur = 0, a
    step = datetime.timedelta(days=1)
    while cur < b:
        cur += step
        if cur.weekday() < 5:
            n += 1
    return n


def _freq_label(med):
    """Etiqueta de frecuencia a partir de la mediana de días hábiles entre VLs consecutivos."""
    if med is None:
        return ""
    if med <= 1.3:
        return "Diaria"
    if med <= 2.5:
        return "Cada 2 días"
    if med <= 4.5:
        return "Cada 3-4 días"
    if med <= 7.5:
        return "Semanal"
    if med <= 16:
        return "Quincenal"
    return "Mensual o menos"


def build_vl_lag(items, run_dt):
    """Mide el RETARDO DE PUBLICACIÓN del VL de cada fondo (T+1, T+2, T+3…): días hábiles entre
    la fecha del último VL y la fecha de ejecución. Bankinter/Allfunds NO declara la liquidación
    T+N en la API, así que se deduce observándolo. Para que la medida sea consistente, SOLO se
    registra en ejecuciones NOCTURNAS (>=20:00), cuando ya se ha publicado el VL del día; las
    ejecuciones matinales/de recuperación sesgarían el retardo, así que no cuentan.
    Acumula las últimas observaciones por fondo y guarda la MODA en data/vl_lag.json:
    {asof, funds:{isin:{tplus:<moda>, n:<nº noches>, last:<última fecha VL>, obs:[...]}}}"""
    import json as _json
    from collections import Counter as _C
    path = "data/vl_lag.json"
    prev = {}
    try:
        if os.path.exists(path):
            prev = (_json.load(open(path, encoding="utf-8")) or {}).get("funds", {})
    except Exception:
        prev = {}
    run_date = run_dt.date().isoformat()
    if run_dt.hour < 20:
        # No es ejecución nocturna: no medir (evita sesgo), pero conservar lo ya acumulado.
        try:
            with open(path, "w", encoding="utf-8") as fh:
                _json.dump({"asof": run_date, "funds": prev}, fh, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            pass
        print(f"vl_lag: ejecución no nocturna ({run_dt.hour}h) -> no se mide el retardo hoy")
        return prev
    out = {}
    for d in items:
        isin = d.get("Isin")
        vdt = d.get("VLDate")
        if not isin or not vdt:
            continue
        lag = _bizdays(vdt[:10], run_date)
        if lag is None:
            continue
        rec = prev.get(isin, {"obs": []})
        rec["obs"] = (rec.get("obs", []) + [lag])[-20:]  # últimas 20 noches
        c = _C(rec["obs"])
        rec["tplus"] = c.most_common(1)[0][0]
        rec["n"] = len(rec["obs"])
        rec["last"] = vdt[:10]
        out[isin] = rec
    try:
        with open(path, "w", encoding="utf-8") as fh:
            _json.dump({"asof": run_date, "funds": out}, fh, ensure_ascii=False, separators=(",", ":"))
        dist = _C(v["tplus"] for v in out.values())
        distxt = ", ".join(f"T+{k}:{dist[k]}" for k in sorted(dist))
        print(f"OK: retardo de publicación (T+N) -> data/vl_lag.json ({len(out)} fondos) [{distxt}]")
    except Exception as e:
        print("vl_lag.json fallo:", e)
    return out


def build_vl_frequency(hist, run_date):
    """Infiere la frecuencia de actualización del VL de cada fondo a partir de las fechas de VL
    acumuladas en vl_history (cuanto más histórico, más fiable). Escribe data/vl_freq.json:
    {isin: {med: <mediana días hábiles entre VLs>, label, n: <nº fechas>, last: <última fecha VL>,
            lag: <días hábiles de retardo del último VL vs fecha de ejecución>}}."""
    import json as _json
    import statistics as _st
    out = {}
    for isin, dvl in (hist or {}).items():
        dates = sorted(d for d in dvl if d)
        last = dates[-1] if dates else ""
        lag = _bizdays(last, run_date) if last else None
        med = None
        if len(dates) >= 3:  # al menos 2 huecos para una mediana con sentido
            gaps = []
            for i in range(1, len(dates)):
                g = _bizdays(dates[i - 1], dates[i])
                if g and g > 0:
                    gaps.append(g)
            if gaps:
                med = round(_st.median(gaps), 1)
        out[isin] = {"med": med, "label": _freq_label(med), "n": len(dates),
                     "last": last, "lag": lag}
    try:
        with open("data/vl_freq.json", "w", encoding="utf-8") as fh:
            _json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
        conf = sum(1 for v in out.values() if v["med"] is not None)
        print(f"OK: frecuencia VL -> data/vl_freq.json ({len(out)} fondos, {conf} con cadencia inferida)")
    except Exception as e:
        print("vl_freq.json fallo:", e)
    return out


WEEKLY_PERIODS = [1, 2, 3, 4, 5, 6, 8, 12]  # semanas ofrecidas en «Rankings por semanas»


def build_weekly_returns(hist, run_date):
    """Rentabilidad a N semanas (1-12) de cada fondo, calculada desde las fotos diarias de VL
    acumuladas en vl_history (la API no da serie diaria; se construye con el histórico propio).
    Para cada periodo busca el VL más cercano a 'hace N semanas' (tolerancia ±4 días).
    Escribe data/weekly_returns.json: {isin:{asof, w1, w2, ...}}. Los periodos sin histórico
    suficiente simplemente no aparecen (se van rellenando según pasan los días)."""
    import json as _json
    import datetime as _dt
    TOL = 4  # días de tolerancia para localizar el VL de referencia de cada periodo
    out = {}
    cov = {w: 0 for w in WEEKLY_PERIODS}
    for isin, dvl in (hist or {}).items():
        pts = []
        for d, v in dvl.items():
            try:
                pts.append((_dt.date.fromisoformat(d[:10]), float(v)))
            except Exception:
                pass
        if len(pts) < 2:
            continue
        pts.sort()
        last_d, last_v = pts[-1]
        if not last_v:
            continue
        rec = {"asof": last_d.isoformat()}
        for w in WEEKLY_PERIODS:
            target = last_d - _dt.timedelta(days=7 * w)
            best, bestdiff = None, None
            for d, v in pts:
                if d >= last_d or not v:
                    continue
                diff = abs((d - target).days)
                if diff <= TOL and (bestdiff is None or diff < bestdiff):
                    best, bestdiff = (d, v), diff
            if best:
                rec["w%d" % w] = round((last_v / best[1] - 1) * 100, 2)
                cov[w] += 1
        if len(rec) > 1:
            out[isin] = rec
    # span de histórico: mediana (por fondo) de días entre su VL más antiguo y el más reciente
    spans = []
    for dvl in (hist or {}).values():
        ds = sorted(d[:10] for d in dvl if d)
        if len(ds) >= 2:
            try:
                spans.append((_dt.date.fromisoformat(ds[-1]) - _dt.date.fromisoformat(ds[0])).days)
            except Exception:
                pass
    span_days = int(sorted(spans)[len(spans) // 2]) if spans else 0
    try:
        with open("data/weekly_returns.json", "w", encoding="utf-8") as fh:
            _json.dump({"asof": run_date, "periods": WEEKLY_PERIODS, "spanDays": span_days, "funds": out}, fh,
                       ensure_ascii=False, separators=(",", ":"))
        covtxt = ", ".join(f"{w}s:{cov[w]}" for w in WEEKLY_PERIODS)
        print(f"OK: rent. por semanas -> data/weekly_returns.json ({len(out)} fondos) [{covtxt}]")
    except Exception as e:
        print("weekly_returns.json fallo:", e)
    return out


def build_weekly_history(items, hist, top_n=40):
    """Histórico SEMANA A SEMANA: para cada semana ISO con datos, calcula el rendimiento de cada
    fondo en esa semana (VL al cierre de la semana / VL al cierre de la semana anterior) y guarda
    los mejores y peores. Se construye desde vl_history (las fotos diarias), así que se va
    rellenando semana a semana hasta ~52. Escribe data/weekly_history.json."""
    import json as _json
    import datetime as _dt
    meta = {d.get("Isin"): {"name": d.get("Name"), "cat": d.get("CategoryName"),
                            "cur": d.get("Currency"), "srri": d.get("SRRI")} for d in items}
    # serie por fondo: [(date, vl)] ordenada
    series = {}
    for isin, dvl in (hist or {}).items():
        pts = []
        for d, v in dvl.items():
            try:
                pts.append((_dt.date.fromisoformat(d[:10]), float(v)))
            except Exception:
                pass
        if pts:
            pts.sort()
            series[isin] = pts
    # todas las fechas de VL -> agrupar por semana ISO; fecha de referencia = último VL de la semana
    alldates = sorted({d for pts in series.values() for d, _ in pts})
    if len(alldates) < 2:
        try:
            _json.dump({"asof": "", "weeks": []}, open("data/weekly_history.json", "w"))
        except Exception:
            pass
        return []
    ref = {}  # (isoyear, isoweek) -> última fecha de esa semana
    for d in alldates:
        y, w, _ = d.isocalendar()
        k = (y, w)
        if k not in ref or d > ref[k]:
            ref[k] = d
    weeks_sorted = sorted(ref)  # de más antigua a más reciente

    def val_asof(pts, target):
        """último VL con fecha <= target y a no más de 6 días (evita usar VL rancio)."""
        best = None
        for d, v in pts:
            if d <= target:
                best = (d, v)
            else:
                break
        if best and (target - best[0]).days <= 6 and best[1]:
            return best[1]
        return None

    out_weeks = []
    for i in range(1, len(weeks_sorted)):
        (y, w) = weeks_sorted[i]
        end = ref[weeks_sorted[i]]
        prev_end = ref[weeks_sorted[i - 1]]
        rows = []
        for isin, pts in series.items():
            v_end = val_asof(pts, end)
            v_prev = val_asof(pts, prev_end)
            if v_end is not None and v_prev is not None and v_prev > 0:
                r = round((v_end / v_prev - 1) * 100, 2)
                m = meta.get(isin, {})
                rows.append({"isin": isin, "name": m.get("name"), "cat": m.get("cat"),
                             "cur": m.get("cur"), "srri": m.get("srri"), "ret": r})
        if len(rows) < 5:
            continue
        rows.sort(key=lambda x: x["ret"], reverse=True)
        out_weeks.append({
            "iso": f"{y}-W{w:02d}",
            "start": (end - _dt.timedelta(days=end.weekday())).isoformat(),
            "end": end.isoformat(),
            "prevEnd": prev_end.isoformat(),
            "n": len(rows),
            "top": rows[:top_n],
            "bottom": rows[-top_n:][::-1],
        })
    out_weeks.reverse()  # más reciente primero
    try:
        with open("data/weekly_history.json", "w", encoding="utf-8") as fh:
            _json.dump({"asof": alldates[-1].isoformat(), "weeks": out_weeks},
                       fh, ensure_ascii=False, separators=(",", ":"))
        print(f"OK: histórico semanal -> data/weekly_history.json ({len(out_weeks)} semanas con datos)")
    except Exception as e:
        print("weekly_history.json fallo:", e)
    return out_weeks


import re as _re
import unicodedata as _ud


def base_fund_key(name):
    """Clave de 'fondo base' para no contar dos clases del mismo fondo (acumulación/distribución,
    divisa, cubierto, letra de clase). Conserva palabras de estrategia (income, growth, value, cap…)
    para no fusionar fondos distintos."""
    s = _ud.normalize("NFD", (name or "").lower())
    s = "".join(c for c in s if not _ud.combining(c))
    s = _re.sub(r"\b(acc|accumulation|dist|distribution|hedged|hedge|hdg|hgd|unhedged|clase|class|shares?)\b", " ", s)
    s = _re.sub(r"\b(eur|usd|gbp|chf|jpy|sek|nok|dkk|aud|cad|pln|czk|huf|sgd|hkd|nzd|zar|euro|dollar|dllr|sterling|yen|h|hg|xh)\b", " ", s)
    s = _re.sub(r"\d+", " ", s)
    s = _re.sub(r"[^a-z ]", " ", s)
    s = _re.sub(r"\b[a-z]{1,2}\b", " ", s)
    return _re.sub(r"\s+", " ", s).strip() or (name or "")


def build_score_history(items):
    """Ranking multifactor (2 perfiles: rentabilidad y riesgo) por percentiles; guarda histórico
    en data/score_history.json y resume los cambios frente a la foto anterior."""
    import json as _json

    def num(x):
        try:
            return float(str(x).replace(",", ".")) if isinstance(x, str) else float(x)
        except (TypeError, ValueError):
            return None

    REQ = ["ReturnM36", "ReturnM12", "ReturnM60", "StandardDeviationM36", "MaxDrawdownM36",
           "SharpeM36", "SortinoM36", "AlphaM36", "InformationRatioM36", "TrackingErrorM36"]
    uni = [d for d in items if all(num(d.get(k)) is not None for k in REQ)]
    if len(uni) < 20:
        return
    for d in uni:
        r, dd = num(d.get("ReturnM36")), num(d.get("MaxDrawdownM36"))
        d["_calmar"] = (r / abs(dd)) if dd else 0.0

    def pctile(sv, v, better):
        n = len(sv); below = sum(1 for x in sv if x < v); eq = sum(1 for x in sv if x == v)
        p = 100 * (below + eq / 2) / n
        return (100 - p) if better == "low" else p

    def score(prof):
        cache = {k: sorted((num(d.get(k)) if k != "_calmar" else d["_calmar"]) for d in uni) for k, _, _ in prof}
        out = {}
        for d in uni:
            sw = ww = 0.0
            for k, b, w in prof:
                v = num(d.get(k)) if k != "_calmar" else d["_calmar"]
                sw += pctile(cache[k], v, b) * w; ww += w
            out[d.get("Isin")] = sw / ww
        return out

    RET = [("ReturnM36", "high", 3), ("ReturnM12", "high", 2), ("ReturnM60", "high", 1),
           ("AlphaM36", "high", 2), ("SharpeM36", "high", 1), ("InformationRatioM36", "high", 1)]
    RISK = [("StandardDeviationM36", "low", 3), ("MaxDrawdownM36", "high", 3), ("SharpeM36", "high", 2),
            ("SortinoM36", "high", 1), ("TrackingErrorM36", "low", 1), ("_calmar", "high", 1)]

    def toplist(sc, n=20):
        ordered = sorted(uni, key=lambda d: sc[d.get("Isin")], reverse=True)
        order, seen = [], set()
        for d in ordered:  # una sola clase por fondo (la de mayor score)
            k = base_fund_key(d.get("Name"))
            if k in seen:
                continue
            seen.add(k); order.append(d)
            if len(order) >= n:
                break
        return [{"isin": d.get("Isin"), "name": d.get("Name"), "cat": d.get("CategoryName"), "cur": d.get("Currency"),
                 "score": round(sc[d.get("Isin")], 1), "r36": num(d.get("ReturnM36")), "ytd": num(d.get("ReturnM0")),
                 "r12": num(d.get("ReturnM12")), "vol": num(d.get("StandardDeviationM36")), "dd": num(d.get("MaxDrawdownM36")),
                 "sharpe": num(d.get("SharpeM36")), "alpha": num(d.get("AlphaM36")), "ter": num(d.get("TER")),
                 "srri": d.get("SRRI"), "invmin": num(d.get("InitialPurchase")),
                 "pctrv": num(d.get("PctRV")), "pctrf": num(d.get("PctRF"))} for d in order]

    ret_l, risk_l = toplist(score(RET)), toplist(score(RISK))
    today = datetime.date.today().isoformat()
    path = os.path.join("data", "score_history.json")
    hist = {}
    if os.path.exists(path):
        try:
            hist = _json.load(open(path, encoding="utf-8"))
        except Exception:
            hist = {}
    prev_dates = sorted([k for k in hist if k < today])
    prev = hist.get(prev_dates[-1]) if prev_dates else None

    def summary(newl, prevl):
        if not prevl:
            return "Primer registro del ranking."
        newis = [x["isin"] for x in newl]; previs = [x["isin"] for x in prevl]
        entr = [x for x in newl if x["isin"] not in previs][:5]
        drop = [p for p in prevl if p["isin"] not in newis][:5]
        prank = {p["isin"]: i for i, p in enumerate(prevl)}
        moves = [(prank[x["isin"]] - i, x["name"], prank[x["isin"]] + 1, i + 1)
                 for i, x in enumerate(newl) if x["isin"] in prank and prank[x["isin"]] != i]
        ups = sorted([m for m in moves if m[0] > 0], reverse=True)[:2]
        downs = sorted([m for m in moves if m[0] < 0])[:2]
        parts = []
        if newl[0]["isin"] != prevl[0]["isin"]:
            parts.append(f"Nuevo nº1: {newl[0]['name']} (antes {prevl[0]['name']}).")
        if entr:
            parts.append("Entran: " + ", ".join(x["name"] for x in entr) + ".")
        if drop:
            parts.append("Salen: " + ", ".join(p["name"] for p in drop) + ".")
        if ups:
            parts.append("Suben: " + ", ".join(f"{m[1]} ({m[2]}º→{m[3]}º)" for m in ups) + ".")
        if downs:
            parts.append("Bajan: " + ", ".join(f"{m[1]} ({m[2]}º→{m[3]}º)" for m in downs) + ".")
        return " ".join(parts) if parts else "Sin cambios en el top."

    hist[today] = {"date": today, "universe": len(uni),
                   "ret": {"list": ret_l, "summary": summary(ret_l, prev["ret"]["list"] if prev else None)},
                   "risk": {"list": risk_l, "summary": summary(risk_l, prev["risk"]["list"] if prev else None)}}
    for k in sorted(hist)[:-90]:  # tope ~90 fotos
        del hist[k]
    with open(path, "w", encoding="utf-8") as fh:
        _json.dump(hist, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"OK: score_history {today} -> data/score_history.json ({len(hist)} fotos, universo {len(uni)})")

    # --- Persistencia acumulada en el TOP20 (nº de veces = absoluto; % sobre ejecuciones = relativo) ---
    # Contador acumulado SIN tope temporal, para trackear a largo plazo cuántas veces se repite cada fondo.
    fpath = os.path.join("data", "top20_frequency.json")
    freq = {"runs": 0, "first": today, "last": None, "ret": {}, "risk": {}}
    if os.path.exists(fpath):
        try:
            freq = _json.load(open(fpath, encoding="utf-8"))
        except Exception:
            freq = {"runs": 0, "first": today, "last": None, "ret": {}, "risk": {}}
    freq.setdefault("ret", {}); freq.setdefault("risk", {})
    if freq.get("last") != today:  # idempotente: no cuenta dos veces si se relanza el mismo día
        freq["runs"] = int(freq.get("runs", 0)) + 1
        freq.setdefault("first", today); freq["last"] = today
        for bucket, lst in (("ret", ret_l), ("risk", risk_l)):
            b = freq[bucket]
            for x in lst:
                isin = x["isin"]
                e = b.get(isin) or {"count": 0, "first": today}
                e["count"] = int(e.get("count", 0)) + 1
                e["name"] = x["name"]; e["cat"] = x["cat"]; e["cur"] = x.get("cur")
                e["score"] = x.get("score"); e["last"] = today; e.setdefault("first", today)
                b[isin] = e
        with open(fpath, "w", encoding="utf-8") as fh:
            _json.dump(freq, fh, ensure_ascii=False, separators=(",", ":"))
        print(f"OK: top20_frequency -> {fpath} ({freq['runs']} ejecuciones, "
              f"{len(freq['ret'])} fondos RENT / {len(freq['risk'])} RIESGO)")


def build_periods(items, hist):
    """Fotos por periodo (semana/mes/trimestre/YTD): rankings + resumen factual. Acumula en data/periods.json."""
    import json as _json
    import statistics
    import math
    from collections import Counter
    today = datetime.date.today()
    iso = today.isocalendar()

    def num(x):
        try:
            return float(str(x).replace(",", "."))
        except (TypeError, ValueError):
            return None

    def in_bucket(ptype, d):
        if ptype == "semana":
            wd = d.isocalendar()
            return (wd[0], int(wd[1])) == (iso[0], int(iso[1]))
        if ptype == "mes":
            return (d.year, d.month) == (today.year, today.month)
        if ptype == "trimestre":
            return d.year == today.year and (d.month - 1) // 3 == (today.month - 1) // 3
        return d.year == today.year  # ytd

    def bkey(ptype):
        if ptype == "semana":
            return f"{iso[0]}-W{int(iso[1]):02d}"
        if ptype == "mes":
            return f"{today.year}-{today.month:02d}"
        if ptype == "trimestre":
            return f"{today.year}-Q{(today.month - 1) // 3 + 1}"
        return f"{today.year}"  # ytd

    def pvol(isin, ptype):
        """Volatilidad realizada del periodo (anualizada %) con los VL diarios de ese periodo, o None."""
        pts = []
        for dt, vl in sorted((hist.get(isin) or {}).items()):
            try:
                y, m, dd = map(int, dt.split("-"))
                date = datetime.date(y, m, dd)
            except Exception:
                continue
            if in_bucket(ptype, date):
                v = num(vl)
                if v is not None:
                    pts.append(v)
        if len(pts) < 4:
            return None
        rets = [pts[i] / pts[i - 1] - 1 for i in range(1, len(pts)) if pts[i - 1]]
        if len(rets) < 3:
            return None
        try:
            return round(statistics.pstdev(rets) * math.sqrt(252) * 100, 2)
        except statistics.StatisticsError:
            return None

    def top_cats(lst, n=3):
        return [f"{k} ({v})" for k, v in Counter(r["cat"] for r in lst if r["cat"]).most_common(n)]

    def snapshot(ptype, retk, plabel):
        rows = []
        for d in items:
            r = num(d.get(retk))
            if r is None:
                continue
            rows.append({"isin": d.get("Isin", ""), "name": d.get("Name", ""), "cat": d.get("CategoryName", ""),
                         "gac": d.get("GlobalAssetClass", ""), "cur": d.get("Currency", ""), "w1": r,
                         "wvol": pvol(d.get("Isin", ""), ptype), "v1y": num(d.get("StandardDeviationM12"))})
        if not rows:
            return None
        up = sorted(rows, key=lambda r: r["w1"], reverse=True)[:15]
        down = sorted(rows, key=lambda r: r["w1"])[:15]
        real = [r for r in rows if r["wvol"] is not None]
        if len(real) >= 10:
            vol = sorted(real, key=lambda r: r["wvol"], reverse=True)[:15]
            vol_metric, vol_label = "wvol", f"Volat. {plabel.lower()} (anualiz.)"
        else:
            vol = sorted([r for r in rows if r["v1y"] is not None], key=lambda r: r["v1y"], reverse=True)[:15]
            vol_metric, vol_label = "v1y", "Volat. 1A (aprox.)"
        breadth = round(100 * sum(1 for r in rows if r["w1"] > 0) / len(rows))
        lead, lag = top_cats(up), top_cats(down)
        avg_up = round(statistics.mean([r["w1"] for r in up]), 2) if up else 0
        avg_dn = round(statistics.mean([r["w1"] for r in down]), 2) if down else 0
        summary = (f"[{plabel}] Amplitud: {breadth}% de fondos en positivo. "
                   f"Lideran {', '.join(lead) if lead else 'n/d'} (media del top +{avg_up}%). "
                   f"Mayores caidas: {', '.join(lag) if lag else 'n/d'} (media del top {avg_dn}%). "
                   f"Volatilidad ordenada por {vol_label.lower()}.")
        return {"updated": today.isoformat(), "breadth": breadth, "summary": summary,
                "up": up, "down": down, "vol": vol, "volMetric": vol_metric, "volLabel": vol_label}

    PERIODS = [("semana", "ReturnW1", "Semana", 104), ("mes", "ReturnM1", "Mes", 36),
               ("trimestre", "ReturnM3", "Trimestre", 20), ("ytd", "ReturnM0", "YTD", 12)]
    path = os.path.join("data", "periods.json")
    allp = {}
    if os.path.exists(path):
        try:
            allp = _json.load(open(path, encoding="utf-8"))
        except Exception:
            allp = {}
    for ptype, retk, plabel, cap in PERIODS:
        entry = snapshot(ptype, retk, plabel)
        if entry is None:
            continue
        allp.setdefault(ptype, {})[bkey(ptype)] = entry
        for k in sorted(allp[ptype])[:-cap]:
            del allp[ptype][k]
    with open(path, "w", encoding="utf-8") as fh:
        _json.dump(allp, fh, ensure_ascii=False, separators=(",", ":"))
    print("OK: rankings por periodo -> data/periods.json (" + ", ".join(f"{k}:{len(v)}" for k, v in allp.items()) + ")")


def parse_series(js):
    """Rentabilidad Nav por ano natural (para la grafica de evolucion). Devuelve {'y':[...], 'r':[...]} o None."""
    try:
        hps = js[0].get("HistoricalPerformanceSeries", [])
        ann = [x for x in hps if x.get("Frequency") == "Y" and x.get("TimePeriod") == "M12"
               and x.get("ReturnType") == "Nav"]
        if not ann:
            return None
        ys, rs = [], []
        for p in sorted(ann[0].get("Return", []), key=lambda z: z.get("Date", "")):
            try:
                ys.append(int(p["Date"][:4]))
                rs.append(round(float(p["Value"]), 2))
            except (TypeError, ValueError, KeyError):
                pass
        return {"y": ys, "r": rs} if ys else None
    except Exception:
        return None


def add(data):
    for f in data or []:
        k = f.get("SecId") or f.get("Isin")
        if k:
            funds[k] = f


def multisort(filters):
    # bucket con mas de 50 y sin mas dimensiones por las que partir: union por varios ordenes
    for field in SORTS:
        for d in ("desc", "asc"):
            j = api({**base(filters), "sortBy": f"{field}.{d}"})
            if j:
                add(j["data"])
            time.sleep(0.25)


def fetch(filters, dims, DIMS):
    j = api(base(filters))
    if not j:
        return
    n = j.get("count", 0)
    if n == 0:
        return
    if n <= PAGE:
        add(j["data"])
        return
    if not dims:
        multisort(filters)
        return
    dim = dims[0]
    for v in DIMS[dim]:
        fetch({**filters, dim: v}, dims[1:], DIMS)


def euribor_json():
    """Descarga EURIBOR (mensual), €STR (diario) y tipos BCE de la API del BCE -> dict."""
    ECB = "https://data-api.ecb.europa.eu/service/data"
    import csv as _csv, io as _io
    def ser(res, key, n=60):
        try:
            r = requests.get(f"{ECB}/{res}/{key}?lastNObservations={n}&format=csvdata",
                             headers={"User-Agent": "euribor-tracker/1.0", "Accept": "text/csv"}, timeout=25)
            if r.status_code != 200:
                return []
            out = []
            for row in _csv.DictReader(_io.StringIO(r.text)):
                try:
                    out.append((row.get("TIME_PERIOD"), float(row.get("OBS_VALUE"))))
                except (TypeError, ValueError):
                    pass
            return out
        except Exception:
            return []
    EUR = {"1M": "M.U2.EUR.RT.MM.EURIBOR1MD_.HSTA", "3M": "M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA",
           "6M": "M.U2.EUR.RT.MM.EURIBOR6MD_.HSTA", "12M": "M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA"}
    eur = {t: ser("FM", k, 48) for t, k in EUR.items()}
    estr = ser("EST", "B.EU000A2X2A25.WT", 90)
    dfr = ser("FM", "D.U2.EUR.4F.KR.DFR.LEV", 5)
    mro = ser("FM", "D.U2.EUR.4F.KR.MRR_FR.LEV", 5)
    last = lambda x: x[-1][1] if x else None
    prev = lambda x: x[-2][1] if len(x) > 1 else None
    months = [d for d, _ in eur["12M"]]
    hist = [{"month": m, **{t: dict(eur[t]).get(m) for t in EUR}} for m in months]
    return {
        "updated": estr[-1][0] if estr else (months[-1] if months else ""),
        "euriborMonth": eur["12M"][-1][0] if eur["12M"] else "",
        "latest": {t: last(eur[t]) for t in EUR}, "prev": {t: prev(eur[t]) for t in EUR},
        "estr": last(estr), "estrDate": estr[-1][0] if estr else "",
        "dfr": last(dfr), "mro": last(mro),
        "history": hist, "estrHistory": [{"date": d, "v": v} for d, v in estr[-60:]],
    }


def main():
    # Fecha/hora del INICIO del raspado. Fijarla aquí (y no tras el descubrimiento) evita que un
    # raspado lento que cruce la medianoche se etiquete con el día siguiente (bug del 2026-09-09).
    now = datetime.datetime.now()
    hoy = now.date().isoformat()
    sello = now.strftime("%Y-%m-%d_%H%M")  # fecha+hora para el nombre del fichero histórico
    DIMS = {
        "CurrencyId": [x["id"] for x in ids("currencies")],
        "KID_SRI": ["1", "2", "3", "4", "5", "6", "7"],
        "DomicileId": [x["id"] for x in ids("domiciles")],
    }
    gac = {x["id"]: x["name"] for x in ids("global-asset-classes")}
    cats = ids("categories")
    print(f"{len(cats)} categorias; recorriendo...")
    for i, c in enumerate(cats, 1):
        if time_left() <= 60:  # deja al menos ~1 min para escribir ficheros
            print(f"AVISO: tope de tiempo en descubrimiento (cat {i}/{len(cats)}); sigo con {len(funds)} fondos.")
            break
        fetch({"CategoryId": c["id"]}, ["CurrencyId", "KID_SRI", "DomicileId"], DIMS)
        if i % 25 == 0:
            print(f"  {i}/{len(cats)} categorias, {len(funds)} fondos acumulados")
        time.sleep(0.2)

    if not funds:
        print("ERROR: no se ha descargado ningun fondo (posible cambio en la API).")
        sys.exit(1)

    cols = [
        # --- Identificación / General ---
        "Isin", "Name", "LegalName", "ProviderCompanyName", "GlobalAssetClass",
        "GlobalCategoryName", "CategoryName", "InvestmentType", "Currency", "DomicileName",
        "SRRI", "StarRatingM255", "TER", "InitialPurchase", "UCITS", "IndexFund", "InceptionDate",
        "CutOffTime", "TimeHorizon",  # hora de corte de ordenes (HH:MM) y horizonte recomendado (años)
        "VL", "VLDate",  # valor liquidativo mas reciente (EUR) y su fecha
        # --- Rent. Acumuladas ---
        "ReturnD1", "ReturnW1", "ReturnM1", "ReturnM3", "ReturnM6",
        "ReturnM0", "ReturnM12", "ReturnM36", "ReturnM60", "ReturnM120",
        # --- Rent. Anuales (YR_1 = año completo más reciente) ---
        "YR_ReturnM12_1", "YR_ReturnM12_2", "YR_ReturnM12_3", "YR_ReturnM12_4",
        "YR_ReturnM12_5", "YR_ReturnM12_6", "YR_ReturnM12_7",
        # --- Cartera ---
        "EquityStyleBox", "BondStyleBox", "AverageMarketCapital", "PERatio", "PBRatio",
        "PSRatio", "DividendYield", "AverageCreditQuality", "EffectiveMaturity",
        # --- Ratios (3 años) ---
        "R2M36", "InformationRatioM36", "TrackingErrorM36",
        # --- Alpha / Beta por periodo (vs indice de referencia; 1/3/5/10 años) ---
        "AlphaM12", "AlphaM36", "AlphaM60", "AlphaM120",
        "BetaM12", "BetaM36", "BetaM60", "BetaM120",
        # --- Indice de referencia y exceso (rent. fondo - rent. indice) por periodo ---
        "BenchmarkName",
        "ExcessD1", "ExcessW1", "ExcessM1", "ExcessM3", "ExcessM6",
        "ExcessM0", "ExcessM12", "ExcessM36", "ExcessM60", "ExcessM120",
        # --- Sharpe / Sortino por periodo (1/3/5/10 años) ---
        "SharpeM12", "SharpeM36", "SharpeM60", "SharpeM120",
        "SortinoM12", "SortinoM36", "SortinoM60", "SortinoM120",
        # --- Riesgo: volatilidad y drawdown por periodo (1/3/5/10 años) ---
        "MorningstarRiskM255",
        "StandardDeviationM12", "StandardDeviationM36", "StandardDeviationM60", "StandardDeviationM120",
        "MaxDrawdownM12", "MaxDrawdownM36", "MaxDrawdownM60", "MaxDrawdownM120",
        # --- Comisiones ---
        "OngoingCostActual", "ManagementFee", "PerformanceFeeCharged",
        "MaxFrontEndLoad", "MaxRedemptionFee", "TransactionFeeActual", "CustodianFee",
        # --- Cuartiles Morningstar por periodo (1 = mejor de su categoria .. 4 = peor) ---
        "QuartileW1", "QuartileM1", "QuartileM3", "QuartileM6", "QuartileM0",
        "QuartileM12", "QuartileM36", "QuartileM60", "QuartileM120",
        # --- Derivados calculados por nosotros ---
        "CalmarM12", "CalmarM36", "CalmarM60", "CalmarM120", "YearsPositivePct", "WorstYear", "BeatCat",
        # --- Distribucion de activos y pignoracion (garantia del credito) ---
        "PctRV", "PctRF", "PctLiq", "PctOtros",
        "TipoPignor", "PignCobertura", "PignSalvaguarda", "PignReposicion", "FichaURL",
        # --- Origen del dato: "Bankinter" (API) o "quefondos"/"FT" (fondos solo-ABANCA) ---
        "Fuente",
    ]

    def fnum(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    def truthy(x):
        return x in (True, "True", "true", 1, "1")

    items = []
    for f in funds.values():
        d = dict(f)
        d["GlobalAssetClass"] = gac.get(d.get("GlobalAssetClassId"), "")
        # SRRI/SRI: Bankinter muestra el SRI del KID PRIIPs (1-7), NO el SRRI antiguo de Morningstar.
        # El campo "SRRI" de la lista es el viejo (colectado, por volatilidad, a veces desactualizado);
        # usamos KID_SRI, que es el indicador oficial vigente. (Se refina luego con el del snapshot.)
        _kid = str(d.get("KID_SRI") or "").strip()
        d["SRRI"] = _kid if _kid not in ("", "0", "None") else d.get("SRRI")
        d["TER"] = d.get("OngoingCostActual") or d.get("ExpenseRatio") or ""  # gastos corrientes reales
        # Calmar 3A = rentabilidad anualizada 3A / |maxima caida 3A|
        r36, dd36 = fnum(d.get("ReturnM36")), fnum(d.get("MaxDrawdownM36"))
        d["CalmarM36"] = round(r36 / abs(dd36), 2) if (r36 is not None and dd36) else ""
        # Consistencia con los 7 anos naturales
        yrs = [fnum(d.get(f"YR_ReturnM12_{i}")) for i in range(1, 8)]
        yrs = [y for y in yrs if y is not None]
        d["YearsPositivePct"] = round(100 * sum(1 for y in yrs if y > 0) / len(yrs)) if yrs else ""
        d["WorstYear"] = round(min(yrs), 2) if yrs else ""
        # Batio a su categoria en X de Y periodos de rentabilidad (1/3/5/10 anos)
        flags = [d.get(k) for k in ("ReturnM12GreaterThanCategory", "ReturnM36GreaterThanCategory",
                                    "ReturnM60GreaterThanCategory", "ReturnM120GreaterThanCategory")]
        tot = sum(1 for x in flags if x not in (None, "", "null"))
        beat = sum(1 for x in flags if truthy(x))
        d["BeatCat"] = f"{beat}/{tot}" if tot else ""
        items.append(d)
    items.sort(key=lambda d: (str(d.get("GlobalAssetClass", "")), str(d.get("CategoryName", "")), str(d.get("Name", ""))))

    # ---- Snapshot por fondo (1 peticion): distribucion RV/RF + serie anual para las graficas ----
    # Se pide a TODOS los fondos (necesario para la grafica de evolucion). Encarece la ejecucion
    # (~2.700 peticiones) pero mantiene los datos frescos a diario, segun lo elegido.
    print(f"Descargando snapshot de {len(items)} fondos (RV/RF + serie + riesgo + VL)...")
    series = {}
    vl_today = {}
    holdings = {}
    prev_holdings = {}  # cartera de la ejecucion anterior (para detectar cambios)
    try:
        import json as _json
        _p = os.path.join("data", "holdings.json")
        if os.path.exists(_p):
            prev_holdings = _json.load(open(_p, encoding="utf-8"))
    except Exception:
        prev_holdings = {}
    for i, d in enumerate(items, 1):
        if time_left() <= 0:
            print(f"AVISO: alcanzado el tope de tiempo ({MAX_RUN_SECONDS//60} min) en el fondo {i}/{len(items)}; "
                  f"escribo lo obtenido hasta aqui y continuo con los ficheros.")
            break
        isin = d.get("Isin", "")
        js = snapshot_json(isin) if isin else None
        if js:
            rv, rf, liq, ot = parse_alloc(js)
            if rv is not None:
                d["PctRV"] = rv
            if rf is not None:
                d["PctRF"] = rf
            if liq is not None:
                d["PctLiq"] = liq
            if ot is not None:
                d["PctOtros"] = ot
            for k, v in parse_risk(js).items():  # volatilidad, drawdown, Sharpe, Sortino (EUR) por periodo
                d[k] = v
            _sri = parse_sri(js)  # SRI del KID/Mifid (el que muestra Bankinter), con fecha -> el más fiable
            if _sri:
                d["SRRI"] = _sri
            _cust = js[0].get("Custom") or {}
            _cut = _cust.get("CustomCutOffTime")
            if _cut:
                d["CutOffTime"] = str(_cut)[:5]  # hora de corte de órdenes (HH:MM)
            _th = (js[0].get("Mifid") or {}).get("TimeHorizon")
            if _th not in (None, ""):
                d["TimeHorizon"] = str(_th)  # horizonte de inversión recomendado (años)
            vdt, vvl = parse_vl(js)  # VL del dia (EUR) -> serie diaria propia acumulada
            if vdt and vvl is not None:
                d["VL"] = vvl
                d["VLDate"] = vdt
                vl_today[isin] = (vdt, vvl)
            # Calmar por periodo = rent. anualizada / |max drawdown| (usando el drawdown EUR de la ficha)
            for P, retk in (("M12", "ReturnM12"), ("M36", "ReturnM36"), ("M60", "ReturnM60"), ("M120", "ReturnM120")):
                dd, rr = fnum(d.get("MaxDrawdown" + P)), fnum(d.get(retk))
                if rr is not None and dd:
                    d["Calmar" + P] = round(rr / abs(dd), 2)
            ser = parse_series(js)
            if ser:
                ser["ytd"] = d.get("ReturnM0", "")
                series[isin] = ser
            hold = parse_holdings(js)  # cartera completa (todas las posiciones + pesos)
            if hold:
                holdings[isin] = hold
            bname, bex = parse_benchmark(js)  # indice de referencia + exceso vs indice
            if bname:
                d["BenchmarkName"] = bname
            for k, v in bex.items():
                d[k] = v
        if i % 100 == 0:
            print(f"  {i}/{len(items)} snapshots, {len(series)} con serie")
        time.sleep(0.12)

    def classify(d):
        gac = d.get("GlobalAssetClass", "")
        rv, rf = fnum(d.get("PctRV")), fnum(d.get("PctRF"))
        if gac == "Equity":
            return "Renta Variable", 166, 140, 150
        if gac == "Fixed Income":
            return "Renta Fija", 133, 120, 125
        if gac == "Capital Preservation":
            return "Monetario/RF defensivo", 133, 120, 125
        if rv is not None and rv > 50:
            return "Renta Variable (>50% RV)", 166, 140, 150
        if rf is not None and rf > 50:
            return "Mixto RF>50%", 133, 133, 125
        if rv is not None or rf is not None:
            return "Revisar (RV/RF <=50%)", "", "", ""
        return "Revisar (sin datos)", "", "", ""

    for d in items:
        t, cob, sal, rep = classify(d)
        d["TipoPignor"] = t
        d["PignCobertura"] = cob
        d["PignSalvaguarda"] = sal
        d["PignReposicion"] = rep
        d["FichaURL"] = ("https://bancaonline.bankinter.com/resources/allfundssheets-enmenm/es/?isin="
                         + d.get("Isin", "") + "&language=es&currency=EUR&channel=nbol")

    for d in items:
        d.setdefault("Fuente", "Bankinter")
    rows = [[d.get(k, "") for k in cols] for d in items]

    # ---- Fondos SOLO-ABANCA (no están en la API de Bankinter): VL diario vía quefondos/FT ----
    # Aditivo y AISLADO: cualquier fallo aquí NO debe impedir guardar la foto de Bankinter.
    try:
        import abanca_collector
        ab_rows, ab_stats = abanca_collector.collect(fecha=hoy, log=lambda m: print("[abanca]", m))
        for ar in ab_rows:
            ar.setdefault("Fuente", "quefondos")
            rows.append([ar.get(k, "") for k in cols])
            vdt, vvl = ar.get("VLDate"), ar.get("VL")
            if vdt and vvl is not None:
                vl_today[ar["Isin"]] = (vdt, vvl)
        print(f"OK: +{len(ab_rows)} fondos solo-ABANCA "
              f"(quefondos={ab_stats['quefondos']}, FT={ab_stats['FT']}, "
              f"sin fuente={len(ab_stats['miss'])}: {ab_stats['miss']})")
    except Exception as e:
        print(f"AVISO: bloque solo-ABANCA falló (la foto de Bankinter NO se ve afectada): {e}")

    os.makedirs("data/history", exist_ok=True)
    for path in ("data/fondos_latest.csv", f"data/history/fondos_{sello}.csv"):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(cols + ["fecha"])
            for r in rows:
                w.writerow(r + [hoy])
    print(f"OK: {len(rows)} fondos -> data/fondos_latest.csv ({hoy})")

    # ---- Serie historica anual (para graficas de evolucion en el comparador) ----
    try:
        import json as _json
        with open("data/series.json", "w", encoding="utf-8") as fh:
            _json.dump(series, fh, ensure_ascii=False, separators=(",", ":"))
        print(f"OK: serie anual de {len(series)} fondos -> data/series.json")
    except Exception as e:
        print("series.json fallo:", e)

    # ---- Cartera completa (todas las posiciones + pesos) ----
    try:
        import json as _json
        with open("data/holdings.json", "w", encoding="utf-8") as fh:
            _json.dump(holdings, fh, ensure_ascii=False, separators=(",", ":"))
        npos = sum(len(v) for v in holdings.values())
        print(f"OK: holdings de {len(holdings)} fondos ({npos} posiciones) -> data/holdings.json")
    except Exception as e:
        print("holdings.json fallo:", e)

    # ---- Cambios de cartera (diff vs ejecucion anterior) ----
    try:
        build_holdings_changes(holdings, prev_holdings)
    except Exception as e:
        print("holdings_changes fallo:", e)

    # ---- VL diario acumulado (serie propia, se va construyendo dia a dia) ----
    try:
        hist = update_vl_history(vl_today)
        build_vl_frequency(hist, hoy)  # frecuencia de actualización del VL por fondo (se afina con los días)
        build_vl_lag(items, now)  # retardo de publicación T+N por fondo (solo mide en runs nocturnos >=20h)
        build_weekly_returns(hist, hoy)  # rentabilidad a 1-12 semanas desde las fotos diarias (se afina con los días)
        build_weekly_history(items, hist)  # histórico semana a semana de los mejores/peores fondos
        build_periods(items, hist)  # rankings por periodo (semana/mes/trimestre/YTD)
        build_score_history(items)  # histórico de rankings multifactor (2 perfiles) + cambios
    except Exception as e:
        print("vl_history/weekly fallo:", e)

    # ---- EURIBOR / tipos (BCE) ----
    try:
        import json as _json
        eu = euribor_json()
        with open("data/euribor.json", "w", encoding="utf-8") as fh:
            _json.dump(eu, fh, ensure_ascii=False)
        print(f"OK: EURIBOR 12M = {eu['latest'].get('12M')} ({eu.get('euriborMonth')}) -> data/euribor.json")
    except Exception as e:
        print("EURIBOR fallo:", e)
    # NOTA privacidad: los datos del credito (capital/intereses) NO se guardan aqui ni se suben al repo.
    # Se editan en la web y se quedan en tu navegador (localStorage). Ver data/intereses_reales.csv en .gitignore.


if __name__ == "__main__":
    main()
