from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.core.management import call_command
from django.db import close_old_connections
from django.test import Client, RequestFactory
from django.urls import reverse

from dashboard.admin import DashboardSnapshotAdmin
from dashboard.models import (
    DashboardSnapshot,
    DashboardVacancyRecord,
    ImmutableDashboardEvidenceError,
)
from dashboard.services import (
    DashboardBuildError,
    build_dashboard_snapshot,
    safe_external_url,
    source_link,
    visible_text,
)
from observations.models import PostingLocationResolution
from vacancies.models import DedupRun

from .factories import create_dashboard_upstream


@pytest.mark.django_db(transaction=True)
def test_aligned_snapshot_is_complete_immutable_and_idempotent() -> None:
    data = create_dashboard_upstream(location_status="UNRESOLVED")
    snapshot, reused = build_dashboard_snapshot(
        as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
    )
    replay, replay_reused = build_dashboard_snapshot(
        as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
    )
    assert not reused
    assert replay_reused
    assert replay.pk == snapshot.pk
    assert snapshot.total_vacancy_states == snapshot.vacancy_records.count() == 1
    record = snapshot.vacancy_records.get()
    assert record.canonical_observation.pk == data["observation"].pk
    assert record.dedup_run_vacancy_state.pk == data["state"].pk
    original = record.title
    with pytest.raises(ImmutableDashboardEvidenceError):
        record.title = "changed"
        record.save()
    with pytest.raises(ImmutableDashboardEvidenceError):
        DashboardVacancyRecord.objects.filter(pk=record.pk).update(title="changed")
    with pytest.raises(ImmutableDashboardEvidenceError):
        DashboardVacancyRecord.objects.filter(pk=record.pk).delete()
    record.refresh_from_db()
    assert record.title == original


@pytest.mark.django_db
@pytest.mark.parametrize("target", ["as_of", "dedup_status", "premium_status", "dedup_version"])
def test_incompatible_runs_fail_closed(target: str) -> None:
    data = create_dashboard_upstream()
    if target == "as_of":
        requested = data["as_of"] + timedelta(seconds=1)
    else:
        requested = data["as_of"]
        if target == "dedup_status":
            DedupRun.objects.filter(pk=data["dedup"].pk).update(status="FAILED")
            data["dedup"].refresh_from_db()
        elif target == "premium_status":
            object.__setattr__(data["premium_run"], "status", "FAILED")
        else:
            object.__setattr__(data["dedup"], "dedup_version", "dedup-v9")
    with pytest.raises(DashboardBuildError):
        build_dashboard_snapshot(
            as_of=requested, dedup_run=data["dedup"], premium_run=data["premium_run"]
        )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("green_result", "premium_status", "expected"),
    [
        ("GREEN_CONFIRMED", "NO_SUFFICIENT_EVIDENCE", "PUBLIC_GREEN_CONFIRMED"),
        ("REVIEW", "SKIPPED_NOT_GREEN", "REVIEW_NOT_PUBLIC"),
        ("NOT_GREEN", "SKIPPED_NOT_GREEN", "EXCLUDED_NOT_GREEN"),
    ],
)
def test_public_eligibility_uses_exact_canonical_green(
    green_result: str, premium_status: str, expected: str
) -> None:
    data = create_dashboard_upstream(green_result=green_result, premium_status=premium_status)
    snapshot, _ = build_dashboard_snapshot(
        as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
    )
    assert snapshot.vacancy_records.get().visibility_status == expected


@pytest.mark.django_db
def test_later_mutable_projection_and_observation_do_not_change_snapshot() -> None:
    data = create_dashboard_upstream(title="Original title")
    snapshot, _ = build_dashboard_snapshot(
        as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
    )
    record = snapshot.vacancy_records.get()
    data["posting"].current_status = "CLOSED_OBSERVED"
    data["posting"].latest_canonical_url = "https://later.example/job"
    data["posting"].save()
    assert DashboardVacancyRecord.objects.get(pk=record.pk).title == "Original title"
    assert DashboardVacancyRecord.objects.get(pk=record.pk).vacancy_status == "ACTIVE"


@pytest.mark.django_db
def test_public_resolution_maps_only_public_coordinates_and_geojson_order(client: Client) -> None:
    data = create_dashboard_upstream(
        location_status="RESOLVED",
        internal_coordinates=(47.999, 8.999),
        public_coordinates=(47.501, 8.701),
    )
    snapshot, _ = build_dashboard_snapshot(
        as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
    )
    record = snapshot.vacancy_records.get()
    assert record.mapping_status == "MAPPABLE"
    response = client.get(reverse("dashboard:geojson", args=[snapshot.pk]))
    payload = response.json()
    assert payload["features"][0]["geometry"]["coordinates"] == [8.701, 47.501]
    serialized = json.dumps(payload)
    assert "47.999" not in serialized
    assert "8.999" not in serialized
    assert "latitude" not in payload["features"][0]["properties"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("location_status", "public_coordinates", "expected"),
    [
        ("REVIEW", None, "LOCATION_REVIEW"),
        ("UNRESOLVED", None, "LOCATION_UNRESOLVED"),
        ("RESOLVED", None, "LOCATION_HIDDEN"),
    ],
)
def test_non_public_location_states_never_map(
    location_status: str,
    public_coordinates: tuple[float, float] | None,
    expected: str,
) -> None:
    data = create_dashboard_upstream(
        location_status=location_status, public_coordinates=public_coordinates
    )
    snapshot, _ = build_dashboard_snapshot(
        as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
    )
    assert snapshot.vacancy_records.get().mapping_status == expected
    assert snapshot.mappable_vacancy_count == 0


@pytest.mark.django_db
def test_private_segment_requires_protected_resolution_and_redacts_address(client: Client) -> None:
    street = "Confidentialstrasse 12"
    data = create_dashboard_upstream(
        premium_segment="PRIVATE_ESTATE_DIRECT",
        premium_status="CLASSIFIED",
        privacy_context="PRIVATE_RESIDENCE",
        description=f"<p>Private villa at {street}</p>",
    )
    PostingLocationResolution.objects.create(
        posting_observation=data["observation"],
        resolver_version="geospatial-v0.1",
        privacy_context="PUBLIC_OR_NON_RESIDENTIAL",
        resolution_status="RESOLVED",
        latitude=47.9,
        longitude=8.9,
        location_precision="EXACT_WORK_ADDRESS",
        coordinate_source="SOURCE_STRUCTURED",
        privacy_display_level="EXACT_ALLOWED",
        public_display_latitude=47.9,
        public_display_longitude=8.9,
        input_fingerprint="a" * 64,
        evidence={"street": street},
    )
    snapshot, _ = build_dashboard_snapshot(
        as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
    )
    record = snapshot.vacancy_records.get()
    assert record.mapping_status == "PRIVACY_RESOLUTION_MISSING"
    assert record.safe_description == ""
    table = client.get(reverse("dashboard:vacancies", args=[snapshot.pk])).content.decode()
    geojson = client.get(reverse("dashboard:geojson", args=[snapshot.pk])).content.decode()
    detail = client.get(
        reverse("dashboard:posting_detail", args=[data["posting"].pk]),
        {"snapshot": snapshot.pk},
    ).content.decode()
    assert street not in table + geojson + detail
    assert "47.9" not in table + geojson + detail


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("javascript:alert(1)", ""),
        ("https://user:pass@example.com/job", ""),
        ("//example.com/job", ""),
        ("https://example.com/job", "https://example.com/job"),
    ],
)
def test_external_url_validation(raw: str, expected: str) -> None:
    assert safe_external_url(raw) == expected


@pytest.mark.parametrize(
    ("status", "label"),
    [
        ("CANONICAL", "Open original advert"),
        ("AGENCY_CANONICAL", "Open original advert"),
        ("ORIGINAL_ATS_LINKED", "Open original advert"),
        ("PORTAL_KNOWN_URL_PENDING", "Open source where published"),
        ("DISCOVERY_OR_HISTORICAL", "Open observed source"),
        ("EXPIRED_SOURCE", "Open expired link"),
        ("NO_LINK_AVAILABLE", ""),
        ("REVIEW", ""),
    ],
)
def test_source_link_labels_are_contractual(status: str, label: str) -> None:
    observation = SimpleNamespace(
        structured_payload={"canonical_url_status": status},
        contract_payload={"source_url": "https://source.example/job"},
        canonical_url="https://source.example/job",
        source=SimpleNamespace(canonicality="CANONICAL"),
    )
    assert source_link(observation)[2] == label


def test_closed_observed_is_not_automatically_expired() -> None:
    observation = SimpleNamespace(
        structured_payload={},
        contract_payload={"source_url": "https://source.example/job"},
        canonical_url="https://source.example/job",
        source=SimpleNamespace(canonicality="CANONICAL"),
        observation_status="ACTIVE",
    )
    assert source_link(observation)[0] == "CANONICAL"


def test_visible_text_removes_scripts_attributes_and_event_handlers() -> None:
    hostile = (
        '<p onclick="steal()">Safe</p><script>privateStreet()</script>'
        '<a href="javascript:x">Link</a>'
    )
    assert visible_text(hostile) == "Safe Link"


@pytest.mark.django_db
def test_api_snapshot_filters_dates_detail_and_zero_feature_geojson(client: Client) -> None:
    data = create_dashboard_upstream(location_status="UNRESOLVED")
    snapshot, _ = build_dashboard_snapshot(
        as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
    )
    assert (
        client.get(reverse("dashboard:current")).json()["headline_market_state"]
        == "SEE_EXACT_DAY0_ASSESSMENT"
    )
    listing = client.get(
        reverse("dashboard:vacancies", args=[snapshot.pk]),
        {"q": "Gardener", "canton": "ZH", "mapping": "UNMAPPABLE"},
    )
    assert listing.status_code == 200
    assert listing.json()["pagination"]["total"] == 1
    assert (
        client.get(
            reverse("dashboard:vacancies", args=[snapshot.pk]), {"status": "FILLED"}
        ).status_code
        == 400
    )
    geojson = client.get(reverse("dashboard:geojson", args=[snapshot.pk])).json()
    assert geojson["type"] == "FeatureCollection"
    assert geojson["features"] == []
    detail = client.get(
        reverse("dashboard:vacancy_detail_api", args=[snapshot.pk, data["state"].run_vacancy_key])
    )
    assert detail.status_code == 200
    assert detail.json()["record"]["salary_availability"] == "NOT_IMPLEMENTED_IN_CURRENT_GATE"


@pytest.mark.django_db
def test_non_public_records_are_excluded_from_every_public_endpoint(client: Client) -> None:
    data = create_dashboard_upstream(green_result="NOT_GREEN", premium_status="SKIPPED_NOT_GREEN")
    snapshot, _ = build_dashboard_snapshot(
        as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
    )
    assert client.get(reverse("dashboard:vacancies", args=[snapshot.pk])).json()["results"] == []
    assert client.get(reverse("dashboard:geojson", args=[snapshot.pk])).json()["features"] == []
    assert (
        client.get(
            reverse(
                "dashboard:vacancy_detail_api", args=[snapshot.pk, data["state"].run_vacancy_key]
            )
        ).status_code
        == 404
    )


@pytest.mark.django_db
def test_json_and_html_escape_hostile_title(client: Client) -> None:
    hostile = '<script>window.pwned=true</script><img src=x onerror="window.pwned=true">'
    data = create_dashboard_upstream(title=hostile)
    snapshot, _ = build_dashboard_snapshot(
        as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
    )
    detail = client.get(
        reverse("dashboard:posting_detail", args=[data["posting"].pk]),
        {"snapshot": snapshot.pk},
    ).content.decode()
    assert "<script>" not in detail
    assert "onerror=" not in detail
    assert "window.pwned" not in detail


@pytest.mark.django_db
def test_jobs_page_has_disclaimer_day_zero_pending_and_accessibility(client: Client) -> None:
    data = create_dashboard_upstream()
    build_dashboard_snapshot(
        as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
    )
    html = client.get("/jobs/").content.decode()
    assert "not yet a complete census" in html
    assert "Pending GATE-011 Day-0" in html
    assert 'aria-modal="true"' in html
    assert "MapLibre" not in html or "maplibre" in html.lower()


@pytest.mark.django_db
def test_list_endpoint_query_count_is_bounded(
    client: Client, django_assert_num_queries: Any
) -> None:
    data = create_dashboard_upstream()
    snapshot, _ = build_dashboard_snapshot(
        as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
    )
    with django_assert_num_queries(3):
        response = client.get(reverse("dashboard:vacancies", args=[snapshot.pk]))
        assert response.status_code == 200


@pytest.mark.django_db
def test_admin_is_observational() -> None:
    admin = DashboardSnapshotAdmin(DashboardSnapshot, AdminSite())
    request = RequestFactory().get("/admin/")
    assert not admin.has_add_permission(request)
    assert not admin.has_change_permission(request)
    assert not admin.has_delete_permission(request)


@pytest.mark.django_db
def test_command_is_idempotent_and_privacy_safe() -> None:
    data = create_dashboard_upstream()
    output = StringIO()
    call_command(
        "build_dashboard_snapshot",
        as_of=data["as_of"].isoformat(),
        dedup_run=str(data["dedup"].pk),
        premium_run=str(data["premium_run"].pk),
        stdout=output,
    )
    first = json.loads(output.getvalue())
    output = StringIO()
    call_command(
        "build_dashboard_snapshot",
        as_of=data["as_of"].isoformat(),
        dedup_run=str(data["dedup"].pk),
        premium_run=str(data["premium_run"].pk),
        stdout=output,
    )
    second = json.loads(output.getvalue())
    assert first["snapshot_id"] == second["snapshot_id"]
    assert second["exact_replay_reused"] is True


@pytest.mark.django_db(transaction=True)
def test_concurrent_exact_build_creates_one_complete_snapshot() -> None:
    data = create_dashboard_upstream()
    barrier = threading.Barrier(2)

    def worker() -> tuple[str, bool]:
        close_old_connections()
        barrier.wait()
        run = DedupRun.objects.get(pk=data["dedup"].pk)
        premium = data["premium_run"].__class__.objects.get(pk=data["premium_run"].pk)
        snapshot, reused = build_dashboard_snapshot(
            as_of=data["as_of"], dedup_run=run, premium_run=premium
        )
        close_old_connections()
        return str(snapshot.pk), reused

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: worker(), range(2)))
    assert len({item[0] for item in results}) == 1
    assert DashboardSnapshot.objects.count() == 1
    assert DashboardVacancyRecord.objects.count() == 1


@pytest.mark.django_db
def test_partial_record_failure_rolls_back_snapshot() -> None:
    data = create_dashboard_upstream()
    with patch.object(DashboardVacancyRecord.objects, "bulk_create", side_effect=RuntimeError("x")):
        with pytest.raises(RuntimeError):
            build_dashboard_snapshot(
                as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
            )
    assert DashboardSnapshot.objects.count() == 0
    assert DashboardVacancyRecord.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_non_code_source_region_is_not_persisted_as_canton() -> None:
    data = create_dashboard_upstream(location_status="UNRESOLVED", location_region="Bern")
    snapshot, _ = build_dashboard_snapshot(
        as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
    )
    assert snapshot.vacancy_records.get().canton_code == ""


@pytest.mark.django_db(transaction=True)
def test_valid_source_canton_code_remains_available() -> None:
    data = create_dashboard_upstream(location_status="UNRESOLVED", location_region="be")
    snapshot, _ = build_dashboard_snapshot(
        as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
    )
    assert snapshot.vacancy_records.get().canton_code == "BE"
