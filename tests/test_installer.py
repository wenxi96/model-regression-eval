from pathlib import Path
import json
import pytest
import subprocess
import sys
import zipfile

from model_regression_eval import installer as installer_module
from model_regression_eval.cli import main
from model_regression_eval.installer import (
    MANAGED_BEGIN,
    detect_system,
    detect_target,
    install_from_any_source,
    install_from_project,
    install_skill_directory,
    install_skill_from_any_source,
    install_skillpack_directory,
    SKILL_INSTALL_NAME,
    uninstall_project,
    write_bootstrap_script,
)
from model_regression_eval.skillpacks import build_skillpacks


def test_detect_target_prefers_windsurf_rules(tmp_path):
    (tmp_path / ".windsurf" / "rules").mkdir(parents=True)
    result = detect_target(tmp_path)
    assert result.target == "windsurf"
    assert result.confidence == "high"


def test_install_dry_run_writes_nothing(tmp_path):
    manifest = install_from_project(
        project_root=Path.cwd(),
        target="codex",
        install_root=tmp_path,
        dry_run=True,
        overwrite=False,
        backup=True,
    )
    assert manifest["dry_run"] is True
    assert not (tmp_path / ".model-regression-eval").exists()
    assert any(a["path"] == "AGENTS.md" for a in manifest["actions"])


def test_install_managed_block_preserves_existing_file_and_uninstalls(tmp_path):
    (tmp_path / "AGENTS.md").write_text("Existing project rules\n", encoding="utf-8")
    manifest = install_from_project(
        project_root=Path.cwd(),
        target="codex",
        install_root=tmp_path,
        dry_run=False,
        overwrite=False,
        backup=True,
    )
    assert manifest["resolved_target"] == "codex"
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "Existing project rules" in text
    assert MANAGED_BEGIN in text
    assert (tmp_path / ".model-regression-eval" / "package" / "scripts" / "mre.py").exists()
    assert (tmp_path / ".model-regression-eval" / "install-manifest.json").exists()

    result = uninstall_project(tmp_path)
    assert any(a["status"] == "removed_block" for a in result["actions"])
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8").strip() == "Existing project rules"
    assert not (tmp_path / ".model-regression-eval" / "package").exists()


def test_install_from_skillpack_directory(tmp_path):
    build_dir = tmp_path / "build"
    built = build_skillpacks(target="windsurf", out_dir=build_dir, package_format="directory")
    target_root = tmp_path / "project"
    target_root.mkdir()
    manifest = install_skillpack_directory(source_skillpack=built[0].package_path, project_root=target_root, target="windsurf")
    assert manifest["resolved_target"] == "windsurf"
    assert (target_root / ".devin" / "rules" / "model-regression-eval.md").exists()
    assert (target_root / ".model-regression-eval" / "package" / "skillpack.manifest.json").exists()


def test_cli_install_detect_and_bootstrap(tmp_path):
    code = main(["skill", "detect", "--project-root", str(tmp_path), "--json"])
    assert code == 0
    script = tmp_path / "install.sh"
    code = main(["skill", "bootstrap", "--platform", "unix", "--out", str(script)])
    assert code == 0
    assert script.exists()
    assert "python" in script.read_text(encoding="utf-8")


def test_install_from_url_file_zip(tmp_path):
    built = build_skillpacks(target="generic", out_dir=tmp_path / "build")
    project = tmp_path / "project"
    project.mkdir()
    url = built[0].package_path.resolve().as_uri()
    manifest = install_from_any_source(from_url=url, target="generic", install_root=project)
    assert manifest["source"]["type"] == "url"
    assert (project / "AGENTS.md").exists()


def test_skillpack_contains_install_scripts(tmp_path):
    built = build_skillpacks(target="generic", out_dir=tmp_path)
    with zipfile.ZipFile(built[0].package_path) as zf:
        names = set(zf.namelist())
        prefix = "model-regression-eval-generic/"
        assert prefix + "install.py" in names
        assert prefix + "install.sh" in names
        assert prefix + "install.ps1" in names
        assert 'default="skill"' in zf.read(prefix + "install.py").decode("utf-8")


def test_top_level_shell_installer_rejects_invalid_mode_before_download():
    proc = subprocess.run(
        ["sh", "scripts/install.sh", "--mode", "skil", "--dry-run"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=5,
    )

    assert proc.returncode == 2
    assert "Invalid --mode" in proc.stderr


def test_root_install_py_defaults_to_true_skill_dry_run(tmp_path):
    project = tmp_path / "project"
    global_skills = tmp_path / "global" / "skills"
    proc = subprocess.run(
        [
            sys.executable,
            "install.py",
            "--dry-run",
            "--target",
            "codex",
            "--project-root",
            str(project),
            "--global-skills-dir",
            str(global_skills),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert proc.returncode == 0, proc.stderr
    manifest = json.loads(proc.stdout)
    assert manifest["install_type"] == "skill"
    assert manifest["resolved_target"] == "codex"
    assert manifest["dry_run"] is True
    assert not global_skills.exists()


def test_true_skill_install_dry_run_writes_nothing(tmp_path):
    global_skills = tmp_path / "global" / "skills"
    ide_skills = tmp_path / "project" / ".cursor" / "skills"

    manifest = install_skill_from_any_source(
        target="generic",
        global_skills_dir=global_skills,
        skills_dir=ide_skills,
        project_root=tmp_path / "project",
        dry_run=True,
    )

    assert manifest["install_type"] == "skill"
    assert manifest["dry_run"] is True
    assert not global_skills.exists()
    assert not ide_skills.exists()
    assert any(a["kind"] == "global_skill_dir" and a["status"] == "would_write" for a in manifest["actions"])
    assert any(a["kind"] == "skill_link" and a["status"] == "would_link" for a in manifest["actions"])


def test_true_skill_install_global_copy_and_custom_symlink(tmp_path):
    built = build_skillpacks(target="generic", out_dir=tmp_path / "build", package_format="directory")
    project = tmp_path / "project"
    global_skills = tmp_path / "global" / "skills"
    ide_skills = project / ".cursor" / "skills"

    manifest = install_skill_directory(
        source_skillpack=built[0].package_path,
        global_skills_dir=global_skills,
        skills_dir=ide_skills,
        project_root=project,
    )

    global_skill = global_skills / SKILL_INSTALL_NAME
    linked_skill = ide_skills / SKILL_INSTALL_NAME
    assert manifest["global_skill_path"] == str(global_skill.resolve())
    assert manifest["skill_path"] == str(linked_skill)
    assert (global_skill / "SKILL.md").exists()
    assert (global_skill / "scripts" / "mre.py").exists()
    assert linked_skill.is_symlink()
    assert linked_skill.resolve() == global_skill.resolve()
    assert not (project / "AGENTS.md").exists()
    assert not (project / ".model-regression-eval").exists()


def test_true_skill_install_supports_multiple_symlinks(tmp_path):
    built = build_skillpacks(target="generic", out_dir=tmp_path / "build", package_format="directory")
    global_skills = tmp_path / "global" / "skills"
    first_skills = tmp_path / "codex" / "skills"
    second_skills = tmp_path / "gemini" / "skills"

    manifest = install_skill_directory(
        source_skillpack=built[0].package_path,
        global_skills_dir=global_skills,
        skills_dir=[first_skills, second_skills],
        project_root=tmp_path / "project",
    )

    global_skill = global_skills / SKILL_INSTALL_NAME
    first_link = first_skills / SKILL_INSTALL_NAME
    second_link = second_skills / SKILL_INSTALL_NAME
    assert len(manifest["skill_links"]) == 2
    assert manifest["skill_path"] == str(first_link)
    assert first_link.is_symlink()
    assert first_link.resolve() == global_skill.resolve()
    assert second_link.is_symlink()
    assert second_link.resolve() == global_skill.resolve()


def test_display_path_does_not_follow_symlink(tmp_path, monkeypatch):
    monkeypatch.setattr(installer_module.Path, "home", lambda: tmp_path)
    target = tmp_path / ".agents" / "skills" / SKILL_INSTALL_NAME
    target.mkdir(parents=True)
    link_root = tmp_path / ".codex" / "skills"
    link_root.mkdir(parents=True)
    link = link_root / SKILL_INSTALL_NAME
    link.symlink_to(target, target_is_directory=True)

    assert installer_module._display_path(link) == "~/.codex/skills/model-regression-eval"


def test_true_skill_install_target_default_symlink(tmp_path):
    project = tmp_path / "cursor-project"
    (project / ".cursor" / "skills").mkdir(parents=True)
    global_skills = tmp_path / "global" / "skills"

    manifest = install_skill_from_any_source(
        target="auto",
        global_skills_dir=global_skills,
        project_root=project,
    )

    linked_skill = project / ".cursor" / "skills" / SKILL_INSTALL_NAME
    assert manifest["resolved_target"] == "cursor"
    assert manifest["skill_dir"]["preset"] == "cursor-project"
    assert linked_skill.is_symlink()
    assert linked_skill.resolve() == (global_skills / SKILL_INSTALL_NAME).resolve()
    assert not (project / "AGENTS.md").exists()


def test_true_skill_install_auto_generic_package_uses_project_skill_signal(tmp_path):
    built = build_skillpacks(target="generic", out_dir=tmp_path / "build", package_format="directory")
    project = tmp_path / "cursor-project"
    (project / ".cursor" / "skills").mkdir(parents=True)
    global_skills = tmp_path / "global" / "skills"

    manifest = install_skill_directory(
        source_skillpack=built[0].package_path,
        target="auto",
        global_skills_dir=global_skills,
        project_root=project,
        dry_run=True,
    )

    linked_skill = project / ".cursor" / "skills" / SKILL_INSTALL_NAME
    assert manifest["resolved_target"] == "cursor"
    assert manifest["skill_dir"]["preset"] == "cursor-project"
    assert manifest["skill_path"] == str(linked_skill)


def test_rules_install_auto_generic_package_uses_project_signal(tmp_path):
    built = build_skillpacks(target="generic", out_dir=tmp_path / "build", package_format="directory")
    project = tmp_path / "cursor-project"
    (project / ".cursor" / "skills").mkdir(parents=True)

    manifest = install_skillpack_directory(
        source_skillpack=built[0].package_path,
        project_root=project,
        target="auto",
        dry_run=True,
    )

    assert manifest["resolved_target"] == "cursor"
    assert any(action["path"].startswith(".cursor/rules/") for action in manifest["actions"])


def test_codex_skill_install_uses_agents_global_root_without_codex_symlink(tmp_path):
    global_skills = tmp_path / "agents" / "skills"

    manifest = install_skill_from_any_source(
        target="codex",
        global_skills_dir=global_skills,
        project_root=tmp_path / "project",
        dry_run=True,
    )

    assert manifest["resolved_target"] == "codex"
    assert manifest["skill_dir"]["preset"] == "agents"
    assert manifest["skill_path"] == manifest["global_skill_path"]
    assert not any(".codex/skills" in a["path"] for a in manifest["actions"])
    assert any(a["kind"] == "skill_link" and a["status"] == "not_needed" for a in manifest["actions"])


def test_wsl_windows_project_defaults_global_skill_to_windows_user_home():
    manifest = install_skill_from_any_source(
        target="cursor",
        project_root=Path("/mnt/c/Users/example/project"),
        dry_run=True,
    )

    assert manifest["global_skills_dir"] == "/mnt/c/Users/example/.agents/skills"
    assert manifest["global_skill_path"] == "/mnt/c/Users/example/.agents/skills/model-regression-eval"
    assert manifest["skill_dir"]["preset"] == "cursor-project"
    assert manifest["skill_path"] == "/mnt/c/Users/example/project/.cursor/skills/model-regression-eval"


def test_known_skill_dir_presets_do_not_claim_unconfirmed_codex_skills_path():
    presets = installer_module.skill_dir_presets(Path.cwd())
    paths = {item["path"] for item in presets}
    aliases = {alias for item in presets for alias in item["aliases"]}
    assert "~/.codex/skills" not in paths
    assert "codex" in aliases
    assert any(path.endswith("/.clinerules/skills") for path in paths)


def test_true_skill_install_validates_version_and_overwrite(tmp_path):
    built = build_skillpacks(target="generic", out_dir=tmp_path / "build", package_format="directory")
    global_skills = tmp_path / "global" / "skills"
    ide_skills = tmp_path / "ide" / "skills"

    first = install_skill_directory(
        source_skillpack=built[0].package_path,
        global_skills_dir=global_skills,
        skills_dir=ide_skills,
        project_root=tmp_path / "project",
    )
    assert any(a["status"] == "written" for a in first["actions"])

    second = install_skill_directory(
        source_skillpack=built[0].package_path,
        global_skills_dir=global_skills,
        skills_dir=ide_skills,
        project_root=tmp_path / "project",
    )
    assert any(a["status"] == "validated_current" for a in second["actions"])
    assert any(a["status"] == "validated_link" for a in second["actions"])

    manifest_path = global_skills / SKILL_INSTALL_NAME / "skillpack.manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["version"] = "0.0.0"
    manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    with pytest.raises(RuntimeError, match="version mismatch"):
        install_skill_directory(
            source_skillpack=built[0].package_path,
            global_skills_dir=global_skills,
            skills_dir=ide_skills,
            project_root=tmp_path / "project",
        )

    updated = install_skill_directory(
        source_skillpack=built[0].package_path,
        global_skills_dir=global_skills,
        skills_dir=ide_skills,
        project_root=tmp_path / "project",
        overwrite=True,
    )
    assert any(a["status"] == "updated" for a in updated["actions"])
    refreshed = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert refreshed["version"] == first["version"]


def test_true_skill_install_reuses_same_version_global_copy_for_different_targets(tmp_path):
    built_codex = build_skillpacks(target="codex", out_dir=tmp_path / "codex", package_format="directory")
    built_cursor = build_skillpacks(target="cursor", out_dir=tmp_path / "cursor", package_format="directory")
    global_skills = tmp_path / "global" / "skills"
    cursor_skills = tmp_path / "project" / ".cursor" / "skills"

    install_skill_directory(
        source_skillpack=built_codex[0].package_path,
        global_skills_dir=global_skills,
        project_root=tmp_path / "project",
    )

    reused = install_skill_directory(
        source_skillpack=built_cursor[0].package_path,
        global_skills_dir=global_skills,
        skills_dir=cursor_skills,
        project_root=tmp_path / "project",
    )

    assert any(a["status"] == "validated_current" for a in reused["actions"])
    assert any(a["status"] == "linked" for a in reused["actions"])
    assert (cursor_skills / SKILL_INSTALL_NAME).resolve() == (global_skills / SKILL_INSTALL_NAME).resolve()
    manifest = json.loads((global_skills / SKILL_INSTALL_NAME / "skillpack.manifest.json").read_text(encoding="utf-8"))
    assert manifest["target"] == "codex"


def test_skill_link_uses_windows_junction_fallback(tmp_path, monkeypatch):
    global_skill = tmp_path / "global" / "skills" / SKILL_INSTALL_NAME
    global_skill.mkdir(parents=True)
    (global_skill / "SKILL.md").write_text("skill", encoding="utf-8")
    link_root = tmp_path / "ide" / "skills"
    actions = []
    calls = []

    def fake_symlink_to(self, target, target_is_directory=False):
        raise OSError("symlink privilege missing")

    class Proc:
        returncode = 0
        stdout = "junction created"
        stderr = ""

    def fake_run(cmd, capture_output, text, **kwargs):
        calls.append(cmd)
        (link_root / SKILL_INSTALL_NAME).mkdir(parents=True)
        return Proc()

    monkeypatch.setattr(Path, "symlink_to", fake_symlink_to)
    monkeypatch.setattr(installer_module, "_is_windows_platform", lambda: True)
    monkeypatch.setattr(installer_module.subprocess, "run", fake_run)

    installer_module._link_skill_dir(
        global_skill,
        link_root,
        skill_name=SKILL_INSTALL_NAME,
        dry_run=False,
        overwrite=False,
        backup=True,
        actions=actions,
    )

    assert calls[0][:4] in (["cmd", "/c", "mklink", "/J"], ["cmd.exe", "/c", "mklink", "/J"])
    assert calls[0][4] == str(link_root / SKILL_INSTALL_NAME)
    assert calls[0][5] == str(global_skill)
    assert actions[-1].status == "linked"
    assert "junction=" in actions[-1].detail


def test_wsl_windows_mount_link_prefers_junction(monkeypatch):
    calls = []

    def fake_symlink_to(self, target, target_is_directory=False):
        raise AssertionError("WSL Windows mount links must not use POSIX symlink")

    class Proc:
        returncode = 0
        stdout = "junction created"
        stderr = ""

    def fake_run(cmd, capture_output, text, **kwargs):
        calls.append(cmd)
        return Proc()

    monkeypatch.setattr(Path, "symlink_to", fake_symlink_to)
    monkeypatch.setattr(installer_module, "_wsl_to_windows_path", lambda p: str(p).replace("/mnt/c", "C:").replace("/", "\\"))
    monkeypatch.setattr(installer_module.subprocess, "run", fake_run)

    result = installer_module._create_directory_link(
        Path("/mnt/c/Users/example/.devin/skills/model-regression-eval"),
        Path("/mnt/c/Users/example/.agents/skills/model-regression-eval"),
    )

    assert result == "junction"
    assert calls[0][:4] in (["cmd", "/c", "mklink", "/J"], ["cmd.exe", "/c", "mklink", "/J"])
    assert calls[0][4].startswith("C:")
    assert calls[0][5].startswith("C:")


def test_wsl_windows_junction_converts_non_mount_target(monkeypatch):
    converted = []
    calls = []

    class Proc:
        returncode = 0
        stdout = "junction created"
        stderr = ""

    def fake_wsl_to_windows(path):
        converted.append(str(path))
        return "WIN:" + str(path)

    def fake_run(cmd, capture_output, text, **kwargs):
        calls.append(cmd)
        return Proc()

    monkeypatch.setattr(installer_module, "_wsl_to_windows_path", fake_wsl_to_windows)
    monkeypatch.setattr(installer_module.subprocess, "run", fake_run)

    result = installer_module._create_windows_junction(
        Path("/mnt/c/Users/example/.cursor/skills/model-regression-eval"),
        Path("/home/cheng/.agents/skills/model-regression-eval"),
    )

    assert result == "junction"
    assert converted == [
        "/mnt/c/Users/example/.cursor/skills/model-regression-eval",
        "/home/cheng/.agents/skills/model-regression-eval",
    ]
    assert calls[0][4].startswith("WIN:/mnt/c/")
    assert calls[0][5].startswith("WIN:/home/")


from model_regression_eval.installer import SystemDetectResult, detect_system, install_rule_content


def test_detect_target_includes_system(tmp_path):
    result = detect_target(tmp_path)
    data = result.to_dict()
    assert "system" in data
    assert data["system"]["os"]
    assert data["system"]["recommended_launcher"]
    assert data["system"]["fallback_launcher"]


def test_detect_target_ignores_global_cli_and_env_without_project_files(tmp_path, monkeypatch):
    monkeypatch.setattr(installer_module.shutil, "which", lambda exe: f"/usr/bin/{exe}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    result = detect_target(tmp_path, include_system=False)
    assert result.target == "generic"
    assert result.confidence == "low"
    assert any("cli:claude" in signal for signal in result.signals)

    (tmp_path / "AGENTS.md").write_text("Existing project rules\n", encoding="utf-8")
    result = detect_target(tmp_path, include_system=False)
    assert result.target == "generic"
    assert result.confidence == "medium"
    assert result.signals == ("AGENTS.md",)


def test_detect_system_wsl_uses_posix_script_and_python3_fallback(monkeypatch):
    monkeypatch.setattr(installer_module.sys, "platform", "linux")
    monkeypatch.setattr(installer_module.platform_module, "release", lambda: "wsl")
    monkeypatch.setattr(installer_module, "_read_proc_version", lambda: "microsoft wsl")
    monkeypatch.setenv("SHELL", "/bin/zsh")
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    monkeypatch.delenv("WSL_INTEROP", raising=False)

    def fake_which(name):
        return f"/usr/bin/{name}" if name in {"python3", "git", "curl", "wget"} else None

    monkeypatch.setattr(installer_module.shutil, "which", fake_which)

    system = detect_system()
    assert system.is_wsl is True
    assert system.recommended_launcher == "./.model-regression-eval/package/scripts/mre"
    assert system.fallback_launcher == "python3 .model-regression-eval/package/scripts/mre.py"


def test_install_manifest_records_system(tmp_path):
    manifest = install_from_project(
        project_root=Path.cwd(),
        target="codex",
        install_root=tmp_path,
        dry_run=True,
        overwrite=False,
        backup=True,
    )
    assert "system" in manifest
    assert manifest["system"]["recommended_launcher"]
    assert manifest["detected"]["system"]["os"] == manifest["system"]["os"]


def test_install_rule_content_uses_windows_launcher():
    system = SystemDetectResult(
        os="windows",
        platform="win32",
        shell="powershell",
        is_wsl=False,
        host_os="windows",
        path_style="windows",
        python="C:\\Python\\python.exe",
        has_git=True,
        has_curl=True,
        has_wget=False,
        recommended_launcher=r".\\.model-regression-eval\\package\\scripts\\mre.bat",
        fallback_launcher=r"python .model-regression-eval\\package\\scripts\\mre.py",
        notes=("Windows detected: PowerShell/cmd examples should use mre.bat or python mre.py.",),
    )
    content = install_rule_content("codex", "AGENTS.md", system=system)
    assert r".\\.model-regression-eval\\package\\scripts\\mre.bat" in content
    assert r"tasks\core.zh.jsonl" in content
    assert "Windows detected" in content


def test_install_rule_content_marks_mock_as_self_check_only():
    content = install_rule_content("generic", "AGENTS.md")
    assert "returns the expected answer" in content
    assert "Never use `mock` results as model or agent capability evidence." in content


def test_bootstrap_auto_and_windows_project_root(tmp_path):
    script = tmp_path / "install.ps1"
    write_bootstrap_script("windows", script, source_url="https://example.invalid/model_regression_eval.zip")
    text = script.read_text(encoding="utf-8")
    assert "$ProjectRoot = (Get-Location).Path" in text
    assert '"--project-root", $ProjectRoot' in text
    assert '[string]$Mode = "skill"' in text
    assert '[string]$SkillsDir = ""' in text

    auto_script = tmp_path / "install_auto.sh"
    write_bootstrap_script("auto", auto_script, source_url="https://example.invalid/model_regression_eval.zip")
    assert auto_script.exists()
    auto_text = auto_script.read_text(encoding="utf-8")
    assert 'INSTALL_MODE="${INSTALL_MODE:-skill}"' in auto_text
    assert "Invalid --mode" in auto_text
    assert "--skills-dir) SKILLS_DIR=" in auto_text

    proc = subprocess.run(
        ["sh", str(auto_script), "--mode", "skil", "--dry-run"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=5,
    )
    assert proc.returncode == 2
    assert "Invalid --mode" in proc.stderr

def test_target_specific_skillpack_installs_own_target_when_auto(tmp_path):
    from model_regression_eval.installer import install_skillpack_directory
    from model_regression_eval.skillpacks import build_skillpacks

    out = tmp_path / "out"
    built = build_skillpacks(target="windsurf", out_dir=out, package_format="directory")
    project = tmp_path / "project"
    project.mkdir()
    manifest = install_skillpack_directory(
        source_skillpack=built[0].package_path,
        project_root=project,
        target="auto",
        dry_run=False,
    )
    assert manifest["resolved_target"] == "windsurf"
    assert (project / ".windsurf" / "rules" / "model-regression-eval.md").exists()
