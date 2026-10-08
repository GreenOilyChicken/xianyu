"""Offline unit tests for the analysis module."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from analyze import (  # noqa: E402
    attr_counts,
    build_histogram,
    credit_bucket,
    deal_candidates,
    describe,
    recency_bucket,
    render_report,
    risk_flags,
)
from common import Item  # noqa: E402


def make_items(prices, condition=None, credit=None, wants=None):
    items = []
    for i, p in enumerate(prices):
        items.append(
            Item(
                item_id=str(1000 + i),
                title=f"测试商品 {i} 256G 国行",
                price=p,
                area="上海",
                seller=f"卖家{i % 3}",
                seller_id=f"S{i % 3}",
                credit_level=credit if credit is not None else (5 + i % 3),
                condition=condition or ("全新" if i % 2 == 0 else "二手"),
                free_ship=(i % 2 == 0),
                publish_time="2026-07-01",
                want_num=(wants[i] if wants else (i % 5)),
            )
        )
    return items


class TestStats(unittest.TestCase):
    def test_describe(self):
        s = describe([1, 2, 3, 4, 5])
        self.assertEqual(s["count"], 5)
        self.assertEqual(s["median"], 3)
        self.assertEqual(s["min"], 1)
        self.assertEqual(s["max"], 5)
        self.assertEqual(s["p25"], 2)
        self.assertEqual(s["p75"], 4)

    def test_describe_empty(self):
        s = describe([])
        self.assertEqual(s["count"], 0)
        self.assertIsNone(s["median"])

    def test_histogram(self):
        lines, edges = build_histogram([1, 2, 3, 4, 5], bins=5)
        self.assertEqual(len(lines), 5)
        self.assertEqual(len(edges), 5)

    def test_buckets(self):
        self.assertEqual(credit_bucket(8), "高(7+)")
        self.assertEqual(credit_bucket(5), "中(4-6)")
        self.assertEqual(credit_bucket(2), "低(1-3)")
        self.assertEqual(credit_bucket(None), "未知")
        from datetime import date

        self.assertEqual(recency_bucket("2026-07-30", date(2026, 7, 30)), "今天")
        self.assertEqual(recency_bucket("2026-07-28", date(2026, 7, 30)), "3天内")
        self.assertEqual(recency_bucket("2026-06-01", date(2026, 7, 30)), "更早")
        self.assertEqual(recency_bucket(None), "未知")

    def test_attr_counts(self):
        out = dict((l, h) for l, h, _r in attr_counts(["iPhone 15 256G 国行 包邮"]))
        self.assertTrue(out["存储容量"] >= 1)
        self.assertTrue(out["国行"] >= 1)
        self.assertTrue(out["包邮"] >= 1)


class TestRiskAndDeals(unittest.TestCase):
    def test_risk_flags_finds_outlier(self):
        items = make_items([1000, 1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 2000, 88])
        s = describe([it.price for it in items])
        suspects = risk_flags(items, s)
        ids = [x["item_id"] for x in suspects]
        self.assertEqual(ids, ["1010"])  # the 88-yuan bait

    def test_bait_price_flagged_when_fence_negative(self):
        """Real-data case: a 1-yuan placeholder price must be flagged even
        when the statistical fence is negative."""
        items = make_items([1, 30, 50, 60, 70, 77, 80, 90, 100, 120, 150])
        s = describe([it.price for it in items])
        suspects = risk_flags(items, s)
        self.assertEqual([x["item_id"] for x in suspects], ["1000"])
        self.assertEqual(suspects[0]["price"], 1.0)

    def test_deal_candidates(self):
        items = make_items([500, 700, 900, 1000, 1200], credit=7)
        s = describe([it.price for it in items])
        deals = deal_candidates(items, s)
        self.assertTrue(all(d.price <= s["p25"] for d in deals))


class TestReport(unittest.TestCase):
    def test_risk_items_excluded_from_deals(self):
        items = make_items([88, 500, 700, 900, 1000, 1200], credit=7)
        s = describe([it.price for it in items])
        suspects = risk_flags(items, s)
        deals = deal_candidates(
            items, s, exclude_ids={x["item_id"] for x in suspects}
        )
        self.assertTrue(all(d.item_id not in {x["item_id"] for x in suspects} for d in deals))

    def test_report_sections(self):
        items = make_items(list(range(800, 1400, 40)))
        report = render_report("测试商品", items, meta={"batch_id": "b1", "pages": 3})
        for section in (
            "# 闲鱼行情分析报告",
            "## 1. 价格概况",
            "## 2. 商品构成",
            "## 3. 卖家与信用",
            "## 4. 地区与时效",
            "## 5. 热度",
            "## 6. 风险提示",
            "## 7. 捡漏候选",
            "## 9. 结论与建议",
        ):
            self.assertIn(section, report)

    def test_report_empty(self):
        report = render_report("无结果", [])
        self.assertIn("本次没有采集到商品", report)


if __name__ == "__main__":
    unittest.main()
