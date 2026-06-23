from pathlib import Path
import json
import zipfile

from model_regression_eval import installer as installer_module
from model_regression_eval.cli import main
from model_regression_eval.installer import (
    MANAGED_BEGIN,
    detect_system,
    detect_target,
    install_from_any_source,
    install_from_project,
    install_skillpack_directory,
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


def test_bootstrap_auto_and_windows_project_root(tmp_path):
    script = tmp_path / "install.ps1"
    write_bootstrap_script("windows", script, source_url="https://example.invalid/model_regression_eval.zip")
    text = script.read_text(encoding="utf-8")
    assert "$ProjectRoot = (Get-Location).Path" in text
    assert '"--project-root", $ProjectRoot' in text

    auto_script = tmp_path / "install_auto.sh"
    write_bootstrap_script("auto", auto_script, source_url="https://example.invalid/model_regression_eval.zip")
    assert auto_script.exists()

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
