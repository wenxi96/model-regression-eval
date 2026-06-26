from model_regression_eval.runner import append_codex_auth_hint, parse_final_json, parse_jsonl_events, detect_tool_use, extract_usage


def test_parse_final_json_fenced():
    text = '```json\n{"answer":"21","confidence":0.9,"reasoning_summary":"x"}\n```'
    obj, err = parse_final_json(text)
    assert not err
    assert obj["answer"] == "21"


def test_parse_cli_stdout_preserves_top_level_final_answer_json():
    from model_regression_eval.runner import parse_cli_stdout

    text = '{"answer":"21","confidence":0.9,"reasoning_summary":"x"}'
    final_text, raw_response, usage, tool_violation = parse_cli_stdout(text, runner_name="subprocess")
    obj, err = parse_final_json(final_text)

    assert not err
    assert obj == {"answer": "21", "confidence": 0.9, "reasoning_summary": "x"}
    assert raw_response == {"answer": "21", "confidence": 0.9, "reasoning_summary": "x"}
    assert usage.input_tokens is None
    assert tool_violation is False


def test_detect_tool_use():
    events = [{"type":"item.completed", "item":{"type":"command_execution"}}]
    assert detect_tool_use(events)


def test_extract_usage():
    events = parse_jsonl_events('{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":2,"reasoning_output_tokens":3}}\n')
    u = extract_usage(events)
    assert u.input_tokens == 1
    assert u.output_tokens == 2
    assert u.reasoning_output_tokens == 3

from pathlib import Path
from model_regression_eval.runner import build_codex_command


def test_build_codex_command_uses_stdin_and_isolation_flags(tmp_path):
    cmd = build_codex_command(
        exe='codex',
        model='gpt-5.5',
        effort='high',
        schema_path=Path('schemas/final_answer.schema.json'),
        final_out_path=tmp_path / 'final.json',
    )
    assert cmd[:3] == ['codex', 'exec', '--json']
    assert '--ignore-user-config' in cmd
    assert '--ignore-rules' in cmd
    assert '--output-schema' in cmd
    assert '-o' in cmd
    assert '-a' not in cmd
    assert cmd[-1] == '-'


def test_codex_auth_hint_points_to_local_config_flag():
    hinted = append_codex_auth_hint("401 Unauthorized: invalid API key", ignore_user_config=True)
    assert "--no-ignore-user-config" in hinted
    assert append_codex_auth_hint("401 Unauthorized", ignore_user_config=False) == "401 Unauthorized"


def test_command_version_is_cached(monkeypatch):
    import subprocess
    from model_regression_eval import runner

    runner._COMMAND_VERSION_CACHE.clear()
    calls = []

    class Proc:
        stdout = 'fake 1.0\n'
        stderr = ''

    def fake_run(cmd, capture_output, text, timeout):
        calls.append(cmd)
        return Proc()

    monkeypatch.setattr(subprocess, 'run', fake_run)
    assert runner.command_version('fake-exe', ['--version']) == 'fake 1.0'
    assert runner.command_version('fake-exe', ['--version']) == 'fake 1.0'
    assert len(calls) == 1


def test_command_version_tries_default_fallback_flags(monkeypatch):
    import subprocess
    from model_regression_eval import runner

    runner._COMMAND_VERSION_CACHE.clear()
    calls = []

    class Proc:
        def __init__(self, stdout='', stderr=''):
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(cmd, capture_output, text, timeout):
        calls.append(cmd)
        if cmd[1] == '--version':
            return Proc()
        if cmd[1] == 'version':
            return Proc(stdout='fake version 2.0\n')
        raise AssertionError('unexpected fallback')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    assert runner.command_version('fake-exe') == 'fake version 2.0'
    assert calls == [['fake-exe', '--version'], ['fake-exe', 'version']]
