"""Sample paragraph for testing Knuth-Plass line breaking algorithm.

Font metrics from Knuth & Plass 1981 paper, reprinted in _Digital Typography_,
CSLI Lecture Notes 78, 1999.
"""

import math
from common import Box, Glue

SAMPLE_TEXT = """In olden times when wishing still helped one, there lived a king
 whose daughters were all beautiful; and the youngest was so beautiful
 that the sun itself, which has seen so much, was astonished whenever it
 shone in her face. Close by the king's castle lay a great dark forest,
 and under an old lime-tree in the forest was a well, and when the day
 was very warm, the king's child went out into the forest and sat down
 by the side of the cool fountain; and when she was bored she took a
 golden ball, and threw it up on high and caught it; and this ball was
 her favorite plaything."""


def get_sample_paragraph():

  # Sample font metrics from Knuth & Plass 1981 paper.
  letter_widths = {'C': 13, 'I': 6, '-': 6}
  lower = [9,10,8,10,8,6,9,10,5,6,10,5,15,10,9,10,10,7,7,7,10,9,13,10,10,8]
  for p in ",;.'":
    letter_widths[p] = 5
  for i in range(26):
    letter_widths[chr(ord('a') + i)] = lower[i]

  glue_types = {
    ' ': Glue(6, 3, 2),
    ',': Glue(6, 4, 2),
    ';': Glue(6, 4, 1),
    '.': Glue(8, 6, 1),
  }

  items = [Box(18)]  # indent of first line by 1 em

  width = 0
  word = ""

  for ch in SAMPLE_TEXT:
    if ch in letter_widths:
      width += letter_widths[ch]
      word += ch

    if ch in glue_types and width > 0:
      # print(f'{width:2} {word:10}', glue_types[ch])
      items.append(Box(width, word))
      items.append(glue_types[ch])
      width = 0
      word = ""
      # if ch != ' ': print()

  return items
