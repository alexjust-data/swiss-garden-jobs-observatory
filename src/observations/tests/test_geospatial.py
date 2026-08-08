from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from tempfile import TemporaryDirectory

import pytest
from django.db import IntegrityError, transaction
from django.test import TestCase

from core.hashing import sha256_hex
from core.models import RawArtifact
from core.storage import RawObjectStore
from observations.geospatial import (
    GeocoderFetchedResponse,
    GeospatialResolutionError,
    GeospatialResolver,
    validate_coordinates,
)
from observations.models import (
    CollectionRun,
    GeocoderCacheEntry,
    GeocodingReviewItem,
    ImmutablePostingLocationResolutionError,
    Posting,
    PostingLocationResolution,
    PostingObservation,
)
from reference_data.models import Municipality
from sources.models import Source


def payload(
    municipality: str = "Winterthur",
    postcode: str = "8400",
    lon: float = 8.7241,
    lat: float = 47.4988,
    origin: str = "zipcode",
) -> bytes:
    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {
                        "attrs": {
                            "municipality": municipality,
                            "canton": "ZH",
                            "country": "CH",
                            "postcode": postcode,
                            "origin": origin,
                            "label": f"{postcode} {municipality}",
                        }
                    },
                }
            ],
        },
        sort_keys=True,
    ).encode()


class FakeClient:
    def __init__(self, body: bytes | None = None) -> None:
        self.body = body or payload()
        self.calls = 0

    def fetch(self, request: dict[str, object]) -> GeocoderFetchedResponse:
        self.calls += 1
        url = "https://api3.geo.admin.ch/rest/services/api/SearchServer?type=locations"
        return GeocoderFetchedResponse(url, url, 200, "application/json", self.body)


class Gate006Tests(TestCase):
    def setUp(self) -> None:
        self.raw = TemporaryDirectory()
        self.addCleanup(self.raw.cleanup)
        self.store = RawObjectStore(self.raw.name)
        self.municipality = Municipality.objects.create(
            bfs_code=230,
            snapshot_date="2026-01-01",
            municipality_name="Winterthur",
            canton_code="ZH",
            canton_name="Zurich",
            district="Winterthur",
            bfs_language_region_code=1,
            language_region="GERMAN",
            statistical_city=True,
            degurb2021=1,
            priority_tier="TIER_1",
        )
        self.source = self.make_source("SRC-OFF-CITY-WINTERTHUR", "DIRECT_PUBLIC_EMPLOYER")

    def make_source(self, source_id: str, source_type: str) -> Source:
        return Source.objects.create(
            source_id=source_id,
            source_name=source_id,
            domain="jobs.winterthur.ch",
            source_family="OFFICIAL",
            source_type=source_type,
            priority="P1",
            coverage_scope="Winterthur",
            canonicality="CANONICAL",
            platform_family="REXX_SYSTEMS",
            access_method="HTML",
            automation_status="COLLECTOR_CANDIDATE",
            legal_review_status="APPROVED",
            verification_status="VERIFIED",
            official_url="https://jobs.winterthur.ch/",
        )

    def observation(
        self,
        posting_id: str = "8280",
        source: Source | None = None,
        street: str = "",
        locality: str = "Winterthur",
        postcode: str = "8400",
        country: str = "CH",
        geo: tuple[float, float] | None = None,
    ) -> PostingObservation:
        selected = source or self.source
        now = datetime(2026, 8, 8, 8, tzinfo=UTC)
        run = CollectionRun.objects.create(
            source=selected, listing_url="https://jobs.winterthur.ch/", started_at=now
        )
        posting = Posting.objects.create(
            source=selected,
            source_posting_id=posting_id,
            first_seen_at=now,
            last_seen_at=now,
            latest_canonical_url=f"https://jobs.winterthur.ch/?yid={posting_id}",
        )
        body = posting_id.encode()
        key = f"source/{run.pk}/{posting_id}.html"
        self.store.write_bytes(key, body)
        artifact = RawArtifact.objects.create(
            object_key=key,
            sha256_digest=sha256_hex(body),
            byte_size=len(body),
            content_type="text/html",
        )
        location: dict[str, object] = {
            "address": {
                "streetAddress": street,
                "addressLocality": locality,
                "postalCode": postcode,
                "addressCountry": country,
            }
        }
        if geo:
            location["geo"] = {"latitude": geo[0], "longitude": geo[1]}
        return PostingObservation.objects.create(
            collection_run=run,
            posting=posting,
            source=selected,
            source_posting_id=posting_id,
            canonical_url=posting.latest_canonical_url,
            title="Gardener",
            location_street=street,
            location_locality=locality,
            location_postal_code=postcode,
            location_country=country,
            municipality=self.municipality,
            raw_artifact=artifact,
            structured_payload={"@type": "JobPosting", "jobLocation": location},
            contract_payload={
                "schema_version": "1.2",
                "raw_location": f"{street} {postcode} {locality}",
                "normalized_location": {
                    "bfs_code": 230,
                    "municipality": "Winterthur",
                    "canton_code": "ZH",
                },
            },
        )

    def resolver(self, client: FakeClient) -> GeospatialResolver:
        return GeospatialResolver(client=client, raw_store=self.store)

    def test_bfs_identity_postcode_and_multiple_precision(self) -> None:
        first = self.resolver(FakeClient()).resolve(self.observation())
        assert (first.resolution_status, first.municipality.pk, first.location_precision) == (
            "RESOLVED",
            230,
            "POSTCODE",
        )
        second = self.resolver(FakeClient()).resolve(
            self.observation("8281", street="Diverse Standorte")
        )
        assert second.municipality.pk == 230
        assert second.location_precision == "REMOTE_OR_MULTIPLE"

    def test_contradiction_and_ambiguity_enter_review(self) -> None:
        contradiction = self.resolver(FakeClient(payload("Zurich", "8000"))).resolve(
            self.observation()
        )
        assert contradiction.resolution_status == "REVIEW"
        assert contradiction.municipality.pk == 230 and contradiction.latitude is None
        assert (
            GeocodingReviewItem.objects.get(location_resolution=contradiction).reason
            == "GEOCODER_CONTRADICTS_BFS"
        )
        data = json.loads(payload())
        extra = deepcopy(data["features"][0])
        extra["geometry"]["coordinates"] = [8.75, 47.51]
        data["features"].append(extra)
        ambiguous = self.resolver(FakeClient(json.dumps(data).encode())).resolve(
            self.observation("8281", street="Teststrasse 1")
        )
        assert ambiguous.resolution_status == "REVIEW"
        assert (
            GeocodingReviewItem.objects.get(location_resolution=ambiguous).reason
            == "MULTIPLE_PLAUSIBLE_RESULTS"
        )

    def test_unexpected_country_is_review_without_network(self) -> None:
        client = FakeClient()
        resolution = self.resolver(client).resolve(self.observation(country="DE"))
        assert resolution.resolution_status == "REVIEW" and client.calls == 0

    def test_invalid_coordinates_are_rejected(self) -> None:
        for latitude, longitude in ((91, 8), (-91, 8), (47, 181), (47, -181)):
            with pytest.raises(GeospatialResolutionError):
                validate_coordinates(latitude, longitude)
        observation = self.observation()
        with pytest.raises(IntegrityError), transaction.atomic():
            PostingLocationResolution.objects.create(
                posting_observation=observation,
                resolver_version="bad",
                resolution_status="RESOLVED",
                municipality=self.municipality,
                latitude=100,
                longitude=8,
                location_precision="MUNICIPALITY",
                coordinate_source="MANUAL_REVIEW",
                geocoding_confidence=2,
                privacy_display_level="HIDDEN",
                input_fingerprint="a" * 64,
            )

    def test_cache_idempotency_and_versioning(self) -> None:
        first, second = self.observation("8280"), self.observation("8281")
        client = FakeClient()
        resolver = self.resolver(client)
        resolution = resolver.resolve(first)
        assert resolver.resolve(first).pk == resolution.pk
        resolver.resolve(second)
        assert client.calls == 1 and resolver.stats.cache_hits == 1
        assert GeocoderCacheEntry.objects.count() == 1
        future = GeospatialResolver(
            client=client, raw_store=self.store, resolver_version="geospatial-v0.2"
        )
        assert future.resolve(first).pk != resolution.pk
        assert PostingLocationResolution.objects.count() == 3

    def test_private_exact_coordinate_is_never_public(self) -> None:
        private = self.make_source("SRC-PRIVATE-TEST", "PRIVATE_HOUSEHOLD_DIRECT")
        resolution = self.resolver(FakeClient()).resolve(
            self.observation(
                "private", source=private, street="Confidential residence", geo=(47.5, 8.7)
            )
        )
        assert (resolution.latitude, resolution.longitude) == (47.5, 8.7)
        assert resolution.public_display_latitude is None
        assert resolution.public_display_longitude is None
        assert resolution.privacy_display_level == "HIDDEN"

    def test_append_only_and_source_evidence_unchanged(self) -> None:
        observation = self.observation()
        structured, contract = (
            deepcopy(observation.structured_payload),
            deepcopy(observation.contract_payload),
        )
        raw = self.store.read_bytes(observation.raw_artifact.object_key)
        resolution = self.resolver(FakeClient()).resolve(observation)
        resolution.resolution_status = "UNRESOLVED"
        with pytest.raises(ImmutablePostingLocationResolutionError):
            resolution.save()
        with pytest.raises(ImmutablePostingLocationResolutionError):
            PostingLocationResolution.objects.filter(pk=resolution.pk).update(
                resolution_status="UNRESOLVED"
            )
        with pytest.raises(ImmutablePostingLocationResolutionError):
            PostingLocationResolution.objects.filter(pk=resolution.pk).delete()
        with pytest.raises(ImmutablePostingLocationResolutionError):
            PostingLocationResolution.objects.bulk_update([resolution], ["resolution_status"])
        observation.refresh_from_db()
        assert observation.structured_payload == structured
        assert observation.contract_payload == contract
        assert self.store.read_bytes(observation.raw_artifact.object_key) == raw
