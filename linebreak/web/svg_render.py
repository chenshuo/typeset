"""Renders typeset lines into an SVG string, using glyph outlines from HarfBuzz.

Works with both the real uharfbuzz and the harfbuzzjs shim in this directory,
so it can be tested outside the browser.  The layout matches
render_lib.render_paragraphs().
"""

from common import Box, Glue, Penalty
import util

FREETYPE_SCALE = 64
LINE_SKIP = 1.4  # multiplier of font size for baseline vertical distance


class _SvgPathPen:
    """fontTools-style pen that writes SVG path data, in px with y pointing down."""

    def __init__(self):
        self.d = []

    def _pt(self, p):
        return '%s %s' % (_num(p[0] / FREETYPE_SCALE), _num(-p[1] / FREETYPE_SCALE))

    def moveTo(self, p):
        self.d.append('M' + self._pt(p))

    def lineTo(self, p):
        self.d.append('L' + self._pt(p))

    def qCurveTo(self, *points):
        # TrueType quadratic splines may have several off-curve points with
        # implied on-curve points in between.
        *offs, end = points
        for i, off in enumerate(offs):
            if i + 1 < len(offs):
                nxt = offs[i + 1]
                on = ((off[0] + nxt[0]) / 2, (off[1] + nxt[1]) / 2)
            else:
                on = end
            self.d.append('Q' + self._pt(off) + ' ' + self._pt(on))

    def curveTo(self, *points):
        self.d.append('C' + ' '.join(self._pt(p) for p in points))

    def closePath(self):
        self.d.append('Z')

    def endPath(self):
        pass


def _num(x: float) -> str:
    s = '%.2f' % x
    s = s.rstrip('0').rstrip('.')
    return '0' if s == '-0' else s


def render_svg(hb_font, size, paragraphs, line_width, par_skip=0.0,
               guides=False) -> str:
    """Returns an SVG document for paragraphs, each a list of lines from
    basic.show_results().

    par_skip is the extra space between paragraphs, in multiples of size.
    With guides, draws the left and right edges of the text block.
    """
    left_margin = size
    right_margin = size
    line_height = size * LINE_SKIP
    img_width = int(left_margin + line_width + right_margin)
    n_lines = sum(len(lines) for lines in paragraphs)
    n_skips = max(len(paragraphs) - 1, 0)
    img_height = int((n_lines + 1) * line_height + n_skips * size * par_skip)

    uses = []
    glyph_ids = set()
    pos_y = line_height + size * (LINE_SKIP - 1.0)
    for i, lines in enumerate(paragraphs):
        if i > 0:
            pos_y += size * par_skip
        for ratio, line in lines:
            pos_x = left_margin
            line = list(line)
            last_item = line[-1]
            if isinstance(last_item, Penalty) and last_item.text:  # Hyphen
                box = util.get_box(last_item.text, hb_font)
                line[-1] = Box(last_item.width, last_item.text, box.glyphs)
            for it in line:
                if isinstance(it, Box):
                    for gid, x, y in it.glyphs or ():
                        glyph_ids.add(gid)
                        uses.append('<use href="#g%d" x="%s" y="%s"/>'
                                    % (gid, _num(x + pos_x), _num(y + pos_y)))
                    pos_x += it.width
                elif isinstance(it, Glue):
                    pos_x += it.get_width(max(ratio, -1))
            pos_y += line_height

    defs = []
    for gid in sorted(glyph_ids):
        pen = _SvgPathPen()
        hb_font.draw_glyph_with_pen(gid, pen)
        if pen.d:
            defs.append('<path id="g%d" d="%s"/>' % (gid, ''.join(pen.d)))

    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
           'viewBox="0 0 %d %d">' % (img_width, img_height, img_width, img_height),
           '<rect width="100%" height="100%" fill="#fff"/>']
    if guides:
        for x in (left_margin, left_margin + line_width):
            out.append('<line x1="%s" y1="0" x2="%s" y2="%d" stroke="#e0a0a0" '
                       'stroke-width="0.5"/>' % (_num(x), _num(x), img_height))
    out.append('<defs>%s</defs>' % ''.join(defs))
    out.append('<g fill="#000">%s</g>' % ''.join(uses))
    out.append('</svg>')
    return '\n'.join(out)
