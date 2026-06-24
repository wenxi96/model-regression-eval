from pathlib import Path

from model_regression_eval.budget import markdown_budget, summarize_budget
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


def test_markdown_budget_uses_chinese_report_labels():
    tasks = load_tasks(Path('tasks/core.zh.jsonl'))[:5]
    summary = summarize_budget(tasks, repeats=1, wrapper='固定包装')
    md = markdown_budget(summary)
    assert md.startswith('# Token 预算估算')
    assert '## 按领域统计' in md
    assert '| 领域 | 题目数 | 提示词 token 估算 | 平均/题 | 最大/题 |' in md
