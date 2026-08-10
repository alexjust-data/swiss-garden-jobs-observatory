from __future__ import annotations

import json
from datetime import UTC, datetime
from tempfile import TemporaryDirectory

import pytest
from django.test import TestCase

from collectors.adapters import get_adapter
from collectors.governed_http import ensure_default_endpoints
from collectors.pipeline import SharedCollectionPipeline
from collectors.platforms import FetchedPage, FetchRequest, UnsupportedPlatformError
from collectors.required_canton_adapters import (
    APPENZELL_AR_API,
    BASEL_LANDSCHAFT_LISTING,
    ZUG_LISTING,
    ZURICH_CANTON_API,
    AppenzellAusserrhodenSoliqueAdapter,
    BaselLandschaftProspectiveLegacyAdapter,
    ZugProspectiveLegacyAdapter,
    ZurichCantonSoliqueAdapter,
)
from core.storage import RawObjectStore
from observations.models import GreenRelevanceAssessment, PostingObservation
from sources.models import Source, SourceEndpoint


def source(source_id: str, platform: str) -> Source:
    return Source.objects.create(
        source_id=source_id,
        source_name=source_id,
        domain="example.ch",
        source_family="OFFICIAL_CANTONAL",
        source_type="DIRECT_PUBLIC_EMPLOYER",
        priority="P0",
        coverage_scope="canton",
        canonicality="CANONICAL",
        platform_family=platform,
        access_method="WEB",
        automation_status="COLLECTOR_CANDIDATE",
        legal_review_status="AUTOMATION_REVIEW_REQUIRED",
        verification_status="VERIFIED",
        official_url="https://example.ch/",
    )


def job_html(title: str, canonical: str, locality: str = "") -> bytes:
    return (
        f'<link rel="canonical" href="{canonical}">'
        '<script type="application/ld+json">'
        + json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "JobPosting",
                "title": title,
                "datePosted": "2026-08-10",
                "hiringOrganization": {"name": "Kanton"},
                "description": "Pflege von Gruenflaechen und Gartenanlagen",
                "jobLocation": {
                    "address": {
                        "addressLocality": locality,
                        "addressRegion": "",
                        "addressCountry": "CH",
                    }
                },
            }
        )
        + "</script>"
    ).encode()


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


class Gate011C1Tests(TestCase):
    def test_adapters_are_authorized_by_exact_source_identity(self) -> None:
        cases = (
            ("SRC-OFF-CANTON-ZH", "SOLIQUE_LINKED", ZurichCantonSoliqueAdapter),
            ("SRC-OFF-CANTON-AR", "SOLIQUE_EMBEDDED", AppenzellAusserrhodenSoliqueAdapter),
            ("SRC-OFF-CANTON-ZG", "PROSPECTIVE", ZugProspectiveLegacyAdapter),
            (
                "SRC-OFF-CANTON-BL",
                "PROSPECTIVE_UMANTIS_LINKED",
                BaselLandschaftProspectiveLegacyAdapter,
            ),
        )
        for source_id, platform, expected in cases:
            assert isinstance(
                get_adapter(Source(source_id=source_id, platform_family=platform)), expected
            )
        with pytest.raises(UnsupportedPlatformError):
            get_adapter(Source(source_id="SRC-OTHER", platform_family="SOLIQUE_LINKED"))

    def test_zurich_canton_solique_api_and_embedded_detail(self) -> None:
        registered = Source(source_id="SRC-OFF-CANTON-ZH", platform_family="SOLIQUE_LINKED")
        adapter = get_adapter(registered)
        request = adapter.initial_listing_request(registered)
        detail = "https://live.solique.ch/ktzh/job/details/4050673/"
        payload = {
            "filters": {"position": {"count": 1}},
            "jobs": [
                {
                    "title": {"id": "4050673", "value": "Gaertner/in"},
                    "link": "/ktzh/job/details/4050673/",
                    "timestamp": 1786009721,
                    "htmlContent": "Pflege von Gruenflaechen",
                    "organization": {"value": "Baudirektion"},
                    "office": {"value": "Amt"},
                    "location": {"value": "Zuerich"},
                }
            ],
        }
        listing = adapter.parse_listing_page(
            FetchedPage(
                request.url,
                request.url,
                200,
                "application/json",
                json.dumps(payload).encode(),
            ),
            request,
            registered,
        )
        assert listing.discovery_complete and listing.total_reported == 1
        parsed = adapter.parse_detail(
            FetchedPage(detail, detail, 200, "text/html", b"detail evidence"),
            listing.entries[0],
            registered,
        )
        assert parsed.source_posting_id == "4050673"
        assert parsed.published_at_parse_method == "MISSING"
        assert parsed.raw_location == "Zuerich" and parsed.location_locality == ""

    def test_appenzell_ar_solique_uses_publication_id_and_json_ld(self) -> None:
        registered = Source(source_id="SRC-OFF-CANTON-AR", platform_family="SOLIQUE_EMBEDDED")
        adapter = get_adapter(registered)
        request = adapter.initial_listing_request(registered)
        detail = "https://live.solique.ch/Microsites/showPublication/example"
        payload = {
            "config": {"client": "kanton-appenzell-ausserrhoden"},
            "filters": {},
            "jobs": [
                {
                    "sPublicationId": "4052143",
                    "jobtitle": "Gaertner/in",
                    "deepLink": detail,
                    "startDate": "2026-08-10T00:00:00+02:00",
                    "dateModified": "2026-08-10T14:30:27+02:00",
                    "workload-from": "60",
                    "workload-to": "100",
                }
            ],
        }
        listing = adapter.parse_listing_page(
            FetchedPage(
                request.url,
                request.url,
                200,
                "application/json",
                json.dumps(payload).encode(),
            ),
            request,
            registered,
        )
        parsed = adapter.parse_detail(
            FetchedPage(
                detail,
                detail,
                200,
                "text/html",
                job_html("Gaertner/in 60% - 100%", detail, "Herisau"),
            ),
            listing.entries[0],
            registered,
        )
        assert listing.discovery_complete and listing.total_reported == 1
        assert parsed.source_posting_id == "4052143"
        assert parsed.published_at_parse_method == "SOURCE_FIELD"
        assert parsed.title == "Gaertner/in 60% - 100%"

    def test_shared_prospective_parser_handles_zug_and_basel_landschaft(self) -> None:
        cases = (
            (
                "SRC-OFF-CANTON-ZG",
                "PROSPECTIVE",
                ZUG_LISTING,
                "https://www.zg.ch/jobs/offene-stellen/gaertner/11111111-1111-4111-8111-111111111111",
                10,
                False,
            ),
            (
                "SRC-OFF-CANTON-BL",
                "PROSPECTIVE_UMANTIS_LINKED",
                BASEL_LANDSCHAFT_LISTING,
                "https://jobs.baselland.ch/offene-stellen/gaertner/22222222-2222-4222-8222-222222222222",
                15,
                True,
            ),
        )
        for source_id, platform, listing_url, detail, offset, has_total in cases:
            registered = Source(source_id=source_id, platform_family=platform)
            adapter = get_adapter(registered)
            request = adapter.initial_listing_request(registered)
            total = "<p>1 offene Stellen</p>" if has_total else ""
            pagination = (
                '<a onclick="sendPagination(0)"></a>'
                '<a onclick="sendPagination(15)"></a>'
                '<a onclick="sendPagination(30)"></a>'
                '<a onclick="sendPagination(45)"></a>'
                if has_total
                else '<a onclick="sendPagination(0)"></a><a onclick="sendPagination(10)"></a>'
            )
            body = (
                f'{total}<a class="job-0" href="{detail}" title="Gaertner/in"></a>{pagination}'
            ).encode()
            listing = adapter.parse_listing_page(
                FetchedPage(listing_url, listing_url, 200, "text/html", body),
                request,
                registered,
            )
            assert listing.next_request is not None and listing.next_request.method == "POST"
            assert ("offset", str(offset)) in listing.next_request.form_data
            parsed = adapter.parse_detail(
                FetchedPage(detail, detail, 200, "text/html", job_html("Gaertner/in", detail)),
                listing.entries[0],
                registered,
            )
            assert parsed.source_posting_id in detail
            assert listing.total_reported == (1 if has_total else None)

    def test_full_source_uses_shared_pipeline_and_green_assessment(self) -> None:
        registered = source("SRC-OFF-CANTON-AR", "SOLIQUE_EMBEDDED")
        detail = "https://live.solique.ch/Microsites/showPublication/example"
        listing_payload = {
            "jobs": [
                {
                    "sPublicationId": "4052143",
                    "jobtitle": "Gaertner/in",
                    "deepLink": detail,
                    "startDate": "2026-08-10T00:00:00+02:00",
                    "dateModified": "2026-08-10T14:30:27+02:00",
                    "workload-from": "60",
                    "workload-to": "100",
                }
            ]
        }
        pages = {
            ("GET", APPENZELL_AR_API): FetchedPage(
                APPENZELL_AR_API,
                APPENZELL_AR_API,
                200,
                "application/json",
                json.dumps(listing_payload).encode(),
            ),
            ("GET", detail): FetchedPage(
                detail, detail, 200, "text/html", job_html("Gaertner/in 60% - 100%", detail)
            ),
        }
        with TemporaryDirectory() as raw:
            run = SharedCollectionPipeline(
                source_id=registered.pk,
                fetcher=Fetcher(pages),
                raw_store=RawObjectStore(raw),
                delay_seconds=0,
                clock=lambda: datetime(2026, 8, 10, 16, tzinfo=UTC),
            ).collect(full_snapshot=True, acknowledge_automation_review=True)
        assert run.snapshot_complete and run.source_health_status == "HEALTHY"
        assert run.listing_total_discovered == run.observations_created == 1
        assert PostingObservation.objects.filter(collection_run=run).count() == 1
        assert (
            GreenRelevanceAssessment.objects.filter(posting_observation__collection_run=run).count()
            == 1
        )

    def test_verified_origins_do_not_authorize_umantis(self) -> None:
        expected = {
            "SRC-OFF-CANTON-ZH": ("SOLIQUE_LINKED", {"www.zh.ch", "live.solique.ch"}),
            "SRC-OFF-CANTON-AR": ("SOLIQUE_EMBEDDED", {"ar.ch", "live.solique.ch"}),
            "SRC-OFF-CANTON-ZG": (
                "PROSPECTIVE",
                {"zg.ch", "zg.prospective.ch", "www.zg.ch"},
            ),
            "SRC-OFF-CANTON-BL": (
                "PROSPECTIVE_UMANTIS_LINKED",
                {"www.baselland.ch", "ohws.prospective.ch", "jobs.baselland.ch"},
            ),
        }
        for source_id, (platform, hosts) in expected.items():
            registered = source(source_id, platform)
            ensure_default_endpoints(registered)
            endpoints = SourceEndpoint.objects.filter(source=registered)
            assert set(endpoints.values_list("host", flat=True)) == hosts
            assert all(
                row.evidence["verification"] == "GATE-011C-1 live technical reconnaissance"
                for row in endpoints
            )
        assert not SourceEndpoint.objects.filter(host__icontains="umantis").exists()

    def test_malformed_or_mismatched_platform_fails_closed(self) -> None:
        with pytest.raises(UnsupportedPlatformError, match="does not match"):
            get_adapter(Source(source_id="SRC-OFF-CANTON-ZH", platform_family="PROSPECTIVE"))
        adapter = ZurichCantonSoliqueAdapter()
        source_row = Source(source_id="SRC-OFF-CANTON-ZH", platform_family="SOLIQUE_LINKED")
        request = adapter.initial_listing_request(source_row)
        with pytest.raises(Exception):
            adapter.parse_listing_page(
                FetchedPage(
                    ZURICH_CANTON_API,
                    ZURICH_CANTON_API,
                    200,
                    "application/json",
                    b"{}",
                ),
                request,
                source_row,
            )
