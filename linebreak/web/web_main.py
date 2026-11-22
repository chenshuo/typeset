"""Entry point for the web page: typesets text into SVG with typeset.py."""

import contextlib
import io

import simple
import font_util
import typeset
import svg_render


def typeset_text(text, font_path, size=12.0, text_width=typeset.Layout.text_width,
                 indent=typeset.Style.indent, par_skip=typeset.Layout.par_skip,
                 hyphen_lang='en_US', runt_penalty=0, trace=False, guides=False):
    """Returns (svg, log).  Blank lines separate paragraphs, as in typeset.py."""
    font = font_util.FontInfo('', '', font_path, 0)
    style = typeset.Style(typeset.get_hb_font(font, size), size,
                          indent=max(indent, 0), runt_penalty=runt_penalty)
    layout = typeset.Layout(text_width=text_width, par_skip=max(par_skip, 0))
    line_width = size * layout.text_width

    simple.TRACE = trace
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        paragraphs = typeset.split_paragraphs(text)
        lines = typeset.typeset_paragraphs(paragraphs, line_width, style, hyphen_lang)
    svg = svg_render.render_svg(style.hb_font, size, lines, line_width,
                                par_skip=layout.par_skip, guides=guides)
    return svg, log.getvalue()
