#!/bin/zsh
# Chequeo de salud de la foto diaria. Se ejecuta cada mañana (L-V): comprueba que la foto del
# día laborable anterior existe y está COMPLETA (>= MINROWS). Si no, avisa con una notificación
# de macOS para que el fallo NUNCA pase desapercibido.
setopt no_nomatch
DIR=/Users/cesar/fondos-bankinter
cd "$DIR" || exit 1
MINROWS=2000
LOG() { echo "[health $(date '+%Y-%m-%d %H:%M:%S %a')] $1" >> "$DIR/health.log"; }
notify() { osascript -e "display notification \"$2\" with title \"$1\" sound name \"Basso\"" >/dev/null 2>&1; }

# Si hay un raspado en curso (recuperación/mañana), no alarmar todavía.
if pgrep -f "extract_fondos.py" >/dev/null; then LOG "scrape en curso; no evaluo aun"; exit 0; fi

DOW=$(date +%u)
if [ "$DOW" -eq 1 ]; then CHK=$(date -v-3d +%Y-%m-%d)            # lunes -> viernes
elif [ "$DOW" -ge 2 ] && [ "$DOW" -le 5 ]; then CHK=$(date -v-1d +%Y-%m-%d)  # mar-vie -> ayer
else exit 0; fi                                                  # sáb/dom: no se comprueba

ok=""
for f in data/history/fondos_${CHK}_*.csv data/history/fondos_${CHK}.csv; do
  [ -f "$f" ] || continue
  [ "$(wc -l < "$f")" -ge "$MINROWS" ] && ok="$f"
done

if [ -n "$ok" ]; then
  LOG "OK: foto completa de $CHK ($(( $(wc -l < "$ok") - 1 )) fondos)"
else
  notify "Fondos Bankinter — ⚠️ FALLO" "Falta o está incompleta la foto del $CHK. Abre el Mac y revisa el scraper."
  LOG "ALERTA: falta/incompleta la foto de $CHK -> notificación enviada"
fi
