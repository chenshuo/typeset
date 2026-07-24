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
KP81_PENALTY = False
LINE_PENALTY = 10

def line_break(items, line_width, max_stretch_ratio=1.0) -> List[LineBreakResult]:
  assert isinstance(items[-1], Penalty) and items[-1].value == EJECT_PENALTY
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
      active = _try_break(active, cum, penalty, items, i, line_width, max_stretch_ratio)
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


def _try_break(active, cum, penalty, items, i, line_width, max_stretch_ratio):
  AWFUL_BAD = 0x3fff_ffff
  min_demerits = AWFUL_BAD
  best_breakpoint = None
  survivors = []
  item = items[i]
  for a in active:
    hyphen_width = item.width if isinstance(item, Penalty) else 0

    ratio = get_ratio(line_width,
                      cum.width - a.total_width + hyphen_width,
                      cum.stretch - a.total_stretch,
                      cum.shrink - a.total_shrink)

    # Cannot say 'if ratio >= -1', because ratio could be NaN.
    if (not ratio < -1) and penalty > EJECT_PENALTY:
      survivors.append(a)

    # Only consider feasible breakpoints.
    # FIXME: how about eject penalty?
    if -1 <= ratio <= max_stretch_ratio:
        b = badness(ratio)
        demerits = (LINE_PENALTY + b)**2
        if penalty >= 0:
          demerits += penalty ** 2
          if KP81_PENALTY:
            demerits = (LINE_PENALTY + b + penalty)**2
        elif penalty > EJECT_PENALTY:
          demerits -= penalty ** 2
        if TRACE:
            start = items[a.position - 1] if a.position > 0 else Box(0, '^')
            end = items[i-1]
            if not isinstance(end, Box):
                end = Box(0, '$')
            print('%10s  %10s  %8d' % (start.text, end.text, demerits))

        if isinstance(item, Penalty):
          item = Glue.ZERO
        s = Breakpoint(i, a.line + 1, cum.width + item.width,
                       cum.stretch + item.stretch,
                       cum.shrink + item.shrink,
                       a.total_demerits + demerits,
                       ratio, demerits, a)
        if s.total_demerits < min_demerits:
          min_demerits = s.total_demerits
          best_breakpoint = s

  if min_demerits < AWFUL_BAD:
    survivors.append(best_breakpoint)

  return survivors


def show_results(items, line_width, breaks):
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
  print('-----')
  print('Total demerits', total_demerits)


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

    LINE_PENALTY = 1
    KP81_PENALTY = True
    line_width = 500
    line_width = 390
    breaks = line_break(items, line_width, 1)
    if TRACE:
      print("Breaks:", breaks)

    show_results(items, line_width, breaks)
