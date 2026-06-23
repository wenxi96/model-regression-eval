from model_regression_eval.graders import grade, parse_int_answer
from model_regression_eval.tasks import EvalTask


def task(expected, grader):
    return EvalTask(id="t", domain="d", skill="s", prompt="p", expected=expected, grader=grader)


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


def test_tool_violation():
    r = grade(task(21, "exact_int"), "21", tool_violation=True)
    assert not r.correct
    assert r.failure_mode == "tool_violation"


def test_numeric_extracts_first_number_from_answer_field():
    assert grade(task(3.14, "numeric"), "约等于3.14").correct
    assert grade(task(3.14, "numeric"), "3.14π").correct
