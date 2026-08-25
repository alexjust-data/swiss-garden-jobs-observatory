from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from tempfile import TemporaryDirectory

import pytest
from django.test import TestCase

from core.hashing import sha256_hex
from core.models import RawArtifact
from core.storage import RawObjectStore
from observations.geospatial import (
    LEGACY_RESOLVER_VERSION,
    RESOLVER_VERSION,
    GeospatialResolver,
    LocationPrivacyContext,
    fingerprint,
    normalized_request,
    resolution_input_material,
)
from observations.models import (
    CollectionRun,
    GeocodingReviewItem,
    Posting,
    PostingLocationResolution,
    PostingObservation,
)
from observations.tests.test_geospatial import FakeClient, payload
from reference_data.models import Municipality
from sources.models import Source


class Gate010C5Tests(TestCase):
    def setUp(self) -> None:
        self.raw = TemporaryDirectory()
        self.addCleanup(self.raw.cleanup)
        self.store = RawObjectStore(self.raw.name)
        self.winterthur = self.municipality(230, "Winterthur", "ZH")
        self.zurich = self.municipality(261, "Zürich", "ZH")
        self.city_source = self.source("SRC-OFF-CITY-WINTERTHUR", "REXX_SYSTEMS")
        self.zurich_source = self.source("SRC-OFF-CANTON-ZH", "SOLIQUE_LINKED")

    @staticmethod
    def municipality(bfs: int, name: str, canton: str) -> Municipality:
        return Municipality.objects.create(
            bfs_code=bfs,
            snapshot_date="2026-01-01",
            municipality_name=name,
            canton_code=canton,
            canton_name=canton,
            district="",
            bfs_language_region_code=1,
            language_region="GERMAN",
            statistical_city=True,
            degurb2021=1,
            priority_tier="TIER_1",
        )

    @staticmethod
    def source(source_id: str, platform: str) -> Source:
        return Source.objects.create(
            source_id=source_id,
            source_name=source_id,
            domain="jobs.example.invalid",
            source_family="OFFICIAL",
            source_type="DIRECT_PUBLIC_EMPLOYER",
            priority="P1",
            coverage_scope=source_id,
            canonicality="CANONICAL",
            platform_family=platform,
            access_method="HTML",
            automation_status="COLLECTOR_CANDIDATE",
            legal_review_status="APPROVED",
            verification_status="VERIFIED",
            official_url="https://jobs.example.invalid/",
        )

    def observation(
        self,
        posting_id: str,
        *,
        source: Source | None = None,
        municipality: Municipality | None = None,
        locality: str = "",
        region: str = "",
        country: str = "CH",
        street: str = "",
        postcode: str = "",
        raw_location: str = "",
        source_format: str = "",
    ) -> PostingObservation:
        selected = source or self.city_source
        now = datetime(2026, 8, 25, 8, tzinfo=UTC)
        run = CollectionRun.objects.create(
            source=selected,
            listing_url="https://jobs.example.invalid/",
            started_at=now,
        )
        posting = Posting.objects.create(
            source=selected,
            source_posting_id=posting_id,
            first_seen_at=now,
            last_seen_at=now,
            latest_canonical_url=f"https://jobs.example.invalid/{posting_id}",
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
        return PostingObservation.objects.create(
            collection_run=run,
            posting=posting,
            source=selected,
            source_posting_id=posting_id,
            canonical_url=posting.latest_canonical_url,
            title="Gärtner/in",
            location_street=street,
            location_locality=locality,
            location_region=region,
            location_postal_code=postcode,
            location_country=country,
            municipality=municipality,
            raw_artifact=artifact,
            structured_payload={
                "source_format": source_format,
                "jobLocation": {
                    "address": {
                        "streetAddress": street,
                        "addressLocality": locality,
                        "addressRegion": region,
                        "postalCode": postcode,
                        "addressCountry": country,
                    }
                },
            },
            contract_payload={
                "schema_version": "1.2",
                "raw_location": raw_location,
            },
        )

    def resolver(self, client: FakeClient) -> GeospatialResolver:
        return GeospatialResolver(client=client, raw_store=self.store)

    def test_locality_canton_and_country_alias_resolve_to_centroid(self) -> None:
        observation = self.observation(
            "locality-alias",
            locality="Winterthur",
            region="Zürich",
            country="Schweiz",
        )
        client = FakeClient(payload(origin="gg25", postcode=""))
        resolution = self.resolver(client).resolve(observation)

        assert client.requests == [
            {
                "geometryFormat": "geojson",
                "lang": "de",
                "limit": 10,
                "origins": "gg25",
                "searchText": "Winterthur ZH",
                "sr": 4326,
                "type": "locations",
            }
        ]
        assert resolution.resolver_version == RESOLVER_VERSION
        assert resolution.resolution_status == "RESOLVED"
        assert resolution.municipality == self.winterthur
        assert resolution.location_precision == "MUNICIPALITY"
        assert resolution.privacy_display_level == "MUNICIPALITY_CENTROID"
        assert resolution.evidence["municipality_derivation"] == "EXACT_LOCALITY_CANTON"

    def test_official_gg25_label_only_candidate_resolves_exact_municipality(self) -> None:
        observation = self.observation(
            "gg25-label-only",
            municipality=self.winterthur,
            locality="Winterthur",
            region="ZH",
        )
        body = json.dumps(
            {
                "features": [
                    {
                        "geometry": {"coordinates": [8.7241, 47.4988]},
                        "properties": {
                            "attrs": {
                                "origin": "gg25",
                                "label": "<b>Winterthur (ZH)</b>",
                                "lat": 47.4988,
                                "lon": 8.7241,
                            }
                        },
                    }
                ]
            }
        ).encode()

        resolution = self.resolver(FakeClient(body)).resolve(observation)

        assert resolution.resolution_status == "RESOLVED"
        assert resolution.municipality == self.winterthur
        assert resolution.location_precision == "MUNICIPALITY"
        assert resolution.privacy_display_level == "MUNICIPALITY_CENTROID"

    def test_malformed_or_foreign_gg25_label_fails_closed(self) -> None:
        observation = self.observation(
            "gg25-foreign-label",
            municipality=self.winterthur,
            locality="Winterthur",
            region="ZH",
        )
        body = json.dumps(
            {
                "features": [
                    {
                        "geometry": {"coordinates": [8.7241, 47.4988]},
                        "properties": {
                            "attrs": {
                                "origin": "gg25",
                                "label": "<b>Winterthur (DE)</b>",
                                "lat": 47.4988,
                                "lon": 8.7241,
                            }
                        },
                    }
                ]
            }
        ).encode()

        resolution = self.resolver(FakeClient(body)).resolve(observation)

        assert resolution.resolution_status == "UNRESOLVED"
        assert resolution.latitude is None and resolution.longitude is None
    def test_bounded_zurich_raw_location_can_establish_exact_municipality(self) -> None:
        observation = self.observation(
            "zurich-raw",
            source=self.zurich_source,
            raw_location="Zuerich",
            source_format="SOLIQUE_KTZH_API_V1",
        )
        client = FakeClient(payload("Zürich", postcode="", origin="gg25"))
        resolution = self.resolver(client).resolve(observation)

        assert client.requests[0]["searchText"] == "Zürich ZH"
        assert client.requests[0]["origins"] == "gg25"
        assert resolution.resolution_status == "RESOLVED"
        assert resolution.municipality == self.zurich
        assert (
            resolution.evidence["municipality_derivation"]
            == "GOVERNED_STRUCTURED_RAW_LOCATION"
        )

    def test_raw_location_outside_bounded_source_rule_is_not_used(self) -> None:
        observation = self.observation(
            "unbounded-raw",
            raw_location="Winterthur",
            source_format="SOME_OTHER_FORMAT",
        )
        client = FakeClient()
        resolution = self.resolver(client).resolve(observation)

        assert resolution.resolution_status == "UNRESOLVED"
        assert resolution.municipality is None
        assert client.calls == 0

    def test_municipality_only_request_rejects_address_candidate(self) -> None:
        observation = self.observation(
            "address-candidate",
            municipality=self.winterthur,
            locality="Winterthur",
            region="ZH",
        )
        resolution = self.resolver(FakeClient(payload(origin="address"))).resolve(observation)

        assert resolution.resolution_status == "REVIEW"
        assert resolution.latitude is None and resolution.longitude is None
        assert (
            GeocodingReviewItem.objects.get(location_resolution=resolution).reason
            == "GEOCODER_CONTRADICTS_BFS"
        )

    def test_multiple_gg25_coordinate_pairs_remain_review(self) -> None:
        data = json.loads(payload(origin="gg25", postcode=""))
        extra = deepcopy(data["features"][0])
        extra["geometry"]["coordinates"] = [8.75, 47.51]
        data["features"].append(extra)
        observation = self.observation(
            "multiple-gg25",
            municipality=self.winterthur,
            locality="Winterthur",
            region="ZH",
        )
        resolution = self.resolver(FakeClient(json.dumps(data).encode())).resolve(observation)

        assert resolution.resolution_status == "REVIEW"
        assert (
            GeocodingReviewItem.objects.get(location_resolution=resolution).reason
            == "MULTIPLE_PLAUSIBLE_RESULTS"
        )

    def test_protected_context_never_uses_raw_derivation(self) -> None:
        canary = "PRIVATE-RAW-LOCATION-CANARY"
        observation = self.observation(
            "protected-raw",
            source=self.zurich_source,
            raw_location=canary,
            source_format="SOLIQUE_KTZH_API_V1",
        )
        client = FakeClient()
        resolution = self.resolver(client).resolve(
            observation,
            LocationPrivacyContext.PRIVATE_RESIDENCE,
        )

        assert client.calls == 0
        assert resolution.resolution_status == "UNRESOLVED"
        assert resolution.privacy_display_level == "HIDDEN"
        assert canary not in json.dumps(resolution.evidence)

    def test_legacy_v01_input_and_request_remain_exactly_replayable(self) -> None:
        observation = self.observation(
            "legacy-v01",
            municipality=self.winterthur,
            locality="Winterthur",
            region="ZH",
        )
        expected_material = {
            "resolver": LEGACY_RESOLVER_VERSION,
            "privacy_context": "PUBLIC_OR_NON_RESIDENTIAL",
            "source": str(self.city_source.pk),
            "bfs": self.winterthur.pk,
            "municipality": "Winterthur",
            "canton": "ZH",
            "street": "",
            "locality": "Winterthur",
            "region": "ZH",
            "postcode": "",
            "country": "CH",
            "jobLocation": observation.structured_payload["jobLocation"],
        }
        assert resolution_input_material(
            observation,
            LocationPrivacyContext.PUBLIC_OR_NON_RESIDENTIAL,
            resolver_version=LEGACY_RESOLVER_VERSION,
        ) == expected_material
        assert normalized_request(
            observation,
            LocationPrivacyContext.PUBLIC_OR_NON_RESIDENTIAL,
            resolver_version=LEGACY_RESOLVER_VERSION,
        ) == {
            "geometryFormat": "geojson",
            "lang": "de",
            "limit": 10,
            "searchText": "Winterthur ZH",
            "sr": 4326,
            "type": "locations",
        }
        legacy = GeospatialResolver(
            client=FakeClient(payload(origin="zipcode")),
            raw_store=self.store,
            resolver_version=LEGACY_RESOLVER_VERSION,
        ).resolve(observation)
        assert legacy.privacy_display_level == "EXACT_ALLOWED"
        assert legacy.input_fingerprint == fingerprint(expected_material)

    def test_unknown_resolver_version_fails_closed(self) -> None:
        with pytest.raises(ValueError, match="unsupported geospatial resolver version"):
            GeospatialResolver(
                client=FakeClient(),
                raw_store=self.store,
                resolver_version="geospatial-v9",
            )

    def test_v01_and_v02_rows_remain_distinct_and_immutable(self) -> None:
        observation = self.observation(
            "version-distinct",
            municipality=self.winterthur,
            locality="Winterthur",
            region="ZH",
        )
        legacy = GeospatialResolver(
            client=FakeClient(payload(origin="zipcode")),
            raw_store=self.store,
            resolver_version=LEGACY_RESOLVER_VERSION,
        ).resolve(observation)
        current = self.resolver(FakeClient(payload(origin="gg25", postcode=""))).resolve(
            observation
        )

        assert legacy.pk != current.pk
        assert {legacy.resolver_version, current.resolver_version} == {
            LEGACY_RESOLVER_VERSION,
            RESOLVER_VERSION,
        }
        assert (
            PostingLocationResolution.objects.filter(
                posting_observation=observation
            ).count()
            == 2
        )
