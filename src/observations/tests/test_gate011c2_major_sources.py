from __future__ import annotations

import json
from datetime import UTC, datetime
from tempfile import TemporaryDirectory

import pytest
from django.test import TestCase

from collectors.adapters import get_adapter
from collectors.federal_canton_adapters import (
    BASEL_STADT_SURFACES,
    BaselStadtSoliqueAdapter,
    FederalProspectiveAdapter,
)
from collectors.governed_http import ensure_default_endpoints
from collectors.pipeline import CollectionPipelineError, SharedCollectionPipeline
from collectors.platforms import (
    FetchedPage,
    FetchRequest,
    ListingEntry,
    PlatformAdapterError,
    UnsupportedPlatformError,
)
from core.storage import RawObjectStore
from dashboard.models import DashboardSnapshot
from day0.models import Day0ReadinessAssessment
from observations.models import (
    CollectionRun,
    GreenRelevanceAssessment,
    Posting,
    PostingLifecycleEvent,
    PostingObservation,
)
from premium_segments.models import PremiumSegmentAssessment
from sources.models import Source, SourceEndpoint
from vacancies.models import Vacancy


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


def federal_payload(offset: int, total: int, *jobs: tuple[str, str, str]) -> bytes:
    return json.dumps(
        {
            "offset": offset,
            "total": total,
            "jobs": [
                {
                    "id": source_id,
                    "title": title,
                    "start_date": "2026-08-10T10:00:00Z",
                    "last_modification_timestamp": "2026-08-10T11:00:00Z",
                    "links": {"directlink": detail},
                }
                for source_id, title, detail in jobs
            ],
        }
    ).encode()


def job_json_ld(title: str, canonical: str, description: str = "Pflege von Grünflächen") -> bytes:
    return (
        f'<link rel="canonical" href="{canonical}">'
        '<script type="application/ld+json">'
        + json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "JobPosting",
                "title": title,
                "description": description,
                "hiringOrganization": {"name": "Bundesverwaltung"},
                "jobLocation": {"address": {"addressCountry": "CH"}},
            }
        )
        + "</script>"
    ).encode()


def bs_listing(
    total: int,
    label: str,
    *entries: tuple[str, str, str],
    next_page: int | None = None,
) -> bytes:
    jobs = "".join(
        f'<div class="job"><a href="job/details/{posting_id}">'
        f'<div class="jobtitle">{title}</div>'
        f'<div class="organization">{organization}</div></a></div>'
        for posting_id, title, organization in entries
    )
    next_link = (
        f'<li class="nextbtn"><a href="?page={next_page}">Weitere</a></li>'
        if next_page is not None
        else ""
    )
    return (
        f'<h3 class="job-counter"><span>{total}</span> offene {label}</h3>'
        f"{jobs}<ul>{next_link}</ul>"
    ).encode()


def bs_detail(title: str) -> bytes:
    return (
        '<html><head><meta property="og:description" '
        'content="Pflege von Gartenanlagen und Grünflächen"></head>'
        f"<body><h1>{title}</h1><h3>Ihre Aufgaben</h3>Gartenpflege</body></html>"
    ).encode()


class Fetcher:
    def __init__(self, pages: dict[tuple[str, str], FetchedPage]) -> None:
        self.pages = pages
        self.requests: list[FetchRequest] = []

    def fetch_request(self, request: FetchRequest) -> FetchedPage:
        self.requests.append(request)
        return self.pages[(request.method, request.url)]

    def fetch(self, url: str) -> FetchedPage:
        return self.fetch_request(FetchRequest(url))


class Gate011C2Tests(TestCase):
    def test_adapters_are_exact_source_authorized_and_blocked_sources_stay_disabled(self) -> None:
        assert isinstance(
            get_adapter(
                Source(source_id="SRC-OFF-JOBS-ADMIN", platform_family="FEDERAL_JOB_PORTAL")
            ),
            FederalProspectiveAdapter,
        )
        assert isinstance(
            get_adapter(
                Source(source_id="SRC-OFF-CANTON-BS", platform_family="BS_EMPLOYER_PORTAL")
            ),
            BaselStadtSoliqueAdapter,
        )
        for source_id, platform in (
            ("SRC-OFF-CANTON-AG", "CANTON_AG_PORTAL"),
            ("SRC-OFF-CANTON-BE", "SITES_BE"),
        ):
            with pytest.raises(UnsupportedPlatformError):
                get_adapter(Source(source_id=source_id, platform_family=platform))
        with pytest.raises(UnsupportedPlatformError):
            get_adapter(Source(source_id="SRC-OTHER", platform_family="FEDERAL_JOB_PORTAL"))

    def test_federal_total_offset_and_json_ld_contract(self) -> None:
        registered = Source(source_id="SRC-OFF-JOBS-ADMIN", platform_family="FEDERAL_JOB_PORTAL")
        adapter = get_adapter(registered)
        first = adapter.initial_listing_request(registered)
        detail = "https://jobs.admin.ch/offene-stellen/gaertner-in/uuid-a"
        page = adapter.parse_listing_page(
            FetchedPage(
                first.url,
                first.url,
                200,
                "application/json",
                federal_payload(0, 1, ("101", "Gärtner/in", detail)),
            ),
            first,
            registered,
        )
        assert page.discovery_complete and page.total_reported == 1
        parsed = adapter.parse_detail(
            FetchedPage(detail, detail, 200, "text/html", job_json_ld("Gärtner/in", detail)),
            page.entries[0],
            registered,
        )
        assert parsed.source_posting_id == "101"
        assert parsed.published_at_parse_method == "SOURCE_FIELD"
        with pytest.raises(PlatformAdapterError, match="offset"):
            adapter.parse_listing_page(
                FetchedPage(first.url, first.url, 200, "application/json", federal_payload(1, 1)),
                first,
                registered,
            )
        with pytest.raises(PlatformAdapterError, match="reported total"):
            adapter.parse_listing_page(
                FetchedPage(
                    first.url,
                    first.url,
                    200,
                    "application/json",
                    federal_payload(0, 2, ("101", "GÃ¤rtner/in", detail)),
                ),
                first,
                registered,
            )

        multiline = ListingEntry(
            "102",
            detail,
            "Leitung Daten,\nMitglied der Geschäftsleitung",
            {"api_job": {"start_date": "2026-08-10T10:00:00Z"}},
        )
        parsed_multiline = adapter.parse_detail(
            FetchedPage(
                detail,
                detail,
                200,
                "text/html",
                job_json_ld("Leitung Daten,<br/>Mitglied der Geschäftsleitung", detail),
            ),
            multiline,
            registered,
        )
        assert parsed_multiline.title == "Leitung Daten, Mitglied der Geschäftsleitung"

        quoted = ListingEntry(
            "103",
            detail,
            "Leitung «Fahrzeugvorschriften»",
            {"api_job": {"start_date": "2026-08-10T10:00:00Z"}},
        )
        parsed_quoted = adapter.parse_detail(
            FetchedPage(
                detail,
                detail,
                200,
                "text/html",
                job_json_ld('Leitung "Fahrzeugvorschriften"', detail),
            ),
            quoted,
            registered,
        )
        assert parsed_quoted.title == 'Leitung "Fahrzeugvorschriften"'

    def test_basel_stadt_full_source_visits_jobs_and_apprenticeships(self) -> None:
        registered = source("SRC-OFF-CANTON-BS", "BS_EMPLOYER_PORTAL")
        ordinary_root = BASEL_STADT_SURFACES[0][1]
        learning_root = BASEL_STADT_SURFACES[1][1]
        ordinary_detail = "https://stellenmarkt.bs.ch/kbs/job/details/4001"
        learning_detail = "https://stellenmarkt.bs.ch/kbs/lehrstellen/job/details/4002"
        pages = {
            ("GET", ordinary_root): FetchedPage(
                ordinary_root,
                ordinary_root,
                200,
                "text/html",
                bs_listing(1, "Jobs", ("4001", "Techniker/in", "BVD")),
            ),
            ("GET", learning_root): FetchedPage(
                learning_root,
                learning_root,
                200,
                "text/html",
                bs_listing(1, "Lehrstelle", ("4002", "Gärtner/in EFZ", "BVD")),
            ),
            ("GET", ordinary_detail): FetchedPage(
                ordinary_detail, ordinary_detail, 200, "text/html", bs_detail("Techniker/in")
            ),
            ("GET", learning_detail): FetchedPage(
                learning_detail, learning_detail, 200, "text/html", bs_detail("Gärtner/in EFZ")
            ),
        }
        fetcher = Fetcher(pages)
        with TemporaryDirectory() as raw:
            run = SharedCollectionPipeline(
                source_id=registered.pk,
                fetcher=fetcher,
                raw_store=RawObjectStore(raw),
                delay_seconds=0,
                clock=lambda: datetime(2026, 8, 11, 10, tzinfo=UTC),
            ).collect(full_snapshot=True, acknowledge_automation_review=True)
        assert run.snapshot_complete and run.source_health_status == "HEALTHY"
        assert run.listing_total_discovered == run.details_fetched == 2
        assert run.observations_created == run.green_assessments_created == 2
        assert (
            GreenRelevanceAssessment.objects.filter(
                posting_observation__collection_run=run, result="GREEN_CONFIRMED"
            ).count()
            == 1
        )
        listing_surfaces = [
            request.context["surface_name"]
            for request in fetcher.requests
            if request.role == "LISTING_PAGE"
        ]
        assert listing_surfaces == ["ordinary", "apprenticeships"]

    def test_basel_stadt_cumulative_pagination_advances_without_double_counting(self) -> None:
        registered = Source(source_id="SRC-OFF-CANTON-BS", platform_family="BS_EMPLOYER_PORTAL")
        adapter = BaselStadtSoliqueAdapter()
        first = adapter.initial_listing_request(registered)
        first_page = adapter.parse_listing_page(
            FetchedPage(
                first.url,
                first.url,
                200,
                "text/html",
                bs_listing(2, "Jobs", ("4001", "First", "BVD"), next_page=2),
            ),
            first,
            registered,
        )
        assert first_page.next_request is not None
        second = first_page.next_request
        second_page = adapter.parse_listing_page(
            FetchedPage(
                second.url,
                second.url,
                200,
                "text/html",
                bs_listing(
                    2,
                    "Jobs",
                    ("4001", "First", "BVD"),
                    ("4002", "Second", "BVD"),
                    next_page=2,
                ),
            ),
            second,
            registered,
        )
        assert [entry.source_posting_id for entry in second_page.entries] == ["4002"]
        assert second_page.next_request is not None
        assert second_page.next_request.context["surface_name"] == "apprenticeships"

        jump = adapter.initial_listing_request(registered)
        with pytest.raises(PlatformAdapterError, match="monotonically"):
            adapter.parse_listing_page(
                FetchedPage(
                    jump.url,
                    jump.url,
                    200,
                    "text/html",
                    bs_listing(3, "Jobs", ("4001", "First", "BVD"), next_page=3),
                ),
                jump,
                registered,
            )

    def test_basel_stadt_duplicate_collapses_and_conflict_fails_closed(self) -> None:
        registered = source("SRC-OFF-CANTON-BS", "BS_EMPLOYER_PORTAL")
        ordinary_root = BASEL_STADT_SURFACES[0][1]
        learning_root = BASEL_STADT_SURFACES[1][1]
        shared = "https://stellenmarkt.bs.ch/kbs/job/details/4001"
        pages = {
            ("GET", ordinary_root): FetchedPage(
                ordinary_root,
                ordinary_root,
                200,
                "text/html",
                bs_listing(1, "Jobs", ("4001", "Shared", "BVD")),
            ),
            ("GET", learning_root): FetchedPage(
                learning_root,
                learning_root,
                200,
                "text/html",
                bs_listing(1, "Lehrstelle", ("4001", "Shared", "BVD")).replace(
                    b'href="job/details/4001"', f'href="{shared}"'.encode()
                ),
            ),
            ("GET", shared): FetchedPage(shared, shared, 200, "text/html", bs_detail("Shared")),
        }
        with TemporaryDirectory() as raw:
            run = SharedCollectionPipeline(
                source_id=registered.pk,
                fetcher=Fetcher(pages),
                raw_store=RawObjectStore(raw),
                delay_seconds=0,
            ).collect(full_snapshot=True, acknowledge_automation_review=True)
        assert run.listing_total_discovered == run.details_fetched == 1

        conflict_pages = dict(pages)
        conflict_pages[("GET", learning_root)] = FetchedPage(
            learning_root,
            learning_root,
            200,
            "text/html",
            bs_listing(1, "Lehrstelle", ("4001", "Shared", "BVD")),
        )
        # The apprenticeship root resolves its relative detail below that root, hence a conflict.
        with (
            TemporaryDirectory() as raw,
            pytest.raises(CollectionPipelineError, match="conflicting detail URLs"),
        ):
            SharedCollectionPipeline(
                source_id=registered.pk,
                fetcher=Fetcher(conflict_pages),
                raw_store=RawObjectStore(raw),
                delay_seconds=0,
            ).collect(full_snapshot=True, acknowledge_automation_review=True)

    def test_basel_stadt_partial_surface_failure_has_no_lifecycle_evidence(self) -> None:
        registered = source("SRC-OFF-CANTON-BS", "BS_EMPLOYER_PORTAL")
        ordinary_root = BASEL_STADT_SURFACES[0][1]
        learning_root = BASEL_STADT_SURFACES[1][1]
        pages = {
            ("GET", ordinary_root): FetchedPage(
                ordinary_root,
                ordinary_root,
                200,
                "text/html",
                bs_listing(1, "Jobs", ("4001", "Techniker/in", "BVD")),
            ),
            ("GET", learning_root): FetchedPage(
                learning_root, learning_root, 200, "text/html", b"<html>malformed</html>"
            ),
        }
        with (
            TemporaryDirectory() as raw,
            pytest.raises(PlatformAdapterError, match="reported surface total"),
        ):
            SharedCollectionPipeline(
                source_id=registered.pk,
                fetcher=Fetcher(pages),
                raw_store=RawObjectStore(raw),
                delay_seconds=0,
            ).collect(full_snapshot=True, acknowledge_automation_review=True)
        run = CollectionRun.objects.get(source=registered)
        assert run.status == "FAILED" and run.snapshot_complete is False
        assert not PostingLifecycleEvent.objects.filter(posting__source=registered).exists()

    def test_basel_stadt_detail_failure_after_both_surfaces_never_adds_absence_evidence(
        self,
    ) -> None:
        registered = source("SRC-OFF-CANTON-BS", "BS_EMPLOYER_PORTAL")
        ordinary_root = BASEL_STADT_SURFACES[0][1]
        learning_root = BASEL_STADT_SURFACES[1][1]
        ordinary_detail = "https://stellenmarkt.bs.ch/kbs/job/details/4001"
        learning_detail = "https://stellenmarkt.bs.ch/kbs/lehrstellen/job/details/4002"
        pages = {
            ("GET", ordinary_root): FetchedPage(
                ordinary_root,
                ordinary_root,
                200,
                "text/html",
                bs_listing(1, "Jobs", ("4001", "Techniker/in", "BVD")),
            ),
            ("GET", learning_root): FetchedPage(
                learning_root,
                learning_root,
                200,
                "text/html",
                bs_listing(1, "Lehrstelle", ("4002", "GÃ¤rtner/in EFZ", "BVD")),
            ),
            ("GET", ordinary_detail): FetchedPage(
                ordinary_detail, ordinary_detail, 200, "text/html", bs_detail("Techniker/in")
            ),
            ("GET", learning_detail): FetchedPage(
                learning_detail, learning_detail, 200, "text/html", b"<html>malformed</html>"
            ),
        }
        fetcher = Fetcher(pages)
        with (
            TemporaryDirectory() as raw,
            pytest.raises(PlatformAdapterError, match="lacks title/description"),
        ):
            SharedCollectionPipeline(
                source_id=registered.pk,
                fetcher=fetcher,
                raw_store=RawObjectStore(raw),
                delay_seconds=0,
            ).collect(full_snapshot=True, acknowledge_automation_review=True)
        run = CollectionRun.objects.get(source=registered)
        assert run.status == "FAILED"
        assert run.source_health_status == "DEGRADED"
        assert run.snapshot_complete is False
        assert run.details_fetched == 2 and run.observations_created == 1
        assert not PostingLifecycleEvent.objects.filter(
            posting__source=registered,
            event_type__in=("DISAPPEARED_PENDING", "CLOSED_OBSERVED"),
        ).exists()
        assert [
            request.context["surface_name"]
            for request in fetcher.requests
            if request.role == "LISTING_PAGE"
        ] == ["ordinary", "apprenticeships"]

    def test_basel_stadt_empty_complete_source_is_healthy(self) -> None:
        registered = source("SRC-OFF-CANTON-BS", "BS_EMPLOYER_PORTAL")
        pages = {
            ("GET", url): FetchedPage(
                url,
                url,
                200,
                "text/html",
                bs_listing(0, "Jobs" if label == "ordinary" else "Lehrstellen"),
            )
            for label, url in BASEL_STADT_SURFACES
        }
        with TemporaryDirectory() as raw:
            run = SharedCollectionPipeline(
                source_id=registered.pk,
                fetcher=Fetcher(pages),
                raw_store=RawObjectStore(raw),
                delay_seconds=0,
            ).collect(full_snapshot=True, acknowledge_automation_review=True)
        assert run.status == "SUCCEEDED"
        assert run.source_health_status == "HEALTHY"
        assert run.snapshot_complete is True
        assert run.listing_total_discovered == 0
        assert run.observations_created == run.green_assessments_created == 0

    def test_adapter_calls_are_pure_and_only_implemented_origins_are_registered(self) -> None:
        before = {
            model: model.objects.count()
            for model in (
                Posting,
                PostingObservation,
                GreenRelevanceAssessment,
                PostingLifecycleEvent,
                Vacancy,
                PremiumSegmentAssessment,
                DashboardSnapshot,
                Day0ReadinessAssessment,
            )
        }
        registered = Source(source_id="SRC-OFF-JOBS-ADMIN", platform_family="FEDERAL_JOB_PORTAL")
        get_adapter(registered).initial_listing_request(registered)
        assert before == {model: model.objects.count() for model in before}

        expected = {
            "SRC-OFF-JOBS-ADMIN": {"jobs.admin.ch", "ohws.prospective.ch"},
            "SRC-OFF-CANTON-BS": {"www.bs.ch", "stellenmarkt.bs.ch"},
        }
        for source_id, hosts in expected.items():
            row = source(
                source_id,
                "FEDERAL_JOB_PORTAL" if source_id == "SRC-OFF-JOBS-ADMIN" else "BS_EMPLOYER_PORTAL",
            )
            ensure_default_endpoints(row)
            endpoints = SourceEndpoint.objects.filter(source=row)
            assert set(endpoints.values_list("host", flat=True)) == hosts
            assert all(
                endpoint.evidence["verification"] == "GATE-011C-2 live technical reconnaissance"
                for endpoint in endpoints
            )
        for blocked_id in (
            "SRC-OFF-CANTON-AG",
            "SRC-OFF-CANTON-BE",
        ):
            assert not SourceEndpoint.objects.filter(source_id=blocked_id).exists()
