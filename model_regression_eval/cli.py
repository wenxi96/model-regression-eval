from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import random
import sys
from typing import Any

from .budget import markdown_budget, summarize_budget
from .graders import grade
from .profiles import DEPTH_CHOICES, PROFILE_CHOICES, apply_profile, fit_request_budget, resolve_profile_and_repeats, stratified_select
from .reporting import (
    compare_rows,
    load_results,
    markdown_compare,
    markdown_summary,
    summarize_rows,
    write_json,
)
from .skillpacks import CANONICAL_TARGETS, TARGET_SPECS, build_skillpacks, normalize_skill_target
from .installer import detect_system, detect_target, install_from_any_source, uninstall_project, write_bootstrap_script
from .runner import (
    RUNNER_CHOICES,
    canonical_runner_name,
    run_anthropic_api,
    run_claude_cli,
    run_codex,
    run_gemini_api,
    run_gemini_cli,
    run_http_runner,
    run_mock,
    run_opencode_cli,
    run_openai_compatible,
    run_subprocess_runner,
)
from .tasks import EvalTask, append_jsonl, load_tasks, write_jsonl


EFFORTS = ["minimal", "low", "medium", "high", "xhigh"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="model-regression-eval", description="Run and compare model capability regression evaluations.")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run tasks through any supported model/agent runner.")
    run_p.add_argument("--tasks", required=True, help="Path to JSONL task file.")
    run_p.add_argument("--out-dir", default="runs", help="Directory where the run folder is written.")
    run_p.add_argument("--run-id", default=None, help="Run id. Defaults to timestamp_model_effort.")
    run_p.add_argument("--model", default=None, help="Model name for the selected runner. Omit only when the runner has a local default.")
    run_p.add_argument("--effort", default="medium", choices=EFFORTS, help="model_reasoning_effort value.")
    run_p.add_argument("--profile", choices=PROFILE_CHOICES, default=None, help="Coverage profile: smoke=40 tasks, standard=100 tasks, full=all tasks. Legacy deep means full + depth=confirm.")
    run_p.add_argument("--depth", choices=DEPTH_CHOICES, default=None, help="Repeat-depth shortcut: quick=1, confirm=3, deep=5. Overridden by --repeats.")
    run_p.add_argument("--repeats", type=int, default=None, help="Number of repeats per task. Overrides --depth. Default is 1.")
    run_p.add_argument("--max-requests", type=int, default=None, help="Hard cap on model invocations after filtering/profile selection. Requests = tasks * repeats.")
    run_p.add_argument("--max-observed-tokens", type=int, default=None, help="Stop after the current case once observed input+output tokens reaches this budget.")
    run_p.add_argument("--runner", choices=RUNNER_CHOICES, default="codex", help="Execution backend. Aliases: codex=codex_cli, claude=claude_cli, gemini=gemini_cli, opencode=opencode_cli.")
    run_p.add_argument("--schema", default="schemas/final_answer.schema.json", help="JSON schema passed to runners that support structured output.")
    run_p.add_argument("--timeout-s", type=int, default=180, help="Per-case timeout for Codex subprocess.")
    run_p.add_argument("--sandbox", default="read-only", choices=["read-only", "workspace-write", "danger-full-access"], help="Codex sandbox policy.")
    run_p.add_argument("--approval", default="never", help="Codex approval policy, usually never for evals.")
    run_p.add_argument("--no-ignore-user-config", action="store_true", help="Do not pass --ignore-user-config to Codex.")
    run_p.add_argument("--no-ignore-rules", action="store_true", help="Do not pass --ignore-rules to Codex.")
    run_p.add_argument("--extra-config", action="append", default=[], help="Additional -c key=value passed to Codex. Repeatable.")
    run_p.add_argument("--extra-arg", action="append", default=[], help="Additional raw CLI arg for Codex/Claude/Gemini/OpenCode runners. Repeatable.")

    # Generic and non-Codex runner options.
    run_p.add_argument("--agent-url", default=None, help="HTTP endpoint for --runner http, or base URL for API-compatible runners when applicable.")
    run_p.add_argument("--agent-command", default=None, help="Command template for --runner subprocess. Supports {prompt_file}, {schema_path}, {final_out_path}, {model} placeholders and receives prompt on stdin.")
    run_p.add_argument("--agent-api-key", default=None, help="API key for API runners. If omitted, runner-specific environment variables are used.")
    run_p.add_argument("--agent-header", action="append", default=[], help="Extra HTTP header for --runner http, formatted as 'Name: Value'. Repeatable.")
    run_p.add_argument("--limit", type=int, default=None, help="Only run first N tasks after profile/filtering. Prefer --profile or --max-requests for balanced sampling.")
    run_p.add_argument("--task-id", action="append", default=None, help="Run only selected task id. Repeatable.")
    run_p.add_argument("--shuffle", action="store_true", help="Shuffle task order with --seed after selection.")
    run_p.add_argument("--seed", type=int, default=0, help="Stratified selection and shuffle seed.")
    run_p.add_argument("--include-quarantined", action="store_true", help="Include tasks marked status=quarantined.")
    run_p.set_defaults(func=cmd_run)

    budget_p = sub.add_parser("budget", help="Estimate prompt token budget without calling a model.")
    budget_p.add_argument("--tasks", required=True, help="Path to JSONL task file.")
    budget_p.add_argument("--profile", choices=PROFILE_CHOICES, default=None, help="Coverage profile: smoke=40, standard=100, full=all. Legacy deep means full + depth=confirm.")
    budget_p.add_argument("--depth", choices=DEPTH_CHOICES, default=None, help="Repeat-depth shortcut: quick=1, confirm=3, deep=5. Overridden by --repeats.")
    budget_p.add_argument("--repeats", type=int, default=None, help="Repeats to estimate. Overrides --depth. Default is 1.")
    budget_p.add_argument("--max-requests", type=int, default=None, help="Apply a hard request budget to the estimate.")
    budget_p.add_argument("--limit", type=int, default=None, help="Only estimate first N tasks after filtering/profile.")
    budget_p.add_argument("--task-id", action="append", default=None, help="Estimate selected task id. Repeatable.")
    budget_p.add_argument("--seed", type=int, default=0, help="Stratified selection seed.")
    budget_p.add_argument("--include-quarantined", action="store_true", help="Include tasks marked status=quarantined.")
    budget_p.add_argument("--out-md", default=None, help="Optional markdown output path.")
    budget_p.add_argument("--out-json", default=None, help="Optional JSON output path.")
    budget_p.set_defaults(func=cmd_budget)


    exp_p = sub.add_parser("export-prompts", help="Export selected prompts for manual or external agent execution.")
    exp_p.add_argument("--tasks", required=True, help="Path to JSONL task file.")
    exp_p.add_argument("--profile", choices=PROFILE_CHOICES, default=None, help="Coverage profile.")
    exp_p.add_argument("--depth", choices=DEPTH_CHOICES, default=None, help="Repeat-depth shortcut.")
    exp_p.add_argument("--repeats", type=int, default=None, help="Repeats to export. Overrides --depth.")
    exp_p.add_argument("--max-requests", type=int, default=None, help="Apply a hard request budget.")
    exp_p.add_argument("--limit", type=int, default=None, help="Only export first N tasks after profile/filtering.")
    exp_p.add_argument("--task-id", action="append", default=None, help="Export selected task id. Repeatable.")
    exp_p.add_argument("--seed", type=int, default=0, help="Stratified selection seed.")
    exp_p.add_argument("--include-quarantined", action="store_true", help="Include tasks marked status=quarantined.")
    exp_p.add_argument("--out", required=True, help="Output JSONL containing task_id, repeat, prompt, expected, grader.")
    exp_p.set_defaults(func=cmd_export_prompts)

    imp_p = sub.add_parser("import-results", help="Import manual/external agent outputs and grade them.")
    imp_p.add_argument("--tasks", required=True, help="Path to JSONL task file.")
    imp_p.add_argument("--outputs", required=True, help="JSONL with task_id, repeat, and final_text/final_json/answer.")
    imp_p.add_argument("--out-dir", default="runs", help="Directory where the imported run folder is written.")
    imp_p.add_argument("--run-id", required=True, help="Run id for imported results.")
    imp_p.add_argument("--runner-name", default="manual_import", help="Runner label stored in results.")
    imp_p.add_argument("--model", default=None, help="Model/agent label stored in results.")
    imp_p.add_argument("--effort", default="manual", help="Effort label stored in results.")
    imp_p.add_argument("--include-quarantined", action="store_true", help="Include tasks marked status=quarantined.")
    imp_p.set_defaults(func=cmd_import_results)

    sum_p = sub.add_parser("summarize", help="Summarize one results.jsonl file.")
    sum_p.add_argument("--results", required=True, help="Path to results.jsonl.")
    sum_p.add_argument("--out-md", default=None, help="Optional markdown report path.")
    sum_p.add_argument("--out-json", default=None, help="Optional JSON summary path.")
    sum_p.set_defaults(func=cmd_summarize)

    cmp_p = sub.add_parser("compare", help="Compare baseline and candidate result files.")
    cmp_p.add_argument("--baseline", required=True, help="Baseline results.jsonl.")
    cmp_p.add_argument("--candidate", required=True, help="Candidate results.jsonl.")
    cmp_p.add_argument("--out-md", default=None, help="Optional markdown compare report path.")
    cmp_p.add_argument("--out-json", default=None, help="Optional JSON compare summary path.")
    cmp_p.add_argument("--fail-on-regression", action="store_true", help="Exit 2 if regression threshold is exceeded.")
    cmp_p.add_argument("--min-delta-pp", type=float, default=5.0, help="Regression threshold in percentage points.")
    cmp_p.add_argument("--min-net-regressions", type=int, default=3, help="Minimum net regression count for --fail-on-regression.")
    cmp_p.set_defaults(func=cmd_compare)

    skill_p = sub.add_parser("skill", help="Build portable skillpack packages for agent environments.")
    skill_sub = skill_p.add_subparsers(dest="skill_command", required=True)

    skill_list_p = skill_sub.add_parser("list-targets", help="List supported skillpack build targets.")
    skill_list_p.set_defaults(func=cmd_skill_list_targets)

    skill_build_p = skill_sub.add_parser("build", help="Build a portable skillpack package. This only produces packages; it does not install them.")
    skill_build_p.add_argument("--target", required=True, help="Target package such as chatgpt, claude, codex, gemini, windsurf, cursor, cline, copilot, opencode, web-manual, qwen-web, glm-web, ai-ide, generic, or all. Unknown values fall back to generic.")
    skill_build_p.add_argument("--out-dir", default="dist/skillpacks", help="Directory where packages are written.")
    skill_build_p.add_argument("--format", choices=["zip", "directory"], default="zip", help="Output format. Default: zip.")
    skill_build_p.add_argument("--project-root", default=None, help="Project root to package. Defaults to this installed project root.")
    skill_build_p.set_defaults(func=cmd_skill_build)

    skill_detect_p = skill_sub.add_parser("detect", help="Detect the most likely local agent/IDE target and runtime system for this project.")
    skill_detect_p.add_argument("--project-root", default=".", help="Project directory to inspect. Default: current directory.")
    skill_detect_p.add_argument("--json", action="store_true", help="Print JSON only.")
    skill_detect_p.set_defaults(func=cmd_skill_detect)

    skill_install_p = skill_sub.add_parser("install", help="Install this evaluator into a project with safe managed blocks and a local package copy.")
    skill_install_p.add_argument("--target", default="auto", help="Target to install, or auto for detection. Unknown targets fall back to generic.")
    skill_install_p.add_argument("--project-root", default=".", help="Project directory to install into. Default: current directory.")
    skill_install_p.add_argument("--from-url", default=None, help="Install from a source zip URL or JSON install manifest URL.")
    skill_install_p.add_argument("--from-git", default=None, help="Install from a git repository URL.")
    skill_install_p.add_argument("--ref", default=None, help="Git branch/tag/ref for --from-git.")
    skill_install_p.add_argument("--sha256", default=None, help="Expected SHA256 for --from-url.")
    skill_install_p.add_argument("--dry-run", action="store_true", help="Preview actions without writing files.")
    skill_install_p.add_argument("--overwrite", action="store_true", help="Refresh existing managed files/package and replace non-managed dedicated rule files.")
    skill_install_p.add_argument("--no-backup", action="store_true", help="Do not create backups before updating files.")
    skill_install_p.set_defaults(func=cmd_skill_install)

    skill_uninstall_p = skill_sub.add_parser("uninstall", help="Remove files/blocks installed by skill install using the install manifest.")
    skill_uninstall_p.add_argument("--project-root", default=".", help="Project directory to uninstall from. Default: current directory.")
    skill_uninstall_p.add_argument("--dry-run", action="store_true", help="Preview removal without writing files.")
    skill_uninstall_p.set_defaults(func=cmd_skill_uninstall)

    skill_bootstrap_p = skill_sub.add_parser("bootstrap", help="Write a standalone install.sh or install.ps1 bootstrap script.")
    skill_bootstrap_p.add_argument("--platform", choices=["auto", "unix", "windows"], default="auto", help="Bootstrap platform. auto uses the current runtime OS.")
    skill_bootstrap_p.add_argument("--out", required=True, help="Output script path.")
    skill_bootstrap_p.add_argument("--source-url", default=None, help="Source zip URL embedded into the bootstrap script.")
    skill_bootstrap_p.add_argument("--git-url", default=None, help="Git repository URL embedded into the bootstrap script.")
    skill_bootstrap_p.set_defaults(func=cmd_skill_bootstrap)

    args = parser.parse_args(argv)
    return int(args.func(args))


def select_tasks_for_args(args: argparse.Namespace) -> tuple[list[EvalTask], int, dict[str, Any]]:
    tasks = load_tasks(args.tasks, include_quarantined=getattr(args, "include_quarantined", False))
    if args.task_id:
        wanted = set(args.task_id)
        tasks = [t for t in tasks if t.id in wanted]

    resolved_profile, repeats, depth_meta = resolve_profile_and_repeats(
        getattr(args, "profile", None),
        getattr(args, "depth", None),
        getattr(args, "repeats", None),
    )
    tasks = apply_profile(tasks, resolved_profile, seed=getattr(args, "seed", 0))
    if getattr(args, "limit", None) is not None:
        tasks = tasks[: args.limit]
    tasks = fit_request_budget(tasks, repeats, getattr(args, "max_requests", None), seed=getattr(args, "seed", 0))
    return tasks, repeats, depth_meta


def cmd_run(args: argparse.Namespace) -> int:
    try:
        tasks, repeats, depth_meta = select_tasks_for_args(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    args.repeats = repeats
    args.resolved_profile = depth_meta["resolved_profile"]
    args.resolved_depth = depth_meta["resolved_depth"]
    args.requested_runner = args.runner
    args.runner = canonical_runner_name(args.runner)
    if args.shuffle:
        rng = random.Random(args.seed)
        rng.shuffle(tasks)
    if not tasks:
        print("No tasks to run after filters/profile/budget.", file=sys.stderr)
        return 1

    run_id = args.run_id or default_run_id(args.model, args.effort)
    args.run_id = run_id
    out_dir = Path(args.out_dir) / run_id
    raw_dir = out_dir / "raw"
    final_dir = out_dir / "final"
    out_dir.mkdir(parents=True, exist_ok=True)
    schema_path = Path(args.schema)
    if not schema_path.is_absolute():
        if not schema_path.exists():
            candidate = Path(__file__).resolve().parents[1] / schema_path
            if candidate.exists():
                schema_path = candidate

    prompt_wrapper = build_prompt(EvalTask("_", "_", "_", "", "", "exact_string"))
    budget = summarize_budget(tasks, repeats=repeats, wrapper=prompt_wrapper)
    manifest = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "tasks_path": str(Path(args.tasks).resolve()),
        "schema_path": str(schema_path.resolve()) if schema_path.exists() else str(schema_path),
        "model": args.model,
        "effort": args.effort,
        "repeats": repeats,
        "requested_profile": depth_meta["requested_profile"],
        "resolved_profile": depth_meta["resolved_profile"],
        "requested_depth": depth_meta["requested_depth"],
        "resolved_depth": depth_meta["resolved_depth"],
        "repeat_source": depth_meta["repeat_source"],
        "legacy_profile_deep": depth_meta["legacy_profile_deep"],
        "max_requests": args.max_requests,
        "max_observed_tokens": args.max_observed_tokens,
        "requested_runner": getattr(args, "requested_runner", args.runner),
        "runner": args.runner,
        "task_count": len(tasks),
        "request_count": len(tasks) * repeats,
        "estimated_prompt_tokens_with_repeats": budget.estimated_prompt_tokens_with_repeats,
    }
    write_json(out_dir / "manifest.json", manifest)
    (out_dir / "budget.md").write_text(markdown_budget(budget), encoding="utf-8")

    rows: list[dict[str, Any]] = []
    results_path = out_dir / "results.jsonl"
    if results_path.exists():
        results_path.unlink()
    total = len(tasks) * repeats
    case_no = 0
    observed_io_tokens = 0
    stopped_for_token_budget = False
    for repeat in range(1, repeats + 1):
        for task in tasks:
            if stopped_for_token_budget:
                break
            case_no += 1
            print(f"[{case_no}/{total}] {task.id} repeat={repeat}", flush=True)
            raw_path = raw_dir / f"{safe_name(task.id)}__r{repeat}.jsonl"
            final_path = final_dir / f"{safe_name(task.id)}__r{repeat}.json"
            try:
                rr = run_with_selected_runner(
                    args=args,
                    task=task,
                    prompt=build_prompt(task),
                    schema_path=schema_path if schema_path.exists() else None,
                    raw_path=raw_path,
                    final_path=final_path,
                )
                answer = rr.final_json.get("answer") if rr.final_json else None
                gr = grade(task, answer, tool_violation=rr.tool_violation, format_error=rr.format_error)
                valid = rr.returncode == 0
                row = result_row(task, repeat, args, rr, gr, valid, raw_path, final_path)
            except subprocess_like_error() as exc:  # type: ignore[misc]
                row = exception_row(task, repeat, args, exc, raw_path, final_path)
            rows.append(row)
            observed_io_tokens += int(row.get("input_tokens") or 0) + int(row.get("output_tokens") or 0)
            status = "OK" if row.get("correct") else "FAIL"
            print(f"  -> {status} answer={row.get('answer')!r} expected={row.get('expected')!r} mode={row.get('failure_mode')}", flush=True)
            append_jsonl(results_path, row)
            if args.max_observed_tokens is not None and observed_io_tokens >= args.max_observed_tokens:
                stopped_for_token_budget = True
                print(f"Stopped after reaching observed token budget: {observed_io_tokens} >= {args.max_observed_tokens}", flush=True)
                break

    summary = summarize_rows(rows)
    summary["planned_cases"] = total
    summary["stopped_for_token_budget"] = stopped_for_token_budget
    write_json(out_dir / "summary.json", summary)
    (out_dir / "report.md").write_text(markdown_summary("Model Capability Regression Run", summary, rows), encoding="utf-8")
    print(f"\nWrote: {results_path}")
    print(f"Wrote: {out_dir / 'report.md'}")
    print(f"Wrote: {out_dir / 'budget.md'}")
    return 0


def run_with_selected_runner(
    *,
    args: argparse.Namespace,
    task: EvalTask,
    prompt: str,
    schema_path: Path | None,
    raw_path: Path,
    final_path: Path,
):
    runner = args.runner
    if runner == "mock":
        rr = run_mock(task.prompt, answer=mock_answer(task))
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text("", encoding="utf-8")
        final_path.write_text(rr.final_text, encoding="utf-8")
        return rr
    if runner == "codex_cli":
        return run_codex(
            prompt,
            model=args.model,
            effort=args.effort,
            schema_path=schema_path,
            raw_jsonl_path=raw_path,
            final_out_path=final_path,
            timeout_s=args.timeout_s,
            sandbox=args.sandbox,
            approval=args.approval,
            ignore_user_config=not args.no_ignore_user_config,
            ignore_rules=not args.no_ignore_rules,
            extra_config=args.extra_config,
            extra_args=args.extra_arg,
        )
    if runner == "claude_cli":
        return run_claude_cli(
            prompt,
            model=args.model,
            schema_path=schema_path,
            raw_jsonl_path=raw_path,
            final_out_path=final_path,
            timeout_s=args.timeout_s,
            extra_args=args.extra_arg,
        )
    if runner == "gemini_cli":
        return run_gemini_cli(
            prompt,
            model=args.model,
            raw_jsonl_path=raw_path,
            final_out_path=final_path,
            timeout_s=args.timeout_s,
            extra_args=args.extra_arg,
        )
    if runner == "opencode_cli":
        return run_opencode_cli(
            prompt,
            model=args.model,
            raw_jsonl_path=raw_path,
            final_out_path=final_path,
            timeout_s=args.timeout_s,
            extra_args=args.extra_arg,
        )
    if runner == "subprocess":
        return run_subprocess_runner(
            prompt,
            agent_command=args.agent_command,
            model=args.model,
            schema_path=schema_path,
            raw_jsonl_path=raw_path,
            final_out_path=final_path,
            timeout_s=args.timeout_s,
        )
    if runner == "http":
        return run_http_runner(
            prompt,
            agent_url=args.agent_url,
            model=args.model,
            schema_path=schema_path,
            raw_jsonl_path=raw_path,
            final_out_path=final_path,
            timeout_s=args.timeout_s,
            agent_header=args.agent_header,
        )
    if runner == "openai_api":
        return run_openai_compatible(
            prompt,
            base_url=args.agent_url or "https://api.openai.com/v1",
            api_key=args.agent_api_key or __import__("os").environ.get("OPENAI_API_KEY"),
            model=args.model,
            schema_path=schema_path,
            raw_jsonl_path=raw_path,
            final_out_path=final_path,
            timeout_s=args.timeout_s,
            runner_name="openai_api",
        )
    if runner == "openai_compatible":
        return run_openai_compatible(
            prompt,
            base_url=args.agent_url,
            api_key=args.agent_api_key,
            model=args.model,
            schema_path=schema_path,
            raw_jsonl_path=raw_path,
            final_out_path=final_path,
            timeout_s=args.timeout_s,
            runner_name="openai_compatible",
        )
    if runner == "hermes":
        import os
        return run_openai_compatible(
            prompt,
            base_url=args.agent_url or os.environ.get("HERMES_BASE_URL", ""),
            api_key=args.agent_api_key or os.environ.get("HERMES_API_KEY"),
            model=args.model or os.environ.get("HERMES_MODEL", ""),
            schema_path=schema_path,
            raw_jsonl_path=raw_path,
            final_out_path=final_path,
            timeout_s=args.timeout_s,
            runner_name="hermes",
        )
    if runner == "qwen_api":
        import os
        return run_openai_compatible(
            prompt,
            base_url=args.agent_url or os.environ.get("QWEN_BASE_URL", ""),
            api_key=args.agent_api_key or os.environ.get("QWEN_API_KEY"),
            model=args.model or os.environ.get("QWEN_MODEL", ""),
            schema_path=schema_path,
            raw_jsonl_path=raw_path,
            final_out_path=final_path,
            timeout_s=args.timeout_s,
            runner_name="qwen_api",
        )
    if runner == "glm_api":
        import os
        return run_openai_compatible(
            prompt,
            base_url=args.agent_url or os.environ.get("GLM_BASE_URL", ""),
            api_key=args.agent_api_key or os.environ.get("GLM_API_KEY"),
            model=args.model or os.environ.get("GLM_MODEL", ""),
            schema_path=schema_path,
            raw_jsonl_path=raw_path,
            final_out_path=final_path,
            timeout_s=args.timeout_s,
            runner_name="glm_api",
        )
    if runner == "claude_api":
        return run_anthropic_api(
            prompt,
            api_key=args.agent_api_key,
            model=args.model,
            schema_path=schema_path,
            raw_jsonl_path=raw_path,
            final_out_path=final_path,
            timeout_s=args.timeout_s,
            base_url=args.agent_url or "https://api.anthropic.com/v1/messages",
        )
    if runner == "gemini_api":
        return run_gemini_api(
            prompt,
            api_key=args.agent_api_key,
            model=args.model,
            schema_path=schema_path,
            raw_jsonl_path=raw_path,
            final_out_path=final_path,
            timeout_s=args.timeout_s,
            base_url=args.agent_url or "https://generativelanguage.googleapis.com/v1beta",
        )
    raise RuntimeError(f"Unsupported runner: {runner}")


def subprocess_like_error():
    import subprocess

    return (RuntimeError, subprocess.TimeoutExpired, OSError)


def build_prompt(task: EvalTask) -> str:
    return (
        "请独立解题。除非题目明确允许，否则不要使用任何外部工具、命令行、网页搜索或文件读取。\n"
        "最终只输出一个 JSON 对象，不要输出 Markdown、代码块或额外解释。JSON 必须符合：\n"
        '{"answer":"最终答案字符串","confidence":0到1之间的数字,"reasoning_summary":"一句话说明关键依据，不要写详细思维链"}\n\n'
        f"题目：\n{task.prompt}\n"
    )


def mock_answer(task: EvalTask) -> str:
    if isinstance(task.expected, list):
        return ",".join(str(x) for x in task.expected)
    return str(task.expected)


def result_row(task: EvalTask, repeat: int, args: argparse.Namespace, rr: Any, gr: Any, valid: bool, raw_path: Path, final_path: Path) -> dict[str, Any]:
    usage = rr.usage
    return {
        "run_id": args.run_id,
        "task_id": task.id,
        "repeat": repeat,
        "domain": task.domain,
        "skill": task.skill,
        "grader": task.grader,
        "weight": task.weight,
        "allow_tools": task.allow_tools,
        "status": task.status,
        "prompt_hash": task.prompt_hash,
        "model": args.model,
        "effort": args.effort,
        "requested_profile": getattr(args, "profile", None),
        "resolved_profile": getattr(args, "resolved_profile", getattr(args, "profile", None)),
        "requested_depth": getattr(args, "depth", None),
        "resolved_depth": getattr(args, "resolved_depth", None),
        "requested_runner": getattr(args, "requested_runner", args.runner),
        "runner": args.runner,
        "answer": rr.final_json.get("answer") if rr.final_json else None,
        "confidence": rr.final_json.get("confidence") if rr.final_json else None,
        "reasoning_summary": rr.final_json.get("reasoning_summary") if rr.final_json else None,
        "expected": task.expected,
        "correct": bool(gr.correct) and bool(valid),
        "score": gr.score if valid else 0.0,
        "failure_mode": gr.failure_mode,
        "grade_detail": gr.detail,
        "valid": bool(valid),
        "format_error": bool(rr.format_error),
        "tool_violation": bool(rr.tool_violation),
        "tool_violation_unknown": rr.tool_violation is None,
        "returncode": rr.returncode,
        "stderr": rr.stderr,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "reasoning_output_tokens": usage.reasoning_output_tokens,
        "latency_s": rr.latency_s,
        "raw_jsonl_path": str(raw_path),
        "final_json_path": str(final_path),
        "codex_version": rr.codex_version,
        "runner_version": getattr(rr, "runner_version", None),
    }


def exception_row(task: EvalTask, repeat: int, args: argparse.Namespace, exc: BaseException, raw_path: Path, final_path: Path) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "task_id": task.id,
        "repeat": repeat,
        "domain": task.domain,
        "skill": task.skill,
        "grader": task.grader,
        "weight": task.weight,
        "allow_tools": task.allow_tools,
        "status": task.status,
        "prompt_hash": task.prompt_hash,
        "model": args.model,
        "effort": args.effort,
        "requested_profile": getattr(args, "profile", None),
        "resolved_profile": getattr(args, "resolved_profile", getattr(args, "profile", None)),
        "requested_depth": getattr(args, "depth", None),
        "resolved_depth": getattr(args, "resolved_depth", None),
        "requested_runner": getattr(args, "requested_runner", args.runner),
        "runner": args.runner,
        "answer": None,
        "confidence": None,
        "reasoning_summary": None,
        "expected": task.expected,
        "correct": False,
        "score": 0.0,
        "failure_mode": "runtime_error",
        "grade_detail": str(exc),
        "valid": False,
        "format_error": False,
        "tool_violation": False,
        "tool_violation_unknown": True,
        "returncode": None,
        "stderr": str(exc),
        "input_tokens": None,
        "output_tokens": None,
        "reasoning_output_tokens": None,
        "latency_s": None,
        "raw_jsonl_path": str(raw_path),
        "final_json_path": str(final_path),
        "codex_version": None,
        "runner_version": None,
    }


def cmd_export_prompts(args: argparse.Namespace) -> int:
    try:
        tasks, repeats, depth_meta = select_tasks_for_args(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for repeat in range(1, repeats + 1):
        for task in tasks:
            rows.append({
                "task_id": task.id,
                "repeat": repeat,
                "domain": task.domain,
                "skill": task.skill,
                "grader": task.grader,
                "expected": task.expected,
                "prompt": build_prompt(task),
            })
    write_jsonl(out, rows)
    manifest = {
        "tasks": len(tasks),
        "repeats": repeats,
        "requests": len(rows),
        "requested_profile": depth_meta["requested_profile"],
        "resolved_profile": depth_meta["resolved_profile"],
        "requested_depth": depth_meta["requested_depth"],
        "resolved_depth": depth_meta["resolved_depth"],
    }
    write_json(out.with_suffix(out.suffix + ".manifest.json"), manifest)
    print(f"Wrote: {out}")
    print(f"Wrote: {out.with_suffix(out.suffix + '.manifest.json')}")
    return 0


def cmd_import_results(args: argparse.Namespace) -> int:
    tasks = {task.id: task for task in load_tasks(args.tasks, include_quarantined=args.include_quarantined)}
    out_dir = Path(args.out_dir) / args.run_id
    raw_dir = out_dir / "raw"
    final_dir = out_dir / "final"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(Path(args.outputs).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        obj = json.loads(line)
        task_id = obj.get("task_id")
        if task_id not in tasks:
            raise RuntimeError(f"Line {line_no}: unknown task_id {task_id!r}")
        task = tasks[task_id]
        repeat = int(obj.get("repeat") or 1)
        final_obj = obj.get("final_json")
        if final_obj is None and "answer" in obj:
            final_obj = {
                "answer": str(obj.get("answer")),
                "confidence": float(obj.get("confidence", 0.0)),
                "reasoning_summary": str(obj.get("reasoning_summary", "manual import")),
            }
        final_text = obj.get("final_text") or json.dumps(final_obj, ensure_ascii=False)
        from .runner import RunnerResult, Usage, parse_final_json
        parsed, format_error = parse_final_json(final_text)
        raw_path = raw_dir / f"{safe_name(task.id)}__r{repeat}.json"
        final_path = final_dir / f"{safe_name(task.id)}__r{repeat}.json"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        final_path.write_text(final_text, encoding="utf-8")
        rr = RunnerResult(
            final_text=final_text,
            final_json=parsed,
            format_error=format_error,
            raw_events=[],
            usage=Usage(
                input_tokens=obj.get("input_tokens"),
                output_tokens=obj.get("output_tokens"),
                reasoning_output_tokens=obj.get("reasoning_output_tokens"),
            ),
            tool_violation=obj.get("tool_violation"),
            latency_s=float(obj.get("latency_s") or 0.0),
            returncode=0,
            stderr="",
            command=["manual_import"],
            runner_name=args.runner_name,
        )
        answer = rr.final_json.get("answer") if rr.final_json else None
        gr = grade(task, answer, tool_violation=bool(rr.tool_violation), format_error=rr.format_error)
        ns = argparse.Namespace(
            run_id=args.run_id,
            model=args.model,
            effort=args.effort,
            profile=None,
            resolved_profile="manual_import",
            depth=None,
            resolved_depth=None,
            runner=args.runner_name,
            requested_runner=args.runner_name,
        )
        rows.append(result_row(task, repeat, ns, rr, gr, True, raw_path, final_path))
    write_jsonl(out_dir / "results.jsonl", rows)
    summary = summarize_rows(rows)
    write_json(out_dir / "summary.json", summary)
    (out_dir / "report.md").write_text(markdown_summary("Imported Manual/External Agent Run", summary, rows), encoding="utf-8")
    print(f"Wrote: {out_dir / 'results.jsonl'}")
    print(f"Wrote: {out_dir / 'report.md'}")
    return 0


def cmd_budget(args: argparse.Namespace) -> int:
    try:
        tasks, repeats, depth_meta = select_tasks_for_args(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    wrapper = build_prompt(EvalTask("_", "_", "_", "", "", "exact_string"))
    summary = summarize_budget(tasks, repeats=repeats, wrapper=wrapper)
    if args.out_json:
        write_json(args.out_json, summary.to_dict())
    md = markdown_budget(summary)
    if args.out_md:
        Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_md).write_text(md, encoding="utf-8")
    else:
        print(md)
    return 0


def cmd_summarize(args: argparse.Namespace) -> int:
    rows = load_results(args.results)
    summary = summarize_rows(rows)
    if args.out_json:
        write_json(args.out_json, summary)
    md = markdown_summary("Model Capability Regression Run", summary, rows)
    if args.out_md:
        Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_md).write_text(md, encoding="utf-8")
    else:
        print(md)
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    baseline = load_results(args.baseline)
    candidate = load_results(args.candidate)
    summary = compare_rows(baseline, candidate)
    if args.out_json:
        write_json(args.out_json, summary)
    md = markdown_compare(summary)
    if args.out_md:
        Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_md).write_text(md, encoding="utf-8")
    else:
        print(md)
    if args.fail_on_regression:
        delta = summary.get("delta_accuracy")
        net = int(summary.get("net_regressions") or 0)
        if delta is not None and delta <= -(args.min_delta_pp / 100.0) and net >= args.min_net_regressions:
            return 2
    return 0


def cmd_skill_list_targets(args: argparse.Namespace) -> int:
    print("Supported skillpack targets:")
    for target in CANONICAL_TARGETS:
        spec = TARGET_SPECS[target]
        print(f"  - {target:16s} [{spec.support}] {spec.description}")
    print("  - all")
    print("Unknown target names are treated as generic.")
    return 0


def cmd_skill_build(args: argparse.Namespace) -> int:
    target = normalize_skill_target(args.target)
    if target == "generic" and args.target.strip().lower().replace("_", "-") not in {"generic", "universal", "fallback"}:
        print(f"No exact skillpack target for {args.target!r}; building generic compatibility package.")
    built = build_skillpacks(
        target=args.target,
        out_dir=Path(args.out_dir),
        project_root=Path(args.project_root) if args.project_root else None,
        package_format=args.format,
    )
    manifest = {"packages": [b.to_dict() for b in built]}
    out_dir = Path(args.out_dir)
    write_json(out_dir / "skillpacks.manifest.json", manifest)
    for item in built:
        print(f"Built {item.target}: {item.package_path}")
    print(f"Wrote: {out_dir / 'skillpacks.manifest.json'}")
    return 0


def cmd_skill_detect(args: argparse.Namespace) -> int:
    result = detect_target(Path(args.project_root))
    obj = result.to_dict()
    if args.json:
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    else:
        print(f"Detected target: {obj['target']}  confidence={obj['confidence']}")
        for signal in obj["signals"]:
            print(f"  - {signal}")
        system = obj.get("system") or detect_system().to_dict()
        print("Runtime system:")
        print(f"  - os: {system['os']}  platform={system['platform']}  wsl={system['is_wsl']}")
        print(f"  - shell: {system.get('shell') or 'unknown'}")
        print(f"  - recommended launcher: {system['recommended_launcher']}")
        print(f"  - fallback launcher: {system['fallback_launcher']}")
        for note in system.get("notes", []):
            print(f"  - note: {note}")
    return 0


def cmd_skill_install(args: argparse.Namespace) -> int:
    try:
        manifest = install_from_any_source(
            from_url=args.from_url,
            from_git=args.from_git,
            ref=args.ref,
            sha256=args.sha256,
            target=args.target,
            install_root=Path(args.project_root),
            dry_run=args.dry_run,
            overwrite=args.overwrite,
            backup=not args.no_backup,
        )
    except Exception as exc:
        print(f"install failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    if args.dry_run:
        print("Dry-run only; no files were written.")
    else:
        print(f"Installed into: {Path(args.project_root).resolve()}")
    return 0


def cmd_skill_uninstall(args: argparse.Namespace) -> int:
    try:
        manifest = uninstall_project(Path(args.project_root), dry_run=args.dry_run)
    except Exception as exc:
        print(f"uninstall failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    if args.dry_run:
        print("Dry-run only; no files were removed.")
    return 0


def cmd_skill_bootstrap(args: argparse.Namespace) -> int:
    if args.source_url and args.git_url:
        print("choose only one of --source-url or --git-url", file=sys.stderr)
        return 1
    try:
        write_bootstrap_script(args.platform, Path(args.out), source_url=args.source_url, git_url=args.git_url)
    except Exception as exc:
        print(f"bootstrap failed: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote: {Path(args.out)}")
    return 0


def default_run_id(model: str | None, effort: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_part = safe_name(model or "default")
    effort_part = safe_name(effort)
    return f"{stamp}_{model_part}_{effort_part}"


def safe_name(s: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in str(s))


if __name__ == "__main__":
    raise SystemExit(main())
