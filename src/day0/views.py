from __future__ import annotations

from typing import Any
from uuid import UUID

from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from .models import Day0ReadinessAssessment, Day0ReadinessSourceEvidence


def _market_envelope(assessment: Day0ReadinessAssessment) -> dict[str, Any]:
    market = assessment.metrics.get("day0_market_state", {})
    authorized = assessment.readiness_status == "DAY_0_AUTHORIZED"
    stale = Day0ReadinessSourceEvidence.objects.filter(
        assessment=assessment,
        evidence__freshness_state="STALE"
    ).count()
    return {
        "assessment_id": str(assessment.pk),
        "authorized": authorized,
        "value": market.get("green_confirmed_count") if authorized else None,
        "as_of": assessment.as_of.isoformat(),
        "status": assessment.readiness_status,
        "coverage": {
            "eligible": assessment.required_freshness_valid_count,
            "required": assessment.required_source_count,
            "blocked": assessment.blocked_required_source_count,
            "stale": stale,
            "eligible_source_ids": market.get("eligible_source_ids", []),
        },
        "market_state": market,
        "corpus_diagnostics": assessment.metrics.get("corpus_diagnostics", {}),
        "policy_versions": {
            "authorization": assessment.policy_version,
            "coverage": assessment.authorization_policy.configuration.get(
                "coverage_policy_version"
            ),
            "freshness": assessment.authorization_policy.configuration.get(
                "freshness_policy_version"
            ),
        },
        "scope": (
            "Canonical dashboard records whose canonical observation belongs to an exact "
            "fresh, healthy, complete required Source. Supporting provenance is not used "
            "to re-canonicalize excluded records."
        ),
        "reasons": assessment.blockers,
    }


def readiness_detail(_request: Any, assessment_id: UUID) -> JsonResponse:
    assessment = get_object_or_404(
        Day0ReadinessAssessment.objects.select_related("authorization_policy"),
        pk=assessment_id,
    )
    return JsonResponse(_market_envelope(assessment))


def readiness_current(_request: Any) -> JsonResponse:
    assessment = (
        Day0ReadinessAssessment.objects.select_related("authorization_policy")
        .order_by("-as_of", "-created_at", "-pk")
        .first()
    )
    if assessment is None:
        return JsonResponse(
            {"authorized": False, "value": None, "status": "NO_DAY_0_ASSESSMENT"},
            status=404,
        )
    response = _market_envelope(assessment)
    response["selection_policy"] = "LATEST_AS_OF_THEN_CREATED_AT_THEN_ID"
    return JsonResponse(response)
