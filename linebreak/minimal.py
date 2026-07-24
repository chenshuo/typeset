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
        demerits = (1 + b)**2
        # print(items[i-1], demerits)
        s = Breakpoint(i, a.line + 1, cum.width + item.width,
                       cum.stretch + item.stretch,
                       cum.shrink + item.shrink,
                       a.total_demerits + demerits, a)
        # TODO: only add Breakpoint with smallest total_demerits to survivors.
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
      ratio = get_ratio(line_width, width, stretch, shrink)
      demerits = print_line(ratio, line)
      total_demerits += demerits
      lines.append((ratio, line))

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
      assert False and "Unknown item"

  # remaining
  stretch += math.inf
  ratio = get_ratio(line_width, width, stretch, shrink)
  demerits = print_line(ratio, line)
  total_demerits += demerits
  lines.append((ratio, line))
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
