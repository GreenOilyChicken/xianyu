"""口算题生成核心逻辑测试。

覆盖：数学正确性、年级范围约束、去重、进位筛选、整除性。
"""
from __future__ import annotations

import random

import pytest

from core import (
    GRADES,
    GenerationError,
    Problem,
    generate_problems,
    has_borrow,
    has_carry,
)


# ------------------------------------------------------------ 基础运算正确性

@pytest.mark.parametrize("a,b,op,expected", [
    (3, 5, "+", 8),
    (12, 7, "-", 5),
    (6, 7, "×", 42),
    (56, 8, "÷", 7),
])
def test_answer_correct(a, b, op, expected):
    assert Problem(a, b, op).answer == expected


def test_text_format():
    assert Problem(3, 5, "+").text() == "3 + 5 ="
    assert Problem(3, 5, "+").text("____") == "3 + 5 = ____"


# ------------------------------------------------------------ 进位/借位判定

@pytest.mark.parametrize("a,b,expect", [
    (3, 5, False),     # 3+5=8，个位不进位
    (7, 5, True),      # 个位 7+5=12 进位
    (23, 45, False),   # 无进位
    (28, 45, True),    # 个位进位
    (95, 8, True),     # 进位传播
    (100, 200, False), # 多位数无进位
])
def test_has_carry(a, b, expect):
    assert has_carry(a, b) is expect


@pytest.mark.parametrize("a,b,expect", [
    (8, 3, False),     # 个位 8-3 够减
    (12, 5, True),     # 个位 2-5 借位
    (30, 12, True),    # 个位 0-2 借位
    (38, 12, False),   # 个位 8-2 够减
    (100, 1, True),    # 连续借位传播
])
def test_has_borrow(a, b, expect):
    assert has_borrow(a, b) is expect


# ------------------------------------------------------------ 生成数量与去重

def test_generate_count_exact():
    ps = generate_problems(GRADES["g2a"], 40, rng=random.Random(1))
    assert len(ps) == 40


def test_no_duplicates_by_default():
    ps = generate_problems(GRADES["g2a"], 60, rng=random.Random(2))
    keys = [p.key() for p in ps]
    assert len(keys) == len(set(keys))


def test_zero_count_returns_empty():
    assert generate_problems(GRADES["g2a"], 0) == []


def test_negative_count_raises():
    with pytest.raises(ValueError):
        generate_problems(GRADES["g2a"], -1)


def test_same_seed_same_result():
    a = generate_problems(GRADES["g3b"], 30, rng=random.Random(99))
    b = generate_problems(GRADES["g3b"], 30, rng=random.Random(99))
    assert [p.key() for p in a] == [p.key() for p in b]


# ------------------------------------------------------------ 年级范围约束

@pytest.mark.parametrize("code", list(GRADES.keys()))
def test_all_grades_respect_constraints(code):
    """每个年级生成 150 道，全部满足：无负数、不超上限、除法整除。"""
    spec = GRADES[code]
    ps = generate_problems(spec, 150, rng=random.Random(5))
    for p in ps:
        assert p.answer >= 0, f"{p} 出现负数"
        if spec.max_answer is not None:
            assert p.answer <= spec.max_answer, f"{p} 超出上限 {spec.max_answer}"
        if p.op == "÷":
            assert p.a % p.b == 0, f"{p} 不能整除"
            assert p.a // p.b == p.answer


@pytest.mark.parametrize("code", list(GRADES.keys()))
def test_operators_within_spec(code):
    spec = GRADES[code]
    ps = generate_problems(spec, 120, rng=random.Random(11))
    assert {p.op for p in ps} <= set(spec.ops)


def test_multiplication_table_bounded():
    """二年级上乘法限定九九表内。"""
    spec = GRADES["g2a"]
    ps = [p for p in generate_problems(spec, 200, rng=random.Random(4)) if p.op == "×"]
    assert ps
    assert all(1 <= p.a <= 9 and 1 <= p.b <= 9 for p in ps)


def test_division_divisor_bounded():
    """二年级下除法限定表内除数。"""
    spec = GRADES["g2b"]
    ps = [p for p in generate_problems(spec, 200, rng=random.Random(6)) if p.op == "÷"]
    assert ps
    assert all(2 <= p.b <= 9 for p in ps)


# ------------------------------------------------------------ 进位筛选

@pytest.mark.parametrize("mode", [True, False])
def test_carry_filter_addition(mode):
    ps = [
        p for p in generate_problems(
            GRADES["g1b"], 80, rng=random.Random(8), carry=mode
        )
        if p.op == "+"
    ]
    assert ps
    assert all(has_carry(p.a, p.b) is mode for p in ps)


@pytest.mark.parametrize("mode", [True, False])
def test_carry_filter_subtraction(mode):
    ps = [
        p for p in generate_problems(
            GRADES["g1b"], 80, rng=random.Random(9), carry=mode
        )
        if p.op == "-"
    ]
    assert ps
    assert all(has_borrow(p.a, p.b) is mode for p in ps)


def test_carry_any_allows_both():
    ps = generate_problems(GRADES["g1b"], 100, rng=random.Random(10), carry=None)
    flags = {has_carry(p.a, p.b) if p.op == "+" else has_borrow(p.a, p.b) for p in ps}
    assert flags == {True, False}


# ------------------------------------------------------------ 边界与错误

def test_impossible_request_raises():
    """数量远超组合总数时应明确报错，而不是死循环。"""
    from core import GradeSpec
    tiny = GradeSpec("t", "微型", ("+",), (1, 2), (1, 2), max_answer=4)
    with pytest.raises(GenerationError):
        generate_problems(tiny, 500, rng=random.Random(1))


def test_allow_duplicates():
    from core import GradeSpec
    tiny = GradeSpec("t", "微型", ("+",), (1, 2), (1, 2), max_answer=4)
    ps = generate_problems(tiny, 30, rng=random.Random(1), allow_duplicates=True)
    assert len(ps) == 30
