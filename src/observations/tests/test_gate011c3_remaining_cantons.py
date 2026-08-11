from __future__ import annotations

import json
from datetime import UTC, datetime
from tempfile import TemporaryDirectory

import pytest
from django.test import TestCase

from collectors.adapters import get_adapter
from collectors.governed_http import ensure_default_endpoints
from collectors.pipeline import SharedCollectionPipeline
from collectors.platforms import (
    FetchedPage,
    FetchRequest,
    PlatformAdapterError,
    UnsupportedPlatformError,
)
from collectors.remaining_canton_adapters import (
    GRAUBUENDEN_NON_VACANCY_STAGE,
    GRAUBUENDEN_SURFACES,
    SCHWYZ_LISTING,
    SOLOTHURN_LISTING,
    GraubuendenReflineAdapter,
    SchwyzProspectiveAdapter,
    SolothurnProspectiveAdapter,
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


def refline_listing(*entries: tuple[str, str, str], empty: bool = False) -> bytes:
    links = "".join(
        f'<a href="https://apply.refline.ch/514915/{posting_id}/pub/{channel}/index.html">{title}</a>'
        for posting_id, channel, title in entries
    )
    empty_text = "Derzeit liegen keine Stellenausschreibungen vor" if empty else ""
    return (
        "<div>Stellentitel Amt Arbeitsort Anmeldefrist</div>"
        f"{links}{empty_text}<footer>powered by Refline</footer>"
    ).encode()


def prospective_listing(
    form_id: str,
    host: str,
    total: int | None,
    entries: list[tuple[str, str]],
    offsets: tuple[int, ...] = (),
) -> bytes:
    heading = f"<h1>{total} offene Stellen</h1>" if total is not None else ""
    links = "".join(
        f'<a class="job" title="{title}" '
        f'href="https://{host}/offene-stellen/{posting_id}/{posting_id}">'
        f"<h2>{title}</h2></a>"
        for posting_id, title in entries
    )
    pages = "".join(f'<a onclick="sendPagination({offset})"></a>' for offset in offsets)
    return f'<form id="{form_id}">{heading}{links}{pages}</form>'.encode()


def job_detail(
    title: str,
    *,
    date_posted: str = "2026-08-10",
    description: str = "Administration",
    canonical: str | None = None,
) -> bytes:
    canonical_link = f'<link rel="canonical" href="{canonical}">' if canonical else ""
    payload = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": title,
        "datePosted": date_posted,
        "description": description,
        "hiringOrganization": {"name": "Kanton"},
        "jobLocation": {
            "address": {
                "addressCountry": "CH",
                "addressLocality": "Chur",
                "addressRegion": "GR",
            }
        },
    }
    return (
        canonical_link + '<script type="application/ld+json">' + json.dumps(payload) + "</script>"
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


class Gate011C3Tests(TestCase):
    def test_exact_source_authorization_and_all_blocked_sources_stay_disabled(self) -> None:
        expected = (
            ("SRC-OFF-CANTON-GR", "CANTON_GR_PORTAL", GraubuendenReflineAdapter),
            ("SRC-OFF-CANTON-SO", "CANTON_SO_PORTAL", SolothurnProspectiveAdapter),
            ("SRC-OFF-CANTON-SZ", "CANTON_SZ_PORTAL", SchwyzProspectiveAdapter),
        )
        for source_id, platform, adapter_type in expected:
            registered = Source(source_id=source_id, platform_family=platform)
            assert isinstance(get_adapter(registered), adapter_type)
            with pytest.raises(UnsupportedPlatformError):
                get_adapter(Source(source_id="SRC-UNAUTHORIZED", platform_family=platform))
        blocked = (
            ("SRC-OFF-CANTON-AI", "OFFICIAL_WEB"),
            ("SRC-OFF-CANTON-FR", "FR_MIGRATION_PORTAL"),
            ("SRC-OFF-CANTON-JU", "OFFICIAL_WEB"),
            ("SRC-OFF-CANTON-NW", "CANTON_NW_PORTAL"),
            ("SRC-OFF-CANTON-OW", "OFFICIAL_WEB"),
            ("SRC-OFF-CANTON-UR", "OFFICIAL_WEB"),
            ("SRC-OFF-CANTON-VS", "OFFICIAL_WEB"),
            ("SRC-OFF-CANTON-AG", "CANTON_AG_PORTAL"),
            ("SRC-OFF-CANTON-BE", "SITES_BE"),
        )
        for source_id, platform in blocked:
            with pytest.raises(UnsupportedPlatformError):
                get_adapter(Source(source_id=source_id, platform_family=platform))

    def test_graubuenden_full_source_visits_all_surfaces_and_classifies_apprentice(self) -> None:
        registered = source("SRC-OFF-CANTON-GR", "CANTON_GR_PORTAL")
        ordinary_url = "https://apply.refline.ch/514915/1001/pub/1/index.html"
        apprentice_url = "https://apply.refline.ch/514915/1002/pub/1/index.html"
        trial_url = "https://apply.refline.ch/514915/1003/pub/1/index.html"
        pages = {
            ("GET", GRAUBUENDEN_SURFACES[0][1]): FetchedPage(
                GRAUBUENDEN_SURFACES[0][1],
                GRAUBUENDEN_SURFACES[0][1],
                200,
                "text/html",
                refline_listing(("1001", "1", "Sachbearbeiter/in")),
            ),
            ("GET", GRAUBUENDEN_SURFACES[1][1]): FetchedPage(
                GRAUBUENDEN_SURFACES[1][1],
                GRAUBUENDEN_SURFACES[1][1],
                200,
                "text/html",
                refline_listing(("1002", "1", "Lehrstelle Gärtner/in EFZ")),
            ),
            ("GET", GRAUBUENDEN_NON_VACANCY_STAGE): FetchedPage(
                GRAUBUENDEN_NON_VACANCY_STAGE,
                GRAUBUENDEN_NON_VACANCY_STAGE,
                200,
                "text/html",
                refline_listing(("1003", "1", "Schnupperlehre Gärtner/in EFZ")),
            ),
            ("GET", ordinary_url): FetchedPage(
                ordinary_url,
                ordinary_url,
                200,
                "text/html",
                job_detail("Sachbearbeiter/in", date_posted="2026-08-10T10:11:12+00:00"),
            ),
            ("GET", apprentice_url): FetchedPage(
                apprentice_url,
                apprentice_url,
                200,
                "text/html",
                job_detail("Lehrstelle Gärtner/in EFZ", description="Pflege von Grünanlagen"),
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
        assert run.status == "SUCCEEDED" and run.source_health_status == "HEALTHY"
        assert run.snapshot_complete and run.listing_total_discovered == run.details_fetched == 2
        assert run.observations_created == run.green_assessments_created == 2
        assert (
            GreenRelevanceAssessment.objects.filter(
                posting_observation__collection_run=run, result="GREEN_CONFIRMED"
            ).count()
            == 1
        )
        assert [
            request.context["surface_name"]
            for request in fetcher.requests
            if request.role == "LISTING_PAGE"
        ] == ["ordinary", "apprenticeships"]
        assert all(request.url != GRAUBUENDEN_NON_VACANCY_STAGE for request in fetcher.requests)
        assert not Posting.objects.filter(source=registered, source_posting_id="1003").exists()
        assert not PostingObservation.objects.filter(
            source=registered, source_posting_id="1003"
        ).exists()
        assert not GreenRelevanceAssessment.objects.filter(
            posting_observation__source=registered,
            posting_observation__source_posting_id="1003",
        ).exists()
        assert trial_url not in {
            observation.canonical_url
            for observation in PostingObservation.objects.filter(source=registered)
        }
        first = PostingObservation.objects.get(source_posting_id="1001")
        assert first.contract_payload["published_at_precision"] == "EXACT_DATETIME"

    def test_graubuenden_broken_secondary_surface_fails_without_negative_lifecycle(self) -> None:
        registered = source("SRC-OFF-CANTON-GR", "CANTON_GR_PORTAL")
        pages = {
            ("GET", GRAUBUENDEN_SURFACES[0][1]): FetchedPage(
                GRAUBUENDEN_SURFACES[0][1],
                GRAUBUENDEN_SURFACES[0][1],
                200,
                "text/html",
                refline_listing(("1001", "1", "Ordinary")),
            ),
            ("GET", GRAUBUENDEN_SURFACES[1][1]): FetchedPage(
                GRAUBUENDEN_SURFACES[1][1],
                GRAUBUENDEN_SURFACES[1][1],
                200,
                "text/html",
                b"<html>broken</html>",
            ),
        }
        with (
            TemporaryDirectory() as raw,
            pytest.raises(PlatformAdapterError, match="contract marker"),
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

    def test_graubuenden_cross_surface_duplicate_collapses_and_conflict_fails(self) -> None:
        registered = source("SRC-OFF-CANTON-GR", "CANTON_GR_PORTAL")
        detail = "https://apply.refline.ch/514915/1001/pub/1/index.html"
        pages = {
            ("GET", GRAUBUENDEN_SURFACES[0][1]): FetchedPage(
                GRAUBUENDEN_SURFACES[0][1],
                GRAUBUENDEN_SURFACES[0][1],
                200,
                "text/html",
                refline_listing(("1001", "1", "Shared")),
            ),
            ("GET", GRAUBUENDEN_SURFACES[1][1]): FetchedPage(
                GRAUBUENDEN_SURFACES[1][1],
                GRAUBUENDEN_SURFACES[1][1],
                200,
                "text/html",
                refline_listing(("1001", "1", "Shared")),
            ),
            ("GET", detail): FetchedPage(detail, detail, 200, "text/html", job_detail("Shared")),
        }
        with TemporaryDirectory() as raw:
            run = SharedCollectionPipeline(
                source_id=registered.pk,
                fetcher=Fetcher(pages),
                raw_store=RawObjectStore(raw),
                delay_seconds=0,
            ).collect(full_snapshot=True, acknowledge_automation_review=True)
        assert run.listing_total_discovered == run.details_fetched == 1

        conflicting = dict(pages)
        conflicting[("GET", GRAUBUENDEN_SURFACES[1][1])] = FetchedPage(
            GRAUBUENDEN_SURFACES[1][1],
            GRAUBUENDEN_SURFACES[1][1],
            200,
            "text/html",
            refline_listing(("1001", "2", "Shared")),
        )
        with TemporaryDirectory() as raw, pytest.raises(Exception, match="conflicting detail URLs"):
            SharedCollectionPipeline(
                source_id=registered.pk,
                fetcher=Fetcher(conflicting),
                raw_store=RawObjectStore(raw),
                delay_seconds=0,
            ).collect(full_snapshot=True, acknowledge_automation_review=True)

    def test_solothurn_requires_reported_total_and_reaches_details(self) -> None:
        registered = source("SRC-OFF-CANTON-SO", "CANTON_SO_PORTAL")
        posting_id = "11111111-1111-4111-8111-111111111111"
        detail = f"https://job.so.ch/offene-stellen/{posting_id}/{posting_id}"
        pages = {
            ("GET", SOLOTHURN_LISTING): FetchedPage(
                SOLOTHURN_LISTING,
                SOLOTHURN_LISTING,
                200,
                "text/html",
                prospective_listing(
                    "careercenter-form", "job.so.ch", 1, [(posting_id, "Lehrstelle Gärtner/in")]
                ),
            ),
            ("GET", detail): FetchedPage(
                detail,
                detail,
                200,
                "text/html",
                job_detail(
                    "Lehrstelle Gärtner/in", canonical=detail, description="Garten- und Grünpflege"
                ),
            ),
        }
        with TemporaryDirectory() as raw:
            run = SharedCollectionPipeline(
                source_id=registered.pk,
                fetcher=Fetcher(pages),
                raw_store=RawObjectStore(raw),
                delay_seconds=0,
            ).collect(full_snapshot=True, acknowledge_automation_review=True)
        assert run.snapshot_complete and run.listing_total_discovered == run.details_fetched == 1
        bad = get_adapter(registered)
        request = bad.initial_listing_request(registered)
        with (
            TemporaryDirectory() as raw,
            pytest.raises(Exception, match="reported total"),
        ):
            SharedCollectionPipeline(
                source_id=registered.pk,
                fetcher=Fetcher(
                    {
                        ("GET", SOLOTHURN_LISTING): FetchedPage(
                            SOLOTHURN_LISTING,
                            SOLOTHURN_LISTING,
                            200,
                            "text/html",
                            prospective_listing(
                                "careercenter-form",
                                "job.so.ch",
                                2,
                                [(posting_id, "One")],
                            ),
                        )
                    }
                ),
                raw_store=RawObjectStore(raw),
                delay_seconds=0,
            ).collect(full_snapshot=True, acknowledge_automation_review=True)
        assert request.context["surface_name"] == "unified"

    def test_schwyz_pagination_requires_exact_progression(self) -> None:
        registered = Source(source_id="SRC-OFF-CANTON-SZ", platform_family="CANTON_SZ_PORTAL")
        adapter = SchwyzProspectiveAdapter()
        first = adapter.initial_listing_request(registered)
        identifier = "22222222-2222-4222-8222-222222222222"
        parsed = adapter.parse_listing_page(
            FetchedPage(
                SCHWYZ_LISTING,
                SCHWYZ_LISTING,
                200,
                "text/html",
                prospective_listing("oh-form", "jobs.sz.ch", None, [(identifier, "First")], (0, 8)),
            ),
            first,
            registered,
        )
        assert parsed.next_request is not None
        assert parsed.next_request.method == "POST"
        assert parsed.next_request.context["offset"] == 8
        with pytest.raises(PlatformAdapterError, match="monotonically"):
            adapter.parse_listing_page(
                FetchedPage(
                    SCHWYZ_LISTING,
                    SCHWYZ_LISTING,
                    200,
                    "text/html",
                    prospective_listing(
                        "oh-form", "jobs.sz.ch", None, [(identifier, "First")], (0, 16)
                    ),
                ),
                first,
                registered,
            )

    def test_schwyz_unified_feed_sends_apprenticeship_to_green_classifier(self) -> None:
        registered = source("SRC-OFF-CANTON-SZ", "CANTON_SZ_PORTAL")
        ordinary_id = "22222222-2222-4222-8222-222222222222"
        learning_id = "33333333-3333-4333-8333-333333333333"
        ordinary_detail = f"https://jobs.sz.ch/offene-stellen/{ordinary_id}/{ordinary_id}"
        learning_detail = f"https://jobs.sz.ch/offene-stellen/{learning_id}/{learning_id}"
        pages = {
            ("GET", SCHWYZ_LISTING): FetchedPage(
                SCHWYZ_LISTING,
                SCHWYZ_LISTING,
                200,
                "text/html",
                prospective_listing(
                    "oh-form",
                    "jobs.sz.ch",
                    None,
                    [(ordinary_id, "Administration")],
                    (0, 8),
                ),
            ),
            ("POST", SCHWYZ_LISTING): FetchedPage(
                SCHWYZ_LISTING,
                SCHWYZ_LISTING,
                200,
                "text/html",
                prospective_listing(
                    "oh-form",
                    "jobs.sz.ch",
                    None,
                    [(learning_id, "Lehrstelle Gärtner/in EFZ")],
                    (0, 8),
                ),
            ),
            ("GET", ordinary_detail): FetchedPage(
                ordinary_detail,
                ordinary_detail,
                200,
                "text/html",
                job_detail("Administration"),
            ),
            ("GET", learning_detail): FetchedPage(
                learning_detail,
                learning_detail,
                200,
                "text/html",
                job_detail(
                    "Lehrstelle Gärtner/in EFZ",
                    description="Pflege von Garten- und Grünanlagen",
                ),
            ),
        }
        fetcher = Fetcher(pages)
        with TemporaryDirectory() as raw:
            run = SharedCollectionPipeline(
                source_id=registered.pk,
                fetcher=fetcher,
                raw_store=RawObjectStore(raw),
                delay_seconds=0,
            ).collect(full_snapshot=True, acknowledge_automation_review=True)
        assert run.listing_total_discovered == run.details_fetched == 2
        assert (
            GreenRelevanceAssessment.objects.filter(
                posting_observation__collection_run=run,
                result="GREEN_CONFIRMED",
            ).count()
            == 1
        )
        assert [request.method for request in fetcher.requests[:2]] == ["GET", "POST"]

    def test_adapter_purity_endpoints_and_blocked_isolation(self) -> None:
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
        registered = Source(source_id="SRC-OFF-CANTON-GR", platform_family="CANTON_GR_PORTAL")
        get_adapter(registered).initial_listing_request(registered)
        assert before == {model: model.objects.count() for model in before}
        for source_id, platform, hosts in (
            ("SRC-OFF-CANTON-GR", "CANTON_GR_PORTAL", {"stellen.gr.ch", "apply.refline.ch"}),
            ("SRC-OFF-CANTON-SO", "CANTON_SO_PORTAL", {"job.so.ch"}),
            ("SRC-OFF-CANTON-SZ", "CANTON_SZ_PORTAL", {"jobs.sz.ch"}),
        ):
            row = source(source_id, platform)
            if source_id == "SRC-OFF-CANTON-GR":
                SourceEndpoint.objects.create(
                    source=row,
                    endpoint_role="LISTING",
                    platform_family=platform,
                    host="apply.refline.ch",
                    base_url=GRAUBUENDEN_NON_VACANCY_STAGE,
                )
            ensure_default_endpoints(row)
            endpoints = SourceEndpoint.objects.filter(source=row)
            assert set(endpoints.values_list("host", flat=True)) == hosts
            assert not endpoints.filter(base_url=GRAUBUENDEN_NON_VACANCY_STAGE).exists()
            assert all(
                endpoint.evidence["verification"] == "GATE-011C-3 live technical reconnaissance"
                for endpoint in endpoints
            )
        for blocked_id in (
            "SRC-OFF-CANTON-AI",
            "SRC-OFF-CANTON-FR",
            "SRC-OFF-CANTON-GL",
            "SRC-OFF-CANTON-JU",
            "SRC-OFF-CANTON-NW",
            "SRC-OFF-CANTON-OW",
            "SRC-OFF-CANTON-SH",
            "SRC-OFF-CANTON-UR",
            "SRC-OFF-CANTON-VS",
            "SRC-OFF-JOBROOM",
            "SRC-OFF-JOBROOM-API",
            "SRC-OFF-CITY-STGALLEN",
        ):
            assert not SourceEndpoint.objects.filter(source_id=blocked_id).exists()
