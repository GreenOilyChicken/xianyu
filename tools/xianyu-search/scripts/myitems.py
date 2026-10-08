"""Fetch the current account's own listings via mtop.idle.web.xyh.item.list.

This is the "my items" capability the upstream xianyu-search skill does not
ship: it only searches other sellers' goods. Here we call the same mtop
transport (MtopClient) against the personal listing endpoint the goofish web
client itself uses, paging through every on-sale item for the logged-in user.

The endpoint returns card metadata (id, title, price, pic, status) but NOT
view/want counts - those live on the item-detail endpoint, which is tracked
separately. This module's job is the stable inventory list: which items are
mine, their ids, titles, prices, and on-sale status.

Usage as a library:

    from login import load_cookies
    from mtop import MtopClient
    from myitems import fetch_my_items

    cookies = load_cookies("~/.xianyu-data/storage_state.json")
    with MtopClient(cookies) as client:
        items = fetch_my_items(client, user_id="<你的用户ID>")
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

if __package__:
    from .common import RateLimitedError, XianyuError, log
else:
    from common import RateLimitedError, XianyuError, log

MY_ITEMS_API = "mtop.idle.web.xyh.item.list"
PAGE_SIZE = 20  # server caps pageSize at 20 (FAIL_BIZ_FORBIDDEN above it)
MAX_PAGES = 50


@dataclass
class MyItem:
    """One of the logged-in user's own listings."""

    item_id: str
    title: str
    price: str
    pic_url: str | None = None
    status: int | None = None
    url: str = ""

    def to_dict(self) -> dict:
        d = {"item_id": self.item_id, "title": self.title, "price": self.price}
        if self.pic_url:
            d["pic_url"] = self.pic_url
        if self.status is not None:
            d["status"] = self.status
        d["url"] = self.url or f"https://www.goofish.com/item?id={self.item_id}"
        return d


def _card_to_item(card: dict[str, Any]) -> MyItem | None:
    cd = card.get("cardData") or {}
    if not isinstance(cd, dict):
        return None
    item_id = str(cd.get("id") or (cd.get("detailParams") or {}).get("itemId") or "")
    title = cd.get("title") or (cd.get("detailParams") or {}).get("title") or ""
    price = (cd.get("priceInfo") or {}).get("price") or (cd.get("detailParams") or {}).get("soldPrice") or ""
    pic = (cd.get("picInfo") or {}).get("picUrl") or (cd.get("detailParams") or {}).get("picUrl")
    status = cd.get("itemStatus")
    if not item_id:
        return None
    return MyItem(
        item_id=item_id,
        title=str(title).strip(),
        price=str(price),
        pic_url=str(pic) if pic else None,
        status=status,
        url=f"https://www.goofish.com/item?id={item_id}",
    )


def fetch_my_items(
    client,
    user_id: str,
    page_size: int = PAGE_SIZE,
    max_pages: int = MAX_PAGES,
    delay: float = 1.5,
    quiet: bool = False,
) -> list[MyItem]:
    """Page through every on-sale item for the logged-in user.

    Stops at the first empty or short page. On a rate-limit hit it backs off
    once and retries the page, then stops and keeps what it has - it never
    bypasses risk control.
    """
    items: list[MyItem] = []
    for page in range(1, max_pages + 1):
        data = {
            "needGroupInfo": True,
            "pageNumber": page,
            "userId": str(user_id),
            "pageSize": page_size,
        }
        try:
            resp = client.request(MY_ITEMS_API, data)
        except RateLimitedError:
            if not quiet:
                log(f"第 {page} 页触发风控，退避 60s 后重试一次…")
            time.sleep(60)
            try:
                resp = client.request(MY_ITEMS_API, data)
            except RateLimitedError as exc:
                if not quiet:
                    log(f"重试仍触发风控，停止抓取（已拿到 {len(items)} 个）: {exc}")
                break
        except XianyuError as exc:
            if not quiet:
                log(f"第 {page} 页失败，停止抓取: {exc}")
            break

        cards = resp.get("cardList") or []
        for card in cards:
            item = _card_to_item(card)
            if item is not None:
                items.append(item)

        if len(cards) < page_size:
            break
        if page < max_pages:
            time.sleep(delay)
    return items


def _user_id_from_cookies(cookies: list[dict[str, str]]) -> str:
    for c in cookies:
        if c.get("name") == "unb":
            return c.get("value", "")
    raise XianyuError("cookies 中没有 unb，无法确定 user_id")
