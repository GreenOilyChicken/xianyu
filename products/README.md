# 小工具打包与交付规范

> 每个可售卖工具在 `products/<工具名>/` 下独立成目录。
> 本文件规定四种形态的开发、打包、交付标准。

## 通用结构

每个工具目录长这样：

```
products/<工具名>/
├── README.md          # 上架文案（用 copywriting/gen_copy.py 生成）
├── specs.md          # 需求/功能清单（自用，记录做了什么）
├── src/              # 源码
│   ├── ...
│   └── requirements.txt / package.json
├── dist/             # 打包好的成品（交付给买家）
│   ├── <工具名>.exe
│   ├── 使用说明.pdf
│   └── 教程视频.mp4
└── .gitignore        # 不传 dist/ 大文件
```

## 形态一：Python 单文件 / exe

**最优先**。开发快、售后轻、适合走量。

### 开发
- 单入口 `main.py`，所有逻辑尽量收敛，减少依赖
- 依赖只装必需的，能在 Win/Mac 跑就别挑平台
- `requirements.txt` 锁版本

### 打包成 exe
```bash
# 在工具 src/ 目录下
pip install pyinstaller
pyinstaller --onefile --windowed --name <工具名> --icon <icon.ico> main.py
# 产物在 dist/<工具名>.exe
```

要点：
- `--onefile` 单文件，买家下载即用
- `--windowed` 不弹黑框（命令行工具用 `--console`）
- 资源文件（图标/字体）用 `--add-data` 打进去
- 打完到干净 Win 机器测一遍，确认无缺失 dll

### 交付清单
- [ ] `dist/<工具名>.exe`
- [ ] 使用说明（PDF 或 md，截图步骤化）
- [ ] 演示视频（30秒-2分钟，发闲鱼当素材）
- [ ] 常见问题清单

---

## 形态二：桌面程序（Electron / Vue + Tauri）

界面友好，演示效果好，客单价高一档。

### 开发
- 前端 Vue3 + Vite，桌面壳用 Tauri（轻量）或 Electron（生态全）
- 后端逻辑能内嵌就内嵌，别起独立服务
- Tauri 优先（产物小，5-10MB；Electron 动辄 100MB+）

### 打包
```bash
# Tauri
npm run tauri build        # 产物 src-tauri/target/release/bundle/

# Electron
npm run build              # 配 electron-builder
```

### 交付清单
- [ ] 安装包 `.exe`（Tauri 用 msi/nsis，Electron 用 nsis）
- [ ] 免安装版 `.zip`（解压即用，部分买家不爱装）
- [ ] 使用说明
- [ ] 演示视频（录界面操作）

---

## 形态三：Web 应用（Vue + Java/Python 后端）

**只接定制，不做成品囤货**。部署售后重。

### 开发
- 前端 Vue3 + Vite + 组件库（Element Plus / Ant Design Vue）
- 后端二选一：
  - Python：FastAPI（轻量，部署简单，推荐小工具）
  - Java：Spring Boot（企业向需求）
- 数据库 SQLite 起步（单机部署免装 DB），需要多用户再上 MySQL

### 打包交付
- 前端 `npm run build` 出静态文件
- 后端 Python 用 `pyinstaller` 或 Docker；Java 用 `mvn package`
- 提供二选一交付：
  - **A. 客户自部署**：交付源码 + 部署文档（docker-compose 一键起）
  - **B. 我帮部署**：帮部署到客户服务器，收部署费 + 首年维护费

### 交付清单
- [ ] 源码（前端 + 后端）
- [ ] 部署文档（docker-compose / 手动步骤）
- [ ] 数据库初始化脚本
- [ ] 接口文档（如有二次开发可能）
- [ ] 首次部署协助（远程或文档）

---

## 形态四：嵌入式定制

走 `templates/` 脚手架 + 交付文档，按单开发。

### 交付清单
- [ ] 源代码（含注释）
- [ ] 原理图 / 接线图
- [ ] 元件清单 BOM
- [ ] 实物（如约定含硬件）
- [ ] 使用说明文档
- [ ] 演示视频

---

## 通用约定

1. **dist/ 不进 git**：大文件、成品二进制，用 `.gitignore` 排除
2. **README.md 是上架文案**：从 `copywriting/gen_copy.py --out products/<工具名>/README.md` 生成
3. **specs.md 记录功能边界**：避免售后扯皮"我以为有这功能"
4. **版本号**：每个工具自己 `v1.0`、`v1.1` 递增，更新内容记进 README
5. **更新策略**：老客户免费更新小版本，大版本（加新功能）半价升级
