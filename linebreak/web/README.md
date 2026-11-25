# `typeset.py` in the browser

A static page that typesets Chinese or mixed Chinese/Latin paragraphs with `../typeset.py`,
at <https://txt2png.chenshuo.com/>. Everything runs in the browser, the text is not sent anywhere,
so the site needs no server. The page renders an SVG, which can be downloaded as SVG or PNG,
or copied to the clipboard as PNG.

## How it works

* [Pyodide](https://pyodide.org/) runs `typeset.py`, `simple.py` and the other Python files
  of `..` unchanged.
* `uharfbuzz.py` stands in for [uharfbuzz](https://github.com/harfbuzz/uharfbuzz),
  which Pyodide does not ship. It implements the part of the uharfbuzz API used here
  on top of [harfbuzzjs](https://github.com/harfbuzz/harfbuzzjs), HarfBuzz compiled to WebAssembly.
* `svg_render.py` draws the lines into an SVG with glyph outlines from HarfBuzz,
  in place of `../render_lib.py`, which needs cairo and FreeType.
  `render_lib.py` here is a stub, for `typeset.py` to import.
* `web_main.py` is the entry point that `index.html` calls.
* uniseg and pyphen are packed into `py/vendor.zip` by `build.sh`, with only the code and
  the hyphenation dictionaries in the page: 0.47 MB, rather than 10.4 MB for their wheels.
* Fonts are downloaded from [jsDelivr](https://www.jsdelivr.com/) when the user picks one,
  and checked against their SHA-256. A first visit downloads about 6 MB besides the font.
* The page keeps the text and the options in `localStorage`.

## Build and run locally

From `linebreak/`:

```sh
GA_ID= web/build.sh              # fonts in fonts.txt, no Google Analytics
python3 -m http.server -d web/site
```

`build.sh` needs `python3` with pip, `curl`, `sha256sum` and `fc-scan` (fontconfig).
It caches what it downloads in `web/.fonts/` and `web/.wheels/`.
Without `GA_ID=`, the page loads Google Analytics with the ID of txt2png.

To test with local font files instead, give them to `build.sh`, which copies them into the site:

```sh
GA_ID= web/build.sh path/to/font.otf ...
```

## Fonts

`fonts.txt` lists the fonts, one per line: `URL SHA256 [NAME]`.
The page lists them in this order, and the smallest file is the default.
NAME is the name in the list, by default the Chinese name in the font, as `fc-scan` reads it.

To add a font:

* It must be a file in a GitHub repository, not a release asset, as jsDelivr serves only those,
  and at most 20 MB. The font file must hold a single face, not a TTC.
* Use a URL at a commit, e.g. `https://cdn.jsdelivr.net/gh/OWNER/REPO@COMMIT/PATH`,
  as a tag may move.
* Get its SHA-256 with `curl -sL URL | sha256sum`, and check its license.

## Deploy

`.github/workflows/pages.yml` runs `build.sh` and deploys `web/site/` to GitHub Pages
on every push to master that touches `linebreak/`.
