#!/bin/zsh
# Atajo: coge el PDF de "Carteras Modelo de Fondos" MÁS RECIENTE de ~/Downloads
# y lo añade al histórico automáticamente (sin escribir el nombre a mano).
#
# Uso:  ./añadir-ultima-cartera.sh
#
# Busca el .pdf más reciente de la carpeta Descargas cuyo contenido sea realmente
# una "Carteras Modelo de Fondos" de Bankinter, y lo pasa a add_cartera_modelo.py.
setopt no_nomatch
DIR=${0:A:h}
cd "$DIR" || exit 1
DL="$HOME/Downloads"
PY="./venv/bin/python"

# Recorre los PDF de ~/Downloads del más nuevo al más viejo y coge el primero que sea
# una cartera modelo (comprobando su texto con pdftotext).
encontrado=""
for f in ${(f)"$(ls -t "$DL"/*.pdf 2>/dev/null)"}; do
  if pdftotext -layout -f 1 -l 1 "$f" - 2>/dev/null | grep -qi "Carteras Modelo de Fondos"; then
    encontrado="$f"
    break
  fi
done

if [ -z "$encontrado" ]; then
  echo "❌ No he encontrado ningún PDF de 'Carteras Modelo de Fondos' en $DL"
  echo "   Descarga primero el PDF desde Bankinter (Análisis y Mercados → Carteras Modelo) y vuelve a ejecutar."
  exit 1
fi

echo "📄 PDF detectado: $encontrado"
$PY add_cartera_modelo.py "$encontrado"
