import unicodedata
from pathlib import Path
from dataclasses import replace

import pytest

from common import Box, Glue, Penalty, HYPHEN_PENALTY, INF_PENALTY
import font_util
import util
import typeset
from typeset import (
    Piece, split_unit, is_latin_word, may_hyphenate, get_items, break_lines,
    get_hb_font, Style, SAMPLE_TEXT, STOP_PUNCTS, OPEN_PUNCTS, CLOSE_PUNCTS,
    CJK_PUNCTS, CJK_FEATURES, LATIN_FEATURES)

SIZE = 10.0
# The font's 'halt' feature covers more than CJK_PUNCTS, e.g. these.
HALT_PUNCTS = CJK_PUNCTS | set('〘〙〚〛')

TEXT1 = "臣本布衣，躬耕于南阳，苟全性命于乱世，不求闻达于诸侯。先帝不以臣卑鄙，猥自枉屈，三顾臣于草庐之中，谘臣以当世之事，由是感激，遂许先帝以驱驰。"
TEXT2 = """《论语》子曰：“学而时习之，不亦说乎？有朋自远方来，不亦乐乎？人不知而不愠，不亦君子乎？”"""
TEXT3 = """子曰：“三人行，必有我师焉。择其善者而从之，其不善者而改之。”"""
TEXT4 = 'Knuth和Plass在1981年发表了Breaking Paragraphs into Lines一文，提出了TeX使用的断行算法。'


def fake_get_box(word, hb_font, features={}):
  """Font-free get_box: wide chars 1em, halt'ed CJK punct 1/2em,
  space 1/4em, other (Latin) chars 1/2em."""
  width = 0.0
  for ch in word:
    if ch == ' ':
      width += SIZE / 4
    elif features.get('halt') and ch in HALT_PUNCTS:
      width += SIZE / 2
    elif unicodedata.east_asian_width(ch) in ('W', 'F'):
      width += SIZE
    else:
      width += SIZE / 2
  return Box(width, word)


def make_params(**kwargs):
  kwargs.setdefault('indent', 0)
  return Style(None, SIZE, get_box=fake_get_box, **kwargs)


def items_of(text, **kwargs):
  """get_items() without the paragraph-end triple."""
  items = get_items(text, make_params(**kwargs))
  assert items[-3:] == [Penalty.NO_BREAK, Glue.INF, Penalty.EJECT]
  return items[:-3]


def items_of_units(*units, **kwargs):
  """Like items_of(), but with a fixed segmentation instead of UAX #14."""
  text = ''.join(units)
  def line_break_units(t):
    assert t == text
    return list(units)
  return items_of(text, line_break_units=line_break_units, **kwargs)


def tokens(items):
  """Compact, readable form of an item list."""
  out = []
  for it in items:
    if isinstance(it, Box):
      out.append(it.text)
    elif isinstance(it, Glue):
      if it == Glue.ZERO:
        out.append('~0')
      elif it.width == 0 and it.text == '':
        out.append('~cjk')
      elif it.width == SIZE / 2 and it.text == '':
        out.append('~punct')
      elif it.text == ' ':
        out.append('~space')
      else:
        out.append(f'~{it}')
    else:
      assert isinstance(it, Penalty)
      if it.value >= INF_PENALTY:
        out.append('nb')
      elif it.is_hyphen:
        out.append('-?' if it.width > 0 else 'hy')
      else:
        out.append(f'P{it.value}')
  return out


def natural_width(items):
  return sum(it.width for it in items if not isinstance(it, Penalty))


def legal_breaks(items):
  """Indices where Knuth-Plass may break."""
  return [i for i, it in enumerate(items)
          if (isinstance(it, Penalty) and it.value < INF_PENALTY)
          or (isinstance(it, Glue) and i > 0 and isinstance(items[i-1], Box))]


# ---------------------------------------------------------------- helpers

def test_is_latin_word():
  assert is_latin_word('')
  assert is_latin_word('Hello')
  assert is_latin_word(' “Hi”')
  assert is_latin_word('1981')
  assert is_latin_word('well-')
  # East Asian Width 'A' (ambiguous) counts as Latin.  is_cjk_char() sides
  # them with CJK inside a mixed unit, see test_rigid_dash_and_ellipsis.
  assert is_latin_word('——')
  assert is_latin_word('……')

  assert not is_latin_word('我')
  assert not is_latin_word(' “变”')
  assert not is_latin_word('。')
  assert not is_latin_word('（')
  assert not is_latin_word('Lines，')


def test_punct_sets_are_disjoint():
  assert not (STOP_PUNCTS & OPEN_PUNCTS)
  assert not (STOP_PUNCTS & CLOSE_PUNCTS)
  assert not (OPEN_PUNCTS & CLOSE_PUNCTS)


def test_punct_east_asian_width():
  # CJK puncts are Wide or Fullwidth, so a unit that contains one is not
  # is_latin_word().  The curly quotes are the exception: they are Ambiguous
  # and count as Latin, see test_latin_quotes_next_to_cjk.
  quotes = set('‘’“”')
  assert quotes <= CJK_PUNCTS
  for ch in sorted(CJK_PUNCTS):
    width = unicodedata.east_asian_width(ch)
    if ch in quotes:
      assert width == 'A', ch
      assert is_latin_word(ch), ch
    else:
      assert width in ('W', 'F'), ch
      assert not is_latin_word(ch), ch


def test_may_hyphenate():
  import pyphen
  dic = pyphen.Pyphen(lang='en_US')
  assert may_hyphenate(None, 'hyphenation') == []
  assert may_hyphenate(dic, 'into') == []  # shorter than 5

  word = 'hyphenation'
  pos = may_hyphenate(dic, word)
  assert pos
  assert all(2 <= p <= len(word) - 3 for p in pos)
  assert pos == sorted(pos)
  # Case-insensitive
  assert may_hyphenate(dic, 'Hyphenation') == pos


# ------------------------------------------------------------ segmentation

def test_uniseg_contract():
  """Pin the UAX #14 segmentations get_items() relies on (uniseg 0.10)."""
  from uniseg.linebreak import line_break_units
  cases = {
      'Hello world': ['Hello ', 'world'],
      'well-known': ['well-', 'known'],
      '中文': ['中', '文'],
      '你好，世界。': ['你', '好，', '世', '界。'],
      '说《论语》好': ['说', '《论', '语》', '好'],
      '说「好」吗': ['说', '「好」', '吗'],
      # LB19a: quotes between East Asian chars allow breaks.
      '上“大学': ['上', '“大', '学'],
      '曰：“学': ['曰：', '“学'],
      '乎？”好': ['乎？”', '好'],
      '“TeX book”': ['“TeX ', 'book”'],
      '读“TeX book”': ['读“TeX ', 'book”'],
      '读 “TeX book”': ['读 ', '“TeX ', 'book”'],
      'Knuth和1981年': ['Knuth', '和', '1981', '年'],
      # ——, …… stay with the char before them, or stand alone.
      '他说……好': ['他', '说……', '好'],
      '他说——好': ['他', '说', '——', '好'],
      # Mixed units, see split_unit().
      '使用TeX。': ['使', '用', 'TeX。'],
      '用《TeX》排': ['用', '《TeX》', '排'],
  }
  for text, units in cases.items():
    assert list(line_break_units(text)) == units, text


def test_split_unit():
  P = Piece
  assert split_unit('Hello') == [P('Hello', True)]
  assert split_unit('Hello ') == [P('Hello', True, True)]
  assert split_unit('看 ') == [P('看', False, True)]
  assert split_unit('“Hi”') == [P('“Hi”', True)]
  assert split_unit('TeX。') == [P('TeX', True, allow_break_after=False), P('。', False)]
  assert split_unit('《TeX》') == [P('《', False, allow_break_after=False),
                                   P('TeX', True, allow_break_after=False),
                                   P('》', False)]
  # —— is one piece.
  assert split_unit('好——') == [P('好', False, allow_break_after=False),
                                P('——', False)]
  assert split_unit('——。') == [P('——', False, allow_break_after=False),
                                P('。', False)]
  assert split_unit('——') == [P('——', False)]


def test_split_unit_more_break():
  """Breaks around CJK quotes that UAX #14 LB19a does not allow."""
  P = Piece
  assert split_unit('读“TeX ') == [P('读', False),
                                  P('“', False, allow_break_after=False),
                                  P('TeX', True, True)]
  assert split_unit('了“TeX”一') == [
      P('了', False), P('“', False, allow_break_after=False),
      P('TeX', True, allow_break_after=False), P('”', False),
      P('一', False)]
  # No break before a stop punct, or between two open puncts.
  assert split_unit('读“TeX”。') == [
      P('读', False), P('“', False, allow_break_after=False),
      P('TeX', True, allow_break_after=False),
      P('”', False, allow_break_after=False), P('。', False)]
  assert [p.allow_break_after for p in split_unit('“《TeX》”')] == \
      [False, False, False, False, True]


def test_open_quote_after_cjk_in_unit():
  # '读“TeX ' is one UAX #14 unit; 读 keeps the 1/2em before the halt'ed “.
  assert tokens(items_of('读“TeX book”')) == [
      '读', '~punct', '“', 'nb', '~cjk', 'TeX', '~space', 'book”']
  assert tokens(items_of('了“TeX”一')) == [
      '了', '~punct', '“', 'nb', '~cjk', 'TeX', 'nb', '~cjk', '”', '~punct',
      '一']


def test_segmenter_gets_raw_text():
  seen = []
  def line_break_units(text):
    seen.append(text)
    return [text]
  items_of('用 TeX', line_break_units=line_break_units)
  assert seen == ['用 TeX']


def test_break_opportunities_come_from_units():
  # One unit: no break anywhere inside.
  assert legal_breaks(items_of_units('中文排版')) == []
  # Two units: exactly one break, between them.
  items = items_of_units('中文', '排版')
  assert tokens(items) == ['中', 'nb', '~cjk', '文', '~cjk', '排', 'nb',
                           '~cjk', '版']
  assert legal_breaks(items) == [4]


def test_blank_units_dropped():
  assert tokens(items_of_units('Hello ', ' ', 'world')) == [
      'Hello', '~space', 'world']
  assert tokens(items_of_units('中 ', '  ', '文')) == ['中', '~cjk', '文']


def test_trailing_spaces_stripped():
  assert tokens(items_of_units('Hello   ', 'world')) == [
      'Hello', '~space', 'world']


def test_latin_break_without_space():
  # e.g. UAX #14 allows a break after '/': zero-width glue.
  assert tokens(items_of_units('and/', 'or')) == ['and/', '~0', 'or']


# ---------------------------------------------------------- paragraph frame

def test_indent():
  items = get_items('中文', make_params(indent=2))
  assert isinstance(items[0], Box)
  assert items[0].width == 2 * SIZE
  assert items[0].text == '　　'

  items = get_items('中文', make_params(indent=0))
  assert items[0].text == '中'

  # The indent need not be a whole number of em.
  items = get_items('中文', make_params(indent=1.5))
  assert items[0].width == 1.5 * SIZE
  assert items[1].text == '中'


def test_paragraph_end():
  for text in ['中文。', 'Hello world', 'Knuth和Plass']:
    items = get_items(text, make_params())
    assert items[-3:] == [Penalty.NO_BREAK, Glue.INF, Penalty.EJECT]
    assert isinstance(items[-4], Box)


def test_empty_text():
  # No items at all, not even the indent box or the paragraph end.
  for text in ['', ' ', '   ', '\n', '\n\n']:
    for indent in [0, 2]:
      assert get_items(text, make_params(indent=indent)) == [], repr(text)


def test_no_glue_after_glue_or_at_start():
  for text in [SAMPLE_TEXT, TEXT1, TEXT2, TEXT3, TEXT4]:
    items = items_of(text, indent=2)
    assert isinstance(items[0], Box)
    for a, b in zip(items, items[1:]):
      assert not (isinstance(a, Glue) and isinstance(b, Glue)), (a, b)


def test_no_whitespace_box():
  for text in ['第一段。\n', '中\n文', 'Hello\nworld\n', '中文\n\n']:
    for it in get_items(text, make_params()):
      if isinstance(it, Box):
        assert it.text and it.text.strip() == it.text, (text, it)


def test_trailing_newline():
  for text in ['中文。', 'Hello world', 'Knuth和Plass']:
    assert tokens(items_of(text + '\n')) == tokens(items_of(text))


def test_soft_newline():
  """A single newline inside a paragraph joins lines, like TeX."""
  # Between CJK chars it vanishes.
  assert tokens(items_of('中\n文')) == tokens(items_of('中文'))
  assert tokens(items_of('你好，\n世界。')) == tokens(items_of('你好，世界。'))
  # Between Latin words it is a space.
  assert tokens(items_of('Hello\nworld')) == tokens(items_of('Hello world'))
  # Between CJK and Latin it is the autospace, as for a source space.
  assert tokens(items_of('用\nTeX\n排版')) == tokens(items_of('用TeX排版'))


# -------------------------------------------------------------- paragraphs
# Paragraphs are separated by blank lines, like TeX and Markdown.
# typeset.split_paragraphs() is looked up at call time, so that only these
# tests fail while it is missing.

def split_paragraphs(text):
  return typeset.split_paragraphs(text)


def test_split_paragraphs_empty():
  for text in ['', '\n', '\n\n', '  \n\t\n　\n']:
    assert split_paragraphs(text) == [], repr(text)


def test_split_paragraphs_one():
  assert split_paragraphs('中文') == ['中文']
  assert split_paragraphs('中文\n') == ['中文']
  assert split_paragraphs('Hello world') == ['Hello world']


def test_split_paragraphs_blank_line():
  assert split_paragraphs('第一段。\n\n第二段。') == ['第一段。', '第二段。']
  assert split_paragraphs('甲\n\n乙\n\n丙\n') == ['甲', '乙', '丙']


def test_split_paragraphs_keeps_single_newline():
  # A single newline stays in the paragraph, get_items() joins the lines,
  # see test_soft_newline.
  assert split_paragraphs('第一行\n第二行\n\n第二段') == [
      '第一行\n第二行', '第二段']
  assert split_paragraphs('Hello\nworld\n\nBye') == ['Hello\nworld', 'Bye']


def test_split_paragraphs_several_blank_lines():
  assert split_paragraphs('甲\n\n\n\n乙') == ['甲', '乙']
  # An odd number of newlines leaves no '\n' at the start of the next one.
  assert split_paragraphs('甲\n\n\n乙') == ['甲', '乙']
  assert split_paragraphs('甲\n\n \n乙') == ['甲', '乙']


def test_split_paragraphs_whitespace_only_line_is_blank():
  # Spaces, tabs and the ideographic space U+3000 are invisible, so a line
  # of them is blank too.
  for blank in [' ', '  ', '\t', '　', ' \t　 ']:
    text = f'甲\n{blank}\n乙'
    assert split_paragraphs(text) == ['甲', '乙'], repr(text)


def test_split_paragraphs_leading_trailing_blank_lines():
  assert split_paragraphs('\n\n甲\n\n') == ['甲']
  assert split_paragraphs('\n \n甲\n\n乙\n \n') == ['甲', '乙']


def test_split_paragraphs_strips_source_indent():
  # Style.indent sets the indent; an indent typed in the source, e.g. '　　'
  # in Chinese text, is dropped so as not to indent twice.
  assert split_paragraphs('　　甲。\n\n　　乙。') == ['甲。', '乙。']
  assert split_paragraphs('  Hello\n\n\tworld') == ['Hello', 'world']
  # Only at the start of a paragraph, not of a line inside it.
  assert split_paragraphs('　　甲\n　　乙') == ['甲\n　　乙']


def test_split_paragraphs_crlf():
  # Text from argv or stdin may keep '\r\n' (Path.read_text() does not).
  assert split_paragraphs('甲\r\n\r\n乙\r\n') == ['甲', '乙']
  assert split_paragraphs('Hello\r\nworld') == ['Hello\nworld']


def test_split_paragraphs_then_get_items():
  text = ('　　《论语》子曰：“学而时习之，\n不亦说乎？”\n'
          '\n'
          'Knuth和Plass在1981年发表了\nBreaking Paragraphs into Lines一文。\n'
          '\n\n')
  paragraphs = split_paragraphs(text)
  assert len(paragraphs) == 2
  for para in paragraphs:
    items = get_items(para, make_params(indent=2))
    assert items[0].width == 2 * SIZE  # each paragraph is indented
    assert items[-3:] == [Penalty.NO_BREAK, Glue.INF, Penalty.EJECT]
    joined = ''.join(b.text for b in items[1:] if isinstance(b, Box))
    assert joined == ''.join(para.split()), para


def test_typeset_paragraphs():
  text = '甲乙丙丁戊己庚辛\n壬癸。\n\nHello world.\n\n\n子丑寅卯。\n'
  paragraphs = split_paragraphs(text)
  result = typeset.typeset_paragraphs(paragraphs, 6 * SIZE,
                                      make_params(indent=2))
  assert len(result) == 3
  texts = [[''.join(it.text for it in line if isinstance(it, Box))
            for _, line in lines] for lines in result]
  # Each paragraph is indented and broken on its own.
  assert texts[0] == ['　　甲乙丙丁', '戊己庚辛壬癸。']
  assert ''.join(texts[1]) == '　　Helloworld.'
  assert texts[2] == ['　　子丑寅卯。']


def test_typeset_paragraphs_none():
  assert typeset.typeset_paragraphs([], 6 * SIZE, make_params()) == []


# ---------------------------------------------------------------- pure CJK

def test_cjk_ideographs():
  assert tokens(items_of('中文排版')) == [
      '中', '~cjk', '文', '~cjk', '排', '~cjk', '版']
  cjk = items_of('中文')[1]
  assert cjk.stretch == SIZE / 8 and cjk.shrink == 0


def test_stop_punct_half_width_plus_glue():
  items = items_of('你好，世界。')
  assert tokens(items) == ['你', '~cjk', '好', 'nb', '~cjk', '，', '~punct',
                           '世', '~cjk', '界', 'nb', '~cjk', '。']
  comma = items[5]
  assert comma.width == SIZE / 2  # 'halt'
  punct = items[6]
  assert (punct.width, punct.stretch, punct.shrink) == \
      pytest.approx((SIZE/2, SIZE/3, SIZE/4))
  # Comma + its glue is a full em in the middle of the line.
  assert natural_width(items[5:7]) == SIZE


def test_no_break_before_stop_punct():
  items = items_of('你好，世界。')
  breaks = legal_breaks(items)
  # Can break after '你' and after '，', but never before '，' or '。'.
  assert [tokens(items)[i - 1] for i in breaks] == ['你', '，', '世']


def test_open_close_punct():
  items = items_of('说《论语》好')
  assert tokens(items) == ['说', '~punct', '《', 'nb', '~cjk', '论', '~cjk',
                           '语', 'nb', '~cjk', '》', '~punct', '好']
  # 《 and 》 are half width each, the other halves come from punct glue.
  assert natural_width(items) == 6 * SIZE
  # No break right after 《 or right before 》.
  toks = tokens(items)
  for i in legal_breaks(items):
    assert toks[i - 1] != '《'
    assert toks[i + 1] != '》'


def test_bracket_pairs():
  pairs = '（）《》〈〉「」『』【】〖〗〔〕［］｛｝'
  for left, right in zip(pairs[::2], pairs[1::2]):
    assert left in OPEN_PUNCTS and right in CLOSE_PUNCTS
    items = items_of_units('说', left + '好' + right, '吗')
    assert tokens(items) == ['说', '~punct', left, 'nb', '~cjk', '好', 'nb',
                             '~cjk', right, '~punct', '吗']
    # Each bracket is 1/2em wide plus 1/2em of punct glue outside.
    assert natural_width(items) == 5 * SIZE


def test_consecutive_punct_compressed():
  # ：“ gets a single punct glue: 1.5em, not 2em.
  items = items_of('曰：“学')
  assert tokens(items) == ['曰', 'nb', '~cjk', '：', '~punct', '“', 'nb',
                           '~cjk', '学']
  assert natural_width(items[3:6]) == 1.5 * SIZE

  # ？” inside one unit: 1em, plus punct glue after it.
  items = items_of('乎？”好')
  assert tokens(items) == ['乎', 'nb', '~cjk', '？', 'nb', '~cjk', '”',
                           '~punct', '好']
  assert natural_width(items[3:8]) == 1.5 * SIZE


@pytest.mark.xfail(strict=True, reason='known bug: 〘〙 are not in '
                   'OPEN_PUNCTS/CLOSE_PUNCTS, so they get no punct glue')
def test_halt_outside_punct_sets():
  # 〘〙 are halt'ed like other CJK brackets, so they need punct glue too.
  items = items_of_units('见', '〘注〙', '文')
  assert natural_width(items) == 5 * SIZE


def squash(toks, ch):
  """Joins a run of ch tokens, dropping 'nb' and '~0' inside the run."""
  is_run = lambda t: t and set(t) == {ch}
  out = []
  for t in toks:
    if is_run(t):
      j = len(out)
      while j > 0 and out[j-1] in ('nb', '~0'):
        j -= 1
      if j > 0 and is_run(out[j-1]):
        del out[j:]
        out[-1] += t
        continue
    out.append(t)
  return out


def test_squash():
  assert squash(['说', 'nb', '~cjk', '…', 'nb', '~0', '…', '~cjk', '好'], '…') == \
      ['说', 'nb', '~cjk', '……', '~cjk', '好']
  assert squash(['……', '~cjk', '好'], '…') == ['……', '~cjk', '好']


@pytest.mark.parametrize('text, ch, expected', [
    # '说……' is one unit, '——' is a unit of its own.
    ('他说……好', '…', ['他', '~cjk', '说', 'nb', '~cjk', '……', '~cjk', '好']),
    ('他说——好', '—', ['他', '~cjk', '说', '~cjk', '——', '~cjk', '好']),
])
def test_rigid_dash_and_ellipsis(text, ch, expected):
  """——, …… side with CJK (no autospace), and never stretch, shrink or
  break in the middle.  They may be one box or several."""
  assert squash(tokens(items_of(text)), ch) == expected


def test_dash_in_a_unit_of_its_own():
  # —— is CJK, at either end of a paragraph too.
  assert tokens(items_of('他说——')) == ['他', '~cjk', '说', '~cjk', '——']
  assert tokens(items_of('——好')) == ['——', '~cjk', '好']
  # With a CJK punct in its unit, e.g. '——”' in '“好——”'.
  assert tokens(items_of('“好——”')) == [
      '“', 'nb', '~cjk', '好', '~cjk', '——', 'nb', '~cjk', '”']
  # A single — is Latin, with spaces around it.
  assert tokens(items_of('Hello — world')) == [
      'Hello', '~space', '—', '~space', 'world']
  assert tokens(items_of('他说 — 好')) == ['他', '~cjk', '说', '~space', '—',
                                          '~space', '好']


# ------------------------------------------------------------------- Latin

def test_latin_words():
  items = items_of('Hello world')
  assert tokens(items) == ['Hello', '~space', 'world']
  space = items[1]
  w = fake_get_box(' ', None).width
  assert (space.width, space.stretch, space.shrink) == (w, w / 2, w / 3)


def test_latin_multiple_spaces():
  assert tokens(items_of('Hello   world')) == ['Hello', '~space', 'world']


def test_explicit_hyphen():
  assert tokens(items_of('well-known fact')) == [
      'well-', 'hy', 'known', '~space', 'fact']


def test_trailing_hyphen():
  # The explicit hyphen penalty at the very end is dropped.
  assert tokens(items_of('well-')) == ['well-']
  assert tokens(items_of('so well-')) == ['so', '~space', 'well-']


def test_no_hyphenation_by_default():
  assert tokens(items_of('Breaking Paragraphs')) == [
      'Breaking', '~space', 'Paragraphs']


def test_hyphenation():
  items = items_of('Breaking Paragraphs', hyphen_lang='en_US')
  toks = tokens(items)
  assert '-?' in toks
  # Syllables concatenate back to the words.
  assert ''.join(t for t in toks if not t.startswith(('~', '-?'))) == \
      'BreakingParagraphs'
  for it in items:
    if isinstance(it, Penalty) and it.is_hyphen:
      assert it.value == HYPHEN_PENALTY
      assert it.width == fake_get_box('-', None).width
      assert it.text == '-'


# ------------------------------------------------------------- CJK + Latin

def test_cjk_latin_space():
  assert tokens(items_of('Knuth和Plass在1981年')) == [
      'Knuth', '~space', '和', '~space', 'Plass', '~space', '在', '~space',
      '1981', '~space', '年']


def test_cjk_latin_source_space_not_doubled():
  assert tokens(items_of('用 TeX 排版')) == tokens(items_of('用TeX排版'))
  assert tokens(items_of('Hello 世界')) == tokens(items_of('Hello世界'))


def test_autospace_param():
  items = items_of('用TeX排', autospace=0.5)
  assert tokens(items) == ['用', '~space', 'TeX', '~space', '排']
  for glue in (items[1], items[3]):
    assert (glue.width, glue.stretch, glue.shrink) == \
        pytest.approx((SIZE/2, SIZE/4, SIZE/6))

  # The space between Latin words still comes from the font.
  items = items_of('用TeX Hello', autospace=0.5)
  assert tokens(items) == ['用', '~space', 'TeX', '~space', 'Hello']
  assert items[1].width == SIZE / 2
  assert items[3].width == fake_get_box(' ', None).width


def test_cjk_stop_punct_before_latin():
  # Punct glue takes precedence: '，' keeps its 1/2em, no autospace on top.
  items = items_of_units('文，', 'TeX', '排')
  assert tokens(items) == ['文', 'nb', '~cjk', '，', '~punct', 'TeX',
                           '~space', '排']


def test_latin_before_cjk_open_punct():
  items = items_of_units('Knuth', '（高）')
  assert tokens(items) == ['Knuth', '~punct', '（', 'nb', '~cjk', '高', 'nb',
                           '~cjk', '）']


def test_latin_followed_by_cjk_punct():
  """No autospace between a Latin run and a CJK punct in the same unit,
  just CJK glue as in '界。'."""
  assert tokens(items_of('使用TeX。')) == [
      '使', '~cjk', '用', '~space', 'TeX', 'nb', '~cjk', '。']
  assert tokens(items_of('TeX，好')) == [
      'TeX', 'nb', '~cjk', '，', '~punct', '好']


def test_latin_inside_cjk_brackets():
  assert tokens(items_of('用《TeX》排')) == [
      '用', '~punct', '《', 'nb', '~cjk', 'TeX', 'nb', '~cjk', '》', '~punct',
      '排']
  assert tokens(items_of('（TeX）')) == [
      '（', 'nb', '~cjk', 'TeX', 'nb', '~cjk', '）']


def test_latin_quotes_next_to_cjk():
  # “” in a Latin unit, i.e. with spaces typed around it, are proportional,
  # not halt'ed, but get punct glue like the CJK quotes in 说“Hi”然, so
  # that the spaces make no difference.
  items = items_of_units('说 ', '“Hi” ', '然')
  assert tokens(items) == ['说', '~punct', '“Hi”', '~punct', '然']
  assert tokens(items_of('说“Hi”然')) == [
      '说', '~punct', '“', 'nb', '~cjk', 'Hi', 'nb', '~cjk', '”', '~punct', '然']
  # CJK punct on the other side still gets its punct glue.
  items = items_of_units('好，', '“Hi”', '（好）')
  assert tokens(items) == ['好', 'nb', '~cjk', '，', '~punct', '“Hi”',
                           '~punct', '（', 'nb', '~cjk', '好', 'nb', '~cjk',
                           '）']


def test_mixed_text4():
  items = items_of(TEXT4)
  toks = tokens(items)
  for word in ['Knuth', 'Plass', '1981', 'Breaking', 'Paragraphs', 'into',
               'Lines', 'TeX']:
    assert word in toks, word


# ---------------------------------------------------------------- runt

def test_runt_penalty():
  items = items_of('Hello big world', runt_penalty=50)
  assert tokens(items) == ['Hello', '~space', 'big', 'P50', '~space', 'world']
  # The glue after the penalty is not a legal break, so the only way to put
  # 'world' alone on the last line is to pay the penalty.
  assert 4 not in legal_breaks(items)

  assert 'P50' not in tokens(items_of('Hello big world'))


def test_runt_penalty_cjk():
  # At the last break, never inside a unit, e.g. not before '。'.
  assert tokens(items_of('你好，世界。', runt_penalty=50)) == [
      '你', '~cjk', '好', 'nb', '~cjk', '，', '~punct', '世', 'P50', '~cjk',
      '界', 'nb', '~cjk', '。']
  # No runt penalty without a break.
  assert 'P50' not in tokens(items_of_units('中文', runt_penalty=50))


def test_runt_penalty_avoids_lone_char():
  params = make_params()
  items, breaks = break_lines(TEXT1, 14 * SIZE, params)
  assert lines_of(items, breaks)[-1] == '驰。'
  items, breaks = break_lines(TEXT1, 14 * SIZE, replace(params, runt_penalty=50))
  assert lines_of(items, breaks)[-1] == '驱驰。'


@pytest.mark.parametrize('text, last', [('Hello big world', 'world'),
                                        ('你好，世界。', '界。')])
def test_break_at_runt_penalty_discards_glue(text, last):
  # The glue after the penalty must not start the last line.
  items, breaks = break_lines(text, 4 * SIZE, make_params(runt_penalty=50))
  assert items[breaks[-2].end] == Penalty(50)
  assert isinstance(items[breaks[-1].start], Box)
  assert lines_of(items, breaks)[-1] == last


# ------------------------------------------------------------ break_lines

@pytest.fixture
def passes(monkeypatch):
  """Records the keyword args of each line_break() call in break_lines()."""
  calls = []
  line_break = typeset.line_break
  def recorder(items, line_width, **kwargs):
    calls.append(kwargs)
    return line_break(items, line_width, **kwargs)
  monkeypatch.setattr(typeset, 'line_break', recorder)
  return calls


FIRST_PASS = {}
SECOND_PASS = {'max_stretch_ratio': 1.5}
FINAL_PASS = {'max_stretch_ratio': 2, 'final_pass': True}
HYPHEN_TEXT = 'the hyphenation algorithm works'


def lines_of(items, breaks):
  """Text of each line, with the hyphen of a hyphenated break."""
  lines = []
  for b in breaks:
    text = ''.join(it.text for it in items[b.start:b.end]
                   if not isinstance(it, Penalty) and it != Glue.INF)
    if isinstance(items[b.end], Penalty):
      text += items[b.end].text
    lines.append(text)
  return lines


def test_break_lines_first_pass(passes):
  items, breaks = break_lines(HYPHEN_TEXT, 12 * SIZE, make_params())
  assert passes == [FIRST_PASS]
  assert lines_of(items, breaks) == ['the hyphenation algorithm', 'works']
  assert '-?' not in tokens(items)
  assert items == get_items(HYPHEN_TEXT, make_params())


def test_break_lines_second_pass_hyphenates(passes):
  items, breaks = break_lines(HYPHEN_TEXT, 10 * SIZE,
                              make_params(runt_penalty=50))
  assert passes == [FIRST_PASS, SECOND_PASS]
  assert lines_of(items, breaks) == ['the hyphenation algo-', 'rithm works']
  assert all(-1 <= b.ratio <= 1.5 for b in breaks)
  # Other params are kept in the second pass.
  assert items == get_items(
      HYPHEN_TEXT, make_params(runt_penalty=50, hyphen_lang='en_US'))
  assert 'P50' in tokens(items)


def test_break_lines_final_pass(passes):
  # Each line holds one 1em char plus 1/2em that no glue can fill.
  items, breaks = break_lines('中文排版', 1.5 * SIZE, make_params())
  assert passes == [FIRST_PASS, SECOND_PASS, FINAL_PASS]
  assert breaks
  assert breaks[0].start == 0
  assert breaks[-1].end == len(items) - 1


def test_break_lines_hyphen_lang(passes):
  # No hyphenation in the second pass either: falls through to the final one.
  items, breaks = break_lines(HYPHEN_TEXT, 10 * SIZE, make_params(),
                              hyphen_lang='')
  assert passes == [FIRST_PASS, SECOND_PASS, FINAL_PASS]
  assert '-?' not in tokens(items)
  assert breaks


@pytest.mark.parametrize('text', ['', '   ', '\n'])
def test_break_lines_empty_text(passes, text):
  assert break_lines(text, 10 * SIZE, make_params(indent=2)) == ([], [])
  assert passes == []


# --------------------------------------------------------------- real font

# Pinned rather than font_util.default_cjk_font(), as the exact widths below
# depend on the font.  It is the default for zh-cn where installed.
FONT_FAMILY = 'Noto Serif CJK SC'


@pytest.fixture(scope='module')
def hb_font():
  try:
    font = font_util.find_font(FONT_FAMILY)
  except OSError:
    pytest.skip('no fontconfig')
  if font is None:
    pytest.skip(f'no font {FONT_FAMILY}')
  return get_hb_font(font, SIZE)


def test_real_font_halt(hb_font):
  for ch in CJK_PUNCTS:
    full = util.get_box(ch, hb_font)
    half = util.get_box(ch, hb_font, features={'halt': True})
    assert full.width == SIZE, ch
    assert half.width == SIZE / 2, ch
  assert util.get_box('中', hb_font, features={'halt': True}).width == SIZE


def test_real_font_latin_quotes(hb_font):
  # Full width by default in the SC font, proportional in a Latin piece.
  assert util.get_box('“', hb_font).width == SIZE
  assert util.get_box('“', hb_font, features=LATIN_FEATURES).width < SIZE / 2
  box = get_items('“Hi”', Style(hb_font, SIZE, indent=0))[0]
  assert box.text == '“Hi”'
  assert box.width < util.get_box('“Hi”', hb_font).width - SIZE


def test_real_font_cjk_dash(hb_font):
  # Each — is narrower than 1em in the SC font, fwid makes —— 2em.
  assert util.get_box('——', hb_font, features={'halt': True}).width < 2 * SIZE
  assert util.get_box('——', hb_font, features=CJK_FEATURES).width == 2 * SIZE


def test_real_font_cjk_quotes_jp():
  # The JP face has proportional quotes, which halt alone does not halve.
  path = Path(__file__).with_name('NotoSerifCJK-Regular.ttc')
  if not path.exists():
    pytest.skip(f'no font file {path.name}')
  font = get_hb_font(font_util.FontInfo('', '', str(path), 0), SIZE)
  for ch in '‘’“”':
    assert util.get_box(ch, font, features={'halt': True}).width < SIZE / 2, ch
    assert util.get_box(ch, font, features=CJK_FEATURES).width == SIZE / 2, ch


@pytest.mark.parametrize('text', [SAMPLE_TEXT, TEXT1, TEXT2, TEXT3, TEXT4],
                         ids=['TEXT', 'TEXT1', 'TEXT2', 'TEXT3', 'TEXT4'])
def test_real_font_items(hb_font, text):
  items = get_items(text, Style(hb_font, SIZE, indent=2))
  assert items[-3:] == [Penalty.NO_BREAK, Glue.INF, Penalty.EJECT]
  boxes = [it for it in items if isinstance(it, Box)]
  assert ''.join(b.text for b in boxes[1:]) == text.replace(' ', '')
  for b in boxes:
    if b.text in CJK_PUNCTS:
      assert b.width == SIZE / 2, b
    elif len(b.text) == 1 and not is_latin_word(b.text):
      assert b.width == SIZE, b


if __name__ == '__main__':
  pytest.main([__file__])
