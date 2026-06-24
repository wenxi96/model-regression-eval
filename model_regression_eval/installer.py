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
SKILL_INSTALL_NAME = "model-regression-eval"
DEFAULT_SKILLS_DIR = "~/.agents/skills"
SKILL_INSTALL_MANIFEST = ".install-manifest.json"


@dataclass(frozen=True)
class SkillDirPreset:
    name: str
    aliases: tuple[str, ...]
    path_template: str
    scope: str
    support: str
    source: str
    description: str

    def to_dict(self, project_root: Path | str = ".") -> dict[str, Any]:
        path = _path_from_skill_dir_template(self.path_template, Path(project_root).resolve())
        return {
            "name": self.name,
            "preset": self.name,
            "aliases": list(self.aliases),
            "path": _display_path(path),
            "scope": self.scope,
            "support": self.support,
            "source": self.source,
            "description": self.description,
        }


SKILL_DIR_PRESETS: dict[str, SkillDirPreset] = {
    "agents": SkillDirPreset(
        "agents",
        ("default", "global", "codex", "codex-user", "codex-cli", "cursor-global", "cursor-user"),
        DEFAULT_SKILLS_DIR,
        "global",
        "default",
        "Codex user skills docs; Cursor user skills docs; model-regression-eval convention",
        "Default shared user skills directory for agents that support the Agent Skills layout.",
    ),
    "project-agents": SkillDirPreset(
        "project-agents",
        ("project", "workspace", "agents-project"),
        "{project_root}/.agents/skills",
        "project",
        "confirmed",
        "Codex repo skills docs; Cursor skills docs",
        "Project-local .agents skills directory.",
    ),
    "cursor-project": SkillDirPreset(
        "cursor-project",
        ("cursor", "cursor-workspace"),
        "{project_root}/.cursor/skills",
        "project",
        "confirmed",
        "Cursor skills docs",
        "Cursor project skills directory.",
    ),
    "cline-project": SkillDirPreset(
        "cline-project",
        ("cline", "cline-workspace"),
        "{project_root}/.cline/skills",
        "project",
        "confirmed",
        "Cline skills docs",
        "Cline workspace skills directory.",
    ),
    "clinerules-project": SkillDirPreset(
        "clinerules-project",
        ("clinerules", "cline-rules", "cline-rules-project"),
        "{project_root}/.clinerules/skills",
        "project",
        "confirmed",
        "Cline skills docs",
        "Cline legacy workspace skills directory.",
    ),
    "cline-global": SkillDirPreset(
        "cline-global",
        ("cline-user",),
        "~/.cline/skills",
        "global",
        "confirmed",
        "Cline skills docs",
        "Cline global skills directory.",
    ),
    "claude-project": SkillDirPreset(
        "claude-project",
        ("claude", "claude-workspace"),
        "{project_root}/.claude/skills",
        "project",
        "confirmed",
        "Claude Code skills docs",
        "Claude Code project skills directory.",
    ),
    "claude-global": SkillDirPreset(
        "claude-global",
        ("claude-user",),
        "~/.claude/skills",
        "global",
        "confirmed",
        "Claude Code skills docs",
        "Claude Code global user skills directory.",
    ),
}

SKILL_DIR_ALIASES: dict[str, str] = {}
for _name, _preset in SKILL_DIR_PRESETS.items():
    SKILL_DIR_ALIASES[_name] = _name
    for _alias in _preset.aliases:
        SKILL_DIR_ALIASES[_alias] = _name

TARGET_SKILL_DIR_PRESETS: dict[str, str] = {
    "claude": "claude-global",
    "cline": "cline-global",
    "cursor": "cursor-project",
}


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


def _path_from_skill_dir_template(template: str, project_root: Path) -> Path:
    if template.startswith("{project_root}/"):
        return project_root / template.removeprefix("{project_root}/")
    return Path(template).expanduser()


def _display_path(path: Path) -> str:
    home = Path.home()
    shown = path.expanduser()
    if not shown.is_absolute():
        shown = Path.cwd() / shown
    try:
        rel = shown.absolute().relative_to(home.resolve())
        return "~" if rel.as_posix() == "." else f"~/{rel.as_posix()}"
    except Exception:
        return str(shown)


def _windows_user_home_from_mount_path(path: Path) -> Path | None:
    parts = path.resolve().parts if path.is_absolute() else path.absolute().parts
    if len(parts) >= 5 and parts[1] == "mnt" and len(parts[2]) == 1 and parts[3].lower() == "users":
        return Path("/", *parts[1:5])
    return None


def resolve_global_skills_dir(global_skills_dir: Path | str | None = None, *, project_root: Path | str | None = None) -> Path:
    if global_skills_dir is None and project_root is not None:
        windows_home = _windows_user_home_from_mount_path(Path(project_root))
        if windows_home is not None:
            return (windows_home / ".agents" / "skills").resolve()
    raw = Path(global_skills_dir).expanduser() if global_skills_dir is not None else Path(DEFAULT_SKILLS_DIR).expanduser()
    return raw.resolve()


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except Exception:
        return left.absolute() == right.absolute()


def _same_path_entry(left: Path, right: Path) -> bool:
    return left.absolute() == right.absolute()


def _path_present(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _is_windows_platform() -> bool:
    return os.name == "nt" or sys.platform.startswith(("win", "cygwin", "msys", "mingw"))


def _is_wsl_windows_mount_path(path: Path) -> bool:
    parts = path.resolve().parts if path.is_absolute() else path.absolute().parts
    return len(parts) >= 3 and parts[1] == "mnt" and len(parts[2]) == 1 and parts[2].isalpha()


def _wsl_to_windows_path(path: Path) -> str:
    try:
        proc = subprocess.run(["wslpath", "-w", str(path)], capture_output=True, text=True)
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except Exception:
        pass
    resolved = path.resolve()
    parts = resolved.parts
    if len(parts) >= 3 and parts[1] == "mnt" and len(parts[2]) == 1:
        drive = parts[2].upper()
        rest = "\\".join(parts[3:])
        return f"{drive}:\\{rest}" if rest else f"{drive}:\\"
    return str(path)


def _create_windows_junction(dest: Path, target: Path) -> str:
    dest_on_windows_mount = _is_wsl_windows_mount_path(dest)
    dest_arg = _wsl_to_windows_path(dest) if dest_on_windows_mount else str(dest)
    target_arg = _wsl_to_windows_path(target) if dest_on_windows_mount or _is_wsl_windows_mount_path(target) else str(target)
    proc = subprocess.run(
        ["cmd.exe" if shutil.which("cmd.exe") else "cmd", "/c", "mklink", "/J", dest_arg, target_arg],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise OSError(f"failed to create Windows junction for {dest}: {detail}")
    return "junction"


def _create_directory_link(dest: Path, target: Path) -> str:
    if _is_wsl_windows_mount_path(dest):
        return _create_windows_junction(dest, target)
    try:
        dest.symlink_to(target, target_is_directory=True)
        return "symlink"
    except OSError as exc:
        if not _is_windows_platform():
            raise
        try:
            return _create_windows_junction(dest, target)
        except Exception as junction_exc:
            raise exc from junction_exc


def normalize_skill_dir_preset(preset: str | None) -> str:
    key = (preset or "agents").strip().lower().replace("_", "-")
    if key not in SKILL_DIR_ALIASES:
        allowed = ", ".join(sorted(SKILL_DIR_PRESETS))
        raise ValueError(f"unknown skill dir preset {preset!r}; choose one of: {allowed}, or pass --skills-dir")
    return SKILL_DIR_ALIASES[key]


def default_skill_dir_preset_for_target(target: str | None) -> str:
    return TARGET_SKILL_DIR_PRESETS.get(normalize_skill_target(target or "generic"), "agents")


def skill_dir_presets(project_root: Path | str = ".") -> list[dict[str, Any]]:
    return [preset.to_dict(project_root) for preset in SKILL_DIR_PRESETS.values()]


def resolve_skills_dir(
    *,
    skills_dir: Path | str | None = None,
    preset: str | None = "agents",
    project_root: Path | str = ".",
) -> tuple[Path, dict[str, Any]]:
    root = Path(project_root).resolve()
    if skills_dir is not None:
        raw = Path(skills_dir).expanduser()
        path = raw if raw.is_absolute() else root / raw
        resolved = path.resolve()
        return resolved, {
            "preset": None,
            "path": _display_path(resolved),
            "scope": "custom",
            "support": "custom",
            "source": "user supplied --skills-dir",
            "description": "Custom skills root supplied by the user or calling agent.",
        }
    name = normalize_skill_dir_preset(preset)
    spec = SKILL_DIR_PRESETS[name]
    path = _path_from_skill_dir_template(spec.path_template, root).resolve()
    data = spec.to_dict(root)
    data["path"] = _display_path(path)
    return path, data


def resolve_link_skills_dir(
    *,
    skills_dir: Path | str | None,
    preset: str | None,
    project_root: Path | str,
    global_skills_dir: Path,
) -> tuple[Path, dict[str, Any]]:
    if skills_dir is None and normalize_skill_dir_preset(preset) == "agents":
        return global_skills_dir, {
            "preset": "agents",
            "path": _display_path(global_skills_dir),
            "scope": "global",
            "support": "default",
            "source": "canonical global skills directory",
            "description": "Canonical global copy; no symlink is needed.",
        }
    return resolve_skills_dir(skills_dir=skills_dir, preset=preset, project_root=project_root)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def resolve_link_skills_dirs(
    *,
    skills_dir: Any,
    preset: Any,
    project_root: Path | str,
    global_skills_dir: Path,
    default_preset: str,
) -> list[tuple[Path, dict[str, Any]]]:
    raw_dirs = _as_list(skills_dir)
    raw_presets = _as_list(preset)
    items: list[tuple[Path, dict[str, Any]]] = []
    if not raw_dirs and not raw_presets:
        items.append(resolve_link_skills_dir(skills_dir=None, preset=default_preset, project_root=project_root, global_skills_dir=global_skills_dir))
    for item in raw_dirs:
        items.append(resolve_skills_dir(skills_dir=item, preset=None, project_root=project_root))
    for item in raw_presets:
        items.append(resolve_link_skills_dir(skills_dir=None, preset=item, project_root=project_root, global_skills_dir=global_skills_dir))

    unique: list[tuple[Path, dict[str, Any]]] = []
    for path, meta in items:
        if any(_same_path(path, existing) for existing, _ in unique):
            continue
        unique.append((path, meta))
    return unique


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
    exists(".cursor/skills", "cursor", 115)
    exists(".clinerules", "cline", 115)
    exists(".cline/skills", "cline", 115)
    exists(".cursor/rules", "cursor", 110)
    exists(".cursorrules", "cursor", 100)
    exists(".github/copilot-instructions.md", "github-copilot", 110)
    exists(".github/instructions", "github-copilot", 100)
    exists(".roo/rules", "roo-code", 100)
    exists(".roorules", "roo-code", 95)
    exists(".kilocode/rules", "kilo-code", 100)
    exists(".aider.conf.yml", "aider", 100)
    exists(".codex/skills", "codex", 105)
    exists(".claude/rules", "claude", 115)
    exists(".claude/skills", "claude", 115)
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
        "export_session": f"{launcher} export-session --tasks {task_path} --profile smoke --depth quick --out runs/session_packet.json",
        "import_session": f"{launcher} import-session --tasks {task_path} --answers runs/session_answers.json --out-dir runs --run-id session_agent",
        "line_cont": line_cont,
    }


def install_rule_content(target: str, rel_path: str, *, system: SystemDetectResult | None = None) -> str:
    spec = target_spec(target)
    system = system or detect_system()
    commands = _launcher_commands(system)
    support = spec.support.replace("_", " ")
    web_note = ""
    if spec.support == "manual_web":
        web_note = "\nThis is a web/manual target. Do not claim local installation inside the web product; use session packets and import-session in a local evaluator environment."
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

## Standard conversation workflow

1. Create a no-answer-leak session packet:
   ```bash
   {commands['export_session']}
   ```
2. Ask the current Agent to answer the packet. If the host supports subagents, each subagent must use the same provider and model as the main session.
3. Import the returned answer set:
   ```bash
   {commands['import_session']}
   ```
4. Escalate to `standard confirm` only when smoke indicates a plausible issue, using independent subagents or fresh sessions.
5. Compare baseline and candidate with the compare command.

Use `--tier frontier --difficulty hard` with `export-session` to select the first hard/frontier capability-ceiling subset.

## Installation self-check only

Self-check the local package when needed:
   ```bash
   {commands['mock']}
   ```
This uses `mock`, which returns the expected answer for each task. Treat it only as an installation, task-loading, and grading self-check.

## Common commands

```bash
{commands['budget']}
{commands['export_session']}
{commands['import_session']}
```

Direct runner commands such as `codex`, `claude_cli`, `gemini_cli`, `http`, and `subprocess` are advanced automation paths for CI/API harnesses. Do not use them as the default skill evaluation path unless explicitly requested.

Never conclude that a model degraded from one failed task or one `smoke quick` run. Use paired comparison, majority accuracy, consistency, stable regressions, and manual review.
Never use `mock` results as model or agent capability evidence.
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


def _is_yaml_frontmatter_content(content: str) -> bool:
    return content.startswith("---\n") or content.startswith("---\r\n")


def _write_managed_file(root: Path, rel: str, content: str, *, dry_run: bool, overwrite: bool, backup: bool, actions: list[InstallAction], backup_root: Path) -> None:
    path = root / rel
    whole_file = _is_whole_managed_file(rel)
    # YAML frontmatter files (SKILL.md) must be written raw — managed markers
    # would break the leading --- line required by frontmatter parsers.
    use_raw = _is_yaml_frontmatter_content(content)
    marker_content = content if use_raw else _wrap_managed_block(content)
    kind = "managed_file" if (whole_file or use_raw) else "managed_block"
    if dry_run:
        existing = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        status = "would_write" if not path.exists() else "would_update" if overwrite or MANAGED_BEGIN in existing or not (whole_file or use_raw) else "would_skip_exists"
        actions.append(InstallAction(kind, rel, status))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if whole_file or use_raw:
        if path.exists() and not use_raw:
            existing = path.read_text(encoding="utf-8", errors="replace")
            if MANAGED_BEGIN not in existing and not overwrite:
                actions.append(InstallAction(kind, rel, "skipped_exists", "use --overwrite to replace a non-managed file"))
                return
        elif path.exists() and use_raw and not overwrite:
            actions.append(InstallAction(kind, rel, "skipped_exists", "use --overwrite to replace the existing skill file"))
            return
        b = _backup_file(path, backup_root) if backup and path.exists() else None
        path.write_text(marker_content, encoding="utf-8")
        actions.append(InstallAction(kind, rel, "updated" if b else "written", backup=b))
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




def _installed_skill_metadata(path: Path) -> dict[str, str | None]:
    out: dict[str, str | None] = {"version": None, "target": None}
    for rel in ("skillpack.manifest.json", SKILL_INSTALL_MANIFEST):
        candidate = path / rel
        if not candidate.exists():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
            if out["version"] is None and data.get("version"):
                out["version"] = str(data.get("version"))
            if out["target"] is None and (data.get("target") or data.get("resolved_target")):
                out["target"] = normalize_skill_target(str(data.get("target") or data.get("resolved_target")))
        except Exception:
            continue
    return out


def _installed_skill_version(path: Path) -> str | None:
    return _installed_skill_metadata(path)["version"]


def _remove_existing_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)


def _backup_existing_path(path: Path, backup_root: Path, backup_name: str) -> str:
    backup_root.mkdir(parents=True, exist_ok=True)
    dest = backup_root / backup_name
    if path.is_symlink() or path.is_file():
        shutil.copy2(path, dest, follow_symlinks=False)
    else:
        shutil.copytree(path, dest)
    return str(dest)


def _install_global_skill_dir(source_skillpack: Path, global_skills_dir: Path, *, skill_name: str, version: str, source_target: str | None, dry_run: bool, overwrite: bool, backup: bool, actions: list[InstallAction]) -> Path:
    dest = global_skills_dir / skill_name
    action_path = _display_path(dest)
    if not (source_skillpack / "SKILL.md").exists():
        raise FileNotFoundError(f"source skillpack does not contain SKILL.md: {source_skillpack}")
    dest_present = _path_present(dest)
    existing_meta = _installed_skill_metadata(dest) if dest_present and not dest.is_symlink() else {"version": None, "target": None}
    existing_version = existing_meta["version"]
    existing_target = existing_meta["target"]
    if dry_run:
        if dest.is_symlink():
            status = "would_fail_invalid_existing"
            detail = "canonical global skill path is a symlink; use --overwrite to replace it with a directory copy"
        elif dest_present and not (dest / "SKILL.md").exists():
            status = "would_fail_invalid_existing"
            detail = "existing global skill path has no SKILL.md"
        elif dest_present and existing_version == version:
            status = "would_validate_current"
            detail = f"version {version} already installed"
            if existing_target and source_target and existing_target != source_target:
                detail += f"; reusing canonical copy installed for {existing_target} with requested target {source_target}"
        elif dest_present and existing_version != version:
            status = "would_update_version_mismatch" if overwrite else "would_fail_version_mismatch"
            detail = f"installed={existing_version or 'unknown'} source={version}"
        else:
            status = "would_write"
            detail = f"version {version}"
        actions.append(InstallAction("global_skill_dir", action_path, status, detail))
        return dest
    global_skills_dir.mkdir(parents=True, exist_ok=True)
    if dest_present:
        if dest.is_symlink():
            actions.append(InstallAction("global_skill_dir", action_path, "invalid_existing", "canonical global skill path is a symlink; use --overwrite to replace it with a directory copy"))
            if not overwrite:
                raise RuntimeError(f"canonical global skill path is a symlink: {dest}; use --overwrite to replace it with a directory copy")
        elif not (dest / "SKILL.md").exists():
            actions.append(InstallAction("global_skill_dir", action_path, "invalid_existing", "existing global skill path has no SKILL.md"))
            if not overwrite:
                raise RuntimeError(f"existing global skill path is not a valid skill: {dest}")
        elif existing_version == version and not overwrite:
            detail = f"version {version} already installed"
            if existing_target and source_target and existing_target != source_target:
                detail += f"; reusing canonical copy installed for {existing_target} with requested target {source_target}"
            actions.append(InstallAction("global_skill_dir", action_path, "validated_current", detail))
            return dest
        elif existing_version != version and not overwrite:
            actions.append(InstallAction("global_skill_dir", action_path, "version_mismatch", f"installed={existing_version or 'unknown'} source={version}; use --overwrite to update"))
            raise RuntimeError(f"global skill version mismatch at {dest}: installed={existing_version or 'unknown'} source={version}; use --overwrite to update")
        if not overwrite:
            actions.append(InstallAction("global_skill_dir", action_path, "skipped_exists", "use --overwrite to replace the existing skill directory"))
            return dest
        b = None
        if backup:
            backup_root = global_skills_dir / ".backups"
            b = _backup_existing_path(dest, backup_root, f"{skill_name}.{datetime.now().strftime('%Y%m%d%H%M%S')}.bak")
        _remove_existing_path(dest)
        shutil.copytree(source_skillpack, dest, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
        actions.append(InstallAction("global_skill_dir", action_path, "updated", f"version {version}", backup=b))
        return dest
    shutil.copytree(source_skillpack, dest, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
    actions.append(InstallAction("global_skill_dir", action_path, "written", f"version {version}"))
    return dest


def _link_skill_dir(global_skill_path: Path, link_skills_dir: Path, *, skill_name: str, dry_run: bool, overwrite: bool, backup: bool, actions: list[InstallAction]) -> Path:
    dest = link_skills_dir / skill_name
    action_path = _display_path(dest)
    if _same_path_entry(dest, global_skill_path):
        actions.append(InstallAction("skill_link", action_path, "not_needed", "link target is the canonical global skill path"))
        return dest
    if dry_run:
        if dest.is_symlink():
            try:
                current = dest.resolve()
            except Exception:
                current = Path(os.readlink(dest))
            status = "would_validate_link" if _same_path(current, global_skill_path) else "would_replace_link" if overwrite else "would_fail_link_mismatch"
            detail = f"target={_display_path(global_skill_path)}"
        elif dest.exists():
            if _same_path(dest, global_skill_path):
                status = "would_validate_link"
                detail = f"target={_display_path(global_skill_path)}"
            else:
                status = "would_replace_existing" if overwrite else "would_fail_exists"
                detail = "existing path is not the expected symlink or junction"
        else:
            status = "would_link"
            detail = f"target={_display_path(global_skill_path)}"
        actions.append(InstallAction("skill_link", action_path, status, detail))
        return dest
    link_skills_dir.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink():
        if _same_path(dest.resolve(), global_skill_path):
            actions.append(InstallAction("skill_link", action_path, "validated_link", f"target={_display_path(global_skill_path)}"))
            return dest
        if not overwrite:
            actions.append(InstallAction("skill_link", action_path, "link_mismatch", f"target={_display_path(global_skill_path)}; use --overwrite to relink"))
            raise RuntimeError(f"skill link points elsewhere: {dest}; use --overwrite to relink")
        dest.unlink()
    elif dest.exists():
        if _same_path(dest, global_skill_path):
            actions.append(InstallAction("skill_link", action_path, "validated_link", f"target={_display_path(global_skill_path)}"))
            return dest
        if not overwrite:
            actions.append(InstallAction("skill_link", action_path, "skipped_exists", "existing path is not a symlink or junction; use --overwrite to replace it"))
            raise RuntimeError(f"skill link destination already exists and is not a symlink or junction: {dest}")
        b = None
        if backup:
            backup_root = link_skills_dir / ".backups"
            b = _backup_existing_path(dest, backup_root, f"{skill_name}.{datetime.now().strftime('%Y%m%d%H%M%S')}.bak")
        _remove_existing_path(dest)
        actions.append(InstallAction("skill_link", action_path, "removed_existing_for_relink", backup=b))
    link_kind = _create_directory_link(dest, global_skill_path)
    actions.append(InstallAction("skill_link", action_path, "linked", f"{link_kind}={_display_path(global_skill_path)}"))
    return dest


def install_skill_directory(
    *,
    source_skillpack: Path | str,
    global_skills_dir: Path | str | None = None,
    skills_dir: Any = None,
    skill_dir_preset: Any = None,
    project_root: Path | str = ".",
    target: str = "auto",
    dry_run: bool = False,
    overwrite: bool = False,
    backup: bool = True,
    skill_name: str = SKILL_INSTALL_NAME,
    source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_dir = Path(source_skillpack).resolve()
    if not source_dir.exists() or not source_dir.is_dir():
        raise FileNotFoundError(f"source skillpack directory not found: {source_dir}")
    root = Path(project_root).resolve()
    requested_target = target
    package_target = _target_from_skillpack(source_dir)
    detected = detect_target(root)
    resolved_target = _resolve_install_target(target, package_target, detected.target)
    link_preset = default_skill_dir_preset_for_target(resolved_target)
    resolved_global_skills_dir = resolve_global_skills_dir(global_skills_dir, project_root=root)
    link_specs = resolve_link_skills_dirs(
        skills_dir=skills_dir,
        preset=skill_dir_preset,
        project_root=root,
        global_skills_dir=resolved_global_skills_dir,
        default_preset=link_preset,
    )
    spec = target_spec(resolved_target)
    version = _package_version_from_source(source_dir)
    actions: list[InstallAction] = []
    global_dest = _install_global_skill_dir(
        source_dir,
        resolved_global_skills_dir,
        skill_name=skill_name,
        version=version,
        source_target=package_target or resolved_target,
        dry_run=dry_run,
        overwrite=overwrite,
        backup=backup,
        actions=actions,
    )
    link_results: list[dict[str, Any]] = []
    for resolved_link_skills_dir, dir_meta in link_specs:
        link_dest = _link_skill_dir(
            global_dest,
            resolved_link_skills_dir,
            skill_name=skill_name,
            dry_run=dry_run,
            overwrite=overwrite,
            backup=backup,
            actions=actions,
        )
        link_results.append(
            {
                "skills_dir": str(resolved_link_skills_dir),
                "skill_path": str(link_dest),
                "skill_dir": dir_meta,
            }
        )
    primary_link = link_results[0]
    manifest = {
        "tool": "model-regression-eval",
        "install_type": "skill",
        "version": version,
        "installed_at": datetime.now().isoformat(timespec="seconds"),
        "skill_name": skill_name,
        "global_skills_dir": str(resolved_global_skills_dir),
        "global_skill_path": str(global_dest),
        "skills_dir": primary_link["skills_dir"],
        "skill_path": primary_link["skill_path"],
        "skill_dir": primary_link["skill_dir"],
        "skill_links": link_results,
        "project_root": str(root),
        "requested_target": requested_target,
        "resolved_target": resolved_target,
        "support": spec.support,
        "family": spec.family,
        "source": source or {"type": "directory", "path": str(source_dir)},
        "dry_run": dry_run,
        "overwrite": overwrite,
        "backup": backup,
        "actions": [a.to_dict() for a in actions],
    }
    if not dry_run and global_dest.exists():
        (global_dest / SKILL_INSTALL_MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _target_from_skillpack(source_dir: Path) -> str | None:
    manifest = source_dir / "skillpack.manifest.json"
    if not manifest.exists():
        return None
    try:
        value = json.loads(manifest.read_text(encoding="utf-8")).get("target")
        return normalize_skill_target(str(value)) if value else None
    except Exception:
        return None


def _resolve_install_target(target: str, package_target: str | None, detected_target: str) -> str:
    if target != "auto":
        return normalize_skill_target(target)
    # Target-specific skillpacks should install as their own target even in a
    # fresh repo, but a generic package should still honor strong project
    # signals such as .cursor/skills or .windsurf/rules.
    if package_target and package_target != "generic":
        return package_target
    return detected_target


def install_skillpack_directory(*, source_skillpack: Path | str, project_root: Path | str = ".", target: str = "auto", dry_run: bool = False, overwrite: bool = False, backup: bool = True, source: dict[str, Any] | None = None) -> dict[str, Any]:
    root = Path(project_root).resolve()
    source_dir = Path(source_skillpack).resolve()
    if not source_dir.exists() or not source_dir.is_dir():
        raise FileNotFoundError(f"source skillpack directory not found: {source_dir}")
    detected = detect_target(root)
    system = detected.system or detect_system()
    requested_target = target
    package_target = _target_from_skillpack(source_dir)
    resolved_target = _resolve_install_target(target, package_target, detected.target)
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


def install_skill_from_project(
    *,
    project_root: Path | str,
    target: str,
    global_skills_dir: Path | str | None,
    skills_dir: Path | str | None,
    skill_dir_preset: str | None,
    install_project_root: Path | str,
    dry_run: bool,
    overwrite: bool,
    backup: bool,
) -> dict[str, Any]:
    resolved = detect_target(install_project_root).target if target == "auto" else normalize_skill_target(target)
    tmp, skillpack = build_temp_skillpack(resolved, Path(project_root))
    try:
        return install_skill_directory(
            source_skillpack=skillpack,
            global_skills_dir=global_skills_dir,
            skills_dir=skills_dir,
            skill_dir_preset=skill_dir_preset,
            project_root=install_project_root,
            target=resolved,
            dry_run=dry_run,
            overwrite=overwrite,
            backup=backup,
            source={"type": "project", "path": str(Path(project_root).resolve())},
        )
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


def install_skill_from_any_source(
    *,
    from_url: str | None = None,
    from_git: str | None = None,
    ref: str | None = None,
    sha256: str | None = None,
    target: str = "auto",
    global_skills_dir: Path | str | None = None,
    skills_dir: Path | str | None = None,
    skill_dir_preset: str | None = None,
    project_root: Path | str = ".",
    dry_run: bool = False,
    overwrite: bool = False,
    backup: bool = True,
) -> dict[str, Any]:
    if from_url and from_git:
        raise ValueError("choose only one of --from-url or --from-git")
    if from_url or from_git:
        with tempfile.TemporaryDirectory(prefix="mre_skill_install_src_") as td:
            work = Path(td)
            if from_url:
                kind, src, source_meta = prepare_source_from_url(from_url, work, expected_sha256=sha256)
            else:
                kind, src, source_meta = prepare_source_from_git(from_git or "", work, ref=ref)
            if kind == "skillpack":
                return install_skill_directory(
                    source_skillpack=src,
                    global_skills_dir=global_skills_dir,
                    skills_dir=skills_dir,
                    skill_dir_preset=skill_dir_preset,
                    project_root=project_root,
                    target=target,
                    dry_run=dry_run,
                    overwrite=overwrite,
                    backup=backup,
                    source=source_meta,
                )
            return install_skill_from_project(
                project_root=src,
                target=target,
                global_skills_dir=global_skills_dir,
                skills_dir=skills_dir,
                skill_dir_preset=skill_dir_preset,
                install_project_root=project_root,
                dry_run=dry_run,
                overwrite=overwrite,
                backup=backup,
            )
    return install_skill_from_project(
        project_root=project_root_from_module(),
        target=target,
        global_skills_dir=global_skills_dir,
        skills_dir=skills_dir,
        skill_dir_preset=skill_dir_preset,
        install_project_root=project_root,
        dry_run=dry_run,
        overwrite=overwrite,
        backup=backup,
    )


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
INSTALL_MODE="${{INSTALL_MODE:-skill}}"
GLOBAL_SKILLS_DIR="${{GLOBAL_SKILLS_DIR:-}}"
SKILLS_DIR="${{SKILLS_DIR:-}}"
SKILL_DIR_PRESET="${{SKILL_DIR_PRESET:-}}"
OVERWRITE="${{OVERWRITE:-0}}"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --target=*) TARGET="${{1#*=}}"; shift ;;
    --mode|--install-mode) INSTALL_MODE="$2"; shift 2 ;;
    --mode=*|--install-mode=*) INSTALL_MODE="${{1#*=}}"; shift ;;
    --global-skills-dir) GLOBAL_SKILLS_DIR="$2"; shift 2 ;;
    --global-skills-dir=*) GLOBAL_SKILLS_DIR="${{1#*=}}"; shift ;;
    --skills-dir) SKILLS_DIR="$2"; shift 2 ;;
    --skills-dir=*) SKILLS_DIR="${{1#*=}}"; shift ;;
    --skill-dir-preset) SKILL_DIR_PRESET="$2"; shift 2 ;;
    --skill-dir-preset=*) SKILL_DIR_PRESET="${{1#*=}}"; shift ;;
    --apply) DRY_RUN=0; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --overwrite) OVERWRITE=1; shift ;;
    --rules) INSTALL_MODE=rules; shift ;;
    --skill) INSTALL_MODE=skill; shift ;;
    --help)
      echo "Usage: install.sh [--target TARGET] [--apply] [--mode skill|rules] [--global-skills-dir DIR] [--skills-dir DIR] [--skill-dir-preset PRESET] [--overwrite]" >&2
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
case "$INSTALL_MODE" in
  skill|rules) ;;
  *) echo "Invalid --mode: $INSTALL_MODE (expected skill or rules)" >&2; exit 2 ;;
esac
TMPDIR="$(mktemp -d)"
PROJECT_ROOT="$(pwd -P)"
trap 'rm -rf "$TMPDIR"' EXIT
if command -v python3 >/dev/null 2>&1; then PY=python3; elif command -v python >/dev/null 2>&1; then PY=python; else echo "Python 3 is required" >&2; exit 1; fi
URL="{source_url}"
if command -v curl >/dev/null 2>&1; then curl -fsSL "$URL" -o "$TMPDIR/source.zip"; else wget -O "$TMPDIR/source.zip" "$URL"; fi
"$PY" - "$TMPDIR/source.zip" "$TARGET" "$DRY_RUN" "$PROJECT_ROOT" "$INSTALL_MODE" "$GLOBAL_SKILLS_DIR" "$SKILLS_DIR" "$SKILL_DIR_PRESET" "$OVERWRITE" <<'PYCODE'
import pathlib, subprocess, sys, zipfile
zip_path, target, dry, project_root, mode, global_skills_dir, skills_dir, skill_dir_preset, overwrite = sys.argv[1:10]
root = pathlib.Path(zip_path).with_suffix('')
root.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(zip_path) as zf:
    zf.extractall(root)
cands = [p.parent for p in root.rglob('pyproject.toml') if (p.parent/'model_regression_eval').exists()]
if not cands:
    raise SystemExit('could not locate project root in archive')
if mode not in ('skill', 'rules'):
    raise SystemExit(f'--mode must be skill or rules, got {{mode!r}}')
subcmd = 'install-skill' if mode == 'skill' else 'install'
cmd = [sys.executable, '-m', 'model_regression_eval.cli', 'skill', subcmd, '--target', target, '--project-root', project_root]
if mode == 'skill':
    if global_skills_dir:
        cmd += ['--global-skills-dir', global_skills_dir]
    if skills_dir:
        cmd += ['--skills-dir', skills_dir]
    if skill_dir_preset:
        cmd += ['--skill-dir-preset', skill_dir_preset]
if dry not in ('0','false','False','no'):
    cmd.append('--dry-run')
if overwrite in ('1','true','True','yes'):
    cmd.append('--overwrite')
subprocess.check_call(cmd, cwd=str(cands[0]))
PYCODE
'''
        elif git_url:
            text = f'''#!/usr/bin/env sh
set -eu
TARGET="${{TARGET:-auto}}"
DRY_RUN="${{DRY_RUN:-1}}"
INSTALL_MODE="${{INSTALL_MODE:-skill}}"
GLOBAL_SKILLS_DIR="${{GLOBAL_SKILLS_DIR:-}}"
SKILLS_DIR="${{SKILLS_DIR:-}}"
SKILL_DIR_PRESET="${{SKILL_DIR_PRESET:-}}"
OVERWRITE="${{OVERWRITE:-0}}"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --target=*) TARGET="${{1#*=}}"; shift ;;
    --mode|--install-mode) INSTALL_MODE="$2"; shift 2 ;;
    --mode=*|--install-mode=*) INSTALL_MODE="${{1#*=}}"; shift ;;
    --global-skills-dir) GLOBAL_SKILLS_DIR="$2"; shift 2 ;;
    --global-skills-dir=*) GLOBAL_SKILLS_DIR="${{1#*=}}"; shift ;;
    --skills-dir) SKILLS_DIR="$2"; shift 2 ;;
    --skills-dir=*) SKILLS_DIR="${{1#*=}}"; shift ;;
    --skill-dir-preset) SKILL_DIR_PRESET="$2"; shift 2 ;;
    --skill-dir-preset=*) SKILL_DIR_PRESET="${{1#*=}}"; shift ;;
    --apply) DRY_RUN=0; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --overwrite) OVERWRITE=1; shift ;;
    --rules) INSTALL_MODE=rules; shift ;;
    --skill) INSTALL_MODE=skill; shift ;;
    --help)
      echo "Usage: install.sh [--target TARGET] [--apply] [--mode skill|rules] [--global-skills-dir DIR] [--skills-dir DIR] [--skill-dir-preset PRESET] [--overwrite]" >&2
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
case "$INSTALL_MODE" in
  skill|rules) ;;
  *) echo "Invalid --mode: $INSTALL_MODE (expected skill or rules)" >&2; exit 2 ;;
esac
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT
if command -v python3 >/dev/null 2>&1; then PY=python3; elif command -v python >/dev/null 2>&1; then PY=python; else echo "Python 3 is required" >&2; exit 1; fi
PROJECT_ROOT="$(pwd -P)"
git clone --depth 1 "{git_url}" "$TMPDIR/repo"
cd "$TMPDIR/repo"
"$PY" - "$TARGET" "$DRY_RUN" "$PROJECT_ROOT" "$INSTALL_MODE" "$GLOBAL_SKILLS_DIR" "$SKILLS_DIR" "$SKILL_DIR_PRESET" "$OVERWRITE" <<'PYCODE'
import subprocess, sys
target, dry, project_root, mode, global_skills_dir, skills_dir, skill_dir_preset, overwrite = sys.argv[1:9]
if mode not in ('skill', 'rules'):
    raise SystemExit(f'--mode must be skill or rules, got {{mode!r}}')
subcmd = 'install-skill' if mode == 'skill' else 'install'
cmd = [sys.executable, '-m', 'model_regression_eval.cli', 'skill', subcmd, '--target', target, '--project-root', project_root]
if mode == 'skill':
    if global_skills_dir:
        cmd += ['--global-skills-dir', global_skills_dir]
    if skills_dir:
        cmd += ['--skills-dir', skills_dir]
    if skill_dir_preset:
        cmd += ['--skill-dir-preset', skill_dir_preset]
if dry not in ('0','false','False','no'):
    cmd.append('--dry-run')
if overwrite in ('1','true','True','yes'):
    cmd.append('--overwrite')
subprocess.check_call(cmd)
PYCODE
'''
        else:
            text = '''#!/usr/bin/env sh
set -eu
echo "No source URL or git URL embedded. Clone the repository and run: python -m model_regression_eval.cli skill install-skill --dry-run" >&2
exit 1
'''
        out.write_text(text, encoding="utf-8")
        out.chmod(out.stat().st_mode | 0o755)
        return
    if platform in {"windows", "powershell", "ps1"}:
        text = f'''param(
  [string]$Target = "auto",
  [ValidateSet("rules", "skill")]
  [string]$Mode = "skill",
  [string]$GlobalSkillsDir = "",
  [string]$SkillsDir = "",
  [string]$SkillDirPreset = "",
  [switch]$Overwrite,
  [switch]$Apply
)
$ErrorActionPreference = "Stop"
$DryRun = -not $Apply
$ProjectRoot = (Get-Location).Path
$Tmp = New-Item -ItemType Directory -Force -Path ([System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), "mre-install-" + [System.Guid]::NewGuid().ToString()))
try {{
  $Url = "{source_url or ''}"
  if (-not $Url) {{ throw "No source URL embedded. Clone the repository and run python -m model_regression_eval.cli skill install-skill." }}
  $Zip = Join-Path $Tmp "source.zip"
  Invoke-WebRequest -Uri $Url -OutFile $Zip
  Expand-Archive -Path $Zip -DestinationPath (Join-Path $Tmp "source") -Force
  $Project = Get-ChildItem -Path (Join-Path $Tmp "source") -Filter pyproject.toml -Recurse | Where-Object {{ Test-Path (Join-Path $_.DirectoryName "model_regression_eval") }} | Select-Object -First 1
  if (-not $Project) {{ throw "could not locate project root in archive" }}
  Push-Location $Project.DirectoryName
  $Subcommand = if ($Mode -eq "skill") {{ "install-skill" }} else {{ "install" }}
  $Args = @("-m", "model_regression_eval.cli", "skill", $Subcommand, "--target", $Target, "--project-root", $ProjectRoot)
  if ($Mode -eq "skill") {{
    if ($GlobalSkillsDir) {{ $Args += @("--global-skills-dir", $GlobalSkillsDir) }}
    if ($SkillsDir) {{ $Args += @("--skills-dir", $SkillsDir) }}
    if ($SkillDirPreset) {{ $Args += @("--skill-dir-preset", $SkillDirPreset) }}
  }}
  if ($DryRun) {{ $Args += "--dry-run" }}
  if ($Overwrite) {{ $Args += "--overwrite" }}
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
    parser = argparse.ArgumentParser(description="Install a generated model-regression-eval skillpack.")
    parser.add_argument("--mode", choices=["rules", "skill"], default="skill")
    parser.add_argument("--target", default="auto")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--global-skills-dir", default=None)
    parser.add_argument("--skills-dir", default=None)
    parser.add_argument("--skill-dir-preset", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args(argv)
    source = Path(__file__).resolve().parent
    if args.mode == "skill":
        manifest = install_skill_directory(
            source_skillpack=source,
            global_skills_dir=args.global_skills_dir,
            skills_dir=args.skills_dir,
            skill_dir_preset=args.skill_dir_preset,
            project_root=args.project_root,
            target=args.target,
            dry_run=args.dry_run,
            overwrite=args.overwrite,
            backup=not args.no_backup,
        )
    else:
        manifest = install_skillpack_directory(source_skillpack=source, project_root=args.project_root, target=args.target, dry_run=args.dry_run, overwrite=args.overwrite, backup=not args.no_backup)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0
