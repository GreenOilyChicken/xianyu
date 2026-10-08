"""Read-only environment checks.

Runs no browser, makes no network request, writes no file and never reads
credential contents - only the presence/type of files.  Emits one JSON object
with an actionable `next_action`.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if __package__:
    from .common import LOGIN_COOKIE, data_dir, default_state_path, emit_json
else:
    from common import LOGIN_COOKIE, data_dir, default_state_path, emit_json


def _find_chrome() -> Path | None:
    candidates = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/usr/bin/google-chrome"),
        Path("/usr/bin/chromium"),
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def _find_playwright_chromium() -> Path | None:
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
    elif sys.platform == "darwin":
        root = Path.home() / "Library/Caches/ms-playwright"
    else:
        root = Path.home() / ".cache/ms-playwright"
    if not root.is_dir():
        return None
    exes = sorted(root.glob("chromium-*/chrome-*/chrome.exe")) or sorted(
        root.glob("chromium-*/chrome-linux/chrome")
    ) or sorted(root.glob("chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium"))
    return exes[-1] if exes else None


def _state_ok() -> tuple[bool, str]:
    state = default_state_path()
    if not state.is_file():
        return False, f"未找到登录态文件 {state}"
    try:
        import json

        data = json.loads(state.read_text(encoding="utf-8"))
        names = {c.get("name") for c in data.get("cookies", [])}
    except Exception:
        return False, "登录态文件存在但无法解析"
    if LOGIN_COOKIE not in names:
        return False, "登录态文件中没有登录 cookie"
    return True, "登录态文件存在"


def run_checks() -> dict:
    checks: list[dict] = []

    py_ok = sys.version_info >= (3, 10)
    checks.append(
        {
            "name": "python",
            "ok": py_ok,
            "detail": f"Python {sys.version.split()[0]}（需要 >= 3.10）",
        }
    )

    for pkg in ("httpx", "playwright"):
        try:
            __import__(pkg)
            checks.append({"name": pkg, "ok": True, "detail": "已安装"})
        except ImportError:
            checks.append(
                {"name": pkg, "ok": False, "detail": f"未安装（pip install {pkg}）"}
            )

    chrome = _find_chrome()
    pw_chromium = _find_playwright_chromium()
    if chrome:
        checks.append({"name": "browser", "ok": True, "detail": f"本机 Chrome：{chrome}"})
    elif pw_chromium:
        checks.append(
            {"name": "browser", "ok": True, "detail": f"Playwright Chromium：{pw_chromium}"}
        )
    else:
        checks.append(
            {
                "name": "browser",
                "ok": False,
                "detail": "未找到可用浏览器（login 需要；search/analyze 不需要浏览器）",
            }
        )

    d = data_dir()
    writable = d.is_dir()
    checks.append({"name": "data-dir", "ok": writable, "detail": f"数据目录：{d}"})

    ok, detail = _state_ok()
    checks.append({"name": "state", "ok": ok, "detail": detail})

    all_ok = all(c["ok"] for c in checks)

    if not py_ok:
        code, msg = "upgrade-python", "请升级 Python 到 3.10+"
    elif not checks[1]["ok"] or not checks[2]["ok"]:
        code, msg = (
            "install-dependencies",
            "pip install -r requirements.txt",
        )
    elif not checks[3]["ok"]:
        code, msg = (
            "install-browser",
            "运行 python -m playwright install chromium（或安装 Chrome）",
        )
    elif not checks[4]["ok"]:
        code, msg = "fix-data-dir", "检查数据目录权限"
    elif not ok:
        code, msg = "login-required", "运行 xianyu.py login 扫码登录"
    else:
        code, msg = "ready", "环境就绪"

    return {"ok": all_ok, "checks": checks, "next_action": {"code": code, "message": msg}}


def run(args: argparse.Namespace) -> int:
    result = run_checks()
    emit_json(result)
    return 0 if result["next_action"]["code"] == "ready" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="xianyu.py doctor", description="环境自检（只读，不启动浏览器）"
    )
    args = parser.parse_args(argv)
    return run(args)
