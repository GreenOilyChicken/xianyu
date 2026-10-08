"""Offline unit tests for the SQLite store."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from common import Item  # noqa: E402
from store import (  # noqa: E402
    connect,
    get_batch,
    item_history,
    latest_batch_id,
    list_batches,
    load_items,
    save_batch,
    seen_item_ids,
)


def item(i, p):
    return Item(item_id=str(i), title=f"商品{i}", price=p, area="上海", seller="卖家A")


class TestStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "t.db"
        self.conn = connect(self.db)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_save_and_load(self):
        save_batch(self.conn, "b1", "iphone", [item(1, 100), item(2, 200)], pages=1, partial=False)
        rows = load_items(self.conn, batch_id="b1")
        self.assertEqual(len(rows), 2)
        self.assertEqual(latest_batch_id(self.conn, "iphone"), "b1")
        self.assertIsNotNone(get_batch(self.conn, "b1"))

    def test_upsert_across_batches(self):
        save_batch(self.conn, "b1", "iphone", [item(1, 100)], pages=1, partial=False)
        save_batch(self.conn, "b2", "iphone", [item(1, 90)], pages=1, partial=False)
        self.assertEqual(seen_item_ids(self.conn), {"1"})
        hist = item_history(self.conn, "1")
        self.assertEqual(len(hist), 2)
        self.assertEqual([h["price"] for h in hist], [100.0, 90.0])
        self.assertEqual(latest_batch_id(self.conn, "iphone"), "b2")

    def test_batch_load_uses_observation_snapshot(self):
        """Loading an old batch must return the crawl-time price, not the
        latest upserted item price."""
        save_batch(self.conn, "b1", "iphone", [item(1, 100)], pages=1, partial=False)
        save_batch(self.conn, "b2", "iphone", [item(1, 90)], pages=1, partial=False)
        rows = load_items(self.conn, batch_id="b1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["price"], 100.0)
        self.assertEqual(rows[0]["batch_id"], "b1")
        rows2 = load_items(self.conn, batch_id="b2")
        self.assertEqual(rows2[0]["price"], 90.0)

    def test_history_by_title(self):
        save_batch(self.conn, "b1", "iphone", [item(7, 300)], pages=1, partial=False)
        save_batch(self.conn, "b2", "iphone", [item(7, 280)], pages=1, partial=False)
        rows = item_history(self.conn, "商品7")
        self.assertEqual(len(rows), 2)

    def test_batches_list(self):
        save_batch(self.conn, "b1", "a", [], pages=1, partial=False)
        save_batch(self.conn, "b2", "b", [], pages=1, partial=True)
        self.assertEqual(len(list_batches(self.conn)), 2)
        self.assertEqual(len(list_batches(self.conn, "a")), 1)
        self.assertTrue(list_batches(self.conn, "b")[0]["partial"])


if __name__ == "__main__":
    unittest.main()
