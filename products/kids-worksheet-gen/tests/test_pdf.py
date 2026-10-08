"""PDF 渲染与字体解析测试。

覆盖：字体可用性、PDF 生成、分页、答案页、中文渲染无缺字。
"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from core import GRADES, generate_problems
from fonts import FontNotFoundError, get_cjk_font
from pdf_render import SheetOptions, render_sheet

pdfium = pytest.importorskip("pypdfium2", reason="需要 pypdfium2 才能校验 PDF 内容")


# ------------------------------------------------------------ 字体

def test_cjk_font_available():
    """环境里应能找到可用中文字体（TrueType 轮廓）。"""
    try:
        name = get_cjk_font()
    except FontNotFoundError as e:
        pytest.skip(f"环境无中文字体：{e}")
    assert name


def test_font_covers_required_glyphs():
    """字体必须覆盖题面用到的全部字符，否则 PDF 会出空白方块。"""
    from fonts import REQUIRED_CHARS
    from reportlab.pdfbase import pdfmetrics

    try:
        name = get_cjk_font()
    except FontNotFoundError as e:
        pytest.skip(f"环境无中文字体：{e}")

    cmap = pdfmetrics.getFont(name).face.charToGlyph
    missing = [ch for ch in REQUIRED_CHARS if ord(ch) not in cmap]
    assert not missing, f"字体缺字：{''.join(missing)}"


# ------------------------------------------------------------ PDF 生成

def _problems(code="g2a", n=40, seed=1):
    return generate_problems(GRADES[code], n, rng=random.Random(seed))


def test_render_creates_file(tmp_path: Path):
    out = tmp_path / "sheet.pdf"
    render_sheet(_problems(), out, SheetOptions(title="口算练习"))
    assert out.exists()
    assert out.stat().st_size > 1000


def test_render_creates_parent_dir(tmp_path: Path):
    out = tmp_path / "nested" / "deep" / "sheet.pdf"
    render_sheet(_problems(), out)
    assert out.exists()


def test_pdf_text_contains_problems(tmp_path: Path):
    """PDF 里能提取到题目文本，证明字体真的嵌入了。"""
    problems = _problems("g2a", 20, seed=3)
    out = tmp_path / "sheet.pdf"
    render_sheet(problems, out, SheetOptions(title="二年级口算"))

    doc = pdfium.PdfDocument(str(out))
    text = "".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))

    assert "二年级口算" in text
    assert "姓名" in text
    # 第一题的题面应能在 PDF 里找到
    assert problems[0].text() in text


def test_single_page_for_40_problems(tmp_path: Path):
    out = tmp_path / "sheet.pdf"
    render_sheet(_problems("g2a", 40), out)
    assert len(pdfium.PdfDocument(str(out))) == 1


def test_pagination_multi_page(tmp_path: Path):
    """120 题应分成多页，且页码标注出现。"""
    out = tmp_path / "sheet.pdf"
    render_sheet(_problems("g2a", 120), out)
    doc = pdfium.PdfDocument(str(out))
    assert len(doc) > 1
    text = "".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
    assert "第 1 /" in text


def test_answer_page_is_separate(tmp_path: Path):
    """答案必须独立成页，不能叠在题目页上。"""
    problems = _problems("g2a", 40, seed=4)
    out = tmp_path / "sheet.pdf"
    render_sheet(problems, out, SheetOptions(show_answers=True))

    doc = pdfium.PdfDocument(str(out))
    pages = [doc[i].get_textpage().get_text_range() for i in range(len(doc))]

    assert len(pages) == 2, "40题+答案应为2页"
    assert "参考答案" not in pages[0], "答案不能出现在题目页"
    assert "参考答案" in pages[1], "答案页缺失"

    # 答案页应包含第一题的正确答案
    assert str(problems[0].answer) in pages[1]


def test_no_answer_page_by_default(tmp_path: Path):
    out = tmp_path / "sheet.pdf"
    render_sheet(_problems("g2a", 40), out, SheetOptions(show_answers=False))
    doc = pdfium.PdfDocument(str(out))
    text = "".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
    assert "参考答案" not in text


def test_blank_answer_marker(tmp_path: Path):
    """作答符会出现在题面里。"""
    out = tmp_path / "sheet.pdf"
    render_sheet(_problems("g1a", 10), out, SheetOptions(blank="（　　）"))
    doc = pdfium.PdfDocument(str(out))
    text = doc[0].get_textpage().get_text_range()
    assert "（　　）" in text


def test_columns_option(tmp_path: Path):
    """列数变化不应报错，且仍能生成。"""
    for cols in (2, 3, 4, 5):
        out = tmp_path / f"sheet_{cols}.pdf"
        render_sheet(_problems("g1a", 20), out, SheetOptions(columns=cols))
        assert out.exists()


def test_invalid_columns_raises(tmp_path: Path):
    with pytest.raises(ValueError):
        render_sheet(_problems("g1a", 5), tmp_path / "x.pdf", SheetOptions(columns=0))


def test_empty_problem_list(tmp_path: Path):
    """空题目列表不应崩溃。"""
    out = tmp_path / "empty.pdf"
    render_sheet([], out)
    assert out.exists()


@pytest.mark.parametrize("code", list(GRADES.keys()))
def test_render_every_grade(tmp_path: Path, code: str):
    """每个年级都能成功出卷。"""
    out = tmp_path / f"{code}.pdf"
    render_sheet(_problems(code, 20), out, SheetOptions(title=GRADES[code].label))
    assert out.exists()
    doc = pdfium.PdfDocument(str(out))
    text = doc[0].get_textpage().get_text_range()
    assert GRADES[code].label in text
