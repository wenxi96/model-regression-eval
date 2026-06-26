from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


DIFFICULTY_CHOICES = {"basic", "medium", "hard", "challenge"}
TIER_CHOICES = {"baseline", "challenge", "frontier"}
ANSWER_MODE_CHOICES = {"deterministic", "rubric", "judge"}


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

    @property
    def difficulty(self) -> str:
        return str((self.metadata or {}).get("difficulty", "basic"))

    @property
    def tier(self) -> str:
        return str((self.metadata or {}).get("tier", "baseline"))

    @property
    def answer_mode(self) -> str:
        return str((self.metadata or {}).get("answer_mode", "deterministic"))


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
            metadata = dict(data.get("metadata", {}))
            if "accept" in metadata:
                accept = metadata["accept"]
                if not isinstance(accept, list) or not all(isinstance(item, str) for item in accept):
                    raise ValueError(f"Task {path}:{line_no} metadata.accept must be a list of strings")
            _validate_metadata(path, line_no, metadata)
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
                    metadata=metadata,
                )
            )
    ids = [t.id for t in tasks]
    duplicates = sorted({x for x in ids if ids.count(x) > 1})
    if duplicates:
        raise ValueError(f"Duplicate task ids in {path}: {duplicates}")
    return tasks


def _validate_metadata(path: Path, line_no: int, metadata: dict[str, Any]) -> None:
    difficulty = str(metadata.get("difficulty", "basic"))
    if difficulty not in DIFFICULTY_CHOICES:
        raise ValueError(f"Task {path}:{line_no} metadata.difficulty must be one of {sorted(DIFFICULTY_CHOICES)}")
    tier = str(metadata.get("tier", "baseline"))
    if tier not in TIER_CHOICES:
        raise ValueError(f"Task {path}:{line_no} metadata.tier must be one of {sorted(TIER_CHOICES)}")
    answer_mode = str(metadata.get("answer_mode", "deterministic"))
    if answer_mode not in ANSWER_MODE_CHOICES:
        raise ValueError(f"Task {path}:{line_no} metadata.answer_mode must be one of {sorted(ANSWER_MODE_CHOICES)}")
    if "rubric" in metadata and not isinstance(metadata["rubric"], (str, dict)):
        raise ValueError(f"Task {path}:{line_no} metadata.rubric must be a string or object")
    if "variant_group" in metadata and not isinstance(metadata["variant_group"], str):
        raise ValueError(f"Task {path}:{line_no} metadata.variant_group must be a string")
    if "allow_decimal" in metadata and not isinstance(metadata["allow_decimal"], bool):
        raise ValueError(f"Task {path}:{line_no} metadata.allow_decimal must be a boolean")
    if "accept_parts" in metadata:
        accept_parts = metadata["accept_parts"]
        if not isinstance(accept_parts, list):
            raise ValueError(f"Task {path}:{line_no} metadata.accept_parts must be a list of lists")
        for aliases in accept_parts:
            if aliases is not None and (not isinstance(aliases, list) or not all(isinstance(item, str) for item in aliases)):
                raise ValueError(f"Task {path}:{line_no} metadata.accept_parts must be a list of lists")
    if "require_simplest" in metadata and not isinstance(metadata["require_simplest"], bool):
        raise ValueError(f"Task {path}:{line_no} metadata.require_simplest must be a boolean")


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
