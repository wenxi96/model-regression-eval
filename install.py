#!/usr/bin/env python3
from model_regression_eval.installer import install_from_any_source
import argparse, json
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description='Install Model Regression Eval into a project.')
    p.add_argument('--target', default='auto')
    p.add_argument('--project-root', default='.')
    p.add_argument('--from-url', default=None)
    p.add_argument('--from-git', default=None)
    p.add_argument('--ref', default=None)
    p.add_argument('--sha256', default=None)
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--overwrite', action='store_true')
    p.add_argument('--no-backup', action='store_true')
    args = p.parse_args()
    manifest = install_from_any_source(
        from_url=args.from_url,
        from_git=args.from_git,
        ref=args.ref,
        sha256=args.sha256,
        target=args.target,
        install_root=Path(args.project_root),
        dry_run=args.dry_run,
        overwrite=args.overwrite,
        backup=not args.no_backup,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
