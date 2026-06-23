from pathlib import Path

from model_regression_eval.runner import (
    build_claude_cli_command,
    build_gemini_cli_command,
    build_opencode_cli_command,
    canonical_runner_name,
    extract_text_from_obj,
    extract_usage_from_obj,
    parse_cli_stdout,
)


def test_runner_aliases():
    assert canonical_runner_name("codex") == "codex_cli"
    assert canonical_runner_name("claude") == "claude_cli"
    assert canonical_runner_name("gemini") == "gemini_cli"
    assert canonical_runner_name("opencode") == "opencode_cli"


def test_claude_cli_command_includes_structured_output_schema(tmp_path):
    schema = tmp_path / "schema.json"
    schema.write_text("{}")
    cmd = build_claude_cli_command(exe="claude", prompt="hello", model="sonnet", schema_path=schema)
    assert cmd[:2] == ["claude", "--bare"]
    assert "-p" in cmd
    assert "--output-format" in cmd and "json" in cmd
    assert "--json-schema" in cmd and str(schema) in cmd


def test_gemini_and_opencode_commands_are_overridable_defaults():
    g = build_gemini_cli_command(exe="gemini", prompt="hello", model="gemini-pro")
    assert g[:3] == ["gemini", "-p", "hello"]
    assert "--output-format" in g
    o = build_opencode_cli_command(exe="opencode", prompt="hello", model="m")
    assert o[:3] == ["opencode", "run", "hello"]


def test_extract_openai_compatible_text_and_usage():
    obj = {
        "choices": [{"message": {"content": '{"answer":"42","confidence":1,"reasoning_summary":"x"}'}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 3},
    }
    assert extract_text_from_obj(obj).startswith('{"answer"')
    u = extract_usage_from_obj(obj)
    assert u.input_tokens == 10
    assert u.output_tokens == 3


def test_extract_gemini_text_and_usage():
    obj = {
        "candidates": [{"content": {"parts": [{"text": '{"answer":"A","confidence":0.8,"reasoning_summary":"x"}'}]}}],
        "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 4, "thoughtsTokenCount": 2},
    }
    assert extract_text_from_obj(obj).startswith('{"answer"')
    u = extract_usage_from_obj(obj)
    assert u.input_tokens == 11
    assert u.output_tokens == 4
    assert u.reasoning_output_tokens == 2


def test_parse_claude_cli_structured_output():
    stdout = '{"structured_output":{"answer":"21","confidence":0.9,"reasoning_summary":"x"},"usage":{"input_tokens":5,"output_tokens":2}}'
    final_text, raw, usage, tool = parse_cli_stdout(stdout, runner_name="claude_cli")
    assert final_text.startswith('{"answer"')
    assert raw is not None
    assert usage.input_tokens == 5
    assert usage.output_tokens == 2
    assert tool is False


def test_parse_cli_stdout_preserves_top_level_final_answer_json():
    stdout = '{"answer":"21","confidence":0.9,"reasoning_summary":"x"}'
    final_text, raw, usage, tool = parse_cli_stdout(stdout, runner_name="subprocess")
    assert final_text.startswith('{"answer"')
    assert '"confidence": 0.9' in final_text
    assert raw == {"answer": "21", "confidence": 0.9, "reasoning_summary": "x"}
    assert usage.input_tokens is None
    assert tool is False
