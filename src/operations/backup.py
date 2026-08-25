"""Credential-free PostgreSQL custom backup publication."""

from __future__ import annotations

import os
import subprocess
import tempfile
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from operations.scheduling import (
    CommandRunner,
    ScheduledRunConfig,
    SchedulingError,
    _atomic_publish,
    _inside_git_worktree,
    canonical_datetime,
    canonical_json_bytes,
    sha256_bytes,
    validate_repository,
)

BACKUP_VERSION = "observatory-postgres-backup-v0.1"
BACKUP_ENVIRONMENT = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_HOST", "POSTGRES_PORT")


@dataclass(frozen=True)
class BackupConfig:
    repo_root: Path
    output_root: Path
    expected_head: str
    pg_dump: Path
    pg_restore: Path

    @classmethod
    def create(
        cls,
        *,
        repo_root: str | Path,
        output_root: str | Path,
        expected_head: str,
        pg_dump: str | Path,
        pg_restore: str | Path,
    ) -> BackupConfig:
        repo = Path(repo_root)
        output = Path(output_root)
        dump = Path(pg_dump)
        restore = Path(pg_restore)
        if not all(path.is_absolute() for path in (repo, output, dump, restore)):
            raise SchedulingError("backup repository, output, and binary paths must be absolute")
        repo = repo.resolve()
        output = output.resolve()
        dump = dump.resolve()
        restore = restore.resolve()
        if not (repo / "manage.py").is_file() or not (repo / ".git").exists():
            raise SchedulingError("backup repository root is invalid")
        if _inside_git_worktree(output):
            raise SchedulingError("backup output root must be outside every Git worktree")
        if not dump.is_file() or not restore.is_file():
            raise SchedulingError("pg_dump and pg_restore must be existing absolute files")
        if len(expected_head) != 40 or any(
            char not in "0123456789abcdef" for char in expected_head
        ):
            raise SchedulingError("expected backup deployment HEAD is invalid")
        return cls(
            repo_root=repo,
            output_root=output,
            expected_head=expected_head,
            pg_dump=dump,
            pg_restore=restore,
        )


def _backup_environment(environment: Mapping[str, str]) -> dict[str, str]:
    missing = [name for name in BACKUP_ENVIRONMENT if not environment.get(name, "").strip()]
    if missing:
        raise SchedulingError(f"required backup environment is missing: {', '.join(missing)}")
    child = dict(environment)
    child["PGHOST"] = environment["POSTGRES_HOST"]
    child["PGPORT"] = environment["POSTGRES_PORT"]
    child["PGUSER"] = environment["POSTGRES_USER"]
    if environment.get("POSTGRES_PASSWORD"):
        child["PGPASSWORD"] = environment["POSTGRES_PASSWORD"]
    return child


def backup_plan(
    config: BackupConfig,
    *,
    environment: Mapping[str, str],
    runner: CommandRunner = subprocess.run,
) -> dict[str, object]:
    child = _backup_environment(environment)
    shim = ScheduledRunConfig.create(
        repo_root=config.repo_root,
        python_executable=config.pg_dump,
        log_root=config.output_root,
        expected_head=config.expected_head,
        django_timeout_seconds=60,
        process_timeout_seconds=61,
    )
    repository = validate_repository(shim, runner=runner)
    return {
        "backup_version": BACKUP_VERSION,
        "git_head": repository["head"],
        "clean": repository["clean"],
        "output_root": str(config.output_root),
        "pg_dump": str(config.pg_dump),
        "pg_restore": str(config.pg_restore),
        "database": child["POSTGRES_DB"],
        "server_identity_sha256": sha256_bytes(f"{child['PGHOST']}:{child['PGPORT']}".encode()),
        "credentials_in_arguments": False,
        "restore_performed": False,
        "retention_deletions": 0,
    }


def create_backup(
    config: BackupConfig,
    *,
    environment: Mapping[str, str] | None = None,
    runner: CommandRunner = subprocess.run,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> tuple[Path, Path, dict[str, object]]:
    active_environment = dict(os.environ if environment is None else environment)
    child_environment = _backup_environment(active_environment)
    plan = backup_plan(config, environment=active_environment, runner=runner)
    config.output_root.mkdir(parents=True, exist_ok=True)
    started = now()
    temporary_dump: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=config.output_root,
            prefix=".observatory-",
            suffix=".dump.tmp",
            delete=False,
        ) as handle:
            temporary_dump = Path(handle.name)
        try:
            dump = runner(
                [
                    str(config.pg_dump),
                    "--format=custom",
                    f"--file={temporary_dump}",
                    child_environment["POSTGRES_DB"],
                ],
                cwd=config.repo_root,
                env=child_environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=7_200,
                check=False,
                shell=False,
            )
        except OSError as exc:
            raise SchedulingError("pg_dump execution failed") from exc
        if dump.returncode != 0:
            raise SchedulingError("pg_dump failed")
        if not temporary_dump.is_file() or temporary_dump.stat().st_size == 0:
            raise SchedulingError("pg_dump did not create a non-empty custom dump")
        with temporary_dump.open("rb+") as handle:
            os.fsync(handle.fileno())
        try:
            inventory = runner(
                [str(config.pg_restore), "--list", str(temporary_dump)],
                cwd=config.repo_root,
                env=child_environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
                check=False,
                shell=False,
            )
        except OSError as exc:
            raise SchedulingError("pg_restore execution failed") from exc
        if inventory.returncode != 0 or not inventory.stdout.strip():
            raise SchedulingError("pg_restore --list did not validate the custom dump")
        dump_bytes = temporary_dump.read_bytes()
        dump_sha = sha256_bytes(dump_bytes)
        base_name = started.astimezone(UTC).strftime("observatory-%Y%m%dT%H%M%S%fZ")
        final_dump = config.output_root / f"{base_name}-{dump_sha[:12]}.dump"
        try:
            os.link(temporary_dump, final_dump)
        except FileExistsError as exc:
            raise SchedulingError("backup target already exists") from exc
        finished = now()
        stable = {
            "backup_version": BACKUP_VERSION,
            "git_head": plan["git_head"],
            "database": plan["database"],
            "server_identity_sha256": plan["server_identity_sha256"],
            "dump_sha256": dump_sha,
            "dump_size_bytes": len(dump_bytes),
            "inventory_sha256": sha256_bytes(inventory.stdout.encode("utf-8")),
            "restore_performed": False,
            "retention_deletions": 0,
        }
        manifest: dict[str, object] = {
            "schema_version": BACKUP_VERSION,
            "backup_id": str(uuid.uuid4()),
            "started_at": canonical_datetime(started),
            "finished_at": canonical_datetime(finished),
            "stable_evidence": stable,
            "evidence_sha256": sha256_bytes(canonical_json_bytes(stable)),
            "dump_file": final_dump.name,
        }
        manifest_path = final_dump.with_suffix(".json")
        try:
            _atomic_publish(manifest_path, canonical_json_bytes(manifest) + b"\n")
        except Exception:
            final_dump.unlink(missing_ok=True)
            raise
        return final_dump, manifest_path, manifest
    finally:
        if temporary_dump is not None:
            temporary_dump.unlink(missing_ok=True)
