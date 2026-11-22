#!/usr/bin/env python3

import argparse
from pathlib import Path
import os, sys
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import partial

from common import Box, Glue, Penalty, HYPHEN_PENALTY
import font_util, util
import basic
from basic import line_break, show_results
from render_lib import FREETYPE_SCALE, render

import pyphen
import uharfbuzz as hb
import uniseg.linebreak

FONT = '/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc'
    # 0 is JP, 1 is KR, 2 is SC, 3 is TC, 4 is HK
FONT_INDEX = 2

SAMPLE_TEXT = """天下之患，最不可为者，名为治平无事，而其实有不测之忧。坐观其变，而不为之所，则恐至於不可救；起而强为之，则天下狃於治平之安而不吾信。惟仁人君子豪杰之士，为能出身为天下犯大难，以求成大功；此固非勉强期月之间，而苟以求名之所能也。"""

STOP_PUNCTS = set('、：，；。．！？')
OPEN_PUNCTS = set('‘“（《〈「『【〖〔［｛')
CLOSE_PUNCTS = set('’”）》〉」』】〗〕］｝')
CJK_PUNCTS = STOP_PUNCTS | OPEN_PUNCTS | CLOSE_PUNCTS

def get_hb_font(font, size):
    hb_blob = hb.Blob.from_file_path(font.path)
    hb_face = hb.Face(hb_blob, font.index)
    hb_font = hb.Font(hb_face)
    hb_font.scale = (int(size * FREETYPE_SCALE), int(size * FREETYPE_SCALE))
    return hb_font


def is_latin_word(word: str):
  return not any(unicodedata.east_asian_width(ch) in ('W', 'F') for ch in word)


def may_hyphenate(hyphen_dict, word):
    if not hyphen_dict or len(word) < 5:
        return None

    n = len(word)
    return [p for p in hyphen_dict.positions(word.lower()) if 2 <= p <= n - 3]


@dataclass
class Params:
  hb_font: hb.Font
  size:   float   # font size in pt or px
  hyphen_lang:   str = ''     # 'en_US' to enable it
  indent:        float = 2    # in em
  cjk_stretch:   float = 1/8  # in em
  cjk_shrink:    float = 0    # in em
  punct_stretch: float = 1/3  # in em
  punct_shrink:  float = 1/4  # in em
  autospace:     float = 1/4  # CJK-Latin gap, in em
  runt_penalty:  int = 0

  # Injectable for unittests
  get_box: Callable = util.get_box
  line_break_units: Callable = uniseg.linebreak.line_break_units


def get_items(text, p: Params):
  em = lambda x: x * p.size

  items = []

  cjk_glue = Glue(0, em(p.cjk_stretch), em(p.cjk_shrink), '')
  punct_glue = Glue(em(0.5), em(p.punct_stretch), em(p.punct_shrink), '')

  space_width = p.get_box(' ', p.hb_font).width
  space_glue = Glue(space_width, space_width / 2, space_width / 3)
  autospace_width = em(p.autospace)
  autospace_glue = Glue(autospace_width, autospace_width / 2, autospace_width / 3)

  hyphen_dict = pyphen.Pyphen(lang=p.hyphen_lang) if p.hyphen_lang else None
  hyphen_width = p.get_box('-', p.hb_font).width
  hyphen_penalty = Penalty(HYPHEN_PENALTY, hyphen_width, '-', is_hyphen=True)
  explicit_hyphen_penalty = Penalty(HYPHEN_PENALTY, is_hyphen=True)


  # Known bug: CJK punctuation with Latin word
  # - 《TeX排版》 will be devided into 《TeX|排|版》
  # - 使用TeX。 -> 使|用|TeX。|
  # “TeX技术”   -> “TeX|技|术” (the difficult one)
  def get_boxes_cjk(word):
    assert not is_latin_word(word)
    for i, ch in enumerate(word):
      box = p.get_box(ch, p.hb_font, features={'halt': True})
      items.append(box)
      if i < len(word) - 1:
        items.append(Penalty.NO_BREAK)
        items.append(cjk_glue)


  def get_boxes_latin(word):
    if hyphens := may_hyphenate(hyphen_dict, word):
      prev = 0
      for hyphen in hyphens:
          syllable = word[prev:hyphen]
          items.append(p.get_box(syllable, p.hb_font))
          items.append(hyphen_penalty)
          prev = hyphen
      items.append(p.get_box(word[prev:], p.hb_font))
    else:
      box = p.get_box(word, p.hb_font)
      items.append(box)


  units = [u for u in p.line_break_units(text) if u.strip()]
  if not units:
    return items

  if p.indent > 0:
    items.append(Box(em(p.indent), '　' * p.indent))

  for i, seg in enumerate(units):
    word = seg.rstrip(' ')
    assert word

    # UAX #14 keeps the trailing space in the unit ('Hello '); move it into glue.
    has_space = len(word) < len(seg)

    next_word = units[i+1] if i+1 < len(units) else ''

    if is_latin_word(word):
      get_boxes_latin(word)
    else:
      get_boxes_cjk(word)

    assert isinstance(items[-1], Box)
    if p.runt_penalty > 0 and i == len(units) - 2:
      items.append(Penalty(p.runt_penalty))

    if is_latin_word(word) and is_latin_word(next_word):
      if has_space:
        items.append(space_glue)
      elif word[-1] == '-':
        items.append(explicit_hyphen_penalty)
      else:
        items.append(Glue.ZERO)
    else:
      last_char = word[-1]
      next_char = next_word[0] if next_word else ''
      # dealt with “ and ” in latin words, e.g. 他说 “Hi” 然后
      if last_char in (STOP_PUNCTS | CLOSE_PUNCTS) and not is_latin_word(word):
        items.append(punct_glue)
      elif next_char in OPEN_PUNCTS and not is_latin_word(next_word):
        items.append(punct_glue)
      elif is_latin_word(word) != is_latin_word(next_word):
        items.append(autospace_glue)
      else:
        items.append(cjk_glue)


  assert isinstance(items[-1], (Glue, Penalty))
  items.pop()
  items.append(Penalty.NO_BREAK)
  items.append(Glue.INF)
  items.append(Penalty.EJECT)
  return items


def break_lines(text, line_width, params: Params, hyphen_lang='en_US'):
  """Breaks text into lines of line_width, in up to three passes like TeX.

  1. Items from params as given (normally no hyphenation), rho = 1.0.
  2. Items with hyphenation in hyphen_lang, rho = 1.5.
  3. Final pass on the same items, rho = 2, overfull lines allowed.

  Returns (items, breaks).  The items are those of the pass that succeeded,
  breaks index into them.  Returns ([], []) for empty text.
  """
  def may_trace(items):
    if basic.TRACE:
      for i, it in enumerate(items):
        print('%3d' % i, it)

  # First pass, with rho = 1.0
  items = get_items(text, params)
  if not items:
    return items, []
  may_trace(items)
  try:
    return items, line_break(items, line_width)
  except RuntimeError as ex:
    if basic.TRACE:
      print(ex)

  # Second pass, enable hyphenation
  items = get_items(text, replace(params, hyphen_lang=hyphen_lang))
  if basic.TRACE:
    print('second pass')
    may_trace(items)
  try:
    return items, line_break(items, line_width, max_stretch_ratio=1.5)
  except RuntimeError as ex:
    if basic.TRACE:
      print(ex)

  # Final pass, rho = 2.0 and set final_pass=True
  if basic.TRACE:
    print('final pass')
  return items, line_break(items, line_width, max_stretch_ratio=2.0,
                           final_pass=True)


def render_paragraph(text, size, text_width_em, runt_penalty, output, font, hyphen_lang):
    hb_font = get_hb_font(font, size)
    params = Params(hb_font, size, runt_penalty=runt_penalty)

    line_width = size * text_width_em
    items, breaks = break_lines(text, line_width, params, hyphen_lang)
    assert breaks

    lines = show_results(items, line_width, breaks)
    render(font.path, size, lines, line_width, output, font_index=font.index)


def resolve_font(ap, args) -> font_util.FontInfo:
    if args.font and args.font_file:
        ap.error("--font and --font_file are mutually exclusive")

    if args.font:
        font = font_util.find_font(args.font)
        if not font:
            ap.error(f"font not found: {args.font!r}, try --font_list")
        return font

    if args.font_file:
        if not os.path.isfile(args.font_file):
            ap.error(f"no such font file: {args.font_file}")
        return font_util.FontInfo(family='', style='', path=args.font_file,
                                  index=args.font_index)

    font = font_util.default_cjk_font()
    if not font:
        ap.error("no CJK font found, please specify --font or --font_file")
    return font


EXAMPLES = """\
examples:
  %(prog)s                                  # built-in sample -> output.pdf
  %(prog)s input.txt --output out.png
  %(prog)s '学而时习之，不亦说乎？' --text_width 10
  %(prog)s --font 'Noto Serif CJK TC' --size 16
  %(prog)s --font_file my.ttc --font_index 2
  %(prog)s --font_list
"""


def main():
    ap = argparse.ArgumentParser(
        description="Render a paragraph of CJK (or mixed CJK/Latin) text into a PDF or PNG,\n"
                    "using the Knuth-Plass line-breaking algorithm.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("text", metavar="TEXT", nargs="?", default="",
                    help="text to typeset, or path to a UTF-8 text file "
                         "(default: a built-in Chinese sample)")

    g = ap.add_argument_group("font")
    g.add_argument("--font", metavar="NAME",
                   help="font family name, e.g. 'Noto Serif CJK SC' or 'Noto Serif CJK SC:bold' "
                        "(default: a suitable installed CJK font)")
    g.add_argument("--font_file", metavar="PATH",
                   help="load font from an OTF/TTF/TTC file instead of by name; "
                        "cannot be used with --font")
    g.add_argument("--font_index", metavar="N", type=int, default=0,
                   help="face index within a TTC file, used with --font_file "
                        "(default: %(default)s)")
    g.add_argument("--font_list", action="store_true",
                   help="list installed Chinese fonts and exit")

    g = ap.add_argument_group("layout")
    g.add_argument("--size", metavar="PX", type=float, default=12.0,
                   help="font size in px (default: %(default)s)")
    g.add_argument("--text_width", metavar="EM", type=float, default=22.0,
                   help="line width in em, i.e. number of CJK characters per line "
                        "(default: %(default)s)")
    g.add_argument("--hyphen_lang", metavar="LANG", default="en_US",
                   help="language for hyphenating Latin words, tried only when no good "
                        "breaks are found without it; '' to disable (default: %(default)s)")
    g.add_argument("--runt_penalty", metavar="N", type=int, default=0,
                   help="penalty for leaving a single word or character alone on the "
                        "last line; 0 to disable (default: %(default)s)")

    g = ap.add_argument_group("output")
    g.add_argument("--output", metavar="FILE", default="output.pdf",
                   help="output file, format chosen by extension: .pdf or .png "
                        "(default: %(default)s)")
    g.add_argument("--trace", action="store_true",
                   help="print the items and each line-breaking pass")
    args = ap.parse_args()

    if args.font_list:
      font_util.print_font_list('zh-cn')
      return
    if args.trace:
        basic.TRACE = True
    text = SAMPLE_TEXT
    if args.text:
      if os.path.exists(args.text):
        text = Path(args.text).read_text(encoding="utf-8")
      else:
        text = args.text

    font = resolve_font(ap, args)
    render_paragraph(text, args.size, args.text_width, args.runt_penalty, args.output,
                     font, args.hyphen_lang)


if __name__ == '__main__':
    main()
