"""A4 口算练习卷 PDF 渲染。

排版目标：一张 A4 打印出来直接给孩子做，留足书写空间。
布局：页眉（标题+信息栏）→ 题目网格（默认 4 列）→ 页脚（页码）
参考答案（可选）单独成页，附在全部题目页之后，不覆盖题目。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as rl_canvas

from core import Problem
from fonts import get_cjk_font

PAGE_W, PAGE_H = A4
MARGIN_X = 56
MARGIN_TOP = 56
MARGIN_BOTTOM = 56


@dataclass
class SheetOptions:
    """一张练习卷的版式与页眉信息。"""

    title: str = "口算练习"
    subtitle: str = ""
    name_line: bool = True
    show_answers: bool = False
    columns: int = 4
    blank: str = ""
    footer_note: str = ""
    font_size: int = 15
    row_gap: int = 46
    answer_columns: int = 6
    answer_row_gap: int = 24


def _chunk(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _layout(options: SheetOptions) -> tuple[int, int, float]:
    """计算 (每页行数, 每页题数, 列宽)。"""
    header_h = 16
    if options.subtitle:
        header_h += 20
    if options.name_line:
        header_h += 22

    grid_top = PAGE_H - MARGIN_TOP - 30 - header_h
    grid_bottom = MARGIN_BOTTOM + 20
    rows_per_page = max(1, int((grid_top - grid_bottom) // options.row_gap))
    per_page = rows_per_page * options.columns
    col_width = (PAGE_W - 2 * MARGIN_X) / options.columns
    return rows_per_page, per_page, col_width


def _draw_header(c: rl_canvas.Canvas, font: str, opt: SheetOptions) -> float:
    """画页眉，返回分隔线 y 坐标。"""
    y = PAGE_H - MARGIN_TOP
    c.setFont(font, 20)
    c.drawCentredString(PAGE_W / 2, y, opt.title)
    y -= 30

    if opt.subtitle:
        c.setFont(font, 10.5)
        c.drawCentredString(PAGE_W / 2, y, opt.subtitle)
        y -= 20

    if opt.name_line:
        c.setFont(font, 10.5)
        c.drawString(
            MARGIN_X, y,
            "姓名：____________　　日期：____________　　"
            "用时：______分______秒　　得分：__________",
        )
        y -= 22

    c.setLineWidth(0.7)
    c.line(MARGIN_X, y - 4, PAGE_W - MARGIN_X, y - 4)
    return y


def _draw_answers(
    c: rl_canvas.Canvas, font: str, problems: list[Problem], opt: SheetOptions
) -> None:
    """在独立页面上排参考答案。调用前 canvas 应处于新页起始状态。"""
    if not problems:
        return

    col_w = (PAGE_W - 2 * MARGIN_X) / opt.answer_columns
    rows_per_page = max(
        1, int((PAGE_H - MARGIN_TOP - MARGIN_BOTTOM - 40) // opt.answer_row_gap)
    )
    per_page = rows_per_page * opt.answer_columns
    pages = _chunk(list(enumerate(problems, start=1)), per_page)
    total = len(pages)

    for page_idx, items in enumerate(pages, start=1):
        c.setFont(font, 15)
        c.drawCentredString(PAGE_W / 2, PAGE_H - MARGIN_TOP, "参考答案")
        c.setLineWidth(0.7)
        c.line(MARGIN_X, PAGE_H - MARGIN_TOP - 12, PAGE_W - MARGIN_X, PAGE_H - MARGIN_TOP - 12)

        c.setFont(font, 10.5)
        top = PAGE_H - MARGIN_TOP - 40
        for i, (num, p) in enumerate(items):
            r, col = divmod(i, opt.answer_columns)
            c.drawString(
                MARGIN_X + col * col_w,
                top - r * opt.answer_row_gap,
                f"{num}. {p.answer}",
            )

        if total > 1:
            c.setFont(font, 9)
            c.drawCentredString(
                PAGE_W / 2, MARGIN_BOTTOM - 22, f"参考答案 第 {page_idx} / {total} 页"
            )
        c.showPage()


def render_sheet(
    problems: list[Problem],
    out_path: str | Path,
    options: SheetOptions | None = None,
) -> Path:
    """把题目列表渲染成 PDF，返回输出路径。"""
    opt = options or SheetOptions()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if opt.columns < 1:
        raise ValueError("columns 必须 >= 1")

    font = get_cjk_font()
    c = rl_canvas.Canvas(str(out_path), pagesize=A4)
    c.setTitle(opt.title)

    rows_per_page, per_page, col_width = _layout(opt)
    pages = _chunk(problems, per_page) or [[]]
    total_pages = len(pages)

    # ---------- 题目页 ----------
    for page_idx, page_items in enumerate(pages, start=1):
        _draw_header(c, font, opt)

        c.setFont(font, opt.font_size)
        grid_top = PAGE_H - MARGIN_TOP - 30 - (
            16 + (20 if opt.subtitle else 0) + (22 if opt.name_line else 0)
        )
        for row in range(rows_per_page):
            row_y = grid_top - row * opt.row_gap
            if row_y < MARGIN_BOTTOM + 20:
                break
            for col in range(opt.columns):
                idx = row * opt.columns + col
                if idx >= len(page_items):
                    break
                num = (page_idx - 1) * per_page + idx + 1
                c.drawString(
                    MARGIN_X + col * col_width, row_y,
                    f"{num}. {page_items[idx].text(opt.blank)}",
                )

        c.setFont(font, 9)
        footer = opt.footer_note
        if total_pages > 1:
            footer = (footer + "　　" if footer else "") + f"第 {page_idx} / {total_pages} 页"
        if footer:
            c.drawCentredString(PAGE_W / 2, MARGIN_BOTTOM - 22, footer)

        c.showPage()

    # ---------- 答案页（独立，附在最后） ----------
    if opt.show_answers and problems:
        _draw_answers(c, font, problems, opt)

    c.save()
    return out_path


def render_answer_book(
    sheets: list[list[Problem]],
    out_path: str | Path,
    *,
    title: str = "参考答案册",
    per_sheet_label: str = "",
    columns: int = 6,
) -> Path:
    """把多份卷子的答案汇总成一本答案册（供家长/老师批改用）。

    sheets 是"每份卷子的题目列表"的列表，页码按份连续编号。
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    font = get_cjk_font()
    c = rl_canvas.Canvas(str(out_path), pagesize=A4)
    c.setTitle(title)

    row_gap = 24
    col_w = (PAGE_W - 2 * MARGIN_X) / columns
    rows_per_page = max(
        1, int((PAGE_H - MARGIN_TOP - MARGIN_BOTTOM - 46) // row_gap)
    )

    # 先把所有行摊平：(份号, 该份内序号, 题目)
    rows: list[tuple[int, int, Problem]] = []
    for sheet_idx, problems in enumerate(sheets, start=1):
        for num, p in enumerate(problems, start=1):
            rows.append((sheet_idx, num, p))

    if not rows:
        c.setFont(font, 15)
        c.drawCentredString(PAGE_W / 2, PAGE_H - MARGIN_TOP, title)
        c.showPage()
        c.save()
        return out_path

    pages = _chunk(rows, rows_per_page * columns)
    total_pages = len(pages)

    for page_idx, page_rows in enumerate(pages, start=1):
        c.setFont(font, 16)
        c.drawCentredString(PAGE_W / 2, PAGE_H - MARGIN_TOP, title)
        c.setLineWidth(0.7)
        c.line(
            MARGIN_X, PAGE_H - MARGIN_TOP - 12,
            PAGE_W - MARGIN_X, PAGE_H - MARGIN_TOP - 12,
        )

        c.setFont(font, 9)
        top = PAGE_H - MARGIN_TOP - 36
        last_sheet = None
        for i, (sheet_idx, num, p) in enumerate(page_rows):
            r, col = divmod(i, columns)
            y = top - r * row_gap
            # 换份时加一条淡分隔线，方便定位
            if sheet_idx != last_sheet and col == 0 and r > 0:
                c.setLineWidth(0.3)
                c.setDash(1, 2)
                c.line(MARGIN_X, y + 15, PAGE_W - MARGIN_X, y + 15)
                c.setDash()
                c.setFont(font, 9)
            last_sheet = sheet_idx
            label = f"{sheet_idx}-{num}." if per_sheet_label else f"{num}."
            c.drawString(MARGIN_X + col * col_w, y, f"{label}{p.answer}")

        c.setFont(font, 9)
        c.drawCentredString(
            PAGE_W / 2, MARGIN_BOTTOM - 22, f"第 {page_idx} / {total_pages} 页"
        )
        c.showPage()

    c.save()
    return out_path
