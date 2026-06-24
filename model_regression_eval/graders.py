from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any

from .tasks import EvalTask


@dataclass(frozen=True)
class GradeResult:
    correct: bool
    score: float
    failure_mode: str = "none"
    detail: str = ""


_CN_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def normalize_text(value: Any) -> str:
    s = str(value).strip()
    replacements = {
        "，": ",",
        "。": "",
        "；": ";",
        "：": ":",
        "（": "(",
        "）": ")",
        "颗": "",
        "个": "",
        "条": "",
        " ": "",
        "\t": "",
        "\n": "",
    }
    for old, new in replacements.items():
        s = s.replace(old, new)
    return s.lower()


def chinese_int_to_int(s: str) -> int | None:
    s = normalize_text(s)
    if not s:
        return None
    if s in _CN_DIGITS:
        return _CN_DIGITS[s]
    if "十" not in s:
        return None
    # Supports 10-99, enough for most short exact-answer tasks here.
    parts = s.split("十")
    if len(parts) != 2:
        return None
    left, right = parts
    tens = 1 if left == "" else _CN_DIGITS.get(left)
    ones = 0 if right == "" else _CN_DIGITS.get(right)
    if tens is None or ones is None:
        return None
    return tens * 10 + ones


def parse_int_answer(value: Any) -> int | None:
    s = normalize_text(value)
    if re.fullmatch(r"[-+]?\d+", s):
        return int(s)
    # Avoid broad extraction from verbose text; this is an answer field, not a transcript.
    cn = chinese_int_to_int(s)
    if cn is not None:
        return cn
    return None


def grade_exact_int(task: EvalTask, answer: Any) -> GradeResult:
    pred = parse_int_answer(answer)
    expected = int(task.expected)
    if pred is None:
        return GradeResult(False, 0.0, "parse_error", f"Could not parse integer from answer={answer!r}")
    ok = pred == expected
    return GradeResult(ok, 1.0 if ok else 0.0, "none" if ok else "wrong_answer", f"pred={pred}, expected={expected}")


def grade_exact_string(task: EvalTask, answer: Any) -> GradeResult:
    pred = normalize_text(answer)
    accepted = [normalize_text(task.expected)]
    accepted.extend(normalize_text(item) for item in (task.metadata or {}).get("accept", []))
    ok = pred in accepted
    return GradeResult(ok, 1.0 if ok else 0.0, "none" if ok else "wrong_answer", f"pred={pred!r}, expected_any={accepted!r}")


def grade_choice(task: EvalTask, answer: Any) -> GradeResult:
    pred = normalize_text(answer)
    expected_values = [normalize_text(task.expected)]
    expected_values.extend(normalize_text(item) for item in (task.metadata or {}).get("accept", []))
    # Accept "A" or "A.xxx" for choice tasks, but not arbitrary prose containing A.
    pred = pred[:1] if pred else pred
    accepted = [item[:1] for item in expected_values if item]
    ok = pred in accepted
    return GradeResult(ok, 1.0 if ok else 0.0, "none" if ok else "wrong_answer", f"pred={pred!r}, expected_any={accepted!r}")


def grade_contains_all(task: EvalTask, answer: Any) -> GradeResult:
    pred = normalize_text(answer)
    expected_values = task.expected
    if not isinstance(expected_values, list):
        return GradeResult(False, 0.0, "grader_config_error", "contains_all expects a list")
    missing = [x for x in expected_values if normalize_text(x) not in pred]
    score = _matched_fraction(len(expected_values), len(missing))
    ok = not missing
    return GradeResult(ok, score, "none" if ok else "missing_expected_parts", f"missing={missing}")


def grade_contains_ordered(task: EvalTask, answer: Any) -> GradeResult:
    pred = normalize_text(answer)
    expected_values = task.expected
    if not isinstance(expected_values, list):
        return GradeResult(False, 0.0, "grader_config_error", "contains_ordered expects a list")
    cursor = 0
    missing = []
    matched = 0
    for raw_item in expected_values:
        item = normalize_text(raw_item)
        index = pred.find(item, cursor)
        if index < 0:
            missing.append(raw_item)
            continue
        matched += 1
        cursor = index + len(item)
    ok = not missing
    return GradeResult(
        ok,
        matched / len(expected_values) if expected_values else 0.0,
        "none" if ok else "missing_ordered_expected_parts",
        f"missing={missing}",
    )


def normalize_boolean_expression(value: Any) -> str:
    s = str(value).strip().lower()
    replacements = {
        "$": "",
        "\\": "",
        " ": "",
        "\t": "",
        "\n": "",
        "（": "(",
        "）": ")",
        "·": "",
        "⋅": "",
        "*": "",
        ".": "",
        "×": "",
        "cdot": "",
        "times": "",
        "left": "",
        "right": "",
        "bar": "overline",
    }
    for old, new in replacements.items():
        s = s.replace(old, new)
    return s


def grade_nand_expression(task: EvalTask, answer: Any) -> GradeResult:
    expected = task.expected
    if not isinstance(expected, str):
        return GradeResult(False, 0.0, "grader_config_error", "nand_expression expects expected to be a string")
    pred = normalize_boolean_expression(answer)
    accepted = [normalize_boolean_expression(expected)]
    accepted.extend(normalize_boolean_expression(item) for item in (task.metadata or {}).get("accept", []))
    ok = pred in accepted
    return GradeResult(ok, 1.0 if ok else 0.0, "none" if ok else "wrong_expression", f"pred={pred!r}, expected_any={accepted!r}")


def parse_numeric_answer(value: Any) -> float | None:
    s = normalize_text(value)
    try:
        return float(s)
    except Exception:
        pass
    # The final answer field should normally be normalized already, but accepting
    # a leading phrase such as "约等于3.14" makes numeric grading more forgiving
    # without turning arbitrary prose into a correct answer. Only the first
    # conventional decimal/scientific-notation number is extracted.
    match = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", s)
    if not match:
        return None
    try:
        return float(match.group(0))
    except Exception:
        return None


def grade_numeric(task: EvalTask, answer: Any) -> GradeResult:
    meta = task.metadata or {}
    tolerance = float(meta.get("tolerance", 0.0))
    pred = parse_numeric_answer(answer)
    try:
        expected = float(task.expected)
    except Exception as exc:
        return GradeResult(False, 0.0, "grader_config_error", str(exc))
    if pred is None:
        return GradeResult(False, 0.0, "parse_error", f"Could not parse numeric answer={answer!r}")
    ok = math.isclose(pred, expected, abs_tol=tolerance, rel_tol=0.0)
    return GradeResult(ok, 1.0 if ok else 0.0, "none" if ok else "wrong_answer", f"pred={pred}, expected={expected}, tolerance={tolerance}")


def grade_unordered_set(task: EvalTask, answer: Any) -> GradeResult:
    expected_values = task.expected
    if not isinstance(expected_values, list):
        return GradeResult(False, 0.0, "grader_config_error", "unordered_set expects expected to be a list")
    pred_items = [normalize_text(x) for x in re.split(r"[,;、]", str(answer)) if normalize_text(x)]
    expected_items = [normalize_text(x) for x in expected_values]
    ok = sorted(pred_items) == sorted(expected_items)
    pred_unique = set(pred_items)
    expected_unique = set(expected_items)
    matched = len(pred_unique & expected_unique)
    denominator = max(len(expected_unique), len(pred_unique))
    score = matched / denominator if denominator else 0.0
    return GradeResult(ok, 1.0 if ok else score, "none" if ok else "wrong_answer", f"pred={pred_items}, expected={expected_items}")


def _matched_fraction(total: int, missing: int) -> float:
    if total <= 0:
        return 0.0
    return max(0.0, min(1.0, (total - missing) / total))


GRADERS = {
    "exact_int": grade_exact_int,
    "exact_string": grade_exact_string,
    "choice": grade_choice,
    "contains_all": grade_contains_all,
    "contains_ordered": grade_contains_ordered,
    "nand_expression": grade_nand_expression,
    "numeric": grade_numeric,
    "unordered_set": grade_unordered_set,
}


def grade(task: EvalTask, answer: Any, *, tool_violation: bool = False, format_error: bool = False) -> GradeResult:
    if format_error:
        return GradeResult(False, 0.0, "format_error", "Final output did not match required JSON shape")
    if tool_violation and not task.allow_tools:
        return GradeResult(False, 0.0, "tool_violation", "Task disallows tool use, but tool use was detected")
    fn = GRADERS.get(task.grader)
    if fn is None:
        return GradeResult(False, 0.0, "grader_config_error", f"Unknown grader: {task.grader}")
    return fn(task, answer)
