from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.db import connection
from django.utils import timezone

from collectors.pipeline import SharedCollectionPipeline
from dashboard.services import build_dashboard_snapshot
from day0.models import Day0ReadinessAssessment, Day0SourceUniverse, Day0SourceUniverseEntry
from day0.policy import (
    AUTHORIZATION_POLICY_VERSION,
    COVERAGE_POLICY_VERSION,
    FINAL_BLOCKED_REQUIRED_SOURCES,
    FRESHNESS_POLICY_VERSION,
    REQUIRED_SOURCE_COUNT,
    SOURCE_UNIVERSE_VERSION,
)
from day0.services import assess_day0_readiness, ensure_source_universe, readiness_summary
from observations.green_relevance import CLASSIFIER_VERSION as GREEN_CLASSIFIER_VERSION
from observations.models import (
    CollectionRun,
    GreenRelevanceAssessment,
    GreenRelevanceReviewDecision,
    GreenRelevanceReviewDecisionApplication,
)
from observations.review import (
    GREEN_REVIEW_GOVERNANCE_VERSION,
    ConflictingGreenReviewDecisionError,
    apply_materially_identical_green_decision,
)
from observations.review_continuity import (
    GREEN_REVIEW_MATERIAL_VERSION,
    green_review_material_fingerprint,
)
from premium_segments.classifier import CLASSIFIER_VERSION as PREMIUM_VERSION
from premium_segments.classifier import run_classification
from sources.models import Source
from vacancies.engine import run_deduplication
from vacancies.models import DedupReviewDecisionApplication
from vacancies.normalizer import DEDUP_VERSION, NORMALIZER_VERSION

from .models import ObservatoryCycle, ObservatorySourceAttempt, OperationalEvent

CYCLE_VERSION = "daily-observatory-cycle-v0.1"
STAGE_ORDER = (
    "cohort",
    "collection",
    "green_continuity",
    "dedup",
    "dedup_continuity",
    "premium",
    "dashboard",
    "readiness",
)
LOCK_NAMESPACE = "daily-observatory-cycle-v0.1:day0-source-universe-v0.2"
DEFAULT_CYCLE_TIMEOUT_SECONDS = 14_400


class ObservatoryOperationError(RuntimeError):
    def __init__(self, stage: str, code: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage
        self.code = code


@dataclass(frozen=True)
class CycleResult:
    cycle: ObservatoryCycle
    reused: bool


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def _bounded_error(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:500]


def _git_sha() -> str:
    value = os.getenv("GIT_SHA", "").strip().lower()
    return value if len(value) == 40 and all(c in "0123456789abcdef" for c in value) else "UNKNOWN"


def _stages() -> dict[str, str]:
    return {stage: "PENDING" for stage in STAGE_ORDER}


def _save_stage(cycle: ObservatoryCycle, stage: str, status: str) -> None:
    stages = dict(cycle.stage_statuses)
    stages[stage] = status
    cycle.stage_statuses = stages
    cycle.heartbeat_at = timezone.now()
    cycle.save()


def _ensure_within_timeout(
    cycle: ObservatoryCycle,
    *,
    timeout_seconds: int,
    stage: str,
    invocation_started: datetime | None = None,
) -> None:
    started = invocation_started or cycle.started_at
    if started is None:
        return
    if timezone.now() - started > timedelta(seconds=timeout_seconds):
        raise ObservatoryOperationError(
            stage,
            "CYCLE_TIMEOUT",
            f"cycle exceeded configured {timeout_seconds}s timeout",
        )


def _event(
    cycle: ObservatoryCycle,
    code: str,
    severity: str,
    *,
    source: Source | None = None,
    detail: dict[str, Any] | None = None,
) -> OperationalEvent:
    bounded = detail or {}
    fingerprint = _sha256(
        {
            "code": code,
            "source": str(source.pk) if source else None,
            "detail": bounded,
        }
    )
    event, _ = OperationalEvent.objects.get_or_create(
        cycle=cycle,
        deduplication_fingerprint=fingerprint,
        defaults={"code": code, "severity": severity, "source": source, "detail": bounded},
    )
    return event


def governed_source_cohort() -> tuple[Day0SourceUniverse, list[Source]]:
    universe = ensure_source_universe()
    entries = list(
        Day0SourceUniverseEntry.objects.filter(universe=universe, target_role="REQUIRED")
        .select_related("source")
        .order_by("source_id")
    )
    blocked = set(FINAL_BLOCKED_REQUIRED_SOURCES)
    selected = [entry.source for entry in entries if str(entry.source_id) not in blocked]
    accidentally_blocked = sorted(
        str(source.pk) for source in selected if str(source.pk) in blocked
    )
    if accidentally_blocked:
        raise ObservatoryOperationError(
            "cohort", "BLOCKED_SOURCE_SELECTED", f"blocked Sources selected: {accidentally_blocked}"
        )
    if len(entries) != REQUIRED_SOURCE_COUNT or len(selected) != len(entries) - len(blocked):
        raise ObservatoryOperationError(
            "cohort",
            "IMPLEMENTED_COHORT_CHANGED",
            "governed cohort changed: "
            f"required={len(entries)} implemented={len(selected)} blocked={len(blocked)}",
        )
    return universe, selected


def _default_collector(source_id: str, **kwargs: Any) -> CollectionRun:
    delay_seconds = float(kwargs.pop("delay_seconds", 1.0))
    return SharedCollectionPipeline(source_id=source_id, delay_seconds=delay_seconds).collect(
        **kwargs
    )


def cycle_configuration(
    trigger: str,
    source_ids: list[str],
    *,
    timeout_seconds: int = DEFAULT_CYCLE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    return {
        "cycle_version": CYCLE_VERSION,
        "trigger": trigger,
        "target_cohort_version": SOURCE_UNIVERSE_VERSION,
        "source_ids": sorted(source_ids),
        "stage_order": list(STAGE_ORDER),
        "cutoff_policy": "continuity-available-aligned-pit-v0.1",
        "whole_cycle_timeout_seconds": timeout_seconds,
        "versions": {
            "coverage": COVERAGE_POLICY_VERSION,
            "freshness": FRESHNESS_POLICY_VERSION,
            "authorization": AUTHORIZATION_POLICY_VERSION,
            "green_classifier": GREEN_CLASSIFIER_VERSION,
            "green_review": GREEN_REVIEW_GOVERNANCE_VERSION,
            "green_material": GREEN_REVIEW_MATERIAL_VERSION,
            "dedup": DEDUP_VERSION,
            "normalizer": NORMALIZER_VERSION,
            "dedup_material": "dedup-review-material-v0.1",
            "premium": PREMIUM_VERSION,
        },
        "code_git_sha": _git_sha(),
    }


def _lock_key() -> int:
    raw = hashlib.sha256(LOCK_NAMESPACE.encode()).digest()[:8]
    return int.from_bytes(raw, "big", signed=True)


@contextmanager
def cycle_lock() -> Iterator[bool]:
    if connection.vendor != "postgresql":
        yield True
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [_lock_key()])
        acquired = bool(cursor.fetchone()[0])
    try:
        yield acquired
    finally:
        if acquired:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [_lock_key()])


def _counter_consistent(run: CollectionRun) -> bool:
    return (
        len(
            {
                run.listings_discovered,
                run.listing_total_discovered,
                run.postings_in_scope,
                run.details_fetched,
                run.observations_created,
                run.green_assessments_created,
            }
        )
        == 1
    )


def _attempt_metrics(run: CollectionRun) -> dict[str, Any]:
    return {
        "listing_discovered": run.listings_discovered,
        "listing_total_discovered": run.listing_total_discovered,
        "postings_in_scope": run.postings_in_scope,
        "details_fetched": run.details_fetched,
        "observations": run.observations_created,
        "green_assessments": run.green_assessments_created,
        "negative_observations": run.negative_observations_created,
    }


def apply_green_continuity(as_of: datetime) -> dict[str, int]:
    counts = {"created": 0, "reused": 0, "unmatched": 0, "conflicts": 0}
    targets = GreenRelevanceAssessment.objects.filter(
        result="REVIEW", created_at__lte=as_of
    ).select_related("posting_observation__posting", "posting_observation__raw_artifact")
    for target in targets:
        if GreenRelevanceReviewDecision.objects.filter(
            assessment=target, governance_version=GREEN_REVIEW_GOVERNANCE_VERSION
        ).exists():
            continue
        existing = GreenRelevanceReviewDecisionApplication.objects.filter(
            target_assessment=target, governance_version=GREEN_REVIEW_GOVERNANCE_VERSION
        ).first()
        if existing:
            existing.full_clean()
            counts["reused"] += 1
            continue
        target_fp = green_review_material_fingerprint(
            target, governance_version=GREEN_REVIEW_GOVERNANCE_VERSION
        )
        matches: list[GreenRelevanceReviewDecision] = []
        decisions = GreenRelevanceReviewDecision.objects.filter(
            assessment__posting_observation__posting_id=target.posting_observation.posting_id,
            governance_version=GREEN_REVIEW_GOVERNANCE_VERSION,
            created_at__lte=as_of,
            reviewed_at__lte=as_of,
        ).select_related("assessment__posting_observation__raw_artifact")
        for candidate in decisions:
            if (
                green_review_material_fingerprint(
                    candidate.assessment, governance_version=GREEN_REVIEW_GOVERNANCE_VERSION
                )
                == target_fp
            ):
                matches.append(candidate)
        if not matches:
            counts["unmatched"] += 1
            continue
        if len(matches) != 1:
            counts["conflicts"] += 1
            raise ConflictingGreenReviewDecisionError(
                f"CONFLICTING_PRIOR_HUMAN_KNOWLEDGE target={target.pk} matches={len(matches)}"
            )
        apply_materially_identical_green_decision(
            target_assessment=target, source_decision=matches[0]
        )
        counts["created"] += 1
    return counts


def _seal_failure(
    cycle: ObservatoryCycle, stage: str, status: str, code: str, exc: BaseException
) -> None:
    stages = dict(cycle.stage_statuses)
    stages[stage] = "FAILED"
    cycle.stage_statuses = stages
    cycle.status = status
    cycle.finished_at = timezone.now()
    cycle.heartbeat_at = cycle.finished_at
    cycle.operational_health = ObservatoryCycle.Health.RED
    cycle.failure_code = code
    cycle.failure_evidence = {"stage": stage, "error": _bounded_error(exc)}
    cycle.save()
    _event(cycle, "CYCLE_FAILED", OperationalEvent.Severity.ERROR, detail=cycle.failure_evidence)


def _previous_success(cycle: ObservatoryCycle) -> ObservatoryCycle | None:
    return (
        ObservatoryCycle.objects.filter(
            cycle_version=CYCLE_VERSION,
            status__in=[
                ObservatoryCycle.Status.SUCCEEDED,
                ObservatoryCycle.Status.SUCCEEDED_NOT_AUTHORIZED,
            ],
            finished_at__lt=cycle.finished_at,
        )
        .order_by("-finished_at")
        .first()
    )


def run_cycle(
    *,
    cycle_id: uuid.UUID | None = None,
    trigger: str = ObservatoryCycle.Trigger.MANUAL,
    resume: bool = False,
    delay_seconds: float = 1.0,
    timeout_seconds: int = DEFAULT_CYCLE_TIMEOUT_SECONDS,
    collector: Callable[..., CollectionRun] = _default_collector,
) -> CycleResult:
    if timeout_seconds < 60:
        raise ObservatoryOperationError(
            "cohort", "INVALID_TIMEOUT", "whole-cycle timeout must be at least 60 seconds"
        )
    if trigger == ObservatoryCycle.Trigger.RECOVERY and cycle_id is None:
        raise ObservatoryOperationError(
            "cohort", "RECOVERY_REQUIRES_CYCLE_ID", "RECOVERY requires --cycle-id"
        )
    universe, sources = governed_source_cohort()
    source_ids = [str(source.pk) for source in sources]
    cycle = ObservatoryCycle.objects.filter(pk=cycle_id).first() if cycle_id else None
    if cycle:
        configuration = cycle_configuration(
            cycle.trigger, source_ids, timeout_seconds=timeout_seconds
        )
        fingerprint = _sha256(configuration)
        if cycle.configuration_fingerprint != fingerprint:
            raise ObservatoryOperationError(
                "cohort", "RETRY_CONFIGURATION_MISMATCH", "cycle configuration differs"
            )
        if cycle.status in {
            ObservatoryCycle.Status.SUCCEEDED,
            ObservatoryCycle.Status.SUCCEEDED_NOT_AUTHORIZED,
        }:
            return CycleResult(cycle, True)
        if not resume:
            raise ObservatoryOperationError(
                "cohort", "RESUME_REQUIRED", "non-success cycle requires --resume"
            )
        if trigger != ObservatoryCycle.Trigger.RECOVERY:
            raise ObservatoryOperationError(
                "cohort", "RECOVERY_TRIGGER_REQUIRED", "resume requires --trigger RECOVERY"
            )
        if cycle.status == ObservatoryCycle.Status.RUNNING:
            heartbeat = cycle.heartbeat_at or cycle.started_at or cycle.requested_at
            if timezone.now() - heartbeat <= timedelta(seconds=timeout_seconds):
                raise ObservatoryOperationError(
                    "cohort", "ACTIVE_CYCLE_RETRY_REFUSED", "cycle heartbeat is not stale"
                )
            _event(
                cycle,
                "STALE_CYCLE_DETECTED",
                OperationalEvent.Severity.WARNING,
                detail={"heartbeat_at": heartbeat.isoformat(), "timeout_seconds": timeout_seconds},
            )
    else:
        configuration = cycle_configuration(
            trigger, source_ids, timeout_seconds=timeout_seconds
        )
        fingerprint = _sha256(configuration)
        cycle = ObservatoryCycle.objects.create(
            id=cycle_id or uuid.uuid4(),
            cycle_version=CYCLE_VERSION,
            trigger=trigger,
            target_cohort_version=universe.universe_version,
            selected_source_ids=source_ids,
            configuration=configuration,
            configuration_fingerprint=fingerprint,
            stage_statuses=_stages(),
            code_git_sha=configuration["code_git_sha"],
        )
    with cycle_lock() as acquired:
        if not acquired:
            cycle.status = ObservatoryCycle.Status.ABORTED_CONCURRENCY
            cycle.finished_at = timezone.now()
            cycle.operational_health = ObservatoryCycle.Health.RED
            cycle.failure_code = "CONCURRENT_CYCLE_RUNNING"
            cycle.failure_evidence = {"http_requests": 0}
            cycle.save()
            _event(
                cycle,
                "CYCLE_FAILED",
                OperationalEvent.Severity.WARNING,
                detail=cycle.failure_evidence,
            )
            return CycleResult(cycle, False)
        other_running = (
            ObservatoryCycle.objects.filter(
                cycle_version=CYCLE_VERSION,
                target_cohort_version=cycle.target_cohort_version,
                status=ObservatoryCycle.Status.RUNNING,
            )
            .exclude(pk=cycle.pk)
            .order_by("requested_at")
            .first()
        )
        if other_running is not None:
            heartbeat = (
                other_running.heartbeat_at
                or other_running.started_at
                or other_running.requested_at
            )
            stale = timezone.now() - heartbeat > timedelta(seconds=timeout_seconds)
            code = "STALE_CYCLE_DETECTED" if stale else "CONCURRENT_CYCLE_RUNNING"
            cycle.status = ObservatoryCycle.Status.ABORTED_CONCURRENCY
            cycle.finished_at = timezone.now()
            cycle.operational_health = ObservatoryCycle.Health.RED
            cycle.failure_code = code
            cycle.failure_evidence = {
                "conflicting_cycle_id": str(other_running.pk),
                "heartbeat_at": heartbeat.isoformat(),
                "http_requests": 0,
            }
            cycle.save()
            _event(cycle, code, OperationalEvent.Severity.WARNING, detail=cycle.failure_evidence)
            return CycleResult(cycle, False)
        invocation_started = timezone.now()
        now = invocation_started
        cycle.status = ObservatoryCycle.Status.RUNNING
        cycle.started_at = cycle.started_at or now
        cycle.heartbeat_at = now
        cycle.finished_at = None
        cycle.failure_code = ""
        cycle.failure_evidence = {}
        cycle.save()
        _save_stage(cycle, "cohort", "SUCCEEDED")
        _ensure_within_timeout(
            cycle,
            timeout_seconds=timeout_seconds,
            stage="collection",
            invocation_started=invocation_started,
        )
        _save_stage(cycle, "collection", "RUNNING")
        current_failures: list[str] = []
        for source in sources:
            prior = cycle.source_attempts.filter(
                source=source,
                result=ObservatorySourceAttempt.Result.SUCCEEDED,
                run_status=CollectionRun.Status.SUCCEEDED,
                source_health=CollectionRun.SourceHealthStatus.HEALTHY,
                snapshot_complete=True,
                counter_consistent=True,
            ).first()
            if prior:
                continue
            attempt_number = cycle.source_attempts.filter(source=source).count() + 1
            started = timezone.now()
            try:
                run = collector(
                    str(source.pk),
                    full_snapshot=True,
                    acknowledge_automation_review=True,
                    delay_seconds=delay_seconds,
                )
                finished = timezone.now()
                consistent = _counter_consistent(run)
                success = (
                    run.status == CollectionRun.Status.SUCCEEDED
                    and run.source_health_status == CollectionRun.SourceHealthStatus.HEALTHY
                    and run.snapshot_complete
                    and consistent
                )
                ObservatorySourceAttempt.objects.create(
                    cycle=cycle,
                    source=source,
                    attempt_number=attempt_number,
                    result=(
                        ObservatorySourceAttempt.Result.SUCCEEDED
                        if success
                        else ObservatorySourceAttempt.Result.FAILED
                    ),
                    collection_run=run,
                    started_at=started,
                    finished_at=finished,
                    runtime_ms=max(0, int((finished - started).total_seconds() * 1000)),
                    run_status=run.status,
                    source_health=run.source_health_status,
                    snapshot_complete=run.snapshot_complete,
                    counter_consistent=consistent,
                    metrics=_attempt_metrics(run),
                    failure_code="" if success else "SOURCE_INCOMPLETE_OR_UNHEALTHY",
                    failure_detail="" if success else run.source_health_reason[:500],
                )
                if not success:
                    current_failures.append(str(source.pk))
                    _event(
                        cycle,
                        "SOURCE_INCOMPLETE",
                        OperationalEvent.Severity.WARNING,
                        source=source,
                        detail={"run": str(run.pk)},
                    )
            except Exception as exc:
                finished = timezone.now()
                current_failures.append(str(source.pk))
                ObservatorySourceAttempt.objects.create(
                    cycle=cycle,
                    source=source,
                    attempt_number=attempt_number,
                    result=ObservatorySourceAttempt.Result.FAILED,
                    started_at=started,
                    finished_at=finished,
                    runtime_ms=max(0, int((finished - started).total_seconds() * 1000)),
                    failure_code="SOURCE_COLLECTION_FAILED",
                    failure_detail=_bounded_error(exc),
                )
                _event(
                    cycle,
                    "SOURCE_DEGRADED",
                    OperationalEvent.Severity.WARNING,
                    source=source,
                    detail={"error_type": type(exc).__name__},
                )
            _ensure_within_timeout(
                cycle,
                timeout_seconds=timeout_seconds,
                stage="collection",
                invocation_started=invocation_started,
            )
        _save_stage(cycle, "collection", "SUCCEEDED")
        try:
            _save_stage(cycle, "green_continuity", "RUNNING")
            _ensure_within_timeout(
                cycle,
                timeout_seconds=timeout_seconds,
                stage="green_continuity",
                invocation_started=invocation_started,
            )
            green = apply_green_continuity(timezone.now())
            _save_stage(cycle, "green_continuity", "SUCCEEDED")
        except Exception as exc:
            _seal_failure(
                cycle,
                "green_continuity",
                ObservatoryCycle.Status.FAILED_CONTINUITY,
                "GREEN_CONTINUITY_FAILED",
                exc,
            )
            return CycleResult(cycle, False)
        dedup_before = DedupReviewDecisionApplication.objects.count()
        try:
            _save_stage(cycle, "dedup", "RUNNING")
            _ensure_within_timeout(
                cycle,
                timeout_seconds=timeout_seconds,
                stage="dedup",
                invocation_started=invocation_started,
            )
            provisional_cutoff = timezone.now()
            provisional_run, provisional_reused = run_deduplication(provisional_cutoff)
            provisional_created = DedupReviewDecisionApplication.objects.count() - dedup_before
            cutoff = timezone.now()
            if provisional_created:
                dedup_run, dedup_reused = run_deduplication(cutoff)
            else:
                dedup_run, dedup_reused = provisional_run, provisional_reused
                cutoff = provisional_cutoff
            _save_stage(cycle, "dedup", "SUCCEEDED")
            _save_stage(cycle, "dedup_continuity", "SUCCEEDED")
        except Exception as exc:
            _seal_failure(cycle, "dedup", ObservatoryCycle.Status.FAILED_DEDUP, "DEDUP_FAILED", exc)
            return CycleResult(cycle, False)
        dedup_created = DedupReviewDecisionApplication.objects.count() - dedup_before
        try:
            _save_stage(cycle, "premium", "RUNNING")
            _ensure_within_timeout(
                cycle,
                timeout_seconds=timeout_seconds,
                stage="premium",
                invocation_started=invocation_started,
            )
            premium_run, premium_reused = run_classification(cutoff)
            _save_stage(cycle, "premium", "SUCCEEDED")
        except Exception as exc:
            _seal_failure(
                cycle, "premium", ObservatoryCycle.Status.FAILED_PREMIUM, "PREMIUM_FAILED", exc
            )
            return CycleResult(cycle, False)
        try:
            _save_stage(cycle, "dashboard", "RUNNING")
            _ensure_within_timeout(
                cycle,
                timeout_seconds=timeout_seconds,
                stage="dashboard",
                invocation_started=invocation_started,
            )
            dashboard, dashboard_reused = build_dashboard_snapshot(
                as_of=cutoff, dedup_run=dedup_run, premium_run=premium_run
            )
            _save_stage(cycle, "dashboard", "SUCCEEDED")
        except Exception as exc:
            _seal_failure(
                cycle,
                "dashboard",
                ObservatoryCycle.Status.FAILED_DASHBOARD,
                "DASHBOARD_BUILD_FAILED",
                exc,
            )
            return CycleResult(cycle, False)
        try:
            _save_stage(cycle, "readiness", "RUNNING")
            _ensure_within_timeout(
                cycle,
                timeout_seconds=timeout_seconds,
                stage="readiness",
                invocation_started=invocation_started,
            )
            readiness, readiness_reused = assess_day0_readiness(
                as_of=cutoff,
                dedup_run=dedup_run,
                premium_run=premium_run,
                dashboard_snapshot=dashboard,
            )
            _save_stage(cycle, "readiness", "SUCCEEDED")
        except Exception as exc:
            _seal_failure(
                cycle,
                "readiness",
                ObservatoryCycle.Status.FAILED_READINESS,
                "READINESS_FAILED",
                exc,
            )
            return CycleResult(cycle, False)
        authorized = readiness.readiness_status == Day0ReadinessAssessment.Status.AUTHORIZED
        cycle.status = (
            ObservatoryCycle.Status.SUCCEEDED
            if authorized
            else ObservatoryCycle.Status.SUCCEEDED_NOT_AUTHORIZED
        )
        cycle.operational_health = (
            ObservatoryCycle.Health.AMBER if current_failures else ObservatoryCycle.Health.GREEN
        )
        cycle.finished_at = timezone.now()
        cycle.heartbeat_at = cycle.finished_at
        cycle.final_cutoff = cutoff
        cycle.dedup_run = dedup_run
        cycle.premium_run = premium_run
        cycle.dashboard_snapshot = dashboard
        cycle.readiness_assessment = readiness
        cycle.continuity_counts = {
            "green": green,
            "dedup": {"created": max(0, dedup_created), "reused": int(dedup_reused)},
        }
        cycle.quality_state = {
            "operational_health": cycle.operational_health,
            "source_failures": sorted(current_failures),
            "selected": len(source_ids),
            "blocked_selected": 0,
            "day0_authorized": authorized,
            "authorization_status": readiness.readiness_status,
            "authorization_blockers": readiness.blockers,
            "critical_reviews": readiness.critical_review_count,
            "replay": {
                "dedup": dedup_reused,
                "premium": premium_reused,
                "dashboard": dashboard_reused,
                "readiness": readiness_reused,
            },
        }
        cycle.save()
        previous = _previous_success(cycle)
        if previous and previous.readiness_assessment:
            old = previous.readiness_assessment.readiness_status
            if old != readiness.readiness_status:
                _event(
                    cycle,
                    "AUTHORIZATION_CHANGED",
                    OperationalEvent.Severity.WARNING,
                    detail={"from": old, "to": readiness.readiness_status},
                )
        return CycleResult(cycle, False)


def cycle_summary(cycle: ObservatoryCycle, *, reused: bool = False) -> dict[str, Any]:
    attempts = list(cycle.source_attempts.select_related("source", "collection_run"))
    successful = [
        item for item in attempts if item.result == ObservatorySourceAttempt.Result.SUCCEEDED
    ]
    readiness = cycle.readiness_assessment
    return {
        "cycle_id": str(cycle.pk),
        "cycle_version": cycle.cycle_version,
        "trigger": cycle.trigger,
        "status": cycle.status,
        "operational_health": cycle.operational_health,
        "requested_at": cycle.requested_at.isoformat(),
        "started_at": cycle.started_at.isoformat() if cycle.started_at else None,
        "finished_at": cycle.finished_at.isoformat() if cycle.finished_at else None,
        "cutoff": cycle.final_cutoff.isoformat() if cycle.final_cutoff else None,
        "selected_source_ids": cycle.selected_source_ids,
        "sources_selected": len(cycle.selected_source_ids),
        "blocked_selected": 0,
        "source_attempts": len(attempts),
        "source_successful": len(successful),
        "source_failed": sorted(
            str(item.source.pk)
            for item in attempts
            if item.result == ObservatorySourceAttempt.Result.FAILED
        ),
        "continuity": cycle.continuity_counts,
        "dedup_run": str(cycle.dedup_run.pk) if cycle.dedup_run else None,
        "premium_run": str(cycle.premium_run.pk) if cycle.premium_run else None,
        "dashboard_snapshot": str(cycle.dashboard_snapshot.pk)
        if cycle.dashboard_snapshot
        else None,
        "readiness_assessment": str(cycle.readiness_assessment.pk)
        if cycle.readiness_assessment
        else None,
        "fingerprints": {
            "dedup": cycle.dedup_run.input_fingerprint if cycle.dedup_run else None,
            "premium": cycle.premium_run.input_fingerprint if cycle.premium_run else None,
            "dashboard": (
                cycle.dashboard_snapshot.input_fingerprint if cycle.dashboard_snapshot else None
            ),
            "readiness": (
                cycle.readiness_assessment.input_fingerprint if cycle.readiness_assessment else None
            ),
        },
        "day0": readiness_summary(readiness, False) if readiness else None,
        "quality_state": cycle.quality_state,
        "failure": {"code": cycle.failure_code, "evidence": cycle.failure_evidence},
        "exact_cycle_retry_reused": reused,
    }


def observatory_status(at: datetime | None = None) -> dict[str, Any]:
    now = at or timezone.now()
    latest = ObservatoryCycle.objects.first()
    last_success = (
        ObservatoryCycle.objects.filter(
            status__in=[
                ObservatoryCycle.Status.SUCCEEDED,
                ObservatoryCycle.Status.SUCCEEDED_NOT_AUTHORIZED,
            ]
        )
        .order_by("-finished_at")
        .first()
    )
    return {
        "latest_cycle": cycle_summary(latest) if latest else None,
        "last_successful_cycle_id": str(last_success.pk) if last_success else None,
        "last_successful_cycle_at": last_success.finished_at.isoformat()
        if last_success and last_success.finished_at
        else None,
        "cycle_age_seconds": int((now - last_success.finished_at).total_seconds())
        if last_success and last_success.finished_at
        else None,
        "pit_cutoff": last_success.final_cutoff.isoformat()
        if last_success and last_success.final_cutoff
        else None,
        "implemented_sources": len(last_success.selected_source_ids) if last_success else None,
        "quality_state": last_success.quality_state if last_success else None,
    }
