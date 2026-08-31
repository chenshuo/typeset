import os
import ctypes
import cairo
import freetype
from datetime import datetime
from common import Box, Glue

LINE_SKIP = 1.4  # multiplier of font size for baseline vertical distance
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


def render(font, size, lines, line_width, output):
    ft_face = freetype.Face(font)
    ft_face.set_char_size(int(size * FREETYPE_SCALE), 0, 72, 72)
    left_margin = size
    right_margin = size
    line_height = size * LINE_SKIP
    img_width = int(left_margin + line_width + right_margin)
    img_height = int((len(lines) + 1) * line_height)

    ext = os.path.splitext(output)[1].lower()
    if ext == ".pdf":
        surface = cairo.PDFSurface(output, img_width, img_height)
    elif ext == ".png":
        surface = cairo.ImageSurface(cairo.FORMAT_RGB24, img_width, img_height)
    else:
        raise ValueError(f"Unsupported output format: '{ext}' (expected .png or .pdf)")

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
                    arr = (_CairoGlyph * len(it.glyphs))(*(_CairoGlyph(int(gid), x + pos_x, y + pos_y) for gid, x, y in it.glyphs))
                    _libcairo.cairo_show_glyphs(raw_cr, arr, len(it.glyphs))
                pos_x += it.width
            elif isinstance(it, Glue):
                pos_x += it.get_width(ratio)
        pos_y += line_height
        # print(pos_x - left_margin)

    # print(datetime.now() - start)

    _libcairo.cairo_font_face_destroy(ff_ptr)
    if ext == ".pdf":
        surface.finish()
        print(f"Saved PDF to: {output} ({img_width}x{img_height} px)\n")
    else:
        surface.write_to_png(output)
        print(f"Saved PNG to: {output} ({img_width}x{img_height} px)\n")
