#!/usr/bin/env python3
"""把 xianyu-skills 的 JSON 输出转成可读的运营复盘表。

数据来源：https://github.com/donggeai/xianyu-skills
    python scripts/cli.py list-my-items                  # 商品列表（含 item_id）
    python scripts/cli.py get-item-stats --item-id ID    # 单商品浏览/想要

用法：
    # 1. 采集（在 xianyu-skills 目录里跑，输出存到 ops/data/）
    python scripts/cli.py list-my-items > ops/data/my-items-2026-10-08.json
    python scripts/cli.py get-item-stats --item-id 123 > ops/data/stats-123.json

    # 2. 转换
    python ops/tools/xianyu_stats.py snapshot ops/data/*.json
    python ops/tools/xianyu_stats.py report          # 打印复盘表
    python ops/tools/xianyu_stats.py diff            # 与上次快照对比增量

只依赖标准库。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# ── 路径 ────────────────────────────────────────────────────────────────
OPS_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = OPS_DIR / "data"
SNAPSHOT_FILE = DATA_DIR / "snapshots.json"

# ── 数字解析 ────────────────────────────────────────────────────────────


def parse_count(value: object) -> int | None:
    """把 '1.2万' / '361' / '1,234' 解析成整数。无法解析返回 None。

    闲鱼页面上的浏览/想要数会带「万」单位，超过万就只显示一位小数，
    所以精确值拿不到 —— 这里只保证量级正确。
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    match = re.match(r"^([\d.]+)\s*(万|w|W)?$", text)
    if not match:
        # 兜底：从字符串里抠出第一个数字
        digits = re.search(r"([\d.]+)\s*(万|w|W)?", text)
        if not digits:
            return None
        match = digits
    number = float(match.group(1))
    unit = match.group(2)
    if unit in ("万", "w", "W"):
        number *= 10000
    return int(number)


def parse_price(value: object) -> float | None:
    """把 '¥9.9' / '9.9' 解析成 float。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"([\d.]+)", str(value).replace(",", ""))
    return float(match.group(1)) if match else None


def extract_item_id(url: str | None) -> str | None:
    """从商品 URL 里取出 item_id。"""
    if not url:
        return None
    match = re.search(r"[?&]id=(\d+)", url)
    return match.group(1) if match else None


# ── 读取 xianyu-skills 输出 ─────────────────────────────────────────────


def load_stats_files(paths: list[Path]) -> dict[str, dict]:
    """读入若干 JSON 文件，返回 {item_id: 归一化记录}。

    兼容三种输入：
      - get-item-stats 输出：单条，含 item_id/views/wanted/price/title
      - list-my-items 输出：{count, items:[{url,text}], profile:{...}}
      - get-item-detail 输出：含 item_id/url/title/price/views/wanted
    """
    records: dict[str, dict] = {}

    for path in paths:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[跳过] {path.name}: {exc}", file=sys.stderr)
            continue

        for entry in _iter_entries(raw):
            item_id = entry.get("item_id") or extract_item_id(entry.get("url"))
            if not item_id:
                continue
            item_id = str(item_id)

            record = records.setdefault(item_id, {"item_id": item_id})
            # 兼容两套字段名：itemstats 用 browse/want，旧格式用 views/wanted
            views_val = entry.get("views") if entry.get("views") is not None else entry.get("browse")
            wanted_val = entry.get("wanted") if entry.get("wanted") is not None else entry.get("want")
            for key, value in (
                ("title", entry.get("title")),
                ("price", parse_price(entry.get("price"))),
                ("views", parse_count(views_val)),
                ("wanted", parse_count(wanted_val)),
                ("url", entry.get("url")),
            ):
                if value not in (None, "") and record.get(key) in (None, ""):
                    record[key] = value

    return records


def _iter_entries(raw: object) -> list[dict]:
    """把各种形状的 JSON 摊平成记录列表。"""
    if not isinstance(raw, dict):
        return []
    # list-my-items：items 里只有 url/text，没有浏览数据
    if isinstance(raw.get("items"), list):
        return [e for e in raw["items"] if isinstance(e, dict)]
    # 单条 stats / detail
    if "item_id" in raw or "url" in raw:
        return [raw]
    return []


# ── 快照存储 ────────────────────────────────────────────────────────────


def load_snapshots() -> list[dict]:
    if not SNAPSHOT_FILE.exists():
        return []
    try:
        data = json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_snapshots(snapshots: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_FILE.write_text(
        json.dumps(snapshots, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── 输出 ────────────────────────────────────────────────────────────────


def fmt(value: object, dash: str = "-") -> str:
    if value is None or value == "":
        return dash
    return str(value)


def render_report(records: dict[str, dict], previous: dict[str, dict] | None = None) -> str:
    """渲染 markdown 复盘表。previous 存在时追加增量列。"""
    lines: list[str] = []
    has_delta = bool(previous)

    if has_delta:
        lines.append("| 商品 | 价格 | 浏览 | 浏览增量 | 想要 | 想要增量 |")
        lines.append("|---|---|---|---|---|---|")
    else:
        lines.append("| 商品 | 价格 | 浏览 | 想要 | 链接 |")
        lines.append("|---|---|---|---|---|")

    # 按浏览量降序，没有浏览数据的排后面
    ordered = sorted(
        records.values(),
        key=lambda r: (r.get("views") is None, -(r.get("views") or 0)),
    )

    for rec in ordered:
        title = (rec.get("title") or rec.get("item_id") or "")[:36]
        price = f"¥{rec['price']}" if rec.get("price") is not None else "-"

        if has_delta:
            old = previous.get(rec["item_id"], {})
            views_delta = _delta(rec.get("views"), old.get("views"))
            wanted_delta = _delta(rec.get("wanted"), old.get("wanted"))
            lines.append(
                f"| {title} | {price} | {fmt(rec.get('views'))} | {views_delta} "
                f"| {fmt(rec.get('wanted'))} | {wanted_delta} |"
            )
        else:
            url = rec.get("url") or "-"
            lines.append(
                f"| {title} | {price} | {fmt(rec.get('views'))} "
                f"| {fmt(rec.get('wanted'))} | {url} |"
            )

    return "\n".join(lines)


def _delta(new: object, old: object) -> str:
    if new is None:
        return "-"
    if old is None:
        return "新增"
    try:
        diff = int(new) - int(old)
    except (TypeError, ValueError):
        return "-"
    if diff > 0:
        return f"+{diff}"
    return str(diff)


def build_analysis(records: dict[str, dict], previous: dict[str, dict] | None) -> str:
    """按冷启动方案第七节的判据，给出可执行结论。"""
    notes: list[str] = []
    zero_views = [r for r in records.values() if not r.get("views")]
    has_views = [r for r in records.values() if r.get("views")]
    wanted = [r for r in records.values() if r.get("wanted")]

    if not records:
        return "没有数据。"

    if zero_views:
        notes.append(
            f"**{len(zero_views)} 个商品零曝光**（{len(records)} 个中）"
            " → 按方案第八节：换标题关键词 + 换首图重发"
        )
    if has_views and not wanted:
        notes.append(
            "**有浏览但零「想要」** → 首图不够吸引或价格高于同行，先改首图"
        )
    if wanted:
        best = max(wanted, key=lambda r: r.get("wanted") or 0)
        notes.append(
            f"**「想要」最高**：{best.get('title') or best['item_id']}"
            f"（{best.get('wanted')}）→ 它的标题关键词值得铺到其他商品"
        )

    if previous:
        grew = []
        for rec in records.values():
            old = previous.get(rec["item_id"])
            if old and rec.get("views") is not None and old.get("views") is not None:
                diff = rec["views"] - old["views"]
                if diff > 0:
                    grew.append((rec, diff))
        if grew:
            grew.sort(key=lambda pair: -pair[1])
            top = grew[0]
            notes.append(
                f"**曝光增长最快**：{top[0].get('title') or top[0]['item_id']}"
                f"（+{top[1]}）→ 观察它靠什么关键词进来的"
            )
        else:
            notes.append("**相比上次快照无增长** → 检查是否被限流，或考虑换关键词重发")

    return "\n".join(f"- {n}" for n in notes)


# ── 子命令 ──────────────────────────────────────────────────────────────


def cmd_snapshot(args: argparse.Namespace) -> int:
    records = load_stats_files([Path(p) for p in args.files])
    if not records:
        print("没有解析到任何商品记录，请检查输入文件。", file=sys.stderr)
        return 1

    snapshots = load_snapshots()
    snapshots.append(
        {
            "captured_at": args.at or datetime.now().astimezone().isoformat(timespec="seconds"),
            "items": records,
        }
    )
    save_snapshots(snapshots)

    print(f"已保存快照：{len(records)} 个商品 → {SNAPSHOT_FILE}")
    print(f"历史快照数：{len(snapshots)}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    snapshots = load_snapshots()
    if not snapshots:
        print("还没有快照。先跑 snapshot 子命令。", file=sys.stderr)
        return 1

    current = snapshots[-1]["items"]
    previous = snapshots[-2]["items"] if len(snapshots) > 1 else None

    print(f"# 闲鱼运营数据（{snapshots[-1]['captured_at']}）\n")
    print(render_report(current, previous))
    print()
    print("## 结论\n")
    print(build_analysis(current, previous))
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    snapshots = load_snapshots()
    if len(snapshots) < 2:
        print("至少需要两次快照才能算增量。", file=sys.stderr)
        return 1
    current, previous = snapshots[-1]["items"], snapshots[-2]["items"]
    print(f"对比：{snapshots[-2]['captured_at']} → {snapshots[-1]['captured_at']}\n")
    print(render_report(current, previous))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="闲鱼运营数据转换工具")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("snapshot", help="把 xianyu-skills 的 JSON 存成快照")
    p.add_argument("files", nargs="+", help="JSON 文件路径（可多个）")
    p.add_argument("--at", help="覆盖采集时间（ISO 格式）")
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("report", help="打印复盘表（有历史则带增量）")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("diff", help="只显示最近两次快照的增量")
    p.set_defaults(func=cmd_diff)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
