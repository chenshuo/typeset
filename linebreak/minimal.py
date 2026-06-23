"""Minimal implementation of Knuth-Plass line breaking algorithm.

Only Box and Glue, no Penality. No hyphenation.
"""

from common import *
from dataclasses import dataclass


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


def line_break(items, line_width, max_stretch_ratio=1):
  active = [Breakpoint(-1, 0, 0, 0, 0, 0)]

  # Cumulative width, stretch and shrink of items beforethe current position.
  cum = Glue(0, 0, 0)
  for i, item in enumerate(items):
    if isinstance(item, Box):
      cum.width += item.width
    elif isinstance(item, Glue):
      # only breakable at glue after a box
      if i > 0 and isinstance(items[i-1], Box):
        active = _try_break(active, cum, item, i, line_width, max_stretch_ratio)
        if not active:
          raise RuntimeError(f"No feasible breakpoints found with line width {line_width} and max stretch ratio {max_stretch_ratio}.")
      cum.width += item.width
      cum.stretch += item.stretch
      cum.shrink += item.shrink
    else:
      assert False and "Unknown item"

  print("Active:", len(active))

  assert active
  best = active[0]
  for a in active:
    if a.total_demerits < best.total_demerits:
      best = a
  print('Best:',best.position, items[best.position-1], best.total_demerits)

  breaks = []
  while best:
    breaks.append(best.position)
    best = best.previous
  assert breaks[-1] == -1
  breaks.pop()
  breaks.reverse()
  return breaks


def _try_break(active, cum, item, i, line_width, max_stretch_ratio):
  survivors = []
  for a in active:
    ratio = get_ratio(line_width,
                      cum.width - a.total_width,
                      cum.stretch - a.total_stretch,
                      cum.shrink - a.total_shrink)
    # print(i, a.position, items[i-1], ratio)

    # Cannot say 'if ratio >= -1', because ratio could be NaN.
    if not ratio < -1:
      survivors.append(a)

    # Only consider feasible breakpoints.
    if -1 <= ratio <= max_stretch_ratio:
        b = badness(ratio)
        demerits = (1 + b)**2
        # print(items[i-1], demerits)
        s = Breakpoint(i, a.line + 1, cum.width + item.width,
                       cum.stretch + item.stretch,
                       cum.shrink + item.shrink,
                       a.total_demerits + demerits, a)
        survivors.append(s)

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
