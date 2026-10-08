# CLI 契约与输出参考

- 所有命令通过 `scripts/xianyu.py COMMAND ...` 调用（Windows 可用 `scripts\xianyu.cmd` 包装）。
- 诊断日志走 stderr；业务输出走 stdout。
- 出错时 stdout 输出一个 JSON 对象 `{"ok": false, "error": "...", "error_type": "..."}`，退出码 `2`；用户取消退出码 `130`。

## doctor

只读检查，不联网、不启动浏览器、不写文件、不读取凭证内容。

```json
{
  "ok": false,
  "checks": [
    {"name": "python", "ok": true, "detail": "Python 3.11.9（需要 >= 3.10）"},
    {"name": "httpx", "ok": true, "detail": "已安装"},
    {"name": "playwright", "ok": true, "detail": "已安装"},
    {"name": "browser", "ok": true, "detail": "本机 Chrome：C:\\..."},
    {"name": "data-dir", "ok": true, "detail": "数据目录：..."},
    {"name": "state", "ok": false, "detail": "未找到登录态文件 ..."}
  ],
  "next_action": {"code": "login-required", "message": "运行 xianyu.py login 扫码登录"}
}
```

`next_action.code`：`upgrade-python` / `install-dependencies` / `install-browser` / `fix-data-dir` / `login-required` / `ready`。退出码：ready 为 0，否则 2。

## login

```text
--state PATH      登录态输出路径（默认 ~/.xianyu-data/storage_state.json）
--timeout SEC     等待登录秒数（默认 300）
--channel NAME    浏览器通道（chrome / msedge 等；默认自动选择）
--cookie-stdin    从 stdin 读 Cookie 头字符串构建登录态（免浏览器）
--quiet           减少提示
```

成功输出一行「登录成功，登录态已保存到 …」。登录态文件权限为仅当前用户可读。`--cookie-stdin` 要求 Cookie 串中包含 `unb`，否则报 `NotLoggedInError`。

## search

```text
keyword            必填
--pages, -p N      页数，默认 3，上限 50
--rows N           每页条数，默认 30
--min-price X      最低价（含边界，本地过滤）
--max-price Y      最高价（含边界，本地过滤）
--location S       地区子串（本地过滤）
--sort NAME        default | time | price-asc | price-desc（提示性排序）
--state PATH       登录态路径（默认同 login）
--delay-min A      页间随机延迟下界（默认 2.0s）
--delay-max B      页间随机延迟上界（默认 5.0s）
--punish-backoff S 风控退避秒数（默认 60）
--dump-raw         每页原始响应写入 数据目录/raw/
--no-store         不入 SQLite，只写结果 JSON
--note TEXT        批次备注
--out PATH         结果 JSON 路径（默认 数据目录/results/<批次>.json）
--json             stdout 输出机器可读 JSON
--quiet            减少 stderr 日志
```

结果 JSON 结构：

```json
{
  "ok": true,
  "keyword": "iPhone 15 Pro",
  "batch_id": "iPhone_15_Pro_20260730_153000",
  "count": 87,
  "pages_scraped": 3,
  "pages_requested": 3,
  "partial": false,
  "error": null,
  "error_type": null,
  "filters": {"min_price": null, "max_price": null, "location": null, "sort": "default"},
  "items": [
    {
      "item_id": "7412...",
      "title": "...",
      "price": 4999.0,
      "area": "上海",
      "seller": "...",
      "seller_id": "...",
      "pic_url": "https://...",
      "credit_level": 6,
      "condition": "全新",
      "free_ship": true,
      "publish_time": "2026-07-24",
      "want_num": 12,
      "tags": ["全新", "12人想要"],
      "url": "https://www.goofish.com/item?id=...",
      "seller_url": "https://www.goofish.com/user?userId=..."
    }
  ]
}
```

风控中断时 `partial: true` 且 `error_type: "RateLimitedError"`，`items` 保留已抓部分。退出码仍为 0（有部分数据可用）；`SessionExpiredError` / `NotLoggedInError` 等致命错误退出码 2。

## analyze

```text
keyword            关键词（默认分析其最近一次批次）
--batch ID         指定批次
--json-file PATH   直接分析一个结果 JSON（或 {"items": [...]}）
--min-price X      分析时二次过滤（排除占位价）
--max-price Y      分析时二次过滤
--bins N           直方图分箱数（默认 10）
--out PATH         报告输出路径（默认 数据目录/results/report_*.md）
--json             stdout 只输出 {"ok": true, "report_path": ..., "count": ...}
--quiet            只打印报告路径
```

默认把完整 Markdown 报告打印到 stdout。报告各节见 README「分析维度」。

## trend

```text
keyword            必填
--last N           最近 N 个批次（默认 10，按时间正序展示）
--json             stdout 输出 {"ok": true, "rows": [[时间,批次,数量,最低,中位,最高,中位变化,状态], ...]}
```

## history

```text
query              纯数字按 item_id 精确匹配；否则按标题子串匹配
--json             stdout 输出 {"ok": true, "rows": [{batch_id, item_id, price, title, crawled_at, keyword}, ...]}
```

## batches

```text
keyword            可选过滤
--limit N          默认 50
--json             stdout 输出 {"ok": true, "batches": [...]}
```

## export

```text
keyword            关键词（默认其最近一批）
--batch ID         或指定批次
--csv PATH         明细 CSV（utf-8-sig，Excel 友好）
--json PATH        明细 JSON
--out PATH         未指定 --csv/--json 时的默认 CSV 路径
--trend            改为导出趋势统计
--last N           与 --trend 连用，取最近 N 批（默认 10）
```

明细 CSV 列：`item_id, title, price, area, seller, seller_id, credit_level, condition, free_ship, publish_time, want_num, url, seller_url`。
趋势 CSV 列：`time, batch_id, keyword, count, min, median, max, mean, p25, p75`。

## watch

```text
keyword            必填
--interval SEC     轮询间隔，默认 1800，最小 1800（30 分钟）
--max-runs N       轮数上限（默认无限，Ctrl+C 退出）
--pages N          每轮页数（默认 1）
--rows N           每页条数（默认 30）
--min-price X / --max-price Y / --location S   过滤
--state PATH       登录态路径
--json             每轮 stdout 输出 JSON：{ok, run, keyword, batch_id, count, new_count, new_items, error, error_type}
```

每轮都会入库为新批次；「新增」= 此前任何批次都没见过的 item_id。风控中断时该轮 `ok: false` 且 `error_type: "RateLimitedError"`，循环继续（下一轮自然等到间隔之后）。

## 错误类型

| error_type | 含义 | 处置 |
|---|---|---|
| `NotLoggedInError` | 缺登录态 | login |
| `SessionExpiredError` | 登录失效 | 重新 login |
| `RateLimitedError` | 风控/滑块 | 停止，冷却 ≥30 分钟 |
| `TokenError` | mtop 签名 token 异常 | 重新 login |
| `ParseError` | 响应结构变化 | --dump-raw 排查，修 parser.py |
| `XianyuError` | 其他接口/业务错误 | 按 message 处理 |
