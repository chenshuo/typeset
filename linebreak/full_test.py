"""Unit tests for full.py: the features added on top of basic.py, namely
flagged penalties (alpha), fitness classes (gamma), discarding glue after a
break, varying line widths and looseness.
"""

import math
import random

import pytest

import full
import basic
import common
from full import line_break, fitness_class
from common import (Box, Glue, Penalty, INF_BAD, INF_PENALTY, EJECT_PENALTY,
                    ratio, badness, demerits)
from sample import get_sample_paragraph

ALPHA = 3000
GAMMA = 3000


@pytest.fixture(autouse=True)
def default_scoring(monkeypatch):
  """TeX82 scoring, (l + b)^2 +- p^2 with l = 10, unless a test changes it."""
  monkeypatch.setattr(common, 'LINE_PENALTY', 10)
  monkeypatch.setattr(common, 'KP81_PENALTY', False)
  monkeypatch.setattr(full, 'DOUBLE_HYPHEN_DEMERITS', ALPHA)
  monkeypatch.setattr(full, 'ADJ_DEMERITS', GAMMA)


def kp81_scoring(monkeypatch):
  """Scoring of the 1981 paper, (1 + b + p)^2."""
  monkeypatch.setattr(common, 'LINE_PENALTY', 1)
  monkeypatch.setattr(common, 'KP81_PENALTY', True)


def paragraph(*items):
  """Ends the paragraph like KP81 does: no break before the finishing glue."""
  return list(items) + [Penalty.NO_BREAK, Glue(0, math.inf, 0), Penalty.EJECT]


def sample_paragraph(strip_last_glue=False):
  """The sample paragraph of KP81, built like main() of full.py."""
  items = get_sample_paragraph(hyphenate=True)
  assert all(x.is_hyphen for x in items if isinstance(x, Penalty))
  if strip_last_glue:
    assert isinstance(items[-1], Glue)
    items.pop()
  return items + [Glue(0, math.inf, 0), Penalty.EJECT]


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


def fitness_classes(breaks):
  return [fitness_class(b.ratio) for b in breaks]


def reference(items, line_widths, max_stretch_ratio):
  """Exhaustive search without an active list: keeps the best way to end
  line j with fitness class c at every legal breakpoint, for every (j, c).

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

  def flagged(i):
    return i >= 0 and isinstance(items[i], Penalty) and items[i].is_hyphen

  nodes = {-1: {(0, 1): 0}}  # position -> {(line, fitness): total demerits}
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
      for (line, fitness), total in ends.items():
        line_width = line_widths[min(line, len(line_widths) - 1)]
        r = ratio(line_width,
                  width[b] - width[s] + hyphen_width,
                  stretch[b] - stretch[s],
                  shrink[b] - shrink[s])
        if not -1 <= r <= max_stretch_ratio:
          continue
        d = demerits(badness(r), penalty)
        if flagged(a) and flagged(b):
          d += full.DOUBLE_HYPHEN_DEMERITS
        c = fitness_class(r)
        if abs(c - fitness) > 1:
          d += full.ADJ_DEMERITS
        key = (line + 1, c)
        here[key] = min(here.get(key, math.inf), total + d)
    if here:
      nodes[b] = here

  result = {}
  for (line, _), total in nodes.get(n - 1, {}).items():
    result[line] = min(result.get(line, math.inf), total)
  return result


def reference_total_demerits(items, line_widths, max_stretch_ratio):
  result = reference(items, line_widths, max_stretch_ratio)
  return min(result.values()) if result else None


# ---------------------------------------------------------------------------
# Fitness classes and adjacent line demerits (gamma)
# ---------------------------------------------------------------------------

def test_fitness_class():
  assert fitness_class(-1) == 0      # tight
  assert fitness_class(-0.51) == 0
  assert fitness_class(-0.5) == 1    # normal
  assert fitness_class(0) == 1
  assert fitness_class(0.5) == 1
  assert fitness_class(0.51) == 2    # loose
  assert fitness_class(1) == 2
  assert fitness_class(1.01) == 3    # very loose
  assert fitness_class(math.inf) == 3


def two_lines(first, second):
  """Two lines of two boxes each, set at the given ratios in 40 units, and a
  short last line.  Every other way of breaking is infeasible."""
  def line(r):
    if r < 0:
      return [Box(20), Glue(-r, 0, 1), Box(20)]
    return [Box(20 - r / 2), Glue(0, 1, 0), Box(20 - r / 2)]
  return paragraph(*line(first), Glue(0, 0, 0), *line(second), Glue(0, 0, 0), Box(5))


@pytest.mark.parametrize('first, second, extra', [
    (-1, 1, GAMMA),      # tight, loose
    (1, -1, GAMMA),      # loose, tight
    (-1, 2, GAMMA),      # tight, very loose
    (0, 2, GAMMA),       # normal, very loose
    (-1, -1, 0),         # tight, tight
    (-1, 0.5, 0),        # tight, normal
    (0.5, 1, 0),         # normal, loose
    (1, 2, 0),           # loose, very loose
])
def test_adjacent_fitness_classes(first, second, extra):
  breaks = line_break(two_lines(first, second), 40, max_stretch_ratio=2)
  assert [b.ratio for b in breaks] == [first, second, 0]
  d1 = (10 + badness(first)) ** 2
  d2 = (10 + badness(second)) ** 2
  # The demerits are charged to the second line of the pair.  The last line
  # has r = 0, which does not go with a very loose line either.
  d3 = 100 + (GAMMA if second > 1 else 0)
  assert [b.demerits for b in breaks] == [d1, d2 + extra, d3]


def test_first_line_follows_a_normal_line():
  # The start of the paragraph counts as class 1: a very loose first line is
  # charged gamma, a loose or tight one is not.
  breaks = line_break(two_lines(2, 0), 40, max_stretch_ratio=2)
  assert breaks[0].demerits == (10 + 800) ** 2 + GAMMA
  breaks = line_break(two_lines(1, 0), 40)
  assert breaks[0].demerits == (10 + 100) ** 2
  breaks = line_break(two_lines(-1, 0), 40)
  assert breaks[0].demerits == (10 + 100) ** 2


def test_last_line_is_charged_gamma_too():
  # The last line has r = 0, class 1, which is too far from class 3.
  breaks = line_break(two_lines(0, 2), 40, max_stretch_ratio=2)
  assert fitness_classes(breaks) == [1, 3, 1]
  assert breaks[2].demerits == 100 + GAMMA


def test_gamma_changes_the_choice(monkeypatch):
  kp81_scoring(monkeypatch)
  items = sample_paragraph()
  # The basic version uses a very loose line (r = 1.12) next to a normal one.
  breaks = basic.line_break(items, 390, max_stretch_ratio=2)
  assert sum(b.demerits for b in breaks) == 28778
  classes = fitness_classes(breaks)
  assert any(abs(c1 - c2) > 1 for c1, c2 in zip(classes, classes[1:]))

  # That costs gamma here, so another way of breaking wins.
  breaks = line_break(items, 390, max_stretch_ratio=2)
  assert sum(b.demerits for b in breaks) == 31040
  classes = fitness_classes(breaks)
  assert all(abs(c1 - c2) <= 1 for c1, c2 in zip(classes, classes[1:]))

  # Without gamma, both versions agree.
  monkeypatch.setattr(full, 'ADJ_DEMERITS', 0)
  breaks = line_break(items, 390, max_stretch_ratio=2)
  assert sum(b.demerits for b in breaks) == 28778


def test_breakpoint_is_kept_for_each_fitness_class():
  # Two ways to reach the break after 'd', at line width 100:
  #   a b / c d    r = 0.5 and -0.6 (tight), 529 + 1024 = 1553 demerits
  #   a b c / d    r = -0.75 and 0 (normal), 2704 + 100 = 2804 demerits
  # The next line, 'e f', is loose (r = 1).  After the tight line it costs
  # gamma, so the path with more demerits at 'd' wins in the end.  It would
  # be lost if only the best breakpoint were kept at 'd'.
  items = paragraph(
      Box(45, 'a'), Glue(5, 10, 4), Box(45, 'b'), Glue(5, 0, 0), Box(3, 'c'),
      Glue(0, 0, 5), Box(100, 'd'), Glue(0, 0, 0),
      Box(45, 'e'), Glue(0, 10, 0), Box(45, 'f'), Glue(0, 0, 0), Box(50, 'g'))
  breaks = line_break(items, 100)
  assert line_ends(items, breaks)[:-1] == ['c', 'd', 'f']
  assert [b.ratio for b in breaks] == [-0.75, 0, 1, 0]
  assert fitness_classes(breaks) == [0, 1, 2, 1]
  assert [b.demerits for b in breaks] == [2704, 100, 12100, 100]

  # The basic version keeps the best breakpoint at 'd', and has no gamma.
  breaks = basic.line_break(items, 100)
  assert line_ends(items, breaks)[:-1] == ['b', 'd', 'f']
  assert fitness_classes(breaks) == [1, 0, 2, 1]
  assert sum(b.demerits for b in breaks) == 1553 + 12100 + 100

  # Without gamma, full.py agrees with it.
  full.ADJ_DEMERITS = 0  # restored by the fixture
  breaks = line_break(items, 100)
  assert line_ends(items, breaks)[:-1] == ['b', 'd', 'f']


# ---------------------------------------------------------------------------
# Flagged penalties: consecutive hyphens (alpha)
# ---------------------------------------------------------------------------

def test_consecutive_hyphens():
  hyphen = Penalty(50, 4, '-', is_hyphen=True)
  items = paragraph(Box(10, 'a'), hyphen, Box(10, 'b'), hyphen, Box(10, 'c'))
  breaks = line_break(items, 14)
  assert line_ends(items, breaks)[:2] == ['a-', 'b-']
  # The second hyphenated line in a row is charged alpha.
  assert [b.demerits for b in breaks] == [2600, 2600 + ALPHA, 100]


def test_unflagged_penalties_are_not_charged():
  flagged = Penalty(50, 4, '-', is_hyphen=True)
  plain = Penalty(50, 4, '-')
  for first, second in ((plain, plain), (flagged, plain), (plain, flagged)):
    items = paragraph(Box(10, 'a'), first, Box(10, 'b'), second, Box(10, 'c'))
    breaks = line_break(items, 14)
    assert [b.demerits for b in breaks] == [2600, 2600, 100]


def test_hyphens_must_be_on_consecutive_lines():
  hyphen = Penalty(50, 4, '-', is_hyphen=True)
  items = paragraph(Box(10, 'a'), hyphen, Box(14, 'b'), Glue(0, 0, 0),
                    Box(10, 'c'), hyphen, Box(10, 'd'))
  breaks = line_break(items, 14)
  assert line_ends(items, breaks)[:3] == ['a-', 'b', 'c-']
  assert [b.demerits for b in breaks] == [2600, 100, 2600, 100]


def test_alpha_changes_the_choice(monkeypatch):
  # aaa- / b bb c- / d ee   two hyphens in a row, all lines perfect
  # aaa- / b bb / c-d ee    one hyphen, but the second line has r = 1
  hyphen = Penalty(50, 2, '-', is_hyphen=True)
  items = paragraph(Box(38, 'aaa'), hyphen, Box(18, 'b'), Glue(0, 4, 0), Box(18, 'bb'),
                    Glue(0, 0, 0), Box(2, 'c'), hyphen, Box(10, 'd'),
                    Glue(0, 4, 0), Box(20, 'ee'))
  breaks = line_break(items, 40)
  assert line_ends(items, breaks)[:-1] == ['aaa-', 'c-']
  assert [b.demerits for b in breaks] == [2600, 2600 + ALPHA, 100]

  # 2600 + alpha > (10 + 100)^2
  monkeypatch.setattr(full, 'DOUBLE_HYPHEN_DEMERITS', 20000)
  breaks = line_break(items, 40)
  assert line_ends(items, breaks)[:-1] == ['aaa-', 'bb']
  assert [b.ratio for b in breaks] == [0, 1, 0]
  assert [b.demerits for b in breaks] == [2600, 12100, 100]


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


# ---------------------------------------------------------------------------
# Varying line widths
# ---------------------------------------------------------------------------

def chars(n):
  """n boxes of width 10 with rigid glue of width 0 in between: lines must
  fit exactly."""
  items = []
  for k in range(n):
    items += [Box(10, str(k + 1)), Glue(0, 0, 0)]
  return paragraph(*items[:-1])


def test_line_widths():
  items = chars(12)
  assert boxes_per_line(items, line_break(items, [20, 40, 30])) == [2, 4, 3, 3]
  assert boxes_per_line(items, line_break(items, [30, 10, 20])) == [3, 1, 2, 2, 2, 2]


def test_last_line_width_repeats():
  items = chars(12)
  assert boxes_per_line(items, line_break(items, [40, 20])) == [4, 2, 2, 2, 2]
  assert boxes_per_line(items, line_break(items, [30])) == [3, 3, 3, 3]
  assert boxes_per_line(items, line_break(items, 30)) == [3, 3, 3, 3]


def test_line_numbers():
  items = chars(12)
  breaks = line_break(items, [20, 40, 30])
  assert [b.line for b in breaks] == [1, 2, 3, 4]


def test_same_position_on_different_lines():
  # 'd' can end line 1 (a b c d, perfect) or line 2 (a b / c d, 12629
  # demerits), both normal lines.  What follows is 'e', 50 wide and rigid,
  # then 'h'.
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
  breaks = line_break(items, [390, 390, 390, 500])
  assert line_ends(items, breaks)[:-1] == [
      'one,', 'beau-', 'the', 'it', 'dark', 'and', 'the', 'when', 'high']
  assert [round(b.ratio, 3) for b in breaks] == [
      0.857, 0.000, 0.280, 0.156, 0.513, 0.158, -0.333, 0.081, 0.275, 0.000]
  assert fitness_classes(breaks) == [2, 1, 1, 1, 2, 1, 1, 1, 1, 1]
  assert [b.demerits for b in breaks] == [4096, 2601, 9, 1, 196, 1, 25, 1, 9, 1]
  assert full.line_break.total_demerits == 6940

  # The first three lines are those of the paragraph set at 390 units.
  narrow = line_break(items, 390)
  assert line_ends(items, narrow)[:3] == line_ends(items, breaks)[:3]


# ---------------------------------------------------------------------------
# Looseness
# ---------------------------------------------------------------------------

def test_looseness_sample(monkeypatch):
  kp81_scoring(monkeypatch)
  items = sample_paragraph()
  totals = reference(items, 500, 10)

  optimum = line_break(items, 500, 10)
  assert len(optimum) == 10
  assert full.line_break.total_demerits == totals[10] == 3606

  tighter = line_break(items, 500, 10, looseness=-1)
  assert len(tighter) == 9
  assert full.line_break.total_demerits == totals[9]
  assert sum(b.demerits for b in tighter) == totals[9]

  looser = line_break(items, 500, 10, looseness=1)
  assert len(looser) == 11
  assert full.line_break.total_demerits == totals[11]

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
  # Boxes of width 10 with glue (0, 5, 0): a line of 40 units holds four
  # boxes (r = 0) or three (r = 1).
  items = []
  for k in range(12):
    items += [Box(10, str(k + 1)), Glue(0, 5, 0)]
  items = paragraph(*items[:-1])
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
  # The paragraph ends like the one in main(), with a legal breakpoint at
  # the finishing glue.
  items = chars(6)
  del items[-3]  # Penalty.NO_BREAK
  breaks = line_break(items, 30)
  assert boxes_per_line(items, breaks) == [3, 3]
  # An empty third line after a break at the finishing glue is infeasible.
  assert line_break(items, 30, looseness=1) == breaks
  assert line_break(items, 30, looseness=-1) == breaks


# ---------------------------------------------------------------------------
# Ties, forced breaks, errors
# ---------------------------------------------------------------------------

def test_ties_keep_the_later_predecessor():
  # Twelve boxes of width 10 with glue (0, 5, 0), no break after the 8th.
  # At 40 units, 3+4+4+1 and 4+3+4+1 have the same total demerits.  The
  # basic version uses "<" and puts the loose line first; "<=" puts it later,
  # like TeX.
  items = []
  for k in range(1, 13):
    items.append(Box(10, str(k)))
    if k == 8:
      items.append(Penalty.NO_BREAK)
    if k < 12:
      items.append(Glue(0, 5, 0))
  items = paragraph(*items)
  breaks = line_break(items, 40)
  assert boxes_per_line(items, breaks) == [4, 3, 4, 1]
  assert [b.ratio for b in breaks] == [0, 1, 0, 0]
  assert boxes_per_line(items, basic.line_break(items, 40)) == [3, 4, 4, 1]


def test_forced_break_accepts_infeasible_line():
  g = Glue(2, 2, 1)
  items = paragraph(Box(10), g, Box(10), Penalty.EJECT, Box(10))
  breaks = line_break(items, 100)
  assert [(b.start, b.end) for b in breaks] == [(0, 3), (4, 7)]
  assert breaks[0].ratio == 39
  # The underfull line is very loose, next to the normal start of paragraph.
  assert breaks[0].demerits == (10 + INF_BAD) ** 2 + GAMMA
  assert breaks[1].demerits == 100 + GAMMA


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
  g = Glue(2, 2, 1)
  first = [Box(10), Glue(0, math.inf, 0), Penalty.EJECT, Glue(7, 0, 0)]
  rest = paragraph(Box(10), g, Box(10), g, Box(10), g, Box(10), g, Box(10))
  for line_width, r in ((24, 1.0), (23, 0.5), (22, 0), (21, -1.0)):
    expected = line_break(rest, line_width)
    breaks = line_break(first + rest, line_width)
    assert [b.ratio for b in breaks] == [0, r, r, 0]
    assert [b.demerits for b in breaks[1:]] == [b.demerits for b in expected]
    # The glue after the forced break is discarded.
    assert [(b.start, b.end) for b in breaks[1:]] == [
        (b.start + 4, b.end + 4) for b in expected]


def test_no_feasible_breakpoints():
  g = Glue(2, 2, 1)
  items = paragraph(Box(10), g, Box(50), g, Box(10))
  with pytest.raises(RuntimeError):
    line_break(items, 20)


def test_paragraph_must_end_with_eject():
  with pytest.raises(AssertionError):
    line_break([Box(10), Glue(2, 2, 1), Box(10)], 22)


# ---------------------------------------------------------------------------
# Same results as basic.py when the new features are not in play
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('max_stretch_ratio', [1, 2, 10])
def test_same_total_as_basic_without_alpha_and_gamma(monkeypatch, max_stretch_ratio):
  monkeypatch.setattr(full, 'DOUBLE_HYPHEN_DEMERITS', 0)
  monkeypatch.setattr(full, 'ADJ_DEMERITS', 0)
  # Without the glue after the last word.  Otherwise basic.py may break
  # there and set the finishing glue on a line of its own, which full.py
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
    assert sum(b.demerits for b in breaks) == sum(b.demerits for b in expected)
    assert len(breaks) == len(expected)
  assert feasible >= 20


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
  optimum = [k for k, total in totals.items() if total == best]
  if looseness != 0 and len(optimum) > 1:
    return True  # the optimum number of lines is ambiguous
  k = optimum[0]
  if looseness > 0:
    k = max(j for j in totals if k <= j <= k + looseness)
  elif looseness < 0:
    k = min(j for j in totals if k + looseness <= j <= k)

  breaks = line_break(items, line_widths, max_stretch_ratio, looseness)
  assert sum(b.demerits for b in breaks) == totals[k]
  assert full.line_break.total_demerits == totals[k]
  if looseness != 0:
    assert len(breaks) == k
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
    if kind < 0.25:
      items.append(Penalty(50, 5, '-', is_hyphen=True))  # hyphen inside a word
      continue
    if kind < 0.35:
      items.append(Penalty(rng.choice([-200, -50, 30, 200])))
    elif kind < 0.40:
      items.append(Penalty.NO_BREAK)
    items.append(Glue(6, rng.choice([2, 3, 4]), rng.choice([1, 2, 4])))
    if kind > 0.95:
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
  # It is a tight line, next to two normal ones: no gamma.
  assert fitness_classes(breaks) == [1, 0, 1]
  assert [b.demerits for b in breaks] == [100, 0, 100]
  assert full.line_break.total_demerits == 200


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
  assert boxes_per_line(items, breaks) == [3, 1]
  assert [b.ratio for b in breaks] == [-11, 0]
  assert [b.demerits for b in breaks] == [0, 100]


def test_final_pass_with_looseness():
  items = overfull_paragraph()
  expected = line_break(items, 20, final_pass=True)
  for looseness in (-1, 1):
    assert line_break(items, 20, looseness=looseness, final_pass=True) == expected


def test_overfull_line_is_not_charged_alpha_or_gamma():
  # 'toolong-' is overfull and ends with a hyphen, right after 'a-'.  The
  # line after it is very loose (r = 2), two classes away from tight.
  hyphen = Penalty(50, 4, '-', is_hyphen=True)
  items = paragraph(Box(16, 'a'), hyphen, Box(50, 'toolong'), hyphen,
                    Box(8, 'b'), Glue(0, 2, 0), Box(8, 'c'), Glue(0, 0, 0), Box(5, 'd'))
  breaks = line_break(items, 20, max_stretch_ratio=2, final_pass=True)
  assert line_ends(items, breaks)[:3] == ['a-', 'toolong-', 'c']
  assert [b.ratio for b in breaks] == [0, -math.inf, 2, 0]
  assert fitness_classes(breaks) == [1, 0, 3, 1]
  # Alpha and gamma are not added to the overfull line itself, but the
  # lines after it are charged as usual.
  assert [b.demerits for b in breaks] == [
      2600, 0, (10 + 800) ** 2 + GAMMA, 100 + GAMMA]


def test_random_paragraphs_final_pass_never_fails():
  rng = random.Random(1983)
  overfull = 0
  for _ in range(300):
    items = random_paragraph(rng)
    line_widths = [rng.randint(20, 120) for _ in range(rng.choice([1, 2, 3]))]
    looseness = rng.choice([-1, 0, 0, 1])
    breaks = line_break(items, line_widths, 2, looseness, final_pass=True)
    assert [b.line for b in breaks] == list(range(1, len(breaks) + 1))
    assert breaks[0].start == 0
    assert breaks[-1].end == len(items) - 1
    for prev, cur in zip(breaks, breaks[1:]):
      assert cur.start > prev.end
      assert not any(isinstance(x, Box) for x in items[prev.end:cur.start])
    overfull += any(b.ratio < -1 for b in breaks)
  assert overfull > 50


if __name__ == '__main__':
  pytest.main([__file__])
