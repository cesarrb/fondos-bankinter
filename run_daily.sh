#!/bin/zsh
# Guardián de la foto diaria de fondos (lo llama launchd varias veces al día).
# - Solo L-V. Foto principal por la noche (>=22:30). Fallback matinal (>=07:00) si se perdió.
# - Como mucho UNA foto COMPLETA por día (>= MINROWS filas).
# - Verifica la foto del DÍA ANTERIOR: si falta o está incompleta, la saca (recuperación).
# - Verifica su PROPIA foto tras raspar: si sale incompleta, la repite una vez.
setopt no_nomatch
DIR=/Users/cesar/fondos-bankinter
cd "$DIR" || exit 1
LOG() { echo "[guard $(date '+%Y-%m-%d %H:%M:%S %a')] $1"; }
MINROWS=2000

photo_ok() {  # ¿existe foto COMPLETA (>= MINROWS) para la fecha $1?
  local d="$1" f
  for f in data/history/fondos_${d}_*.csv data/history/fondos_${d}.csv; do
    [ -f "$f" ] || continue
    [ "$(wc -l < "$f")" -ge "$MINROWS" ] && return 0
  done
  return 1
}

# Raspa y VERIFICA su resultado; si sale incompleto, reintenta 1 vez. $1 = motivo (log)
run_scrape() {
  LOG "===== sacando foto ($1) ====="
  ./venv/bin/python -u extract_fondos.py
  # Verificar por el nº REAL de fondos del fichero recién escrito (no por la fecha: un raspado
  # que cruza medianoche no debe confundir la comprobación).
  local rows
  rows=$(( $(wc -l < data/fondos_latest.csv 2>/dev/null || echo 1) - 1 ))
  if [ "$rows" -ge "$MINROWS" ]; then LOG "foto verificada COMPLETA ($rows fondos)"; return 0; fi
  LOG "foto INCOMPLETA ($rows fondos) -> reintento único"
  ./venv/bin/python -u extract_fondos.py
  rows=$(( $(wc -l < data/fondos_latest.csv 2>/dev/null || echo 1) - 1 ))
  [ "$rows" -ge "$MINROWS" ] && LOG "reintento OK ($rows fondos)" || LOG "reintento tampoco completó ($rows); se revisará mañana"
}

# 0) No solapar
if pgrep -f "extract_fondos.py" >/dev/null; then LOG "ya hay un scrape en curso; salgo"; exit 0; fi

DOW=$(date +%u); HHMM=$((10#$(date +%H%M))); TODAY=$(date +%Y-%m-%d)

# 1) Solo días laborables
if [ "$DOW" -gt 5 ]; then LOG "fin de semana: no se saca foto"; exit 0; fi

# 2) NIVEL DE SEGURIDAD: verificar la foto del DÍA LABORABLE ANTERIOR (si es mala, sacarla ahora)
if [ "$HHMM" -ge 700 ]; then
  PDOW=$(date -v-1d +%u); PW=$(date -v-1d +%Y-%m-%d)
  [ "$PDOW" -eq 7 ] && PW=$(date -v-3d +%Y-%m-%d)   # ayer domingo -> viernes
  [ "$PDOW" -eq 6 ] && PW=$(date -v-2d +%Y-%m-%d)   # ayer sábado  -> viernes
  if ! photo_ok "$PW"; then
    run_scrape "recuperación: la foto anterior ($PW) falta o está incompleta"
    exit 0
  fi
fi

# 3) Foto de HOY: si ya está completa, nada; si no, sacarla en la ventana correcta
if photo_ok "$TODAY"; then LOG "ya hay foto COMPLETA de hoy ($TODAY)"; exit 0; fi
if [ "$HHMM" -ge 2230 ]; then run_scrape "noche 22:30"; exit 0; fi

LOG "esperando a la ventana de las 22:30 (o al fallback matinal)"
exit 0
