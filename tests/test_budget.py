from pathlib import Path

from model_regression_eval.budget import summarize_budget
from model_regression_eval.tasks import load_tasks


def test_budget_summary_counts_requests_and_tokens():
    tasks = load_tasks(Path('tasks/core.zh.jsonl'))[:5]
    summary = summarize_budget(tasks, repeats=2, wrapper='固定包装')
    assert summary.tasks == 5
    assert summary.repeats == 2
    assert summary.requests == 10
    assert summary.estimated_prompt_tokens_per_run > 0
    assert summary.estimated_prompt_tokens_with_repeats == summary.estimated_prompt_tokens_per_run * 2
    assert summary.by_domain
