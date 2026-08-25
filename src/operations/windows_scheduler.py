"""Deterministic Windows Task Scheduler plan for the Observatory."""

from __future__ import annotations

import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from operations.scheduling import (
    ScheduledRunConfig,
    SchedulingError,
    scheduled_plan,
)

TASK_PLAN_VERSION = "windows-observatory-task-v0.1"
WINDOWS_TIME_ZONE_IDS = (
    "W. Europe Standard Time",
    "Romance Standard Time",
)
TASK_NAMESPACE = "http://schemas.microsoft.com/windows/2004/02/mit/task"
_TASK_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}$")
CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class WindowsTaskConfig:
    task_name: str
    start_boundary: str
    scheduled_run: ScheduledRunConfig

    @classmethod
    def create(
        cls,
        *,
        task_name: str,
        start_boundary: str,
        scheduled_run: ScheduledRunConfig,
    ) -> WindowsTaskConfig:
        if not _TASK_NAME_RE.fullmatch(task_name):
            raise SchedulingError("Windows task name contains unsupported characters")
        try:
            parsed = datetime.strptime(start_boundary, "%Y-%m-%dT%H:%M:%S")
        except ValueError as exc:
            raise SchedulingError(
                "start boundary must be local time formatted YYYY-MM-DDTHH:MM:SS"
            ) from exc
        if parsed.second != 0:
            raise SchedulingError("scheduled start boundary must use a whole minute")
        return cls(
            task_name=task_name,
            start_boundary=start_boundary,
            scheduled_run=scheduled_run,
        )


def _element(parent: ET.Element, name: str, text: str | None = None) -> ET.Element:
    value = ET.SubElement(parent, f"{{{TASK_NAMESPACE}}}{name}")
    if text is not None:
        value.text = text
    return value


def task_arguments(config: WindowsTaskConfig) -> tuple[str, ...]:
    run = config.scheduled_run
    return (
        str(run.repo_root / "scripts" / "run_scheduled_observatory.py"),
        "--repo-root",
        str(run.repo_root),
        "--python",
        str(run.python_executable),
        "--log-root",
        str(run.log_root),
        "--expected-head",
        run.expected_head,
        "--django-timeout-seconds",
        str(run.django_timeout_seconds),
        "--process-timeout-seconds",
        str(run.process_timeout_seconds),
    )


def build_task_xml(config: WindowsTaskConfig) -> str:
    ET.register_namespace("", TASK_NAMESPACE)
    task = ET.Element(f"{{{TASK_NAMESPACE}}}Task", {"version": "1.4"})
    registration = _element(task, "RegistrationInfo")
    _element(registration, "Description", "Swiss Garden Jobs Observatory daily governed cycle")
    triggers = _element(task, "Triggers")
    calendar = _element(triggers, "CalendarTrigger")
    _element(calendar, "StartBoundary", config.start_boundary)
    _element(calendar, "Enabled", "true")
    schedule = _element(calendar, "ScheduleByDay")
    _element(schedule, "DaysInterval", "1")
    principals = _element(task, "Principals")
    principal = _element(principals, "Principal")
    principal.set("id", "Author")
    _element(principal, "LogonType", "InteractiveToken")
    _element(principal, "RunLevel", "LeastPrivilege")
    settings = _element(task, "Settings")
    _element(settings, "MultipleInstancesPolicy", "IgnoreNew")
    _element(settings, "DisallowStartIfOnBatteries", "false")
    _element(settings, "StopIfGoingOnBatteries", "false")
    _element(settings, "AllowHardTerminate", "true")
    _element(settings, "StartWhenAvailable", "false")
    _element(settings, "RunOnlyIfNetworkAvailable", "true")
    _element(settings, "AllowStartOnDemand", "true")
    _element(settings, "Enabled", "true")
    _element(settings, "Hidden", "false")
    _element(settings, "ExecutionTimeLimit", f"PT{config.scheduled_run.process_timeout_seconds}S")
    _element(settings, "Priority", "7")
    actions = _element(task, "Actions")
    actions.set("Context", "Author")
    execute = _element(actions, "Exec")
    _element(execute, "Command", str(config.scheduled_run.python_executable))
    _element(execute, "Arguments", subprocess.list2cmdline(list(task_arguments(config))))
    _element(execute, "WorkingDirectory", str(config.scheduled_run.repo_root))
    return ET.tostring(task, encoding="unicode", xml_declaration=True)


def task_plan(config: WindowsTaskConfig) -> dict[str, object]:
    return {
        "plan_version": TASK_PLAN_VERSION,
        "task_name": config.task_name,
        "start_boundary_local": config.start_boundary,
        "timezone": "Europe/Zurich",
        "accepted_windows_time_zone_ids": list(WINDOWS_TIME_ZONE_IDS),
        "program": str(config.scheduled_run.python_executable),
        "arguments": list(task_arguments(config)),
        "working_directory": str(config.scheduled_run.repo_root),
        "multiple_instances": "IgnoreNew",
        "start_when_available": False,
        "execution_time_limit_seconds": config.scheduled_run.process_timeout_seconds,
        "credentials_in_arguments": False,
        "registration_performed": False,
    }


def _canonical_xml(value: str) -> str:
    try:
        return ET.canonicalize(value)
    except ET.ParseError as exc:
        raise SchedulingError("existing Windows task XML is malformed") from exc


def validate_windows_time_zone(*, runner: CommandRunner = subprocess.run) -> None:
    result = runner(
        ["tzutil.exe", "/g"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
        shell=False,
    )
    if result.returncode != 0 or result.stdout.strip() not in WINDOWS_TIME_ZONE_IDS:
        raise SchedulingError("Windows host timezone is not governed Europe/Zurich time")


def register_task(
    config: WindowsTaskConfig,
    *,
    environment: Mapping[str, str],
    git_runner: CommandRunner = subprocess.run,
    runner: CommandRunner = subprocess.run,
) -> str:
    if not (config.scheduled_run.repo_root / "scripts" / "run_scheduled_observatory.py").is_file():
        raise SchedulingError("scheduled wrapper is missing from deployment repository")
    scheduled_plan(
        config.scheduled_run,
        environment=environment,
        runner=git_runner,
    )
    validate_windows_time_zone(runner=runner)
    intended = build_task_xml(config)
    query = runner(
        ["schtasks.exe", "/Query", "/TN", config.task_name, "/XML", "ONE"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
        shell=False,
    )
    if query.returncode == 0:
        if _canonical_xml(query.stdout) != _canonical_xml(intended):
            raise SchedulingError("existing Windows task conflicts with governed task plan")
        return "REUSED_IDENTICAL"

    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".xml", encoding="utf-8", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(intended)
        created = runner(
            ["schtasks.exe", "/Create", "/TN", config.task_name, "/XML", str(temporary)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
            shell=False,
        )
        if created.returncode != 0:
            raise SchedulingError("Windows Task Scheduler registration failed")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return "CREATED"
