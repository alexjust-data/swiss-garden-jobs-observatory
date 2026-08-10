from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import connection, transaction

from dashboard.models import DashboardSnapshot, DashboardVacancyRecord
from observations.models import CollectionRun, GeocodingReviewItem
from premium_segments.models import PremiumSegmentReviewItem, PremiumSegmentRun
from sources.models import Source
from vacancies.models import DedupReviewItem, DedupRun

from .models import (
    Day0ReadinessAssessment,
    Day0ReadinessSourceEvidence,
    Day0SourceUniverse,
    Day0SourceUniverseEntry,
)

SOURCE_UNIVERSE_VERSION = "day0-source-universe-v0.1"
POLICY_VERSION = "day0-authorization-policy-proposed-v0.1"
READINESS_VERSION = "day0-readiness-v0.1"
METRIC_VERSION = "day0-coverage-metrics-v0.1"
THRESHOLD_POLICY_STATUS = Day0SourceUniverse.ThresholdPolicyStatus.PENDING

REQUIRED_CITY_IDS = {
    "SRC-OFF-CITY-ZURICH",
    "SRC-OFF-CITY-WINTERTHUR",
    "SRC-OFF-CITY-BERN",
    "SRC-OFF-CITY-LUZERN",
    "SRC-OFF-CITY-STGALLEN",
    "SRC-OFF-CITY-SCHAFFHAUSEN",
}
SUPPORTING_IDS = {
    "SRC-PUB-JOBROOM-DISCOVERY",
    "SRC-OFF-GSZ-ZURICH",
    "SRC-OFF-GREEN-BERN",
    "SRC-OFF-BASEL-STADTGAERTNEREI",
}
NOT_APPLICABLE_IDS = {
    "SRC-REF-BFS-GEOGRAPHY",
    "SRC-PUB-JOBROOM-PUBLISHING-API",
    "SRC-STAT-AMSTAT",
    "SRC-SALARY-LOHNRECHNER",
    "SRC-SALARY-LOHNBUCH",
}


class Day0ContractError(ValueError):
    pass


@dataclass(frozen=True)
class SourceEvidencePlan:
    entry: Day0SourceUniverseEntry
    run: CollectionRun | None
    complete: bool
    healthy: bool
    evidence: dict[str, Any]


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def _frozen_path(name: str) -> Path:
    return Path(settings.BASE_DIR) / "docs" / "research" / "v0_4" / name


def _frozen_rows() -> list[dict[str, str]]:
    with _frozen_path("source_registry.csv").open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _value(row: dict[str, str], *names: str) -> str:
    for name in names:
        if row.get(name):
            return row[name].strip()
    return ""


def _source_id(row: dict[str, str]) -> str:
    return _value(row, "source_id", "id")


def _priority(row: dict[str, str]) -> str:
    return _value(row, "priority", "source_priority")


def _family(row: dict[str, str]) -> str:
    return _value(row, "source_family", "family", "source_type", "source_category")


def _is_required(row: dict[str, str]) -> bool:
    source_id = _source_id(row)
    family = _family(row).casefold()
    if source_id in REQUIRED_CITY_IDS:
        return True
    if _priority(row) != "P0":
        return False
    return "canton" in family or "federal" in family


def _target_role(row: dict[str, str]) -> str:
    source_id = _source_id(row)
    if source_id in NOT_APPLICABLE_IDS:
        return Day0SourceUniverseEntry.TargetRole.NONE
    if _is_required(row):
        return Day0SourceUniverseEntry.TargetRole.REQUIRED
    if source_id in SUPPORTING_IDS or _priority(row) == "P1":
        return Day0SourceUniverseEntry.TargetRole.SUPPORTING
    return Day0SourceUniverseEntry.TargetRole.NONE


def _has_access_blocker(row: dict[str, str]) -> bool:
    values = " ".join(
        _value(row, name)
        for name in (
            "automation_status",
            "legal_review_status",
            "verification_status",
            "access_method",
        )
    ).casefold()
    approved = ("approved" in values or "verified" in values) and not any(
        token in values for token in ("review_required", "pending", "blocked", "unsupported")
    )
    return not approved


def _entry_spec(row: dict[str, str]) -> dict[str, Any]:
    source_id = _source_id(row)
    target_role = _target_role(row)
    if source_id in NOT_APPLICABLE_IDS:
        classification = Day0SourceUniverseEntry.Classification.NOT_APPLICABLE
        reason = (
            "Reference, publishing-only, statistical, or salary source; "
            "not a vacancy collection surface."
        )
    elif target_role != Day0SourceUniverseEntry.TargetRole.NONE and _has_access_blocker(row):
        classification = Day0SourceUniverseEntry.Classification.BLOCKED
        reason = (
            "Target source remains in the denominator but automation/access review is unresolved."
        )
    elif target_role == Day0SourceUniverseEntry.TargetRole.REQUIRED:
        classification = Day0SourceUniverseEntry.Classification.REQUIRED
        reason = "Minimum canonical federal, canton, or priority-city Day-0 cohort."
    elif target_role == Day0SourceUniverseEntry.TargetRole.SUPPORTING:
        classification = Day0SourceUniverseEntry.Classification.SUPPORTING
        reason = (
            "Adds sector, discovery, staffing, or specialist coverage without "
            "defining the core denominator."
        )
    else:
        classification = Day0SourceUniverseEntry.Classification.DEFERRED
        reason = (
            "Lower-priority regional/general source deferred until the required "
            "cohort is implemented."
        )

    if target_role == Day0SourceUniverseEntry.TargetRole.REQUIRED:
        batch = 1 if source_id in REQUIRED_CITY_IDS else 2
    elif target_role == Day0SourceUniverseEntry.TargetRole.SUPPORTING:
        family = _family(row).casefold()
        batch = 4 if "staff" in family or "ett" in family else 3
    else:
        batch = None

    implemented = source_id in {"SRC-OFF-CITY-WINTERTHUR", "SRC-OFF-CITY-ZURICH"}
    return {
        "classification": classification,
        "target_role": target_role,
        "reason": reason,
        "priority": _priority(row),
        "source_name": _value(row, "source_name", "name"),
        "source_family": _family(row),
        "source_type": _value(row, "source_type"),
        "platform_family": _value(row, "platform_family", "platform", "access_method"),
        "coverage_scope": _value(row, "coverage_scope", "geographic_scope", "region"),
        "canonicality": _value(row, "canonicality", "source_role", "role"),
        "automation_status": _value(row, "automation_status"),
        "legal_review_status": _value(row, "legal_review_status", "legal_status"),
        "verification_status": _value(row, "verification_status"),
        "existing_adapter_reuse": implemented,
        "new_adapter_required": not implemented,
        "blocking_issue": "ACCESS_OR_AUTOMATION_REVIEW"
        if _has_access_blocker(row) and target_role != Day0SourceUniverseEntry.TargetRole.NONE
        else "",
        "implementation_batch": batch,
    }


@transaction.atomic
def ensure_source_universe() -> Day0SourceUniverse:
    rows = _frozen_rows()
    registry_hash = hashlib.sha256(_frozen_path("source_registry.csv").read_bytes()).hexdigest()
    coverage_hash = hashlib.sha256(_frozen_path("coverage_matrix.csv").read_bytes()).hexdigest()
    source_ids = [_source_id(row) for row in rows]
    sources = {source.pk: source for source in Source.objects.filter(pk__in=source_ids)}
    missing = sorted(set(source_ids) - set(sources))
    if missing:
        raise Day0ContractError(
            f"Reference import is incomplete; missing {len(missing)} governed sources"
        )

    configuration = {
        "readiness_version": READINESS_VERSION,
        "metric_version": METRIC_VERSION,
        "accepted_threshold": None,
        "proposed_thresholds": ["1.00", "0.95", "0.90"],
        "required_city_ids": sorted(REQUIRED_CITY_IDS),
        "principle": "expected governed source coverage, not true market coverage",
    }
    fingerprint = _sha256(
        {
            "universe_version": SOURCE_UNIVERSE_VERSION,
            "policy_version": POLICY_VERSION,
            "registry_hash": registry_hash,
            "coverage_hash": coverage_hash,
            "entries": [{"source_id": _source_id(row), **_entry_spec(row)} for row in rows],
            "configuration": configuration,
        }
    )
    existing = Day0SourceUniverse.objects.filter(universe_version=SOURCE_UNIVERSE_VERSION).first()
    if existing:
        if existing.input_fingerprint != fingerprint:
            raise Day0ContractError("Source-universe version exists with different frozen inputs")
        return existing

    universe = Day0SourceUniverse.objects.create(
        universe_version=SOURCE_UNIVERSE_VERSION,
        policy_version=POLICY_VERSION,
        threshold_policy_status=THRESHOLD_POLICY_STATUS,
        required_completion_threshold=None,
        source_registry_sha256=registry_hash,
        coverage_matrix_sha256=coverage_hash,
        configuration=configuration,
        input_fingerprint=fingerprint,
    )
    Day0SourceUniverseEntry.objects.bulk_create(
        [
            Day0SourceUniverseEntry(
                universe=universe,
                source=sources[_source_id(row)],
                **_entry_spec(row),
            )
            for row in rows
        ]
    )
    return universe


def _complete_run(run: CollectionRun | None) -> tuple[bool, bool]:
    if run is None:
        return False, False
    healthy = run.source_health_status == "HEALTHY"
    complete = (
        run.run_scope == "FULL_SOURCE"
        and run.status == "SUCCEEDED"
        and healthy
        and run.snapshot_complete
        and run.listings_discovered == run.observations_created == run.green_assessments_created
    )
    return complete, healthy


def _source_plan(entry: Day0SourceUniverseEntry, as_of: datetime) -> SourceEvidencePlan:
    run = (
        CollectionRun.objects.filter(
            source=entry.source, finished_at__isnull=False, finished_at__lte=as_of
        )
        .order_by("-finished_at", "-started_at", "-pk")
        .first()
    )
    complete, healthy = _complete_run(run)
    evidence = {
        "classification": entry.classification,
        "target_role": entry.target_role,
        "run_id": str(run.pk) if run else None,
        "run_scope": run.run_scope if run else None,
        "status": run.status if run else None,
        "source_health": run.source_health_status if run else None,
        "snapshot_complete": run.snapshot_complete if run else False,
        "counts_equal": bool(
            run
            and run.listings_discovered == run.observations_created == run.green_assessments_created
        ),
    }
    return SourceEvidencePlan(
        entry=entry, run=run, complete=complete, healthy=healthy, evidence=evidence
    )


def _metric(
    numerator: int, denominator: int, definition: str, evidence_ids: list[str]
) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "ratio": str(Decimal(numerator) / Decimal(denominator)) if denominator else None,
        "definition": definition,
        "version": METRIC_VERSION,
        "evidence_ids": sorted(evidence_ids),
    }


def _validate_alignment(
    *,
    as_of: datetime,
    dedup_run: DedupRun,
    premium_run: PremiumSegmentRun,
    dashboard_snapshot: DashboardSnapshot,
) -> None:
    if any(item.status != "SUCCEEDED" for item in (dedup_run, premium_run)):
        raise Day0ContractError("Dedup and premium runs must be successful")
    if dedup_run.as_of != as_of or premium_run.as_of != as_of or dashboard_snapshot.as_of != as_of:
        raise Day0ContractError("All readiness inputs must have the exact same as_of")
    if (
        dashboard_snapshot.dedup_run.pk != dedup_run.pk
        or dashboard_snapshot.premium_run.pk != premium_run.pk
    ):
        raise Day0ContractError("Dashboard snapshot is not aligned to the selected upstream runs")


def _review_evidence(
    dedup_run: DedupRun,
    premium_run: PremiumSegmentRun,
    dashboard_snapshot: DashboardSnapshot,
) -> tuple[list[str], list[str]]:
    records = list(
        DashboardVacancyRecord.objects.filter(snapshot=dashboard_snapshot).values(
            "visibility_status",
            "mapping_status",
            "green_assessment_id",
            "premium_assessment_id",
            "canonical_posting_id",
            "canonical_observation_id",
            "location_resolution_id",
        )
    )
    public_postings = {
        row["canonical_posting_id"]
        for row in records
        if row["visibility_status"] == "PUBLIC_GREEN_CONFIRMED"
    }
    critical: list[str] = []
    noncritical: list[str] = []
    for dedup_review in DedupReviewItem.objects.filter(
        algorithm_decision__dedup_run=dedup_run, status="PENDING"
    ).select_related("algorithm_decision"):
        pair = {
            dedup_review.algorithm_decision.posting_a_id,
            dedup_review.algorithm_decision.posting_b_id,
        }
        target = critical if pair and pair.issubset(public_postings) else noncritical
        target.append(f"dedup:{dedup_review.pk}")

    public_observations = {
        row["canonical_observation_id"]
        for row in records
        if row["visibility_status"] == "PUBLIC_GREEN_CONFIRMED"
    }
    for premium_review in PremiumSegmentReviewItem.objects.filter(
        assessment__run=premium_run, status="PENDING"
    ).select_related("assessment"):
        target = (
            critical
            if premium_review.assessment.posting_observation_id in public_observations
            else noncritical
        )
        target.append(f"premium:{premium_review.pk}")
    for geocoding_review in GeocodingReviewItem.objects.filter(
        location_resolution_id__in=[
            row["location_resolution_id"]
            for row in records
            if row["location_resolution_id"] is not None
        ],
        review_status="PENDING",
    ):
        target = (
            critical
            if geocoding_review.posting_observation.pk in public_observations
            else noncritical
        )
        target.append(f"geospatial:{geocoding_review.pk}")

    for row in records:
        if row["visibility_status"] == "REVIEW_NOT_PUBLIC":
            critical.append(f"green:{row['green_assessment_id'] or row['canonical_posting_id']}")
        if row["visibility_status"] == "MISSING_GREEN_ASSESSMENT":
            critical.append(f"green-missing:{row['canonical_posting_id']}")
    return sorted(set(critical)), sorted(set(noncritical))


def _evaluate_status(
    universe: Day0SourceUniverse,
    required_complete: int,
    required_count: int,
    critical_count: int,
    access_blockers: int,
) -> str:
    if universe.threshold_policy_status == Day0SourceUniverse.ThresholdPolicyStatus.PENDING:
        return Day0ReadinessAssessment.Status.POLICY_PENDING
    if access_blockers:
        return Day0ReadinessAssessment.Status.BLOCKED_ACCESS
    if critical_count:
        return Day0ReadinessAssessment.Status.BLOCKED_QUALITY
    if not required_count or universe.required_completion_threshold is None:
        return Day0ReadinessAssessment.Status.NOT_READY
    ratio = Decimal(required_complete) / Decimal(required_count)
    if ratio < universe.required_completion_threshold:
        return Day0ReadinessAssessment.Status.NOT_READY
    return Day0ReadinessAssessment.Status.AUTHORIZED


def _advisory_lock(fingerprint: str) -> None:
    key = int(fingerprint[:15], 16)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])


@transaction.atomic
def assess_day0_readiness(
    *,
    as_of: datetime,
    dedup_run: DedupRun,
    premium_run: PremiumSegmentRun,
    dashboard_snapshot: DashboardSnapshot,
    source_universe: Day0SourceUniverse | None = None,
) -> tuple[Day0ReadinessAssessment, bool]:
    universe = source_universe or ensure_source_universe()
    if (
        universe.universe_version != SOURCE_UNIVERSE_VERSION
        or universe.policy_version != POLICY_VERSION
    ):
        raise Day0ContractError("Unsupported Day-0 source-universe or policy version")
    _validate_alignment(
        as_of=as_of,
        dedup_run=dedup_run,
        premium_run=premium_run,
        dashboard_snapshot=dashboard_snapshot,
    )
    entries = list(
        Day0SourceUniverseEntry.objects.filter(universe=universe).select_related("source")
    )
    plans = [_source_plan(entry, as_of) for entry in entries]
    required = [
        plan
        for plan in plans
        if plan.entry.target_role == Day0SourceUniverseEntry.TargetRole.REQUIRED
    ]
    supporting = [
        plan
        for plan in plans
        if plan.entry.target_role == Day0SourceUniverseEntry.TargetRole.SUPPORTING
    ]
    complete = [plan for plan in required if plan.complete]
    healthy = [plan for plan in required if plan.healthy]
    access_blockers = [
        plan
        for plan in required
        if plan.entry.classification == Day0SourceUniverseEntry.Classification.BLOCKED
    ]
    critical_ids, noncritical_ids = _review_evidence(dedup_run, premium_run, dashboard_snapshot)

    public_records = list(
        DashboardVacancyRecord.objects.filter(
            snapshot=dashboard_snapshot,
            visibility_status="PUBLIC_GREEN_CONFIRMED",
        ).select_related("dedup_run_vacancy_state")
    )
    known_position_records = [
        record for record in public_records if record.positions_count is not None
    ]
    known_positions_total = sum(record.positions_count or 0 for record in known_position_records)
    unknown_positions = len(public_records) - len(known_position_records)
    multi_hire = sum(bool(record.multi_hire_possible) for record in public_records)
    complete_ids = [str(plan.run.pk) for plan in complete if plan.run]
    healthy_ids = [str(plan.run.pk) for plan in healthy if plan.run]
    canonical_required = [
        plan for plan in required if "canonical" in plan.entry.canonicality.casefold()
    ]
    canonical_complete = [plan for plan in canonical_required if plan.complete]
    required_geographies = {
        plan.entry.coverage_scope or str(plan.entry.source.pk) for plan in required
    }
    covered_geographies = {
        plan.entry.coverage_scope or str(plan.entry.source.pk) for plan in complete
    }
    source_link_known = sum(
        record.source_link_status not in {"NO_LINK_AVAILABLE", "REVIEW"}
        for record in public_records
    )
    dedup_denominator = len(public_records) + len(
        [item for item in critical_ids if item.startswith("dedup:")]
    )
    metrics = {
        "required_source_run_coverage": _metric(
            len(complete),
            len(required),
            "Healthy, successful, complete FULL_SOURCE required runs",
            complete_ids,
        ),
        "source_health_coverage": _metric(
            len(healthy),
            len(required),
            "Required sources whose selected run is HEALTHY",
            healthy_ids,
        ),
        "canonical_source_coverage": _metric(
            len(canonical_complete),
            len(canonical_required),
            "Completed required sources marked canonical by governed registry evidence",
            complete_ids,
        ),
        "geographic_coverage": _metric(
            len(covered_geographies),
            len(required_geographies),
            "Governed required source scopes covered; not a job-count or true-market ratio",
            complete_ids,
        ),
        "publication_date_coverage": _metric(
            dashboard_snapshot.known_publication_date_count,
            dashboard_snapshot.public_green_eligible_count,
            "Public green vacancy records with governed source publication dates",
            [str(dashboard_snapshot.pk)],
        ),
        "geospatial_resolution_coverage": _metric(
            dashboard_snapshot.mappable_vacancy_count,
            dashboard_snapshot.public_green_eligible_count,
            "Public green records with safe public-display coordinates",
            [str(dashboard_snapshot.pk)],
        ),
        "green_classification_coverage": _metric(
            dashboard_snapshot.public_green_eligible_count
            + dashboard_snapshot.excluded_not_green_count
            + dashboard_snapshot.review_not_public_count,
            dashboard_snapshot.total_vacancy_states,
            "Run vacancy states with a selected green assessment outcome",
            [str(dashboard_snapshot.pk)],
        ),
        "dedup_resolution_quality": _metric(
            len(public_records),
            dedup_denominator,
            "Public records not affected by a critical pending dedup review",
            [
                str(dedup_run.pk),
                *[item for item in critical_ids if item.startswith("dedup:")],
            ],
        ),
        "position_count_disclosure_coverage": _metric(
            len(known_position_records),
            len(public_records),
            "Public unique vacancies with explicit advertised positions_count",
            [str(record.pk) for record in known_position_records],
        ),
        "source_link_provenance_coverage": _metric(
            source_link_known,
            len(public_records),
            "Public records with a governed, renderable source-link status",
            [str(record.pk) for record in public_records],
        ),
    }
    selected_run_ids = sorted(str(plan.run.pk) for plan in plans if plan.run)
    blockers: list[dict[str, Any]] = []
    if universe.threshold_policy_status == Day0SourceUniverse.ThresholdPolicyStatus.PENDING:
        blockers.append(
            {
                "code": "THRESHOLD_POLICY_PENDING",
                "detail": "No numeric Day-0 threshold is authorized by frozen research.",
            }
        )
    if access_blockers:
        blockers.append(
            {
                "code": "REQUIRED_SOURCE_ACCESS_REVIEW",
                "count": len(access_blockers),
                "source_ids": sorted(str(plan.entry.source.pk) for plan in access_blockers),
            }
        )
    if len(complete) < len(required):
        blockers.append(
            {
                "code": "REQUIRED_SOURCE_RUNS_INCOMPLETE",
                "complete": len(complete),
                "required": len(required),
            }
        )
    if critical_ids:
        blockers.append(
            {"code": "CRITICAL_REVIEWS", "count": len(critical_ids), "review_ids": critical_ids}
        )

    fingerprint_payload = {
        "readiness_version": READINESS_VERSION,
        "as_of": as_of.isoformat(),
        "source_universe": str(universe.pk),
        "source_universe_fingerprint": universe.input_fingerprint,
        "dedup_run": str(dedup_run.pk),
        "dedup_fingerprint": dedup_run.input_fingerprint,
        "premium_run": str(premium_run.pk),
        "premium_fingerprint": premium_run.input_fingerprint,
        "dashboard_snapshot": str(dashboard_snapshot.pk),
        "dashboard_fingerprint": dashboard_snapshot.input_fingerprint,
        "source_evidence": [
            {
                "entry": str(plan.entry.pk),
                "run": str(plan.run.pk) if plan.run else None,
                "evidence": plan.evidence,
            }
            for plan in sorted(plans, key=lambda item: str(item.entry.source.pk))
        ],
        "critical_reviews": critical_ids,
        "noncritical_reviews": noncritical_ids,
        "metrics": metrics,
    }
    fingerprint = _sha256(fingerprint_payload)
    _advisory_lock(fingerprint)
    existing = Day0ReadinessAssessment.objects.filter(input_fingerprint=fingerprint).first()
    if existing:
        return existing, True

    status = _evaluate_status(
        universe, len(complete), len(required), len(critical_ids), len(access_blockers)
    )
    assessment = Day0ReadinessAssessment.objects.create(
        as_of=as_of,
        source_universe=universe,
        readiness_version=READINESS_VERSION,
        policy_version=universe.policy_version,
        dedup_run=dedup_run,
        premium_run=premium_run,
        dashboard_snapshot=dashboard_snapshot,
        readiness_status=status,
        selected_source_ids=sorted(str(plan.entry.source.pk) for plan in plans),
        selected_collection_run_ids=selected_run_ids,
        metrics=metrics,
        critical_review_ids=critical_ids,
        noncritical_review_ids=noncritical_ids,
        blockers=blockers,
        required_source_count=len(required),
        supporting_source_count=len(supporting),
        deferred_source_count=sum(
            plan.entry.classification == Day0SourceUniverseEntry.Classification.DEFERRED
            for plan in plans
        ),
        blocked_source_count=sum(
            plan.entry.classification == Day0SourceUniverseEntry.Classification.BLOCKED
            for plan in plans
        ),
        implemented_required_source_count=len(complete),
        required_full_source_healthy_count=len(complete),
        required_source_completion_ratio=(
            Decimal(len(complete)) / Decimal(len(required)) if required else None
        ),
        healthy_source_ratio=(Decimal(len(healthy)) / Decimal(len(required)) if required else None),
        critical_review_count=len(critical_ids),
        noncritical_review_count=len(noncritical_ids),
        observed_postings=dashboard_snapshot.dedup_run.posting_assignments.count(),
        active_unique_vacancies=sum(record.vacancy_status == "ACTIVE" for record in public_records),
        known_positions_total=known_positions_total,
        vacancies_unknown_position_count=unknown_positions,
        multi_hire_possible_count=multi_hire,
        input_fingerprint=fingerprint,
    )
    Day0ReadinessSourceEvidence.objects.bulk_create(
        [
            Day0ReadinessSourceEvidence(
                assessment=assessment,
                universe_entry=plan.entry,
                source=plan.entry.source,
                collection_run=plan.run,
                completion_status=(
                    Day0ReadinessSourceEvidence.CompletionStatus.COMPLETE_HEALTHY
                    if plan.complete
                    else (
                        Day0ReadinessSourceEvidence.CompletionStatus.NO_ELIGIBLE_RUN
                        if plan.run is None
                        else Day0ReadinessSourceEvidence.CompletionStatus.INCOMPLETE
                    )
                ),
                is_complete=plan.complete,
                is_healthy=plan.healthy,
                evidence=plan.evidence,
            )
            for plan in plans
        ]
    )
    return assessment, False


def readiness_summary(assessment: Day0ReadinessAssessment, reused: bool) -> dict[str, Any]:
    return {
        "assessment_id": str(assessment.pk),
        "as_of": assessment.as_of.isoformat(),
        "status": assessment.readiness_status,
        "source_universe_version": assessment.source_universe.universe_version,
        "policy_version": assessment.policy_version,
        "threshold_policy_status": assessment.source_universe.threshold_policy_status,
        "input_fingerprint": assessment.input_fingerprint,
        "dedup_run_id": str(assessment.dedup_run.pk),
        "premium_run_id": str(assessment.premium_run.pk),
        "dashboard_snapshot_id": str(assessment.dashboard_snapshot.pk),
        "required_sources": assessment.required_source_count,
        "supporting_sources": assessment.supporting_source_count,
        "deferred_sources": assessment.deferred_source_count,
        "blocked_sources": assessment.blocked_source_count,
        "required_complete": assessment.implemented_required_source_count,
        "required_healthy": assessment.required_full_source_healthy_count,
        "observed_postings": assessment.observed_postings,
        "active_unique_vacancies": assessment.active_unique_vacancies,
        "known_positions_total": assessment.known_positions_total,
        "vacancies_unknown_position_count": assessment.vacancies_unknown_position_count,
        "multi_hire_possible_count": assessment.multi_hire_possible_count,
        "critical_review_count": len(assessment.critical_review_ids),
        "noncritical_review_count": len(assessment.noncritical_review_ids),
        "metrics": assessment.metrics,
        "blockers": assessment.blockers,
        "exact_replay_reused": reused,
    }
