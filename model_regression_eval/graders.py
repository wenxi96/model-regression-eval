from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
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


def compact_math_text(value: Any, *, strip_outer: bool = True) -> str:
    s = str(value).strip().lower()
    replacements = {
        "$": "",
        " ": "",
        "\t": "",
        "\n": "",
        "，": ",",
        "（": "(",
        "）": ")",
        "−": "-",
        "\\left": "",
        "\\right": "",
    }
    for old, new in replacements.items():
        s = s.replace(old, new)
    return _strip_outer_parens(s) if strip_outer else s


def _strip_outer_parens(s: str) -> str:
    while s.startswith("(") and s.endswith(")"):
        depth = 0
        encloses_all = True
        for index, char in enumerate(s):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0 and index != len(s) - 1:
                    encloses_all = False
                    break
        if not encloses_all or depth != 0:
            break
        s = s[1:-1]
    return s


def _parse_fraction_literal(value: Any, *, allow_decimal: bool = False) -> tuple[Fraction, bool, str] | None:
    s = compact_math_text(value)
    latex = re.fullmatch(r"\\(?:frac|dfrac|tfrac)\{([-+]?\d+)\}\{([-+]?\d+)\}", s)
    if latex:
        numerator = int(latex.group(1))
        denominator = int(latex.group(2))
        return _fraction_with_simplest_flag(numerator, denominator, "fraction")
    plain = re.fullmatch(r"([-+]?\d+)/([-+]?\d+)", s)
    if plain:
        numerator = int(plain.group(1))
        denominator = int(plain.group(2))
        return _fraction_with_simplest_flag(numerator, denominator, "fraction")
    if re.fullmatch(r"[-+]?\d+", s):
        return Fraction(int(s), 1), True, "integer"
    if allow_decimal and re.fullmatch(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", s):
        return Fraction(s), True, "decimal"
    return None


def _fraction_with_simplest_flag(numerator: int, denominator: int, kind: str) -> tuple[Fraction, bool, str] | None:
    if denominator == 0:
        return None
    value = Fraction(numerator, denominator)
    normalized_numerator = numerator
    normalized_denominator = denominator
    if normalized_denominator < 0:
        normalized_numerator *= -1
        normalized_denominator *= -1
    simplest = value.numerator == normalized_numerator and value.denominator == normalized_denominator
    return value, simplest, kind


def grade_fraction_string(task: EvalTask, answer: Any) -> GradeResult:
    meta = task.metadata or {}
    allow_decimal = bool(meta.get("allow_decimal", False))
    require_simplest = bool(meta.get("require_simplest", True))
    expected = _parse_fraction_literal(task.expected, allow_decimal=False)
    if expected is None:
        return GradeResult(False, 0.0, "grader_config_error", "fraction_string expects a fraction-like expected value")
    pred = _parse_fraction_literal(answer, allow_decimal=allow_decimal)
    if pred is None:
        return GradeResult(False, 0.0, "parse_error", f"Could not parse fraction answer={answer!r}")
    pred_value, pred_simplest, pred_kind = pred
    expected_value = expected[0]
    if require_simplest and pred_kind == "fraction" and not pred_simplest:
        return GradeResult(False, 0.0, "non_simplest_fraction", f"pred={pred_value}, expected={expected_value}")
    ok = pred_value == expected_value
    return GradeResult(ok, 1.0 if ok else 0.0, "none" if ok else "wrong_answer", f"pred={pred_value}, expected={expected_value}")


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


def _parse_rational_endpoint(value: Any) -> Fraction | None:
    parsed = _parse_fraction_literal(value, allow_decimal=False)
    return parsed[0] if parsed else None


def _expected_interval(task: EvalTask) -> tuple[str | None, Fraction, Fraction, bool, bool] | None:
    expected = task.expected
    if not isinstance(expected, dict):
        return None
    try:
        lower = _parse_rational_endpoint(expected["lower"])
        upper = _parse_rational_endpoint(expected["upper"])
    except KeyError:
        return None
    if lower is None or upper is None:
        return None
    return (
        str(expected.get("var")) if expected.get("var") is not None else None,
        lower,
        upper,
        bool(expected.get("lower_closed", False)),
        bool(expected.get("upper_closed", False)),
    )


def _parse_interval_answer(value: Any, expected_var: str | None) -> tuple[str | None, Fraction, Fraction, bool, bool] | None:
    s = compact_math_text(value, strip_outer=False).replace("∈", "in")
    s = s.replace("属于", "in")
    interval = re.fullmatch(r"(?:(?P<var>[a-z_][a-z0-9_]*)in)?(?P<left>[\(\[])(?P<lower>[^,]+),(?P<upper>[^\]\)]+)(?P<right>[\)\]])", s)
    if interval:
        lower = _parse_rational_endpoint(interval.group("lower"))
        upper = _parse_rational_endpoint(interval.group("upper"))
        if lower is None or upper is None:
            return None
        return (
            interval.group("var"),
            lower,
            upper,
            interval.group("left") == "[",
            interval.group("right") == "]",
        )
    var = re.escape(expected_var) if expected_var else r"[a-z_][a-z0-9_]*"
    increasing = re.fullmatch(rf"(?P<lower>.+?)(?P<lop><=|<)(?P<var>{var})(?P<uop><=|<)(?P<upper>.+)", s)
    if increasing:
        lower = _parse_rational_endpoint(increasing.group("lower"))
        upper = _parse_rational_endpoint(increasing.group("upper"))
        if lower is None or upper is None:
            return None
        return (
            increasing.group("var"),
            lower,
            upper,
            increasing.group("lop") == "<=",
            increasing.group("uop") == "<=",
        )
    decreasing = re.fullmatch(rf"(?P<upper>.+?)(?P<uop>>=|>)(?P<var>{var})(?P<lop>>=|>)(?P<lower>.+)", s)
    if decreasing:
        lower = _parse_rational_endpoint(decreasing.group("lower"))
        upper = _parse_rational_endpoint(decreasing.group("upper"))
        if lower is None or upper is None:
            return None
        return (
            decreasing.group("var"),
            lower,
            upper,
            decreasing.group("lop") == ">=",
            decreasing.group("uop") == ">=",
        )
    return None


def grade_range_interval(task: EvalTask, answer: Any) -> GradeResult:
    expected = _expected_interval(task)
    if expected is None:
        return GradeResult(False, 0.0, "grader_config_error", "range_interval expects object expected with lower/upper endpoints")
    expected_var, expected_lower, expected_upper, expected_lower_closed, expected_upper_closed = expected
    pred = _parse_interval_answer(answer, expected_var)
    if pred is None:
        return GradeResult(False, 0.0, "parse_error", f"Could not parse interval answer={answer!r}")
    pred_var, pred_lower, pred_upper, pred_lower_closed, pred_upper_closed = pred
    if expected_var and pred_var and pred_var != expected_var:
        return GradeResult(False, 0.0, "wrong_interval", f"pred_var={pred_var!r}, expected_var={expected_var!r}")
    ok = (
        pred_lower == expected_lower
        and pred_upper == expected_upper
        and pred_lower_closed == expected_lower_closed
        and pred_upper_closed == expected_upper_closed
    )
    detail = (
        f"pred=({pred_lower},{pred_upper},{pred_lower_closed},{pred_upper_closed}), "
        f"expected=({expected_lower},{expected_upper},{expected_lower_closed},{expected_upper_closed})"
    )
    return GradeResult(ok, 1.0 if ok else 0.0, "none" if ok else "wrong_interval", detail)


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
    "fraction_string": grade_fraction_string,
    "choice": grade_choice,
    "contains_all": grade_contains_all,
    "contains_ordered": grade_contains_ordered,
    "nand_expression": grade_nand_expression,
    "numeric": grade_numeric,
    "range_interval": grade_range_interval,
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
