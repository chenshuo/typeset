import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

@dataclass
class Box:
  """Rigid item (character, word fragment, rule). Cannot stretch or shrink."""

  width: float
  text: str = ""
  glyphs: list = None


@dataclass
class Glue:
  """Flexible space: natural width w, max stretch +y, max shrink -z."""

  width: float
  stretch: float
  shrink: float
  text: str = ' '

  def get_width(self, ratio):
    return self.width + ratio * (self.stretch if ratio >= 0 else self.shrink)

Glue.ZERO = Glue(0, 0, 0)
Glue.INF = Glue(0, math.inf, 0)


INF_BAD = 10000
INF_PENALTY = 10000
EJECT_PENALTY = -10000

@dataclass
class Penalty:
  """."""

  value: int
  width: float = 0.0
  text: str = ''

Penalty.NO_BREAK = Penalty(INF_PENALTY)
Penalty.EJECT = Penalty(EJECT_PENALTY)


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


def badness(ratio: float) -> int:
  if math.isnan(ratio) or ratio < -1.0:
    return INF_BAD

  # not using round() because Python3's round-half-to-even
  return int(100 * (abs(ratio) ** 3) + 0.5)


