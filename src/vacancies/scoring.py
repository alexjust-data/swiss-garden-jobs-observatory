from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .evidence import PostingEvidence
from .normalizer import normalize_text

WEIGHTS = {
    "employer": Decimal("0.25"),
    "title": Decimal("0.25"),
    "location": Decimal("0.15"),
    "text": Decimal("0.20"),
    "pensum_contract_start": Decimal("0.10"),
    "contact_requisition": Decimal("0.05"),
}


@dataclass(frozen=True)
class PairAssessment:
    method: str
    outcome: str
    score: Decimal
    feature_scores: dict[str, str]
    hard_barriers: list[dict[str, str]]
    hard_key_evidence: list[dict[str, str]]


def _tokens(value: str) -> set[str]:
    return {token for token in normalize_text(value).split() if len(token) > 1}


def token_similarity(left: str, right: str) -> Decimal:
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return Decimal("0")
    return (Decimal(len(a & b)) / Decimal(len(a | b))).quantize(Decimal("0.0001"))


def outcome_for_score(score: Decimal) -> str:
    if score >= Decimal("0.90"):
        return "AUTO_MERGE"
    if score >= Decimal("0.78"):
        return "REVIEW"
    return "KEEP_SEPARATE"


def hard_key_evidence(left: PostingEvidence, right: PostingEvidence) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    if left.requisition_id and left.requisition_id == right.requisition_id:
        evidence.append({"type": "STABLE_REQUISITION_ID", "value": left.requisition_id})
    if left.normalized_url and left.normalized_url == right.normalized_url:
        evidence.append({"type": "NORMALIZED_CANONICAL_URL", "value": left.normalized_url})
    if left.redirect_target and left.redirect_target == right.normalized_url:
        evidence.append({"type": "EXPLICIT_REDIRECT", "value": left.redirect_target})
    if right.redirect_target and right.redirect_target == left.normalized_url:
        evidence.append({"type": "EXPLICIT_REDIRECT", "value": right.redirect_target})
    return evidence


def hard_barriers(left: PostingEvidence, right: PostingEvidence) -> list[dict[str, str]]:
    barriers: list[dict[str, str]] = []
    if (
        left.normalized_employer
        and left.normalized_employer == right.normalized_employer
        and left.requisition_id
        and right.requisition_id
        and left.requisition_id != right.requisition_id
    ):
        barriers.append(
            {
                "type": "DISTINCT_REQUISITION_IDS",
                "left": left.requisition_id,
                "right": right.requisition_id,
            }
        )
    if (
        left.normalized_location
        and right.normalized_location
        and left.normalized_location != right.normalized_location
    ):
        left_tokens, right_tokens = _tokens(left.location), _tokens(right.location)
        if left_tokens.isdisjoint(right_tokens):
            barriers.append(
                {
                    "type": "MATERIALLY_DIFFERENT_LOCATION",
                    "left": left.location,
                    "right": right.location,
                }
            )
    if (
        left.pensum_contract_start
        and right.pensum_contract_start
        and normalize_text(left.pensum_contract_start)
        != normalize_text(right.pensum_contract_start)
    ):
        barriers.append(
            {
                "type": "INCOMPATIBLE_EXPLICIT_EMPLOYMENT_TERMS",
                "left": left.pensum_contract_start,
                "right": right.pensum_contract_start,
            }
        )
    return barriers


def is_candidate(left: PostingEvidence, right: PostingEvidence) -> bool:
    if hard_key_evidence(left, right):
        return True
    if not left.normalized_employer or left.normalized_employer != right.normalized_employer:
        return False
    return token_similarity(left.title, right.title) >= Decimal("0.20")


def assess_pair(left: PostingEvidence, right: PostingEvidence) -> PairAssessment:
    keys = hard_key_evidence(left, right)
    barriers = hard_barriers(left, right)
    features = {
        "employer": Decimal("1")
        if left.normalized_employer and left.normalized_employer == right.normalized_employer
        else Decimal("0"),
        "title": token_similarity(left.title, right.title),
        "location": Decimal("1")
        if left.normalized_location and left.normalized_location == right.normalized_location
        else Decimal("0"),
        "text": token_similarity(left.text, right.text),
        "pensum_contract_start": Decimal("1")
        if left.pensum_contract_start
        and normalize_text(left.pensum_contract_start)
        == normalize_text(right.pensum_contract_start)
        else Decimal("0"),
        "contact_requisition": Decimal("1")
        if left.requisition_id and left.requisition_id == right.requisition_id
        else Decimal("0"),
    }
    score = sum((features[key] * WEIGHTS[key] for key in WEIGHTS), Decimal("0")).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )
    method = "HARD_KEY" if keys else "RULE_SCORE"
    outcome = "AUTO_MERGE" if keys else outcome_for_score(score)
    if barriers:
        outcome = "KEEP_SEPARATE"
    return PairAssessment(
        method, outcome, score, {key: str(value) for key, value in features.items()}, barriers, keys
    )
