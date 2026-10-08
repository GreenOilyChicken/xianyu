"""Parse Xianyu search responses into normalized Item records.

This is the most fragile part of the pipeline: item data mostly lives in
`clickParam.args` (clean values), with `exContent` as fallback.  Card
parsing is isolated so a single broken or ad card can never abort a page.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

if __package__:
    from .common import Item, ParseError
else:
    from common import Item, ParseError

_WANT_RE = re.compile(r"([\d.]+)\s*(万?)\s*人想要")
_WEAR_RE = re.compile(
    r"痕迹|划痕|磕碰|掉漆|磨损|瑕疵|成新|\d+\s*新|使用感|成色|起球|发黄|轻微使用|明显使用"
)


def parse_price(parts: list[dict[str, Any]] | None) -> float | None:
    """Price segment array -> yuan.  E.g. [{"text": "¥"}, {"text": "1299"}]."""
    if not parts:
        return None
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    text = text.replace("¥", "").replace("￥", "").replace(",", "").strip()
    mult = 1.0
    if text.endswith("万"):
        mult = 10000.0
        text = text[:-1]
    try:
        return float(text) * mult
    except ValueError:
        return None


def _to_float(v: Any) -> float | None:
    try:
        return float(str(v).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _to_int(v: Any) -> int | None:
    f = _to_float(v)
    return int(f) if f is not None else None


def parse_tag(tag: str | None) -> tuple[bool, bool, int | None]:
    """Parse a tag string like "new/freeship/credit-6".

    Returns (has_new, free_ship, credit_level).
    """
    parts = {t.strip() for t in (tag or "").split("/") if t.strip()}
    has_new = "new" in parts
    free_ship = "freeship" in parts
    credit = None
    for p in parts:
        if p.startswith("credit-"):
            credit = _to_int(p[len("credit-") :])
            break
    return has_new, free_ship, credit


def _fish_tag_texts(ex: dict[str, Any]) -> list[str]:
    ft = ex.get("fishTags")
    if not isinstance(ft, dict):
        return []
    out: list[str] = []
    for zone in ft.values():
        for tag in (zone or {}).get("tagList") or []:
            content = ((tag or {}).get("data") or {}).get("content", "")
            if content:
                out.append(content)
    return out


def parse_condition(tag_texts: list[str], has_new_tag: bool) -> str | None:
    joined = " ".join(tag_texts)
    if "全新" in joined and "几乎全新" not in joined:
        return "全新"
    if has_new_tag:
        return "全新"
    if "几乎全新" in joined or "无痕" in joined or _WEAR_RE.search(joined):
        return "二手"
    return None


def _want_from_texts(tag_texts: list[str]) -> int | None:
    for content in tag_texts:
        m = _WANT_RE.search(content)
        if m:
            val = _to_float(m.group(1))
            if val is not None:
                return int(val * (10000 if m.group(2) else 1))
    return None


def _publish_date(ms: Any) -> str | None:
    v = _to_int(ms)
    if not v:
        return None
    try:
        return datetime.fromtimestamp(v / 1000).date().isoformat()
    except (ValueError, OSError, OverflowError):
        return None


def _normalize_pic(url: Any) -> str | None:
    if not url:
        return None
    url = str(url)
    if url.startswith("//"):
        return "https:" + url
    return url


def item_from_card(card: dict[str, Any]) -> Item | None:
    """Extract one Item from a resultList card; None when unusable."""
    try:
        main = card["data"]["item"]["main"]
    except (KeyError, TypeError):
        return None
    ex = main.get("exContent") or {}
    args = (main.get("clickParam") or {}).get("args") or {}
    item_id = args.get("item_id") or args.get("id") or ex.get("itemId")
    price = _to_float(args.get("displayPrice") or args.get("price"))
    if price is None:
        price = parse_price(ex.get("price"))
    if not item_id or price is None:
        return None
    has_new, free_ship, credit = parse_tag(args.get("tag"))
    tag_texts = _fish_tag_texts(ex)
    want = _want_from_texts(tag_texts)
    if want is None:
        want = _to_int(args.get("wantNum"))
    seller_id = args.get("seller_id")
    return Item(
        item_id=str(item_id),
        title=(ex.get("title") or "").strip(),
        price=price,
        area=ex.get("area"),
        seller=ex.get("userNickName"),
        pic_url=_normalize_pic(ex.get("picUrl")),
        seller_id=str(seller_id) if seller_id else None,
        credit_level=credit,
        condition=parse_condition(tag_texts, has_new),
        free_ship=free_ship,
        publish_time=_publish_date(args.get("publishTime")),
        want_num=want,
        tags=[t for t in tag_texts if t][:20],
    )


def parse_search_response(data: dict[str, Any]) -> tuple[list[Item], int]:
    """Parse a full search response; returns (items, skipped_card_count)."""
    result_list = data.get("resultList")
    if result_list is None:
        raise ParseError(
            "响应缺少 resultList 字段（页面结构可能已变化，"
            "可用 --dump-raw 保留原始响应后对照 references/data_schema.md 排查）"
        )
    items: list[Item] = []
    skipped = 0
    for card in result_list:
        if not isinstance(card, dict):
            skipped += 1
            continue
        item = item_from_card(card)
        if item is None:
            skipped += 1
            continue
        items.append(item)
    return items, skipped
