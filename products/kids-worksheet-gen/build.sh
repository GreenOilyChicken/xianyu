#!/usr/bin/env bash
# 打包成单文件 exe。
# 用法：./build.sh            打包 CLI 版
#       ./build.sh --gui      打包 GUI 版（需先实现 src/gui.py）
set -euo pipefail

cd "$(dirname "$0")"

NAME="口算练习生成器"

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

echo "▶ 打包 $ENTRY （模式 $MODE）"

pyinstaller \
    --onefile \
    "$MODE" \
    --name "$NAME" \
    --clean \
    --noconfirm \
    --paths src \
    "$ENTRY"

echo
echo "✅ 产物: dist/$NAME.exe"
echo
echo "⚠️  交付前必做："
echo "   1. 在干净的 Windows 机器上跑一遍（确认无缺失 dll）"
echo "   2. 确认中文不乱码（字体探测在打包后是否正常）"
echo "   3. 测试：生成一份 PDF 并打开"
