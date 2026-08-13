from __future__ import annotations

import uuid
from datetime import timedelta
from hashlib import sha256
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError

from core.models import RawArtifact
from dashboard.tests.factories import create_dashboard_upstream
from observations.models import (
    CollectionRun,
    GreenRelevanceAssessment,
    GreenRelevanceReviewDecisionApplication,
    PostingObservation,
)
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


def _equivalent_target(data: dict[str, Any], *, raw_changed: bool = False):
    source = data["observation"]
    token = uuid.uuid4().hex
    raw = RawArtifact.objects.create(
        object_key=f"gate011g/{token}.json",
        sha256_digest=sha256(
            (token if raw_changed else source.raw_artifact.sha256_digest).encode()
        ).hexdigest(),
        byte_size=2,
        content_type="application/json",
    )
    run = CollectionRun.objects.create(
        source=source.source,
        status="SUCCEEDED",
        listing_url=source.canonical_url,
    )
    observation = PostingObservation.objects.create(
        collection_run=run,
        posting=source.posting,
        source=source.source,
        source_posting_id=source.source_posting_id,
        canonical_url=source.canonical_url,
        title=source.title,
        hiring_organization=source.hiring_organization,
        description_html=source.description_html,
        responsibilities_html=source.responsibilities_html,
        qualifications_html=source.qualifications_html,
        benefits_html=source.benefits_html,
        raw_artifact=raw,
        structured_payload=source.structured_payload,
        contract_payload=source.contract_payload,
    )
    original = data["green"]
    return GreenRelevanceAssessment.objects.create(
        posting_observation=observation,
        classifier_version=original.classifier_version,
        taxonomy_version=original.taxonomy_version,
        taxonomy_sha256=original.taxonomy_sha256,
        result=original.result,
        matched_positive_terms=original.matched_positive_terms,
        matched_conditional_terms=original.matched_conditional_terms,
        matched_exclusion_terms=original.matched_exclusion_terms,
        evidence=original.evidence,
    )


def test_identical_material_reuses_prior_green_decision() -> None:
    original = _fixture("REVIEW")
    decision = _decision(original)
    target_green = _equivalent_target(original)
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
    target_green = _equivalent_target(data)
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


def test_application_persistence_rejects_false_material_and_provenance() -> None:
    data = _fixture("REVIEW")
    decision = _decision(data)
    target = _equivalent_target(data, raw_changed=True)
    application = apply_materially_identical_green_decision(
        target_assessment=target, source_decision=decision
    )
    application.material_fingerprint = "0" * 64
    application.fingerprint_version = "wrong-version"
    application.evidence = {**application.evidence, "target_raw_sha256": "0" * 64}
    with pytest.raises(Exception):
        application.full_clean()


def test_green_integrity_collision_refetches_identical_authority() -> None:
    data = _fixture("REVIEW")
    decision = _decision(data)
    target = _equivalent_target(data)
    existing = apply_materially_identical_green_decision(
        target_assessment=target, source_decision=decision
    )
    absent = MagicMock()
    absent.first.return_value = None
    present = MagicMock()
    present.first.return_value = existing
    with (
        patch.object(
            GreenRelevanceReviewDecisionApplication.objects,
            "filter",
            side_effect=[absent, present],
        ),
        patch.object(
            GreenRelevanceReviewDecisionApplication,
            "save",
            side_effect=IntegrityError("simulated unique collision"),
        ),
    ):
        result = apply_materially_identical_green_decision(
            target_assessment=target, source_decision=decision
        )
    assert result == existing
    assert GreenRelevanceReviewDecisionApplication.objects.count() == 1


def test_conflicting_prior_human_knowledge_fails_closed() -> None:
    data = _fixture("REVIEW")
    _decision(data, "CONFIRMED_GREEN")
    second = _equivalent_target(data)
    record_green_review_decision(
        assessment=second,
        outcome="CONFIRMED_NOT_GREEN",
        reason_code="CONFLICTING_FIXTURE",
        reason="Adversarial historical conflict.",
        evidence={"reviewed_surfaces": ["title"], "evidence_basis": "bounded"},
    )
    target = _equivalent_target(data)
    with pytest.raises(CommandError, match="CONFLICTING_PRIOR_HUMAN_KNOWLEDGE"):
        call_command("apply_review_continuity", target_as_of=target.created_at)
