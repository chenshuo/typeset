"""Stand-in for ../render_lib.py in the browser, which needs cairo and freetype.

typeset.py imports FREETYPE_SCALE and render_paragraphs from render_lib; the web
page renders with svg_render.render_svg() instead.
"""

FREETYPE_SCALE = 64


def render(*args, **kwargs):
    raise NotImplementedError('use svg_render.render_svg() in the browser')


def render_paragraphs(*args, **kwargs):
    raise NotImplementedError('use svg_render.render_svg() in the browser')
