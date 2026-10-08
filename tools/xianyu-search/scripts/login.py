"""One-time login capture for Xianyu.

Only this command starts a browser; everything else uses plain HTTP with the
saved cookies.  The user must complete the QR/OTP flow personally - this
script never types credentials and never bypasses a challenge.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
import time
from pathlib import Path

if __package__:
    from .common import (
        LOGIN_COOKIE,
        XIANYU_HOME,
        NotLoggedInError,
        XianyuError,
        default_state_path,
        dump_json_atomic,
        force_utf8_stdio,
        log,
        protect_file,
    )
else:
    from common import (
        LOGIN_COOKIE,
        XIANYU_HOME,
        NotLoggedInError,
        XianyuError,
        default_state_path,
        dump_json_atomic,
        force_utf8_stdio,
        log,
        protect_file,
    )


def _wait_for_login(context, timeout_s: float) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        names = {c["name"] for c in context.cookies()}
        if LOGIN_COOKIE in names:
            time.sleep(2)  # let _m_h5_tk and friends land
            return True
        time.sleep(1)
    return False


def login_with_browser(
    state_path: Path,
    timeout_s: float = 300,
    channel: str | None = None,
    quiet: bool = False,
) -> Path:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = None
        if channel:
            launches = [{"channel": channel, "headless": False}]
        else:
            # Prefer the locally installed Chrome (natural fingerprint, no
            # download); fall back to the Playwright-bundled Chromium.
            launches = [{"channel": "chrome", "headless": False}, {"headless": False}]
        for kwargs in launches:
            try:
                browser = p.chromium.launch(**kwargs)
                break
            except Exception:
                continue
        if browser is None:
            raise XianyuError(
                "无法启动浏览器：请安装 Chrome，或运行 "
                "`python -m playwright install chromium`"
            )
        context = browser.new_context(locale="zh-CN")
        page = context.new_page()
        page.goto(XIANYU_HOME)
        if not quiet:
            log(
                f"已打开浏览器，请在窗口中扫码登录闲鱼（最长等待 {timeout_s:.0f}s）…"
                "扫码后页面若要求手机确认/短信验证，请本人完成。"
            )
        try:
            ok = _wait_for_login(context, timeout_s)
            if not ok:
                raise XianyuError("登录超时：未检测到登录成功，请重试 login")
            state = context.storage_state()
        finally:
            try:
                browser.close()
            except Exception:
                pass

    state_path.parent.mkdir(parents=True, exist_ok=True)
    dump_json_atomic(state_path, state)
    protect_file(state_path)
    return state_path


def login_with_cookie_header(cookie_header: str, state_path: Path) -> Path:
    """Build a state file from a raw Cookie header (extension export).

    All cookies are attached to .goofish.com; the login cookie must be
    present or the state is refused.
    """
    records = []
    for pair in cookie_header.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        name, _, value = pair.partition("=")
        records.append(
            {
                "name": name.strip(),
                "value": value.strip(),
                "domain": ".goofish.com",
                "path": "/",
            }
        )
    if LOGIN_COOKIE not in {r["name"] for r in records}:
        raise NotLoggedInError(
            f"Cookie 串中缺少登录 cookie（{LOGIN_COOKIE}），请确认已在浏览器登录闲鱼后再导出"
        )
    state_path.parent.mkdir(parents=True, exist_ok=True)
    dump_json_atomic(state_path, {"cookies": records, "origins": []})
    protect_file(state_path)
    return state_path


def load_cookies(state_path: Path | str) -> list[dict[str, str]]:
    """Read login cookies from a Playwright storage_state JSON file."""
    state_path = Path(state_path)
    if not state_path.exists():
        raise NotLoggedInError(
            f"未找到登录态文件 {state_path}，请先运行 `xianyu.py login` 扫码登录"
        )
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise NotLoggedInError(f"登录态文件损坏：{state_path}") from exc
    records = [
        {
            "name": c.get("name", ""),
            "value": c.get("value", ""),
            "domain": c.get("domain") or "",
            "path": c.get("path") or "/",
        }
        for c in state.get("cookies", [])
        if isinstance(c, dict) and c.get("name")
    ]
    if LOGIN_COOKIE not in {r["name"] for r in records}:
        raise NotLoggedInError(
            "登录态文件里没有登录 cookie，登录可能已失效，请重新运行 `xianyu.py login`"
        )
    return records


def run(args: argparse.Namespace) -> int:
    state_path = Path(args.state) if args.state else default_state_path()

    if args.cookie_stdin:
        if sys.stdin.isatty():
            cookie_header = getpass.getpass("请粘贴浏览器导出的 Cookie 字符串（输入不回显）：")
        else:
            cookie_header = sys.stdin.read().strip()
        login_with_cookie_header(cookie_header, state_path)
        print(f"登录态已保存（来自 Cookie 导入）")
    else:
        saved = login_with_browser(
            state_path, timeout_s=args.timeout, channel=args.channel, quiet=args.quiet
        )
        print(f"登录成功，登录态已保存到 {saved}")

    print("提示：登录态只是候选凭证。请立即用 1 页搜索验证一次，确认抓取可用。")
    return 0


def main(argv: list[str] | None = None) -> int:
    force_utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="xianyu.py login", description="闲鱼扫码登录（一次性）"
    )
    parser.add_argument("--state", default=None, help="登录态输出路径（默认 ~/.xianyu-data/storage_state.json）")
    parser.add_argument("--timeout", type=float, default=300, help="登录等待秒数（默认 300）")
    parser.add_argument("--channel", default=None, help="浏览器通道，如 chrome / msedge（默认自动选择）")
    parser.add_argument(
        "--cookie-stdin",
        action="store_true",
        help="从标准输入读取 Cookie 头字符串构建登录态（免浏览器方案）",
    )
    parser.add_argument("--quiet", action="store_true", help="减少提示输出")
    args = parser.parse_args(argv)
    return run(args)
