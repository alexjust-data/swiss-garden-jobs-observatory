from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime, timedelta
from tempfile import TemporaryDirectory
from urllib.request import Request

import pytest
from django.test import TestCase

from collectors.adapters import RexxAdapter, ZurichCitySuccessFactorsLinkedAdapter, get_adapter
from collectors.governed_http import (
    GovernedHttpError,
    _AuthorizedRedirectHandler,
    ensure_default_endpoints,
    validate_authorized_url,
)
from collectors.pipeline import (
    CollectionPipelineError,
    SharedCollectionPipeline,
    publication_confidence,
)
from collectors.platforms import (
    FetchedPage,
    FetchRequest,
    ListingEntry,
    ListingPage,
    ParsedSourcePosting,
    UnsupportedPlatformError,
)
from core.hashing import sha256_hex
from core.models import RawArtifact
from core.storage import RawObjectStore
from observations.geospatial import GeospatialResolver
from observations.lifecycle import record_healthy_absences
from observations.models import (
    CollectionRun,
    CollectionRunFetch,
    GreenRelevanceAssessment,
    Posting,
    PostingLifecycleEvent,
    PostingObservation,
)
from observations.tests.test_winterthur_collector import detail_payload
from sources.models import Source, SourceEndpoint


class Clock:
    def __call__(self) -> datetime:
        return datetime(2026, 8, 8, 8, tzinfo=UTC)


class Fetcher:
    def __init__(self, pages: dict[str, FetchedPage]) -> None:
        self.pages, self.calls = pages, []

    def fetch(self, url: str) -> FetchedPage:
        self.calls.append(url)
        return self.pages[url]


class SyntheticAdapter:
    platform_family = "TEST_PLATFORM"

    def __init__(self, incomplete: bool = False) -> None:
        self.incomplete = incomplete

    def initial_listing_request(self, source: Source) -> FetchRequest:
        return FetchRequest("https://example.test/list/1", role="LISTING_PAGE")

    def parse_listing_page(
        self, page: FetchedPage, request: FetchRequest, source: Source
    ) -> ListingPage:
        if request.url.endswith("/1"):
            return ListingPage(
                [
                    ListingEntry("123", "https://example.test/jobs/123"),
                    ListingEntry("123", "https://example.test/jobs/123"),
                ],
                FetchRequest("https://example.test/list/2", role="LISTING_PAGE"),
                False,
                2,
            )
        if self.incomplete:
            return ListingPage([], None, False, 2)
        return ListingPage([ListingEntry("456", "https://example.test/jobs/456")], None, True, 2)

    def detail_request(self, entry: ListingEntry, source: Source) -> FetchRequest:
        return FetchRequest(entry.url, role="DETAIL")

    def parse_detail(
        self, page: FetchedPage, entry: ListingEntry, source: Source
    ) -> ParsedSourcePosting:
        return ParsedSourcePosting(
            entry.source_posting_id,
            entry.url,
            page.body.decode(),
            None,
            None,
            None,
            "",
            "Stadt",
            "Software role",
            "",
            "",
            "",
            "Unknown",
            "",
            "",
            "",
            "",
            "CH",
            {"title": page.body.decode()},
        )


class Gate007Tests(TestCase):
    def setUp(self) -> None:
        self.source = Source.objects.create(
            source_id="SRC-TEST-PLATFORM",
            source_name="Test",
            domain="example.test",
            source_family="OFFICIAL",
            source_type="DIRECT_PUBLIC_EMPLOYER",
            priority="P0",
            coverage_scope="test",
            canonicality="CANONICAL",
            platform_family="TEST_PLATFORM",
            access_method="WEB",
            automation_status="COLLECTOR_CANDIDATE",
            legal_review_status="APPROVED",
            verification_status="VERIFIED",
            official_url="https://example.test/",
        )
        SourceEndpoint.objects.create(
            source=self.source,
            endpoint_role="API",
            platform_family="TEST_PLATFORM",
            scheme="https",
            host="example.test",
            base_url="https://example.test/",
        )

    def pages(self) -> dict[str, FetchedPage]:
        values = {
            "https://example.test/list/1": b"page1",
            "https://example.test/list/2": b"page2",
            "https://example.test/jobs/123": b"Gaertner Gartenunterhalt",
            "https://example.test/jobs/456": b"IT Engineer",
        }
        return {url: FetchedPage(url, url, 200, "text/html", body) for url, body in values.items()}

    def pipeline(
        self, raw: str, adapter: SyntheticAdapter, fetcher: Fetcher | None = None
    ) -> SharedCollectionPipeline:
        return SharedCollectionPipeline(
            source_id=self.source.pk,
            adapter=adapter,
            fetcher=fetcher or Fetcher(self.pages()),
            raw_store=RawObjectStore(raw),
            delay_seconds=0,
            clock=Clock(),
        )

    def test_endpoint_security_and_unsupported_platform_fail_closed(self) -> None:
        validate_authorized_url(self.source, "https://example.test/jobs/1")
        with pytest.raises(GovernedHttpError):
            validate_authorized_url(self.source, "http://example.test/jobs/1")
        with pytest.raises(GovernedHttpError):
            validate_authorized_url(self.source, "https://external.test/jobs/1")
        with pytest.raises(UnsupportedPlatformError):
            get_adapter(self.source)

    def test_paginated_shared_pipeline_deduplicates_and_proves_complete_sets(self) -> None:
        with TemporaryDirectory() as raw:
            run = self.pipeline(raw, SyntheticAdapter()).collect(full_snapshot=True)
        assert run.snapshot_complete and run.listing_total_discovered == 2
        assert run.details_fetched == run.observations_created == run.green_assessments_created == 2
        assert (
            CollectionRunFetch.objects.filter(collection_run=run, fetch_role="LISTING_PAGE").count()
            == 2
        )
        ids = set(
            PostingObservation.objects.filter(
                collection_run=run, observation_status="ACTIVE"
            ).values_list("source_posting_id", flat=True)
        )
        assessed = set(
            GreenRelevanceAssessment.objects.filter(
                posting_observation__collection_run=run
            ).values_list("posting_observation__source_posting_id", flat=True)
        )
        assert ids == assessed == {"123", "456"}

    def test_incomplete_pagination_fails_without_negative_lifecycle(self) -> None:
        with TemporaryDirectory() as raw:
            with pytest.raises(CollectionPipelineError):
                self.pipeline(raw, SyntheticAdapter(True)).collect(full_snapshot=True)
        run = CollectionRun.objects.get()
        assert run.status == "FAILED" and run.snapshot_complete is False
        assert run.source_health_status == "OUTAGE"
        assert CollectionRunFetch.objects.count() == 2 and PostingObservation.objects.count() == 0

    def test_governance_blocks_before_network(self) -> None:
        self.source.legal_review_status = "AUTOMATION_REVIEW_REQUIRED"
        self.source.save()
        fetcher = Fetcher(self.pages())
        with TemporaryDirectory() as raw:
            with pytest.raises(CollectionPipelineError):
                self.pipeline(raw, SyntheticAdapter(), fetcher).collect(full_snapshot=True)
        assert fetcher.calls == []

    def test_source_identity_and_nullable_municipality_are_conservative(self) -> None:
        second = Source.objects.create(
            source_id="SRC-SECOND",
            source_name="Second",
            domain="second.test",
            source_family="OFFICIAL",
            source_type="DIRECT_PUBLIC_EMPLOYER",
            priority="P0",
            coverage_scope="test",
            canonicality="CANONICAL",
            platform_family="TEST_PLATFORM",
            access_method="WEB",
            automation_status="COLLECTOR_CANDIDATE",
            legal_review_status="APPROVED",
            verification_status="VERIFIED",
            official_url="https://second.test/",
        )
        now = Clock()()
        for source in (self.source, second):
            Posting.objects.create(
                source=source,
                source_posting_id="123",
                first_seen_at=now,
                last_seen_at=now,
                latest_canonical_url=f"https://{source.domain}/123",
            )
        assert Posting.objects.filter(source_posting_id="123").count() == 2
        Posting.objects.all().delete()
        with TemporaryDirectory() as raw:
            run = self.pipeline(raw, SyntheticAdapter()).collect(posting_ids={"456"})
            observation = PostingObservation.objects.get(
                collection_run=run, observation_status="ACTIVE"
            )
            assert observation.municipality is None
            resolution = GeospatialResolver(raw_store=RawObjectStore(raw)).resolve(observation)
        assert resolution.resolution_status == "UNRESOLVED" and resolution.municipality is None

    def test_adapters_emit_common_dto_without_database_writes(self) -> None:
        before_counts = (
            PostingObservation.objects.count(),
            Posting.objects.count(),
            GreenRelevanceAssessment.objects.count(),
            PostingLifecycleEvent.objects.count(),
        )
        rexx = RexxAdapter()
        rexx_source = Source(
            source_id="SRC-OFF-CITY-WINTERTHUR",
            source_name="Winterthur",
            platform_family="REXX_SYSTEMS",
        )
        rexx_request = rexx.initial_listing_request(rexx_source)
        rexx_listing_body = b'<a href="https://jobs.winterthur.ch/?yid=8280">Gardener</a>'
        rexx_listing = rexx.parse_listing_page(
            FetchedPage(
                rexx_request.url,
                rexx_request.url,
                200,
                "text/html",
                rexx_listing_body,
            ),
            rexx_request,
            rexx_source,
        )
        rexx_entry = rexx_listing.entries[0]
        parsed_rexx = rexx.parse_detail(
            FetchedPage(
                rexx_entry.url,
                rexx_entry.url,
                200,
                "text/html",
                detail_payload(),
            ),
            rexx_entry,
            rexx_source,
        )
        assert isinstance(parsed_rexx, ParsedSourcePosting)
        assert parsed_rexx.source_posting_id == "8280"
        assert parsed_rexx.published_at_parse_method == "STRUCTURED_DATA"
        adapter = ZurichCitySuccessFactorsLinkedAdapter()
        source = Source(
            source_id="SRC-OFF-CITY-ZURICH",
            source_name="Zurich",
            platform_family=adapter.platform_family,
        )
        request = adapter.initial_listing_request(source)
        payload = json.dumps(
            {
                "results": [
                    {
                        "href": (
                            "/de/politik-und-verwaltung/arbeiten-bei-der-stadt/jobs/"
                            "job-detailseite.61263.html"
                        ),
                        "heading": "Gaertner",
                        "meta": ["Gruen Stadt Zuerich", "7. August 2026"],
                    }
                ],
                "meta": {"total": 1},
            }
        ).encode()
        listing = adapter.parse_listing_page(
            FetchedPage(request.url, request.url, 200, "application/json", payload), request, source
        )
        html = (
            b"<link rel='canonical' href='https://www.stadt-zuerich.ch/de/politik-und-"
            b"verwaltung/arbeiten-bei-der-stadt/jobs/job-detailseite.61263.html'>"
            b"<stzh-heading slot='heading'>Gaertner</stzh-heading>"
            b"<stzh-text slot='lead'>Dauerstelle</stzh-text>"
            b"<stzh-text slot='lead'>Gruen Stadt Zuerich</stzh-text>"
            b"<p>Gartenunterhalt</p><h2>Aufgaben</h2><p>Gruenpflege</p>"
            b"<stzh-cta href='https://career2.successfactors.eu/career?"
            b"career_job_req_id=49697'></stzh-cta>"
        )
        parsed = adapter.parse_detail(
            FetchedPage(listing.entries[0].url, listing.entries[0].url, 200, "text/html", html),
            listing.entries[0],
            source,
        )
        assert isinstance(parsed, ParsedSourcePosting)
        assert (
            parsed.source_posting_id == "61263"
            and parsed.date_posted == datetime(2026, 8, 7).date()
        )
        assert parsed.structured_payload["successfactors_requisition_id"] == "49697"
        assert parsed.published_at_parse_method == "SOURCE_FIELD"
        after_counts = (
            PostingObservation.objects.count(),
            Posting.objects.count(),
            GreenRelevanceAssessment.objects.count(),
            PostingLifecycleEvent.objects.count(),
        )
        assert after_counts == before_counts

    def test_pipeline_has_one_non_replaceable_production_contract_builder(self) -> None:
        parameters = inspect.signature(SharedCollectionPipeline.__init__).parameters
        assert "contract_builder" not in parameters
        import collectors.winterthur as winterthur_module

        assert not hasattr(winterthur_module, "build_contract_payload")

    def test_unparsed_publication_evidence_has_no_confidence(self) -> None:
        parsed = ParsedSourcePosting(
            "bad-date",
            "https://example.test/jobs/bad-date",
            "Role",
            "not a valid date",
            None,
            None,
            "",
            "Employer",
            "Text",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "CH",
            {},
            published_at_precision="UNKNOWN",
            published_at_parse_method="MISSING",
        )
        assert publication_confidence(parsed) is None

    def test_endpoint_verification_provenance_is_populated_once(self) -> None:
        source = Source.objects.create(
            source_id="SRC-OFF-CITY-WINTERTHUR",
            source_name="Winterthur",
            domain="jobs.winterthur.ch",
            source_family="OFFICIAL",
            source_type="DIRECT_PUBLIC_EMPLOYER",
            priority="P0",
            coverage_scope="Winterthur",
            canonicality="CANONICAL",
            platform_family="REXX_SYSTEMS",
            access_method="WEB",
            automation_status="COLLECTOR_CANDIDATE",
            legal_review_status="APPROVED",
            verification_status="VERIFIED",
            official_url="https://jobs.winterthur.ch/",
        )
        ensure_default_endpoints(source)
        endpoint = SourceEndpoint.objects.filter(source=source).first()
        assert endpoint is not None and endpoint.verified_at is not None
        first_verified_at = endpoint.verified_at
        assert endpoint.evidence["verification"] == "GATE-007 live technical reconnaissance"
        ensure_default_endpoints(source)
        endpoint.refresh_from_db()
        assert endpoint.verified_at == first_verified_at

    def test_unauthorized_redirect_is_blocked_before_following(self) -> None:
        handler = _AuthorizedRedirectHandler(self.source)
        request = Request("https://example.test/path")
        with pytest.raises(GovernedHttpError):
            handler.redirect_request(
                request,
                None,
                302,
                "Found",
                {},
                "https://unauthorized.example/path",
            )
        with pytest.raises(GovernedHttpError):
            validate_authorized_url(self.source, "https://user:secret@example.test/path")

    def test_healthy_absence_is_lifecycle_isolated_by_source(self) -> None:
        now = Clock()()
        with TemporaryDirectory() as raw:
            active_run = self.pipeline(raw, SyntheticAdapter()).collect(posting_ids={"123"})
        source_a_posting = Posting.objects.get(source=self.source, source_posting_id="123")
        source_b = Source.objects.create(
            source_id="SRC-LIFECYCLE-B",
            source_name="Lifecycle B",
            domain="source-b.test",
            source_family="OFFICIAL",
            source_type="DIRECT_PUBLIC_EMPLOYER",
            priority="P0",
            coverage_scope="test",
            canonicality="CANONICAL",
            platform_family="TEST_PLATFORM",
            access_method="WEB",
            automation_status="COLLECTOR_CANDIDATE",
            legal_review_status="APPROVED",
            verification_status="VERIFIED",
            official_url="https://source-b.test/",
        )
        source_b_posting = Posting.objects.create(
            source=source_b,
            source_posting_id="123",
            first_seen_at=now,
            last_seen_at=now,
            latest_canonical_url="https://source-b.test/jobs/123",
        )
        before = (
            source_b_posting.first_negative_at,
            source_b_posting.last_negative_at,
            source_b_posting.negative_scan_count,
            source_b_posting.closed_observed_at,
            source_b_posting.current_status,
        )
        listing_body = b"empty healthy source-a listing"
        artifact = RawArtifact.objects.create(
            object_key="tests/gate007/source-a-empty-listing",
            sha256_digest=sha256_hex(listing_body),
            byte_size=len(listing_body),
            content_type="text/html",
        )
        absence_run = CollectionRun.objects.create(
            source=self.source,
            run_scope=CollectionRun.RunScope.FULL_SOURCE,
            source_health_status=CollectionRun.SourceHealthStatus.HEALTHY,
            listing_url="https://example.test/list/empty",
            listing_final_url="https://example.test/list/empty",
            listing_http_status=200,
            listing_raw_artifact=artifact,
            listing_total_discovered=0,
        )
        assert (
            record_healthy_absences(
                run=absence_run,
                active_ids=set(),
                observed_at=now + timedelta(days=1),
            )
            == 1
        )
        source_a_posting.refresh_from_db()
        source_b_posting.refresh_from_db()
        assert source_a_posting.current_status == Posting.LifecycleStatus.DISAPPEARED_PENDING
        after = (
            source_b_posting.first_negative_at,
            source_b_posting.last_negative_at,
            source_b_posting.negative_scan_count,
            source_b_posting.closed_observed_at,
            source_b_posting.current_status,
        )
        assert after == before
        assert active_run.source.pk == self.source.pk
