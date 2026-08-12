from __future__ import annotations

from typing import TypedDict

import pytest
from django.test import TestCase

from collectors.adapters import get_adapter
from collectors.governed_http import ensure_default_endpoints
from collectors.platforms import UnsupportedPlatformError
from sources.models import Source, SourceEndpoint

FINAL_BLOCKED = (
    ("SRC-OFF-CANTON-AI", "OFFICIAL_WEB"),
    ("SRC-OFF-CANTON-AG", "CANTON_AG_PORTAL"),
    ("SRC-OFF-CANTON-BE", "SITES_BE"),
    ("SRC-OFF-CANTON-FR", "FR_MIGRATION_PORTAL"),
    ("SRC-OFF-CANTON-JU", "OFFICIAL_WEB"),
    ("SRC-OFF-CANTON-NW", "CANTON_NW_PORTAL"),
    ("SRC-OFF-CANTON-OW", "OFFICIAL_WEB"),
    ("SRC-OFF-CANTON-UR", "OFFICIAL_WEB"),
    ("SRC-OFF-CANTON-VS", "OFFICIAL_WEB"),
)


class NWTrainingObject(TypedDict):
    label: str
    canonical_url: str
    application_id: str
    availability: dict[str, str]
    classification: str


NW_TRAINING_OBJECTS: tuple[NWTrainingObject, ...] = (
    {
        "label": "Kauffrau / Kaufmann EFZ",
        "canonical_url": "https://jobs.nw.ch/kauffrau-kaufmann-efz/",
        "application_id": "NW-1430",
        "availability": {"2026": "besetzt", "2027": "freie Stelle(n)"},
        "classification": "STATEFUL_RECURRING_VACANCY",
    },
    {
        "label": "Automobil EFZ",
        "canonical_url": (
            "https://jobs.nw.ch/automobilfachfrau-fachmann-efz-oder-"
            "automobilmechatroniker-mechatronikerin-efz/"
        ),
        "application_id": "NW-1433",
        "availability": {"2026": "besetzt", "2027": "besetzt"},
        "classification": "STATEFUL_RECURRING_VACANCY",
    },
    {
        "label": "Fachfrau / Fachmann Betriebsunterhalt EFZ",
        "canonical_url": ("https://jobs.nw.ch/fachfrau-fachmann-betriebsunterhalt-efz/"),
        "application_id": "NW-1432",
        "availability": {"2026": "besetzt", "2027": "besetzt"},
        "classification": "STATEFUL_RECURRING_VACANCY",
    },
    {
        "label": "Kaufmännisches Praktikum",
        "canonical_url": "https://jobs.nw.ch/praktika/",
        "application_id": "NW-1616",
        "availability": {
            "2026": "freie Stellen auf Anfrage",
            "2027": "freie Stellen auf Anfrage",
        },
        "classification": "UNRESOLVED",
    },
)


def source(source_id: str, platform_family: str) -> Source:
    return Source.objects.create(
        source_id=source_id,
        source_name=source_id,
        domain="example.ch",
        source_family="OFFICIAL_CANTON",
        source_type="DIRECT_PUBLIC_EMPLOYER",
        priority="P0",
        coverage_scope="required",
        canonicality="CANONICAL",
        platform_family=platform_family,
        access_method="WEB",
        automation_status="COLLECTOR_CANDIDATE",
        legal_review_status="AUTOMATION_REVIEW_REQUIRED",
        verification_status="VERIFIED",
        official_url="https://example.ch/",
    )


class Gate011C6FinalDispositionTests(TestCase):
    def test_all_nine_final_blocked_sources_have_no_adapter(self) -> None:
        for source_id, platform_family in FINAL_BLOCKED:
            with pytest.raises(UnsupportedPlatformError, match="explicitly blocked"):
                get_adapter(source(source_id, platform_family))

    def test_all_nine_final_blocked_sources_promote_no_endpoint(self) -> None:
        for source_id, platform_family in FINAL_BLOCKED:
            registered = source(source_id, platform_family)
            ensure_default_endpoints(registered)
            assert not SourceEndpoint.objects.filter(source=registered).exists()

    def test_final_disposition_covers_exactly_the_nine_remaining_sources(self) -> None:
        assert len(FINAL_BLOCKED) == 9
        assert len({source_id for source_id, _ in FINAL_BLOCKED}) == 9
        assert {source_id for source_id, _ in FINAL_BLOCKED} == {
            "SRC-OFF-CANTON-AI",
            "SRC-OFF-CANTON-AG",
            "SRC-OFF-CANTON-BE",
            "SRC-OFF-CANTON-FR",
            "SRC-OFF-CANTON-JU",
            "SRC-OFF-CANTON-NW",
            "SRC-OFF-CANTON-OW",
            "SRC-OFF-CANTON-UR",
            "SRC-OFF-CANTON-VS",
        }

    def test_nidwalden_profiles_have_real_identity_but_concurrent_cohorts_block(self) -> None:
        by_id = {item["application_id"]: item for item in NW_TRAINING_OBJECTS}

        assert len(by_id) == 4
        assert all(item["canonical_url"] for item in NW_TRAINING_OBJECTS)
        assert by_id["NW-1430"]["classification"] == "STATEFUL_RECURRING_VACANCY"
        assert by_id["NW-1430"]["availability"] == {
            "2026": "besetzt",
            "2027": "freie Stelle(n)",
        }
        assert set(by_id["NW-1432"]["availability"].values()) == {"besetzt"}
        assert set(by_id["NW-1433"]["availability"].values()) == {"besetzt"}

        practicum = by_id["NW-1616"]
        active_cohorts = {
            year
            for year, state in practicum["availability"].items()
            if state == "freie Stellen auf Anfrage"
        }
        assert active_cohorts == {"2026", "2027"}
        assert practicum["classification"] == "UNRESOLVED"

        blocked = source("SRC-OFF-CANTON-NW", "CANTON_NW_PORTAL")
        with pytest.raises(UnsupportedPlatformError, match="explicitly blocked"):
            get_adapter(blocked)
        ensure_default_endpoints(blocked)
        assert not SourceEndpoint.objects.filter(source=blocked).exists()
