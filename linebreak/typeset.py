#!/usr/bin/env python3

import argparse
from pathlib import Path
import re, os
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, replace

from common import Box, Glue, Penalty, HYPHEN_PENALTY
import font_util, util
import simple
from simple import line_break, show_results
from render_lib import FREETYPE_SCALE, render_paragraphs

import pyphen
import uharfbuzz as hb
import uniseg.linebreak

SAMPLE_TEXT = """天下之患，最不可为者，名为治平无事，而其实有不测之忧。坐观其变，而不为之所，则恐至於不可救；起而强为之，则天下狃於治平之安而不吾信。惟仁人君子豪杰之士，为能出身为天下犯大难，以求成大功；此固非勉强期月之间，而苟以求名之所能也。"""

STOP_PUNCTS = set('、：，；。．！？')
OPEN_PUNCTS = set('‘“（《〈「『【〖〔［｛')
CLOSE_PUNCTS = set('’”）》〉」』】〗〕］｝')
CJK_PUNCTS = STOP_PUNCTS | OPEN_PUNCTS | CLOSE_PUNCTS
NO_BREAK_BEFORE = STOP_PUNCTS | CLOSE_PUNCTS

# Curly quotes are ambiguous width: full width in Noto CJK SC even next to
# Latin letters, as in “Hello”, so pwid makes them proportional in a Latin
# piece.  In a CJK piece, fwid then halt makes them 1/2em in fonts with
# proportional quotes too, e.g. Noto CJK JP, and makes —— 2em in Noto CJK
# SC, where each — is narrower than 1em.
CJK_FEATURES = {'fwid': True, 'halt': True}
LATIN_FEATURES = {'pwid': True}

@dataclass
class Style:
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


@dataclass
class Piece:
  """A single CJK char, or a run of Latin text, inside a UAX #14 unit."""

  text: str
  is_latin: bool
  has_trailing_space: bool = False
  allow_break_after: bool = True


def is_wide(ch):
  return unicodedata.east_asian_width(ch) in ('W', 'F')


def is_latin_word(word: str):
  return not any(is_wide(ch) for ch in word)


def may_break_at_quote(prev: Piece, ch: str):
  """Breaks LB19a leaves out, as CJK quotes are tied to CJK text.

  UAX #14 LB19a allows a break before an opening quote only if East Asian
  chars are on both sides, so '读“TeX' is one unit.  Break before an opening
  quote after a CJK char, 读|“TeX, and after a closing quote before a CJK
  char, TeX”|一.
  """
  if prev.is_latin:
    return False
  last = prev.text[-1]
  if ch in '‘“':
    return last not in OPEN_PUNCTS
  if last in '’”':
    # Not before a stop punct, ……, —— or another quote.
    return ch not in NO_BREAK_BEFORE and is_wide(ch)
  return False


def split_paragraphs(text):
  """Splits text into paragraphs at blank lines, like TeX and Markdown.

  A line of spaces, tabs or U+3000 is blank too.  A single newline stays
  in the paragraph, get_items() joins the lines.  The indent typed at the
  start of a paragraph, e.g. '\u3000\u3000', is dropped, as Style.indent sets it.
  """
  text = text.replace('\r\n', '\n')
  paras = re.split(r'\n[ \t\u3000]*\n', text)   # blank line(s)
  paras = (p.strip(' \t\u3000\n') for p in paras)
  return [p for p in paras if p]


def join_lines(text):
  """Joins the lines of a paragraph into one, like TeX.

  A newline, with the spaces around it, vanishes next to a wide (CJK) char,
  e.g. 学而\\n时习, and is a space between other chars, e.g. Hello\\nworld.
  Also strips the text, so that blank text becomes ''.
  """
  text = text.replace('\r\n', '\n').strip(' \t\n')

  def repl(m):
    # The text is stripped, so a newline is never at either end, and both
    # neighbors exist.  Wide, not is_cjk_char(): curly quotes are ambiguous
    # width, so 'said\n“Hi”' gets a space, while '说\n“你”' does not.
    # Between CJK and Latin, e.g. '用\nTeX', the newline vanishes too and
    # get_items() puts the autospace there, as for '用TeX'.
    before, after = text[m.start() - 1], text[m.end()]
    return '' if is_wide(before) or is_wide(after) else ' '

  # One match per run of newlines with the spaces and tabs around them, so
  # 'Hello \n world' and 'a\n\nb' each get a single space.  U+3000 is left
  # alone: it is a char the author typed, not layout of the source.
  return re.sub(r'[ \t]*(?:\n[ \t]*)+', repl, text)


def split_unit(unit):
  """Splits a UAX #14 unit into pieces.

  A unit without wide chars is one Latin piece, so its curly quotes stay
  Latin, e.g. “Hi”.  A mixed unit like 'TeX。' or '《TeX》' is split into
  CJK chars and Latin runs, so that the Latin runs are shaped as a whole.
  """

  def is_cjk_char(ch):
    if ch in CJK_PUNCTS or is_wide(ch):
      return True
    # Ambiguous punct like —— and …… sides with CJK in a CJK unit,
    # Ambiguous letters like é do not.
    return (unicodedata.east_asian_width(ch) == 'A'
            and unicodedata.category(ch).startswith('P'))

  # UAX #14 keeps the trailing space in the unit ('Hello '); move it into glue.
  word = unit.rstrip(' ')
  if not word:
    return []

  has_space = len(word) < len(unit)
  pieces = []
  # The Chinese dash —— is CJK even in a unit of its own, e.g. in 说——好 or
  # “好——”, but a single — is Latin, e.g. 'Hello — world'.
  if is_latin_word(word) and '——' not in word:
    return [Piece(word, True, has_trailing_space=has_space, allow_break_after=True)]
  for ch in word:
    if ch == '—' and pieces and pieces[-1].text[-1] == '—' and not pieces[-1].is_latin:
      # —— in one piece, as dashes shaped one by one leave a gap between them.
      pieces[-1].text += ch
    elif is_cjk_char(ch):
      if pieces and may_break_at_quote(pieces[-1], ch):
        pieces[-1].allow_break_after = True
      pieces.append(Piece(ch, False, allow_break_after=False))
    elif pieces and pieces[-1].is_latin:
      pieces[-1].text += ch
    else:
      pieces.append(Piece(ch, True, allow_break_after=False))

  pieces[-1].has_trailing_space = has_space
  pieces[-1].allow_break_after = True
  return pieces


@dataclass
class Glues:
  """The glues and penalties get_items() puts between and inside pieces."""

  cjk: Glue
  punct: Glue               # the other half of a halt'ed punct
  space: Glue               # between Latin words
  autospace: Glue           # between CJK and Latin
  hyphen: Penalty           # a discretionary hyphen inside a Latin word
  explicit_hyphen: Penalty  # after a '-' in the text


def make_glues(p: Style) -> Glues:
  em = lambda x: x * p.size
  space_width = p.get_box(' ', p.hb_font).width
  autospace_width = em(p.autospace)
  hyphen_width = p.get_box('-', p.hb_font).width
  return Glues(
      cjk=Glue(0, em(p.cjk_stretch), em(p.cjk_shrink), ''),
      punct=Glue(em(0.5), em(p.punct_stretch), em(p.punct_shrink), ''),
      space=Glue(space_width, space_width / 2, space_width / 3),
      autospace=Glue(autospace_width, autospace_width / 2, autospace_width / 3),
      hyphen=Penalty(HYPHEN_PENALTY, hyphen_width, '-', is_hyphen=True),
      explicit_hyphen=Penalty(HYPHEN_PENALTY, is_hyphen=True))


def may_hyphenate(hyphen_dict, word):
  if not hyphen_dict or len(word) < 5:
    return []

  # \lefthyphenmin=2 \righthyphenmin=3 % disallow x- or -xx breaks
  n = len(word)
  return [p for p in hyphen_dict.positions(word.lower()) if 2 <= p <= n - 3]


def piece_boxes(piece: Piece, p: Style, hyphen_dict, hyphen: Penalty):
  """The boxes of a piece, with discretionary hyphens in a Latin word."""
  if not piece.is_latin:
    return [p.get_box(piece.text, p.hb_font, features=CJK_FEATURES)]

  word = piece.text
  items = []
  prev = 0
  for pos in may_hyphenate(hyphen_dict, word):
    items += [p.get_box(word[prev:pos], p.hb_font, features=LATIN_FEATURES),
              hyphen]
    prev = pos
  items.append(p.get_box(word[prev:], p.hb_font, features=LATIN_FEATURES))
  return items


def glue_between(piece: Piece, next_piece: Piece | None, g: Glues):
  """The items between two pieces: a glue or penalty, after a NO_BREAK
  penalty if the pieces are in the same UAX #14 unit."""
  if next_piece is None:
    return []  # get_items() ends the paragraph after the last piece

  items = [] if piece.allow_break_after else [Penalty.NO_BREAK]
  last = piece.text[-1]
  first = next_piece.text[0]

  if piece.is_latin and next_piece.is_latin:
    if piece.has_trailing_space:
      return items + [g.space]
    if last == '-':
      return items + [g.explicit_hyphen]
    return items + [Glue.ZERO]

  # The other half of a halt'ed punct, but no more than one punct glue
  # between two puncts in a unit, e.g. ？”.  A proportional quote in a
  # Latin piece, e.g. in 说 “Hi” 然, gets it too, so that it looks the
  # same as the halt'ed quote in 说“Hi”然.
  if last in NO_BREAK_BEFORE or first in OPEN_PUNCTS:
    return items + [g.punct if piece.allow_break_after else g.cjk]

  if piece.is_latin != next_piece.is_latin:
    # No autospace next to a CJK punct, e.g. TeX。 or （TeX）.
    if last in OPEN_PUNCTS or first in NO_BREAK_BEFORE:
      return items + [g.cjk]
    return items + [g.autospace]

  if last + first in ('……', '——'):
    return items + [Glue.ZERO]
  return items + [g.cjk]


def runt_break(pieces):
  """The index of the piece before the last break in the paragraph, or None.

  A runt penalty there makes a lone last word or char, e.g. '患。' in a
  unit of its own, cost more.  It goes before the glue, which simple.py
  discards after a break.
  """
  for i in range(len(pieces) - 2, -1, -1):
    if pieces[i].allow_break_after:
      return i
  return None


def get_items(text, p: Style):
  """Turns a paragraph into Knuth-Plass boxes, glues and penalties."""
  pieces = []
  for unit in p.line_break_units(join_lines(text)):
    pieces.extend(split_unit(unit))
  if not pieces:
    return []

  g = make_glues(p)
  hyphen_dict = pyphen.Pyphen(lang=p.hyphen_lang) if p.hyphen_lang else None
  items = []
  if p.indent > 0:
    # The text is for display only; the indent need not be a whole number.
    items.append(Box(p.indent * p.size, '　' * round(p.indent)))

  runt_at = runt_break(pieces) if p.runt_penalty > 0 else None
  for i, piece in enumerate(pieces):
    next_piece = pieces[i + 1] if i + 1 < len(pieces) else None
    items += piece_boxes(piece, p, hyphen_dict, g.hyphen)
    if i == runt_at:
      items.append(Penalty(p.runt_penalty))
    items += glue_between(piece, next_piece, g)

  # End the paragraph like TeX's \parfillskip, with a forced break.
  assert isinstance(items[-1], Box)
  return items + [Penalty.NO_BREAK, Glue.INF, Penalty.EJECT]


def break_lines(text, line_width, style: Style, hyphen_lang='en_US'):
  """Breaks text into lines of line_width, in up to three passes like TeX.

  1. Items from style as given (normally no hyphenation), rho = 1.0.
  2. Items with hyphenation in hyphen_lang, rho = 1.5.
  3. Final pass on the same items, rho = 2, overfull lines allowed.

  Returns (items, breaks).  The items are those of the pass that succeeded,
  breaks index into them.  Returns ([], []) for empty text.
  """
  def trace(name, items):
    if simple.TRACE:
      print(name)
      for i, it in enumerate(items):
        print('%3d' % i, it)

  def try_pass(name, items, **kwargs):
    """Breaks lines, or returns None if no feasible breaks are found."""
    trace(name, items)
    try:
      return line_break(items, line_width, **kwargs)
    except RuntimeError as ex:
      if simple.TRACE:
        print(ex)
      return None

  items = get_items(text, style)
  if not items:
    return [], []
  if (breaks := try_pass('first pass', items)) is not None:
    return items, breaks

  items = get_items(text, replace(style, hyphen_lang=hyphen_lang))
  if (breaks := try_pass('second pass', items, max_stretch_ratio=1.5)) is not None:
    return items, breaks

  # The final pass always sets the paragraph, with overfull lines if need be.
  trace('final pass', [])
  return items, line_break(items, line_width, max_stretch_ratio=2.0,
                           final_pass=True)


def typeset_paragraphs(paragraphs, line_width, style: Style, hyphen_lang='en_US'):
  """Breaks each paragraph into lines on its own, like TeX.

  Returns a list of lines for each paragraph, as show_results() makes them.
  """
  result = []
  for i, text in enumerate(paragraphs):
    items, breaks = break_lines(text, line_width, style, hyphen_lang)
    assert breaks, text  # split_paragraphs() drops blank paragraphs
    print(f'Paragraph {i + 1} of {len(paragraphs)}')
    result.append(show_results(items, line_width, breaks))
  return result


@dataclass
class Layout:
  """The page, as opposed to Style for the text in a paragraph."""

  text_width: float = 22.0  # line width in em
  par_skip:   float = 0.5   # extra space between paragraphs, in em


def render_document(paragraphs, font, style: Style, layout: Layout, output,
                    hyphen_lang='en_US'):
  line_width = style.size * layout.text_width
  lines = typeset_paragraphs(paragraphs, line_width, style, hyphen_lang)
  render_paragraphs(font.path, style.size, lines, line_width, output,
                    font_index=font.index, par_skip=layout.par_skip)


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


def read_text(args):
  """The text to typeset: a file, the TEXT argument, or the built-in sample."""
  if not args.text:
    return SAMPLE_TEXT
  if os.path.exists(args.text):
    return Path(args.text).read_text(encoding="utf-8")
  return args.text


EXAMPLES = """\
examples:
  %(prog)s                                  # built-in sample -> output.pdf
  %(prog)s input.txt --output out.png
  %(prog)s '学而时习之，不亦说乎？' --text_width 10
  %(prog)s --indent 2                       # indent the first line by 2 em
  %(prog)s book.txt --parskip 0.5           # paragraphs are split at blank lines
  %(prog)s --font 'Noto Serif CJK TC' --size 16
  %(prog)s --font_file my.ttc --font_index 2
  %(prog)s --font_list
"""


def build_arg_parser():
  ap = argparse.ArgumentParser(
      description="Render CJK (or mixed CJK/Latin) text into a PDF or PNG,\n"
                  "using the Knuth-Plass line-breaking algorithm.",
      epilog=EXAMPLES,
      formatter_class=argparse.RawDescriptionHelpFormatter)
  ap.add_argument("text", metavar="TEXT", nargs="?", default="",
                  help="text to typeset, or path to a UTF-8 text file; blank lines "
                       "separate paragraphs (default: a built-in Chinese sample)")

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
  g.add_argument("--text_width", metavar="EM", type=float, default=Layout.text_width,
                 help="line width in em, i.e. number of CJK characters per line "
                      "(default: %(default)s)")
  g.add_argument("--indent", metavar="EM", type=float, default=Style.indent,
                 help="indent of the first line in em, e.g. 2 for Chinese text "
                      "(default: %(default)s)")
  g.add_argument("--parskip", metavar="EM", type=float, default=Layout.par_skip,
                 help="extra space between paragraphs in em; Chinese text usually "
                      "relies on the indent alone (default: %(default)s)")
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
  return ap


def get_hb_font(font, size):
  hb_blob = hb.Blob.from_file_path(font.path)
  hb_face = hb.Face(hb_blob, font.index)
  hb_font = hb.Font(hb_face)
  hb_font.scale = (int(size * FREETYPE_SCALE), int(size * FREETYPE_SCALE))
  return hb_font


def main():
  ap = build_arg_parser()
  args = ap.parse_args()
  if args.font_list:
    font_util.print_font_list('zh-cn')
    return
  if args.trace:
    simple.TRACE = True
  if args.indent < 0:
    ap.error("--indent must not be negative")
  if args.parskip < 0:
    ap.error("--parskip must not be negative")

  paragraphs = split_paragraphs(read_text(args))
  if not paragraphs:
    ap.error("no text to typeset")

  font = resolve_font(ap, args)
  style = Style(get_hb_font(font, args.size), args.size,
                indent=args.indent, runt_penalty=args.runt_penalty)
  layout = Layout(text_width=args.text_width, par_skip=args.parskip)
  render_document(paragraphs, font, style, layout, args.output, args.hyphen_lang)


if __name__ == '__main__':
  main()
