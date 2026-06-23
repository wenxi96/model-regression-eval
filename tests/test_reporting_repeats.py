from model_regression_eval.reporting import compare_rows, summarize_rows


def row(task_id, repeat, correct, domain='math'):
    return {
        'task_id': task_id,
        'repeat': repeat,
        'domain': domain,
        'skill': 's',
        'weight': 1,
        'valid': True,
        'correct': correct,
        'format_error': False,
        'tool_violation': False,
    }


def test_summarize_rows_reports_majority_and_consistency():
    rows = [
        row('a', 1, True), row('a', 2, True), row('a', 3, False),
        row('b', 1, False), row('b', 2, False), row('b', 3, False),
    ]
    summary = summarize_rows(rows)
    assert summary['task_count'] == 2
    assert summary['max_repeats_per_task'] == 3
    assert summary['majority_accuracy'] == 0.5
    assert summary['consistency_rate'] == 0.5
    assert summary['unstable_task_count'] == 1
    assert summary['stable_failure_count'] == 1


def test_summarize_rows_reports_tool_violation_unknown_rate():
    rows = [
        row('a', 1, True) | {'tool_violation': False, 'tool_violation_unknown': True},
        row('b', 1, True) | {'tool_violation': True, 'tool_violation_unknown': False},
    ]
    summary = summarize_rows(rows)
    assert summary['tool_violation_rate'] == 1.0
    assert summary['tool_violation_unknown_rate'] == 0.5
    assert summary['by_domain'][0]['tool_violation_rate'] == 1.0
    assert summary['by_domain'][0]['tool_violation_unknown_rate'] == 0.5


def test_compare_rows_reports_stable_task_regressions():
    baseline = [row('a', 1, True), row('a', 2, True), row('a', 3, True)]
    candidate = [row('a', 1, False), row('a', 2, False), row('a', 3, True)]
    summary = compare_rows(baseline, candidate)
    assert summary['paired_tasks'] == 1
    assert summary['stable_regressions'] == 1
    assert summary['net_stable_regressions'] == 1
    assert summary['candidate_majority_accuracy'] == 0.0


def test_compare_rows_keeps_regression_when_domains_differ():
    baseline = [row('a', 1, True, domain='math')]
    candidate = [row('a', 1, False, domain='logic')]
    summary = compare_rows(baseline, candidate)
    assert summary['net_regressions'] == 1
    assert summary['domain_mismatch_count'] == 1
    assert summary['warnings']
    assert summary['by_domain'][0]['domain'] == 'math -> logic'
    assert summary['by_domain'][0]['regressions'] == 1


def test_compare_rows_warns_on_task_set_mismatch():
    baseline = [row('a', 1, True), row('b', 1, True)]
    candidate = [row('a', 1, True), row('c', 1, False)]
    summary = compare_rows(baseline, candidate)
    assert summary['paired_cases'] == 1
    assert summary['task_overlap_rate'] < 1
    assert any('Task sets differ' in w for w in summary['warnings'])
