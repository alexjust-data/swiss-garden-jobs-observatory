from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from django.db import connection, transaction
from django.db.models import Model
from django.utils import timezone

from core.models import ReviewAuthorityLineageImport
from observations.models import (
    GreenRelevanceAssessment,
    GreenRelevanceReviewDecision,
    GreenRelevanceReviewDecisionApplication,
    PostingObservation,
)
from observations.review import GREEN_REVIEW_GOVERNANCE_VERSION
from observations.review_continuity import green_review_material_fingerprint
from vacancies.models import DedupDecision, DedupReviewDecisionApplication, DedupRun
from vacancies.review_continuity import (
    DEDUP_REVIEW_MATERIAL_VERSION,
    FROZEN_CONFIGURATION,
    reconstruct_source_human_material,
)

LINEAGE_VERSION = "review-authority-lineage-v0.1"
REGISTRY_VERSION = "review-authority-registry-v0.1"
GATE_SHAS = {
    "gate_011e": "cbf1054b329843ea3fff7eeac77ea9342df60147",
    "gate_011g": "3f8e5cacc191309188e142ebf28ae0d1115e95e7",
    "c1_baseline": "520b68d989d36abfc382143458b30d1f3bad96b2",
}
EXPECTED_GREEN_OUTCOMES = {
    "CONFIRMED_GREEN": 37,
    "CONFIRMED_NOT_GREEN": 16,
    "INSUFFICIENT_EVIDENCE": 2,
}
EXPECTED_DEDUP_DECISION_ID = "74550a24-4075-469c-946a-4ea48c045877"
EXPECTED_DEDUP_MATERIAL = "c9f0c0f6a4c0d57062bd15b8024dd434bee2d889a531b74d950277e77d518087"
SHA256 = re.compile(r"[0-9a-f]{64}")


class ReviewAuthorityLineageError(RuntimeError):
    pass


class ExactAuthorityTransplantNotPossible(ReviewAuthorityLineageError):
    pass


@dataclass(frozen=True)
class ImportResult:
    batch: ReviewAuthorityLineageImport
    imported_green: int
    reused_green: int
    imported_dedup: int
    reused_dedup: int
    imported_green_applications: int
    reused_green_applications: int
    imported_dedup_applications: int
    reused_dedup_applications: int


def canonical_value(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID | Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): canonical_value(value[key]) for key in sorted(value)}
    if isinstance(value, list | tuple):
        return [canonical_value(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(canonical_value(value), sort_keys=True, separators=(",", ":"))


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def model_payload(instance: Model) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for field in instance._meta.fields:
        fields[field.attname] = canonical_value(getattr(instance, field.attname))
    payload = {
        "model": instance._meta.label_lower,
        "pk": str(instance.pk),
        "fields": fields,
    }
    payload["row_sha256"] = sha256(payload)
    return payload


def verify_row(row: dict[str, Any]) -> None:
    supplied = row.get("row_sha256")
    unsigned = {key: value for key, value in row.items() if key != "row_sha256"}
    if not isinstance(supplied, str) or supplied != sha256(unsigned):
        raise ReviewAuthorityLineageError(
            f"row hash mismatch: {row.get('model')}:{row.get('pk')}"
        )


def _sorted_rows(instances: Iterable[Model]) -> list[dict[str, Any]]:
    return [model_payload(item) for item in sorted(instances, key=lambda value: str(value.pk))]


def _registry(green: list[GreenRelevanceReviewDecision], dedup: DedupDecision) -> dict[str, Any]:
    green_rows = []
    for decision in green:
        observation = decision.assessment.posting_observation
        green_rows.append(
            {
                "authority_type": "GREEN_HUMAN_DECISION",
                "authority_id": str(decision.pk),
                "governance_version": decision.governance_version,
                "outcome": decision.outcome,
                "reason_code": decision.reason_code,
                "assessment_id": str(decision.assessment.pk),
                "observation_id": str(observation.pk),
                "source_id": observation.source_id,
                "source_native_id": observation.source_posting_id,
                "raw_sha256": observation.raw_artifact.sha256_digest,
                "decision_row_sha256": model_payload(decision)["row_sha256"],
                "assessment_row_sha256": model_payload(decision.assessment)["row_sha256"],
                "observation_row_sha256": model_payload(observation)["row_sha256"],
                "material_fingerprint": green_review_material_fingerprint(
                    decision.assessment,
                    governance_version=decision.governance_version,
                ),
                "reviewed_at": decision.reviewed_at.isoformat(),
                "created_at": decision.created_at.isoformat(),
            }
        )
    proof = reconstruct_source_human_material(dedup, FROZEN_CONFIGURATION)
    return {
        "registry_version": REGISTRY_VERSION,
        "merged_governance": GATE_SHAS,
        "green_human_decisions": sorted(green_rows, key=lambda row: row["authority_id"]),
        "dedup_human_decisions": [
            {
                "authority_type": "DEDUP_HUMAN_DECISION",
                "authority_id": str(dedup.pk),
                "outcome": dedup.outcome,
                "dedup_version": dedup.dedup_version,
                "normalizer_version": dedup.normalizer_version,
                "dedup_run_id": str(dedup.dedup_run.pk),
                "algorithm_decision_id": str(proof.algorithm_decision.pk),
                "posting_ids": sorted((str(dedup.posting_a.pk), str(dedup.posting_b.pk))),
                "observation_ids": sorted(
                    (str(dedup.observation_a.pk), str(dedup.observation_b.pk))
                ),
                "material_version": DEDUP_REVIEW_MATERIAL_VERSION,
                "material_fingerprint": proof.material_fingerprint,
                "decision_row_sha256": model_payload(dedup)["row_sha256"],
                "algorithm_row_sha256": model_payload(proof.algorithm_decision)["row_sha256"],
                "dedup_run_row_sha256": model_payload(dedup.dedup_run)["row_sha256"],
                "created_at": dedup.created_at.isoformat(),
            }
        ],
    }


def export_package() -> tuple[dict[str, Any], dict[str, Any]]:
    """Export one coherent read-only snapshot from the configured source database."""

    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        green = list(
            GreenRelevanceReviewDecision.objects.filter(
                governance_version=GREEN_REVIEW_GOVERNANCE_VERSION
            )
            .select_related(
                "assessment__posting_observation__source",
                "assessment__posting_observation__raw_artifact",
            )
            .order_by("pk")
        )
        outcomes: dict[str, int] = {}
        for decision in green:
            outcomes[decision.outcome] = outcomes.get(decision.outcome, 0) + 1
            decision.full_clean()
        if len(green) != 55 or outcomes != EXPECTED_GREEN_OUTCOMES:
            raise ReviewAuthorityLineageError(
                f"merged green authority differs: count={len(green)} outcomes={outcomes}"
            )
        human_dedup = list(
            DedupDecision.objects.filter(method=DedupDecision.Method.HUMAN).select_related(
                "dedup_run", "posting_a", "posting_b", "observation_a", "observation_b"
            )
        )
        if [str(item.pk) for item in human_dedup] != [EXPECTED_DEDUP_DECISION_ID]:
            raise ReviewAuthorityLineageError(
                "merged dedup authority differs: "
                f"{sorted(str(item.pk) for item in human_dedup)}"
            )
        dedup = human_dedup[0]
        proof = reconstruct_source_human_material(dedup, FROZEN_CONFIGURATION)
        if proof.material_fingerprint != EXPECTED_DEDUP_MATERIAL:
            raise ReviewAuthorityLineageError(
                f"dedup material differs: {proof.material_fingerprint}"
            )
        assessments = {str(item.assessment.pk): item.assessment for item in green}
        observations = {
            str(item.assessment.posting_observation_id): item.assessment.posting_observation
            for item in green
        }
        observations[str(dedup.observation_a_id)] = dedup.observation_a
        observations[str(dedup.observation_b_id)] = dedup.observation_b
        green_apps = list(
            GreenRelevanceReviewDecisionApplication.objects.select_related(
                "source_decision", "target_assessment__posting_observation"
            ).order_by("pk")
        )
        for application in green_apps:
            assessments[str(application.target_assessment_id)] = application.target_assessment
            observation = application.target_assessment.posting_observation
            observations[str(observation.pk)] = observation
        dedup_apps = list(
            DedupReviewDecisionApplication.objects.select_related(
                "source_human_decision",
                "target_algorithm_decision__dedup_run",
                "target_algorithm_decision__observation_a",
                "target_algorithm_decision__observation_b",
            ).order_by("pk")
        )
        target_algorithms = [application.target_algorithm_decision for application in dedup_apps]
        target_runs = {str(item.dedup_run_id): item.dedup_run for item in target_algorithms}
        for algorithm in target_algorithms:
            observations[str(algorithm.observation_a_id)] = algorithm.observation_a
            observations[str(algorithm.observation_b_id)] = algorithm.observation_b
        registry = _registry(green, dedup)
        rows = {
            "dependency_assessments": _sorted_rows(assessments.values()),
            "dependency_observations": _sorted_rows(observations.values()),
            "green_human_decisions": _sorted_rows(green),
            "authority_dependency_dedup_runs": _sorted_rows([dedup.dedup_run]),
            "authority_dependency_dedup_algorithms": _sorted_rows([proof.algorithm_decision]),
            "dependency_dedup_target_runs": _sorted_rows(target_runs.values()),
            "dependency_dedup_target_algorithms": _sorted_rows(target_algorithms),
            "dedup_human_decisions": _sorted_rows([dedup]),
            "green_applications": _sorted_rows(green_apps),
            "dedup_applications": _sorted_rows(dedup_apps),
        }
        snapshot_fingerprint = sha256(
            {
                name: [row["row_sha256"] for row in values]
                for name, values in sorted(rows.items())
            }
        )
        package: dict[str, Any] = {
            "manifest": {
                "lineage_version": LINEAGE_VERSION,
                "source_snapshot_method": "POSTGRESQL_REPEATABLE_READ_READ_ONLY",
                "source_snapshot_fingerprint": snapshot_fingerprint,
                "merged_governance": GATE_SHAS,
                "authority_registry_sha256": sha256(registry),
                "models_included": sorted(
                    {row["model"] for values in rows.values() for row in values}
                ),
                "models_explicitly_excluded": [
                    "sources.source",
                    "observations.collectionrun",
                    "observations.posting",
                    "observations.postinglifecycleevent",
                    "core.rawartifact",
                    "vacancies.vacancy",
                ],
                "counts": {name: len(values) for name, values in rows.items()},
            },
            "registry": registry,
            "rows": rows,
        }
        package["package_sha256"] = sha256(package)
        return package, registry


def verify_package(package: dict[str, Any], expected_registry: dict[str, Any]) -> None:
    supplied = package.get("package_sha256")
    unsigned = {key: value for key, value in package.items() if key != "package_sha256"}
    if not isinstance(supplied, str) or supplied != sha256(unsigned):
        raise ReviewAuthorityLineageError("package SHA-256 mismatch")
    manifest = package.get("manifest")
    if not isinstance(manifest, dict) or manifest.get("lineage_version") != LINEAGE_VERSION:
        raise ReviewAuthorityLineageError("unsupported lineage package version")
    if manifest.get("merged_governance") != GATE_SHAS:
        raise ReviewAuthorityLineageError("merged-governance evidence differs")
    if package.get("registry") != expected_registry:
        raise ReviewAuthorityLineageError("package registry differs from accepted registry")
    if manifest.get("authority_registry_sha256") != sha256(expected_registry):
        raise ReviewAuthorityLineageError("accepted registry fingerprint differs")
    rows = package.get("rows")
    if not isinstance(rows, dict):
        raise ReviewAuthorityLineageError("package rows are absent")
    allowed = {
        "dependency_assessments",
        "dependency_observations",
        "green_human_decisions",
        "authority_dependency_dedup_runs",
        "authority_dependency_dedup_algorithms",
        "dependency_dedup_target_runs",
        "dependency_dedup_target_algorithms",
        "dedup_human_decisions",
        "green_applications",
        "dedup_applications",
    }
    if set(rows) != allowed:
        raise ReviewAuthorityLineageError("package contains unsupported row classes")
    for values in rows.values():
        if not isinstance(values, list):
            raise ReviewAuthorityLineageError("package row collection is malformed")
        for row in values:
            verify_row(row)
            if row.get("model") not in MODEL_MAP:
                raise ReviewAuthorityLineageError(
                    f"package contains unsupported model: {row.get('model')}"
                )
    if len(rows["green_human_decisions"]) != 55:
        raise ReviewAuthorityLineageError("package does not contain all 55 green authorities")
    if len(rows["dedup_human_decisions"]) != 1:
        raise ReviewAuthorityLineageError("package does not contain exactly one dedup authority")
    green_registry = expected_registry.get("green_human_decisions")
    dedup_registry = expected_registry.get("dedup_human_decisions")
    if not isinstance(green_registry, list) or not isinstance(dedup_registry, list):
        raise ReviewAuthorityLineageError("accepted authority registry is malformed")
    outcomes: dict[str, int] = {}
    green_by_id = {row["pk"]: row for row in rows["green_human_decisions"]}
    assessment_by_id = {row["pk"]: row for row in rows["dependency_assessments"]}
    observation_by_id = {row["pk"]: row for row in rows["dependency_observations"]}
    for authority in green_registry:
        outcomes[authority["outcome"]] = outcomes.get(authority["outcome"], 0) + 1
        decision = green_by_id.get(authority["authority_id"])
        assessment = assessment_by_id.get(authority["assessment_id"])
        observation = observation_by_id.get(authority["observation_id"])
        if decision is None or assessment is None or observation is None:
            raise ReviewAuthorityLineageError("registry authority dependency is absent")
        expected_hashes = {
            "decision_row_sha256": decision["row_sha256"],
            "assessment_row_sha256": assessment["row_sha256"],
            "observation_row_sha256": observation["row_sha256"],
        }
        if any(authority.get(key) != value for key, value in expected_hashes.items()):
            raise ReviewAuthorityLineageError("registry green row hash differs")
    if len(green_registry) != 55 or outcomes != EXPECTED_GREEN_OUTCOMES:
        raise ReviewAuthorityLineageError("accepted green authority aggregate differs")
    if len(dedup_registry) != 1:
        raise ReviewAuthorityLineageError("accepted dedup registry aggregate differs")
    dedup_authority = dedup_registry[0]
    if (
        dedup_authority.get("authority_id") != EXPECTED_DEDUP_DECISION_ID
        or dedup_authority.get("outcome") != DedupDecision.Outcome.KEEP_SEPARATE
        or dedup_authority.get("material_fingerprint") != EXPECTED_DEDUP_MATERIAL
    ):
        raise ReviewAuthorityLineageError("accepted dedup authority differs")
    dedup_decision = rows["dedup_human_decisions"][0]
    dedup_algorithm = rows["authority_dependency_dedup_algorithms"][0]
    dedup_run = rows["authority_dependency_dedup_runs"][0]
    if any(
        dedup_authority.get(key) != value
        for key, value in {
            "decision_row_sha256": dedup_decision["row_sha256"],
            "algorithm_row_sha256": dedup_algorithm["row_sha256"],
            "dedup_run_row_sha256": dedup_run["row_sha256"],
        }.items()
    ):
        raise ReviewAuthorityLineageError("registry dedup row hash differs")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReviewAuthorityLineageError(f"JSON object required: {path}")
    return value


def verify_registry_against_merged_governance(
    registry: dict[str, Any], governance_document: Path
) -> None:
    """Mechanically reconcile every green authority with the merged 011E table."""

    uuid_pattern = re.compile(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    )
    expected: dict[str, dict[str, str]] = {}
    for line in governance_document.read_text(encoding="utf-8").splitlines():
        if not re.match(r"^\|\s*\d+\s*\|", line):
            continue
        columns = re.split(r"(?<!\\)\|", line)
        if len(columns) < 11:
            raise ReviewAuthorityLineageError("malformed merged GATE-011E authority row")
        identity_ids = uuid_pattern.findall(columns[2])
        source_tokens = re.findall(r"`([^`]+)`", columns[3])
        raw_match = re.search(r"raw `([0-9a-f]{64})`", columns[5])
        outcome_tokens = re.findall(r"`([^`]+)`", columns[8])
        metadata_tokens = re.findall(r"`([^`]+)`", columns[9])
        if (
            len(identity_ids) != 2
            or len(source_tokens) < 3
            or raw_match is None
            or len(outcome_tokens) < 2
            or len(metadata_tokens) < 2
        ):
            raise ReviewAuthorityLineageError("incomplete merged GATE-011E authority row")
        assessment_id, decision_id = identity_ids
        observation_id = source_tokens[0]
        if not uuid_pattern.fullmatch(observation_id):
            raise ReviewAuthorityLineageError("merged GATE-011E observation ID is malformed")
        expected[decision_id] = {
            "assessment_id": assessment_id,
            "observation_id": observation_id,
            "source_id": source_tokens[1],
            "source_native_id": source_tokens[2],
            "raw_sha256": raw_match.group(1),
            "outcome": outcome_tokens[0],
            "reason_code": outcome_tokens[1],
            "reviewed_at": metadata_tokens[0],
            "governance_version": metadata_tokens[1],
        }
    if len(expected) != 55:
        raise ReviewAuthorityLineageError(
            f"merged GATE-011E registry contains {len(expected)} rows, expected 55"
        )
    actual = {
        row["authority_id"]: {
            key: row[key] for key in expected[row["authority_id"]]
        }
        for row in registry["green_human_decisions"]
        if row["authority_id"] in expected
    }
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(
            {row["authority_id"] for row in registry["green_human_decisions"]} - set(expected)
        )
        differing = sorted(
            decision_id
            for decision_id in set(actual) & set(expected)
            if actual[decision_id] != expected[decision_id]
        )
        raise ReviewAuthorityLineageError(
            f"source authority differs from merged governance: "
            f"missing={missing} extra={extra} differing={differing}"
        )


MODEL_MAP: dict[str, type[Model]] = {
    "observations.greenrelevanceassessment": GreenRelevanceAssessment,
    "observations.postingobservation": PostingObservation,
    "observations.greenrelevancereviewdecision": GreenRelevanceReviewDecision,
    "observations.greenrelevancereviewdecisionapplication": (
        GreenRelevanceReviewDecisionApplication
    ),
    "vacancies.deduprun": DedupRun,
    "vacancies.dedupdecision": DedupDecision,
    "vacancies.dedupreviewdecisionapplication": DedupReviewDecisionApplication,
}


def _instance(row: dict[str, Any]) -> Model:
    try:
        model = MODEL_MAP[row["model"]]
    except (KeyError, TypeError) as exc:
        raise ReviewAuthorityLineageError(f"unsupported model row: {row.get('model')}") from exc
    values: dict[str, Any] = {}
    supplied = row.get("fields")
    if not isinstance(supplied, dict):
        raise ReviewAuthorityLineageError("row fields are malformed")
    expected_names = {field.attname for field in model._meta.fields}
    if set(supplied) != expected_names:
        raise ReviewAuthorityLineageError(
            f"field set differs for {row['model']}:{row['pk']}"
        )
    for field in model._meta.fields:
        value = supplied[field.attname]
        if field.is_relation and value is not None:
            value = cast(Any, field).target_field.to_python(value)
        else:
            value = field.to_python(value)
        values[field.attname] = value
    return model(**values)


def _existing_for_row(row: dict[str, Any]) -> Model | None:
    model = MODEL_MAP[row["model"]]
    return model._default_manager.filter(pk=row["pk"]).first()


def _require_identical(row: dict[str, Any], *, label: str) -> Model:
    existing = _existing_for_row(row)
    if existing is None:
        raise ExactAuthorityTransplantNotPossible(
            f"DEPENDENCY_MISSING {label} {row['model']}:{row['pk']}"
        )
    if model_payload(existing) != row:
        raise ExactAuthorityTransplantNotPossible(
            f"PRESENT_CONFLICTING {label} {row['model']}:{row['pk']}"
        )
    return existing


def _insert_or_reuse(row: dict[str, Any], *, label: str) -> tuple[Model, bool]:
    existing = _existing_for_row(row)
    if existing is not None:
        if model_payload(existing) != row:
            raise ExactAuthorityTransplantNotPossible(
                f"ID_CONFLICT {label} {row['model']}:{row['pk']}"
            )
        return existing, False
    instance = _instance(row)
    instance.full_clean()
    instance.save(force_insert=True)
    if model_payload(instance) != row:
        raise ExactAuthorityTransplantNotPossible(
            f"post-insert identity differs {label} {row['model']}:{row['pk']}"
        )
    return instance, True


def _target_prestate(package: dict[str, Any]) -> str:
    state: list[dict[str, Any]] = []
    for category, rows in sorted(package["rows"].items()):
        for row in rows:
            existing = _existing_for_row(row)
            state.append(
                {
                    "category": category,
                    "model": row["model"],
                    "pk": row["pk"],
                    "target_row_sha256": (
                        model_payload(existing)["row_sha256"] if existing is not None else None
                    ),
                }
            )
    return sha256(state)


def _unique_authority_collisions(package: dict[str, Any]) -> None:
    for row in package["rows"]["green_human_decisions"]:
        fields = row["fields"]
        collision = GreenRelevanceReviewDecision.objects.filter(
            assessment_id=fields["assessment_id"],
            governance_version=fields["governance_version"],
        ).exclude(pk=row["pk"])
        if collision.exists():
            raise ExactAuthorityTransplantNotPossible(
                f"UNIQUE_KEY_CONFLICT green authority {row['pk']}"
            )
    for category in (
        "authority_dependency_dedup_runs",
        "authority_dependency_dedup_algorithms",
        "dedup_human_decisions",
    ):
        for row in package["rows"][category]:
            fields = row["fields"]
            if row["model"] == "vacancies.deduprun":
                run_collision = DedupRun.objects.filter(
                    dedup_version=fields["dedup_version"],
                    as_of=fields["as_of"],
                    input_fingerprint=fields["input_fingerprint"],
                ).exclude(pk=row["pk"])
                if run_collision.exists():
                    raise ExactAuthorityTransplantNotPossible(
                        f"UNIQUE_KEY_CONFLICT {category} {row['pk']}"
                    )
            else:
                decision_collision = DedupDecision.objects.filter(
                    dedup_run_id=fields["dedup_run_id"],
                    posting_a_id=fields["posting_a_id"],
                    posting_b_id=fields["posting_b_id"],
                    method=fields["method"],
                ).exclude(pk=row["pk"])
                if decision_collision.exists():
                    raise ExactAuthorityTransplantNotPossible(
                        f"UNIQUE_KEY_CONFLICT {category} {row['pk']}"
                    )


def _result_from_batch(
    batch: ReviewAuthorityLineageImport, *, replay: bool = False
) -> ImportResult:
    imported = batch.imported_authority_counts
    reused = batch.reused_authority_counts
    if replay:
        reused = {
            key: imported.get(key, 0) + reused.get(key, 0)
            for key in set(imported) | set(reused)
        }
        imported = {}
    return ImportResult(
        batch=batch,
        imported_green=imported.get("green_human_decisions", 0),
        reused_green=reused.get("green_human_decisions", 0),
        imported_dedup=imported.get("dedup_human_decisions", 0),
        reused_dedup=reused.get("dedup_human_decisions", 0),
        imported_green_applications=imported.get("green_applications", 0),
        reused_green_applications=reused.get("green_applications", 0),
        imported_dedup_applications=imported.get("dedup_applications", 0),
        reused_dedup_applications=reused.get("dedup_applications", 0),
    )


def _verify_existing_batch_rows(package: dict[str, Any]) -> None:
    rows = package["rows"]
    for category in (
        "authority_dependency_dedup_runs",
        "authority_dependency_dedup_algorithms",
        "green_human_decisions",
        "dedup_human_decisions",
    ):
        for row in rows[category]:
            _require_identical(row, label=f"previously imported {category}")
    assessments = {row["pk"]: row for row in rows["dependency_assessments"]}
    for row in rows["green_applications"]:
        target_row = assessments.get(row["fields"]["target_assessment_id"])
        target = _existing_for_row(target_row) if target_row else None
        existing = _existing_for_row(row)
        if target_row is not None and target is not None and model_payload(target) == target_row:
            _require_identical(row, label="previously imported green application")
        elif existing is not None:
            if model_payload(existing) != row:
                raise ExactAuthorityTransplantNotPossible(
                    f"PRESENT_CONFLICTING skipped green application {row['pk']}"
                )
    algorithms = {row["pk"]: row for row in rows["dependency_dedup_target_algorithms"]}
    for row in rows["dedup_applications"]:
        target_row = algorithms.get(row["fields"]["target_algorithm_decision_id"])
        target = _existing_for_row(target_row) if target_row else None
        existing = _existing_for_row(row)
        if target_row is not None and target is not None and model_payload(target) == target_row:
            _require_identical(row, label="previously imported dedup application")
        elif existing is not None:
            if model_payload(existing) != row:
                raise ExactAuthorityTransplantNotPossible(
                    f"PRESENT_CONFLICTING skipped dedup application {row['pk']}"
                )


def import_package(
    package: dict[str, Any], expected_registry: dict[str, Any]
) -> ImportResult:
    """Preflight and atomically replicate exact authority into the configured target."""

    verify_package(package, expected_registry)
    existing_batch = ReviewAuthorityLineageImport.objects.filter(
        package_sha256=package["package_sha256"]
    ).first()
    if existing_batch is not None:
        if (
            existing_batch.lineage_version != LINEAGE_VERSION
            or existing_batch.authority_registry_sha256 != sha256(expected_registry)
            or existing_batch.source_snapshot_fingerprint
            != package["manifest"]["source_snapshot_fingerprint"]
            or existing_batch.source_gate_shas != GATE_SHAS
        ):
            raise ReviewAuthorityLineageError("existing lineage batch conflicts with package")
        _verify_existing_batch_rows(package)
        return _result_from_batch(existing_batch, replay=True)

    rows = package["rows"]
    authority_assessment_ids = {
        row["fields"]["assessment_id"] for row in rows["green_human_decisions"]
    }
    authority_observation_ids = {
        row["fields"]["posting_observation_id"]
        for row in rows["dependency_assessments"]
        if row["pk"] in authority_assessment_ids
    }
    dedup_human = rows["dedup_human_decisions"][0]
    authority_observation_ids.update(
        {
            dedup_human["fields"]["observation_a_id"],
            dedup_human["fields"]["observation_b_id"],
        }
    )
    assessments_by_id = {row["pk"]: row for row in rows["dependency_assessments"]}
    observations_by_id = {row["pk"]: row for row in rows["dependency_observations"]}
    for assessment_id in authority_assessment_ids:
        try:
            _require_identical(
                assessments_by_id[assessment_id], label="green authority assessment"
            )
        except KeyError as exc:
            raise ExactAuthorityTransplantNotPossible(
                f"DEPENDENCY_MISSING assessment package row {assessment_id}"
            ) from exc
    for observation_id in authority_observation_ids:
        try:
            _require_identical(
                observations_by_id[observation_id], label="authority observation"
            )
        except KeyError as exc:
            raise ExactAuthorityTransplantNotPossible(
                f"DEPENDENCY_MISSING observation package row {observation_id}"
            ) from exc
    _unique_authority_collisions(package)
    target_prestate = _target_prestate(package)
    imported = {
        "green_human_decisions": 0,
        "dedup_human_decisions": 0,
        "green_applications": 0,
        "dedup_applications": 0,
        "dedup_dependency_rows": 0,
        "green_applications_regenerate": 0,
        "dedup_applications_regenerate": 0,
    }
    reused = {key: 0 for key in imported}
    with transaction.atomic():
        for category in (
            "authority_dependency_dedup_runs",
            "authority_dependency_dedup_algorithms",
        ):
            for row in rows[category]:
                _, created = _insert_or_reuse(row, label=category)
                (imported if created else reused)["dedup_dependency_rows"] += 1
        algorithm_id = expected_registry["dedup_human_decisions"][0][
            "algorithm_decision_id"
        ]
        algorithm = DedupDecision.objects.get(pk=algorithm_id)
        selected_human = cast(DedupDecision, _instance(dedup_human))
        selected_human.dedup_run = algorithm.dedup_run
        proof = reconstruct_source_human_material(selected_human, FROZEN_CONFIGURATION)
        if proof.material_fingerprint != EXPECTED_DEDUP_MATERIAL:
            raise ExactAuthorityTransplantNotPossible(
                f"target dedup material differs: {proof.material_fingerprint}"
            )
        for row in rows["green_human_decisions"]:
            _, created = _insert_or_reuse(row, label="green human authority")
            (imported if created else reused)["green_human_decisions"] += 1
        _, created = _insert_or_reuse(dedup_human, label="dedup human authority")
        (imported if created else reused)["dedup_human_decisions"] += 1

        for row in rows["green_applications"]:
            target_id = row["fields"]["target_assessment_id"]
            dependency = assessments_by_id.get(target_id)
            target = _existing_for_row(dependency) if dependency else None
            if dependency is None or target is None or model_payload(target) != dependency:
                imported["green_applications_regenerate"] += 1
                continue
            _, created = _insert_or_reuse(row, label="derived green application")
            (imported if created else reused)["green_applications"] += 1
        target_algorithms = {
            row["pk"]: row for row in rows["dependency_dedup_target_algorithms"]
        }
        for row in rows["dedup_applications"]:
            target_id = row["fields"]["target_algorithm_decision_id"]
            dependency = target_algorithms.get(target_id)
            target = _existing_for_row(dependency) if dependency else None
            if dependency is None or target is None or model_payload(target) != dependency:
                imported["dedup_applications_regenerate"] += 1
                continue
            _, created = _insert_or_reuse(row, label="derived dedup application")
            (imported if created else reused)["dedup_applications"] += 1
        batch_input = {
            "lineage_version": LINEAGE_VERSION,
            "package_sha256": package["package_sha256"],
            "authority_registry_sha256": sha256(expected_registry),
            "source_snapshot_fingerprint": package["manifest"][
                "source_snapshot_fingerprint"
            ],
            "target_prestate_fingerprint": target_prestate,
            "source_gate_shas": GATE_SHAS,
        }
        batch = ReviewAuthorityLineageImport(
            lineage_version=LINEAGE_VERSION,
            package_sha256=package["package_sha256"],
            authority_registry_sha256=sha256(expected_registry),
            source_snapshot_fingerprint=package["manifest"][
                "source_snapshot_fingerprint"
            ],
            source_gate_shas=GATE_SHAS,
            target_prestate_fingerprint=target_prestate,
            imported_authority_counts=imported,
            reused_authority_counts=reused,
            conflict_counts={"total": 0},
            replicated_at=timezone.now(),
            input_fingerprint=sha256(batch_input),
        )
        batch.save()
    return _result_from_batch(batch)
