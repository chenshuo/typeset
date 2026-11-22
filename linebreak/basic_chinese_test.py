import pytest
import logging

from common import Box, Glue, Penalty
from util import get_box
from basic import line_break, show_results
from render_lib import DEFAULT_FONT, FREETYPE_SCALE, render
from minimal_chinese_test import FONT, FONT_INDEX, TEXT1, TEXT2, TEXT3, TEXT4, PUNCT_NONE, PUNCT_COMPRESS

from functools import partial
from typing import List
import uharfbuzz as hb
from uniseg.linebreak import line_break_units

logger = logging.getLogger(__name__)

# 0 is JP, 1 is KR, 2 is SC, 3 is TC, 4 is HK
FONT_INDEX_TC = 3

TEXT5 = """子曰：“学而时习之，不亦说乎？有朋自远方来，不亦乐乎？人不知而不愠，不亦君子乎？”"""
TEXT6 = """郦道元《水经注》记载：“沼西际山枕水，有唐叔虞祠。”"""
TEXT7 = """我这时很兴奋，但不知道怎么说才好，只是说：“阿！闰土哥，——你来了？……”"""
PUNCT_CONTEXT = 3


def get_hb_font(font, size, font_index=0):
    hb_blob = hb.Blob.from_file_path(font)
    hb_face = hb.Face(hb_blob, font_index)
    hb_font = hb.Font(hb_face)
    hb_font.scale = (int(size * FREETYPE_SCALE), int(size * FREETYPE_SCALE))
    return hb_font


def test_basic0():
    logger.info('|'.join(line_break_units('今天气温 23℃。')))

    font = '/usr/share/fonts/opentype/linux-libertine/LinLibertine_R.otf'
    size = 24
    hb_font = get_hb_font(font, size)

    box = get_box("different  difficulty", hb_font)
    box1 = get_box("different", hb_font)
    print(box1)
    box2 = get_box("difficulty", hb_font)
    space = get_box("  ", hb_font)
    boxes2 = [get_box(frag, hb_font) for frag in ('dif', 'fer', 'ent', '  ', 'dif', 'fi', 'cul', 'ty')]
    width2 = sum(b.width for b in boxes2[:3])
    print(width2)

    lines = [(0.0, (box1, Box(space.width-box1.width+width2), box2,)),
             (0.0, boxes2)]
    render(font, size, lines, box.width, 'hyphen1.pdf')


WORD_JOINER = '\u2060'
STOP_PUNCTS = set('、：，；。？！')
OPEN_PUNCTS = set('‘“（《〈')
CLOSE_PUNCTS = set('’”）》〉')


class Layout:
  def __init__(self, font, size, punct=PUNCT_NONE, indent=2, runt_penalty=0, font_index=FONT_INDEX):
    self.size = size
    self.indent = indent
    self.punct = punct
    self.runt_penalty = runt_penalty
    self.hb_font = get_hb_font(font, size, font_index)


  def get_items(self, text):
    items = []
    if self.indent > 0:
        items.append(Box(self.size*self.indent, '　'*self.indent))

    cjk_glue = Glue(0, self.size/6, 0, '')
    punct_glue = Glue(self.size/2, self.size/3, self.size/4, '')

    def get_boxes_plain(word):
      for i, ch in enumerate(word):
          box = get_box(ch, self.hb_font)
          items.append(box)
          if i < len(word) - 1:
            items.append(Penalty.NO_BREAK)
          items.append(cjk_glue)

    def get_boxes_compress(word):
      for i, ch in enumerate(word):
          box = get_box(ch, self.hb_font, features={'halt': True})
          items.append(box)
          if i < len(word) - 1:
            items.append(Penalty.NO_BREAK)
            items.append(cjk_glue)
          else:  # last character
            if ch in (STOP_PUNCTS | CLOSE_PUNCTS):
              items.append(punct_glue)
            else:
              items.append(cjk_glue)

    def get_boxes_context(word):
      if word[0] in OPEN_PUNCTS:
        # ensure half-width glue before this box
        if items and isinstance(items[-1], Glue):
          items[-1] = punct_glue

      get_boxes_compress(word)


    units = list(line_break_units(text))
    for i, seg in enumerate(units):
        word = seg.rstrip(' ')
        if not word:
            continue
        has_space = len(word) < len(seg)
        # word = list(filter(lambda x: x != WORD_JOINER, word))
        if self.punct == PUNCT_NONE:
          get_boxes_plain(word)
        elif self.punct == PUNCT_COMPRESS:
          get_boxes_compress(word)
        elif self.punct == PUNCT_CONTEXT:
          get_boxes_context(word)

        if self.runt_penalty > 0 and i == len(units) - 2:  # second to last one
          assert isinstance(items[-1], Glue)
          g = items[-1]
          items[-1] = Penalty(self.runt_penalty)
          items.append(g)

    assert isinstance(items[-1], Glue)
    items.pop()
    items.append(Penalty.NO_BREAK)
    items.append(Glue.INF)
    items.append(Penalty.EJECT)
    return items


def run(size, text_width, text, output, rho=1, layout=None, trace=0):
  if not layout:
    layout = Layout(FONT, size, font_index=FONT_INDEX)
  items = layout.get_items(text)

  if trace:
    for i, it in enumerate(items):
      print('%3d' % i, it)

  line_width = layout.size * text_width
  breaks = line_break(items, line_width, rho)
  lines = show_results(items, line_width, breaks)
  render(FONT, layout.size, lines, line_width, output)


def test_basic1():
  run(12, 12, TEXT1, 'basic_12.pdf')
  run(12, 18, TEXT1, 'basic_18.pdf')
  l = Layout(FONT, 12, runt_penalty=50)
  run(12, 12, TEXT1, 'basic_12runt.pdf', layout=l, trace=0)
  l = Layout(FONT, 12, runt_penalty=50)
  run(12, 18, TEXT1, 'basic_18runt.pdf', layout=l, trace=0)


def test_basic2():
  text = '叫声：“变！”化'
  l = Layout(FONT, 16, indent=0)
  run(16, len(text), text, 'basic_7.pdf', layout=l)
  l = Layout(FONT, 16, punct=PUNCT_COMPRESS, indent=0)
  run(16, len(text), text, 'basic_7compress.pdf', layout=l)

  text_width = 15
  l = Layout(FONT, 12, indent=0)
  run(12, text_width, TEXT2, 'basic_15.pdf', layout=l)

  l = Layout(FONT, 12, punct=PUNCT_COMPRESS, indent=0)
  run(12, text_width, TEXT2, 'basic_15compress.pdf', layout=l, trace=0)


def test_basic3():
  l = Layout(FONT, 12)
  # run(12, 15, TEXT4, 'basic_15.pdf', layout=l, rho=2)
  run(12, 17, TEXT4, 'basic_17.pdf', layout=l)

  l = Layout(FONT, 12, punct=PUNCT_COMPRESS, runt_penalty=50)
  # run(12, 15, TEXT4, 'basic_15compress.pdf', layout=l, trace=0)
  run(12, 17, TEXT4, 'basic_17compress.pdf', layout=l, trace=0)


def test_basic4():
  # shrinking: punct glue (6,4,3) lets one line squeeze in half a character
  l = Layout(FONT, 12)
  run(12, 14, TEXT4, 'basic_14.pdf', layout=l)

  l = Layout(FONT, 12, punct=PUNCT_COMPRESS)
  run(12, 14, TEXT4, 'basic_14compress.pdf', layout=l)


def test_basic5():
  l = Layout(FONT, 12, indent=0, font_index=FONT_INDEX_TC)
  text = '大江東去，浪淘盡、千古風流人物。 ……亂石穿空，驚濤拍岸，捲起千堆雪。江山如畫，一時多少豪傑！'
  run(12, 16, text, 'basic_16tw.pdf', layout=l)

  l = Layout(FONT, 12, indent=2, font_index=FONT_INDEX_TC)
  text = '子曰：「參乎！吾道一以貫之。」曾子曰：「唯。」子出，門人問曰：「何謂也？」曾子曰：「夫子之道，忠恕而已矣。」'
  run(12, 17, text, 'basic_17tw.pdf', layout=l)


def test_basic6():
  l = Layout(FONT, 12, indent=0, punct=PUNCT_NONE)
  run(12, 11, TEXT6, 'basic_11.pdf', layout=l)

  l = Layout(FONT, 12, indent=0, punct=PUNCT_COMPRESS)
  run(12, 11, TEXT6, 'basic_11compress.pdf', layout=l)

  l = Layout(FONT, 12, indent=0, punct=PUNCT_CONTEXT)
  run(12, 11, TEXT6, 'basic_11ctx.pdf', layout=l)

  text = '《论语》有云：“学而时习之，不亦说乎？”'
  run(12, 13, text, 'basic_13ctx.pdf', layout=l)

  l = Layout(FONT, 12, indent=2, punct=PUNCT_CONTEXT)
  run(12, 13, text, 'basic_13ctx2.pdf', layout=l)

def test_basic7():
  print('|'.join(line_break_units(TEXT7)))
  l = Layout(FONT, 12, indent=2, punct=PUNCT_CONTEXT)
  run(12, 12, TEXT7, 'basic_lx.pdf', layout=l, trace=1)
