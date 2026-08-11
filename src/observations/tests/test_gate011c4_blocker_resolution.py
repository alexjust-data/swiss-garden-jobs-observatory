from __future__ import annotations

import html
import json
from datetime import UTC, datetime
from tempfile import TemporaryDirectory

import pytest
from django.test import TestCase

from collectors.adapters import get_adapter
from collectors.blocker_resolution_adapters import (
    LUZERN_CANTON_SURFACES,
    ST_GALLEN_LISTING,
    THURGAU_LISTING,
    LuzernCantonReflineAdapter,
    StGallenCantonUmantisAdapter,
    ThurgauCantonProspectiveAdapter,
)
from collectors.governed_http import ensure_default_endpoints
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


def source(source_id: str, platform: str) -> Source:
    return Source.objects.create(
        source_id=source_id,
        source_name=source_id,
        domain="example.ch",
        source_family="OFFICIAL_CANTON",
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


class Fetcher:
    def __init__(self, pages: dict[tuple[str, str], FetchedPage]) -> None:
        self.pages = pages
        self.requests: list[FetchRequest] = []

    def fetch_request(self, request: FetchRequest) -> FetchedPage:
        self.requests.append(request)
        return self.pages[(request.method, request.url)]

    def fetch(self, url: str) -> FetchedPage:
        return self.fetch_request(FetchRequest(url))


def job_detail(
    title: str,
    *,
    description: str = "Administration",
    locality: str = "Luzern",
    region: str = "LU",
) -> bytes:
    payload = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": title,
        "datePosted": "2026-08-10",
        "description": description,
        "hiringOrganization": {"name": "Kanton"},
        "jobLocation": {
            "address": {
                "addressCountry": "CH",
                "addressLocality": locality,
                "addressRegion": region,
            }
        },
    }
    return ('<script type="application/ld+json">' + json.dumps(payload) + "</script>").encode()


def luzern_listing(*entries: tuple[str, str, str], empty: bool = False) -> bytes:
    links = "".join(
        f'<a href="https://apply.refline.ch/891537/{posting_id}/pub/{channel}/index.html">'
        f"{title}</a>"
        for posting_id, channel, title in entries
    )
    empty_text = "Derzeit liegen keine Stellenausschreibungen vor" if empty else ""
    return f"<div>Kanton Luzern Stelle Pensum</div>{links}{empty_text}".encode()


def luzern_apprenticeship_listing(*rows: dict[str, object]) -> bytes:
    return json.dumps({"total": len(rows), "rows": rows}).encode()


def luzern_apprenticeship_detail(
    profile_id: str,
    *,
    free: bool,
    trial: bool,
    link_job: str | None,
    title: str = "Gärtner/in EFZ",
) -> bytes:
    return json.dumps(
        {
            "id": profile_id,
            "free": free,
            "trial": trial,
            "link_job": link_job,
            "description": "Pflege von Garten- und Grünanlagen",
            "updated_at": "2026-08-06T11:55:01.000000Z",
            "type": {"id": 1, "title": title},
            "location": {
                "id": 1,
                "title": "Dienststelle Landwirtschaft und Wald",
                "zip": 6210,
                "city": "Sursee",
            },
        },
        ensure_ascii=False,
    ).encode()


def umantis_listing(
    page_number: int,
    total: int | None,
    entries: list[tuple[str, str, str, str]],
) -> bytes:
    start = (page_number - 1) * 25 + 1
    end = start + len(entries) - 1
    next_url = f"?tc1152481=p{page_number + 1}&_search_token1152481=test"
    live_value = (lambda value: str(value)) if page_number > 1 else (lambda value: value)
    state = {
        "TableCurrentPage": live_value(page_number),
        "TableFrom": live_value(start),
        "TableTo": live_value(end),
        "TableTotalLines": live_value(total) if total is not None else None,
        "NextLink": {"EnhancedUrl": next_url},
    }
    rows = "".join(
        (
            '<tr class="tableaslist_contentrow1"><td><div>'
            '<span class="tableaslist_subtitle tableaslist_element_1152488">'
            f'<a href="/Vacancies/{posting_id}/Description/1" '
            f'class="HSTableLinkSubTitle">{title}</a></span>'
            '<span class="tableaslist_subtitle tableaslist_element_1152491">'
            " | Art: Vollzeit</span>"
            '<span class="tableaslist_subtitle tableaslist_element_1152494">'
            f" {organization}</span>"
            '<span class="tableaslist_subtitle tableaslist_element_1152495">'
            f" {location}</span></div></td></tr>"
        )
        for posting_id, title, organization, location in entries
    )
    encoded = html.escape(json.dumps(state), quote=True)
    return (
        '<div id="connectortable_1" data-one-item-chunk="25">'
        f'<table-navigation initial-data-string="{encoded}"></table-navigation>'
        f"<table>{rows}</table></div>"
    ).encode()


def umantis_detail(title: str, *, location: str = "St.Gallen") -> bytes:
    return (
        f'<meta property="og:title" content="{title}">'
        f"<h1>{title}</h1><p>Pensum: 100% Arbeitsort: {location}</p>"
        "<h2>Was Sie erwartet</h2><p>Pflege von Grünanlagen und Gartenflächen.</p>"
    ).encode()


def thurgau_listing(
    total: int | None,
    entries: list[tuple[str, str]],
    *,
    include_external_filter: bool = True,
    next_page: int | None = None,
) -> bytes:
    heading = f"<h1>Offene Stellen: {total}</h1>" if total is not None else ""
    option = (
        '<select><option value="28">Externe Institutionen</option></select>'
        if include_external_filter
        else ""
    )
    links = "".join(
        '<h2 class="mod-entry-title">'
        f'<a href="https://ohws.prospective.ch/public/v1/jobs/{posting_id}">{title}</a>'
        "</h2>"
        for posting_id, title in entries
    )
    next_link = (
        f'<a href="https://stellen.tg.ch/stellen.html/1917/pjobpage/{next_page}">weiter</a>'
        if next_page is not None
        else ""
    )
    return f"{heading}{option}{links}{next_link}".encode()


class Gate011C4Tests(TestCase):
    def test_exact_source_authorization_endpoints_and_blocked_isolation(self) -> None:
        expected = (
            ("SRC-OFF-CANTON-LU", "CANTON_LU_PORTAL", LuzernCantonReflineAdapter),
            ("SRC-OFF-CANTON-SG", "CANTON_SG_PORTAL", StGallenCantonUmantisAdapter),
            ("SRC-OFF-CANTON-TG", "CANTON_TG_PORTAL", ThurgauCantonProspectiveAdapter),
        )
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
        for source_id, platform, adapter_type in expected:
            transient = Source(source_id=source_id, platform_family=platform)
            assert isinstance(get_adapter(transient), adapter_type)
            with pytest.raises(UnsupportedPlatformError):
                get_adapter(Source(source_id="SRC-UNAUTHORIZED", platform_family=platform))
            get_adapter(transient).initial_listing_request(transient)
            row = source(source_id, platform)
            ensure_default_endpoints(row)
            assert all(
                endpoint.evidence["verification"] == "GATE-011C-4 live technical reconnaissance"
                for endpoint in SourceEndpoint.objects.filter(source=row)
            )
        assert before == {model: model.objects.count() for model in before}
        assert set(
            SourceEndpoint.objects.filter(source_id="SRC-OFF-CANTON-LU").values_list(
                "host", flat=True
            )
        ) == {"stellen.lu.ch", "apply.refline.ch", "lehre.lu"}
        assert set(
            SourceEndpoint.objects.filter(source_id="SRC-OFF-CANTON-SG").values_list(
                "host", flat=True
            )
        ) == {"www.sg.ch", "recruitingapp-2800.umantis.com"}
        assert set(
            SourceEndpoint.objects.filter(source_id="SRC-OFF-CANTON-TG").values_list(
                "host", flat=True
            )
        ) == {"stellen.tg.ch", "ohws.prospective.ch"}
        assert not SourceEndpoint.objects.filter(host="lernende.tg.ch").exists()
        for blocked in (
            "SRC-OFF-CANTON-AI",
            "SRC-OFF-CANTON-JU",
            "SRC-OFF-CANTON-NW",
            "SRC-OFF-CANTON-AG",
            "SRC-OFF-CANTON-BE",
            "SRC-OFF-CANTON-FR",
            "SRC-OFF-CANTON-GL",
            "SRC-OFF-CANTON-OW",
            "SRC-OFF-CANTON-SH",
            "SRC-OFF-CANTON-UR",
            "SRC-OFF-CANTON-VS",
            "SRC-OFF-CITY-STGALLEN",
            "SRC-OFF-JOBROOM",
            "SRC-OFF-JOBROOM-API",
        ):
            assert not SourceEndpoint.objects.filter(source_id=blocked).exists()

    def test_luzern_full_source_admits_open_apprenticeship_only(self) -> None:
        registered = source("SRC-OFF-CANTON-LU", "CANTON_LU_PORTAL")
        ordinary_url = "https://apply.refline.ch/891537/7001/pub/1/index.html"
        teacher_url = "https://apply.refline.ch/891537/7002/pub/1/index.html"
        open_profile = "gaertner-in-efz-101"
        open_detail = f"{LUZERN_CANTON_SURFACES[2][1]}/{open_profile}"
        pages = {
            ("GET", LUZERN_CANTON_SURFACES[0][1]): FetchedPage(
                LUZERN_CANTON_SURFACES[0][1],
                LUZERN_CANTON_SURFACES[0][1],
                200,
                "text/html",
                luzern_listing(("7001", "1", "Sachbearbeiter/in")),
            ),
            ("GET", LUZERN_CANTON_SURFACES[1][1]): FetchedPage(
                LUZERN_CANTON_SURFACES[1][1],
                LUZERN_CANTON_SURFACES[1][1],
                200,
                "text/html",
                luzern_listing(("7002", "1", "Lehrperson Sekundarstufe")),
            ),
            ("GET", LUZERN_CANTON_SURFACES[2][1]): FetchedPage(
                LUZERN_CANTON_SURFACES[2][1],
                LUZERN_CANTON_SURFACES[2][1],
                200,
                "application/json",
                luzern_apprenticeship_listing(
                    {"id": open_profile, "title": "Gärtner/in EFZ", "free": True},
                    {
                        "id": "evergreen-inactive-102",
                        "title": "Gärtner/in EFZ",
                        "free": False,
                    },
                    {
                        "id": "schnupper-only-103",
                        "title": "Gärtner/in EFZ",
                        "free": False,
                        "trial": True,
                    },
                ),
            ),
            ("GET", ordinary_url): FetchedPage(
                ordinary_url,
                ordinary_url,
                200,
                "text/html",
                job_detail("Sachbearbeiter/in"),
            ),
            ("GET", teacher_url): FetchedPage(
                teacher_url,
                teacher_url,
                200,
                "text/html",
                job_detail("Lehrperson Sekundarstufe"),
            ),
            ("GET", open_detail): FetchedPage(
                open_detail,
                open_detail,
                200,
                "application/json",
                luzern_apprenticeship_detail(
                    open_profile,
                    free=True,
                    trial=True,
                    link_job="https://apply.refline.ch/891537/0306/",
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
                clock=lambda: datetime(2026, 8, 11, 10, tzinfo=UTC),
            ).collect(full_snapshot=True, acknowledge_automation_review=True)
        assert run.snapshot_complete and run.status == "SUCCEEDED"
        assert run.listing_total_discovered == run.details_fetched == 3
        assert run.observations_created == run.green_assessments_created == 3
        assert (
            GreenRelevanceAssessment.objects.filter(
                posting_observation__collection_run=run,
                result="GREEN_CONFIRMED",
            ).count()
            == 1
        )
        assert Posting.objects.filter(
            source=registered,
            source_posting_id=f"lehre:{open_profile}",
        ).exists()
        assert not Posting.objects.filter(source_posting_id__contains="inactive").exists()
        assert not Posting.objects.filter(source_posting_id__contains="schnupper").exists()
        apprenticeship = PostingObservation.objects.get(
            posting__source_posting_id=f"lehre:{open_profile}"
        )
        assert apprenticeship.canonical_url == f"https://lehre.lu/map/{open_profile}"
        assert apprenticeship.source_posting_id == f"lehre:{open_profile}"
        assert apprenticeship.location_locality == "Sursee"
        assert apprenticeship.location_postal_code == "6210"
        assert apprenticeship.location_region == ""
        assert apprenticeship.location_country == "CH"
        assert apprenticeship.contract_payload["source_published_at"] is None
        assert apprenticeship.contract_payload["source_updated_at"].startswith("2026-08-06")
        assert apprenticeship.structured_payload["vacancy_boundary"] == {
            "active": True,
            "application_id": "0306",
            "profile_is_evergreen": True,
            "schnupper_content_promoted": False,
        }

    def test_luzern_secondary_failure_has_no_negative_lifecycle(self) -> None:
        registered = source("SRC-OFF-CANTON-LU", "CANTON_LU_PORTAL")
        pages = {
            ("GET", LUZERN_CANTON_SURFACES[0][1]): FetchedPage(
                LUZERN_CANTON_SURFACES[0][1],
                LUZERN_CANTON_SURFACES[0][1],
                200,
                "text/html",
                luzern_listing(("7001", "1", "Ordinary")),
            ),
            ("GET", LUZERN_CANTON_SURFACES[1][1]): FetchedPage(
                LUZERN_CANTON_SURFACES[1][1],
                LUZERN_CANTON_SURFACES[1][1],
                200,
                "text/html",
                luzern_listing(empty=True),
            ),
            ("GET", LUZERN_CANTON_SURFACES[2][1]): FetchedPage(
                LUZERN_CANTON_SURFACES[2][1],
                LUZERN_CANTON_SURFACES[2][1],
                200,
                "application/json",
                b"{broken",
            ),
        }
        with (
            TemporaryDirectory() as raw,
            pytest.raises(PlatformAdapterError, match="invalid JSON"),
        ):
            SharedCollectionPipeline(
                source_id=registered.pk,
                fetcher=Fetcher(pages),
                raw_store=RawObjectStore(raw),
                delay_seconds=0,
            ).collect(full_snapshot=True, acknowledge_automation_review=True)
        run = CollectionRun.objects.get(source=registered)
        assert run.status == "FAILED" and not run.snapshot_complete
        assert not PostingLifecycleEvent.objects.filter(posting__source=registered).exists()

    def test_luzern_duplicate_collapses_and_conflicting_detail_fails_closed(self) -> None:
        registered = source("SRC-OFF-CANTON-LU", "CANTON_LU_PORTAL")
        detail = "https://apply.refline.ch/891537/7001/pub/1/index.html"
        pages = {
            ("GET", LUZERN_CANTON_SURFACES[0][1]): FetchedPage(
                LUZERN_CANTON_SURFACES[0][1],
                LUZERN_CANTON_SURFACES[0][1],
                200,
                "text/html",
                luzern_listing(("7001", "1", "Shared")),
            ),
            ("GET", LUZERN_CANTON_SURFACES[1][1]): FetchedPage(
                LUZERN_CANTON_SURFACES[1][1],
                LUZERN_CANTON_SURFACES[1][1],
                200,
                "text/html",
                luzern_listing(("7001", "1", "Shared")),
            ),
            ("GET", detail): FetchedPage(detail, detail, 200, "text/html", job_detail("Shared")),
            ("GET", LUZERN_CANTON_SURFACES[2][1]): FetchedPage(
                LUZERN_CANTON_SURFACES[2][1],
                LUZERN_CANTON_SURFACES[2][1],
                200,
                "application/json",
                luzern_apprenticeship_listing(),
            ),
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
        conflicting[("GET", LUZERN_CANTON_SURFACES[1][1])] = FetchedPage(
            LUZERN_CANTON_SURFACES[1][1],
            LUZERN_CANTON_SURFACES[1][1],
            200,
            "text/html",
            luzern_listing(("7001", "2", "Shared")),
        )
        with TemporaryDirectory() as raw, pytest.raises(Exception, match="conflicting detail URLs"):
            SharedCollectionPipeline(
                source_id=registered.pk,
                fetcher=Fetcher(conflicting),
                raw_store=RawObjectStore(raw),
                delay_seconds=0,
            ).collect(full_snapshot=True, acknowledge_automation_review=True)

    def test_st_gallen_exhausts_unified_umantis_and_classifies_apprentice(self) -> None:
        registered = source("SRC-OFF-CANTON-SG", "CANTON_SG_PORTAL")
        first_entries = [
            (str(8000 + index), f"Ordinary {index}", "Bau- und Umweltdepartement", "St.Gallen")
            for index in range(25)
        ]
        final_entry = ("9001", "Lehrstelle Gärtner/in EFZ", "Volkswirtschaftsdepartement", "Salez")
        next_url = (
            "https://recruitingapp-2800.umantis.com/Jobs/All?tc1152481=p2&_search_token1152481=test"
        )
        pages: dict[tuple[str, str], FetchedPage] = {
            ("GET", ST_GALLEN_LISTING): FetchedPage(
                ST_GALLEN_LISTING,
                ST_GALLEN_LISTING,
                200,
                "text/html",
                umantis_listing(1, 26, first_entries),
            ),
            ("GET", next_url): FetchedPage(
                next_url,
                next_url,
                200,
                "text/html",
                umantis_listing(2, 26, [final_entry]),
            ),
        }
        for posting_id, title, _, location in [*first_entries, final_entry]:
            detail = f"https://recruitingapp-2800.umantis.com/Vacancies/{posting_id}/Description/1"
            pages[("GET", detail)] = FetchedPage(
                detail,
                detail,
                200,
                "text/html",
                umantis_detail(title, location=location),
            )
        fetcher = Fetcher(pages)
        with TemporaryDirectory() as raw:
            run = SharedCollectionPipeline(
                source_id=registered.pk,
                fetcher=fetcher,
                raw_store=RawObjectStore(raw),
                delay_seconds=0,
            ).collect(full_snapshot=True, acknowledge_automation_review=True)
        assert run.status == "SUCCEEDED" and run.snapshot_complete
        assert run.listing_total_discovered == run.details_fetched == 26
        assert run.observations_created == run.green_assessments_created == 26
        assert (
            GreenRelevanceAssessment.objects.filter(
                posting_observation__collection_run=run,
                posting_observation__source_posting_id="9001",
                result="GREEN_CONFIRMED",
            ).count()
            == 1
        )
        assert all("nachwuchsentwicklung" not in request.url for request in fetcher.requests)

    def test_st_gallen_pagination_failure_is_incomplete_without_lifecycle(self) -> None:
        registered = source("SRC-OFF-CANTON-SG", "CANTON_SG_PORTAL")
        entry = [("8001", "Ordinary", "Departement", "St.Gallen")]
        broken = umantis_listing(1, 2, entry).replace(b"tc1152481=p2", b"tc1152481=p3")
        pages = {
            ("GET", ST_GALLEN_LISTING): FetchedPage(
                ST_GALLEN_LISTING, ST_GALLEN_LISTING, 200, "text/html", broken
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
        assert not PostingLifecycleEvent.objects.filter(posting__source=registered).exists()

    def test_thurgau_excludes_external_employers_and_admits_real_apprentice(self) -> None:
        registered = source("SRC-OFF-CANTON-TG", "CANTON_TG_PORTAL")
        ordinary_id = "11111111-1111-4111-8111-111111111111"
        apprentice_id = "22222222-2222-4222-8222-222222222222"
        external_id = "33333333-3333-4333-8333-333333333333"
        pages = {
            ("GET", THURGAU_LISTING): FetchedPage(
                THURGAU_LISTING,
                THURGAU_LISTING,
                200,
                "text/html",
                thurgau_listing(
                    3,
                    [
                        (ordinary_id, "Sachbearbeiter/in"),
                        (apprentice_id, "Lehrstelle Gärtner/in EFZ"),
                        (external_id, "Externe Fachperson"),
                    ],
                ),
            ),
            ("POST", THURGAU_LISTING): FetchedPage(
                THURGAU_LISTING,
                THURGAU_LISTING,
                200,
                "text/html",
                thurgau_listing(
                    1,
                    [(external_id, "Externe Fachperson")],
                    include_external_filter=False,
                ),
            ),
        }
        for posting_id, title, description in (
            (ordinary_id, "Sachbearbeiter/in", "Administration"),
            (apprentice_id, "Lehrstelle Gärtner/in EFZ", "Pflege von Garten- und Grünanlagen"),
        ):
            detail = f"https://ohws.prospective.ch/public/v1/jobs/{posting_id}"
            pages[("GET", detail)] = FetchedPage(
                detail,
                detail,
                200,
                "text/html",
                job_detail(title, description=description, locality="Frauenfeld", region="TG"),
            )
        fetcher = Fetcher(pages)
        with TemporaryDirectory() as raw:
            run = SharedCollectionPipeline(
                source_id=registered.pk,
                fetcher=fetcher,
                raw_store=RawObjectStore(raw),
                delay_seconds=0,
            ).collect(full_snapshot=True, acknowledge_automation_review=True)
        assert run.status == "SUCCEEDED" and run.snapshot_complete
        assert run.listing_total_discovered == run.details_fetched == 2
        assert run.observations_created == run.green_assessments_created == 2
        assert not Posting.objects.filter(source=registered, source_posting_id=external_id).exists()
        assert (
            GreenRelevanceAssessment.objects.filter(
                posting_observation__collection_run=run,
                posting_observation__source_posting_id=apprentice_id,
                result="GREEN_CONFIRMED",
            ).count()
            == 1
        )
        assert all("lernende.tg.ch" not in request.url for request in fetcher.requests)
        external_request = next(
            request
            for request in fetcher.requests
            if request.context.get("surface_name") == "separate_employers"
        )
        assert external_request.method == "POST"
        assert ("prospectivejobSearchParams.dynamic_group.4", "28") in external_request.form_data

    def test_thurgau_external_boundary_failure_has_no_partial_truth(self) -> None:
        registered = source("SRC-OFF-CANTON-TG", "CANTON_TG_PORTAL")
        posting_id = "11111111-1111-4111-8111-111111111111"
        pages = {
            ("GET", THURGAU_LISTING): FetchedPage(
                THURGAU_LISTING,
                THURGAU_LISTING,
                200,
                "text/html",
                thurgau_listing(1, [(posting_id, "Ordinary")]),
            ),
            ("POST", THURGAU_LISTING): FetchedPage(
                THURGAU_LISTING,
                THURGAU_LISTING,
                200,
                "text/html",
                b"<html>malformed external surface</html>",
            ),
        }
        with (
            TemporaryDirectory() as raw,
            pytest.raises(PlatformAdapterError, match="reported total"),
        ):
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

    def test_complete_empty_sources_are_healthy_without_promoted_truth(self) -> None:
        cases = (
            (
                source("SRC-OFF-CANTON-LU", "CANTON_LU_PORTAL"),
                {
                    ("GET", listing_url): FetchedPage(
                        listing_url,
                        listing_url,
                        200,
                        (
                            "application/json"
                            if surface_name == "apprenticeships"
                            else "text/html"
                        ),
                        (
                            luzern_apprenticeship_listing()
                            if surface_name == "apprenticeships"
                            else luzern_listing(empty=True)
                        ),
                    )
                    for surface_name, listing_url in LUZERN_CANTON_SURFACES
                },
            ),
            (
                source("SRC-OFF-CANTON-SG", "CANTON_SG_PORTAL"),
                {
                    ("GET", ST_GALLEN_LISTING): FetchedPage(
                        ST_GALLEN_LISTING,
                        ST_GALLEN_LISTING,
                        200,
                        "text/html",
                        umantis_listing(1, 0, []),
                    )
                },
            ),
            (
                source("SRC-OFF-CANTON-TG", "CANTON_TG_PORTAL"),
                {
                    ("GET", THURGAU_LISTING): FetchedPage(
                        THURGAU_LISTING,
                        THURGAU_LISTING,
                        200,
                        "text/html",
                        thurgau_listing(0, []),
                    ),
                    ("POST", THURGAU_LISTING): FetchedPage(
                        THURGAU_LISTING,
                        THURGAU_LISTING,
                        200,
                        "text/html",
                        thurgau_listing(0, [], include_external_filter=False),
                    ),
                },
            ),
        )
        for registered, pages in cases:
            with TemporaryDirectory() as raw:
                run = SharedCollectionPipeline(
                    source_id=registered.pk,
                    fetcher=Fetcher(pages),
                    raw_store=RawObjectStore(raw),
                    delay_seconds=0,
                ).collect(full_snapshot=True, acknowledge_automation_review=True)
            assert run.status == "SUCCEEDED"
            assert run.source_health_status == "HEALTHY"
            assert run.snapshot_complete
            assert run.listing_total_discovered == run.details_fetched == 0
            assert run.observations_created == run.green_assessments_created == 0
            assert not Posting.objects.filter(source=registered).exists()
