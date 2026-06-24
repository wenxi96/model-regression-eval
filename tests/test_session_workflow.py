from __future__ import annotations

import json
from pathlib import Path

import pytest

from model_regression_eval.cli import main, mock_answer
from model_regression_eval.reporting import summarize_rows
from model_regression_eval.tasks import load_tasks


def test_export_session_does_not_leak_expected_answers_by_default(tmp_path):
    out = tmp_path / "packet.json"
    code = main([
        "export-session",
        "--tasks",
        "tasks/core.zh.jsonl",
        "--limit",
        "2",
        "--out",
        str(out),
    ])

    assert code == 0
    packet = json.loads(out.read_text(encoding="utf-8"))
    assert packet["packet_type"] == "model_regression_eval.session_packet"
    assert packet["include_answers"] is False
    assert packet["tasks_path"] == "tasks/core.zh.jsonl"
    assert packet["assignment_count"] == 2
    assert "answers" not in packet
    assert all("expected" not in item for item in packet["assignments"])
    assert all("grader" not in item for item in packet["assignments"])
    assert all("allow_tools" in item for item in packet["assignments"])
    assert {"task_id", "repeat", "answer", "confidence", "reasoning_summary"}.issubset(packet["answer_schema"])


def test_export_session_returns_error_for_empty_selection(tmp_path):
    out = tmp_path / "packet.json"
    code = main([
        "export-session",
        "--tasks",
        "tasks/core.zh.jsonl",
        "--tier",
        "frontier",
        "--difficulty",
        "basic",
        "--out",
        str(out),
    ])

    assert code == 1
    assert not out.exists()


def test_export_prompts_legacy_path_does_not_leak_expected_without_flag(tmp_path):
    out = tmp_path / "prompts.jsonl"
    code = main([
        "export-prompts",
        "--tasks",
        "tasks/core.zh.jsonl",
        "--limit",
        "1",
        "--out",
        str(out),
    ])

    assert code == 0
    row = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    assert "expected" not in row
    assert "grader" not in row
    assert "allow_tools" in row

    with_answers = tmp_path / "prompts_with_answers.jsonl"
    code = main([
        "export-prompts",
        "--tasks",
        "tasks/core.zh.jsonl",
        "--limit",
        "1",
        "--include-answers",
        "--out",
        str(with_answers),
    ])

    assert code == 0
    row = json.loads(with_answers.read_text(encoding="utf-8").splitlines()[0])
    assert "expected" in row
    assert "grader" in row


def test_export_prompts_returns_error_for_empty_selection(tmp_path):
    out = tmp_path / "prompts.jsonl"
    code = main([
        "export-prompts",
        "--tasks",
        "tasks/core.zh.jsonl",
        "--tier",
        "frontier",
        "--difficulty",
        "basic",
        "--out",
        str(out),
    ])

    assert code == 1
    assert not out.exists()


def test_import_session_accepts_answers_object_and_writes_results(tmp_path):
    tasks = load_tasks(Path("tasks/core.zh.jsonl"))[:2]
    answers = {
        "answers": [
            {
                "task_id": task.id,
                "repeat": 1,
                "agent_instance": "subagent-1",
                "execution_mode": "subagent",
                "answer": mock_answer(task),
                "confidence": 0.9,
                "reasoning_summary": "matched expected deterministic answer",
            }
            for task in tasks
        ]
    }
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(json.dumps(answers, ensure_ascii=False), encoding="utf-8")

    code = main([
        "import-session",
        "--tasks",
        "tasks/core.zh.jsonl",
        "--answers",
        str(answers_path),
        "--out-dir",
        str(tmp_path / "runs"),
        "--run-id",
        "session_ok",
    ])

    assert code == 0
    rows = [
        json.loads(line)
        for line in (tmp_path / "runs" / "session_ok" / "results.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 2
    assert all(row["correct"] for row in rows)
    assert all(row["execution_mode"] == "subagent" for row in rows)
    assert all(row["agent_instance"] == "subagent-1" for row in rows)
    summary = json.loads((tmp_path / "runs" / "session_ok" / "summary.json").read_text(encoding="utf-8"))
    assert summary["score"] == 1.0
    assert summary["by_difficulty"][0]["difficulty"] == "basic"
    assert summary["by_tier"][0]["tier"] == "baseline"
    assert summary["by_answer_mode"][0]["answer_mode"] == "deterministic"


def test_import_session_rejects_duplicate_task_repeat_agent_instance(tmp_path):
    task = load_tasks(Path("tasks/core.zh.jsonl"))[0]
    answer = {
        "task_id": task.id,
        "repeat": 1,
        "agent_instance": "same-agent",
        "answer": mock_answer(task),
        "confidence": 0.9,
        "reasoning_summary": "x",
    }
    answers_path = tmp_path / "answers.jsonl"
    answers_path.write_text(
        json.dumps(answer, ensure_ascii=False) + "\n" + json.dumps(answer, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="duplicate"):
        main([
            "import-session",
            "--tasks",
            "tasks/core.zh.jsonl",
            "--answers",
            str(answers_path),
            "--out-dir",
            str(tmp_path / "runs"),
            "--run-id",
            "dup",
        ])


def test_import_session_rejects_non_positive_repeat(tmp_path):
    task = load_tasks(Path("tasks/core.zh.jsonl"))[0]
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(
        json.dumps(
            {
                "answers": [
                    {
                        "task_id": task.id,
                        "repeat": 0,
                        "answer": mock_answer(task),
                        "confidence": 0.9,
                        "reasoning_summary": "x",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="repeat must be positive"):
        main([
            "import-session",
            "--tasks",
            "tasks/core.zh.jsonl",
            "--answers",
            str(answers_path),
            "--out-dir",
            str(tmp_path / "runs"),
            "--run-id",
            "bad_repeat",
        ])


def test_import_session_rejects_nan_confidence(tmp_path):
    task = load_tasks(Path("tasks/core.zh.jsonl"))[0]
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(
        json.dumps(
            {
                "answers": [
                    {
                        "task_id": task.id,
                        "repeat": 1,
                        "answer": mock_answer(task),
                        "confidence": "NaN",
                        "reasoning_summary": "x",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="confidence must be between 0 and 1"):
        main([
            "import-session",
            "--tasks",
            "tasks/core.zh.jsonl",
            "--answers",
            str(answers_path),
            "--out-dir",
            str(tmp_path / "runs"),
            "--run-id",
            "bad_confidence",
        ])


def test_import_results_rejects_non_positive_repeat(tmp_path):
    task = load_tasks(Path("tasks/core.zh.jsonl"))[0]
    outputs_path = tmp_path / "outputs.jsonl"
    outputs_path.write_text(
        json.dumps({"task_id": task.id, "repeat": 0, "answer": mock_answer(task)}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="repeat must be positive"):
        main([
            "import-results",
            "--tasks",
            "tasks/core.zh.jsonl",
            "--outputs",
            str(outputs_path),
            "--out-dir",
            str(tmp_path / "runs"),
            "--run-id",
            "bad_legacy_repeat",
        ])


def test_reporting_exposes_score_confidence_and_metadata_groups():
    rows = [
        {
            "task_id": "a",
            "repeat": 1,
            "domain": "math",
            "skill": "s",
            "difficulty": "hard",
            "tier": "frontier",
            "answer_mode": "deterministic",
            "weight": 1,
            "valid": True,
            "correct": True,
            "score": 0.75,
            "confidence": 0.9,
            "format_error": False,
            "tool_violation": False,
        },
        {
            "task_id": "b",
            "repeat": 1,
            "domain": "math",
            "skill": "s",
            "difficulty": "hard",
            "tier": "frontier",
            "answer_mode": "deterministic",
            "weight": 1,
            "valid": True,
            "correct": False,
            "score": 0.25,
            "confidence": 0.95,
            "format_error": False,
            "tool_violation": False,
        },
    ]

    summary = summarize_rows(rows)
    assert summary["score"] == 0.5
    assert summary["weighted_score"] == 0.5
    assert summary["mean_confidence"] == pytest.approx(0.925)
    assert summary["high_confidence_error_rate"] == 0.5
    assert summary["by_difficulty"][0]["difficulty"] == "hard"
    assert summary["by_difficulty"][0]["score"] == 0.5
