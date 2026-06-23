from __future__ import annotations

import json
from pathlib import Path
import shutil
import stat
import zipfile
from dataclasses import dataclass
from typing import Any


DEFAULT_TASKS = "tasks/core.zh.jsonl"
DEFAULT_SCHEMA = "schemas/final_answer.schema.json"
RULE_FILE = "model-regression-eval.md"


@dataclass(frozen=True)
class TargetSpec:
    name: str
    aliases: tuple[str, ...]
    support: str
    description: str
    family: str
    template: str


TARGET_SPECS: dict[str, TargetSpec] = {
    "chatgpt": TargetSpec("chatgpt", ("openai", "openai-skill", "chatgpt-skill"), "strong", "ChatGPT Skill zip with SKILL.md and agents/openai.yaml.", "native_skill", "chatgpt"),
    "claude": TargetSpec("claude", ("claude-code", "anthropic", "claude-cli"), "strong", "Claude / Claude Code package with CLAUDE.md and SKILL.md.", "agent_project", "claude"),
    "codex": TargetSpec("codex", ("codex-cli",), "strong", "Codex project package with AGENTS.md.", "agent_project", "codex"),
    "gemini": TargetSpec("gemini", ("gemini-cli",), "strong", "Gemini CLI package with GEMINI.md.", "agent_project", "gemini"),
    "opencode": TargetSpec("opencode", ("opencode-cli",), "strong", "OpenCode package with AGENTS.md and OPENCODE.md.", "agent_project", "opencode"),
    "hermes": TargetSpec("hermes", ("hermes-api",), "strong", "Hermes / OpenAI-compatible package.", "api_agent", "hermes"),
    "windsurf": TargetSpec("windsurf", ("devin-desktop", "devin"), "strong", "Windsurf/Devin Desktop workspace rules package.", "ai_ide", "windsurf"),
    "cline": TargetSpec("cline", ("cline-bot",), "strong", "Cline rules package with .clinerules and AGENTS.md.", "ai_ide", "cline"),
    "github-copilot": TargetSpec("github-copilot", ("copilot", "github"), "strong", "GitHub Copilot repository instructions package.", "ai_ide", "github-copilot"),
    "cursor": TargetSpec("cursor", ("cursor-ide",), "best_effort", "Cursor rules package with .cursor/rules and AGENTS.md fallback.", "ai_ide", "cursor"),
    "roo-code": TargetSpec("roo-code", ("roo", "roocode"), "best_effort", "Roo Code rules package with AGENTS.md fallback.", "ai_ide", "roo-code"),
    "kilo-code": TargetSpec("kilo-code", ("kilo", "kilocode"), "best_effort", "Kilo Code rules package with AGENTS.md fallback.", "ai_ide", "kilo-code"),
    "zed": TargetSpec("zed", ("zcode", "zed-code"), "best_effort", "Zed/Zcode package with AGENTS.md fallback.", "ai_ide", "zed"),
    "aider": TargetSpec("aider", ("aider-chat",), "best_effort", "Aider package with AGENTS.md and .aider.conf.yml.", "ai_ide", "aider"),
    "trae": TargetSpec("trae", ("trae-ide",), "best_effort", "Trae package with AGENTS.md fallback and TRAE.md entrypoint.", "ai_ide", "trae"),
    "continue": TargetSpec("continue", ("continue-dev",), "best_effort", "Continue package with AGENTS.md fallback.", "ai_ide", "continue"),
    "junie": TargetSpec("junie", ("jetbrains-junie", "jetbrains"), "best_effort", "JetBrains Junie package with AGENTS.md fallback.", "ai_ide", "junie"),
    "kiro": TargetSpec("kiro", ("kiro-ide",), "best_effort", "Kiro package with AGENTS.md fallback.", "ai_ide", "kiro"),
    "augment-code": TargetSpec("augment-code", ("augment",), "best_effort", "Augment Code package with AGENTS.md fallback.", "ai_ide", "augment-code"),
    "warp": TargetSpec("warp", ("warp-terminal",), "best_effort", "Warp terminal agent package with AGENTS.md fallback.", "ai_ide", "warp"),
    "ai-ide": TargetSpec("ai-ide", ("ide", "aiide", "editor"), "best_effort", "Multi-rule AI IDE package containing several common project instruction files.", "ai_ide", "ai-ide"),
    "web-manual": TargetSpec("web-manual", ("web", "manual-web", "browser", "web-agent"), "manual_web", "Manual web-agent package for products that cannot install local skills.", "web", "web-manual"),
    "qwen-web": TargetSpec("qwen-web", ("qwen", "tongyi", "tongyi-web"), "manual_web", "Qwen web manual workflow package.", "web", "web-manual"),
    "glm-web": TargetSpec("glm-web", ("glm", "z-ai", "zai", "chatglm-web"), "manual_web", "GLM/Z.ai web manual workflow package.", "web", "web-manual"),
    "kimi-web": TargetSpec("kimi-web", ("kimi",), "manual_web", "Kimi web manual workflow package.", "web", "web-manual"),
    "deepseek-web": TargetSpec("deepseek-web", ("deepseek",), "manual_web", "DeepSeek web manual workflow package.", "web", "web-manual"),
    "doubao-web": TargetSpec("doubao-web", ("doubao", "豆包"), "manual_web", "Doubao web manual workflow package.", "web", "web-manual"),
    "yuanbao-web": TargetSpec("yuanbao-web", ("yuanbao", "腾讯元宝", "tencent-yuanbao"), "manual_web", "Tencent Yuanbao web manual workflow package.", "web", "web-manual"),
    "claude-web": TargetSpec("claude-web", ("claude-ai", "claude-browser"), "manual_web", "Claude web manual workflow package.", "web", "web-manual"),
    "gemini-web": TargetSpec("gemini-web", ("gemini-browser", "google-ai-studio-web"), "manual_web", "Gemini web manual workflow package.", "web", "web-manual"),
    "qwen-api": TargetSpec("qwen-api", ("qwen-compatible", "dashscope-compatible"), "api_preset", "Qwen API/OpenAI-compatible preset package.", "api_agent", "qwen-api"),
    "glm-api": TargetSpec("glm-api", ("z-ai-api", "zai-api", "chatglm-api"), "api_preset", "GLM/Z.ai API/OpenAI-compatible preset package.", "api_agent", "glm-api"),
    "generic": TargetSpec("generic", ("universal", "fallback", "compat", "unknown"), "generic", "Generic package with README.md and AGENTS.md fallback.", "generic", "generic"),
}

CANONICAL_TARGETS = list(TARGET_SPECS.keys())

TARGET_ALIASES: dict[str, str] = {}
for _name, _spec in TARGET_SPECS.items():
    TARGET_ALIASES[_name] = _name
    for _alias in _spec.aliases:
        TARGET_ALIASES[_alias] = _name
TARGET_ALIASES["all"] = "all"


@dataclass(frozen=True)
class BuiltSkillpack:
    target: str
    package_path: Path
    staging_dir: Path | None
    files_count: int
    bytes_size: int
    support: str = "unknown"
    family: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "support": self.support,
            "family": self.family,
            "package_path": str(self.package_path),
            "staging_dir": str(self.staging_dir) if self.staging_dir else None,
            "files_count": self.files_count,
            "bytes_size": self.bytes_size,
        }


def normalize_skill_target(target: str) -> str:
    key = (target or "generic").strip().lower().replace("_", "-")
    return TARGET_ALIASES.get(key, "generic")


def target_spec(target: str) -> TargetSpec:
    return TARGET_SPECS[normalize_skill_target(target)]


def project_root_from_module() -> Path:
    return Path(__file__).resolve().parents[1]


def build_skillpacks(
    *,
    target: str,
    out_dir: Path | str,
    project_root: Path | str | None = None,
    package_format: str = "zip",
    overwrite: bool = True,
) -> list[BuiltSkillpack]:
    root = Path(project_root) if project_root else project_root_from_module()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    normalized = normalize_skill_target(target)
    targets = CANONICAL_TARGETS if normalized == "all" else [normalized]
    built = [
        build_one_skillpack(
            target=t,
            out_dir=out,
            project_root=root,
            package_format=package_format,
            overwrite=overwrite,
            multi_target=normalized == "all",
        )
        for t in targets
    ]
    staging_parent = out / "_skillpack_build"
    if staging_parent.exists():
        shutil.rmtree(staging_parent)
    return built


def build_one_skillpack(
    *,
    target: str,
    out_dir: Path,
    project_root: Path,
    package_format: str = "zip",
    overwrite: bool = True,
    multi_target: bool = False,
) -> BuiltSkillpack:
    canonical = normalize_skill_target(target)
    if canonical == "all":
        raise ValueError("build_one_skillpack cannot build target=all")
    if package_format not in {"zip", "directory"}:
        raise ValueError("package_format must be 'zip' or 'directory'")
    spec = TARGET_SPECS[canonical]

    staging_parent = out_dir / "_skillpack_build"
    if overwrite and staging_parent.exists():
        shutil.rmtree(staging_parent)
    staging_parent.mkdir(parents=True, exist_ok=True)
    package_name = f"model-regression-eval-{canonical}"
    skill_dir = staging_parent / package_name
    if skill_dir.exists():
        shutil.rmtree(skill_dir)
    skill_dir.mkdir(parents=True)

    _write_target_files(skill_dir, spec)
    _copy_eval_project(project_root, skill_dir / "assets" / "eval_project")
    _write_manifest(skill_dir, spec, project_root)

    files_count = sum(1 for p in skill_dir.rglob("*") if p.is_file())
    bytes_size = sum(p.stat().st_size for p in skill_dir.rglob("*") if p.is_file())

    if package_format == "directory":
        final_dir = out_dir / package_name
        if final_dir.exists():
            if overwrite:
                shutil.rmtree(final_dir)
            else:
                raise FileExistsError(final_dir)
        shutil.copytree(skill_dir, final_dir)
        return BuiltSkillpack(canonical, final_dir, final_dir, files_count, bytes_size, spec.support, spec.family)

    if canonical == "chatgpt" and not multi_target:
        zip_path = out_dir / "skill.zip"
    else:
        zip_path = out_dir / f"{package_name}.zip"
    if zip_path.exists():
        if overwrite:
            zip_path.unlink()
        else:
            raise FileExistsError(zip_path)
    _zip_dir(skill_dir, zip_path)
    return BuiltSkillpack(canonical, zip_path, None, files_count, zip_path.stat().st_size, spec.support, spec.family)


def _copy_eval_project(project_root: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    include_dirs = ["model_regression_eval", "tasks", "schemas"]
    include_files = ["pyproject.toml", "README.md", "LICENSE"]
    for name in include_dirs:
        src = project_root / name
        if src.exists():
            shutil.copytree(src, dest / name, ignore=_copy_ignore)
    for name in include_files:
        src = project_root / name
        if src.exists():
            shutil.copy2(src, dest / name)


def _copy_ignore(dir_path: str, names: list[str]) -> set[str]:
    ignored = set()
    for name in names:
        if name in {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".git", ".venv", "venv", "dist", "build", "runs", "examples"}:
            ignored.add(name)
        if name.endswith((".pyc", ".pyo", ".log")):
            ignored.add(name)
    return ignored


def _zip_dir(src: Path, dest_zip: Path) -> None:
    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(src.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(src.parent))


def _write_manifest(skill_dir: Path, spec: TargetSpec, project_root: Path) -> None:
    task_path = project_root / DEFAULT_TASKS
    task_count = _count_jsonl(task_path)
    manifest = {
        "name": "model-regression-eval",
        "target": spec.name,
        "support": spec.support,
        "family": spec.family,
        "description": spec.description,
        "version": _read_project_version(project_root),
        "task_file": DEFAULT_TASKS,
        "task_count": task_count,
        "schema_file": DEFAULT_SCHEMA,
        "entrypoints": ["scripts/mre", "scripts/mre.py", "scripts/mre.bat"],
        "default_profiles": {"smoke": 40, "standard": 100, "full": task_count},
        "default_depths": {"quick": 1, "confirm": 3, "deep": 5},
        "notes": "package-only skillpack; it does not install itself or write global agent configuration",
    }
    (skill_dir / "skillpack.manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _read_project_version(project_root: Path) -> str:
    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        return "unknown"
    for line in pyproject.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("version"):
            return line.split("=", 1)[1].strip().strip('"')
    return "unknown"


def _write_target_files(skill_dir: Path, spec: TargetSpec) -> None:
    (skill_dir / "scripts").mkdir(parents=True, exist_ok=True)
    (skill_dir / "references").mkdir(parents=True, exist_ok=True)
    (skill_dir / "assets").mkdir(parents=True, exist_ok=True)
    _write_mre_scripts(skill_dir)
    _write_install_scripts(skill_dir)
    _write_references(skill_dir)
    template = spec.template
    if template == "chatgpt":
        _write_chatgpt_skill(skill_dir)
    elif template == "claude":
        _write_claude_skill(skill_dir)
    elif template == "codex":
        _write_agent_manifest(skill_dir, "AGENTS.md", "Codex", spec)
    elif template == "gemini":
        _write_agent_manifest(skill_dir, "GEMINI.md", "Gemini CLI", spec)
        _write_json(skill_dir / ".gemini" / "settings.json", {"contextFileName": "GEMINI.md"})
    elif template == "opencode":
        _write_agent_manifest(skill_dir, "AGENTS.md", "OpenCode", spec)
        _write_agent_manifest(skill_dir, "OPENCODE.md", "OpenCode", spec, readme=False)
    elif template == "hermes":
        _write_agent_manifest(skill_dir, "HERMES.md", "Hermes / OpenAI-compatible agent", spec)
        _write_api_preset(skill_dir, spec, runner="hermes")
    elif template == "windsurf":
        _write_windsurf(skill_dir, spec)
    elif template == "cline":
        _write_cline(skill_dir, spec)
    elif template == "github-copilot":
        _write_github_copilot(skill_dir, spec)
    elif template in {"cursor", "roo-code", "kilo-code", "zed", "aider", "trae", "continue", "junie", "kiro", "augment-code", "warp"}:
        _write_best_effort_ide(skill_dir, spec)
    elif template == "ai-ide":
        _write_ai_ide(skill_dir, spec)
    elif template == "web-manual":
        _write_web_manual(skill_dir, spec)
    elif template in {"qwen-api", "glm-api"}:
        _write_api_preset(skill_dir, spec, runner=template)
    else:
        _write_agent_manifest(skill_dir, "AGENTS.md", "Generic agent", spec)


def _write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_mre_scripts(skill_dir: Path) -> None:
    py = skill_dir / "scripts" / "mre.py"
    py.write_text(
        '''#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def main() -> int:
    here = Path(__file__).resolve().parent
    root = here.parent
    project = root / "assets" / "eval_project"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    cmd = [sys.executable, "-m", "model_regression_eval.cli", *_resolve_bundled_paths(sys.argv[1:], project)]
    return subprocess.run(cmd, env=env).returncode


def _resolve_bundled_paths(argv: list[str], project: Path) -> list[str]:
    path_flags = {"--tasks", "--schema"}
    resolved: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in path_flags and i + 1 < len(argv):
            resolved.append(arg)
            resolved.append(_resolve_one_path(argv[i + 1], project))
            i += 2
            continue
        prefix = next((flag + "=" for flag in path_flags if arg.startswith(flag + "=")), None)
        if prefix:
            resolved.append(prefix + _resolve_one_path(arg[len(prefix):], project))
        else:
            resolved.append(arg)
        i += 1
    return resolved


def _resolve_one_path(value: str, project: Path) -> str:
    path = Path(value)
    if path.is_absolute() or path.exists():
        return value
    bundled = project / path
    if bundled.exists():
        return str(bundled)
    return value


if __name__ == "__main__":
    raise SystemExit(main())
''',
        encoding="utf-8",
    )
    py.chmod(py.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    sh = skill_dir / "scripts" / "mre"
    sh.write_text(
        '''#!/usr/bin/env sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "Python 3 is required" >&2
  exit 1
fi
exec "$PY" "$SCRIPT_DIR/mre.py" "$@"
''',
        encoding="utf-8",
    )
    sh.chmod(sh.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    bat = skill_dir / "scripts" / "mre.bat"
    bat.write_text(
        '''@echo off
python "%~dp0mre.py" %*
''',
        encoding="utf-8",
    )


def _write_install_scripts(skill_dir: Path) -> None:
    install_py = '#!/usr/bin/env python3\nfrom __future__ import annotations\n\nimport json\nfrom pathlib import Path\nimport sys\n\nROOT = Path(__file__).resolve().parent\nPROJECT = ROOT / "assets" / "eval_project"\nsys.path.insert(0, str(PROJECT))\n\nfrom model_regression_eval.installer import install_skillpack_directory\n\n\ndef main(argv=None):\n    import argparse\n    parser = argparse.ArgumentParser(description="Install this Model Regression Eval skillpack into a project.")\n    parser.add_argument("--target", default="auto")\n    parser.add_argument("--project-root", default=".")\n    parser.add_argument("--dry-run", action="store_true")\n    parser.add_argument("--overwrite", action="store_true")\n    parser.add_argument("--no-backup", action="store_true")\n    args = parser.parse_args(argv)\n    manifest = install_skillpack_directory(\n        source_skillpack=ROOT,\n        project_root=args.project_root,\n        target=args.target,\n        dry_run=args.dry_run,\n        overwrite=args.overwrite,\n        backup=not args.no_backup,\n    )\n    print(json.dumps(manifest, ensure_ascii=False, indent=2))\n    return 0\n\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n'
    _write_text(skill_dir / "install.py", install_py)
    (skill_dir / "install.py").chmod((skill_dir / "install.py").stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    _write_text(skill_dir / "install.sh", '#!/usr/bin/env sh\nset -eu\nif command -v python3 >/dev/null 2>&1; then PY=python3; elif command -v python >/dev/null 2>&1; then PY=python; else echo "Python 3 is required" >&2; exit 1; fi\nDIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexec "$PY" "$DIR/install.py" "$@"\n')
    (skill_dir / "install.sh").chmod((skill_dir / "install.sh").stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    _write_text(skill_dir / "install.ps1", 'param(\n  [string]$Target = "auto",\n  [string]$ProjectRoot = ".",\n  [switch]$DryRun,\n  [switch]$Overwrite\n)\n$ErrorActionPreference = "Stop"\n$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path\n$Args = @("$Dir\\install.py", "--target", $Target, "--project-root", $ProjectRoot)\nif ($DryRun) { $Args += "--dry-run" }\nif ($Overwrite) { $Args += "--overwrite" }\npython @Args\n')


def _write_references(skill_dir: Path) -> None:
    _write_text(skill_dir / "references" / "workflow.md", WORKFLOW_MD)
    _write_text(skill_dir / "references" / "runners.md", RUNNERS_MD)
    _write_text(skill_dir / "references" / "interpretation.md", INTERPRETATION_MD)
    _write_text(skill_dir / "references" / "ide-targets.md", IDE_TARGETS_MD)
    _write_text(skill_dir / "references" / "web-manual.md", WEB_MANUAL_MD)


def _write_chatgpt_skill(skill_dir: Path) -> None:
    _write_text(skill_dir / "SKILL.md", CHATGPT_SKILL_MD)
    _write_text(
        skill_dir / "agents" / "openai.yaml",
        '''interface:
  display_name: Model Regression Eval
  short_description: Evaluate model and agent capability regressions.
  icon: chart-bar
  background_color: "#1f6feb"
''',
    )


def _write_claude_skill(skill_dir: Path) -> None:
    _write_text(skill_dir / "SKILL.md", CLAUDE_SKILL_MD)
    spec = TARGET_SPECS["claude"]
    _write_agent_manifest(skill_dir, "CLAUDE.md", "Claude / Claude Code", spec)
    _write_text(skill_dir / ".claude" / "rules" / RULE_FILE, _rule_md("Claude / Claude Code", spec))


def _write_agent_manifest(skill_dir: Path, filename: str, agent_name: str, spec: TargetSpec, *, readme: bool = True) -> None:
    _write_text(skill_dir / filename, _manifest_md(agent_name, spec))
    if readme and filename != "README.md" and not (skill_dir / "README.md").exists():
        _write_text(skill_dir / "README.md", _manifest_md(agent_name, spec))


def _rule_md(agent_name: str, spec: TargetSpec) -> str:
    return _manifest_md(agent_name, spec, compact=True)


def _manifest_md(agent_name: str, spec: TargetSpec, *, compact: bool = False) -> str:
    support = spec.support.replace("_", " ")
    note = SUPPORT_NOTES.get(spec.support, SUPPORT_NOTES["generic"])
    header = f"# Model Regression Eval for {agent_name}\n\n"
    body = f"""Support level: `{spec.support}` ({support}).

{note}

This package contains a self-contained model/agent capability regression evaluator with the full 300-task Chinese task set.

## Entry point

Run commands through the bundled wrapper:

```bash
./scripts/mre budget --tasks tasks/core.zh.jsonl --profile smoke --depth quick
./scripts/mre run --runner mock --tasks tasks/core.zh.jsonl --profile smoke --depth quick --out-dir runs --run-id selfcheck
```

On Windows:

```bat
scripts\\mre.bat budget --tasks tasks/core.zh.jsonl --profile smoke --depth quick
```

The wrapper runs from `assets/eval_project`, so the default task and schema paths are:

- `tasks/core.zh.jsonl`
- `schemas/final_answer.schema.json`

## Recommended workflow

1. Estimate cost: `./scripts/mre budget --tasks tasks/core.zh.jsonl --profile smoke --depth quick`.
2. Self-check: `./scripts/mre run --runner mock --tasks tasks/core.zh.jsonl --profile smoke --depth quick`.
3. Test the target agent with `smoke quick`.
4. If results look abnormal, run `standard confirm`.
5. For final confirmation, run `full confirm` and compare against a baseline.

## Profiles and depths

- `--profile smoke`: 40 tasks.
- `--profile standard`: 100 tasks.
- `--profile full`: all 300 tasks.
- `--depth quick`: 1 repeat per task.
- `--depth confirm`: 3 repeats per task.
- `--depth deep`: 5 repeats per task.

Use `--max-requests` and `--max-observed-tokens` to control cost.

## Common runners

```bash
./scripts/mre run --runner codex --tasks tasks/core.zh.jsonl --profile smoke --depth quick --model gpt-5.5
./scripts/mre run --runner claude_cli --tasks tasks/core.zh.jsonl --profile smoke --depth quick --model claude-sonnet-4-5
./scripts/mre run --runner gemini_cli --tasks tasks/core.zh.jsonl --profile smoke --depth quick --model gemini-2.5-pro
./scripts/mre run --runner opencode --tasks tasks/core.zh.jsonl --profile smoke --depth quick --model <model>
./scripts/mre run --runner hermes --tasks tasks/core.zh.jsonl --profile smoke --depth quick --agent-url http://localhost:8000/v1 --model <model>
./scripts/mre run --runner http --tasks tasks/core.zh.jsonl --profile smoke --depth quick --agent-url http://localhost:8000/eval
./scripts/mre run --runner subprocess --tasks tasks/core.zh.jsonl --profile smoke --agent-command 'my-agent --prompt-file {{prompt_file}} --schema {{schema_path}}'
```

## Manual/web agents

For agents that cannot be called directly, export prompts and import results:

```bash
./scripts/mre export-prompts --tasks tasks/core.zh.jsonl --profile smoke --out runs/manual_prompts.jsonl
./scripts/mre import-results --tasks tasks/core.zh.jsonl --outputs runs/manual_outputs.jsonl --out-dir runs --run-id manual_agent
```

## Interpreting results

Do not conclude degradation from one failed case. Prefer paired baseline/candidate comparison, majority accuracy, consistency rate, stable regressions, and manual review of regression cases.
"""
    if compact:
        return header + body
    return header + body + "\nSee `references/` for detailed workflow, runner, IDE target, and web/manual guidance.\n"


def _write_windsurf(skill_dir: Path, spec: TargetSpec) -> None:
    _write_agent_manifest(skill_dir, "AGENTS.md", "Windsurf / Devin Desktop", spec)
    _write_text(skill_dir / ".devin" / "rules" / RULE_FILE, _rule_md("Windsurf / Devin Desktop", spec))
    _write_text(skill_dir / ".windsurf" / "rules" / RULE_FILE, _rule_md("Windsurf fallback rules", spec))
    _write_text(skill_dir / ".windsurfrules", _rule_md("legacy Windsurf rules", spec))


def _write_cline(skill_dir: Path, spec: TargetSpec) -> None:
    _write_agent_manifest(skill_dir, "AGENTS.md", "Cline", spec)
    _write_text(skill_dir / ".clinerules" / RULE_FILE, _rule_md("Cline", spec))


def _write_github_copilot(skill_dir: Path, spec: TargetSpec) -> None:
    _write_agent_manifest(skill_dir, "AGENTS.md", "GitHub Copilot", spec)
    _write_text(skill_dir / ".github" / "copilot-instructions.md", _rule_md("GitHub Copilot repository instructions", spec))
    _write_text(skill_dir / ".github" / "instructions" / "model-regression-eval.instructions.md", _rule_md("GitHub Copilot path instructions", spec))


def _write_best_effort_ide(skill_dir: Path, spec: TargetSpec) -> None:
    _write_agent_manifest(skill_dir, "AGENTS.md", spec.name, spec)
    mapping = {
        "cursor": [(".cursor/rules/model-regression-eval.mdc", "Cursor project rules"), (".cursorrules", "legacy Cursor rules")],
        "roo-code": [(".roo/rules/model-regression-eval.md", "Roo Code rules"), (".roorules", "legacy Roo rules")],
        "kilo-code": [(".kilocode/rules/model-regression-eval.md", "Kilo Code rules")],
        "zed": [("ZED.md", "Zed/Zcode instructions")],
        "aider": [("AIDER.md", "Aider instructions")],
        "trae": [("TRAE.md", "Trae instructions"), (".trae/README.md", "Trae workspace notes")],
        "continue": [("CONTINUE.md", "Continue instructions"), (".continue/README.md", "Continue workspace notes")],
        "junie": [("JUNIE.md", "JetBrains Junie instructions")],
        "kiro": [("KIRO.md", "Kiro instructions")],
        "augment-code": [("AUGMENT.md", "Augment Code instructions")],
        "warp": [("WARP.md", "Warp terminal agent instructions")],
    }
    for rel, name in mapping.get(spec.name, []):
        _write_text(skill_dir / rel, _rule_md(name, spec))
    if spec.name == "aider":
        _write_text(skill_dir / ".aider.conf.yml", "read:\n  - AGENTS.md\n")


def _write_ai_ide(skill_dir: Path, spec: TargetSpec) -> None:
    _write_agent_manifest(skill_dir, "AGENTS.md", "AI IDE generic package", spec)
    _write_text(skill_dir / "CLAUDE.md", _rule_md("Claude-compatible IDE", spec))
    _write_text(skill_dir / "GEMINI.md", _rule_md("Gemini-compatible IDE", spec))
    _write_text(skill_dir / ".github" / "copilot-instructions.md", _rule_md("GitHub Copilot", spec))
    _write_text(skill_dir / ".github" / "instructions" / "model-regression-eval.instructions.md", _rule_md("GitHub Copilot instructions", spec))
    _write_text(skill_dir / ".devin" / "rules" / RULE_FILE, _rule_md("Windsurf/Devin", spec))
    _write_text(skill_dir / ".windsurf" / "rules" / RULE_FILE, _rule_md("Windsurf", spec))
    _write_text(skill_dir / ".clinerules" / RULE_FILE, _rule_md("Cline", spec))
    _write_text(skill_dir / ".cursor" / "rules" / "model-regression-eval.mdc", _rule_md("Cursor", spec))
    _write_text(skill_dir / ".roo" / "rules" / RULE_FILE, _rule_md("Roo Code", spec))
    _write_text(skill_dir / ".kilocode" / "rules" / RULE_FILE, _rule_md("Kilo Code", spec))
    for name in ["OPENCODE.md", "TRAE.md", "ZED.md", "AIDER.md", "CONTINUE.md", "JUNIE.md", "KIRO.md", "AUGMENT.md", "WARP.md"]:
        _write_text(skill_dir / name, _rule_md(name.removesuffix(".md"), spec))
    _write_text(skill_dir / ".aider.conf.yml", "read:\n  - AGENTS.md\n")
    _write_json(skill_dir / ".gemini" / "settings.json", {"contextFileName": "GEMINI.md"})


def _write_web_manual(skill_dir: Path, spec: TargetSpec) -> None:
    _write_agent_manifest(skill_dir, "README.md", spec.name, spec)
    _write_text(skill_dir / "WEB_AGENT_INSTRUCTIONS.md", WEB_AGENT_INSTRUCTIONS_MD.format(target=spec.name))
    _write_text(skill_dir / "SYSTEM_PROMPT.md", WEB_SYSTEM_PROMPT_MD)
    _write_text(skill_dir / "templates" / "manual_outputs.template.jsonl", MANUAL_OUTPUT_TEMPLATE_JSONL)


def _write_api_preset(skill_dir: Path, spec: TargetSpec, *, runner: str) -> None:
    _write_agent_manifest(skill_dir, "AGENTS.md", spec.name, spec)
    if runner == "qwen-api":
        preset = API_PRESET_MD.format(runner="qwen_api", env_url="QWEN_BASE_URL", env_key="QWEN_API_KEY", env_model="QWEN_MODEL", example_model="qwen-max")
    elif runner == "glm-api":
        preset = API_PRESET_MD.format(runner="glm_api", env_url="GLM_BASE_URL", env_key="GLM_API_KEY", env_model="GLM_MODEL", example_model="glm-4-plus")
    else:
        preset = API_PRESET_MD.format(runner="hermes", env_url="HERMES_BASE_URL", env_key="HERMES_API_KEY", env_model="HERMES_MODEL", example_model="NousResearch/Hermes-3-Llama-3.1-8B")
    _write_text(skill_dir / "API_PRESET.md", preset)


SUPPORT_NOTES = {
    "strong": "This target has a dedicated package shape with a known project instruction file or native skill entrypoint.",
    "best_effort": "This target uses the best-known project-rule files plus AGENTS.md fallback. Verify that your local IDE version loads these files.",
    "manual_web": "This target is for web products that usually cannot install local executable skills. Use export-prompts/import-results.",
    "api_preset": "This target is an API runner preset. Configure endpoint and API key through environment variables or CLI flags.",
    "generic": "This target is the fallback compatibility package. It uses README.md and AGENTS.md plus scripts/mre.",
}


CHATGPT_SKILL_MD = """---
name: model-regression-eval
description: evaluate model and agent capability regressions using a fixed 300-task chinese task set, deterministic grading, profile/depth sampling, token budgeting, majority voting, and baseline/candidate comparison. use when asked to test whether an llm, coding agent, cli agent, api model, web agent, ai ide, chatgpt, claude, codex, gemini, windsurf, cursor, cline, github copilot, opencode, hermes, qwen, glm, or generic agent has degraded; export prompts; import manual results; or generate regression reports.
---

# Model Regression Eval

Use this skill to run standardized model or agent capability regression checks. Prefer the bundled scripts over ad hoc evaluation logic.

## Workflow

1. Estimate cost with `scripts/mre budget` before calling a paid or rate-limited agent.
2. Run `smoke quick` first.
3. If abnormal, run `standard confirm`.
4. For final confirmation, run `full confirm`, not `full deep` unless explicitly requested.
5. Compare against a baseline with `scripts/mre compare`.
6. Review regression cases before concluding that a model or agent degraded.

## Entrypoint

Use `scripts/mre` on POSIX systems, `scripts/mre.bat` on Windows, or `python scripts/mre.py` everywhere.

The script runs from the bundled project directory at `assets/eval_project`, so use these paths:

- task file: `tasks/core.zh.jsonl`
- schema file: `schemas/final_answer.schema.json`

## Common commands

```bash
scripts/mre budget --tasks tasks/core.zh.jsonl --profile smoke --depth quick
scripts/mre run --runner mock --tasks tasks/core.zh.jsonl --profile smoke --depth quick --out-dir runs --run-id selfcheck
scripts/mre run --runner http --agent-url http://localhost:8000/eval --tasks tasks/core.zh.jsonl --profile smoke --depth quick
scripts/mre export-prompts --tasks tasks/core.zh.jsonl --profile smoke --out runs/manual_prompts.jsonl
scripts/mre import-results --tasks tasks/core.zh.jsonl --outputs runs/manual_outputs.jsonl --out-dir runs --run-id manual_agent
```

## Target selection

Consult `references/ide-targets.md` when selecting an IDE/agent package. Use `web-manual` for web-only products such as Qwen Web, GLM/Z.ai Web, Kimi, DeepSeek, Doubao, Yuanbao, Claude Web, or Gemini Web.

## Interpretation

Consult `references/interpretation.md` before stating conclusions. Do not call a model degraded based on a single run, a single task, or raw reasoning-token changes alone.
"""

CLAUDE_SKILL_MD = CHATGPT_SKILL_MD

WORKFLOW_MD = """# Workflow

## Standard path

1. Run `budget` for the selected profile/depth.
2. Run `mock smoke quick` once after unpacking the package.
3. Run the target agent with `smoke quick`.
4. Escalate to `standard confirm` only if the smoke run exposes a plausible issue.
5. Use `full confirm` for final confirmation.
6. Compare candidate and baseline result files.

## Cost controls

Use `--max-requests` to cap calls and `--max-observed-tokens` to stop when observed input+output usage crosses a threshold.

## Evidence standard

Treat `smoke quick` as a screening run. Treat `standard confirm` or `full confirm` plus paired comparison and manual review as stronger evidence.
"""

RUNNERS_MD = """# Runners

## Direct runners

- `codex` / `codex_cli`
- `claude` / `claude_cli`
- `claude_api`
- `gemini` / `gemini_cli`
- `gemini_api`
- `opencode` / `opencode_cli`
- `hermes`
- `qwen_api`
- `glm_api`
- `openai_api`
- `openai_compatible`

## Universal runners

Use these when the agent has no exact adapter:

- `http`: call an HTTP endpoint that accepts `{prompt, model, schema}`.
- `subprocess`: call any local command with placeholders `{prompt_file}`, `{schema_path}`, `{final_out_path}`, `{model}`.
- `export-prompts` / `import-results`: use for web-only or manual agents.

## API aliases

`qwen_api` and `glm_api` route through OpenAI-compatible chat completions. Pass `--agent-url`, `--agent-api-key`, and `--model`, or set provider-specific environment variables documented in the generated API preset package.
"""

INTERPRETATION_MD = """# Interpreting Results

Prefer these signals:

- paired baseline/candidate regressions and improvements
- task-majority stable regressions
- majority accuracy
- consistency rate
- domain-level concentration of failures
- tool violation and format error rates
- actual token totals when the runner reports usage

Avoid these mistakes:

- concluding degradation from one failed task
- comparing runs with different task sets without checking warnings
- treating reasoning tokens as a direct intelligence metric
- ignoring task ambiguity or grader mistakes
"""

IDE_TARGETS_MD = """# IDE and Agent Target Selection

Use a strong target when available. Use best-effort targets when your IDE has no verified native skill format but can read project rule files. Use `generic` only when there is no closer match.

## Strong targets

- `chatgpt`: standard ChatGPT Skill zip.
- `claude`: Claude / Claude Code.
- `codex`: AGENTS.md package.
- `gemini`: GEMINI.md package.
- `windsurf`: .devin/.windsurf rules plus AGENTS.md.
- `cline`: .clinerules plus AGENTS.md.
- `github-copilot`: .github/copilot-instructions.md and .github/instructions/*.instructions.md.
- `opencode`: AGENTS.md and OPENCODE.md.

## Best-effort AI IDE targets

- `cursor`
- `roo-code`
- `kilo-code`
- `zed`
- `aider`
- `trae`
- `continue`
- `junie`
- `kiro`
- `augment-code`
- `warp`
- `ai-ide`

Best-effort packages include AGENTS.md fallback and common rule-file locations. Verify your IDE version loads the generated files.

## Web/manual targets

Use `web-manual` or a web-specific alias for Qwen Web, GLM/Z.ai Web, Kimi, DeepSeek, Doubao, Yuanbao, Claude Web, or Gemini Web. These packages are for prompt export/import, not local executable skill installation.
"""

WEB_MANUAL_MD = """# Web Manual Workflow

Use this workflow for web-only products that cannot install or execute local skills.

1. Run `./scripts/mre export-prompts --tasks tasks/core.zh.jsonl --profile smoke --out runs/manual_prompts.jsonl`.
2. Copy prompts into the web product or upload the prompt file if supported.
3. Require each answer to be JSON with `answer`, `confidence`, and `reasoning_summary`.
4. Save results as JSONL matching `templates/manual_outputs.template.jsonl`.
5. Run `./scripts/mre import-results --tasks tasks/core.zh.jsonl --outputs runs/manual_outputs.jsonl --out-dir runs --run-id web_agent`.
6. Compare against baseline with `./scripts/mre compare`.
"""

WEB_AGENT_INSTRUCTIONS_MD = """# Web Agent Instructions for {target}

You are being evaluated with Model Regression Eval. For each prompt, answer without external tools unless the prompt explicitly allows tools.

Return only JSON:

```json
{{"answer":"...","confidence":0.0,"reasoning_summary":"..."}}
```

Rules:

- Put the final answer in `answer` only.
- Use a number between 0 and 1 for `confidence`.
- Keep `reasoning_summary` to one concise sentence.
- Do not include markdown outside the JSON object.
"""

WEB_SYSTEM_PROMPT_MD = """Answer each evaluation prompt as a standalone task. Return only a JSON object with keys `answer`, `confidence`, and `reasoning_summary`. Do not use external tools unless explicitly allowed by the prompt.
"""

MANUAL_OUTPUT_TEMPLATE_JSONL = '''{"task_id":"example_task_id","repeat":1,"answer":"example answer","confidence":0.9,"reasoning_summary":"brief rationale"}
'''

API_PRESET_MD = """# API Preset

This package is intended for `{runner}` through an OpenAI-compatible or provider-compatible endpoint.

Environment variables:

- `{env_url}`: base URL, usually ending in `/v1` for OpenAI-compatible services.
- `{env_key}`: API key.
- `{env_model}`: model name.

Example:

```bash
export {env_url}=http://localhost:8000/v1
export {env_key}=...
export {env_model}={example_model}
./scripts/mre run --runner {runner} --tasks tasks/core.zh.jsonl --profile smoke --depth quick --model ${env_model}
```

If the provider is not exactly compatible, use `--runner http` or `--runner subprocess`.
"""
