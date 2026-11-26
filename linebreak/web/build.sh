#!/bin/sh
# Assembles a static site in web/site/ that runs typeset.py in the browser.
#
# usage: web/build.sh [FONT_FILE...]
#
# Users pick a font from a list in the page, the smallest file by default.  The
# fonts are those in fonts.txt, which the page downloads from jsDelivr, or
# else the FONT_FILEs, copied into the site, e.g. for testing.  Each font
# file must hold a single face, not a TTC.  The list shows the Chinese name
# of the font if it has one, as fc-scan reads it.
#
# The page loads Google Analytics with the measurement ID in GA_ID, by default
# the one of txt2png.  Set GA_ID= (empty) to build without it, e.g. for testing.
#
# Serve the result with any static web server, e.g.
#   python3 -m http.server -d web/site
set -e

WEB=$(cd "$(dirname "$0")" && pwd)
SRC=$(dirname "$WEB")
OUT="$WEB/site"
GA_ID=${GA_ID-G-15PPB5SH29}

if [ -n "$GA_ID" ] && ! printf '%s' "$GA_ID" | grep -Eqx 'G-[A-Z0-9]+'; then
  echo "not a Google Analytics measurement ID: $GA_ID" >&2
  exit 1
fi

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

# Adds a font to $json, the list for fonts.json: add_font URL SHA256 FILE [NAME]
json='['
add_font() {
  faces=$(fc-scan --format '%{index}\n' "$3" | wc -l)
  if [ "$faces" -ne 1 ]; then
    echo "not a font file with a single face: $1" >&2
    exit 1
  fi
  name=${4:-$(font_name "$3")}
  case $1$name in
    *'"'* | *'\'*) echo "font URL and name must not contain \" or \\: $1" >&2; exit 1 ;;
  esac
  [ "$json" = '[' ] || json="$json,"
  json=$(printf '%s\n  {"url": "%s",\n   "sha256": "%s", "size": %d, "name": "%s"}' \
         "$json" "$1" "$2" "$(wc -c < "$3")" "${name:-${1##*/}}")
}

# The fonts: files from the command line, copied into the site, or else
# those in fonts.txt, downloaded into $WEB/.fonts/ to check their SHA-256
# and to read their names.
if [ $# -eq 0 ]; then
  mkdir -p "$WEB/.fonts"
  while read -r url sha256 name; do
    case $url in '' | '#'*) continue ;; esac
    file="$WEB/.fonts/$sha256"
    if [ ! -e "$file" ]; then
      echo "downloading $url" >&2
      curl -sSfL -o "$file.tmp" "$url"
      if ! echo "$sha256  $file.tmp" | sha256sum -c --status; then
        echo "SHA-256 mismatch: $url" >&2
        rm -f "$file.tmp"
        exit 1
      fi
      mv "$file.tmp" "$file"
    fi
    add_font "$url" "$sha256" "$file" "$name"
  done < "$WEB/fonts.txt"
else
  for file; do
    add_font "fonts/$(basename "$file")" "$(sha256sum < "$file" | cut -d' ' -f1)" "$file"
  done
fi
if [ "$json" = '[' ]; then
  echo "no fonts in $WEB/fonts.txt" >&2
  exit 1
fi

COMMIT_FULL='' COMMIT_SHORT='' COMMIT_DATE='' COMMIT_ISO=''
if git_info=$(git -C "$WEB" log -1 --format='%H %h %cs %cI' 2>/dev/null); then
  IFS=' ' read -r COMMIT_FULL COMMIT_SHORT COMMIT_DATE COMMIT_ISO <<EOF
$git_info
EOF
fi

rm -rf "$OUT"
mkdir -p "$OUT/py"
# Replaces <!-- analytics --> with the gtag.js snippet (if GA_ID is set) and
# <!-- updated --> with the commit date and hash (if built from a git repo).
awk -v id="$GA_ID" -v q="'" \
    -v commit="$COMMIT_FULL" -v short="$COMMIT_SHORT" \
    -v date="$COMMIT_DATE" -v iso="$COMMIT_ISO" '
  /<!-- analytics -->/ {
    if (id != "") {
      print "<script async src=\"https://www.googletagmanager.com/gtag/js?id=" id "\"></script>"
      print "<script>"
      print "  window.dataLayer = window.dataLayer || [];"
      print "  function gtag(){dataLayer.push(arguments);}"
      print "  gtag(" q "js" q ", new Date());"
      print "  gtag(" q "config" q ", " q id q ");"
      print "</script>"
    }
    next
  }
  /<!-- updated -->/ {
    if (commit != "") {
      url = "https://github.com/chenshuo/typeset/commit/" commit
      print "    · 更新：<time datetime=\"" iso "\" title=\"" iso "\">" date "</time> (<a href=\"" url "\">" short "</a>)"
    }
    next
  }
  { print }' "$WEB/index.html" > "$OUT/index.html"
cp "$SRC/common.py" "$SRC/basic.py" "$SRC/simple.py" "$SRC/util.py" "$SRC/font_util.py" \
   "$SRC/typeset.py" "$OUT/py/"
# The browser versions of uharfbuzz and render_lib replace the real ones.
cp "$WEB/uharfbuzz.py" "$WEB/render_lib.py" "$WEB/svg_render.py" "$WEB/web_main.py" "$OUT/py/"

# uniseg and pyphen go in py/vendor.zip, rather than their wheels installed
# with micropip: the uniseg wheel is 8 MB, mostly its HTML docs, and pyphen
# has dictionaries of 40-odd languages.  HYPHEN_DICTS must cover the
# languages in the page; pyphen finds fr for fr_FR.
HYPHEN_DICTS="en_US en_GB de_DE fr"
python3 -m pip download -q --no-deps --only-binary=:all: -d "$WEB/.wheels" \
    uniseg==0.10.1 pyphen==0.17.2
python3 - "$OUT/py/vendor.zip" "$WEB"/.wheels/uniseg-0.10.1-*.whl \
    "$WEB"/.wheels/pyphen-0.17.2-*.whl $HYPHEN_DICTS <<'PY'
import re, sys, zipfile

out, wheels, langs = sys.argv[1], sys.argv[2:4], sys.argv[4:]
dicts = '|'.join(re.escape(lang) for lang in langs)
keep = re.compile(r'uniseg/[^/]+\.py'                      # not uniseg/docs/
                  r'|pyphen/__init__\.py'
                  rf'|pyphen/dictionaries/(hyph|README_hyph)_({dicts})\.(dic|txt)'
                  r'|[^/]+\.dist-info/(?!RECORD$).+')       # metadata and licenses
missing = set(langs)
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for wheel in wheels:
        with zipfile.ZipFile(wheel) as w:
            for name in w.namelist():
                if keep.fullmatch(name):
                    z.writestr(name, w.read(name))
                    if m := re.fullmatch(r'pyphen/dictionaries/hyph_(.+)\.dic', name):
                        missing.discard(m.group(1))
if missing:
    sys.exit('no pyphen dictionary for %s' % ' '.join(sorted(missing)))
PY

mkdir -p "$OUT/fonts"
for file; do
  if [ -e "$OUT/fonts/$(basename "$file")" ]; then
    echo "two font files named $(basename "$file")" >&2
    exit 1
  fi
  cp "$file" "$OUT/fonts/"
done
printf '%s\n]\n' "$json" > "$OUT/fonts/fonts.json"

echo "built $OUT"
