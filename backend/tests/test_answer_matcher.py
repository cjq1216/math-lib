"""答案多空等价匹配引擎测试用例。"""


from app.services.answer_matcher import (
    match_answer,
    normalize_math_text,
    parse_to_fraction_or_float,
)


def test_normalize_math_text():
    assert normalize_math_text("$x = 2$") == "x=2"
    assert normalize_math_text("$$ 1 / 2 $$") == "1/2"
    assert normalize_math_text(r"\frac{1}{2}") == "(1)/(2)"
    assert normalize_math_text(r"-\frac{3}{4}") == "-(3)/(4)"
    assert normalize_math_text(r"\left( x + 1 \right)") == "(x+1)"
    assert normalize_math_text("A ， B ； C") == "A,B;C"
    assert normalize_math_text("  x   +   y  =  5 ") == "x+y=5"


def test_parse_to_fraction_or_float():
    assert parse_to_fraction_or_float("0.5") == 0.5
    assert parse_to_fraction_or_float("1/2") == 0.5
    assert parse_to_fraction_or_float(r"\frac{3}{6}") == 0.5
    assert parse_to_fraction_or_float("-3/4") == -0.75
    assert parse_to_fraction_or_float("invalid") is None
    assert parse_to_fraction_or_float("1/0") is None


def test_exact_match():
    # 格式与空格容错
    res1 = match_answer("$x=2$", "x = 2")
    assert res1.is_correct is True
    assert res1.rule_applied in ("exact", "auto_equivalence")

    # 大小写
    res2 = match_answer("x=A", "x=a", match_rule={"case_sensitive": False})
    assert res2.is_correct is True

    res3 = match_answer("x=A", "x=a", match_rule={"case_sensitive": True})
    assert res3.is_correct is False


def test_allow_set_match():
    rule = {
        "rule_type": "allow_set",
        "allow_set": ["0.5", r"\frac{1}{2}", "50%"],
    }
    # 匹配主答案
    assert match_answer("1/2", "1/2", rule).is_correct is True
    # 匹配备选答案
    assert match_answer("0.5", "1/2", rule).is_correct is True
    assert match_answer(r"$\frac{1}{2}$", "1/2", rule).is_correct is True
    # 不在集合内
    assert match_answer("0.6", "1/2", rule).is_correct is False


def test_unordered_set_match():
    rule = {"rule_type": "unordered_set"}
    # 根的顺序无关
    res1 = match_answer("x=1, x=2", "x=2, x=1", rule)
    assert res1.is_correct is True

    res2 = match_answer("2, 3", "3, 2", rule)
    assert res2.is_correct is True

    res3 = match_answer("2, 3, 4", "2, 3", rule)
    assert res3.is_correct is False


def test_numeric_tolerance():
    rule = {"rule_type": "numeric", "tolerance": 0.01}
    assert match_answer("3.1415", "3.14", rule).is_correct is True
    assert match_answer("3.149", "3.14", rule).is_correct is True
    assert match_answer("3.16", "3.14", rule).is_correct is False

    # 无法解析为数值
    assert match_answer("abc", "3.14", rule).is_correct is False


def test_fraction_equivalence():
    rule = {"rule_type": "fraction"}
    assert match_answer("0.5", "1/2", rule).is_correct is True
    assert match_answer(r"\frac{2}{4}", "1/2", rule).is_correct is True
    assert match_answer(r"-\frac{3}{6}", "-0.5", rule).is_correct is True
    assert match_answer("0.75", r"\frac{3}{4}", rule).is_correct is True
    assert match_answer("0.76", r"\frac{3}{4}", rule).is_correct is False


def test_regex_match():
    rule = {"rule_type": "regex", "pattern": r"^[xX]\s*=\s*[+-]?\d+$"}
    assert match_answer("x = 5", "x=5", rule).is_correct is True
    assert match_answer("X = -12", "x=5", rule).is_correct is True
    assert match_answer("y = 5", "x=5", rule).is_correct is False

    # 错误正则
    bad_rule = {"rule_type": "regex", "pattern": r"([a-"}
    bad_res = match_answer("x=1", "x=1", bad_rule)
    assert bad_res.is_correct is False
    assert "正则表达式错误" in bad_res.reason


def test_empty_and_auto_equivalence():
    # 空答案
    assert match_answer("", "123").is_correct is False
    assert match_answer(None, "123").is_correct is False

    # 无规则时自动识别数值/分数等同
    auto_res = match_answer(r"$\frac{1}{4}$", "0.25")
    assert auto_res.is_correct is True
    assert auto_res.rule_applied == "auto_equivalence"
