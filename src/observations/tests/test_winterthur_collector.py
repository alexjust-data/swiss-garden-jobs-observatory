from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.request import Request

import pytest
from django.test import TestCase

from collectors.winterthur import (
    WINTERTHUR_LISTING_URL,
    FetchedPage,
    WinterthurCollector,
    WinterthurCollectorError,
    WinterthurGovernanceError,
    _SameOriginRedirectHandler,
    enforce_winterthur_source_policy,
    parse_detail,
    parse_listing,
)
from core.hashing import sha256_hex
from core.models import RawArtifact
from core.storage import RawObjectStore
from observations.contracts import (
    PostingObservationContractError,
    validate_posting_observation_contract,
)
from observations.models import (
    CollectionRun,
    ImmutablePostingObservationError,
    PostingObservation,
)
from reference_data.models import Municipality
from sources.models import Source

LISTING = b"""<!doctype html><a href=\"https://jobs.winterthur.ch/?yid=8280\">Garden role</a>"""
DETAIL_URL = "https://jobs.winterthur.ch/?yid=8280"
CANONICAL_URL = "https://jobs.winterthur.ch/Gaertnerin-Gartenunterhalt-100--de-j8280.html"


def location(locality: str = "Winterthur", country: str | None = "CH") -> dict[str, object]:
    address: dict[str, object] = {
        "@type": "PostalAddress",
        "streetAddress": "Diverse Standorte",
        "addressLocality": locality,
        "postalCode": "8400",
    }
    if country is not None:
        address["addressCountry"] = country
    return {"@type": "Place", "address": address}


def detail_payload(*, locations: object | None = None) -> bytes:
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
        "jobLocation": location() if locations is None else locations,
        "description": "<p>Garden work</p>",
        "responsibilities": "<ul><li>Care</li></ul>",
        "qualifications": "<ul><li>EFZ</li></ul>",
        "jobBenefits": "<ul><li>Five weeks</li></ul>",
    }
    encoded = json.dumps(payload).encode()
    return (
        b'<!doctype html><meta property="og:url" content="'
        + CANONICAL_URL.encode()
        + b'"><script type="application/ld+json">'
        + encoded
        + b"</script>"
    )


class FakeFetcher:
    def __init__(self, pages: dict[str, FetchedPage]) -> None:
        self.pages = pages
        self.urls: list[str] = []

    def fetch(self, url: str) -> FetchedPage:
        self.urls.append(url)
        return self.pages[url]


def fake_fetcher(detail: bytes | None = None) -> FakeFetcher:
    detail = detail or detail_payload()
    return FakeFetcher(
        {
            WINTERTHUR_LISTING_URL: FetchedPage(
                requested_url=WINTERTHUR_LISTING_URL,
                final_url=WINTERTHUR_LISTING_URL,
                status_code=200,
                content_type="text/html",
                body=LISTING,
            ),
            DETAIL_URL: FetchedPage(
                requested_url=DETAIL_URL,
                final_url=DETAIL_URL,
                status_code=200,
                content_type="text/html",
                body=detail,
            ),
        }
    )


def policy_source(
    *,
    legal_review_status: str,
    automation_status: str = "COLLECTOR_CANDIDATE",
    source_id: str = "SRC-OFF-CITY-WINTERTHUR",
    domain: str = "jobs.winterthur.ch",
    platform_family: str = "REXX_SYSTEMS",
) -> Source:
    return Source(
        source_id=source_id,
        domain=domain,
        platform_family=platform_family,
        automation_status=automation_status,
        legal_review_status=legal_review_status,
    )


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

    def collect_once(self, raw_dir: str, *, detail: bytes | None = None) -> CollectionRun:
        return WinterthurCollector(
            fetcher=fake_fetcher(detail),
            raw_store=RawObjectStore(raw_dir),
            delay_seconds=0,
        ).collect(acknowledge_automation_review=True)

    def test_valid_contract_and_exact_raw_are_persisted(self) -> None:
        detail = detail_payload()
        with TemporaryDirectory() as raw_dir:
            store = RawObjectStore(raw_dir)
            run = self.collect_once(raw_dir, detail=detail)
            observation = PostingObservation.objects.get()
            listing_artifact = run.listing_raw_artifact
            contract = observation.contract_payload

            validate_posting_observation_contract(contract)
            assert run.status == CollectionRun.Status.SUCCEEDED
            assert observation.source_posting_id == "8280"
            assert observation.title == "G\u00e4rtner:in Gartenunterhalt (100 %)"
            assert observation.date_posted == date(2026, 8, 3)
            assert observation.valid_through == date(2026, 8, 31)
            assert observation.municipality.pk == 230
            assert contract["schema_version"] == "1.2"
            assert contract["observation_status"] == "ACTIVE"
            assert contract["source_url"] == DETAIL_URL
            assert contract["canonical_url"] == CANONICAL_URL
            assert contract["http_status"] == 200
            assert contract["published_at_raw"] == "2026-08-03"
            assert contract["published_at_precision"] == "EXACT_DATE"
            assert contract["published_at_parse_method"] == "STRUCTURED_DATA"
            assert contract["raw_payload_sha256"] == observation.raw_artifact.sha256_digest
            assert observation.raw_artifact.sha256_digest == sha256_hex(detail)
            assert store.read_bytes(observation.raw_artifact.object_key) == detail
            assert listing_artifact is not None
            assert store.read_bytes(listing_artifact.object_key) == LISTING

    def test_invalid_contract_retains_raw_but_blocks_promotion(self) -> None:
        with TemporaryDirectory() as raw_dir:
            collector = WinterthurCollector(
                fetcher=fake_fetcher(),
                raw_store=RawObjectStore(raw_dir),
                delay_seconds=0,
            )
            with (
                patch("collectors.winterthur.build_contract_payload", return_value={}),
                pytest.raises(PostingObservationContractError, match="validation failed"),
            ):
                collector.collect(acknowledge_automation_review=True)

            run = CollectionRun.objects.get()
            assert run.status == CollectionRun.Status.FAILED
            assert "validation failed" in run.error_message
            assert PostingObservation.objects.count() == 0
            assert RawArtifact.objects.count() == 2

    def test_repeated_runs_append_and_preserve_first_observation(self) -> None:
        with TemporaryDirectory() as raw_dir:
            store = RawObjectStore(raw_dir)
            first_run = self.collect_once(raw_dir)
            first = PostingObservation.objects.get(collection_run=first_run)
            first_snapshot = {
                "id": first.pk,
                "title": first.title,
                "contract": deepcopy(first.contract_payload),
                "raw_key": first.raw_artifact.object_key,
                "raw": store.read_bytes(first.raw_artifact.object_key),
            }

            second_run = self.collect_once(raw_dir)
            second = PostingObservation.objects.get(collection_run=second_run)
            first.refresh_from_db()

            assert first.pk != second.pk
            assert PostingObservation.objects.count() == 2
            assert first.title == first_snapshot["title"]
            assert first.contract_payload == first_snapshot["contract"]
            assert first.raw_artifact.object_key == first_snapshot["raw_key"]
            assert store.read_bytes(first.raw_artifact.object_key) == first_snapshot["raw"]

    def test_observation_model_rejects_update_and_delete(self) -> None:
        with TemporaryDirectory() as raw_dir:
            self.collect_once(raw_dir)
            observation = PostingObservation.objects.get()
            observation.title = "changed"
            with pytest.raises(ImmutablePostingObservationError, match="append-only"):
                observation.save()
            with pytest.raises(ImmutablePostingObservationError, match="cannot be deleted"):
                observation.delete()

    def test_requested_posting_must_be_active(self) -> None:
        with TemporaryDirectory() as raw_dir:
            collector = WinterthurCollector(
                fetcher=fake_fetcher(),
                raw_store=RawObjectStore(raw_dir),
                delay_seconds=0,
            )
            with pytest.raises(WinterthurCollectorError, match="not active"):
                collector.collect(
                    posting_ids={"9999"},
                    acknowledge_automation_review=True,
                )


def test_listing_parser_deduplicates_source_posting_ids() -> None:
    entries = parse_listing(LISTING + LISTING)
    assert [(entry.source_posting_id, entry.title) for entry in entries] == [
        ("8280", "Garden role")
    ]


def test_detail_parser_uses_json_ld_and_canonical_url() -> None:
    posting = parse_detail(
        detail_payload(),
        requested_url=DETAIL_URL,
        expected_posting_id="8280",
    )
    assert posting.canonical_url == CANONICAL_URL
    assert posting.location_locality == "Winterthur"
    assert posting.location_country == "CH"


@pytest.mark.parametrize(
    "locations",
    [
        location("Z\u00fcrich", "CH"),
        location("Winterthur", "DE"),
        [location("Winterthur", "CH"), location("Z\u00fcrich", "CH")],
    ],
)
def test_location_mismatch_blocks_bfs_230(locations: object) -> None:
    with pytest.raises(WinterthurCollectorError, match="does not justify BFS 230"):
        parse_detail(
            detail_payload(locations=locations),
            requested_url=DETAIL_URL,
            expected_posting_id="8280",
        )


def test_multiple_unambiguous_winterthur_locations_are_allowed() -> None:
    posting = parse_detail(
        detail_payload(locations=[location("Winterthur", "CH"), location("Winterthur", None)]),
        requested_url=DETAIL_URL,
        expected_posting_id="8280",
    )
    assert posting.location_locality == "Winterthur"
    assert posting.location_country == "CH"


def test_detail_parser_rejects_cross_origin_canonical_url() -> None:
    body = detail_payload().replace(b"https://jobs.winterthur.ch/", b"https://example.com/")
    with pytest.raises(WinterthurCollectorError, match="outside"):
        parse_detail(body, requested_url=DETAIL_URL, expected_posting_id="8280")


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


@pytest.mark.parametrize(
    ("legal_status", "acknowledge", "allowed"),
    [
        ("AUTOMATION_REVIEW_REQUIRED", False, False),
        ("AUTOMATION_REVIEW_REQUIRED", True, True),
        ("APPROVED", False, True),
        ("DO_NOT_AUTOMATE", True, False),
        ("UNKNOWN_FUTURE_STATE", True, False),
    ],
)
def test_governance_legal_policy_is_fail_closed(
    legal_status: str, acknowledge: bool, allowed: bool
) -> None:
    source = policy_source(legal_review_status=legal_status)
    if allowed:
        enforce_winterthur_source_policy(
            source,
            acknowledge_automation_review=acknowledge,
        )
    else:
        with pytest.raises(WinterthurGovernanceError):
            enforce_winterthur_source_policy(
                source,
                acknowledge_automation_review=acknowledge,
            )


@pytest.mark.parametrize(
    "override",
    [
        {"automation_status": "ACTIVE"},
        {"domain": "example.com"},
        {"platform_family": "OTHER"},
        {"source_id": "OTHER"},
    ],
)
def test_governance_registry_identity_is_fail_closed(override: dict[str, str]) -> None:
    source = policy_source(legal_review_status="APPROVED", **override)
    with pytest.raises(WinterthurGovernanceError, match="contract mismatch"):
        enforce_winterthur_source_policy(
            source,
            acknowledge_automation_review=True,
        )
