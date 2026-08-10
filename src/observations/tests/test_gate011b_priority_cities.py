from __future__ import annotations

import json
from datetime import UTC, datetime
from tempfile import TemporaryDirectory

import pytest
from django.test import TestCase

from collectors.adapters import get_adapter
from collectors.governed_http import GovernedHttpClient, GovernedHttpError, ensure_default_endpoints
from collectors.pipeline import SharedCollectionPipeline, SourceGovernanceError
from collectors.platforms import (
    FetchedPage,
    FetchRequest,
    ListingEntry,
    ParsedSourcePosting,
    PlatformAdapterError,
    UnsupportedPlatformError,
)
from collectors.priority_city_adapters import (
    BERN_API,
    SCHAFFHAUSEN_LISTING,
    BernProspectiveApiAdapter,
    LuzernProspectiveLegacyAdapter,
    SchaffhausenUmantisLinkedAdapter,
    _ProspectiveAdapterBase,
)
from core.storage import RawObjectStore
from observations.models import (
    CollectionRunFetch,
    GreenRelevanceAssessment,
    Posting,
    PostingLifecycleEvent,
    PostingObservation,
)
from sources.models import Source, SourceEndpoint


def make_source(source_id: str, platform: str, domain: str) -> Source:
    return Source.objects.create(
        source_id=source_id,
        source_name=source_id,
        domain=domain,
        source_family="OFFICIAL_MUNICIPAL",
        source_type="DIRECT_PUBLIC_EMPLOYER",
        priority="P0",
        coverage_scope="city",
        canonicality="CANONICAL",
        platform_family=platform,
        access_method="WEB",
        automation_status="COLLECTOR_CANDIDATE",
        legal_review_status="AUTOMATION_REVIEW_REQUIRED",
        verification_status="VERIFIED",
        official_url=f"https://{domain}/",
    )


def job_posting_html(
    title: str,
    *,
    date_posted: str = "2026-08-10",
    locality: str = "",
    region: str = "",
    canonical: str = "",
) -> bytes:
    payload = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": title,
        "datePosted": date_posted,
        "validThrough": "2026-09-10",
        "employmentType": "FULL_TIME",
        "hiringOrganization": {"name": "City"},
        "description": "Garden care",
        "responsibilities": "Maintain green spaces",
        "qualifications": "EFZ",
        "jobBenefits": "Five weeks",
        "jobLocation": {
            "address": {
                "streetAddress": "Parkstrasse 1" if locality else "",
                "postalCode": "3000" if locality else "",
                "addressLocality": locality,
                "addressRegion": region,
                "addressCountry": "CH",
            }
        },
    }
    canonical_tag = f'<link rel="canonical" href="{canonical}">' if canonical else ""
    return (
        canonical_tag + '<script type="application/ld+json">' + json.dumps(payload) + "</script>"
    ).encode()


def bern_job(detail_url: str) -> dict[str, object]:
    return {
        "id": 101,
        "title": "Gaertner*in",
        "links": {"directlink": detail_url},
        "start_date": "2026-08-10T08:00:00Z",
        "last_modification_timestamp": "2026-08-10T09:00:00Z",
    }


class Fetcher:
    def __init__(self, pages: dict[tuple[str, str], FetchedPage]) -> None:
        self.pages = pages
        self.requests: list[FetchRequest] = []

    def fetch(self, url: str) -> FetchedPage:
        request = FetchRequest(url)
        self.requests.append(request)
        return self.pages[("GET", url)]

    def fetch_request(self, request: FetchRequest) -> FetchedPage:
        self.requests.append(request)
        return self.pages[(request.method, request.url)]


class Gate011BTests(TestCase):
    def test_bern_api_pagination_detail_and_source_field_provenance(self) -> None:
        adapter = BernProspectiveApiAdapter()
        registered = Source(source_id="SRC-OFF-CITY-BERN", platform_family=adapter.platform_family)
        request = adapter.initial_listing_request(registered)
        detail_url = "https://jobs.bern.ch/offene-stellen/gaertner/uuid-1"
        payload = {"total": 2, "jobs": [bern_job(detail_url)]}
        listing = adapter.parse_listing_page(
            FetchedPage(
                request.url, request.url, 200, "application/json", json.dumps(payload).encode()
            ),
            request,
            registered,
        )
        assert listing.next_request is not None and "offset=1" in listing.next_request.url
        entry = listing.entries[0]
        parsed = adapter.parse_detail(
            FetchedPage(
                entry.url,
                entry.url,
                200,
                "text/html",
                job_posting_html("Gaertner*in", locality="Bern", region="BE", canonical=entry.url),
            ),
            entry,
            registered,
        )
        assert isinstance(parsed, ParsedSourcePosting)
        assert parsed.source_posting_id == "101"
        assert parsed.published_at_parse_method == "SOURCE_FIELD"
        assert parsed.published_at_precision == "EXACT_DATETIME"
        assert parsed.source_updated_at == datetime(2026, 8, 10, 9, tzinfo=UTC)
        assert parsed.location_locality == "Bern"

    def test_luzern_post_pagination_and_json_ld_detail(self) -> None:
        adapter = LuzernProspectiveLegacyAdapter()
        registered = Source(
            source_id="SRC-OFF-CITY-LUZERN", platform_family=adapter.platform_family
        )
        request = adapter.initial_listing_request(registered)
        detail_url = "https://job.stadtluzern.ch/stellen/stadtluzern/offene-stellen/g/uuid"
        body = f"""
        <a id="job-101" href="{detail_url}" title="Gaertner*in"><h3>Gaertner*in</h3></a>
        <a id="button-forward" class="next" onclick="sendPagination(25);return false;"></a>
        """.encode()
        listing = adapter.parse_listing_page(
            FetchedPage(request.url, request.url, 200, "text/html", body), request, registered
        )
        assert listing.next_request is not None
        assert listing.next_request.method == "POST"
        assert ("offset", "25") in listing.next_request.form_data
        assert "filter_10" not in request.url
        assert all(key != "filter_10" for key, _ in listing.next_request.form_data)
        parsed = adapter.parse_detail(
            FetchedPage(
                detail_url,
                detail_url,
                200,
                "text/html",
                job_posting_html(
                    "Gaertner*in - Eintritt: 1.12.2026",
                    locality="Luzern",
                    region="LU",
                    canonical=detail_url,
                ),
            ),
            listing.entries[0],
            registered,
        )
        assert parsed.published_at_parse_method == "STRUCTURED_DATA"
        assert parsed.location_locality == "Luzern"

    def test_full_source_luzern_includes_ordinary_and_apprenticeship(self) -> None:
        registered = make_source("SRC-OFF-CITY-LUZERN", "CITY_LUZERN_PORTAL", "stadtluzern.ch")
        adapter = get_adapter(registered)
        listing_request = adapter.initial_listing_request(registered)
        ordinary_url = (
            "https://job.stadtluzern.ch/stellen/stadtluzern/offene-stellen/"
            "sachbearbeiter-in/ordinary"
        )
        apprenticeship_url = (
            "https://job.stadtluzern.ch/stellen/stadtluzern/offene-stellen/"
            "lehrstelle-gaertner-in/apprenticeship"
        )
        listing_body = f"""
        <a id="job-201" href="{ordinary_url}" title="Sachbearbeiter*in">
          <h3>Sachbearbeiter*in</h3>
        </a>
        <a id="job-202" href="{apprenticeship_url}" title="Lehrstelle Gärtner*in">
          <h3>Lehrstelle Gärtner*in</h3>
        </a>
        """.encode()
        pages = {
            ("GET", listing_request.url): FetchedPage(
                listing_request.url,
                listing_request.url,
                200,
                "text/html",
                listing_body,
            ),
            ("GET", ordinary_url): FetchedPage(
                ordinary_url,
                ordinary_url,
                200,
                "text/html",
                job_posting_html("Sachbearbeiter*in", canonical=ordinary_url),
            ),
            ("GET", apprenticeship_url): FetchedPage(
                apprenticeship_url,
                apprenticeship_url,
                200,
                "text/html",
                job_posting_html("Lehrstelle Gärtner*in", canonical=apprenticeship_url),
            ),
        }
        with TemporaryDirectory() as raw:
            run = SharedCollectionPipeline(
                source_id=registered.pk,
                fetcher=Fetcher(pages),
                raw_store=RawObjectStore(raw),
                delay_seconds=0,
                clock=lambda: datetime(2026, 8, 10, 12, tzinfo=UTC),
            ).collect(full_snapshot=True, acknowledge_automation_review=True)
        observations = PostingObservation.objects.filter(collection_run=run)
        assessments = GreenRelevanceAssessment.objects.filter(
            posting_observation__collection_run=run
        )
        assert run.snapshot_complete and run.listing_total_discovered == 2
        assert set(observations.values_list("source_posting_id", flat=True)) == {"201", "202"}
        assert observations.count() == assessments.count() == 2
        assert (
            assessments.get(posting_observation__source_posting_id="202").result
            == "GREEN_CONFIRMED"
        )

    def test_schaffhausen_uses_local_mirror_and_explicit_exhaustion(self) -> None:
        adapter = SchaffhausenUmantisLinkedAdapter()
        registered = Source(
            source_id="SRC-OFF-CITY-SCHAFFHAUSEN", platform_family=adapter.platform_family
        )
        index_request = adapter.initial_listing_request(registered)
        mirror = "https://jobs.stadt-schaffhausen.ch/jobs/gaertnerin-gaertner-5158/"
        index = json.dumps(
            [{"id": 6564, "slug": "gaertnerin-gaertner-5158", "link": mirror}]
        ).encode()
        index_page = adapter.parse_listing_page(
            FetchedPage(index_request.url, index_request.url, 200, "application/json", index),
            index_request,
            registered,
        )
        assert index_page.next_request is not None
        listing_body = b"""
        <div>Den Filterkriterien entsprechende Inserate: 1</div>
        <a href="https://recruitingapp-2808.umantis.com/Vacancies/5158/Description/1"
           class="job-post"><h2>Gaertnerin/Gaertner</h2><span>City metadata</span></a>
        """
        listing = adapter.parse_listing_page(
            FetchedPage(
                SCHAFFHAUSEN_LISTING,
                SCHAFFHAUSEN_LISTING,
                200,
                "text/html",
                listing_body,
            ),
            index_page.next_request,
            registered,
        )
        assert listing.discovery_complete and listing.total_reported == 1
        assert listing.entries[0].url == mirror
        assert listing.entries[0].title == "Gaertnerin/Gaertner"
        assert "umantis.com" in str(listing.entries[0].listing_metadata["observed_listing_url"])
        detail_request = adapter.detail_request(listing.entries[0], registered)
        assert detail_request.url.endswith("/wp-json/wp/v2/jobs/6564")
        rest_payload = {
            "id": 6564,
            "slug": "gaertnerin-gaertner-5158",
            "link": mirror,
            "title": {"rendered": "Gaertnerin/Gaertner"},
            "excerpt": {"rendered": "<p>(80 %)</p>"},
            "date": "2026-08-10T09:10:03",
            "modified": "2026-08-10T10:10:03",
        }
        parsed = adapter.parse_detail(
            FetchedPage(
                detail_request.url,
                detail_request.url,
                200,
                "application/json",
                json.dumps(rest_payload).encode(),
            ),
            listing.entries[0],
            registered,
        )
        assert parsed.date_posted is not None
        assert parsed.date_posted.isoformat() == "2026-08-10"
        assert parsed.location_locality == ""

    def test_schaffhausen_duplicate_ids_share_one_local_detail_identity(self) -> None:
        adapter = SchaffhausenUmantisLinkedAdapter()
        registered = Source(platform_family=adapter.platform_family)
        request = adapter.initial_listing_request(registered)
        mirror = "https://jobs.stadt-schaffhausen.ch/jobs/gaertner-5158/"
        index_page = adapter.parse_listing_page(
            FetchedPage(
                request.url,
                request.url,
                200,
                "application/json",
                json.dumps([{"id": 6564, "slug": "gaertner-5158", "link": mirror}]).encode(),
            ),
            request,
            registered,
        )
        assert index_page.next_request is not None
        body = f"""
        <div>Inserate: 1</div>
        <a class="job-post" href="{mirror}"><h2>Gaertner</h2></a>
        <a class="job-post" href="https://recruitingapp-2808.umantis.com/Vacancies/5158/Description/1"><h2>Gaertner</h2></a>
        """.encode()
        listing = adapter.parse_listing_page(
            FetchedPage(SCHAFFHAUSEN_LISTING, SCHAFFHAUSEN_LISTING, 200, "text/html", body),
            index_page.next_request,
            registered,
        )
        assert {entry.source_posting_id for entry in listing.entries} == {"5158"}
        assert {entry.detail_url for entry in listing.entries} == {mirror}

    def test_full_source_bern_uses_shared_pipeline_and_request_evidence(self) -> None:
        registered = make_source("SRC-OFF-CITY-BERN", "JOBS_BERN_CH", "bern.ch")
        adapter = get_adapter(registered)
        listing_request = adapter.initial_listing_request(registered)
        detail_url = "https://jobs.bern.ch/offene-stellen/gaertner/uuid-1"
        listing = json.dumps({"total": 1, "jobs": [bern_job(detail_url)]}).encode()
        pages = {
            ("GET", listing_request.url): FetchedPage(
                listing_request.url,
                listing_request.url,
                200,
                "application/json",
                listing,
            ),
            ("GET", detail_url): FetchedPage(
                detail_url,
                detail_url,
                200,
                "text/html",
                job_posting_html("Gaertner*in", canonical=detail_url),
            ),
        }
        with TemporaryDirectory() as raw:
            run = SharedCollectionPipeline(
                source_id=registered.pk,
                fetcher=Fetcher(pages),
                raw_store=RawObjectStore(raw),
                delay_seconds=0,
                clock=lambda: datetime(2026, 8, 10, 12, tzinfo=UTC),
            ).collect(full_snapshot=True, acknowledge_automation_review=True)
        assert run.snapshot_complete
        assert run.details_fetched == run.observations_created == run.green_assessments_created == 1
        assert PostingObservation.objects.get().source_posting_id == "101"
        fetch = CollectionRunFetch.objects.get(fetch_role="LISTING_PAGE")
        assert fetch.evidence["request_method"] == "GET"

    def test_adapters_are_pure_and_prospective_detail_translation_is_shared(self) -> None:
        before = (
            Posting.objects.count(),
            PostingObservation.objects.count(),
            GreenRelevanceAssessment.objects.count(),
            PostingLifecycleEvent.objects.count(),
        )
        assert issubclass(BernProspectiveApiAdapter, _ProspectiveAdapterBase)
        assert issubclass(LuzernProspectiveLegacyAdapter, _ProspectiveAdapterBase)
        assert before == (
            Posting.objects.count(),
            PostingObservation.objects.count(),
            GreenRelevanceAssessment.objects.count(),
            PostingLifecycleEvent.objects.count(),
        )

    def test_verified_endpoint_origins_and_provenance(self) -> None:
        cases = (
            ("SRC-OFF-CITY-BERN", "JOBS_BERN_CH", "bern.ch", {"www.bern.ch", "jobs.bern.ch"}),
            (
                "SRC-OFF-CITY-LUZERN",
                "CITY_LUZERN_PORTAL",
                "stadtluzern.ch",
                {"jobs.stadtluzern.ch", "job.stadtluzern.ch"},
            ),
            (
                "SRC-OFF-CITY-SCHAFFHAUSEN",
                "UMANTIS_LINKED",
                "stadt-schaffhausen.ch",
                {"jobs.stadt-schaffhausen.ch"},
            ),
        )
        for source_id, platform, domain, expected_hosts in cases:
            registered = make_source(source_id, platform, domain)
            ensure_default_endpoints(registered)
            endpoints = list(SourceEndpoint.objects.filter(source=registered))
            assert {endpoint.host for endpoint in endpoints} == expected_hosts
            assert all(endpoint.verified_at is not None for endpoint in endpoints)
            assert all(
                endpoint.evidence["verification"] == "GATE-011B live technical reconnaissance"
                for endpoint in endpoints
            )
        assert not SourceEndpoint.objects.filter(host="recruitingapp-2808.umantis.com").exists()

    def test_stgallen_is_blocked_without_adapter_or_endpoint_authorization(self) -> None:
        registered = make_source("SRC-OFF-CITY-STGALLEN", "CITY_SG_PORTAL", "stadt.sg.ch")
        ensure_default_endpoints(registered)
        with pytest.raises(UnsupportedPlatformError):
            get_adapter(registered)
        assert not SourceEndpoint.objects.filter(source=registered).exists()

    def test_missing_acknowledgement_blocks_before_network(self) -> None:
        registered = make_source("SRC-OFF-CITY-BERN", "JOBS_BERN_CH", "bern.ch")
        fetcher = Fetcher({})
        with TemporaryDirectory() as raw:
            pipeline = SharedCollectionPipeline(
                source_id=registered.pk,
                fetcher=fetcher,
                raw_store=RawObjectStore(raw),
                delay_seconds=0,
            )
            with pytest.raises(SourceGovernanceError, match="acknowledge"):
                pipeline.collect(full_snapshot=True)
        assert fetcher.requests == []

    def test_governed_http_rejects_unsupported_method_before_network(self) -> None:
        registered = make_source("SRC-OFF-CITY-BERN", "JOBS_BERN_CH", "bern.ch")
        ensure_default_endpoints(registered)
        with pytest.raises(GovernedHttpError, match="method"):
            GovernedHttpClient(registered).fetch_request(FetchRequest(BERN_API, method="DELETE"))

    def test_json_ld_entities_and_description_repair_are_bounded(self) -> None:
        luzern_url = "https://job.stadtluzern.ch/stellen/stadtluzern/offene-stellen/job/uuid"
        luzern_entry = ListingEntry("101", luzern_url, "Leiter*in Projekte & Community (70 %)", {})
        parsed = LuzernProspectiveLegacyAdapter().parse_detail(
            FetchedPage(
                luzern_url,
                luzern_url,
                200,
                "text/html",
                job_posting_html(
                    "Leiter*in Projekte &amp; Community (70 %) - Eintritt: 1. Januar 2027",
                    canonical=luzern_url,
                ),
            ),
            luzern_entry,
            Source(platform_family="CITY_LUZERN_PORTAL"),
        )
        self.assertEqual(
            parsed.title, "Leiter*in Projekte & Community (70 %) - Eintritt: 1. Januar 2027"
        )

        schaff_url = "https://jobs.stadt-schaffhausen.ch/jobs/job-5141/"
        malformed_description = b"""<script type="application/ld+json">{
          "@context":"https://schema.org/", "@type":"JobPosting",
          "title":"Sozialpaedagogin", "description":"<span style="">Text</span>",
          "hiringOrganization":{"@type":"Organization","name":"Stadt Schaffhausen"}
        }</script>"""
        repaired = SchaffhausenUmantisLinkedAdapter().parse_detail(
            FetchedPage(schaff_url, schaff_url, 200, "text/html", malformed_description),
            ListingEntry("5141", schaff_url, "Sozialpaedagogin", {}),
            Source(platform_family="UMANTIS_LINKED"),
        )
        self.assertTrue(repaired.structured_payload["json_ld_description_repaired"])
        self.assertIn('style=""', repaired.description_html)

        unrelated_malformed = b'<script type="application/ld+json">{"@type":broken}</script>'
        with self.assertRaises(PlatformAdapterError):
            SchaffhausenUmantisLinkedAdapter().parse_detail(
                FetchedPage(schaff_url, schaff_url, 200, "text/html", unrelated_malformed),
                ListingEntry("5141", schaff_url, "Sozialpaedagogin", {}),
                Source(platform_family="UMANTIS_LINKED"),
            )

    def test_malformed_payloads_fail_closed(self) -> None:
        for adapter in (BernProspectiveApiAdapter(), SchaffhausenUmantisLinkedAdapter()):
            registered = Source(source_id="SRC", platform_family=adapter.platform_family)
            request = adapter.initial_listing_request(registered)
            with pytest.raises(Exception):
                adapter.parse_listing_page(
                    FetchedPage(request.url, request.url, 200, "application/json", b"not json"),
                    request,
                    registered,
                )

    def test_winterthur_and_zurich_adapter_regression(self) -> None:
        assert get_adapter(Source(platform_family="REXX_SYSTEMS")).platform_family == "REXX_SYSTEMS"
        assert (
            get_adapter(Source(platform_family="CITY_SITE_SUCCESSFACTORS_LINKED")).platform_family
            == "CITY_SITE_SUCCESSFACTORS_LINKED"
        )
