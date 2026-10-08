"""字帖生成器：在 A4 上排田字格，支持描红 / 临摹 / 混合三种模式。

设计原则（对应产品"边界客观"的定位）：
  字帖的字由国标字表定义，田字格规格由书写规范定义 —— 没有主观配置空间。
  本模块只负责"把字排进田字格"，出题/选字逻辑独立，便于单测与复用。

复用：fonts.py 的字体探测（保持不动，缺字校验同样适用）。
布局参数与 pdf_render.py 的页眉/页脚风格保持一致，但渲染逻辑独立，
因为田字格是"格 + 字"两层结构，和口算的"题目网格"完全不同。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as rl_canvas

from fonts import get_cjk_font

PAGE_W, PAGE_H = A4
MARGIN_X = 40
MARGIN_TOP = 56
MARGIN_BOTTOM = 48

# 田字格规格：边长约 22mm，一行 8 格，间距 4mm
CELL = 62          # 格子边长（约 22mm × 2.83 pt/mm ≈ 62pt）
CELL_GAP = 11      # 格间水平间距（约 4mm）
ROW_GAP = 14       # 行间垂直间距
COLS = 8           # 一行 8 格，A4 横向排满
ROWS = 10          # 默认一页约 10 行（实际由 _layout 精确算）

# 模式
MIAOHONG = "miaohong"   # 描红：第一格灰范字，后几格空白
LINMO = "linmo"         # 临摹：第一格黑范字，后面全空白
HUNHE = "hunhe"         # 混合：第一行描红，第二行临摹，交替
MODES = (MIAOHONG, LINMO, HUNHE)

# 三种模式里"范字格"占每行第几格（0 基）
# 描红：第 0 格印灰色范字，第 1~7 格空白供描写
# 临摹：第 0 格印黑色范字，第 1~7 格空白供临写
# 混合：偶数行（0,2,4…）描红规则，奇数行（1,3,5…）临摹规则


@dataclass
class ZitieOptions:
    """字帖版式与页眉信息。"""

    title: str = "字帖"
    name_line: bool = True
    mode: str = MIAOHONG
    cols: int = COLS
    rows: int = ROWS
    font_size: int = 44          # 范字字号（约占格内 70%）
    pinyin: bool = False         # 是否在字上方印拼音
    pinyin_size: int = 10        # 拼音字号
    # 描红模式下每行重复几个范字：1 = 只第一格，2 = 前两格，…
    # 默认 1，即"看一眼写到底"；多数字帖用 1
    guide_cells_per_row: int = 1


class CharSpec:
    """一个待排版的字 + 可选拼音。"""

    __slots__ = ("char", "pinyin")

    def __init__(self, char: str, pinyin: str = ""):
        if len(char) != 1:
            raise ValueError(f"字帖每个字必须是单字符，收到：{char!r}")
        self.char = char
        self.pinyin = pinyin


def _layout(opt: ZitieOptions) -> tuple[int, float]:
    """返回 (每页行数, 起始 y)。"""
    header_h = 16
    if opt.name_line:
        header_h += 22

    grid_top = PAGE_H - MARGIN_TOP - 30 - header_h
    row_step = CELL + ROW_GAP + (opt.pinyin_size + 4 if opt.pinyin else 0)
    grid_bottom = MARGIN_BOTTOM + 20
    rows = max(1, int((grid_top - grid_bottom) // row_step))
    return rows, grid_top


def _draw_header(c: rl_canvas.Canvas, font: str, opt: ZitieOptions) -> float:
    """画页眉，返回分隔线 y 坐标。"""
    y = PAGE_H - MARGIN_TOP
    c.setFont(font, 20)
    c.drawCentredString(PAGE_W / 2, y, opt.title)
    y -= 30

    if opt.name_line:
        c.setFont(font, 10.5)
        c.drawString(
            MARGIN_X, y,
            "姓名：____________　　日期：____________　　"
            "　　　　　　　　　　得分：__________",
        )
        y -= 22

    c.setLineWidth(0.7)
    c.line(MARGIN_X, y - 4, PAGE_W - MARGIN_X, y - 4)
    return y


def _draw_cell_box(c: rl_canvas.Canvas, x: float, y: float, size: float) -> None:
    """画一个田字格：外框实线 + 内部虚线十字。"""
    # 外框
    c.setLineWidth(0.5)
    c.rect(x, y, size, size, stroke=1, fill=0)
    # 内部虚线十字
    c.setDash(1, 2)
    c.setLineWidth(0.3)
    # 竖虚线
    c.line(x + size / 2, y, x + size / 2, y + size)
    # 横虚线
    c.line(x, y + size / 2, x + size, y + size / 2)
    c.setDash()  # 复位


def _draw_char(
    c: rl_canvas.Canvas,
    font: str,
    ch: str,
    x: float,
    y: float,
    size: float,
    font_size: int,
    *,
    gray: bool = False,
) -> None:
    """在格子中心画一个字。gray=True 用浅灰色（描红范字）。"""
    if gray:
        c.setFillColorRGB(0.75, 0.75, 0.75)
    else:
        c.setFillColorRGB(0, 0, 0)
    c.setFont(font, font_size)
    # 居中：drawCentredString 的 x 是中心，y 是基线
    # 基线大约在格子中心偏下 font_size*0.35 处，使视觉居中
    c.drawCentredString(x + size / 2, y + size / 2 - font_size * 0.35, ch)
    c.setFillColorRGB(0, 0, 0)


def _draw_pinyin(
    c: rl_canvas.Canvas,
    font: str,
    py: str,
    x: float,
    y_top: float,
    size: int,
) -> None:
    """在格子顶部上方画拼音。y_top 是格子顶部 y。"""
    if not py:
        return
    c.setFont(font, size)
    c.setFillColorRGB(0.2, 0.2, 0.2)
    c.drawCentredString(x, y_top + 3, py)
    c.setFillColorRGB(0, 0, 0)


def _draw_row(
    c: rl_canvas.Canvas,
    font: str,
    char: CharSpec,
    x0: float,
    y: float,
    opt: ZitieOptions,
    row_index: int,
) -> None:
    """画一行田字格 + 该字。row_index 用于混合模式判断。"""
    col_w = CELL + CELL_GAP
    # 决定本行的"范字印法"
    if opt.mode == MIAOHONG:
        guide_gray, guide_count = True, opt.guide_cells_per_row
    elif opt.mode == LINMO:
        guide_gray, guide_count = False, 1
    else:  # HUNHE
        if row_index % 2 == 0:
            guide_gray, guide_count = True, opt.guide_cells_per_row
        else:
            guide_gray, guide_count = False, 1

    for col in range(opt.cols):
        cx = x0 + col * col_w
        _draw_cell_box(c, cx, y, CELL)
        if col < guide_count:
            _draw_char(
                c, font, char.char, cx, y, CELL, opt.font_size, gray=guide_gray
            )
        if opt.pinyin:
            _draw_pinyin(c, font, char.pinyin, cx + CELL / 2, y + CELL, opt.pinyin_size)


def render_zitie(
    chars: list[CharSpec],
    out_path: str | Path,
    options: ZitieOptions | None = None,
) -> Path:
    """把字列表渲染成字帖 PDF，返回输出路径。

    每个字占若干行（默认每字 1 行），按行铺满整页后自动分页。
    """
    opt = options or ZitieOptions()
    if opt.mode not in MODES:
        raise ValueError(f"未知字帖模式：{opt.mode}，可选：{MODES}")
    if opt.cols < 1:
        raise ValueError("cols 必须 >= 1")
    if opt.rows < 1:
        raise ValueError("rows 必须 >= 1")
    if not chars:
        raise ValueError("字列表不能为空")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    font = get_cjk_font()
    c = rl_canvas.Canvas(str(out_path), pagesize=A4)
    c.setTitle(opt.title)

    rows_per_page, grid_top0 = _layout(opt)
    rows_per_page = min(rows_per_page, opt.rows) if opt.rows else rows_per_page
    col_w = CELL + CELL_GAP
    grid_w = opt.cols * col_w - CELL_GAP
    x0 = (PAGE_W - grid_w) / 2

    # 拼音占位时行高要加
    row_extra = (opt.pinyin_size + 4) if opt.pinyin else 0
    row_step = CELL + ROW_GAP + row_extra

    # 每个字占几行（默认 1）
    rows_per_char = 1

    # 把字按行展开：每个字重复 rows_per_char 行
    lines: list[tuple[int, CharSpec]] = []  # (全局行号, char)
    g_row = 0
    for ch in chars:
        for _ in range(rows_per_char):
            lines.append((g_row, ch))
            g_row += 1

    pages = [
        lines[i : i + rows_per_page]
        for i in range(0, len(lines), rows_per_page)
    ] or [[]]
    total_pages = len(pages)

    for page_idx, page_lines in enumerate(pages, start=1):
        _draw_header(c, font, opt)
        for r, (abs_row, char) in enumerate(page_lines):
            y = grid_top0 - CELL - r * row_step
            if y < MARGIN_BOTTOM:
                break
            # 混合模式按"本页内行号"还是"全局行号"？用全局，跨页保持交替规律
            _draw_row(c, font, char, x0, y, opt, abs_row)

        c.setFont(font, 9)
        footer = ""
        if total_pages > 1:
            footer = f"第 {page_idx} / {total_pages} 页"
        if footer:
            c.drawCentredString(PAGE_W / 2, MARGIN_BOTTOM - 22, footer)
        c.showPage()

    c.save()
    return out_path


def load_chars_from_file(path: str | Path) -> list[str]:
    """从文本文件读字表，一行一个字或连续字符，忽略空行与注释。

    支持两种格式：
      - 每行一个字（规范）
      - 每行多个字连续（兼容）
    自动去重、去非汉字字符。
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"字表文件不存在：{p}")
    text = p.read_text(encoding="utf-8")
    seen: list[str] = []
    sset: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        for ch in line:
            # 只保留 CJK 汉字（基本区 + 扩展A），过滤标点空格
            cp = ord(ch)
            if 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF:
                if ch not in sset:
                    sset.add(ch)
                    seen.append(ch)
    return seen


__all__ = [
    "CharSpec",
    "ZitieOptions",
    "MIAOHONG",
    "LINMO",
    "HUNHE",
    "MODES",
    "render_zitie",
    "load_chars_from_file",
]
