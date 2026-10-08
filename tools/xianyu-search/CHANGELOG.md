# Changelog

本文件记录 xianyu-search 的重要变更。版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.2.0] - 2026-08-20

### 新增
- `watch` 命令：周期性抓取并只报告新增商品（间隔最低 30 分钟）。
- `trend` / `history` / `batches` 命令：多批次行情趋势、单商品价格历史、批次管理。
- `export` 命令：CSV（utf-8-sig，Excel 友好）/ JSON 明细与趋势导出。
- 分析报告新增：标题属性命中、挂牌最多卖家、与上一批次对比。
- `doctor` 环境自检命令（只读、不启动浏览器）。
- 结果 JSON 落盘（每次 search 一份，作为稳定数据接口）。

### 修复
- Windows 控制台 GBK 编码导致中文/emoji 输出崩溃 → 启动时强制 UTF-8 stdio。
- 带 BOM 的 JSON 文件读取失败 → 统一 utf-8-sig。
- 历史批次分析串价（读 items 表最新价而非该批次观测快照）→ `load_items` 改用 observations 快照。
- 第 1 页有广告卡被跳过时误判为末页 → 末页判定改用 API 原始卡片数。
- 异常低价漏报（1 元占位价未被识别）→ 增加「低于 max(10, 中位价×20%)」的引流价判据，且风险商品不再混入捡漏候选。

## [0.1.0] - 2026-08-20

### 初始版本
- mtop 签名客户端（token 自动刷新、风控分类与退避）。
- Playwright 扫码登录 + Cookie 导入（`login --cookie-stdin`）。
- 多页搜索抓取（页间随机延迟、运行内去重、本地价格/地区过滤、排序提示）。
- 多维分析报告（价格统计/直方图/成色/信用/地区/时效/热度/风险/捡漏/结论）。
- SQLite 持久化（batches / items / observations）。
- 离线单元测试套件（解析/统计/报告/存储/翻页）。
