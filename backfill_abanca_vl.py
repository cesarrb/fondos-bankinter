#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backfill del histórico de VL de los fondos SOLO-ABANCA en data/vl_history.csv.

Fuente: quefondos.com (serie `var fondo` de la ficha) -> VL REAL, fin de mes,
desde el lanzamiento del fondo (años de histórico). Da a los ABANCA una serie
larga de VL, igualando/superando el timeframe de los Bankinter (que en
vl_history solo tienen la ventana diaria reciente).

Dos fases con checkpoint para que un corte no pierda el trabajo:
  Fase A  fetch  -> guarda cada serie en data/abanca_vl_series.json
  Fase B  merge  -> fusiona los puntos fin-de-mes en data/vl_history.csv
                    (dedup por isin+fecha; conserva los puntos DIARIOS ya
                     existentes de las fotos recientes)

Uso:  ./venv/bin/python backfill_abanca_vl.py            (fetch + merge)
      ./venv/bin/python backfill_abanca_vl.py --merge    (solo merge del JSON)
"""
import csv, re, json, time, sys, os
import requests

DIR = os.path.dirname(os.path.abspath(__file__))
SOLO = os.path.join(DIR, "data", "abanca_solo.csv")
SERIES = os.path.join(DIR, "data", "abanca_vl_series.json")
HIST = os.path.join(DIR, "data", "vl_history.csv")
CAP = 1500  # máx puntos por fondo en vl_history


def iso(d):  # MM/DD/YYYY -> YYYY-MM-DD
    mm, dd, yy = d.split("/")
    return f"{yy}-{mm}-{dd}"


def fetch_all():
    isins = [r["Isin"] for r in csv.DictReader(open(SOLO, encoding="utf-8"), delimiter=";") if r.get("Isin")]
    got = {}
    if os.path.exists(SERIES):
        got = json.load(open(SERIES, encoding="utf-8"))
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0"
    miss = []
    for i, isin in enumerate(isins, 1):
        if isin in got:  # ya descargado (reanudable)
            continue
        try:
            raw = s.get(f"https://www.quefondos.com/es/fondos/ficha/index.html?isin={isin}", timeout=25).text
            m = re.search(r"var\s+fondo\s*=\s*(\[\[.*?\]\]);", raw, re.S)
            if not m:
                miss.append(isin)
            else:
                arr = json.loads(m.group(1).replace("'", '"'))
                got[isin] = {iso(d): round(float(v), 4) for d, v in arr if v}
        except Exception:
            miss.append(isin)
        if i % 25 == 0:
            json.dump(got, open(SERIES, "w"), ensure_ascii=False)
            print(f"{i}/{len(isins)} series={len(got)} miss={len(miss)}", flush=True)
        time.sleep(0.2)
    json.dump(got, open(SERIES, "w"), ensure_ascii=False)
    print(f"FETCH DONE: series={len(got)}/{len(isins)} sin_serie={len(miss)}", flush=True)
    if miss:
        print("  sin serie:", ",".join(miss), flush=True)
    return got


def merge():
    got = json.load(open(SERIES, encoding="utf-8"))
    hist = {}
    for r in csv.reader(open(HIST, encoding="utf-8"), delimiter=";"):
        if len(r) >= 3 and r[0] and r[1] and r[0] != "fecha":
            hist.setdefault(r[1], {})[r[0]] = r[2]
    added = 0
    for isin, pts in got.items():
        for d, vl in pts.items():
            if d not in hist.get(isin, {}):
                hist.setdefault(isin, {})[d] = repr(vl)
                added += 1
    with open(HIST, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["fecha", "Isin", "VL_EUR"])
        for isin in sorted(hist):
            for d in sorted(hist[isin])[-CAP:]:
                w.writerow([d, isin, hist[isin][d]])
    tot = sum(len(v) for v in hist.values())
    print(f"MERGE DONE: puntos añadidos={added}, ISINs en vl_history={len(hist)}, filas={tot}", flush=True)


if __name__ == "__main__":
    if "--merge" in sys.argv:
        merge()
    else:
        fetch_all()
        merge()
