"""A minimal uharfbuzz-compatible shim over harfbuzzjs, for running in Pyodide.

Pyodide does not ship uharfbuzz, so the page loads harfbuzzjs (HarfBuzz
compiled to WebAssembly) and exposes it as `globalThis.hbjs`.  This module
implements just the subset of the uharfbuzz API used by util.py, typeset.py
and svg_render.py.
"""

from collections import namedtuple

from js import hbjs
from pyodide.ffi import to_js

GlyphInfo = namedtuple('GlyphInfo', 'codepoint cluster')
GlyphPosition = namedtuple('GlyphPosition', 'x_advance y_advance x_offset y_offset')


class Blob:
    _cache = {}

    def __init__(self, data: bytes):
        self._js = hbjs.Blob.new(to_js(data))

    @classmethod
    def from_file_path(cls, path):
        # Font files are large (CJK fonts are 10-20 MB), copy each into the
        # WebAssembly heap only once.  The page writes every uploaded font to
        # a new path, so a path never changes its content.
        blob = cls._cache.get(path)
        if blob is None:
            with open(path, 'rb') as f:
                blob = cls(f.read())
            cls._cache[path] = blob
        return blob


class Face:
    def __init__(self, blob: Blob, index: int = 0):
        self._js = hbjs.Face.new(blob._js, index)

    @property
    def upem(self):
        return self._js.upem


class Font:
    def __init__(self, face: Face):
        self._js = hbjs.Font.new(face._js)
        self._scale = (face.upem, face.upem)

    @property
    def scale(self):
        return self._scale

    @scale.setter
    def scale(self, value):
        self._scale = tuple(value)
        self._js.setScale(*self._scale)

    def draw_glyph_with_pen(self, gid: int, pen):
        """Draws the outline of a glyph using a fontTools-style pen."""
        for cmd in self._js.glyphToJson(gid).to_py():
            t, v = cmd['type'], cmd['values']
            if t == 'M':
                pen.moveTo((v[0], v[1]))
            elif t == 'L':
                pen.lineTo((v[0], v[1]))
            elif t == 'Q':
                pen.qCurveTo((v[0], v[1]), (v[2], v[3]))
            elif t == 'C':
                pen.curveTo((v[0], v[1]), (v[2], v[3]), (v[4], v[5]))
            elif t == 'Z':
                pen.closePath()


class Buffer:
    def __init__(self):
        self._js = hbjs.Buffer.new()
        self.glyph_infos = []
        self.glyph_positions = []

    def add_str(self, text: str):
        self._js.addText(text)

    def guess_segment_properties(self):
        self._js.guessSegmentProperties()

    def _update(self):
        glyphs = self._js.getGlyphInfosAndPositions().to_py()
        self.glyph_infos = [GlyphInfo(g['codepoint'], g['cluster']) for g in glyphs]
        self.glyph_positions = [
            GlyphPosition(g['xAdvance'], g['yAdvance'], g['xOffset'], g['yOffset'])
            for g in glyphs]


def shape(font: Font, buffer: Buffer, features=None):
    feats = [hbjs.Feature.new(tag, int(value)) for tag, value in (features or {}).items()]
    hbjs.shape(font._js, buffer._js, to_js(feats))
    buffer._update()
