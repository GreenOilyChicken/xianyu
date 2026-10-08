"""资源路径解析测试。

★ 重点：PyInstaller --onefile 打包后，Path(__file__).parent.parent 会失效。
本测试模拟 sys._MEIPASS 环境，锁死"打包后能找到字表"这个行为，
避免以后改动导致打包版静默失效。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

import resource_path


@pytest.fixture
def frozen_env(tmp_path, monkeypatch):
    """模拟 PyInstaller 打包环境。"""
    fake_meipass = tmp_path / "_MEI12345"
    assets = fake_meipass / "assets"
    assets.mkdir(parents=True)
    (assets / "chars_3500.txt").write_text("永和九年", encoding="utf-8")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(fake_meipass), raising=False)
    return fake_meipass


@pytest.fixture
def source_env(monkeypatch):
    """模拟源码运行环境。"""
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)


# ------------------------------------------------------------ 源码模式

def test_source_not_frozen(source_env):
    assert resource_path.is_frozen() is False


def test_source_root_is_project_root(source_env):
    root = resource_path.resource_root()
    # src/resource_path.py 的上两级 = 项目根，其下有 assets/
    assert (root / "assets").is_dir()
    assert (root / "src").is_dir()


def test_source_char_file_exists(source_env):
    cf = resource_path.char_file_default()
    assert cf.exists()
    assert cf.name == "chars_3500.txt"


def test_source_asset_path(source_env):
    p = resource_path.asset_path("chars_3500.txt")
    assert p == resource_path.resource_root() / "assets" / "chars_3500.txt"


# ------------------------------------------------------------ 打包模式

def test_frozen_detected(frozen_env):
    assert resource_path.is_frozen() is True


def test_frozen_root_is_meipass(frozen_env):
    assert resource_path.resource_root() == frozen_env


def test_frozen_char_file_resolves(frozen_env):
    """核心保证：打包后字表路径指向 _MEIPASS/assets/。"""
    cf = resource_path.char_file_default()
    assert cf == frozen_env / "assets" / "chars_3500.txt"
    assert cf.exists()


def test_frozen_nested_asset(frozen_env):
    p = resource_path.asset_path("sub", "file.txt")
    assert p == frozen_env / "assets" / "sub" / "file.txt"


# ------------------------------------------------------------ 描述输出

def test_describe_source(source_env):
    text = resource_path.describe()
    assert "源码" in text
    assert "字表存在: 是" in text


def test_describe_frozen(frozen_env):
    text = resource_path.describe()
    assert "打包" in text
    assert str(frozen_env) in text
    assert "字表存在: 是" in text


def test_describe_reports_missing(frozen_env, monkeypatch):
    """字表缺失时应明确报告，而不是静默。"""
    (frozen_env / "assets" / "chars_3500.txt").unlink()
    assert "字表存在: 否" in resource_path.describe()
