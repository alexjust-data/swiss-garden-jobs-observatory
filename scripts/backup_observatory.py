#!/usr/bin/env python
"""Create and verify one no-overwrite PostgreSQL Observatory backup."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


sys.path.insert(0, str(_project_root() / "src"))

from operations.backup import BackupConfig, backup_plan, create_backup  # noqa: E402
from operations.scheduling import SchedulingError  # noqa: E402


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--repo-root", type=Path, default=_project_root())
    value.add_argument("--output-root", type=Path, required=True)
    value.add_argument("--expected-head", required=True)
    value.add_argument("--pg-dump", type=Path, required=True)
    value.add_argument("--pg-restore", type=Path, required=True)
    value.add_argument("--dry-run", action="store_true")
    return value


def main() -> int:
    args = parser().parse_args()
    try:
        config = BackupConfig.create(
            repo_root=args.repo_root,
            output_root=args.output_root,
            expected_head=args.expected_head,
            pg_dump=args.pg_dump,
            pg_restore=args.pg_restore,
        )
        if args.dry_run:
            print(json.dumps(backup_plan(config, environment=os.environ), sort_keys=True))
            return 0
        dump, manifest, evidence = create_backup(config)
    except SchedulingError as exc:
        print(f"BACKUP_CONFIGURATION_ERROR: {exc}", file=sys.stderr)
        return 9
    print(
        json.dumps(
            {
                "dump": str(dump),
                "manifest": str(manifest),
                "evidence_sha256": evidence["evidence_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

