# mypy: disable-error-code="attr-defined,assignment"
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from django.conf import settings
from django.db import IntegrityError, connection, transaction

from dashboard.models import DashboardSnapshot, DashboardVacancyRecord
from observations.models import CollectionRun
from premium_segments.models import (
    PremiumSegmentAssessment,
    PremiumSegmentReviewItem,
    PremiumSegmentRun,
)
from sources.models import Source
from vacancies.models import DedupReviewItem, DedupRun, DedupRunPostingAssignment

from .models import (
    Day0AuthorizationPolicy,
    Day0AuthorizationPolicyDesignation,
    Day0ReadinessAssessment,
    Day0ReadinessSourceEvidence,
    Day0SourceUniverse,
    Day0SourceUniverseEntry,
)
from .policy import (
    AUTHORIZATION_POLICY_VERSION,
    COVERAGE_POLICY_VERSION,
    DERIVED_CANTON_FLOOR,
    FINAL_BLOCKED_REQUIRED_SOURCES,
    FRESHNESS_POLICY_VERSION,
    MAX_FULL_SOURCE_AGE_HOURS,
    MINIMUM_REQUIRED_SOURCE_COUNT,
    MINIMUM_REQUIRED_SOURCE_COVERAGE,
    READINESS_VERSION,
    REQUIRED_SOURCE_COUNT,
    REQUIRED_STRATUM_MINIMA,
    SOURCE_UNIVERSE_VERSION,
    VACANCY_CANONICALITY_VALUES,
    SourcePolicyError,
    assert_policy_ids_exist,
    classify_source,
)

POLICY_VERSION = AUTHORIZATION_POLICY_VERSION
METRIC_VERSION = "day0-coverage-metrics-v0.3"
CANONICAL_AUTHORIZATION_POLICY_FINGERPRINT = (
    "a72dd56dee6f6a580e1904c4e5427dd3dab9109775fd83722f2108cafb8d294e"
)
POLICY_DESIGNATION_VERSION = "day0-authorization-policy-designation-v0.1"
POLICY_AUTHORITY_EFFECTIVE_AT = datetime(2026, 8, 12, 8, 9, 55, tzinfo=UTC)
POLICY_AUTHORITY_EVIDENCE = {
    "pr_number": 19,
    "merged_sha": "1a1af1f5ac3fb2657d5b034cd6ff602a5c08cc5b",
    "final_policy_commit": "75cab6b54ea9295cf9f3c072b0f69243ecf6d95c",
    "final_tree_commit": "76c427ef9bf038872addfd32d1cfac3f633b04da",
    "adr_path": "docs/decisions/0015-gate-011d-day0-authorization-policy.md",
}


class Day0ContractError(ValueError):
    pass


@dataclass(frozen=True)
class SourceEvidencePlan:
    entry: Day0SourceUniverseEntry
    latest_activity_run: CollectionRun | None
    latest_full_source_run: CollectionRun | None
    latest_health_run: CollectionRun | None
    structurally_complete: bool
    currently_healthy: bool
    freshness_valid: bool | None
    terminal_disposition: str
    blocker_classification: str
    stratum: str
    evidence: dict[str, Any]


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def _frozen_path(name: str) -> Path:
    return Path(settings.BASE_DIR) / "docs" / "research" / "v0_4" / name


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _frozen_rows() -> list[dict[str, str]]:
    with _frozen_path("source_registry.csv").open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _source_id(row: dict[str, str]) -> str:
    return (row.get("source_id") or row.get("id") or "").strip()


def _entry_spec(source: Source) -> dict[str, Any]:
    try:
        decision = classify_source(source)
    except SourcePolicyError as exc:
        raise Day0ContractError(str(exc)) from exc
    if decision.target_role == "REQUIRED":
        batch = 1 if source.source_family == "OFFICIAL_MUNICIPAL" else 2
    elif decision.target_role == "SUPPORTING":
        family = source.source_family.casefold()
        batch = 4 if "staff" in family or "ett" in family else 3
    else:
        batch = None
    implemented = source.source_id in {"SRC-OFF-CITY-WINTERTHUR", "SRC-OFF-CITY-ZURICH"}
    blocked = decision.access_status == "BLOCKED_PENDING_ACCESS_REVIEW"
    return {
        "classification": decision.classification,
        "target_role": decision.target_role,
        "access_status": decision.access_status,
        "reason": decision.reason,
        "access_reason": decision.access_reason,
        "canton_code": decision.canton_code or "",
        "source_name": source.source_name,
        "source_family": source.source_family,
        "source_type": source.source_type,
        "priority": source.priority,
        "coverage_scope": source.coverage_scope,
        "canonicality": source.canonicality,
        "platform_family": source.platform_family,
        "automation_status": source.automation_status,
        "legal_review_status": source.legal_review_status,
        "verification_status": source.verification_status,
        "existing_adapter_reuse": implemented,
        "new_adapter_required": not implemented and decision.target_role != "NONE",
        "blocking_issue": decision.access_reason if blocked else "",
        "implementation_batch": batch,
    }


def canonical_authorization_policy_configuration() -> dict[str, Any]:
    return {
        "coverage_policy_version": COVERAGE_POLICY_VERSION,
        "freshness_policy_version": FRESHNESS_POLICY_VERSION,
        "authorization_policy_version": POLICY_VERSION,
        "denominator": REQUIRED_SOURCE_COUNT,
        "minimum_required_source_count": MINIMUM_REQUIRED_SOURCE_COUNT,
        "minimum_required_source_coverage": MINIMUM_REQUIRED_SOURCE_COVERAGE,
        "equal_source_weighting": True,
        "stratum_minima": REQUIRED_STRATUM_MINIMA,
        "derived_canton_floor": DERIVED_CANTON_FLOOR,
        "governed_disposition_required": REQUIRED_SOURCE_COUNT,
        "final_blocked_required_sources": FINAL_BLOCKED_REQUIRED_SOURCES,
        "freshness": {
            "timestamp": "CollectionRun.finished_at",
            "maximum_age_hours": MAX_FULL_SOURCE_AGE_HOURS,
            "boundary": "inclusive",
            "clock": "wall_clock",
            "selected_run": "latest_causally_available_HEALTHY_complete_FULL_SOURCE",
            "later_failed_activity": ("preserves accepted evidence but invalidates current health"),
        },
        "market_semantics": (
            "Observed active GREEN_CONFIRMED vacancies in fresh, healthy, complete "
            "required Sources at the exact PIT cutoff; never a national census or estimate."
        ),
        "alternatives_considered": ["1.00", "0.90", "0.80", "two_thirds"],
    }


def authorization_policy_artifact_fingerprint(configuration: dict[str, Any]) -> str:
    return _sha256(
        {
            "version": POLICY_VERSION,
            "threshold_status": "ACCEPTED",
            "freshness_status": "ACCEPTED",
            "configuration": configuration,
        }
    )


def _validate_canonical_policy_artifact(
    policy: Day0AuthorizationPolicy, configuration: dict[str, Any], fingerprint: str
) -> None:
    expected = {
        "policy_version": POLICY_VERSION,
        "threshold_policy_status": "ACCEPTED",
        "required_completion_threshold": Decimal(MINIMUM_REQUIRED_SOURCE_COVERAGE),
        "freshness_policy_status": "ACCEPTED",
        "required_source_max_age_hours": MAX_FULL_SOURCE_AGE_HOURS,
        "configuration": configuration,
        "input_fingerprint": fingerprint,
    }
    mismatched = [name for name, value in expected.items() if getattr(policy, name) != value]
    if mismatched:
        raise Day0ContractError(
            "Canonical authorization policy artifact is inconsistent: " + ", ".join(mismatched)
        )


def _validate_policy_designation(
    designation: Day0AuthorizationPolicyDesignation,
    policy: Day0AuthorizationPolicy,
) -> None:
    try:
        designation.full_clean()
    except Exception as exc:
        raise Day0ContractError("Invalid authorization policy designation") from exc
    expected = {
        "designation_version": POLICY_DESIGNATION_VERSION,
        "policy_version": POLICY_VERSION,
        "authoritative_policy_id": policy.pk,
        "authority_basis": "MERGED_GOVERNANCE_DECISION",
        "governance_evidence": POLICY_AUTHORITY_EVIDENCE,
        "effective_at": POLICY_AUTHORITY_EFFECTIVE_AT,
    }
    mismatched = [name for name, value in expected.items() if getattr(designation, name) != value]
    if mismatched:
        raise Day0ContractError(
            "Authorization policy designation conflicts with merged governance: "
            + ", ".join(mismatched)
        )


def ensure_authorization_policy_designation(
    policy: Day0AuthorizationPolicy,
) -> Day0AuthorizationPolicyDesignation:
    candidate = Day0AuthorizationPolicyDesignation(
        designation_version=POLICY_DESIGNATION_VERSION,
        policy_version=POLICY_VERSION,
        authoritative_policy=policy,
        authority_basis="MERGED_GOVERNANCE_DECISION",
        governance_evidence=POLICY_AUTHORITY_EVIDENCE,
        effective_at=POLICY_AUTHORITY_EFFECTIVE_AT,
    )
    candidate.input_fingerprint = candidate.expected_input_fingerprint()
    exact = Day0AuthorizationPolicyDesignation.objects.filter(
        input_fingerprint=candidate.input_fingerprint
    ).first()
    if exact:
        _validate_policy_designation(exact, policy)
        return exact
    conflict = Day0AuthorizationPolicyDesignation.objects.filter(
        designation_version=POLICY_DESIGNATION_VERSION,
        policy_version=POLICY_VERSION,
    ).first()
    if conflict:
        raise Day0ContractError("Conflicting authorization policy authority designation")
    try:
        with transaction.atomic():
            candidate.save()
    except IntegrityError:
        exact = Day0AuthorizationPolicyDesignation.objects.filter(
            input_fingerprint=candidate.input_fingerprint
        ).first()
        if exact is None:
            raise Day0ContractError(
                "Conflicting concurrent authorization policy authority designation"
            )
        _validate_policy_designation(exact, policy)
        return exact
    return candidate


@transaction.atomic
def ensure_authorization_policy() -> Day0AuthorizationPolicy:
    configuration = canonical_authorization_policy_configuration()
    fingerprint = authorization_policy_artifact_fingerprint(configuration)
    if fingerprint != CANONICAL_AUTHORIZATION_POLICY_FINGERPRINT:
        raise Day0ContractError("Generated v0.1 policy artifact does not match merged governance")
    policy = Day0AuthorizationPolicy.objects.filter(input_fingerprint=fingerprint).first()
    if policy is None:
        policy, _ = Day0AuthorizationPolicy.objects.get_or_create(
            input_fingerprint=fingerprint,
            defaults={
                "policy_version": POLICY_VERSION,
                "threshold_policy_status": "ACCEPTED",
                "required_completion_threshold": Decimal(MINIMUM_REQUIRED_SOURCE_COVERAGE),
                "freshness_policy_status": "ACCEPTED",
                "required_source_max_age_hours": MAX_FULL_SOURCE_AGE_HOURS,
                "configuration": configuration,
            },
        )
    _validate_canonical_policy_artifact(policy, configuration, fingerprint)
    designation = ensure_authorization_policy_designation(policy)
    _validate_policy_designation(designation, policy)
    return designation.authoritative_policy


@transaction.atomic
def ensure_source_universe() -> Day0SourceUniverse:
    try:
        assert_policy_ids_exist()
    except SourcePolicyError as exc:
        raise Day0ContractError(str(exc)) from exc
    ids = [_source_id(row) for row in _frozen_rows()]
    if len(ids) != len(set(ids)) or any(not item for item in ids):
        raise Day0ContractError("Frozen source registry IDs must be present and unique")
    sources = {str(source.pk): source for source in Source.objects.filter(pk__in=ids)}
    missing = sorted(set(ids) - set(sources))
    if missing:
        raise Day0ContractError(f"Frozen registry sources are not imported: {missing}")
    specs = [(sources[source_id], _entry_spec(sources[source_id])) for source_id in ids]
    registry_hash = _file_sha256(_frozen_path("source_registry.csv"))
    coverage_hash = _file_sha256(_frozen_path("coverage_matrix.csv"))
    configuration = {
        "selection": "frozen-field-rules-v0.2",
        "access_is_orthogonal": True,
        "geographic_coverage": "NOT_COMPUTABLE",
        "authorization_policy_version": POLICY_VERSION,
    }
    fingerprint = _sha256(
        {
            "version": SOURCE_UNIVERSE_VERSION,
            "registry": registry_hash,
            "coverage": coverage_hash,
            "configuration": configuration,
            "policy_version": POLICY_VERSION,
            "entries": [{"source_id": str(source.pk), **spec} for source, spec in specs],
        }
    )
    existing = Day0SourceUniverse.objects.filter(
        universe_version=SOURCE_UNIVERSE_VERSION, input_fingerprint=fingerprint
    ).first()
    if existing:
        return existing
    universe = Day0SourceUniverse.objects.create(
        universe_version=SOURCE_UNIVERSE_VERSION,
        policy_version=POLICY_VERSION,
        threshold_policy_status="ACCEPTED",
        required_completion_threshold=Decimal(MINIMUM_REQUIRED_SOURCE_COVERAGE),
        source_registry_sha256=registry_hash,
        coverage_matrix_sha256=coverage_hash,
        configuration=configuration,
        input_fingerprint=fingerprint,
    )
    rows = [
        Day0SourceUniverseEntry(universe=universe, source=source, **spec) for source, spec in specs
    ]
    for row in rows:
        row.full_clean()
    Day0SourceUniverseEntry.objects.bulk_create(rows)
    return universe


def _run_payload(run: CollectionRun | None) -> dict[str, Any] | None:
    if run is None:
        return None
    return {
        "id": str(run.pk),
        "source_id": str(run.source_id),
        "run_scope": run.run_scope,
        "status": run.status,
        "health": run.source_health_status,
        "snapshot_complete": run.snapshot_complete,
        "listings_discovered": run.listings_discovered,
        "listing_total_discovered": run.listing_total_discovered,
        "postings_in_scope": run.postings_in_scope,
        "details_fetched": run.details_fetched,
        "observations_created": run.observations_created,
        "green_assessments_created": run.green_assessments_created,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


def _structurally_complete(run: CollectionRun | None) -> bool:
    if run is None:
        return False
    counters = (
        run.listings_discovered,
        run.listing_total_discovered,
        run.postings_in_scope,
        run.details_fetched,
        run.observations_created,
        run.green_assessments_created,
    )
    return (
        run.run_scope == "FULL_SOURCE"
        and run.status == "SUCCEEDED"
        and run.snapshot_complete
        and len(set(counters)) == 1
    )


def _source_stratum(entry: Day0SourceUniverseEntry) -> str:
    if entry.source_family == "OFFICIAL_FEDERAL":
        return "FEDERAL"
    if entry.source_family == "OFFICIAL_CANTON":
        return "CANTON"
    if entry.source_family == "OFFICIAL_MUNICIPAL":
        return "CITY"
    return "OTHER"


def _source_plan(
    entry: Day0SourceUniverseEntry,
    as_of: datetime,
    policy: Day0AuthorizationPolicy,
) -> SourceEvidencePlan:
    runs = CollectionRun.objects.filter(
        source=entry.source, finished_at__isnull=False, finished_at__lte=as_of
    ).order_by("-finished_at", "-started_at", "-pk")
    activity = runs.first()
    full_attempts = list(runs.filter(run_scope="FULL_SOURCE"))
    latest_full_attempt = full_attempts[0] if full_attempts else None
    full = next(
        (
            run
            for run in full_attempts
            if _structurally_complete(run) and run.source_health_status == "HEALTHY"
        ),
        None,
    )
    health = activity
    source_id = str(entry.source_id)
    final_policy = policy.configuration.get("authorization_policy_version") == POLICY_VERSION
    if final_policy:
        blocker_classification = FINAL_BLOCKED_REQUIRED_SOURCES.get(source_id, "")
    else:
        blocker_classification = (
            "LEGACY_ACCESS_BLOCKED"
            if entry.classification == "BLOCKED_PENDING_ACCESS_REVIEW"
            else ""
        )
    terminal_disposition = "ACCEPTED_BLOCKED" if blocker_classification else "ACCEPTED_IMPLEMENTED"
    if terminal_disposition == "ACCEPTED_BLOCKED":
        full = None
    complete = terminal_disposition == "ACCEPTED_IMPLEMENTED" and _structurally_complete(full)
    healthy = bool(
        terminal_disposition == "ACCEPTED_IMPLEMENTED"
        and health
        and health.status == "SUCCEEDED"
        and health.source_health_status == "HEALTHY"
    )
    freshness: bool | None = False if terminal_disposition == "ACCEPTED_BLOCKED" else None
    if (
        policy.freshness_policy_status == "ACCEPTED"
        and policy.required_source_max_age_hours is not None
        and full
        and full.finished_at
    ):
        freshness = as_of - full.finished_at <= timedelta(
            hours=policy.required_source_max_age_hours
        )
    evidence = {
        "latest_activity_run": _run_payload(activity),
        "latest_full_source_attempt": _run_payload(latest_full_attempt),
        "latest_full_source_run": _run_payload(full),
        "latest_health_run": _run_payload(health),
        "structurally_complete": complete,
        "currently_healthy": healthy,
        "freshness_valid": freshness,
        "classification": entry.classification,
        "target_role": entry.target_role,
        "access_status": entry.access_status,
        "terminal_disposition": terminal_disposition,
        "blocker_classification": blocker_classification,
        "stratum": _source_stratum(entry),
        "freshness_state": (
            "BLOCKED"
            if terminal_disposition == "ACCEPTED_BLOCKED"
            else "FRESH"
            if freshness is True
            else "STALE"
            if freshness is False
            else "NO_ACCEPTED_RUN"
            if full is None
            else "POLICY_PENDING"
        ),
        "run_age_seconds": (
            int((as_of - full.finished_at).total_seconds())
            if full is not None and full.finished_at is not None
            else None
        ),
        "counts_toward_coverage": complete and healthy and freshness is True,
    }
    return SourceEvidencePlan(
        entry,
        activity,
        full,
        health,
        complete,
        healthy,
        freshness,
        terminal_disposition,
        blocker_classification,
        _source_stratum(entry),
        evidence,
    )


def _persisted_ratio(numerator: int, denominator: int) -> Decimal | None:
    if not denominator:
        return None
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.000001"))


def _metric(
    numerator: int | None,
    denominator: int | None,
    definition: str,
    evidence_ids: list[str],
    status: str = "COMPUTABLE",
) -> dict[str, Any]:
    ratio = None
    if status == "COMPUTABLE" and numerator is not None and denominator:
        ratio = str(Decimal(numerator) / Decimal(denominator))
    return {
        "version": METRIC_VERSION,
        "status": status,
        "numerator": numerator,
        "denominator": denominator,
        "ratio": ratio,
        "definition": definition,
        "evidence_ids": sorted(evidence_ids),
    }


def _validate_alignment(
    as_of: datetime,
    dedup_run: DedupRun,
    premium_run: PremiumSegmentRun,
    dashboard_snapshot: DashboardSnapshot,
) -> None:
    if dedup_run.status != "SUCCEEDED" or premium_run.status != "SUCCEEDED":
        raise Day0ContractError("Dedup and premium runs must be SUCCEEDED")
    if dedup_run.as_of != as_of or premium_run.as_of != as_of or dashboard_snapshot.as_of != as_of:
        raise Day0ContractError("All governed inputs must share readiness as_of")
    if (
        dashboard_snapshot.dedup_run_id != dedup_run.pk
        or dashboard_snapshot.premium_run_id != premium_run.pk
    ):
        raise Day0ContractError("Dashboard snapshot is not aligned to exact upstream runs")


def _review_evidence(
    dedup_run: DedupRun,
    premium_run: PremiumSegmentRun,
    dashboard_snapshot: DashboardSnapshot,
    eligible_source_ids: set[str],
) -> tuple[list[str], list[str], int, int, int]:
    critical: list[str] = []
    noncritical: list[str] = []
    active_canonical_observation_ids = set(
        DashboardVacancyRecord.objects.filter(
            snapshot=dashboard_snapshot,
            vacancy_status="ACTIVE",
        ).values_list("canonical_observation_id", flat=True)
    )
    assessments = list(
        PremiumSegmentAssessment.objects.filter(run=premium_run).select_related(
            "green_relevance_assessment", "green_review_decision", "posting_observation"
        )
    )
    observation_by_posting = {
        row.posting_observation.posting_id: row.posting_observation_id for row in assessments
    }
    active_observation_ids = {
        observation_by_posting[assignment.posting_id]
        for assignment in DedupRunPostingAssignment.objects.filter(
            dedup_run=dedup_run,
            run_vacancy_state__status="ACTIVE",
        )
        if assignment.posting_id in observation_by_posting
    }
    green_by_observation = {
        row.posting_observation_id: row.effective_green_result for row in assessments
    }
    green_reviews = [
        str(row.green_relevance_assessment_id)
        for row in assessments
        if row.green_relevance_assessment_id
        and row.effective_green_result == "REVIEW"
        and str(row.posting_observation.source_id) in eligible_source_ids
        and row.posting_observation_id in active_canonical_observation_ids
    ]
    excluded_green_reviews = [
        (
            str(row.green_relevance_assessment_id),
            (
                "green-excluded-source"
                if str(row.posting_observation.source_id) not in eligible_source_ids
                else "green-excluded-inactive"
            ),
        )
        for row in assessments
        if row.green_relevance_assessment_id
        and row.effective_green_result == "REVIEW"
        and (
            str(row.posting_observation.source_id) not in eligible_source_ids
            or row.posting_observation_id not in active_canonical_observation_ids
        )
    ]
    critical.extend(f"green:{item}" for item in green_reviews)
    noncritical.extend(f"{reason}:{item}" for item, reason in excluded_green_reviews)
    critical_dedup = 0
    reviews = DedupReviewItem.objects.filter(status="PENDING").select_related(
        "algorithm_decision__observation_a",
        "algorithm_decision__observation_b",
        "run_vacancy_state_a",
        "run_vacancy_state_b",
    )
    for review in reviews:
        decision = review.algorithm_decision
        if decision.dedup_run_id != dedup_run.pk:
            continue
        candidates = (
            (
                review.run_vacancy_state_a,
                decision.observation_a,
                green_by_observation.get(decision.observation_a_id),
            ),
            (
                review.run_vacancy_state_b,
                decision.observation_b,
                green_by_observation.get(decision.observation_b_id),
            ),
        )
        marker = f"dedup:{review.pk}"
        active_public_candidates = [
            (state, observation, green)
            for state, observation, green in candidates
            if state is not None
            and state.dedup_run_id == dedup_run.pk
            and state.status == "ACTIVE"
            and observation.pk in active_observation_ids
            and str(observation.source_id) in eligible_source_ids
            and green in {"GREEN_CONFIRMED", "REVIEW"}
        ]
        # KEEP_SEPARATE preserves these identities. MERGE can move their memberships,
        # recalculate the canonical Posting by precedence, and reconcile lifecycle.
        # One eligible active public-capable side is therefore sufficient; requiring
        # both sides ACTIVE would miss ACTIVE-vs-CLOSED identity/count effects.
        if active_public_candidates:
            critical.append(marker)
            critical_dedup += 1
        else:
            noncritical.append(marker)
    premium_reviews = PremiumSegmentReviewItem.objects.filter(
        assessment__run=premium_run,
        assessment__posting_observation__source_id__in=eligible_source_ids,
        assessment__posting_observation_id__in=active_canonical_observation_ids,
        status="PENDING",
    ).values_list("pk", flat=True)
    critical.extend(f"premium:{item}" for item in premium_reviews)
    location_reviews = DashboardVacancyRecord.objects.filter(
        snapshot=dashboard_snapshot,
        canonical_observation__source_id__in=eligible_source_ids,
        vacancy_status="ACTIVE",
        mapping_status="LOCATION_REVIEW",
    ).values_list("pk", flat=True)
    critical.extend(f"geospatial-record:{item}" for item in location_reviews)
    critical = sorted(set(critical))
    noncritical = sorted(set(noncritical))
    other = len(critical) - len(green_reviews) - critical_dedup
    return critical, noncritical, len(green_reviews), critical_dedup, other


def _evaluate_status(
    policy: Day0AuthorizationPolicy | Day0SourceUniverse,
    required_authorized: int,
    required_count: int,
    critical_count: int,
    access_blockers: int,
    governed_disposition_complete: bool = True,
    structural_coverage_pass: bool = True,
) -> str:
    freshness_status = getattr(policy, "freshness_policy_status", "ACCEPTED")
    if policy.threshold_policy_status == "PENDING" or freshness_status == "PENDING":
        return cast(str, Day0ReadinessAssessment.Status.POLICY_PENDING)
    if not governed_disposition_complete:
        return cast(str, Day0ReadinessAssessment.Status.NOT_READY)
    final_policy = policy.configuration.get("authorization_policy_version") == POLICY_VERSION
    if not final_policy and access_blockers:
        return cast(str, Day0ReadinessAssessment.Status.BLOCKED_ACCESS)
    if critical_count:
        return cast(str, Day0ReadinessAssessment.Status.BLOCKED_QUALITY)
    if not required_count or policy.required_completion_threshold is None:
        return cast(str, Day0ReadinessAssessment.Status.NOT_READY)
    ratio = Decimal(required_authorized) / Decimal(required_count)
    if ratio < policy.required_completion_threshold or not structural_coverage_pass:
        return cast(str, Day0ReadinessAssessment.Status.NOT_READY)
    return cast(str, Day0ReadinessAssessment.Status.AUTHORIZED)


def _advisory_lock(fingerprint: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [int(fingerprint[:15], 16)])


def _completion_status(plan: SourceEvidencePlan) -> str:
    if plan.latest_full_source_run is None:
        return "NO_ELIGIBLE_RUN"
    if not plan.structurally_complete:
        return "INCOMPLETE"
    if plan.latest_health_run and plan.latest_health_run.status == "FAILED":
        return "FAILED"
    if plan.latest_health_run and plan.latest_health_run.source_health_status == "OUTAGE":
        return "OUTAGE"
    if plan.latest_health_run and plan.latest_health_run.source_health_status == "DEGRADED":
        return "DEGRADED"
    if plan.currently_healthy and plan.freshness_valid is True:
        return "COMPLETE_HEALTHY"
    if plan.currently_healthy and plan.freshness_valid is None:
        return "COMPLETE_FRESHNESS_PENDING"
    return "INCOMPLETE"


@transaction.atomic
def assess_day0_readiness(
    *,
    as_of: datetime,
    dedup_run: DedupRun,
    premium_run: PremiumSegmentRun,
    dashboard_snapshot: DashboardSnapshot,
    source_universe: Day0SourceUniverse | None = None,
    authorization_policy: Day0AuthorizationPolicy | None = None,
) -> tuple[Day0ReadinessAssessment, bool]:
    universe = source_universe or ensure_source_universe()
    if authorization_policy is not None:
        policy = authorization_policy
        if policy.policy_version == POLICY_VERSION:
            authoritative = ensure_authorization_policy()
            if policy.pk != authoritative.pk:
                raise Day0ContractError(
                    "New readiness cannot use a non-authoritative v0.1 policy artifact"
                )
    elif source_universe is not None:
        if universe.configuration.get("authorization_policy_version") == POLICY_VERSION:
            policy = ensure_authorization_policy()
        else:
            _advisory_lock(_sha256({"fixture_policy": str(universe.pk)}))
            policy = Day0AuthorizationPolicy.objects.filter(
                policy_version=universe.policy_version
            ).first()
            if policy is None:
                accepted = universe.threshold_policy_status == "ACCEPTED"
                policy = Day0AuthorizationPolicy.objects.create(
                    policy_version=universe.policy_version,
                    threshold_policy_status=universe.threshold_policy_status,
                    required_completion_threshold=universe.required_completion_threshold,
                    freshness_policy_status="ACCEPTED" if accepted else "PENDING",
                    required_source_max_age_hours=1000000 if accepted else None,
                    configuration={"fixture_compatibility": True},
                    input_fingerprint=_sha256({"fixture_universe": str(universe.pk)}),
                )
    else:
        policy = ensure_authorization_policy()
    if universe.universe_version != SOURCE_UNIVERSE_VERSION:
        raise Day0ContractError("Unsupported Day-0 source-universe version")
    if universe.policy_version != policy.policy_version:
        raise Day0ContractError("Source universe and authorization policy versions differ")
    _validate_alignment(as_of, dedup_run, premium_run, dashboard_snapshot)
    plans = [
        _source_plan(entry, as_of, policy)
        for entry in Day0SourceUniverseEntry.objects.filter(universe=universe).select_related(
            "source"
        )
    ]
    required = [plan for plan in plans if plan.entry.target_role == "REQUIRED"]
    supporting = [plan for plan in plans if plan.entry.target_role == "SUPPORTING"]
    complete = [plan for plan in required if plan.structurally_complete]
    healthy = [plan for plan in required if plan.currently_healthy]
    fresh = [plan for plan in required if plan.freshness_valid is True]
    authorized = [
        plan
        for plan in required
        if plan.structurally_complete and plan.currently_healthy and plan.freshness_valid is True
    ]
    final_policy = policy.configuration.get("authorization_policy_version") == POLICY_VERSION
    market_plans = (
        authorized
        if final_policy
        else [plan for plan in required if plan.structurally_complete and plan.currently_healthy]
    )
    eligible_source_ids = {str(plan.entry.source_id) for plan in market_plans}
    blocked_required = [
        plan for plan in required if plan.terminal_disposition == "ACCEPTED_BLOCKED"
    ]
    governed_disposition_complete = all(
        plan.terminal_disposition in {"ACCEPTED_IMPLEMENTED", "ACCEPTED_BLOCKED"}
        for plan in required
    )
    if final_policy:
        governed_disposition_complete = (
            governed_disposition_complete and len(required) == REQUIRED_SOURCE_COUNT
        )
    stratum_minima = policy.configuration.get("stratum_minima", {})
    eligible_by_stratum = {
        stratum: sum(plan.stratum == stratum for plan in authorized) for stratum in stratum_minima
    }
    required_by_stratum = {
        stratum: sum(plan.stratum == stratum for plan in required) for stratum in stratum_minima
    }
    structural_coverage_pass = all(
        eligible_by_stratum[stratum] >= minimum for stratum, minimum in stratum_minima.items()
    )
    blocked_supporting = [
        plan for plan in supporting if plan.entry.access_status == "BLOCKED_PENDING_ACCESS_REVIEW"
    ]
    blocked_other = [
        plan
        for plan in plans
        if plan.entry.target_role == "NONE"
        and plan.entry.access_status == "BLOCKED_PENDING_ACCESS_REVIEW"
    ]
    critical, noncritical, critical_green, critical_dedup, other_critical = _review_evidence(
        dedup_run,
        premium_run,
        dashboard_snapshot,
        eligible_source_ids,
    )
    records = list(DashboardVacancyRecord.objects.filter(snapshot=dashboard_snapshot))
    public = [row for row in records if row.visibility_status == "PUBLIC_GREEN_CONFIRMED"]
    market = [
        row
        for row in public
        if str(row.canonical_observation.source_id) in eligible_source_ids
        and row.vacancy_status == "ACTIVE"
    ]
    known = [row for row in market if row.positions_count is not None]
    green_confirmed = sum(row.visibility_status == "PUBLIC_GREEN_CONFIRMED" for row in records)
    green_review = sum(row.visibility_status == "REVIEW_NOT_PUBLIC" for row in records)
    not_green = sum(row.visibility_status == "EXCLUDED_NOT_GREEN" for row in records)
    missing_green = sum(row.visibility_status == "MISSING_GREEN_ASSESSMENT" for row in records)
    canonical_required = [
        plan for plan in required if plan.entry.canonicality in VACANCY_CANONICALITY_VALUES
    ]
    canonical_complete = [plan for plan in canonical_required if plan.structurally_complete]
    metrics = {
        "governed_disposition_coverage": _metric(
            len(required) if governed_disposition_complete else 0,
            len(required),
            "Required Sources with an ACCEPTED_IMPLEMENTED or ACCEPTED_BLOCKED disposition.",
            [str(plan.entry.source_id) for plan in required],
        ),
        "day0_acquisition_coverage": _metric(
            len(authorized),
            len(required),
            (
                "Required Sources with accepted implementation plus fresh, healthy, "
                "structurally complete FULL_SOURCE evidence."
            ),
            [
                str(plan.latest_full_source_run.pk)
                for plan in authorized
                if plan.latest_full_source_run
            ],
        ),
        "day0_market_state": {
            "version": "day0-market-state-v0.1",
            "eligible_source_ids": sorted(eligible_source_ids),
            "canonicalization_rule": "CANONICAL_OBSERVATION_SOURCE_MUST_BE_ELIGIBLE",
            "green_confirmed_count": len(market),
            "active_unique_vacancies": sum(row.vacancy_status == "ACTIVE" for row in market),
            "known_positions_total": sum(row.positions_count or 0 for row in known),
            "unknown_position_vacancy_count": len(market) - len(known),
            "multi_hire_possible_count": sum(bool(row.multi_hire_possible) for row in market),
        },
        "corpus_diagnostics": {
            "dashboard_green_confirmed_count": len(public),
            "dashboard_green_review_count": green_review,
            "dashboard_record_count": len(records),
            "excluded_source_green_review_count": sum(
                marker.startswith("green-excluded-source:") for marker in noncritical
            ),
        },
        "day0_structural_coverage": {
            "version": METRIC_VERSION,
            "status": "PASS" if structural_coverage_pass else "FAIL",
            "eligible": eligible_by_stratum,
            "required": required_by_stratum,
            "minimum": stratum_minima,
            "derived_canton_floor_if_total_and_federal_pass": DERIVED_CANTON_FLOOR,
            "current_eligible_cantons": sum(plan.stratum == "CANTON" for plan in authorized),
        },
        "required_source_run_coverage": _metric(
            len(complete),
            len(required),
            "Required sources with structurally complete FULL_SOURCE evidence.",
            [
                str(plan.latest_full_source_run.pk)
                for plan in complete
                if plan.latest_full_source_run
            ],
        ),
        "source_health_coverage": _metric(
            len(healthy),
            len(required),
            "Required sources whose latest activity is SUCCEEDED and HEALTHY.",
            [str(plan.latest_health_run.pk) for plan in healthy if plan.latest_health_run],
        ),
        "required_source_freshness_coverage": _metric(
            len(fresh) if policy.freshness_policy_status == "ACCEPTED" else None,
            len(required) if policy.freshness_policy_status == "ACCEPTED" else None,
            "Required FULL_SOURCE runs within an accepted maximum age.",
            [str(plan.latest_full_source_run.pk) for plan in fresh if plan.latest_full_source_run],
            "COMPUTABLE" if policy.freshness_policy_status == "ACCEPTED" else "POLICY_PENDING",
        ),
        "canonical_source_coverage": _metric(
            len(canonical_complete),
            len(canonical_required),
            (
                "Structurally complete required vacancy sources with an explicitly "
                "accepted canonicality."
            ),
            [
                str(plan.latest_full_source_run.pk)
                for plan in canonical_complete
                if plan.latest_full_source_run
            ],
        ),
        "geographic_coverage": _metric(
            None,
            None,
            (
                "NOT_COMPUTABLE: free-text coverage_scope is not a governed "
                "administrative denominator."
            ),
            [],
            "NOT_COMPUTABLE",
        ),
        "publication_date_coverage": _metric(
            sum(row.source_published_date is not None for row in market),
            len(market),
            "Eligible Day-0 market records with source publication dates.",
            [str(dashboard_snapshot.pk)],
        ),
        "geospatial_resolution_coverage": _metric(
            sum(row.mapping_status == "MAPPABLE" for row in market),
            len(market),
            "Eligible Day-0 market records with safe public-display coordinates.",
            [str(dashboard_snapshot.pk)],
        ),
        "green_classification_coverage": _metric(
            green_confirmed + green_review + not_green,
            len(records),
            "Run vacancy states with an exact selected green outcome.",
            [str(dashboard_snapshot.pk)],
        ),
        "dedup_resolution_quality": _metric(
            len(market),
            len(market) + critical_dedup,
            (
                "Public unique vacancies relative to pending dedup decisions capable "
                "of changing the count."
            ),
            [str(dedup_run.pk), *[item for item in critical if item.startswith("dedup:")]],
        ),
        "position_count_disclosure_coverage": _metric(
            len(known),
            len(market),
            "Eligible Day-0 market vacancies with explicit positions_count.",
            [str(row.pk) for row in known],
        ),
        "source_link_provenance_coverage": _metric(
            sum(row.source_link_status not in {"NO_LINK_AVAILABLE", "REVIEW"} for row in market),
            len(market),
            "Eligible Day-0 market records with governed source-link status.",
            [str(row.pk) for row in market],
        ),
    }
    blockers: list[dict[str, Any]] = []
    if policy.threshold_policy_status == "PENDING":
        blockers.append({"code": "THRESHOLD_POLICY_PENDING"})
    if policy.freshness_policy_status == "PENDING":
        blockers.append({"code": "FRESHNESS_POLICY_PENDING"})
    if blocked_required:
        blockers.append(
            {
                "code": "FINAL_BLOCKED_REQUIRED_SOURCES",
                "count": len(blocked_required),
                "sources": {
                    str(plan.entry.source_id): plan.blocker_classification
                    for plan in sorted(blocked_required, key=lambda item: str(item.entry.source_id))
                },
                "authorization_effect": "DENOMINATOR_ONLY_NOT_AUTOMATIC_VETO",
            }
        )
    if not governed_disposition_complete:
        blockers.append({"code": "GOVERNED_DISPOSITION_INCOMPLETE"})
    if policy.required_completion_threshold is not None and (
        Decimal(len(authorized)) / Decimal(len(required)) < policy.required_completion_threshold
    ):
        blockers.append(
            {
                "code": "ACQUISITION_COVERAGE_BELOW_THRESHOLD",
                "eligible": len(authorized),
                "required": len(required),
                "minimum_count": policy.configuration.get("minimum_required_source_count"),
                "minimum_ratio": str(policy.required_completion_threshold),
            }
        )
    if not structural_coverage_pass:
        blockers.append(
            {
                "code": "STRUCTURAL_COVERAGE_BELOW_MINIMUM",
                "eligible": eligible_by_stratum,
                "minimum": stratum_minima,
            }
        )
    if not final_policy and len(complete) < len(required):
        blockers.append(
            {
                "code": "REQUIRED_SOURCE_RUNS_INCOMPLETE",
                "complete": len(complete),
                "required": len(required),
            }
        )
    if not final_policy and len(healthy) < len(required):
        blockers.append(
            {
                "code": "REQUIRED_SOURCE_HEALTH_INCOMPLETE",
                "healthy": len(healthy),
                "required": len(required),
            }
        )
    if critical:
        blockers.append(
            {"code": "CRITICAL_REVIEWS", "count": len(critical), "review_ids": critical}
        )
    fingerprint = _sha256(
        {
            "readiness_version": READINESS_VERSION,
            "as_of": as_of.isoformat(),
            "universe": str(universe.pk),
            "universe_fingerprint": universe.input_fingerprint,
            "policy": str(policy.pk),
            "policy_fingerprint": policy.input_fingerprint,
            "dedup": [str(dedup_run.pk), dedup_run.input_fingerprint],
            "premium": [str(premium_run.pk), premium_run.input_fingerprint],
            "dashboard": [str(dashboard_snapshot.pk), dashboard_snapshot.input_fingerprint],
            "source_evidence": [
                {"entry": str(plan.entry.pk), "evidence": plan.evidence}
                for plan in sorted(plans, key=lambda item: str(item.entry.source_id))
            ],
            "critical": critical,
            "noncritical": noncritical,
            "metrics": metrics,
        }
    )
    _advisory_lock(fingerprint)
    existing = Day0ReadinessAssessment.objects.filter(input_fingerprint=fingerprint).first()
    if existing:
        return existing, True
    selected_run_ids = sorted(
        {
            str(run.pk)
            for plan in plans
            for run in (
                plan.latest_activity_run,
                plan.latest_full_source_run,
                plan.latest_health_run,
            )
            if run
        }
    )
    selected_postings = dedup_run.posting_assignments.count()
    assessment = Day0ReadinessAssessment(
        readiness_version=READINESS_VERSION,
        as_of=as_of,
        source_universe=universe,
        authorization_policy=policy,
        policy_version=policy.policy_version,
        dedup_run=dedup_run,
        premium_run=premium_run,
        dashboard_snapshot=dashboard_snapshot,
        readiness_status=_evaluate_status(
            policy,
            len(authorized),
            len(required),
            len(critical),
            len(blocked_required),
            governed_disposition_complete,
            structural_coverage_pass,
        ),
        selected_source_ids=sorted(str(plan.entry.source_id) for plan in plans),
        selected_collection_run_ids=selected_run_ids,
        metrics=metrics,
        critical_review_ids=critical,
        noncritical_review_ids=noncritical,
        blockers=blockers,
        required_source_count=len(required),
        supporting_source_count=len(supporting),
        deferred_source_count=sum(plan.entry.classification == "DEFERRED" for plan in plans),
        not_applicable_source_count=sum(
            plan.entry.classification == "NOT_APPLICABLE" for plan in plans
        ),
        blocked_source_count=len(blocked_required) + len(blocked_supporting) + len(blocked_other),
        blocked_required_source_count=len(blocked_required),
        blocked_supporting_source_count=len(blocked_supporting),
        blocked_other_source_count=len(blocked_other),
        implemented_required_source_count=len(complete),
        required_complete_count=len(complete),
        required_healthy_count=len(healthy),
        required_freshness_valid_count=len(fresh),
        required_full_source_healthy_count=sum(
            plan.structurally_complete and plan.currently_healthy for plan in required
        ),
        required_source_completion_ratio=_persisted_ratio(len(complete), len(required)),
        healthy_source_ratio=_persisted_ratio(len(healthy), len(required)),
        critical_review_count=len(critical),
        noncritical_review_count=len(noncritical),
        critical_green_review_count=critical_green,
        critical_dedup_review_count=critical_dedup,
        other_critical_review_count=other_critical,
        green_confirmed_count=green_confirmed,
        green_review_count=green_review,
        not_green_count=not_green,
        missing_green_count=missing_green,
        observed_postings=selected_postings,
        selected_source_postings=selected_postings,
        active_unique_vacancies=sum(row.vacancy_status == "ACTIVE" for row in market),
        known_positions_total=sum(row.positions_count or 0 for row in known),
        vacancies_unknown_position_count=len(market) - len(known),
        multi_hire_possible_count=sum(bool(row.multi_hire_possible) for row in market),
        input_fingerprint=fingerprint,
    )
    assessment.save()
    evidence_rows = []
    for plan in plans:
        row = Day0ReadinessSourceEvidence(
            assessment=assessment,
            universe_entry=plan.entry,
            source=plan.entry.source,
            collection_run=plan.latest_full_source_run,
            latest_activity_run=plan.latest_activity_run,
            latest_full_source_run=plan.latest_full_source_run,
            latest_health_run=plan.latest_health_run,
            completion_status=_completion_status(plan),
            is_complete=plan.structurally_complete,
            is_healthy=plan.currently_healthy,
            structurally_complete=plan.structurally_complete,
            currently_healthy=plan.currently_healthy,
            freshness_valid=plan.freshness_valid,
            evidence=plan.evidence,
        )
        row.full_clean()
        evidence_rows.append(row)
    Day0ReadinessSourceEvidence.objects.bulk_create(evidence_rows)
    return assessment, False


def readiness_summary(assessment: Day0ReadinessAssessment, reused: bool) -> dict[str, Any]:
    policy = assessment.authorization_policy
    return {
        "assessment_id": str(assessment.pk),
        "as_of": assessment.as_of.isoformat(),
        "status": assessment.readiness_status,
        "source_universe_version": assessment.source_universe.universe_version,
        "policy_version": assessment.policy_version,
        "threshold_policy_status": policy.threshold_policy_status if policy else "LEGACY",
        "freshness_policy_status": policy.freshness_policy_status if policy else "LEGACY",
        "input_fingerprint": assessment.input_fingerprint,
        "dedup_run_id": str(assessment.dedup_run_id),
        "premium_run_id": str(assessment.premium_run_id),
        "dashboard_snapshot_id": str(assessment.dashboard_snapshot_id),
        "required_sources": assessment.required_source_count,
        "supporting_sources": assessment.supporting_source_count,
        "deferred_sources": assessment.deferred_source_count,
        "not_applicable_sources": assessment.not_applicable_source_count,
        "blocked_required": assessment.blocked_required_source_count,
        "blocked_supporting": assessment.blocked_supporting_source_count,
        "blocked_other": assessment.blocked_other_source_count,
        "required_complete": assessment.required_complete_count,
        "required_healthy": assessment.required_healthy_count,
        "freshness_valid": assessment.required_freshness_valid_count,
        "selected_source_postings": assessment.selected_source_postings,
        "observed_postings": assessment.observed_postings,
        "active_unique_vacancies": assessment.active_unique_vacancies,
        "known_positions_total": assessment.known_positions_total,
        "vacancies_unknown_position_count": assessment.vacancies_unknown_position_count,
        "multi_hire_possible_count": assessment.multi_hire_possible_count,
        "green_confirmed_count": assessment.green_confirmed_count,
        "green_review_count": assessment.green_review_count,
        "not_green_count": assessment.not_green_count,
        "missing_green_count": assessment.missing_green_count,
        "critical_green_reviews": assessment.critical_green_review_count,
        "critical_dedup_reviews": assessment.critical_dedup_review_count,
        "other_critical_reviews": assessment.other_critical_review_count,
        "noncritical_reviews": assessment.noncritical_review_count,
        "metrics": assessment.metrics,
        "blockers": assessment.blockers,
        "exact_replay_reused": reused,
    }
