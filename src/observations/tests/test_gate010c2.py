from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.db import close_old_connections, connection
from django.test import TestCase

from core.models import RawArtifact
from core.storage import RawObjectStore
from dashboard.tests.factories import create_dashboard_upstream
from observations.geospatial import (
    GeocoderFetchedResponse,
    GeospatialResolutionError,
    GeospatialResolver,
    LocationPrivacyContext,
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
        url = "https://api3.geo.admin.ch/rest/services/api/SearchServer?type=locations"
        return GeocoderFetchedResponse(url, url, 200, "application/json", body)


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
        result = resolve_premium_run_locations(upstream["premium_run"].pk, dry_run=True)
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
        for index, context in enumerate(
            ("PRIVATE_RESIDENCE", "CONFIDENTIAL_PRIVATE_RESIDENCE")
        ):
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
        PostingLocationResolution.objects.filter(
            posting_observation_id=observation_id
        ).count()
        == 1
    )
    assert GeocoderCacheEntry.objects.count() == 1
    assert sum(client.calls for client in clients) == 1
