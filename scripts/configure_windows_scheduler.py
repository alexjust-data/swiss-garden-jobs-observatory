#!/usr/bin/env python
"""Plan or explicitly register the Windows daily Observatory task."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


sys.path.insert(0, str(_project_root() / "src"))

from operations.scheduling import ScheduledRunConfig, SchedulingError  # noqa: E402
from operations.windows_scheduler import (  # noqa: E402
    WindowsTaskConfig,
    build_task_xml,
    register_task,
    task_plan,
)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--task-name", default="Swiss Garden Jobs Observatory Daily")
    value.add_argument("--start-boundary", required=True)
    value.add_argument("--repo-root", type=Path, default=_project_root())
    value.add_argument("--python", type=Path, default=Path(sys.executable))
    value.add_argument("--log-root", type=Path, required=True)
    value.add_argument("--expected-head", required=True)
    value.add_argument("--django-timeout-seconds", type=int, default=14_400)
    value.add_argument("--process-timeout-seconds", type=int, default=15_000)
    value.add_argument("--show-xml", action="store_true")
    value.add_argument("--apply", action="store_true")
    return value


def main() -> int:
    args = parser().parse_args()
    try:
        scheduled = ScheduledRunConfig.create(
            repo_root=args.repo_root,
            python_executable=args.python,
            log_root=args.log_root,
            expected_head=args.expected_head,
            django_timeout_seconds=args.django_timeout_seconds,
            process_timeout_seconds=args.process_timeout_seconds,
        )
        config = WindowsTaskConfig.create(
            task_name=args.task_name,
            start_boundary=args.start_boundary,
            scheduled_run=scheduled,
        )
        plan = task_plan(config)
        if args.show_xml:
            plan["task_xml"] = build_task_xml(config)
        if args.apply:
            plan["registration_result"] = register_task(config)
            plan["registration_performed"] = True
    except SchedulingError as exc:
        print(f"SCHEDULER_CONFIGURATION_ERROR: {exc}", file=sys.stderr)
        return 9
    print(json.dumps(plan, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
