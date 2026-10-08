# 数据 Schema 与扩展点

## Item（商品，结果 JSON 与 SQLite 共用的核心结构）

| 字段 | 类型 | 来源 | 说明 |
|---|---|---|---|
| `item_id` | str | args.item_id | 商品 ID，去重主键 |
| `title` | str | exContent.title | 标题 |
| `price` | float | args.displayPrice → exContent.price 分段数组 | 价格（元） |
| `area` | str? | exContent.area | 地区 |
| `seller` | str? | exContent.userNickName | 卖家昵称 |
| `seller_id` | str? | args.seller_id | 卖家 ID |
| `pic_url` | str? | exContent.picUrl | 主图（`//` 前缀已补 https） |
| `credit_level` | int? | args.tag 的 `credit-N` | 卖家信用等级，越高越好 |
| `condition` | "全新"\|"二手"\|null | fishTags 文本 / tag 的 `new` | 成色；无信号为 null（未知） |
| `free_ship` | bool | args.tag 的 `freeship` | 是否包邮 |
| `publish_time` | "YYYY-MM-DD"\|null | args.publishTime 毫秒时间戳 | 上架日期 |
| `want_num` | int? | fishTags「N人想要」→ args.wantNum | 想要人数（热度） |
| `tags` | list[str] | exContent.fishTags 各 zone 文本 | 最多 20 条 |
| `url` | str | 派生 | `https://www.goofish.com/item?id={item_id}` |
| `seller_url` | str? | 派生 | `https://www.goofish.com/user?userId={seller_id}` |

## 结果 JSON 文件

`search` 落盘的文件 = `{ok, keyword, batch_id, count, pages_scraped, pages_requested, partial, error, error_type, filters, items[]}`，见 `api_reference.md`。这份文件就是给外部系统的稳定数据接口。

## SQLite（默认 `~/.xianyu-data/xianyu.db`）

### batches（每次抓取一行）

`id`(PK) `keyword` `created_at` `pages` `item_count` `partial`(0/1) `min_price` `max_price` `location` `note`

### items（商品维度，跨批次 upsert）

`item_id`(PK) `title` `price` `area` `seller` `seller_id` `pic_url` `credit_level` `condition` `free_ship` `publish_time` `want_num` `first_seen` `last_seen`

### observations（每批次对每商品的一次观测）

`batch_id`+`item_id`(联合 PK) `price` `title` `crawled_at`

单商品价格历史 = `observations JOIN batches` 按 `item_id` 查询。

## 原始响应结构（抓取接口）

`POST https://h5api.m.goofish.com/h5/mtop.taobao.idlemtopsearch.pc.search/1.0/`，返回：

```
data.resultList[]
  └─ data.item.main
       ├─ exContent: { title, area, userNickName, picUrl, price[{text}], fishTags{zone:{tagList:[{data:{content}}]}} }
       └─ clickParam.args: { item_id, displayPrice, tag("new/freeship/credit-N"), wantNum, publishTime(ms), seller_id }
```

解析入口 `parser.item_from_card()`。**接口字段变动时只改这里**：用 `search --dump-raw` 保留现场，对照新结构调整取值路径与兜底顺序。

## 扩展点清单

| 扩展点 | 位置 | 说明 |
|---|---|---|
| 商品字段解析 | `scripts/parser.py::item_from_card` | 新增/调整字段唯一入口 |
| 标题属性维度 | `scripts/analyze.py::ATTR_PATTERNS` | `(标签, 正则)` 表，按品类增删 |
| 排序映射 | `scripts/spider.py::SORT_MAP` | 服务端排序字段对 |
| 风险判定 | `scripts/analyze.py::risk_flags` | 异常低价阈值 |
| 捡漏判定 | `scripts/analyze.py::deal_candidates` | 评分权重 |
| 报告结构 | `scripts/analyze.py::render_report` | Markdown 各节 |
| 导出列 | `scripts/export.py::CSV_COLUMNS` | CSV 明细列 |
| mtop 客户端 | `scripts/mtop.py::MtopClient` | 可复用于其他 mtop 接口（详情页等） |
| 数据目录 | 环境变量 `XIANYU_DATA_DIR` | 默认 `~/.xianyu-data` |

## 扩展示例：新增一个详情接口

```python
from mtop import MtopClient
from login import load_cookies

with MtopClient(load_cookies("~/.xianyu-data/storage_state.json")) as c:
    data = c.request("mtop.taobao.idle.item.detail", {"itemId": "7412..."})
```

签名、token 刷新、风控识别都已由 `MtopClient` 处理；新接口只要沿用同一 appKey 与请求封装即可。
