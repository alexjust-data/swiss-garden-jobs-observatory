from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from typing import Any
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.db import close_old_connections

from dashboard.models import DashboardSnapshot
from dashboard.services import build_dashboard_snapshot
from dashboard.tests.factories import create_dashboard_upstream
from day0.models import (
    Day0ReadinessAssessment,
    Day0ReadinessSourceEvidence,
    Day0SourceUniverse,
    Day0SourceUniverseEntry,
    ImmutableDay0EvidenceError,
)
from day0.services import (
    POLICY_VERSION,
    SOURCE_UNIVERSE_VERSION,
    Day0ContractError,
    _evaluate_status,
    assess_day0_readiness,
)
from premium_segments.models import PremiumSegmentRun
from vacancies.models import (
    DedupDecision,
    DedupReviewItem,
    DedupRun,
    DedupRunPostingAssignment,
)


def complete_collection(data: dict[str, Any], *, jobs: int = 1) -> None:
    run = data["observation"].collection_run
    run.run_scope = "FULL_SOURCE"
    run.status = "SUCCEEDED"
    run.source_health_status = "HEALTHY"
    run.snapshot_complete = True
    run.listings_discovered = jobs
    run.observations_created = jobs
    run.green_assessments_created = jobs
    run.save(
        update_fields=[
            "run_scope",
            "status",
            "source_health_status",
            "snapshot_complete",
            "listings_discovered",
            "observations_created",
            "green_assessments_created",
        ]
    )


def universe(*, accepted: bool = False, threshold: Decimal | None = None) -> Day0SourceUniverse:
    return Day0SourceUniverse.objects.create(
        universe_version=SOURCE_UNIVERSE_VERSION,
        policy_version=POLICY_VERSION,
        threshold_policy_status="ACCEPTED" if accepted else "PENDING",
        required_completion_threshold=threshold if accepted else None,
        source_registry_sha256="1" * 64,
        coverage_matrix_sha256="2" * 64,
        configuration={"fixture": True},
        input_fingerprint=("3" if not accepted else "4") * 64,
    )


def add_entry(
    source_universe: Day0SourceUniverse,
    source: Any,
    *,
    target_role: str = "REQUIRED",
    classification: str = "DAY0_REQUIRED",
    batch: int | None = 1,
) -> Day0SourceUniverseEntry:
    return Day0SourceUniverseEntry.objects.create(
        universe=source_universe,
        source=source,
        classification=classification,
        target_role=target_role,
        reason="fixture governed reason",
        source_name=source.source_name,
        source_family=source.source_family,
        source_type=source.source_type,
        priority=source.priority,
        coverage_scope=source.coverage_scope,
        canonicality=source.canonicality,
        platform_family=source.platform_family,
        automation_status=source.automation_status,
        legal_review_status=source.legal_review_status,
        verification_status=source.verification_status,
        existing_adapter_reuse=True,
        new_adapter_required=False,
        implementation_batch=batch,
    )


def upstream(
    *, suffix: str = "day0", as_of: Any = None
) -> tuple[dict[str, Any], DashboardSnapshot]:
    data = create_dashboard_upstream(suffix=suffix, as_of=as_of)
    complete_collection(data)
    snapshot, _ = build_dashboard_snapshot(
        as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
    )
    return data, snapshot


def assess(data: dict[str, Any], snapshot: Any, source_universe: Day0SourceUniverse):
    return assess_day0_readiness(
        as_of=data["as_of"],
        dedup_run=data["dedup"],
        premium_run=data["premium_run"],
        dashboard_snapshot=snapshot,
        source_universe=source_universe,
    )


@pytest.mark.django_db(transaction=True)
def test_pending_policy_builds_not_authorized_assessment_and_exact_replay() -> None:
    data, snapshot = upstream()
    source_universe = universe()
    add_entry(source_universe, data["source"])

    first, reused = assess(data, snapshot, source_universe)
    replay, replayed = assess(data, snapshot, source_universe)

    assert not reused
    assert replayed and replay.pk == first.pk
    assert first.readiness_status == "DAY_0_THRESHOLD_POLICY_PENDING"
    assert first.required_source_count == 1
    assert first.implemented_required_source_count == 1
    assert first.observed_postings == 1
    assert first.active_unique_vacancies == 1
    assert first.known_positions_total == 0
    assert first.vacancies_unknown_position_count == 1
    assert first.metrics["required_source_run_coverage"]["numerator"] == 1
    assert first.metrics["required_source_run_coverage"]["denominator"] == 1


@pytest.mark.django_db(transaction=True)
def test_accepted_threshold_boundary_and_missing_required_source() -> None:
    data, snapshot = upstream(suffix="threshold")
    source_universe = universe(accepted=True, threshold=Decimal("1.0"))
    add_entry(source_universe, data["source"])
    ready, _ = assess(data, snapshot, source_universe)
    assert ready.readiness_status == "DAY_0_AUTHORIZED"

    other, _ = upstream(suffix="missing", as_of=data["as_of"] + timedelta(hours=2))
    add_entry(source_universe, other["source"])
    not_ready, _ = assess(data, snapshot, source_universe)
    assert not_ready.readiness_status == "DAY_0_NOT_READY"
    assert not_ready.required_source_completion_ratio == Decimal("0.500000")


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "health,status,complete",
    [
        ("DEGRADED", "SUCCEEDED", True),
        ("OUTAGE", "SUCCEEDED", True),
        ("HEALTHY", "FAILED", True),
        ("HEALTHY", "SUCCEEDED", False),
    ],
)
def test_unhealthy_failed_or_incomplete_required_source_does_not_count(
    health: str, status: str, complete: bool
) -> None:
    data, snapshot = upstream(suffix=f"bad-{health}-{status}-{complete}")
    run = data["observation"].collection_run
    run.source_health_status = health
    run.status = status
    run.snapshot_complete = complete
    run.save(update_fields=["source_health_status", "status", "snapshot_complete"])
    source_universe = universe(accepted=True, threshold=Decimal("1.0"))
    add_entry(source_universe, data["source"])
    result, _ = assess(data, snapshot, source_universe)
    assert result.readiness_status == "DAY_0_NOT_READY"
    assert result.implemented_required_source_count == 0


@pytest.mark.django_db(transaction=True)
def test_healthy_zero_job_source_counts_as_complete_and_supporting_is_not_denominator() -> None:
    data, snapshot = upstream(suffix="zero")
    complete_collection(data, jobs=0)
    source_universe = universe(accepted=True, threshold=Decimal("1.0"))
    add_entry(source_universe, data["source"])
    support = create_dashboard_upstream(suffix="support", as_of=data["as_of"])["source"]
    add_entry(
        source_universe,
        support,
        target_role="SUPPORTING",
        classification="DAY0_SUPPORTING",
        batch=3,
    )
    result, _ = assess(data, snapshot, source_universe)
    assert result.readiness_status == "DAY_0_AUTHORIZED"
    assert result.required_source_count == 1
    assert result.supporting_source_count == 1


@pytest.mark.django_db(transaction=True)
def test_blocked_required_source_is_retained_in_denominator() -> None:
    data, snapshot = upstream(suffix="blocked")
    source_universe = universe(accepted=True, threshold=Decimal("1.0"))
    add_entry(
        source_universe,
        data["source"],
        classification="BLOCKED_PENDING_ACCESS_REVIEW",
    )
    result, _ = assess(data, snapshot, source_universe)
    assert result.readiness_status == "DAY_0_BLOCKED_BY_SOURCE_ACCESS"
    assert result.required_source_count == 1
    assert result.blocked_source_count == 1


@pytest.mark.django_db(transaction=True)
def test_reverse_order_source_evidence_does_not_leak_backward() -> None:
    t1_data, t1_snapshot = upstream(suffix="pit-1")
    t2_data, t2_snapshot = upstream(suffix="pit-2", as_of=t1_data["as_of"] + timedelta(days=1))
    source_universe = universe(accepted=True, threshold=Decimal("1.0"))
    add_entry(source_universe, t1_data["source"])
    add_entry(source_universe, t2_data["source"])

    t2, _ = assess(t2_data, t2_snapshot, source_universe)
    t1, _ = assess(t1_data, t1_snapshot, source_universe)

    assert t2.required_source_completion_ratio == Decimal("1.000000")
    assert t1.required_source_completion_ratio == Decimal("0.500000")
    assert t2.readiness_status == "DAY_0_AUTHORIZED"
    assert t1.readiness_status == "DAY_0_NOT_READY"
    old_fingerprint = t1.input_fingerprint
    t2_data["observation"].collection_run.source_health_status = "OUTAGE"
    t2_data["observation"].collection_run.save(update_fields=["source_health_status"])
    t1.refresh_from_db()
    assert t1.input_fingerprint == old_fingerprint


@pytest.mark.django_db(transaction=True)
def test_incompatible_inputs_and_malformed_universe_fail_closed() -> None:
    data, snapshot = upstream(suffix="alignment")
    other, _ = upstream(suffix="alignment-other", as_of=data["as_of"])
    source_universe = universe()
    add_entry(source_universe, data["source"])
    with pytest.raises(Day0ContractError, match="not aligned"):
        assess_day0_readiness(
            as_of=data["as_of"],
            dedup_run=data["dedup"],
            premium_run=other["premium_run"],
            dashboard_snapshot=snapshot,
            source_universe=source_universe,
        )
    source_universe.universe_version = "malformed"
    with pytest.raises(Day0ContractError, match="Unsupported"):
        assess(data, snapshot, source_universe)


@pytest.mark.django_db(transaction=True)
def test_readiness_evidence_is_append_only() -> None:
    data, snapshot = upstream(suffix="immutable")
    source_universe = universe()
    add_entry(source_universe, data["source"])
    result, _ = assess(data, snapshot, source_universe)
    evidence = result.source_evidence.get()
    with pytest.raises(ImmutableDay0EvidenceError):
        result.readiness_status = "DAY_0_AUTHORIZED"
        result.save()
    with pytest.raises(ImmutableDay0EvidenceError):
        Day0ReadinessAssessment.objects.filter(pk=result.pk).update(blockers=[])
    with pytest.raises(ImmutableDay0EvidenceError):
        Day0ReadinessSourceEvidence.objects.filter(pk=evidence.pk).delete()
    with pytest.raises(ImmutableDay0EvidenceError):
        Day0ReadinessAssessment.objects.bulk_update([result], ["blockers"])


@pytest.mark.django_db(transaction=True)
def test_partial_source_evidence_failure_rolls_back_assessment() -> None:
    data, snapshot = upstream(suffix="rollback")
    source_universe = universe()
    add_entry(source_universe, data["source"])
    with patch.object(
        Day0ReadinessSourceEvidence.objects, "bulk_create", side_effect=RuntimeError("boom")
    ):
        with pytest.raises(RuntimeError, match="boom"):
            assess(data, snapshot, source_universe)
    assert Day0ReadinessAssessment.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_source_denominators_and_unknown_positions_are_explicit() -> None:
    data, snapshot = upstream(suffix="denominators")
    source_universe = universe()
    add_entry(source_universe, data["source"])
    result, _ = assess(data, snapshot, source_universe)
    assert result.metrics["geographic_coverage"]["denominator"] == 1
    assert result.metrics["position_count_disclosure_coverage"]["denominator"] == 1
    assert result.metrics["position_count_disclosure_coverage"]["numerator"] == 0
    assert result.known_positions_total == 0
    assert result.vacancies_unknown_position_count == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_exact_assessment_creates_one_complete_result() -> None:
    data, snapshot = upstream(suffix="concurrent")
    source_universe = universe()
    add_entry(source_universe, data["source"])
    barrier = threading.Barrier(2)

    def worker(_: int) -> tuple[str, int]:
        close_old_connections()
        barrier.wait(timeout=10)
        try:
            result, _ = assess_day0_readiness(
                as_of=data["as_of"],
                dedup_run=DedupRun.objects.get(pk=data["dedup"].pk),
                premium_run=PremiumSegmentRun.objects.get(pk=data["premium_run"].pk),
                dashboard_snapshot=DashboardSnapshot.objects.get(pk=snapshot.pk),
                source_universe=Day0SourceUniverse.objects.get(pk=source_universe.pk),
            )
            return str(result.pk), Day0ReadinessSourceEvidence.objects.filter(
                assessment=result
            ).count()
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, range(2)))
    assert len({item[0] for item in results}) == 1
    assert {item[1] for item in results} == {1}


@pytest.mark.django_db(transaction=True)
def test_threshold_boundary_uses_accepted_policy_without_optimizing_for_data() -> None:
    source_universe = universe(accepted=True, threshold=Decimal("0.95"))
    assert _evaluate_status(source_universe, 95, 100, 0, 0) == "DAY_0_AUTHORIZED"
    assert _evaluate_status(source_universe, 94, 100, 0, 0) == "DAY_0_NOT_READY"


@pytest.mark.django_db(transaction=True)
def test_green_review_is_critical_and_unrelated_dedup_review_is_noncritical() -> None:
    green_review_data = create_dashboard_upstream(
        suffix="green-review",
        green_result="REVIEW",
        premium_status="SKIPPED_NOT_GREEN",
    )
    complete_collection(green_review_data)
    green_snapshot, _ = build_dashboard_snapshot(
        as_of=green_review_data["as_of"],
        dedup_run=green_review_data["dedup"],
        premium_run=green_review_data["premium_run"],
    )
    green_universe = universe()
    add_entry(green_universe, green_review_data["source"])
    green_result, _ = assess(green_review_data, green_snapshot, green_universe)
    assert green_result.critical_review_count == 1
    assert green_result.critical_review_ids[0].startswith("green:")

    data, snapshot = upstream(suffix="dedup-review")
    other = create_dashboard_upstream(suffix="dedup-review-other", as_of=data["as_of"])
    decision = DedupDecision.objects.create(
        dedup_run=data["dedup"],
        posting_a=data["posting"],
        posting_b=other["posting"],
        observation_a=data["observation"],
        observation_b=other["observation"],
        dedup_version="dedup-v0.1",
        normalizer_version="dedup-normalizer-v0.1",
        method="RULE_SCORE",
        outcome="REVIEW",
        score=Decimal("0.8000"),
    )
    review = DedupReviewItem.objects.create(algorithm_decision=decision)
    source_universe = universe(accepted=True, threshold=Decimal("1.0"))
    add_entry(source_universe, data["source"])
    result, _ = assess(data, snapshot, source_universe)
    assert result.critical_review_count == 0
    assert result.noncritical_review_count == 1
    assert result.noncritical_review_ids == [f"dedup:{review.pk}"]


@pytest.mark.django_db(transaction=True)
def test_observed_postings_unique_vacancies_and_unknown_positions_stay_distinct() -> None:
    data = create_dashboard_upstream(suffix="quantities")
    complete_collection(data)
    other = create_dashboard_upstream(suffix="quantities-other", as_of=data["as_of"])
    DedupRunPostingAssignment.objects.create(
        dedup_run=data["dedup"],
        posting=other["posting"],
        run_vacancy_state=data["state"],
        membership_role="SUPPORTING",
        link_method="RULE_SCORE",
    )
    data["premium"].__class__.objects.create(
        run=data["premium_run"],
        posting_observation=other["observation"],
        green_relevance_assessment=other["green"],
        segment="UNKNOWN",
        assessment_status="NO_SUFFICIENT_EVIDENCE",
        method="FIXTURE",
        evidence_strength="NONE",
        privacy_context="PUBLIC_OR_NON_RESIDENTIAL",
        evidence={"fixture": "postings-vacancies-positions"},
    )
    snapshot, _ = build_dashboard_snapshot(
        as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
    )
    source_universe = universe()
    add_entry(source_universe, data["source"])
    result, _ = assess(data, snapshot, source_universe)
    assert result.observed_postings == 2
    assert result.active_unique_vacancies == 1
    assert result.known_positions_total == 0
    assert result.vacancies_unknown_position_count == 1


@pytest.mark.django_db(transaction=True)
def test_management_command_uses_frozen_universe_and_succeeds_when_not_ready() -> None:
    call_command("import_reference_data", verbosity=0)
    data, snapshot = upstream(suffix="command")
    output = StringIO()
    with patch("socket.create_connection", side_effect=AssertionError("network forbidden")):
        call_command(
            "assess_day0_readiness",
            as_of=data["as_of"].isoformat(),
            dedup_run=str(data["dedup"].pk),
            premium_run=str(data["premium_run"].pk),
            dashboard_snapshot=str(snapshot.pk),
            stdout=output,
        )
    payload = json.loads(output.getvalue())
    assert payload["status"] == "DAY_0_THRESHOLD_POLICY_PENDING"
    assert payload["required_sources"] == 29
    assert payload["exact_replay_reused"] is False
