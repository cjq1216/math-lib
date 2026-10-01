"""题目答案多空等价匹配引擎。

支持功能：
1. 题解与 LaTeX 文本正规化（去除外层 $, \\left/\\right, \\frac 格式转换, 空白折叠）；
2. 精确匹配（exact）；
3. 允许候选答案集合匹配（allow_set）；
4. 无序集合匹配（unordered_set，如多个解 x=1, x=2）；
5. 数值误差匹配（numeric，支持绝对误差 tolerance）；
6. 分数与小数等价匹配（fraction，如 1/2 == \\frac{1}{2} == 0.5 == 2/4）；
7. 正则表达式匹配（regex）；
8. 智能回退匹配（未显式声明规则时自动检测数值与分数等价）。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Any


@dataclass(frozen=True)
class MatchResult:
    """匹配结果"""

    is_correct: bool
    score_ratio: float
    rule_applied: str
    normalized_student_answer: str
    reason: str = ""


_RE_OUTER_MATH = re.compile(r"^\${1,2}(.*)\${1,2}$", re.DOTALL)
_RE_FRAC = re.compile(r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}")
_RE_LEFT_RIGHT = re.compile(r"\\(left|right)\b\s*")


def normalize_math_text(text: str | None) -> str:
    """正规化数学答案文本。"""
    if not text:
        return ""

    s = text.strip()

    # 去除外层 LaTeX 行内或块级美元符号
    if s.startswith("$$") and s.endswith("$$") and len(s) >= 4:
        s = s[2:-2].strip()
    elif s.startswith("$") and s.endswith("$") and len(s) >= 2:
        s = s[1:-1].strip()
    # 替换中文标点为英文标点
    s = s.replace("，", ",").replace("；", ";").replace("（", "(").replace("）", ")")

    # 去除 \left 和 \right 修饰符
    s = _RE_LEFT_RIGHT.sub("", s)

    # 替换 LaTeX 常见符号
    s = s.replace(r"\times", "*").replace(r"\div", "/").replace(r"\cdot", "*")

    # 替换 \frac{a}{b} -> (a)/(b)
    # 循环替换以支持简单嵌套
    for _ in range(3):
        if r"\frac" in s:
            s = _RE_FRAC.sub(r"(\1)/(\2)", s)
        else:
            break

    # 统一空白字符：折叠多余空白
    s = re.sub(r"\s+", " ", s).strip()

    # 去除运算符与括号两端的冗余空格，保留紧凑形态
    s = re.sub(r"\s*([=+\-*/,;()\[\]])\s*", r"\1", s)
    return s


def parse_to_fraction_or_float(text: str) -> Fraction | float | None:
    """尝试将文本解析为 Fraction 或浮点数。"""
    norm = normalize_math_text(text)
    if not norm:
        return None

    # 如果有外层括号，剥离
    while norm.startswith("(") and norm.endswith(")") and norm.count("(") == 1:
        norm = norm[1:-1].strip()

    # 尝试直接解析为 Fraction (支持 "1/2", "-3/4", "5")
    try:
        if "/" in norm:
            # 去除分子分母两侧括号
            parts = norm.split("/")
            if len(parts) == 2:
                num_s = parts[0].replace("(", "").replace(")", "").strip()
                den_s = parts[1].replace("(", "").replace(")", "").strip()
                # 检查是否为有效浮点或整数
                num = float(num_s)
                den = float(den_s)
                if den != 0:
                    return Fraction(num / den).limit_denominator(100000)
            return None
        return Fraction(float(norm)).limit_denominator(100000)
    except (ValueError, ZeroDivisionError, OverflowError):
        pass

    try:
        return float(norm)
    except ValueError:
        return None


def match_answer(
    student_answer: str | None,
    expected_answer: str | None,
    match_rule: dict[str, Any] | None = None,
) -> MatchResult:
    """评估学生作答与标准答案是否等价。

    :param student_answer: 学生提交的答案
    :param expected_answer: 标准主答案
    :param match_rule: 规则配置字典，可选字段：
        - rule_type: 'exact' | 'allow_set' | 'numeric' | 'fraction' | 'regex' | 'unordered_set'
        - allow_set: list[str]，备选允许的答案列表
        - tolerance: float，数值绝对容差（numeric 规则下生效）
        - pattern: str，正则表达式（regex 规则下生效）
        - case_sensitive: bool，是否大小写敏感（默认 False）
        - delimiter: str，无序集合的分隔符（默认 ','）
    """
    if student_answer is None:
        student_answer = ""
    if expected_answer is None:
        expected_answer = ""

    norm_student = normalize_math_text(student_answer)
    norm_expected = normalize_math_text(expected_answer)
    rule = match_rule or {}
    rule_type = str(rule.get("rule_type") or "").strip().lower()
    case_sensitive = bool(rule.get("case_sensitive", False))

    if not norm_student:
        return MatchResult(
            is_correct=False,
            score_ratio=0.0,
            rule_applied=rule_type or "none",
            normalized_student_answer=norm_student,
            reason="学生答案为空",
        )

    # 1. 正则匹配规则
    if rule_type == "regex":
        pattern = rule.get("pattern") or rule.get("regex") or ""
        if not pattern:
            return MatchResult(
                is_correct=False,
                score_ratio=0.0,
                rule_applied="regex",
                normalized_student_answer=norm_student,
                reason="未配置正则表达式",
            )
        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            matched = bool(re.search(pattern, student_answer.strip(), flags=flags))
            return MatchResult(
                is_correct=matched,
                score_ratio=1.0 if matched else 0.0,
                rule_applied="regex",
                normalized_student_answer=norm_student,
                reason="正则匹配成功" if matched else "不符合正则模式",
            )
        except re.error as e:
            return MatchResult(
                is_correct=False,
                score_ratio=0.0,
                rule_applied="regex",
                normalized_student_answer=norm_student,
                reason=f"正则表达式错误: {e}",
            )

    # 2. 备选答案集合匹配 (allow_set)
    if rule_type == "allow_set":
        allow_set = rule.get("allow_set") or []
        candidates = [norm_expected] + [normalize_math_text(str(x)) for x in allow_set]
        s_target = norm_student if case_sensitive else norm_student.lower()
        for cand in candidates:
            c_target = cand if case_sensitive else cand.lower()
            if s_target == c_target:
                return MatchResult(
                    is_correct=True,
                    score_ratio=1.0,
                    rule_applied="allow_set",
                    normalized_student_answer=norm_student,
                    reason=f"命中候选集合答案: {cand}",
                )
            # 尝试数值/分数等价
            sf = parse_to_fraction_or_float(s_target)
            cf = parse_to_fraction_or_float(c_target)
            if sf is not None and cf is not None and math.isclose(float(sf), float(cf), rel_tol=1e-7, abs_tol=1e-7):
                return MatchResult(
                    is_correct=True,
                    score_ratio=1.0,
                    rule_applied="allow_set",
                    normalized_student_answer=norm_student,
                    reason=f"数值等价命中候选集合答案: {cand}",
                )

        return MatchResult(
            is_correct=False,
            score_ratio=0.0,
            rule_applied="allow_set",
            normalized_student_answer=norm_student,
            reason="未命中候选答案集合",
        )

    # 3. 无序集合匹配 (unordered_set，如解集或多个数值)
    if rule_type == "unordered_set":
        delimiter = rule.get("delimiter") or ","
        s_tokens = {normalize_math_text(t) for t in norm_student.split(delimiter) if t.strip()}
        e_tokens = {normalize_math_text(t) for t in norm_expected.split(delimiter) if t.strip()}
        if not case_sensitive:
            s_tokens = {t.lower() for t in s_tokens}
            e_tokens = {t.lower() for t in e_tokens}
        if s_tokens == e_tokens:
            return MatchResult(
                is_correct=True,
                score_ratio=1.0,
                rule_applied="unordered_set",
                normalized_student_answer=norm_student,
                reason="集合元素完全匹配",
            )
        return MatchResult(
            is_correct=False,
            score_ratio=0.0,
            rule_applied="unordered_set",
            normalized_student_answer=norm_student,
            reason="集合元素不匹配",
        )

    # 4. 数值误差匹配 (numeric)
    if rule_type == "numeric":
        tolerance = float(rule.get("tolerance", rule.get("precision", 1e-4)))
        sf = parse_to_fraction_or_float(norm_student)
        ef = parse_to_fraction_or_float(norm_expected)
        if sf is not None and ef is not None:
            diff = abs(float(sf) - float(ef))
            matched = diff <= tolerance
            return MatchResult(
                is_correct=matched,
                score_ratio=1.0 if matched else 0.0,
                rule_applied="numeric",
                normalized_student_answer=norm_student,
                reason=f"数值误差 {diff:.6f} <= 容差 {tolerance}" if matched else f"数值误差 {diff:.6f} 超出容差 {tolerance}",
            )
        return MatchResult(
            is_correct=False,
            score_ratio=0.0,
            rule_applied="numeric",
            normalized_student_answer=norm_student,
            reason="无法解析为有效数值进行比较",
        )

    # 5. 分数/小数等价匹配 (fraction)
    if rule_type == "fraction":
        sf = parse_to_fraction_or_float(norm_student)
        ef = parse_to_fraction_or_float(norm_expected)
        if sf is not None and ef is not None:
            matched = math.isclose(float(sf), float(ef), rel_tol=1e-7, abs_tol=1e-7)
            return MatchResult(
                is_correct=matched,
                score_ratio=1.0 if matched else 0.0,
                rule_applied="fraction",
                normalized_student_answer=norm_student,
                reason="分数/小数数值等价" if matched else "分数/小数值不等",
            )
        return MatchResult(
            is_correct=False,
            score_ratio=0.0,
            rule_applied="fraction",
            normalized_student_answer=norm_student,
            reason="无法解析为有效分数或小数",
        )

    # 6. 精确匹配 (exact) 或默认自动判断
    s_target = norm_student if case_sensitive else norm_student.lower()
    e_target = norm_expected if case_sensitive else norm_expected.lower()

    if s_target == e_target:
        return MatchResult(
            is_correct=True,
            score_ratio=1.0,
            rule_applied="exact",
            normalized_student_answer=norm_student,
            reason="文本正规化后完全一致",
        )

    # 自动等价智能回退：若未指定规则，但两边均为合法数值/分数，尝试判断是否等价
    if not rule_type or rule_type == "exact":
        sf = parse_to_fraction_or_float(norm_student)
        ef = parse_to_fraction_or_float(norm_expected)
        if sf is not None and ef is not None and math.isclose(float(sf), float(ef), rel_tol=1e-7, abs_tol=1e-7):
            return MatchResult(
                is_correct=True,
                score_ratio=1.0,
                rule_applied="auto_equivalence",
                normalized_student_answer=norm_student,
                reason="自动识别为数值/分数等价",
            )

    return MatchResult(
        is_correct=False,
        score_ratio=0.0,
        rule_applied=rule_type or "exact",
        normalized_student_answer=norm_student,
        reason="答案不一致",
    )
