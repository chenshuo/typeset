"""Knuth-Plass line breaking as a plain DP over an array, same model as minimal.py.

Only Box and Glue, no Penalty. No hyphenation.

  dp[j + 1] = min over i < j of dp[i] + demerits(items[i:j])

where dp[i] is the least total demerits of the lines before a line starting at
item i, and demerits is (1 + badness)**2, or infinity if the line is
infeasible.  The legal line starts are 0 (start of paragraph) and j + 1 for
every glue j right after a box; every other position before the end stays at
infinity.  dp[len(items) + 1], after the end of paragraph, holds the answer.
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

  assert all(isinstance(item, (Box, Glue)) for item in items), "Unknown item"

  # A break at glue j drops the glue, so the next line starts at j + 1.
  dp = [math.inf] * (n + 2)   # dp[i]: least demerits before a line starting at i
  prev = [-1] * (n + 2)       # prev[j + 1] = i: the best last line is items[i:j]
  dp[0] = 0

  for j in range(1, n + 1):
    # A line may end at the end of the paragraph or at a glue right after a box.
    if j < n and not (isinstance(items[j], Glue) and isinstance(items[j-1], Box)):
      continue

    # Running totals of items[i:j].  Prefix sums would work too: with
    # cum_width[k] the total width of items[0:k], the line is cum_width[j] -
    # cum_width[i] wide, likewise for stretch and shrink.  The last line has
    # infinite stretch, as in show_results.
    total_width = 0
    total_stretch = math.inf if j == n else 0
    total_shrink = 0

    # Fill in dp[j+1] and prev[j+1] by trying every earlier i as the start of
    # the line items[i:j], skipping those that are not legal line starts.
    # i < j, so a line is never empty, e.g. after a trailing glue at the end of
    # the paragraph.  Walk i backwards: each step makes the line longer, so
    # once it is overfull, every earlier i is overfull too.
    for i in range(j - 1, -1, -1):
      # Add items[i] before skipping i, so the totals stay those of items[i:j].
      total_width += items[i].width
      if isinstance(items[i], Glue):
        total_stretch += items[i].stretch
        total_shrink += items[i].shrink
      if dp[i] == math.inf:
        continue
      r = ratio(line_width, total_width, total_stretch, total_shrink)
      if r < -1:
        break
      if not -1 <= r <= max_stretch_ratio:
        continue
      d = dp[i] + (1 + badness(r))**2
      if d < dp[j+1]:
        dp[j+1] = d
        prev[j+1] = i

  if TRACE:
    print(' break        dp  prev  text before break')
    for i in range(n + 2):
      if dp[i] < math.inf:
        text = items[i-2].text if i >= 2 else ''
        p = prev[i] - 1 if i > 0 else ''
        print(f'{i-1:6} {dp[i]:9} {p:>5}  {text}')

  if dp[n+1] == math.inf:
    raise RuntimeError(f"No feasible breakpoints found with line width "
                       f"{line_width} and max stretch ratio {max_stretch_ratio}.")

  # Back trace, dropping the end of paragraph.
  result = []
  i = prev[n+1]
  while i > 0:
    result.append(i - 1)
    i = prev[i]
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
