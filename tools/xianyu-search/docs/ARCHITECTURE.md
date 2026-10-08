# 架构说明

## 数据流

```
用户/Agent 说「帮我查 猫别墅 100元以内」
        │
        ▼
  xianyu.py CLI（或 xianyu-web 的 chat 接口）
        │
        ├─ doctor    环境自检（Python/依赖/浏览器/登录态）
        ├─ login     Playwright 扫码（一次性）→ storage_state.json（Cookie，仅本机）
        ▼
  spider.crawl() ──► MtopClient.request()  ──► h5api.m.goofish.com
        │                 │  sign = md5(token&t&appKey&data)
        │                 │  token = _m_h5_tk cookie（自动刷新重试）
        │                 ▼
        │              resultList（原始 JSON）
        ▼
  parser.parse_search_response() ──► Item（item_id/title/price/area/seller/credit/…）
        │
        ├─► store.save_batch()  → SQLite（batches / items / observations）
        └─► 结果 JSON 落盘（results/<批次>.json，稳定数据接口）
        │
        ▼
  analyze.render_report() ──► Markdown 报告（统计/直方图/成色/信用/地区/热度/风险/捡漏/结论）
        │
        ├─► trend / history / batches / export（趋势、价格历史、导出 CSV/JSON）
        └─► watch（周期抓取，只报告新增商品）
```

## 模块地图

| 模块 | 职责 | 定制点 |
|---|---|---|
| `scripts/common.py` | 常量、路径（`~/.xianyu-data`）、错误类型、`Item` 数据类 | 环境变量 `XIANYU_DATA_DIR` |
| `scripts/mtop.py` | mtop 签名 + HTTP 客户端；token 自动刷新；风控分类（RGV587/滑块→停止） | 复用同一客户端接其他 mtop 接口 |
| `scripts/parser.py` | 搜索结果 → `Item` | **字段变动唯一入口** `item_from_card()` |
| `scripts/spider.py` | 翻页编排：随机延迟、退避重试、去重、本地过滤、末页判定 | `SORT_MAP` 排序映射 |
| `scripts/login.py` | 扫码登录 / Cookie 导入 / 凭证加载 | `--channel` 浏览器通道 |
| `scripts/store.py` | SQLite 持久化（批次快照语义） | — |
| `scripts/analyze.py` | 统计 + 报告渲染 | `ATTR_PATTERNS`、`risk_flags`、`deal_candidates` |
| `scripts/export.py` | CSV（utf-8-sig）/ JSON 导出 | `CSV_COLUMNS` |
| `scripts/doctor.py` | 只读环境自检 | — |
| `scripts/xianyu.py` | CLI 分发（9 个子命令） | — |

## 关键设计决策

1. **登录一次 + 纯 HTTP**：`login` 用 Playwright 打开可见浏览器让用户本人扫码，
   之后所有抓取都是普通 HTTP 请求（mtop 接口），速度快且不需要常驻浏览器。
2. **批次快照语义**：`observations` 表保存每个批次对每个商品的当时价格；
   分析历史批次读观测快照而非 items 表最新值，避免趋势串价。
3. **风控即停**：触发验证码/风控退避重试一次后停止并保留已抓数据，绝不绕行。
   页间 2–5 秒随机延迟，同关键词 10 分钟冷却，`watch` 间隔下限 30 分钟。
4. **凭证隔离**：登录态只存 `~/.xianyu-data/storage_state.json`（当前用户权限），
   任何输出都不包含 Cookie；`login --cookie-stdin` 供无浏览器环境导入。
5. **结果 JSON 即接口**：每次 search 落盘一份完整结果 JSON，外部系统（含
   `xianyu-web`）无需依赖本仓库即可消费。

## 与 xianyu-web 的关系

`xianyu-web`（独立项目）内置了同源的 `scraper/` 包。闲鱼接口字段变动时，
同步更新两边的 `parser.py`（其余模块互不影响）。
