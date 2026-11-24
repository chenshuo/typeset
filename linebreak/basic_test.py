"""Unit tests for basic.py (and the scoring functions in common.py)."""

import math
import random

import pytest

import basic
import common
from basic import line_break
from common import (Box, Glue, Penalty, INF_BAD, INF_PENALTY, EJECT_PENALTY,
                    ratio, badness, demerits)
from sample import get_sample_paragraph


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
  return list(items) + [Glue(0, math.inf, 0), Penalty.EJECT]


def sample_paragraph():
  return paragraph(*get_sample_paragraph(hyphenate=True))


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


def reference_total_demerits(items, line_width, max_stretch_ratio):
  """Minimum total demerits by trying every pair of legal breakpoints, without
  an active list.  Returns None if the paragraph cannot be set.

  The paragraph must not contain forced breaks other than the final one.
  """
  n = len(items)
  width, stretch, shrink = [0], [0], [0]
  for item in items:
    is_penalty = isinstance(item, Penalty)
    width.append(width[-1] + (0 if is_penalty else item.width))
    stretch.append(stretch[-1] + getattr(item, 'stretch', 0))
    shrink.append(shrink[-1] + getattr(item, 'shrink', 0))

  best = {-1: 0}  # break position -> total demerits
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

    totals = []
    for a, total in best.items():
      # The line consists of items[a+1 : b], plus the hyphen if any.
      r = ratio(line_width,
                width[b] - width[a + 1] + hyphen_width,
                stretch[b] - stretch[a + 1],
                shrink[b] - shrink[a + 1])
      if -1 <= r <= max_stretch_ratio:
        totals.append(total + demerits(badness(r), penalty))
    if totals:
      best[b] = min(totals)
  return best.get(n - 1)


# ---------------------------------------------------------------------------
# Scoring: ratio, badness, demerits
# ---------------------------------------------------------------------------

def test_ratio():
  assert ratio(100, 100, 0, 0) == 0
  assert ratio(100, 90, 20, 5) == 0.5      # stretch: (W - L) / Y
  assert ratio(100, 104, 20, 8) == -0.5    # shrink: (W - L) / Z
  assert ratio(100, 90, 0, 5) == math.inf   # nothing to stretch
  assert ratio(100, 104, 20, 0) == -math.inf  # nothing to shrink
  assert ratio(100, 90, math.inf, 0) == 0   # last line of a paragraph


def test_badness():
  assert badness(0) == 0
  assert badness(0.5) == 13   # 12.5 rounds up
  assert badness(-0.5) == 13
  assert badness(1) == 100
  assert badness(-1) == 100
  assert badness(2) == 800
  assert badness(10) == INF_BAD  # capped
  assert badness(-1.01) == INF_BAD  # cannot shrink more than the shrinkability
  assert badness(math.inf) == INF_BAD
  assert badness(-math.inf) == INF_BAD


def test_demerits_tex82():
  assert demerits(0, 0) == 100             # (l + b)^2
  assert demerits(13, 0) == 23 ** 2
  assert demerits(13, 50) == 23 ** 2 + 50 ** 2
  assert demerits(13, -50) == 23 ** 2 - 50 ** 2
  assert demerits(13, EJECT_PENALTY) == 23 ** 2  # forced break is free


def test_demerits_kp81(monkeypatch):
  kp81_scoring(monkeypatch)
  assert demerits(0, 0) == 1
  assert demerits(13, 0) == 14 ** 2
  assert demerits(13, 50) == (1 + 13 + 50) ** 2
  assert demerits(13, -50) == 14 ** 2 - 50 ** 2
  assert demerits(13, EJECT_PENALTY) == 14 ** 2


# ---------------------------------------------------------------------------
# Lines, ratios and tolerance
# ---------------------------------------------------------------------------

def five_words():
  """Five words of width 10 separated by glue (2, 2, 1); two words are 22 wide."""
  g = Glue(2, 2, 1)
  return paragraph(Box(10, 'a'), g, Box(10, 'b'), g, Box(10, 'c'), g,
                   Box(10, 'd'), g, Box(10, 'e'))


def test_paragraph_must_end_with_inf_glue_and_eject():
  with pytest.raises(AssertionError):
    line_break([Box(10), Glue(2, 2, 1), Box(10)], 22)
  with pytest.raises(AssertionError):
    line_break([Box(10), Penalty.EJECT], 22)


def test_single_line():
  items = paragraph(Box(10), Glue(2, 2, 1), Box(10))
  breaks = line_break(items, 100)
  assert len(breaks) == 1
  b = breaks[0]
  # The last line is not stretched, thanks to the infinite glue.
  assert (b.line, b.start, b.end, b.ratio, b.demerits) == (1, 0, 4, 0, 100)


def test_result_fields():
  items = five_words()
  breaks = line_break(items, 22)
  # Each line starts right after the previous break and ends at the glue or
  # penalty where it is broken.
  assert [(b.line, b.start, b.end) for b in breaks] == [(1, 0, 3), (2, 4, 7), (3, 8, 10)]
  assert [b.ratio for b in breaks] == [0, 0, 0]
  assert [b.demerits for b in breaks] == [100, 100, 100]


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
  assert [b.demerits for b in breaks] == [(10 + 800) ** 2] * 2 + [100]


def test_cannot_shrink_below_minus_one():
  # Two words can shrink to 21 at most.
  with pytest.raises(RuntimeError):
    line_break(five_words(), 20.5, max_stretch_ratio=10)


# ---------------------------------------------------------------------------
# Legal breakpoints
# ---------------------------------------------------------------------------

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


def test_no_break_penalty():
  items = twelve_chars()
  breaks = line_break(items, 40)
  assert boxes_per_line(items, breaks) == [4, 4, 4]
  assert sum(b.demerits for b in breaks) == 300

  # Glue after an infinite penalty is not a legal breakpoint, so the second
  # line cannot end after the 8th box: one line has to be loose.
  items = twelve_chars(no_break_after=8)
  breaks = line_break(items, 40)
  assert '8' not in line_ends(items, breaks)
  assert len(breaks) == 4
  assert sum(b.demerits for b in breaks) == (10 + 100) ** 2 + 300


def test_ties_keep_the_earlier_predecessor():
  # 3+4+4+1 and 4+3+4+1 have the same total demerits.  Two paths meet after
  # the 7th box; "<" keeps the one seen first, which has the loose line first.
  items = twelve_chars(no_break_after=8)
  breaks = line_break(items, 40)
  assert boxes_per_line(items, breaks) == [3, 4, 4, 1]
  assert [b.ratio for b in breaks] == [1, 0, 0, 0]


def test_glue_is_breakable_only_after_box():
  # Breaking at the second glue would give two perfect lines, but only glue
  # that follows a box is a legal breakpoint.  Breaking at the first glue
  # leaves a line that cannot be stretched, and both boxes do not fit on one
  # line.
  items = paragraph(Box(10), Glue(5, 0, 0), Glue(0, 0, 0), Box(10))
  with pytest.raises(RuntimeError):
    line_break(items, 15)


def test_glue_after_break_belongs_to_next_line():
  # Only the glue at the break is dropped.  Unlike TeX, further glue is not
  # discarded: the second line is 5 + 20 = 25 wide.
  items = paragraph(Box(10), Glue(5, 0, 0), Box(10),
                    Glue(0, 0, 0), Glue(5, 0, 0), Box(20),
                    Glue(0, 0, 0), Box(10))
  breaks = line_break(items, 25)
  assert [(b.start, b.end) for b in breaks] == [(0, 3), (4, 6), (7, 9)]
  assert [b.ratio for b in breaks] == [0, 0, 0]


# ---------------------------------------------------------------------------
# Penalties
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('value, d', [
    (30, 100 + 900),
    (0, 100),
    (-30, 100 - 900),
])
def test_break_at_penalty(value, d):
  breaks = line_break(paragraph(Box(10), Penalty(value), Box(10)), 10)
  assert [(b.start, b.end) for b in breaks] == [(0, 1), (2, 4)]
  assert [b.demerits for b in breaks] == [d, 100]


def test_break_at_penalty_kp81(monkeypatch):
  kp81_scoring(monkeypatch)
  breaks = line_break(paragraph(Box(10), Penalty(30), Box(10)), 10)
  assert [b.demerits for b in breaks] == [(1 + 0 + 30) ** 2, 1]


def test_penalty_changes_the_choice():
  def chars(penalty):
    g = Glue(0, 5, 5)
    return paragraph(Box(10, '1'), g, Box(10, '2'), g, Box(10, '3'), penalty,
                     Box(10, '4'), g, Box(10, '5'))

  # 3+2: r = -0.5 and 0, total 23^2 + 100 = 629, plus the penalty.
  # 2+3: r = 1 and -1, total 110^2 + 110^2 = 24200.
  items = chars(Penalty(0))
  breaks = line_break(items, 25)
  assert boxes_per_line(items, breaks) == [3, 2]
  assert sum(b.demerits for b in breaks) == 629
  # A penalty of 200 costs 40000, more than the difference.
  items = chars(Penalty(200))
  breaks = line_break(items, 25)
  assert boxes_per_line(items, breaks) == [2, 3]
  assert sum(b.demerits for b in breaks) == 24200
  # A bonus is welcome.
  items = chars(Penalty(-150))
  breaks = line_break(items, 25)
  assert boxes_per_line(items, breaks) == [3, 2]
  assert sum(b.demerits for b in breaks) == 629 - 22500


def test_hyphen_width_counts_only_when_broken():
  hyphen = Penalty(50, 4, '-')
  items = paragraph(Box(10, 'a'), hyphen, Box(10, 'b'), hyphen, Box(10, 'c'))
  # 10 + 4 = 14: the hyphen is part of the line that ends with it.
  breaks = line_break(items, 14)
  assert line_ends(items, breaks)[:2] == ['a-', 'b-']
  assert [b.ratio for b in breaks] == [0, 0, 0]
  # No extra demerits for consecutive hyphens in the basic version.
  assert [b.demerits for b in breaks] == [2600, 2600, 100]

  # 10 + 10 + 10 = 30: unused hyphens take no space.
  breaks = line_break(items, 30)
  assert len(breaks) == 1
  assert breaks[0].ratio == 0


def test_forced_break():
  g = Glue(2, 2, 1)
  items = paragraph(Box(10), g, Box(10), Glue(0, 10000, 0), Penalty.EJECT,
                    Box(10), g, Box(10))
  breaks = line_break(items, 100)  # wide enough for everything
  assert [(b.start, b.end) for b in breaks] == [(0, 4), (5, 9)]
  assert breaks[0].ratio == pytest.approx(78 / 10002)
  assert breaks[1].ratio == 0
  assert [b.demerits for b in breaks] == [100, 100]  # a forced break is free


def test_forced_break_after_infinite_glue():
  g = Glue(2, 2, 1)
  items = paragraph(Box(10), g, Box(10), Glue(0, math.inf, 0), Penalty.EJECT,
                    Box(10), g, Box(10))
  breaks = line_break(items, 100)
  assert [(b.start, b.end) for b in breaks] == [(0, 4), (5, 9)]
  assert [b.ratio for b in breaks] == [0, 0]
  assert [b.demerits for b in breaks] == [100, 100]


def test_lines_after_forced_break_can_stretch_and_shrink():
  # The running sums restart after a forced break; otherwise the infinite
  # glue before it would spoil the ratios of all later lines.
  first = [Box(10), Glue(0, math.inf, 0), Penalty.EJECT]
  rest = five_words()
  for line_width, r in ((24, 1.0), (23, 0.5), (22, 0), (21, -1.0)):
    expected = line_break(rest, line_width)
    breaks = line_break(first + rest, line_width)
    assert [b.ratio for b in breaks] == [0, r, r, 0]
    assert [b.demerits for b in breaks[1:]] == [b.demerits for b in expected]
    assert [(b.start, b.end) for b in breaks[1:]] == [
        (b.start + 3, b.end + 3) for b in expected]


def test_forced_break_accepts_infeasible_line():
  # No infinite glue before the forced break: the first line is underfull
  # (r = 78 / 2), but a forced break has to be taken anyway.
  g = Glue(2, 2, 1)
  items = paragraph(Box(10), g, Box(10), Penalty.EJECT, Box(10))
  breaks = line_break(items, 100)
  assert [(b.start, b.end) for b in breaks] == [(0, 3), (4, 6)]
  assert breaks[0].ratio == 39
  assert breaks[0].demerits == (10 + INF_BAD) ** 2
  assert breaks[1].demerits == 100


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
  assert [(b.start, b.end) for b in breaks] == [(0, 3), (4, 5), (6, 8)]
  assert [b.ratio for b in breaks] == [0, -math.inf, 0]
  assert [b.demerits for b in breaks] == [100, 0, 100]


def test_final_pass_does_not_change_feasible_paragraph():
  items = sample_paragraph()
  assert line_break(items, 500, final_pass=True) == line_break(items, 500)


# ---------------------------------------------------------------------------
# The sample paragraph of Knuth & Plass 1981
# ---------------------------------------------------------------------------

def test_kp81_sample_500(monkeypatch):
  kp81_scoring(monkeypatch)
  items = sample_paragraph()
  breaks = line_break(items, 500)
  assert [b.line for b in breaks] == list(range(1, 11))
  assert line_ends(items, breaks)[:-1] == [
      'a', 'was', 'was', "king's", 'the', "king's", 'the', 'ball,', 'her']
  assert [round(b.ratio, 3) for b in breaks] == [
      0.774, 0.179, 0.629, 0.545, 0.000, 0.079, 0.282, 0.294, 0.575, 0.000]
  assert sum(b.demerits for b in breaks) == 3606


def test_kp81_sample_390(monkeypatch):
  kp81_scoring(monkeypatch)
  items = sample_paragraph()
  breaks = line_break(items, 390)
  assert line_ends(items, breaks)[:-1] == [
      'one,', 'beau-', 'the', 'aston-', 'the', 'an', 'when', 'out', 'the', 'a', 'caught']
  assert [round(b.ratio, 3) for b in breaks] == [
      0.857, 0.000, 0.280, 1.000, 0.067, -0.278, 0.536, -0.167, 0.700, -0.176, 0.357, 0.000]
  assert sum(b.demerits for b in breaks) == 31040

  # A higher tolerance admits a very loose line (r = 1.12) and a better total.
  breaks = line_break(items, 390, max_stretch_ratio=2)
  assert max(b.ratio for b in breaks) == pytest.approx(1.12)
  assert sum(b.demerits for b in breaks) == 28778


def test_results_are_consistent():
  items = sample_paragraph()
  breaks = line_break(items, 500)
  # Lines are numbered from 1 and cover the paragraph without gaps.
  assert [b.line for b in breaks] == list(range(1, len(breaks) + 1))
  assert breaks[0].start == 0
  assert breaks[-1].end == len(items) - 1
  for prev, cur in zip(breaks, breaks[1:]):
    assert cur.start == prev.end + 1
  # The reported ratio really sets each line to the line width.
  for b in breaks[:-1]:
    line = items[b.start:b.end]
    width = sum(x.width for x in line if isinstance(x, Box))
    width += sum(x.get_width(b.ratio) for x in line if isinstance(x, Glue))
    if isinstance(items[b.end], Penalty):
      width += items[b.end].width
    assert width == pytest.approx(500)
    assert -1 <= b.ratio <= 1


# ---------------------------------------------------------------------------
# Optimality: compare with exhaustive search
# ---------------------------------------------------------------------------

def check_against_reference(items, line_width, max_stretch_ratio):
  """Returns False if the paragraph cannot be set."""
  expected = reference_total_demerits(items, line_width, max_stretch_ratio)
  if expected is None:
    try:
      breaks = line_break(items, line_width, max_stretch_ratio)
    except RuntimeError:
      return False
    # The only way out is an infeasible last line at the forced break.
    assert not -1 <= breaks[-1].ratio <= max_stretch_ratio
    return False
  breaks = line_break(items, line_width, max_stretch_ratio)
  assert sum(b.demerits for b in breaks) == expected
  return True


@pytest.mark.parametrize('kp81', [False, True])
@pytest.mark.parametrize('max_stretch_ratio', [1, 2, 10])
def test_sample_is_optimal(monkeypatch, kp81, max_stretch_ratio):
  if kp81:
    kp81_scoring(monkeypatch)
  items = sample_paragraph()
  feasible = 0
  for line_width in range(300, 701, 10):
    feasible += check_against_reference(items, line_width, max_stretch_ratio)
  assert feasible >= 20


def random_paragraph(rng):
  items = []
  for _ in range(rng.randint(5, 60)):
    items.append(Box(rng.randint(5, 40)))
    kind = rng.random()
    if kind < 0.10:
      items.append(Penalty(50, 5, '-'))  # hyphen inside a word
      continue
    if kind < 0.20:
      items.append(Penalty(rng.choice([-200, -50, 30, 200])))
    elif kind < 0.25:
      items.append(Penalty.NO_BREAK)
    items.append(Glue(6, rng.choice([2, 3, 4]), rng.choice([1, 2])))
  items.append(Box(rng.randint(5, 40)))
  return paragraph(*items)


def test_random_paragraphs_are_optimal():
  rng = random.Random(1981)
  feasible = 0
  for _ in range(300):
    items = random_paragraph(rng)
    line_width = rng.randint(80, 300)
    max_stretch_ratio = rng.choice([1, 2, 5])
    feasible += check_against_reference(items, line_width, max_stretch_ratio)
  assert feasible > 100


if __name__ == '__main__':
  pytest.main([__file__])
