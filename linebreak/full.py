"""Full Knuth-Plass line breaking algorithm, following "The Algorithm Itself"
of the 1981 paper: flagged penalties, fitness classes, varying line widths and
looseness.  Like basic.py, it has a final pass that sets an overfull line
instead of giving up.
"""

import math
from dataclasses import dataclass
from typing import List

from common import *
import common
from basic import LineBreakResult

DOUBLE_HYPHEN_DEMERITS = 3000  # alpha
ADJ_DEMERITS = 3000            # gamma


@dataclass
class Breakpoint:
  position: int
  line: int
  fitness: int
  cum_width: float
  cum_stretch: float
  cum_shrink: float
  total_demerits: int
  ratio: float
  demerits: int
  previous: "Breakpoint" = None


def fitness_class(r: float) -> int:
  if r < -0.5:
    return 0  # tight
  if r <= 0.5:
    return 1  # normal
  if r <= 1:
    return 2  # loose
  return 3    # very loose


def is_flagged(items, position) -> bool:
  return position >= 0 and getattr(items[position], 'is_hyphen', False)


def cum_after(items, i, cum) -> Glue:
  """Totals up to the first box after a break at i: glue and penalties at the
  beginning of a line are discarded, after(b) in the paper."""
  after = Glue(cum.width, cum.stretch, cum.shrink)
  for k in range(i, len(items)):
    item = items[k]
    if isinstance(item, Box):
      break
    if isinstance(item, Glue):
      after.width += item.width
      after.stretch += item.stretch
      after.shrink += item.shrink
    elif item.value <= EJECT_PENALTY and k > i:
      break
  return after


def line_break(items, line_widths, max_stretch_ratio=1.0,
               looseness=0, final_pass=False) -> List[LineBreakResult]:
  # final_pass: like TeX's final pass, force an overfull line instead of
  # raising an error when the active list is about to become empty.
  assert isinstance(items[-1], Penalty) and items[-1].value == EJECT_PENALTY, \
      "Paragraph must end with Penalty.EJECT."
  if not isinstance(line_widths, (list, tuple)):
    line_widths = [line_widths]

  # Breakpoints ending line j0 or later are equivalent: all later lines have
  # the same width.  With looseness, line numbers always matter.
  j0 = len(line_widths) - 1
  while j0 > 0 and line_widths[j0 - 1] == line_widths[-1]:
    j0 -= 1
  if looseness != 0:
    j0 = math.inf

  active: List[Breakpoint] = [Breakpoint(-1, 0, 1, 0, 0, 0, 0, 0.0, 0)]
  max_active = 1

  cum = Glue(0, 0, 0)
  for i, item in enumerate(items):
    is_break = False
    if isinstance(item, Glue):
      is_break = i > 0 and isinstance(items[i-1], Box)
    elif isinstance(item, Penalty):
      is_break = item.value < INF_PENALTY

    if is_break:
      active = _try_break(active, cum, items, i, line_widths, j0, max_stretch_ratio,
                          final_pass)
      if not active:
        raise RuntimeError(f"No feasible breakpoints found at {i}.")
      max_active = max(max_active, len(active))
      if isinstance(item, Penalty) and item.value <= EJECT_PENALTY:
        # No line spans a forced break, so restart the running sums.  The
        # line before it usually ends with infinite glue, which would turn
        # the stretch of every later line into inf - inf = nan.
        cum = Glue(0, 0, 0)
        after = cum_after(items, i, cum)
        for a in active:
          a.cum_width = after.width
          a.cum_stretch = after.stretch
          a.cum_shrink = after.shrink

    if isinstance(item, Box):
      cum.width += item.width
    elif isinstance(item, Glue):
      cum.width += item.width
      cum.stretch += item.stretch
      cum.shrink += item.shrink

  assert all(n.position == len(items) - 1 for n in active)
  best = min(active, key=lambda n: n.total_demerits)
  if looseness != 0:
    best = _choose_looseness(active, best, looseness)
  line_break.max_active = max_active
  line_break.total_demerits = best.total_demerits

  breaks = []
  while best.previous:
    start = best.previous.position + 1
    while start < best.position and not isinstance(items[start], Box):
      start += 1  # skip discarded items
    breaks.append(LineBreakResult(best.line, start, best.position,
                                  best.ratio, best.demerits))
    best = best.previous
  breaks.reverse()
  return breaks


def _choose_looseness(active, best, looseness):
  k = best.line  # optimum number of lines
  s = 0
  for a in active:
    delta = a.line - k
    if looseness <= delta < s or s < delta <= looseness:
      s = delta
      best = a
    elif delta == s and a.total_demerits < best.total_demerits:
      best = a
  return best


def _try_break(active, cum, items, i, line_widths, j0, max_stretch_ratio,
               final_pass=False):
  item = items[i]
  penalty, hyphen_width = 0, 0
  if isinstance(item, Penalty):
    penalty, hyphen_width = item.value, item.width
  forced = penalty <= EJECT_PENALTY
  after = cum_after(items, i, cum)

  survivors = []
  best = {}      # (line, fitness) -> best Breakpoint ending here
  fallback = {}  # the same for infeasible lines, used only at a forced break
  for a in active:
    line = a.line + 1
    line_width = line_widths[min(line, len(line_widths)) - 1]
    r = ratio(line_width,
              total_width=cum.width - a.cum_width + hyphen_width,
              total_stretch=cum.stretch - a.cum_stretch,
              total_shrink=cum.shrink - a.cum_shrink)

    if r >= -1 and not forced:
      survivors.append(a)

    feasible = -1 <= r <= max_stretch_ratio
    if feasible or forced:
      b = badness(r) if feasible else INF_BAD
      d = demerits(b, penalty)
      if is_flagged(items, i) and is_flagged(items, a.position):
        d += DOUBLE_HYPHEN_DEMERITS  # alpha
      c = fitness_class(r)
      if abs(c - a.fitness) > 1:
        d += ADJ_DEMERITS            # gamma

      key = (min(line, j0), c)
      total = a.total_demerits + d
      candidates = best if feasible else fallback
      if key not in candidates or total <= candidates[key].total_demerits:
        candidates[key] = Breakpoint(position=i, line=line, fitness=c,
                               cum_width=after.width,
                               cum_stretch=after.stretch,
                               cum_shrink=after.shrink,
                               total_demerits=total,
                               ratio=r, demerits=d, previous=a)

  # A forced break has to be taken, but an infeasible line is accepted only
  # if there is no feasible one.  Otherwise looseness could choose it for its
  # number of lines.
  if not best:
    best = fallback

  # At most 4 breakpoints per line number, one for each fitness class.
  for (line, c), s in sorted(best.items()):
    least = min(t.total_demerits for (l, _), t in best.items() if l == line)
    if s.total_demerits <= least + ADJ_DEMERITS:
      survivors.append(s)

  # On the final pass, never lose all active nodes (tex.web §854): break
  # here anyway, giving an overfull line with "artificial_demerits", i.e.
  # demerits 0, without alpha or gamma.  The active list is ordered by
  # position, so the last node is the latest possible start, the least
  # overfull line.  If several nodes are there, for different line numbers
  # or fitness classes, take the best one.
  if final_pass and not survivors:
    last = [a for a in active if a.position == active[-1].position]
    a = min(reversed(last), key=lambda n: n.total_demerits)
    line = a.line + 1
    r = ratio(line_widths[min(line, len(line_widths)) - 1],
              total_width=cum.width - a.cum_width + hyphen_width,
              total_stretch=cum.stretch - a.cum_stretch,
              total_shrink=cum.shrink - a.cum_shrink)
    survivors.append(Breakpoint(position=i, line=line, fitness=fitness_class(r),
                                cum_width=after.width,
                                cum_stretch=after.stretch,
                                cum_shrink=after.shrink,
                                total_demerits=a.total_demerits,
                                ratio=r, demerits=0, previous=a))

  return survivors


def show_results(items, breaks):
  print(' ratio badness fit demerits  text')
  print(' ----- ------- --- --------  ----')
  total = 0
  for b in breaks:
    text = ''.join(x.text for x in items[b.start:b.end] if not isinstance(x, Penalty))
    if isinstance(items[b.end], Penalty):
      text += items[b.end].text
    total += b.demerits
    bad = badness(b.ratio)
    print(f'{b.ratio:6.3f} {bad:7} {fitness_class(b.ratio):3} {b.demerits:8}  {text}')
  print('-----')
  print('Total demerits', total)


def main():
  from sample import get_sample_paragraph

  items = get_sample_paragraph(hyphenate=True)
  items.append(Glue(0, math.inf, 0))
  items.append(Penalty.EJECT)

  # Same scoring as KP81: demerits = (1 + b + p)^2.
  common.LINE_PENALTY = 1
  common.KP81_PENALTY = True

  # The first 3 lines are 390 units wide, the rest are 500 units.
  line_widths = [390, 390, 390, 500]
  breaks = line_break(items, line_widths, max_stretch_ratio=1)
  show_results(items, breaks)


if __name__ == "__main__":
  main()
