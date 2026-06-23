from pathlib import Path
import subprocess
import sys
import zipfile

from model_regression_eval.skillpacks import CANONICAL_TARGETS, TARGET_SPECS, build_skillpacks, normalize_skill_target
from model_regression_eval.cli import main


def test_skill_target_aliases_and_fallback():
    assert normalize_skill_target("claude-code") == "claude"
    assert normalize_skill_target("gemini_cli") == "gemini"
    assert normalize_skill_target("copilot") == "github-copilot"
    assert normalize_skill_target("zcode") == "zed"
    assert normalize_skill_target("qwen") == "qwen-web"
    assert normalize_skill_target("glm") == "glm-web"
    assert normalize_skill_target("unknown-agent") == "generic"


def test_target_registry_has_support_labels():
    assert TARGET_SPECS["windsurf"].support == "strong"
    assert TARGET_SPECS["cursor"].support == "best_effort"
    assert TARGET_SPECS["qwen-web"].support == "manual_web"
    assert TARGET_SPECS["qwen-api"].support == "api_preset"


def test_build_chatgpt_skill_zip_contains_skill_and_full_task_set(tmp_path):
    built = build_skillpacks(target="chatgpt", out_dir=tmp_path)
    assert len(built) == 1
    path = built[0].package_path
    assert path.name == "skill.zip"
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        assert "model-regression-eval-chatgpt/SKILL.md" in names
        assert "model-regression-eval-chatgpt/agents/openai.yaml" in names
        assert "model-regression-eval-chatgpt/scripts/mre.py" in names
        task_name = "model-regression-eval-chatgpt/assets/eval_project/tasks/core.zh.jsonl"
        assert task_name in names
        task_text = zf.read(task_name).decode("utf-8")
        assert sum(1 for line in task_text.splitlines() if line.strip()) == 300


def test_build_windsurf_contains_native_and_fallback_rule_files(tmp_path):
    built = build_skillpacks(target="windsurf", out_dir=tmp_path)
    assert built[0].support == "strong"
    with zipfile.ZipFile(built[0].package_path) as zf:
        names = set(zf.namelist())
        prefix = "model-regression-eval-windsurf/"
        assert prefix + "AGENTS.md" in names
        assert prefix + ".devin/rules/model-regression-eval.md" in names
        assert prefix + ".windsurf/rules/model-regression-eval.md" in names
        assert prefix + ".windsurfrules" in names


def test_posix_mre_script_falls_back_between_python_commands(tmp_path):
    built = build_skillpacks(target="generic", out_dir=tmp_path, package_format="directory")
    script = built[0].package_path / "scripts" / "mre"
    text = script.read_text(encoding="utf-8")
    assert "command -v python3" in text
    assert "command -v python" in text
    assert 'exec "$PY" "$SCRIPT_DIR/mre.py" "$@"' in text


def test_mre_python_wrapper_preserves_caller_output_directory(tmp_path):
    built = build_skillpacks(target="generic", out_dir=tmp_path / "build", package_format="directory")
    project = tmp_path / "third_party_project"
    project.mkdir()
    out_md = project / "budget.md"
    proc = subprocess.run(
        [
            sys.executable,
            str(built[0].package_path / "scripts" / "mre.py"),
            "budget",
            "--tasks",
            "tasks/core.zh.jsonl",
            "--profile",
            "smoke",
            "--depth",
            "quick",
            "--out-md",
            "budget.md",
        ],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert out_md.exists()
    assert "Tasks: 40" in out_md.read_text(encoding="utf-8")


def test_build_ai_ide_contains_multiple_rule_files(tmp_path):
    built = build_skillpacks(target="ai-ide", out_dir=tmp_path)
    assert built[0].support == "best_effort"
    with zipfile.ZipFile(built[0].package_path) as zf:
        names = set(zf.namelist())
        prefix = "model-regression-eval-ai-ide/"
        assert prefix + "AGENTS.md" in names
        assert prefix + "CLAUDE.md" in names
        assert prefix + "GEMINI.md" in names
        assert prefix + ".cursor/rules/model-regression-eval.mdc" in names
        assert prefix + ".github/copilot-instructions.md" in names
        assert prefix + ".clinerules/model-regression-eval.md" in names


def test_build_web_manual_contains_manual_instructions(tmp_path):
    built = build_skillpacks(target="qwen-web", out_dir=tmp_path)
    assert built[0].target == "qwen-web"
    assert built[0].support == "manual_web"
    with zipfile.ZipFile(built[0].package_path) as zf:
        names = set(zf.namelist())
        prefix = "model-regression-eval-qwen-web/"
        assert prefix + "WEB_AGENT_INSTRUCTIONS.md" in names
        assert prefix + "SYSTEM_PROMPT.md" in names
        assert prefix + "templates/manual_outputs.template.jsonl" in names


def test_build_api_preset_contains_api_preset_doc(tmp_path):
    built = build_skillpacks(target="glm-api", out_dir=tmp_path)
    assert built[0].support == "api_preset"
    with zipfile.ZipFile(built[0].package_path) as zf:
        names = set(zf.namelist())
        prefix = "model-regression-eval-glm-api/"
        assert prefix + "API_PRESET.md" in names
        assert "GLM_API_KEY" in zf.read(prefix + "API_PRESET.md").decode("utf-8")


def test_build_all_skillpacks_cli(tmp_path):
    out = tmp_path / "dist"
    code = main(["skill", "build", "--target", "all", "--out-dir", str(out)])
    assert code == 0
    assert (out / "skillpacks.manifest.json").exists()
    for target in CANONICAL_TARGETS:
        assert (out / f"model-regression-eval-{target}.zip").exists()


def test_build_unknown_target_falls_back_to_generic(tmp_path):
    out = tmp_path / "dist"
    code = main(["skill", "build", "--target", "some-new-agent", "--out-dir", str(out)])
    assert code == 0
    assert (out / "model-regression-eval-generic.zip").exists()
