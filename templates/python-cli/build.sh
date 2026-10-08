#!/usr/bin/env bash
# 打包成单文件 exe。用法：./build.sh 工具名
set -e
NAME="${1:-app}"
pyinstaller --onefile --windowed --name "$NAME" --clean main.py
echo "✅ 产物: dist/$NAME.exe"
echo "   测试: 在干净的 Windows 上跑一遍"
