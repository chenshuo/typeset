"""Simple implementation of Knuth-Plass line breaking algorithm.

Box, Glue, and Penalty.  No double hyphen demerits, no fit classes.
"""

from common import *
import common
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class Breakpoint:
  position: int
  line: int
  total_width: float
  total_stretch: float
  total_shrink: float
  total_demerits: int
  ratio: float
  demerits: int
  previous: "Breakpoint" = None


@dataclass
class LineBreakResult:
  line: int  # line number 1-based
  start: int  # inclusive starting node of this line
  end: int  # inclusive break node (e.g. glue or penalty index)
  ratio: float = 0.0  # glue set ratio
  demerits: int = 0  # demerits of this line


TRACE = False

def line_break(items, line_width, max_stretch_ratio=1.0,
               final_pass=False) -> List[LineBreakResult]:
  # final_pass: like TeX's final pass, force an overfull line instead of
  # raising an error when the active list is about to become empty.
  # The paragraph must end with infinitely stretchable glue (so the last line
  # is always feasible, ratio == 0) followed by the eject penalty.
  assert (len(items) >= 2
          and isinstance(items[-2], Glue) and math.isinf(items[-2].stretch)
          and isinstance(items[-1], Penalty) and items[-1].value == EJECT_PENALTY), \
      "Paragraph must end with Glue(0, inf, 0) and Penalty.EJECT."
  active: List[Breakpoint] = [Breakpoint(-1, 0, 0, 0, 0, 0, 0.0, 0)]

  # Cumulative width, stretch and shrink of items before the current position.
  cum = Glue(0, 0, 0)
  for i, item in enumerate(items):
    is_break = False
    penalty = 0
    if isinstance(item, Glue):
      # Breakable at glue after a box
      if i > 0 and isinstance(items[i-1], Box):
        is_break = True
    elif isinstance(item, Penalty):
      # Or less than INF_PENALTY
      if item.value < INF_PENALTY:
        is_break = True
        penalty = item.value

    if is_break:
      active = _try_break(active, cum, penalty, items, i, line_width, max_stretch_ratio,
                          final_pass)
      if not active:
        raise RuntimeError(f"No feasible breakpoints found at {i} with line width "
                           f"{line_width} and max stretch ratio {max_stretch_ratio}.")

    # Update running sums
    if isinstance(item, Box):
      cum.width += item.width
    elif isinstance(item, Glue):
      cum.width += item.width
      cum.stretch += item.stretch
      cum.shrink += item.shrink
    else:
      # Penalty has no width
      assert isinstance(item, Penalty)

  if TRACE:
    print("#Active:", len(active))
    for a in active:
      print('Active:', a.position, a.total_demerits, items[a.position-1].text)

  assert active
  assert all(n.position == len(items) - 1 for n in active)
  best = min(active, key=lambda n: n.total_demerits)
  print('Best:', best.position, items[best.position], best.total_demerits)

  breaks = []
  while best.previous:
    breaks.append(LineBreakResult(best.line,
                                  best.previous.position + 1,
                                  best.position,
                                  best.ratio,
                                  best.demerits))
    best = best.previous
  assert breaks[-1].start == 0, breaks
  breaks.reverse()
  return breaks


def _try_break(active, cum, penalty, items, i, line_width, max_stretch_ratio,
               final_pass=False):
  AWFUL_BAD = 0x3fff_ffff
  min_demerits = AWFUL_BAD
  best_breakpoint = None
  survivors = []
  item = items[i]
  hyphen_width = 0
  if isinstance(item, Penalty):
      hyphen_width = item.width
      item = Glue.ZERO
  # A forced break (eject) deactivates every active node, so the line must be
  # set even if no candidate is feasible (cf. TeX's artificial_demerits).
  forced = penalty <= EJECT_PENALTY
  for a in active:
    ratio = get_ratio(line_width,
                      cum.width - a.total_width + hyphen_width,
                      cum.stretch - a.total_stretch,
                      cum.shrink - a.total_shrink)

    # Cannot say 'if ratio >= -1', because ratio could be NaN.
    if (not ratio < -1) and not forced:
      survivors.append(a)

    # Only consider feasible breakpoints, except at a forced break where
    # infeasible lines are accepted with maximal badness.
    #
    # Using INF_BAD for any infeasible line (overfull, too loose, or NaN) is a
    # simplification of TeX82 (tex.web §851-855).  There, an infeasible line
    # at a forced break is normally just deactivated and dropped; only when
    # this would empty the active list on the final pass is the last remaining
    # node kept, with "artificial_demerits", i.e. demerits 0 (not (l+b)^2).
    # Since the active list is ordered by position, TeX thus falls back to the
    # latest (shortest) possible last line, whereas here every active node is
    # a candidate and the one with the lowest total demerits wins.  As a forced
    # break leaves exactly one active node either way, this choice affects only
    # which line is picked and the reported totals, never later comparisons.
    feasible = -1 <= ratio <= max_stretch_ratio
    if feasible or forced:
        b = badness(ratio) if feasible else INF_BAD
        d = demerits(b, penalty)

        if TRACE:
            start = items[a.position - 1] if a.position > 0 else Box(0, '^')
            end = items[i-1]
            if not isinstance(end, Box):
                end = Box(0, '$')
            print('%10s  %10s  %8d' % (start.text, end.text, d))

        # The new line starts right after the break item.  Note that TeX82
        # discards all discardable items (glue, penalties, kerns, math) at the
        # beginning of a line, up to the first box; here only the break item
        # itself is consumed, so any further glue after the break is counted
        # in the next line's width.
        s = Breakpoint(i, a.line + 1, cum.width + item.width,
                       cum.stretch + item.stretch,
                       cum.shrink + item.shrink,
                       a.total_demerits + d,
                       ratio, d, a)
        if s.total_demerits < min_demerits:
          min_demerits = s.total_demerits
          best_breakpoint = s

  if min_demerits < AWFUL_BAD:
    survivors.append(best_breakpoint)

  # On the final pass, never lose all active nodes (tex.web §854): break
  # here anyway from the last active node, giving an overfull line with
  # "artificial_demerits", i.e. demerits 0.  The active list is ordered by
  # position, so this is the latest possible start, the least overfull line.
  if final_pass and not survivors:
    a = active[-1]
    ratio = get_ratio(line_width,
                      cum.width - a.total_width + hyphen_width,
                      cum.stretch - a.total_stretch,
                      cum.shrink - a.total_shrink)
    if TRACE:
      print('Overfull line forced at', i, 'ratio %.3f' % ratio)
    survivors.append(Breakpoint(i, a.line + 1, cum.width + item.width,
                                cum.stretch + item.stretch,
                                cum.shrink + item.shrink,
                                a.total_demerits, ratio, 0, a))

  return survivors


def show_results(items, line_width, breaks):
  lines = []
  print(' ratio badness demerits  text')
  print(' ----- ------- --------  ----')
  total_demerits = 0
  for b in breaks:
    ratio = b.ratio
    bad = badness(ratio)
    text = ''.join(x.text for x in items[b.start:b.end] if not isinstance(x, Penalty))
    text += items[b.end].text
    total_demerits += b.demerits
    print(f'{ratio:6.3f} {bad:7} {b.demerits:8} ', text)
    if isinstance(items[b.end], Glue):
        lines.append((ratio, items[b.start:b.end]))
    else:
        assert isinstance(items[b.end], Penalty)
        # include hyphen
        lines.append((ratio, items[b.start:b.end+1]))
  print('-----')
  print('Total demerits', total_demerits)
  return lines


if __name__ == "__main__":
    from sample import get_sample_paragraph
    import sys

    items = get_sample_paragraph(hyphenate=True)
    items.append(Glue(0, math.inf, 0))
    items.append(Penalty.EJECT)
    print("Items:", len(items))
    TRACE = 0
    if TRACE:
      for i, item in enumerate(items):
        print(f"{i:3} {item}")

    common.LINE_PENALTY = 1
    common.KP81_PENALTY = True
    line_width = 500
    line_width = 390
    breaks = line_break(items, line_width, 1)
    if TRACE:
      print("Breaks:", breaks)

    show_results(items, line_width, breaks)
