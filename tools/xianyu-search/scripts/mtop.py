"""mtop protocol signing and HTTP client for Xianyu's web search API.

Signing follows the standard mtop scheme:

    sign = md5(f"{token}&{t}&{appKey}&{data}")

where `token` is the part of the `_m_h5_tk` cookie before the first
underscore.  The server may refresh that cookie on any response, so the
client reads it from the cookie jar on every request and retries once when
the server reports a token error.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

import httpx

if __package__:
    from .common import (
        API_BASE,
        APP_KEY,
        USER_AGENT,
        XIANYU_HOME,
        ParseError,
        RateLimitedError,
        SessionExpiredError,
        TokenError,
        XianyuError,
    )
else:
    from common import (
        API_BASE,
        APP_KEY,
        USER_AGENT,
        XIANYU_HOME,
        ParseError,
        RateLimitedError,
        SessionExpiredError,
        TokenError,
        XianyuError,
    )


def mtop_sign(token: str, t: str, app_key: str, data: str) -> str:
    return hashlib.md5(f"{token}&{t}&{app_key}&{data}".encode()).hexdigest()


class MtopClient:
    """One HTTP session against h5api.m.goofish.com with login cookies."""

    def __init__(self, cookies: list[dict[str, str]], timeout: float = 20.0):
        jar = httpx.Cookies()
        for c in cookies:
            # Keep domain/path so a refreshed _m_h5_tk replaces the old
            # cookie instead of coexisting with it (which would raise
            # httpx.CookieConflict on the next request).
            jar.set(
                c.get("name", ""),
                c.get("value", ""),
                domain=c.get("domain") or "",
                path=c.get("path") or "/",
            )
        self._client = httpx.Client(
            base_url=API_BASE,
            cookies=jar,
            headers={
                "user-agent": USER_AGENT,
                "origin": XIANYU_HOME,
                "referer": XIANYU_HOME + "/",
                "content-type": "application/x-www-form-urlencoded",
                "accept": "application/json, text/plain, */*",
            },
            timeout=timeout,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "MtopClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _token(self) -> str:
        hits = [ck for ck in self._client.cookies.jar if ck.name == "_m_h5_tk"]
        if not hits:
            return ""
        # Prefer the most specific .goofish.com cookie when duplicates exist.
        hits.sort(
            key=lambda ck: ((ck.domain or "").endswith("goofish.com"), len(ck.domain or ""))
        )
        return (hits[-1].value or "").split("_")[0]

    def request(
        self,
        api: str,
        data: dict[str, Any],
        version: str = "1.0",
        max_token_retries: int = 2,
    ) -> dict[str, Any]:
        """Send one mtop request and return the response `data` object."""
        data_str = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        last_ret = ""
        for _ in range(max_token_retries + 1):
            t = str(int(time.time() * 1000))
            params = {
                "jsv": "2.7.2",
                "appKey": APP_KEY,
                "t": t,
                "sign": mtop_sign(self._token(), t, APP_KEY, data_str),
                "v": version,
                "type": "originaljson",
                "accountSite": "xianyu",
                "dataType": "json",
                "timeout": "20000",
                "api": api,
                "sessionOption": "AutoLoginOnly",
            }
            resp = self._client.post(
                f"/h5/{api}/{version}/", params=params, data={"data": data_str}
            )
            try:
                body = resp.json()
            except Exception:
                text = resp.text[:300]
                if "punish" in text or "x5sec" in text or resp.status_code in (419, 429):
                    raise RateLimitedError("触发风控：返回了非 JSON 的拦截页") from None
                raise ParseError(
                    f"响应不是 JSON（HTTP {resp.status_code}）：{text}"
                ) from None

            ret_list = body.get("ret") or ["FAIL_SYS_UNKNOWN::空响应"]
            ret = ret_list[0] if isinstance(ret_list, list) else str(ret_list)
            last_ret = ret
            if str(ret).startswith("SUCCESS"):
                return body.get("data") or {}
            if "TOKEN" in str(ret):
                # The refreshed token already landed in the cookie jar via
                # Set-Cookie; retry immediately.
                time.sleep(0.5)
                continue
            if any(k in str(ret) for k in ("SESSION_EXPIRED", "ILLEGAL_ACCESS", "AUTH")):
                raise SessionExpiredError(f"登录已失效（{ret}）")
            if any(k in str(ret) for k in ("RGV587", "USER_VALIDATE")) or "punish" in json.dumps(
                body
            ):
                raise RateLimitedError(f"触发风控（{ret}）")
            raise XianyuError(f"接口返回失败：{ret}")
        raise TokenError(f"token 刷新重试耗尽（{last_ret}）")
