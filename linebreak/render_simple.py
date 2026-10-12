#!/usr/bin/env python3

import argparse
import os, sys

import math
from datetime import datetime
import uharfbuzz as hb
import pyphen

from common import Box, Glue, Penalty, HYPHEN_PENALTY
from util import get_box, get_space_glue
import simple
from simple import line_break, show_results
from render_lib import DEFAULT_FONT, FREETYPE_SCALE, render
from sample import SAMPLE_TEXT


def may_hyphenate(hyphen_dict, word):
    if not hyphen_dict or len(word) < 5:
        return None

    n = len(word)
    return [p for p in hyphen_dict.positions(word.lower()) if 2 <= p <= n - 3]


def get_items(font_file, size, hyphen_dict, text):
    start = datetime.now()
    blob = hb.Blob.from_file_path(font_file)
    face = hb.Face(blob)
    font = hb.Font(face)
    font.scale = (int(size * FREETYPE_SCALE), int(size * FREETYPE_SCALE))

    hyphen_width = get_box("-", font).width
    hyphen_penalty = Penalty(HYPHEN_PENALTY, hyphen_width, '-')
    print(f'hyphen:', hyphen_penalty)

    load = datetime.now()
    # print(load - start)
    space_glue = get_space_glue(font)
    print(f'space:', space_glue)
    print(f'size: {size}px')
    items = [Box(size * 2, '  ')]  # 2em

    for word in text.split():
        if hyphens := may_hyphenate(hyphen_dict, word):
            prev = 0
            for hyphen in hyphens:
                syllable = word[prev:hyphen]
                items.append(get_box(syllable, font))
                items.append(hyphen_penalty)
                prev = hyphen
            items.append(get_box(word[prev:], font))
        else:
            box = get_box(word, font)
            items.append(box)
        items.append(space_glue)
        # print(f'<{word}> {box.width:6.3f} {glyphs}')

    items.append(Glue(0, math.inf, 0))
    items.append(Penalty.EJECT)
    # print(datetime.now() - load)
    return items


def main():
    ap = argparse.ArgumentParser(description="Render a paragraph using the minimal version of Knuth-Plass line-breaking algorithm.")
    ap.add_argument("text", nargs="?", default="", help="The text to render")
    # ap.add_argument("-hb", action="store_true", help="Enable HarfBuzz text-shaping (handles kerning/ligatures)")
    ap.add_argument("--font", default=DEFAULT_FONT, help="Path to OTF/TTF/TTC font file")
    ap.add_argument("--font_index", type=int, default=0, help="Font index of TTC font (default: 0)")
    ap.add_argument("--size", type=float, default=18.0, help="Font size in px (default: 18)")
    ap.add_argument("--text_width", type=float, default=27.0, help="Text width in em (default: 27)")
    ap.add_argument("--hyphen", action=argparse.BooleanOptionalAction, default=True, help="Enable hyphenation (default: true)")
    ap.add_argument("--output", default="output.pdf", help="Output file path (PNG or PDF, default: output.pdf)")
    args = ap.parse_args()

    if not os.path.exists(args.font):
        print(f"Error: Font file '{args.font}' not found.")
        sys.exit(1)

    line_width = args.size * args.text_width
    print(f'line_width: {line_width}px')
    text = args.text if args.text else SAMPLE_TEXT

    hyphen_dict = None
    if args.hyphen:
        hyphen_dict = pyphen.Pyphen(lang='en_US')
        print('Loaded hyphen dict.')

    items = get_items(args.font, args.size, hyphen_dict, text)
    print(f'items: {len(items)}')

    if simple.TRACE:
        cum_width = 0
        for i, item in enumerate(items):
            if not isinstance(item, Penalty):
                cum_width += item.width
            print('%3d  %12s  %6.3f  %8.3f' % (i, item.text, item.width, cum_width))

    breaks = line_break(items, line_width, 1.0)
    # print(f'breaks: {len(breaks)}', breaks)

    lines = show_results(items, line_width, breaks)
    print(f'lines: {len(lines)}')
    render(args.font, args.size, lines, line_width, args.output)


if __name__ == '__main__':
    main()

