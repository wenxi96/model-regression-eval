#!/usr/bin/env sh
set -eu
TARGET="${TARGET:-auto}"
DRY_RUN="${DRY_RUN:-1}"
TMPDIR="$(mktemp -d)"
PROJECT_ROOT="$(pwd -P)"
trap 'rm -rf "$TMPDIR"' EXIT
if command -v python3 >/dev/null 2>&1; then PY=python3; elif command -v python >/dev/null 2>&1; then PY=python; else echo "Python 3 is required" >&2; exit 1; fi
URL="https://github.com/wenxi96/model-regression-eval/archive/refs/heads/main.zip"
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
