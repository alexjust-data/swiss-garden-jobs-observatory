"""External scheduling helpers for one governed Observatory Cycle."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

WRAPPER_VERSION = "observatory-scheduler-wrapper-v0.1"
PROCESS_TIMEOUT_EXIT = 124
PROCESS_EXECUTION_ERROR_EXIT = 125
REQUIRED_ENVIRONMENT = (
    "DJANGO_SECRET_KEY",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "JOB_OBSERVATORY_RAW_STORE_PATH",
    "JOB_OBSERVATORY_OPERATIONAL_RAW_STORE_PATH",
    "JOB_OBSERVATORY_RAW_LINEAGE_MANIFEST_SHA256",
)

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


class SchedulingError(RuntimeError):
    """Fail-closed external scheduling error."""


@dataclass(frozen=True)
class ScheduledRunConfig:
    repo_root: Path
    python_executable: Path
    log_root: Path
    expected_head: str
    django_timeout_seconds: int = 14_400
    process_timeout_seconds: int = 15_000

    @classmethod
    def create(
        cls,
        *,
        repo_root: str | Path,
        python_executable: str | Path,
        log_root: str | Path,
        expected_head: str,
        django_timeout_seconds: int = 14_400,
        process_timeout_seconds: int = 15_000,
    ) -> ScheduledRunConfig:
        repo = Path(repo_root)
        python = Path(python_executable)
        logs = Path(log_root)
        if not repo.is_absolute() or not python.is_absolute() or not logs.is_absolute():
            raise SchedulingError("repository, Python, and log paths must be absolute")
        repo = repo.resolve()
        python = python.resolve()
        logs = logs.resolve()
        if not (repo / "manage.py").is_file() or not (repo / ".git").exists():
            raise SchedulingError("repository root is not a Git worktree with manage.py")
        if not python.is_file():
            raise SchedulingError("configured Python executable does not exist")
        if _inside_git_worktree(logs):
            raise SchedulingError("scheduled log root must be outside every Git worktree")
        if not _SHA_RE.fullmatch(expected_head):
            raise SchedulingError("expected deployment HEAD must be a 40-character lowercase SHA")
        if django_timeout_seconds < 60 or django_timeout_seconds > 86_400:
            raise SchedulingError("Django timeout must be between 60 and 86400 seconds")
        if process_timeout_seconds <= django_timeout_seconds or process_timeout_seconds > 90_000:
            raise SchedulingError("process timeout must be greater than the Django timeout")
        return cls(
            repo_root=repo,
            python_executable=python,
            log_root=logs,
            expected_head=expected_head,
            django_timeout_seconds=django_timeout_seconds,
            process_timeout_seconds=process_timeout_seconds,
        )


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_datetime(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise SchedulingError("scheduled timestamps must be timezone-aware")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _inside_git_worktree(path: Path) -> bool:
    candidate = path.resolve()
    for current in (candidate, *candidate.parents):
        if (current / ".git").exists():
            return True
    return False


def _run_text(
    argv: Sequence[str],
    *,
    cwd: Path,
    timeout: int,
    runner: CommandRunner = subprocess.run,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return runner(
        list(argv),
        cwd=cwd,
        env=dict(env) if env is not None else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        shell=False,
    )


def validate_environment(environment: Mapping[str, str]) -> None:
    missing = [name for name in REQUIRED_ENVIRONMENT if not environment.get(name, "").strip()]
    if missing:
        raise SchedulingError(f"required scheduler environment is missing: {', '.join(missing)}")


def validate_repository(
    config: ScheduledRunConfig,
    *,
    runner: CommandRunner = subprocess.run,
) -> dict[str, object]:
    head = _run_text(
        ("git", "-c", f"safe.directory={config.repo_root.as_posix()}", "rev-parse", "HEAD"),
        cwd=config.repo_root,
        timeout=30,
        runner=runner,
    )
    if head.returncode != 0:
        raise SchedulingError("cannot read deployment Git HEAD")
    actual_head = head.stdout.strip()
    if actual_head != config.expected_head:
        raise SchedulingError("deployment Git HEAD differs from the configured audited SHA")
    status = _run_text(
        (
            "git",
            "-c",
            f"safe.directory={config.repo_root.as_posix()}",
            "status",
            "--porcelain=v1",
            "--untracked-files=normal",
        ),
        cwd=config.repo_root,
        timeout=30,
        runner=runner,
    )
    if status.returncode != 0:
        raise SchedulingError("cannot inspect deployment Git worktree")
    if status.stdout.strip():
        raise SchedulingError("deployment Git worktree is not clean")
    return {"head": actual_head, "clean": True}


def cycle_argv(config: ScheduledRunConfig) -> tuple[str, ...]:
    return (
        str(config.python_executable),
        str(config.repo_root / "manage.py"),
        "run_daily_observatory",
        "--trigger",
        "SCHEDULED",
        "--timeout-seconds",
        str(config.django_timeout_seconds),
        "--json",
    )


def status_argv(config: ScheduledRunConfig) -> tuple[str, ...]:
    return (
        str(config.python_executable),
        str(config.repo_root / "manage.py"),
        "observatory_status",
        "--json",
    )


def scheduled_plan(
    config: ScheduledRunConfig,
    *,
    environment: Mapping[str, str],
    runner: CommandRunner = subprocess.run,
) -> dict[str, object]:
    validate_environment(environment)
    repository = validate_repository(config, runner=runner)
    return {
        "wrapper_version": WRAPPER_VERSION,
        "repository": str(config.repo_root),
        "git_head": repository["head"],
        "clean": repository["clean"],
        "python": str(config.python_executable),
        "log_root": str(config.log_root),
        "django_timeout_seconds": config.django_timeout_seconds,
        "process_timeout_seconds": config.process_timeout_seconds,
        "cycle_argv": list(cycle_argv(config)),
        "status_argv": list(status_argv(config)),
        "environment_names": list(REQUIRED_ENVIRONMENT),
        "database_or_raw_writes": 0,
        "source_http_requests": 0,
        "provider_http_requests": 0,
    }


def _parse_json_line(output: str) -> dict[str, Any] | None:
    for line in reversed(output.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _bounded_cycle_summary(value: dict[str, Any] | None) -> dict[str, object] | None:
    if value is None:
        return None
    allowed = (
        "cycle_id",
        "status",
        "operational_health",
        "cutoff",
        "sources_selected",
        "source_successful",
        "blocked_selected",
        "dedup_run",
        "premium_run",
        "dashboard_snapshot",
        "readiness_assessment",
        "exact_cycle_retry_reused",
    )
    return {key: value.get(key) for key in allowed if key in value}


def _bounded_status_summary(value: dict[str, Any] | None) -> dict[str, object] | None:
    if value is None:
        return None
    latest = value.get("latest_cycle")
    latest_bounded: dict[str, object] | None = None
    if isinstance(latest, dict):
        latest_bounded = {
            key: latest.get(key)
            for key in ("cycle_id", "status", "operational_health", "cutoff")
            if key in latest
        }
    return {
        "latest_cycle": latest_bounded,
        "last_successful_cycle_id": value.get("last_successful_cycle_id"),
        "pit_cutoff": value.get("pit_cutoff"),
        "headline_available": value.get("headline_available"),
    }


def _publish_file_no_overwrite(
    source: Path,
    target: Path,
    *,
    collision_message: str,
    platform_name: str | None = None,
) -> None:
    platform = os.name if platform_name is None else platform_name
    try:
        if platform == "nt":
            os.rename(source, target)
        else:
            os.link(source, target)
    except FileExistsError as exc:
        raise SchedulingError(collision_message) from exc


def _atomic_publish(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=".scheduled-", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _publish_file_no_overwrite(
            temporary,
            path,
            collision_message=f"scheduled invocation envelope already exists: {path.name}",
        )
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def run_scheduled_cycle(
    config: ScheduledRunConfig,
    *,
    environment: Mapping[str, str] | None = None,
    runner: CommandRunner = subprocess.run,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> tuple[int, Path, dict[str, object]]:
    active_environment = dict(os.environ if environment is None else environment)
    plan = scheduled_plan(config, environment=active_environment, runner=runner)
    started = now()
    cycle_stdout = ""
    cycle_stderr = ""
    timed_out = False
    process_error = False
    try:
        cycle = _run_text(
            cycle_argv(config),
            cwd=config.repo_root,
            timeout=config.process_timeout_seconds,
            runner=runner,
            env=active_environment,
        )
        cycle_exit = cycle.returncode
        cycle_stdout = cycle.stdout
        cycle_stderr = cycle.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        cycle_exit = PROCESS_TIMEOUT_EXIT
        cycle_stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        cycle_stderr = exc.stderr if isinstance(exc.stderr, str) else ""
    except OSError:
        process_error = True
        cycle_exit = PROCESS_EXECUTION_ERROR_EXIT
        cycle_stdout = ""
        cycle_stderr = ""

    status_timed_out = False
    status_process_error = False
    try:
        status = _run_text(
            status_argv(config),
            cwd=config.repo_root,
            timeout=120,
            runner=runner,
            env=active_environment,
        )
        status_exit = status.returncode
        status_stdout = status.stdout
        status_stderr = status.stderr
    except subprocess.TimeoutExpired as exc:
        status_timed_out = True
        status_exit = PROCESS_TIMEOUT_EXIT
        status_stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        status_stderr = exc.stderr if isinstance(exc.stderr, str) else ""
    except OSError:
        status_process_error = True
        status_exit = PROCESS_EXECUTION_ERROR_EXIT
        status_stdout = ""
        status_stderr = ""

    finished = now()
    stable_evidence: dict[str, object] = {
        "wrapper_version": WRAPPER_VERSION,
        "git_head": plan["git_head"],
        "cycle_argv": plan["cycle_argv"],
        "cycle_exit_code": cycle_exit,
        "cycle_process_timed_out": timed_out,
        "cycle_process_error": process_error,
        "cycle_stdout_sha256": sha256_bytes(cycle_stdout.encode("utf-8")),
        "cycle_stderr_sha256": sha256_bytes(cycle_stderr.encode("utf-8")),
        "cycle_summary": _bounded_cycle_summary(_parse_json_line(cycle_stdout)),
        "status_exit_code": status_exit,
        "status_process_timed_out": status_timed_out,
        "status_process_error": status_process_error,
        "status_stdout_sha256": sha256_bytes(status_stdout.encode("utf-8")),
        "status_stderr_sha256": sha256_bytes(status_stderr.encode("utf-8")),
        "status_summary": _bounded_status_summary(_parse_json_line(status_stdout)),
    }
    invocation_fingerprint = sha256_bytes(canonical_json_bytes(stable_evidence))
    envelope: dict[str, object] = {
        "schema_version": WRAPPER_VERSION,
        "invocation_id": str(uuid.uuid4()),
        "started_at": canonical_datetime(started),
        "finished_at": canonical_datetime(finished),
        "duration_milliseconds": max(0, int((finished - started).total_seconds() * 1000)),
        "stable_evidence": stable_evidence,
        "invocation_fingerprint": invocation_fingerprint,
    }
    filename = (
        "scheduled-"
        + started.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "-"
        + str(envelope["invocation_id"])
        + ".json"
    )
    target = config.log_root / filename
    _atomic_publish(target, canonical_json_bytes(envelope) + b"\n")
    return cycle_exit, target, envelope
