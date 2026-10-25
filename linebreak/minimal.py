"""Minimal implementation of Knuth-Plass line breaking algorithm.

Only Box and Glue, no Penalty. No hyphenation.
"""

import common
from common import *
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class Breakpoint:
  position: int
  line: int
  cum_width: float
  cum_stretch: float
  cum_shrink: float
  total_demerits: int
  previous: "Breakpoint" = None

TRACE = False


def line_break(items, line_width, max_stretch_ratio=1.0) -> List[int]:
  active: List[Breakpoint] = [Breakpoint(-1, 0, 0, 0, 0, 0)]

  # Cumulative width, stretch and shrink of items before the current position.
  cum = Glue(0, 0, 0)  # Cannot say cum = Glue.ZERO, needs a new object
  for i, item in enumerate(items):
    if isinstance(item, Box):
      cum.width += item.width
    elif isinstance(item, Glue):
      # Only breakable at glue after a box
      if i > 0 and isinstance(items[i-1], Box):
        active = _try_break(active, cum, item, i, line_width, max_stretch_ratio)
        if not active:
          raise RuntimeError(f"No feasible breakpoints found at {i} with line width "
                             f"{line_width} and max stretch ratio {max_stretch_ratio}.")
      cum.width += item.width
      cum.stretch += item.stretch
      cum.shrink += item.shrink
    else:
      assert False, "Unknown item"

  if TRACE:
    print("Active:", len(active))
    for a in active:
      print('Active:', a.position, a.total_demerits, items[a.position-1].text)

  assert active
  # BUG: the last line, from best.position to the end, is never checked for
  # feasibility, nor are its demerits counted.  Since fewer lines mean fewer
  # total demerits, this favors breaking less often and may leave the last
  # line overfull, e.g. 5 words of Box(40) with Glue(10, 5, 3) in a line of 90
  # gives "aaaa bbbb / cccc dddd eeee" (ratio -8.333) instead of 3 lines.
  best = min(active, key=lambda n: n.total_demerits)
  if TRACE:
    print('Best:', best.position, items[best.position-1], best.total_demerits)

  # Back trace
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
    r = ratio(line_width,
              total_width=cum.width - a.cum_width,
              total_stretch=cum.stretch - a.cum_stretch,
              total_shrink=cum.shrink - a.cum_shrink)

    # Cannot say 'if r >= -1', because ratio could be NaN.
    if not r < -1:
      survivors.append(a)

    # Only consider feasible breakpoints.
    if -1 <= r <= max_stretch_ratio:
      b = badness(r)
      demerits = (1 + b)**2
      if TRACE:
        print(a.position, i, ' %6.3f %3d %4d' % (r, b, demerits))
      s = Breakpoint(position=i, line=a.line + 1,
                     cum_width=cum.width + item.width,
                     cum_stretch=cum.stretch + item.stretch,
                     cum_shrink=cum.shrink + item.shrink,
                     total_demerits=a.total_demerits + demerits,
                     previous=a)
      # TODO: only add Breakpoint with smallest total_demerits to survivors.
      # Currently every feasible predecessor 'a' adds its own Breakpoint at
      # position i, so the active list keeps one node per path rather than
      # per position, and may grow exponentially with paragraph length.
      survivors.append(s)

  return survivors


def print_line(ratio, line):
  b = badness(ratio)
  demerits = (1 + b) ** 2
  text = ''.join(x.text for x in line)
  print(f'{ratio:6.3f} {b:7} {demerits:8} ', text)
  return demerits


def show_results(items, line_width, breaks) -> List[Tuple[float, List]]:
  lines = []
  line = []
  width = 0
  stretch = 0
  shrink = 0
  total_demerits = 0
  print(' ratio badness demerits  text')
  print(' ----- ------- --------  ----')
  for i, it in enumerate(items):
    if i in breaks:
      r = ratio(line_width, width, stretch, shrink)
      demerits = print_line(r, line)
      total_demerits += demerits
      lines.append((r, line))

      line = []
      width = 0
      stretch = 0
      shrink = 0
      continue

    if isinstance(it, Box):
      line.append(it)
      width += it.width
    elif isinstance(it, Glue):
      line.append(it)
      width += it.width
      stretch += it.stretch
      shrink += it.shrink
    else:
      assert False, "Unknown item"

  # remaining
  stretch += math.inf
  r = ratio(line_width, width, stretch, shrink)
  demerits = print_line(r, line)
  total_demerits += demerits
  lines.append((r, line))
  print('-----')
  print('Total demerits', total_demerits)
  return lines

if __name__ == "__main__":
    from sample import get_sample_paragraph

    items = get_sample_paragraph()
    print("Items:", len(items))

    TRACE = False
    line_width = 500
    breaks = line_break(items, line_width, 1)
    print("Breaks:", breaks)

    show_results(items, line_width, breaks)
