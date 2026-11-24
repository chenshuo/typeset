"""Unit tests for simple.py: what it adds to basic.py, namely discarding glue
after a break, varying line widths, looseness and "<=" for ties, and what it
keeps, the final pass.
"""

import math
import random

import pytest

import basic
import common
import simple
from simple import line_break
from common import (Box, Glue, Penalty, INF_BAD, INF_PENALTY, EJECT_PENALTY,
                    ratio, badness, demerits)
from sample import get_sample_paragraph
from render_simple import get_items, SAMPLE_TEXT
from render_simple_test import make_params, lines_of, SIZE, TEXT1, TEXT2, TEXT3


@pytest.fixture(autouse=True)
def default_scoring(monkeypatch):
  """TeX82 scoring, (l + b)^2 +- p^2 with l = 10, unless a test changes it."""
  monkeypatch.setattr(common, 'LINE_PENALTY', 10)
  monkeypatch.setattr(common, 'KP81_PENALTY', False)


def kp81_scoring(monkeypatch):
  """Scoring of the 1981 paper, (1 + b + p)^2."""
  monkeypatch.setattr(common, 'LINE_PENALTY', 1)
  monkeypatch.setattr(common, 'KP81_PENALTY', True)


def paragraph(*items):
  """Ends the paragraph like KP81 does: no break before the finishing glue."""
  return list(items) + [Penalty.NO_BREAK, Glue(0, math.inf, 0), Penalty.EJECT]


def sample_paragraph(strip_last_glue=False):
  """The sample paragraph of KP81."""
  items = get_sample_paragraph(hyphenate=True)
  if strip_last_glue:
    assert isinstance(items[-1], Glue)
    items.pop()
  return items + [Glue(0, math.inf, 0), Penalty.EJECT]


def five_words():
  """Five words of width 10 separated by glue (2, 2, 1); two words are 22 wide."""
  g = Glue(2, 2, 1)
  return paragraph(Box(10, 'a'), g, Box(10, 'b'), g, Box(10, 'c'), g,
                   Box(10, 'd'), g, Box(10, 'e'))


def chars(n):
  """n boxes of width 10 with rigid glue of width 0 in between: lines must
  fit exactly."""
  items = []
  for k in range(n):
    items += [Box(10, str(k + 1)), Glue(0, 0, 0)]
  return paragraph(*items[:-1])


def twelve_chars(no_break_after=None):
  """Twelve boxes of width 10 separated by glue (0, 5, 0), like CJK text.
  At line width 40, a line holds four boxes (r = 0) or three boxes (r = 1).
  """
  items = []
  for k in range(1, 13):
    items.append(Box(10, str(k)))
    if k == no_break_after:
      items.append(Penalty.NO_BREAK)
    if k < 12:
      items.append(Glue(0, 5, 0))
  return paragraph(*items)


def line_ends(items, breaks):
  """Last word of each line, with the hyphen if the line ends at one."""
  ends = []
  for b in breaks:
    end = items[b.end]
    hyphen = end.text if isinstance(end, Penalty) else ''
    ends.append(items[b.end - 1].text + hyphen)
  return ends


def boxes_per_line(items, breaks):
  return [sum(isinstance(x, Box) for x in items[b.start:b.end]) for b in breaks]


def total(breaks):
  return sum(b.demerits for b in breaks)


def width_of(line_widths, line):
  if not isinstance(line_widths, (list, tuple)):
    return line_widths
  return line_widths[min(line, len(line_widths)) - 1]


def check_lines(items, breaks, line_widths):
  """The result covers the paragraph, every line starts at a box, and the
  reported ratio is the one of items[start:end] in the width of that line."""
  assert [b.line for b in breaks] == list(range(1, len(breaks) + 1))
  assert breaks[0].start == 0
  assert breaks[-1].end == len(items) - 1
  for prev, cur in zip(breaks, breaks[1:]):
    assert cur.start > prev.end
    # Only glue and penalties are dropped between two lines.
    assert not any(isinstance(x, Box) for x in items[prev.end:cur.start])
  for b in breaks:
    assert isinstance(items[b.start], Box)
    line = items[b.start:b.end]
    glue = [x for x in line if isinstance(x, Glue)]
    width = sum(x.width for x in line if not isinstance(x, Penalty))
    if isinstance(items[b.end], Penalty):
      width += items[b.end].width
    r = ratio(width_of(line_widths, b.line), width,
              sum(x.stretch for x in glue), sum(x.shrink for x in glue))
    assert b.ratio == pytest.approx(r)


def reference(items, line_widths, max_stretch_ratio):
  """Exhaustive search without an active list: keeps the best way to end
  line j at every legal breakpoint, for every j.

  Returns {number of lines: minimum total demerits}, empty if the paragraph
  cannot be set.  The only forced break must be the final one.
  """
  if not isinstance(line_widths, (list, tuple)):
    line_widths = [line_widths]
  n = len(items)
  width, stretch, shrink = [0], [0], [0]
  for item in items:
    is_penalty = isinstance(item, Penalty)
    width.append(width[-1] + (0 if is_penalty else item.width))
    stretch.append(stretch[-1] + getattr(item, 'stretch', 0))
    shrink.append(shrink[-1] + getattr(item, 'shrink', 0))

  def line_start(a):
    """Index of the first box after a break at a; the glue and penalties in
    between are discarded."""
    k = a + 1
    while k < n - 1 and not isinstance(items[k], Box):
      k += 1
    return k

  nodes = {-1: {0: 0}}  # position -> {line: total demerits}
  for b, item in enumerate(items):
    penalty, hyphen_width = 0, 0
    if isinstance(item, Glue):
      if b == 0 or not isinstance(items[b - 1], Box):
        continue
    elif isinstance(item, Penalty):
      if item.value >= INF_PENALTY:
        continue
      penalty, hyphen_width = item.value, item.width
    else:
      continue

    here = {}
    for a, ends in nodes.items():
      s = line_start(a)
      for line, total_demerits in ends.items():
        line_width = line_widths[min(line, len(line_widths) - 1)]
        r = ratio(line_width,
                  width[b] - width[s] + hyphen_width,
                  stretch[b] - stretch[s],
                  shrink[b] - shrink[s])
        if not -1 <= r <= max_stretch_ratio:
          continue
        d = demerits(badness(r), penalty)
        here[line + 1] = min(here.get(line + 1, math.inf), total_demerits + d)
    if here:
      nodes[b] = here
  return nodes.get(n - 1, {})


# ---------------------------------------------------------------------------
# What basic.py does, too
# ---------------------------------------------------------------------------

def test_paragraph_must_end_with_inf_glue_and_eject():
  with pytest.raises(AssertionError):
    line_break([Box(10), Glue(2, 2, 1), Box(10)], 22)
  with pytest.raises(AssertionError):
    line_break([Box(10), Penalty.EJECT], 22)


def test_result_fields():
  items = five_words()
  breaks = line_break(items, 22)
  assert [(b.line, b.start, b.end) for b in breaks] == [(1, 0, 3), (2, 4, 7), (3, 8, 11)]
  assert [b.ratio for b in breaks] == [0, 0, 0]
  assert [b.demerits for b in breaks] == [100, 100, 100]
  check_lines(items, breaks, 22)


@pytest.mark.parametrize('line_width, r, d', [
    (24, 1.0, (10 + 100) ** 2),   # fully stretched
    (23, 0.5, (10 + 13) ** 2),
    (21, -1.0, (10 + 100) ** 2),  # fully shrunk
])
def test_stretch_and_shrink(line_width, r, d):
  breaks = line_break(five_words(), line_width)
  assert [b.ratio for b in breaks] == [r, r, 0]
  assert [b.demerits for b in breaks] == [d, d, 100]


def test_tolerance():
  # Two words need r = 2 to fill 26 units, three words do not fit.
  with pytest.raises(RuntimeError):
    line_break(five_words(), 26, max_stretch_ratio=1)
  breaks = line_break(five_words(), 26, max_stretch_ratio=2)
  assert [b.ratio for b in breaks] == [2, 2, 0]


def test_hyphen_width_counts_only_when_broken():
  hyphen = Penalty(50, 4, '-', is_hyphen=True)
  items = paragraph(Box(10, 'a'), hyphen, Box(10, 'b'), hyphen, Box(10, 'c'))
  breaks = line_break(items, 14)
  assert line_ends(items, breaks)[:2] == ['a-', 'b-']
  # No extra demerits for consecutive hyphens.
  assert [b.demerits for b in breaks] == [2600, 2600, 100]
  assert len(line_break(items, 30)) == 1


def test_kp81_sample(monkeypatch):
  kp81_scoring(monkeypatch)
  items = sample_paragraph()
  breaks = line_break(items, 500)
  assert line_ends(items, breaks)[:-1] == [
      'a', 'was', 'was', "king's", 'the', "king's", 'the', 'ball,', 'her']
  assert total(breaks) == 3606
  check_lines(items, breaks, 500)

  breaks = line_break(items, 390)
  assert line_ends(items, breaks)[:-1] == [
      'one,', 'beau-', 'the', 'aston-', 'the', 'an', 'when', 'out', 'the', 'a', 'caught']
  assert total(breaks) == 31040


@pytest.mark.parametrize('max_stretch_ratio', [1, 2, 10])
def test_same_total_as_basic(monkeypatch, max_stretch_ratio):
  kp81_scoring(monkeypatch)
  # Without the glue after the last word.  Otherwise basic.py may break
  # there and set the finishing glue on a line of its own, which simple.py
  # cannot do as it discards glue after a break.
  items = sample_paragraph(strip_last_glue=True)
  feasible = 0
  for line_width in range(300, 701, 10):
    try:
      expected = basic.line_break(items, line_width, max_stretch_ratio)
    except RuntimeError:
      with pytest.raises(RuntimeError):
        line_break(items, line_width, max_stretch_ratio)
      continue
    feasible += 1
    breaks = line_break(items, line_width, max_stretch_ratio)
    assert total(breaks) == total(expected)
    assert len(breaks) == len(expected)
  assert feasible >= 20


# ---------------------------------------------------------------------------
# Discardable items after a break
# ---------------------------------------------------------------------------

def test_glue_after_break_is_discarded():
  # The glue of width 5 after the first break is dropped, so the second line
  # is 25 wide.  The basic version counts it, see basic_test.py.
  items = paragraph(Box(10), Glue(5, 0, 0), Box(10),
                    Glue(0, 0, 0), Glue(5, 0, 0), Box(25),
                    Glue(0, 0, 0), Box(10))
  breaks = line_break(items, 25)
  assert [b.ratio for b in breaks] == [0, 0, 0]
  # Lines start at their first box.
  assert [(b.line, b.start, b.end) for b in breaks] == [(1, 0, 3), (2, 5, 6), (3, 7, 10)]

  with pytest.raises(RuntimeError):
    basic.line_break(items, 25)


def test_penalty_after_break_is_discarded():
  items = paragraph(Box(10), Glue(5, 0, 0), Box(10),
                    Glue(0, 0, 0), Penalty(0), Glue(5, 0, 0), Penalty.NO_BREAK, Box(25),
                    Glue(0, 0, 0), Box(10))
  breaks = line_break(items, 25)
  assert [b.ratio for b in breaks] == [0, 0, 0]
  assert [b.start for b in breaks] == [0, 7, 9]


def test_glue_after_penalty_break_is_discarded():
  # A break at the penalty; the stretchable glue behind it would make the
  # second line 30 wide.
  items = paragraph(Box(10), Glue(5, 0, 0), Box(10),
                    Penalty(0), Glue(5, 3, 3), Box(25),
                    Glue(0, 0, 0), Box(10))
  breaks = line_break(items, 25)
  assert [(b.start, b.end) for b in breaks] == [(0, 3), (5, 6), (7, 10)]
  assert [b.ratio for b in breaks] == [0, 0, 0]


# ---------------------------------------------------------------------------
# Varying line widths
# ---------------------------------------------------------------------------

def test_line_widths():
  items = chars(12)
  assert boxes_per_line(items, line_break(items, [20, 40, 30])) == [2, 4, 3, 3]
  assert boxes_per_line(items, line_break(items, [30, 10, 20])) == [3, 1, 2, 2, 2, 2]
  assert boxes_per_line(items, line_break(items, (30, 10, 20))) == [3, 1, 2, 2, 2, 2]


def test_last_line_width_repeats():
  items = chars(12)
  assert boxes_per_line(items, line_break(items, [40, 20])) == [4, 2, 2, 2, 2]
  assert boxes_per_line(items, line_break(items, [30])) == [3, 3, 3, 3]
  assert boxes_per_line(items, line_break(items, 30)) == [3, 3, 3, 3]


def test_line_numbers():
  items = chars(12)
  breaks = line_break(items, [20, 40, 30])
  assert [b.line for b in breaks] == [1, 2, 3, 4]
  check_lines(items, breaks, [20, 40, 30])


def test_same_position_on_different_lines():
  # 'd' can end line 1 (a b c d, perfect) or line 2 (a b / c d, 12629
  # demerits).  What follows is 'e', 50 wide and rigid, then 'h'.
  items = paragraph(Box(25, 'a'), Glue(0, 50, 0), Box(25, 'b'), Glue(0, 0, 0),
                    Box(25, 'c'), Glue(0, 100, 0), Box(25, 'd'), Glue(0, 0, 0),
                    Box(50, 'e'), Glue(0, 0, 0), Box(60, 'h'))

  # If the second line is 50 wide, 'e' fits right after the perfect line.
  breaks = line_break(items, [100, 50, 100])
  assert line_ends(items, breaks)[:-1] == ['d', 'e']
  assert [b.demerits for b in breaks] == [100, 100, 100]

  # If only the third line is 50 wide, 'd' has to end line 2.  That
  # breakpoint must be kept although it is far from the best one at 'd'.
  breaks = line_break(items, [100, 100, 50, 100])
  assert line_ends(items, breaks)[:-1] == ['b', 'd', 'e']
  assert [b.line for b in breaks] == [1, 2, 3, 4]
  assert [b.ratio for b in breaks] == [1, 0.5, 0, 0]
  assert [b.demerits for b in breaks] == [12100, 529, 100, 100]


def test_kp81_sample_with_narrow_first_lines(monkeypatch):
  # Three lines of 390 units, then 500 units, as if there were a figure at
  # the top right corner of the paragraph.
  kp81_scoring(monkeypatch)
  items = sample_paragraph()
  line_widths = [390, 390, 390, 500]
  breaks = line_break(items, line_widths)
  assert line_ends(items, breaks)[:-1] == [
      'one,', 'beau-', 'the', 'it', 'dark', 'and', 'the', 'when', 'high']
  assert [round(b.ratio, 3) for b in breaks] == [
      0.857, 0.000, 0.280, 0.156, 0.513, 0.158, -0.333, 0.081, 0.275, 0.000]
  assert total(breaks) == min(reference(items, line_widths, 1).values())
  check_lines(items, breaks, line_widths)


# ---------------------------------------------------------------------------
# Looseness
# ---------------------------------------------------------------------------

def test_looseness_sample(monkeypatch):
  kp81_scoring(monkeypatch)
  items = sample_paragraph()
  totals = reference(items, 500, 10)

  optimum = line_break(items, 500, 10)
  assert len(optimum) == 10
  assert total(optimum) == totals[10] == 3606

  tighter = line_break(items, 500, 10, looseness=-1)
  assert len(tighter) == 9
  assert total(tighter) == totals[9]

  looser = line_break(items, 500, 10, looseness=1)
  assert len(looser) == 11
  assert total(looser) == totals[11]

  # The result with looseness is worse than the optimum, but the best
  # possible with that many lines.
  assert totals[9] > totals[10] < totals[11]


def test_looseness_goes_as_far_as_possible(monkeypatch):
  kp81_scoring(monkeypatch)
  items = sample_paragraph()
  # Eight lines are impossible at 500 units.
  assert 8 not in reference(items, 500, 10)
  assert len(line_break(items, 500, 10, looseness=-2)) == 9
  assert len(line_break(items, 500, 10, looseness=-100)) == 9
  # A tolerance of 1 does not allow an extra line.
  assert 11 not in reference(items, 500, 1)
  assert line_break(items, 500, 1, looseness=1) == line_break(items, 500, 1)


def test_looseness_zero_is_the_default():
  items = sample_paragraph()
  assert line_break(items, 500, looseness=0) == line_break(items, 500)


def test_looseness_small_paragraph():
  items = twelve_chars()
  assert boxes_per_line(items, line_break(items, 40)) == [4, 4, 4]
  # One loose line makes room for a fourth line; "<=" puts it as late as
  # possible.
  breaks = line_break(items, 40, looseness=1)
  assert boxes_per_line(items, breaks) == [4, 4, 3, 1]
  assert [b.demerits for b in breaks] == [100, 100, 12100, 100]
  # Five lines are impossible: four lines of three boxes leave nothing.
  assert line_break(items, 40, looseness=2) == breaks
  # Fewer than three lines is impossible.
  assert len(line_break(items, 40, looseness=-1)) == 3


def test_looseness_does_not_add_an_empty_line():
  # Rigid boxes: 3 + 3 is the only way to set six of them in 30 units.
  # Here the finishing glue is a legal breakpoint.
  items = chars(6)
  del items[-3]  # Penalty.NO_BREAK
  breaks = line_break(items, 30)
  assert boxes_per_line(items, breaks) == [3, 3]
  # An empty third line after a break at the finishing glue is infeasible.
  assert line_break(items, 30, looseness=1) == breaks
  assert line_break(items, 30, looseness=-1) == breaks


def test_looseness_with_line_widths():
  # Lines of 40, 40, then 30 units.  A line of 30 units holds three boxes
  # (r = 0), or two if r = 2 is allowed.
  items = twelve_chars()
  line_widths = [40, 40, 30]
  breaks = line_break(items, line_widths, 2)
  assert boxes_per_line(items, breaks) == [4, 4, 3, 1]
  totals = reference(items, line_widths, 2)
  assert sorted(totals) == [4, 5]
  assert total(breaks) == totals[4] == 400
  # Five lines need two loose lines of 40 units and a very loose one of 30.
  looser = line_break(items, line_widths, 2, looseness=1)
  assert sorted(boxes_per_line(items, looser)) == [1, 2, 3, 3, 3]
  assert total(looser) == totals[5]
  check_lines(items, looser, line_widths)
  # Three lines are impossible, and so are five with a tolerance of 1.
  assert line_break(items, line_widths, 2, looseness=-1) == breaks
  assert line_break(items, line_widths, 1, looseness=1) == breaks


# ---------------------------------------------------------------------------
# Ties, forced breaks, errors
# ---------------------------------------------------------------------------

def test_ties_keep_the_later_predecessor():
  # No break after the 8th box.  At 40 units, 3+4+4+1 and 4+3+4+1 have the
  # same total demerits.  The basic version uses "<" and puts the loose line
  # first; "<=" puts it later, like TeX.
  items = twelve_chars(no_break_after=8)
  breaks = line_break(items, 40)
  assert boxes_per_line(items, breaks) == [4, 3, 4, 1]
  assert [b.ratio for b in breaks] == [0, 1, 0, 0]
  expected = basic.line_break(items, 40)
  assert boxes_per_line(items, expected) == [3, 4, 4, 1]
  assert total(breaks) == total(expected)


def test_forced_break_accepts_infeasible_line():
  # No infinite glue before the forced break: the first line is underfull
  # (r = 78 / 2), but a forced break has to be taken anyway.
  g = Glue(2, 2, 1)
  items = paragraph(Box(10), g, Box(10), Penalty.EJECT, Box(10))
  breaks = line_break(items, 100)
  assert [(b.start, b.end) for b in breaks] == [(0, 3), (4, 7)]
  assert breaks[0].ratio == 39
  assert [b.demerits for b in breaks] == [(10 + INF_BAD) ** 2, 100]


def test_infeasible_line_only_without_feasible_one():
  # At the final forced break, the overfull line 'b c' (r = -2) is not a
  # candidate because 'c' alone is feasible.
  g = Glue(2, 2, 1)
  items = paragraph(Box(10, 'a'), g, Box(10, 'b'), g, Box(10, 'c'))
  for looseness in (0, -1):
    breaks = line_break(items, 21, looseness=looseness)
    assert boxes_per_line(items, breaks) == [2, 1]
    assert [b.demerits for b in breaks] == [(10 + 100) ** 2, 100]


def test_forced_break_after_infinite_glue():
  # The running sums restart after a forced break; otherwise the infinite
  # glue before it would spoil the ratios of all later lines.
  first = [Box(10), Glue(0, math.inf, 0), Penalty.EJECT, Glue(7, 0, 0)]
  rest = five_words()
  for line_width, r in ((24, 1.0), (23, 0.5), (22, 0), (21, -1.0)):
    expected = line_break(rest, line_width)
    breaks = line_break(first + rest, line_width)
    assert [b.ratio for b in breaks] == [0, r, r, 0]
    assert [b.demerits for b in breaks[1:]] == [b.demerits for b in expected]
    # The glue after the forced break is discarded.
    assert [(b.start, b.end) for b in breaks[1:]] == [
        (b.start + 4, b.end + 4) for b in expected]


def test_line_widths_across_forced_break():
  # Line numbers go on after a forced break: the third line is 30 wide.
  first = [Box(10), Glue(0, 0, 0), Box(10), Glue(0, 0, 0), Box(10),
           Glue(0, math.inf, 0), Penalty.EJECT]
  items = first + chars(5)
  breaks = line_break(items, [20, 20, 30])
  assert boxes_per_line(items, breaks) == [2, 1, 3, 2]
  assert [b.ratio for b in breaks] == [0, 0, 0, 0]


def test_no_feasible_breakpoints():
  g = Glue(2, 2, 1)
  items = paragraph(Box(10), g, Box(50), g, Box(10))
  with pytest.raises(RuntimeError):
    line_break(items, 20)


# ---------------------------------------------------------------------------
# Final pass: overfull lines
# ---------------------------------------------------------------------------

def overfull_paragraph():
  g = Glue(2, 2, 1)
  return paragraph(Box(10, 'a'), g, Box(8, 'b'), g, Box(50, 'toolong'), g, Box(10, 'c'))


def test_overfull_raises_without_final_pass():
  with pytest.raises(RuntimeError):
    line_break(overfull_paragraph(), 20)


def test_final_pass_sets_overfull_line():
  items = overfull_paragraph()
  breaks = line_break(items, 20, final_pass=True)
  assert line_ends(items, breaks)[:2] == ['b', 'toolong']
  # The overfull line is on its own, with zero ("artificial") demerits.
  assert [(b.start, b.end) for b in breaks] == [(0, 3), (4, 5), (6, 9)]
  assert [b.ratio for b in breaks] == [0, -math.inf, 0]
  assert [b.demerits for b in breaks] == [100, 0, 100]


def test_final_pass_does_not_change_feasible_paragraph():
  items = sample_paragraph()
  assert line_break(items, 500, final_pass=True) == line_break(items, 500)
  line_widths = [390, 390, 390, 500]
  assert (line_break(items, line_widths, looseness=1, final_pass=True)
          == line_break(items, line_widths, looseness=1))


def test_final_pass_with_line_widths():
  items = overfull_paragraph()
  # A second line of 50 units is just right for the long word.
  breaks = line_break(items, [20, 50, 20])
  assert line_ends(items, breaks)[:2] == ['b', 'toolong']
  assert [b.ratio for b in breaks] == [0, 0, 0]

  # A first line of 50 units is too wide for 'a b' (r = 15) and too narrow
  # for 'a b toolong', 72 units with 2 units of shrink.
  with pytest.raises(RuntimeError):
    line_break(items, [50, 20])
  breaks = line_break(items, [50, 20], final_pass=True)
  assert line_ends(items, breaks)[:1] == ['toolong']
  assert boxes_per_line(items, breaks) == [3, 1]
  assert [b.ratio for b in breaks] == [-11, 0]
  assert [b.demerits for b in breaks] == [0, 100]


def test_final_pass_with_looseness():
  items = overfull_paragraph()
  expected = line_break(items, 20, final_pass=True)
  for looseness in (-1, 1):
    assert line_break(items, 20, looseness=looseness, final_pass=True) == expected


# ---------------------------------------------------------------------------
# Optimality: compare with exhaustive search
# ---------------------------------------------------------------------------

def check_against_reference(items, line_widths, max_stretch_ratio, looseness=0):
  """Returns False if the paragraph cannot be set."""
  totals = reference(items, line_widths, max_stretch_ratio)
  if not totals:
    try:
      breaks = line_break(items, line_widths, max_stretch_ratio, looseness)
    except RuntimeError:
      return False
    # The only way out is an infeasible last line at the forced break.
    assert not -1 <= breaks[-1].ratio <= max_stretch_ratio
    return False

  best = min(totals.values())
  optimum = [k for k, t in totals.items() if t == best]
  if looseness != 0 and len(optimum) > 1:
    return True  # the optimum number of lines is ambiguous
  k = optimum[0]
  if looseness > 0:
    k = max(j for j in totals if k <= j <= k + looseness)
  elif looseness < 0:
    k = min(j for j in totals if k + looseness <= j <= k)

  breaks = line_break(items, line_widths, max_stretch_ratio, looseness)
  assert total(breaks) == totals[k]
  if looseness != 0:
    assert len(breaks) == k
  check_lines(items, breaks, line_widths)
  assert all(-1 <= b.ratio <= max_stretch_ratio for b in breaks)
  # The final pass is not needed, and changes nothing.
  assert line_break(items, line_widths, max_stretch_ratio, looseness,
                    final_pass=True) == breaks
  return True


@pytest.mark.parametrize('kp81', [False, True])
@pytest.mark.parametrize('max_stretch_ratio', [1, 2, 10])
def test_sample_is_optimal(monkeypatch, kp81, max_stretch_ratio):
  if kp81:
    kp81_scoring(monkeypatch)
  items = sample_paragraph()
  feasible = 0
  for line_width in range(300, 701, 20):
    feasible += check_against_reference(items, line_width, max_stretch_ratio)
  assert feasible >= 10


@pytest.mark.parametrize('line_widths', [
    [390, 390, 390, 500],
    [500, 500, 500, 390],
    [300, 400, 500, 600, 500, 400],
    [600, 350],
    [450, 350, 450, 350, 450, 350, 450, 350, 450],
])
@pytest.mark.parametrize('max_stretch_ratio', [1, 3, 10])
def test_sample_with_varying_widths_is_optimal(monkeypatch, line_widths, max_stretch_ratio):
  kp81_scoring(monkeypatch)
  check_against_reference(sample_paragraph(), line_widths, max_stretch_ratio)


@pytest.mark.parametrize('looseness', [-2, -1, 1, 2, 3])
def test_sample_with_looseness_is_optimal(monkeypatch, looseness):
  kp81_scoring(monkeypatch)
  items = sample_paragraph()
  for line_width in (350, 390, 450, 500, 600):
    for max_stretch_ratio in (2, 10):
      check_against_reference(items, line_width, max_stretch_ratio, looseness)
  check_against_reference(items, [390, 390, 390, 500], 10, looseness)


def random_paragraph(rng):
  items = []
  for _ in range(rng.randint(5, 50)):
    items.append(Box(rng.randint(5, 40)))
    kind = rng.random()
    if kind < 0.15:
      items.append(Penalty(50, 5, '-', is_hyphen=True))  # hyphen inside a word
      continue
    if kind < 0.30:
      items.append(Penalty(rng.choice([-200, -50, 30, 200])))
    elif kind < 0.40:
      items.append(Penalty.NO_BREAK)
    items.append(Glue(6, rng.choice([2, 3, 4]), rng.choice([1, 2, 4])))
    if kind > 0.90:
      items.append(Glue(3, 1, 1))  # discarded after a break
  items.append(Box(rng.randint(5, 40)))
  return paragraph(*items)


def check_random_paragraphs(seed, loosenesses):
  rng = random.Random(seed)
  feasible = 0
  for _ in range(300):
    items = random_paragraph(rng)
    line_widths = [rng.randint(60, 250) for _ in range(rng.choice([1, 1, 2, 3, 5]))]
    max_stretch_ratio = rng.choice([1, 2, 5])
    looseness = rng.choice(loosenesses)
    feasible += check_against_reference(items, line_widths, max_stretch_ratio, looseness)
  assert feasible > 100


def test_random_paragraphs_are_optimal():
  check_random_paragraphs(1981, [0])


def test_random_paragraphs_with_looseness_are_optimal():
  check_random_paragraphs(1982, [-2, -1, 1, 2])


def test_random_paragraphs_final_pass_never_fails():
  rng = random.Random(1983)
  overfull = 0
  for _ in range(300):
    items = random_paragraph(rng)
    line_widths = [rng.randint(20, 120) for _ in range(rng.choice([1, 2, 3]))]
    looseness = rng.choice([-1, 0, 0, 1])
    breaks = line_break(items, line_widths, 2, looseness, final_pass=True)
    check_lines(items, breaks, line_widths)
    overfull += any(b.ratio < -1 for b in breaks)
  assert overfull > 50


# ---------------------------------------------------------------------------
# Chinese text, with the items of render_simple.py
# ---------------------------------------------------------------------------

def em(x):
  return x * SIZE


def chinese_items(text, **kwargs):
  """Font-free items: Chinese characters are 1em wide, punctuation 1/2em
  followed or preceded by glue of 1/2em."""
  return get_items(text, make_params(**kwargs))


@pytest.mark.parametrize('text', [SAMPLE_TEXT, TEXT1, TEXT2, TEXT3])
@pytest.mark.parametrize('params', [{}, {'indent': 2}, {'runt_penalty': 200}])
def test_chinese_is_optimal(text, params):
  items = chinese_items(text, **params)
  feasible = 0
  for width in range(8, 26):
    feasible += check_against_reference(items, em(width), 1)
    check_against_reference(items, [em(width - 4)] * 2 + [em(width)], 2)
    for looseness in (-1, 1):
      check_against_reference(items, em(width), 2, looseness)
  assert feasible >= 10


@pytest.mark.parametrize('text', [SAMPLE_TEXT, TEXT1, TEXT2, TEXT3])
def test_chinese_same_total_as_basic(text):
  # These items have a single glue between two boxes, so nothing else is
  # discarded after a break at glue, and both versions find the same optimum.
  items = chinese_items(text, indent=2)
  for width in range(8, 26):
    try:
      expected = basic.line_break(items, em(width))
    except RuntimeError:
      with pytest.raises(RuntimeError):
        line_break(items, em(width))
      continue
    breaks = line_break(items, em(width))
    assert total(breaks) == total(expected)
    assert len(breaks) == len(expected)


def test_chinese_punct_glue_after_runt_penalty_is_discarded():
  # The only break is at the runt penalty after '，'.  The glue of 1/2em
  # that follows it must not start the last line.
  items = chinese_items('天地玄，黄', runt_penalty=50)
  runt = items.index(Penalty(50))
  assert items[runt + 1] == Glue(em(0.5), em(1/3), em(1/4), '')
  breaks = line_break(items, em(3.5))
  assert lines_of(items, breaks) == ['天地玄，', '黄']
  assert [b.end for b in breaks] == [runt, len(items) - 1]
  assert isinstance(items[breaks[1].start], Box)
  assert [b.ratio for b in breaks] == [0, 0]
  # basic.py keeps that glue at the start of the last line.
  expected = basic.line_break(items, em(3.5))
  assert expected[1].start == runt + 1 == breaks[1].start - 1


def test_chinese_looseness_removes_short_last_line():
  items = chinese_items(TEXT1)
  breaks = line_break(items, em(14))
  assert lines_of(items, breaks)[-1] == '驰。'
  assert boxes_per_line(items, breaks) == [14, 14, 13, 14, 13, 2]

  # Punctuation can shrink: the last two lines fit into one.
  tighter = line_break(items, em(14), looseness=-1)
  assert boxes_per_line(items, tighter) == [14, 14, 13, 14, 15]
  assert lines_of(items, tighter)[:4] == lines_of(items, breaks)[:4]
  assert all(-1 <= b.ratio <= 1 for b in tighter)
  assert total(tighter) > total(breaks)
  check_lines(items, tighter, em(14))


def test_chinese_line_widths():
  # Two lines of 10em next to a figure, then 14em.
  items = chinese_items(TEXT1, indent=2)
  line_widths = [em(10), em(10), em(14)]
  breaks = line_break(items, line_widths)
  check_lines(items, breaks, line_widths)
  lines = lines_of(items, breaks)
  assert lines[0] == '　　臣本布衣，躬耕于'
  for b, line in zip(breaks, lines):
    line_width = line_widths[min(b.line, 3) - 1]
    natural = sum(x.width for x in items[b.start:b.end] if not isinstance(x, Penalty))
    if b is not breaks[-1]:
      assert abs(natural - line_width) <= em(1)
    # No line starts with closing punctuation or ends with an opening one.
    assert line[0] not in '，。、；：？！”》' and line[-1] not in '“《'


if __name__ == '__main__':
  pytest.main([__file__])
