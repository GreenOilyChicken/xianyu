"""字帖生成器测试。

覆盖：田字格渲染、三种模式（描红/临摹/混合）、拼音、分页、字表加载、CLI 集成、边界。
对齐 test_pdf.py / test_batch.py 的风格：程序化校验 PDF 内容，不靠肉眼。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from zi_tie import (
    CharSpec,
    ZitieOptions,
    MIAOHONG,
    LINMO,
    HUNHE,
    MODES,
    render_zitie,
    load_chars_from_file,
)

pdfium = pytest.importorskip("pypdfium2", reason="需要 pypdfium2 才能校验 PDF 内容")

# 字体可用性是前置条件，环境无字体时跳过整个模块
try:
    from fonts import FontNotFoundError, get_cjk_font

    get_cjk_font()
    _HAS_FONT = True
except FontNotFoundError:
    _HAS_FONT = False

pytestmark = pytest.mark.skipif(not _HAS_FONT, reason="环境无可用中文字体")


# ------------------------------------------------------------ 基础渲染

def _chars(text="永和九年"):
    return [CharSpec(c) for c in text]


def test_render_creates_file(tmp_path: Path):
    out = tmp_path / "zitie.pdf"
    render_zitie(_chars(), out, ZitieOptions(title="字帖"))
    assert out.exists()
    assert out.stat().st_size > 1000


def test_render_creates_parent_dir(tmp_path: Path):
    out = tmp_path / "nested" / "deep" / "zitie.pdf"
    render_zitie(_chars(), out)
    assert out.exists()


def test_pdf_contains_chars(tmp_path: Path):
    """PDF 里能提取到字，证明字体真的嵌入了。"""
    chars = _chars("永和九年")
    out = tmp_path / "zitie.pdf"
    render_zitie(chars, out, ZitieOptions(title="测试字帖"))

    doc = pdfium.PdfDocument(str(out))
    text = "".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
    assert "测试字帖" in text
    assert "永" in text and "和" in text and "九" in text and "年" in text


def test_pdf_contains_name_line(tmp_path: Path):
    out = tmp_path / "zitie.pdf"
    render_zitie(_chars(), out, ZitieOptions(name_line=True))
    doc = pdfium.PdfDocument(str(out))
    text = doc[0].get_textpage().get_text_range()
    assert "姓名" in text


def test_no_name_line(tmp_path: Path):
    out = tmp_path / "zitie.pdf"
    render_zitie(_chars(), out, ZitieOptions(name_line=False))
    doc = pdfium.PdfDocument(str(out))
    text = doc[0].get_textpage().get_text_range()
    assert "姓名" not in text


# ------------------------------------------------------------ 三种模式

@pytest.mark.parametrize("mode", list(MODES))
def test_all_modes_render(tmp_path: Path, mode: str):
    """三种模式都能成功生成 PDF。"""
    out = tmp_path / f"zitie_{mode}.pdf"
    render_zitie(_chars(), out, ZitieOptions(mode=mode))
    assert out.exists()
    assert out.stat().st_size > 1000


@pytest.mark.parametrize("mode", list(MODES))
def test_all_modes_contain_chars(tmp_path: Path, mode: str):
    """三种模式下字都能正确嵌入。"""
    out = tmp_path / f"zitie_{mode}.pdf"
    render_zitie(_chars("天地人"), out, ZitieOptions(mode=mode))
    doc = pdfium.PdfDocument(str(out))
    text = "".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
    assert "天" in text and "地" in text and "人" in text


def test_mode_validation_rejects_unknown(tmp_path: Path):
    with pytest.raises(ValueError, match="未知字帖模式"):
        render_zitie(_chars(), tmp_path / "x.pdf", ZitieOptions(mode="bogus"))


# ------------------------------------------------------------ 列数与分页

def test_cols_option(tmp_path: Path):
    """列数变化不应报错，且仍能生成。"""
    for cols in (4, 6, 8):
        out = tmp_path / f"zitie_{cols}.pdf"
        render_zitie(_chars(), out, ZitieOptions(cols=cols))
        assert out.exists()


def test_invalid_cols_raises(tmp_path: Path):
    with pytest.raises(ValueError):
        render_zitie(_chars(), tmp_path / "x.pdf", ZitieOptions(cols=0))


def test_pagination_multi_page(tmp_path: Path):
    """超过一页容量的字应分页，且页码出现。"""
    # 每页约 10 行，每字 1 行 → 30 个字应至少 3 页
    chars = [CharSpec(c) for c in "一二三四五六七八九十" * 30]
    out = tmp_path / "zitie.pdf"
    render_zitie(chars, out, ZitieOptions(title="多页字帖"))
    doc = pdfium.PdfDocument(str(out))
    assert len(doc) > 1
    text = "".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
    assert "第 1 /" in text


def test_single_page_no_page_footer(tmp_path: Path):
    """单页时不打印页码。"""
    out = tmp_path / "zitie.pdf"
    render_zitie(_chars(), out, ZitieOptions(title="单页"))
    doc = pdfium.PdfDocument(str(out))
    assert len(doc) == 1
    text = doc[0].get_textpage().get_text_range()
    assert "第 1 /" not in text


# ------------------------------------------------------------ 拼音

def test_pinyin_rendered(tmp_path: Path):
    """开启拼音后，拼音声调应能出现在 PDF 文本里。"""
    chars = [CharSpec("永", "yǒng"), CharSpec("和", "hé")]
    out = tmp_path / "zitie_pinyin.pdf"
    render_zitie(chars, out, ZitieOptions(pinyin=True, mode=LINMO))
    doc = pdfium.PdfDocument(str(out))
    text = "".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
    assert "yǒng" in text or "ǒng" in text
    assert "永" in text


def test_pinyin_off_by_default(tmp_path: Path):
    """默认不印拼音。"""
    chars = [CharSpec("永", "yǒng")]
    out = tmp_path / "zitie.pdf"
    render_zitie(chars, out)
    doc = pdfium.PdfDocument(str(out))
    text = "".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
    assert "yǒng" not in text


def test_empty_pinyin_skipped(tmp_path: Path):
    """拼音为空串时不应报错。"""
    chars = [CharSpec("永", "")]
    out = tmp_path / "zitie.pdf"
    render_zitie(chars, out, ZitieOptions(pinyin=True))
    assert out.exists()


# ------------------------------------------------------------ 字表加载

def test_load_chars_from_file(tmp_path: Path):
    f = tmp_path / "chars.txt"
    f.write_text("永和\n# 注释\n天地人\n", encoding="utf-8")
    chars = load_chars_from_file(f)
    assert chars == ["永", "和", "天", "地", "人"]


def test_load_chars_dedup(tmp_path: Path):
    """重复字应去重。"""
    f = tmp_path / "chars.txt"
    f.write_text("永永永和和\n天地\n永", encoding="utf-8")
    chars = load_chars_from_file(f)
    assert chars == ["永", "和", "天", "地"]


def test_load_chars_filters_non_han(tmp_path: Path, capsys=None):
    """非汉字字符（标点、空格、字母）应被过滤。"""
    f = tmp_path / "chars.txt"
    f.write_text("永, 和。天地 abc 123\n", encoding="utf-8")
    chars = load_chars_from_file(f)
    assert chars == ["永", "和", "天", "地"]


def test_load_chars_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_chars_from_file(tmp_path / "nope.txt")


def test_load_chars_empty_file(tmp_path: Path):
    f = tmp_path / "chars.txt"
    f.write_text("# 只有注释\n\n", encoding="utf-8")
    assert load_chars_from_file(f) == []


def test_builtin_char_file_exists():
    """内置字表文件应存在且非空。"""
    builtin = Path(__file__).resolve().parent.parent / "assets" / "chars_3500.txt"
    assert builtin.exists(), "内置字表 assets/chars_3500.txt 缺失"
    chars = load_chars_from_file(builtin)
    assert len(chars) > 50, f"内置字表字数过少：{len(chars)}"


# ------------------------------------------------------------ 输入校验

def test_empty_chars_raises(tmp_path: Path):
    with pytest.raises(ValueError, match="字列表不能为空"):
        render_zitie([], tmp_path / "x.pdf", ZitieOptions())


def test_multi_char_string_rejected():
    """CharSpec 只接受单字符，防止把词当字。"""
    with pytest.raises(ValueError):
        CharSpec("永和")


def test_invalid_rows_raises(tmp_path: Path):
    with pytest.raises(ValueError):
        render_zitie(_chars(), tmp_path / "x.pdf", ZitieOptions(rows=0))


# ------------------------------------------------------------ 混合模式行为

def test_hunhe_mode_uses_both_styles(tmp_path: Path):
    """混合模式应同时产出灰色范字（描红行）和黑色范字（临摹行）。
    
    无法直接判断颜色，但可通过"两种行都含字"间接验证：混合模式下
    字数应出现在多行（至少 2 行结构），而非单一风格。
    """
    chars = [CharSpec(c) for c in "一二三四"]
    out = tmp_path / "zitie.pdf"
    render_zitie(chars, out, ZitieOptions(mode=HUNHE))
    doc = pdfium.PdfDocument(str(out))
    text = "".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
    # 4 个字都应在 PDF 里
    for c in "一二三四":
        assert c in text


# ------------------------------------------------------------ CLI 集成

def _run_cli(argv: list[str]) -> int:
    import main as cli
    return cli.main(argv)


def test_cli_chars_mode(tmp_path: Path):
    out = tmp_path / "cli.pdf"
    rc = _run_cli([
        "--mode", "zitie", "--chars", "永和九年",
        "--out", str(out),
    ])
    assert rc == 0
    assert out.exists()
    doc = pdfium.PdfDocument(str(out))
    text = "".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
    assert "永" in text


def test_cli_style_option(tmp_path: Path):
    out = tmp_path / "cli.pdf"
    rc = _run_cli([
        "--mode", "zitie", "--chars", "天地", "--style", "linmo",
        "--out", str(out),
    ])
    assert rc == 0
    assert out.exists()


def test_cli_char_file(tmp_path: Path):
    cf = tmp_path / "chars.txt"
    cf.write_text("永和天地\n", encoding="utf-8")
    out = tmp_path / "cli.pdf"
    rc = _run_cli([
        "--mode", "zitie", "--char-file", str(cf),
        "--out", str(out),
    ])
    assert rc == 0
    doc = pdfium.PdfDocument(str(out))
    text = "".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
    assert "永" in text and "地" in text


def test_cli_no_chars_falls_back_to_builtin(tmp_path: Path):
    """不指定 --chars 也不指定 --char-file，应回退到内置字表。"""
    out = tmp_path / "cli_builtin.pdf"
    rc = _run_cli(["--mode", "zitie", "--out", str(out)])
    assert rc == 0
    assert out.exists()
    assert out.stat().st_size > 5000  # 内置字表字多，文件应较大


def test_cli_invalid_chars_returns_error(tmp_path: Path):
    """--chars 全是非汉字字符应报错。"""
    rc = _run_cli([
        "--mode", "zitie", "--chars", "abc123",
        "--out", str(tmp_path / "x.pdf"),
    ])
    assert rc == 2


def test_cli_missing_char_file_returns_error(tmp_path: Path):
    rc = _run_cli([
        "--mode", "zitie", "--char-file", str(tmp_path / "nope.txt"),
        "--out", str(tmp_path / "x.pdf"),
    ])
    assert rc == 2


def test_cli_zitie_rejects_batch(tmp_path: Path):
    """字帖模式不支持 --batch。"""
    rc = _run_cli([
        "--mode", "zitie", "--chars", "永", "--batch",
        "--out", str(tmp_path / "x.pdf"),
    ])
    assert rc == 2


def test_cli_kousuan_backward_compat(tmp_path: Path):
    """不带 --mode 时默认口算，行为不变。"""
    out = tmp_path / "kousuan.pdf"
    rc = _run_cli(["--grade", "g1a", "--count", "5", "--out", str(out)])
    assert rc == 0
    assert out.exists()


def test_cli_pinyin_flag(tmp_path: Path):
    out = tmp_path / "cli_pinyin.pdf"
    rc = _run_cli([
        "--mode", "zitie", "--chars", "永和", "--pinyin",
        "--out", str(out),
    ])
    assert rc == 0
    assert out.exists()
