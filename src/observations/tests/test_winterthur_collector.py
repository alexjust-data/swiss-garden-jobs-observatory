from __future__ import annotations

import json
from datetime import date
from tempfile import TemporaryDirectory
from urllib.request import Request

import pytest
from django.test import TestCase

from collectors.winterthur import (
    WINTERTHUR_LISTING_URL,
    FetchedPage,
    WinterthurCollector,
    WinterthurCollectorError,
    _SameOriginRedirectHandler,
    parse_detail,
    parse_listing,
)
from core.hashing import sha256_hex
from core.storage import RawObjectStore
from observations.models import CollectionRun, PostingObservation
from reference_data.models import Municipality
from sources.models import Source

LISTING = b"""<!doctype html><a href=\"https://jobs.winterthur.ch/?yid=8280\">Garden role</a>"""


def detail_payload() -> bytes:
    payload = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "G\u00e4rtner:in Gartenunterhalt (100 %)",
        "datePosted": "2026-08-03",
        "validThrough": "2026-08-31",
        "employmentType": "FULL_TIME",
        "hiringOrganization": {
            "@type": "Organization",
            "name": "Stadt Winterthur Jobportal",
        },
        "jobLocation": {
            "@type": "Place",
            "address": {
                "@type": "PostalAddress",
                "streetAddress": "Diverse Standorte",
                "addressLocality": "Winterthur",
                "postalCode": "8400",
                "addressCountry": "CH",
            },
        },
        "description": "<p>Garden work</p>",
        "responsibilities": "<ul><li>Care</li></ul>",
        "qualifications": "<ul><li>EFZ</li></ul>",
        "jobBenefits": "<ul><li>Five weeks</li></ul>",
    }
    encoded = json.dumps(payload).encode()
    return (
        b'<!doctype html><meta property="og:url" '
        b'content="https://jobs.winterthur.ch/'
        b'Gaertnerin-Gartenunterhalt-100--de-j8280.html">'
        b'<script type="application/ld+json">' + encoded + b"</script>"
    )


class FakeFetcher:
    def __init__(self, pages: dict[str, FetchedPage]) -> None:
        self.pages = pages
        self.urls: list[str] = []

    def fetch(self, url: str) -> FetchedPage:
        self.urls.append(url)
        return self.pages[url]


class WinterthurCollectorTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        Source.objects.create(
            source_id="SRC-OFF-CITY-WINTERTHUR",
            source_name="Stadt Winterthur Jobportal",
            domain="jobs.winterthur.ch",
            source_family="OFFICIAL_MUNICIPAL",
            source_type="DIRECT_PUBLIC_EMPLOYER",
            priority="P0",
            coverage_scope="Winterthur",
            canonicality="CANONICAL",
            platform_family="REXX_SYSTEMS",
            access_method="WEB",
            automation_status="COLLECTOR_CANDIDATE",
            legal_review_status="AUTOMATION_REVIEW_REQUIRED",
            verification_status="VERIFIED",
            official_url="https://jobs.winterthur.ch/",
        )
        Municipality.objects.create(
            bfs_code=230,
            snapshot_date=date(2026, 1, 1),
            municipality_name="Winterthur",
            canton_code="ZH",
            canton_name="Z\u00fcrich",
            bfs_language_region_code=1,
            language_region="GERMAN",
            statistical_city=True,
            degurb2021=1,
            priority_tier="P0",
        )

    def test_point_in_time_collection_preserves_exact_raw_bytes(self) -> None:
        detail = detail_payload()
        detail_url = "https://jobs.winterthur.ch/?yid=8280"
        fetcher = FakeFetcher(
            {
                WINTERTHUR_LISTING_URL: FetchedPage(
                    WINTERTHUR_LISTING_URL,
                    WINTERTHUR_LISTING_URL,
                    LISTING,
                    "text/html",
                ),
                detail_url: FetchedPage(detail_url, detail_url, detail, "text/html"),
            }
        )
        with TemporaryDirectory() as raw_dir:
            store = RawObjectStore(raw_dir)
            run = WinterthurCollector(
                fetcher=fetcher,
                raw_store=store,
                delay_seconds=0,
            ).collect()
            observation = PostingObservation.objects.get()
            listing_artifact = run.listing_raw_artifact

            assert run.status == CollectionRun.Status.SUCCEEDED
            assert run.listings_discovered == 1
            assert run.observations_created == 1
            assert observation.source_posting_id == "8280"
            assert observation.title == "G\u00e4rtner:in Gartenunterhalt (100 %)"
            assert observation.date_posted == date(2026, 8, 3)
            assert observation.valid_through == date(2026, 8, 31)
            assert observation.municipality.pk == 230
            assert observation.raw_artifact.sha256_digest == sha256_hex(detail)
            assert store.read_bytes(observation.raw_artifact.object_key) == detail
            assert listing_artifact is not None
            assert store.read_bytes(listing_artifact.object_key) == LISTING

    def test_requested_posting_must_be_active(self) -> None:
        fetcher = FakeFetcher(
            {
                WINTERTHUR_LISTING_URL: FetchedPage(
                    WINTERTHUR_LISTING_URL,
                    WINTERTHUR_LISTING_URL,
                    LISTING,
                    "text/html",
                )
            }
        )
        with TemporaryDirectory() as raw_dir:
            collector = WinterthurCollector(
                fetcher=fetcher,
                raw_store=RawObjectStore(raw_dir),
                delay_seconds=0,
            )
            with pytest.raises(WinterthurCollectorError, match="not active"):
                collector.collect(posting_ids={"9999"})


def test_listing_parser_deduplicates_source_posting_ids() -> None:
    entries = parse_listing(LISTING + LISTING)
    assert [(entry.source_posting_id, entry.title) for entry in entries] == [
        ("8280", "Garden role")
    ]


def test_detail_parser_uses_json_ld_and_canonical_url() -> None:
    posting = parse_detail(
        detail_payload(),
        requested_url="https://jobs.winterthur.ch/?yid=8280",
        expected_posting_id="8280",
    )
    assert posting.canonical_url.endswith("-de-j8280.html")
    assert posting.location_locality == "Winterthur"
    assert posting.location_country == "CH"


def test_detail_parser_rejects_cross_origin_canonical_url() -> None:
    body = detail_payload().replace(b"https://jobs.winterthur.ch/", b"https://example.com/")
    with pytest.raises(WinterthurCollectorError, match="outside"):
        parse_detail(
            body,
            requested_url="https://jobs.winterthur.ch/?yid=8280",
            expected_posting_id="8280",
        )


def test_redirect_handler_rejects_cross_origin_before_following() -> None:
    handler = _SameOriginRedirectHandler()
    request = Request(WINTERTHUR_LISTING_URL)

    with pytest.raises(WinterthurCollectorError, match="outside"):
        handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://example.com/redirected",
        )
