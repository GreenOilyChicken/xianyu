# xianyu-search · 闲鱼行情抓取与分析 Skill

![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)
![Tests](https://img.shields.io/badge/tests-28%20passed-brightgreen.svg)
[![GitHub](https://img.shields.io/badge/GitHub-SearchT--zy%2Fxianyu--search-181717.svg)](https://github.com/SearchT-zy/xianyu-search)
[![Changelog](https://img.shields.io/badge/CHANGELOG-0.2.0-orange.svg)](CHANGELOG.md)

一个本地运行的闲鱼（goofish.com）数据抓取与分析工具集：输入一个关键词，就能拿到在售商品列表，并自动生成多维行情分析报告。既可以直接配合 AI Agent 使用（SKILL.md），也可以作为独立 CLI / Python 库用于**定制开发**。

> 🖥️ 配套的**对话式网页版**是独立项目 `xianyu-web`（自带完整抓取代码、独立 venv 运行），支持配置大模型 API Key（DeepSeek/OpenAI 兼容）做智能意图解析和 AI 解读报告，两个项目共享同一登录态和数据库。

## 功能一览

| 功能 | 命令 | 说明 |
|---|---|---|
| 环境自检 | `doctor` | 只读检查 Python / 依赖 / 浏览器 / 登录态 |
| 扫码登录 | `login` | 一次性扫码，之后纯 HTTP 抓取；支持 Cookie 导入 |
| 搜索抓取 | `search "关键词"` | 多页翻页、价格/地区过滤、排序、去重、自动入库 |
| 行情分析 | `analyze "关键词"` | 生成 Markdown 分析报告（见下方「分析维度」） |
| 趋势对比 | `trend "关键词"` | 多批次中位价变化 |
| 商品历史 | `history "标题或ID"` | 单个商品跨批次价格轨迹 |
| 批次管理 | `batches` | 查看历史抓取记录 |
| 数据导出 | `export` | CSV（Excel 友好）/ JSON 明细与趋势 |
| 上新监控 | `watch "关键词"` | 周期抓取，只报告新增商品（间隔 ≥30 分钟） |

## 快速开始

```powershell
# 1. 准备环境（一次）
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m playwright install chromium    # 本机有 Chrome 可跳过
scripts\xianyu.cmd doctor

# 2. 登录（一次，本人扫码）
scripts\xianyu.cmd login

# 3. 抓取
scripts\xianyu.cmd search "iPhone 15 Pro" --pages 3
scripts\xianyu.cmd search "MacBook Air M2" --pages 2 --min-price 3500 --max-price 6000 --location 上海

# 4. 分析（默认分析最近一次批次）
scripts\xianyu.cmd analyze "iPhone 15 Pro"
```

macOS/Linux 把 `.venv\Scripts\python` 换成 `.venv/bin/python`，`scripts\xianyu.cmd` 换成 `scripts/xianyu.sh`。

> 国内网络：pip 加 `-i https://pypi.tuna.tsinghua.edu.cn/simple`；Playwright 浏览器下载慢先设
> `$env:PLAYWRIGHT_DOWNLOAD_HOST="https://cdn.npmmirror.com/binaries/playwright"`。

### pip 安装方式（可选）

```powershell
pip install -e .        # 装完后直接使用 xianyu 命令
xianyu doctor
xianyu search "猫别墅" --pages 3
xianyu analyze "猫别墅"
```

> pip 方式下登录态/数据目录逻辑不变；Agent Skill 场景仍建议直接用 `scripts/xianyu.cmd`。

### 无浏览器环境登录

在你自己电脑的 Chrome/Edge 登录 goofish.com，用 Cookie-Editor 等扩展复制 Cookie 字符串：

```powershell
scripts\xianyu.cmd login --cookie-stdin < cookie.txt
```

## 分析维度

`analyze` 生成的报告包含：

1. **价格概况**：样本数、均值、中位数、P25/P75、最低/最高、标准差 + ASCII 直方图
2. **成色分组**：全新 / 二手 / 未知的中位价与价格范围、包邮比例
3. **商品构成**：标题属性命中（容量、版本、电池、官换、急出、可刀……）
4. **卖家与信用**：信用等级分布、挂牌最多的卖家（识别批量铺货商家号）
5. **地区与时效**：地区分布 Top、上架时间分布（今天/3天内/7天内/更早）
6. **热度**：想要人数 Top 10
7. **风险提示**：异常低价清单（低于 P25 − 1.5×IQR 或中位价 60%，防引流/诈骗话术）
8. **捡漏候选**：低价 + 高信用/新成色，附商品链接
9. **趋势**：与上一批次的样本数、中位价变化
10. **结论与建议**：基于数据自动生成购买参考

## 定制开发

### 1. 当库用

```python
import sys
sys.path.insert(0, "scripts")

from login import load_cookies
from mtop import MtopClient
from spider import crawl
from store import connect, save_batch
from analyze import describe, render_report
from export import write_items_csv

cookies = load_cookies("~/.xianyu-data/storage_state.json")
with MtopClient(cookies) as client:
    summary = crawl(client, "显卡 4090", pages=2, max_price=15000)
    report = render_report("显卡 4090", summary.items)
```

### 2. 当数据管道用

每次 `search` 都会落盘一份结果 JSON（默认 `~/.xianyu-data/results/<批次>.json`），字段稳定、任何语言可消费；同时写入 SQLite（`~/.xianyu-data/xianyu.db`，三张表：batches / items / observations）。字段说明见 `references/data_schema.md`。

### 3. 常见定制点

| 想改什么 | 改哪里 |
|---|---|
| 抓取字段变化导致解析失败 | `parser.py` 的 `item_from_card()`（对照 `--dump-raw` 的原始响应） |
| 标题属性分析维度 | `analyze.py` 的 `ATTR_PATTERNS` 表 |
| 排序方式 | `spider.py` 的 `SORT_MAP` |
| 数据目录 | 环境变量 `XIANYU_DATA_DIR` |
| 风险/捡漏判定阈值 | `analyze.py` 的 `risk_flags()` / `deal_candidates()` |
| 抓取节奏 | `search --delay-min/--delay-max/--punish-backoff` |

## 原理

- 登录一次后，通过闲鱼网页版 mtop 搜索接口 `mtop.taobao.idlemtopsearch.pc.search` 抓取，签名算法为标准 mtop 方案（见 `scripts/mtop.py`）；token 过期自动刷新重试。
- 商品字段主要取自响应的 `clickParam.args`（干净数值），`exContent` 兜底（见 `scripts/parser.py`）。
- 风控策略：页间随机延迟 2–5s；触发风控退避重试一次后停止并保留已抓数据。**不破解、不绕过验证码。**

## 项目结构

```
xianyu-search/
├── SKILL.md               Agent Skill 指令（含触发条件与安全规则）
├── scripts/               CLI 与核心模块（mtop/parser/spider/login/store/analyze/export）
├── references/            api_reference.md（CLI 契约）· data_schema.md（字段与扩展点）
├── docs/                  ARCHITECTURE.md（数据流与模块地图）
├── tests/                 28 个离线单测
├── evals/                 skill 触发评测用例
├── pyproject.toml         pip 安装与 xianyu 命令入口
├── CHANGELOG.md           版本历史
├── SECURITY.md            安全与合规边界
└── CONTRIBUTING.md        贡献指南
```

## 合规与免责

- 仅供个人学习研究使用。请遵守闲鱼服务条款与 robots 约定，控制请求频率；由此产生的账号风险由使用者自负。
- 本工具不提供下单、聊天、自动回复等交易功能；分析结论基于当前在售列表，成色/真伪/保修等以商品页为准，交易风险自担。

## 测试

```powershell
python -m unittest discover -s tests -v
```

全部为离线测试，覆盖解析、统计、报告渲染与 SQLite 存储，不消耗请求配额。
