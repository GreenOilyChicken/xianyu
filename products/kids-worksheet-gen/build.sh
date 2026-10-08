#!/usr/bin/env bash
# 打包成单文件 exe。
# 用法：./build.sh            打包 CLI 版
#       ./build.sh --gui      打包 GUI 版（需先实现 src/gui.py）
set -euo pipefail

cd "$(dirname "$0")"

NAME="口算练习生成器"
SEP=":"   # PyInstaller --add-data 的分隔符：Unix 用 : ，Windows 用 ;

# Git Bash / MSYS / Cygwin 下跑的是 Windows 版 PyInstaller，分隔符必须是 ;
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) SEP=";" ;;
esac

# ---------- 依赖预检 ----------
# pkg_resources 在 setuptools 81+ 被移除，而 PyInstaller 的依赖 altgraph
# 仍然 import 它，缺了会直接 ModuleNotFoundError: No module named 'pkg_resources'。
if ! python -c "import pkg_resources" 2>/dev/null; then
    echo "❌ 缺少 pkg_resources（PyInstaller 的依赖 altgraph 需要它）" >&2
    echo "   原因：setuptools 81+ 已移除 pkg_resources" >&2
    echo "   修复：pip install \"setuptools<81\"" >&2
    exit 1
fi

if ! python -c "import PyInstaller" 2>/dev/null; then
    echo "❌ 未安装 PyInstaller，请先：pip install pyinstaller" >&2
    exit 1
fi

if [[ "${1:-}" == "--gui" ]]; then
    ENTRY="src/gui.py"
    MODE="--windowed"
    if [[ ! -f "$ENTRY" ]]; then
        echo "❌ $ENTRY 不存在，GUI 版尚未实现（见 重构方案.md 提示词 2）" >&2
        exit 1
    fi
else
    ENTRY="src/main.py"
    MODE="--console"
fi

# ---------- 资源检查 ----------
if [[ ! -f assets/chars_3500.txt ]]; then
    echo "❌ 缺少 assets/chars_3500.txt（字帖模式的字表）" >&2
    exit 1
fi

echo "▶ 打包 $ENTRY （模式 $MODE）"
echo "  分隔符: $SEP   资源: assets/"

pyinstaller \
    --onefile \
    "$MODE" \
    --name "$NAME" \
    --clean \
    --noconfirm \
    --paths src \
    --add-data "assets${SEP}assets" \
    "$ENTRY"

echo
echo "✅ 产物: dist/$NAME.exe"
echo
echo "⚠️  交付前必做："
echo "   1. 在干净的 Windows 机器上跑一遍（确认无缺失 dll）"
echo "   2. 确认中文不乱码："
echo "      dist/口算练习生成器.exe --grade g2a --count 10 --out 测试.pdf"
echo "   3. 确认字表能读到（打包后资源路径的关键验证）："
echo "      dist/口算练习生成器.exe --mode zitie --chars 永和九年 --out 字帖.pdf"
echo "   4. 若报字体找不到，用环境变量指定："
echo "      set KIDS_FONT_PATH=C:\\Windows\\Fonts\\msyh.ttc"
