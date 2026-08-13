from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from observations.models import (
    GreenRelevanceAssessment,
    GreenRelevanceReviewDecision,
    GreenRelevanceReviewDecisionApplication,
)
from observations.review_continuity import (
    GREEN_REVIEW_MATERIAL_VERSION,
    green_review_material_fingerprint,
)

GREEN_REVIEW_GOVERNANCE_VERSION = "green-review-v0.1"


class ConflictingGreenReviewDecisionError(RuntimeError):
    pass


@dataclass(frozen=True)
class EffectiveGreenResult:
    result: str
    decision: GreenRelevanceReviewDecision | None
    application: GreenRelevanceReviewDecisionApplication | None = None

    @property
    def origin(self) -> str:
        if self.application:
            return "MATERIAL_IDENTICAL_HUMAN_REUSE"
        if self.decision:
            return "DIRECT_HUMAN_DECISION"
        return "ORIGINAL_CLASSIFIER"


def effective_green_result(
    assessment: GreenRelevanceAssessment | None,
    *,
    as_of: datetime,
) -> EffectiveGreenResult:
    if assessment is None:
        return EffectiveGreenResult("MISSING", None)
    if assessment.result != GreenRelevanceAssessment.Result.REVIEW:
        return EffectiveGreenResult(str(assessment.result), None)
    decision = (
        GreenRelevanceReviewDecision.objects.filter(
            assessment=assessment,
            governance_version=GREEN_REVIEW_GOVERNANCE_VERSION,
            reviewed_at__lte=as_of,
            created_at__lte=as_of,
        )
        .order_by("-reviewed_at", "-created_at", "-pk")
        .first()
    )
    application = None
    if decision is None:
        application = (
            GreenRelevanceReviewDecisionApplication.objects.filter(
                target_assessment=assessment,
                governance_version=GREEN_REVIEW_GOVERNANCE_VERSION,
                created_at__lte=as_of,
                source_decision__reviewed_at__lte=as_of,
                source_decision__created_at__lte=as_of,
            )
            .select_related("source_decision")
            .first()
        )
        if application is not None:
            application.full_clean()
        decision = application.source_decision if application else None
    if decision is None or decision.outcome == "INSUFFICIENT_EVIDENCE":
        return EffectiveGreenResult("REVIEW", decision, application)
    if decision.outcome == "CONFIRMED_GREEN":
        return EffectiveGreenResult("GREEN_CONFIRMED", decision, application)
    return EffectiveGreenResult("NOT_GREEN", decision, application)


@transaction.atomic
def apply_materially_identical_green_decision(
    *,
    target_assessment: GreenRelevanceAssessment,
    source_decision: GreenRelevanceReviewDecision,
) -> GreenRelevanceReviewDecisionApplication:
    version = source_decision.governance_version
    source_fp = green_review_material_fingerprint(
        source_decision.assessment, governance_version=version
    )
    target_fp = green_review_material_fingerprint(target_assessment, governance_version=version)
    if source_fp != target_fp:
        raise ValueError("green review material differs")
    existing = GreenRelevanceReviewDecisionApplication.objects.filter(
        target_assessment=target_assessment, governance_version=version
    ).first()
    if existing:
        if (
            existing.source_decision_id == source_decision.pk
            and existing.material_fingerprint == target_fp
            and existing.fingerprint_version == GREEN_REVIEW_MATERIAL_VERSION
            and existing.governance_version == version
            and existing.application_method == "MATERIAL_IDENTICAL_HUMAN_REUSE"
        ):
            return existing
        raise ConflictingGreenReviewDecisionError("conflicting inherited application exists")
    now = timezone.now()
    application = GreenRelevanceReviewDecisionApplication(
        target_assessment=target_assessment,
        source_decision=source_decision,
        material_fingerprint=target_fp,
        fingerprint_version=GREEN_REVIEW_MATERIAL_VERSION,
        governance_version=version,
        created_at=now,
        evidence={
            "source_raw_sha256": (
                source_decision.assessment.posting_observation.raw_artifact.sha256_digest
            ),
            "target_raw_sha256": target_assessment.posting_observation.raw_artifact.sha256_digest,
            "source_assessment_id": str(source_decision.assessment.pk),
            "target_assessment_id": str(target_assessment.pk),
        },
    )
    try:
        with transaction.atomic():
            application.save()
    except IntegrityError as exc:
        concurrent = GreenRelevanceReviewDecisionApplication.objects.filter(
            target_assessment=target_assessment, governance_version=version
        ).first()
        if concurrent is not None and (
            concurrent.source_decision_id == source_decision.pk
            and concurrent.material_fingerprint == target_fp
            and concurrent.fingerprint_version == GREEN_REVIEW_MATERIAL_VERSION
            and concurrent.application_method == "MATERIAL_IDENTICAL_HUMAN_REUSE"
        ):
            return concurrent
        raise ConflictingGreenReviewDecisionError(
            "conflicting concurrent inherited application exists"
        ) from exc
    return application


@transaction.atomic
def record_green_review_decision(
    *,
    assessment: GreenRelevanceAssessment,
    outcome: str,
    reason_code: str,
    reason: str,
    evidence: dict[str, Any],
    reviewed_at: datetime | None = None,
    governance_version: str = GREEN_REVIEW_GOVERNANCE_VERSION,
) -> GreenRelevanceReviewDecision:
    if assessment.result != GreenRelevanceAssessment.Result.REVIEW:
        raise ValueError("only REVIEW assessments may be adjudicated")
    if GreenRelevanceReviewDecisionApplication.objects.filter(
        target_assessment=assessment, governance_version=governance_version
    ).exists():
        raise ConflictingGreenReviewDecisionError("assessment already inherits human knowledge")
    available_at = timezone.now()
    effective_at = reviewed_at or available_at
    observation = assessment.posting_observation
    if not isinstance(evidence, dict):
        raise ValueError("review evidence must be a JSON object")
    complete_evidence = {
        **evidence,
        "posting_observation_id": str(observation.pk),
        "green_relevance_assessment_id": str(assessment.pk),
        "source_id": observation.source.source_id,
        "source_native_id": observation.source_posting_id,
        "original_classifier_result": str(assessment.result),
        "raw_payload_sha256": observation.raw_artifact.sha256_digest,
        "reviewed_surfaces": evidence.get("reviewed_surfaces")
        or evidence.get("evidence_surfaces_reviewed"),
        "evidence_basis": evidence.get("evidence_basis") or reason,
    }
    existing = GreenRelevanceReviewDecision.objects.filter(
        assessment=assessment,
        governance_version=governance_version,
    ).first()
    if existing is not None:
        if (
            existing.outcome == outcome
            and existing.reason_code == reason_code
            and existing.reason == reason
            and existing.evidence == complete_evidence
        ):
            return existing
        raise ConflictingGreenReviewDecisionError(
            "a conflicting decision already exists for this assessment and governance version"
        )
    decision = GreenRelevanceReviewDecision(
        assessment=assessment,
        outcome=outcome,
        reason_code=reason_code,
        reason=reason,
        evidence=complete_evidence,
        governance_version=governance_version,
        reviewed_at=effective_at,
        created_at=available_at,
    )
    try:
        with transaction.atomic():
            decision.save()
    except IntegrityError as exc:
        concurrent = GreenRelevanceReviewDecision.objects.filter(
            assessment=assessment,
            governance_version=governance_version,
        ).first()
        if concurrent is not None and (
            concurrent.outcome == outcome
            and concurrent.reason_code == reason_code
            and concurrent.reason == reason
            and concurrent.evidence == complete_evidence
        ):
            return concurrent
        raise ConflictingGreenReviewDecisionError(
            "a conflicting concurrent decision exists for this assessment and governance version"
        ) from exc
    return decision
