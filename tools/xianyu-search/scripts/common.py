"""Shared constants, paths, errors and helpers for the xianyu-search skill.

All persistent data (SQLite database, raw responses, reports, results and the
login state) lives under one user-private directory: `~/.xianyu-data` by
default, overridable with the `XIANYU_DATA_DIR` environment variable.  The
login state file contains cookies and is treated as a secret: this skill
never prints or transmits it.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

XIANYU_HOME = "https://www.goofish.com"
ITEM_URL = "https://www.goofish.com/item?id={id}"
SELLER_URL = "https://www.goofish.com/user?userId={id}"

API_BASE = "https://h5api.m.goofish.com"
APP_KEY = "34839810"
SEARCH_API = "mtop.taobao.idlemtopsearch.pc.search"
API_VERSION = "1.0"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Cookie that appears only after a successful login.
LOGIN_COOKIE = "unb"

ROWS_PER_PAGE = 30
DEFAULT_PAGES = 3
MAX_PAGES = 50
DEFAULT_DELAY_RANGE = (2.0, 5.0)
PUNISH_BACKOFF_SECONDS = 60.0
MIN_WATCH_INTERVAL_SECONDS = 1800


class XianyuError(Exception):
    """Base error.  Messages are safe to show to the user."""


class NotLoggedInError(XianyuError):
    """No usable login state file."""


class SessionExpiredError(XianyuError):
    """The login session is no longer accepted."""


class RateLimitedError(XianyuError):
    """Xianyu risk control (slider/captcha/RGV587) rejected the request."""


class TokenError(XianyuError):
    """The mtop sign token could not be obtained or refreshed."""


class ParseError(XianyuError):
    """A response could not be parsed (site layout may have changed)."""


def data_dir() -> Path:
    root = Path(os.environ.get("XIANYU_DATA_DIR") or (Path.home() / ".xianyu-data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def default_state_path() -> Path:
    return Path(os.environ.get("XIANYU_STATE") or (data_dir() / "storage_state.json"))


def db_path() -> Path:
    return data_dir() / "xianyu.db"


def results_dir() -> Path:
    p = data_dir() / "results"
    p.mkdir(parents=True, exist_ok=True)
    return p


def raw_dir() -> Path:
    p = data_dir() / "raw"
    p.mkdir(parents=True, exist_ok=True)
    return p


def load_json(path: Path | str) -> Any:
    # utf-8-sig tolerates a BOM written by editors/PowerShell on Windows.
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def dump_json_atomic(path: Path | str, obj: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def timestamp_slug() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def slugify(text: str, max_len: int = 24) -> str:
    out = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in text)
    out = out.strip("_") or "query"
    return out[:max_len]


def sleep_jitter(lo: float, hi: float) -> None:
    time.sleep(random.uniform(lo, hi))


def protect_file(path: Path | str) -> None:
    """Restrict a file to the current user where the platform supports it."""
    path = Path(path)
    try:
        if os.name == "nt":
            user = os.environ.get("USERNAME", "CURRENT_USER")
            subprocess.run(
                ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:(F)"],
                capture_output=True,
                check=False,
            )
        else:
            os.chmod(path, 0o600)
    except OSError:
        pass


def force_utf8_stdio() -> None:
    """Reconfigure stdio to UTF-8 so Chinese/emoji survive Windows pipes.

    The Windows console/pipes default to the legacy locale encoding (GBK),
    which crashes or garbles Chinese output.  Call this at program start.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def emit_json(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2), flush=True)


def fmt_price(v: float | None) -> str:
    if v is None:
        return "-"
    if abs(v) >= 100:
        return f"{v:,.0f}"
    return f"{v:.2f}"


@dataclass
class Item:
    """One normalized Xianyu listing."""

    item_id: str
    title: str
    price: float
    area: str | None = None
    seller: str | None = None
    seller_id: str | None = None
    pic_url: str | None = None
    credit_level: int | None = None
    condition: str | None = None  # "全新" | "二手" | None (未知)
    free_ship: bool = False
    publish_time: str | None = None  # YYYY-MM-DD
    want_num: int | None = None
    tags: list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        return ITEM_URL.format(id=self.item_id)

    @property
    def seller_url(self) -> str | None:
        return SELLER_URL.format(id=self.seller_id) if self.seller_id else None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["url"] = self.url
        d["seller_url"] = self.seller_url
        return d
