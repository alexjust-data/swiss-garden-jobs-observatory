from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum
from html import unescape
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.conf import settings
from django.db import transaction

from core.hashing import sha256_file, sha256_hex
from core.models import RawArtifact
from core.storage import RawObjectStore
from observations.models import (
    GeocoderCacheEntry,
    GeocodingReviewItem,
    PostingLocationResolution,
    PostingObservation,
)

RESOLVER_VERSION = "geospatial-v0.1"
PROVIDER = "SWISSTOPO_SEARCHSERVER"
PROVIDER_VERSION = "geo-admin-searchserver-api-2026-08"
HOST = "api3.geo.admin.ch"
ENDPOINT = "https://api3.geo.admin.ch/rest/services/api/SearchServer"
USER_AGENT = "SwissGardenJobsObservatory/0.1 (+https://github.com/alexjust-data/swiss-garden-jobs-observatory)"
MAX_RESPONSE_BYTES = 1024 * 1024
PRIVACY_POLICY_VERSION = "location-privacy-v0.1"


class LocationPrivacyContext(StrEnum):
    PUBLIC_OR_NON_RESIDENTIAL = "PUBLIC_OR_NON_RESIDENTIAL"
    PRIVATE_RESIDENCE = "PRIVATE_RESIDENCE"
    CONFIDENTIAL_PRIVATE_RESIDENCE = "CONFIDENTIAL_PRIVATE_RESIDENCE"


MULTIPLE_MARKERS = (
    "diverse standorte",
    "mehrere standorte",
    "verschiedene standorte",
    "multiple locations",
    "remote",
)
TAG_RE = re.compile(r"<[^>]+>")


class GeospatialResolutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class GeocoderFetchedResponse:
    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    body: bytes


@dataclass(frozen=True)
class Candidate:
    municipality: str
    canton: str
    country: str
    postcode: str
    latitude: float
    longitude: float
    origin: str
    label: str
    raw: dict[str, Any]


@dataclass
class ResolutionStats:
    observations_considered: int = 0
    already_resolved: int = 0
    resolved: int = 0
    review: int = 0
    unresolved: int = 0
    unique_geocoder_requests: set[str] = field(default_factory=set)
    cache_hits: int = 0
    network_requests: int = 0
    privacy_generalizations: int = 0
    precision_distribution: dict[str, int] = field(default_factory=dict)
    coordinate_source_distribution: dict[str, int] = field(default_factory=dict)


class GeocoderClient(Protocol):
    def fetch(self, request: dict[str, object]) -> GeocoderFetchedResponse: ...


def normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def fingerprint(value: object) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(body).hexdigest()


def validate_coordinates(latitude: float, longitude: float) -> None:
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise GeospatialResolutionError("coordinates outside valid latitude/longitude ranges")


def validate_url(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != HOST
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise GeospatialResolutionError(f"unsafe geo.admin URL: {url}")


def build_url(request: dict[str, object]) -> str:
    required = {"geometryFormat", "lang", "limit", "searchText", "sr", "type"}
    allowed = required | {"origins"}
    if not required.issubset(request) or not set(request).issubset(allowed):
        raise GeospatialResolutionError("unexpected SearchServer request parameters")
    url = f"{ENDPOINT}?{urlencode(sorted((key, str(value)) for key, value in request.items()))}"
    validate_url(url)
    return url


class SameOriginRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> Request | None:
        validate_url(urljoin(req.full_url, newurl))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class GeoAdminSearchServerClient:
    def __init__(self, timeout_seconds: float = 15.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout must be positive")
        self.timeout_seconds = timeout_seconds
        self.opener = build_opener(SameOriginRedirectHandler())

    def fetch(self, request_data: dict[str, object]) -> GeocoderFetchedResponse:
        url = build_url(request_data)
        request = Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json, application/json"},
        )
        with self.opener.open(request, timeout=self.timeout_seconds) as response:
            final_url = response.geturl()
            validate_url(final_url)
            status = int(response.status)
            content_type = response.headers.get_content_type()
            body = response.read(MAX_RESPONSE_BYTES + 1)
        if (
            status != 200
            or len(body) > MAX_RESPONSE_BYTES
            or content_type not in {"application/json", "application/geo+json"}
        ):
            raise GeospatialResolutionError("invalid SearchServer HTTP response")
        return GeocoderFetchedResponse(url, final_url, status, content_type, body)


def number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(cast(Any, value))
    except (TypeError, ValueError):
        return None


def text(value: object) -> str:
    return " ".join(unescape(TAG_RE.sub("", value if isinstance(value, str) else "")).split())


def candidates(payload: object) -> list[Candidate]:
    if not isinstance(payload, dict):
        raise GeospatialResolutionError("SearchServer payload must be an object")
    records: list[tuple[dict[str, Any], object]] = []
    for item in payload.get("features", []):
        if isinstance(item, dict):
            properties = item.get("properties", {})
            attrs = properties.get("attrs", properties) if isinstance(properties, dict) else {}
            records.append((attrs if isinstance(attrs, dict) else {}, item.get("geometry")))
    for item in payload.get("results", []):
        if isinstance(item, dict):
            attrs = item.get("attrs", item)
            records.append((attrs if isinstance(attrs, dict) else {}, item.get("geometry")))
    result = []
    for attrs, geometry in records:
        lat, lon = (
            number(attrs.get("lat") or attrs.get("latitude")),
            number(attrs.get("lon") or attrs.get("longitude")),
        )
        if (
            isinstance(geometry, dict)
            and isinstance(geometry.get("coordinates"), list)
            and len(geometry["coordinates"]) >= 2
        ):
            lon, lat = number(geometry["coordinates"][0]), number(geometry["coordinates"][1])
        if lat is None or lon is None:
            continue
        validate_coordinates(lat, lon)
        result.append(
            Candidate(
                text(
                    attrs.get("municipality")
                    or attrs.get("commune")
                    or attrs.get("city")
                    or attrs.get("locality")
                ),
                text(attrs.get("canton") or attrs.get("canton_code")).upper(),
                text(attrs.get("country") or attrs.get("country_code")).upper(),
                text(attrs.get("postcode") or attrs.get("zip")),
                lat,
                lon,
                text(attrs.get("origin")),
                text(attrs.get("label") or attrs.get("detail")),
                attrs,
            )
        )
    return result


def source_coordinates(observation: PostingObservation) -> tuple[float, float] | None:
    value = observation.structured_payload.get("jobLocation")
    locations = value if isinstance(value, list) else [value]
    found = set()
    for location in locations:
        if isinstance(location, dict) and isinstance(location.get("geo"), dict):
            lat, lon = (
                number(location["geo"].get("latitude")),
                number(location["geo"].get("longitude")),
            )
            if lat is not None and lon is not None:
                validate_coordinates(lat, lon)
                found.add((lat, lon))
    if len(found) > 1:
        raise GeospatialResolutionError("multiple distinct source coordinates")
    return next(iter(found)) if found else None


def multiple(observation: PostingObservation) -> bool:
    value = normalize(
        " ".join(
            (
                observation.location_street,
                observation.location_locality,
                str(observation.contract_payload.get("raw_location", "")),
            )
        )
    )
    return ";" in value or any(marker in value for marker in MULTIPLE_MARKERS)


def normalized_request(
    observation: PostingObservation,
    privacy_context: LocationPrivacyContext,
) -> dict[str, object] | None:
    locality = observation.location_locality.strip() or observation.municipality.municipality_name
    postcode = observation.location_postal_code.strip()
    street = observation.location_street.strip()
    region = observation.location_region.strip() or observation.municipality.canton_code
    protected = privacy_context != LocationPrivacyContext.PUBLIC_OR_NON_RESIDENTIAL
    origins = None
    if protected and locality:
        query = f"{locality} {region}".strip()
        origins = "gg25"
    elif street and not multiple(observation):
        query = " ".join(x for x in (street, postcode, locality) if x)
    elif postcode and locality:
        query = f"{postcode} {locality}"
    elif locality:
        query = f"{locality} {region}".strip()
    elif region:
        query = region
    else:
        return None
    request: dict[str, object] = {
        "geometryFormat": "geojson",
        "lang": "de",
        "limit": 10,
        "searchText": " ".join(query.split()),
        "sr": 4326,
        "type": "locations",
    }
    if origins is not None:
        request["origins"] = origins
    return request


def review_candidate_evidence(
    items: list[Candidate],
    privacy_context: LocationPrivacyContext,
) -> list[dict[str, Any]]:
    if privacy_context == LocationPrivacyContext.PUBLIC_OR_NON_RESIDENTIAL:
        return [item.raw for item in items]
    return [
        {
            "origin": item.origin,
            "municipality": item.municipality,
            "canton": item.canton,
            "country": item.country,
            "postcode": item.postcode,
            "latitude": item.latitude,
            "longitude": item.longitude,
        }
        for item in items
    ]


class GeospatialResolver:
    def __init__(
        self,
        client: GeocoderClient | None = None,
        raw_store: RawObjectStore | None = None,
        resolver_version: str = RESOLVER_VERSION,
    ) -> None:
        self.client = client or GeoAdminSearchServerClient()
        self.raw_store = raw_store or RawObjectStore(settings.CORE_RAW_OBJECT_STORE_PATH)
        self.resolver_version = resolver_version
        self.stats = ResolutionStats()

    def resolve(
        self,
        observation: PostingObservation,
        privacy_context: LocationPrivacyContext = (
            LocationPrivacyContext.PUBLIC_OR_NON_RESIDENTIAL
        ),
    ) -> PostingLocationResolution:
        self.stats.observations_considered += 1
        existing = PostingLocationResolution.objects.filter(
            posting_observation=observation, resolver_version=self.resolver_version
        ).first()
        if existing:
            self.stats.already_resolved += 1
            return existing
        input_value = {
            "resolver": self.resolver_version,
            "source": str(observation.source.pk),
            "bfs": observation.municipality.pk,
            "municipality": observation.municipality.municipality_name,
            "canton": observation.municipality.canton_code,
            "street": observation.location_street,
            "locality": observation.location_locality,
            "region": observation.location_region,
            "postcode": observation.location_postal_code,
            "country": observation.location_country,
            "jobLocation": observation.structured_payload.get("jobLocation"),
        }
        input_fingerprint = fingerprint(input_value)
        evidence: dict[str, Any] = {
            "input": input_value,
            "input_fingerprint": input_fingerprint,
            "_privacy_context": privacy_context.value,
        }
        country = observation.location_country.strip().upper()
        if country and country != "CH":
            return self.persist(
                observation,
                input_fingerprint,
                "REVIEW",
                "UNKNOWN",
                "UNKNOWN",
                None,
                None,
                evidence,
                "UNEXPECTED_COUNTRY",
                [],
            )
        try:
            coordinates = source_coordinates(observation)
        except GeospatialResolutionError as exc:
            evidence["source_coordinate_error"] = str(exc)
            return self.persist(
                observation,
                input_fingerprint,
                "REVIEW",
                "UNKNOWN",
                "SOURCE_STRUCTURED",
                None,
                None,
                evidence,
                "AMBIGUOUS_SOURCE_COORDINATES",
                [],
            )
        if coordinates:
            precision = (
                "REMOTE_OR_MULTIPLE"
                if multiple(observation)
                else (
                    "EXACT_WORK_ADDRESS" if observation.location_street.strip() else "MUNICIPALITY"
                )
            )
            return self.persist(
                observation,
                input_fingerprint,
                "RESOLVED",
                precision,
                "SOURCE_STRUCTURED",
                coordinates[0],
                coordinates[1],
                evidence,
            )
        request = normalized_request(observation, privacy_context)
        if not request:
            return self.persist(
                observation,
                input_fingerprint,
                "UNRESOLVED",
                "UNKNOWN",
                "UNKNOWN",
                None,
                None,
                evidence,
            )
        cache = self.cached(request)
        found = candidates(cache.response_payload)
        evidence["geocoder"] = {
            "provider": cache.provider,
            "provider_version": cache.provider_version,
            "request_fingerprint": cache.request_fingerprint,
            "cache_entry_id": str(cache.pk),
            "raw_sha256": cache.raw_artifact.sha256_digest,
            "final_url": cache.final_url,
        }
        name = normalize(observation.municipality.municipality_name)
        canton = observation.municipality.canton_code.upper()
        postcode = observation.location_postal_code.strip()
        matches = [
            item
            for item in found
            if name in normalize(f"{item.municipality} {item.label}")
            and (not item.canton or item.canton == canton)
            and (not item.country or item.country == "CH")
            and not (postcode and item.postcode and postcode != item.postcode)
        ]
        if not matches:
            status, reason = (
                ("REVIEW", "GEOCODER_CONTRADICTS_BFS") if found else ("UNRESOLVED", None)
            )
            return self.persist(
                observation,
                input_fingerprint,
                status,
                "UNKNOWN",
                "SWISSTOPO_SEARCHSERVER",
                None,
                None,
                evidence,
                reason,
                review_candidate_evidence(found, privacy_context),
            )
        if len({(item.latitude, item.longitude) for item in matches}) > 1:
            return self.persist(
                observation,
                input_fingerprint,
                "REVIEW",
                "UNKNOWN",
                "SWISSTOPO_SEARCHSERVER",
                None,
                None,
                evidence,
                "MULTIPLE_PLAUSIBLE_RESULTS",
                review_candidate_evidence(matches, privacy_context),
            )
        selected = matches[0]
        precision = (
            "REMOTE_OR_MULTIPLE"
            if multiple(observation)
            else (
                "EXACT_WORK_ADDRESS"
                if observation.location_street.strip() and selected.origin.casefold() == "address"
                else ("POSTCODE" if postcode else "MUNICIPALITY")
            )
        )
        evidence["selected_candidate"] = review_candidate_evidence([selected], privacy_context)[0]
        return self.persist(
            observation,
            input_fingerprint,
            "RESOLVED",
            precision,
            "SWISSTOPO_SEARCHSERVER",
            selected.latitude,
            selected.longitude,
            evidence,
        )

    def cached(self, request: dict[str, object]) -> GeocoderCacheEntry:
        request_fingerprint = fingerprint(
            {"provider": PROVIDER, "version": PROVIDER_VERSION, "request": request}
        )
        self.stats.unique_geocoder_requests.add(request_fingerprint)
        entry = GeocoderCacheEntry.objects.filter(
            provider=PROVIDER,
            provider_version=PROVIDER_VERSION,
            request_fingerprint=request_fingerprint,
        ).first()
        if entry:
            self.stats.cache_hits += 1
            return entry
        self.stats.network_requests += 1
        response = self.client.fetch(request)
        validate_url(response.requested_url)
        validate_url(response.final_url)
        if response.status_code != 200 or len(response.body) > MAX_RESPONSE_BYTES:
            raise GeospatialResolutionError("invalid SearchServer response")
        try:
            payload = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GeospatialResolutionError("invalid SearchServer JSON") from exc
        candidates(payload)
        digest = sha256_hex(response.body)
        key = (
            f"geocoder/{PROVIDER.lower()}/{PROVIDER_VERSION}/"
            f"{request_fingerprint}-{digest[:16]}.json"
        )
        path: Path = self.raw_store.write_bytes(key, response.body)
        if sha256_file(path) != digest:
            raise GeospatialResolutionError("geocoder RAW hash mismatch")
        with transaction.atomic():
            artifact = RawArtifact.objects.create(
                object_key=key,
                sha256_digest=digest,
                byte_size=len(response.body),
                content_type=response.content_type,
            )
            return GeocoderCacheEntry.objects.create(
                provider=PROVIDER,
                provider_version=PROVIDER_VERSION,
                normalized_request=request,
                request_fingerprint=request_fingerprint,
                requested_url=response.requested_url,
                final_url=response.final_url,
                http_status=response.status_code,
                content_type=response.content_type,
                raw_artifact=artifact,
                response_payload=payload,
            )

    def persist(
        self,
        observation: PostingObservation,
        input_fingerprint: str,
        status: str,
        precision: str,
        coordinate_source: str,
        latitude: float | None,
        longitude: float | None,
        evidence: dict[str, Any],
        review_reason: str | None = None,
        candidate_evidence: list[dict[str, Any]] | None = None,
    ) -> PostingLocationResolution:
        if (latitude is None) != (longitude is None):
            raise GeospatialResolutionError("coordinates must be present together")
        if latitude is not None and longitude is not None:
            validate_coordinates(latitude, longitude)
        privacy_context = LocationPrivacyContext(evidence.pop("_privacy_context"))
        protected = privacy_context != LocationPrivacyContext.PUBLIC_OR_NON_RESIDENTIAL
        hidden = protected
        privacy = "HIDDEN" if hidden else "EXACT_ALLOWED"
        evidence["privacy"] = {
            "context": privacy_context.value,
            "policy_version": PRIVACY_POLICY_VERSION,
            "generalized": hidden,
            "display_level": privacy,
        }
        with transaction.atomic():
            resolution = PostingLocationResolution.objects.create(
                posting_observation=observation,
                resolver_version=self.resolver_version,
                resolution_status=status,
                municipality=observation.municipality,
                latitude=latitude,
                longitude=longitude,
                location_precision=precision,
                coordinate_source=coordinate_source,
                geocoding_confidence=None,
                privacy_display_level=privacy,
                public_display_latitude=None if hidden else latitude,
                public_display_longitude=None if hidden else longitude,
                input_fingerprint=input_fingerprint,
                evidence=evidence,
            )
            if review_reason:
                GeocodingReviewItem.objects.create(
                    posting_observation=observation,
                    location_resolution=resolution,
                    reason=review_reason,
                    candidate_evidence=candidate_evidence or [],
                    resolver_version=self.resolver_version,
                )
        if status == "RESOLVED":
            self.stats.resolved += 1
        elif status == "REVIEW":
            self.stats.review += 1
        else:
            self.stats.unresolved += 1
        self.stats.precision_distribution[precision] = (
            self.stats.precision_distribution.get(precision, 0) + 1
        )
        self.stats.coordinate_source_distribution[coordinate_source] = (
            self.stats.coordinate_source_distribution.get(coordinate_source, 0) + 1
        )
        self.stats.privacy_generalizations += int(hidden)
        return resolution
