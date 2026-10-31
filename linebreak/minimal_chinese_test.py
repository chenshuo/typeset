import pytest
import os

from common import Box, Glue
from util import get_box
from minimal import line_break, show_results
from render_lib import DEFAULT_FONT, FREETYPE_SCALE, render

from functools import partial
from typing import List
import uharfbuzz as hb
from uniseg.linebreak import line_break_units

FONT = '/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc'
    # 0 is JP, 1 is KR, 2 is SC, 3 is TC, 4 is HK
FONT_INDEX = 2

TEXT1 = "臣本布衣，躬耕于南阳，苟全性命于乱世，不求闻达于诸侯。先帝不以臣卑鄙，猥自枉屈，三顾臣于草庐之中，谘臣以当世之事，由是感激，遂许先帝以驱驰。"
TEXT1nb = "臣本布衣，躬耕于南阳，苟全性命于乱世，不求闻达于诸侯。先帝不以臣卑鄙，猥自枉屈，三顾臣于草庐之中，谘臣以当世之事，由是感激，遂许先帝以驱\u2060驰。"

TEXT2 = '好猴王，即拔一把毫毛，入口嚼烂，喷将出去，念动咒语，叫声：“变！”'

TEXT0 = """子曰：“学而时习之，不亦说乎？有朋自远方来，不亦乐乎？人不知而不愠，不亦君子乎？”"""
TEXT3 = """子曰：“三人行，必有我师焉。择其善者而从之，其不善者而改之。”"""

TEXT4 = '子曰：“参乎，吾道一以贯之。”曾子曰：“唯。”子出，门人问曰：“何谓也？”曾子曰：“夫子之道，忠恕而已矣。”'

TRACE = 0
INDENT = 2

PUNCT_NONE = 0
PUNCT_COMPRESS = 1
PUNCT_HANGING = 2
STOP_PUNCTS = set('、：，；。？！')
OPEN_PUNCTS = set('‘“（《〈')
CLOSE_PUNCTS = set('’”）》〉')

def get_items(text, size, punct=PUNCT_NONE, cjk_glue=None):
    # --- HarfBuzz ---
    hb_blob = hb.Blob.from_file_path(FONT)
    hb_face = hb.Face(hb_blob, FONT_INDEX)
    hb_font = hb.Font(hb_face)
    hb_font.scale = (int(size * FREETYPE_SCALE), int(size * FREETYPE_SCALE))

    items = []
    if INDENT > 0:
        items.append(Box(size*INDENT, '　'*INDENT))
    if cjk_glue is None:
        cjk_glue = Glue(0, size/6, 0, '')

    if punct == PUNCT_COMPRESS:
        punct_glue = Glue(size/2, size/3, size/4, '')
        box_width_adj = -size / 2
    elif punct == PUNCT_HANGING:
        punct_glue = Glue(size, size/3, size/4, '')
        box_width_adj = -size

    for seg in line_break_units(text):
        word = seg.rstrip(' ')
        if not word:
            continue
        has_space = len(word) < len(seg)
        box = get_box(seg, hb_font)
        if TRACE >= 2:
            print(box)
        items.append(box)
        if punct and word[-1] in STOP_PUNCTS:
            items[-1].width += box_width_adj
            items.append(punct_glue)
        else:
            items.append(cjk_glue)

    return items


def get_items_chws(text, size, chws=True):
    # --- HarfBuzz ---
    hb_blob = hb.Blob.from_file_path(FONT)
    hb_face = hb.Face(hb_blob, FONT_INDEX)
    hb_font = hb.Font(hb_face)
    hb_font.scale = (int(size * FREETYPE_SCALE), int(size * FREETYPE_SCALE))

    items = []
    if INDENT > 0:
        items.append(Box(size*INDENT, '　'*INDENT))
    
    cjk_glue = Glue(0, size/6, 0, '')

    punct_glue = Glue(size/2, size/3, size/4, '')

    units = list(line_break_units(text))
    for i, seg in enumerate(units):
        word = seg.rstrip(' ')
        if not word:
            continue
        has_space = len(word) < len(seg)
        box = get_box(seg, hb_font, features={'chws': chws})
        if TRACE >= 2:
            print(box)
        items.append(box)
        if word[-1] in (STOP_PUNCTS | CLOSE_PUNCTS):
            items[-1].width -= size/2
            if i+1 < len(units) and units[i+1][0] in OPEN_PUNCTS:
                items.append(cjk_glue)
            else:
                items.append(punct_glue)
        else:
            items.append(cjk_glue)

    return items


def run(size, text_width, text, get_items, output, rho=1):
    items = get_items(text, size)
    line_width = size * text_width

    breaks = line_break(items, line_width, rho)
    lines = show_results(items, line_width, breaks)
    render(FONT, size, lines, line_width, output, font_index=FONT_INDEX)


def greedy(items, line_width) -> List[int]:
  """Puts as many Boxes as possible in each line, as long as r >= -1."""
  breaks = []
  start = 0
  last = None
  width = stretch = shrink = 0
  for i, item in enumerate(items):
    if isinstance(item, Glue) and isinstance(items[i-1], Box):
      if width - shrink > line_width and last is not None:
        breaks.append(last)
        start = last + 1
        last = None
        width = sum(x.width for x in items[start:i])
        stretch = sum(x.stretch for x in items[start:i] if isinstance(x, Glue))
        shrink = sum(x.shrink for x in items[start:i] if isinstance(x, Glue))
      if width - shrink <= line_width:
        last = i
    width += item.width
    if isinstance(item, Glue):
      stretch += item.stretch
      shrink += item.shrink
  return breaks


def run_greedy(size, text_width, text, get_items, output, rho=1):
    items = get_items(text, size)
    line_width = size * text_width

    breaks = greedy(items, line_width)
    lines = show_results(items, line_width, breaks)
    render(FONT, size, lines, line_width, output, font_index=FONT_INDEX)


def test_get_items_minimal1():
    run(12, 18, TEXT1, get_items, 'minimal_18.pdf')
    run(12, 12, TEXT1, get_items, 'minimal_12.pdf')
    run(12, 18, TEXT1nb, get_items, 'minimal_18nb.pdf')
    run(12, 12, TEXT1nb, get_items, 'minimal_12nb.pdf')


def test_get_items_minimal2(monkeypatch):
    monkeypatch.setitem(globals(), 'INDENT', 0)
    items = get_items(TEXT2, 12)
    for i, it in enumerate(items):
        print('%2d' % i, it)

    width = 16
    run(12, width, TEXT2, get_items, 'minimal_16dp.pdf', rho=2)
    run_greedy(12, width, TEXT2, get_items, 'minimal_16greedy.pdf', rho=2)

    width = 15.5
    get_items_func = partial(get_items, punct=PUNCT_COMPRESS)
    run(12, width, TEXT2, get_items_func, 'minimal_16dpc.pdf', rho=2)
    run_greedy(12, width, TEXT2, get_items_func, 'minimal_16greedyc.pdf', rho=2)


def test_get_items_minimal3():
    items = get_items(TEXT1, 12)
    for i, it in enumerate(items[:13]):
        print('%2d' % i, it)

    get_items_func = partial(get_items, punct=PUNCT_COMPRESS)
    run(12, 16, TEXT1, get_items_func, 'minimal_16compress.pdf')

    items = get_items_func(TEXT1, 12)
    for i, it in enumerate(items[:13]):
        print('%2d' % i, it)


def test_get_items_minimal4():
    # punct compress only
    get_items_func = partial(get_items, punct=PUNCT_COMPRESS, cjk_glue=Glue(0,0.3,0,''))
    items = get_items_func(TEXT1, 12)
    for i, it in enumerate(items[:13]):
        print('%2d' % i, it)
    run(12, 18, TEXT1, get_items_func, 'minimal_18compress.pdf')


def test_get_items_minimal5():
    get_items_func = partial(get_items, punct=PUNCT_HANGING)
    items = get_items_func(TEXT1, 12)
    for i, it in enumerate(items[:13]):
        print('%2d' % i, it)
    for w in (10, 18):
        run(12, w, TEXT1, get_items_func, 'minimal_%dhanging.pdf' % w)


def test_get_items_minimal6(monkeypatch):
    chws_font = 'WenYuanSerifSC-Regular.otf'
    if not os.path.exists(chws_font):
        pytest.skip(f'{chws_font} not exists.')
    monkeypatch.setitem(globals(), 'FONT', chws_font)
    monkeypatch.setitem(globals(), 'FONT_INDEX', 0)
    items = get_items_chws(TEXT4, 12)
    for i, it in enumerate(items[:30]):
        print('%2d' % i, it)

    run(12, 10, TEXT4[:23], get_items_chws, 'minimal_10chws.pdf')
    run(12, 16, TEXT4, get_items_chws, 'minimal_16chws.pdf')


def unused():
    for w in range(10, 21):
        try:
            run(24, w, TEXT4, get_items_chws, 'minimal_%dchws.png' % w, rho=2)
        except Exception as ex:
            print(ex)


if __name__ == '__main__':
    pytest.main()
