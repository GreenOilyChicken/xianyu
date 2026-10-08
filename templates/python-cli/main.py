#!/usr/bin/env python3
"""工具入口。接定制单时改这里的参数和业务调用。

用法示例：
    python main.py --input ./imgs --output ./out --watermark logo.png
"""
import argparse
import sys
from pathlib import Path

from core import run  # 核心逻辑放 core.py


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="TODO: 一句话说明这工具干什么",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：\n  python main.py --input ./in --output ./out",
    )
    p.add_argument("--input", "-i", required=True, help="输入路径")
    p.add_argument("--output", "-o", default="./output", help="输出目录，默认 ./output")
    p.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        run(
            input_path=Path(args.input),
            output_path=Path(args.output),
            verbose=args.verbose,
        )
    except FileNotFoundError as e:
        print(f"❌ 找不到文件：{e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"❌ 出错了：{e}", file=sys.stderr)
        return 1
    print("✅ 完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
