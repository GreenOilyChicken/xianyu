"""CSV / JSON export of stored listing data."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable

CSV_COLUMNS = [
    "item_id",
    "title",
    "price",
    "area",
    "seller",
    "seller_id",
    "credit_level",
    "condition",
    "free_ship",
    "publish_time",
    "want_num",
    "url",
    "seller_url",
]


def _row(item: dict[str, Any]) -> list[str]:
    d = {
        "free_ship": "是" if item.get("free_ship") else "否",
        "url": f"https://www.goofish.com/item?id={item['item_id']}",
        "seller_url": (
            f"https://www.goofish.com/user?userId={item['seller_id']}"
            if item.get("seller_id")
            else ""
        ),
    }
    return [str(item.get(c) if c not in d else d[c]) or "" for c in CSV_COLUMNS]


def write_items_csv(path: Path | str, items: Iterable[dict[str, Any]]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig so Excel on Windows opens Chinese correctly.
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_COLUMNS)
        for item in items:
            writer.writerow(_row(item))
    return path


def write_items_json(path: Path | str, items: Iterable[dict[str, Any]]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(list(items), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path
