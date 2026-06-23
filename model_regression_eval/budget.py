from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re
from typing import Any

from .tasks import EvalTask

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_ASCII_WORD_RE = re.compile(r"[A-Za-z0-9_]+|[^\sA-Za-z0-9_\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def estimate_text_tokens(text: str) -> int:
    """Rough, tokenizer-free estimate suitable for budgeting, not billing.

    Chinese characters are counted close to one token each; ASCII words and punctuation
    are counted as compact token-like chunks. A small overhead is added to avoid
    optimistic estimates for short prompts.
    """
    cjk = len(_CJK_RE.findall(text))
    non_cjk = _CJK_RE.sub(" ", text)
    chunks = _ASCII_WORD_RE.findall(non_cjk)
    # ASCII chunks are often one token but long identifiers/code fragments split.
    ascii_like = 0
    for chunk in chunks:
        if re.fullmatch(r"[A-Za-z0-9_]+", chunk):
            ascii_like += max(1, (len(chunk) + 5) // 6)
        else:
            ascii_like += 1
    return max(1, int(cjk + ascii_like + 12))


def estimate_task_prompt_tokens(task: EvalTask, wrapper: str = "") -> int:
    return estimate_text_tokens(wrapper + task.prompt)


@dataclass(frozen=True)
class BudgetSummary:
    tasks: int
    repeats: int
    requests: int
    estimated_prompt_tokens_per_run: int
    estimated_prompt_tokens_with_repeats: int
    average_prompt_tokens: float
    max_prompt_tokens: int
    by_domain: list[dict[str, Any]]
    by_skill: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tasks": self.tasks,
            "repeats": self.repeats,
            "requests": self.requests,
            "estimated_prompt_tokens_per_run": self.estimated_prompt_tokens_per_run,
            "estimated_prompt_tokens_with_repeats": self.estimated_prompt_tokens_with_repeats,
            "average_prompt_tokens": self.average_prompt_tokens,
            "max_prompt_tokens": self.max_prompt_tokens,
            "by_domain": self.by_domain,
            "by_skill": self.by_skill,
        }


def summarize_budget(tasks: list[EvalTask], *, repeats: int = 1, wrapper: str = "") -> BudgetSummary:
    token_by_task = [(task, estimate_task_prompt_tokens(task, wrapper)) for task in tasks]
    total = sum(tokens for _, tokens in token_by_task)
    avg = total / len(token_by_task) if token_by_task else 0.0
    max_tokens = max((tokens for _, tokens in token_by_task), default=0)
    return BudgetSummary(
        tasks=len(tasks),
        repeats=repeats,
        requests=len(tasks) * repeats,
        estimated_prompt_tokens_per_run=total,
        estimated_prompt_tokens_with_repeats=total * repeats,
        average_prompt_tokens=avg,
        max_prompt_tokens=max_tokens,
        by_domain=_group_budget(token_by_task, "domain"),
        by_skill=_group_budget(token_by_task, "skill"),
    )


def _group_budget(token_by_task: list[tuple[EvalTask, int]], attr: str) -> list[dict[str, Any]]:
    groups: dict[str, list[int]] = defaultdict(list)
    for task, tokens in token_by_task:
        groups[str(getattr(task, attr))].append(tokens)
    out = []
    for name, values in sorted(groups.items()):
        total = sum(values)
        out.append(
            {
                attr: name,
                "tasks": len(values),
                "estimated_prompt_tokens": total,
                "average_prompt_tokens": total / len(values) if values else 0.0,
                "max_prompt_tokens": max(values) if values else 0,
            }
        )
    return out


def markdown_budget(summary: BudgetSummary) -> str:
    data = summary.to_dict()
    lines = ["# Token Budget Estimate", ""]
    lines += [
        f"- Tasks: {data['tasks']}",
        f"- Repeats: {data['repeats']}",
        f"- Requests: {data['requests']}",
        f"- Estimated prompt tokens / single pass: {data['estimated_prompt_tokens_per_run']}",
        f"- Estimated prompt tokens including repeats: {data['estimated_prompt_tokens_with_repeats']}",
        f"- Average prompt tokens / task: {data['average_prompt_tokens']:.1f}",
        f"- Max prompt tokens / task: {data['max_prompt_tokens']}",
        "",
        "> This is a tokenizer-free planning estimate. Treat Codex JSONL `turn.completed.usage` as the source of truth after a real run.",
        "",
        "## By domain",
        "",
        "| domain | tasks | est prompt tokens | avg/task | max/task |",
        "|---|---:|---:|---:|---:|",
    ]
    for item in data["by_domain"]:
        lines.append(
            f"| {item['domain']} | {item['tasks']} | {item['estimated_prompt_tokens']} | "
            f"{item['average_prompt_tokens']:.1f} | {item['max_prompt_tokens']} |"
        )
    lines += ["", "## By skill", "", "| skill | tasks | est prompt tokens | avg/task | max/task |", "|---|---:|---:|---:|---:|"]
    for item in data["by_skill"]:
        lines.append(
            f"| {item['skill']} | {item['tasks']} | {item['estimated_prompt_tokens']} | "
            f"{item['average_prompt_tokens']:.1f} | {item['max_prompt_tokens']} |"
        )
    return "\n".join(lines) + "\n"
