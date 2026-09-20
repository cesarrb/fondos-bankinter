#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Añade una foto de las CARTERAS MODELO de Bankinter al histórico.

Uso:
    ./venv/bin/python add_cartera_modelo.py <ruta_al_pdf> [YYYY-MM-DD]

- Detecta la fecha del propio PDF (portada "..., D de mes de AAAA") si no se pasa.
- Archiva el PDF en carteras_modelo/carteras_modelo_fondos_<fecha>.pdf
- Extrae las 6 carteras (Doméstica/Global × Defensivo-Conservador/Moderado/Dinámico-Agresivo)
  con su composición actual ("Nueva cartera": ISIN, peso, nombre, clasificación ESG).
- Fusiona la foto en data/carteras_modelo.json manteniendo el HISTÓRICO por fecha.

Bankinter publica este PDF (contentFile?name=carteras_modelo_fondos.pdf) solo en su
versión vigente y requiere login: no es automatizable en la nube. Este script es la vía
para ir construyendo el histórico a mano según se publica cada actualización.
"""
import subprocess, re, json, sys, os, shutil, datetime

DIR = os.path.dirname(os.path.abspath(__file__))
ARCHIVE = os.path.join(DIR, "carteras_modelo")
DATA = os.path.join(DIR, "data", "carteras_modelo.json")

MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
         "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
         "noviembre": 11, "diciembre": 12}
RV_DEFAULT = {"Agresivo": 80, "Dinámico": 65, "Moderado": 50, "Conservador": 35, "Defensivo": 25}
ISIN_RE = re.compile(r"\b([A-Z]{2}[0-9A-Z]{9}[0-9])\s+(\d{1,3})%\s+(.+?)\s+(Art\.\s*\d+)")
PERFIL_NAME = {"DEFENSIVO/CONSERVADOR": "Defensivo/Conservador", "MODERADO": "Moderado",
               "DIN": "Dinámico/Agresivo"}


def _pdftotext(pdf, p):
    return subprocess.run(["pdftotext", "-layout", "-f", str(p), "-l", str(p), pdf, "-"],
                          capture_output=True, text=True).stdout


def detect_date(pdf):
    t = _pdftotext(pdf, 1)
    m = re.search(r"(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(\d{4})", t, re.I)
    if m and m.group(2).lower() in MESES:
        return f"{int(m.group(3)):04d}-{MESES[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    return None


def _parse_page(txt, ambito):
    marks = []
    for name in ["DEFENSIVO/CONSERVADOR", "MODERADO", "DIN"]:
        m = re.search(r"PERFIL " + name, txt)
        if m:
            marks.append((m.start(), name))
    marks.sort()
    out = []
    for i, (pos, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(txt)
        block = txt[pos:end]
        seen = set()
        fondos = []
        for mm in ISIN_RE.finditer(block):
            isin = mm.group(1)
            if isin in seen:
                continue
            seen.add(isin)
            fondos.append({"isin": isin, "peso": int(mm.group(2)),
                           "nombre": re.sub(r"\s{2,}", " ", mm.group(3).strip()),
                           "esg": mm.group(4).replace(" ", "")})
        out.append({"ambito": ambito, "perfil": PERFIL_NAME[name],
                    "n_fondos": len(fondos), "suma_pesos": sum(f["peso"] for f in fondos),
                    "fondos": fondos})
    return out


def parse_pdf(pdf):
    carteras = _parse_page(_pdftotext(pdf, 2), "Doméstica") + _parse_page(_pdftotext(pdf, 3), "Global")
    return {"exposicion_rv": RV_DEFAULT, "carteras": carteras}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    pdf = sys.argv[1]
    fecha = sys.argv[2] if len(sys.argv) > 2 else detect_date(pdf)
    if not fecha:
        print("No pude detectar la fecha; pásala como 2º argumento (YYYY-MM-DD).")
        sys.exit(1)
    os.makedirs(ARCHIVE, exist_ok=True)
    dest = os.path.join(ARCHIVE, f"carteras_modelo_fondos_{fecha}.pdf")
    if os.path.abspath(pdf) != os.path.abspath(dest):
        shutil.copy2(pdf, dest)
    snap = parse_pdf(dest)
    bad = [f"{c['ambito']}/{c['perfil']}={c['suma_pesos']}%" for c in snap["carteras"] if c["suma_pesos"] != 100]
    if bad:
        print("AVISO: carteras que no suman 100%:", bad)
    hist = {"latest": "", "snapshots": {}}
    if os.path.exists(DATA):
        hist = json.load(open(DATA, encoding="utf-8"))
    hist["snapshots"][fecha] = snap
    hist["latest"] = max(hist["snapshots"])
    hist["fuente"] = "Bankinter — Carteras Modelo de Fondos (Análisis y Mercados)"
    hist["updated"] = datetime.date.today().isoformat()
    json.dump(hist, open(DATA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"OK: cartera modelo {fecha} archivada y fusionada. Fotos en histórico: {len(hist['snapshots'])}")
    for c in snap["carteras"]:
        print(f"   {c['ambito']:10} {c['perfil']:22} {c['n_fondos']} fondos ({c['suma_pesos']}%)")


if __name__ == "__main__":
    main()
