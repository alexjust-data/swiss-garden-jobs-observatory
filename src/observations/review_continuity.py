from __future__ import annotations

import hashlib
import json
from typing import Any

from observations.green_relevance import normalize_for_matching
from observations.models import GreenRelevanceAssessment

GREEN_REVIEW_MATERIAL_VERSION = "green-review-material-v0.1"


def _sorted_evidence(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        values, key=lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"))
    )


def green_review_material_payload(
    assessment: GreenRelevanceAssessment, *, governance_version: str
) -> dict[str, Any]:
    observation = assessment.posting_observation
    return {
        "material_version": GREEN_REVIEW_MATERIAL_VERSION,
        "review_governance_version": governance_version,
        "source_id": observation.source_id,
        "posting_id": str(observation.posting_id),
        "source_native_id": observation.source_posting_id,
        "classifier_version": assessment.classifier_version,
        "taxonomy_version": assessment.taxonomy_version,
        "taxonomy_sha256": assessment.taxonomy_sha256,
        "surfaces": {
            "TITLE": normalize_for_matching(observation.title),
            "TEXT": normalize_for_matching(
                "\n".join(
                    (
                        observation.description_html,
                        observation.responsibilities_html,
                        observation.qualifications_html,
                        observation.benefits_html,
                    )
                )
            ),
            "ORGANIZATION": normalize_for_matching(observation.hiring_organization),
        },
        "original_classifier_result": assessment.result,
        "matched_positive_terms": _sorted_evidence(assessment.matched_positive_terms),
        "matched_conditional_terms": _sorted_evidence(assessment.matched_conditional_terms),
        "matched_exclusion_terms": _sorted_evidence(assessment.matched_exclusion_terms),
        "classifier_evidence": assessment.evidence,
    }


def green_review_material_fingerprint(
    assessment: GreenRelevanceAssessment, *, governance_version: str
) -> str:
    payload = green_review_material_payload(assessment, governance_version=governance_version)
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
