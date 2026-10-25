"""Knuth-Plass line breaking as a plain DP over an array, same model as minimal.py.

Only Box and Glue, no Penalty. No hyphenation.

  dp[k] = min over j < k of dp[j] + demerits(line from breaks[j] to breaks[k])

where breaks[] lists the candidate breakpoints in order: -1 for the start of
the paragraph, every glue right after a box, and len(items) for the end.
Unlike minimal.py, the end is a real breakpoint, so the last line is checked
and its demerits counted (with infinite stretch, as in show_results), and each
position keeps only its best predecessor.

This is the textbook DP form, for readers familiar with dynamic programming.
minimal.py and basic.py follow Knuth's formulation instead, scanning items
once and keeping a list of active breakpoints.
"""

import math
from typing import List

from common import Box, Glue, ratio, badness

TRACE = False


def line_break(items, line_width, max_stretch_ratio=1.0) -> List[int]:
  n = len(items)
  breaks = [-1] + [i for i, item in enumerate(items)
                   if isinstance(item, Glue) and i > 0 and isinstance(items[i-1], Box)]
  breaks.append(n)

  # Prefix sums: cum_width[i] is the total width of items[0:i], likewise for
  # cum_stretch and cum_shrink.  A line from break a to break b holds items[a+1:b].
  cum_width = [0.0] * (n + 1)
  cum_stretch = [0.0] * (n + 1)
  cum_shrink = [0.0] * (n + 1)
  for i, item in enumerate(items):
    assert isinstance(item, (Box, Glue)), "Unknown item"
    cum_width[i+1] = cum_width[i] + item.width
    cum_stretch[i+1] = cum_stretch[i] + (item.stretch if isinstance(item, Glue) else 0)
    cum_shrink[i+1] = cum_shrink[i] + (item.shrink if isinstance(item, Glue) else 0)

  m = len(breaks)
  dp = [math.inf] * m     # dp[k]: least total demerits of a paragraph ending at breaks[k]
  prev = [-1] * m         # prev[k]: index j into breaks of the best previous break
  dp[0] = 0

  # j and k index into breaks[]; start and end are positions in items.
  for k in range(1, m):
    end = breaks[k]
    last = (k == m - 1)
    # Walk j backwards: each step makes the line longer, so once it is
    # overfull, every earlier j is overfull too.
    for j in range(k - 1, -1, -1):
      start = breaks[j] + 1  # the glue at breaks[j] is dropped, not in either line
      stretch = cum_stretch[end] - cum_stretch[start]
      if last:
        stretch += math.inf  # the last line has infinite stretch, as in show_results
      r = ratio(line_width,
                total_width=cum_width[end] - cum_width[start],
                total_stretch=stretch,
                total_shrink=cum_shrink[end] - cum_shrink[start])
      if r < -1:
        break
      if not -1 <= r <= max_stretch_ratio or dp[j] == math.inf:
        continue
      d = dp[j] + (1 + badness(r))**2
      if d < dp[k]:
        dp[k] = d
        prev[k] = j

  if TRACE:
    print('   k  break        dp  prev  text before break')
    for k in range(m):
      b = breaks[k]
      text = items[b-1].text if 0 < b <= n else ''
      print(f'{k:4} {b:6} {dp[k]:9} {prev[k]:5}  {text}')

  if dp[-1] == math.inf:
    raise RuntimeError(f"No feasible breakpoints found with line width "
                       f"{line_width} and max stretch ratio {max_stretch_ratio}.")

  # Back trace, dropping the end of paragraph.
  result = []
  k = prev[-1]
  while k > 0:
    result.append(breaks[k])
    k = prev[k]
  result.reverse()
  return result


if __name__ == "__main__":
  from sample import get_sample_paragraph
  from minimal import show_results

  items = get_sample_paragraph()
  print("Items:", len(items))

  TRACE = False
  line_width = 500
  breaks = line_break(items, line_width, 1)
  print("Breaks:", breaks)

  show_results(items, line_width, breaks)
