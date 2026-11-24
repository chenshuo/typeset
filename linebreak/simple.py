"""Knuth-Plass line breaking for Chinese (and mixed Chinese/Latin) text.

This is basic.py plus the features that matter for CJK paragraphs:

* Glue and penalties after a break are discarded, up to the next box, so
  e.g. the half-width glue around punctuation never starts a line.
* Varying line widths: the n-th line has width line_widths[n-1], the last
  width repeats.
* Looseness: ask for a paragraph that is some lines longer or shorter than
  the optimum, e.g. to get rid of a single character on the last line.
* Ties go to the later predecessor ("<="), like TeX.

The final pass of basic.py, which sets an overfull line instead of giving up,
is kept.  No fitness classes, no double hyphen demerits.
"""

import math
from typing import List

from common import *
# In a Breakpoint of this file, cum_width, cum_stretch and cum_shrink are the
# totals up to the first box of the next line, i.e. without the items
# discarded after the break.
from basic import Breakpoint, LineBreakResult, show_results


TRACE = False


def cum_after(items, i, cum) -> Glue:
  """Totals up to the first box after a break at i: glue and penalties at the
  beginning of a line are discarded, after(b) in the 1981 paper."""
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
      break  # nothing is discarded across a forced break
  return after


def line_break(items, line_widths, max_stretch_ratio=1.0,
               looseness=0, final_pass=False) -> List[LineBreakResult]:
  # line_widths: one width for all lines, or a list with the widths of the
  # first lines; the last one is used for all further lines.
  # looseness: try to make the paragraph this many lines longer (> 0) or
  # shorter (< 0) than the optimum, as far as feasible.
  # final_pass: like TeX's final pass, force an overfull line instead of
  # raising an error when the active list is about to become empty.
  # The paragraph must end with infinitely stretchable glue (so the last line
  # is always feasible, ratio == 0) followed by the eject penalty.
  assert (len(items) >= 2
          and isinstance(items[-2], Glue) and math.isinf(items[-2].stretch)
          and isinstance(items[-1], Penalty) and items[-1].value == EJECT_PENALTY), \
      "Paragraph must end with Glue(0, inf, 0) and Penalty.EJECT."
  if not isinstance(line_widths, (list, tuple)):
    line_widths = [line_widths]

  # Breakpoints that end line j0 or a later one are equivalent if they are at
  # the same position: all lines after them have the same width.  Only the
  # best of them is kept.  With looseness the line number always matters.
  j0 = len(line_widths) - 1
  while j0 > 0 and line_widths[j0 - 1] == line_widths[-1]:
    j0 -= 1
  if looseness != 0:
    j0 = math.inf

  active: List[Breakpoint] = [Breakpoint(-1, 0, 0, 0, 0, 0, 0.0, 0)]

  # Cumulative width, stretch and shrink of items before the current position.
  cum = Glue(0, 0, 0)  # Cannot say cum = Glue.ZERO, needs a new object
  for i, item in enumerate(items):
    is_break = False
    if isinstance(item, Glue):
      # Breakable at glue after a box
      is_break = i > 0 and isinstance(items[i-1], Box)
    elif isinstance(item, Penalty):
      # Or less than INF_PENALTY
      is_break = item.value < INF_PENALTY

    if is_break:
      active = _try_break(active, cum, items, i, line_widths, j0,
                          max_stretch_ratio, final_pass)
      if not active:
        raise RuntimeError(f"No feasible breakpoints found at {i} with line widths "
                           f"{line_widths} and max stretch ratio {max_stretch_ratio}.")
      if TRACE:
        new = [str(a) for a in active if a.position == i]
        print('%3d' % i, items[i-1].text, *new, sep='  ')
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

  assert active
  assert all(n.position == len(items) - 1 for n in active)
  # Among equals, min() takes the first one, which has the fewest lines.
  best = min(active, key=lambda n: n.total_demerits)
  if looseness != 0:
    best = _choose_looseness(active, best, looseness)
  if TRACE:
    for a in active:
      print('Active:', a, '<- best' if a is best else '')

  # Back trace
  breaks = []
  while best.previous:
    start = best.previous.position + 1
    while start < best.position and not isinstance(items[start], Box):
      start += 1  # skip the items discarded after the previous break
    breaks.append(LineBreakResult(best.line, start, best.position,
                                  best.ratio, best.demerits))
    best = best.previous
  # breaks is never empty here: the paragraph ends with Penalty.EJECT, so every
  # active node is at len(items) - 1 (asserted above), never the initial node.
  assert breaks[-1].start == 0, breaks
  breaks.reverse()
  return breaks


def _choose_looseness(active, best, looseness):
  """The paragraph whose number of lines is as close as possible to the
  optimum plus looseness, without overshooting; the best one of that length."""
  k = best.line  # optimum number of lines
  s = 0          # difference in lines of the best choice so far
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
  # A forced break (eject) deactivates every active node, so the line must be
  # set even if no candidate is feasible (cf. TeX's artificial_demerits).
  forced = penalty <= EJECT_PENALTY
  after = cum_after(items, i, cum)

  def ratio_from(a):
    """Adjustment ratio of the line from a to i, which is line a.line + 1."""
    line_width = line_widths[min(a.line + 1, len(line_widths)) - 1]
    return ratio(line_width,
                 total_width=cum.width - a.cum_width + hyphen_width,
                 total_stretch=cum.stretch - a.cum_stretch,
                 total_shrink=cum.shrink - a.cum_shrink)

  def break_from(a, r, d):
    return Breakpoint(position=i, line=a.line + 1,
                      cum_width=after.width,
                      cum_stretch=after.stretch,
                      cum_shrink=after.shrink,
                      total_demerits=a.total_demerits + d,
                      ratio=r, demerits=d, previous=a)

  survivors = []
  best = {}      # line number, at most j0 -> best Breakpoint ending that line here
  fallback = {}  # the same for infeasible lines, used only at a forced break
  for a in active:
    r = ratio_from(a)
    if r >= -1 and not forced:
      survivors.append(a)

    # Only consider feasible breakpoints, except at a forced break where
    # infeasible lines (overfull or too loose) are accepted with maximal
    # badness.  See basic.py for how this differs from TeX82.
    feasible = -1 <= r <= max_stretch_ratio
    if feasible or forced:
      b = badness(r) if feasible else INF_BAD
      d = demerits(b, penalty)
      s = break_from(a, r, d)
      if TRACE:
        print('    r=%.3f b=%3d d=%4d D=%5d  %d to %d, line %d' % (
            r, b, d, s.total_demerits, a.position, i, s.line))

      key = min(s.line, j0)
      candidates = best if feasible else fallback
      # "<=": among equals the later predecessor wins, the active list is
      # ordered by position.
      if key not in candidates or s.total_demerits <= candidates[key].total_demerits:
        candidates[key] = s

  # A forced break has to be taken, but an infeasible line is accepted only
  # if there is no feasible one.  Otherwise looseness could choose it for its
  # number of lines.
  if not best:
    best = fallback
  survivors.extend(best[key] for key in sorted(best))

  # On the final pass, never lose all active nodes (tex.web §854): break
  # here anyway, giving an overfull line with "artificial_demerits", i.e.
  # demerits 0.  The active list is ordered by position, so the last node is
  # the latest possible start, the least overfull line.  If several nodes end
  # different lines there, take the best one.
  if final_pass and not survivors:
    last = [a for a in active if a.position == active[-1].position]
    a = min(reversed(last), key=lambda n: n.total_demerits)
    r = ratio_from(a)
    if TRACE:
      print('Overfull line forced at', i, 'ratio %.3f' % r)
    survivors.append(break_from(a, r, 0))

  return survivors


def main():
  """Sets the sample text of render_simple.py in a few ways."""
  import font_util
  from render_simple import Params, SAMPLE_TEXT, get_hb_font, get_items

  size = 12
  font = font_util.default_cjk_font()
  assert font, 'no CJK font found'
  items = get_items(SAMPLE_TEXT, Params(get_hb_font(font, size), size))

  def show(title, line_widths_em, **kwargs):
    print(f'\n{title}')
    line_widths = [size * w for w in line_widths_em]
    breaks = line_break(items, line_widths, **kwargs)
    show_results(items, line_widths, breaks)

  show('22 em', [22])
  show('22 em, looseness=1', [22], max_stretch_ratio=2, looseness=1)
  show('Three lines of 16 em, then 22 em', [16, 16, 16, 22], max_stretch_ratio=2,
       final_pass=True)


if __name__ == "__main__":
  main()
