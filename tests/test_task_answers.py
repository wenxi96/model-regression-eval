from __future__ import annotations

import ast
from fractions import Fraction
import itertools
from pathlib import Path
import re
import subprocess
import sys

from model_regression_eval.graders import normalize_text
from model_regression_eval.tasks import EvalTask, load_tasks


_ALLOWED_AST = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.USub,
    ast.UAdd,
)


def _safe_eval(expr: str, **names: int | float) -> float:
    tree = ast.parse(expr, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_AST):
            raise ValueError(f"disallowed expression node: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id not in names:
            raise ValueError(f"unknown name: {node.id}")
    return eval(compile(tree, "<task-answer-check>", "eval"), {"__builtins__": {}}, names)


def _parse_arithmetic(task: EvalTask) -> int | None:
    prompt = task.prompt
    match = re.search(r"计算[:：](.+?)(?:。|$)", prompt)
    if match:
        expr = match.group(1).replace("×", "*").replace("÷", "/")
        return int(_safe_eval(expr))
    match = re.search(r"2 的 8 次方除以 16", prompt)
    if match:
        return 2**8 // 16
    match = re.search(r"45 的五分之二", prompt)
    if match:
        return 45 * 2 // 5
    return None


def _parse_equation(task: EvalTask) -> int | None:
    match = re.search(r"解方程[:：](.+?)[。；]", task.prompt)
    if not match:
        return None
    equation = match.group(1).replace("÷", "/")
    equation = re.sub(r"(\d)(x)", r"\1*\2", equation)
    equation = re.sub(r"(\d)\(", r"\1*(", equation)
    left, right = equation.split("=", 1)
    for x in range(-1000, 1001):
        if abs(_safe_eval(left, x=x) - _safe_eval(right, x=x)) < 1e-9:
            return x
    return None


def _parse_unit(task: EvalTask) -> int | None:
    prompt = task.prompt
    if "千克" in prompt and "克" in prompt:
        match = re.search(r"(\d+(?:\.\d+)?)千克", prompt)
        if match:
            return int(float(match.group(1)) * 1000)
    if "米" in prompt and "厘米" in prompt:
        match = re.search(r"(\d+(?:\.\d+)?)米", prompt)
        if match:
            return int(float(match.group(1)) * 100)
    if "小时" in prompt and "分钟" in prompt:
        match = re.search(r"(\d+(?:\.\d+)?)小时", prompt)
        if match:
            return int(float(match.group(1)) * 60)
    return None


def _parse_inventory(task: EvalTask) -> int | None:
    prompt = task.prompt
    match = re.search(r"(?:早上有|初始)(\d+)", prompt)
    if not match:
        return None
    total = int(match.group(1))
    rest = prompt[match.end() :]
    end = re.search(r"(?:最后剩|库存多少|晚上还剩|傍晚结束库存)(?:多少)?", rest)
    if not end:
        return None
    rest = rest[: end.start()]
    for op, value in re.findall(r"(增加|减少|发出|补入|售出|退回|移出)\D*?(\d+)", rest):
        n = int(value)
        if op in {"增加", "补入", "退回"}:
            total += n
        else:
            total -= n
    return total


def _extract_code(prompt: str) -> str | None:
    if "\n\n" not in prompt:
        return None
    text = prompt.split("\n\n", 1)[1]
    code = re.split(r"\n\n(?=[\u4e00-\u9fff])", text, maxsplit=1)[0].strip()
    if "print(" not in code or re.search(r"[\u4e00-\u9fff]", code):
        return None
    return code or None


def _run_code_stdout(code: str) -> str:
    proc = subprocess.run(
        [sys.executable, "-I", "-c", code],
        capture_output=True,
        text=True,
        timeout=2,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stderr
    return (proc.stdout or "").strip().splitlines()[-1]


def _task_by_id(tasks: list[EvalTask], task_id: str) -> EvalTask:
    return next(task for task in tasks if task.id == task_id)


def _decode_letter_average_cipher(text: str) -> str:
    words = []
    for word in text.split():
        chars = []
        for a, b in zip(word[::2], word[1::2]):
            avg = (ord(a) - 96 + ord(b) - 96) // 2
            chars.append(chr(avg + 96))
        words.append("".join(chars))
    return " ".join(words)


def _is_adjacent_seat(left: int, right: int) -> bool:
    return left // 4 == right // 4 and abs(left - right) == 1


def _safe_password_candidates() -> list[str]:
    guesses = ["9062437", "8593624", "4286915", "3450982"]
    candidates = []
    for digits in itertools.permutations("0123456789", 7):
        password = "".join(digits)
        ok = True
        for guess in guesses:
            matched = [i for i, (actual, guessed) in enumerate(zip(password, guess)) if actual == guessed]
            if len(matched) != 2 or abs(matched[0] - matched[1]) == 1:
                ok = False
                break
        if ok:
            candidates.append(password)
    return candidates


def _random_flip_success_probability() -> Fraction:
    def terminal_success(state: int) -> bool:
        return bool(state & 0b0000011 == 0b0000011)

    def terminal_failure(state: int) -> bool:
        return bool(state & 0b0011100 == 0b0011100 or state & 0b1100000 == 0b1100000)

    states = [state for state in range(1 << 7) if not terminal_success(state) and not terminal_failure(state)]
    index = {state: i for i, state in enumerate(states)}
    n = len(states)
    matrix = [[Fraction(0) for _ in range(n)] for _ in range(n)]
    rhs = [Fraction(0) for _ in range(n)]
    for state in states:
        row = index[state]
        matrix[row][row] = Fraction(1)
        for bit in range(7):
            nxt = state ^ (1 << bit)
            if terminal_success(nxt):
                rhs[row] += Fraction(1, 7)
            elif terminal_failure(nxt):
                continue
            else:
                matrix[row][index[nxt]] -= Fraction(1, 7)

    for col in range(n):
        pivot = next(row for row in range(col, n) if matrix[row][col])
        matrix[col], matrix[pivot] = matrix[pivot], matrix[col]
        rhs[col], rhs[pivot] = rhs[pivot], rhs[col]
        factor = matrix[col][col]
        matrix[col] = [value / factor for value in matrix[col]]
        rhs[col] /= factor
        for row in range(n):
            if row == col or not matrix[row][col]:
                continue
            factor = matrix[row][col]
            matrix[row] = [value - factor * base for value, base in zip(matrix[row], matrix[col])]
            rhs[row] -= factor * rhs[col]

    return rhs[index[0]]


def test_calculable_math_and_reading_answers_match_expected():
    tasks = load_tasks(Path("tasks/core.zh.jsonl"))
    checked = []
    for task in tasks:
        actual = None
        if task.id.startswith("math_arithmetic_"):
            actual = _parse_arithmetic(task)
        elif task.id.startswith("math_equation_"):
            actual = _parse_equation(task)
        elif task.skill == "unit_conversion":
            actual = _parse_unit(task)
        elif task.domain == "reading" and task.grader == "exact_int":
            actual = _parse_inventory(task)
        if actual is None:
            continue
        checked.append(task.id)
        assert actual == int(task.expected), task.id

    assert len(checked) >= 20


def test_python_code_trace_answers_match_execution():
    tasks = load_tasks(Path("tasks/core.zh.jsonl"))
    checked = []
    for task in tasks:
        if task.domain != "code" or task.grader not in {"exact_int", "exact_string"}:
            continue
        code = _extract_code(task.prompt)
        if code is None:
            continue
        actual = normalize_text(_run_code_stdout(code))
        expected = normalize_text(task.expected)
        checked.append(task.id)
        assert actual == expected, task.id

    assert len(checked) >= 25


def test_reviewed_complex_answers_match_independent_programmatic_checks():
    tasks = load_tasks(Path("tasks/core.zh.jsonl"))

    concat = _task_by_id(tasks, "math_concat_permutation_001")
    numbers = ["2", "0", "1", "9", "20", "19"]
    unique_values = {"".join(parts) for parts in itertools.permutations(numbers) if parts[0] != "0"}
    assert len(unique_values) == int(concat.expected)

    seating = _task_by_id(tasks, "math_seating_constraints_001")
    people = "ABCDEFGH"
    count = 0
    for arrangement in itertools.permutations(people):
        positions = {person: arrangement.index(person) for person in people}
        if _is_adjacent_seat(positions["A"], positions["B"]) and not _is_adjacent_seat(positions["C"], positions["D"]):
            count += 1
    assert count == int(seating.expected)

    cube = _task_by_id(tasks, "math_cube_cut_water_level_001")
    lower_cut_volume = 10 * (30 * 30 - 4 * 10 * 10)
    middle_volume = 10 * 30 * 30
    h = Fraction(2500 * 20 + lower_cut_volume + middle_volume - 500 * 20, 2500 - 500)
    assert h == int(cube.expected)

    password = _task_by_id(tasks, "logic_safe_password_001")
    candidates = _safe_password_candidates()
    assert candidates == [str(password.expected)]

    cipher = _task_by_id(tasks, "logic_letter_average_cipher_001")
    encoded = "oyekaijzdf aaptcg suaokybhai ouow aqht mynznvaatzacdfoulxxz"
    assert _decode_letter_average_cipher(encoded) == cipher.expected

    random_flip = _task_by_id(tasks, "math_random_flip_absorption_001")
    assert str(_random_flip_success_probability()) == random_flip.expected

    piecewise = _task_by_id(tasks, "math_piecewise_function_collinear_slope_001")
    assert piecewise.grader == "range_interval"
    assert Fraction(piecewise.expected["lower"]) == Fraction(0)
    assert Fraction(piecewise.expected["upper"]) == Fraction(2, 9)
    assert piecewise.expected["lower_closed"] is False
    assert piecewise.expected["upper_closed"] is False
