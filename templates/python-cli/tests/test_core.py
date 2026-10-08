"""core.py 的单元测试。接单交付前至少跑通核心逻辑的测试。"""
from pathlib import Path

from core import run


def test_run_basic(tmp_path: Path):
    """基本流程：输入存在 → 输出目录被创建。"""
    inp = tmp_path / "in"
    inp.mkdir()
    (inp / "a.txt").write_text("hi")
    out = tmp_path / "out"

    run(input_path=inp, output_path=out, verbose=False)

    assert out.exists() and out.is_dir()


def test_run_missing_input(tmp_path: Path):
    """输入不存在 → 抛 FileNotFoundError。"""
    import pytest
    with pytest.raises(FileNotFoundError):
        run(input_path=tmp_path / "nope", output_path=tmp_path / "out")
