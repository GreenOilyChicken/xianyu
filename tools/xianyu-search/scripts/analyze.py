"""Multi-dimension analysis of Xianyu listings and Markdown report rendering.

Pure functions: they take lists of Item and return dicts/text, so custom
tooling can import and extend them (see references/data_schema.md).  The
attribute pattern table at the bottom is the natural customization point.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from datetime import date, datetime
from statistics import mean, median, pstdev, quantiles
from typing import Any, Iterable

if __package__:
    from .common import Item, fmt_price
else:
    from common import Item, fmt_price

# ---------------------------------------------------------------- statistics

def describe(prices: list[float]) -> dict[str, float | int | None]:
    """Summary statistics for a price sample."""
    n = len(prices)
    if n == 0:
        return {"count": 0, "mean": None, "median": None, "p25": None,
                "p75": None, "min": None, "max": None, "stdev": None}
    q = quantiles(prices, n=4, method="inclusive")  # [p25, p50, p75]
    return {
        "count": n,
        "mean": mean(prices),
        "median": median(prices),
        "p25": q[0],
        "p75": q[2],
        "min": min(prices),
        "max": max(prices),
        "stdev": pstdev(prices),
    }


def build_histogram(
    prices: list[float], bins: int = 10, width: int = 40
) -> tuple[list[str], list[tuple[float, float]]]:
    """ASCII histogram lines plus the (lo, hi) bin edges."""
    if not prices:
        return [], []
    lo, hi = min(prices), max(prices)
    if hi - lo < 1e-9:
        hi = lo + 1
    step = (hi - lo) / bins
    edges: list[tuple[float, float]] = []
    counts: list[int] = []
    for i in range(bins):
        b_lo = lo + i * step
        b_hi = b_lo + step
        if i == bins - 1:
            b_hi = hi + 1e-9  # include max value in the last bin
        edges.append((b_lo, b_hi))
        counts.append(sum(1 for p in prices if b_lo <= p < b_hi))
    peak = max(counts) or 1
    lines = []
    for (b_lo, b_hi), c in zip(edges, counts):
        bar = "█" * max(0, round(c / peak * width))
        label_lo = f"{b_lo:,.0f}" if b_lo >= 100 else f"{b_lo:.2f}"
        label_hi = f"{b_hi:,.0f}" if b_hi >= 100 else f"{b_hi:.2f}"
        lines.append(f"`{label_lo} ~ {label_hi}` | {c:>4} | {bar}")
    return lines, edges


# ------------------------------------------------------------- item grouping

def credit_bucket(level: int | None) -> str:
    if level is None:
        return "未知"
    if level >= 7:
        return "高(7+)"
    if level >= 4:
        return "中(4-6)"
    return "低(1-3)"


def recency_bucket(publish_time: str | None, today: date | None = None) -> str:
    """Bucket a YYYY-MM-DD publish date relative to today."""
    if not publish_time:
        return "未知"
    try:
        d = datetime.strptime(publish_time, "%Y-%m-%d").date()
    except ValueError:
        return "未知"
    today = today or date.today()
    days = (today - d).days
    if days < 0:
        return "未知"
    if days == 0:
        return "今天"
    if days <= 3:
        return "3天内"
    if days <= 7:
        return "7天内"
    return "更早"


# ------------------------------------------------------- attribute scanning
#
# Customization point: extend or trim this table to match the product
# categories you care about.  Patterns are matched against listing titles.

ATTR_PATTERNS: list[tuple[str, str]] = [
    ("存储容量", r"\d+\s*[gGtT][bB]?"),
    ("运行内存", r"\d+\s*[gG](?!\s*[bB])"),
    ("国行", r"国行|国版"),
    ("港版", r"港版|港行"),
    ("美版", r"美版|美行"),
    ("日版", r"日版|日行"),
    ("其他版本", r"韩版|欧版|英版|澳版|加版|台版"),
    ("全新/未拆", r"全新|未拆|未激活"),
    ("几乎全新", r"几乎全新|99新|95新|9成新|九五新"),
    ("电池", r"电池"),
    ("官换/官翻", r"官换|官翻|官方翻新"),
    ("维修史", r"维修|换过|修过|拆过|进水"),
    ("包邮", r"包邮"),
    ("发票/在保", r"发票|有票|在保|保修|保内"),
    ("裸机", r"裸机"),
    ("急出", r"急出|急售|急用钱"),
    ("可刀", r"可刀|可小刀|接刀"),
]


def attr_counts(titles: list[str]) -> list[tuple[str, int, float]]:
    """(label, hit_count, hit_rate) for each attribute pattern."""
    n = len(titles) or 1
    out = []
    for label, pattern in ATTR_PATTERNS:
        rx = re.compile(pattern)
        hits = sum(1 for t in titles if rx.search(t or ""))
        out.append((label, hits, hits / n))
    return out


# ------------------------------------------------------------ risk & deals

def risk_flags(
    items: list[Item], stats: dict[str, Any]
) -> list[dict[str, Any]]:
    """Listings that look suspiciously cheap (possible scams / bait prices).

    Two independent criteria:
    - statistical: below P25 - 1.5*IQR (outlier of the normal spread);
    - bait floor: below max(10, 20% of median) (占位/引流价 like "1元起").
    """
    if stats["count"] < 10 or stats["p25"] is None or stats["median"] is None:
        return []
    iqr = (stats["p75"] or 0) - (stats["p25"] or 0)
    fence = stats["p25"] - 1.5 * iqr
    bait_floor = max(10.0, stats["median"] * 0.2)
    suspects = [it for it in items if it.price < fence or it.price < bait_floor]
    suspects.sort(key=lambda it: it.price)
    return [
        {
            "item_id": it.item_id,
            "title": it.title,
            "price": it.price,
            "seller": it.seller,
            "credit_level": it.credit_level,
            "url": it.url,
        }
        for it in suspects[:20]
    ]


def deal_candidates(
    items: list[Item], stats: dict[str, Any], exclude_ids: set[str] | None = None
) -> list[Item]:
    """Below-P25 listings from trustworthy sellers: worth a manual look."""
    exclude_ids = exclude_ids or set()
    if stats["count"] < 5 or stats["p25"] is None:
        return []
    cheap = [
        it
        for it in items
        if it.price <= stats["p25"] and it.item_id not in exclude_ids
    ]
    scored: list[tuple[float, Item]] = []
    for it in cheap:
        score = 0.0
        if it.credit_level is not None and it.credit_level >= 5:
            score += 3
        if it.condition == "全新":
            score += 2
        if it.free_ship:
            score += 0.5
        if it.want_num is not None and it.want_num >= 3:
            score += 1
        if score >= 2.5:
            scored.append((score, it))
    scored.sort(key=lambda pair: (-pair[0], pair[1].price))
    return [it for _, it in scored[:10]]


# ------------------------------------------------------------ report text

def _table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for row in rows:
        cells = [str(c).replace("|", "\\|").replace("\n", " ") for c in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def render_report(
    keyword: str,
    items: list[Item],
    meta: dict[str, Any] | None = None,
    bins: int = 10,
    prev_stats: dict[str, Any] | None = None,
) -> str:
    """Render the full Markdown analysis report."""
    meta = meta or {}
    prices = [it.price for it in items]
    stats = describe(prices)
    hist_lines, _ = build_histogram(prices, bins=bins)
    n = len(items)

    lines: list[str] = []
    lines.append(f"# 闲鱼行情分析报告：{keyword}")
    created = meta.get("created_at") or datetime.now().isoformat(timespec="seconds")
    note = f"，备注：{meta['note']}" if meta.get("note") else ""
    lines.append(
        f"> 批次 `{meta.get('batch_id', '-')}` · 抓取 {meta.get('pages', '-')} 页 · "
        f"共 {n} 条 · 时间 {created}{note}"
    )
    filters = []
    if meta.get("min_price") is not None:
        filters.append(f"最低价 ≥ {fmt_price(meta['min_price'])}")
    if meta.get("max_price") is not None:
        filters.append(f"最高价 ≤ {fmt_price(meta['max_price'])}")
    if meta.get("location"):
        filters.append(f"地区含 {meta['location']}")
    if filters:
        lines.append(f"> 过滤条件：{'，'.join(filters)}")
    lines.append("")

    # 1. price
    lines.append("## 1. 价格概况")
    if n == 0:
        lines.append("本次没有采集到商品，请扩大页数或调整过滤条件。")
    else:
        lines.append(
            _table(
                ["指标", "数值"],
                [
                    ["样本数", str(stats["count"])],
                    ["均值", fmt_price(stats["mean"])],
                    ["中位数", fmt_price(stats["median"])],
                    ["P25 / P75", f"{fmt_price(stats['p25'])} / {fmt_price(stats['p75'])}"],
                    ["最低 / 最高", f"{fmt_price(stats['min'])} / {fmt_price(stats['max'])}"],
                    ["标准差", fmt_price(stats["stdev"])],
                ],
            )
        )
        lines.append("")
        lines.append("**价格分布**")
        lines.append("")
        lines.append("| 价格区间 | 数量 | 分布 |")
        lines.append("|---|---|---|")
        lines.extend(hist_lines)
        lines.append("")
        groups: dict[str, list[float]] = {}
        for it in items:
            groups.setdefault(it.condition or "未知", []).append(it.price)
        if len(groups) > 1:
            lines.append("**按成色分组**")
            rows = []
            for label in ("全新", "二手", "未知"):
                if label in groups:
                    g = groups[label]
                    rows.append(
                        [
                            label,
                            str(len(g)),
                            fmt_price(median(g)),
                            fmt_price(min(g)) + " ~ " + fmt_price(max(g)),
                        ]
                    )
            lines.append(_table(["成色", "数量", "中位价", "价格范围"], rows))
            lines.append("")

    # 2. composition
    lines.append("## 2. 商品构成")
    cond_counter = Counter(it.condition or "未知" for it in items)
    ship = sum(1 for it in items if it.free_ship)
    lines.append(
        f"- 成色：全新 {cond_counter.get('全新', 0)} · 二手 {cond_counter.get('二手', 0)} · 未知 {cond_counter.get('未知', 0)}"
    )
    lines.append(f"- 包邮：{ship}/{n}（{ship / n * 100:.0f}%）" if n else "- 包邮：无数据")
    lines.append("")
    attrs = [a for a in attr_counts([it.title for it in items]) if a[1] > 0]
    if attrs:
        lines.append("**标题属性命中**（同一商品可命中多项）")
        lines.append(_table(["属性", "命中数", "占比"], [
            [label, str(hits), f"{rate * 100:.0f}%"] for label, hits, rate in attrs
        ]))
        lines.append("")

    # 3. sellers
    lines.append("## 3. 卖家与信用")
    credit_counter = Counter(credit_bucket(it.credit_level) for it in items)
    lines.append(
        "信用分布：" + " · ".join(
            f"{k} {credit_counter.get(k, 0)}" for k in ("高(7+)", "中(4-6)", "低(1-3)", "未知")
        )
    )
    seller_map: dict[str, list[Item]] = {}
    for it in items:
        seller_map.setdefault(it.seller or it.seller_id or "未知卖家", []).append(it)
    top_sellers = sorted(seller_map.items(), key=lambda kv: -len(kv[1]))[:10]
    multi = [(s, lst) for s, lst in top_sellers if len(lst) >= 2]
    if multi:
        rows = []
        for seller, lst in multi:
            prices = [it.price for it in lst]
            rows.append(
                [
                    seller,
                    str(len(lst)),
                    credit_bucket(lst[0].credit_level),
                    fmt_price(min(prices)) + " ~ " + fmt_price(max(prices)),
                ]
            )
        lines.append("")
        lines.append("**挂牌最多的卖家**（≥2 件，注意批量铺货的商家号）")
        lines.append(_table(["卖家", "挂牌数", "信用", "价格范围"], rows))
        lines.append("")

    # 4. area & time
    lines.append("## 4. 地区与时效")
    area_counter = Counter(it.area or "未知" for it in items)
    lines.append("地区分布 Top：" + " · ".join(
        f"{a} {c}" for a, c in area_counter.most_common(10)
    ))
    lines.append("")
    rec_counter = Counter(recency_bucket(it.publish_time) for it in items)
    lines.append(
        "上架时间：" + " · ".join(
            f"{k} {rec_counter.get(k, 0)}" for k in ("今天", "3天内", "7天内", "更早", "未知")
        )
    )
    lines.append("")

    # 5. heat
    lines.append("## 5. 热度（想要人数）")
    wanted = sorted(
        (it for it in items if it.want_num is not None and it.want_num > 0),
        key=lambda it: -it.want_num,
    )[:10]
    if wanted:
        lines.append(_table(["标题", "价格", "想要"], [
            [it.title[:40], fmt_price(it.price), str(it.want_num)] for it in wanted
        ]))
    else:
        lines.append("本批次没有采集到想要人数数据。")
    lines.append("")

    # 6. risk
    lines.append("## 6. 风险提示")
    suspects = risk_flags(items, stats)
    if suspects:
        lines.append(
            f"⚠️ 发现 {len(suspects)} 条**异常低价**商品（低于统计下界，可能存在标价陷阱、"
            "引流行骗或瑕疵隐瞒，交易前务必让卖家说明实价）："
        )
        lines.append("")
        lines.append(_table(["标题", "价格", "卖家", "信用"], [
            [s["title"][:40], fmt_price(s["price"]), s["seller"] or "-", credit_bucket(s["credit_level"])]
            for s in suspects
        ]))
        lines.append("")
        lines.append("> 异常低价判定：低于 P25 − 1.5×IQR（统计下界），或低于 max(10, 中位价×20%)（占位/引流价）。")
    else:
        lines.append("本批次未发现统计意义上的异常低价。")
    lines.append("")

    # 7. deals
    lines.append("## 7. 捡漏候选（供人工核实）")
    deals = deal_candidates(
        items, stats, exclude_ids={s["item_id"] for s in suspects}
    )
    if deals:
        lines.append(
            "以下商品价格在 P25 以内且卖家信用较好/成色较新，建议点进商品页人工核实细节："
        )
        lines.append("")
        lines.append(_table(["标题", "价格", "卖家", "信用", "成色", "想要", "链接"], [
            [
                it.title[:30],
                fmt_price(it.price),
                it.seller or "-",
                credit_bucket(it.credit_level),
                it.condition or "-",
                str(it.want_num or 0),
                f"[查看]({it.url})",
            ]
            for it in deals
        ]))
    else:
        lines.append("本批次没有同时满足「低价 + 高信用/新成色」的商品。")
    lines.append("")

    # 8. trend vs previous batch
    if prev_stats is not None and prev_stats.get("count"):
        lines.append("## 8. 与上一批次对比")
        cur, pre = stats["median"], prev_stats["median"]
        delta = ""
        if cur is not None and pre:
            pct = (cur - pre) / pre * 100
            delta = f"（{'↑' if pct >= 0 else '↓'} {abs(pct):.0f}%）"
        lines.append(
            f"- 样本数：{prev_stats['count']} → {stats['count']}；"
            f"中位价：{fmt_price(pre)} → {fmt_price(cur)}{delta}"
        )
        lines.append("")

    # 9. conclusion
    lines.append("## 9. 结论与建议")
    if n == 0:
        lines.append("暂无数据，无法给出结论。")
    else:
        bullets: list[str] = []
        if stats["mean"] and stats["median"]:
            if stats["mean"] > stats["median"] * 1.1:
                bullets.append(
                    f"均值（{fmt_price(stats['mean'])}）明显高于中位数（{fmt_price(stats['median'])}），"
                    "少数高价商品拉高了整体水平，实际主流价位看中位数更靠谱。"
                )
            elif stats["median"] > stats["mean"] * 1.1:
                bullets.append("中位数高于均值，低价商品占比较高，注意甄别低价陷阱。")
        if stats["p25"] is not None and stats["p75"] is not None:
            bullets.append(
                f"主流成交价位集中在 {fmt_price(stats['p25'])} ~ {fmt_price(stats['p75'])} 之间，"
                "议价时可以这个区间为参考。"
            )
        new_rate = cond_counter.get("全新", 0) / n
        if new_rate > 0.3:
            bullets.append(f"全新商品占比 {new_rate * 100:.0f}%，全新与二手价差明显，按需选择成色档位。")
        if suspects:
            bullets.append("存在异常低价商品：远低于行情的价格多为引流或诈骗话术，坚持平台内交易、不提前转账。")
        else:
            bullets.append("价格分布正常，未见明显异常低价。")
        if wanted:
            hot = wanted[0]
            bullets.append(
                f"热度最高的商品是「{hot.title[:30]}」（{hot.want_num} 人想要），需求集中，可能更容易成交。"
            )
        bullets.append(
            "数据来自本次真实抓取，仅反映当前在售列表；成色、保修、真伪等信息请以商品页和卖家沟通为准，"
            "交易风险自担。"
        )
        lines.extend(f"- {b}" for b in bullets)
    lines.append("")

    if meta.get("partial"):
        lines.append("> ⚠️ 本批次为不完整抓取（中途触发风控或接口异常），数据可能只覆盖部分页面。")

    return "\n".join(lines)
