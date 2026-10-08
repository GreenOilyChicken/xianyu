"""SQLite persistence for batches, items and per-batch observations.

Schema summary:
- batches:      one row per crawl run
- items:        one row per listing (upserted across runs)
- observations: one row per (batch, item) price observation
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

if __package__:
    from .common import Item, XianyuError, db_path, now_iso
else:
    from common import Item, XianyuError, db_path, now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS batches (
    id          TEXT PRIMARY KEY,
    keyword     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    pages       INTEGER NOT NULL,
    item_count  INTEGER NOT NULL,
    partial     INTEGER NOT NULL DEFAULT 0,
    min_price   REAL,
    max_price   REAL,
    location    TEXT,
    note        TEXT
);
CREATE TABLE IF NOT EXISTS items (
    item_id      TEXT PRIMARY KEY,
    title        TEXT,
    price        REAL,
    area         TEXT,
    seller       TEXT,
    seller_id    TEXT,
    pic_url      TEXT,
    credit_level INTEGER,
    condition    TEXT,
    free_ship    INTEGER NOT NULL DEFAULT 0,
    publish_time TEXT,
    want_num     INTEGER,
    first_seen   TEXT NOT NULL,
    last_seen    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS observations (
    batch_id   TEXT NOT NULL,
    item_id    TEXT NOT NULL,
    price      REAL NOT NULL,
    title      TEXT,
    crawled_at TEXT NOT NULL,
    PRIMARY KEY (batch_id, item_id)
);
CREATE INDEX IF NOT EXISTS idx_obs_item ON observations(item_id);
CREATE INDEX IF NOT EXISTS idx_batches_keyword ON batches(keyword, created_at);
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(path) if path else db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def save_batch(
    conn: sqlite3.Connection,
    batch_id: str,
    keyword: str,
    items: Iterable[Item],
    pages: int,
    partial: bool,
    min_price: float | None = None,
    max_price: float | None = None,
    location: str | None = None,
    note: str = "",
) -> int:
    """Persist one crawl run; returns the number of items stored."""
    ts = now_iso()
    items = list(items)
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO batches"
            "(id, keyword, created_at, pages, item_count, partial, min_price, max_price, location, note) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (batch_id, keyword, ts, pages, len(items), int(partial), min_price, max_price, location, note),
        )
        for it in items:
            conn.execute(
                """
                INSERT INTO items
                  (item_id, title, price, area, seller, seller_id, pic_url,
                   credit_level, condition, free_ship, publish_time, want_num,
                   first_seen, last_seen)
                VALUES
                  (:item_id, :title, :price, :area, :seller, :seller_id, :pic_url,
                   :credit_level, :condition, :free_ship, :publish_time, :want_num,
                   :ts, :ts)
                ON CONFLICT(item_id) DO UPDATE SET
                  title=excluded.title, price=excluded.price, area=excluded.area,
                  seller=excluded.seller, seller_id=excluded.seller_id,
                  pic_url=excluded.pic_url, credit_level=excluded.credit_level,
                  condition=excluded.condition, free_ship=excluded.free_ship,
                  publish_time=excluded.publish_time, want_num=excluded.want_num,
                  last_seen=excluded.last_seen
                """,
                {**it.to_dict(), "ts": ts},
            )
            conn.execute(
                "INSERT OR REPLACE INTO observations(batch_id, item_id, price, title, crawled_at) "
                "VALUES (?,?,?,?,?)",
                (batch_id, it.item_id, it.price, it.title, ts),
            )
    return len(items)


def latest_batch_id(conn: sqlite3.Connection, keyword: str) -> str | None:
    row = conn.execute(
        "SELECT id FROM batches WHERE keyword=? ORDER BY created_at DESC, id DESC LIMIT 1",
        (keyword,),
    ).fetchone()
    return row["id"] if row else None


def list_batches(
    conn: sqlite3.Connection, keyword: str | None = None, limit: int = 50
) -> list[dict]:
    if keyword:
        rows = conn.execute(
            "SELECT * FROM batches WHERE keyword=? ORDER BY created_at DESC, id DESC LIMIT ?",
            (keyword, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM batches ORDER BY created_at DESC, id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_batch(conn: sqlite3.Connection, batch_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM batches WHERE id=?", (batch_id,)).fetchone()
    return dict(row) if row else None


def load_items(
    conn: sqlite3.Connection,
    batch_id: str | None = None,
    keyword: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """Load items of one batch using the batch's price/title snapshot.

    Keyword resolves to its latest batch.  Price and title come from the
    observation row (the value seen at crawl time), while seller/credit etc.
    come from the items table (latest known).
    """
    if batch_id is None:
        if not keyword:
            raise XianyuError("必须指定关键词或批次 ID")
        batch_id = latest_batch_id(conn, keyword)
        if batch_id is None:
            raise XianyuError(f"本地没有关键词 {keyword!r} 的抓取记录，请先 search")
    sql = (
        "SELECT i.item_id, o.title, o.price, i.area, i.seller, i.seller_id, "
        "i.pic_url, i.credit_level, i.condition, i.free_ship, i.publish_time, "
        "i.want_num, i.first_seen, i.last_seen, o.batch_id "
        "FROM observations o JOIN items i ON i.item_id = o.item_id "
        "WHERE o.batch_id = ?"
    )
    params: list[Any] = [batch_id]
    if min_price is not None:
        sql += " AND o.price >= ?"
        params.append(min_price)
    if max_price is not None:
        sql += " AND o.price <= ?"
        params.append(max_price)
    sql += " ORDER BY o.price"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def item_history(conn: sqlite3.Connection, query: str) -> list[dict]:
    """Price history of one item across batches.

    A numeric query matches item_id exactly; otherwise the title substring.
    """
    if query.isdigit():
        rows = conn.execute(
            """
            SELECT o.batch_id, o.item_id, o.price, o.title, o.crawled_at, b.keyword
            FROM observations o JOIN batches b ON b.id = o.batch_id
            WHERE o.item_id = ? ORDER BY o.crawled_at
            """,
            (query,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT o.batch_id, o.item_id, o.price, o.title, o.crawled_at, b.keyword
            FROM observations o JOIN batches b ON b.id = o.batch_id
            WHERE o.item_id IN (SELECT item_id FROM items WHERE title LIKE ?)
            ORDER BY o.crawled_at
            """,
            (f"%{query}%",),
        ).fetchall()
    return [dict(r) for r in rows]


def seen_item_ids(conn: sqlite3.Connection) -> set[str]:
    return {r["item_id"] for r in conn.execute("SELECT item_id FROM items").fetchall()}
