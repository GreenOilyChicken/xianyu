"""Tests for the crawl loop's pagination and stop logic (offline, fake client)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from spider import crawl  # noqa: E402


def make_page(items, ad_cards=0, id_offset=0):
    cards = [{"data": {"item": {"main": {"exContent": {"title": t, "price": [{"text": "¥"}, {"text": str(p)}]}, "clickParam": {"args": {"item_id": str(1000 + id_offset + i), "displayPrice": str(p), "tag": ""}}}}}} for i, (t, p) in enumerate(items)]
    cards += [{"data": {"ad": True}}] * ad_cards
    return {"resultList": cards}


class FakeClient:
    def __init__(self, pages):
        self.pages = pages
        self.calls = 0

    def request(self, api, data=None, **kw):
        self.calls += 1
        page = data["pageNumber"]
        return self.pages.get(page, {"resultList": []})


class TestCrawlPagination(unittest.TestCase):
    def test_full_page_with_skipped_ad_card_keeps_going(self):
        """A full raw page (30 cards, 1 unparseable ad) must NOT stop early."""
        p1 = make_page([(f"item{i}", 50 + i) for i in range(29)], ad_cards=1, id_offset=0)
        p2 = make_page([(f"item{i}", 60 + i) for i in range(30)], id_offset=100)
        client = FakeClient({1: p1, 2: p2})
        summary = crawl(client, "test", pages=3, rows=30, delay=(0, 0), quiet=True)
        self.assertEqual(client.calls, 3)  # page 3 is empty and ends the run
        self.assertEqual(summary.pages_done, 2)
        self.assertEqual(summary.item_count, 59)

    def test_short_raw_page_stops(self):
        """A genuinely short raw page means the last page."""
        p1 = make_page([(f"item{i}", 50 + i) for i in range(10)])
        client = FakeClient({1: p1})
        summary = crawl(client, "test", pages=5, rows=30, delay=(0, 0), quiet=True)
        self.assertEqual(client.calls, 1)
        self.assertEqual(summary.pages_done, 1)
        self.assertEqual(summary.item_count, 10)

    def test_dedup_across_pages(self):
        def card(item_id, title, price):
            return {"data": {"item": {"main": {"exContent": {"title": title, "price": [{"text": "¥"}, {"text": str(price)}]}, "clickParam": {"args": {"item_id": str(item_id), "displayPrice": str(price), "tag": ""}}}}}}

        p1 = {"resultList": [card(1, "a", 1), card(2, "b", 2)]}
        p2 = {"resultList": [card(1, "a", 1), card(3, "c", 3)]}
        client = FakeClient({1: p1, 2: p2})
        summary = crawl(client, "test", pages=2, rows=2, delay=(0, 0), quiet=True)
        self.assertEqual(summary.item_count, 3)


if __name__ == "__main__":
    unittest.main()
