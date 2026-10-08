"""资源路径解析：兼容源码运行与 PyInstaller 打包。

★ 为什么需要这个模块 ★
PyInstaller --onefile 打包后，代码被解压到临时目录（sys._MEIPASS），
此时 Path(__file__).parent.parent / "assets" 指向的位置**不存在**，
字表等资源会 FileNotFoundError。

正确做法：优先用 sys._MEIPASS（打包后），回落到源码树（开发时）。
同时打包命令必须用 --add-data 把 assets 打进去。
"""
from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    """是否运行在 PyInstaller 打包环境里。"""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def resource_root() -> Path:
    """返回资源根目录（其下应有 assets/）。"""
    if is_frozen():
        # PyInstaller 解压目录
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    # 源码运行：src/resource_path.py → 上两级是项目根
    return Path(__file__).resolve().parent.parent


def asset_path(*parts: str) -> Path:
    """拼出 assets/ 下的资源路径。

    用法：
        asset_path("chars_3500.txt")  → <root>/assets/chars_3500.txt
    """
    return resource_root() / "assets" / Path(*parts)


def char_file_default() -> Path:
    """内置字表文件的默认路径。"""
    return asset_path("chars_3500.txt")


def describe() -> str:
    """诊断信息，排查打包后资源找不到时用。"""
    frozen = is_frozen()
    root = resource_root()
    cf = char_file_default()
    return (
        f"运行模式: {'PyInstaller 打包' if frozen else '源码'}\n"
        f"资源根目录: {root}\n"
        f"字表文件: {cf}\n"
        f"字表存在: {'是' if cf.exists() else '否 ← 若为否则 --add-data 没配对'}"
    )
