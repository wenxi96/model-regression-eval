from __future__ import annotations

from dataclasses import dataclass, asdict
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from typing import Any
from urllib import request, error


@dataclass
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_output_tokens: int | None = None


@dataclass
class RunnerResult:
    final_text: str
    final_json: dict[str, Any] | None
    format_error: bool
    raw_events: list[dict[str, Any]]
    usage: Usage
    tool_violation: bool | None
    latency_s: float
    returncode: int
    stderr: str = ""
    command: list[str] | None = None
    runner_name: str | None = None
    runner_version: str | None = None
    codex_version: str | None = None  # Backward-compatible legacy field.
    raw_response: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["usage"] = asdict(self.usage)
        return data


TOOL_TYPE_MARKERS = {
    "command_execution",
    "mcp_tool_call",
    "web_search",
    "file_change",
    "tool_call",
    "tool_calls",
    "function_call",
    "function_calls",
    "exec_command",
    "apply_patch",
    "shell_command",
    "bash",
    "Bash",
}


RUNNER_CHOICES = [
    "mock",
    "codex",
    "codex_cli",
    "claude",
    "claude_cli",
    "claude_api",
    "gemini",
    "gemini_cli",
    "gemini_api",
    "openai_api",
    "openai_compatible",
    "hermes",
    "qwen_api",
    "glm_api",
    "http",
    "subprocess",
    "opencode",
    "opencode_cli",
]


def canonical_runner_name(name: str) -> str:
    aliases = {
        "codex": "codex_cli",
        "claude": "claude_cli",
        "gemini": "gemini_cli",
        "opencode": "opencode_cli",
        "hermes": "hermes",
        "qwen_api": "qwen_api",
        "qwen-api": "qwen_api",
        "glm_api": "glm_api",
        "glm-api": "glm_api",
    }
    return aliases.get(name, name)


def parse_jsonl_events(stdout: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _recursive_contains_tool_marker(value: Any) -> bool:
    if isinstance(value, dict):
        for k, v in value.items():
            if k in {"type", "item_type", "name", "tool_name"} and isinstance(v, str):
                if v in TOOL_TYPE_MARKERS or any(marker in v for marker in TOOL_TYPE_MARKERS):
                    return True
            if k in {"tool_calls", "tools", "function_call"} and v:
                return True
            if _recursive_contains_tool_marker(v):
                return True
    elif isinstance(value, list):
        return any(_recursive_contains_tool_marker(x) for x in value)
    elif isinstance(value, str):
        return value in TOOL_TYPE_MARKERS
    return False


def detect_tool_use(events: list[dict[str, Any]] | dict[str, Any] | None) -> bool:
    if not events:
        return False
    if isinstance(events, dict):
        return _recursive_contains_tool_marker(events)
    return any(_recursive_contains_tool_marker(event) for event in events)


def extract_usage(events: list[dict[str, Any]]) -> Usage:
    usage: dict[str, Any] = {}
    for event in events:
        event_type = event.get("type", "")
        if event_type in {"turn.completed", "turn_completed"}:
            usage = event.get("usage") or usage
    return Usage(
        input_tokens=_safe_int(usage.get("input_tokens")),
        output_tokens=_safe_int(usage.get("output_tokens")),
        reasoning_output_tokens=_safe_int(usage.get("reasoning_output_tokens")),
    )


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _first_int(*values: Any) -> int | None:
    for value in values:
        parsed = _safe_int(value)
        if parsed is not None:
            return parsed
    return None


def extract_final_text(events: list[dict[str, Any]]) -> str:
    final_text = ""
    for event in events:
        if event.get("type") in {"item.completed", "item_completed"}:
            item = event.get("item", {})
            if isinstance(item, dict) and item.get("type") in {"agent_message", "message"}:
                text = item.get("text") or item.get("content") or final_text
                if isinstance(text, list):
                    text = "".join(str(x.get("text", x)) if isinstance(x, dict) else str(x) for x in text)
                final_text = str(text)
    return final_text


def parse_final_json(text: str) -> tuple[dict[str, Any] | None, bool]:
    text = text.strip()
    if not text:
        return None, True
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                obj = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None, True
        else:
            return None, True
    if not isinstance(obj, dict):
        return None, True
    required = {"answer", "confidence", "reasoning_summary"}
    if not required.issubset(obj):
        return obj, True
    if not isinstance(obj.get("answer"), str):
        return obj, True
    if not isinstance(obj.get("reasoning_summary"), str):
        return obj, True
    try:
        confidence = float(obj.get("confidence"))
    except Exception:
        return obj, True
    if not (0.0 <= confidence <= 1.0):
        return obj, True
    obj["confidence"] = confidence
    return obj, False


def load_schema(schema_path: str | Path | None) -> dict[str, Any] | None:
    if not schema_path:
        return None
    path = Path(schema_path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_raw(path: str | Path, text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", errors="replace")


def write_final(path: str | Path, text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", errors="replace")


_COMMAND_VERSION_CACHE: dict[tuple[str, tuple[str, ...] | None], str | None] = {}


def command_version(exe: str, args: list[str] | tuple[str, ...] | None = None) -> str | None:
    cache_key = (exe, tuple(args) if args is not None else None)
    if cache_key in _COMMAND_VERSION_CACHE:
        return _COMMAND_VERSION_CACHE[cache_key]

    result: str | None = None
    candidates = [list(args)] if args is not None else [["--version"], ["version"], ["-v"]]
    for candidate_args in candidates:
        try:
            proc = subprocess.run([exe, *candidate_args], capture_output=True, text=True, timeout=10)
        except FileNotFoundError:
            result = None
            break
        except Exception:
            result = None
            continue
        out = (proc.stdout or proc.stderr or "").strip()
        if out:
            result = out
            break
    _COMMAND_VERSION_CACHE[cache_key] = result
    return result


def codex_version(exe: str) -> str | None:
    return command_version(exe, ["--version"])


def build_codex_command(
    *,
    exe: str,
    model: str | None,
    effort: str,
    schema_path: Path | None,
    final_out_path: Path | None,
    sandbox: str = "read-only",
    approval: str = "never",
    ignore_user_config: bool = True,
    ignore_rules: bool = True,
    extra_config: list[str] | None = None,
    extra_args: list[str] | None = None,
) -> list[str]:
    cmd = [
        exe,
        "exec",
        "--json",
        "--skip-git-repo-check",
        "--ephemeral",
        "-a",
        approval,
        "-s",
        sandbox,
        "-c",
        f"model_reasoning_effort={effort}",
    ]
    if ignore_user_config:
        cmd.append("--ignore-user-config")
    if ignore_rules:
        cmd.append("--ignore-rules")
    if model:
        cmd += ["-m", model]
    if schema_path is not None:
        cmd += ["--output-schema", str(schema_path)]
    if final_out_path is not None:
        cmd += ["-o", str(final_out_path)]
    for item in extra_config or []:
        cmd += ["-c", item]
    cmd += extra_args or []
    cmd.append("-")
    return cmd


def build_claude_cli_command(
    *,
    exe: str,
    prompt: str,
    model: str | None,
    schema_path: Path | None,
    extra_args: list[str] | None = None,
    bare: bool = True,
) -> list[str]:
    cmd = [exe]
    if bare:
        cmd.append("--bare")
    cmd += ["-p", prompt, "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    if schema_path is not None:
        cmd += ["--json-schema", str(schema_path)]
    cmd += extra_args or []
    return cmd


def build_gemini_cli_command(
    *,
    exe: str,
    prompt: str,
    model: str | None,
    extra_args: list[str] | None = None,
) -> list[str]:
    cmd = [exe, "-p", prompt]
    if model:
        cmd += ["--model", model]
    # The documented flag is useful when present; if a local Gemini CLI version lacks it,
    # users can override with --agent-command or pass --extra-arg values.
    cmd += ["--output-format", "json"]
    cmd += extra_args or []
    return cmd


def build_opencode_cli_command(
    *,
    exe: str,
    prompt: str,
    model: str | None,
    extra_args: list[str] | None = None,
) -> list[str]:
    # opencode CLI versions have changed their non-interactive entrypoints over time.
    # The default is conservative and easy to override with --agent-command.
    cmd = [exe, "run", prompt]
    if model:
        cmd += ["--model", model]
    cmd += extra_args or []
    return cmd


def _run_subprocess_command(
    *,
    cmd: list[str],
    prompt: str | None,
    raw_jsonl_path: str | Path,
    final_out_path: str | Path,
    timeout_s: int,
    runner_name: str,
    env: dict[str, str] | None = None,
    input_to_stdin: bool = True,
) -> RunnerResult:
    start = time.perf_counter()
    proc = subprocess.run(
        cmd,
        input=prompt if input_to_stdin else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
        env=env or os.environ.copy(),
    )
    latency_s = time.perf_counter() - start
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    write_raw(raw_jsonl_path, stdout)
    final_text, raw_response, usage, tool_violation = parse_cli_stdout(stdout, runner_name=runner_name)
    if not final_text:
        final_text = stdout.strip()
    write_final(final_out_path, final_text)
    final_json, format_error = parse_final_json(final_text)
    return RunnerResult(
        final_text=final_text,
        final_json=final_json,
        format_error=format_error,
        raw_events=parse_jsonl_events(stdout),
        usage=usage,
        tool_violation=tool_violation,
        latency_s=latency_s,
        returncode=proc.returncode,
        stderr=stderr.strip(),
        command=cmd,
        runner_name=runner_name,
        runner_version=command_version(cmd[0]) if cmd else None,
        codex_version=codex_version(cmd[0]) if runner_name == "codex_cli" and cmd else None,
        raw_response=raw_response,
    )


def parse_cli_stdout(stdout: str, *, runner_name: str) -> tuple[str, dict[str, Any] | None, Usage, bool | None]:
    text = stdout.strip()
    if not text:
        return "", None, Usage(), False
    events = parse_jsonl_events(text)
    if events and any(isinstance(event, dict) and "type" in event for event in events):
        final_text = extract_final_text(events) or ""
        usage = extract_usage(events)
        return final_text, {"events": events}, usage, detect_tool_use(events)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return text, None, Usage(), None
    parsed_final, format_error = parse_final_json(text)
    if parsed_final is not None and not format_error:
        final_text = json.dumps(parsed_final, ensure_ascii=False)
        return final_text, obj, extract_usage_from_obj(obj, runner_name=runner_name), detect_tool_use(obj)
    final_text = extract_text_from_obj(obj, runner_name=runner_name)
    usage = extract_usage_from_obj(obj, runner_name=runner_name)
    tool = detect_tool_use(obj)
    return final_text, obj, usage, tool


def extract_text_from_obj(obj: Any, *, runner_name: str = "generic") -> str:
    if isinstance(obj, str):
        return obj
    if not isinstance(obj, dict):
        return json.dumps(obj, ensure_ascii=False)
    for key in ("structured_output", "final_json"):
        if key in obj:
            value = obj[key]
            return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    if "choices" in obj and isinstance(obj["choices"], list) and obj["choices"]:
        choice = obj["choices"][0]
        if isinstance(choice, dict):
            return extract_text_from_obj(choice.get("message") or choice.get("text") or choice, runner_name=runner_name)
    if "candidates" in obj and isinstance(obj["candidates"], list) and obj["candidates"]:
        return extract_text_from_obj(obj["candidates"][0], runner_name=runner_name)
    if "content" in obj and isinstance(obj["content"], dict):
        return extract_text_from_obj(obj["content"], runner_name=runner_name)
    if "parts" in obj and isinstance(obj["parts"], list):
        return "".join(str(p.get("text", "")) if isinstance(p, dict) else str(p) for p in obj["parts"])
    for key in ("output", "result", "text", "message", "content", "answer"):
        if key in obj:
            value = obj[key]
            if isinstance(value, dict):
                return extract_text_from_obj(value, runner_name=runner_name)
            if isinstance(value, list):
                return "".join(extract_text_from_obj(x, runner_name=runner_name) for x in value)
            return str(value)
    return json.dumps(obj, ensure_ascii=False)


def extract_usage_from_obj(obj: Any, *, runner_name: str = "generic") -> Usage:
    if not isinstance(obj, dict):
        return Usage()
    usage = obj.get("usage") or obj.get("usage_metadata") or obj.get("usageMetadata") or obj.get("metadata", {}).get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    return Usage(
        input_tokens=_first_int(
            usage.get("input_tokens"),
            usage.get("prompt_tokens"),
            usage.get("promptTokenCount"),
            usage.get("inputTokens"),
        ),
        output_tokens=_first_int(
            usage.get("output_tokens"),
            usage.get("completion_tokens"),
            usage.get("candidatesTokenCount"),
            usage.get("outputTokens"),
        ),
        reasoning_output_tokens=_first_int(
            usage.get("reasoning_output_tokens"),
            usage.get("reasoning_tokens"),
            usage.get("thoughtsTokenCount"),
            usage.get("thoughts_tokens"),
        ),
    )


def run_codex(
    prompt: str,
    *,
    model: str | None,
    effort: str,
    schema_path: str | Path | None,
    raw_jsonl_path: str | Path,
    final_out_path: str | Path,
    timeout_s: int = 180,
    sandbox: str = "read-only",
    approval: str = "never",
    ignore_user_config: bool = True,
    ignore_rules: bool = True,
    extra_config: list[str] | None = None,
    extra_args: list[str] | None = None,
) -> RunnerResult:
    exe = shutil.which("codex")
    if not exe:
        raise RuntimeError("Cannot find codex executable. Install Codex CLI and ensure it is on PATH, or run with --runner mock.")
    raw_jsonl_path = Path(raw_jsonl_path)
    final_out_path = Path(final_out_path)
    raw_jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    final_out_path.parent.mkdir(parents=True, exist_ok=True)
    if final_out_path.exists():
        final_out_path.unlink()
    cmd = build_codex_command(
        exe=exe,
        model=model,
        effort=effort,
        schema_path=Path(schema_path) if schema_path else None,
        final_out_path=final_out_path,
        sandbox=sandbox,
        approval=approval,
        ignore_user_config=ignore_user_config,
        ignore_rules=ignore_rules,
        extra_config=extra_config,
        extra_args=extra_args,
    )
    env = os.environ.copy()
    env.setdefault("NO_COLOR", "1")
    rr = _run_subprocess_command(
        cmd=cmd,
        prompt=prompt,
        raw_jsonl_path=raw_jsonl_path,
        final_out_path=final_out_path,
        timeout_s=timeout_s,
        runner_name="codex_cli",
        env=env,
        input_to_stdin=True,
    )
    # Codex may write the schema-constrained final message to -o; prefer that file.
    if final_out_path.exists():
        file_text = final_out_path.read_text(encoding="utf-8", errors="replace").strip()
        if file_text:
            final_json, format_error = parse_final_json(file_text)
            rr.final_text = file_text
            rr.final_json = final_json
            rr.format_error = format_error
    rr.usage = extract_usage(rr.raw_events)
    rr.tool_violation = detect_tool_use(rr.raw_events)
    rr.codex_version = codex_version(exe)
    rr.runner_version = rr.codex_version
    return rr


def run_claude_cli(
    prompt: str,
    *,
    model: str | None,
    schema_path: str | Path | None,
    raw_jsonl_path: str | Path,
    final_out_path: str | Path,
    timeout_s: int = 180,
    extra_args: list[str] | None = None,
) -> RunnerResult:
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError("Cannot find claude executable. Install Claude Code CLI or use --runner claude_api/http/subprocess.")
    cmd = build_claude_cli_command(
        exe=exe,
        prompt=prompt,
        model=model,
        schema_path=Path(schema_path) if schema_path else None,
        extra_args=extra_args,
    )
    env = os.environ.copy()
    env.setdefault("NO_COLOR", "1")
    return _run_subprocess_command(
        cmd=cmd,
        prompt=None,
        raw_jsonl_path=raw_jsonl_path,
        final_out_path=final_out_path,
        timeout_s=timeout_s,
        runner_name="claude_cli",
        env=env,
        input_to_stdin=False,
    )


def run_gemini_cli(
    prompt: str,
    *,
    model: str | None,
    raw_jsonl_path: str | Path,
    final_out_path: str | Path,
    timeout_s: int = 180,
    extra_args: list[str] | None = None,
) -> RunnerResult:
    exe = shutil.which("gemini")
    if not exe:
        raise RuntimeError("Cannot find gemini executable. Install Gemini CLI or use --runner gemini_api/http/subprocess.")
    cmd = build_gemini_cli_command(exe=exe, prompt=prompt, model=model, extra_args=extra_args)
    return _run_subprocess_command(
        cmd=cmd,
        prompt=None,
        raw_jsonl_path=raw_jsonl_path,
        final_out_path=final_out_path,
        timeout_s=timeout_s,
        runner_name="gemini_cli",
        input_to_stdin=False,
    )


def run_opencode_cli(
    prompt: str,
    *,
    model: str | None,
    raw_jsonl_path: str | Path,
    final_out_path: str | Path,
    timeout_s: int = 180,
    extra_args: list[str] | None = None,
) -> RunnerResult:
    exe = shutil.which("opencode")
    if not exe:
        raise RuntimeError("Cannot find opencode executable. Install opencode or use --runner subprocess with --agent-command.")
    cmd = build_opencode_cli_command(exe=exe, prompt=prompt, model=model, extra_args=extra_args)
    return _run_subprocess_command(
        cmd=cmd,
        prompt=None,
        raw_jsonl_path=raw_jsonl_path,
        final_out_path=final_out_path,
        timeout_s=timeout_s,
        runner_name="opencode_cli",
        input_to_stdin=False,
    )


def run_subprocess_runner(
    prompt: str,
    *,
    agent_command: str,
    model: str | None,
    schema_path: str | Path | None,
    raw_jsonl_path: str | Path,
    final_out_path: str | Path,
    timeout_s: int = 180,
) -> RunnerResult:
    if not agent_command:
        raise RuntimeError("--agent-command is required for --runner subprocess.")
    with tempfile.TemporaryDirectory(prefix="mre_agent_") as tmp:
        prompt_file = Path(tmp) / "prompt.txt"
        prompt_file.write_text(prompt, encoding="utf-8")
        fmt = {
            "prompt_file": str(prompt_file),
            "schema_path": str(schema_path or ""),
            "final_out_path": str(final_out_path),
            "model": model or "",
        }
        cmd = [part.format(**fmt) for part in shlex.split(agent_command)]
        return _run_subprocess_command(
            cmd=cmd,
            prompt=prompt,
            raw_jsonl_path=raw_jsonl_path,
            final_out_path=final_out_path,
            timeout_s=timeout_s,
            runner_name="subprocess",
            input_to_stdin=True,
        )


def _http_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout_s: int) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(url, data=data, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"HTTP response was not JSON: {raw[:500]}") from exc


def _runner_result_from_response(
    *,
    obj: dict[str, Any],
    raw_jsonl_path: str | Path,
    final_out_path: str | Path,
    latency_s: float,
    runner_name: str,
    command: list[str] | None = None,
) -> RunnerResult:
    raw_text = json.dumps(obj, ensure_ascii=False, indent=2)
    write_raw(raw_jsonl_path, raw_text)
    final_text = extract_text_from_obj(obj, runner_name=runner_name)
    write_final(final_out_path, final_text)
    final_json, format_error = parse_final_json(final_text)
    return RunnerResult(
        final_text=final_text,
        final_json=final_json,
        format_error=format_error,
        raw_events=[],
        usage=extract_usage_from_obj(obj, runner_name=runner_name),
        tool_violation=detect_tool_use(obj),
        latency_s=latency_s,
        returncode=0,
        stderr="",
        command=command,
        runner_name=runner_name,
        runner_version=None,
        raw_response=obj,
    )


def run_http_runner(
    prompt: str,
    *,
    agent_url: str,
    model: str | None,
    schema_path: str | Path | None,
    raw_jsonl_path: str | Path,
    final_out_path: str | Path,
    timeout_s: int = 180,
    agent_header: list[str] | None = None,
) -> RunnerResult:
    if not agent_url:
        raise RuntimeError("--agent-url is required for --runner http.")
    schema = load_schema(schema_path)
    payload = {"prompt": prompt, "model": model, "schema": schema}
    headers = {"Content-Type": "application/json"}
    for item in agent_header or []:
        if ":" not in item:
            raise RuntimeError("--agent-header must be in 'Name: Value' format.")
        k, v = item.split(":", 1)
        headers[k.strip()] = v.strip()
    start = time.perf_counter()
    obj = _http_json(agent_url, payload, headers, timeout_s)
    latency_s = time.perf_counter() - start
    return _runner_result_from_response(
        obj=obj,
        raw_jsonl_path=raw_jsonl_path,
        final_out_path=final_out_path,
        latency_s=latency_s,
        runner_name="http",
        command=["POST", agent_url],
    )


def run_openai_compatible(
    prompt: str,
    *,
    base_url: str,
    api_key: str | None,
    model: str,
    schema_path: str | Path | None,
    raw_jsonl_path: str | Path,
    final_out_path: str | Path,
    timeout_s: int = 180,
    runner_name: str = "openai_compatible",
) -> RunnerResult:
    if not base_url:
        raise RuntimeError("A base URL is required for OpenAI-compatible runners.")
    if not model:
        raise RuntimeError("--model is required for OpenAI-compatible runners.")
    url = base_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"
    schema = load_schema(schema_path)
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }
    if schema:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "eval_final_answer", "schema": schema, "strict": True},
        }
    else:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    start = time.perf_counter()
    obj = _http_json(url, payload, headers, timeout_s)
    latency_s = time.perf_counter() - start
    return _runner_result_from_response(
        obj=obj,
        raw_jsonl_path=raw_jsonl_path,
        final_out_path=final_out_path,
        latency_s=latency_s,
        runner_name=runner_name,
        command=["POST", url],
    )


def run_anthropic_api(
    prompt: str,
    *,
    api_key: str | None,
    model: str,
    schema_path: str | Path | None,
    raw_jsonl_path: str | Path,
    final_out_path: str | Path,
    timeout_s: int = 180,
    base_url: str = "https://api.anthropic.com/v1/messages",
) -> RunnerResult:
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY or --agent-api-key is required for --runner claude_api.")
    if not model:
        raise RuntimeError("--model is required for --runner claude_api.")
    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }
    schema = load_schema(schema_path)
    if schema:
        payload["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": os.environ.get("ANTHROPIC_VERSION", "2023-06-01"),
    }
    start = time.perf_counter()
    obj = _http_json(base_url, payload, headers, timeout_s)
    latency_s = time.perf_counter() - start
    return _runner_result_from_response(
        obj=obj,
        raw_jsonl_path=raw_jsonl_path,
        final_out_path=final_out_path,
        latency_s=latency_s,
        runner_name="claude_api",
        command=["POST", base_url],
    )


def run_gemini_api(
    prompt: str,
    *,
    api_key: str | None,
    model: str,
    schema_path: str | Path | None,
    raw_jsonl_path: str | Path,
    final_out_path: str | Path,
    timeout_s: int = 180,
    base_url: str = "https://generativelanguage.googleapis.com/v1beta",
) -> RunnerResult:
    api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY/GOOGLE_API_KEY or --agent-api-key is required for --runner gemini_api.")
    if not model:
        raise RuntimeError("--model is required for --runner gemini_api.")
    url = f"{base_url.rstrip('/')}/models/{model}:generateContent?key={api_key}"
    generation_config: dict[str, Any] = {"temperature": 0, "responseMimeType": "application/json"}
    schema = load_schema(schema_path)
    if schema:
        generation_config["responseSchema"] = schema
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": generation_config}
    headers = {"Content-Type": "application/json"}
    start = time.perf_counter()
    obj = _http_json(url, payload, headers, timeout_s)
    latency_s = time.perf_counter() - start
    return _runner_result_from_response(
        obj=obj,
        raw_jsonl_path=raw_jsonl_path,
        final_out_path=final_out_path,
        latency_s=latency_s,
        runner_name="gemini_api",
        command=["POST", f"{base_url.rstrip('/')}/models/{model}:generateContent"],
    )


def run_mock(prompt: str, *, answer: str, delay_s: float = 0.0) -> RunnerResult:
    start = time.perf_counter()
    if delay_s > 0:
        time.sleep(delay_s)
    final_json = {"answer": str(answer), "confidence": 1.0, "reasoning_summary": "mock runner returned the task expected answer"}
    final_text = json.dumps(final_json, ensure_ascii=False)
    latency_s = time.perf_counter() - start
    return RunnerResult(
        final_text=final_text,
        final_json=final_json,
        format_error=False,
        raw_events=[],
        usage=Usage(input_tokens=None, output_tokens=None, reasoning_output_tokens=None),
        tool_violation=False,
        latency_s=latency_s,
        returncode=0,
        stderr="",
        command=["mock"],
        runner_name="mock",
        runner_version=None,
        codex_version=None,
    )
