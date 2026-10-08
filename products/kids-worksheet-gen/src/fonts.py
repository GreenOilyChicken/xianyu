"""跨平台中文字体查找与注册。

★★ 重要坑（实测）★★
reportlab 只支持 TrueType 轮廓(glyf)的字体，不支持 PostScript/CFF 轮廓。
  - Noto Sans CJK / Noto Serif CJK 的 .ttc 是 PostScript 轮廓
    → registerFont 抛 TTFError: "postscript outlines are not supported"
  - 文泉驿(wqy) / 微软雅黑 / 宋体 / 黑体 是 TrueType 轮廓 → 正常
所以候选表里**故意不放 Noto CJK**，并且每个候选都实际注册一次做验证，
注册失败就跳过，绝不把坏字体交给渲染层。
"""
from __future__ import annotations

import os
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_NAME = "CJK"

# 环境变量覆盖：KIDS_FONT_PATH / KIDS_FONT_INDEX
ENV_PATH = "KIDS_FONT_PATH"
ENV_INDEX = "KIDS_FONT_INDEX"

# (字体文件, ttc 子字体索引)。按平台优先序排列。
CANDIDATES: list[tuple[str, int]] = [
    # ---- Windows ----
    ("C:/Windows/Fonts/msyh.ttc", 0),        # 微软雅黑
    ("C:/Windows/Fonts/msyhbd.ttc", 0),      # 微软雅黑 Bold
    ("C:/Windows/Fonts/simhei.ttf", 0),      # 黑体
    ("C:/Windows/Fonts/simsun.ttc", 0),      # 宋体
    ("C:/Windows/Fonts/Deng.ttf", 0),        # 等线
    # ---- macOS ----
    ("/System/Library/Fonts/PingFang.ttc", 0),          # 苹方
    ("/System/Library/Fonts/STHeiti Light.ttc", 0),     # 华文黑体
    ("/Library/Fonts/Arial Unicode.ttf", 0),
    # ---- Linux ----
    ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0),   # 文泉驿正黑
    ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 0),  # 文泉驿微米黑
    ("/usr/share/fonts/truetype/arphic/uming.ttc", 0),      # AR PL UMing
    ("/usr/share/fonts/truetype/arphic/ukai.ttc", 0),       # AR PL UKai
]

# 题面上会用到的全部字符，用于校验字体字形覆盖是否够用
REQUIRED_CHARS = (
    "一二三四五六七八九十百千万年级口算练习"
    "姓名日期用时分秒得分第页共答案"
    "加减乘除等于"
    "×÷＋－＝"
    "0123456789."
    "（）()、："
)


class FontNotFoundError(RuntimeError):
    """找不到可用的中文字体。"""


_registered: str | None = None


def _try_register(path: str, index: int, name: str) -> bool:
    """尝试注册字体，成功返回 True。不抛异常。"""
    if not Path(path).exists():
        return False
    try:
        pdfmetrics.registerFont(TTFont(name, path, subfontIndex=index))
    except Exception:
        # PostScript 轮廓 / 文件损坏 / ttc 索引越界 等，统一视为不可用
        return False
    return True


def _missing_chars(name: str, required: str) -> str:
    """返回字体缺失的字符集合（去重）。取不到 cmap 时返回空串（视为通过）。"""
    try:
        face = pdfmetrics.getFont(name).face
        cmap = face.charToGlyph
    except Exception:
        return ""
    return "".join(sorted({ch for ch in required if ord(ch) not in cmap}))


def get_cjk_font(required: str = REQUIRED_CHARS) -> str:
    """找到并注册一个可用的中文字体，返回 reportlab 里的字体名。

    结果会被缓存，重复调用不重复注册。
    """
    global _registered
    if _registered is not None:
        return _registered

    candidates: list[tuple[str, int]] = []
    env_path = os.environ.get(ENV_PATH)
    if env_path:
        candidates.append((env_path, int(os.environ.get(ENV_INDEX, "0"))))
    candidates.extend(CANDIDATES)

    tried: list[str] = []
    for i, (path, index) in enumerate(candidates):
        probe = f"__probe_{i}__"
        if not _try_register(path, index, probe):
            tried.append(f"{path}[{index}]")
            continue
        missing = _missing_chars(probe, required)
        if missing:
            tried.append(f"{path}[{index}] 缺字:{missing[:12]}")
            continue
        # 探测成功，用正式名字再注册一次
        _try_register(path, index, FONT_NAME)
        _registered = FONT_NAME
        return _registered

    raise FontNotFoundError(
        "找不到可用的中文字体（需 TrueType 轮廓）。已尝试：\n  "
        + "\n  ".join(tried)
        + f"\n可用环境变量 {ENV_PATH} 手动指定字体文件路径。"
        "\n注意：Noto Sans/Serif CJK 为 PostScript 轮廓，reportlab 不支持。"
    )


def describe() -> str:
    """返回当前使用的字体路径说明，用于日志/排查。"""
    name = get_cjk_font()
    try:
        face = pdfmetrics.getFont(name).face
        return f"{name} <- {getattr(face, 'filename', '?')}"
    except Exception:
        return name
