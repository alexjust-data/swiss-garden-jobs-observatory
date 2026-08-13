from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from core.models import (
    ImmutableReviewAuthorityLineageImportError,
    ReviewAuthorityLineageImport,
)
from core.review_authority_lineage import (
    EXPECTED_DEDUP_DECISION_ID,
    EXPECTED_DEDUP_MATERIAL,
    GATE_SHAS,
    LINEAGE_VERSION,
    ReviewAuthorityLineageError,
    canonical_json,
    load_json,
    sha256,
    verify_package,
    verify_registry_against_merged_governance,
)
from vacancies.models import DedupDecision


def _row(model: str, pk: str, fields: dict[str, object]) -> dict[str, Any]:
    value: dict[str, Any] = {"model": model, "pk": pk, "fields": fields}
    value["row_sha256"] = sha256(value)
    return value


def _package_fixture() -> tuple[dict[str, Any], dict[str, Any]]:
    outcomes = ["CONFIRMED_GREEN"] * 37
    outcomes += ["CONFIRMED_NOT_GREEN"] * 16
    outcomes += ["INSUFFICIENT_EVIDENCE"] * 2
    decisions = []
    assessments = []
    observations = []
    green_registry = []
    for index, outcome in enumerate(outcomes):
        decision_id = f"decision-{index:02d}"
        assessment_id = f"assessment-{index:02d}"
        observation_id = f"observation-{index:02d}"
        decision = _row(
            "observations.greenrelevancereviewdecision",
            decision_id,
            {"outcome": outcome, "evidence": {"bounded": index}},
        )
        assessment = _row(
            "observations.greenrelevanceassessment", assessment_id, {"result": "REVIEW"}
        )
        observation = _row(
            "observations.postingobservation", observation_id, {"source_posting_id": str(index)}
        )
        decisions.append(decision)
        assessments.append(assessment)
        observations.append(observation)
        green_registry.append(
            {
                "authority_id": decision_id,
                "assessment_id": assessment_id,
                "observation_id": observation_id,
                "outcome": outcome,
                "decision_row_sha256": decision["row_sha256"],
                "assessment_row_sha256": assessment["row_sha256"],
                "observation_row_sha256": observation["row_sha256"],
            }
        )
    dedup_run = _row("vacancies.deduprun", "dedup-run", {"as_of": "2026-08-12"})
    algorithm = _row(
        "vacancies.dedupdecision", "algorithm", {"method": "RULE_SCORE"}
    )
    human = _row(
        "vacancies.dedupdecision",
        EXPECTED_DEDUP_DECISION_ID,
        {"method": "HUMAN", "outcome": "KEEP_SEPARATE"},
    )
    registry: dict[str, Any] = {
        "registry_version": "review-authority-registry-v0.1",
        "green_human_decisions": green_registry,
        "dedup_human_decisions": [
            {
                "authority_id": EXPECTED_DEDUP_DECISION_ID,
                "outcome": "KEEP_SEPARATE",
                "material_fingerprint": EXPECTED_DEDUP_MATERIAL,
                "decision_row_sha256": human["row_sha256"],
                "algorithm_row_sha256": algorithm["row_sha256"],
                "dedup_run_row_sha256": dedup_run["row_sha256"],
            }
        ],
    }
    rows = {
        "dependency_assessments": assessments,
        "dependency_observations": observations,
        "green_human_decisions": decisions,
        "authority_dependency_dedup_runs": [dedup_run],
        "authority_dependency_dedup_algorithms": [algorithm],
        "dependency_dedup_target_runs": [],
        "dependency_dedup_target_algorithms": [],
        "dedup_human_decisions": [human],
        "green_applications": [],
        "dedup_applications": [],
    }
    package: dict[str, Any] = {
        "manifest": {
            "lineage_version": LINEAGE_VERSION,
            "merged_governance": GATE_SHAS,
            "authority_registry_sha256": sha256(registry),
        },
        "registry": registry,
        "rows": rows,
    }
    package["package_sha256"] = sha256(package)
    return package, registry


def _resign(package: dict[str, Any]) -> None:
    package.pop("package_sha256", None)
    package["package_sha256"] = sha256(package)


def test_canonical_json_is_deterministic() -> None:
    assert canonical_json({"b": [2, 1], "a": {"z": 3}}) == canonical_json(
        {"a": {"z": 3}, "b": [2, 1]}
    )


def test_empty_dedup_hard_barriers_are_valid_material_evidence() -> None:
    field = DedupDecision._meta.get_field("hard_barriers")
    assert getattr(field, "blank") is True
    assert getattr(field, "get_default")() == []


def test_package_verification_rejects_tampering_and_unsupported_models() -> None:
    package, registry = _package_fixture()
    verify_package(package, registry)

    tampered = copy.deepcopy(package)
    tampered["rows"]["green_human_decisions"][0]["fields"]["evidence"] = {"false": True}
    tampered["rows"]["green_human_decisions"][0]["row_sha256"] = sha256(
        {
            key: value
            for key, value in tampered["rows"]["green_human_decisions"][0].items()
            if key != "row_sha256"
        }
    )
    _resign(tampered)
    with pytest.raises(ReviewAuthorityLineageError, match="registry green row hash differs"):
        verify_package(tampered, registry)

    unsupported = copy.deepcopy(package)
    unsupported["rows"]["dependency_observations"][0]["model"] = "sources.source"
    unsupported["rows"]["dependency_observations"][0]["row_sha256"] = sha256(
        {
            key: value
            for key, value in unsupported["rows"]["dependency_observations"][0].items()
            if key != "row_sha256"
        }
    )
    _resign(unsupported)
    with pytest.raises(ReviewAuthorityLineageError, match="unsupported model"):
        verify_package(unsupported, registry)


def test_registry_matches_all_merged_gate011e_rows() -> None:
    root = Path(__file__).resolve().parents[3]
    registry = load_json(root / "docs/day0/gate_011g_c1_review_authority_registry_v0_1.json")
    governance = root / "docs/day0/gate_011e_critical_review_resolution_v0_1.md"
    verify_registry_against_merged_governance(registry, governance)
    altered = copy.deepcopy(registry)
    altered["green_human_decisions"][0]["source_id"] = "SRC-FORGED"
    with pytest.raises(ReviewAuthorityLineageError, match="differs from merged governance"):
        verify_registry_against_merged_governance(altered, governance)


@pytest.mark.django_db
def test_lineage_batch_is_append_only_and_validates_hashes() -> None:
    batch = ReviewAuthorityLineageImport.objects.create(
        lineage_version=LINEAGE_VERSION,
        package_sha256="a" * 64,
        authority_registry_sha256="b" * 64,
        source_snapshot_fingerprint="c" * 64,
        source_gate_shas=GATE_SHAS,
        target_prestate_fingerprint="d" * 64,
        imported_authority_counts={"green": 55, "dedup": 1},
        reused_authority_counts={"green": 0, "dedup": 0},
        conflict_counts={"total": 0},
        input_fingerprint="e" * 64,
    )
    batch.conflict_counts = {"total": 1}
    with pytest.raises(ImmutableReviewAuthorityLineageImportError):
        batch.save()
    with pytest.raises(ImmutableReviewAuthorityLineageImportError):
        batch.delete()
