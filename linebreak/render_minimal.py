#!/usr/bin/env python3

import argparse
import os, sys

from datetime import datetime
import uharfbuzz as hb

from common import Box, Glue
from minimal import line_break, show_results
from render_lib import DEFAULT_FONT, FREETYPE_SCALE, render
from sample import SAMPLE_TEXT


def get_items(font_file, size, text):
    start = datetime.now()
    blob = hb.Blob.from_file_path(font_file)
    face = hb.Face(blob)
    font = hb.Font(face)
    font.scale = (int(size * FREETYPE_SCALE), int(size * FREETYPE_SCALE))

    load = datetime.now()
    # print(load - start)
    print(f'size: {size}px')
    items = [Box(size * 2)]  # 2em

    space = hb.Buffer()
    space.add_str(' ')
    space.guess_segment_properties()
    hb.shape(font, space)
    space_width = space.glyph_positions[0].x_advance / FREETYPE_SCALE
    print(f'space_width: {space_width}+{space_width/2}-{space_width/3:.3f} px')
    space_glue = Glue(space_width, space_width / 2, space_width / 3)

    for word in text.split():
        buf = hb.Buffer()
        buf.add_str(word)
        buf.guess_segment_properties()
        features = {"kern": True, "liga": True}
        hb.shape(font, buf, features)

        glyphs = []
        pos_x = 0.0
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            glyphs.append((
                info.codepoint,
                pos_x + pos.x_offset / FREETYPE_SCALE,
                pos.y_offset / FREETYPE_SCALE
            ))
            pos_x += pos.x_advance / FREETYPE_SCALE

        # width = sum(pos.x_advance for pos in buf.glyph_positions) / FREETYPE_SCALE
        box = Box(pos_x, word)
        box.glyphs = glyphs

        items.append(box)
        items.append(space_glue)
        # print(f'<{word}> {box.width:6.3f} {glyphs}')

    # print(datetime.now() - load)
    return items

def main():
    ap = argparse.ArgumentParser(description="Render a paragraph using the minimal version of Knuth-Plass line-breaking algorithm.")
    ap.add_argument("text", nargs="?", default="", help="The text to render")
    # ap.add_argument("-hb", action="store_true", help="Enable HarfBuzz text-shaping (handles kerning/ligatures)")
    ap.add_argument("--font", default=DEFAULT_FONT, help="Path to OTF/TTF/TTC font file")
    ap.add_argument("--font_index", type=int, default=0, help="Font index of TTC font")
    ap.add_argument("--size", type=float, default=24.0, help="Font size in px (default: 24)")
    ap.add_argument("--text_width", type=float, default=29.0, help="Text width in em (default: 29)")
    ap.add_argument("--output", default="output.png", help="Output file path (PNG or PDF, default: output.png)")
    args = ap.parse_args()

    if not os.path.exists(args.font):
        print(f"Error: Font file '{args.font}' not found.")
        sys.exit(1)

    line_width = args.size * args.text_width
    print(f'line_width: {line_width}px')
    text = args.text if args.text else SAMPLE_TEXT
    items = get_items(args.font, args.size, text)
    print(f'items: {len(items)}')
    breaks = line_break(items, line_width, 1.0)

    lines = show_results(items, line_width, breaks)
    print(f'lines: {len(lines)}')
    render(args.font, args.size, lines, line_width, args.output)


if __name__ == '__main__':
    main()

