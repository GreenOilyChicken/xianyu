#!/usr/bin/env python3
"""练习卷生成器 —— 命令行入口。

用法（口算模式）：
    python main.py --grade g2a --count 40 --out 口算练习.pdf
    python main.py --list-grades

用法（字帖模式）：
    python main.py --mode zitie --chars "永和九年" --out 字帖.pdf
    python main.py --mode zitie --char-file assets/chars_3500.txt --out 字帖.pdf
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import GRADES, GenerationError, generate_problems  # noqa: E402
from pdf_render import SheetOptions, render_sheet  # noqa: E402
from resource_path import char_file_default  # noqa: E402

DEFAULT_CHAR_FILE = char_file_default()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="生成 A4 练习卷 PDF（口算 / 字帖），打印即用。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例（口算）：\n"
            "  python main.py --grade g2a --count 40\n"
            "  python main.py --grade g1b --count 60 --columns 3 --out 一页60题.pdf\n"
            "  python main.py --grade g3b --count 40 --answers --out 带答案.pdf\n"
            "  python main.py --list-grades\n\n"
            "示例（字帖）：\n"
            "  python main.py --mode zitie --chars '永和九年'\n"
            "  python main.py --mode zitie --char-file assets/chars_3500.txt\n"
            "  python main.py --mode zitie --chars '永和' --style miaohong --pinyin\n"
        ),
    )
    p.add_argument("--mode", choices=["kousuan", "zitie"], default="kousuan",
                   help="生成模式：kousuan=口算卷（默认）；zitie=字帖")
    p.add_argument("--grade", "-g", default="g2a", help="年级/题型代码，见 --list-grades（口算模式）")
    p.add_argument("--count", "-n", type=int, default=40, help="题目数量，默认 40（口算模式）")
    p.add_argument("--out", "-o", default=None, help="输出 PDF 路径")
    p.add_argument("--columns", "-c", type=int, default=4, help="每行列数，默认 4（口算模式）")
    p.add_argument("--carry", choices=["any", "yes", "no"], default="any",
                   help="any=不限（默认）；yes=只要进位/借位；no=只要不进位/不借位（口算模式）")
    p.add_argument("--title", default=None, help="自定义标题，默认用题型名称 / 字帖")
    p.add_argument("--subtitle", default=None, help="副标题（口算模式）")
    p.add_argument("--blank", default="", help="作答符，如 --blank '（　　）' 或 '____'（口算模式）")
    p.add_argument("--answers", action="store_true", help="附加参考答案页（口算模式）")
    p.add_argument("--no-name-line", action="store_true", help="不打印姓名/日期信息栏")
    p.add_argument("--seed", type=int, default=None, help="随机种子，同种子出同一套题（口算模式）")
    p.add_argument("--list-grades", action="store_true", help="列出所有口算题型代码后退出")
    p.add_argument("--doctor", action="store_true",
                   help="自检运行环境（字体/字表/依赖），打包后排查问题用")

    # ---- 批量出卷（内容包生产）----
    g = p.add_argument_group("批量出卷（内容包生产）")
    g.add_argument("--batch", action="store_true",
                   help="批量模式：一次生成多份卷子，跨份全局不重复")
    g.add_argument("--sheets", type=int, default=50, help="批量份数，默认 50")
    g.add_argument("--per-sheet", type=int, default=40, help="每份题数，默认 40")
    g.add_argument("--out-dir", default=None,
                   help="批量输出目录，默认 ./内容包_<题型>")
    g.add_argument("--prefix", default=None, help="文件名前缀，默认自动取年级段")
    g.add_argument("--each-answers", action="store_true",
                   help="每份卷子末尾附该份答案页")
    g.add_argument("--answer-book", action="store_true",
                   help="额外生成一本总答案册（所有份汇总）")
    g.add_argument("--capacity", action="store_true",
                   help="查询该题型最多能出多少道不重复的题，然后退出")

    # ---- 字帖模式 ----
    z = p.add_argument_group("字帖模式（--mode zitie）")
    z.add_argument("--chars", default=None,
                   help="字帖要练的字，直接给出（如 '永和九年'）。与 --char-file 二选一")
    z.add_argument("--char-file", default=None,
                   help="从文本文件读字表（一行一个或连续均可）。默认用内置 assets/chars_3500.txt")
    z.add_argument("--style", choices=["miaohong", "linmo", "hunhe"], default="miaohong",
                   help="字帖样式：miaohong=描红（默认）；linmo=临摹；hunhe=混合（描红/临摹交替行）")
    z.add_argument("--pinyin", action="store_true",
                   help="在字上方印拼音（需字带拼音数据；--chars 模式不带拼音，仅作占位）")
    z.add_argument("--cols-zitie", type=int, default=None,
                   help="字帖每行格数，默认 8")
    return p


def list_grades() -> None:
    print("可用题型代码：\n")
    for code, spec in GRADES.items():
        print(f"  {code:<6} {spec.label}")
        if spec.note:
            print(f"         {spec.note}")
    print("\n用法示例：python main.py --grade g2a --count 40")


def show_capacity(code: str, carry: str) -> int:
    """打印题型容量，供批量出卷前预检。"""
    from core import unique_capacity

    spec = GRADES.get(code)
    if spec is None:
        print(f"❌ 未知题型代码：{code}", file=sys.stderr)
        return 2

    mode = {"any": None, "yes": True, "no": False}[carry]
    cap = unique_capacity(spec, mode)
    label = {"any": "不限", "yes": "只要进位/借位", "no": "只要不进位/不借位"}[carry]

    print(f"题型：{spec.label}")
    print(f"筛选：{label}")
    print(f"最多可出 {cap} 道互不相同的题")
    if cap:
        print(f"  → 40 题/份可出 {cap // 40} 份；30 题/份可出 {cap // 30} 份")
    return 0


def run_batch_mode(args) -> int:
    """批量出卷流程。"""
    from batch import BatchOptions, run_batch

    if args.grade not in GRADES:
        print(f"❌ 未知题型代码：{args.grade}", file=sys.stderr)
        print("   可用代码见：python main.py --list-grades", file=sys.stderr)
        return 2

    spec = GRADES[args.grade]
    from batch import grade_short_name
    from core import unique_capacity

    # ★ 先预检容量，再打印横幅：避免超限时报错与横幅输出顺序错乱
    carry_mode = {"any": None, "yes": True, "no": False}[args.carry]
    total = args.sheets * args.per_sheet
    cap = unique_capacity(spec, carry_mode)
    if total > cap:
        mode_hint = "（含进位/借位筛选）" if carry_mode is not None else ""
        print(f"❌ 题量超出上限：{spec.label}{mode_hint}最多只能出 {cap} 道不重复的题。",
              file=sys.stderr)
        print(f"   当前请求：{args.sheets} 份 × {args.per_sheet} 题 = {total} 道",
              file=sys.stderr)
        if args.per_sheet:
            print(f"   可用份数上限：{cap // args.per_sheet} 份（每份 {args.per_sheet} 题）",
                  file=sys.stderr)
        print("   提示：用 --capacity 查询该题型的出题上限", file=sys.stderr)
        return 3

    out_dir = args.out_dir or f"内容包_{grade_short_name(spec)}"

    opts = BatchOptions(
        code=args.grade,
        sheets=args.sheets,
        per_sheet=args.per_sheet,
        out_dir=Path(out_dir),
        prefix=args.prefix,
        seed=args.seed,
        carry=args.carry,
        columns=args.columns,
        blank=args.blank,
        include_answers=args.each_answers,
        answer_book=args.answer_book,
        name_line=not args.no_name_line,
    )

    total = args.sheets * args.per_sheet
    print(f"▶ 批量出卷：{spec.label}")
    print(f"  {args.sheets} 份 × {args.per_sheet} 题 = {total} 道（跨份不重复）")
    print(f"  输出：{out_dir}")
    print()
    def on_progress(i: int, n: int, name: str) -> None:
        print(f"  [{i:>{len(str(n))}}/{n}] {name}")

    try:
        result = run_batch(opts, on_progress=on_progress)
    except GenerationError as e:
        print(f"\n❌ {e}", file=sys.stderr)
        print("   提示：用 --capacity 查询该题型的出题上限", file=sys.stderr)
        return 3
    except ValueError as e:
        print(f"\n❌ {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"\n❌ 生成失败：{e}", file=sys.stderr)
        return 1

    print()
    print(f"✅ 完成：{len(result.files)} 份，共 {result.total_problems} 道题")
    print(f"   目录：{Path(out_dir).resolve()}")
    if result.answer_book:
        print(f"   答案册：{result.answer_book.name}")
    return 0


def run_zitie_mode(args) -> int:
    """字帖生成流程。"""
    from zi_tie import CharSpec, ZitieOptions, render_zitie, load_chars_from_file

    # 取字：--chars 优先，否则 --char-file，否则内置字表
    raw_chars: list[str] = []
    if args.chars:
        for ch in args.chars:
            if 0x4E00 <= ord(ch) <= 0x9FFF or 0x3400 <= ord(ch) <= 0x4DBF:
                raw_chars.append(ch)
        if not raw_chars:
            print("❌ --chars 没有包含有效汉字", file=sys.stderr)
            return 2
        # 去重保序
        seen: set[str] = set()
        raw_chars = [c for c in raw_chars if not (c in seen or seen.add(c))]
    else:
        char_path = Path(args.char_file) if args.char_file else DEFAULT_CHAR_FILE
        try:
            raw_chars = load_chars_from_file(char_path)
        except FileNotFoundError as e:
            print(f"❌ {e}", file=sys.stderr)
            print("   可用 --chars 直接指定字，或用 --char-file 指定字表文件",
                  file=sys.stderr)
            return 2
        if not raw_chars:
            print(f"❌ 字表文件里没有有效汉字：{char_path}", file=sys.stderr)
            return 2

    chars = [CharSpec(c) for c in raw_chars]

    opt = ZitieOptions(
        title=args.title or "字帖",
        name_line=not args.no_name_line,
        mode=args.style,
        cols=args.cols_zitie if args.cols_zitie else 8,
        pinyin=args.pinyin,
    )

    out_path = args.out or "字帖.pdf"
    try:
        out = render_zitie(chars, out_path, opt)
    except ValueError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"❌ 生成字帖失败：{e}", file=sys.stderr)
        return 1

    size_kb = out.stat().st_size / 1024
    style_name = {"miaohong": "描红", "linmo": "临摹", "hunhe": "混合"}[args.style]
    print(f"✅ 已生成：{out}")
    print(f"   {len(chars)} 个字 · {opt.cols} 列 · {style_name}样式 · {size_kb:.1f} KB")
    return 0


def run_doctor() -> int:
    """自检：打包后排查"字体找不到 / 字表找不到"用。"""
    import resource_path

    print("=== 运行环境自检 ===\n")
    print(resource_path.describe())
    print()

    ok = True

    # 字体
    try:
        from fonts import describe as font_describe

        print(f"中文字体: {font_describe()}")
    except Exception as e:
        print(f"中文字体: ❌ {e}")
        ok = False

    # 字表
    cf = resource_path.char_file_default()
    if cf.exists():
        try:
            from zi_tie import load_chars_from_file

            n = len(load_chars_from_file(cf))
            print(f"字表字数: {n}")
        except Exception as e:
            print(f"字表读取: ❌ {e}")
            ok = False
    else:
        print("字表读取: ❌ 文件不存在（打包时 --add-data 没配对）")
        ok = False

    # PDF 库
    try:
        import reportlab

        print(f"reportlab: {reportlab.Version}")
    except Exception as e:
        print(f"reportlab: ❌ {e}")
        ok = False

    print()
    print("✅ 自检通过" if ok else "❌ 自检发现问题，见上方 ❌ 项")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.doctor:
        return run_doctor()

    if args.list_grades:
        list_grades()
        return 0

    if args.capacity:
        return show_capacity(args.grade, args.carry)

    # ---- 模式分发 ----
    if args.mode == "zitie":
        if args.batch:
            print("❌ 字帖模式暂不支持 --batch（字表本身就是固定的，无需批量去重）",
                  file=sys.stderr)
            return 2
        return run_zitie_mode(args)

    # 以下为口算模式
    if args.batch:
        return run_batch_mode(args)

    spec = GRADES.get(args.grade)
    if spec is None:
        print(f"❌ 未知题型代码：{args.grade}", file=sys.stderr)
        print("   可用代码见：python main.py --list-grades", file=sys.stderr)
        return 2

    if args.count <= 0:
        print("❌ --count 必须大于 0", file=sys.stderr)
        return 2

    carry = {"any": None, "yes": True, "no": False}[args.carry]

    try:
        problems = generate_problems(
            spec, args.count, rng=random.Random(args.seed), carry=carry
        )
    except GenerationError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 3

    opts = SheetOptions(
        title=args.title or spec.label,
        subtitle=args.subtitle or "",
        name_line=not args.no_name_line,
        show_answers=args.answers,
        columns=args.columns,
        blank=args.blank,
    )

    out_path = args.out or "口算练习.pdf"
    try:
        out = render_sheet(problems, out_path, opts)
    except Exception as e:
        print(f"❌ 生成 PDF 失败：{e}", file=sys.stderr)
        return 1

    size_kb = out.stat().st_size / 1024
    print(f"✅ 已生成：{out}")
    print(f"   {len(problems)} 道题 · {args.columns} 列 · {size_kb:.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
