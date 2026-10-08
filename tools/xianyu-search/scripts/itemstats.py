"""Fetch item detail stats (browse/want/sold counts) via mtop.taobao.idle.pc.detail.

Unlike the search and my-items endpoints, the detail endpoint applies stricter
risk control and requires an x5sec token - a risk-control proof the web client
obtains after solving a captcha. The token expires (hours to days); when it
does, the caller must re-export it from a logged-in browser and refresh the
stored cookie. This module never solves captchas; it only carries a token the
user supplied.

The fields we care about live under `data.itemDO`:

    browseCnt   - page view count (浏览)
    wantCnt     - want count (想要)
    soldCnt     - sold count (售出)
    soldPrice   - price
    collectCnt  - favorites (收藏)

Usage as a library:

    from login import load_cookies
    from mtop import MtopClient
    from itemstats import fetch_item_stats

    cookies = load_cookies(state_path)
    with MtopClient(cookies) as client:
        stats = fetch_item_stats(client, "1086312718103")
        # stats.browse, stats.want, stats.sold, stats.price
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

if __package__:
    from .common import API_BASE, APP_KEY, XianyuError
else:
    from common import API_BASE, APP_KEY, XianyuError

DETAIL_API = "mtop.taobao.idle.pc.detail"

# Browser-faithful headers. The detail endpoint's risk control is stricter
# than search; mimicking a real browser improves the success rate but the
# x5sec token remains the decisive factor.
_BROWSER_HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36 Edg/154.0.0.0"
    ),
    "origin": "https://www.goofish.com",
    "referer": "https://www.goofish.com/",
    "content-type": "application/x-www-form-urlencoded",
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
    "sec-ch-ua": '"Chromium";v="154", "Microsoft Edge";v="154", "Not A(Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
}


@dataclass
class ItemStats:
    """Traffic stats for one listing."""

    item_id: str
    browse: int | None = None
    want: int | None = None
    sold: int | None = None
    price: str | None = None
    title: str | None = None
    collect: int | None = None

    def to_dict(self) -> dict:
        d = {"item_id": self.item_id}
        for k in ("title", "price", "browse", "want", "sold", "collect"):
            v = getattr(self, k)
            if v is not None:
                d[k] = v
        d["url"] = f"https://www.goofish.com/item?id={self.item_id}"
        return d


class X5secExpiredError(XianyuError):
    """The x5sec risk-control token was rejected (needs re-export)."""


def _get_x5sec() -> str:
    """Read the x5sec token from env var or stored cookie file."""
    val = os.environ.get("XIANYU_X5SEC", "")
    if val:
        return val.strip()
    # Fall back to a file alongside the login state
    path = os.environ.get("XIANYU_X5SEC_FILE") or os.path.expanduser("~/.xianyu-data/x5sec.txt")
    try:
        return (open(path).read().strip() if os.path.exists(path) else "")
    except OSError:
        return ""


def fetch_item_stats(cookies, item_id: str, x5sec: str | None = None) -> ItemStats:
    """Fetch browse/want/sold for one item. Raises X5secExpiredError when the
    token is rejected and needs re-export.

    This builds its own httpx.Client because the detail endpoint needs
    browser-faithful headers and the x5sec cookie, which the shared
    MtopClient does not carry.
    """
    import hashlib
    import httpx

    token_val = ""
    for c in cookies:
        if c.get("name") == "_m_h5_tk":
            token_val = (c.get("value") or "").split("_")[0]
            break

    sec = x5sec or _get_x5sec()
    if not sec:
        raise X5secExpiredError(
            "没有 x5sec token。请在已登录的浏览器里打开一次商品详情页，"
            "从请求 cookie 中复制 x5sec 的值，写入 ~/.xianyu-data/x5sec.txt "
            "或环境变量 XIANYU_X5SEC"
        )

    jar = httpx.Cookies()
    for c in cookies:
        jar.set(c["name"], c["value"], domain=c.get("domain") or "", path=c.get("path") or "/")
    jar.set("x5sec", sec, domain=".goofish.com", path="/")

    client = httpx.Client(base_url=API_BASE, cookies=jar, headers=_BROWSER_HEADERS, timeout=20, follow_redirects=True)
    try:
        data_str = json.dumps({"itemId": str(item_id)}, separators=(",", ":"))
        t = str(int(time.time() * 1000))
        sign = hashlib.md5(f"{token_val}&{t}&{APP_KEY}&{data_str}".encode()).hexdigest()
        params = {
            "jsv": "2.7.2", "appKey": APP_KEY, "t": t, "sign": sign, "v": "1.0",
            "type": "originaljson", "accountSite": "xianyu", "dataType": "json",
            "timeout": "20000", "api": DETAIL_API, "sessionOption": "AutoLoginOnly",
            "spm_cnt": "a21ybx.item.0.0",
        }
        resp = client.post(f"/h5/{DETAIL_API}/1.0/", params=params, data={"data": data_str})
        body = resp.json()
        ret = (body.get("ret") or [""])[0]
        ret_str = str(ret)

        if "USER_VALIDATE" in ret_str or "RGV587" in ret_str or "punish" in json.dumps(body):
            raise X5secExpiredError(
                f"x5sec token 被拒绝（{ret_str}）。请在浏览器重新打开商品详情页，"
                "重新复制 x5sec 并更新 ~/.xianyu-data/x5sec.txt"
            )
        if not ret_str.startswith("SUCCESS"):
            raise XianyuError(f"详情接口返回失败：{ret_str}")

        data = body.get("data") or {}
        item_do = data.get("itemDO") or {}
        return ItemStats(
            item_id=str(item_id),
            title=item_do.get("title"),
            price=str(item_do.get("soldPrice")) if item_do.get("soldPrice") is not None else None,
            browse=item_do.get("browseCnt"),
            want=item_do.get("wantCnt"),
            sold=item_do.get("soldCnt"),
            collect=item_do.get("collectCnt"),
        )
    finally:
        client.close()
