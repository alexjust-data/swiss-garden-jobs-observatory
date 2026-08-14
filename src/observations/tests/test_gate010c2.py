from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest.mock import patch

import pytest
from django.conf import settings
from django.core.management import call_command
from django.db import close_old_connections, connection
from django.test import TestCase, override_settings

from core.hashing import sha256_hex
from core.models import RawArtifact
from core.storage import RawObjectStore
from dashboard.tests.factories import create_dashboard_upstream
from observations.geospatial import (
    PROVIDER,
    PROVIDER_VERSION,
    GeocoderFetchedResponse,
    GeospatialResolutionError,
    GeospatialResolver,
    LocationPrivacyContext,
    build_url,
    fingerprint,
    normalized_request,
    resolution_input_fingerprint,
)
from observations.geospatial_batch import GeospatialBatchError, resolve_premium_run_locations
from observations.models import (
    GeocoderCacheEntry,
    GeocodingReviewItem,
    PostingLocationResolution,
    PostingObservation,
)
from premium_segments.models import PremiumSegmentAssessment


class FakeClient:
    def __init__(self) -> None:
        self.calls = 0
        self.requests: list[dict[str, object]] = []

    def fetch(self, request: dict[str, object]) -> GeocoderFetchedResponse:
        self.calls += 1
        self.requests.append(request)
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
        url = build_url(request)
        return GeocoderFetchedResponse(url, url, 200, "application/json", body)


class RegionFailingClient(FakeClient):
    def fetch(self, request: dict[str, object]) -> GeocoderFetchedResponse:
        if str(request.get("searchText", "")).endswith("BE"):
            self.calls += 1
            self.requests.append(request)
            raise GeospatialResolutionError("injected second-target provider failure")
        return super().fetch(request)


class StaticResponseClient:
    def __init__(self, response: GeocoderFetchedResponse) -> None:
        self.response = response
        self.calls = 0

    def fetch(self, request: dict[str, object]) -> GeocoderFetchedResponse:
        self.calls += 1
        return self.response


def install_cache_fixture(
    resolver: GeospatialResolver,
    observation: PostingObservation,
    *,
    requested_url: str | None = None,
    content_type: str = "application/json",
) -> GeocoderCacheEntry:
    request = normalized_request(
        observation,
        LocationPrivacyContext.PUBLIC_OR_NON_RESIDENTIAL,
    )
    assert request is not None
    response = FakeClient().fetch(request)
    request_digest = fingerprint(
        {"provider": PROVIDER, "version": PROVIDER_VERSION, "request": request}
    )
    body_digest = sha256_hex(response.body)
    key = f"geocoder/{PROVIDER.lower()}/{PROVIDER_VERSION}/{request_digest}-{body_digest[:16]}.json"
    resolver.raw_store.write_bytes(key, response.body)
    artifact = RawArtifact.objects.create(
        object_key=key,
        sha256_digest=body_digest,
        byte_size=len(response.body),
        content_type=content_type,
    )
    return GeocoderCacheEntry.objects.create(
        provider=PROVIDER,
        provider_version=PROVIDER_VERSION,
        normalized_request=request,
        request_fingerprint=request_digest,
        requested_url=requested_url or build_url(request),
        final_url=build_url(request),
        http_status=200,
        content_type=content_type,
        raw_artifact=artifact,
        response_payload=json.loads(response.body),
    )


class Gate010C2BatchTests(TestCase):
    def setUp(self) -> None:
        self.raw = TemporaryDirectory()
        self.addCleanup(self.raw.cleanup)

    def resolver(self, client: FakeClient) -> GeospatialResolver:
        return GeospatialResolver(client=client, raw_store=RawObjectStore(self.raw.name))

    def test_dry_run_pins_green_cohort_without_writes_or_network(self) -> None:
        upstream = create_dashboard_upstream(suffix="c2-dry")
        client = FakeClient()
        result = resolve_premium_run_locations(
            upstream["premium_run"].pk,
            dry_run=True,
            resolver=self.resolver(client),
        )
        assert result.selected == 1
        assert result.premium_run_fingerprint == upstream["premium_run"].input_fingerprint
        assert result.selected_observation_ids == (str(upstream["observation"].pk),)
        assert result.created == 0 and result.resolution_ids == ()
        assert client.calls == 0
        assert PostingLocationResolution.objects.count() == 0

    def test_non_green_assessment_is_not_selected(self) -> None:
        upstream = create_dashboard_upstream(green_result="NOT_GREEN", suffix="c2-not-green")
        result = resolve_premium_run_locations(
            upstream["premium_run"].pk,
            dry_run=True,
            resolver=self.resolver(FakeClient()),
        )
        assert result.selected == 0
        assert result.selected_observation_ids == ()

    def test_exact_replay_reuses_resolution_and_geocoder_cache(self) -> None:
        upstream = create_dashboard_upstream(suffix="c2-replay")
        client = FakeClient()
        resolver = self.resolver(client)
        first = resolve_premium_run_locations(upstream["premium_run"].pk, resolver=resolver)
        second = resolve_premium_run_locations(upstream["premium_run"].pk, resolver=resolver)
        resolution = PostingLocationResolution.objects.get(pk=first.resolution_ids[0])
        assert first.created == 1 and second.created == 0
        assert first.resolution_ids == second.resolution_ids
        assert resolution.input_fingerprint == resolution_input_fingerprint(
            upstream["observation"],
            LocationPrivacyContext.PUBLIC_OR_NON_RESIDENTIAL,
        )
        assert first.network_requests == 1
        assert second.network_requests == 0
        assert client.calls == 1
        assert PostingLocationResolution.objects.count() == 1

    def test_protected_contexts_without_municipality_fail_closed_without_network(self) -> None:
        for index, context in enumerate(("PRIVATE_RESIDENCE", "CONFIDENTIAL_PRIVATE_RESIDENCE")):
            upstream = create_dashboard_upstream(
                privacy_context=context,
                suffix=f"c2-private-{index}",
            )
            client = FakeClient()
            result = resolve_premium_run_locations(
                upstream["premium_run"].pk,
                resolver=self.resolver(client),
            )
            resolution = PostingLocationResolution.objects.get(pk=result.resolution_ids[0])
            assert result.privacy_contexts == {context: 1}
            assert resolution.privacy_context == LocationPrivacyContext(context)
            assert resolution.privacy_display_level == "HIDDEN"
            assert resolution.public_display_latitude is None
            assert resolution.public_display_longitude is None
            assert resolution.resolution_status == "UNRESOLVED"
            assert client.calls == 0
        assert GeocoderCacheEntry.objects.count() == 0

    def test_existing_identity_with_different_material_fails_closed(self) -> None:
        upstream = create_dashboard_upstream(suffix="c2-conflict")
        resolver = self.resolver(FakeClient())
        resolver.resolve(upstream["observation"])
        upstream["observation"].location_locality = "Zurich"
        with self.assertRaises(GeospatialResolutionError):
            resolver.resolve(upstream["observation"])

    def test_batch_preflight_conflict_is_order_independent_and_writes_nothing(self) -> None:
        first = create_dashboard_upstream(suffix="c2-preflight-a")
        second = create_dashboard_upstream(suffix="c2-preflight-b")
        second_premium = second["premium"]
        combined = PremiumSegmentAssessment.objects.create(
            run=first["premium_run"],
            posting_observation=second["observation"],
            green_relevance_assessment=second["green"],
            green_result_origin=second_premium.green_result_origin,
            effective_green_result=second_premium.effective_green_result,
            segment=second_premium.segment,
            assessment_status=second_premium.assessment_status,
            method=second_premium.method,
            evidence_strength=second_premium.evidence_strength,
            matched_signal_ids=second_premium.matched_signal_ids,
            matched_fields_and_scopes=second_premium.matched_fields_and_scopes,
            matched_evidence=second_premium.matched_evidence,
            prohibited_inferences=second_premium.prohibited_inferences,
            privacy_context=second_premium.privacy_context,
            evidence=second_premium.evidence,
            created_at=second_premium.created_at,
        )
        conflict = PostingLocationResolution.objects.create(
            posting_observation=second["observation"],
            resolver_version="geospatial-v0.1",
            privacy_context="PUBLIC_OR_NON_RESIDENTIAL",
            resolution_status="UNRESOLVED",
            location_precision="UNKNOWN",
            coordinate_source="UNKNOWN",
            privacy_display_level="HIDDEN",
            input_fingerprint="f" * 64,
            evidence={"fixture": "conflicting-existing-resolution"},
        )
        expected = resolution_input_fingerprint(
            second["observation"],
            LocationPrivacyContext.PUBLIC_OR_NON_RESIDENTIAL,
        )
        assert conflict.input_fingerprint != expected
        baseline = {
            "resolutions": PostingLocationResolution.objects.count(),
            "cache": GeocoderCacheEntry.objects.count(),
            "raw": RawArtifact.objects.count(),
            "reviews": GeocodingReviewItem.objects.count(),
        }
        client = FakeClient()
        resolver = self.resolver(client)
        orders = (
            [first["premium"], combined],
            [combined, first["premium"]],
        )
        for order in orders:
            for dry_run in (True, False):
                with patch("observations.geospatial_batch._targets", return_value=order):
                    with self.assertRaises(GeospatialBatchError):
                        resolve_premium_run_locations(
                            first["premium_run"].pk,
                            dry_run=dry_run,
                            resolver=resolver,
                        )
        assert client.calls == 0
        assert PostingLocationResolution.objects.count() == baseline["resolutions"]
        assert GeocoderCacheEntry.objects.count() == baseline["cache"]
        assert RawArtifact.objects.count() == baseline["raw"]
        assert GeocodingReviewItem.objects.count() == baseline["reviews"]

    def test_management_command_emits_deterministic_json_dry_run(self) -> None:
        upstream = create_dashboard_upstream(suffix="c2-command")
        output = StringIO()
        with override_settings(CORE_RAW_OBJECT_STORE_PATH=Path(self.raw.name)):
            call_command(
                "resolve_premium_locations",
                premium_run=str(upstream["premium_run"].pk),
                dry_run=True,
                json=True,
                stdout=output,
            )
        payload = json.loads(output.getvalue())
        assert payload["batch_version"] == "geospatial-resolution-batch-v0.1"
        assert payload["selected"] == 1
        assert payload["created"] == 0

    def test_non_operational_database_cannot_use_default_raw_store(self) -> None:
        upstream = create_dashboard_upstream(suffix="c3-raw-scope")
        with override_settings(
            CORE_RAW_OBJECT_STORE_PATH=settings.BASE_DIR / "data" / "raw",
            JOB_OBSERVATORY_OPERATIONAL_DB_NAME="not-this-test-database",
        ):
            with self.assertRaisesRegex(
                GeospatialBatchError,
                "non-operational database must use a distinct isolated RAW store",
            ):
                resolve_premium_run_locations(upstream["premium_run"].pk, dry_run=True)
        assert PostingLocationResolution.objects.count() == 0

    def test_exact_orphan_raw_bytes_are_reused_and_registered_locally(self) -> None:
        upstream = create_dashboard_upstream(suffix="c3-orphan")
        client = FakeClient()
        request = normalized_request(
            upstream["observation"],
            LocationPrivacyContext.PUBLIC_OR_NON_RESIDENTIAL,
        )
        assert request is not None
        response = client.fetch(request)
        client.calls = 0
        client.requests.clear()
        request_digest = fingerprint(
            {"provider": PROVIDER, "version": PROVIDER_VERSION, "request": request}
        )
        body_digest = sha256_hex(response.body)
        key = (
            f"geocoder/{PROVIDER.lower()}/{PROVIDER_VERSION}/"
            f"{request_digest}-{body_digest[:16]}.json"
        )
        path = RawObjectStore(self.raw.name).write_bytes(key, response.body)
        original_mtime = path.stat().st_mtime_ns

        result = resolve_premium_run_locations(
            upstream["premium_run"].pk,
            resolver=self.resolver(client),
        )

        artifact = RawArtifact.objects.get(object_key=key)
        assert result.created == 1
        assert client.calls == 1
        assert path.stat().st_mtime_ns == original_mtime
        assert artifact.sha256_digest == body_digest
        assert GeocoderCacheEntry.objects.get(raw_artifact=artifact)

    def test_conflicting_orphan_raw_bytes_fail_without_overwrite_or_db_evidence(
        self,
    ) -> None:
        upstream = create_dashboard_upstream(suffix="c3-orphan-conflict")
        client = FakeClient()
        request = normalized_request(
            upstream["observation"],
            LocationPrivacyContext.PUBLIC_OR_NON_RESIDENTIAL,
        )
        assert request is not None
        response = client.fetch(request)
        client.calls = 0
        client.requests.clear()
        request_digest = fingerprint(
            {"provider": PROVIDER, "version": PROVIDER_VERSION, "request": request}
        )
        body_digest = sha256_hex(response.body)
        key = (
            f"geocoder/{PROVIDER.lower()}/{PROVIDER_VERSION}/"
            f"{request_digest}-{body_digest[:16]}.json"
        )
        conflicting = b'{"conflicting":"bytes"}'
        store = RawObjectStore(self.raw.name)
        store.write_bytes(key, conflicting)
        baseline = {
            "raw": RawArtifact.objects.count(),
            "cache": GeocoderCacheEntry.objects.count(),
            "resolution": PostingLocationResolution.objects.count(),
            "review": GeocodingReviewItem.objects.count(),
        }

        with self.assertRaisesRegex(GeospatialBatchError, "rolled back"):
            resolve_premium_run_locations(
                upstream["premium_run"].pk,
                resolver=self.resolver(client),
            )

        assert store.read_bytes(key) == conflicting
        assert RawArtifact.objects.count() == baseline["raw"]
        assert GeocoderCacheEntry.objects.count() == baseline["cache"]
        assert PostingLocationResolution.objects.count() == baseline["resolution"]
        assert GeocodingReviewItem.objects.count() == baseline["review"]

    def test_existing_cache_is_revalidated_against_immutable_raw_bytes(self) -> None:
        first = create_dashboard_upstream(suffix="c3-cache-first")
        second = create_dashboard_upstream(suffix="c3-cache-second")
        client = FakeClient()
        resolver = self.resolver(client)
        resolver.resolve(first["observation"])
        cache = GeocoderCacheEntry.objects.get()
        raw_path = resolver.raw_store.object_path(cache.raw_artifact.object_key)
        raw_path.write_bytes(b'{"tampered":"payload"}')
        baseline = PostingLocationResolution.objects.count()

        with self.assertRaisesRegex(
            GeospatialResolutionError,
            "existing geocoder RAW object conflicts",
        ):
            resolver.resolve(second["observation"])

        assert PostingLocationResolution.objects.count() == baseline
        assert client.calls == 1

    def test_batch_provider_failure_rolls_back_every_new_database_row(self) -> None:
        first = create_dashboard_upstream(location_region="ZH", suffix="c3-batch-a")
        second = create_dashboard_upstream(location_region="BE", suffix="c3-batch-b")
        second_premium = second["premium"]
        combined = PremiumSegmentAssessment.objects.create(
            run=first["premium_run"],
            posting_observation=second["observation"],
            green_relevance_assessment=second["green"],
            green_result_origin=second_premium.green_result_origin,
            effective_green_result=second_premium.effective_green_result,
            segment=second_premium.segment,
            assessment_status=second_premium.assessment_status,
            method=second_premium.method,
            evidence_strength=second_premium.evidence_strength,
            matched_signal_ids=second_premium.matched_signal_ids,
            matched_fields_and_scopes=second_premium.matched_fields_and_scopes,
            matched_evidence=second_premium.matched_evidence,
            prohibited_inferences=second_premium.prohibited_inferences,
            privacy_context=second_premium.privacy_context,
            evidence=second_premium.evidence,
            created_at=second_premium.created_at,
        )
        baseline = {
            "raw": RawArtifact.objects.count(),
            "cache": GeocoderCacheEntry.objects.count(),
            "resolution": PostingLocationResolution.objects.count(),
            "review": GeocodingReviewItem.objects.count(),
        }
        client = RegionFailingClient()
        resolver = self.resolver(client)
        with patch(
            "observations.geospatial_batch._targets",
            return_value=[first["premium"], combined],
        ):
            with self.assertRaisesRegex(GeospatialBatchError, "rolled back"):
                resolve_premium_run_locations(
                    first["premium_run"].pk,
                    resolver=resolver,
                )

        assert client.calls == 2
        assert RawArtifact.objects.count() == baseline["raw"]
        assert GeocoderCacheEntry.objects.count() == baseline["cache"]
        assert PostingLocationResolution.objects.count() == baseline["resolution"]
        assert GeocodingReviewItem.objects.count() == baseline["review"]

    def test_batch_raw_conflict_rolls_back_database_in_both_orders(self) -> None:
        first = create_dashboard_upstream(location_region="ZH", suffix="c3-raw-batch-a")
        second = create_dashboard_upstream(location_region="BE", suffix="c3-raw-batch-b")
        second_premium = second["premium"]
        combined = PremiumSegmentAssessment.objects.create(
            run=first["premium_run"],
            posting_observation=second["observation"],
            green_relevance_assessment=second["green"],
            green_result_origin=second_premium.green_result_origin,
            effective_green_result=second_premium.effective_green_result,
            segment=second_premium.segment,
            assessment_status=second_premium.assessment_status,
            method=second_premium.method,
            evidence_strength=second_premium.evidence_strength,
            matched_signal_ids=second_premium.matched_signal_ids,
            matched_fields_and_scopes=second_premium.matched_fields_and_scopes,
            matched_evidence=second_premium.matched_evidence,
            prohibited_inferences=second_premium.prohibited_inferences,
            privacy_context=second_premium.privacy_context,
            evidence=second_premium.evidence,
            created_at=second_premium.created_at,
        )
        baseline = {
            "raw": RawArtifact.objects.count(),
            "cache": GeocoderCacheEntry.objects.count(),
            "resolution": PostingLocationResolution.objects.count(),
            "review": GeocodingReviewItem.objects.count(),
        }
        request = normalized_request(
            second["observation"],
            LocationPrivacyContext.PUBLIC_OR_NON_RESIDENTIAL,
        )
        assert request is not None
        response = FakeClient().fetch(request)
        request_digest = fingerprint(
            {"provider": PROVIDER, "version": PROVIDER_VERSION, "request": request}
        )
        body_digest = sha256_hex(response.body)
        key = (
            f"geocoder/{PROVIDER.lower()}/{PROVIDER_VERSION}/"
            f"{request_digest}-{body_digest[:16]}.json"
        )
        conflicting = b'{"conflicting":"batch-bytes"}'

        for index, order in enumerate(([first["premium"], combined], [combined, first["premium"]])):
            raw_root = Path(self.raw.name) / f"raw-conflict-order-{index}"
            store = RawObjectStore(raw_root)
            store.write_bytes(key, conflicting)
            client = FakeClient()
            with patch("observations.geospatial_batch._targets", return_value=order):
                with self.assertRaisesRegex(GeospatialBatchError, "rolled back"):
                    resolve_premium_run_locations(
                        first["premium_run"].pk,
                        resolver=GeospatialResolver(client=client, raw_store=store),
                    )
            assert client.calls == (2 if index == 0 else 1)
            assert store.read_bytes(key) == conflicting
            assert RawArtifact.objects.count() == baseline["raw"]
            assert GeocoderCacheEntry.objects.count() == baseline["cache"]
            assert PostingLocationResolution.objects.count() == baseline["resolution"]
            assert GeocodingReviewItem.objects.count() == baseline["review"]

        reverse_client = RegionFailingClient()
        with patch(
            "observations.geospatial_batch._targets",
            return_value=[combined, first["premium"]],
        ):
            with self.assertRaisesRegex(GeospatialBatchError, "rolled back"):
                resolve_premium_run_locations(
                    first["premium_run"].pk,
                    resolver=self.resolver(reverse_client),
                )
        assert reverse_client.calls == 1
        assert RawArtifact.objects.count() == baseline["raw"]
        assert GeocoderCacheEntry.objects.count() == baseline["cache"]
        assert PostingLocationResolution.objects.count() == baseline["resolution"]
        assert GeocodingReviewItem.objects.count() == baseline["review"]

    def test_custom_operational_raw_root_is_enforced_for_default_store(self) -> None:
        upstream = create_dashboard_upstream(suffix="c3-custom-root")
        operational_root = Path(self.raw.name) / "operational"
        isolated_root = Path(self.raw.name) / "isolated"
        operational_root.mkdir()
        isolated_root.mkdir()
        common = {
            "JOB_OBSERVATORY_OPERATIONAL_DB_NAME": "not-this-test-database",
            "JOB_OBSERVATORY_OPERATIONAL_RAW_STORE_PATH": operational_root,
        }
        with override_settings(
            **common,
            CORE_RAW_OBJECT_STORE_PATH=operational_root,
        ):
            with self.assertRaisesRegex(
                GeospatialBatchError,
                "non-operational database must use a distinct isolated RAW store",
            ):
                resolve_premium_run_locations(upstream["premium_run"].pk, dry_run=True)
        with override_settings(
            **common,
            CORE_RAW_OBJECT_STORE_PATH=isolated_root,
        ):
            result = resolve_premium_run_locations(upstream["premium_run"].pk, dry_run=True)
        assert result.selected == 1
        assert PostingLocationResolution.objects.count() == 0

    def test_injected_resolver_cannot_bypass_operational_raw_root_scope(self) -> None:
        upstream = create_dashboard_upstream(suffix="c3-injected-root")
        operational_root = Path(self.raw.name) / "designated-operational"
        isolated_root = Path(self.raw.name) / "designated-isolated"
        operational_root.mkdir()
        isolated_root.mkdir()
        client = FakeClient()
        baseline_raw = RawArtifact.objects.count()
        common = {
            "JOB_OBSERVATORY_OPERATIONAL_DB_NAME": "not-this-test-database",
            "JOB_OBSERVATORY_OPERATIONAL_RAW_STORE_PATH": operational_root,
        }
        with override_settings(**common):
            with self.assertRaisesRegex(
                GeospatialBatchError,
                "non-operational database must use a distinct isolated RAW store",
            ):
                resolve_premium_run_locations(
                    upstream["premium_run"].pk,
                    resolver=GeospatialResolver(
                        client=client,
                        raw_store=RawObjectStore(operational_root),
                    ),
                )
            result = resolve_premium_run_locations(
                upstream["premium_run"].pk,
                dry_run=True,
                resolver=GeospatialResolver(
                    client=client,
                    raw_store=RawObjectStore(isolated_root),
                ),
            )
        assert result.selected == 1
        assert client.calls == 0
        assert PostingLocationResolution.objects.count() == 0
        assert RawArtifact.objects.count() == baseline_raw
        assert GeocoderCacheEntry.objects.count() == 0

    def test_cache_rejects_same_origin_but_non_deterministic_requested_url(self) -> None:
        upstream = create_dashboard_upstream(suffix="c3-cache-url")
        resolver = self.resolver(FakeClient())
        request = normalized_request(
            upstream["observation"],
            LocationPrivacyContext.PUBLIC_OR_NON_RESIDENTIAL,
        )
        assert request is not None
        wrong_request = dict(request)
        wrong_request["searchText"] = "Zurich ZH"
        install_cache_fixture(
            resolver,
            upstream["observation"],
            requested_url=build_url(wrong_request),
        )

        with self.assertRaisesRegex(
            GeospatialResolutionError,
            "cache metadata conflicts",
        ):
            resolver.resolve(upstream["observation"])
        assert PostingLocationResolution.objects.count() == 0

    def test_cache_rejects_unaccepted_content_type_even_with_valid_json(self) -> None:
        upstream = create_dashboard_upstream(suffix="c3-cache-content-type")
        resolver = self.resolver(FakeClient())
        install_cache_fixture(
            resolver,
            upstream["observation"],
            content_type="text/plain",
        )

        with self.assertRaisesRegex(
            GeospatialResolutionError,
            "cache metadata conflicts",
        ):
            resolver.resolve(upstream["observation"])
        assert PostingLocationResolution.objects.count() == 0

    def test_fetched_response_requires_exact_requested_url_and_content_type(self) -> None:
        for index, defect in enumerate(("requested_url", "content_type")):
            upstream = create_dashboard_upstream(suffix=f"c3-response-{index}")
            baseline_raw = RawArtifact.objects.count()
            request = normalized_request(
                upstream["observation"],
                LocationPrivacyContext.PUBLIC_OR_NON_RESIDENTIAL,
            )
            assert request is not None
            valid = FakeClient().fetch(request)
            response = GeocoderFetchedResponse(
                (
                    "https://api3.geo.admin.ch/rest/services/api/SearchServer"
                    "?type=locations&searchText=wrong"
                    if defect == "requested_url"
                    else valid.requested_url
                ),
                valid.final_url,
                valid.status_code,
                "text/plain" if defect == "content_type" else valid.content_type,
                valid.body,
            )
            client = StaticResponseClient(response)
            resolver = GeospatialResolver(
                client=client,
                raw_store=RawObjectStore(Path(self.raw.name) / f"response-{index}"),
            )
            with self.assertRaises(GeospatialResolutionError):
                resolver.resolve(upstream["observation"])
            assert client.calls == 1
            assert RawArtifact.objects.count() == baseline_raw
        assert PostingLocationResolution.objects.count() == 0
        assert GeocoderCacheEntry.objects.count() == 0
        assert GeocodingReviewItem.objects.count() == 0

    def test_batch_raw_metadata_conflict_rolls_back_database_in_both_orders(self) -> None:
        first = create_dashboard_upstream(location_region="ZH", suffix="c3-meta-a")
        second = create_dashboard_upstream(location_region="BE", suffix="c3-meta-b")
        second_premium = second["premium"]
        combined = PremiumSegmentAssessment.objects.create(
            run=first["premium_run"],
            posting_observation=second["observation"],
            green_relevance_assessment=second["green"],
            green_result_origin=second_premium.green_result_origin,
            effective_green_result=second_premium.effective_green_result,
            segment=second_premium.segment,
            assessment_status=second_premium.assessment_status,
            method=second_premium.method,
            evidence_strength=second_premium.evidence_strength,
            matched_signal_ids=second_premium.matched_signal_ids,
            matched_fields_and_scopes=second_premium.matched_fields_and_scopes,
            matched_evidence=second_premium.matched_evidence,
            prohibited_inferences=second_premium.prohibited_inferences,
            privacy_context=second_premium.privacy_context,
            evidence=second_premium.evidence,
            created_at=second_premium.created_at,
        )
        request = normalized_request(
            second["observation"],
            LocationPrivacyContext.PUBLIC_OR_NON_RESIDENTIAL,
        )
        assert request is not None
        response = FakeClient().fetch(request)
        request_digest = fingerprint(
            {"provider": PROVIDER, "version": PROVIDER_VERSION, "request": request}
        )
        body_digest = sha256_hex(response.body)
        key = (
            f"geocoder/{PROVIDER.lower()}/{PROVIDER_VERSION}/"
            f"{request_digest}-{body_digest[:16]}.json"
        )
        baseline_artifact = RawArtifact.objects.create(
            object_key=key,
            sha256_digest=body_digest,
            byte_size=len(response.body),
            content_type="text/plain",
        )
        baseline = {
            "raw": RawArtifact.objects.count(),
            "cache": GeocoderCacheEntry.objects.count(),
            "resolution": PostingLocationResolution.objects.count(),
            "review": GeocodingReviewItem.objects.count(),
        }

        for index, order in enumerate(([first["premium"], combined], [combined, first["premium"]])):
            raw_root = Path(self.raw.name) / f"metadata-order-{index}"
            store = RawObjectStore(raw_root)
            store.write_bytes(key, response.body)
            client = FakeClient()
            with patch("observations.geospatial_batch._targets", return_value=order):
                with self.assertRaisesRegex(GeospatialBatchError, "rolled back"):
                    resolve_premium_run_locations(
                        first["premium_run"].pk,
                        resolver=GeospatialResolver(client=client, raw_store=store),
                    )
            assert RawArtifact.objects.get(pk=baseline_artifact.pk).content_type == "text/plain"
            assert RawArtifact.objects.count() == baseline["raw"]
            assert GeocoderCacheEntry.objects.count() == baseline["cache"]
            assert PostingLocationResolution.objects.count() == baseline["resolution"]
            assert GeocodingReviewItem.objects.count() == baseline["review"]


@pytest.mark.django_db(transaction=True)
def test_concurrent_identical_resolution_converges_on_postgresql() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("authoritative advisory-lock contention requires PostgreSQL")
    upstream = create_dashboard_upstream(suffix="c2-concurrent")
    observation_id = upstream["observation"].pk
    ready = Barrier(2)
    clients: list[FakeClient] = []
    with TemporaryDirectory() as raw_path:

        def worker() -> str:
            close_old_connections()
            client = FakeClient()
            clients.append(client)
            observation = PostingObservation.objects.get(pk=observation_id)
            ready.wait(timeout=10)
            resolution = GeospatialResolver(
                client=client,
                raw_store=RawObjectStore(raw_path),
            ).resolve(observation)
            close_old_connections()
            return str(resolution.pk)

        with ThreadPoolExecutor(max_workers=2) as pool:
            resolution_ids = list(pool.map(lambda _: worker(), range(2)))

    assert len(set(resolution_ids)) == 1
    assert (
        PostingLocationResolution.objects.filter(posting_observation_id=observation_id).count() == 1
    )
    assert GeocoderCacheEntry.objects.count() == 1
    assert sum(client.calls for client in clients) == 1
