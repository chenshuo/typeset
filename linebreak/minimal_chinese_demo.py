#!/usr/bin/env python3
"""PyQt6 demo: Chinese punctuation strategies with the minimal Knuth-Plass algorithm.

Glyphs are shaped by HarfBuzz (util.get_box) and drawn directly by Qt via
QRawFont/QGlyphRun using glyph indices.

    python3 minimal_chinese_demo.py
"""

import math
import os
import sys
from dataclasses import dataclass
from typing import List, Tuple

import uharfbuzz as hb
from uniseg.linebreak import line_break_units

from PyQt6.QtCore import Qt, QPointF, QRectF, QSize
from PyQt6.QtGui import (QColor, QFont, QFontDatabase, QGlyphRun, QPainter,
                         QPen, QRawFont)
from PyQt6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox,
                             QDoubleSpinBox, QFormLayout, QGroupBox,
                             QHBoxLayout, QLabel, QMainWindow, QPlainTextEdit,
                             QRadioButton, QScrollArea, QSpinBox, QSplitter,
                             QTableWidget, QTableWidgetItem, QVBoxLayout,
                             QWidget)

from common import Box, Glue, get_ratio, badness
from util import get_box, FREETYPE_SCALE
import minimal

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = '/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc'
FONT_INDEX = 2  # 0 JP, 1 KR, 2 SC, 3 TC, 4 HK
QT_FAMILY = 'Noto Serif CJK SC'

TEXTS = {
    '出师表': "臣本布衣，躬耕于南阳，苟全性命于乱世，不求闻达于诸侯。先帝不以臣卑鄙，猥自枉屈，三顾臣于草庐之中，谘臣以当世之事，由是感激，遂许先帝以驱驰。后值倾覆，受任于败军之际，奉命于危难之间，尔来二十有一年矣。",
    '西游记': '好猴王，即拔一把毫毛，入口嚼烂，喷将出去，念动咒语，叫声：“变！”变做千百个小猴，都乱搬乱抢，有力的拿五七件，力小的拿三二件，尽数搬个罄净。径踏云头，弄个摄法，唤转狂风，带领小猴，俱回本处。',
    '论语·学而': '子曰：“学而时习之，不亦说乎？有朋自远方来，不亦乐乎？人不知而不愠，不亦君子乎？”',
    '论语·述而': '子曰：“三人行，必有我师焉。择其善者而从之，其不善者而改之。”',
    '论语·里仁': '子曰：“参乎，吾道一以贯之。”曾子曰：“唯。”子出，门人问曰：“何谓也？”曾子曰：“夫子之道，忠恕而已矣。”',
    '晁错论': '天下之患，最不可为者，名为治平无事，而其实有不测之忧。坐观其变，而不为之所，则恐至於不可救；起而强为之，则天下狃於治平之安而不吾信。惟仁人君子豪杰之士，为能出身为天下犯大难，以求成大功；此固非勉强期月之间，而苟以求名之所能也。'
}

STOP_PUNCTS = set('、：，；。？！')
OPEN_PUNCTS = set('‘“（《〈')
CLOSE_PUNCTS = set('’”）》〉')

# Punctuation strategies
P_NONE, P_HALF, P_HANG, P_CONTEXT = range(4)
STRATEGY_NAMES = [
    '不处理：标点始终占一个字',
    '行末半宽：标点拆成半宽 box + glue(½em)',
    '标点悬挂：box 不含标点宽度 + glue(1em)',
    '上下文：box 内 chws，box 尾标点半宽，glue 看下一 box 开头',
]
STRATEGY_TIPS = [
    '汉字连同其后标点放入同一 box，宽度一律为整字，只有汉字间的 glue 可伸缩。',
    '“衣，”box 只含逗号左半边 (1.5em)，右半边空白交给 glue(w=½em)。'
    '行末断点处 glue 被丢弃，逗号只占半个字（国标 5.1.10）。',
    'box 仍宽 1em，逗号墨迹画在 box 右边界之外，glue 自然宽度 1em；'
    '行末 glue 丢弃，逗号挂到版心之外。',
    'box 内部打开 OpenType chws 压缩连用标点；box 末尾标点压成半宽，'
    '下一 box 若以前引号等左空白标点开头则只用普通 glue，否则用标点 glue。',
]


# ---------------------------------------------------------------------------
# Item construction
# ---------------------------------------------------------------------------

@dataclass
class Params:
    text: str
    size: float
    strategy: int
    indent: int
    cjk_stretch: float   # in em
    cjk_shrink: float    # in em
    punct_stretch: float  # in em
    punct_shrink: float   # in em
    no_runt: bool


_HB_CACHE = {}


def get_hb_font(size):
    key = size
    if key not in _HB_CACHE:
        blob = hb.Blob.from_file_path(FONT)
        face = hb.Face(blob, FONT_INDEX)
        font = hb.Font(face)
        font.scale = (int(size * FREETYPE_SCALE), int(size * FREETYPE_SCALE))
        _HB_CACHE[key] = font
    return _HB_CACHE[key]


def build_items(p: Params) -> List:
    size = p.size
    hb_font = get_hb_font(size)
    em = lambda x: x * size

    items = []
    if p.indent > 0:
        items.append(Box(em(p.indent), '　' * p.indent))

    cjk_glue = Glue(0, em(p.cjk_stretch), em(p.cjk_shrink), '')
    punct_glue = Glue(em(0.5), em(p.punct_stretch), em(p.punct_shrink), '')
    hang_glue = Glue(em(1.0), em(p.punct_stretch), em(p.punct_shrink), '')

    units = [u for u in line_break_units(p.text) if u.strip()]
    if p.no_runt and len(units) >= 2:
        # Glue the last two units together with WORD JOINER (U+2060).
        units = units[:-2] + [units[-2] + '\u2060' + units[-1]]

    features = {'chws': True} if p.strategy == P_CONTEXT else {}
    for i, seg in enumerate(units):
        box = get_box(seg, hb_font, features)
        last = seg[-1]
        nxt = units[i + 1][0] if i + 1 < len(units) else ''
        glue = cjk_glue
        if p.strategy == P_HALF and last in STOP_PUNCTS:
            box.width -= em(0.5)
            glue = punct_glue
        elif p.strategy == P_HANG and last in STOP_PUNCTS:
            box.width -= em(1.0)
            glue = hang_glue
        elif p.strategy == P_CONTEXT and last in STOP_PUNCTS:
            box.width -= em(0.5)
            glue = cjk_glue if nxt in OPEN_PUNCTS else punct_glue
        items.append(box)
        items.append(glue)
    return items


# ---------------------------------------------------------------------------
# Line breaking
# ---------------------------------------------------------------------------

def greedy(items, line_width) -> List[int]:
    """Puts as many Boxes as possible in each line, as long as r >= -1."""
    breaks = []
    start = 0
    last = None
    width = stretch = shrink = 0
    for i, item in enumerate(items):
        if isinstance(item, Glue) and isinstance(items[i - 1], Box):
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


def make_lines(items, line_width, breaks) -> List[Tuple[float, List]]:
    """Same as minimal.show_results() but silent."""
    lines, line = [], []
    width = stretch = shrink = 0
    bset = set(breaks)
    for i, it in enumerate(items):
        if i in bset:
            lines.append((get_ratio(line_width, width, stretch, shrink), line))
            line, width, stretch, shrink = [], 0, 0, 0
            continue
        line.append(it)
        width += it.width
        if isinstance(it, Glue):
            stretch += it.stretch
            shrink += it.shrink
    if line:
        lines.append((get_ratio(line_width, width, stretch + math.inf, shrink), line))
    return lines


# ---------------------------------------------------------------------------
# Canvas
# ---------------------------------------------------------------------------

class Canvas(QWidget):
    def __init__(self):
        super().__init__()
        self.lines = []
        self.size = 24.0
        self.line_width = 0
        self.zoom = 1.0
        self.show_grid = True
        self.show_boxes = True
        self.show_glue = True
        self.show_ratio = True
        self.raw_font = None
        self.setMinimumSize(200, 100)

    def set_data(self, lines, size, line_width):
        self.lines, self.size, self.line_width = lines, size, line_width
        font = QFont(QT_FAMILY)
        font.setPixelSize(int(round(size)))
        self.raw_font = QRawFont.fromFont(font)
        # Match HarfBuzz scale exactly (pixelSize is int above).
        self.raw_font.setPixelSize(size)
        self.updateGeometry()
        self.update()

    def line_height(self):
        return self.size * 1.6

    def sizeHint(self):
        w = (self.size * 2 + self.line_width + self.size * 5) * self.zoom
        h = (len(self.lines) + 1.5) * self.line_height() * self.zoom
        return self.minimumSize().expandedTo(QSize(int(w), int(h)))

    def paintEvent(self, ev):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.RenderHint.Antialiasing)
        qp.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        qp.fillRect(self.rect(), Qt.GlobalColor.white)
        if not self.lines or self.raw_font is None:
            return
        qp.scale(self.zoom, self.zoom)
        size = self.size
        left = size * 2
        lh = self.line_height()
        top = lh
        n = len(self.lines)

        # Grid: blue lines every em, grey dashed every half em.
        if self.show_grid:
            x0, x1 = left, left + self.line_width
            y0, y1 = top - lh * 0.9, top + (n - 1) * lh + size * 0.4
            pen = QPen(QColor(120, 120, 120, 120), 0.5, Qt.PenStyle.DashLine)
            qp.setPen(pen)
            x = x0 + size / 2
            while x < x1:
                qp.drawLine(QPointF(x, y0), QPointF(x, y1))
                x += size
            qp.setPen(QPen(QColor(60, 90, 220, 140), 0.6))
            k = 0
            while left + k * size <= x1 + 1e-6:
                x = left + k * size
                qp.drawLine(QPointF(x, y0), QPointF(x, y1))
                k += 1
            qp.setPen(QPen(QColor(220, 40, 40), 1.0))
            qp.drawLine(QPointF(x1, y0), QPointF(x1, y1))  # right edge

        label_font = QFont('sans-serif')
        label_font.setPixelSize(max(9, int(size * 0.42)))

        for li, (ratio, line) in enumerate(self.lines):
            baseline = top + li * lh
            x = left
            r = 0.0 if math.isnan(ratio) else ratio
            for it in line:
                if isinstance(it, Box):
                    if self.show_boxes and it.width > 0:
                        qp.setPen(QPen(QColor(40, 160, 70, 160), 0.6))
                        qp.setBrush(Qt.BrushStyle.NoBrush)
                        qp.drawRect(QRectF(x, baseline - size * 0.88, it.width, size * 1.0))
                    if it.glyphs:
                        run = QGlyphRun()
                        run.setRawFont(self.raw_font)
                        run.setGlyphIndexes([int(g) for g, _, _ in it.glyphs])
                        run.setPositions([QPointF(x + gx, baseline - gy) for _, gx, gy in it.glyphs])
                        qp.setPen(Qt.GlobalColor.black)
                        qp.drawGlyphRun(QPointF(0, 0), run)
                    x += it.width
                elif isinstance(it, Glue):
                    w = it.get_width(r)
                    if self.show_glue and (w > 1e-3 or it.width > 0):
                        stretched = w - it.width
                        col = QColor(255, 170, 60, 110) if stretched >= 0 else QColor(170, 100, 255, 110)
                        qp.fillRect(QRectF(x, baseline - size * 0.88, w, size * 1.0), col)
                    x += w
            if self.show_ratio:
                qp.setFont(label_font)
                qp.setPen(QColor(90, 90, 90))
                b = badness(ratio)
                txt = f'r={ratio:+.3f}  b={b}' if not math.isnan(ratio) else 'r=NaN'
                qp.drawText(QPointF(left + self.line_width + size * 0.6, baseline), txt)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('极简版 Knuth-Plass 断行算法 —— 中文标点处理策略演示')
        self._building = True

        # ---- controls ----
        ctl = QWidget()
        form = QVBoxLayout(ctl)

        g = QGroupBox('文本')
        l = QVBoxLayout(g)
        self.text_combo = QComboBox()
        self.text_combo.addItems(list(TEXTS))
        self.text_edit = QPlainTextEdit(TEXTS[self.text_combo.currentText()])
        self.text_edit.setMaximumHeight(90)
        l.addWidget(self.text_combo)
        l.addWidget(self.text_edit)
        form.addWidget(g)

        g = QGroupBox('标点策略')
        l = QVBoxLayout(g)
        self.strategy_group = QButtonGroup(self)
        for i, name in enumerate(STRATEGY_NAMES):
            rb = QRadioButton(name)
            rb.setToolTip(STRATEGY_TIPS[i])
            self.strategy_group.addButton(rb, i)
            l.addWidget(rb)
        self.strategy_group.button(P_NONE).setChecked(True)
        self.tip_label = QLabel(STRATEGY_TIPS[P_NONE])
        self.tip_label.setWordWrap(True)
        self.tip_label.setStyleSheet('color: #555; font-size: 11px;')
        l.addWidget(self.tip_label)
        form.addWidget(g)

        g = QGroupBox('版面')
        fl = QFormLayout(g)
        self.chars_spin = QSpinBox(); self.chars_spin.setRange(4, 60); self.chars_spin.setValue(16)
        self.size_spin = QSpinBox(); self.size_spin.setRange(10, 80); self.size_spin.setValue(24); self.size_spin.setSuffix(' px')
        self.indent_spin = QSpinBox(); self.indent_spin.setRange(0, 4); self.indent_spin.setValue(2)
        self.algo_combo = QComboBox(); self.algo_combo.addItems(['Knuth-Plass (minimal.py)', '贪心 (first fit)'])
        self.rho_spin = QDoubleSpinBox(); self.rho_spin.setRange(0.1, 20); self.rho_spin.setSingleStep(0.1); self.rho_spin.setValue(1.0)
        self.runt_check = QCheckBox('段末禁止单字成行 (U+2060 WJ)')
        fl.addRow('每行字数', self.chars_spin)
        fl.addRow('字号', self.size_spin)
        fl.addRow('段首缩进(字)', self.indent_spin)
        fl.addRow('算法', self.algo_combo)
        fl.addRow('容忍度 ρ', self.rho_spin)
        fl.addRow(self.runt_check)
        form.addWidget(g)

        g = QGroupBox('Glue 参数（单位：em）')
        fl = QFormLayout(g)
        self.cjk_stretch = QDoubleSpinBox(); self.cjk_stretch.setDecimals(4); self.cjk_stretch.setRange(0, 2); self.cjk_stretch.setSingleStep(1/12); self.cjk_stretch.setValue(1/6)
        self.cjk_shrink = QDoubleSpinBox(); self.cjk_shrink.setDecimals(5); self.cjk_shrink.setRange(0, 1); self.cjk_shrink.setSingleStep(0.00001); self.cjk_shrink.setValue(1e-5)
        self.punct_stretch = QDoubleSpinBox(); self.punct_stretch.setDecimals(4); self.punct_stretch.setRange(0, 2); self.punct_stretch.setSingleStep(1/12); self.punct_stretch.setValue(1/3)
        self.punct_shrink = QDoubleSpinBox(); self.punct_shrink.setDecimals(4); self.punct_shrink.setRange(0, 1); self.punct_shrink.setSingleStep(1/12); self.punct_shrink.setValue(1/4)
        fl.addRow('汉字间 y (stretch)', self.cjk_stretch)
        fl.addRow('汉字间 z (shrink)', self.cjk_shrink)
        fl.addRow('标点后 y (stretch)', self.punct_stretch)
        fl.addRow('标点后 z (shrink)', self.punct_shrink)
        form.addWidget(g)

        g = QGroupBox('显示')
        fl = QFormLayout(g)
        self.grid_check = QCheckBox('汉字宽度网格'); self.grid_check.setChecked(True)
        self.box_check = QCheckBox('Box 边框'); self.box_check.setChecked(True)
        self.glue_check = QCheckBox('Glue（橙=拉伸/紫=压缩）'); self.glue_check.setChecked(True)
        self.ratio_check = QCheckBox('每行调整率 r'); self.ratio_check.setChecked(True)
        self.zoom_spin = QDoubleSpinBox(); self.zoom_spin.setRange(0.5, 4); self.zoom_spin.setSingleStep(0.25); self.zoom_spin.setValue(1.0)
        for w in (self.grid_check, self.box_check, self.glue_check, self.ratio_check):
            fl.addRow(w)
        fl.addRow('缩放', self.zoom_spin)
        form.addWidget(g)
        form.addStretch(1)

        ctl_scroll = QScrollArea()
        ctl_scroll.setWidget(ctl)
        ctl_scroll.setWidgetResizable(True)
        ctl_scroll.setMinimumWidth(360)

        # ---- canvas + tables ----
        self.canvas = Canvas()
        canvas_scroll = QScrollArea()
        canvas_scroll.setWidget(self.canvas)
        canvas_scroll.setWidgetResizable(True)

        self.status = QLabel()
        self.status.setStyleSheet('font-weight: bold;')

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['行', 'r', 'badness', 'demerits', '文本'])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self.items_view = QPlainTextEdit()
        self.items_view.setReadOnly(True)
        self.items_view.setFont(QFont('monospace'))

        bottom = QSplitter(Qt.Orientation.Horizontal)
        bottom.addWidget(self.table)
        bottom.addWidget(self.items_view)

        right = QSplitter(Qt.Orientation.Vertical)
        rw = QWidget(); rl = QVBoxLayout(rw); rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.status); rl.addWidget(canvas_scroll)
        right.addWidget(rw)
        right.addWidget(bottom)
        right.setSizes([500, 250])

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(ctl_scroll)
        split.addWidget(right)
        split.setSizes([380, 900])
        self.setCentralWidget(split)
        self.resize(1300, 800)

        # ---- signals ----
        self.text_combo.currentTextChanged.connect(lambda t: self.text_edit.setPlainText(TEXTS[t]))
        self.text_edit.textChanged.connect(self.refresh)
        self.strategy_group.idToggled.connect(self.on_strategy)
        for w in (self.chars_spin, self.size_spin, self.indent_spin, self.rho_spin,
                  self.cjk_stretch, self.cjk_shrink, self.punct_stretch, self.punct_shrink):
            w.valueChanged.connect(self.refresh)
        self.algo_combo.currentIndexChanged.connect(self.refresh)
        self.runt_check.toggled.connect(self.refresh)
        self.grid_check.toggled.connect(self.on_display)
        self.box_check.toggled.connect(self.on_display)
        self.glue_check.toggled.connect(self.on_display)
        self.ratio_check.toggled.connect(self.on_display)
        self.zoom_spin.valueChanged.connect(self.on_display)

        self._building = False
        self.refresh()

    # ------------------------------------------------------------------
    def on_strategy(self, sid, checked):
        if checked:
            self.tip_label.setText(STRATEGY_TIPS[sid])
            self.refresh()

    def on_display(self):
        c = self.canvas
        c.show_grid = self.grid_check.isChecked()
        c.show_boxes = self.box_check.isChecked()
        c.show_glue = self.glue_check.isChecked()
        c.show_ratio = self.ratio_check.isChecked()
        c.zoom = self.zoom_spin.value()
        c.updateGeometry()
        c.update()

    def params(self) -> Params:
        return Params(
            text=self.text_edit.toPlainText().strip(),
            size=float(self.size_spin.value()),
            strategy=self.strategy_group.checkedId(),
            indent=self.indent_spin.value(),
            cjk_stretch=self.cjk_stretch.value(),
            cjk_shrink=self.cjk_shrink.value(),
            punct_stretch=self.punct_stretch.value(),
            punct_shrink=self.punct_shrink.value(),
            no_runt=self.runt_check.isChecked(),
        )

    def refresh(self):
        if self._building:
            return
        p = self.params()
        if not p.text:
            return
        items = build_items(p)
        line_width = p.size * self.chars_spin.value()
        rho = self.rho_spin.value()

        self.items_view.setPlainText('\n'.join(
            f'{i:3d} {fmt_item(it, p.size)}' for i, it in enumerate(items)))

        try:
            if self.algo_combo.currentIndex() == 0:
                breaks = minimal.line_break(items, line_width, rho)
            else:
                breaks = greedy(items, line_width)
        except RuntimeError as ex:
            self.status.setStyleSheet('color: #c00; font-weight: bold;')
            self.status.setText(f'无可行方案：{ex}  （试试增大 ρ）')
            self.canvas.set_data([], p.size, line_width)
            self.table.setRowCount(0)
            return

        lines = make_lines(items, line_width, breaks)
        self.canvas.set_data(lines, p.size, line_width)
        self.on_display()

        total = 0
        self.table.setRowCount(len(lines))
        for i, (ratio, line) in enumerate(lines):
            b = badness(ratio)
            d = (1 + b) ** 2
            total += d
            text = ''.join(x.text for x in line).replace('\u2060', '')
            for col, val in enumerate([str(i + 1), f'{ratio:+.3f}', str(b), str(d), text]):
                cell = QTableWidgetItem(val)
                if col < 4:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(i, col, cell)
        self.table.resizeColumnsToContents()
        self.status.setStyleSheet('font-weight: bold;')
        self.status.setText(
            f'{len(items)} items，{len(lines)} 行，行宽 {line_width:g}px = '
            f'{self.chars_spin.value()} 字 × {p.size:g}px，总 demerits = {total}')


def fmt_item(it, size):
    if isinstance(it, Box):
        return f"Box(width={it.width / size:5.2f}em, '{it.text.replace(chr(0x2060), '')}')"
    return f'Glue(width={it.width / size:.2f}em, stretch={it.stretch / size:.3f}em, shrink={it.shrink / size:.5f}em)'


def main():
    app = QApplication(sys.argv)
    fid = QFontDatabase.addApplicationFont(FONT)
    if fid < 0:
        print(f'Cannot load font {FONT}', file=sys.stderr)
        sys.exit(1)
    minimal.TRACE = False
    w = Main()
    w.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
