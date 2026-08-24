from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.gate_pre_audit import (
    AuditStatus,
    CheckResult,
    CommandRecord,
    CommandRunner,
    _ci_status,
    _github_checks,
    _local_validation_checks,
    _validate_output_directory,
    aggregate_status,
    canonical_sha256,
    discover_profile,
    load_profile,
    query_pull_request,
    run_audit,
    write_report,
)


def check(status: AuditStatus, *, mandatory: bool = True) -> CheckResult:
    return CheckResult(
        check_id=f"check-{status.value}-{mandatory}",
        label="check",
        status=status,
        mandatory=mandatory,
        source="test",
        summary="test",
    )


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def write_profile(
    path: Path,
    *,
    blob: str,
    base_sha: str = "b" * 40,
    extra: dict[str, object] | None = None,
) -> None:
    payload: dict[str, object] = {
        "schema_version": "gate-pre-audit-profile-v1",
        "gate": "GATE-TEST",
        "pr": 30,
        "expected_base_ref": "main",
        "expected_base_sha": base_sha,
        "expected_head_ref": "gate-test",
        "contract": "docs/contract.md",
        "contract_blob": blob,
        "frozen_paths": ["docs/research/v0_4/"],
        "focused_tests": [],
        "expected_migrations": [],
    }
    payload.update(extra or {})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def make_repository(tmp_path: Path) -> tuple[Path, str, str, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.name", "Gate Test")
    git(repo, "config", "user.email", "gate@example.invalid")
    frozen = repo / "docs/research/v0_4/frozen.md"
    frozen.parent.mkdir(parents=True)
    frozen.write_text("frozen\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")

    contract = repo / "docs/contract.md"
    contract.write_text("contract\n", encoding="utf-8")
    blob = git(repo, "hash-object", "docs/contract.md")
    profile_path = repo / "docs/governance/gate_profiles/gate-test.json"
    write_profile(profile_path, blob=blob, base_sha=base)
    (repo / "implementation.py").write_text("VALUE = 1\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "gate")
    head = git(repo, "rev-parse", "HEAD")
    return repo, base, head, profile_path


def pull_request(base: str, head: str) -> dict[str, object]:
    return {
        "number": 30,
        "state": "OPEN",
        "isDraft": True,
        "baseRefOid": base,
        "headRefOid": head,
        "baseRefName": "main",
        "headRefName": "gate-test",
        "url": "https://github.com/example/project/pull/30",
        "reviews": [],
        "statusCheckRollup": [
            {"name": "test", "status": "COMPLETED", "conclusion": "SUCCESS"},
            {
                "name": "GitGuardian Security Checks",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
            },
        ],
    }


def passed_github_checks(*args: object, **kwargs: object) -> list[CheckResult]:
    del args, kwargs
    return [
        CheckResult("github_pr", "GitHub PR metadata", AuditStatus.PASS, True, "test", "ok"),
        CheckResult("ci_exact_head", "Exact-head CI", AuditStatus.PASS, True, "test", "ok"),
        CheckResult("gitguardian", "GitGuardian", AuditStatus.PASS, True, "test", "ok"),
        CheckResult("review_threads", "Review threads", AuditStatus.PASS, True, "test", "0"),
    ]


@pytest.mark.parametrize(
    ("checks", "expected"),
    [
        ([check(AuditStatus.PASS)], AuditStatus.PASS),
        ([check(AuditStatus.PASS), check(AuditStatus.NOT_PROVEN)], AuditStatus.NOT_PROVEN),
        ([check(AuditStatus.NOT_PROVEN), check(AuditStatus.FAIL)], AuditStatus.FAIL),
        (
            [check(AuditStatus.PASS), check(AuditStatus.FAIL, mandatory=False)],
            AuditStatus.PASS,
        ),
    ],
)
def test_tri_state_aggregation(checks: list[CheckResult], expected: AuditStatus) -> None:
    assert aggregate_status(checks) == expected


def test_profile_is_small_and_rejects_arbitrary_commands(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.json"
    write_profile(profile_path, blob="a" * 40, extra={"commands": ["dangerous"]})
    with pytest.raises(ValueError, match="extra=.*commands"):
        load_profile(profile_path)


def test_canonical_evidence_hash_is_order_independent() -> None:
    assert canonical_sha256({"b": 2, "a": 1}) == canonical_sha256({"a": 1, "b": 2})


def test_ci_and_gitguardian_are_independently_classified() -> None:
    entries = [
        {"name": "test", "status": "COMPLETED", "conclusion": "SUCCESS"},
        {
            "name": "GitGuardian Security Checks",
            "status": "IN_PROGRESS",
            "conclusion": "",
        },
    ]
    assert _ci_status(entries, gitguardian=False) == AuditStatus.PASS
    assert _ci_status(entries, gitguardian=True) == AuditStatus.NOT_PROVEN


def test_github_absence_degrades_to_not_proven(tmp_path: Path) -> None:
    checks = _github_checks(CommandRunner(), tmp_path, 30, None)
    mandatory = [item for item in checks if item.mandatory]
    assert mandatory
    assert {item.status for item in mandatory} == {AuditStatus.NOT_PROVEN}


def test_output_inside_repository_is_restricted_to_gate_audit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    assert (
        _validate_output_directory(repo, repo / ".gate-audit" / "run")
        == (repo / ".gate-audit" / "run").resolve()
    )
    with pytest.raises(ValueError, match="must stay below .gate-audit"):
        _validate_output_directory(repo, repo / "reports")


def test_mechanical_git_checks_and_non_inference(tmp_path: Path) -> None:
    repo, base, head, profile_path = make_repository(tmp_path)
    with (
        patch("scripts.gate_pre_audit.query_pull_request", return_value=pull_request(base, head)),
        patch("scripts.gate_pre_audit._github_checks", side_effect=passed_github_checks),
    ):
        result, checks = run_audit(
            runner=CommandRunner(),
            repo=repo,
            output_dir=repo / ".gate-audit",
            pr_number=30,
            explicit_profile=profile_path,
            skip_local_validation=True,
        )

    by_id = {item.check_id: item for item in checks}
    assert by_id["head_exact"].status == AuditStatus.PASS
    assert by_id["git_clean_after_validation"].status == AuditStatus.PASS
    assert by_id["contract_blob"].status == AuditStatus.PASS
    assert by_id["frozen_paths"].status == AuditStatus.PASS
    assert by_id["migrations"].status == AuditStatus.PASS
    assert by_id["source_http"].status == AuditStatus.NOT_PROVEN
    assert by_id["source_http"].mandatory is False
    assert by_id["provider_http"].status == AuditStatus.NOT_PROVEN
    assert by_id["real_db_mutation"].status == AuditStatus.NOT_PROVEN
    assert by_id["exact_pit_replay"].status == AuditStatus.NOT_PROVEN
    assert result["evidence"]["readiness"] == AuditStatus.NOT_PROVEN.value


def test_contract_blob_drift_fails_closed(tmp_path: Path) -> None:
    repo, base, _, profile_path = make_repository(tmp_path)
    (repo / "docs/contract.md").write_text("changed contract\n", encoding="utf-8")
    git(repo, "add", "docs/contract.md")
    git(repo, "commit", "-m", "drift")
    head = git(repo, "rev-parse", "HEAD")
    with (
        patch("scripts.gate_pre_audit.query_pull_request", return_value=pull_request(base, head)),
        patch("scripts.gate_pre_audit._github_checks", side_effect=passed_github_checks),
    ):
        _, checks = run_audit(
            runner=CommandRunner(),
            repo=repo,
            output_dir=repo / ".gate-audit",
            pr_number=30,
            explicit_profile=profile_path,
            skip_local_validation=True,
        )
    by_id = {item.check_id: item for item in checks}
    assert by_id["contract_blob"].status == AuditStatus.FAIL
    assert aggregate_status(checks) == AuditStatus.FAIL


def test_report_hash_excludes_volatile_execution(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    evidence = {
        "gate": "GATE-TEST",
        "pr": 30,
        "git": {"pr_head": "a" * 40, "base": "b" * 40},
        "checks": [],
        "readiness": "READY FOR SEMANTIC AUDIT",
    }
    runner = CommandRunner()
    _, _, first = write_report(
        repo=repo,
        output_dir=repo / ".gate-audit",
        evidence=evidence,
        runner=runner,
        started_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        started_monotonic=0.0,
    )
    _, _, second = write_report(
        repo=repo,
        output_dir=repo / ".gate-audit",
        evidence=evidence,
        runner=runner,
        started_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        started_monotonic=1.0,
    )
    assert first["evidence_sha256"] == second["evidence_sha256"]
    assert first["execution"] != second["execution"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("contract", "../outside.md"),
        ("contract", "C:\\outside.md"),
        ("frozen_paths", [":(exclude)docs/research/v0_4/"]),
        ("focused_tests", ["--collect-only"]),
        ("focused_tests", ["src/core/tests/test_gate_pre_audit.py::test_name"]),
    ],
)
def test_profile_rejects_path_and_argument_injection(
    tmp_path: Path, field: str, value: object
) -> None:
    profile_path = tmp_path / "profile.json"
    write_profile(profile_path, blob="a" * 40, extra={field: value})
    with pytest.raises(ValueError):
        load_profile(profile_path)


def test_malformed_profile_fails_closed(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.json"
    profile_path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot read profile"):
        load_profile(profile_path)


def test_explicit_profile_must_use_governed_repository_directory(tmp_path: Path) -> None:
    repo, _, _, _ = make_repository(tmp_path)
    external = tmp_path / "alternate.json"
    write_profile(external, blob="a" * 40)
    with pytest.raises(ValueError, match="governed profile directory"):
        discover_profile(
            repo=repo,
            pr_number=30,
            explicit_path=external,
            changed_files=[],
        )


def test_missing_gh_returns_unavailable_metadata(tmp_path: Path) -> None:
    with patch("scripts.gate_pre_audit.subprocess.run", side_effect=FileNotFoundError("gh")):
        assert query_pull_request(CommandRunner(), tmp_path, 30) is None


def test_github_unavailable_is_not_proven_not_configuration_error(tmp_path: Path) -> None:
    repo, _, _, _ = make_repository(tmp_path)
    with patch("scripts.gate_pre_audit.query_pull_request", return_value=None):
        result, checks = run_audit(
            runner=CommandRunner(),
            repo=repo,
            output_dir=repo / ".gate-audit",
            pr_number=30,
            explicit_profile=None,
            skip_local_validation=True,
        )
    assert aggregate_status(checks) == AuditStatus.NOT_PROVEN
    assert result["evidence"]["readiness"] == AuditStatus.NOT_PROVEN.value


def test_stale_local_head_fails_closed(tmp_path: Path) -> None:
    repo, base, _, profile_path = make_repository(tmp_path)
    with (
        patch("scripts.gate_pre_audit.query_pull_request", return_value=pull_request(base, base)),
        patch("scripts.gate_pre_audit._github_checks", side_effect=passed_github_checks),
    ):
        _, checks = run_audit(
            runner=CommandRunner(),
            repo=repo,
            output_dir=repo / ".gate-audit",
            pr_number=30,
            explicit_profile=profile_path,
            skip_local_validation=True,
        )
    assert {item.check_id: item for item in checks}["head_exact"].status == AuditStatus.FAIL


def test_wrong_pr_base_fails_closed(tmp_path: Path) -> None:
    repo, _, head, profile_path = make_repository(tmp_path)
    with (
        patch("scripts.gate_pre_audit.query_pull_request", return_value=pull_request(head, head)),
        patch("scripts.gate_pre_audit._github_checks", side_effect=passed_github_checks),
    ):
        _, checks = run_audit(
            runner=CommandRunner(),
            repo=repo,
            output_dir=repo / ".gate-audit",
            pr_number=30,
            explicit_profile=profile_path,
            skip_local_validation=True,
        )
    assert {item.check_id: item for item in checks}["base_exact"].status == AuditStatus.FAIL


def test_dirty_untracked_tree_fails_closed(tmp_path: Path) -> None:
    repo, base, head, profile_path = make_repository(tmp_path)
    (repo / "untracked.txt").write_text("dirty\n", encoding="utf-8")
    with (
        patch("scripts.gate_pre_audit.query_pull_request", return_value=pull_request(base, head)),
        patch("scripts.gate_pre_audit._github_checks", side_effect=passed_github_checks),
    ):
        _, checks = run_audit(
            runner=CommandRunner(),
            repo=repo,
            output_dir=repo / ".gate-audit",
            pr_number=30,
            explicit_profile=profile_path,
            skip_local_validation=True,
        )
    by_id = {item.check_id: item for item in checks}
    assert by_id["git_clean"].status == AuditStatus.FAIL
    assert by_id["git_clean_after_validation"].status == AuditStatus.FAIL


def test_unexpected_migration_fails_closed(tmp_path: Path) -> None:
    repo, base, _, profile_path = make_repository(tmp_path)
    migration = repo / "src/example/migrations/0001_test.py"
    migration.parent.mkdir(parents=True)
    migration.write_text("# migration\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "migration")
    head = git(repo, "rev-parse", "HEAD")
    with (
        patch("scripts.gate_pre_audit.query_pull_request", return_value=pull_request(base, head)),
        patch("scripts.gate_pre_audit._github_checks", side_effect=passed_github_checks),
    ):
        _, checks = run_audit(
            runner=CommandRunner(),
            repo=repo,
            output_dir=repo / ".gate-audit",
            pr_number=30,
            explicit_profile=profile_path,
            skip_local_validation=True,
        )
    assert {item.check_id: item for item in checks}["migrations"].status == AuditStatus.FAIL


def test_frozen_research_change_fails_closed(tmp_path: Path) -> None:
    repo, base, _, profile_path = make_repository(tmp_path)
    frozen = repo / "docs/research/v0_4/frozen.md"
    frozen.write_text("changed\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "frozen drift")
    head = git(repo, "rev-parse", "HEAD")
    with (
        patch("scripts.gate_pre_audit.query_pull_request", return_value=pull_request(base, head)),
        patch("scripts.gate_pre_audit._github_checks", side_effect=passed_github_checks),
    ):
        _, checks = run_audit(
            runner=CommandRunner(),
            repo=repo,
            output_dir=repo / ".gate-audit",
            pr_number=30,
            explicit_profile=profile_path,
            skip_local_validation=True,
        )
    assert {item.check_id: item for item in checks}["frozen_paths"].status == AuditStatus.FAIL


class FailingValidationRunner(CommandRunner):
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout: int | None = None,
    ) -> CommandRecord:
        del env, timeout
        record = CommandRecord(tuple(argv), str(cwd), 1, "", "forced failure", 0)
        self.records.append(record)
        return record


def test_each_standard_validation_failure_is_mandatory(tmp_path: Path) -> None:
    repo, _, _, profile_path = make_repository(tmp_path)
    profile = load_profile(profile_path)
    checks = _local_validation_checks(
        FailingValidationRunner(),
        repo=repo,
        output_dir=repo / ".gate-audit",
        profile=profile,
        skip=False,
    )
    expected = {
        "pytest_full",
        "ruff",
        "mypy",
        "django_check",
        "migration_drift",
    }
    assert expected <= {item.check_id for item in checks}
    assert all(item.mandatory and item.status == AuditStatus.FAIL for item in checks)


class PaginatedGraphQLRunner(CommandRunner):
    def __init__(self) -> None:
        super().__init__()
        self.page = 0

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout: int | None = None,
    ) -> CommandRecord:
        del env, timeout
        self.page += 1
        has_next = self.page == 1
        payload = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [{"isResolved": self.page == 1}],
                            "pageInfo": {
                                "hasNextPage": has_next,
                                "endCursor": "next" if has_next else None,
                            },
                        }
                    }
                }
            }
        }
        record = CommandRecord(tuple(argv), str(cwd), 0, json.dumps(payload), "", 0)
        self.records.append(record)
        return record


def test_review_threads_are_paginated_before_pass_or_fail(tmp_path: Path) -> None:
    runner = PaginatedGraphQLRunner()
    checks = _github_checks(
        runner,
        tmp_path,
        30,
        pull_request("a" * 40, "b" * 40),
    )
    review = {item.check_id: item for item in checks}["review_threads"]
    assert runner.page == 2
    assert review.status == AuditStatus.FAIL
    assert review.details == {"unresolved": 1, "total": 2}


def test_informational_not_proven_does_not_poison_pass() -> None:
    checks = [
        check(AuditStatus.PASS),
        check(AuditStatus.NOT_PROVEN, mandatory=False),
    ]
    assert aggregate_status(checks) == AuditStatus.PASS


def test_wrong_pr_head_ref_fails_closed(tmp_path: Path) -> None:
    repo, base, head, profile_path = make_repository(tmp_path)
    metadata = pull_request(base, head)
    metadata["headRefName"] = "unexpected-branch"
    with (
        patch("scripts.gate_pre_audit.query_pull_request", return_value=metadata),
        patch("scripts.gate_pre_audit._github_checks", side_effect=passed_github_checks),
    ):
        _, checks = run_audit(
            runner=CommandRunner(),
            repo=repo,
            output_dir=repo / ".gate-audit",
            pr_number=30,
            explicit_profile=profile_path,
            skip_local_validation=True,
        )
    assert {item.check_id: item for item in checks}["head_ref"].status == AuditStatus.FAIL


def test_explicit_profile_for_another_pr_fails_closed(tmp_path: Path) -> None:
    repo, base, head, profile_path = make_repository(tmp_path)
    metadata = pull_request(base, head)
    metadata["number"] = 31
    with patch("scripts.gate_pre_audit.query_pull_request", return_value=metadata):
        with pytest.raises(ValueError, match="profile declares PR #30"):
            run_audit(
                runner=CommandRunner(),
                repo=repo,
                output_dir=repo / ".gate-audit",
                pr_number=31,
                explicit_profile=profile_path,
                skip_local_validation=True,
            )
