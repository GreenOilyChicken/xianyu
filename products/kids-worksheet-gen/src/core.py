"""口算题生成核心：纯逻辑，不依赖 reportlab，便于单测与复用。

设计原则（对应产品"边界客观"的定位）：
  题目的对错由数学定义，题型范围由课标定义 —— 没有主观配置空间。
  本模块只负责"生成合法题目"，排版渲染在 pdf_render.py。
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from functools import lru_cache


# ----------------------------------------------------------------- 数据结构

@dataclass(frozen=True)
class Problem:
    """一道口算题：a op b = ?"""

    a: int
    b: int
    op: str

    @property
    def answer(self) -> int:
        if self.op == "+":
            return self.a + self.b
        if self.op == "-":
            return self.a - self.b
        if self.op == "×":
            return self.a * self.b
        if self.op == "÷":
            return self.a // self.b
        raise ValueError(f"未知运算符: {self.op!r}")

    def text(self, blank: str = "") -> str:
        """题面。blank 传下划线可打印作答线。"""
        return f"{self.a} {self.op} {self.b} = {blank}".rstrip()

    def key(self) -> tuple[int, int, str]:
        """去重键。"""
        return (self.a, self.b, self.op)

    def __str__(self) -> str:  # pragma: no cover - 便于调试
        return self.text()


@dataclass(frozen=True)
class GradeSpec:
    """一个年级/题型的出题规格。所有范围都是闭区间。

    加减用 a_range / b_range；
    乘法用 mul_a_range / mul_b_range（缺省回落到 a_range / b_range）；
    除法用 div_b_range（除数）/ div_q_range（商），被除数由两者相乘得出，
    因此**必然整除**，不需要事后修正。
    """

    key: str
    label: str
    ops: tuple[str, ...]
    a_range: tuple[int, int]
    b_range: tuple[int, int]
    max_answer: int | None = None
    mul_a_range: tuple[int, int] | None = None
    mul_b_range: tuple[int, int] | None = None
    div_b_range: tuple[int, int] | None = None
    div_q_range: tuple[int, int] | None = None
    note: str = ""


# ----------------------------------------------------------------- 课标题库
# 范围依据人教版小学数学教材，取整数运算部分（小数/分数见方案 v1.1）

GRADES: dict[str, GradeSpec] = {
    "g1a": GradeSpec(
        "g1a", "一年级上 · 20以内加减法", ("+", "-"),
        (1, 19), (1, 19), max_answer=20, note="结果不超过20，不含负数",
    ),
    "g1b": GradeSpec(
        "g1b", "一年级下 · 100以内加减法", ("+", "-"),
        (1, 99), (1, 99), max_answer=100, note="结果不超过100",
    ),
    "g2a": GradeSpec(
        "g2a", "二年级上 · 100以内加减 + 表内乘法", ("+", "-", "×"),
        (1, 99), (1, 99), max_answer=100,
        mul_a_range=(1, 9), mul_b_range=(1, 9),
        note="乘法限定九九表内",
    ),
    "g2b": GradeSpec(
        "g2b", "二年级下 · 100以内加减 + 表内除法", ("+", "-", "÷"),
        (1, 99), (1, 99), max_answer=100,
        div_b_range=(2, 9), div_q_range=(1, 9),
        note="除法限定表内，整除",
    ),
    "g3a": GradeSpec(
        "g3a", "三年级上 · 多位数乘一位数 + 万以内加减", ("+", "-", "×"),
        (10, 999), (10, 999), max_answer=10000,
        mul_a_range=(12, 99), mul_b_range=(2, 9),
        note="乘法为两位数乘一位数",
    ),
    "g3b": GradeSpec(
        "g3b", "三年级下 · 两位数乘两位数 + 除数是一位数", ("×", "÷"),
        (10, 99), (10, 99), max_answer=10000,
        mul_a_range=(11, 99), mul_b_range=(11, 99),
        div_b_range=(2, 9), div_q_range=(10, 99),
        note="除法整除，商为两位数",
    ),
    "g4a": GradeSpec(
        "g4a", "四年级上 · 三位数乘两位数 + 除数是两位数", ("×", "÷"),
        (100, 999), (10, 99), max_answer=100000,
        mul_a_range=(100, 999), mul_b_range=(10, 99),
        div_b_range=(10, 99), div_q_range=(2, 99),
        note="除法整除",
    ),
}


class GenerationError(RuntimeError):
    """无法在限定尝试次数内生成足够的不重复题目。"""


# ----------------------------------------------------------------- 进位判断

def has_carry(a: int, b: int) -> bool:
    """a + b 是否产生进位（逐位模拟，含进位传播）。"""
    carry = 0
    while a or b:
        s = (a % 10) + (b % 10) + carry
        if s >= 10:
            return True
        carry = 0
        a //= 10
        b //= 10
    return False


def has_borrow(a: int, b: int) -> bool:
    """a - b（a >= b）是否产生借位。"""
    borrow = 0
    while b or borrow:
        if (a % 10) - borrow < (b % 10):
            return True
        borrow = 0
        a //= 10
        b //= 10
    return False


# ----------------------------------------------------------------- 出题逻辑

def _make_one(
    spec: GradeSpec, rng: random.Random, carry: bool | None
) -> Problem | None:
    """随机造一道题，不满足约束返回 None。"""
    op = rng.choice(spec.ops)

    if op == "+":
        a = rng.randint(*spec.a_range)
        b = rng.randint(*spec.b_range)
        if spec.max_answer is not None and a + b > spec.max_answer:
            return None
        if carry is not None and has_carry(a, b) != carry:
            return None
        return Problem(a, b, "+")

    if op == "-":
        a = rng.randint(*spec.a_range)
        b = rng.randint(*spec.b_range)
        if a < b:
            a, b = b, a
        if a == b:  # 结果为 0 太简单，跳过
            return None
        if spec.max_answer is not None and a > spec.max_answer:
            return None
        if carry is not None and has_borrow(a, b) != carry:
            return None
        return Problem(a, b, "-")

    if op == "×":
        ar = spec.mul_a_range or spec.a_range
        br = spec.mul_b_range or spec.b_range
        a = rng.randint(*ar)
        b = rng.randint(*br)
        if spec.max_answer is not None and a * b > spec.max_answer:
            return None
        return Problem(a, b, "×")

    if op == "÷":
        br = spec.div_b_range or spec.b_range
        qr = spec.div_q_range or (1, 9)
        b = rng.randint(*br)
        q = rng.randint(*qr)
        a = b * q  # 先定除数和商，被除数反推 → 必然整除
        if spec.max_answer is not None and a > spec.max_answer:
            return None
        return Problem(a, b, "÷")

    raise ValueError(f"未知运算符: {op!r}")


@lru_cache(maxsize=None)
def unique_capacity(spec: GradeSpec, carry: bool | None = None) -> int:
    """该题型在约束下**最多能出多少道互不相同的题**。

    用于批量出卷前预检：如果要求的总题数超过容量，直接明确报错，
    而不是靠随机采样硬撞（那会退化成接近死循环）。
    结果按 (spec, carry) 缓存，重复调用不重算。
    """
    keys: set[tuple[int, int, str]] = set()

    for op in spec.ops:
        if op == "+":
            for a in range(spec.a_range[0], spec.a_range[1] + 1):
                for b in range(spec.b_range[0], spec.b_range[1] + 1):
                    if spec.max_answer is not None and a + b > spec.max_answer:
                        continue
                    if carry is not None and has_carry(a, b) != carry:
                        continue
                    keys.add((a, b, "+"))

        elif op == "-":
            for a in range(spec.a_range[0], spec.a_range[1] + 1):
                for b in range(spec.b_range[0], spec.b_range[1] + 1):
                    if a <= b:  # 结果为 0 或负数，_make_one 不会产出
                        continue
                    if spec.max_answer is not None and a > spec.max_answer:
                        continue
                    if carry is not None and has_borrow(a, b) != carry:
                        continue
                    keys.add((a, b, "-"))

        elif op == "×":
            ar = spec.mul_a_range or spec.a_range
            br = spec.mul_b_range or spec.b_range
            for a in range(ar[0], ar[1] + 1):
                for b in range(br[0], br[1] + 1):
                    if spec.max_answer is not None and a * b > spec.max_answer:
                        continue
                    keys.add((a, b, "×"))

        elif op == "÷":
            br = spec.div_b_range or spec.b_range
            qr = spec.div_q_range or (1, 9)
            for b in range(br[0], br[1] + 1):
                for q in range(qr[0], qr[1] + 1):
                    a = b * q
                    if spec.max_answer is not None and a > spec.max_answer:
                        continue
                    keys.add((a, b, "÷"))

    return len(keys)


def generate_problems(
    spec: GradeSpec,
    count: int,
    *,
    rng: random.Random | None = None,
    carry: bool | None = None,
    allow_duplicates: bool = False,
    exclude: set[tuple[int, int, str]] | None = None,
) -> list[Problem]:
    """生成 count 道题。

    carry: None=不限；True=只出进位/借位题；False=只出不进位/不借位题。
    默认同一页内不出现重复题目。
    exclude: 额外要避开的题目键集合（批量出卷时用于**跨文件去重**）。
             不传则不影响原行为；本函数**不会修改**传入的集合。
    """
    if count < 0:
        raise ValueError("题目数量不能为负")
    if count == 0:
        return []

    rng = rng or random.Random()
    problems: list[Problem] = []
    seen: set[tuple[int, int, str]] = set(exclude) if exclude else set()

    if not allow_duplicates:
        # 预检容量，避免在接近满容量时退化成近乎死循环的随机采样
        cap = unique_capacity(spec, carry)
        if len(seen) + count > cap:
            raise GenerationError(
                f"题量超出上限：{spec.label} 在"
                f"{'（含进位筛选）' if carry is not None else ''}"
                f"最多只能出 {cap} 道不重复的题，"
                f"当前已用 {len(seen)} 道，还需要 {count} 道。\n"
                f"请减少题量或换题型。"
            )

    max_attempts = max(2000, count * 400)
    attempts = 0
    while len(problems) < count and attempts < max_attempts:
        attempts += 1
        p = _make_one(spec, rng, carry)
        if p is None:
            continue
        if not allow_duplicates and p.key() in seen:
            continue
        seen.add(p.key())
        problems.append(p)

    if len(problems) < count:
        raise GenerationError(
            f"只生成了 {len(problems)}/{count} 道不重复题目（尝试 {attempts} 次）。"
            f"请减少题目数量或放宽范围：{spec.label}"
        )
    return problems


def generate_batch(
    spec: GradeSpec,
    sheets: int,
    per_sheet: int,
    *,
    rng: random.Random | None = None,
    carry: bool | None = None,
    exclude: set[tuple[int, int, str]] | None = None,
) -> list[list[Problem]]:
    """批量出卷：生成 sheets 份，每份 per_sheet 道，**跨份全局不重复**。

    这是"内容包"产品线的生产函数：一次生成一学期的练习，题与题之间不重样。
    """
    if sheets < 0:
        raise ValueError("份数不能为负")
    if per_sheet < 0:
        raise ValueError("每份题数不能为负")

    rng = rng or random.Random()
    seen: set[tuple[int, int, str]] = set(exclude) if exclude else set()

    total = sheets * per_sheet
    cap = unique_capacity(spec, carry)
    if len(seen) + total > cap:
        raise GenerationError(
            f"题量超出上限：{spec.label} 最多只能出 {cap} 道不重复的题，"
            f"当前请求 {sheets} 份 × {per_sheet} 题 = {total} 道"
            f"（已有 {len(seen)} 道）。\n"
            f"请减少份数或每份题数。"
        )

    result: list[list[Problem]] = []
    for _ in range(sheets):
        problems = generate_problems(
            spec, per_sheet, rng=rng, carry=carry, exclude=seen
        )
        seen.update(p.key() for p in problems)
        result.append(problems)
    return result
