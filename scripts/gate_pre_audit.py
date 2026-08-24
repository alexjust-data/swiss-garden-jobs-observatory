#!/usr/bin/env python3
"""Mechanical, read-only pre-audit evidence for governed gate pull requests."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

PROFILE_VERSION = "gate-pre-audit-profile-v1"
REPORT_VERSION = "gate-pre-audit-report-v1"
PROFILE_KEYS = {
    "schema_version",
    "gate",
    "pr",
    "expected_base_ref",
    "expected_base_sha",
    "expected_head_ref",
    "contract",
    "contract_blob",
    "frozen_paths",
    "focused_tests",
    "expected_migrations",
}
PROFILE_DIRECTORY = Path("docs/governance/gate_profiles")
DEFAULT_OUTPUT_DIRECTORY = Path(".gate-audit")
FAILED_CONCLUSIONS = {
    "ACTION_REQUIRED",
    "CANCELLED",
    "FAILURE",
    "STALE",
    "STARTUP_FAILURE",
    "TIMED_OUT",
}


class AuditStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_PROVEN = "NOT_PROVEN"


@dataclass(frozen=True)
class GateProfile:
    gate: str
    pr: int | None
    expected_base_ref: str
    expected_base_sha: str
    expected_head_ref: str
    contract: str
    contract_blob: str
    frozen_paths: tuple[str, ...]
    focused_tests: tuple[str, ...]
    expected_migrations: tuple[str, ...]
    source_name: str
    sha256: str


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    label: str
    status: AuditStatus
    mandatory: bool
    source: str
    summary: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def canonical(self) -> dict[str, Any]:
        return {
            "id": self.check_id,
            "label": self.label,
            "status": self.status.value,
            "mandatory": self.mandatory,
            "source": self.source,
            "summary": self.summary,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class CommandRecord:
    argv: tuple[str, ...]
    cwd: str
    returncode: int | None
    stdout: str
    stderr: str
    duration_ms: int
    error: str | None = None

    def execution(self) -> dict[str, Any]:
        return {
            "argv": list(self.argv),
            "cwd": self.cwd,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


class CommandRunner:
    def __init__(self) -> None:
        self.records: list[CommandRecord] = []

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout: int | None = None,
    ) -> CommandRecord:
        started = time.monotonic()
        try:
            completed = subprocess.run(
                list(argv),
                cwd=cwd,
                env=dict(env) if env is not None else None,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
            record = CommandRecord(
                argv=tuple(str(value) for value in argv),
                cwd=str(cwd),
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                duration_ms=round((time.monotonic() - started) * 1000),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            record = CommandRecord(
                argv=tuple(str(value) for value in argv),
                cwd=str(cwd),
                returncode=None,
                stdout="",
                stderr="",
                duration_ms=round((time.monotonic() - started) * 1000),
                error=f"{type(exc).__name__}: {exc}",
            )
        self.records.append(record)
        return record


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _safe_relative_path(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty relative path")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        path.is_absolute()
        or ".." in path.parts
        or "." in path.parts
        or ":" in normalized
        or "\x00" in normalized
        or normalized.startswith("-")
    ):
        raise ValueError(f"{field_name} must stay within the repository")
    return path.as_posix()


def _string_list(value: Any, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    return tuple(_safe_relative_path(item, field_name=field_name) for item in value)


def _focused_test_list(value: Any) -> tuple[str, ...]:
    tests = _string_list(value, field_name="focused_tests")
    for selector in tests:
        if not selector.endswith(".py"):
            raise ValueError("focused_tests entries must be Python test file paths")
    return tests


def _git_ref(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty Git ref name")
    ref = value.strip()
    if (
        ref.startswith(("-", "/"))
        or ref.endswith(("/", "."))
        or ".." in ref
        or "//" in ref
        or re.fullmatch(r"[A-Za-z0-9._/-]+", ref) is None
    ):
        raise ValueError(f"{field_name} must be a safe Git ref name")
    return ref


def _git_object_id(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40,64}", value) is None:
        raise ValueError(f"{field_name} must be a lowercase Git object id")
    return value


def load_profile(path: Path) -> GateProfile:
    try:
        raw_bytes = path.read_bytes()
        payload = json.loads(raw_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read profile {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("profile must be a JSON object")
    extra = sorted(set(payload) - PROFILE_KEYS)
    missing = sorted(PROFILE_KEYS - set(payload))
    if extra or missing:
        raise ValueError(f"profile keys mismatch; missing={missing}, extra={extra}")
    if payload["schema_version"] != PROFILE_VERSION:
        raise ValueError(f"unsupported profile schema: {payload['schema_version']!r}")
    gate = payload["gate"]
    if not isinstance(gate, str) or not gate.strip():
        raise ValueError("gate must be a non-empty string")
    pr = payload["pr"]
    if pr is not None and (not isinstance(pr, int) or isinstance(pr, bool) or pr < 1):
        raise ValueError("pr must be null or a positive integer")
    blob = _git_object_id(payload["contract_blob"], field_name="contract_blob")
    return GateProfile(
        gate=gate.strip(),
        pr=pr,
        expected_base_ref=_git_ref(payload["expected_base_ref"], field_name="expected_base_ref"),
        expected_base_sha=_git_object_id(
            payload["expected_base_sha"], field_name="expected_base_sha"
        ),
        expected_head_ref=_git_ref(payload["expected_head_ref"], field_name="expected_head_ref"),
        contract=_safe_relative_path(payload["contract"], field_name="contract"),
        contract_blob=blob,
        frozen_paths=_string_list(payload["frozen_paths"], field_name="frozen_paths"),
        focused_tests=_focused_test_list(payload["focused_tests"]),
        expected_migrations=tuple(
            sorted(_string_list(payload["expected_migrations"], field_name="expected_migrations"))
        ),
        source_name=path.name,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
    )


def aggregate_status(checks: Iterable[CheckResult]) -> AuditStatus:
    mandatory = [check for check in checks if check.mandatory]
    if any(check.status == AuditStatus.FAIL for check in mandatory):
        return AuditStatus.FAIL
    if any(check.status == AuditStatus.NOT_PROVEN for check in mandatory):
        return AuditStatus.NOT_PROVEN
    return AuditStatus.PASS


def _git(runner: CommandRunner, repo: Path, *args: str) -> CommandRecord:
    safe_path = repo.as_posix()
    return runner.run(
        ["git", "-c", f"safe.directory={safe_path}", "-C", str(repo), *args],
        cwd=repo,
    )


def _stdout(record: CommandRecord) -> str | None:
    if record.returncode != 0:
        return None
    return record.stdout.strip()


def query_pull_request(runner: CommandRunner, repo: Path, pr_number: int) -> dict[str, Any] | None:
    fields = (
        "number,title,state,isDraft,mergeStateStatus,mergeable,headRefOid,baseRefOid,"
        "headRefName,baseRefName,statusCheckRollup,url,reviews,reviewDecision"
    )
    record = runner.run(
        ["gh", "pr", "view", str(pr_number), "--json", fields],
        cwd=repo,
    )
    if record.returncode != 0:
        return None
    try:
        payload = json.loads(record.stdout)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _changed_files(
    runner: CommandRunner,
    repo: Path,
    base_sha: str | None,
    head_sha: str | None,
) -> tuple[list[str] | None, CommandRecord | None]:
    if not base_sha or not head_sha:
        return None, None
    record = _git(runner, repo, "diff", "--name-only", base_sha, head_sha, "--")
    if record.returncode != 0:
        return None, record
    return sorted(line for line in record.stdout.splitlines() if line), record


def discover_profile(
    *,
    repo: Path,
    pr_number: int,
    explicit_path: Path | None,
    changed_files: Sequence[str] | None,
) -> tuple[Path, GateProfile]:
    directory = (repo / PROFILE_DIRECTORY).resolve()
    if explicit_path is not None:
        path = (explicit_path if explicit_path.is_absolute() else repo / explicit_path).resolve()
        try:
            path.relative_to(directory)
        except ValueError as exc:
            raise ValueError(
                "explicit profile must stay in the governed profile directory"
            ) from exc
        if path.suffix.casefold() != ".json":
            raise ValueError("explicit profile must be a JSON file")
        return path, load_profile(path)

    candidates: list[tuple[Path, GateProfile]] = []
    for path in sorted(directory.glob("*.json")):
        profile = load_profile(path)
        if profile.pr == pr_number:
            candidates.append((path, profile))
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        raise ValueError(f"multiple profiles declare PR #{pr_number}")

    if changed_files is not None:
        changed = set(changed_files)
        for path in sorted(directory.glob("*.json")):
            relative = path.relative_to(repo).as_posix()
            profile = load_profile(path)
            if relative in changed and profile.pr is None:
                candidates.append((path, profile))
    if len(candidates) == 1:
        return candidates[0]
    raise ValueError(f"no unique gate profile for PR #{pr_number}; pass --profile explicitly")


def _check(
    check_id: str,
    label: str,
    status: AuditStatus,
    *,
    mandatory: bool = True,
    source: str,
    summary: str,
    details: Mapping[str, Any] | None = None,
) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        label=label,
        status=status,
        mandatory=mandatory,
        source=source,
        summary=summary,
        details=details or {},
    )


def _unavailable(check_id: str, label: str, summary: str, *, mandatory: bool = True) -> CheckResult:
    return _check(
        check_id,
        label,
        AuditStatus.NOT_PROVEN,
        mandatory=mandatory,
        source="unavailable",
        summary=summary,
    )


def _ci_status(entries: Sequence[Mapping[str, Any]], *, gitguardian: bool) -> AuditStatus:
    selected = []
    for entry in entries:
        name = str(entry.get("name") or entry.get("context") or "")
        is_gitguardian = "gitguardian" in name.casefold()
        if is_gitguardian == gitguardian:
            selected.append(entry)
    if not selected:
        return AuditStatus.NOT_PROVEN
    conclusions = {str(item.get("conclusion") or "").upper() for item in selected}
    statuses = {str(item.get("status") or "").upper() for item in selected}
    if conclusions & FAILED_CONCLUSIONS:
        return AuditStatus.FAIL
    if statuses != {"COMPLETED"} or conclusions != {"SUCCESS"}:
        return AuditStatus.NOT_PROVEN
    return AuditStatus.PASS


def _github_checks(
    runner: CommandRunner,
    repo: Path,
    pr_number: int,
    pull_request: Mapping[str, Any] | None,
) -> list[CheckResult]:
    if pull_request is None:
        return [
            _unavailable("github_pr", "GitHub PR metadata", "gh metadata unavailable"),
            _unavailable("ci_exact_head", "Exact-head CI", "GitHub checks unavailable"),
            _unavailable("gitguardian", "GitGuardian", "GitGuardian result unavailable"),
            _unavailable(
                "review_threads", "Unresolved review threads", "review threads unavailable"
            ),
            _unavailable(
                "review_submissions",
                "Review submissions",
                "review submissions unavailable",
                mandatory=False,
            ),
        ]

    checks = list(pull_request.get("statusCheckRollup") or [])
    ci_status = _ci_status(checks, gitguardian=False)
    guardian_status = _ci_status(checks, gitguardian=True)
    result = [
        _check(
            "github_pr",
            "GitHub PR metadata",
            AuditStatus.PASS,
            source="github",
            summary=f"PR #{pr_number} metadata read",
            details={
                "state": pull_request.get("state"),
                "draft": pull_request.get("isDraft"),
                "url": pull_request.get("url"),
            },
        ),
        _check(
            "ci_exact_head",
            "Exact-head CI",
            ci_status,
            source="github",
            summary=(
                "all non-GitGuardian checks succeeded"
                if ci_status == AuditStatus.PASS
                else "exact-head CI is failed, pending, skipped, or unavailable"
            ),
            details={
                "checks": sorted(
                    str(item.get("name") or item.get("context") or "")
                    for item in checks
                    if "gitguardian"
                    not in str(item.get("name") or item.get("context") or "").casefold()
                )
            },
        ),
        _check(
            "gitguardian",
            "GitGuardian",
            guardian_status,
            source="github",
            summary=(
                "GitGuardian succeeded"
                if guardian_status == AuditStatus.PASS
                else "GitGuardian is failed, pending, skipped, or unavailable"
            ),
        ),
    ]

    reviews = pull_request.get("reviews")
    if isinstance(reviews, list):
        result.append(
            _check(
                "review_submissions",
                "Review submissions",
                AuditStatus.PASS,
                mandatory=False,
                source="github",
                summary=f"{len(reviews)} review submissions observed",
                details={"count": len(reviews)},
            )
        )
    else:
        result.append(
            _unavailable(
                "review_submissions",
                "Review submissions",
                "review submissions unavailable",
                mandatory=False,
            )
        )

    url = str(pull_request.get("url") or "")
    path_parts = [part for part in urlparse(url).path.split("/") if part]
    if len(path_parts) < 2:
        result.append(
            _unavailable(
                "review_threads", "Unresolved review threads", "repository identity unavailable"
            )
        )
        return result
    owner, name = path_parts[0], path_parts[1]
    query = """
query($owner:String!,$name:String!,$number:Int!,$cursor:String){
  repository(owner:$owner,name:$name){
    pullRequest(number:$number){
      reviewThreads(first:100,after:$cursor){
        nodes{isResolved}
        pageInfo{hasNextPage endCursor}
      }
    }
  }
}
""".strip()
    nodes: list[Mapping[str, Any]] = []
    cursor: str | None = None
    try:
        while True:
            argv = [
                "gh",
                "api",
                "graphql",
                "-f",
                f"query={query}",
                "-f",
                f"owner={owner}",
                "-f",
                f"name={name}",
                "-F",
                f"number={pr_number}",
            ]
            if cursor is not None:
                argv.extend(["-f", f"cursor={cursor}"])
            record = runner.run(argv, cwd=repo)
            payload = json.loads(record.stdout) if record.returncode == 0 else None
            if not isinstance(payload, dict):
                raise TypeError("GraphQL payload must be an object")
            connection = payload["data"]["repository"]["pullRequest"]["reviewThreads"]
            page_nodes = connection["nodes"]
            page_info = connection["pageInfo"]
            if not isinstance(page_nodes, list) or not isinstance(page_info, dict):
                raise TypeError("review thread connection must be complete")
            nodes.extend(page_nodes)
            if not page_info.get("hasNextPage"):
                break
            next_cursor = page_info.get("endCursor")
            if not isinstance(next_cursor, str) or not next_cursor or next_cursor == cursor:
                raise TypeError("review thread pagination cursor unavailable")
            cursor = next_cursor
        unresolved = sum(1 for node in nodes if not node.get("isResolved"))
    except (KeyError, TypeError, json.JSONDecodeError):
        result.append(
            _unavailable(
                "review_threads", "Unresolved review threads", "review thread query unavailable"
            )
        )
    else:
        result.append(
            _check(
                "review_threads",
                "Unresolved review threads",
                AuditStatus.PASS if unresolved == 0 else AuditStatus.FAIL,
                source="github_graphql",
                summary=f"{unresolved} unresolved review threads",
                details={"unresolved": unresolved, "total": len(nodes)},
            )
        )
    return result


def _stable_command_summary(record: CommandRecord) -> str:
    lines = [
        line.strip() for line in (record.stdout + "\n" + record.stderr).splitlines() if line.strip()
    ]
    if not lines:
        return (
            "command completed"
            if record.returncode == 0
            else "command produced no diagnostic output"
        )
    summary = lines[-1]
    summary = re.sub(r"\s+in\s+\d+(?:\.\d+)?s(?:\s+\([^)]*\))?$", "", summary)
    return summary[:300]


def _local_command_check(
    runner: CommandRunner,
    *,
    repo: Path,
    output_dir: Path,
    check_id: str,
    label: str,
    argv: Sequence[str],
) -> CheckResult:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "MYPY_CACHE_DIR": str(output_dir / "cache" / "mypy"),
            "RUFF_CACHE_DIR": str(output_dir / "cache" / "ruff"),
        }
    )
    record = runner.run(argv, cwd=repo, env=env)
    if record.returncode is None:
        return _unavailable(check_id, label, record.error or "command unavailable")
    status = AuditStatus.PASS if record.returncode == 0 else AuditStatus.FAIL
    return _check(
        check_id,
        label,
        status,
        source="local_execution",
        summary=_stable_command_summary(record),
        details={"exit_code": record.returncode, "command": _display_command(argv)},
    )


def _display_command(argv: Sequence[str]) -> list[str]:
    values = [str(item) for item in argv]
    if values and Path(values[0]).name.casefold().startswith("python"):
        values[0] = "python"
    return values


def _local_validation_checks(
    runner: CommandRunner,
    *,
    repo: Path,
    output_dir: Path,
    profile: GateProfile,
    skip: bool,
) -> list[CheckResult]:
    definitions: list[tuple[str, str, list[str]]] = []
    if profile.focused_tests:
        definitions.append(
            (
                "pytest_focused",
                "Focused pytest",
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    *profile.focused_tests,
                ],
            )
        )
    definitions.extend(
        [
            (
                "pytest_full",
                "Full pytest",
                [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
            ),
            ("ruff", "Ruff", [sys.executable, "-m", "ruff", "check", "."]),
            ("mypy", "mypy", [sys.executable, "-m", "mypy", "src", "manage.py"]),
            ("django_check", "Django check", [sys.executable, "manage.py", "check"]),
            (
                "migration_drift",
                "Migration drift",
                [sys.executable, "manage.py", "makemigrations", "--check", "--dry-run"],
            ),
        ]
    )
    if skip:
        return [
            _unavailable(check_id, label, "local validation explicitly skipped")
            for check_id, label, _ in definitions
        ]
    return [
        _local_command_check(
            runner,
            repo=repo,
            output_dir=output_dir,
            check_id=check_id,
            label=label,
            argv=argv,
        )
        for check_id, label, argv in definitions
    ]


def run_audit(
    *,
    runner: CommandRunner,
    repo: Path,
    output_dir: Path,
    pr_number: int,
    explicit_profile: Path | None,
    skip_local_validation: bool,
) -> tuple[dict[str, Any], list[CheckResult]]:
    pull_request = query_pull_request(runner, repo, pr_number)
    base_sha = str(pull_request.get("baseRefOid") or "") if pull_request else None
    head_sha = str(pull_request.get("headRefOid") or "") if pull_request else None
    changed_files, _ = _changed_files(runner, repo, base_sha, head_sha)
    profile_path, profile = discover_profile(
        repo=repo,
        pr_number=pr_number,
        explicit_path=explicit_profile,
        changed_files=changed_files,
    )
    if profile.pr is not None and profile.pr != pr_number:
        raise ValueError(f"profile declares PR #{profile.pr}, but audit requested PR #{pr_number}")

    checks: list[CheckResult] = []
    repo_check = _git(runner, repo, "rev-parse", "--show-toplevel")
    if repo_check.returncode == 0:
        checks.append(
            _check(
                "git_repository",
                "Git repository",
                AuditStatus.PASS,
                source="local_git",
                summary="repository metadata available",
            )
        )
    else:
        checks.append(
            _unavailable("git_repository", "Git repository", "Git repository unavailable")
        )

    local_head = _stdout(_git(runner, repo, "rev-parse", "HEAD"))
    local_branch = _stdout(_git(runner, repo, "rev-parse", "--abbrev-ref", "HEAD"))
    status_record = _git(runner, repo, "status", "--porcelain=v1")
    if status_record.returncode == 0:
        dirty_lines = sorted(line for line in status_record.stdout.splitlines() if line)
        checks.append(
            _check(
                "git_clean",
                "Git working tree",
                AuditStatus.PASS if not dirty_lines else AuditStatus.FAIL,
                source="local_git",
                summary="clean" if not dirty_lines else f"{len(dirty_lines)} local changes present",
                details={"changes": dirty_lines},
            )
        )
    else:
        checks.append(
            _unavailable("git_clean", "Git working tree", "working-tree status unavailable")
        )

    if pull_request is None:
        checks.append(_unavailable("head_exact", "Exact PR head", "GitHub PR head unavailable"))
        checks.append(_unavailable("base_exact", "Exact PR base", "GitHub PR base unavailable"))
        checks.append(_unavailable("head_ref", "PR head branch", "GitHub PR branch unavailable"))
    else:
        exact = bool(local_head and local_head == head_sha)
        checks.append(
            _check(
                "head_exact",
                "Exact PR head",
                AuditStatus.PASS if exact else AuditStatus.FAIL,
                source="local_git+github",
                summary="local HEAD matches PR head"
                if exact
                else "local HEAD does not match PR head",
                details={"local": local_head, "pr": head_sha},
            )
        )
        actual_base_ref = str(pull_request.get("baseRefName") or "")
        actual_head_ref = str(pull_request.get("headRefName") or "")
        base_exact = (
            actual_base_ref == profile.expected_base_ref and base_sha == profile.expected_base_sha
        )
        checks.append(
            _check(
                "base_exact",
                "Exact PR base",
                AuditStatus.PASS if base_exact else AuditStatus.FAIL,
                source="github+profile",
                summary="PR base matches profile" if base_exact else "PR base differs from profile",
                details={
                    "expected_ref": profile.expected_base_ref,
                    "actual_ref": actual_base_ref,
                    "expected_sha": profile.expected_base_sha,
                    "actual_sha": base_sha,
                },
            )
        )
        head_ref_exact = actual_head_ref == profile.expected_head_ref
        checks.append(
            _check(
                "head_ref",
                "PR head branch",
                AuditStatus.PASS if head_ref_exact else AuditStatus.FAIL,
                source="github+profile",
                summary=(
                    "PR head branch matches profile"
                    if head_ref_exact
                    else "PR head branch differs from profile"
                ),
                details={"expected": profile.expected_head_ref, "actual": actual_head_ref},
            )
        )

    object_details: dict[str, bool] = {}
    objects_proven = bool(base_sha and head_sha)
    for label, sha in (("base", base_sha), ("head", head_sha)):
        if not sha:
            object_details[label] = False
            objects_proven = False
            continue
        record = _git(runner, repo, "cat-file", "-e", f"{sha}^{{commit}}")
        object_details[label] = record.returncode == 0
        objects_proven = objects_proven and record.returncode == 0
    checks.append(
        _check(
            "git_objects",
            "PR Git objects",
            AuditStatus.PASS if objects_proven else AuditStatus.NOT_PROVEN,
            source="local_git",
            summary="base and head objects available"
            if objects_proven
            else "base or head object unavailable",
            details=object_details,
        )
    )

    if not head_sha or not objects_proven:
        checks.append(
            _unavailable("contract_blob", "Frozen contract blob", "PR head object unavailable")
        )
    else:
        record = _git(runner, repo, "rev-parse", f"{head_sha}:{profile.contract}")
        actual_blob = _stdout(record)
        if actual_blob is None:
            checks.append(
                _check(
                    "contract_blob",
                    "Frozen contract blob",
                    AuditStatus.FAIL,
                    source="local_git",
                    summary="contract is absent from PR head",
                    details={"path": profile.contract},
                )
            )
        else:
            matches = actual_blob == profile.contract_blob
            checks.append(
                _check(
                    "contract_blob",
                    "Frozen contract blob",
                    AuditStatus.PASS if matches else AuditStatus.FAIL,
                    source="local_git+profile",
                    summary="contract blob matches" if matches else "contract blob mismatch",
                    details={
                        "path": profile.contract,
                        "expected": profile.contract_blob,
                        "actual": actual_blob,
                    },
                )
            )

    if not base_sha or not head_sha or not objects_proven:
        checks.append(
            _unavailable("frozen_paths", "Frozen paths", "base/head comparison unavailable")
        )
    else:
        frozen_changes: list[str] = []
        frozen_error = False
        for frozen_path in profile.frozen_paths:
            record = _git(
                runner, repo, "diff", "--name-only", base_sha, head_sha, "--", frozen_path
            )
            if record.returncode != 0:
                frozen_error = True
                continue
            frozen_changes.extend(line for line in record.stdout.splitlines() if line)
        if frozen_error:
            checks.append(
                _unavailable("frozen_paths", "Frozen paths", "frozen-path diff unavailable")
            )
        else:
            frozen_changes = sorted(set(frozen_changes))
            checks.append(
                _check(
                    "frozen_paths",
                    "Frozen paths",
                    AuditStatus.PASS if not frozen_changes else AuditStatus.FAIL,
                    source="local_git+profile",
                    summary=(
                        "frozen paths unchanged"
                        if not frozen_changes
                        else f"{len(frozen_changes)} frozen files changed"
                    ),
                    details={"paths": list(profile.frozen_paths), "changes": frozen_changes},
                )
            )

    if changed_files is None:
        checks.append(_unavailable("changed_files", "Changed files", "PR diff unavailable"))
        checks.append(_unavailable("migrations", "Migration inventory", "PR diff unavailable"))
        migrations: list[str] = []
    else:
        checks.append(
            _check(
                "changed_files",
                "Changed files",
                AuditStatus.PASS,
                source="local_git",
                summary=f"{len(changed_files)} changed files inventoried",
                details={"files": changed_files},
            )
        )
        migrations = sorted(
            path
            for path in changed_files
            if re.fullmatch(r"src/[^/]+/migrations/(?!__init__\.py$).+\.py", path)
        )
        expected = list(profile.expected_migrations)
        matches = migrations == expected
        checks.append(
            _check(
                "migrations",
                "Migration inventory",
                AuditStatus.PASS if matches else AuditStatus.FAIL,
                source="local_git+profile",
                summary=(
                    "migration inventory matches profile"
                    if matches
                    else "migration inventory differs from profile"
                ),
                details={"expected": expected, "actual": migrations},
            )
        )

    checks.extend(_github_checks(runner, repo, pr_number, pull_request))
    checks.extend(
        _local_validation_checks(
            runner,
            repo=repo,
            output_dir=output_dir,
            profile=profile,
            skip=skip_local_validation,
        )
    )
    post_status_record = _git(runner, repo, "status", "--porcelain=v1")
    if post_status_record.returncode == 0:
        post_changes = sorted(line for line in post_status_record.stdout.splitlines() if line)
        checks.append(
            _check(
                "git_clean_after_validation",
                "Git tree after validation",
                AuditStatus.PASS if not post_changes else AuditStatus.FAIL,
                source="local_git",
                summary=(
                    "validation left the checkout clean"
                    if not post_changes
                    else f"validation left {len(post_changes)} local changes"
                ),
                details={"changes": post_changes},
            )
        )
    else:
        checks.append(
            _unavailable(
                "git_clean_after_validation",
                "Git tree after validation",
                "post-validation status unavailable",
            )
        )
    for check_id, label in (
        ("source_http", "Source HTTP requests"),
        ("provider_http", "Provider HTTP requests"),
        ("real_db_mutation", "Real database mutations"),
        ("exact_pit_replay", "Exact PIT replay"),
    ):
        checks.append(
            _unavailable(
                check_id,
                label,
                "outside H1 mechanical evidence boundary",
                mandatory=False,
            )
        )

    overall = aggregate_status(checks)
    evidence = {
        "gate": profile.gate,
        "pr": pr_number,
        "profile": {"file": profile.source_name, "sha256": profile.sha256},
        "git": {
            "branch": local_branch,
            "local_head": local_head,
            "base": base_sha,
            "pr_head": head_sha,
            "changed_files": changed_files,
            "migrations": migrations,
        },
        "github": {
            "state": pull_request.get("state") if pull_request else None,
            "draft": pull_request.get("isDraft") if pull_request else None,
            "url": pull_request.get("url") if pull_request else None,
        },
        "checks": [check.canonical() for check in sorted(checks, key=lambda item: item.check_id)],
        "overall": overall.value,
        "readiness": "READY FOR SEMANTIC AUDIT" if overall == AuditStatus.PASS else overall.value,
    }
    context = {
        "profile_path": profile_path,
        "profile": profile,
        "pull_request": pull_request,
    }
    return {"evidence": evidence, "context": context}, checks


def _render_text(evidence: Mapping[str, Any]) -> str:
    lines = [
        "GATE PRE-AUDIT",
        "",
        f"Gate: {evidence['gate']}",
        f"PR: #{evidence['pr']}",
        f"Head: {evidence['git']['pr_head'] or 'NOT_PROVEN'}",
        f"Base: {evidence['git']['base'] or 'NOT_PROVEN'}",
        "",
    ]
    for check in evidence["checks"]:
        requirement = "mandatory" if check["mandatory"] else "informational"
        lines.append(
            f"{check['label']:<32} {check['status']:<10} [{requirement}] {check['summary']}"
        )
    lines.extend(["", "OVERALL", str(evidence["readiness"]), ""])
    return "\n".join(lines)


def _validate_output_directory(repo: Path, output_dir: Path) -> Path:
    resolved_repo = repo.resolve()
    resolved_output = output_dir.resolve()
    try:
        relative = resolved_output.relative_to(resolved_repo)
    except ValueError:
        return resolved_output
    if relative == DEFAULT_OUTPUT_DIRECTORY or DEFAULT_OUTPUT_DIRECTORY in relative.parents:
        return resolved_output
    raise ValueError("an output directory inside the repository must stay below .gate-audit/")


def write_report(
    *,
    repo: Path,
    output_dir: Path,
    evidence: Mapping[str, Any],
    runner: CommandRunner,
    started_at: datetime,
    started_monotonic: float,
) -> tuple[Path, Path, dict[str, Any]]:
    output_dir = _validate_output_directory(repo, output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_hash = canonical_sha256(evidence)
    execution = {
        "generated_at": datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "started_at": started_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "duration_ms": round((time.monotonic() - started_monotonic) * 1000),
        "commands": [record.execution() for record in runner.records],
    }
    report = {
        "schema_version": REPORT_VERSION,
        "evidence": evidence,
        "evidence_sha256": evidence_hash,
        "execution": execution,
    }
    slug = re.sub(r"[^a-z0-9]+", "-", str(evidence["gate"]).casefold()).strip("-")
    stem = f"pr-{evidence['pr']}-{slug}"
    json_path = output_dir / f"{stem}.json"
    text_path = output_dir / f"{stem}.txt"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    text_path.write_text(_render_text(evidence), encoding="utf-8")
    return json_path, text_path, report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect and verify mechanical gate evidence without semantic approval."
    )
    parser.add_argument("--pr", type=int, required=True, help="GitHub pull request number")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="audited checkout")
    parser.add_argument("--profile", type=Path, help="explicit small gate profile")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="report directory (default: <repo>/.gate-audit)",
    )
    parser.add_argument(
        "--skip-local-validation",
        action="store_true",
        help="do not run local validation; mandatory command checks become NOT_PROVEN",
    )
    return parser


def main(argv: Sequence[str] | None = None, *, runner: CommandRunner | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.pr < 1:
        parser.error("--pr must be positive")
    repo = args.repo.resolve()
    output_dir = (args.output_dir or repo / DEFAULT_OUTPUT_DIRECTORY).resolve()
    started_at = datetime.now(UTC)
    started_monotonic = time.monotonic()
    active_runner = runner or CommandRunner()
    try:
        result, checks = run_audit(
            runner=active_runner,
            repo=repo,
            output_dir=output_dir,
            pr_number=args.pr,
            explicit_profile=args.profile,
            skip_local_validation=args.skip_local_validation,
        )
        json_path, text_path, report = write_report(
            repo=repo,
            output_dir=output_dir,
            evidence=result["evidence"],
            runner=active_runner,
            started_at=started_at,
            started_monotonic=started_monotonic,
        )
    except ValueError as exc:
        print(f"gate-pre-audit configuration error: {exc}", file=sys.stderr)
        return 3

    print(_render_text(report["evidence"]), end="")
    print(f"JSON: {json_path}")
    print(f"Text: {text_path}")
    overall = aggregate_status(checks)
    return {
        AuditStatus.PASS: 0,
        AuditStatus.FAIL: 1,
        AuditStatus.NOT_PROVEN: 2,
    }[overall]


if __name__ == "__main__":
    raise SystemExit(main())
