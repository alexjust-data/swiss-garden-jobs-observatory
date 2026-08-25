from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from operations.backup import BackupConfig, backup_plan, create_backup
from operations.scheduling import (
    PROCESS_EXECUTION_ERROR_EXIT,
    PROCESS_TIMEOUT_EXIT,
    REQUIRED_ENVIRONMENT,
    ScheduledRunConfig,
    SchedulingError,
    _publish_file_no_overwrite,
    run_scheduled_cycle,
    scheduled_plan,
)
from operations.windows_scheduler import (
    WindowsTaskConfig,
    build_task_xml,
    register_task,
    task_plan,
    validate_windows_time_zone,
)

HEAD = "a" * 40


def environment() -> dict[str, str]:
    value = {name: f"configured-{name.lower()}" for name in REQUIRED_ENVIRONMENT}
    value["POSTGRES_PASSWORD"] = "PRIVATE-PASSWORD-CANARY"
    return value


def repository(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: external\n", encoding="utf-8")
    (repo / "manage.py").write_text("# test\n", encoding="utf-8")
    scripts = repo / "scripts"
    scripts.mkdir()
    (scripts / "run_scheduled_observatory.py").write_text("# test\n", encoding="utf-8")
    python = tmp_path / "python.exe"
    python.write_bytes(b"python")
    logs = tmp_path / "logs"
    return repo, python, logs


def config(tmp_path: Path) -> ScheduledRunConfig:
    repo, python, logs = repository(tmp_path)
    return ScheduledRunConfig.create(
        repo_root=repo,
        python_executable=python,
        log_root=logs,
        expected_head=HEAD,
        django_timeout_seconds=100,
        process_timeout_seconds=120,
    )


def completed(
    argv: list[str],
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(argv, returncode, stdout, stderr)


def git_runner(*, head: str = HEAD, dirty: str = "") -> Any:
    def run(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        if "rev-parse" in argv:
            return completed(argv, stdout=head + "\n")
        if "status" in argv:
            return completed(argv, stdout=dirty)
        raise AssertionError(argv)

    return run


def test_dry_plan_is_read_only_secret_free_and_deterministic(tmp_path: Path) -> None:
    value = config(tmp_path)
    first = scheduled_plan(value, environment=environment(), runner=git_runner())
    second = scheduled_plan(value, environment=environment(), runner=git_runner())
    assert first == second
    assert not value.log_root.exists()
    assert first["database_or_raw_writes"] == 0
    assert first["source_http_requests"] == 0
    assert "PRIVATE-PASSWORD-CANARY" not in json.dumps(first)
    cycle_command = first["cycle_argv"]
    assert isinstance(cycle_command, list)
    assert cycle_command[-1] == "--json"


def test_missing_environment_fails_before_command(tmp_path: Path) -> None:
    value = environment()
    value.pop("POSTGRES_DB")
    with pytest.raises(SchedulingError, match="POSTGRES_DB"):
        scheduled_plan(config(tmp_path), environment=value, runner=git_runner())


@pytest.mark.parametrize(
    ("head", "dirty", "message"),
    [("b" * 40, "", "HEAD differs"), (HEAD, " M changed.py\n", "not clean")],
)
def test_repository_drift_fails_closed(tmp_path: Path, head: str, dirty: str, message: str) -> None:
    with pytest.raises(SchedulingError, match=message):
        scheduled_plan(
            config(tmp_path), environment=environment(), runner=git_runner(head=head, dirty=dirty)
        )


def test_log_root_inside_worktree_is_rejected(tmp_path: Path) -> None:
    repo, python, _ = repository(tmp_path)
    with pytest.raises(SchedulingError, match="outside every Git worktree"):
        ScheduledRunConfig.create(
            repo_root=repo,
            python_executable=python,
            log_root=repo / "logs",
            expected_head=HEAD,
        )


def test_windows_no_overwrite_publication_does_not_require_hardlinks(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.tmp"
    target = tmp_path / "target.json"
    source.write_bytes(b"first")

    _publish_file_no_overwrite(
        source,
        target,
        collision_message="collision",
        platform_name="nt",
    )
    assert target.read_bytes() == b"first"
    assert not source.exists()

    second = tmp_path / "second.tmp"
    second.write_bytes(b"second")
    with pytest.raises(SchedulingError, match="collision"):
        _publish_file_no_overwrite(
            second, target, collision_message="collision", platform_name="nt"
        )
    assert target.read_bytes() == b"first"


def test_cycle_exit_is_propagated_and_envelope_is_bounded(tmp_path: Path) -> None:
    value = config(tmp_path)
    calls: list[list[str]] = []

    def runner(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        if "rev-parse" in argv:
            return completed(argv, stdout=HEAD + "\n")
        if "status" in argv and "observatory_status" not in argv:
            return completed(argv)
        if "run_daily_observatory" in argv:
            payload: dict[str, object] = {
                "cycle_id": "00000000-0000-0000-0000-000000000001",
                "status": "FAILED_COLLECTION",
                "description": "PRIVATE-DESCRIPTION-CANARY",
            }
            return completed(argv, returncode=3, stdout=json.dumps(payload) + "\n")
        if "observatory_status" in argv:
            payload = {
                "latest_cycle": {
                    "cycle_id": "00000000-0000-0000-0000-000000000001",
                    "status": "FAILED_COLLECTION",
                    "private": "PRIVATE-STATUS-CANARY",
                },
                "pit_cutoff": None,
            }
            return completed(argv, stdout=json.dumps(payload) + "\n")
        raise AssertionError(argv)

    times = iter(
        [
            datetime(2026, 8, 25, 3, 0, tzinfo=UTC),
            datetime(2026, 8, 25, 3, 0, 2, tzinfo=UTC),
        ]
    )
    exit_code, path, envelope = run_scheduled_cycle(
        value,
        environment=environment(),
        runner=runner,
        now=lambda: next(times),
    )
    assert exit_code == 3
    assert path.is_file()
    assert envelope["duration_milliseconds"] == 2000
    rendered = path.read_text(encoding="utf-8")
    assert "PRIVATE-DESCRIPTION-CANARY" not in rendered
    assert "PRIVATE-STATUS-CANARY" not in rendered
    assert "PRIVATE-PASSWORD-CANARY" not in rendered
    stable = envelope["stable_evidence"]
    assert isinstance(stable, dict)
    assert stable["cycle_exit_code"] == 3
    assert stable["cycle_summary"] == {
        "cycle_id": "00000000-0000-0000-0000-000000000001",
        "status": "FAILED_COLLECTION",
    }
    assert sum("run_daily_observatory" in argv for argv in calls) == 1


def test_process_timeout_is_distinct_and_status_is_still_read(tmp_path: Path) -> None:
    value = config(tmp_path)

    def runner(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        if "rev-parse" in argv:
            return completed(argv, stdout=HEAD + "\n")
        if "status" in argv and "observatory_status" not in argv:
            return completed(argv)
        if "run_daily_observatory" in argv:
            raise subprocess.TimeoutExpired(argv, timeout=120)
        if "observatory_status" in argv:
            return completed(argv, stdout=json.dumps({"latest_cycle": None}) + "\n")
        raise AssertionError(argv)

    start = datetime(2026, 8, 25, 3, 0, tzinfo=UTC)
    times = iter((start, start + timedelta(seconds=121)))
    exit_code, _, envelope = run_scheduled_cycle(
        value,
        environment=environment(),
        runner=runner,
        now=lambda: next(times),
    )
    assert exit_code == PROCESS_TIMEOUT_EXIT
    stable = envelope["stable_evidence"]
    assert isinstance(stable, dict)
    assert stable["cycle_process_timed_out"] is True
    assert stable["status_exit_code"] == 0


def test_status_execution_error_preserves_cycle_exit_and_publishes_evidence(
    tmp_path: Path,
) -> None:
    value = config(tmp_path)

    def runner(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        if "rev-parse" in argv:
            return completed(argv, stdout=HEAD + "\n")
        if "status" in argv and "observatory_status" not in argv:
            return completed(argv)
        if "run_daily_observatory" in argv:
            return completed(argv, returncode=3, stdout="{}\n")
        if "observatory_status" in argv:
            raise OSError("PRIVATE-STATUS-ERROR-CANARY")
        raise AssertionError(argv)

    start = datetime(2026, 8, 25, 3, 0, tzinfo=UTC)
    times = iter((start, start + timedelta(seconds=1)))
    exit_code, path, envelope = run_scheduled_cycle(
        value,
        environment=environment(),
        runner=runner,
        now=lambda: next(times),
    )
    assert exit_code == 3
    assert path.is_file()
    stable = envelope["stable_evidence"]
    assert isinstance(stable, dict)
    assert stable["status_exit_code"] == PROCESS_EXECUTION_ERROR_EXIT
    assert stable["status_process_error"] is True
    assert "PRIVATE-STATUS-ERROR-CANARY" not in path.read_text(encoding="utf-8")


def windows_config(tmp_path: Path) -> WindowsTaskConfig:
    return WindowsTaskConfig.create(
        task_name="Swiss Garden Jobs Observatory Daily",
        start_boundary="2026-09-01T03:17:00",
        scheduled_run=config(tmp_path),
    )


def test_windows_task_plan_is_non_overlapping_no_catchup_and_secret_free(tmp_path: Path) -> None:
    value = windows_config(tmp_path)
    xml_one = build_task_xml(value)
    xml_two = build_task_xml(value)
    assert xml_one == xml_two
    assert "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>" in xml_one
    assert "<StartWhenAvailable>false</StartWhenAvailable>" in xml_one
    assert "<RunLevel>LeastPrivilege</RunLevel>" in xml_one
    assert "PRIVATE-PASSWORD-CANARY" not in xml_one
    plan = task_plan(value)
    assert plan["registration_performed"] is False
    assert plan["credentials_in_arguments"] is False


def test_windows_registration_reuses_identical_and_rejects_conflict(tmp_path: Path) -> None:
    value = windows_config(tmp_path)
    intended = build_task_xml(value)

    def identical(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        if argv[0] == "tzutil.exe":
            return completed(argv, stdout="W. Europe Standard Time\n")
        return completed(argv, stdout=intended)

    assert (
        register_task(value, environment=environment(), git_runner=git_runner(), runner=identical)
        == "REUSED_IDENTICAL"
    )

    def conflicting(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        if argv[0] == "tzutil.exe":
            return completed(argv, stdout="W. Europe Standard Time\n")
        return completed(argv, stdout=intended.replace("03:17:00", "04:17:00"))

    with pytest.raises(SchedulingError, match="conflicts"):
        register_task(value, environment=environment(), git_runner=git_runner(), runner=conflicting)


def test_windows_registration_creates_without_force(tmp_path: Path) -> None:
    value = windows_config(tmp_path)
    calls: list[list[str]] = []

    def runner(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        if argv[0] == "tzutil.exe":
            return completed(argv, stdout="W. Europe Standard Time\n")
        if "/Query" in argv:
            return completed(argv, returncode=1)
        return completed(argv)

    assert (
        register_task(value, environment=environment(), git_runner=git_runner(), runner=runner)
        == "CREATED"
    )
    create = next(argv for argv in calls if "/Create" in argv)
    assert "/F" not in create


def test_windows_registration_validates_deployment_before_task_activity(
    tmp_path: Path,
) -> None:
    value = windows_config(tmp_path)
    calls: list[list[str]] = []

    def task_runner(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return completed(argv)

    with pytest.raises(SchedulingError, match="HEAD differs"):
        register_task(
            value,
            environment=environment(),
            git_runner=git_runner(head="b" * 40),
            runner=task_runner,
        )

    assert calls == []


@pytest.mark.parametrize("zone", ["W. Europe Standard Time", "Romance Standard Time"])
def test_windows_timezone_accepts_governed_zurich_equivalents(zone: str) -> None:
    def runner(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return completed(argv, stdout=zone + "\n")

    validate_windows_time_zone(runner=runner)


def test_windows_timezone_must_match_governed_zone() -> None:
    def runner(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return completed(argv, stdout="Pacific Standard Time\n")

    with pytest.raises(SchedulingError, match="timezone"):
        validate_windows_time_zone(runner=runner)


def backup_config(tmp_path: Path) -> BackupConfig:
    repo, _, output = repository(tmp_path)
    pg_dump = tmp_path / "pg_dump.exe"
    pg_restore = tmp_path / "pg_restore.exe"
    pg_dump.write_bytes(b"dump")
    pg_restore.write_bytes(b"restore")
    return BackupConfig.create(
        repo_root=repo,
        output_root=output,
        expected_head=HEAD,
        pg_dump=pg_dump,
        pg_restore=pg_restore,
    )


def test_backup_dry_plan_is_read_only_and_secret_free(tmp_path: Path) -> None:
    value = backup_config(tmp_path)
    plan = backup_plan(value, environment=environment(), runner=git_runner())
    assert not value.output_root.exists()
    assert plan["restore_performed"] is False
    assert plan["retention_deletions"] == 0
    assert "PRIVATE-PASSWORD-CANARY" not in json.dumps(plan)


def test_backup_publishes_verified_dump_and_manifest(tmp_path: Path) -> None:
    value = backup_config(tmp_path)

    def runner(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        if "rev-parse" in argv:
            return completed(argv, stdout=HEAD + "\n")
        if "status" in argv:
            return completed(argv)
        if str(value.pg_dump) == argv[0]:
            target = Path(
                next(item.split("=", 1)[1] for item in argv if item.startswith("--file="))
            )
            target.write_bytes(b"CUSTOM-DUMP-EVIDENCE")
            return completed(argv)
        if str(value.pg_restore) == argv[0]:
            return completed(argv, stdout="; Archive created at 2026-08-25\nTABLE DATA public x\n")
        raise AssertionError(argv)

    start = datetime(2026, 8, 25, 4, 0, tzinfo=UTC)
    times = iter((start, start + timedelta(seconds=2)))
    dump, manifest_path, manifest = create_backup(
        value,
        environment=environment(),
        runner=runner,
        now=lambda: next(times),
    )
    assert dump.read_bytes() == b"CUSTOM-DUMP-EVIDENCE"
    assert manifest_path.is_file()
    assert manifest["dump_file"] == dump.name
    assert "PRIVATE-PASSWORD-CANARY" not in manifest_path.read_text(encoding="utf-8")
    assert not list(value.output_root.glob("*.tmp"))


@pytest.mark.parametrize(("stage", "message"), [("dump", "pg_dump"), ("restore", "pg_restore")])
def test_backup_failure_publishes_nothing(tmp_path: Path, stage: str, message: str) -> None:
    value = backup_config(tmp_path)

    def runner(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        if "rev-parse" in argv:
            return completed(argv, stdout=HEAD + "\n")
        if "status" in argv:
            return completed(argv)
        if str(value.pg_dump) == argv[0]:
            target = Path(
                next(item.split("=", 1)[1] for item in argv if item.startswith("--file="))
            )
            target.write_bytes(b"CUSTOM-DUMP-EVIDENCE")
            return completed(argv, returncode=1 if stage == "dump" else 0)
        if str(value.pg_restore) == argv[0]:
            return completed(argv, returncode=1 if stage == "restore" else 0)
        raise AssertionError(argv)

    with pytest.raises(SchedulingError, match=message):
        create_backup(value, environment=environment(), runner=runner)
    assert not list(value.output_root.glob("*.dump"))
    assert not list(value.output_root.glob("*.json"))


@pytest.mark.parametrize("stage", ["dump", "restore"])
def test_backup_execution_error_is_bounded(tmp_path: Path, stage: str) -> None:
    value = backup_config(tmp_path)

    def runner(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        if "rev-parse" in argv:
            return completed(argv, stdout=HEAD + "\n")
        if "status" in argv:
            return completed(argv)
        if str(value.pg_dump) == argv[0]:
            if stage == "dump":
                raise OSError("PRIVATE-DUMP-CANARY")
            target = Path(
                next(item.split("=", 1)[1] for item in argv if item.startswith("--file="))
            )
            target.write_bytes(b"CUSTOM-DUMP-EVIDENCE")
            return completed(argv)
        if str(value.pg_restore) == argv[0]:
            raise OSError("PRIVATE-RESTORE-CANARY")
        raise AssertionError(argv)

    with pytest.raises(SchedulingError, match=f"pg_{stage} execution"):
        create_backup(value, environment=environment(), runner=runner)
    assert not list(value.output_root.glob("*.dump"))
    assert not list(value.output_root.glob("*.json"))


def test_backup_manifest_failure_removes_new_dump(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import operations.backup as backup_module

    value = backup_config(tmp_path)

    def runner(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        if "rev-parse" in argv:
            return completed(argv, stdout=HEAD + "\n")
        if "status" in argv:
            return completed(argv)
        if str(value.pg_dump) == argv[0]:
            target = Path(
                next(item.split("=", 1)[1] for item in argv if item.startswith("--file="))
            )
            target.write_bytes(b"CUSTOM-DUMP-EVIDENCE")
            return completed(argv)
        return completed(argv, stdout="TABLE DATA public x\n")

    def refuse_manifest(path: Path, payload: bytes) -> None:
        raise SchedulingError("manifest collision")

    monkeypatch.setattr(backup_module, "_atomic_publish", refuse_manifest)
    with pytest.raises(SchedulingError, match="manifest collision"):
        create_backup(value, environment=environment(), runner=runner)
    assert not list(value.output_root.glob("*.dump"))
    assert not list(value.output_root.glob("*.json"))
