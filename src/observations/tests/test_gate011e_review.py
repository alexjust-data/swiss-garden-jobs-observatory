from datetime import timedelta
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from dashboard.services import build_dashboard_snapshot
from dashboard.tests.factories import create_dashboard_upstream
from day0.services import _review_evidence
from observations.models import (
    GreenRelevanceAssessment,
    GreenRelevanceReviewDecision,
    ImmutableGreenRelevanceReviewDecisionError,
)
from observations.review import (
    ConflictingGreenReviewDecisionError,
    effective_green_result,
    record_green_review_decision,
)
from premium_segments.classifier import run_classification, select_inputs
from premium_segments.models import PremiumSegmentAssessment


@pytest.mark.django_db(transaction=True)
def test_green_review_decision_is_append_only_and_does_not_rewrite_classifier() -> None:
    data = create_dashboard_upstream(
        suffix="011e-immutable", green_result="REVIEW", premium_status="SKIPPED_NOT_GREEN"
    )
    decision = record_green_review_decision(
        assessment=data["green"],
        outcome="CONFIRMED_NOT_GREEN",
        reason_code="DUTIES_OUTSIDE_GREEN_SCOPE",
        reason="The governed description contains no gardening or green-maintenance duties.",
        evidence={"reviewed_surfaces": ["description_html", "classifier_matches"]},
    )
    data["green"].refresh_from_db()
    assert data["green"].result == "REVIEW"
    decision.reason = "rewrite"
    with pytest.raises(ImmutableGreenRelevanceReviewDecisionError):
        decision.save()
    with pytest.raises(ImmutableGreenRelevanceReviewDecisionError):
        GreenRelevanceReviewDecision.objects.filter(pk=decision.pk).update(reason="rewrite")


@pytest.mark.django_db(transaction=True)
def test_review_decision_is_point_in_time_and_changes_premium_fingerprint() -> None:
    cutoff = timezone.now() + timedelta(minutes=2)
    data = create_dashboard_upstream(
        suffix="011e-pit", as_of=cutoff, green_result="REVIEW", premium_status="SKIPPED_NOT_GREEN"
    )
    before = timezone.now() - timedelta(microseconds=1)
    prior_inputs = select_inputs(before)
    prior = next(item for item in prior_inputs if item.observation.pk == data["observation"].pk)
    assert prior.effective_green.result == "REVIEW"

    decision = record_green_review_decision(
        assessment=data["green"],
        outcome="CONFIRMED_GREEN",
        reason_code="GREEN_DUTIES_EXPLICIT",
        reason="The governed description explicitly requires maintenance of public green spaces.",
        evidence={"reviewed_surfaces": ["description_html", "classifier_matches"]},
    )
    assert effective_green_result(data["green"], as_of=before).result == "REVIEW"
    assert effective_green_result(data["green"], as_of=cutoff).decision == decision

    pre_run, _ = run_classification(before)
    post_run, _ = run_classification(cutoff)
    assert pre_run.input_fingerprint != post_run.input_fingerprint
    post = PremiumSegmentAssessment.objects.get(
        run=post_run, posting_observation=data["observation"]
    )
    assert post.effective_green_result == "GREEN_CONFIRMED"
    assert post.green_review_decision == decision


@pytest.mark.django_db(transaction=True)
def test_resolved_not_green_review_leaves_critical_queue_and_public_market() -> None:
    cutoff = timezone.now() + timedelta(minutes=2)
    data = create_dashboard_upstream(
        suffix="011e-critical",
        as_of=cutoff,
        green_result="REVIEW",
        premium_status="SKIPPED_NOT_GREEN",
    )
    record_green_review_decision(
        assessment=data["green"],
        outcome="CONFIRMED_NOT_GREEN",
        reason_code="DUTIES_OUTSIDE_GREEN_SCOPE",
        reason="The governed description does not satisfy green relevance.",
        evidence={"reviewed_surfaces": ["description_html", "classifier_matches"]},
    )
    premium_run, _ = run_classification(cutoff)
    snapshot, _ = build_dashboard_snapshot(
        as_of=cutoff, dedup_run=data["dedup"], premium_run=premium_run
    )
    critical, _, critical_green, *_ = _review_evidence(
        data["dedup"], premium_run, snapshot, {str(data["source"].pk)}
    )
    record = snapshot.vacancy_records.get()
    assert record.visibility_status == "EXCLUDED_NOT_GREEN"
    assert critical_green == 0
    assert not any(item.startswith("green:") for item in critical)


@pytest.mark.django_db(transaction=True)
def test_resolved_green_review_enters_public_market_and_leaves_critical_queue() -> None:
    cutoff = timezone.now() + timedelta(minutes=2)
    data = create_dashboard_upstream(
        suffix="011e-confirmed-green",
        as_of=cutoff,
        green_result="REVIEW",
        premium_status="SKIPPED_NOT_GREEN",
    )
    record_green_review_decision(
        assessment=data["green"],
        outcome="CONFIRMED_GREEN",
        reason_code="GREEN_DUTIES_EXPLICIT",
        reason="The governed description explicitly satisfies green relevance.",
        evidence={"reviewed_surfaces": ["description_html", "classifier_matches"]},
    )
    premium_run, _ = run_classification(cutoff)
    snapshot, _ = build_dashboard_snapshot(
        as_of=cutoff, dedup_run=data["dedup"], premium_run=premium_run
    )
    critical, _, critical_green, *_ = _review_evidence(
        data["dedup"], premium_run, snapshot, {str(data["source"].pk)}
    )
    assert snapshot.vacancy_records.get().visibility_status == "PUBLIC_GREEN_CONFIRMED"
    assert critical_green == 0
    assert not any(item.startswith("green:") for item in critical)


@pytest.mark.django_db(transaction=True)
def test_insufficient_evidence_remains_review_and_authorization_critical() -> None:
    cutoff = timezone.now() + timedelta(minutes=2)
    data = create_dashboard_upstream(
        suffix="011e-insufficient",
        as_of=cutoff,
        green_result="REVIEW",
        premium_status="SKIPPED_NOT_GREEN",
    )
    record_green_review_decision(
        assessment=data["green"],
        outcome="INSUFFICIENT_EVIDENCE",
        reason_code="SOURCE_DUTIES_INSUFFICIENT",
        reason="The source evidence does not support a governed binary decision.",
        evidence={"reviewed_surfaces": ["description_html", "classifier_matches"]},
    )
    premium_run, _ = run_classification(cutoff)
    snapshot, _ = build_dashboard_snapshot(
        as_of=cutoff, dedup_run=data["dedup"], premium_run=premium_run
    )
    critical, _, critical_green, *_ = _review_evidence(
        data["dedup"], premium_run, snapshot, {str(data["source"].pk)}
    )
    assert snapshot.vacancy_records.get().visibility_status == "REVIEW_NOT_PUBLIC"
    assert critical_green == 1
    assert any(item.startswith("green:") for item in critical)


def _premium_candidate(
    data: dict[str, Any],
    *,
    assessment: GreenRelevanceAssessment | None,
    decision: GreenRelevanceReviewDecision | None,
    effective: str,
) -> PremiumSegmentAssessment:
    original = data["premium"]
    return PremiumSegmentAssessment(
        run=original.run,
        posting_observation=original.posting_observation,
        green_relevance_assessment=assessment,
        green_review_decision=decision,
        effective_green_result=effective,
        segment=original.segment,
        assessment_status=original.assessment_status,
        method=original.method,
        evidence_strength=original.evidence_strength,
        privacy_context=original.privacy_context,
        evidence={"fixture": "invalid-pinning"},
    )


@pytest.mark.django_db(transaction=True)
def test_review_decision_is_idempotent_and_conflicting_repeat_fails_closed() -> None:
    data = create_dashboard_upstream(
        suffix="011e-idempotent", green_result="REVIEW", premium_status="SKIPPED_NOT_GREEN"
    )
    kwargs = {
        "assessment": data["green"],
        "outcome": "CONFIRMED_GREEN",
        "reason_code": "GREEN_DUTIES_EXPLICIT",
        "reason": "Explicit green duties in governed source evidence.",
        "evidence": {"reviewed_surfaces": ["description_html", "classifier_matches"]},
    }
    first = record_green_review_decision(**kwargs)
    assert record_green_review_decision(**kwargs) == first
    assert GreenRelevanceReviewDecision.objects.filter(assessment=data["green"]).count() == 1
    with pytest.raises(ConflictingGreenReviewDecisionError):
        record_green_review_decision(
            **{**kwargs, "outcome": "CONFIRMED_NOT_GREEN", "reason_code": "OUTSIDE_SCOPE"}
        )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("outcome", "invalid_effective"),
    [
        ("CONFIRMED_GREEN", "NOT_GREEN"),
        ("CONFIRMED_NOT_GREEN", "GREEN_CONFIRMED"),
        ("INSUFFICIENT_EVIDENCE", "GREEN_CONFIRMED"),
    ],
)
def test_premium_rejects_effective_result_contradicting_decision(
    outcome: str, invalid_effective: str
) -> None:
    suffix = {
        "CONFIRMED_GREEN": "011e-matrix-green",
        "CONFIRMED_NOT_GREEN": "011e-matrix-not-green",
        "INSUFFICIENT_EVIDENCE": "011e-matrix-insufficient",
    }[outcome]
    data = create_dashboard_upstream(
        suffix=suffix,
        green_result="REVIEW",
        premium_status="SKIPPED_NOT_GREEN",
    )
    decision = record_green_review_decision(
        assessment=data["green"],
        outcome=outcome,
        reason_code="MATRIX_TEST",
        reason="Bounded evidence for matrix validation.",
        evidence={"reviewed_surfaces": ["description_html", "classifier_matches"]},
    )
    candidate = _premium_candidate(
        data, assessment=data["green"], decision=decision, effective=invalid_effective
    )
    with pytest.raises(ValidationError, match="expected"):
        candidate.full_clean()


@pytest.mark.django_db(transaction=True)
def test_premium_rejects_cross_assessment_missing_assessment_and_future_decision() -> None:
    cutoff = timezone.now() + timedelta(minutes=2)
    left = create_dashboard_upstream(
        suffix="011e-cross-left",
        as_of=cutoff,
        green_result="REVIEW",
        premium_status="SKIPPED_NOT_GREEN",
    )
    right = create_dashboard_upstream(
        suffix="011e-cross-right",
        as_of=cutoff,
        green_result="REVIEW",
        premium_status="SKIPPED_NOT_GREEN",
    )
    decision = record_green_review_decision(
        assessment=right["green"],
        outcome="CONFIRMED_GREEN",
        reason_code="GREEN_DUTIES_EXPLICIT",
        reason="Bounded evidence for cross-assessment validation.",
        evidence={"reviewed_surfaces": ["description_html", "classifier_matches"]},
    )
    with pytest.raises(ValidationError):
        _premium_candidate(
            left,
            assessment=left["green"],
            decision=decision,
            effective="GREEN_CONFIRMED",
        ).full_clean()
    with pytest.raises(ValidationError):
        _premium_candidate(
            left, assessment=None, decision=decision, effective="GREEN_CONFIRMED"
        ).full_clean()
    left["premium"].run.as_of = decision.created_at - timedelta(microseconds=1)
    with pytest.raises(ValidationError, match="causally available"):
        _premium_candidate(
            left,
            assessment=right["green"],
            decision=decision,
            effective="GREEN_CONFIRMED",
        ).full_clean(exclude={"posting_observation"})


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("original", ["GREEN_CONFIRMED", "NOT_GREEN"])
def test_non_review_classifier_results_reject_review_decisions(original: str) -> None:
    data = create_dashboard_upstream(suffix=f"011e-original-{original}", green_result=original)
    invalid = GreenRelevanceReviewDecision(
        assessment=data["green"],
        outcome="CONFIRMED_GREEN",
        reason_code="INVALID",
        reason="A non-review result cannot be adjudicated.",
        evidence={},
        governance_version="green-review-v0.1",
        reviewed_at=timezone.now(),
        created_at=timezone.now(),
    )
    with pytest.raises(ValidationError):
        invalid.save()


@pytest.mark.django_db(transaction=True)
def test_review_without_decision_remains_review_and_incomplete_provenance_fails() -> None:
    data = create_dashboard_upstream(
        suffix="011e-unresolved-review",
        green_result="REVIEW",
        premium_status="SKIPPED_NOT_GREEN",
    )
    assert data["premium"].effective_green_result == "REVIEW"
    invalid = GreenRelevanceReviewDecision(
        assessment=data["green"],
        outcome="CONFIRMED_GREEN",
        reason_code="MISSING_PROVENANCE",
        reason="Evidence is deliberately incomplete.",
        evidence={},
        governance_version="green-review-v0.1",
        reviewed_at=timezone.now(),
        created_at=timezone.now(),
    )
    with pytest.raises(ValidationError, match="missing required provenance"):
        invalid.save()


@pytest.mark.django_db(transaction=True)
def test_non_review_assessment_cannot_be_adjudicated() -> None:
    data = create_dashboard_upstream(suffix="011e-invalid")
    with pytest.raises(ValueError):
        record_green_review_decision(
            assessment=data["green"],
            outcome="CONFIRMED_GREEN",
            reason_code="X",
            reason="Not allowed",
            evidence={},
        )
    invalid = GreenRelevanceReviewDecision(
        assessment=data["green"],
        outcome="CONFIRMED_GREEN",
        reason_code="X",
        reason="Not allowed",
        evidence={},
        governance_version="green-review-v0.1",
        reviewed_at=timezone.now(),
        created_at=timezone.now(),
    )
    with pytest.raises(ValidationError):
        invalid.save()


@pytest.mark.django_db(transaction=True)
def test_historical_premium_rows_backfill_original_green_result() -> None:
    data = create_dashboard_upstream(
        suffix="011e-migration-backfill",
        green_result="GREEN_CONFIRMED",
        premium_status="NO_SUFFICIENT_EVIDENCE",
    )
    premium_id = data["premium"].pk
    executor = MigrationExecutor(connection)
    executor.migrate([("premium_segments", "0001_initial")])
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
    historical = executor.loader.project_state().apps.get_model(
        "premium_segments", "PremiumSegmentAssessment"
    )
    assert historical.objects.get(pk=premium_id).effective_green_result == "GREEN_CONFIRMED"
