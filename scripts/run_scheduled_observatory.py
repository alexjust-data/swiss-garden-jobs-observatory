#!/usr/bin/env python
"""Run one externally scheduled governed Observatory Cycle."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


sys.path.insert(0, str(_project_root() / "src"))

from operations.scheduling import (  # noqa: E402
    ScheduledRunConfig,
    SchedulingError,
    run_scheduled_cycle,
    scheduled_plan,
)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--repo-root", type=Path, default=_project_root())
    value.add_argument("--python", type=Path, default=Path(sys.executable))
    value.add_argument("--log-root", type=Path, required=True)
    value.add_argument("--expected-head", required=True)
    value.add_argument("--django-timeout-seconds", type=int, default=14_400)
    value.add_argument("--process-timeout-seconds", type=int, default=15_000)
    value.add_argument("--dry-run", action="store_true")
    return value


def main() -> int:
    args = parser().parse_args()
    try:
        config = ScheduledRunConfig.create(
            repo_root=args.repo_root,
            python_executable=args.python,
            log_root=args.log_root,
            expected_head=args.expected_head,
            django_timeout_seconds=args.django_timeout_seconds,
            process_timeout_seconds=args.process_timeout_seconds,
        )
        if args.dry_run:
            print(json.dumps(scheduled_plan(config, environment=os.environ), sort_keys=True))
            return 0
        exit_code, envelope_path, envelope = run_scheduled_cycle(config)
    except SchedulingError as exc:
        print(f"SCHEDULER_CONFIGURATION_ERROR: {exc}", file=sys.stderr)
        return 9
    print(
        json.dumps(
            {
                "exit_code": exit_code,
                "invocation_fingerprint": envelope["invocation_fingerprint"],
                "invocation_log": str(envelope_path),
            },
            sort_keys=True,
        )
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

