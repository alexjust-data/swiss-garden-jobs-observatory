from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from dashboard.services import build_dashboard_snapshot
from dashboard.tests.factories import create_dashboard_upstream
from day0.services import _review_evidence
from observations.models import (
    GreenRelevanceReviewDecision,
    ImmutableGreenRelevanceReviewDecisionError,
)
from observations.review import effective_green_result, record_green_review_decision
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
        evidence={"posting_observation_id": str(data["observation"].pk)},
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
        evidence={"posting_observation_id": str(data["observation"].pk)},
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
        evidence={"posting_observation_id": str(data["observation"].pk)},
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
        evidence={"posting_observation_id": str(data["observation"].pk)},
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
        evidence={"posting_observation_id": str(data["observation"].pk)},
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
