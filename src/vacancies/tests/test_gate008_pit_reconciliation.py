from __future__ import annotations

from datetime import UTC, datetime, timedelta
from tempfile import TemporaryDirectory
from typing import Any

from django.test import TestCase

from collectors.pipeline import SharedCollectionPipeline
from collectors.platforms import FetchedPage, FetchRequest, ListingPage
from core.storage import RawObjectStore
from observations.models import Posting, PostingObservation
from sources.models import Source, SourceEndpoint
from vacancies.engine import run_deduplication, run_summary
from vacancies.evidence import select_posting_evidence
from vacancies.models import (
    DedupDecision,
    DedupReviewItem,
    DedupRunPostingAssignment,
    DedupRunVacancyState,
    PositionCountEvidence,
    Vacancy,
    VacancyEpisode,
    VacancyLifecycleEvent,
    VacancyMembershipEvent,
    VacancyPostingMembership,
)
from vacancies.review import resolve_review
from vacancies.tests.test_gate008 import Adapter, Clock, Fetcher


class EmptyAdapter(Adapter):
    def parse_listing_page(
        self, page: FetchedPage, request: FetchRequest, source: Source
    ) -> ListingPage:
        return ListingPage([], None, True, 0)


class Gate008PITReconciliationTests(TestCase):
    def source(self, source_id: str, source_type: str = "DIRECT_PUBLIC_EMPLOYER") -> Source:
        domain = f"{source_id.casefold().replace('_', '-')}.test"
        source = Source.objects.create(
            source_id=source_id,
            source_name=source_id,
            domain=domain,
            source_family="OFFICIAL",
            source_type=source_type,
            priority="P0",
            coverage_scope="test",
            canonicality="CANONICAL",
            platform_family="DEDUP_TEST",
            access_method="WEB",
            automation_status="COLLECTOR_CANDIDATE",
            legal_review_status="APPROVED",
            verification_status="VERIFIED",
            official_url=f"https://{domain}/",
        )
        SourceEndpoint.objects.create(
            source=source,
            endpoint_role="API",
            platform_family="DEDUP_TEST",
            scheme="https",
            host=domain,
            base_url=f"https://{domain}/",
        )
        return source

    def collect(self, source: Source, adapter: Adapter, when: datetime) -> PostingObservation:
        listing = f"https://{source.domain}/list"
        detail = f"https://{source.domain}/jobs/{adapter.posting_id}"
        pages = {
            listing: FetchedPage(listing, listing, 200, "application/json", b"listing"),
            detail: FetchedPage(detail, detail, 200, "application/json", b"detail"),
        }
        with TemporaryDirectory() as raw:
            SharedCollectionPipeline(
                source_id=source.pk,
                adapter=adapter,
                fetcher=Fetcher(pages),
                raw_store=RawObjectStore(raw),
                delay_seconds=0,
                clock=Clock(when),
            ).collect(posting_ids={adapter.posting_id})
        return PostingObservation.objects.get(
            source=source,
            source_posting_id=adapter.posting_id,
            observed_at=when,
        )

    def collect_empty(self, source: Source, when: datetime) -> None:
        listing = f"https://{source.domain}/list"
        pages = {listing: FetchedPage(listing, listing, 200, "application/json", b"empty")}
        with TemporaryDirectory() as raw:
            SharedCollectionPipeline(
                source_id=source.pk,
                adapter=EmptyAdapter("unused"),
                fetcher=Fetcher(pages),
                raw_store=RawObjectStore(raw),
                delay_seconds=0,
                clock=Clock(when),
            ).collect(full_snapshot=True)

    def close_posting(self, source: Source, opened: datetime) -> datetime:
        self.collect_empty(source, opened + timedelta(days=1))
        closed_at = opened + timedelta(days=3)
        self.collect_empty(source, closed_at)
        return closed_at

    @staticmethod
    def state_payload(run_id: object) -> list[tuple[object, ...]]:
        return list(
            DedupRunVacancyState.objects.filter(dedup_run_id=run_id)
            .order_by("run_vacancy_key")
            .values_list(
                "run_vacancy_key",
                "status",
                "canonical_posting_id",
                "first_seen_at",
                "last_seen_at",
                "closed_observed_at",
                "episode_number",
                "positions_count",
                "multi_hire_possible",
            )
        )

    def test_reverse_time_pit_and_historical_summary_stability(self) -> None:
        source = self.source("SRC-PIT-REVERSE")
        t1 = datetime(2026, 1, 1, tzinfo=UTC)
        t2 = t1 + timedelta(days=1)
        self.collect(source, Adapter("A"), t1)
        self.collect(source, Adapter("B"), t1)
        self.collect(source, Adapter("A", requisition="REQ-SHARED"), t2)
        self.collect(source, Adapter("B", requisition="REQ-SHARED"), t2)

        later_run, _ = run_deduplication(t2)
        assert run_summary(later_run)["effective_vacancies"] == 1
        earlier_run, _ = run_deduplication(t1)
        earlier_summary = run_summary(earlier_run)
        earlier_state = self.state_payload(earlier_run.pk)
        assert earlier_summary["effective_vacancies"] == 2
        assert DedupRunPostingAssignment.objects.filter(dedup_run=earlier_run).count() == 2

        assert run_summary(later_run)["effective_vacancies"] == 1
        assert run_summary(earlier_run) == earlier_summary
        assert self.state_payload(earlier_run.pk) == earlier_state

    def test_forward_time_run_state_remains_field_equivalent(self) -> None:
        source = self.source("SRC-PIT-FORWARD")
        t1 = datetime(2026, 2, 1, tzinfo=UTC)
        t2 = t1 + timedelta(days=1)
        self.collect(source, Adapter("A"), t1)
        self.collect(source, Adapter("B"), t1)
        earlier_run, _ = run_deduplication(t1)
        before = self.state_payload(earlier_run.pk)

        self.collect(source, Adapter("A", requisition="REQ-LATER"), t2)
        self.collect(source, Adapter("B", requisition="REQ-LATER"), t2)
        run_deduplication(t2)

        assert self.state_payload(earlier_run.pk) == before
        assert run_summary(earlier_run)["effective_vacancies"] == 2

    def test_lifecycle_event_changes_input_fingerprint_without_new_active(self) -> None:
        source = self.source("SRC-LIFECYCLE-FINGERPRINT")
        opened = datetime(2026, 3, 1, tzinfo=UTC)
        as_of = opened + timedelta(days=1)
        observation = self.collect(source, Adapter("A"), opened)
        first_run, _ = run_deduplication(as_of)

        self.collect_empty(source, as_of)
        second_run, reused = run_deduplication(as_of)

        assert not reused
        assert second_run.pk != first_run.pk
        assert second_run.input_fingerprint != first_run.input_fingerprint
        selected = select_posting_evidence(as_of)
        assert selected[0].observation_id == str(observation.pk)
        assert selected[0].lifecycle_events[-1]["event_type"] == "DISAPPEARED_PENDING"

    def test_historical_evidence_never_falls_back_to_current_projection(self) -> None:
        source = self.source("SRC-MUTABLE-STATUS")
        observed_at = datetime(2026, 4, 1, tzinfo=UTC)
        self.collect(source, Adapter("A"), observed_at)
        posting = Posting.objects.get(source=source, source_posting_id="A")
        posting.current_status = Posting.LifecycleStatus.CLOSED_OBSERVED
        posting.save(update_fields=["current_status", "updated_at"])

        selected = select_posting_evidence(observed_at)
        assert selected[0].lifecycle_status == "NEW"
        assert selected[0].lifecycle_status != "CLOSED_OBSERVED"

    def test_human_merge_reconciles_state_and_does_not_repeat_review(self) -> None:
        official = self.source("SRC-HUMAN-OFFICIAL")
        aggregator = self.source("SRC-HUMAN-AGG", "GENERAL_AGGREGATOR")
        when = datetime(2026, 5, 1, tzinfo=UTC)
        self.collect(
            official,
            Adapter("A", text="2 Mitarbeitende fuer Gruenpflege"),
            when,
        )
        self.collect(
            aggregator,
            Adapter("B", text="1 Mitarbeitende fuer Gruenpflege"),
            when,
        )
        run, _ = run_deduplication(when)
        historical_summary = run_summary(run)
        review = DedupReviewItem.objects.get(status=DedupReviewItem.Status.PENDING)
        assert Vacancy.objects.filter(merged_into__isnull=True).count() == 2
        assert VacancyEpisode.objects.count() == 2

        human = resolve_review(str(review.pk), merge=True, reason="Controlled same-vacancy fixture")
        review.refresh_from_db()
        effective = Vacancy.objects.get(merged_into__isnull=True)
        memberships = VacancyPostingMembership.objects.filter(vacancy=effective)
        episode = VacancyEpisode.objects.filter(vacancy=effective).get()
        assert memberships.count() == 2
        assert effective.canonical_posting is not None
        assert effective.canonical_posting.source == official
        assert episode.positions_count == 2
        assert PositionCountEvidence.objects.filter(vacancy_episode=episode).count() == 2
        assert DedupDecision.objects.filter(
            pk=review.algorithm_decision.pk,
            outcome=DedupDecision.Outcome.REVIEW,
        ).exists()
        assert human.method == DedupDecision.Method.HUMAN
        assert review.status == DedupReviewItem.Status.MERGED
        assert VacancyMembershipEvent.objects.filter(
            dedup_run=run,
            event_type=VacancyMembershipEvent.EventType.HUMAN_CONFIRM,
        ).exists()

        later_run, _ = run_deduplication(when + timedelta(seconds=1))
        assert later_run.review_pairs == 0
        assert not DedupReviewItem.objects.filter(status=DedupReviewItem.Status.PENDING).exists()
        assert run_summary(later_run)["effective_vacancies"] == 1
        assert run_summary(run) == historical_summary

    def test_human_keep_separate_does_not_repeat_for_identical_evidence(self) -> None:
        source = self.source("SRC-HUMAN-SEPARATE")
        when = datetime(2026, 5, 2, tzinfo=UTC)
        self.collect(source, Adapter("A"), when)
        self.collect(source, Adapter("B"), when)
        run_deduplication(when)
        review = DedupReviewItem.objects.get(status=DedupReviewItem.Status.PENDING)
        resolve_review(str(review.pk), merge=False, reason="Distinct assignments")

        later_run, _ = run_deduplication(when + timedelta(seconds=1))
        assert later_run.review_pairs == 0
        assert not DedupReviewItem.objects.filter(status=DedupReviewItem.Status.PENDING).exists()
        assert run_summary(later_run)["effective_vacancies"] == 2

    def _run_repost_case(self, *, gap_days: int, requisition: str | None) -> tuple[Vacancy, int]:
        source = self.source(f"SRC-REPOST-{gap_days}-{requisition or 'NONE'}")
        opened = datetime(2026, 1, 1, tzinfo=UTC)
        common: dict[str, Any] = {
            "title": "Gaertner Gartenunterhalt",
            "employer": "Stadt Test",
            "location": "Winterthur ZH",
            "text": "Pflege der Gruenanlagen",
            "employment_terms": "permanent",
            "requisition": requisition,
        }
        self.collect(source, Adapter("A", **common), opened)
        first_run, _ = run_deduplication(opened)
        original = Vacancy.objects.get(merged_into__isnull=True)
        original_id = original.pk
        closed_at = self.close_posting(source, opened)
        reappeared_at = closed_at + timedelta(days=gap_days)
        self.collect(source, Adapter("B", **common), reappeared_at)
        run_deduplication(reappeared_at)
        effective = Vacancy.objects.filter(merged_into__isnull=True)
        vacancy = effective.order_by("first_seen_at").first()
        assert vacancy is not None
        return vacancy, effective.count() if vacancy.pk == original_id else effective.count()

    def test_repost_new_id_within_90_days_creates_episode_two(self) -> None:
        vacancy, effective_count = self._run_repost_case(gap_days=45, requisition=None)
        assert effective_count == 1
        episode = VacancyEpisode.objects.get(vacancy=vacancy, episode_number=2)
        assert episode.reappearance_gap_days == 45
        assert VacancyLifecycleEvent.objects.filter(
            vacancy=vacancy,
            event_type=VacancyLifecycleEvent.EventType.REAPPEARED,
        ).exists()

    def test_repost_new_id_outside_90_days_creates_new_vacancy(self) -> None:
        _, effective_count = self._run_repost_case(gap_days=120, requisition=None)
        assert effective_count == 2
        assert VacancyEpisode.objects.filter(episode_number=1).count() == 2

    def test_same_requisition_outside_90_days_creates_episode_two(self) -> None:
        vacancy, effective_count = self._run_repost_case(gap_days=120, requisition="REQ-STABLE")
        assert effective_count == 1
        assert VacancyEpisode.objects.filter(
            vacancy=vacancy, episode_number=2, reappearance_gap_days=120
        ).exists()

    def test_official_source_upgrades_canonical_evidence(self) -> None:
        aggregator = self.source("SRC-UPGRADE-AGG", "GENERAL_AGGREGATOR")
        official = self.source("SRC-UPGRADE-OFFICIAL")
        day1 = datetime(2026, 6, 1, tzinfo=UTC)
        self.collect(aggregator, Adapter("A", requisition="REQ-UPGRADE"), day1)
        run_deduplication(day1)
        original = Vacancy.objects.get(merged_into__isnull=True)
        assert original.canonical_posting is not None
        assert original.canonical_posting.source == aggregator

        self.collect(
            official,
            Adapter("B", requisition="REQ-UPGRADE"),
            day1 + timedelta(days=1),
        )
        run_deduplication(day1 + timedelta(days=1))
        original.refresh_from_db()
        assert original.merged_into is None
        assert original.canonical_posting is not None
        assert original.canonical_posting.source == official
        assert Posting.objects.filter(source=aggregator, source_posting_id="A").exists()
        assert VacancyMembershipEvent.objects.filter(
            to_vacancy=original,
            event_type=VacancyMembershipEvent.EventType.CANONICAL_PROMOTE,
        ).exists()

    def test_stale_aggregator_does_not_keep_canonical_vacancy_open(self) -> None:
        aggregator = self.source("SRC-STALE-AGG", "GENERAL_AGGREGATOR")
        official = self.source("SRC-STALE-OFFICIAL")
        opened = datetime(2026, 7, 1, tzinfo=UTC)
        self.collect(aggregator, Adapter("A", requisition="REQ-CLOSE"), opened)
        self.collect(official, Adapter("B", requisition="REQ-CLOSE"), opened)
        run_deduplication(opened)
        vacancy = Vacancy.objects.get(merged_into__isnull=True)
        assert vacancy.canonical_posting is not None
        assert vacancy.canonical_posting.source == official

        closed_at = self.close_posting(official, opened)
        run_deduplication(closed_at)
        vacancy.refresh_from_db()
        assert Posting.objects.get(source=aggregator, source_posting_id="A").current_status in {
            Posting.LifecycleStatus.NEW,
            Posting.LifecycleStatus.STILL_ACTIVE,
        }
        assert vacancy.current_status == Vacancy.Status.CLOSED_OBSERVED
