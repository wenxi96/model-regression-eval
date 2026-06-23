from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
import platform as platform_module
from pathlib import Path
import sys
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from typing import Any

from .skillpacks import (
    RULE_FILE,
    build_skillpacks,
    normalize_skill_target,
    project_root_from_module,
    target_spec,
)

MANAGED_BEGIN = "<!-- BEGIN MODEL_REGRESSION_EVAL -->"
MANAGED_END = "<!-- END MODEL_REGRESSION_EVAL -->"
INSTALL_DIR = ".model-regression-eval"
PACKAGE_DIR = f"{INSTALL_DIR}/package"
MANIFEST_PATH = f"{INSTALL_DIR}/install-manifest.json"


@dataclass(frozen=True)
class SystemDetectResult:
    os: str
    platform: str
    shell: str | None
    is_wsl: bool
    host_os: str | None
    path_style: str
    python: str
    has_git: bool
    has_curl: bool
    has_wget: bool
    recommended_launcher: str
    fallback_launcher: str
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "os": self.os,
            "platform": self.platform,
            "shell": self.shell,
            "is_wsl": self.is_wsl,
            "host_os": self.host_os,
            "path_style": self.path_style,
            "python": self.python,
            "has_git": self.has_git,
            "has_curl": self.has_curl,
            "has_wget": self.has_wget,
            "recommended_launcher": self.recommended_launcher,
            "fallback_launcher": self.fallback_launcher,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class DetectResult:
    target: str
    confidence: str
    signals: tuple[str, ...]
    system: SystemDetectResult | None = None

    def to_dict(self) -> dict[str, Any]:
        obj = {"target": self.target, "confidence": self.confidence, "signals": list(self.signals)}
        if self.system is not None:
            obj["system"] = self.system.to_dict()
        return obj


@dataclass(frozen=True)
class InstallAction:
    kind: str
    path: str
    status: str
    detail: str = ""
    backup: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "path": self.path, "status": self.status, "detail": self.detail, "backup": self.backup}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_proc_version() -> str:
    try:
        return Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
    except Exception:
        return ""


def detect_system() -> SystemDetectResult:
    """Detect the local runtime used by a human terminal or coding agent."""
    sys_platform = sys.platform
    release = platform_module.release().lower()
    proc_version = _read_proc_version()
    env = os.environ
    is_wsl = bool(env.get("WSL_DISTRO_NAME") or env.get("WSL_INTEROP") or "microsoft" in proc_version or "wsl" in release)

    if sys_platform.startswith("win"):
        os_name = "windows"
        path_style = "windows"
        host_os = "windows"
    elif sys_platform == "darwin":
        os_name = "macos"
        path_style = "posix"
        host_os = "macos"
    elif sys_platform.startswith("linux"):
        os_name = "linux"
        path_style = "posix"
        host_os = "windows" if is_wsl else "linux"
    elif sys_platform.startswith("cygwin"):
        os_name = "cygwin"
        path_style = "posix"
        host_os = "windows"
    elif sys_platform.startswith(("msys", "mingw")):
        os_name = "msys"
        path_style = "posix"
        host_os = "windows"
    else:
        os_name = "unknown"
        path_style = "windows" if os.name == "nt" else "posix"
        host_os = None

    shell = (env.get("SHELL") or env.get("COMSPEC") or ("powershell" if env.get("PSModulePath") and os_name == "windows" else None))

    posix_script_launcher = "./.model-regression-eval/package/scripts/mre"
    posix_python = "python3" if shutil.which("python3") else "python"
    posix_python_launcher = f"{posix_python} .model-regression-eval/package/scripts/mre.py"

    if os_name == "windows":
        recommended = r".\.model-regression-eval\package\scripts\mre.bat"
        fallback = r"python .model-regression-eval\package\scripts\mre.py"
    elif is_wsl:
        recommended = posix_script_launcher
        fallback = posix_python_launcher
    else:
        recommended = posix_script_launcher
        fallback = posix_python_launcher

    notes: list[str] = []
    if is_wsl:
        notes.append("WSL detected: use the POSIX launcher inside WSL; if a Windows-side IDE runs outside WSL, install or run from that Windows environment.")
    if os_name == "windows":
        notes.append("Windows detected: PowerShell/cmd examples should use mre.bat or python mre.py.")

    return SystemDetectResult(
        os=os_name,
        platform=sys_platform,
        shell=shell,
        is_wsl=is_wsl,
        host_os=host_os,
        path_style=path_style,
        python=sys.executable,
        has_git=bool(shutil.which("git")),
        has_curl=bool(shutil.which("curl")),
        has_wget=bool(shutil.which("wget")),
        recommended_launcher=recommended,
        fallback_launcher=fallback,
        notes=tuple(notes),
    )


def detect_target(project_root: Path | str = ".", *, include_system: bool = True) -> DetectResult:
    root = Path(project_root).resolve()
    project_signals: list[tuple[str, str, int]] = []
    environment_hints: list[str] = []

    def exists(rel: str, target: str, score: int = 100) -> None:
        if (root / rel).exists():
            project_signals.append((target, rel, score))

    exists(".devin/rules", "windsurf", 120)
    exists(".windsurf/rules", "windsurf", 115)
    exists(".windsurfrules", "windsurf", 110)
    exists(".clinerules", "cline", 115)
    exists(".cursor/rules", "cursor", 110)
    exists(".cursorrules", "cursor", 100)
    exists(".github/copilot-instructions.md", "github-copilot", 110)
    exists(".github/instructions", "github-copilot", 100)
    exists(".roo/rules", "roo-code", 100)
    exists(".roorules", "roo-code", 95)
    exists(".kilocode/rules", "kilo-code", 100)
    exists(".aider.conf.yml", "aider", 100)
    exists(".claude/rules", "claude", 115)
    exists(".claude", "claude", 100)
    exists("CLAUDE.md", "claude", 110)
    exists(".gemini", "gemini", 100)
    exists("GEMINI.md", "gemini", 110)
    exists("OPENCODE.md", "opencode", 100)
    exists("TRAE.md", "trae", 90)
    exists("ZED.md", "zed", 90)
    exists("CONTINUE.md", "continue", 90)
    exists("KIRO.md", "kiro", 90)
    exists("AUGMENT.md", "augment-code", 90)
    exists("WARP.md", "warp", 90)
    exists("AGENTS.md", "generic", 80)

    for exe, target in [("claude", "claude"), ("codex", "codex"), ("gemini", "gemini"), ("opencode", "opencode"), ("aider", "aider")]:
        if shutil.which(exe):
            environment_hints.append(f"cli:{exe} available for explicit --target {target}")

    for var, target in [("HERMES_BASE_URL", "hermes"), ("GEMINI_API_KEY", "gemini"), ("GOOGLE_API_KEY", "gemini"), ("ANTHROPIC_API_KEY", "claude")]:
        if os.environ.get(var):
            environment_hints.append(f"env:{var} available for explicit --target {target}")

    if not project_signals:
        signals = ["no specific agent project files detected; use --target to select a CLI/API target explicitly"]
        signals.extend(environment_hints)
        return DetectResult("generic", "low", tuple(signals), detect_system() if include_system else None)

    scores: dict[str, int] = {}
    sigs: dict[str, list[str]] = {}
    for target, signal, score in project_signals:
        scores[target] = scores.get(target, 0) + score
        sigs.setdefault(target, []).append(signal)
    target = max(scores.items(), key=lambda item: item[1])[0]
    score = scores[target]
    confidence = "high" if score >= 110 else "medium" if score >= 70 else "low"
    return DetectResult(target, confidence, tuple(sigs[target]), detect_system() if include_system else None)


def rule_paths_for_target(target: str) -> list[str]:
    target = normalize_skill_target(target)
    common = ["AGENTS.md"]
    mapping: dict[str, list[str]] = {
        "chatgpt": ["README.md"],
        "claude": ["CLAUDE.md", f".claude/rules/{RULE_FILE}"],
        "codex": ["AGENTS.md"],
        "gemini": ["GEMINI.md"],
        "opencode": ["AGENTS.md", "OPENCODE.md"],
        "hermes": ["HERMES.md", "AGENTS.md"],
        "windsurf": ["AGENTS.md", f".devin/rules/{RULE_FILE}", f".windsurf/rules/{RULE_FILE}", ".windsurfrules"],
        "cline": ["AGENTS.md", f".clinerules/{RULE_FILE}"],
        "github-copilot": ["AGENTS.md", ".github/copilot-instructions.md", ".github/instructions/model-regression-eval.instructions.md"],
        "cursor": ["AGENTS.md", ".cursor/rules/model-regression-eval.mdc", ".cursorrules"],
        "roo-code": ["AGENTS.md", f".roo/rules/{RULE_FILE}", ".roorules"],
        "kilo-code": ["AGENTS.md", f".kilocode/rules/{RULE_FILE}"],
        "zed": ["AGENTS.md", "ZED.md"],
        "aider": ["AGENTS.md", "AIDER.md"],
        "trae": ["AGENTS.md", "TRAE.md", ".trae/README.md"],
        "continue": ["AGENTS.md", "CONTINUE.md", ".continue/README.md"],
        "junie": ["AGENTS.md", "JUNIE.md"],
        "kiro": ["AGENTS.md", "KIRO.md"],
        "augment-code": ["AGENTS.md", "AUGMENT.md"],
        "warp": ["AGENTS.md", "WARP.md"],
        "ai-ide": [
            "AGENTS.md", "CLAUDE.md", "GEMINI.md", "OPENCODE.md", "TRAE.md", "ZED.md", "AIDER.md", "CONTINUE.md", "JUNIE.md", "KIRO.md", "AUGMENT.md", "WARP.md",
            ".github/copilot-instructions.md", ".github/instructions/model-regression-eval.instructions.md", f".devin/rules/{RULE_FILE}", f".windsurf/rules/{RULE_FILE}", f".clinerules/{RULE_FILE}", ".cursor/rules/model-regression-eval.mdc", f".roo/rules/{RULE_FILE}", f".kilocode/rules/{RULE_FILE}",
        ],
        "web-manual": [f"{INSTALL_DIR}/web-manual/WEB_AGENT_INSTRUCTIONS.md", f"{INSTALL_DIR}/web-manual/SYSTEM_PROMPT.md"],
        "qwen-web": [f"{INSTALL_DIR}/web-manual/WEB_AGENT_INSTRUCTIONS.md", f"{INSTALL_DIR}/web-manual/SYSTEM_PROMPT.md"],
        "glm-web": [f"{INSTALL_DIR}/web-manual/WEB_AGENT_INSTRUCTIONS.md", f"{INSTALL_DIR}/web-manual/SYSTEM_PROMPT.md"],
        "kimi-web": [f"{INSTALL_DIR}/web-manual/WEB_AGENT_INSTRUCTIONS.md", f"{INSTALL_DIR}/web-manual/SYSTEM_PROMPT.md"],
        "deepseek-web": [f"{INSTALL_DIR}/web-manual/WEB_AGENT_INSTRUCTIONS.md", f"{INSTALL_DIR}/web-manual/SYSTEM_PROMPT.md"],
        "doubao-web": [f"{INSTALL_DIR}/web-manual/WEB_AGENT_INSTRUCTIONS.md", f"{INSTALL_DIR}/web-manual/SYSTEM_PROMPT.md"],
        "yuanbao-web": [f"{INSTALL_DIR}/web-manual/WEB_AGENT_INSTRUCTIONS.md", f"{INSTALL_DIR}/web-manual/SYSTEM_PROMPT.md"],
        "claude-web": [f"{INSTALL_DIR}/web-manual/WEB_AGENT_INSTRUCTIONS.md", f"{INSTALL_DIR}/web-manual/SYSTEM_PROMPT.md"],
        "gemini-web": [f"{INSTALL_DIR}/web-manual/WEB_AGENT_INSTRUCTIONS.md", f"{INSTALL_DIR}/web-manual/SYSTEM_PROMPT.md"],
        "qwen-api": ["AGENTS.md", "API_PRESET.md"],
        "glm-api": ["AGENTS.md", "API_PRESET.md"],
        "generic": common,
    }
    return mapping.get(target, common)


def _is_whole_managed_file(rel: str) -> bool:
    root_user_files = {"AGENTS.md", "CLAUDE.md", "GEMINI.md", "README.md", "OPENCODE.md", "HERMES.md", "API_PRESET.md", "TRAE.md", "ZED.md", "AIDER.md", "CONTINUE.md", "JUNIE.md", "KIRO.md", "AUGMENT.md", "WARP.md", ".windsurfrules", ".cursorrules", ".roorules"}
    if rel in root_user_files:
        return False
    if rel.startswith(f"{INSTALL_DIR}/"):
        return True
    return True


def _launcher_commands(system: SystemDetectResult) -> dict[str, str]:
    launcher = system.recommended_launcher
    fallback = system.fallback_launcher
    task_path = r"tasks\core.zh.jsonl" if system.path_style == "windows" else "tasks/core.zh.jsonl"
    line_cont = " `\n  " if system.os == "windows" else " \\\n  "
    return {
        "launcher": launcher,
        "fallback": fallback,
        "task_path": task_path,
        "budget": f"{launcher} budget --tasks {task_path} --profile smoke --depth quick",
        "mock": f"{launcher} run --runner mock --tasks {task_path} --profile smoke --depth quick --out-dir runs --run-id selfcheck",
        "compare": f"{launcher} compare --baseline runs/baseline/results.jsonl --candidate runs/candidate/results.jsonl --out-md runs/compare.md --out-json runs/compare.json",
        "codex": f"{launcher} run --runner codex --tasks {task_path} --profile smoke --depth quick --model gpt-5.5",
        "claude": f"{launcher} run --runner claude_cli --tasks {task_path} --profile smoke --depth quick --model claude-sonnet-4-5",
        "gemini": f"{launcher} run --runner gemini_cli --tasks {task_path} --profile smoke --depth quick --model gemini-2.5-pro",
        "http": f"{launcher} run --runner http --tasks {task_path} --profile smoke --depth quick --agent-url http://localhost:8000/eval",
        "export": f"{launcher} export-prompts --tasks {task_path} --profile smoke --out runs/manual_prompts.jsonl",
        "import": f"{launcher} import-results --tasks {task_path} --outputs runs/manual_outputs.jsonl --out-dir runs --run-id manual_agent",
        "line_cont": line_cont,
    }


def install_rule_content(target: str, rel_path: str, *, system: SystemDetectResult | None = None) -> str:
    spec = target_spec(target)
    system = system or detect_system()
    commands = _launcher_commands(system)
    support = spec.support.replace("_", " ")
    web_note = ""
    if spec.support == "manual_web":
        web_note = "\nThis is a web/manual target. Do not claim local installation inside the web product; use export-prompts/import-results."
    elif spec.support == "best_effort":
        web_note = "\nThis is a best-effort IDE target. If this IDE does not load this file, fall back to AGENTS.md or the generic package."
    system_notes = "\n".join(f"- {note}" for note in system.notes) or "- No special runtime notes detected."
    return f"""# Model Regression Eval

Target: `{spec.name}`  
Support level: `{spec.support}` ({support}).{web_note}

Use the project-local evaluator installed at `{PACKAGE_DIR}`. Do not install global dependencies or write API keys into files.

## Runtime detected during installation

- OS: `{system.os}`
- Platform: `{system.platform}`
- Shell: `{system.shell or 'unknown'}`
- WSL: `{system.is_wsl}`
- Recommended launcher: `{commands['launcher']}`
- Cross-platform fallback: `{commands['fallback']}`

{system_notes}

If these commands are being executed by a different environment than the installer used, prefer the fallback launcher:

```bash
{commands['fallback']} --help
```

## Standard workflow

1. Estimate cost first:
   ```bash
   {commands['budget']}
   ```
2. Self-check the local package:
   ```bash
   {commands['mock']}
   ```
3. Start real evaluation with `smoke quick`.
4. Escalate to `standard confirm` only when smoke indicates a plausible issue.
5. Use `full confirm` for final confirmation.
6. Compare baseline and candidate with the compare command.

## Common commands

```bash
{commands['codex']}
{commands['claude']}
{commands['gemini']}
{commands['http']}
{commands['export']}
{commands['import']}
```

Never conclude that a model degraded from one failed task or one `smoke quick` run. Use paired comparison, majority accuracy, consistency, stable regressions, and manual review.
"""

def _wrap_managed_block(content: str) -> str:
    return f"{MANAGED_BEGIN}\n{content.rstrip()}\n{MANAGED_END}\n"


def _replace_managed_block(existing: str, block: str) -> str:
    start = existing.find(MANAGED_BEGIN)
    end = existing.find(MANAGED_END)
    if start != -1 and end != -1 and end > start:
        end += len(MANAGED_END)
        prefix = existing[:start].rstrip()
        suffix = existing[end:].lstrip()
        parts = []
        if prefix:
            parts.append(prefix)
        parts.append(block.rstrip())
        if suffix:
            parts.append(suffix)
        return "\n\n".join(parts) + "\n"
    if existing.strip():
        return existing.rstrip() + "\n\n" + block
    return block


def _backup_file(path: Path, backup_root: Path) -> str | None:
    if not path.exists():
        return None
    rel = path.relative_to(path.anchor).as_posix() if path.is_absolute() else path.as_posix()
    rel = rel.replace(":", "_")
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    dest = backup_root / f"{rel}.{stamp}.bak"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)
    return str(dest)


def _write_managed_file(root: Path, rel: str, content: str, *, dry_run: bool, overwrite: bool, backup: bool, actions: list[InstallAction], backup_root: Path) -> None:
    path = root / rel
    whole_file = _is_whole_managed_file(rel)
    marker_content = _wrap_managed_block(content)
    if dry_run:
        existing = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        status = "would_write" if not path.exists() else "would_update" if overwrite or MANAGED_BEGIN in existing or not whole_file else "would_skip_exists"
        actions.append(InstallAction("managed_file" if whole_file else "managed_block", rel, status))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if whole_file:
        if path.exists():
            existing = path.read_text(encoding="utf-8", errors="replace")
            if MANAGED_BEGIN not in existing and not overwrite:
                actions.append(InstallAction("managed_file", rel, "skipped_exists", "use --overwrite to replace a non-managed file"))
                return
        b = _backup_file(path, backup_root) if backup and path.exists() else None
        path.write_text(marker_content, encoding="utf-8")
        actions.append(InstallAction("managed_file", rel, "updated" if b else "written", backup=b))
        return
    existing = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    b = _backup_file(path, backup_root) if backup and path.exists() else None
    path.write_text(_replace_managed_block(existing, marker_content), encoding="utf-8")
    actions.append(InstallAction("managed_block", rel, "updated" if b else "written", backup=b))


def _copy_package_dir(source_skillpack: Path, project_root: Path, *, dry_run: bool, overwrite: bool, backup: bool, actions: list[InstallAction], backup_root: Path) -> None:
    dest = project_root / PACKAGE_DIR
    if dry_run:
        actions.append(InstallAction("package_dir", PACKAGE_DIR, "would_replace" if dest.exists() else "would_write"))
        return
    if dest.exists():
        if not overwrite:
            actions.append(InstallAction("package_dir", PACKAGE_DIR, "skipped_exists", "use --overwrite to refresh installed package"))
            return
        b = None
        if backup:
            bdir = backup_root / f"package.{datetime.now().strftime('%Y%m%d%H%M%S')}.bak"
            shutil.copytree(dest, bdir)
            b = str(bdir)
        shutil.rmtree(dest)
        shutil.copytree(source_skillpack, dest, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
        actions.append(InstallAction("package_dir", PACKAGE_DIR, "updated", backup=b))
    else:
        shutil.copytree(source_skillpack, dest, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
        actions.append(InstallAction("package_dir", PACKAGE_DIR, "written"))




def _target_from_skillpack(source_dir: Path) -> str | None:
    manifest = source_dir / "skillpack.manifest.json"
    if not manifest.exists():
        return None
    try:
        value = json.loads(manifest.read_text(encoding="utf-8")).get("target")
        return normalize_skill_target(str(value)) if value else None
    except Exception:
        return None

def install_skillpack_directory(*, source_skillpack: Path | str, project_root: Path | str = ".", target: str = "auto", dry_run: bool = False, overwrite: bool = False, backup: bool = True, source: dict[str, Any] | None = None) -> dict[str, Any]:
    root = Path(project_root).resolve()
    source_dir = Path(source_skillpack).resolve()
    if not source_dir.exists() or not source_dir.is_dir():
        raise FileNotFoundError(f"source skillpack directory not found: {source_dir}")
    detected = detect_target(root)
    system = detected.system or detect_system()
    requested_target = target
    package_target = _target_from_skillpack(source_dir)
    if target == "auto":
        # A target-specific skillpack should install as its own target when run directly.
        # This keeps `model-regression-eval-windsurf/install.py --target auto` from
        # degrading to generic in a fresh repository with no existing IDE signals.
        resolved_target = package_target or detected.target
    else:
        resolved_target = normalize_skill_target(target)
    spec = target_spec(resolved_target)
    actions: list[InstallAction] = []
    install_root = root / INSTALL_DIR
    backup_root = install_root / "backups"
    if dry_run:
        actions.append(InstallAction("directory", INSTALL_DIR, "would_ensure"))
    else:
        install_root.mkdir(parents=True, exist_ok=True)
        backup_root.mkdir(parents=True, exist_ok=True)
    _copy_package_dir(source_dir, root, dry_run=dry_run, overwrite=overwrite, backup=backup, actions=actions, backup_root=backup_root)
    for rel in rule_paths_for_target(resolved_target):
        content = install_rule_content(resolved_target, rel, system=system)
        _write_managed_file(root, rel, content, dry_run=dry_run, overwrite=overwrite, backup=backup, actions=actions, backup_root=backup_root)
    manifest = {
        "tool": "model-regression-eval",
        "version": _package_version_from_source(source_dir),
        "installed_at": datetime.now().isoformat(timespec="seconds"),
        "project_root": str(root),
        "requested_target": requested_target,
        "resolved_target": resolved_target,
        "support": spec.support,
        "family": spec.family,
        "detected": detected.to_dict(),
        "system": system.to_dict(),
        "source": source or {"type": "directory", "path": str(source_dir)},
        "dry_run": dry_run,
        "overwrite": overwrite,
        "backup": backup,
        "actions": [a.to_dict() for a in actions],
    }
    if not dry_run:
        (root / MANIFEST_PATH).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _package_version_from_source(source_dir: Path) -> str:
    manifest = source_dir / "skillpack.manifest.json"
    if manifest.exists():
        try:
            return str(json.loads(manifest.read_text(encoding="utf-8")).get("version") or "unknown")
        except Exception:
            return "unknown"
    pyproject = source_dir / "assets" / "eval_project" / "pyproject.toml"
    if pyproject.exists():
        for line in pyproject.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("version"):
                return line.split("=", 1)[1].strip().strip('"')
    return "unknown"


def build_temp_skillpack(target: str, project_root: Path | None = None) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    tmp = tempfile.TemporaryDirectory(prefix="mre_skillpack_")
    built = build_skillpacks(target=target, out_dir=Path(tmp.name), project_root=project_root, package_format="directory")
    return tmp, built[0].package_path


def install_from_project(*, project_root: Path | str, target: str, install_root: Path | str, dry_run: bool, overwrite: bool, backup: bool) -> dict[str, Any]:
    resolved = detect_target(install_root).target if target == "auto" else normalize_skill_target(target)
    tmp, skillpack = build_temp_skillpack(resolved, Path(project_root))
    try:
        return install_skillpack_directory(source_skillpack=skillpack, project_root=install_root, target=target, dry_run=dry_run, overwrite=overwrite, backup=backup, source={"type": "project", "path": str(Path(project_root).resolve())})
    finally:
        tmp.cleanup()


def uninstall_project(project_root: Path | str = ".", *, dry_run: bool = False) -> dict[str, Any]:
    root = Path(project_root).resolve()
    manifest_path = root / MANIFEST_PATH
    if not manifest_path.exists():
        raise FileNotFoundError(f"install manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actions: list[InstallAction] = []
    for item in reversed(manifest.get("actions", [])):
        rel = item.get("path")
        kind = item.get("kind")
        if not rel:
            continue
        path = root / rel
        if kind == "managed_block":
            if not path.exists():
                actions.append(InstallAction(kind, rel, "missing"))
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            start = text.find(MANAGED_BEGIN)
            end = text.find(MANAGED_END)
            if start == -1 or end == -1 or end < start:
                actions.append(InstallAction(kind, rel, "skipped_no_marker"))
                continue
            new_text = (text[:start].rstrip() + "\n\n" + text[end + len(MANAGED_END):].lstrip()).strip()
            if dry_run:
                actions.append(InstallAction(kind, rel, "would_remove_block"))
            else:
                path.write_text((new_text + "\n") if new_text else "", encoding="utf-8")
                actions.append(InstallAction(kind, rel, "removed_block"))
        elif kind in {"managed_file", "package_dir"}:
            if not path.exists():
                actions.append(InstallAction(kind, rel, "missing"))
                continue
            if dry_run:
                actions.append(InstallAction(kind, rel, "would_remove"))
            else:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                actions.append(InstallAction(kind, rel, "removed"))
    if not dry_run:
        manifest_path.unlink(missing_ok=True)
    return {"tool": "model-regression-eval", "project_root": str(root), "dry_run": dry_run, "actions": [a.to_dict() for a in actions]}


def download_url(url: str, dest: Path, *, expected_sha256: str | None = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as resp:
        dest.write_bytes(resp.read())
    if expected_sha256:
        actual = sha256_file(dest)
        if actual.lower() != expected_sha256.lower():
            raise RuntimeError(f"sha256 mismatch for {url}: expected {expected_sha256}, got {actual}")
    return dest


def locate_project_root(path: Path) -> Path:
    if (path / "pyproject.toml").exists() and (path / "model_regression_eval").exists():
        return path
    matches = [p.parent for p in path.rglob("pyproject.toml") if (p.parent / "model_regression_eval").exists()]
    if not matches:
        raise FileNotFoundError(f"could not locate model-regression-eval project root under {path}")
    return matches[0]


def locate_skillpack_root(path: Path) -> Path:
    if (path / "skillpack.manifest.json").exists() and (path / "assets" / "eval_project").exists():
        return path
    matches = [p.parent for p in path.rglob("skillpack.manifest.json") if (p.parent / "assets" / "eval_project").exists()]
    if not matches:
        raise FileNotFoundError(f"could not locate model-regression-eval skillpack root under {path}")
    return matches[0]


def prepare_source_from_url(url: str, work_dir: Path, *, expected_sha256: str | None = None) -> tuple[str, Path, dict[str, Any]]:
    if url.endswith(".json"):
        manifest_path = download_url(url, work_dir / "mre-install.json", expected_sha256=expected_sha256)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        asset = manifest.get("assets", {}).get("source_zip") or manifest.get("source_zip")
        if not asset or not asset.get("url"):
            raise RuntimeError("install manifest does not contain assets.source_zip.url")
        return prepare_source_from_url(asset["url"], work_dir, expected_sha256=asset.get("sha256"))
    archive = download_url(url, work_dir / "source.zip", expected_sha256=expected_sha256)
    if not zipfile.is_zipfile(archive):
        raise RuntimeError("--from-url currently supports .zip archives or JSON manifests pointing to a source_zip")
    extract_dir = work_dir / "source"
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(extract_dir)
    try:
        return "skillpack", locate_skillpack_root(extract_dir), {"type": "url", "url": url, "sha256": sha256_file(archive)}
    except FileNotFoundError:
        return "project", locate_project_root(extract_dir), {"type": "url", "url": url, "sha256": sha256_file(archive)}


def prepare_source_from_git(repo: str, work_dir: Path, *, ref: str | None = None) -> tuple[str, Path, dict[str, Any]]:
    dest = work_dir / "repo"
    cmd = ["git", "clone", "--depth", "1"]
    if ref:
        cmd += ["--branch", ref]
    cmd += [repo, str(dest)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "git clone failed")
    return "project", locate_project_root(dest), {"type": "git", "url": repo, "ref": ref}


def install_from_any_source(*, from_url: str | None = None, from_git: str | None = None, ref: str | None = None, sha256: str | None = None, target: str = "auto", install_root: Path | str = ".", dry_run: bool = False, overwrite: bool = False, backup: bool = True) -> dict[str, Any]:
    if from_url and from_git:
        raise ValueError("choose only one of --from-url or --from-git")
    if from_url or from_git:
        with tempfile.TemporaryDirectory(prefix="mre_install_src_") as td:
            work = Path(td)
            if from_url:
                kind, src, source_meta = prepare_source_from_url(from_url, work, expected_sha256=sha256)
            else:
                kind, src, source_meta = prepare_source_from_git(from_git or "", work, ref=ref)
            if kind == "skillpack":
                return install_skillpack_directory(source_skillpack=src, project_root=install_root, target=target, dry_run=dry_run, overwrite=overwrite, backup=backup, source=source_meta)
            return install_from_project(project_root=src, target=target, install_root=install_root, dry_run=dry_run, overwrite=overwrite, backup=backup)
    return install_from_project(project_root=project_root_from_module(), target=target, install_root=install_root, dry_run=dry_run, overwrite=overwrite, backup=backup)


def write_bootstrap_script(platform: str, out: Path, *, source_url: str | None = None, git_url: str | None = None) -> None:
    platform = platform.lower()
    if platform == "auto":
        platform = "windows" if detect_system().os == "windows" else "unix"
    out.parent.mkdir(parents=True, exist_ok=True)
    if platform in {"unix", "linux", "macos", "posix"}:
        if source_url:
            text = f'''#!/usr/bin/env sh
set -eu
TARGET="${{TARGET:-auto}}"
DRY_RUN="${{DRY_RUN:-1}}"
TMPDIR="$(mktemp -d)"
PROJECT_ROOT="$(pwd -P)"
trap 'rm -rf "$TMPDIR"' EXIT
if command -v python3 >/dev/null 2>&1; then PY=python3; elif command -v python >/dev/null 2>&1; then PY=python; else echo "Python 3 is required" >&2; exit 1; fi
URL="{source_url}"
if command -v curl >/dev/null 2>&1; then curl -fsSL "$URL" -o "$TMPDIR/source.zip"; else wget -O "$TMPDIR/source.zip" "$URL"; fi
"$PY" - "$TMPDIR/source.zip" "$TARGET" "$DRY_RUN" "$PROJECT_ROOT" <<'PYCODE'
import pathlib, subprocess, sys, zipfile
zip_path, target, dry, project_root = sys.argv[1:5]
root = pathlib.Path(zip_path).with_suffix('')
root.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(zip_path) as zf:
    zf.extractall(root)
cands = [p.parent for p in root.rglob('pyproject.toml') if (p.parent/'model_regression_eval').exists()]
if not cands:
    raise SystemExit('could not locate project root in archive')
cmd = [sys.executable, '-m', 'model_regression_eval.cli', 'skill', 'install', '--target', target, '--project-root', project_root]
if dry not in ('0','false','False','no'):
    cmd.append('--dry-run')
subprocess.check_call(cmd, cwd=str(cands[0]))
PYCODE
'''
        elif git_url:
            text = f'''#!/usr/bin/env sh
set -eu
TARGET="${{TARGET:-auto}}"
DRY_RUN="${{DRY_RUN:-1}}"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT
if command -v python3 >/dev/null 2>&1; then PY=python3; elif command -v python >/dev/null 2>&1; then PY=python; else echo "Python 3 is required" >&2; exit 1; fi
PROJECT_ROOT="$(pwd -P)"
git clone --depth 1 "{git_url}" "$TMPDIR/repo"
cd "$TMPDIR/repo"
CMD="$PY -m model_regression_eval.cli skill install --target $TARGET --project-root $PROJECT_ROOT"
if [ "$DRY_RUN" != "0" ]; then CMD="$CMD --dry-run"; fi
sh -c "$CMD"
'''
        else:
            text = '''#!/usr/bin/env sh
set -eu
echo "No source URL or git URL embedded. Clone the repository and run: python -m model_regression_eval.cli skill install --target auto --dry-run" >&2
exit 1
'''
        out.write_text(text, encoding="utf-8")
        out.chmod(out.stat().st_mode | 0o755)
        return
    if platform in {"windows", "powershell", "ps1"}:
        text = f'''param(
  [string]$Target = "auto",
  [switch]$Apply
)
$ErrorActionPreference = "Stop"
$DryRun = -not $Apply
$ProjectRoot = (Get-Location).Path
$Tmp = New-Item -ItemType Directory -Force -Path ([System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), "mre-install-" + [System.Guid]::NewGuid().ToString()))
try {{
  $Url = "{source_url or ''}"
  if (-not $Url) {{ throw "No source URL embedded. Clone the repository and run python -m model_regression_eval.cli skill install." }}
  $Zip = Join-Path $Tmp "source.zip"
  Invoke-WebRequest -Uri $Url -OutFile $Zip
  Expand-Archive -Path $Zip -DestinationPath (Join-Path $Tmp "source") -Force
  $Project = Get-ChildItem -Path (Join-Path $Tmp "source") -Filter pyproject.toml -Recurse | Where-Object {{ Test-Path (Join-Path $_.DirectoryName "model_regression_eval") }} | Select-Object -First 1
  if (-not $Project) {{ throw "could not locate project root in archive" }}
  Push-Location $Project.DirectoryName
  $Args = @("-m", "model_regression_eval.cli", "skill", "install", "--target", $Target, "--project-root", $ProjectRoot)
  if ($DryRun) {{ $Args += "--dry-run" }}
  python @Args
  Pop-Location
}} finally {{
  Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
}}
'''
        out.write_text(text, encoding="utf-8")
        return
    raise ValueError("platform must be unix or windows")


def install_py_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install a generated model-regression-eval skillpack into the current project.")
    parser.add_argument("--target", default="auto")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args(argv)
    source = Path(__file__).resolve().parent
    manifest = install_skillpack_directory(source_skillpack=source, project_root=args.project_root, target=args.target, dry_run=args.dry_run, overwrite=args.overwrite, backup=not args.no_backup)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0
