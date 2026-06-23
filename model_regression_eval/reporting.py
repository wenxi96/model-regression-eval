from __future__ import annotations

from collections import defaultdict
import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from .tasks import read_jsonl


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _percent(x: float | None) -> str:
    if x is None or math.isnan(x):
        return "-"
    return f"{x * 100:.1f}%"


def weighted_accuracy(rows: Iterable[dict[str, Any]]) -> float | None:
    total_weight = 0.0
    correct_weight = 0.0
    for row in rows:
        if row.get("valid") is False:
            continue
        weight = float(row.get("weight", 1.0))
        total_weight += weight
        correct_weight += weight * (1.0 if row.get("correct") else 0.0)
    if total_weight <= 0:
        return None
    return correct_weight / total_weight


def simple_accuracy(rows: Iterable[dict[str, Any]]) -> float | None:
    usable = [r for r in rows if r.get("valid") is not False]
    if not usable:
        return None
    return sum(1 for r in usable if r.get("correct")) / len(usable)


def median_field(rows: Iterable[dict[str, Any]], field: str) -> float | None:
    vals = [_safe_float(row.get(field)) for row in rows]
    vals = [x for x in vals if x is not None]
    if not vals:
        return None
    return float(median(vals))


def sum_field(rows: Iterable[dict[str, Any]], field: str) -> int | None:
    vals = [_safe_float(row.get(field)) for row in rows]
    vals = [x for x in vals if x is not None]
    if not vals:
        return None
    return int(sum(vals))


def observed_io_tokens(rows: Iterable[dict[str, Any]]) -> int | None:
    rows = list(rows)
    input_total = sum_field(rows, "input_tokens")
    output_total = sum_field(rows, "output_tokens")
    if input_total is None and output_total is None:
        return None
    return int(input_total or 0) + int(output_total or 0)


def group_by_task(rows: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("task_id"))].append(row)
    for items in grouped.values():
        items.sort(key=lambda r: int(r.get("repeat") or 0))
    return dict(grouped)


def task_vote(items: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [r for r in items if r.get("valid") is not False]
    correct_count = sum(1 for r in valid if r.get("correct"))
    valid_count = len(valid)
    incorrect_count = valid_count - correct_count
    if valid_count == 0:
        majority_correct = None
        any_correct = None
        all_correct = None
        consistency = None
        tie = False
    else:
        majority_correct = correct_count > (valid_count / 2)
        any_correct = correct_count > 0
        all_correct = correct_count == valid_count
        consistency = correct_count in {0, valid_count}
        tie = correct_count == incorrect_count
    first = items[0] if items else {}
    return {
        "task_id": first.get("task_id"),
        "domain": first.get("domain"),
        "skill": first.get("skill"),
        "valid_repeats": valid_count,
        "total_repeats": len(items),
        "correct_repeats": correct_count,
        "incorrect_repeats": incorrect_count,
        "majority_correct": majority_correct,
        "any_correct": any_correct,
        "all_correct": all_correct,
        "consistent": consistency,
        "tie": tie,
    }


def repetition_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped = group_by_task(rows)
    votes = [task_vote(items) for items in grouped.values()]
    valid_votes = [v for v in votes if v["valid_repeats"] > 0]
    if not valid_votes:
        return {
            "task_count": len(grouped),
            "max_repeats_per_task": 0,
            "majority_accuracy": None,
            "any_correct_rate": None,
            "all_correct_rate": None,
            "consistency_rate": None,
            "tie_rate": None,
            "unstable_task_count": 0,
            "stable_failure_count": 0,
            "stable_success_count": 0,
            "unstable_items": [],
            "stable_failure_items": [],
        }
    max_repeats = max(v["total_repeats"] for v in votes) if votes else 0
    unstable = [v for v in valid_votes if v["consistent"] is False]
    stable_failures = [v for v in valid_votes if v["valid_repeats"] > 0 and v["correct_repeats"] == 0]
    stable_successes = [v for v in valid_votes if v["valid_repeats"] > 0 and v["correct_repeats"] == v["valid_repeats"]]
    return {
        "task_count": len(grouped),
        "max_repeats_per_task": max_repeats,
        "majority_accuracy": sum(1 for v in valid_votes if v["majority_correct"]) / len(valid_votes),
        "any_correct_rate": sum(1 for v in valid_votes if v["any_correct"]) / len(valid_votes),
        "all_correct_rate": sum(1 for v in valid_votes if v["all_correct"]) / len(valid_votes),
        "consistency_rate": sum(1 for v in valid_votes if v["consistent"]) / len(valid_votes),
        "tie_rate": sum(1 for v in valid_votes if v["tie"]) / len(valid_votes),
        "unstable_task_count": len(unstable),
        "stable_failure_count": len(stable_failures),
        "stable_success_count": len(stable_successes),
        "unstable_items": unstable[:100],
        "stable_failure_items": stable_failures[:100],
    }


def group_summary(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(key, "unknown"))].append(row)
    out = []
    for name, items in sorted(groups.items()):
        rep = repetition_summary(items)
        out.append(
            {
                key: name,
                "n": len(items),
                "tasks": rep["task_count"],
                "accuracy": simple_accuracy(items),
                "weighted_accuracy": weighted_accuracy(items),
                "majority_accuracy": rep["majority_accuracy"],
                "consistency_rate": rep["consistency_rate"],
                "format_error_rate": rate(items, "format_error"),
                "tool_violation_rate": tool_violation_rate(items),
                "tool_violation_unknown_rate": rate(items, "tool_violation_unknown"),
                "median_input_tokens": median_field(items, "input_tokens"),
                "median_output_tokens": median_field(items, "output_tokens"),
                "median_reasoning_tokens": median_field(items, "reasoning_output_tokens"),
                "median_latency_s": median_field(items, "latency_s"),
                "total_input_tokens": sum_field(items, "input_tokens"),
                "total_output_tokens": sum_field(items, "output_tokens"),
                "total_reasoning_tokens": sum_field(items, "reasoning_output_tokens"),
                "observed_io_tokens": observed_io_tokens(items),
            }
        )
    return out


def rate(rows: Iterable[dict[str, Any]], field: str) -> float | None:
    rows = list(rows)
    if not rows:
        return None
    return sum(1 for r in rows if r.get(field)) / len(rows)


def tool_violation_rate(rows: Iterable[dict[str, Any]]) -> float | None:
    known = [r for r in rows if not r.get("tool_violation_unknown")]
    return rate(known, "tool_violation")


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rep = repetition_summary(rows)
    return {
        "n": len(rows),
        "task_count": rep["task_count"],
        "max_repeats_per_task": rep["max_repeats_per_task"],
        "accuracy": simple_accuracy(rows),
        "weighted_accuracy": weighted_accuracy(rows),
        "majority_accuracy": rep["majority_accuracy"],
        "any_correct_rate": rep["any_correct_rate"],
        "all_correct_rate": rep["all_correct_rate"],
        "consistency_rate": rep["consistency_rate"],
        "tie_rate": rep["tie_rate"],
        "unstable_task_count": rep["unstable_task_count"],
        "stable_failure_count": rep["stable_failure_count"],
        "stable_success_count": rep["stable_success_count"],
        "unstable_items": rep["unstable_items"],
        "stable_failure_items": rep["stable_failure_items"],
        "format_error_rate": rate(rows, "format_error"),
        "tool_violation_rate": tool_violation_rate(rows),
        "tool_violation_unknown_rate": rate(rows, "tool_violation_unknown"),
        "median_input_tokens": median_field(rows, "input_tokens"),
        "median_output_tokens": median_field(rows, "output_tokens"),
        "median_reasoning_tokens": median_field(rows, "reasoning_output_tokens"),
        "median_latency_s": median_field(rows, "latency_s"),
        "total_input_tokens": sum_field(rows, "input_tokens"),
        "total_output_tokens": sum_field(rows, "output_tokens"),
        "total_reasoning_tokens": sum_field(rows, "reasoning_output_tokens"),
        "observed_io_tokens": observed_io_tokens(rows),
        "by_domain": group_summary(rows, "domain"),
        "by_skill": group_summary(rows, "skill"),
    }


def markdown_summary(title: str, summary: dict[str, Any], rows: list[dict[str, Any]] | None = None) -> str:
    lines = [f"# {title}", ""]
    lines += [
        f"- Cases: {summary['n']}",
        f"- Unique tasks: {summary.get('task_count', '-')}",
        f"- Max repeats per task: {summary.get('max_repeats_per_task', '-')}",
        f"- Accuracy: {_percent(summary['accuracy'])}",
        f"- Weighted accuracy: {_percent(summary['weighted_accuracy'])}",
        f"- Majority accuracy by task: {_percent(summary.get('majority_accuracy'))}",
        f"- Any-correct rate by task: {_percent(summary.get('any_correct_rate'))}",
        f"- All-correct rate by task: {_percent(summary.get('all_correct_rate'))}",
        f"- Consistency rate by task: {_percent(summary.get('consistency_rate'))}",
        f"- Tie rate by task: {_percent(summary.get('tie_rate'))}",
        f"- Unstable tasks: {summary.get('unstable_task_count', 0)}",
        f"- Stable failure tasks: {summary.get('stable_failure_count', 0)}",
        f"- Format error rate: {_percent(summary['format_error_rate'])}",
        f"- Tool violation rate: {_percent(summary['tool_violation_rate'])}",
        f"- Tool violation unknown rate: {_percent(summary.get('tool_violation_unknown_rate'))}",
        f"- Median input tokens: {fmt_num(summary.get('median_input_tokens'))}",
        f"- Median output tokens: {fmt_num(summary.get('median_output_tokens'))}",
        f"- Median reasoning tokens: {fmt_num(summary['median_reasoning_tokens'])}",
        f"- Median latency: {fmt_num(summary['median_latency_s'])} s",
        f"- Total input tokens: {fmt_num(summary.get('total_input_tokens'))}",
        f"- Total output tokens: {fmt_num(summary.get('total_output_tokens'))}",
        f"- Total reasoning tokens: {fmt_num(summary.get('total_reasoning_tokens'))}",
        f"- Observed input+output tokens: {fmt_num(summary.get('observed_io_tokens'))}",
        "",
        "## By domain",
        "",
        "| domain | cases | tasks | accuracy | majority | consistency | weighted | format errors | tool violations | tool unknown | total in | total out | total reasoning | median reasoning | median latency s |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in summary["by_domain"]:
        lines.append(
            f"| {item['domain']} | {item['n']} | {item['tasks']} | {_percent(item['accuracy'])} | {_percent(item.get('majority_accuracy'))} | "
            f"{_percent(item.get('consistency_rate'))} | {_percent(item['weighted_accuracy'])} | "
            f"{_percent(item['format_error_rate'])} | {_percent(item['tool_violation_rate'])} | {_percent(item.get('tool_violation_unknown_rate'))} | "
            f"{fmt_num(item.get('total_input_tokens'))} | {fmt_num(item.get('total_output_tokens'))} | {fmt_num(item.get('total_reasoning_tokens'))} | "
            f"{fmt_num(item['median_reasoning_tokens'])} | {fmt_num(item['median_latency_s'])} |"
        )
    if rows:
        failures = [r for r in rows if not r.get("correct")]
        if failures:
            lines += ["", "## Failures", "", "| task | repeat | domain | skill | failure mode | answer | expected | detail |", "|---|---:|---|---|---|---|---|---|"]
            for r in failures[:50]:
                lines.append(
                    f"| {esc(r.get('task_id'))} | {r.get('repeat')} | {esc(r.get('domain'))} | {esc(r.get('skill'))} | "
                    f"{esc(r.get('failure_mode'))} | {esc(r.get('answer'))} | {esc(r.get('expected'))} | {esc(r.get('grade_detail'))} |"
                )
            if len(failures) > 50:
                lines.append(f"\nOnly showing first 50 failures of {len(failures)}.")
        unstable = summary.get("unstable_items") or []
        if unstable:
            lines += ["", "## Unstable tasks", "", "| task | domain | skill | correct / repeats |", "|---|---|---|---:|"]
            for item in unstable[:50]:
                lines.append(
                    f"| {esc(item.get('task_id'))} | {esc(item.get('domain'))} | {esc(item.get('skill'))} | "
                    f"{item.get('correct_repeats')}/{item.get('valid_repeats')} |"
                )
    return "\n".join(lines) + "\n"


def fmt_num(value: Any) -> str:
    if value is None:
        return "-"
    try:
        x = float(value)
    except Exception:
        return str(value)
    if math.isnan(x):
        return "-"
    if abs(x - round(x)) <= 1e-9:
        return str(int(round(x)))
    if 0 < abs(x) < 0.001:
        return f"{x:.3g}"
    if abs(x) < 1:
        return f"{x:.4f}"
    return f"{x:.1f}"


def esc(value: Any) -> str:
    s = str(value) if value is not None else ""
    return s.replace("|", "\\|").replace("\n", " ")


def exact_binomial_two_sided(k: int, n: int, p: float = 0.5) -> float | None:
    if n <= 0:
        return None
    observed = math.comb(n, k) * (p**k) * ((1 - p) ** (n - k))
    total = 0.0
    for i in range(n + 1):
        prob = math.comb(n, i) * (p**i) * ((1 - p) ** (n - i))
        if prob <= observed + 1e-15:
            total += prob
    return min(1.0, total)


def compare_rows(baseline: list[dict[str, Any]], candidate: list[dict[str, Any]]) -> dict[str, Any]:
    base_map = {(r.get("task_id"), r.get("repeat")): r for r in baseline}
    cand_map = {(r.get("task_id"), r.get("repeat")): r for r in candidate}
    common_keys = sorted(set(base_map) & set(cand_map))
    pairs = [(base_map[k], cand_map[k]) for k in common_keys]
    regressions = [(b, c) for b, c in pairs if b.get("correct") and not c.get("correct")]
    improvements = [(b, c) for b, c in pairs if not b.get("correct") and c.get("correct")]
    discordant = len(regressions) + len(improvements)
    p_value = exact_binomial_two_sided(min(len(regressions), len(improvements)), discordant) if discordant else None

    base_task_ids = {r.get("task_id") for r in baseline}
    cand_task_ids = {r.get("task_id") for r in candidate}
    common_task_ids = base_task_ids & cand_task_ids
    task_overlap_denominator = max(len(base_task_ids | cand_task_ids), 1)
    task_overlap_rate = len(common_task_ids) / task_overlap_denominator
    warnings: list[str] = []
    if base_task_ids != cand_task_ids:
        warnings.append(
            f"Task sets differ: baseline={len(base_task_ids)}, candidate={len(cand_task_ids)}, common={len(common_task_ids)}. "
            "Only common (task_id, repeat) pairs are compared."
        )
    missing_baseline_cases = len(set(cand_map) - set(base_map))
    missing_candidate_cases = len(set(base_map) - set(cand_map))
    if missing_baseline_cases or missing_candidate_cases:
        warnings.append(
            f"Case sets differ: missing_in_baseline={missing_baseline_cases}, missing_in_candidate={missing_candidate_cases}."
        )
    domain_mismatches = [
        {
            "task_id": b.get("task_id"),
            "repeat": b.get("repeat"),
            "baseline_domain": b.get("domain"),
            "candidate_domain": c.get("domain"),
        }
        for b, c in pairs
        if str(b.get("domain", "unknown")) != str(c.get("domain", "unknown"))
    ]
    if domain_mismatches:
        warnings.append(f"Domain mismatch in {len(domain_mismatches)} paired cases. By-domain rows use 'baseline -> candidate' labels for mismatches.")

    def pair_domain(b: dict[str, Any], c: dict[str, Any]) -> str:
        bd = str(b.get("domain", "unknown"))
        cd = str(c.get("domain", "unknown"))
        return bd if bd == cd else f"{bd} -> {cd}"

    by_domain = []
    domains = sorted({pair_domain(b, c) for b, c in pairs})
    for domain in domains:
        domain_pairs = [(b, c) for b, c in pairs if pair_domain(b, c) == domain]
        base_items = [b for b, _ in domain_pairs]
        cand_items = [c for _, c in domain_pairs]
        by_domain.append(
            {
                "domain": domain,
                "n": len(domain_pairs),
                "baseline_accuracy": simple_accuracy(base_items),
                "candidate_accuracy": simple_accuracy(cand_items),
                "delta_accuracy": delta(simple_accuracy(cand_items), simple_accuracy(base_items)),
                "regressions": sum(1 for b, c in domain_pairs if b.get("correct") and not c.get("correct")),
                "improvements": sum(1 for b, c in domain_pairs if not b.get("correct") and c.get("correct")),
            }
        )

    task_level = compare_task_majorities(baseline, candidate)
    base_acc = simple_accuracy([b for b, _ in pairs])
    cand_acc = simple_accuracy([c for _, c in pairs])
    return {
        "paired_cases": len(pairs),
        "paired_tasks": task_level["paired_tasks"],
        "baseline_task_count": len(base_task_ids),
        "candidate_task_count": len(cand_task_ids),
        "common_task_count": len(common_task_ids),
        "task_overlap_rate": task_overlap_rate,
        "missing_baseline_cases": missing_baseline_cases,
        "missing_candidate_cases": missing_candidate_cases,
        "domain_mismatch_count": len(domain_mismatches),
        "domain_mismatch_items": domain_mismatches[:100],
        "warnings": warnings,
        "baseline_accuracy": base_acc,
        "candidate_accuracy": cand_acc,
        "delta_accuracy": delta(cand_acc, base_acc),
        "baseline_weighted_accuracy": weighted_accuracy([b for b, _ in pairs]),
        "candidate_weighted_accuracy": weighted_accuracy([c for _, c in pairs]),
        "baseline_majority_accuracy": task_level["baseline_majority_accuracy"],
        "candidate_majority_accuracy": task_level["candidate_majority_accuracy"],
        "delta_majority_accuracy": delta(task_level["candidate_majority_accuracy"], task_level["baseline_majority_accuracy"]),
        "stable_regressions": task_level["stable_regressions"],
        "stable_improvements": task_level["stable_improvements"],
        "net_stable_regressions": task_level["stable_regressions"] - task_level["stable_improvements"],
        "mcnemar_exact_p_task_majority": task_level["mcnemar_exact_p"],
        "regressions": len(regressions),
        "improvements": len(improvements),
        "net_regressions": len(regressions) - len(improvements),
        "mcnemar_exact_p": p_value,
        "by_domain": by_domain,
        "regression_items": [comparison_item(b, c) for b, c in regressions],
        "improvement_items": [comparison_item(b, c) for b, c in improvements],
        "stable_regression_items": task_level["stable_regression_items"],
        "stable_improvement_items": task_level["stable_improvement_items"],
    }


def compare_task_majorities(baseline: list[dict[str, Any]], candidate: list[dict[str, Any]]) -> dict[str, Any]:
    base_votes = {tid: task_vote(items) for tid, items in group_by_task(baseline).items()}
    cand_votes = {tid: task_vote(items) for tid, items in group_by_task(candidate).items()}
    common = sorted(set(base_votes) & set(cand_votes))
    usable = [tid for tid in common if base_votes[tid]["majority_correct"] is not None and cand_votes[tid]["majority_correct"] is not None]
    regressions = [tid for tid in usable if base_votes[tid]["majority_correct"] and not cand_votes[tid]["majority_correct"]]
    improvements = [tid for tid in usable if not base_votes[tid]["majority_correct"] and cand_votes[tid]["majority_correct"]]
    discordant = len(regressions) + len(improvements)
    return {
        "paired_tasks": len(usable),
        "baseline_majority_accuracy": (sum(1 for tid in usable if base_votes[tid]["majority_correct"]) / len(usable)) if usable else None,
        "candidate_majority_accuracy": (sum(1 for tid in usable if cand_votes[tid]["majority_correct"]) / len(usable)) if usable else None,
        "stable_regressions": len(regressions),
        "stable_improvements": len(improvements),
        "mcnemar_exact_p": exact_binomial_two_sided(min(len(regressions), len(improvements)), discordant) if discordant else None,
        "stable_regression_items": [majority_comparison_item(base_votes[tid], cand_votes[tid]) for tid in regressions[:100]],
        "stable_improvement_items": [majority_comparison_item(base_votes[tid], cand_votes[tid]) for tid in improvements[:100]],
    }


def majority_comparison_item(b: dict[str, Any], c: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": b.get("task_id"),
        "domain": b.get("domain"),
        "skill": b.get("skill"),
        "baseline_correct_repeats": b.get("correct_repeats"),
        "baseline_valid_repeats": b.get("valid_repeats"),
        "candidate_correct_repeats": c.get("correct_repeats"),
        "candidate_valid_repeats": c.get("valid_repeats"),
    }


def delta(candidate: float | None, baseline: float | None) -> float | None:
    if candidate is None or baseline is None:
        return None
    return candidate - baseline


def comparison_item(b: dict[str, Any], c: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": b.get("task_id"),
        "repeat": b.get("repeat"),
        "domain": b.get("domain"),
        "skill": b.get("skill"),
        "baseline_answer": b.get("answer"),
        "candidate_answer": c.get("answer"),
        "expected": b.get("expected"),
        "candidate_failure_mode": c.get("failure_mode"),
        "candidate_detail": c.get("grade_detail"),
    }


def markdown_compare(summary: dict[str, Any]) -> str:
    lines = ["# Model Capability Regression Compare", ""]
    if summary.get("warnings"):
        lines += ["## Warnings", ""]
        for warning in summary["warnings"]:
            lines.append(f"- {esc(warning)}")
        lines.append("")
    lines += [
        f"- Paired cases: {summary['paired_cases']}",
        f"- Paired tasks: {summary.get('paired_tasks', '-')}",
        f"- Task overlap rate: {_percent(summary.get('task_overlap_rate'))}",
        f"- Domain mismatches: {summary.get('domain_mismatch_count', 0)}",
        f"- Baseline case accuracy: {_percent(summary['baseline_accuracy'])}",
        f"- Candidate case accuracy: {_percent(summary['candidate_accuracy'])}",
        f"- Delta case accuracy: {fmt_delta(summary['delta_accuracy'])}",
        f"- Baseline majority accuracy: {_percent(summary.get('baseline_majority_accuracy'))}",
        f"- Candidate majority accuracy: {_percent(summary.get('candidate_majority_accuracy'))}",
        f"- Delta majority accuracy: {fmt_delta(summary.get('delta_majority_accuracy'))}",
        f"- Case regressions: {summary['regressions']}",
        f"- Case improvements: {summary['improvements']}",
        f"- Net case regressions: {summary['net_regressions']}",
        f"- Stable task regressions: {summary.get('stable_regressions', 0)}",
        f"- Stable task improvements: {summary.get('stable_improvements', 0)}",
        f"- Net stable task regressions: {summary.get('net_stable_regressions', 0)}",
        f"- McNemar/sign-test exact p-value, cases: {fmt_num(summary['mcnemar_exact_p'])}",
        f"- McNemar/sign-test exact p-value, task majority: {fmt_num(summary.get('mcnemar_exact_p_task_majority'))}",
        "",
        "## By domain",
        "",
        "| domain | n | baseline | candidate | delta | regressions | improvements |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in summary["by_domain"]:
        lines.append(
            f"| {esc(item['domain'])} | {item['n']} | {_percent(item['baseline_accuracy'])} | "
            f"{_percent(item['candidate_accuracy'])} | {fmt_delta(item['delta_accuracy'])} | "
            f"{item['regressions']} | {item['improvements']} |"
        )
    if summary.get("stable_regression_items"):
        lines += ["", "## Stable task regression cases", "", "| task | domain | skill | baseline correct/repeats | candidate correct/repeats |", "|---|---|---|---:|---:|"]
        for r in summary["stable_regression_items"][:100]:
            lines.append(
                f"| {esc(r['task_id'])} | {esc(r['domain'])} | {esc(r['skill'])} | "
                f"{r['baseline_correct_repeats']}/{r['baseline_valid_repeats']} | {r['candidate_correct_repeats']}/{r['candidate_valid_repeats']} |"
            )
    if summary["regression_items"]:
        lines += ["", "## Case-level regression cases", "", "| task | repeat | domain | skill | baseline | candidate | expected | failure mode |", "|---|---:|---|---|---|---|---|---|"]
        for r in summary["regression_items"][:100]:
            lines.append(
                f"| {esc(r['task_id'])} | {r['repeat']} | {esc(r['domain'])} | {esc(r['skill'])} | "
                f"{esc(r['baseline_answer'])} | {esc(r['candidate_answer'])} | {esc(r['expected'])} | {esc(r['candidate_failure_mode'])} |"
            )
    return "\n".join(lines) + "\n"


def fmt_delta(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:+.1f} pp"


def load_results(path: str | Path) -> list[dict[str, Any]]:
    return read_jsonl(path)


def write_json(path: str | Path, data: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
