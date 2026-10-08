# Windows 端接手说明

> 这个仓库在 Linux 上开发，你要在 Windows 上编译/打包。
> 本文说明：怎么拉代码、哪些东西没入库、怎么补齐。

---

## 一、拉取仓库

```bash
git clone https://github.com/GreenOilyChicken/xianyu.git
cd xianyu
```

---

## 二、没有入库的东西（需要自己补）

| 目录/文件 | 为什么没入库 | 怎么补 |
|---|---|---|
| `products/photo-sorter/assets/adb/` | 三平台二进制 30MB+ | 见 [README-依赖下载.md](products/photo-sorter/README-依赖下载.md) |
| `products/kids-worksheet-gen/out/` | 生成的内容包 5.5MB | 跑命令重新生成（见下） |
| `products/kids-worksheet-gen/libs/` | Python 依赖 | `pip install -r requirements.txt` |
| `.xianyu-data/` | **含闲鱼登录 cookie** | 需重新登录抓取工具 |
| `ops/data/` | **含他人手机号等隐私** | 需重新抓取 |

> ⚠️ 前两个是体积原因，后两个是**安全原因**。别把 `.xianyu-data/` 或 `ops/data/` 传到任何公开地方。

---

## 三、口算练习生成器：Windows 上怎么跑

### 1. 装依赖

```bash
cd products/kids-worksheet-gen
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

> 国内直连 pypi.org 会超时，加清华镜像。

### 2. 跑测试（应该 136 项全绿）

```bash
python -m pytest
```

> `pytest.ini` 里已配好 `pythonpath = src`，不用手动设 PYTHONPATH。

### 3. 生成练习卷

```bash
# 单份
python src/main.py --grade g2a --count 40 --out 口算练习.pdf

# 批量（内容包生产）
python src/main.py --batch --grade g2a --sheets 50 --per-sheet 40 --answer-book

# 查题型上限
python src/main.py --grade g1a --capacity

# 列出所有题型
python src/main.py --list-grades
```

### 4. 打包成 exe

```bash
./build.sh              # CLI 版（Git Bash 里跑）
```

或手动：

```bash
pyinstaller --onefile --console --name 口算练习生成器 --paths src src/main.py
```

> **★ 打包后必测**：中文是否乱码。
> reportlab 只支持 TrueType 轮廓字体，Noto CJK 会报错。
> 代码已做多候选探测，但打包环境可能有差异 —— 生成一份 PDF 打开确认。
> 万一找不到字体，用环境变量指定：`set KIDS_FONT_PATH=C:\Windows\Fonts\msyh.ttc`

---

## 四、photo-sorter：Windows 上怎么编译

```bash
cd products/photo-sorter
flutter build windows
```

**前置条件**：
1. 装 Flutter SDK（含 Windows 桌面支持）
2. 补齐 `assets/adb/windows/`（见依赖下载文档）
3. 确认 `pubspec.yaml` 里 `assets/adb/` 已声明

> 注意：photo-sorter 目前**只有方案文档，没有源码**（代码在 Cursor 那边）。
> 需要先把代码放进这个目录。

---

## 五、待办清单（按优先级）

- [ ] **打包 exe 并在干净 Windows 上测中文**（口算生成器工具线）
- [ ] 生成 7 个年级的内容包（内容包线，命令见上）
- [ ] 做商品首图/详情图（决定闲鱼点击率）
- [ ] 写 `specs.md`（功能边界清单）
- [ ] photo-sorter 源码入库

---

## 六、仓库约定

- **提交信息**：中文，说清做了什么
- **不要提交**：`libs/`、`out/`、`.xianyu-data/`、`ops/data/`、`assets/adb/`
  （已在 `.gitignore` 里排除，别用 `git add -f` 强加）
- **敏感信息**：提交前扫一遍手机号/cookie/token

---

## 七、这台 Linux 机器的说明（给未来的自己）

仓库在 `/home/www/xianyu`，属主是 `www`，但日常操作的是 `zyuge`。
`.git` 目录已设为 `777` 以便 `zyuge` 能 push。工作区文件是 `644`。

如果以后权限又出问题，报错通常是：

```
致命错误：检测到可疑的仓库所有权
  → git config --global --add safe.directory /home/www/xianyu

错误：unable to move logfile logs/refs/heads/master ... 权限不够
  → sudo chmod -R a+rwX /home/www/xianyu/.git
```
