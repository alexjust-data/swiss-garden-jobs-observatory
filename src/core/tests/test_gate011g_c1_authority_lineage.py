from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from django.core.exceptions import ValidationError

from core.models import (
    ImmutableReviewAuthorityLineageImportError,
    ReviewAuthorityLineageImport,
)
from core.review_authority_lineage import (
    EXPECTED_DEDUP_DECISION_ID,
    EXPECTED_DEDUP_MATERIAL,
    GATE_SHAS,
    LINEAGE_VERSION,
    MODEL_MAP,
    ReviewAuthorityLineageError,
    import_package,
    lineage_batch_input_fingerprint,
    load_json,
    package_designation,
    sha256,
    verify_package,
    verify_package_designation,
    verify_registry_against_merged_governance,
)
from core.review_authority_package import (
    canonical_json,
    canonical_value,
    relationship_graph,
    row_hash_inventory,
    source_snapshot_fingerprint,
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
    decisions: list[dict[str, Any]] = []
    assessments: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    green_registry: list[dict[str, Any]] = []
    for index, outcome in enumerate(outcomes):
        decision_id = f"decision-{index:02d}"
        assessment_id = f"assessment-{index:02d}"
        observation_id = f"observation-{index:02d}"
        decision = _row(
            "observations.greenrelevancereviewdecision",
            decision_id,
            {
                "assessment_id": assessment_id,
                "outcome": outcome,
                "evidence": {"bounded": index},
            },
        )
        assessment = _row(
            "observations.greenrelevanceassessment",
            assessment_id,
            {"posting_observation_id": observation_id, "result": "REVIEW"},
        )
        observation = _row(
            "observations.postingobservation",
            observation_id,
            {"source_posting_id": str(index)},
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
        "vacancies.dedupdecision",
        "algorithm",
        {"dedup_run_id": "dedup-run", "method": "RULE_SCORE"},
    )
    human = _row(
        "vacancies.dedupdecision",
        EXPECTED_DEDUP_DECISION_ID,
        {
            "dedup_run_id": "dedup-run",
            "method": "HUMAN",
            "outcome": "KEEP_SEPARATE",
            "evidence": {"algorithm_decision_id": "algorithm"},
        },
    )
    registry: dict[str, Any] = {
        "registry_version": "review-authority-registry-v0.1",
        "merged_governance": GATE_SHAS,
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
    counts = {name: len(values) for name, values in rows.items()}
    models = sorted({row["model"] for values in rows.values() for row in values})
    graph = relationship_graph(rows, MODEL_MAP)
    metadata = {
        "database_identity": {"vendor": "postgresql", "database_name": "source-evidence"},
        "server_identity": {
            "vendor": "postgresql",
            "server_version_num": "170000",
            "server_address_sha256": "a" * 64,
        },
        "transaction_snapshot": "100:200:",
        "export_started_at": "2026-08-13T20:00:00.000000Z",
        "transaction_started_at": "2026-08-13T20:00:00.000000Z",
        "migration_inventory": [{"app": "core", "name": "0002_previous"}],
        "merged_governance": GATE_SHAS,
        "bounded_source_metadata": {
            "row_counts": counts,
            "models_included": models,
            "green_authority_outcomes": {
                "CONFIRMED_GREEN": 37,
                "CONFIRMED_NOT_GREEN": 16,
                "INSUFFICIENT_EVIDENCE": 2,
            },
            "green_authority_count": 55,
            "dedup_human_authority_count": 1,
        },
    }
    snapshot = source_snapshot_fingerprint(metadata, row_hash_inventory(rows), graph)
    package: dict[str, Any] = {
        "manifest": {
            "lineage_version": LINEAGE_VERSION,
            "source_snapshot_method": "POSTGRESQL_REPEATABLE_READ_READ_ONLY",
            "source_snapshot_fingerprint": snapshot,
            "merged_governance": GATE_SHAS,
            "authority_registry_sha256": sha256(registry),
            "models_included": models,
            "models_explicitly_excluded": [],
            "counts": counts,
        },
        "source_snapshot_metadata": metadata,
        "relationship_graph": graph,
        "registry": registry,
        "rows": rows,
    }
    package["package_sha256"] = sha256(package)
    return package, registry


def _resign(package: dict[str, Any]) -> None:
    package.pop("package_sha256", None)
    package["package_sha256"] = sha256(package)


def _batch_values(package_sha: str = "a" * 64) -> dict[str, Any]:
    imported = {"green_human_decisions": 55, "dedup_human_decisions": 1}
    reused = {"green_human_decisions": 0, "dedup_human_decisions": 0}
    conflicts = {"total": 0}
    values: dict[str, Any] = {
        "lineage_version": LINEAGE_VERSION,
        "package_sha256": package_sha,
        "authority_registry_sha256": "b" * 64,
        "source_snapshot_fingerprint": "c" * 64,
        "source_gate_shas": GATE_SHAS,
        "target_prestate_fingerprint": "d" * 64,
        "imported_authority_counts": imported,
        "reused_authority_counts": reused,
        "conflict_counts": conflicts,
    }
    values["input_fingerprint"] = lineage_batch_input_fingerprint(**values)
    return values


def test_canonical_json_and_timestamps_are_deterministic() -> None:
    assert canonical_json({"b": [2, 1], "a": {"z": 3}}) == canonical_json(
        {"a": {"z": 3}, "b": [2, 1]}
    )
    assert canonical_value(datetime(2026, 8, 13, 20, tzinfo=UTC)) == (
        "2026-08-13T20:00:00.000000Z"
    )
    instant = datetime(2026, 8, 13, 20, 0, 0, 123456, tzinfo=UTC)
    assert canonical_value(instant) == "2026-08-13T20:00:00.123456Z"
    assert canonical_value(instant.astimezone(timezone(timedelta(hours=2)))) == canonical_value(
        instant
    )
    with pytest.raises(ValueError, match="naive datetime"):
        canonical_value(datetime(2026, 8, 13, 20))


def test_empty_dedup_hard_barriers_are_valid_material_evidence() -> None:
    field = DedupDecision._meta.get_field("hard_barriers")
    assert getattr(field, "blank") is True
    assert getattr(field, "get_default")() == []


def test_package_verification_recomputes_manifest_snapshot_and_graph() -> None:
    package, registry = _package_fixture()
    verify_package(package, registry)

    cases = [
        ("metadata", "source snapshot fingerprint"),
        ("transaction", "source snapshot fingerprint"),
        ("migration", "source snapshot fingerprint"),
        ("count", "manifest counts"),
        ("models", "manifest models"),
        ("graph", "relationship graph"),
        ("missing_edge", "relationship graph"),
        ("fingerprint", "source snapshot fingerprint"),
    ]
    for case, message in cases:
        altered = copy.deepcopy(package)
        if case == "metadata":
            altered["source_snapshot_metadata"]["database_identity"]["database_name"] = "other"
        elif case == "transaction":
            altered["source_snapshot_metadata"]["transaction_snapshot"] = "101:201:"
        elif case == "migration":
            altered["source_snapshot_metadata"]["migration_inventory"][0]["name"] = "forged"
        elif case == "count":
            altered["manifest"]["counts"]["green_human_decisions"] = 54
        elif case == "models":
            altered["manifest"]["models_included"] = []
        elif case == "graph":
            altered["relationship_graph"][0]["target_pk"] = "forged"
        elif case == "missing_edge":
            altered["relationship_graph"].pop()
        else:
            altered["manifest"]["source_snapshot_fingerprint"] = "f" * 64
        _resign(altered)
        with pytest.raises(ReviewAuthorityLineageError, match=message):
            verify_package(altered, registry)


def test_package_designation_pins_first_import_identity() -> None:
    package, registry = _package_fixture()
    designation = package_designation(package, registry)
    verify_package_designation(package, registry, designation)
    altered = copy.deepcopy(designation)
    altered["package_sha256"] = "f" * 64
    with pytest.raises(ReviewAuthorityLineageError, match="audited designation"):
        verify_package_designation(package, registry, altered)


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
def test_lineage_batch_is_append_only_at_instance_queryset_and_manager_layers() -> None:
    batch = ReviewAuthorityLineageImport.objects.create(**_batch_values())
    batch.conflict_counts = {"total": 1}
    with pytest.raises(ImmutableReviewAuthorityLineageImportError):
        batch.save()
    with pytest.raises(ImmutableReviewAuthorityLineageImportError):
        batch.delete()
    with pytest.raises(ImmutableReviewAuthorityLineageImportError):
        ReviewAuthorityLineageImport.objects.filter(pk=batch.pk).update(
            package_sha256="f" * 64
        )
    with pytest.raises(ImmutableReviewAuthorityLineageImportError):
        ReviewAuthorityLineageImport.objects.filter(pk=batch.pk).delete()
    with pytest.raises(ImmutableReviewAuthorityLineageImportError):
        ReviewAuthorityLineageImport.objects.bulk_update([batch], ["package_sha256"])


@pytest.mark.django_db
def test_one_package_per_lineage_fails_closed_before_authority_mutation() -> None:
    ReviewAuthorityLineageImport.objects.create(**_batch_values("a" * 64))
    package, registry = _package_fixture()
    designation = package_designation(package, registry)
    with pytest.raises(ReviewAuthorityLineageError, match="different package"):
        import_package(package, registry, designation)
    conflicting = _batch_values("f" * 64)
    conflicting["input_fingerprint"] = lineage_batch_input_fingerprint(**{
        key: value for key, value in conflicting.items() if key != "input_fingerprint"
    })
    with pytest.raises(ValidationError):
        ReviewAuthorityLineageImport.objects.create(**conflicting)
