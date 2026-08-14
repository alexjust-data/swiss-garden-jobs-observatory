from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from tempfile import TemporaryDirectory
from threading import Barrier

import pytest
from django.core.management import call_command
from django.db import close_old_connections, connection
from django.test import TestCase

from core.storage import RawObjectStore
from dashboard.tests.factories import create_dashboard_upstream
from observations.geospatial import (
    GeocoderFetchedResponse,
    GeospatialResolutionError,
    GeospatialResolver,
    LocationPrivacyContext,
)
from observations.geospatial_batch import resolve_premium_run_locations
from observations.models import GeocoderCacheEntry, PostingLocationResolution, PostingObservation


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
        assert first.created == 1 and second.created == 0
        assert first.resolution_ids == second.resolution_ids
        assert first.network_requests == 1
        assert second.network_requests == 0
        assert client.calls == 1
        assert PostingLocationResolution.objects.count() == 1

    def test_protected_contexts_are_preserved_and_public_coordinates_are_hidden(self) -> None:
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
            cache = GeocoderCacheEntry.objects.get(
                pk=resolution.evidence["geocoder"]["cache_entry_id"]
            )
            assert cache.normalized_request["origins"] == "gg25"
            assert "street" not in cache.normalized_request

    def test_existing_identity_with_different_material_fails_closed(self) -> None:
        upstream = create_dashboard_upstream(suffix="c2-conflict")
        resolver = self.resolver(FakeClient())
        resolver.resolve(upstream["observation"])
        upstream["observation"].location_locality = "Zurich"
        with self.assertRaises(GeospatialResolutionError):
            resolver.resolve(upstream["observation"])

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
