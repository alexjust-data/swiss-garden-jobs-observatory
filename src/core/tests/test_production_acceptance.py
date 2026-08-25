from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.request import OpenerDirector

import pytest
from django.db import connection
from django.test import override_settings

from core.models import RawArtifact
from core.production_acceptance import (
    AcceptanceStatus,
    ProductionAcceptanceError,
    ProviderHttpRecorder,
    _assert_output_scope,
    canonical_json,
    canonical_value,
    capture_snapshot,
    compare_snapshots,
    current_database_identity,
    governed_model_labels,
    run_geospatial_acceptance,
    sha256,
    write_report,
)
from core.storage import RawObjectStore
from dashboard.services import build_dashboard_snapshot
from dashboard.tests.factories import create_dashboard_upstream
from observations.geospatial import (
    PROVIDER,
    PROVIDER_VERSION,
    LocationPrivacyContext,
    build_url,
    fingerprint,
    normalized_request,
)
from observations.models import GeocoderCacheEntry, PostingLocationResolution

pytestmark = pytest.mark.django_db(transaction=True)


def _database_identity_sha256() -> str:
    return current_database_identity()["database_identity_sha256"]


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _settings(raw_root: Path, operational_root: Path) -> override_settings:
    return override_settings(
        CORE_RAW_OBJECT_STORE_PATH=str(raw_root),
        JOB_OBSERVATORY_OPERATIONAL_RAW_STORE_PATH=str(operational_root),
        JOB_OBSERVATORY_OPERATIONAL_DB_NAME="swiss_garden_jobs",
        JOB_OBSERVATORY_RAW_LINEAGE_MANIFEST_SHA256="",
    )


def _materialize_factory_raw(upstream: dict[str, Any], store: RawObjectStore) -> None:
    artifact = upstream["observation"].raw_artifact
    content = b"{}"
    store.write_bytes(artifact.object_key, content)
    RawArtifact.objects.filter(pk=artifact.pk).update(
        sha256_digest=_digest(content), byte_size=len(content), content_type="application/json"
    )
    artifact.refresh_from_db()


def _install_cache(upstream: dict[str, Any], store: RawObjectStore) -> None:
    observation = upstream["observation"]
    request = normalized_request(
        observation,
        LocationPrivacyContext.PUBLIC_OR_NON_RESIDENTIAL,
    )
    assert request is not None
    body = json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [8.7241, 47.4988]},
                    "properties": {
                        "attrs": {
                            "municipality": "Winterthur",
                            "canton": "ZH",
                            "country": "CH",
                            "origin": "gg25",
                            "label": "Winterthur",
                        }
                    },
                }
            ],
        },
        sort_keys=True,
    ).encode()
    request_fingerprint = fingerprint(
        {"provider": PROVIDER, "version": PROVIDER_VERSION, "request": request}
    )
    body_digest = _digest(body)
    object_key = (
        f"geocoder/{PROVIDER.lower()}/{PROVIDER_VERSION}/"
        f"{request_fingerprint}-{body_digest[:16]}.json"
    )
    store.write_bytes(object_key, body)
    artifact = RawArtifact.objects.create(
        object_key=object_key,
        sha256_digest=body_digest,
        byte_size=len(body),
        content_type="application/json",
    )
    url = build_url(request)
    GeocoderCacheEntry.objects.create(
        provider=PROVIDER,
        provider_version=PROVIDER_VERSION,
        normalized_request=request,
        request_fingerprint=request_fingerprint,
        requested_url=url,
        final_url=url,
        http_status=200,
        content_type="application/json",
        raw_artifact=artifact,
        response_payload=json.loads(body),
    )


def test_canonical_datetime_is_fixed_utc_and_rejects_naive() -> None:
    utc = datetime(2026, 8, 24, 20, 1, 2, tzinfo=UTC)
    offset = utc.astimezone(timezone(timedelta(hours=2)))
    assert canonical_value(utc) == "2026-08-24T20:01:02.000000Z"
    assert canonical_value(offset) == canonical_value(utc)
    with pytest.raises(ProductionAcceptanceError, match="naive"):
        canonical_value(datetime(2026, 8, 24, 20, 1, 2))


def test_canonical_hash_is_deterministic_and_rejects_non_finite() -> None:
    left = {"b": [2, 1], "a": {"value": "x"}}
    right = {"a": {"value": "x"}, "b": [2, 1]}
    assert canonical_json(left) == canonical_json(right)
    assert sha256(left) == sha256(right)
    with pytest.raises(ProductionAcceptanceError, match="non-finite"):
        canonical_value(float("nan"))


def test_snapshot_delta_detects_created_modified_and_deleted_rows(tmp_path: Path) -> None:
    with _settings(tmp_path / "raw", tmp_path / "operational"):
        before = capture_snapshot(verify_raw_bytes=False)
        artifact = RawArtifact.objects.create(
            object_key="h2/example.json",
            sha256_digest="a" * 64,
            byte_size=1,
            content_type="application/json",
        )
        created = capture_snapshot(verify_raw_bytes=False)
        created_delta = compare_snapshots(before, created)
        assert created_delta["core.RawArtifact"]["created"] == [str(artifact.pk)]

        RawArtifact.objects.filter(pk=artifact.pk).update(byte_size=2)
        modified = capture_snapshot(verify_raw_bytes=False)
        modified_delta = compare_snapshots(created, modified)
        assert modified_delta["core.RawArtifact"]["modified"] == [str(artifact.pk)]

        RawArtifact.objects.filter(pk=artifact.pk).delete()
        deleted = capture_snapshot(verify_raw_bytes=False)
        deleted_delta = compare_snapshots(modified, deleted)
        assert deleted_delta["core.RawArtifact"]["deleted"] == [str(artifact.pk)]


def test_snapshot_covers_every_governed_project_model_and_detects_old_gap(
    tmp_path: Path,
) -> None:
    upstream = create_dashboard_upstream(suffix="h2-full-model-surface")
    labels = governed_model_labels()
    assert "sources.Source" in labels
    assert "observations.PostingObservation" in labels
    assert "premium_segments.PremiumSegmentAssessment" in labels
    assert "observations.PostingLifecycleEvent" in labels

    with _settings(tmp_path / "raw", tmp_path / "operational"):
        before = capture_snapshot(verify_raw_bytes=False)
        source = upstream["source"]
        source_name = source.source_name
        type(source).objects.filter(pk=source.pk).update(source_name=f"{source_name} changed")
        after = capture_snapshot(verify_raw_bytes=False)

    delta = compare_snapshots(before, after)
    assert delta["sources.Source"]["modified"] == [str(source.pk)]


def test_expected_database_identity_mismatch_refuses_before_operation(tmp_path: Path) -> None:
    upstream = create_dashboard_upstream(suffix="h2-db-identity-mismatch")
    with _settings(tmp_path / "raw", tmp_path / "operational"):
        with pytest.raises(ProductionAcceptanceError, match="expected-database-identity"):
            run_geospatial_acceptance(
                premium_run_id=str(upstream["premium_run"].pk),
                expected_database=current_database_identity()["database"],
                expected_database_identity_sha256="f" * 64,
                execute=True,
                allow_operational=False,
                verify_raw_bytes=True,
            )
    assert PostingLocationResolution.objects.count() == 0


def test_expected_database_mismatch_refuses_before_operation(tmp_path: Path) -> None:
    upstream = create_dashboard_upstream(suffix="h2-db-mismatch")
    with _settings(tmp_path / "raw", tmp_path / "operational"):
        with pytest.raises(ProductionAcceptanceError, match="expected-database"):
            run_geospatial_acceptance(
                premium_run_id=str(upstream["premium_run"].pk),
                expected_database="definitely-not-the-connected-database",
                expected_database_identity_sha256=_database_identity_sha256(),
                execute=True,
                allow_operational=False,
                verify_raw_bytes=True,
            )
    assert PostingLocationResolution.objects.count() == 0


def test_dry_run_is_not_proven_and_mutates_nothing(tmp_path: Path) -> None:
    upstream = create_dashboard_upstream(suffix="h2-dry")
    with _settings(tmp_path / "raw", tmp_path / "operational"):
        report = run_geospatial_acceptance(
            premium_run_id=str(upstream["premium_run"].pk),
            expected_database=str(connection.settings_dict["NAME"]),
            expected_database_identity_sha256=_database_identity_sha256(),
            execute=False,
            allow_operational=False,
            verify_raw_bytes=False,
        )
    assert report["overall"] == AcceptanceStatus.NOT_PROVEN
    assert report["operation_result"]["dry_run"] is True
    assert report["operation_result"]["created"] == 0
    assert PostingLocationResolution.objects.count() == 0


def test_raw_preflight_failure_stops_before_geospatial_mutation(tmp_path: Path) -> None:
    upstream = create_dashboard_upstream(suffix="h2-raw-fail")
    with _settings(tmp_path / "raw", tmp_path / "operational"):
        report = run_geospatial_acceptance(
            premium_run_id=str(upstream["premium_run"].pk),
            expected_database=str(connection.settings_dict["NAME"]),
            expected_database_identity_sha256=_database_identity_sha256(),
            execute=True,
            allow_operational=False,
            verify_raw_bytes=True,
        )
    assert report["overall"] == AcceptanceStatus.FAIL
    assert report["operation_result"] is None
    assert PostingLocationResolution.objects.count() == 0


def test_isolated_cached_geospatial_acceptance_and_retry_pass(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    store = RawObjectStore(raw_root)
    upstream = create_dashboard_upstream(suffix="h2-pass")
    _materialize_factory_raw(upstream, store)
    _install_cache(upstream, store)

    with _settings(raw_root, tmp_path / "operational"):
        report = run_geospatial_acceptance(
            premium_run_id=str(upstream["premium_run"].pk),
            expected_database=str(connection.settings_dict["NAME"]),
            expected_database_identity_sha256=_database_identity_sha256(),
            execute=True,
            allow_operational=False,
            verify_raw_bytes=True,
        )

    assert report["overall"] == AcceptanceStatus.PASS
    assert report["operation_result"]["created"] == 1
    assert report["operation_result"]["network_requests"] == 0
    assert report["retry_result"]["created"] == 0
    assert report["retry_result"]["network_requests"] == 0
    assert report["operation_result"]["resolution_ids"] == report["retry_result"]["resolution_ids"]
    assert report["retry_delta"]["observations.PostingLocationResolution"]["created"] == []
    assert PostingLocationResolution.objects.count() == 1
    checks = {item["check_id"]: item for item in report["checks"]}
    assert checks["source_http"]["status"] == AcceptanceStatus.PASS
    assert checks["provider_http"]["status"] == AcceptanceStatus.PASS
    assert checks["exact_retry"]["status"] == AcceptanceStatus.PASS


def test_operational_database_requires_explicit_boundary(tmp_path: Path) -> None:
    upstream = create_dashboard_upstream(suffix="h2-operational-boundary")
    database = str(connection.settings_dict["NAME"])
    with override_settings(
        CORE_RAW_OBJECT_STORE_PATH=str(tmp_path / "raw"),
        JOB_OBSERVATORY_OPERATIONAL_RAW_STORE_PATH=str(tmp_path / "raw"),
        JOB_OBSERVATORY_OPERATIONAL_DB_NAME=database,
        JOB_OBSERVATORY_OPERATIONAL_DB_IDENTITY_SHA256=_database_identity_sha256(),
        JOB_OBSERVATORY_RAW_LINEAGE_MANIFEST_SHA256="a" * 64,
    ):
        with pytest.raises(ProductionAcceptanceError, match="allow-operational"):
            run_geospatial_acceptance(
                premium_run_id=str(upstream["premium_run"].pk),
                expected_database=database,
                expected_database_identity_sha256=_database_identity_sha256(),
                execute=True,
                allow_operational=False,
                verify_raw_bytes=True,
            )
    assert PostingLocationResolution.objects.count() == 0


def test_operational_database_name_alone_is_not_authority(tmp_path: Path) -> None:
    upstream = create_dashboard_upstream(suffix="h2-operational-identity")
    database = current_database_identity()["database"]
    with override_settings(
        CORE_RAW_OBJECT_STORE_PATH=str(tmp_path / "raw"),
        JOB_OBSERVATORY_OPERATIONAL_RAW_STORE_PATH=str(tmp_path / "raw"),
        JOB_OBSERVATORY_OPERATIONAL_DB_NAME=database,
        JOB_OBSERVATORY_OPERATIONAL_DB_IDENTITY_SHA256="0" * 64,
        JOB_OBSERVATORY_RAW_LINEAGE_MANIFEST_SHA256="a" * 64,
    ):
        with pytest.raises(ProductionAcceptanceError, match="identity designation mismatch"):
            run_geospatial_acceptance(
                premium_run_id=str(upstream["premium_run"].pk),
                expected_database=database,
                expected_database_identity_sha256=_database_identity_sha256(),
                execute=True,
                allow_operational=True,
                verify_raw_bytes=True,
            )
    assert PostingLocationResolution.objects.count() == 0


def test_isolated_database_cannot_share_operational_raw_root(tmp_path: Path) -> None:
    upstream = create_dashboard_upstream(suffix="h2-shared-root")
    shared = tmp_path / "shared"
    with override_settings(
        CORE_RAW_OBJECT_STORE_PATH=str(shared),
        JOB_OBSERVATORY_OPERATIONAL_RAW_STORE_PATH=str(shared),
        JOB_OBSERVATORY_OPERATIONAL_DB_NAME="some-other-operational-database",
        JOB_OBSERVATORY_RAW_LINEAGE_MANIFEST_SHA256="a" * 64,
    ):
        with pytest.raises(ProductionAcceptanceError, match="distinct"):
            run_geospatial_acceptance(
                premium_run_id=str(upstream["premium_run"].pk),
                expected_database=str(connection.settings_dict["NAME"]),
                expected_database_identity_sha256=_database_identity_sha256(),
                execute=True,
                allow_operational=False,
                verify_raw_bytes=True,
            )
    assert PostingLocationResolution.objects.count() == 0


def test_snapshot_exposes_bounded_pit_ids_and_fingerprints(tmp_path: Path) -> None:
    upstream = create_dashboard_upstream(suffix="h2-pit-summary")
    dashboard, reused = build_dashboard_snapshot(
        as_of=upstream["as_of"],
        dedup_run=upstream["dedup"],
        premium_run=upstream["premium_run"],
    )
    assert not reused
    with _settings(tmp_path / "raw", tmp_path / "operational"):
        snapshot = capture_snapshot(verify_raw_bytes=False)
    dedup = snapshot["artifacts"]["vacancies.DedupRun"]
    premium = snapshot["artifacts"]["premium_segments.PremiumSegmentRun"]
    dashboards = snapshot["artifacts"]["dashboard.DashboardSnapshot"]
    assert {item["id"] for item in dedup} == {str(upstream["dedup"].pk)}
    assert dedup[0]["input_fingerprint"] == upstream["dedup"].input_fingerprint
    assert {item["id"] for item in premium} == {str(upstream["premium_run"].pk)}
    assert premium[0]["input_fingerprint"] == upstream["premium_run"].input_fingerprint
    assert {item["id"] for item in dashboards} == {str(dashboard.pk)}
    assert dashboards[0]["as_of"] == canonical_value(dashboard.as_of)
    assert dashboards[0]["input_fingerprint"] == dashboard.input_fingerprint
    assert "status" not in dashboards[0]


def test_output_path_must_be_disjoint_from_raw(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    with _settings(raw, tmp_path / "operational"):
        with pytest.raises(ProductionAcceptanceError, match="disjoint"):
            _assert_output_scope(raw / "reports")
        with pytest.raises(ProductionAcceptanceError, match="disjoint"):
            _assert_output_scope(tmp_path)


def test_output_path_must_also_be_disjoint_from_operational_raw(tmp_path: Path) -> None:
    execution = tmp_path / "execution"
    operational = tmp_path / "operational"
    with _settings(execution, operational):
        with pytest.raises(ProductionAcceptanceError, match="disjoint"):
            _assert_output_scope(operational / "reports")
        with pytest.raises(ProductionAcceptanceError, match="disjoint"):
            _assert_output_scope(tmp_path)


def test_relative_raw_roots_are_rejected_before_mutation(tmp_path: Path) -> None:
    upstream = create_dashboard_upstream(suffix="h2-relative-root")
    with override_settings(
        CORE_RAW_OBJECT_STORE_PATH="relative/raw",
        JOB_OBSERVATORY_OPERATIONAL_RAW_STORE_PATH=str(tmp_path / "operational"),
        JOB_OBSERVATORY_OPERATIONAL_DB_NAME="some-other-operational-database",
        JOB_OBSERVATORY_RAW_LINEAGE_MANIFEST_SHA256="a" * 64,
    ):
        with pytest.raises(ProductionAcceptanceError, match="absolute"):
            run_geospatial_acceptance(
                premium_run_id=str(upstream["premium_run"].pk),
                expected_database=str(connection.settings_dict["NAME"]),
                expected_database_identity_sha256=_database_identity_sha256(),
                execute=True,
                allow_operational=False,
                verify_raw_bytes=True,
            )
    assert PostingLocationResolution.objects.count() == 0


def test_http_recorder_classifies_non_provider_transport_without_url_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_open(opener: object, fullurl: object, *args: object, **kwargs: object) -> object:
        return object()

    monkeypatch.setattr(OpenerDirector, "open", fake_open)
    with ProviderHttpRecorder() as recorder:
        OpenerDirector().open("https://jobs.example.invalid/private-query")
        evidence = recorder.evidence()
    assert evidence.source_transport_requests == 1
    assert evidence.provider_transport_requests == 0
    assert not hasattr(evidence, "urls")


def test_report_write_is_atomic_and_deterministic(tmp_path: Path) -> None:
    report = {
        "operation": "geospatial-recovery",
        "overall": "PASS",
        "evidence_sha256": "b" * 64,
        "checks": [
            {
                "check_id": "example",
                "status": "PASS",
                "mandatory": True,
                "summary": "bounded",
                "details": {},
            }
        ],
        "volatile": {"duration_seconds": 1.0},
    }
    raw = tmp_path / "raw"
    output = tmp_path / "reports"
    with _settings(raw, tmp_path / "operational"):
        first_json, first_text = write_report(report, output)
        first_bytes = first_json.read_bytes()
        second_json, second_text = write_report(report, output)
    assert second_json.read_bytes() == first_bytes
    assert "INDEPENDENT AUDIT STILL REQUIRED" in second_text.read_text(encoding="utf-8")
    assert first_text == second_text
    assert not list(output.glob("*.tmp"))
    assert not list(output.glob(".h2-write-probe-*"))


def test_provider_recorder_restores_client_method() -> None:
    from observations.geospatial import GeoAdminSearchServerClient

    original_fetch = GeoAdminSearchServerClient.fetch
    original_open = OpenerDirector.open
    with ProviderHttpRecorder() as recorder:
        assert GeoAdminSearchServerClient.fetch is not original_fetch
        assert OpenerDirector.open is not original_open
        assert recorder.evidence().provider_fetches == 0
        assert recorder.evidence().source_transport_requests == 0
    assert GeoAdminSearchServerClient.fetch is original_fetch
    assert OpenerDirector.open is original_open
