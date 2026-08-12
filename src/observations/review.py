from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.db import transaction
from django.utils import timezone

from observations.models import GreenRelevanceAssessment, GreenRelevanceReviewDecision

GREEN_REVIEW_GOVERNANCE_VERSION = "green-review-v0.1"


@dataclass(frozen=True)
class EffectiveGreenResult:
    result: str
    decision: GreenRelevanceReviewDecision | None


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
    if decision is None or decision.outcome == "INSUFFICIENT_EVIDENCE":
        return EffectiveGreenResult("REVIEW", decision)
    if decision.outcome == "CONFIRMED_GREEN":
        return EffectiveGreenResult("GREEN_CONFIRMED", decision)
    return EffectiveGreenResult("NOT_GREEN", decision)


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
    available_at = timezone.now()
    effective_at = reviewed_at or available_at
    decision = GreenRelevanceReviewDecision(
        assessment=assessment,
        outcome=outcome,
        reason_code=reason_code,
        reason=reason,
        evidence=evidence,
        governance_version=governance_version,
        reviewed_at=effective_at,
        created_at=available_at,
    )
    decision.save()
    return decision
