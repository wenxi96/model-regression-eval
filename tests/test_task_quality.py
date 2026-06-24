from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import re

from model_regression_eval.tasks import load_tasks


def _prompt_skeleton(prompt: str) -> str:
    text = prompt.lower()
    text = re.sub(r"```.*?```", "<code>", text, flags=re.S)
    text = re.sub(r"\d+(?:\.\d+)?", "<n>", text)
    text = re.sub(r"[一二三四五六七八九十零〇两]+", "<cn>", text)
    text = re.sub(r"周[一二三四五六日天]", "周<d>", text)
    text = re.sub(r"\s+", "", text)
    return text


def test_choice_answer_letters_are_not_dominated_within_large_skill_groups():
    tasks = load_tasks(Path("tasks/core.zh.jsonl"))
    by_skill: dict[str, Counter[str]] = defaultdict(Counter)
    for task in tasks:
        if task.grader == "choice":
            by_skill[task.skill][str(task.expected)[:1]] += 1

    offenders = {}
    for skill, counts in by_skill.items():
        total = sum(counts.values())
        if total < 4:
            continue
        max_share = max(counts.values()) / total
        if max_share >= 0.70:
            offenders[skill] = dict(counts)

    assert offenders == {}


def test_prompt_near_duplicate_skeletons_are_capped():
    tasks = load_tasks(Path("tasks/core.zh.jsonl"))
    clusters: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for task in tasks:
        clusters[(task.domain, task.skill, _prompt_skeleton(task.prompt))].append(task.id)

    offenders = {key: ids for key, ids in clusters.items() if len(ids) > 8}
    assert offenders == {}


def test_task_distribution_guardrails():
    tasks = load_tasks(Path("tasks/core.zh.jsonl"))
    assert len(tasks) == 300
    domains = Counter(task.domain for task in tasks)
    assert {"math", "logic", "code", "instruction", "reading", "robustness", "metacognition"}.issubset(domains)
    assert domains["metacognition"] >= 5
    assert domains["math"] >= 70
    assert domains["code"] >= 40
