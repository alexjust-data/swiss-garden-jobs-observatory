from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from dashboard.services import (
    DashboardBuildError,
    build_dashboard_snapshot,
    safe_external_url,
    source_link,
    visible_text,
)
from observations.models import PostingLocationResolution

from .factories import create_dashboard_upstream, digest


@pytest.mark.django_db
def test_future_geospatial_derivation_cannot_leak_into_historical_snapshot() -> None:
    data = create_dashboard_upstream(suffix="future-location")
    PostingLocationResolution.objects.create(
        posting_observation=data["observation"],
        resolver_version="geospatial-v0.1",
        privacy_context="PUBLIC_OR_NON_RESIDENTIAL",
        resolution_status="RESOLVED",
        latitude=47.5,
        longitude=8.7,
        location_precision="MUNICIPALITY",
        coordinate_source="SOURCE_STRUCTURED",
        privacy_display_level="MUNICIPALITY_CENTROID",
        public_display_latitude=47.5,
        public_display_longitude=8.7,
        input_fingerprint=digest("future-location-resolution"),
        evidence={"fixture": "future evidence"},
        created_at=data["as_of"] + timedelta(seconds=1),
    )

    snapshot, _ = build_dashboard_snapshot(
        as_of=data["as_of"],
        dedup_run=data["dedup"],
        premium_run=data["premium_run"],
    )

    record = snapshot.vacancy_records.get()
    assert record.location_resolution is None
    assert record.mapping_status == "LOCATION_UNRESOLVED"
    assert snapshot.mappable_vacancy_count == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("normalizer_version", "premium-normalizer-v9"),
        ("taxonomy_version", "research-v9"),
        ("taxonomy_sha256", "f" * 64),
    ],
)
def test_run_compatibility_rejects_semantically_incompatible_premium_run(
    field: str, value: str
) -> None:
    data = create_dashboard_upstream(suffix=f"inc-{field[:8]}")
    object.__setattr__(data["premium_run"], field, value)
    with pytest.raises(DashboardBuildError):
        build_dashboard_snapshot(
            as_of=data["as_of"],
            dedup_run=data["dedup"],
            premium_run=data["premium_run"],
        )


def _link_observation(status: str) -> SimpleNamespace:
    return SimpleNamespace(
        structured_payload={"canonical_url_status": status},
        contract_payload={"source_url": "https://observed.example/publication/42"},
        canonical_url="https://portal.example/search?q=42",
        source=SimpleNamespace(canonicality="CANONICAL"),
    )


@pytest.mark.parametrize(
    ("status", "expected_url", "expected_label"),
    [
        (
            "PORTAL_KNOWN_URL_PENDING",
            "https://observed.example/publication/42",
            "Open source where published",
        ),
        (
            "DISCOVERY_OR_HISTORICAL",
            "https://observed.example/publication/42",
            "Open observed source",
        ),
    ],
)
def test_non_original_link_statuses_prefer_observed_source(
    status: str, expected_url: str, expected_label: str
) -> None:
    resolved_status, url, label, _, _ = source_link(_link_observation(status))
    assert resolved_status == status
    assert url == expected_url
    assert label == expected_label


def test_unknown_explicit_link_status_fails_closed() -> None:
    status, url, label, method, _ = source_link(_link_observation("TRUST_ME_CANONICAL"))
    assert (status, url, label, method) == ("REVIEW", "", "", "INVALID_EXPLICIT_STATUS")


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com/job\nX-Header: secret",
        "https://example.com/white space",
        "https://user@example.com/job",
        "https://example.com:bad/job",
        "data:text/html,hello",
        "javascript%3Aalert(1)",
        "//example.com/job",
    ],
)
def test_external_url_obfuscation_fails_closed(value: str) -> None:
    assert safe_external_url(value) == ""


def test_visible_text_excludes_active_and_foreign_markup_surfaces() -> None:
    canary = "PRIVATE-CANARY"
    value = (
        "<p>Visible role</p>"
        f"<svg><foreignObject>{canary}</foreignObject></svg>"
        f"<math>{canary}</math><iframe>{canary}</iframe>"
        f"<object>{canary}</object><script>{canary}</script>"
    )
    rendered = visible_text(value)
    assert rendered == "Visible role"
    assert canary not in rendered


@pytest.mark.django_db
def test_dashboard_record_cross_object_and_mapping_validation() -> None:
    data = create_dashboard_upstream(
        suffix="record-validation",
        location_status="RESOLVED",
        public_coordinates=(47.5, 8.7),
    )
    snapshot, _ = build_dashboard_snapshot(
        as_of=data["as_of"],
        dedup_run=data["dedup"],
        premium_run=data["premium_run"],
    )
    record = snapshot.vacancy_records.get()
    record.source_name = "Another source"
    with pytest.raises(ValidationError):
        record.clean()

    record.source_name = data["source"].source_name
    record.location_resolution_status = "REVIEW"
    with pytest.raises(ValidationError):
        record.clean()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "query",
    [
        "?unknown=value",
        "?status=ACTIVE&status=CLOSED_OBSERVED",
        "?published_from=2026-08-11&published_to=2026-08-10",
        "?q=" + ("x" * 201),
    ],
)
def test_filter_ambiguity_is_rejected_consistently(client: Client, query: str) -> None:
    data = create_dashboard_upstream(suffix=digest(query)[:12])
    snapshot, _ = build_dashboard_snapshot(
        as_of=data["as_of"],
        dedup_run=data["dedup"],
        premium_run=data["premium_run"],
    )
    table = client.get(reverse("dashboard:vacancies", args=[snapshot.pk]) + query)
    geojson = client.get(reverse("dashboard:geojson", args=[snapshot.pk]) + query)
    assert table.status_code == 400
    assert geojson.status_code == 400


def test_frontend_cancels_stale_requests_and_avoids_innerhtml() -> None:
    script = (
        __import__("pathlib")
        .Path("src/dashboard/static/dashboard/dashboard.js")
        .read_text(encoding="utf-8")
    )
    assert "new AbortController()" in script
    assert "sequence !== requestSequence" in script
    assert "drawerContent.innerHTML" not in script
    assert "drawerContent.replaceChildren" in script
