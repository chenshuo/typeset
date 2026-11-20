import math
import unicodedata

import pytest

from common import Box, Glue, Penalty, HYPHEN_PENALTY, INF_PENALTY
import font_util
import util
import render_paragraph
from render_paragraph import (
    is_latin_word, may_hyphenate, get_items, break_lines, get_hb_font, Params,
    SAMPLE_TEXT, STOP_PUNCTS, OPEN_PUNCTS, CLOSE_PUNCTS, CJK_PUNCTS)

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
  return Params(None, SIZE, get_box=fake_get_box, **kwargs)


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
  # East Asian Width 'A' (ambiguous) counts as Latin.
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
  assert may_hyphenate(None, 'hyphenation') is None
  assert may_hyphenate(dic, 'into') is None  # shorter than 5

  word = 'hyphenation'
  pos = may_hyphenate(dic, word)
  assert pos
  assert all(2 <= p <= len(word) - 3 for p in pos)
  assert pos == sorted(pos)
  # Case-insensitive
  assert may_hyphenate(dic, 'Hyphenation') == pos


# ---------------------------------------------------------- paragraph frame

def test_indent():
  items = get_items('中文', make_params(indent=2))
  assert isinstance(items[0], Box)
  assert items[0].width == 2 * SIZE
  assert items[0].text == '　　'

  items = get_items('中文', make_params(indent=0))
  assert items[0].text == '中'


def test_paragraph_end():
  for text in ['中文。', 'Hello world', 'Knuth和Plass']:
    items = get_items(text, make_params())
    assert items[-3:] == [Penalty.NO_BREAK, Glue.INF, Penalty.EJECT]
    assert isinstance(items[-4], Box)


def test_empty_text():
  # No items at all, not even the indent box or the paragraph end.
  for text in ['', ' ', '   ']:
    for indent in [0, 2]:
      assert get_items(text, make_params(indent=indent)) == []


def test_no_glue_after_glue_or_at_start():
  for text in [SAMPLE_TEXT, TEXT1, TEXT2, TEXT3, TEXT4]:
    items = items_of(text, indent=2)
    assert isinstance(items[0], Box)
    for a, b in zip(items, items[1:]):
      assert not (isinstance(a, Glue) and isinstance(b, Glue)), (a, b)


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


def test_latin_quotes_next_to_cjk():
  # “” in a Latin unit are not halt'ed (still 1em in the SC font), so they
  # get autospace, not punct glue.
  items = items_of_units('说 ', '“Hi” ', '然')
  assert tokens(items) == ['说', '~space', '“Hi”', '~space', '然']
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


# ------------------------------------------------------------ break_lines

@pytest.fixture
def passes(monkeypatch):
  """Records the keyword args of each line_break() call in break_lines()."""
  calls = []
  line_break = render_paragraph.line_break
  def recorder(items, line_width, **kwargs):
    calls.append(kwargs)
    return line_break(items, line_width, **kwargs)
  monkeypatch.setattr(render_paragraph, 'line_break', recorder)
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


def test_break_lines_empty_text(passes):
  assert break_lines('', 10 * SIZE, make_params(indent=2)) == ([], [])
  assert passes == []


# ------------------------------------------------- segmentation (injected)

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


def test_uniseg_contract():
  """Pin the UAX #14 segmentations get_items() relies on (uniseg 0.10)."""
  from uniseg.linebreak import line_break_units
  cases = {
      '中文': ['中', '文'],
      '你好，世界。': ['你', '好，', '世', '界。'],
      '说《论语》好': ['说', '《论', '语》', '好'],
      '说「好」吗': ['说', '「好」', '吗'],
      # LB19a: quotes between East Asian chars allow breaks.
      '曰：“学': ['曰：', '“学'],
      '乎？”好': ['乎？”', '好'],
      'Hello world': ['Hello ', 'world'],
      'well-known': ['well-', 'known'],
      'Knuth和1981年': ['Knuth', '和', '1981', '年'],
      # Mixed units, see the xfail tests below.
      '使用TeX。': ['使', '用', 'TeX。'],
      '用《TeX》排': ['用', '《TeX》', '排'],
  }
  for text, units in cases.items():
    assert list(line_break_units(text)) == units, text


# ----------------------------------------------------- known bugs (xfail)

@pytest.mark.xfail(strict=True, reason='UAX #14 unit "TeX。" is mixed; '
                   'Latin letters become separate halt boxes with CJK glue')
def test_latin_followed_by_cjk_punct():
  assert tokens(items_of_units('使', '用', 'TeX。')) == [
      '使', '~cjk', '用', '~space', 'TeX', 'nb', '。']


@pytest.mark.xfail(strict=True, reason='unit "《TeX》" is mixed')
def test_latin_inside_cjk_brackets():
  assert tokens(items_of_units('用', '《TeX》', '排')) == [
      '用', '~punct', '《', 'nb', 'TeX', 'nb', '》', '~punct', '排']


@pytest.mark.xfail(strict=True, reason='halt applies to every CJK char, but '
                   'only CJK_PUNCTS get punct glue: 〘〙〚〛 stay 1/2em')
def test_halt_outside_punct_sets():
  items = items_of_units('见', '〘注〙', '文')
  assert natural_width(items) == 5 * SIZE


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


@pytest.mark.parametrize('text', [SAMPLE_TEXT, TEXT1, TEXT2, TEXT3, TEXT4],
                         ids=['TEXT', 'TEXT1', 'TEXT2', 'TEXT3', 'TEXT4'])
def test_real_font_items(hb_font, text):
  items = get_items(text, Params(hb_font, SIZE))
  assert items[-3:] == [Penalty.NO_BREAK, Glue.INF, Penalty.EJECT]
  boxes = [it for it in items if isinstance(it, Box)]
  assert ''.join(b.text for b in boxes[1:]) == text.replace(' ', '')
  for b in boxes:
    if b.text in CJK_PUNCTS:
      assert b.width == SIZE / 2, b
    elif len(b.text) == 1 and not is_latin_word(b.text):
      assert b.width == SIZE, b
