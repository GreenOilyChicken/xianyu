"""Unified CLI for the xianyu-search skill.

    python scripts/xianyu.py COMMAND --help

Commands: doctor, login, search, analyze, trend, history, batches, export, watch.
See references/api_reference.md for the full contract.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
import time
from pathlib import Path

if __package__:
    from . import doctor as doctor_mod
    from . import login as login_mod
    from .analyze import describe, render_report
    from .common import (
        DEFAULT_DELAY_RANGE,
        MAX_PAGES,
        MIN_WATCH_INTERVAL_SECONDS,
        PUNISH_BACKOFF_SECONDS,
        ROWS_PER_PAGE,
        Item,
        XianyuError,
        db_path,
        default_state_path,
        dump_json_atomic,
        emit_json,
        fmt_price,
        force_utf8_stdio,
        load_json,
        log,
        now_iso,
        raw_dir,
        results_dir,
        slugify,
        timestamp_slug,
    )
    from .export import write_items_csv, write_items_json
    from .login import load_cookies
    from .mtop import MtopClient
    from .myitems import fetch_my_items, _user_id_from_cookies
    from .itemstats import fetch_item_stats, X5secExpiredError
    from .spider import crawl, resolve_sort
    from .store import (
        connect,
        get_batch,
        item_history,
        latest_batch_id,
        list_batches,
        load_items,
        save_batch,
        seen_item_ids,
    )
else:
    import doctor as doctor_mod
    import login as login_mod
    from analyze import describe, render_report
    from common import (
        DEFAULT_DELAY_RANGE,
        MAX_PAGES,
        MIN_WATCH_INTERVAL_SECONDS,
        PUNISH_BACKOFF_SECONDS,
        ROWS_PER_PAGE,
        Item,
        XianyuError,
        db_path,
        default_state_path,
        dump_json_atomic,
        emit_json,
        fmt_price,
        force_utf8_stdio,
        load_json,
        log,
        now_iso,
        raw_dir,
        results_dir,
        slugify,
        timestamp_slug,
    )
    from export import write_items_csv, write_items_json
    from login import load_cookies
    from mtop import MtopClient
    from myitems import fetch_my_items, _user_id_from_cookies
    from itemstats import fetch_item_stats, X5secExpiredError
    from spider import crawl, resolve_sort
    from store import (
        connect,
        get_batch,
        item_history,
        latest_batch_id,
        list_batches,
        load_items,
        save_batch,
        seen_item_ids,
    )

_ITEM_FIELDS = {f.name for f in dataclasses.fields(Item)}


def _items_from_dicts(dicts: list[dict]) -> list[Item]:
    return [Item(**{k: v for k, v in d.items() if k in _ITEM_FIELDS}) for d in dicts]


def _open_conn():
    return connect()


# ------------------------------------------------------------------ search

def cmd_search(args: argparse.Namespace) -> int:
    state_path = Path(args.state) if args.state else default_state_path()
    cookies = load_cookies(state_path)  # raises NotLoggedInError with guidance
    sort_field, sort_value = resolve_sort(args.sort)
    delay = (
        max(0.5, args.delay_min if args.delay_min is not None else DEFAULT_DELAY_RANGE[0]),
        max(0.5, args.delay_max if args.delay_max is not None else DEFAULT_DELAY_RANGE[1]),
    )
    if delay[1] < delay[0]:
        delay = (delay[1], delay[0])

    if args.dump_raw:
        slug = slugify(args.keyword)

        def on_raw(page: int, raw: dict) -> None:
            dump_json_atomic(raw_dir() / f"{slug}_{timestamp_slug()}_p{page}.json", raw)

    else:
        on_raw = None

    client = MtopClient(cookies)
    try:
        summary = crawl(
            client,
            args.keyword,
            args.pages,
            rows=args.rows,
            min_price=args.min_price,
            max_price=args.max_price,
            location=args.location,
            sort_field=sort_field,
            sort_value=sort_value,
            delay=delay,
            punish_backoff=args.punish_backoff,
            on_raw=on_raw,
            quiet=args.quiet,
        )
    finally:
        client.close()

    batch_id = f"{slugify(args.keyword)}_{timestamp_slug()}"
    if not args.no_store:
        conn = _open_conn()
        try:
            save_batch(
                conn,
                batch_id,
                args.keyword,
                summary.items,
                pages=summary.pages_done,
                partial=summary.partial,
                min_price=args.min_price,
                max_price=args.max_price,
                location=args.location,
                note=args.note or "",
            )
        finally:
            conn.close()

    out_path = Path(args.out) if args.out else results_dir() / f"{batch_id}.json"
    payload = {
        "ok": summary.error is None,
        "keyword": args.keyword,
        "batch_id": batch_id,
        "count": summary.item_count,
        "pages_scraped": summary.pages_done,
        "pages_requested": summary.pages_requested,
        "partial": summary.partial,
        "error": summary.error,
        "error_type": summary.error_type,
        "filters": {
            "min_price": args.min_price,
            "max_price": args.max_price,
            "location": args.location,
            "sort": args.sort,
        },
        "items": [it.to_dict() for it in summary.items],
    }
    dump_json_atomic(out_path, payload)

    if args.json:
        emit_json(payload)
    else:
        if summary.error_type == "SessionExpiredError":
            print("❌ 登录已失效，请重新运行 login 扫码登录")
        elif summary.error_type == "RateLimitedError":
            print("⚠️ 触发风控，本次只拿到部分数据（建议冷却 30 分钟以上再试）")
        elif summary.partial:
            print(f"⚠️ 不完整抓取：{summary.error}")
        print(f"关键词：{args.keyword}")
        print(
            f"批次：{batch_id} · 完成 {summary.pages_done}/{summary.pages_requested} 页 · "
            f"商品 {summary.item_count} 条"
        )
        print(f"结果文件：{out_path}")
        if summary.item_count:
            print(f"下一步：运行 `xianyu.py analyze \"{args.keyword}\"` 生成分析报告")
    return 0


# ----------------------------------------------------------------- myitems
def cmd_myitems(args: argparse.Namespace) -> int:
    """List the logged-in account's own on-sale items."""
    state_path = Path(args.state) if args.state else default_state_path()
    cookies = load_cookies(state_path)
    user_id = args.user_id or _user_id_from_cookies(cookies)

    client = MtopClient(cookies)
    try:
        items = fetch_my_items(client, user_id, quiet=args.quiet)
    finally:
        client.close()

    payload = {
        "ok": True,
        "user_id": user_id,
        "count": len(items),
        "items": [it.to_dict() for it in items],
        "captured_at": now_iso(),
    }
    if args.out:
        out_path = Path(args.out)
        dump_json_atomic(out_path, payload)
    if args.json:
        emit_json(payload)
    else:
        print(f"我的在售商品：{len(items)} 个")
        for it in items:
            print(f"  {it.item_id} | ¥{it.price} | {it.title}")
        if args.out:
            print(f"结果文件：{args.out}")
    return 0


# ----------------------------------------------------------------- itemstats
def cmd_itemstats(args: argparse.Namespace) -> int:
    """Fetch browse/want/sold counts for one or more items."""
    state_path = Path(args.state) if args.state else default_state_path()
    cookies = load_cookies(state_path)

    item_ids = list(args.item_ids)
    # If no ids given, pull them from myitems
    if not item_ids:
        user_id = args.user_id or _user_id_from_cookies(cookies)
        client = MtopClient(cookies)
        try:
            items = fetch_my_items(client, user_id, quiet=args.quiet)
        finally:
            client.close()
        item_ids = [it.item_id for it in items]
        if not args.quiet:
            print(f"从 myitems 取到 {len(item_ids)} 个商品，逐个查详情…")

    import time as _time
    results = []
    for i, iid in enumerate(item_ids):
        try:
            stats = fetch_item_stats(cookies, iid)
            results.append(stats)
            if not args.json:
                print(f"  {iid} | 浏览 {stats.browse} | 想要 {stats.want} | 售出 {stats.sold} | {stats.title or ''}")
        except X5secExpiredError as exc:
            if not args.quiet:
                print(f"⚠️ x5sec 失效（第 {i+1} 个商品起）: {exc}", file=sys.stderr)
            # Stop: once x5sec is rejected, the rest will fail too
            break
        except XianyuError as exc:
            if not args.quiet:
                print(f"  {iid} 失败: {exc}", file=sys.stderr)
            results.append(None)
        if i < len(item_ids) - 1:
            _time.sleep(args.delay)

    results_clean = [r for r in results if r is not None]
    payload = {
        "ok": len(results_clean) > 0,
        "count": len(results_clean),
        "total": len(item_ids),
        "items": [r.to_dict() for r in results_clean],
        "captured_at": now_iso(),
    }
    if args.out:
        dump_json_atomic(Path(args.out), payload)
    if args.json:
        emit_json(payload)
    elif args.out:
        print(f"结果文件：{args.out}")
    return 0 if results_clean else 1


# ----------------------------------------------------------------- analyze

def cmd_analyze(args: argparse.Namespace) -> int:
    prev_stats = None
    if args.json_file:
        data = load_json(args.json_file)
        raw_items = data.get("items", data) if isinstance(data, dict) else data
        items = _items_from_dicts(raw_items)
        keyword = args.keyword or "导入数据"
        meta: dict = {}
    else:
        conn = _open_conn()
        try:
            batch = None
            if args.batch:
                batch = get_batch(conn, args.batch)
                if batch is None:
                    raise XianyuError(f"批次不存在：{args.batch}")
            else:
                if not args.keyword:
                    raise XianyuError("需要关键词或 --batch/--json-file")
                batch_id = latest_batch_id(conn, args.keyword)
                if batch_id is None:
                    raise XianyuError(
                        f"本地没有关键词 {args.keyword!r} 的抓取记录，请先 search"
                    )
                batch = get_batch(conn, batch_id)
            assert batch is not None
            keyword = batch["keyword"]
            rows = load_items(
                conn,
                batch_id=batch["id"],
                min_price=args.min_price,
                max_price=args.max_price,
            )
            prev = conn.execute(
                "SELECT id FROM batches WHERE keyword=? AND id<>? "
                "ORDER BY created_at DESC, id DESC LIMIT 1",
                (keyword, batch["id"]),
            ).fetchone()
            if prev is not None:
                prev_rows = load_items(conn, batch_id=prev["id"])
                prev_stats = describe([r["price"] for r in prev_rows])
        finally:
            conn.close()
        items = _items_from_dicts(rows)
        meta = {**batch, "batch_id": batch["id"]}

    report = render_report(keyword, items, meta=meta, bins=args.bins, prev_stats=prev_stats)
    out_path = Path(args.out) if args.out else results_dir() / f"report_{slugify(keyword)}_{timestamp_slug()}.md"
    out_path.write_text(report, encoding="utf-8")

    if args.json:
        emit_json({"ok": True, "keyword": keyword, "report_path": str(out_path), "count": len(items)})
    elif args.quiet:
        print(out_path)
    else:
        print(report)
        print(f"\n> 报告已保存：{out_path}")
    return 0


# ------------------------------------------------------------------- trend

def cmd_trend(args: argparse.Namespace) -> int:
    conn = _open_conn()
    try:
        batches = list_batches(conn, args.keyword, limit=args.last)
        if not batches:
            raise XianyuError(f"本地没有关键词 {args.keyword!r} 的抓取记录")
        batches = list(reversed(batches))  # chronological
        stats_rows = []
        prev = None
        for b in batches:
            rows = load_items(conn, batch_id=b["id"])
            s = describe([r["price"] for r in rows])
            delta = ""
            if prev is not None and s["median"] is not None and prev["median"]:
                pct = (s["median"] - prev["median"]) / prev["median"] * 100
                delta = f"{'+' if pct >= 0 else ''}{pct:.0f}%"
            stats_rows.append(
                [
                    b["created_at"][:16],
                    b["id"],
                    str(s["count"]),
                    fmt_price(s["min"]),
                    fmt_price(s["median"]),
                    fmt_price(s["max"]),
                    delta,
                    "部分" if b["partial"] else "完整",
                ]
            )
            prev = s
    finally:
        conn.close()

    header = "| 时间 | 批次 | 数量 | 最低 | 中位 | 最高 | 中位变化 | 状态 |\n|---|---|---|---|---|---|---|---|"
    table = "\n".join("| " + " | ".join(r) + " |" for r in stats_rows)
    text = f"# {args.keyword} 行情趋势\n\n{header}\n{table}\n"
    if args.json:
        emit_json({"ok": True, "keyword": args.keyword, "rows": stats_rows})
    else:
        print(text)
    return 0


# ----------------------------------------------------------------- history

def cmd_history(args: argparse.Namespace) -> int:
    conn = _open_conn()
    try:
        rows = item_history(conn, args.query)
    finally:
        conn.close()
    if not rows:
        raise XianyuError(f"没有找到 {args.query!r} 相关的历史记录")
    items = [
        [r["crawled_at"][:16], r["batch_id"], r["title"][:36], fmt_price(r["price"])]
        for r in rows
    ]
    text = (
        f"# {args.query} 价格历史\n\n"
        "| 时间 | 批次 | 标题 | 价格 |\n|---|---|---|---|\n"
        + "\n".join("| " + " | ".join(i) + " |" for i in items)
        + "\n"
    )
    if args.json:
        emit_json({"ok": True, "rows": rows})
    else:
        print(text)
    return 0


# ----------------------------------------------------------------- batches

def cmd_batches(args: argparse.Namespace) -> int:
    conn = _open_conn()
    try:
        rows = list_batches(conn, args.keyword, limit=args.limit)
    finally:
        conn.close()
    if args.json:
        emit_json({"ok": True, "batches": rows})
        return 0
    if not rows:
        print("暂无抓取记录。")
        return 0
    table = [
        [r["created_at"][:16], r["id"], r["keyword"], str(r["item_count"]),
         str(r["pages"]), "部分" if r["partial"] else "完整", r.get("note") or ""]
        for r in rows
    ]
    print("| 时间 | 批次 | 关键词 | 商品数 | 页数 | 状态 | 备注 |")
    print("|---|---|---|---|---|---|---|")
    for row in table:
        print("| " + " | ".join(str(c).replace("|", "\\|") for c in row) + " |")
    return 0


# ------------------------------------------------------------------ export

def cmd_export(args: argparse.Namespace) -> int:
    conn = _open_conn()
    try:
        if args.trend:
            batches = list_batches(conn, args.keyword, limit=args.last)
            rows = []
            for b in reversed(batches):
                items = load_items(conn, batch_id=b["id"])
                s = describe([r["price"] for r in items])
                rows.append(
                    {
                        "time": b["created_at"],
                        "batch_id": b["id"],
                        "keyword": b["keyword"],
                        "count": s["count"],
                        "min": s["min"],
                        "median": s["median"],
                        "max": s["max"],
                        "mean": s["mean"],
                        "p25": s["p25"],
                        "p75": s["p75"],
                    }
                )
        else:
            batch = None
            if args.batch:
                batch = get_batch(conn, args.batch)
                if batch is None:
                    raise XianyuError(f"批次不存在：{args.batch}")
            else:
                if not args.keyword:
                    raise XianyuError("需要关键词或 --batch")
                batch_id = latest_batch_id(conn, args.keyword)
                if batch_id is None:
                    raise XianyuError(f"本地没有关键词 {args.keyword!r} 的抓取记录")
                batch = get_batch(conn, batch_id)
            assert batch is not None
            rows = load_items(conn, batch_id=batch["id"])
    finally:
        conn.close()

    if args.trend:
        if args.csv:
            import csv

            with open(args.csv, "w", newline="", encoding="utf-8-sig") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else [])
                if rows:
                    w.writeheader()
                    w.writerows(rows)
        else:
            print(__import__("json").dumps(rows, ensure_ascii=False, indent=2))
        return 0

    base = slugify(args.keyword or args.batch)
    if args.csv:
        write_items_csv(args.csv, rows)
        print(f"CSV 已导出：{args.csv}")
    if args.json:
        write_items_json(args.json, rows)
        print(f"JSON 已导出：{args.json}")
    if not args.csv and not args.json:
        out = Path(args.out) if args.out else Path(f"{base}_items.csv")
        write_items_csv(out, rows)
        print(f"CSV 已导出：{out}")
    return 0


# ------------------------------------------------------------------- watch

def cmd_watch(args: argparse.Namespace) -> int:
    interval = max(args.interval, MIN_WATCH_INTERVAL_SECONDS)
    if args.interval < MIN_WATCH_INTERVAL_SECONDS:
        log(f"间隔已提升到最小值 {MIN_WATCH_INTERVAL_SECONDS}s（30 分钟），避免触发风控")
    state_path = Path(args.state) if args.state else default_state_path()
    cookies = load_cookies(state_path)
    runs = 0
    while args.max_runs is None or runs < args.max_runs:
        runs += 1
        log(f"第 {runs} 轮抓取…")
        client = MtopClient(cookies)
        conn = _open_conn()
        try:
            seen = seen_item_ids(conn)
            summary = crawl(
                client,
                args.keyword,
                args.pages,
                rows=args.rows,
                min_price=args.min_price,
                max_price=args.max_price,
                location=args.location,
                quiet=True,
            )
            batch_id = f"{slugify(args.keyword)}_{timestamp_slug()}"
            save_batch(
                conn,
                batch_id,
                args.keyword,
                summary.items,
                pages=summary.pages_done,
                partial=summary.partial,
                min_price=args.min_price,
                max_price=args.max_price,
                location=args.location,
            )
        finally:
            client.close()
            conn.close()
        new_items = [it for it in summary.items if it.item_id not in seen]
        payload = {
            "ok": summary.error is None,
            "run": runs,
            "keyword": args.keyword,
            "batch_id": batch_id,
            "count": summary.item_count,
            "new_count": len(new_items),
            "new_items": [it.to_dict() for it in new_items],
            "error": summary.error,
            "error_type": summary.error_type,
        }
        if args.json:
            emit_json(payload)
        else:
            print(f"[{time.strftime('%H:%M:%S')}] {args.keyword}："
                  f"抓到 {summary.item_count} 条，新增 {len(new_items)} 条")
            for it in new_items[:20]:
                print(f"  · {fmt_price(it.price)} {it.title[:50]} ({it.url})")
        if args.max_runs is None or runs < args.max_runs:
            log(f"等待 {interval // 60} 分钟后进行下一轮（Ctrl+C 退出）")
            time.sleep(interval)
    return 0


# ------------------------------------------------------------------- main

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xianyu.py", description="闲鱼数据抓取与分析 CLI"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("doctor", help="环境自检（只读）")

    p = sub.add_parser("login", help="扫码登录（一次性，需要浏览器）")
    p.add_argument("--state", default=None)
    p.add_argument("--timeout", type=float, default=300)
    p.add_argument("--channel", default=None)
    p.add_argument("--cookie-stdin", action="store_true")
    p.add_argument("--quiet", action="store_true")

    p = sub.add_parser("search", help="按关键词抓取搜索列表")
    p.add_argument("keyword")
    p.add_argument("--pages", "-p", type=int, default=3, help=f"页数（默认 3，上限 {MAX_PAGES}）")
    p.add_argument("--rows", type=int, default=ROWS_PER_PAGE)
    p.add_argument("--min-price", type=float, default=None)
    p.add_argument("--max-price", type=float, default=None)
    p.add_argument("--location", default=None, help="地区子串过滤，如 上海")
    p.add_argument("--sort", default="default", choices=["default", "time", "price-asc", "price-desc"])
    p.add_argument("--state", default=None)
    p.add_argument("--delay-min", type=float, default=None)
    p.add_argument("--delay-max", type=float, default=None)
    p.add_argument("--punish-backoff", type=float, default=PUNISH_BACKOFF_SECONDS)
    p.add_argument("--dump-raw", action="store_true", help="保存每页原始响应到数据目录 raw/")
    p.add_argument("--no-store", action="store_true", help="不入库，只写结果 JSON")
    p.add_argument("--note", default="")
    p.add_argument("--out", default=None, help="结果 JSON 输出路径")
    p.add_argument("--json", action="store_true", help="stdout 输出机器可读 JSON")
    p.add_argument("--quiet", action="store_true")

    p = sub.add_parser("myitems", help="列出我自己的在售商品")
    p.add_argument("--user-id", default=None, help="覆盖 user_id（默认从 cookie 的 unb 取）")
    p.add_argument("--state", default=None)
    p.add_argument("--out", default=None, help="结果 JSON 输出路径")
    p.add_argument("--json", action="store_true")
    p.add_argument("--quiet", action="store_true")

    p = sub.add_parser("itemstats", help="查商品浏览/想要/售出数（需要 x5sec）")
    p.add_argument("item_ids", nargs="*", help="商品 ID（不给则用 myitems 全量）")
    p.add_argument("--user-id", default=None)
    p.add_argument("--state", default=None)
    p.add_argument("--out", default=None, help="结果 JSON 输出路径")
    p.add_argument("--delay", type=float, default=3.0, help="每个商品间隔秒数（默认 3）")
    p.add_argument("--json", action="store_true")
    p.add_argument("--quiet", action="store_true")

    p = sub.add_parser("analyze", help="生成行情分析报告")
    p.add_argument("keyword", nargs="?", default=None)
    p.add_argument("--batch", default=None)
    p.add_argument("--json-file", default=None, help="直接分析一个结果 JSON 文件")
    p.add_argument("--min-price", type=float, default=None)
    p.add_argument("--max-price", type=float, default=None)
    p.add_argument("--bins", type=int, default=10)
    p.add_argument("--out", default=None)
    p.add_argument("--json", action="store_true")
    p.add_argument("--quiet", action="store_true")

    p = sub.add_parser("trend", help="多批次行情趋势")
    p.add_argument("keyword")
    p.add_argument("--last", type=int, default=10)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("history", help="单商品跨批次价格历史")
    p.add_argument("query", help="item_id 或标题片段")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("batches", help="列出抓取批次")
    p.add_argument("keyword", nargs="?", default=None)
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("export", help="导出商品明细 / 趋势")
    p.add_argument("keyword", nargs="?", default=None)
    p.add_argument("--batch", default=None)
    p.add_argument("--csv", default=None)
    p.add_argument("--json", default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--trend", action="store_true")
    p.add_argument("--last", type=int, default=10)

    p = sub.add_parser("watch", help="周期性抓取并报告新增商品")
    p.add_argument("keyword")
    p.add_argument("--interval", type=int, default=MIN_WATCH_INTERVAL_SECONDS)
    p.add_argument("--max-runs", type=int, default=None)
    p.add_argument("--pages", "-p", type=int, default=1)
    p.add_argument("--rows", type=int, default=ROWS_PER_PAGE)
    p.add_argument("--min-price", type=float, default=None)
    p.add_argument("--max-price", type=float, default=None)
    p.add_argument("--location", default=None)
    p.add_argument("--state", default=None)
    p.add_argument("--json", action="store_true")

    return parser


COMMANDS = {
    "doctor": doctor_mod.run,
    "login": login_mod.run,
    "search": cmd_search,
    "myitems": cmd_myitems,
    "itemstats": cmd_itemstats,
    "analyze": cmd_analyze,
    "trend": cmd_trend,
    "history": cmd_history,
    "batches": cmd_batches,
    "export": cmd_export,
    "watch": cmd_watch,
}


def main(argv: list[str] | None = None) -> int:
    force_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except XianyuError as exc:
        emit_json({"ok": False, "error": str(exc), "error_type": type(exc).__name__})
        return 2
    except KeyboardInterrupt:
        emit_json({"ok": False, "error": "已取消", "error_type": "KeyboardInterrupt"})
        return 130
    except ValueError as exc:
        emit_json({"ok": False, "error": str(exc), "error_type": "ValueError"})
        return 2


if __name__ == "__main__":
    sys.exit(main())
