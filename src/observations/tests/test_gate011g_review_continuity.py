from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import pytest

from dashboard.tests.factories import create_dashboard_upstream
from observations.models import GreenRelevanceReviewDecisionApplication
from observations.review import (
    ConflictingGreenReviewDecisionError,
    apply_materially_identical_green_decision,
    effective_green_result,
    record_green_review_decision,
)
from observations.review_continuity import green_review_material_fingerprint

pytestmark = pytest.mark.django_db


def _fixture(result: str) -> dict[str, Any]:
    return create_dashboard_upstream(
        suffix=f"011g-{result}-{uuid.uuid4().hex[:10]}",
        green_result=result,
        premium_status="SKIPPED_NOT_GREEN",
    )


def _decision(data: dict[str, Any], outcome: str = "CONFIRMED_GREEN"):
    return record_green_review_decision(
        assessment=data["green"],
        outcome=outcome,
        reason_code="EXACT_MATERIAL_FIXTURE",
        reason="Exact decision-relevant evidence fixture.",
        evidence={"reviewed_surfaces": ["title", "description"], "evidence_basis": "bounded"},
    )


def test_identical_material_reuses_prior_green_decision() -> None:
    original = _fixture("REVIEW")
    decision = _decision(original)
    target = _fixture("REVIEW")
    source_observation = original["green"].posting_observation
    target_observation = target["green"].posting_observation
    target_observation.posting = source_observation.posting
    target_observation.source = source_observation.source
    for field in (
        "title",
        "description_html",
        "responsibilities_html",
        "qualifications_html",
        "benefits_html",
        "hiring_organization",
        "source_posting_id",
    ):
        setattr(target_observation, field, getattr(source_observation, field))
    target_green = target["green"]
    target_green.posting_observation = target_observation
    application = apply_materially_identical_green_decision(
        target_assessment=target_green, source_decision=decision
    )
    result = effective_green_result(target_green, as_of=application.created_at)
    assert result.result == "GREEN_CONFIRMED"
    assert result.application == application
    assert result.origin == "MATERIAL_IDENTICAL_HUMAN_REUSE"


def test_material_change_and_new_identity_do_not_reuse() -> None:
    original = _fixture("REVIEW")
    decision = _decision(original)
    target = _fixture("REVIEW")
    with pytest.raises(ValueError, match="material differs"):
        apply_materially_identical_green_decision(
            target_assessment=target["green"], source_decision=decision
        )


def test_reuse_is_causal_immutable_and_conflict_safe() -> None:
    data = _fixture("REVIEW")
    decision = _decision(data, "INSUFFICIENT_EVIDENCE")
    target = _fixture("REVIEW")
    source = data["green"].posting_observation
    target_obs = target["green"].posting_observation
    target_obs.posting = source.posting
    target_obs.source = source.source
    target_obs.source_posting_id = source.source_posting_id
    target_obs.title = source.title
    target_obs.description_html = source.description_html
    target_obs.responsibilities_html = source.responsibilities_html
    target_obs.qualifications_html = source.qualifications_html
    target_obs.benefits_html = source.benefits_html
    target_obs.hiring_organization = source.hiring_organization
    target_green = target["green"]
    target_green.posting_observation = target_obs
    application = apply_materially_identical_green_decision(
        target_assessment=target_green, source_decision=decision
    )
    assert (
        effective_green_result(
            target_green, as_of=application.created_at - timedelta(microseconds=1)
        ).result
        == "REVIEW"
    )
    assert effective_green_result(target_green, as_of=application.created_at).result == "REVIEW"
    assert (
        apply_materially_identical_green_decision(
            target_assessment=target_green, source_decision=decision
        )
        == application
    )
    with pytest.raises(ConflictingGreenReviewDecisionError):
        record_green_review_decision(
            assessment=target_green,
            outcome="CONFIRMED_GREEN",
            reason_code="CONFLICT",
            reason="Conflicting authority",
            evidence={"reviewed_surfaces": ["title"], "evidence_basis": "x"},
        )
    with pytest.raises(Exception):
        GreenRelevanceReviewDecisionApplication.objects.filter(pk=application.pk).update(
            material_fingerprint="0" * 64
        )


def test_raw_hash_is_provenance_not_material() -> None:
    data = _fixture("REVIEW")
    fingerprint = green_review_material_fingerprint(
        data["green"], governance_version="green-review-v0.1"
    )
    assert len(fingerprint) == 64
