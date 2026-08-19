#!/usr/bin/env python3
"""
Descarga el catalogo completo de fondos del buscador de Bankinter (fuente: Allfunds/Morningstar)
y lo vuelca a CSV. Uso personal. El endpoint es interno/no documentado y podria cambiar.
"""
import time, csv, datetime, os, sys
import requests

BASE = "https://allfunds-bankinter-components-back.webfg.com/v1"
HDRS = {"Accept": "application/json", "User-Agent": "fondos-tracker/1.0 (uso personal)"}
SORTS = ["ReturnM0", "ReturnM12", "ReturnM36", "ReturnM60", "InceptionDate", "ExpenseRatio", "FundTNAV"]
PAGE = 50

s = requests.Session()
s.headers.update(HDRS)
funds = {}   # clave: SecId


def api(params):
    for a in range(4):
        try:
            r = s.get(f"{BASE}/fund", params=params, timeout=25)
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(1.5 * (a + 1))
    return None


def ids(endpoint):
    r = s.get(f"{BASE}/ms-api/{endpoint}", timeout=25)
    r.raise_for_status()
    return r.json()["data"]


def base(filters):
    return {"page": 1, "pageSize": PAGE, "sortBy": "ReturnM0.desc", **filters}


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


def main():
    DIMS = {
        "CurrencyId": [x["id"] for x in ids("currencies")],
        "KID_SRI": ["1", "2", "3", "4", "5", "6", "7"],
        "DomicileId": [x["id"] for x in ids("domiciles")],
    }
    gac = {x["id"]: x["name"] for x in ids("global-asset-classes")}
    cats = ids("categories")
    print(f"{len(cats)} categorias; recorriendo...")
    for i, c in enumerate(cats, 1):
        fetch({"CategoryId": c["id"]}, ["CurrencyId", "KID_SRI", "DomicileId"], DIMS)
        if i % 25 == 0:
            print(f"  {i}/{len(cats)} categorias, {len(funds)} fondos acumulados")
        time.sleep(0.2)

    if not funds:
        print("ERROR: no se ha descargado ningun fondo (posible cambio en la API).")
        sys.exit(1)

    hoy = datetime.date.today().isoformat()
    cols = ["Isin", "Name", "LegalName", "ProviderCompanyName", "GlobalAssetClass",
            "GlobalCategoryName", "CategoryName", "Currency", "DomicileName", "SRRI",
            "StarRatingM255", "ExpenseRatio", "ManagementFee", "ReturnM0", "ReturnM12",
            "ReturnM36", "ReturnM60", "InceptionDate", "UCITS", "IndexFund", "InitialPurchase"]
    rows = []
    for f in funds.values():
        d = dict(f)
        d["GlobalAssetClass"] = gac.get(d.get("GlobalAssetClassId"), "")
        rows.append([d.get(k, "") for k in cols])
    rows.sort(key=lambda r: (str(r[4]), str(r[6]), str(r[1])))  # clase activo, categoria, nombre

    os.makedirs("data/history", exist_ok=True)
    for path in ("data/fondos_latest.csv", f"data/history/fondos_{hoy}.csv"):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(cols + ["fecha"])
            for r in rows:
                w.writerow(r + [hoy])
    print(f"OK: {len(rows)} fondos -> data/fondos_latest.csv ({hoy})")


if __name__ == "__main__":
    main()
