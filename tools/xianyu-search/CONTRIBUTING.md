# Contributing

欢迎贡献。提交前请阅读 [SECURITY.md](SECURITY.md) 了解数据与抓取行为边界。

## 开发环境

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
# 本机有 Chrome 可跳过浏览器下载：
.venv\Scripts\python -m playwright install chromium
```

## 运行测试

```powershell
python -m unittest discover -s tests -v
```

全部为离线测试（解析 / 统计 / 报告 / 存储 / 翻页），不消耗请求配额，无需登录。

## 提交约定

- 改动字段解析只改 `scripts/parser.py::item_from_card`，用 `search --dump-raw`
  保留原始响应作为排查依据。
- 新增分析维度放在 `scripts/analyze.py`，并为纯函数补单测。
- 不要提交登录态、Cookie、`~/.xianyu-data` 下的任何文件。
- 如接口字段变动，同时同步 `xianyu-web` 项目的 `scraper/parser.py`。

## 目录结构

```
xianyu-search/
├── SKILL.md               Agent Skill 指令（DSH/Claude 兼容 frontmatter）
├── scripts/               CLI 与核心模块（见 docs/ARCHITECTURE.md）
├── references/            CLI 契约与数据 Schema
├── tests/                 离线单测
├── docs/                  架构说明
└── evals/                 skill 触发评测用例
```
