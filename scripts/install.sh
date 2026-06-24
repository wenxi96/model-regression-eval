#!/usr/bin/env sh
set -eu
TARGET="${TARGET:-auto}"
DRY_RUN="${DRY_RUN:-1}"
INSTALL_MODE="${INSTALL_MODE:-skill}"
GLOBAL_SKILLS_DIR="${GLOBAL_SKILLS_DIR:-}"
SKILLS_DIR="${SKILLS_DIR:-}"
SKILL_DIR_PRESET="${SKILL_DIR_PRESET:-}"
OVERWRITE="${OVERWRITE:-0}"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --target=*) TARGET="${1#*=}"; shift ;;
    --mode|--install-mode) INSTALL_MODE="$2"; shift 2 ;;
    --mode=*|--install-mode=*) INSTALL_MODE="${1#*=}"; shift ;;
    --global-skills-dir) GLOBAL_SKILLS_DIR="$2"; shift 2 ;;
    --global-skills-dir=*) GLOBAL_SKILLS_DIR="${1#*=}"; shift ;;
    --skills-dir) SKILLS_DIR="$2"; shift 2 ;;
    --skills-dir=*) SKILLS_DIR="${1#*=}"; shift ;;
    --skill-dir-preset) SKILL_DIR_PRESET="$2"; shift 2 ;;
    --skill-dir-preset=*) SKILL_DIR_PRESET="${1#*=}"; shift ;;
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
URL="https://github.com/wenxi96/model-regression-eval/archive/refs/heads/main.zip"
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
    raise SystemExit(f'--mode must be skill or rules, got {mode!r}')
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
