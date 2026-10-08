"""批量出卷：生产"内容包"产品线。

一次生成一整套练习卷（如"二年级上口算 50 份"），跨文件全局去重，
可附一份总答案册。产出直接打包上架，无需买家安装任何软件。
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from core import (
    GRADES,
    GradeSpec,
    GenerationError,
    Problem,
    generate_batch,
    unique_capacity,
)
from pdf_render import SheetOptions, render_sheet

ProgressFn = Callable[[int, int, str], None]


def safe_stem(text: str) -> str:
    """把题型名称转成安全的文件名片段（去掉路径分隔符等）。"""
    cleaned = re.sub(r'[\\/:*?"<>|\s]+', "", text)
    return cleaned or "练习"


def grade_short_name(spec: GradeSpec) -> str:
    """从题型 label 里取年级段，如 '二年级上 · 100以内加减' → '二年级上'。"""
    head = spec.label.split("·")[0].strip()
    return safe_stem(head) or spec.key


@dataclass
class BatchOptions:
    """批量出卷配置。"""

    code: str
    sheets: int = 50
    per_sheet: int = 40
    out_dir: Path = Path("内容包")
    prefix: str = ""
    seed: int | None = None
    carry: str = "any"          # any / yes / no
    columns: int = 4
    blank: str = ""
    include_answers: bool = False   # 每份末尾附该份答案
    answer_book: bool = False       # 额外产出总答案册
    name_line: bool = True


@dataclass
class BatchResult:
    """批量出卷结果。"""

    files: list[Path]
    answer_book: Path | None
    total_problems: int
    sheets: int
    per_sheet: int


def _carry_value(mode: str) -> bool | None:
    return {"any": None, "yes": True, "no": False}[mode]


def run_batch(
    options: BatchOptions, on_progress: ProgressFn | None = None
) -> BatchResult:
    """执行批量出卷。返回结果摘要。"""
    spec = GRADES.get(options.code)
    if spec is None:
        raise ValueError(f"未知题型代码：{options.code}")

    if options.sheets <= 0:
        raise ValueError("份数必须大于 0")
    if options.per_sheet <= 0:
        raise ValueError("每份题数必须大于 0")

    carry = _carry_value(options.carry)

    # ★ 先做容量预检，再创建目录：超限时不应留下空目录
    total = options.sheets * options.per_sheet
    cap = unique_capacity(spec, carry)
    if total > cap:
        mode_hint = "（含进位/借位筛选）" if carry is not None else ""
        raise GenerationError(
            f"题量超出上限：{spec.label}{mode_hint}最多只能出 {cap} 道不重复的题，"
            f"当前请求 {options.sheets} 份 × {options.per_sheet} 题 = {total} 道。\n"
            f"可用份数上限：{cap // options.per_sheet} 份（每份 {options.per_sheet} 题）。\n"
            f"请减少份数或每份题数，或换题型。"
        )

    out_dir = Path(options.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(options.seed)

    # 一次性生成全部题目
    all_sheets = generate_batch(
        spec, options.sheets, options.per_sheet, rng=rng, carry=carry
    )

    prefix = options.prefix or f"口算_{grade_short_name(spec)}"
    width = max(2, len(str(options.sheets)))

    files: list[Path] = []
    for i, problems in enumerate(all_sheets, start=1):
        name = f"{prefix}_{i:0{width}d}.pdf"
        path = out_dir / name
        opts = SheetOptions(
            title=spec.label,
            subtitle=f"第 {i} 份 · 共 {options.sheets} 份",
            name_line=options.name_line,
            show_answers=options.include_answers,
            columns=options.columns,
            blank=options.blank,
        )
        render_sheet(problems, path, opts)
        files.append(path)
        if on_progress:
            on_progress(i, options.sheets, name)

    book: Path | None = None
    if options.answer_book:
        from pdf_render import render_answer_book

        book = out_dir / f"{prefix}_答案册.pdf"
        render_answer_book(
            all_sheets,
            book,
            title=f"{spec.label} · 参考答案册",
            per_sheet_label=prefix,
        )

    return BatchResult(
        files=files,
        answer_book=book,
        total_problems=options.sheets * options.per_sheet,
        sheets=options.sheets,
        per_sheet=options.per_sheet,
    )


def collect_all_keys(sheets: Iterable[Iterable[Problem]]) -> set[tuple[int, int, str]]:
    """把多份题目汇总成一个键集合，用于校验全局去重。"""
    keys: set[tuple[int, int, str]] = set()
    for sheet in sheets:
        for p in sheet:
            keys.add(p.key())
    return keys


__all__ = [
    "BatchOptions",
    "BatchResult",
    "GenerationError",
    "collect_all_keys",
    "grade_short_name",
    "run_batch",
    "safe_stem",
]
