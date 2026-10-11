"""YTD (rentabilidad en lo que va de año) de fondos de IronIA, calculado con el VL del Financial Times.

IronIA no publica ni el YTD ni el valor liquidativo (su API solo da 1m/3m/6m/1a…5a), así que en el panel
el periodo «YTD» salía vacío para «Solo IronIA». Este script lo calcula para una lista CORTA de fondos
(los 16.000 de IronIA llevarían horas cada día):
  - los ISIN de las listas fijas `fixedIronia:{…}` de los clusters de index.html (p. ej. «Robin Brooks»)
  - los miembros IronIA de TODOS los clusters del panel (data/ironia/ytd_clusters.txt, lo genera el panel)
  - y los que se añadan a mano en data/ironia/ytd_watch.txt (uno por línea; # = comentario).

YTD = último VL / VL del último día hábil del año anterior − 1, en la divisa de la clase (como el resto de
rentabilidades de IronIA). Fuente: markets.ft.com (tearsheet → xid → ajax get-historical-prices).
Salida: data/ironia/ytd.json (local y privado, igual que el resto de data/ironia).

Uso: ./venv/bin/python ironia_ytd.py
"""
import csv, datetime as dt, html, json, os, re, sys, time
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
IRDIR = os.path.join(HERE, "data", "ironia")
OUT = os.path.join(IRDIR, "ytd.json")
WATCH = os.path.join(IRDIR, "ytd_watch.txt")
CLUS = os.path.join(IRDIR, "ytd_clusters.txt")  # miembros IronIA de todos los clusters (lo genera el panel)
UA = {"User-Agent": "Mozilla/5.0"}
ISIN_RE = re.compile(r"\b[A-Z]{2}[0-9A-Z]{9}[0-9]\b")


def watchlist():
    isins = []
    src = open(os.path.join(HERE, "index.html"), encoding="utf-8").read()
    for blk in re.findall(r"fixedIronia:\{([^}]*)\}", src):
        isins += ISIN_RE.findall(blk)
    for f in (WATCH, CLUS):
        if not os.path.exists(f):
            continue
        for ln in open(f, encoding="utf-8"):
            ln = ln.split("#")[0].strip().upper()
            isins += ISIN_RE.findall(ln)
    return list(dict.fromkeys(isins))


def currencies():
    path = os.path.join(IRDIR, "ironia_latest.csv")
    cur = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter=";"):
            cur[r["isin"]] = r["currency"] or "EUR"
    return cur


def ft_prices(isin, ccy, start, end):
    t = requests.get(f"https://markets.ft.com/data/funds/tearsheet/historical?s={isin}:{ccy}",
                     headers=UA, timeout=30).text
    m = re.search(r"xid&quot;:&quot;(\d+)", t)
    if not m:
        return None
    j = requests.get("https://markets.ft.com/data/equities/ajax/get-historical-prices",
                     params={"startDate": start.strftime("%Y/%m/%d"), "endDate": end.strftime("%Y/%m/%d"),
                             "symbol": m.group(1)}, headers=UA, timeout=30).json()
    px = {}
    for row in re.findall(r"<tr>(.*?)</tr>", j.get("html", ""), re.S):
        cells = [html.unescape(re.sub("<[^>]+>", "", c)).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        d = re.search(r'mod-ui-hide-small-below">([^<]+)<', row)
        if not d or len(cells) < 5:
            continue
        day = dt.datetime.strptime(re.search(r"[A-Z][a-z]+ \d{2}, \d{4}", d.group(1)).group(0), "%B %d, %Y").date()
        try:
            px[day] = float(cells[4].replace(",", ""))
        except ValueError:
            pass
    return px


def main():
    today = dt.date.today()
    y0 = dt.date(today.year - 1, 12, 31)
    isins, cur = watchlist(), currencies()
    prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
    items, fails = {}, []
    hoy_prev = (prev.get("items") or {}) if prev.get("fecha") == str(today) else {}
    for isin in isins:
        ccy = cur.get(isin, "EUR")
        if isin in hoy_prev:  # ya calculado hoy: no se vuelve a pedir al FT
            items[isin] = hoy_prev[isin]
            continue
        try:
            px = ft_prices(isin, ccy, y0 - dt.timedelta(days=12), today)
        except Exception as e:  # red o FT caído: se conserva el dato anterior
            px = None
            print(f"  {isin}: error {e}", file=sys.stderr)
        base = max((d for d in (px or {}) if d <= y0), default=None)
        last = max((d for d in (px or {}) if d > y0), default=None)
        if base and last:
            ytd = round((px[last] / px[base] - 1) * 100, 3)
            items[isin] = {"ytd": ytd, "base_fecha": str(base), "base": px[base], "ultimo_fecha": str(last),
                           "ultimo": px[last], "divisa": ccy, "fuente": "FT"}
            print(f"  {isin} {ccy}: YTD {ytd:+.2f}% ({base} → {last})")
        else:
            fails.append(isin)
            old = (prev.get("items") or {}).get(isin)
            if old:
                items[isin] = old  # se mantiene el último YTD bueno
            print(f"  {isin} {ccy}: sin datos en FT", file=sys.stderr)
        time.sleep(1.5)  # FT limita las peticiones seguidas
    json.dump({"fecha": str(today), "anio": today.year, "items": items, "sin_dato": fails},
              open(OUT, "w"), indent=1, ensure_ascii=False)
    print(f"YTD IronIA: {len(items)}/{len(isins)} fondos → {OUT}")
    return 0 if items or not isins else 1


if __name__ == "__main__":
    sys.exit(main())
