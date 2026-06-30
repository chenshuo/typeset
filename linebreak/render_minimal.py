#!/usr/bin/env python3

import argparse
import os, sys

import ctypes
import cairo
import freetype
import uharfbuzz as hb
import uniseg

from datetime import datetime
from common import Box, Glue, show_results
from minimal import line_break
from sample import SAMPLE_TEXT

LINE_SKIP = 1.4  # multipler of font size for baseline vertical distance
FREETYPE_SCALE = 64
DEFAULT_FONT = "fonts/LinLibertine_R.otf"

_libcairo = ctypes.CDLL("libcairo.so.2")
_libcairo.cairo_ft_font_face_create_for_ft_face.restype = ctypes.c_void_p
_libcairo.cairo_ft_font_face_create_for_ft_face.argtypes = [ctypes.c_void_p, ctypes.c_int]
_libcairo.cairo_set_font_face.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
_libcairo.cairo_set_font_size.argtypes = [ctypes.c_void_p, ctypes.c_double]
_libcairo.cairo_show_glyphs.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
_libcairo.cairo_font_face_destroy.argtypes = [ctypes.c_void_p]

_PTR_SIZE = ctypes.sizeof(ctypes.c_void_p)

class _CairoGlyph(ctypes.Structure):
    _fields_ = [
        ("index", ctypes.c_ulong),
        ("x",     ctypes.c_double),
        ("y",     ctypes.c_double),
    ]

def _raw_ptr(pycairo_obj) -> int:
    """Extract the raw Cairo pointer from a pycairo wrapper object."""
    return ctypes.c_void_p.from_address(id(pycairo_obj) + 2 * _PTR_SIZE).value

def _ft_face_ptr(ft_face: freetype.Face) -> int:
    """Extract the raw FT_Face pointer from a freetype-py Face object."""
    return ctypes.cast(ft_face._FT_Face, ctypes.c_void_p).value


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
    space_glue.text = ' '

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


def render(font, size, lines, line_width, output):
    ft_face = freetype.Face(font)
    ft_face.set_char_size(int(size * FREETYPE_SCALE), 0, 72, 72)
    left_margin = size
    right_margin = size
    line_height = size * LINE_SKIP
    img_width = int(left_margin + line_width + right_margin)
    img_height = int((len(lines) + 1) * line_height)

    surface = cairo.ImageSurface(cairo.FORMAT_RGB24, img_width, img_height)
    cr = cairo.Context(surface)
    cr.set_source_rgb(1, 1, 1)
    cr.paint()
    cr.set_source_rgb(0, 0, 0)

    # Pass our FreeType FT_Face pointer to Cairo
    raw_cr = _raw_ptr(cr)
    ff_ptr = _libcairo.cairo_ft_font_face_create_for_ft_face(_ft_face_ptr(ft_face), 0)
    _libcairo.cairo_set_font_face(raw_cr, ff_ptr)
    _libcairo.cairo_set_font_size(raw_cr, ctypes.c_double(size))

    start = datetime.now()
    pos_y = line_height + size * (LINE_SKIP - 1.0)
    for ratio, line in lines:
        pos_x = left_margin
        for it in line:
            if isinstance(it, Box):
                if it.glyphs:
                    arr = (_CairoGlyph* len(it.glyphs))(*(_CairoGlyph(int(gid), x + pos_x, y + pos_y) for gid, x, y in it.glyphs))
                    _libcairo.cairo_show_glyphs(raw_cr, arr, len(it.glyphs))
                pos_x += it.width
            elif isinstance(it, Glue):
                pos_x += it.get_width(ratio)
        pos_y += line_height
        # print(pos_x - left_margin)

    # print(datetime.now() - start)

    _libcairo.cairo_font_face_destroy(ff_ptr)
    surface.write_to_png(output)
    print(f"Saved PNG to: {output} ({img_width}x{img_height} px)\n")

def main():
    ap = argparse.ArgumentParser(description="Render a paragraph using the minimal version of Knuth-Plass line-breaking algorithm.")
    ap.add_argument("text", nargs="?", default="", help="The text to render")
    # ap.add_argument("-hb", action="store_true", help="Enable HarfBuzz text-shaping (handles kerning/ligatures)")
    ap.add_argument("--font", default=DEFAULT_FONT, help="Path to OTF/TTF/TTC font file")
    ap.add_argument("--font_index", type=int, default=0, help="Font index of TTC font")
    ap.add_argument("--size", type=float, default=24.0, help="Font size in px (default: 24)")
    ap.add_argument("--text_width", type=float, default=29.0, help="Text width in em (default: 29)")
    ap.add_argument("--output", default="output.png", help="Output PNG path (default: output.png)")
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

