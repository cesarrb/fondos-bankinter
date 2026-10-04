#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Relleno único de los datos de «Mi Cartera → Riesgo y desglose» sin esperar a la foto diaria.

Descarga la ficha (snapshot) de cada fondo de Bankinter de data/fondos_latest.csv y genera:
  data/qreturns.json  rentabilidad trimestral (EUR) desde 2016 -> correlaciones y volatilidad
  data/exposure.json  región y sector de la parte de renta variable
  data/holdings.json  posiciones completas (se refresca; se conserva lo anterior si falla un fondo)
Los fondos solo-ABANCA salen de data/abanca_vl_series.json (VL mensual, divisa del fondo).

Reanudable: guarda cada 100 fondos. Uso:  ./venv/bin/python backfill_cartera_data.py
"""
import csv, json, os, time
from concurrent.futures import ThreadPoolExecutor

import extract_fondos as e

DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(DIR)
P = {k: os.path.join("data", k + ".json") for k in ("qreturns", "exposure", "holdings")}


def load(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}


def dump(obj, path):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def main():
    rows = list(csv.DictReader(open("data/fondos_latest.csv", encoding="utf-8"), delimiter=";"))
    isins = [r["Isin"] for r in rows if r.get("Isin") and (r.get("Fuente") or "Bankinter") == "Bankinter"]
    qr, ex, ho = load(P["qreturns"]), load(P["exposure"]), load(P["holdings"])
    todo = [i for i in isins if i not in qr]
    print(f"{len(isins)} fondos Bankinter; {len(todo)} pendientes de rentabilidad trimestral", flush=True)

    def one(isin):
        js = e.snapshot_json(isin)
        time.sleep(0.1)
        if not js:
            return isin, None, None, None
        return isin, e.parse_qreturns(js), e.parse_exposure(js), e.parse_holdings(js)

    done = miss = 0
    with ThreadPoolExecutor(max_workers=3) as pool:
        for isin, q, x, h in pool.map(one, todo):
            done += 1
            if q:
                qr[isin] = q
            else:
                miss += 1
            if x:
                ex[isin] = x
            if h:
                ho[isin] = h
            if done % 100 == 0:
                dump(qr, P["qreturns"]); dump(ex, P["exposure"]); dump(ho, P["holdings"])
                print(f"  {done}/{len(todo)} (sin serie: {miss})", flush=True)
    for isin, q in e.abanca_qreturns().items():
        qr.setdefault(isin, q)
    dump(qr, P["qreturns"]); dump(ex, P["exposure"]); dump(ho, P["holdings"])
    print(f"OK: qreturns={len(qr)} exposure={len(ex)} holdings={len(ho)} (sin serie: {miss})")


if __name__ == "__main__":
    main()
