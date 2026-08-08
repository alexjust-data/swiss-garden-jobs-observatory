from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from observations.models import Posting

from .evidence import PostingEvidence
from .models import (
    DedupDecision,
    DedupRun,
    DedupRunPostingAssignment,
    DedupRunVacancyState,
    Vacancy,
    VacancyPostingMembership,
)
from .positions import extract_position_count
from .precedence import source_precedence_rank


class RunClusters:
    def __init__(self, posting_ids: Iterable[str]) -> None:
        self.parent = {posting_id: posting_id for posting_id in posting_ids}

    def find(self, posting_id: str) -> str:
        parent = self.parent[posting_id]
        if parent != posting_id:
            self.parent[posting_id] = self.find(parent)
        return self.parent[posting_id]

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root == right_root:
            return
        winner, loser = sorted((left_root, right_root))
        self.parent[loser] = winner

    def groups(self) -> list[list[str]]:
        grouped: dict[str, list[str]] = {}
        for posting_id in sorted(self.parent):
            grouped.setdefault(self.find(posting_id), []).append(posting_id)
        return [grouped[key] for key in sorted(grouped)]


def _run_vacancy_key(posting_ids: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(posting_ids)).encode()).hexdigest()


def _canonical(group: list[PostingEvidence]) -> PostingEvidence:
    postings = {
        str(posting.pk): posting
        for posting in Posting.objects.filter(
            pk__in=[item.posting_id for item in group]
        ).select_related("source")
    }
    return min(
        group,
        key=lambda item: (
            source_precedence_rank(postings[item.posting_id].source),
            item.first_seen_at,
            item.posting_id,
        ),
    )


def _episode_number(group: list[PostingEvidence]) -> int:
    events = sorted(
        (
            event["observed_at"],
            event["event_type"],
            item.posting_id,
        )
        for item in group
        for event in item.lifecycle_events
    )
    episode_number = 1
    closed = False
    for _, event_type, _ in events:
        if event_type == "CLOSED_OBSERVED":
            closed = True
        elif closed and event_type in {"NEW", "STILL_ACTIVE"}:
            episode_number += 1
            closed = False
    return episode_number


def _position_projection(
    group: list[PostingEvidence], postings: dict[str, Posting]
) -> tuple[int | None, bool]:
    ranked: list[tuple[int, int | None, bool]] = []
    for item in group:
        result = extract_position_count(" ".join((item.title, item.text)))
        ranked.append(
            (
                source_precedence_rank(postings[item.posting_id].source),
                result.positions_count,
                result.multi_hire_possible,
            )
        )
    numeric = sorted((item for item in ranked if item[1] is not None), key=lambda item: item[0])
    if numeric:
        return numeric[0][1], True
    return None, any(item[2] for item in ranked)


def _group_decisions(
    run: DedupRun,
    posting_ids: set[str],
    inherited: dict[str, DedupDecision],
) -> dict[str, DedupDecision]:
    result = dict(inherited)
    for decision in DedupDecision.objects.filter(
        dedup_run=run,
        outcome__in=[DedupDecision.Outcome.AUTO_MERGE, DedupDecision.Outcome.MERGE],
    ):
        if str(decision.posting_a.pk) in posting_ids and str(decision.posting_b.pk) in posting_ids:
            result[str(decision.posting_b.pk)] = decision
    return result


def persist_run_snapshot(
    run: DedupRun,
    selected: list[PostingEvidence],
    clusters: RunClusters,
    inherited_decisions: dict[str, DedupDecision] | None = None,
) -> None:
    if DedupRunVacancyState.objects.filter(dedup_run=run).exists():
        return
    by_id = {item.posting_id: item for item in selected}
    postings = {
        str(posting.pk): posting
        for posting in Posting.objects.filter(pk__in=by_id).select_related("source")
    }
    inherited = inherited_decisions or {}
    for posting_ids in clusters.groups():
        group = [by_id[posting_id] for posting_id in posting_ids]
        canonical = _canonical(group)
        canonical_posting = postings[canonical.posting_id]
        membership = VacancyPostingMembership.objects.select_related("vacancy").get(
            posting=canonical_posting,
            identity_version=run.dedup_version,
        )
        latest_event = (
            canonical.lifecycle_events[-1]["event_type"]
            if canonical.lifecycle_events
            else "ACTIVE_OBSERVED"
        )
        status = (
            Vacancy.Status.CLOSED_OBSERVED
            if latest_event == "CLOSED_OBSERVED"
            else Vacancy.Status.ACTIVE
        )
        closed_at = None
        if status == Vacancy.Status.CLOSED_OBSERVED:
            closed_at = datetime.fromisoformat(
                next(
                    event["observed_at"]
                    for event in reversed(canonical.lifecycle_events)
                    if event["event_type"] == "CLOSED_OBSERVED"
                )
            )
        positions_count, multi_hire = _position_projection(group, postings)
        state = DedupRunVacancyState.objects.create(
            dedup_run=run,
            vacancy_identity=membership.vacancy,
            run_vacancy_key=_run_vacancy_key(posting_ids),
            status=status,
            canonical_posting=canonical_posting,
            first_seen_at=min(item.first_seen_at for item in group),
            last_seen_at=max(item.observed_at for item in group),
            closed_observed_at=closed_at,
            episode_number=_episode_number(group),
            positions_count=positions_count,
            multi_hire_possible=multi_hire,
        )
        decisions = _group_decisions(run, set(posting_ids), inherited)
        for posting_id in posting_ids:
            decision = decisions.get(posting_id)
            DedupRunPostingAssignment.objects.create(
                dedup_run=run,
                posting=postings[posting_id],
                run_vacancy_state=state,
                membership_role=(
                    VacancyPostingMembership.EvidenceRole.CANONICAL
                    if posting_id == canonical.posting_id
                    else VacancyPostingMembership.EvidenceRole.SUPPORTING
                ),
                link_method=(
                    decision.method if decision else VacancyPostingMembership.LinkMethod.INITIAL
                ),
                decision=decision,
            )


def snapshot_summary(run: DedupRun) -> dict[str, Any]:
    states = DedupRunVacancyState.objects.filter(dedup_run=run)
    position_counts = Counter(
        "explicit_numeric"
        if state.positions_count
        else "multi_hire_possible"
        if state.multi_hire_possible
        else "unknown"
        for state in states
    )
    return {
        "effective_vacancies": states.count(),
        "active_vacancies": states.filter(status=Vacancy.Status.ACTIVE).count(),
        "closed_vacancies": states.filter(status=Vacancy.Status.CLOSED_OBSERVED).count(),
        "episode_1": states.filter(episode_number=1).count(),
        "reappeared": states.filter(episode_number__gt=1).count(),
        "position_count": dict(position_counts),
        "review_queue_size": run.review_pairs,
    }
