from __future__ import annotations

from datetime import UTC, datetime, timedelta
from tempfile import TemporaryDirectory

import pytest
from django.contrib import admin
from django.http import HttpRequest

from collectors.winterthur import (
    WINTERTHUR_LISTING_URL,
    FetchedPage,
    WinterthurCollector,
    WinterthurCollectorError,
)
from core.storage import RawObjectStore
from observations.admin import PostingAdmin
from observations.contracts import validate_posting_observation_contract
from observations.models import (
    CollectionRun,
    ImmutablePostingLifecycleEventError,
    Posting,
    PostingLifecycleEvent,
    PostingObservation,
)
from observations.tests.test_winterthur_collector import (
    FakeFetcher,
    WinterthurCollectorTests,
    detail_payload,
)


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def listing(*posting_ids: str) -> bytes:
    links = "".join(
        f'<a href="https://jobs.winterthur.ch/?yid={posting_id}">Role {posting_id}</a>'
        for posting_id in posting_ids
    )
    return f"<!doctype html>{links}".encode()


def fetcher_for(*posting_ids: str) -> FakeFetcher:
    listing_body = listing(*posting_ids)
    pages = {
        WINTERTHUR_LISTING_URL: FetchedPage(
            WINTERTHUR_LISTING_URL,
            WINTERTHUR_LISTING_URL,
            200,
            "text/html",
            listing_body,
        )
    }
    for posting_id in posting_ids:
        url = f"https://jobs.winterthur.ch/?yid={posting_id}"
        body = detail_payload().replace(b"8280", posting_id.encode())
        pages[url] = FetchedPage(url, url, 200, "text/html", body)
    return FakeFetcher(pages)


class FailingFetcher:
    def __init__(self, message: str) -> None:
        self.message = message

    def fetch(self, url: str) -> FetchedPage:
        raise WinterthurCollectorError(self.message)


class DetailFailingFetcher(FakeFetcher):
    def fetch(self, url: str) -> FetchedPage:
        if url != WINTERTHUR_LISTING_URL:
            raise WinterthurCollectorError("expected HTTP 200, found 429")
        return super().fetch(url)


class TemporalLifecycleTests(WinterthurCollectorTests):
    def run_full(
        self,
        raw_dir: str,
        observed_at: datetime,
        *posting_ids: str,
        fetcher: FakeFetcher | None = None,
    ) -> CollectionRun:
        return WinterthurCollector(
            fetcher=fetcher or fetcher_for(*posting_ids),
            raw_store=RawObjectStore(raw_dir),
            delay_seconds=0,
            clock=FixedClock(observed_at),
        ).collect(full_snapshot=True, acknowledge_automation_review=True)

    def test_active_replay_preserves_first_seen_and_advances_last_seen(self) -> None:
        first_at = datetime(2026, 8, 8, 8, tzinfo=UTC)
        second_at = first_at + timedelta(days=1)
        with TemporaryDirectory() as raw_dir:
            first_run = self.run_full(raw_dir, first_at, "8280")
            posting = Posting.objects.get(source_posting_id="8280")
            assert posting.current_status == Posting.LifecycleStatus.NEW
            assert posting.first_seen_at == posting.last_seen_at == first_at
            assert first_run.source_health_status == CollectionRun.SourceHealthStatus.HEALTHY

            self.run_full(raw_dir, second_at, "8280")
            posting.refresh_from_db()
            assert posting.current_status == Posting.LifecycleStatus.STILL_ACTIVE
            assert posting.first_seen_at == first_at
            assert posting.last_seen_at == second_at
            assert list(
                PostingLifecycleEvent.objects.filter(posting=posting).values_list(
                    "event_type", flat=True
                )
            ) == [
                PostingLifecycleEvent.EventType.NEW,
                PostingLifecycleEvent.EventType.STILL_ACTIVE,
            ]

    def test_two_healthy_negatives_at_least_48_hours_apart_close_posting(self) -> None:
        active_at = datetime(2026, 8, 8, 8, tzinfo=UTC)
        first_negative_at = active_at + timedelta(days=1)
        closing_at = first_negative_at + timedelta(hours=48)
        with TemporaryDirectory() as raw_dir:
            self.run_full(raw_dir, active_at, "8280")
            latest_active = PostingObservation.objects.get(
                source_posting_id="8280", observation_status="ACTIVE"
            )
            pending_run = self.run_full(raw_dir, first_negative_at, "9000")
            posting = Posting.objects.get(source_posting_id="8280")
            assert posting.current_status == Posting.LifecycleStatus.DISAPPEARED_PENDING
            assert posting.negative_scan_count == 1
            assert posting.closed_observed_at is None
            assert pending_run.negative_observations_created == 1
            negative = PostingObservation.objects.get(
                collection_run=pending_run, source_posting_id="8280"
            )
            assert negative.observation_status == "NOT_FOUND"
            validate_posting_observation_contract(negative.contract_payload)
            assert pending_run.listing_raw_artifact is not None
            assert negative.raw_artifact.pk == pending_run.listing_raw_artifact.pk
            contract = negative.contract_payload
            assert contract["source_url"] == pending_run.listing_final_url
            assert contract["canonical_url"] == negative.canonical_url
            assert contract["http_status"] == pending_run.listing_http_status
            assert contract["raw_payload_sha256"] == pending_run.listing_raw_artifact.sha256_digest
            event = PostingLifecycleEvent.objects.get(posting_observation=negative)
            assert event.evidence["absence_evidence_type"] == "FULL_SOURCE_LISTING_ABSENCE"
            assert event.evidence["listing_url"] == pending_run.listing_final_url
            assert event.evidence["listing_http_status"] == pending_run.listing_http_status
            assert (
                event.evidence["listing_raw_sha256"]
                == pending_run.listing_raw_artifact.sha256_digest
            )
            assert event.evidence["previous_active_observation_id"] == str(latest_active.pk)
            assert event.evidence["source_posting_id"] == "8280"
            assert event.evidence["listing_total_discovered"] == 1

            closing_run = self.run_full(raw_dir, closing_at, "9000")
            posting.refresh_from_db()
            assert posting.current_status == Posting.LifecycleStatus.CLOSED_OBSERVED
            assert posting.negative_scan_count == 2
            assert posting.closed_observed_at == closing_at
            assert closing_run.negative_observations_created == 1

    def test_negative_before_48_hours_does_not_close(self) -> None:
        active_at = datetime(2026, 8, 8, 8, tzinfo=UTC)
        with TemporaryDirectory() as raw_dir:
            self.run_full(raw_dir, active_at, "8280")
            self.run_full(raw_dir, active_at + timedelta(hours=1), "9000")
            self.run_full(raw_dir, active_at + timedelta(hours=47), "9000")
            posting = Posting.objects.get(source_posting_id="8280")
            assert posting.current_status == Posting.LifecycleStatus.DISAPPEARED_PENDING
            assert posting.negative_scan_count == 2
            assert posting.closed_observed_at is None

    def test_targeted_run_records_total_and_scope_without_negative_transition(self) -> None:
        observed_at = datetime(2026, 8, 8, 8, tzinfo=UTC)
        with TemporaryDirectory() as raw_dir:
            self.run_full(raw_dir, observed_at, "8280", "9000")
            run = WinterthurCollector(
                fetcher=fetcher_for("8280", "9000"),
                raw_store=RawObjectStore(raw_dir),
                delay_seconds=0,
                clock=FixedClock(observed_at + timedelta(days=1)),
            ).collect(posting_ids={"8280"}, acknowledge_automation_review=True)
            other = Posting.objects.get(source_posting_id="9000")
            assert run.listing_total_discovered == 2
            assert run.postings_in_scope == 1
            assert run.snapshot_complete is False
            assert run.negative_observations_created == 0
            assert other.current_status == Posting.LifecycleStatus.NEW

    def assert_listing_outage_never_advances_closure(self, message: str) -> None:
        observed_at = datetime(2026, 8, 8, 8, tzinfo=UTC)
        with TemporaryDirectory() as raw_dir:
            self.run_full(raw_dir, observed_at, "8280")
            collector = WinterthurCollector(
                fetcher=FailingFetcher(message),
                raw_store=RawObjectStore(raw_dir),
                delay_seconds=0,
                clock=FixedClock(observed_at + timedelta(days=3)),
            )
            with pytest.raises(WinterthurCollectorError):
                collector.collect(full_snapshot=True, acknowledge_automation_review=True)
            run = CollectionRun.objects.order_by("-started_at").first()
            posting = Posting.objects.get(source_posting_id="8280")
            assert run is not None
            assert run.source_health_status == CollectionRun.SourceHealthStatus.OUTAGE
            assert posting.current_status == Posting.LifecycleStatus.NEW
            assert posting.negative_scan_count == 0

    def test_http_403_never_advances_closure(self) -> None:
        self.assert_listing_outage_never_advances_closure("expected HTTP 200, found 403")

    def test_http_429_never_advances_closure(self) -> None:
        self.assert_listing_outage_never_advances_closure("expected HTTP 200, found 429")

    def test_captcha_never_advances_closure(self) -> None:
        self.assert_listing_outage_never_advances_closure("captcha")

    def test_detail_failure_is_degraded_and_preserves_prior_evidence(self) -> None:
        observed_at = datetime(2026, 8, 8, 8, tzinfo=UTC)
        with TemporaryDirectory() as raw_dir:
            self.run_full(raw_dir, observed_at, "8280")
            base = fetcher_for("9000")
            collector = WinterthurCollector(
                fetcher=DetailFailingFetcher(base.pages),
                raw_store=RawObjectStore(raw_dir),
                delay_seconds=0,
                clock=FixedClock(observed_at + timedelta(days=3)),
            )
            with pytest.raises(WinterthurCollectorError):
                collector.collect(full_snapshot=True, acknowledge_automation_review=True)
            run = CollectionRun.objects.order_by("-started_at").first()
            posting = Posting.objects.get(source_posting_id="8280")
            assert run is not None
            assert run.source_health_status == CollectionRun.SourceHealthStatus.DEGRADED
            assert run.snapshot_complete is False
            assert posting.current_status == Posting.LifecycleStatus.NEW
            assert PostingObservation.objects.filter(posting=posting).count() == 1

    def test_posting_admin_is_observational_only(self) -> None:
        model_admin = PostingAdmin(Posting, admin.site)
        request = HttpRequest()
        assert set(model_admin.readonly_fields) == {field.name for field in Posting._meta.fields}
        assert model_admin.has_add_permission(request) is False
        assert model_admin.has_change_permission(request) is False
        assert model_admin.has_delete_permission(request) is False

    def test_lifecycle_event_is_append_only(self) -> None:
        observed_at = datetime(2026, 8, 8, 8, tzinfo=UTC)
        with TemporaryDirectory() as raw_dir:
            self.run_full(raw_dir, observed_at, "8280")
            event = PostingLifecycleEvent.objects.get()
            event.event_type = PostingLifecycleEvent.EventType.CLOSED_OBSERVED
            with pytest.raises(ImmutablePostingLifecycleEventError):
                event.save()
            with pytest.raises(ImmutablePostingLifecycleEventError):
                PostingLifecycleEvent.objects.filter(pk=event.pk).update(
                    event_type=PostingLifecycleEvent.EventType.CLOSED_OBSERVED
                )
            with pytest.raises(ImmutablePostingLifecycleEventError):
                PostingLifecycleEvent.objects.filter(pk=event.pk).delete()
            with pytest.raises(ImmutablePostingLifecycleEventError):
                PostingLifecycleEvent.objects.bulk_update([event], ["event_type"])
