import math
from dataclasses import dataclass

@dataclass
class Box:
  """Rigid item (character, word fragment, rule). Cannot stretch or shrink."""

  width: float
  text: str = ""


@dataclass
class Glue:
  """Flexible space: natural width w, max stretch +y, max shrink -z."""

  width: float
  stretch: float
  shrink: float


def get_ratio(line_width, total_width, total_stretch, total_shrink):
  if total_width == line_width:
    return 0.0

  # stretch
  if total_width < line_width:
    if total_stretch > 0:
      return (line_width - total_width) / total_stretch

  # shrink
  if total_width > line_width:
    if total_shrink > 0:
      return (line_width - total_width) / total_shrink
  return math.nan

INF_BAD = 10000

def badness(ratio: float) -> int:
  if math.isnan(ratio) or ratio < -1.0:
    return INF_BAD

  # not using round() because Python3's round-half-to-even
  return int(100 * (abs(ratio) ** 3) + 0.5)

def show_results(items, line_width, breaks):
  lines = []
  line = ''
  width = 0
  stretch = 0
  shrink = 0
  total_demerits = 0
  print(' ratio demerits  text')
  print(' ----- --------  ----')
  for i, it in enumerate(items):
    if i in breaks:
      ratio = get_ratio(line_width, width, stretch, shrink)
      demerits = (1 + badness(ratio)) ** 2
      print(f'{ratio:6.3f} {demerits:8} ', line)
      total_demerits += demerits

      line = ''
      width = 0
      stretch = 0
      shrink = 0
      continue

    if isinstance(it, Box):
      line += it.text
      width += it.width

    elif isinstance(it, Glue):
      line += ' '
      width += it.width
      stretch += it.stretch
      shrink += it.shrink

  # remaining
  stretch += math.inf
  ratio = get_ratio(line_width, width, stretch, shrink)
  demerits = (1 + badness(ratio)) ** 2
  total_demerits += demerits
  print(f'{ratio:6.3f} {demerits:8} ', line)
  print('-----')
  print('Total demerits', total_demerits)

