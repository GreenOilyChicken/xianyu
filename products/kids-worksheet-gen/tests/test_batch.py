"""批量出卷测试：内容包产品线的核心保障。

重点验证「跨文件全局去重」——这是内容包相对单份出卷的唯一增量价值。
"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from batch import (
    BatchOptions,
    collect_all_keys,
    grade_short_name,
    run_batch,
    safe_stem,
)
from core import (
    GRADES,
    GradeSpec,
    GenerationError,
    generate_batch,
    generate_problems,
    unique_capacity,
)

pdfium = pytest.importorskip("pypdfium2", reason="需要 pypdfium2 校验 PDF")


# ------------------------------------------------------------ 容量计算

@pytest.mark.parametrize("code", list(GRADES.keys()))
def test_capacity_positive(code):
    assert unique_capacity(GRADES[code]) > 0


def test_capacity_matches_bruteforce():
    """容量计算必须与暴力枚举一致，否则预检会误判。"""
    spec = GradeSpec("t", "微型", ("+", "-"), (1, 9), (1, 9), max_answer=10)
    keys = set()
    for a in range(1, 10):
        for b in range(1, 10):
            if a + b <= 10:
                keys.add((a, b, "+"))
            if a > b:
                keys.add((a, b, "-"))
    assert unique_capacity(spec) == len(keys)


def test_capacity_with_carry_filter_is_smaller():
    """加进位筛选后容量应变小（且不是简单减半）。"""
    spec = GRADES["g1a"]
    assert unique_capacity(spec, True) < unique_capacity(spec, None)
    assert unique_capacity(spec, False) < unique_capacity(spec, None)


def test_capacity_is_cached():
    """同一参数应命中缓存，返回相同值。"""
    a = unique_capacity(GRADES["g2a"], None)
    b = unique_capacity(GRADES["g2a"], None)
    assert a == b


def test_known_small_capacity():
    """一年级上容量实测为 361，这是个容易踩的坑，锁死防止回归。"""
    assert unique_capacity(GRADES["g1a"]) == 361


# ------------------------------------------------------------ 批量生成去重

def test_batch_global_dedup():
    """核心保证：跨份完全不重复。"""
    sheets = generate_batch(GRADES["g2a"], 20, 40, rng=random.Random(1))
    assert len(sheets) == 20
    keys = collect_all_keys(sheets)
    assert len(keys) == 20 * 40, "存在跨份重复题目"


def test_batch_each_sheet_has_right_count():
    sheets = generate_batch(GRADES["g2a"], 5, 30, rng=random.Random(2))
    assert all(len(s) == 30 for s in sheets)


def test_batch_respects_carry_filter():
    from core import has_carry, has_borrow

    sheets = generate_batch(GRADES["g1b"], 5, 30, rng=random.Random(3), carry=True)
    for sheet in sheets:
        for p in sheet:
            ok = has_carry(p.a, p.b) if p.op == "+" else has_borrow(p.a, p.b)
            assert ok, f"{p} 不满足进位约束"


def test_batch_exclude_param():
    """exclude 里的题目不应再被生成。"""
    first = generate_problems(GRADES["g2a"], 40, rng=random.Random(4))
    used = {p.key() for p in first}
    more = generate_problems(
        GRADES["g2a"], 40, rng=random.Random(5), exclude=used
    )
    assert not (used & {p.key() for p in more})


def test_exclude_does_not_mutate_input():
    """exclude 是只读的，函数内部不应修改调用方的集合。"""
    used = {(1, 1, "+")}
    snapshot = set(used)
    generate_problems(GRADES["g2a"], 10, rng=random.Random(6), exclude=used)
    assert used == snapshot, "exclude 集合被意外修改"


def test_batch_over_capacity_raises():
    with pytest.raises(GenerationError) as e:
        generate_batch(GRADES["g1a"], 100, 40, rng=random.Random(7))
    assert "超出上限" in str(e.value)


def test_batch_exactly_at_capacity():
    """正好用满容量应成功（边界值）。"""
    cap = unique_capacity(GRADES["g1a"])
    sheets = cap // 40
    result = generate_batch(GRADES["g1a"], sheets, 40, rng=random.Random(8))
    assert len(collect_all_keys(result)) == sheets * 40


def test_batch_zero_sheets():
    assert generate_batch(GRADES["g2a"], 0, 40) == []


def test_batch_negative_raises():
    with pytest.raises(ValueError):
        generate_batch(GRADES["g2a"], -1, 40)
    with pytest.raises(ValueError):
        generate_batch(GRADES["g2a"], 5, -1)


def test_batch_same_seed_reproducible():
    a = generate_batch(GRADES["g3b"], 3, 20, rng=random.Random(42))
    b = generate_batch(GRADES["g3b"], 3, 20, rng=random.Random(42))
    assert collect_all_keys(a) == collect_all_keys(b)


# ------------------------------------------------------------ 文件产出

def test_run_batch_creates_files(tmp_path: Path):
    opts = BatchOptions(code="g2a", sheets=3, per_sheet=20, out_dir=tmp_path / "pkg")
    result = run_batch(opts)
    assert len(result.files) == 3
    assert all(f.exists() for f in result.files)
    assert result.total_problems == 60


def test_run_batch_filenames_numbered(tmp_path: Path):
    opts = BatchOptions(code="g2a", sheets=12, per_sheet=10, out_dir=tmp_path)
    result = run_batch(opts)
    names = [f.name for f in result.files]
    assert names[0].endswith("_01.pdf")
    assert names[-1].endswith("_12.pdf"), "序号宽度应按总份数对齐"


def test_run_batch_progress_callback(tmp_path: Path):
    seen = []
    opts = BatchOptions(code="g2a", sheets=3, per_sheet=10, out_dir=tmp_path)
    run_batch(opts, on_progress=lambda i, n, name: seen.append((i, n, name)))
    assert seen == [(1, 3, seen[0][2]), (2, 3, seen[1][2]), (3, 3, seen[2][2])]


def test_run_batch_answer_book(tmp_path: Path):
    opts = BatchOptions(
        code="g2a", sheets=3, per_sheet=20, out_dir=tmp_path, answer_book=True
    )
    result = run_batch(opts)
    assert result.answer_book is not None
    assert result.answer_book.exists()
    # 答案册应汇总全部 60 题的答案
    doc = pdfium.PdfDocument(str(result.answer_book))
    text = "".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
    assert "参考答案册" in text
    assert "1-1." in text


def test_run_batch_each_answers(tmp_path: Path):
    opts = BatchOptions(
        code="g2a", sheets=2, per_sheet=10, out_dir=tmp_path, include_answers=True
    )
    result = run_batch(opts)
    for f in result.files:
        doc = pdfium.PdfDocument(str(f))
        text = "".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
        assert "参考答案" in text


def test_run_batch_over_capacity_raises_before_mkdir(tmp_path: Path):
    """超限时应直接报错，且不留空目录。"""
    out = tmp_path / "should_not_exist"
    opts = BatchOptions(code="g1a", sheets=50, per_sheet=40, out_dir=out)
    with pytest.raises(GenerationError):
        run_batch(opts)
    assert not out.exists(), "超限时不应创建输出目录"


def test_run_batch_bad_code(tmp_path: Path):
    opts = BatchOptions(code="不存在的题型", sheets=1, per_sheet=10, out_dir=tmp_path)
    with pytest.raises(ValueError):
        run_batch(opts)


def test_run_batch_invalid_counts(tmp_path: Path):
    with pytest.raises(ValueError):
        run_batch(BatchOptions(code="g2a", sheets=0, per_sheet=10, out_dir=tmp_path))
    with pytest.raises(ValueError):
        run_batch(BatchOptions(code="g2a", sheets=2, per_sheet=0, out_dir=tmp_path))


def test_run_batch_pdfs_are_valid_and_deduped(tmp_path: Path):
    """端到端：产出 PDF 可解析，且从 PDF 回读的题目全局无重复。"""
    import re

    opts = BatchOptions(code="g2a", sheets=5, per_sheet=20, out_dir=tmp_path)
    result = run_batch(opts)

    seen: list[tuple] = []
    for f in result.files:
        doc = pdfium.PdfDocument(str(f))
        text = "".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
        seen.extend(re.findall(r"(\d+)\s*([+\-×÷])\s*(\d+)", text))

    assert len(seen) == 100
    assert len(set(seen)) == 100, "PDF 内容存在重复题目"


# ------------------------------------------------------------ 辅助函数

@pytest.mark.parametrize("raw,expect", [
    ("二年级上 · 100以内加减", "二年级上"),
    ("一年级上 · 20以内加减法", "一年级上"),
])
def test_grade_short_name(raw, expect):
    spec = GradeSpec("t", raw, ("+",), (1, 2), (1, 2))
    assert grade_short_name(spec) == expect


@pytest.mark.parametrize("raw", ['a/b\\c:d*e?f"g<h>i|j', "  a  b  "])
def test_safe_stem_removes_unsafe(raw):
    out = safe_stem(raw)
    assert not any(ch in out for ch in '\\/:*?"<>| ')
