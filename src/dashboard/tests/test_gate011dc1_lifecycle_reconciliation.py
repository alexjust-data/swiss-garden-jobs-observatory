from __future__ import annotations

from datetime import timedelta

import pytest

from dashboard.services import DashboardBuildError, build_dashboard_snapshot
from dashboard.tests.factories import create_dashboard_upstream
from day0.services import _review_evidence
from observations.models import CollectionRun, PostingLifecycleEvent, PostingObservation
from observations.pit_selection import PIT_SELECTION_VERSION
from premium_segments.classifier import run_classification
from premium_segments.models import PremiumSegmentAssessment
from vacancies.evidence import select_posting_evidence


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
    data = create_dashboard_upstream(
        suffix="011dc1-legacy", premium_pit_selection_version=None
    )
    with pytest.raises(DashboardBuildError, match="unsupported premium PIT selection version"):
        build_dashboard_snapshot(
            as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
        )


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
