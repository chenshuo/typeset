"""Plain implementation of Knuth-Plass line breaking algorithm.

Box, Glue, and Penalty.  No double hyphen demerits, no fit classes.
"""

from common import *
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
  previous: "Breakpoint" = None

TRACE = False

def line_break(items, line_width, max_stretch_ratio=1.0) -> List[int]:
  active: List[Breakpoint] = [Breakpoint(-1, 0, 0, 0, 0, 0)]

  # Cumulative width, stretch and shrink of items before the current position.
  cum = Glue(0, 0, 0)
  for i, item in enumerate(items):
    is_break = False

    if isinstance(item, Box):
      cum.width += item.width
    elif isinstance(item, Glue):
      # Only breakable at glue after a box
      if i > 0 and isinstance(items[i-1], Box):
        active = _try_break(active, cum, item, i, line_width, max_stretch_ratio)
        if not active:
          raise RuntimeError(f"No feasible breakpoints found with line width "
                             "{line_width} and max stretch ratio {max_stretch_ratio}.")
      cum.width += item.width
      cum.stretch += item.stretch
      cum.shrink += item.shrink

    else:
      assert False and "Unknown item"

  if TRACE:
    print("Active:", len(active))
    for a in active:
      print('Active:', a.position, a.total_demerits, items[a.position-1].text)

  assert active
  best = min(active, key=lambda n: n.total_demerits)
  print('Best:', best.position, items[best.position-1], best.total_demerits)

  breaks = []
  while best:
    breaks.append(best.position)
    best = best.previous
  assert breaks[-1] == -1
  breaks.pop()
  breaks.reverse()
  return breaks


def _try_break(active, cum, item, i, line_width, max_stretch_ratio):
  AWFUL_BAD = 1_000_000_000
  min_demerits = AWFUL_BAD
  best_breakpoint = None
  survivors = []
  for a in active:
    ratio = get_ratio(line_width,
                      cum.width - a.total_width,
                      cum.stretch - a.total_stretch,
                      cum.shrink - a.total_shrink)

    # Cannot say 'if ratio >= -1', because ratio could be NaN.
    if not ratio < -1:
      survivors.append(a)

    # Only consider feasible breakpoints.
    if -1 <= ratio <= max_stretch_ratio:
        b = badness(ratio)
        demerits = (LINE_PENALTY + b)**2
        s = Breakpoint(i, a.line + 1, cum.width + item.width,
                       cum.stretch + item.stretch,
                       cum.shrink + item.shrink,
                       a.total_demerits + demerits, a)
        if s.total_demerits < min_demerits:
          min_demerits = s.total_demerits
          best_breakpoint = s

  if min_demerits < AWFUL_BAD:
    survivors.append(best_breakpoint)

  return survivors

if __name__ == "__main__":
    from sample import get_sample_paragraph

    items = get_sample_paragraph()
    print("Items:", len(items))

    TRACE = True
    line_width = 500
    breaks = line_break(items, line_width)
    print("Breaks:", breaks)

    show_results(items, line_width, breaks)
