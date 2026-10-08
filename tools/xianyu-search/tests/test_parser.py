"""Offline unit tests.  Run from the skill root:

    python -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from parser import (  # noqa: E402
    _fish_tag_texts,
    item_from_card,
    parse_condition,
    parse_price,
    parse_search_response,
    parse_tag,
)


def card(
    item_id="123",
    title="iPhone 13 256G 国行",
    price=None,
    display_price="2899",
    area="广东深圳",
    seller="卖家A",
    tag="new/freeship/credit-6",
    fish_tags=None,
    want_num=0,
    publish_time="1783421732000",
    seller_id="SELLER_1",
):
    if price is None:
        price = [{"text": "¥"}, {"text": "2899"}]
    return {
        "data": {
            "item": {
                "main": {
                    "exContent": {
                        "title": title,
                        "area": area,
                        "userNickName": seller,
                        "picUrl": "//img.alicdn.com/a.jpg",
                        "price": price,
                        "fishTags": fish_tags
                        or {
                            "r2": {"tagList": [{"data": {"content": "全新"}}]},
                            "r3": {"tagList": [{"data": {"content": "8人想要"}}]},
                        },
                    },
                    "clickParam": {
                        "args": {
                            "item_id": item_id,
                            "displayPrice": display_price,
                            "tag": tag,
                            "wantNum": want_num,
                            "publishTime": publish_time,
                            "seller_id": seller_id,
                        }
                    },
                }
            }
        }
    }


class TestParser(unittest.TestCase):
    def test_basic_card(self):
        it = item_from_card(card())
        self.assertIsNotNone(it)
        self.assertEqual(it.item_id, "123")
        self.assertEqual(it.title, "iPhone 13 256G 国行")
        self.assertEqual(it.price, 2899.0)
        self.assertEqual(it.area, "广东深圳")
        self.assertEqual(it.seller, "卖家A")
        self.assertEqual(it.credit_level, 6)
        self.assertEqual(it.condition, "全新")
        self.assertTrue(it.free_ship)
        self.assertEqual(it.want_num, 8)
        self.assertEqual(it.publish_time, "2026-07-07")
        self.assertEqual(it.url, "https://www.goofish.com/item?id=123")
        self.assertEqual(it.seller_url, "https://www.goofish.com/user?userId=SELLER_1")
        self.assertEqual(it.pic_url, "https://img.alicdn.com/a.jpg")

    def test_price_fallback_to_segments(self):
        it = item_from_card(
            card(display_price=None, price=[{"text": "¥"}, {"text": "1299"}, {"text": ".00"}])
        )
        self.assertIsNotNone(it)
        self.assertEqual(it.price, 1299.0)

    def test_wan_price(self):
        self.assertEqual(parse_price([{"text": "¥"}, {"text": "1.2万"}]), 12000.0)

    def test_condition_secondhand(self):
        it = item_from_card(
            card(
                tag="freeship/credit-3",
                fish_tags={"r2": {"tagList": [{"data": {"content": "95新 有轻微使用痕迹"}}]}},
            )
        )
        self.assertIsNotNone(it)
        self.assertEqual(it.condition, "二手")
        self.assertEqual(it.credit_level, 3)
        self.assertFalse(it.free_ship is False)

    def test_parse_tag(self):
        self.assertEqual(parse_tag("new/freeship/credit-6"), (True, True, 6))
        self.assertEqual(parse_tag(""), (False, False, None))
        self.assertEqual(parse_tag(None), (False, False, None))

    def test_parse_condition(self):
        self.assertEqual(parse_condition(["全新未拆封"], False), "全新")
        self.assertEqual(parse_condition(["几乎全新"], False), "二手")
        self.assertEqual(parse_condition(["没什么描述"], False), None)

    def test_fish_tag_texts(self):
        texts = _fish_tag_texts(
            {"fishTags": {"r2": {"tagList": [{"data": {"content": "包邮"}}, {"data": {}}]}}}
        )
        self.assertEqual(texts, ["包邮"])

    def test_ads_card_skipped(self):
        items, skipped = parse_search_response(
            {
                "resultList": [
                    {"data": {"item": {"main": {}}}},
                    card(),
                ]
            }
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(skipped, 1)

    def test_missing_result_list_raises(self):
        with self.assertRaises(Exception):
            parse_search_response({"data": {}})


if __name__ == "__main__":
    unittest.main()
