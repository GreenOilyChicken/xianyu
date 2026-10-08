"""Paginated Xianyu search crawling with polite delays and risk-control handling.

Risk control is respected, never bypassed: on a punish response the crawler
waits out a backoff window and retries the page once, then stops and keeps
whatever data was already collected.
"""

from __future__ import annotations

import random
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

if __package__:
    from .common import (
        DEFAULT_DELAY_RANGE,
        MAX_PAGES,
        ROWS_PER_PAGE,
        SEARCH_API,
        Item,
        RateLimitedError,
        XianyuError,
        log,
    )
    from .parser import parse_search_response
else:
    from common import (
        DEFAULT_DELAY_RANGE,
        MAX_PAGES,
        ROWS_PER_PAGE,
        SEARCH_API,
        Item,
        RateLimitedError,
        XianyuError,
        log,
    )
    from parser import parse_search_response

# Best-effort sort mapping.  The web UI's 综合/最新/价格 controls translate to
# these field/value pairs; the server may ignore them, so treat sort as a hint.
SORT_MAP: dict[str, tuple[str, str]] = {
    "default": ("", ""),
    "time": ("addTime", "desc"),
    "price-asc": ("addPrice", "asc"),
    "price-desc": ("addPrice", "desc"),
}


def resolve_sort(value: str | None) -> tuple[str, str]:
    if not value or value == "default":
        return "", ""
    if value not in SORT_MAP:
        raise ValueError(f"未知排序方式 {value!r}，可选：{', '.join(SORT_MAP)}")
    return SORT_MAP[value]


@dataclass
class CrawlSummary:
    keyword: str = ""
    pages_requested: int = 0
    pages_done: int = 0
    item_count: int = 0
    partial: bool = False
    items: list[Item] = field(default_factory=list)
    error: str | None = None
    error_type: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["items"] = [it.to_dict() for it in self.items]
        return d


def build_search_data(
    keyword: str,
    page: int,
    rows: int = ROWS_PER_PAGE,
    sort_field: str = "",
    sort_value: str = "",
) -> dict[str, Any]:
    return {
        "pageNumber": page,
        "keyword": keyword,
        "fromFilter": False,
        "rowsPerPage": rows,
        "sortValue": sort_value,
        "sortField": sort_field,
        "customDistance": "",
        "gps": "",
        "propValueStr": {},
        "customGps": "",
        "searchReqFromPage": "pcSearch",
        "extraFilterValue": "{}",
        "userPositionJson": "{}",
    }


def apply_local_filters(
    items: list[Item],
    min_price: float | None = None,
    max_price: float | None = None,
    location: str | None = None,
) -> list[Item]:
    """Filter server results locally (price bounds inclusive, location substring)."""
    out: list[Item] = []
    for it in items:
        if min_price is not None and it.price < min_price:
            continue
        if max_price is not None and it.price > max_price:
            continue
        if location and location not in (it.area or ""):
            continue
        out.append(it)
    return out


def crawl(
    client,
    keyword: str,
    pages: int,
    rows: int = ROWS_PER_PAGE,
    min_price: float | None = None,
    max_price: float | None = None,
    location: str | None = None,
    sort_field: str = "",
    sort_value: str = "",
    delay: tuple[float, float] = DEFAULT_DELAY_RANGE,
    punish_backoff: float = 60.0,
    on_page: Callable[[int, list[Item]], None] | None = None,
    on_raw: Callable[[int, dict[str, Any]], None] | None = None,
    quiet: bool = False,
) -> CrawlSummary:
    pages = max(1, min(int(pages), MAX_PAGES))
    summary = CrawlSummary(keyword=keyword, pages_requested=pages)

    def fetch(page: int) -> dict[str, Any]:
        return client.request(
            SEARCH_API,
            data=build_search_data(keyword, page, rows, sort_field, sort_value),
        )

    seen: set[str] = set()
    for page in range(1, pages + 1):
        try:
            raw = fetch(page)
        except RateLimitedError:
            if not quiet:
                log(f"第 {page} 页触发风控，退避 {punish_backoff:.0f}s 后重试一次…")
            time.sleep(punish_backoff)
            try:
                raw = fetch(page)
            except RateLimitedError as exc:
                summary.partial = True
                summary.error = str(exc)
                summary.error_type = "RateLimitedError"
                break
        except XianyuError as exc:
            summary.partial = True
            summary.error = str(exc)
            summary.error_type = type(exc).__name__
            break

        if on_raw is not None:
            on_raw(page, raw)

        # Last-page check uses the RAW card count, not parsed items: ad cards
        # can be skipped by the parser and make a full page look short.
        raw_len = len(raw.get("resultList") or [])
        items, skipped = parse_search_response(raw)
        if skipped and not quiet:
            log(f"  (第 {page} 页跳过 {skipped} 张无法解析的卡片：广告/运营位或结构异常)")
        items = apply_local_filters(items, min_price, max_price, location)
        fresh = [it for it in items if it.item_id not in seen]
        seen.update(it.item_id for it in fresh)
        summary.items.extend(fresh)
        summary.item_count += len(fresh)
        if on_page is not None:
            on_page(page, fresh)

        # An empty raw page ends the run without counting as a scraped page;
        # a short raw page (fewer cards than requested) means the last page.
        if raw_len == 0:
            break
        summary.pages_done = page
        if raw_len < rows:
            break
        if page < pages:
            time.sleep(random.uniform(*delay))
    return summary
