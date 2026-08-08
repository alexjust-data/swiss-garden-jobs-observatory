from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal
from itertools import combinations
from typing import Any

from django.db import transaction
from django.utils import timezone

from observations.models import Posting, PostingLifecycleEvent

from .evidence import PostingEvidence, evidence_snapshot, input_fingerprint, select_posting_evidence
from .models import (
    DedupDecision,
    DedupReviewItem,
    DedupRun,
    PositionCountEvidence,
    Vacancy,
    VacancyEpisode,
    VacancyLifecycleEvent,
    VacancyMembershipEvent,
    VacancyPostingMembership,
)
from .normalizer import (
    DEDUP_VERSION,
    NORMALIZER_VERSION,
    POSITION_COUNT_VERSION,
    REPOST_WINDOW_DAYS,
    SOURCE_PRECEDENCE_VERSION,
)
from .positions import extract_position_count
from .precedence import source_precedence_rank
from .scoring import WEIGHTS, PairAssessment, assess_pair, is_candidate

CONFIGURATION: dict[str, Any] = {
    "weights": {key: str(value) for key, value in WEIGHTS.items()},
    "thresholds": {"auto_merge": "0.90", "review": "0.78"},
    "repost_window_days": REPOST_WINDOW_DAYS,
    "normalizer_version": NORMALIZER_VERSION,
    "source_precedence_version": SOURCE_PRECEDENCE_VERSION,
}


def canonical_pair(
    left: PostingEvidence, right: PostingEvidence
) -> tuple[PostingEvidence, PostingEvidence]:
    return (left, right) if left.posting_id < right.posting_id else (right, left)


def qualifies_as_repost(
    closed_at: datetime,
    reappeared_at: datetime,
    *,
    same_requisition: bool,
    score: Decimal,
) -> bool:
    if same_requisition:
        return True
    gap_days = (reappeared_at - closed_at).total_seconds() / 86400
    return 0 <= gap_days <= REPOST_WINDOW_DAYS and score >= Decimal("0.90")


def _posting_closed_at(posting_id: str, as_of: datetime) -> datetime | None:
    event = (
        PostingLifecycleEvent.objects.filter(
            posting_id=posting_id,
            event_type="CLOSED_OBSERVED",
            observed_at__lte=as_of,
        )
        .order_by("-observed_at")
        .first()
    )
    return event.observed_at if event else None


def _repost_window_barrier(
    left: PostingEvidence, right: PostingEvidence, assessment: PairAssessment, as_of: datetime
) -> dict[str, str] | None:
    earlier, later = (left, right) if left.first_seen_at <= right.first_seen_at else (right, left)
    closed_at = _posting_closed_at(earlier.posting_id, as_of)
    if not closed_at or later.first_seen_at <= closed_at:
        return None
    if qualifies_as_repost(
        closed_at,
        later.first_seen_at,
        same_requisition=bool(
            earlier.requisition_id and earlier.requisition_id == later.requisition_id
        ),
        score=assessment.score,
    ):
        return None
    return {
        "type": "REPOST_WINDOW_EXCEEDED",
        "closed_at": closed_at.isoformat(),
        "reappeared_at": later.first_seen_at.isoformat(),
    }


def _create_initial_membership(
    item: PostingEvidence, run: DedupRun
) -> tuple[VacancyPostingMembership, bool]:
    existing = (
        VacancyPostingMembership.objects.filter(
            posting_id=item.posting_id, identity_version=DEDUP_VERSION
        )
        .select_related("vacancy")
        .first()
    )
    if existing:
        return existing, False
    posting = Posting.objects.select_related("source").get(pk=item.posting_id)
    vacancy = Vacancy.objects.create(
        identity_version=DEDUP_VERSION,
        first_seen_at=posting.first_seen_at,
        last_seen_at=posting.last_seen_at,
        canonical_posting=posting,
    )
    membership = VacancyPostingMembership.objects.create(
        vacancy=vacancy,
        posting=posting,
        identity_version=DEDUP_VERSION,
        link_method=VacancyPostingMembership.LinkMethod.INITIAL,
        source_precedence_rank=source_precedence_rank(posting.source),
        canonical_evidence_role=VacancyPostingMembership.EvidenceRole.CANONICAL,
    )
    VacancyMembershipEvent.objects.create(
        membership=membership,
        to_vacancy=vacancy,
        dedup_run=run,
        event_type=VacancyMembershipEvent.EventType.LINK,
        reason="Initial provisional economic identity",
        evidence={"posting_id": item.posting_id, "observation_id": item.observation_id},
    )
    return membership, True


def _canonicalize(vacancy: Vacancy, run: DedupRun) -> None:
    memberships = list(
        VacancyPostingMembership.objects.filter(vacancy=vacancy)
        .select_related("posting__source")
        .order_by("source_precedence_rank", "created_at")
    )
    if not memberships:
        return
    canonical = memberships[0]
    for membership in memberships:
        role = (
            VacancyPostingMembership.EvidenceRole.CANONICAL
            if membership.pk == canonical.pk
            else VacancyPostingMembership.EvidenceRole.SUPPORTING
        )
        if membership.canonical_evidence_role != role:
            membership.canonical_evidence_role = role
            membership.save(update_fields=["canonical_evidence_role", "updated_at"])
            VacancyMembershipEvent.objects.create(
                membership=membership,
                from_vacancy=vacancy,
                to_vacancy=vacancy,
                dedup_run=run,
                event_type=VacancyMembershipEvent.EventType.CANONICAL_PROMOTE,
                reason="Canonical evidence recalculated by source precedence",
                evidence={"role": role, "rank": membership.source_precedence_rank},
            )
    if vacancy.canonical_posting != canonical.posting:
        vacancy.canonical_posting = canonical.posting
        vacancy.save(update_fields=["canonical_posting", "updated_at"])


def merge_vacancies(
    left: VacancyPostingMembership,
    right: VacancyPostingMembership,
    run: DedupRun,
    decision: DedupDecision,
    *,
    human: bool = False,
) -> Vacancy:
    if left.vacancy.pk == right.vacancy.pk:
        return left.vacancy
    winner = min(
        (left.vacancy, right.vacancy),
        key=lambda vacancy: (vacancy.first_seen_at, str(vacancy.pk)),
    )
    loser = right.vacancy if winner.pk == left.vacancy.pk else left.vacancy
    memberships = list(loser.memberships.filter(identity_version=DEDUP_VERSION))
    for membership in memberships:
        previous = membership.vacancy
        membership.vacancy = winner
        membership.link_method = (
            VacancyPostingMembership.LinkMethod.HUMAN if human else decision.method
        )
        membership.dedup_decision = decision
        membership.save(update_fields=["vacancy", "link_method", "dedup_decision", "updated_at"])
        VacancyMembershipEvent.objects.create(
            membership=membership,
            from_vacancy=previous,
            to_vacancy=winner,
            dedup_run=run,
            event_type=(
                VacancyMembershipEvent.EventType.HUMAN_CONFIRM
                if human
                else VacancyMembershipEvent.EventType.MERGE_IDENTITY
            ),
            reason="Audited vacancy identity reconciliation",
            evidence={"decision_id": str(decision.pk)},
        )
    loser.merged_into = winner
    loser.save(update_fields=["merged_into", "updated_at"])
    _canonicalize(winner, run)
    return winner


def _sync_episode(
    vacancy: Vacancy, run: DedupRun, evidence_by_posting: dict[str, PostingEvidence]
) -> bool:
    selected = [
        evidence_by_posting[str(member.posting.pk)]
        for member in VacancyPostingMembership.objects.filter(
            vacancy=vacancy, identity_version=DEDUP_VERSION
        )
        if str(member.posting.pk) in evidence_by_posting
    ]
    if not selected:
        return False
    first_seen = min(item.first_seen_at for item in selected)
    last_seen = max(item.observed_at for item in selected)
    episode = VacancyEpisode.objects.filter(vacancy=vacancy).order_by("-episode_number").first()
    created = False
    if episode is None:
        episode = VacancyEpisode.objects.create(
            vacancy=vacancy,
            episode_number=1,
            opened_observed_at=first_seen,
            last_seen_at=last_seen,
        )
        VacancyLifecycleEvent.objects.create(
            vacancy=vacancy,
            episode=episode,
            dedup_run=run,
            event_type=VacancyLifecycleEvent.EventType.NEW,
            observed_at=first_seen,
            supporting_postings=[item.posting_id for item in selected],
            reason="First derived economic vacancy appearance",
            dedup_version=DEDUP_VERSION,
        )
        created = True
    canonical = vacancy.canonical_posting
    canonical_closed = _posting_closed_at(str(canonical.pk), run.as_of) if canonical else None
    reappearance_event = None
    if canonical_closed:
        reappearance_event = (
            PostingLifecycleEvent.objects.filter(
                posting_id__in=[item.posting_id for item in selected],
                event_type__in=["NEW", "STILL_ACTIVE"],
                observed_at__gt=canonical_closed,
                observed_at__lte=run.as_of,
            )
            .order_by("observed_at", "pk")
            .first()
        )
    can_reopen = bool(
        canonical_closed and reappearance_event and episode.opened_observed_at <= canonical_closed
    )
    if can_reopen and canonical_closed and reappearance_event:
        reopened = reappearance_event.observed_at
        if episode.closed_observed_at is None:
            episode.closed_observed_at = canonical_closed
            episode.status = VacancyEpisode.Status.CLOSED_OBSERVED
            episode.save(update_fields=["closed_observed_at", "status", "updated_at"])
        number = episode.episode_number + 1
        episode, was_created = VacancyEpisode.objects.get_or_create(
            vacancy=vacancy,
            episode_number=number,
            defaults={
                "opened_observed_at": reopened,
                "last_seen_at": last_seen,
                "reappearance_gap_days": (reopened - canonical_closed).days,
            },
        )
        if was_created:
            vacancy.current_episode_number = number
            VacancyLifecycleEvent.objects.create(
                vacancy=vacancy,
                episode=episode,
                dedup_run=run,
                event_type=VacancyLifecycleEvent.EventType.REAPPEARED,
                observed_at=reopened,
                supporting_postings=[str(reappearance_event.posting.pk)],
                reason="Same vacancy reappeared as a new episode",
                dedup_version=DEDUP_VERSION,
                evidence={"gap_days": episode.reappearance_gap_days},
            )
            created = True
    canonical_current_closed = bool(canonical_closed and reappearance_event is None)
    vacancy.first_seen_at = first_seen
    vacancy.last_seen_at = last_seen
    vacancy.current_status = (
        Vacancy.Status.CLOSED_OBSERVED if canonical_current_closed else Vacancy.Status.ACTIVE
    )
    vacancy.closed_observed_at = canonical_closed if canonical_current_closed else None
    vacancy.save(
        update_fields=[
            "first_seen_at",
            "last_seen_at",
            "current_status",
            "closed_observed_at",
            "current_episode_number",
            "updated_at",
        ]
    )
    if canonical_current_closed and episode.status != VacancyEpisode.Status.CLOSED_OBSERVED:
        episode.status = VacancyEpisode.Status.CLOSED_OBSERVED
        episode.closed_observed_at = canonical_closed
        episode.save(update_fields=["status", "closed_observed_at", "updated_at"])
        VacancyLifecycleEvent.objects.create(
            vacancy=vacancy,
            episode=episode,
            dedup_run=run,
            event_type=VacancyLifecycleEvent.EventType.CLOSED_OBSERVED,
            observed_at=canonical_closed,
            supporting_postings=[str(canonical.pk)] if canonical else [],
            reason="Canonical source posting is CLOSED_OBSERVED",
            dedup_version=DEDUP_VERSION,
        )
    return created


def _sync_positions(vacancy: Vacancy, evidence_by_posting: dict[str, PostingEvidence]) -> None:
    episode = VacancyEpisode.objects.filter(vacancy=vacancy).order_by("-episode_number").first()
    if episode is None:
        return
    candidates: list[tuple[int, PositionCountEvidence]] = []
    for membership in VacancyPostingMembership.objects.filter(vacancy=vacancy):
        item = evidence_by_posting.get(str(membership.posting.pk))
        if item is None:
            continue
        parsed = extract_position_count(" ".join((item.title, item.text)))
        method = (
            PositionCountEvidence.Method.EXPLICIT_NUMERIC
            if parsed.positions_count is not None
            else PositionCountEvidence.Method.MULTI_HIRE_SIGNAL
            if parsed.multi_hire_possible
            else PositionCountEvidence.Method.NOT_DISCLOSED
        )
        row, _ = PositionCountEvidence.objects.get_or_create(
            posting_observation_id=item.observation_id,
            vacancy_episode=episode,
            extractor_version=POSITION_COUNT_VERSION,
            defaults={
                "positions_count": parsed.positions_count,
                "multi_hire_possible": parsed.multi_hire_possible,
                "method": method,
                "raw_evidence": {"text": parsed.raw_evidence, "method": parsed.method},
            },
        )
        candidates.append((membership.source_precedence_rank, row))
    numeric = sorted(
        (candidate for candidate in candidates if candidate[1].positions_count),
        key=lambda item: item[0],
    )
    if numeric:
        episode.positions_count = numeric[0][1].positions_count
        episode.multi_hire_possible = True
    else:
        episode.positions_count = None
        episode.multi_hire_possible = any(row.multi_hire_possible for _, row in candidates)
    episode.save(update_fields=["positions_count", "multi_hire_possible", "updated_at"])


@transaction.atomic
def run_deduplication(as_of: datetime, dedup_version: str = DEDUP_VERSION) -> tuple[DedupRun, bool]:
    if dedup_version != DEDUP_VERSION:
        raise ValueError(f"Unsupported dedup version: {dedup_version}")
    selected = select_posting_evidence(as_of)
    fingerprint = input_fingerprint(as_of, CONFIGURATION, selected)
    existing = DedupRun.objects.filter(
        dedup_version=dedup_version,
        as_of=as_of,
        input_fingerprint=fingerprint,
        status=DedupRun.Status.SUCCEEDED,
    ).first()
    if existing:
        return existing, True
    run = DedupRun.objects.create(
        dedup_version=dedup_version,
        normalizer_version=NORMALIZER_VERSION,
        position_count_version=POSITION_COUNT_VERSION,
        source_precedence_version=SOURCE_PRECEDENCE_VERSION,
        as_of=as_of,
        input_fingerprint=fingerprint,
        configuration=CONFIGURATION,
        postings_considered=len(selected),
    )
    memberships: dict[str, VacancyPostingMembership] = {}
    for item in selected:
        membership, created = _create_initial_membership(item, run)
        memberships[item.posting_id] = membership
        run.vacancies_created += int(created)
    for raw_left, raw_right in combinations(selected, 2):
        left, right = canonical_pair(raw_left, raw_right)
        if not is_candidate(left, right):
            continue
        run.candidate_pairs += 1
        assessment = assess_pair(left, right)
        barriers = list(assessment.hard_barriers)
        repost_barrier = _repost_window_barrier(left, right, assessment, as_of)
        if repost_barrier:
            barriers.append(repost_barrier)
        outcome = "KEEP_SEPARATE" if barriers else assessment.outcome
        decision = DedupDecision.objects.create(
            dedup_run=run,
            posting_a_id=left.posting_id,
            posting_b_id=right.posting_id,
            observation_a_id=left.observation_id,
            observation_b_id=right.observation_id,
            dedup_version=DEDUP_VERSION,
            normalizer_version=NORMALIZER_VERSION,
            method=assessment.method,
            outcome=outcome,
            score=assessment.score,
            feature_scores=assessment.feature_scores,
            weights={key: str(value) for key, value in WEIGHTS.items()},
            blocking_evidence={"hard_keys": assessment.hard_key_evidence},
            hard_barriers=barriers,
            evidence={"left": evidence_snapshot(left), "right": evidence_snapshot(right)},
        )
        if barriers:
            run.hard_barrier_pairs += 1
            run.keep_separate_pairs += 1
        elif outcome == "AUTO_MERGE":
            run.hard_key_merges += int(assessment.method == "HARD_KEY")
            run.rule_auto_merges += int(assessment.method == "RULE_SCORE")
            merge_vacancies(
                memberships[left.posting_id], memberships[right.posting_id], run, decision
            )
            memberships[left.posting_id].refresh_from_db()
            memberships[right.posting_id].refresh_from_db()
        elif outcome == "REVIEW":
            run.review_pairs += 1
            DedupReviewItem.objects.get_or_create(
                algorithm_decision=decision,
                defaults={
                    "vacancy_a": memberships[left.posting_id].vacancy,
                    "vacancy_b": memberships[right.posting_id].vacancy,
                },
            )
        else:
            run.keep_separate_pairs += 1
    evidence_by_posting = {item.posting_id: item for item in selected}
    effective = Vacancy.objects.filter(identity_version=DEDUP_VERSION, merged_into__isnull=True)
    for vacancy in effective:
        _canonicalize(vacancy, run)
        run.episodes_created += int(_sync_episode(vacancy, run, evidence_by_posting))
        _sync_positions(vacancy, evidence_by_posting)
    run.status = DedupRun.Status.SUCCEEDED
    run.finished_at = timezone.now()
    run.save()
    return run, False


def run_summary(run: DedupRun) -> dict[str, Any]:
    effective = Vacancy.objects.filter(identity_version=run.dedup_version, merged_into__isnull=True)
    episodes = VacancyEpisode.objects.filter(vacancy__in=effective)
    position_counts = Counter(
        "explicit_numeric"
        if episode.positions_count
        else "multi_hire_possible"
        if episode.multi_hire_possible
        else "unknown"
        for episode in episodes
    )
    return {
        "effective_vacancies": effective.count(),
        "active_vacancies": effective.filter(current_status=Vacancy.Status.ACTIVE).count(),
        "closed_vacancies": effective.filter(current_status=Vacancy.Status.CLOSED_OBSERVED).count(),
        "episode_1": episodes.filter(episode_number=1).count(),
        "reappeared": episodes.filter(episode_number__gt=1).values("vacancy_id").distinct().count(),
        "position_count": dict(position_counts),
        "review_queue_size": DedupReviewItem.objects.filter(
            status=DedupReviewItem.Status.PENDING
        ).count(),
    }
