#!/bin/sh
# Assembles a static site in web/site/ that runs typeset.py in the browser.
#
# usage: web/build.sh FONT_FILE...
#
# The fonts are bundled with the site, users pick one from a list in the
# page, the first by default.  Each font file must hold a single face, not
# a TTC.  The list shows the Chinese name of the font if it has one, as
# fc-scan reads it.
#
# Serve the result with any static web server, e.g.
#   python3 -m http.server -d web/site
set -e

WEB=$(cd "$(dirname "$0")" && pwd)
SRC=$(dirname "$WEB")
OUT="$WEB/site"

rm -rf "$OUT"
mkdir -p "$OUT/py"
cp "$WEB/index.html" "$OUT/"
cp "$SRC/common.py" "$SRC/basic.py" "$SRC/simple.py" "$SRC/util.py" "$SRC/font_util.py" \
   "$SRC/typeset.py" "$OUT/py/"
# The browser versions of uharfbuzz and render_lib replace the real ones.
cp "$WEB/uharfbuzz.py" "$WEB/render_lib.py" "$WEB/svg_render.py" "$WEB/web_main.py" "$OUT/py/"

# The full name of a font, in Chinese if it has one.
font_name() {
  fc-scan --format '%{fullname}\n%{fullnamelang}\n' "$1" | awk -F, '
    NR == 1 { n = split($0, names) }
    NR == 2 {
      split($0, langs)
      for (i = 1; i <= n; i++) if (langs[i] == "zh-cn") { print names[i]; exit }
      for (i = 1; i <= n; i++) if (langs[i] ~ /^zh/) { print names[i]; exit }
      print names[1]
    }'
}

if [ $# -eq 0 ]; then
  echo "usage: $0 FONT_FILE..." >&2
  exit 1
fi
mkdir -p "$OUT/fonts"
json='['
for file; do
  faces=$(fc-scan --format '%{index}\n' "$file" | wc -l)
  if [ "$faces" -ne 1 ]; then
    echo "not a font file with a single face: $file" >&2
    exit 1
  fi
  base=$(basename "$file")
  name=$(font_name "$file")
  case $base$name in
    *'"'* | *'\'*) echo "font name must not contain \" or \\: $base" >&2; exit 1 ;;
  esac
  if [ -e "$OUT/fonts/$base" ]; then
    echo "font file listed twice: $base" >&2
    exit 1
  fi
  cp "$file" "$OUT/fonts/$base"
  [ "$json" = '[' ] || json="$json,"
  json=$(printf '%s\n  {"file": "%s", "name": "%s"}' "$json" "$base" "${name:-$base}")
done
printf '%s\n]\n' "$json" > "$OUT/fonts/fonts.json"

echo "built $OUT"
