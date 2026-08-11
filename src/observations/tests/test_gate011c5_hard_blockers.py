from __future__ import annotations

import html
import json
from tempfile import TemporaryDirectory

import pytest
from django.test import TestCase

from collectors.adapters import get_adapter
from collectors.governed_http import ensure_default_endpoints
from collectors.hard_blocker_adapters import (
    GLARUS_LISTING,
    SCHAFFHAUSEN_CANTON_LISTING,
    ST_GALLEN_CITY_API,
    GlarusUmantisAdapter,
    SchaffhausenCantonUmantisAdapter,
    StGallenCitySoliqueAdapter,
)
from collectors.pipeline import SharedCollectionPipeline
from collectors.platforms import (
    FetchedPage,
    FetchRequest,
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


def source(source_id: str, platform: str, *, family: str = "OFFICIAL_CANTON") -> Source:
    return Source.objects.create(
        source_id=source_id,
        source_name=source_id,
        domain="example.ch",
        source_family=family,
        source_type="DIRECT_PUBLIC_EMPLOYER",
        priority="P0",
        coverage_scope="required",
        canonicality="CANONICAL",
        platform_family=platform,
        access_method="WEB",
        automation_status="COLLECTOR_CANDIDATE",
        legal_review_status="AUTOMATION_REVIEW_REQUIRED",
        verification_status="VERIFIED",
        official_url="https://example.ch/",
    )


class Fetcher:
    def __init__(self, pages: dict[tuple[str, str], FetchedPage]) -> None:
        self.pages = pages
        self.requests: list[FetchRequest] = []

    def fetch_request(self, request: FetchRequest) -> FetchedPage:
        self.requests.append(request)
        return self.pages[(request.method, request.url)]

    def fetch(self, url: str) -> FetchedPage:
        return self.fetch_request(FetchRequest(url))


def umantis_listing(
    *,
    origin: str,
    table_number: str,
    page_size: int,
    page_number: int,
    total: int,
    entries: list[tuple[str, str]],
    next_page: int | None = None,
) -> bytes:
    start = (page_number - 1) * page_size + 1 if total else 1
    end = start + len(entries) - 1 if entries else 0
    state = {
        "TableNr": table_number,
        "TableCurrentPage": page_number,
        "TableMaxEntries": str(page_size),
        "TableFrom": start,
        "TableTo": end,
        "TableTotalLines": str(total),
        "NextLink": {
            "EnhancedUrl": (
                f"?tc{table_number}=p{next_page}&_search_token{table_number}=fixture"
                if next_page is not None
                else ""
            )
        },
    }
    rows = "".join(
        '<tr class="tableaslist_contentrow1"><td>'
        f'<a href="/Vacancies/{posting_id}/Description/1" '
        f'class="HSTableLinkSubTitle">{title}</a></td></tr>'
        for posting_id, title in entries
    )
    encoded = html.escape(json.dumps(state), quote=True)
    return (
        f'<div id="connectortable_1" data-one-item-chunk="{page_size}">'
        f'<table-navigation initial-data-string="{encoded}"></table-navigation>'
        f"<table>{rows}</table></div>"
    ).encode()


def umantis_detail(title: str) -> bytes:
    return (
        f'<meta property="og:title" content="{title}"><h1>{title}</h1>'
        "<main>Pflege von Garten- und Gr\u00fcnanlagen. Jetzt bewerben.</main>"
    ).encode()




class Gate011C5HardBlockerTests(TestCase):
    def test_exact_source_adapters_and_blocked_sources_remain_disabled(self) -> None:
        cases = (
            ("SRC-OFF-CANTON-GL", "UMANTIS_LINKED", GlarusUmantisAdapter),
            ("SRC-OFF-CANTON-SH", "OFFICIAL_WEB", SchaffhausenCantonUmantisAdapter),
            (
                "SRC-OFF-CITY-STGALLEN",
                "CITY_SG_PORTAL",
                StGallenCitySoliqueAdapter,
            ),
        )
        for source_id, platform, adapter_type in cases:
            assert isinstance(get_adapter(source(source_id, platform)), adapter_type)

        blocked = (
            ("SRC-OFF-CANTON-AG", "UMANTIS_LINKED"),
            ("SRC-OFF-CANTON-BE", "OFFICIAL_WEB"),
            ("SRC-OFF-CANTON-FR", "FR_MIGRATION_PORTAL"),
            ("SRC-OFF-CANTON-OW", "OFFICIAL_WEB"),
            ("SRC-OFF-CANTON-UR", "OFFICIAL_WEB"),
            ("SRC-OFF-CANTON-VS", "OFFICIAL_WEB"),
            ("SRC-OFF-CANTON-AI", "OFFICIAL_WEB"),
            ("SRC-OFF-CANTON-JU", "OFFICIAL_WEB"),
            ("SRC-OFF-CANTON-NW", "OFFICIAL_WEB"),
        )
        for source_id, platform in blocked:
            with pytest.raises(UnsupportedPlatformError):
                get_adapter(source(source_id, platform))

    def test_default_endpoints_only_promote_accepted_c5_sources(self) -> None:
        implemented = (
            ("SRC-OFF-CANTON-GL", "UMANTIS_LINKED"),
            ("SRC-OFF-CANTON-SH", "OFFICIAL_WEB"),
            ("SRC-OFF-CITY-STGALLEN", "CITY_SG_PORTAL"),
        )
        for source_id, platform in implemented:
            row = source(source_id, platform)
            ensure_default_endpoints(row)
            assert SourceEndpoint.objects.filter(source=row).exists()
            assert all(
                endpoint.evidence["decision"].endswith(
                    "0013-gate-011c5-hard-blocker-resolution-wave2.md"
                )
                for endpoint in SourceEndpoint.objects.filter(source=row)
            )
        for source_id in (
            "SRC-OFF-CANTON-AG",
            "SRC-OFF-CANTON-BE",
            "SRC-OFF-CANTON-FR",
            "SRC-OFF-CANTON-OW",
            "SRC-OFF-CANTON-UR",
            "SRC-OFF-CANTON-VS",
            "SRC-OFF-CANTON-AI",
            "SRC-OFF-CANTON-JU",
            "SRC-OFF-CANTON-NW",
        ):
            row = source(source_id, "BLOCKED")
            ensure_default_endpoints(row)
            assert not SourceEndpoint.objects.filter(source=row).exists()

    def test_glarus_umantis_exhausts_and_classifies_real_apprenticeship(self) -> None:
        registered = source("SRC-OFF-CANTON-GL", "UMANTIS_LINKED")
        entries = [
            ("101", "Sachbearbeiter/in"),
            ("102", "Lehrstelle G\u00e4rtner/in EFZ"),
        ]
        pages: dict[tuple[str, str], FetchedPage] = {
            ("GET", GLARUS_LISTING): FetchedPage(
                GLARUS_LISTING,
                GLARUS_LISTING,
                200,
                "text/html",
                umantis_listing(
                    origin="https://recruitingapp-2910.umantis.com",
                    table_number="1152481",
                    page_size=25,
                    page_number=1,
                    total=2,
                    entries=entries,
                ),
            )
        }
        for posting_id, title in entries:
            detail = f"https://recruitingapp-2910.umantis.com/Vacancies/{posting_id}/Description/1"
            pages[("GET", detail)] = FetchedPage(
                detail, detail, 200, "text/html", umantis_detail(title)
            )
        with TemporaryDirectory() as raw:
            run = SharedCollectionPipeline(
                source_id=registered.pk,
                fetcher=Fetcher(pages),
                raw_store=RawObjectStore(raw),
                delay_seconds=0,
            ).collect(full_snapshot=True, acknowledge_automation_review=True)
        assert run.status == "SUCCEEDED" and run.snapshot_complete
        assert run.listing_total_discovered == run.details_fetched == 2
        assert run.observations_created == run.green_assessments_created == 2
        assert GreenRelevanceAssessment.objects.filter(
            posting_observation__collection_run=run,
            posting_observation__source_posting_id="102",
            result="GREEN_CONFIRMED",
        ).exists()

    def test_schaffhausen_pagination_skip_fails_without_partial_truth(self) -> None:
        registered = source("SRC-OFF-CANTON-SH", "OFFICIAL_WEB")
        broken = umantis_listing(
            origin="https://recruitingapp-2876.umantis.com",
            table_number="66856",
            page_size=1,
            page_number=1,
            total=2,
            entries=[("201", "Ordinary")],
            next_page=3,
        )
        pages = {
            ("GET", SCHAFFHAUSEN_CANTON_LISTING): FetchedPage(
                SCHAFFHAUSEN_CANTON_LISTING,
                SCHAFFHAUSEN_CANTON_LISTING,
                200,
                "text/html",
                broken,
            )
        }
        with TemporaryDirectory() as raw, pytest.raises(PlatformAdapterError, match="skipped"):
            SharedCollectionPipeline(
                source_id=registered.pk,
                fetcher=Fetcher(pages),
                raw_store=RawObjectStore(raw),
                delay_seconds=0,
            ).collect(full_snapshot=True, acknowledge_automation_review=True)
        run = CollectionRun.objects.get(source=registered)
        assert run.status == "FAILED" and not run.snapshot_complete
        assert not Posting.objects.filter(source=registered).exists()
        assert not PostingLifecycleEvent.objects.filter(posting__source=registered).exists()

    def test_stadt_st_gallen_solique_unifies_jobs_apprenticeships_and_practica(self) -> None:
        registered = source(
            "SRC-OFF-CITY-STGALLEN", "CITY_SG_PORTAL", family="OFFICIAL_MUNICIPAL"
        )
        jobs = [
            {
                "title": {"id": "301", "value": "G\u00e4rtner/in Botanischer Garten"},
                "link": "jobs/Gaertner-in--301",
                "htmlContent": "Pflege von Garten- und Gr\u00fcnanlagen",
                "company": {"id": "ORG10", "value": "Stadt St.Gallen"},
                "position": {"id": "POS60", "value": "Unbefristete Stellen"},
            },
            {
                "title": {"id": "302", "value": "Lehrstelle Zeichner/in EFZ"},
                "link": "jobs/Lehrstelle--302",
                "htmlContent": "Ausbildung in der Stadtverwaltung",
                "company": {"id": "ORG10", "value": "Stadt St.Gallen"},
                "position": {"id": "POS40", "value": "Lernende"},
            },
            {
                "title": {"id": "303", "value": "Praktikum Umwelt"},
                "link": "jobs/Praktikum--303",
                "htmlContent": "Praktikum Umwelt und Energie",
                "company": {"id": "ORG20", "value": "St.Galler Stadtwerke"},
                "position": {"id": "POS50", "value": "Praktika"},
            },
        ]
        payload = {"filters": {"position": {"count": 3}}, "jobs": jobs}
        pages: dict[tuple[str, str], FetchedPage] = {
            ("GET", ST_GALLEN_CITY_API): FetchedPage(
                ST_GALLEN_CITY_API,
                ST_GALLEN_CITY_API,
                200,
                "application/json",
                json.dumps(payload).encode(),
            )
        }
        detail_titles = (
            "G\u00e4rtner/in Botanischer Garten",
            "Lehrstelle Zeichner/in EFZ",
            "Praktikum Umwelt",
        )
        for index, (job, detail_title) in enumerate(zip(jobs, detail_titles, strict=True)):
            detail = f"https://live.solique.ch/STSG/de/{job['link']}"
            pages[("GET", detail)] = FetchedPage(
                detail,
                detail,
                200,
                "text/html",
                (
                    f'<meta property="og:title" content="{detail_title}">'
                    + (
                        "<h1>G\u00e4rtner/in<br>Botanischer Garten</h1>"
                        if index == 0
                        else f"<h1>{detail_title}</h1>"
                    )
                    + "<main>official detail</main>"
                ).encode(),
            )
        with TemporaryDirectory() as raw_dir:
            run = SharedCollectionPipeline(
                source_id=registered.pk,
                fetcher=Fetcher(pages),
                raw_store=RawObjectStore(raw_dir),
                delay_seconds=0,
            ).collect(full_snapshot=True, acknowledge_automation_review=True)
        assert run.status == "SUCCEEDED" and run.snapshot_complete
        assert run.listing_total_discovered == run.details_fetched == 3
        assert run.observations_created == run.green_assessments_created == 3
        assert GreenRelevanceAssessment.objects.filter(
            posting_observation__collection_run=run,
            posting_observation__source_posting_id="301",
            result="GREEN_CONFIRMED",
        ).exists()

    def test_adapter_parsing_is_pure(self) -> None:
        registered = source("SRC-OFF-CANTON-GL", "UMANTIS_LINKED")
        adapter = GlarusUmantisAdapter()
        request = adapter.initial_listing_request(registered)
        adapter.parse_listing_page(
            FetchedPage(
                GLARUS_LISTING,
                GLARUS_LISTING,
                200,
                "text/html",
                umantis_listing(
                    origin="https://recruitingapp-2910.umantis.com",
                    table_number="1152481",
                    page_size=25,
                    page_number=1,
                    total=1,
                    entries=[("1", "Ordinary")],
                ),
            ),
            request,
            registered,
        )
        for model in (
            CollectionRun,
            Posting,
            PostingObservation,
            GreenRelevanceAssessment,
            PostingLifecycleEvent,
            Vacancy,
            PremiumSegmentAssessment,
            DashboardSnapshot,
            Day0ReadinessAssessment,
        ):
            assert model.objects.count() == 0
