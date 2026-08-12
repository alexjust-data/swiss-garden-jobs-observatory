from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from dashboard.models import DashboardSnapshot
from dashboard.services import DashboardBuildError, build_dashboard_snapshot
from dashboard.tests.factories import create_dashboard_upstream, digest
from day0.services import _review_evidence
from observations.models import CollectionRun, PostingLifecycleEvent, PostingObservation
from observations.pit_selection import PIT_SELECTION_VERSION
from premium_segments.classifier import run_classification
from premium_segments.models import PremiumSegmentAssessment, PremiumSegmentRun
from vacancies.engine import run_deduplication
from vacancies.evidence import select_posting_evidence
from vacancies.models import (
    DedupDecision,
    DedupReviewItem,
    DedupRun,
    DedupRunPostingAssignment,
    DedupRunVacancyState,
    Vacancy,
    VacancyEpisode,
)


@pytest.mark.django_db(transaction=True)
def test_pending_closed_and_reappeared_use_shared_content_evidence() -> None:
    data = create_dashboard_upstream(suffix="011dc1-lifecycle")
    t1 = data["observation"].observed_at
    t2, t3, t4 = (t1 + timedelta(days=value) for value in (1, 3, 4))
    posting = data["posting"]
    source = data["source"]

    for when, state in ((t2, "DISAPPEARED_PENDING"), (t3, "CLOSED_OBSERVED")):
        collection = CollectionRun.objects.create(
            source=source,
            started_at=when,
            finished_at=when,
            status="SUCCEEDED",
            run_scope="FULL_SOURCE",
            source_health_status="HEALTHY",
            snapshot_complete=True,
            listing_url=source.search_url,
        )
        missing = PostingObservation.objects.create(
            collection_run=collection,
            posting=posting,
            source=source,
            observation_status="NOT_FOUND",
            source_posting_id=posting.source_posting_id,
            observed_at=when,
            canonical_url=data["observation"].canonical_url,
            title=data["observation"].title,
            raw_artifact=data["observation"].raw_artifact,
            structured_payload={},
            contract_payload={"schema_version": "1.2"},
        )
        PostingLifecycleEvent.objects.create(
            posting=posting,
            posting_observation=missing,
            collection_run=collection,
            event_type=state,
            observed_at=when,
            source_health_status="HEALTHY",
            evidence={"fixture": "gate-011d-c1"},
        )

    reappeared_run = CollectionRun.objects.create(
        source=source,
        started_at=t4,
        finished_at=t4,
        status="SUCCEEDED",
        run_scope="FULL_SOURCE",
        source_health_status="HEALTHY",
        snapshot_complete=True,
        listing_url=source.search_url,
    )
    reappeared = PostingObservation.objects.create(
        collection_run=reappeared_run,
        posting=posting,
        source=source,
        observation_status="ACTIVE",
        source_posting_id=posting.source_posting_id,
        observed_at=t4,
        canonical_url=data["observation"].canonical_url,
        title=data["observation"].title,
        hiring_organization=data["observation"].hiring_organization,
        description_html=data["observation"].description_html,
        raw_artifact=data["observation"].raw_artifact,
        structured_payload=data["observation"].structured_payload,
        contract_payload={
            **data["observation"].contract_payload,
            "observed_at": t4.isoformat(),
            "collector_run_id": str(reappeared_run.pk),
        },
    )
    PostingLifecycleEvent.objects.create(
        posting=posting,
        posting_observation=reappeared,
        collection_run=reappeared.collection_run,
        event_type="STILL_ACTIVE",
        observed_at=t4,
        source_health_status="HEALTHY",
        evidence={"fixture": "gate-011d-c1"},
    )

    for cutoff, expected_observation, expected_state in (
        (t1, data["observation"], "NEW"),
        (t2, data["observation"], "DISAPPEARED_PENDING"),
        (t3, data["observation"], "CLOSED_OBSERVED"),
        (t4, reappeared, "STILL_ACTIVE"),
    ):
        dedup_evidence = select_posting_evidence(cutoff)
        premium_run, _ = run_classification(cutoff)
        premium = PremiumSegmentAssessment.objects.get(run=premium_run)
        assert dedup_evidence[0].observation_id == str(expected_observation.pk)
        assert premium.posting_observation == expected_observation
        assert premium.evidence["lifecycle_state"] == expected_state
        assert premium.evidence["pit_selection_version"] == PIT_SELECTION_VERSION


@pytest.mark.django_db(transaction=True)
def test_dashboard_rejects_legacy_premium_selection_contract() -> None:
    data = create_dashboard_upstream(suffix="011dc1-legacy", premium_pit_selection_version=None)
    with pytest.raises(DashboardBuildError, match="unsupported premium PIT selection version"):
        build_dashboard_snapshot(
            as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
        )


@pytest.mark.django_db(transaction=True)
def test_equal_observed_at_uses_created_at_before_uuid_in_every_layer() -> None:
    data = create_dashboard_upstream(suffix="011dc1-tied-lifecycle")
    posting = data["posting"]
    source = data["source"]
    when = data["as_of"] + timedelta(days=1)
    closed_run = CollectionRun.objects.create(
        source=source,
        started_at=when,
        finished_at=when,
        status="SUCCEEDED",
        run_scope="FULL_SOURCE",
        source_health_status="HEALTHY",
        snapshot_complete=True,
        listing_url=source.search_url,
    )
    closed_observation = PostingObservation.objects.create(
        collection_run=closed_run,
        posting=posting,
        source=source,
        observation_status="NOT_FOUND",
        source_posting_id=posting.source_posting_id,
        observed_at=when,
        canonical_url=data["observation"].canonical_url,
        title=data["observation"].title,
        raw_artifact=data["observation"].raw_artifact,
        structured_payload={},
        contract_payload={"schema_version": "1.2"},
    )
    PostingLifecycleEvent.objects.create(
        pk=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
        posting=posting,
        posting_observation=closed_observation,
        collection_run=closed_run,
        event_type="CLOSED_OBSERVED",
        observed_at=when,
        created_at=when + timedelta(seconds=1),
        source_health_status="HEALTHY",
    )
    active_run = CollectionRun.objects.create(
        source=source,
        started_at=when,
        finished_at=when,
        status="SUCCEEDED",
        run_scope="FULL_SOURCE",
        source_health_status="HEALTHY",
        snapshot_complete=True,
        listing_url=source.search_url,
    )
    active_observation = PostingObservation.objects.create(
        collection_run=active_run,
        posting=posting,
        source=source,
        observation_status="ACTIVE",
        source_posting_id=posting.source_posting_id,
        observed_at=when,
        canonical_url=data["observation"].canonical_url,
        title=data["observation"].title,
        hiring_organization=data["observation"].hiring_organization,
        description_html=data["observation"].description_html,
        raw_artifact=data["observation"].raw_artifact,
        structured_payload=data["observation"].structured_payload,
        contract_payload={
            **data["observation"].contract_payload,
            "observed_at": when.isoformat(),
            "collector_run_id": str(active_run.pk),
        },
    )
    latest = PostingLifecycleEvent.objects.create(
        pk=UUID("00000000-0000-0000-0000-000000000001"),
        posting=posting,
        posting_observation=active_observation,
        collection_run=active_run,
        event_type="STILL_ACTIVE",
        observed_at=when,
        created_at=when + timedelta(seconds=2),
        source_health_status="HEALTHY",
    )

    evidence = select_posting_evidence(when)[0]
    dedup_run, _ = run_deduplication(when)
    premium_run, _ = run_classification(when)
    premium = PremiumSegmentAssessment.objects.get(run=premium_run)
    state = DedupRunVacancyState.objects.get(dedup_run=dedup_run)
    vacancy = Vacancy.objects.get(pk=state.vacancy_identity_id)
    latest_episode = VacancyEpisode.objects.get(vacancy=vacancy, episode_number=2)

    assert evidence.lifecycle_events[-1]["id"] == str(latest.pk)
    assert evidence.lifecycle_status == "STILL_ACTIVE"
    assert evidence.observation_id == str(active_observation.pk)
    assert state.status == "ACTIVE"
    assert state.episode_number == 2
    assert vacancy.current_status == "ACTIVE"
    assert vacancy.current_episode_number == 2
    assert latest_episode.status == "ACTIVE"
    assert premium.posting_observation == active_observation
    assert premium.evidence["lifecycle_event_id"] == str(latest.pk)
    assert premium.evidence["lifecycle_state"] == "STILL_ACTIVE"


@pytest.mark.django_db(transaction=True)
def test_equal_observed_at_later_close_wins_operational_and_pit_projection() -> None:
    data = create_dashboard_upstream(suffix="011dc1-tied-close-latest")
    posting = data["posting"]
    source = data["source"]
    when = data["as_of"] + timedelta(days=1)
    active_run = CollectionRun.objects.create(
        source=source,
        started_at=when,
        finished_at=when,
        status="SUCCEEDED",
        run_scope="FULL_SOURCE",
        source_health_status="HEALTHY",
        snapshot_complete=True,
        listing_url=source.search_url,
    )
    active_observation = PostingObservation.objects.create(
        collection_run=active_run,
        posting=posting,
        source=source,
        observation_status="ACTIVE",
        source_posting_id=posting.source_posting_id,
        observed_at=when,
        canonical_url=data["observation"].canonical_url,
        title=data["observation"].title,
        hiring_organization=data["observation"].hiring_organization,
        description_html=data["observation"].description_html,
        raw_artifact=data["observation"].raw_artifact,
        structured_payload=data["observation"].structured_payload,
        contract_payload={
            **data["observation"].contract_payload,
            "observed_at": when.isoformat(),
            "collector_run_id": str(active_run.pk),
        },
    )
    PostingLifecycleEvent.objects.create(
        pk=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
        posting=posting,
        posting_observation=active_observation,
        collection_run=active_run,
        event_type="STILL_ACTIVE",
        observed_at=when,
        created_at=when + timedelta(seconds=1),
        source_health_status="HEALTHY",
    )
    closed_run = CollectionRun.objects.create(
        source=source,
        started_at=when,
        finished_at=when,
        status="SUCCEEDED",
        run_scope="FULL_SOURCE",
        source_health_status="HEALTHY",
        snapshot_complete=True,
        listing_url=source.search_url,
    )
    closed_observation = PostingObservation.objects.create(
        collection_run=closed_run,
        posting=posting,
        source=source,
        observation_status="NOT_FOUND",
        source_posting_id=posting.source_posting_id,
        observed_at=when,
        canonical_url=data["observation"].canonical_url,
        title=data["observation"].title,
        raw_artifact=data["observation"].raw_artifact,
        structured_payload={},
        contract_payload={"schema_version": "1.2"},
    )
    latest = PostingLifecycleEvent.objects.create(
        pk=UUID("00000000-0000-0000-0000-000000000001"),
        posting=posting,
        posting_observation=closed_observation,
        collection_run=closed_run,
        event_type="CLOSED_OBSERVED",
        observed_at=when,
        created_at=when + timedelta(seconds=2),
        source_health_status="HEALTHY",
    )

    evidence = select_posting_evidence(when)[0]
    dedup_run, _ = run_deduplication(when)
    premium_run, _ = run_classification(when)
    state = DedupRunVacancyState.objects.get(dedup_run=dedup_run)
    vacancy = Vacancy.objects.get(pk=state.vacancy_identity_id)
    premium = PremiumSegmentAssessment.objects.get(run=premium_run)

    assert evidence.lifecycle_events[-1]["id"] == str(latest.pk)
    assert evidence.lifecycle_status == "CLOSED_OBSERVED"
    assert state.status == "CLOSED_OBSERVED"
    assert state.episode_number == 1
    assert vacancy.current_status == "CLOSED_OBSERVED"
    assert vacancy.current_episode_number == 1
    assert VacancyEpisode.objects.get(vacancy=vacancy).status == "CLOSED_OBSERVED"
    assert premium.evidence["lifecycle_event_id"] == str(latest.pk)
    assert premium.evidence["lifecycle_state"] == "CLOSED_OBSERVED"


@pytest.mark.django_db(transaction=True)
def test_closed_green_record_and_review_are_not_current_day0_market() -> None:
    active = create_dashboard_upstream(suffix="011dc1-active")
    closed = create_dashboard_upstream(
        suffix="011dc1-closed",
        green_result="REVIEW",
        premium_status="SKIPPED_NOT_GREEN",
        vacancy_status="CLOSED_OBSERVED",
    )
    closed_snapshot, _ = build_dashboard_snapshot(
        as_of=closed["as_of"],
        dedup_run=closed["dedup"],
        premium_run=closed["premium_run"],
    )
    critical, noncritical, critical_green, *_ = _review_evidence(
        closed["dedup"],
        closed["premium_run"],
        closed_snapshot,
        {str(closed["source"].pk)},
    )
    assert critical_green == 0 and not critical
    assert any(item.startswith("green-excluded-inactive:") for item in noncritical)

    active_snapshot, _ = build_dashboard_snapshot(
        as_of=active["as_of"],
        dedup_run=active["dedup"],
        premium_run=active["premium_run"],
    )
    assert active_snapshot.vacancy_records.filter(vacancy_status="ACTIVE").count() == 1


def _cross_state_review_fixture(
    *, active_green: str, closed_green: str, suffix: str
) -> tuple[DedupReviewItem, DedupRun, PremiumSegmentRun, DashboardSnapshot, set[str]]:
    active = create_dashboard_upstream(
        suffix=f"{suffix}-active",
        green_result=active_green,
        premium_status=(
            "NO_SUFFICIENT_EVIDENCE" if active_green == "GREEN_CONFIRMED" else "SKIPPED_NOT_GREEN"
        ),
    )
    closed = create_dashboard_upstream(
        suffix=f"{suffix}-closed",
        as_of=active["as_of"],
        green_result=closed_green,
        premium_status=(
            "NO_SUFFICIENT_EVIDENCE" if closed_green == "GREEN_CONFIRMED" else "SKIPPED_NOT_GREEN"
        ),
        vacancy_status="CLOSED_OBSERVED",
    )
    run = DedupRun.objects.create(
        dedup_version="dedup-v0.1",
        normalizer_version="dedup-normalizer-v0.1",
        position_count_version="position-count-v0.1",
        source_precedence_version="source-precedence-v0.1",
        as_of=active["as_of"],
        status="SUCCEEDED",
        started_at=active["as_of"],
        finished_at=active["as_of"],
        postings_considered=2,
        review_pairs=1,
        input_fingerprint=digest(f"{suffix}-dedup"),
    )
    states = []
    for data, status in ((active, "ACTIVE"), (closed, "CLOSED_OBSERVED")):
        state = DedupRunVacancyState.objects.create(
            dedup_run=run,
            run_vacancy_key=digest(f"{suffix}-{status}"),
            status=status,
            canonical_posting=data["posting"],
            first_seen_at=data["observation"].observed_at,
            last_seen_at=data["observation"].observed_at,
            closed_observed_at=(data["as_of"] if status == "CLOSED_OBSERVED" else None),
        )
        DedupRunPostingAssignment.objects.create(
            dedup_run=run,
            posting=data["posting"],
            run_vacancy_state=state,
            membership_role="CANONICAL",
            link_method="INITIAL",
        )
        states.append(state)
    premium_run = PremiumSegmentRun.objects.create(
        as_of=active["as_of"],
        classifier_version=active["premium_run"].classifier_version,
        normalizer_version=active["premium_run"].normalizer_version,
        taxonomy_version=active["premium_run"].taxonomy_version,
        taxonomy_sha256=active["premium_run"].taxonomy_sha256,
        configuration={"pit_selection_version": PIT_SELECTION_VERSION},
        input_fingerprint=digest(f"{suffix}-premium"),
        observations_considered=2,
        green_confirmed_eligible=sum(
            value == "GREEN_CONFIRMED" for value in (active_green, closed_green)
        ),
        no_sufficient_evidence_count=sum(
            value == "GREEN_CONFIRMED" for value in (active_green, closed_green)
        ),
        skipped_not_green_count=sum(value == "NOT_GREEN" for value in (active_green, closed_green)),
        unknown_count=2,
        status="SUCCEEDED",
        started_at=active["as_of"],
        finished_at=active["as_of"],
    )
    for data, green in ((active, active_green), (closed, closed_green)):
        PremiumSegmentAssessment.objects.create(
            run=premium_run,
            posting_observation=data["observation"],
            green_relevance_assessment=data["green"],
            effective_green_result=green,
            segment="UNKNOWN",
            assessment_status=(
                "NO_SUFFICIENT_EVIDENCE" if green == "GREEN_CONFIRMED" else "SKIPPED_NOT_GREEN"
            ),
            method="FIXTURE",
            evidence_strength="NONE",
            evidence={"fixture": "gate-011d-c1-cross-state"},
        )
    decision = DedupDecision.objects.create(
        dedup_run=run,
        posting_a=active["posting"],
        posting_b=closed["posting"],
        observation_a=active["observation"],
        observation_b=closed["observation"],
        dedup_version="dedup-v0.1",
        normalizer_version="dedup-normalizer-v0.1",
        method="RULE_SCORE",
        outcome="REVIEW",
        score=Decimal("0.8000"),
    )
    review = DedupReviewItem.objects.create(
        algorithm_decision=decision,
        run_vacancy_state_a=states[0],
        run_vacancy_state_b=states[1],
    )
    active_snapshot, _ = build_dashboard_snapshot(
        as_of=active["as_of"],
        dedup_run=active["dedup"],
        premium_run=active["premium_run"],
    )
    return review, run, premium_run, active_snapshot, {str(active["source"].pk)}


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("case", "active_green", "closed_green", "expected_critical"),
    [
        ("gg", "GREEN_CONFIRMED", "GREEN_CONFIRMED", True),
        ("gn", "GREEN_CONFIRMED", "NOT_GREEN", True),
        ("ng", "NOT_GREEN", "GREEN_CONFIRMED", False),
    ],
)
def test_active_closed_dedup_review_criticality_follows_possible_market_effect(
    case: str, active_green: str, closed_green: str, expected_critical: bool
) -> None:
    review, run, premium_run, snapshot, eligible = _cross_state_review_fixture(
        active_green=active_green,
        closed_green=closed_green,
        suffix=f"cross-{case}",
    )
    critical, noncritical, _, critical_dedup, _ = _review_evidence(
        run, premium_run, snapshot, eligible
    )
    marker = f"dedup:{review.pk}"

    assert (marker in critical) is expected_critical
    assert (marker in noncritical) is (not expected_critical)
    assert critical_dedup == int(expected_critical)
