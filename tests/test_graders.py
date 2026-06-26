import pytest

from model_regression_eval.graders import grade, parse_int_answer
from model_regression_eval.tasks import load_tasks
from model_regression_eval.tasks import EvalTask


def task(expected, grader, metadata=None):
    return EvalTask(id="t", domain="d", skill="s", prompt="p", expected=expected, grader=grader, metadata=metadata or {})


def test_parse_int_answer_chinese():
    assert parse_int_answer("二十一颗") == 21
    assert parse_int_answer("十") == 10
    assert parse_int_answer("四十二") == 42


def test_exact_int():
    r = grade(task(21, "exact_int"), "21")
    assert r.correct


def test_contains_all():
    r = grade(task(["歧义", "21", "29"], "contains_all"), "存在歧义：可按形状选择是21，完全盲抽是29")
    assert r.correct


def test_contains_all_partial_score_without_correctness():
    r = grade(task(["歧义", "21", "29"], "contains_all"), "存在歧义：可按形状选择是21")
    assert not r.correct
    assert r.score == pytest.approx(2 / 3)


def test_contains_ordered_requires_sequence():
    t = task(["88", "72"], "contains_ordered")
    assert grade(t, "最大值88，最小值72").correct
    wrong = grade(t, "最小值72，最大值88")
    assert not wrong.correct
    assert wrong.score == 0.5


def test_nand_expression_accepts_structured_latex_variants():
    t = task(
        r"\overline{\overline{ABC}\cdot\overline{\overline{A}\cdot\overline{B}\cdot\overline{C}}}",
        "nand_expression",
    )
    assert grade(t, r"\overline{\overline{ABC} \cdot \overline{\overline{A}\cdot\overline{B}\cdot\overline{C}}}").correct
    assert grade(t, r"$\overline{\overline{A*B*C} \cdot \overline{\bar{A}\cdot\bar{B}\cdot\bar{C}}}$").correct


def test_nand_expression_rejects_fragment_soup():
    t = task(
        r"\overline{\overline{ABC}\cdot\overline{\overline{A}\cdot\overline{B}\cdot\overline{C}}}",
        "nand_expression",
    )
    r = grade(t, "xxx overline{overline{ABC} yyy overline{overline{A} zzz overline{B} qqq overline{C}")
    assert not r.correct
    assert r.failure_mode == "wrong_expression"


def test_tool_violation():
    r = grade(task(21, "exact_int"), "21", tool_violation=True)
    assert not r.correct
    assert r.failure_mode == "tool_violation"


def test_numeric_extracts_first_number_from_answer_field():
    assert grade(task(3.14, "numeric"), "约等于3.14").correct
    assert grade(task(3.14, "numeric"), "3.14π").correct


def test_numeric_accepts_simple_fraction_answer_field():
    assert grade(task(10 / 3, "numeric", metadata={"tolerance": 0.0001}), "10/3").correct
    assert grade(task(10 / 7, "numeric", metadata={"tolerance": 0.0001}), r"\frac{10}{7}").correct
    assert grade(task(10 / 3, "numeric", metadata={"tolerance": 0.0001}), "约10/3小时").correct


def test_unordered_set_partial_score_without_correctness():
    r = grade(task(["红", "蓝", "绿"], "unordered_set"), "蓝, 红")
    assert not r.correct
    assert r.score == pytest.approx(2 / 3)


def test_unordered_set_partial_score_penalizes_extra_items():
    r = grade(task(["红", "蓝"], "unordered_set"), "蓝, 红, 绿")
    assert not r.correct
    assert r.score == pytest.approx(2 / 3)


def test_exact_string_accept_metadata():
    t = task("至多2个通过", "exact_string", metadata={"accept": ["最多2个通过", "至多两个通过", "最多两个通过"]})
    assert grade(t, "最多两个通过").correct
    assert not grade(t, "至少2个通过").correct


def test_contains_all_accept_parts_metadata():
    t = task(
        ["信息不足", "差值"],
        "contains_all",
        metadata={"accept_parts": [["不能得到唯一", "无法得到唯一"], ["身高差"]]},
    )
    assert grade(t, "不能得到唯一数值答案；缺少甲乙和乙丙的具体身高差").correct
    wrong = grade(t, "不能得到唯一数值答案")
    assert not wrong.correct
    assert wrong.score == pytest.approx(0.5)


def test_fraction_string_accepts_plain_and_latex_fraction():
    t = task("189213/468097", "fraction_string")
    assert grade(t, "189213/468097").correct
    assert grade(t, r"\frac{189213}{468097}").correct
    assert grade(t, r"\dfrac{189213}{468097}").correct
    assert grade(t, r"(\tfrac{189213}{468097})").correct


def test_fraction_string_rejects_non_simplest_by_default():
    t = task("1/2", "fraction_string")
    r = grade(t, "2/4")
    assert not r.correct
    assert r.failure_mode == "non_simplest_fraction"


def test_fraction_string_can_allow_decimal_with_metadata():
    t = task("1/2", "fraction_string", metadata={"allow_decimal": True})
    assert grade(t, "0.5").correct
    assert not grade(task("1/2", "fraction_string"), "0.5").correct


def test_range_interval_accepts_equivalent_open_interval_forms():
    t = task({"var": "k", "lower": "0", "upper": "2/9", "lower_closed": False, "upper_closed": False}, "range_interval")
    assert grade(t, "0 < k < 2/9").correct
    assert grade(t, "k in (0, 2/9)").correct
    assert grade(t, "(0, 2/9)").correct
    assert grade(t, "2/9 > k > 0").correct


def test_range_interval_rejects_wrong_or_closed_interval():
    t = task({"var": "k", "lower": "0", "upper": "2/9", "lower_closed": False, "upper_closed": False}, "range_interval")
    assert not grade(t, "0 <= k < 2/9").correct
    assert not grade(t, "0 < k < 1/3").correct


def test_choice_accept_metadata():
    t = task("B", "choice", metadata={"accept": ["C"]})
    assert grade(t, "C. 等价表述").correct
    assert not grade(t, "A").correct


def test_load_tasks_rejects_invalid_accept_metadata(tmp_path):
    path = tmp_path / "tasks.jsonl"
    path.write_text(
        '{"id":"t","domain":"d","skill":"s","prompt":"p","expected":"x","grader":"exact_string","metadata":{"accept":"x"}}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="metadata.accept"):
        load_tasks(path)


def test_load_tasks_rejects_invalid_capability_metadata(tmp_path):
    path = tmp_path / "tasks.jsonl"
    path.write_text(
        '{"id":"t","domain":"d","skill":"s","prompt":"p","expected":"x","grader":"exact_string","metadata":{"difficulty":"impossible"}}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="metadata.difficulty"):
        load_tasks(path)


def test_load_tasks_rejects_invalid_fraction_metadata(tmp_path):
    path = tmp_path / "tasks.jsonl"
    path.write_text(
        '{"id":"t","domain":"d","skill":"s","prompt":"p","expected":"1/2","grader":"fraction_string","metadata":{"allow_decimal":"yes"}}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="metadata.allow_decimal"):
        load_tasks(path)


def test_load_tasks_rejects_invalid_accept_parts_metadata(tmp_path):
    path = tmp_path / "tasks.jsonl"
    path.write_text(
        '{"id":"t","domain":"d","skill":"s","prompt":"p","expected":["x"],"grader":"contains_all","metadata":{"accept_parts":["x"]}}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="metadata.accept_parts"):
        load_tasks(path)
