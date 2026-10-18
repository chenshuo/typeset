import uharfbuzz as hb

from common import Box, Glue

FREETYPE_SCALE = 64

def get_box(word: str, hb_font, features={}) -> Box:
    buf = hb.Buffer()
    buf.add_str(word)
    buf.guess_segment_properties()
    hb.shape(hb_font, buf, features)

    glyphs = []
    pos_x = 0.0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        glyphs.append((
            info.codepoint,
            pos_x + pos.x_offset / FREETYPE_SCALE,
            pos.y_offset / FREETYPE_SCALE
        ))
        pos_x += pos.x_advance / FREETYPE_SCALE

    box = Box(pos_x, word)
    box.glyphs = glyphs
    return box


def get_space_glue(hb_font) -> Glue:
    space_width = get_box(' ', hb_font).width
    space_glue = Glue(space_width, space_width / 2, space_width / 3)
    return space_glue


