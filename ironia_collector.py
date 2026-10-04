#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Foto diaria del universo de fondos de IronIA (~27.000 clases), tercera fuente del panel.

Fuente: API pública del buscador de IronIA (storeironia.azure-api.net), sin login:
  /funds?available=true|false&class_category=false   catálogo: nombre, gestora, categoría,
                                                     comisiones, clase limpia, puntos IronIA…
  /FundsWithRatiosBySubCategory?ratio=X&subCategory=Y métricas de IronIA por fondo a
                                                     1m/3m/6m/1a…5a (+ la de su índice)
La API NO expone el VL diario (la propia ficha de IronIA no lo carga), así que la foto son
las métricas.

Salida (PRIVADA, gitignored: son datos de IronIA/Allfunds, no para republicar):
  data/ironia/ironia_latest.csv                 foto más reciente (delimitador ';')
  data/ironia/history/ironia_<fecha>.csv.gz     una foto por día

Uso:  ./venv/bin/python ironia_collector.py
"""
import csv, datetime, gzip, io, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor

import requests

DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(DIR, "data", "ironia")
HIST = os.path.join(OUT, "history")
API = "https://storeironia.azure-api.net"
HDRS = {"User-Agent": "Mozilla/5.0 (fondos-tracker, uso personal)", "Origin": "https://store.ironia.tech",
        "Accept": "application/json"}
PAGE = 200
WORKERS = 3
MIN_FUNDS = 15000  # por debajo, la foto se considera incompleta y no se guarda

# métrica de IronIA -> (prefijo de columna, periodos, escala)
METRICS = {
    "linear_return": ("ret", ["1m", "3m", "6m", "1y", "2y", "3y", "4y", "5y"], 100),
    "volatility":    ("vol", ["1y", "3y", "5y"], 100),
    "sharpe":        ("sharpe", ["1y", "3y", "5y"], 1),
    "sortino":       ("sortino", ["3y"], 1),
    "max_drawdown":  ("mdd", ["1y", "3y", "5y"], 100),
    "alpha":         ("alpha", ["3y"], 100),
    "beta":          ("beta", ["3y"], 1),
}
BENCH = [("linear_return", p) for p in ("1y", "3y", "5y")]  # rentabilidad del índice de la categoría

META = [("isin", "isin"), ("name", "name"), ("family", "family"), ("manager", "manager"),
        ("category", "category"), ("subcategory", "subcategory"), ("ms_cat", "morningStarCategoryId"),
        ("currency", "currency"), ("available", "available"), ("clean", "cleanShare"),
        ("hedged", "currencyHedge"), ("income", "income"), ("indexed", "indexed"),
        ("switchable", "switchable"), ("ucits", "ucits"), ("complex", "complexity"),
        ("ongoing", "ongoingCharges"), ("mgmt_fee", "managementFee"), ("perf_fee", "performanceFee"),
        ("rebate", "rebate"), ("min_initial", "minimumInitialInvestment"), ("score", "averageScore"),
        ("benchmark", "benchmark")]

s = requests.Session()
s.headers.update(HDRS)


def get(path, params=None, tries=4):
    for k in range(tries):
        try:
            r = s.get(API + path, params=params, timeout=(10, 90))
            if r.status_code == 200:
                return r.json()
            if r.status_code in (400, 404):
                return None
        except (requests.RequestException, ValueError):
            pass
        time.sleep(2 * (k + 1))
    return None


def catalog():
    funds = {}
    for avail in ("true", "false"):
        first = get("/funds", {"count": PAGE, "page": 0, "available": avail, "class_category": "false"})
        if not first:
            raise RuntimeError(f"catálogo available={avail}: sin respuesta")
        pages = (first["total"] + PAGE - 1) // PAGE
        res = [first] + [None] * (pages - 1)

        def one(p):
            return p, get("/funds", {"count": PAGE, "page": p, "available": avail, "class_category": "false"})
        with ThreadPoolExecutor(WORKERS) as pool:
            for p, j in pool.map(one, range(1, pages)):
                res[p] = j
        missing = [p for p, j in enumerate(res) if not j]
        if missing:
            raise RuntimeError(f"catálogo available={avail}: faltan páginas {missing}")
        for j in res:
            for f in j.get("results", []):
                if f.get("isin"):
                    funds[f["isin"]] = f
        print(f"  catálogo available={avail}: {pages} páginas, {len(funds)} clases acumuladas", flush=True)
    return funds


def ratios(subcats):
    """{isin: {col: valor}} con las métricas de METRICS para todas las subcategorías."""
    jobs = [(m, sc) for m in METRICS for sc in subcats]
    out, fails = {}, []

    def one(job):
        m, sc = job
        return job, get("/FundsWithRatiosBySubCategory", {"ratio": m, "subCategory": sc})
    done = 0
    with ThreadPoolExecutor(WORKERS) as pool:
        for (m, sc), rows in pool.map(one, jobs):
            done += 1
            if rows is None:
                fails.append((m, sc))
                continue
            pre, periods, scale = METRICS[m]
            for r in rows:
                d = out.setdefault(r["isin"], {})
                for p in periods:
                    v = r.get("ratio" + p)
                    if isinstance(v, (int, float)):
                        d[f"{pre}_{p}"] = round(v * scale, 3)
                if m == "linear_return":
                    for _, p in BENCH:
                        v = r.get("bench" + p)
                        if isinstance(v, (int, float)):
                            d[f"bench_ret_{p}"] = round(v * 100, 3)
            if done % 200 == 0:
                print(f"  métricas: {done}/{len(jobs)} peticiones", flush=True)
    return out, fails


def main():
    t0 = time.time()
    hoy = datetime.date.today().isoformat()
    print(f"IronIA: foto {hoy}", flush=True)
    funds = catalog()
    if len(funds) < MIN_FUNDS:
        print(f"ERROR: catálogo incompleto ({len(funds)} < {MIN_FUNDS}); no se guarda", flush=True)
        return 1
    subcats = sorted({f.get("subcategory") for f in funds.values() if f.get("subcategory")})
    print(f"  {len(subcats)} subcategorías; descargando {len(METRICS)} métricas…", flush=True)
    rat, fails = ratios(subcats)
    cols = [c for c, _ in META] + [f"{pre}_{p}" for pre, ps, _ in METRICS.values() for p in ps] \
        + [f"bench_ret_{p}" for _, p in BENCH] + ["fecha"]
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(cols)
    n_rat = 0
    for isin in sorted(funds):
        f, r = funds[isin], rat.get(isin, {})
        n_rat += bool(r)
        row = []
        for c, k in META:
            v = f.get(k)
            row.append("" if v is None else (int(v) if isinstance(v, bool) else v))
        row += [r.get(c, "") for c in cols[len(META):-1]] + [hoy]
        w.writerow(row)
    os.makedirs(HIST, exist_ok=True)
    data = buf.getvalue().encode("utf-8")
    tmp = os.path.join(OUT, "ironia_latest.csv.tmp")
    open(tmp, "wb").write(data)
    os.replace(tmp, os.path.join(OUT, "ironia_latest.csv"))
    with gzip.open(os.path.join(HIST, f"ironia_{hoy}.csv.gz"), "wb") as fh:
        fh.write(data)
    status = {"fecha": hoy, "clases": len(funds), "con_metricas": n_rat, "subcategorias": len(subcats),
              "peticiones_fallidas": len(fails), "segundos": round(time.time() - t0)}
    json.dump(status, open(os.path.join(OUT, "status.json"), "w"), ensure_ascii=False)
    print(f"OK: IronIA {len(funds)} clases ({n_rat} con métricas), {len(subcats)} subcategorías, "
          f"{len(fails)} peticiones fallidas, {status['segundos']} s -> data/ironia/", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
