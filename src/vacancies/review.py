from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from .engine import merge_vacancies
from .models import DedupDecision, DedupReviewItem, VacancyPostingMembership
from .normalizer import DEDUP_VERSION, NORMALIZER_VERSION


@transaction.atomic
def resolve_review(review_id: str, *, merge: bool, reason: str) -> DedupDecision:
    if not reason.strip():
        raise ValueError("A non-empty review reason is required")
    review = (
        DedupReviewItem.objects.select_for_update()
        .select_related(
            "algorithm_decision__dedup_run",
            "algorithm_decision__posting_a",
            "algorithm_decision__posting_b",
            "algorithm_decision__observation_a",
            "algorithm_decision__observation_b",
        )
        .get(pk=review_id)
    )
    if review.status != DedupReviewItem.Status.PENDING:
        raise ValueError("Review item has already been resolved")
    algorithm = review.algorithm_decision
    human = DedupDecision.objects.create(
        dedup_run=algorithm.dedup_run,
        posting_a=algorithm.posting_a,
        posting_b=algorithm.posting_b,
        observation_a=algorithm.observation_a,
        observation_b=algorithm.observation_b,
        dedup_version=DEDUP_VERSION,
        normalizer_version=NORMALIZER_VERSION,
        method=DedupDecision.Method.HUMAN,
        outcome=DedupDecision.Outcome.MERGE if merge else DedupDecision.Outcome.KEEP_SEPARATE,
        score=algorithm.score,
        feature_scores=algorithm.feature_scores,
        weights=algorithm.weights,
        blocking_evidence=algorithm.blocking_evidence,
        hard_barriers=algorithm.hard_barriers,
        evidence={"reason": reason, "algorithm_decision_id": str(algorithm.pk)},
    )
    if merge:
        left = VacancyPostingMembership.objects.select_related("vacancy").get(
            posting=algorithm.posting_a, identity_version=DEDUP_VERSION
        )
        right = VacancyPostingMembership.objects.select_related("vacancy").get(
            posting=algorithm.posting_b, identity_version=DEDUP_VERSION
        )
        merge_vacancies(left, right, algorithm.dedup_run, human, human=True)
        review.status = DedupReviewItem.Status.MERGED
    else:
        review.status = DedupReviewItem.Status.KEPT_SEPARATE
    review.resolution_reason = reason
    review.resolved_at = timezone.now()
    review.save(update_fields=["status", "resolution_reason", "resolved_at", "updated_at"])
    return human
