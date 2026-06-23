from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class EvalTask:
    id: str
    domain: str
    skill: str
    prompt: str
    expected: Any
    grader: str
    weight: float = 1.0
    allow_tools: bool = False
    status: str = "active"
    metadata: dict[str, Any] | None = None

    @property
    def prompt_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.prompt.encode("utf-8")).hexdigest()


def load_tasks(path: str | Path, *, include_quarantined: bool = False) -> list[EvalTask]:
    path = Path(path)
    tasks: list[EvalTask] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on {path}:{line_no}: {exc}") from exc
            status = str(data.get("status", "active"))
            if status == "quarantined" and not include_quarantined:
                continue
            missing = [k for k in ["id", "domain", "skill", "prompt", "expected", "grader"] if k not in data]
            if missing:
                raise ValueError(f"Task {path}:{line_no} missing required fields: {missing}")
            tasks.append(
                EvalTask(
                    id=str(data["id"]),
                    domain=str(data["domain"]),
                    skill=str(data["skill"]),
                    prompt=str(data["prompt"]),
                    expected=data["expected"],
                    grader=str(data["grader"]),
                    weight=float(data.get("weight", 1.0)),
                    allow_tools=bool(data.get("allow_tools", False)),
                    status=status,
                    metadata=dict(data.get("metadata", {})),
                )
            )
    ids = [t.id for t in tasks]
    duplicates = sorted({x for x in ids if ids.count(x) > 1})
    if duplicates:
        raise ValueError(f"Duplicate task ids in {path}: {duplicates}")
    return tasks


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")




def append_jsonl(path: str | Path, row: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on {path}:{line_no}: {exc}") from exc
    return rows
