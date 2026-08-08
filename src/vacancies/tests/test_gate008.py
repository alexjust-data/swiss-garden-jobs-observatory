from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from tempfile import TemporaryDirectory

import pytest
from django.contrib import admin
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.test import TestCase

from collectors.pipeline import SharedCollectionPipeline
from collectors.platforms import (
    FetchedPage,
    FetchRequest,
    ListingEntry,
    ListingPage,
    ParsedSourcePosting,
)
from core.storage import RawObjectStore
from observations.models import Posting, PostingObservation
from sources.models import Source, SourceEndpoint
from vacancies.admin import ReadOnlyAdmin
from vacancies.engine import canonical_pair, qualifies_as_repost, run_deduplication
from vacancies.evidence import PostingEvidence, select_posting_evidence
from vacancies.models import (
    DedupDecision,
    DedupReviewItem,
    ImmutableVacancyEvidenceError,
    PositionCountEvidence,
    Vacancy,
    VacancyEpisode,
    VacancyLifecycleEvent,
    VacancyPostingMembership,
)
from vacancies.normalizer import (
    DEDUP_VERSION,
    extract_explicit_requisition,
    normalize_text,
    normalize_url,
)
from vacancies.positions import extract_position_count
from vacancies.precedence import source_precedence_rank
from vacancies.review import resolve_review
from vacancies.scoring import WEIGHTS, assess_pair, outcome_for_score


class Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class Fetcher:
    def __init__(self, pages: dict[str, FetchedPage]) -> None:
        self.pages = pages

    def fetch(self, url: str) -> FetchedPage:
        return self.pages[url]


class Adapter:
    platform_family = "DEDUP_TEST"

    def __init__(
        self,
        posting_id: str,
        *,
        title: str = "Gaertner Gartenunterhalt",
        employer: str = "Stadt Test",
        location: str = "Winterthur ZH",
        text: str = "Pflege der Gruenanlagen",
        requisition: str | None = None,
    ) -> None:
        self.posting_id = posting_id
        self.title = title
        self.employer = employer
        self.location = location
        self.text = text
        self.requisition = requisition

    def initial_listing_request(self, source: Source) -> FetchRequest:
        return FetchRequest(f"https://{source.domain}/list", role="LISTING")

    def parse_listing_page(
        self, page: FetchedPage, request: FetchRequest, source: Source
    ) -> ListingPage:
        return ListingPage(
            [ListingEntry(self.posting_id, f"https://{source.domain}/jobs/{self.posting_id}")],
            None,
            True,
            1,
        )

    def detail_request(self, entry: ListingEntry, source: Source) -> FetchRequest:
        return FetchRequest(entry.url, role="DETAIL")

    def parse_detail(
        self, page: FetchedPage, entry: ListingEntry, source: Source
    ) -> ParsedSourcePosting:
        structured: dict[str, object] = {
            "description": self.text,
            "hiring_organization": self.employer,
            "location_raw": self.location,
        }
        if self.requisition:
            structured["requisition_id"] = self.requisition
        return ParsedSourcePosting(
            self.posting_id,
            entry.url,
            self.title,
            None,
            None,
            None,
            "",
            self.employer,
            self.text,
            "",
            "",
            "",
            self.location,
            "",
            "",
            "ZH",
            "",
            "CH",
            structured,
            published_at_precision="UNKNOWN",
            published_at_parse_method="MISSING",
        )


def evidence(
    posting_id: str,
    *,
    source_id: str = "SRC-A",
    title: str = "Greenkeeper",
    employer: str = "Stadt Zuerich",
    location: str = "Zuerich ZH",
    text: str = "Rasenpflege Sportanlage",
    requisition: str | None = None,
    url: str | None = None,
    first_seen: datetime | None = None,
) -> PostingEvidence:
    now = first_seen or datetime(2026, 8, 8, tzinfo=UTC)
    return PostingEvidence(
        posting_id=posting_id,
        observation_id=f"obs-{posting_id}",
        source_id=source_id,
        source_posting_id=posting_id,
        observed_at=now,
        first_seen_at=now,
        lifecycle_status="NEW",
        title=title,
        employer=employer,
        text=text,
        location=location,
        canonical_url=url or f"https://example.test/jobs/{posting_id}",
        redirect_target=None,
        requisition_id=requisition,
        requisition_provenance="requisition_id" if requisition else None,
        pensum_contract_start="",
    )


class Gate008Tests(TestCase):
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
            source=source, observed_at=when, source_posting_id=adapter.posting_id
        )

    def test_normalization_url_identity_and_explicit_requisition(self) -> None:
        assert normalize_text("  Stadt   Zuerich ") == normalize_text("stadt zuerich")
        assert normalize_url("https://example.ch/job/123?utm_source=x") == normalize_url(
            "https://example.ch/job/123?utm_campaign=y"
        )
        assert normalize_url("https://example.ch/job?id=123") != normalize_url(
            "https://example.ch/job?id=456"
        )
        assert extract_explicit_requisition({"jobReqId": "REQ-1"}) == ("REQ-1", "jobReqId")
        assert extract_explicit_requisition({"description": "Reference 12345"}) == (None, None)

    def test_frozen_weights_threshold_boundaries_and_missing_evidence(self) -> None:
        assert sum(WEIGHTS.values()) == Decimal("1.00")
        assert outcome_for_score(Decimal("0.8999")) == "REVIEW"
        assert outcome_for_score(Decimal("0.90")) == "AUTO_MERGE"
        assert outcome_for_score(Decimal("0.7799")) == "KEEP_SEPARATE"
        assert outcome_for_score(Decimal("0.78")) == "REVIEW"
        result = assess_pair(evidence("a", location=""), evidence("b", location=""))
        assert result.feature_scores["location"] == "0"

    def test_hard_barriers_override_title_and_template_similarity(self) -> None:
        requisition = assess_pair(
            evidence("a", requisition="REQ-100"), evidence("b", requisition="REQ-101")
        )
        assert requisition.outcome == "KEEP_SEPARATE"
        assert requisition.hard_barriers[0]["type"] == "DISTINCT_REQUISITION_IDS"
        location = assess_pair(
            evidence("a", location="Basel BS"), evidence("b", location="Zuerich ZH")
        )
        assert location.outcome == "KEEP_SEPARATE"
        ett = assess_pair(
            evidence("a", employer="Agency", location="Basel BS", text="Generic template"),
            evidence("b", employer="Agency", location="Zuerich ZH", text="Generic template"),
        )
        assert ett.outcome == "KEEP_SEPARATE"

    def test_position_extraction_is_conservative(self) -> None:
        assert extract_position_count("80-100 %").positions_count is None
        assert extract_position_count("ab 1. August").positions_count is None
        assert extract_position_count("2 Mitarbeitende gesucht").positions_count == 2
        assert extract_position_count("zwei Teams").positions_count is None
        plural = extract_position_count("mehrere Mitarbeitende gesucht")
        assert plural.positions_count is None and plural.multi_hire_possible

    def test_repost_window_and_stable_requisition_rules(self) -> None:
        closed = datetime(2026, 1, 1, tzinfo=UTC)
        assert qualifies_as_repost(
            closed, closed + timedelta(days=45), same_requisition=False, score=Decimal("0.90")
        )
        assert not qualifies_as_repost(
            closed, closed + timedelta(days=120), same_requisition=False, score=Decimal("0.99")
        )
        assert qualifies_as_repost(
            closed, closed + timedelta(days=120), same_requisition=True, score=Decimal("0")
        )

    def test_pair_order_is_canonical(self) -> None:
        left, right = canonical_pair(evidence("b"), evidence("a"))
        assert (left.posting_id, right.posting_id) == ("a", "b")

    def test_pit_selection_does_not_leak_future_requisition(self) -> None:
        source = self.source("SRC-PIT")
        t1 = datetime(2026, 8, 1, tzinfo=UTC)
        t2 = t1 + timedelta(days=1)
        self.collect(source, Adapter("1"), t1)
        self.collect(source, Adapter("1", requisition="REQ-FUTURE"), t2)
        at_t1 = select_posting_evidence(t1)
        at_t2 = select_posting_evidence(t2)
        assert at_t1[0].requisition_id is None
        assert at_t2[0].requisition_id == "REQ-FUTURE"

    def test_official_and_aggregator_merge_without_losing_postings_and_idempotency(self) -> None:
        official = self.source("SRC-OFFICIAL")
        aggregator = self.source("SRC-AGGREGATOR", "GENERAL_AGGREGATOR")
        when = datetime(2026, 8, 8, tzinfo=UTC)
        self.collect(aggregator, Adapter("A", requisition="REQ-42"), when)
        self.collect(official, Adapter("B", requisition="REQ-42"), when)
        source_counts = (Posting.objects.count(), PostingObservation.objects.count())
        run, reused = run_deduplication(when)
        assert not reused and run.hard_key_merges == 1
        effective = Vacancy.objects.get(identity_version=DEDUP_VERSION, merged_into__isnull=True)
        assert VacancyPostingMembership.objects.filter(vacancy=effective).count() == 2
        assert effective.canonical_posting is not None
        assert effective.canonical_posting.source == official
        assert (Posting.objects.count(), PostingObservation.objects.count()) == source_counts
        counts = (
            Vacancy.objects.count(),
            VacancyPostingMembership.objects.count(),
            VacancyEpisode.objects.count(),
            PositionCountEvidence.objects.count(),
            DedupReviewItem.objects.count(),
        )
        same_run, reused = run_deduplication(when)
        assert reused and same_run.pk == run.pk
        assert counts == (
            Vacancy.objects.count(),
            VacancyPostingMembership.objects.count(),
            VacancyEpisode.objects.count(),
            PositionCountEvidence.objects.count(),
            DedupReviewItem.objects.count(),
        )

    def test_review_is_not_merged_until_audited_human_resolution(self) -> None:
        source = self.source("SRC-REVIEW")
        when = datetime(2026, 8, 8, tzinfo=UTC)
        self.collect(source, Adapter("A"), when)
        self.collect(source, Adapter("B"), when)
        run, _ = run_deduplication(when)
        review = DedupReviewItem.objects.get(status=DedupReviewItem.Status.PENDING)
        assert run.review_pairs == 1
        assert Vacancy.objects.filter(merged_into__isnull=True).count() == 2
        algorithm_id = review.algorithm_decision.pk
        human = resolve_review(
            str(review.pk), merge=False, reason="Different operational assignments"
        )
        review.refresh_from_db()
        assert review.status == DedupReviewItem.Status.KEPT_SEPARATE
        assert human.method == DedupDecision.Method.HUMAN
        assert DedupDecision.objects.filter(pk=algorithm_id).exists()

    def test_append_only_evidence_and_read_only_admin(self) -> None:
        source = self.source("SRC-IMMUTABLE")
        when = datetime(2026, 8, 8, tzinfo=UTC)
        self.collect(source, Adapter("A"), when)
        self.collect(source, Adapter("B"), when)
        run_deduplication(when)
        decision = DedupDecision.objects.get()
        decision.outcome = DedupDecision.Outcome.KEEP_SEPARATE
        with pytest.raises(ImmutableVacancyEvidenceError):
            decision.save()
        with pytest.raises(ImmutableVacancyEvidenceError):
            DedupDecision.objects.filter(pk=decision.pk).update(outcome="KEEP_SEPARATE")
        with pytest.raises(ImmutableVacancyEvidenceError):
            DedupDecision.objects.filter(pk=decision.pk).delete()
        with pytest.raises(ImmutableVacancyEvidenceError):
            DedupDecision.objects.bulk_update([decision], ["outcome"])
        model_admin = ReadOnlyAdmin(Vacancy, admin.site)
        request = HttpRequest()
        assert model_admin.has_add_permission(request) is False
        assert model_admin.has_change_permission(request) is False
        assert model_admin.has_delete_permission(request) is False

    def test_database_rejects_zero_position_count(self) -> None:
        source = self.source("SRC-CONSTRAINT")
        when = datetime(2026, 8, 8, tzinfo=UTC)
        self.collect(source, Adapter("A"), when)
        run_deduplication(when)
        vacancy = Vacancy.objects.get(merged_into__isnull=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            VacancyEpisode.objects.create(
                vacancy=vacancy,
                episode_number=2,
                opened_observed_at=when,
                last_seen_at=when,
                positions_count=0,
            )

    def test_source_precedence_is_explicit(self) -> None:
        official = self.source("SRC-PRECEDENCE-OFFICIAL")
        aggregator = self.source("SRC-PRECEDENCE-AGG", "GENERAL_AGGREGATOR")
        assert source_precedence_rank(official) < source_precedence_rank(aggregator)

    def test_same_posting_reappearance_creates_one_new_episode(self) -> None:
        source = self.source("SRC-REAPPEAR")
        opened = datetime(2026, 1, 1, tzinfo=UTC)
        self.collect(source, Adapter("A"), opened)

        class EmptyAdapter(Adapter):
            def parse_listing_page(
                self, page: FetchedPage, request: FetchRequest, source: Source
            ) -> ListingPage:
                return ListingPage([], None, True, 0)

        def collect_empty(when: datetime) -> None:
            listing_url = f"https://{source.domain}/list"
            pages = {
                listing_url: FetchedPage(
                    listing_url, listing_url, 200, "application/json", b"empty"
                )
            }
            with TemporaryDirectory() as raw:
                SharedCollectionPipeline(
                    source_id=source.pk,
                    adapter=EmptyAdapter("unused"),
                    fetcher=Fetcher(pages),
                    raw_store=RawObjectStore(raw),
                    delay_seconds=0,
                    clock=Clock(when),
                ).collect(full_snapshot=True)

        collect_empty(opened + timedelta(days=1))
        closed_at = opened + timedelta(days=3)
        collect_empty(closed_at)
        run_deduplication(closed_at)
        vacancy = Vacancy.objects.get(merged_into__isnull=True)
        assert vacancy.current_status == Vacancy.Status.CLOSED_OBSERVED
        assert VacancyEpisode.objects.filter(vacancy=vacancy).count() == 1

        reappeared_at = opened + timedelta(days=4)
        self.collect(source, Adapter("A"), reappeared_at)
        run_deduplication(reappeared_at)
        vacancy.refresh_from_db()
        assert vacancy.current_status == Vacancy.Status.ACTIVE
        assert VacancyEpisode.objects.filter(vacancy=vacancy).count() == 2
        assert (
            VacancyLifecycleEvent.objects.filter(
                vacancy=vacancy,
                event_type=VacancyLifecycleEvent.EventType.REAPPEARED,
            ).count()
            == 1
        )

        run_deduplication(reappeared_at + timedelta(seconds=1))
        assert VacancyEpisode.objects.filter(vacancy=vacancy).count() == 2
