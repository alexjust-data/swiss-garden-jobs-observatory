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
from django.db import connection, transaction

from collectors.location_normalization import (
    canonical_canton_code,
    canonical_swiss_country,
    resolve_swiss_municipality,
    swiss_place_key,
)
from core.hashing import sha256_file, sha256_hex
from core.models import RawArtifact
from core.storage import RawObjectAlreadyExistsError, RawObjectStore
from observations.models import (
    GeocoderCacheEntry,
    GeocodingReviewItem,
    PostingLocationResolution,
    PostingObservation,
)
from reference_data.models import Municipality

LEGACY_RESOLVER_VERSION = "geospatial-v0.1"
RESOLVER_VERSION = "geospatial-v0.2"
SUPPORTED_RESOLVER_VERSIONS = frozenset({LEGACY_RESOLVER_VERSION, RESOLVER_VERSION})
PROVIDER = "SWISSTOPO_SEARCHSERVER"
PROVIDER_VERSION = "geo-admin-searchserver-api-2026-08"
HOST = "api3.geo.admin.ch"
ENDPOINT = "https://api3.geo.admin.ch/rest/services/api/SearchServer"
USER_AGENT = "SwissGardenJobsObservatory/0.1 (+https://github.com/alexjust-data/swiss-garden-jobs-observatory)"
MAX_RESPONSE_BYTES = 1024 * 1024
ACCEPTED_CONTENT_TYPES = frozenset({"application/json", "application/geo+json"})
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
GG25_MUNICIPALITY_LABEL_RE = re.compile(
    r"^(?P<municipality>.+?)\s+\((?P<canton>[A-Z]{2})\)$"
)


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


def validated_response_payload(
    request: dict[str, object],
    response: GeocoderFetchedResponse,
) -> object:
    expected_requested_url = build_url(request)
    if response.requested_url != expected_requested_url:
        raise GeospatialResolutionError(
            "SearchServer requested URL does not match the normalized request"
        )
    validate_url(response.final_url)
    if (
        response.status_code != 200
        or response.content_type not in ACCEPTED_CONTENT_TYPES
        or len(response.body) > MAX_RESPONSE_BYTES
    ):
        raise GeospatialResolutionError("invalid SearchServer HTTP response")
    try:
        payload = json.loads(response.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GeospatialResolutionError("invalid SearchServer JSON") from exc
    candidates(payload)
    return payload


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
        municipality = text(
            attrs.get("municipality")
            or attrs.get("commune")
            or attrs.get("city")
            or attrs.get("locality")
        )
        canton = text(attrs.get("canton") or attrs.get("canton_code")).upper()
        country = text(attrs.get("country") or attrs.get("country_code")).upper()
        origin = text(attrs.get("origin"))
        label = text(attrs.get("label") or attrs.get("detail"))
        if origin.casefold() == "gg25":
            label_match = GG25_MUNICIPALITY_LABEL_RE.fullmatch(label)
            if label_match is not None:
                label_municipality = label_match.group("municipality").strip()
                label_canton = canonical_canton_code(label_match.group("canton"))
                if not label_canton:
                    continue
                if municipality and swiss_place_key(municipality) != swiss_place_key(
                    label_municipality
                ):
                    continue
                if canton and canonical_canton_code(canton) != label_canton:
                    continue
                if country and canonical_swiss_country(country) != "CH":
                    continue
                municipality = municipality or label_municipality
                canton = canton or label_canton
                country = country or "CH"
        result.append(
            Candidate(
                municipality,
                canton,
                country,
                text(attrs.get("postcode") or attrs.get("zip")),
                lat,
                lon,
                origin,
                label,
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


def governed_municipality(
    observation: PostingObservation,
    privacy_context: LocationPrivacyContext,
    *,
    resolver_version: str,
) -> tuple[Municipality | None, str]:
    if observation.municipality is not None:
        return observation.municipality, "OBSERVATION_FK"
    if (
        resolver_version != RESOLVER_VERSION
        or privacy_context != LocationPrivacyContext.PUBLIC_OR_NON_RESIDENTIAL
    ):
        return None, "NONE"

    canton_code = canonical_canton_code(observation.location_region)
    if observation.location_locality.strip() and canton_code:
        municipality = resolve_swiss_municipality(
            observation.location_locality,
            canton_code,
        )
        if municipality is not None:
            return municipality, "EXACT_LOCALITY_CANTON"

    source_format = str(observation.structured_payload.get("source_format", ""))
    raw_location = str(observation.contract_payload.get("raw_location", "")).strip()
    bounded_zurich_raw = (
        str(observation.source.pk) == "SRC-OFF-CANTON-ZH"
        and source_format == "SOLIQUE_KTZH_API_V1"
        and not observation.location_locality.strip()
        and not observation.location_street.strip()
        and not observation.location_postal_code.strip()
        and raw_location
        and not multiple(observation)
    )
    if bounded_zurich_raw:
        municipality = resolve_swiss_municipality(
            raw_location,
            fallback_canton="ZH",
        )
        if municipality is not None:
            return municipality, "GOVERNED_STRUCTURED_RAW_LOCATION"
    return None, "NONE"

def resolution_input_material(
    observation: PostingObservation,
    privacy_context: LocationPrivacyContext,
    *,
    resolver_version: str = RESOLVER_VERSION,
) -> dict[str, object]:
    if resolver_version == LEGACY_RESOLVER_VERSION:
        municipality = observation.municipality
        common: dict[str, object] = {
            "resolver": resolver_version,
            "privacy_context": privacy_context.value,
            "source": str(observation.source.pk),
            "bfs": municipality.pk if municipality else None,
            "municipality": municipality.municipality_name if municipality else "",
            "canton": municipality.canton_code if municipality else "",
        }
        if privacy_context != LocationPrivacyContext.PUBLIC_OR_NON_RESIDENTIAL:
            return {**common, "country": observation.location_country}
        return {
            **common,
            "street": observation.location_street,
            "locality": observation.location_locality,
            "region": observation.location_region,
            "postcode": observation.location_postal_code,
            "country": observation.location_country,
            "jobLocation": observation.structured_payload.get("jobLocation"),
        }

    municipality, derivation = governed_municipality(
        observation,
        privacy_context,
        resolver_version=resolver_version,
    )
    common = {
        "resolver": resolver_version,
        "privacy_policy": PRIVACY_POLICY_VERSION,
        "privacy_context": privacy_context.value,
        "source": str(observation.source.pk),
        "bfs": municipality.pk if municipality else None,
        "municipality": municipality.municipality_name if municipality else "",
        "canton": municipality.canton_code if municipality else "",
        "municipality_derivation": derivation,
        "country": canonical_swiss_country(observation.location_country),
    }
    if privacy_context != LocationPrivacyContext.PUBLIC_OR_NON_RESIDENTIAL:
        return common
    return {
        **common,
        "street": observation.location_street,
        "locality": observation.location_locality,
        "region": observation.location_region,
        "postcode": observation.location_postal_code,
        "country_original": observation.location_country,
        "raw_location": observation.contract_payload.get("raw_location"),
        "source_format": observation.structured_payload.get("source_format"),
        "jobLocation": observation.structured_payload.get("jobLocation"),
    }


def resolution_input_fingerprint(
    observation: PostingObservation,
    privacy_context: LocationPrivacyContext,
    *,
    resolver_version: str = RESOLVER_VERSION,
) -> str:
    return fingerprint(
        resolution_input_material(
            observation,
            privacy_context,
            resolver_version=resolver_version,
        )
    )


def normalized_request(
    observation: PostingObservation,
    privacy_context: LocationPrivacyContext,
    *,
    resolver_version: str = RESOLVER_VERSION,
) -> dict[str, object] | None:
    municipality, _ = governed_municipality(
        observation,
        privacy_context,
        resolver_version=resolver_version,
    )
    protected = privacy_context != LocationPrivacyContext.PUBLIC_OR_NON_RESIDENTIAL
    if protected:
        if municipality is None:
            return None
        query = f"{municipality.municipality_name} {municipality.canton_code}".strip()
        if not query:
            return None
        return {
            "geometryFormat": "geojson",
            "lang": "de",
            "limit": 10,
            "origins": "gg25",
            "searchText": " ".join(query.split()),
            "sr": 4326,
            "type": "locations",
        }
    locality = observation.location_locality.strip() or (
        municipality.municipality_name if municipality else ""
    )
    postcode = observation.location_postal_code.strip()
    street = observation.location_street.strip()
    region = observation.location_region.strip() or (
        municipality.canton_code if municipality else ""
    )
    municipality_only = (
        resolver_version == RESOLVER_VERSION
        and municipality is not None
        and not street
        and not postcode
        and not multiple(observation)
    )
    if municipality_only:
        if municipality is None:
            raise GeospatialResolutionError("municipality-only request lost governed identity")
        query = f"{municipality.municipality_name} {municipality.canton_code}".strip()
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
    if municipality_only:
        request["origins"] = "gg25"
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
        if resolver_version not in SUPPORTED_RESOLVER_VERSIONS:
            raise ValueError(f"unsupported geospatial resolver version: {resolver_version}")
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
        with transaction.atomic():
            self._advisory_lock(
                "resolution",
                str(observation.pk),
                self.resolver_version,
                privacy_context.value,
            )
            return self._resolve_locked(observation, privacy_context)

    def _resolve_locked(
        self,
        observation: PostingObservation,
        privacy_context: LocationPrivacyContext,
    ) -> PostingLocationResolution:
        protected = privacy_context != LocationPrivacyContext.PUBLIC_OR_NON_RESIDENTIAL
        municipality, municipality_derivation = governed_municipality(
            observation,
            privacy_context,
            resolver_version=self.resolver_version,
        )
        municipality_name = municipality.municipality_name if municipality else ""
        municipality_canton = municipality.canton_code if municipality else ""
        input_value = resolution_input_material(
            observation,
            privacy_context,
            resolver_version=self.resolver_version,
        )
        input_fingerprint = resolution_input_fingerprint(
            observation,
            privacy_context,
            resolver_version=self.resolver_version,
        )
        existing = PostingLocationResolution.objects.filter(
            posting_observation=observation,
            resolver_version=self.resolver_version,
            privacy_context=privacy_context.value,
        ).first()
        if existing:
            if existing.input_fingerprint != input_fingerprint:
                raise GeospatialResolutionError(
                    "existing location resolution conflicts with current governed input"
                )
            self.stats.already_resolved += 1
            return existing
        evidence: dict[str, Any] = {
            "input": input_value,
            "input_fingerprint": input_fingerprint,
            "_privacy_context": privacy_context.value,
        }
        if self.resolver_version == RESOLVER_VERSION:
            evidence["municipality_derivation"] = municipality_derivation
            if municipality is not None and observation.municipality is None:
                evidence["_resolved_bfs"] = municipality.pk
            country = canonical_swiss_country(observation.location_country)
        else:
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
        request = normalized_request(
            observation,
            privacy_context,
            resolver_version=self.resolver_version,
        )
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
        postcode = "" if protected else observation.location_postal_code.strip()
        municipality_only_request = (
            self.resolver_version == RESOLVER_VERSION
            and request.get("origins") == "gg25"
        )
        if municipality_only_request:
            name = swiss_place_key(municipality_name)
            matches = [
                item
                for item in found
                if name
                and item.origin.casefold() == "gg25"
                and swiss_place_key(item.municipality) == name
                and (
                    not item.canton
                    or canonical_canton_code(item.canton) == municipality_canton
                )
                and (
                    not item.country
                    or canonical_swiss_country(item.country) == "CH"
                )
            ]
        else:
            name = normalize(
                municipality_name
                if protected
                else (municipality_name or observation.location_locality)
            )
            canton = (
                municipality_canton
                if protected
                else (municipality_canton or observation.location_region)
            ).upper()
            matches = [
                item
                for item in found
                if name
                and name in normalize(f"{item.municipality} {item.label}")
                and (not item.canton or item.canton == canton)
                and (not item.country or item.country == "CH")
                and not (postcode and item.postcode and postcode != item.postcode)
            ]
        if not matches:
            status, reason = (
                ("REVIEW", "GEOCODER_CONTRADICTS_BFS")
                if found and municipality is not None
                else (("REVIEW", "NO_UNAMBIGUOUS_MUNICIPALITY") if found else ("UNRESOLVED", None))
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
        if municipality is None:
            if self.resolver_version == RESOLVER_VERSION:
                selected_municipality = resolve_swiss_municipality(
                    selected.municipality,
                    selected.canton,
                )
                municipality_matches = [selected_municipality] if selected_municipality else []
            else:
                candidate_municipalities = Municipality.objects.filter(
                    municipality_name__iexact=selected.municipality
                )
                if selected.canton:
                    candidate_municipalities = candidate_municipalities.filter(
                        canton_code=selected.canton
                    )
                municipality_matches = list(candidate_municipalities[:2])
            if len(municipality_matches) != 1:
                return self.persist(
                    observation,
                    input_fingerprint,
                    "REVIEW",
                    "UNKNOWN",
                    "SWISSTOPO_SEARCHSERVER",
                    None,
                    None,
                    evidence,
                    "NO_UNAMBIGUOUS_MUNICIPALITY",
                    review_candidate_evidence(matches, privacy_context),
                )
            evidence["_resolved_bfs"] = municipality_matches[0].pk
        precision = (
            "MUNICIPALITY"
            if protected
            else (
                "REMOTE_OR_MULTIPLE"
                if multiple(observation)
                else (
                    "EXACT_WORK_ADDRESS"
                    if observation.location_street.strip()
                    and selected.origin.casefold() == "address"
                    else ("POSTCODE" if postcode else "MUNICIPALITY")
                )
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
        self._advisory_lock("cache", PROVIDER, PROVIDER_VERSION, request_fingerprint)
        self.stats.unique_geocoder_requests.add(request_fingerprint)
        entry = GeocoderCacheEntry.objects.filter(
            provider=PROVIDER,
            provider_version=PROVIDER_VERSION,
            request_fingerprint=request_fingerprint,
        ).first()
        if entry:
            self._validate_cache_entry(entry, request)
            self.stats.cache_hits += 1
            return entry
        self.stats.network_requests += 1
        response = self.client.fetch(request)
        payload = validated_response_payload(request, response)
        digest = sha256_hex(response.body)
        key = (
            f"geocoder/{PROVIDER.lower()}/{PROVIDER_VERSION}/"
            f"{request_fingerprint}-{digest[:16]}.json"
        )
        try:
            path: Path = self.raw_store.write_bytes(key, response.body)
        except RawObjectAlreadyExistsError as exc:
            raise GeospatialResolutionError(
                "existing geocoder RAW object conflicts with fetched bytes"
            ) from exc
        if sha256_file(path) != digest:
            raise GeospatialResolutionError("geocoder RAW hash mismatch")
        with transaction.atomic():
            artifact = RawArtifact.objects.filter(object_key=key).first()
            if artifact is None:
                artifact = RawArtifact.objects.create(
                    object_key=key,
                    sha256_digest=digest,
                    byte_size=len(response.body),
                    content_type=response.content_type,
                )
            elif (
                artifact.sha256_digest != digest
                or artifact.byte_size != len(response.body)
                or artifact.content_type != response.content_type
            ):
                raise GeospatialResolutionError("existing geocoder RAW metadata conflicts")
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

    def _validate_cache_entry(
        self,
        entry: GeocoderCacheEntry,
        request: dict[str, object],
    ) -> None:
        expected_request_fingerprint = fingerprint(
            {"provider": PROVIDER, "version": PROVIDER_VERSION, "request": request}
        )
        expected_requested_url = build_url(request)
        if (
            entry.provider != PROVIDER
            or entry.provider_version != PROVIDER_VERSION
            or entry.normalized_request != request
            or entry.request_fingerprint != expected_request_fingerprint
            or entry.requested_url != expected_requested_url
            or entry.http_status != 200
            or entry.content_type not in ACCEPTED_CONTENT_TYPES
            or entry.content_type != entry.raw_artifact.content_type
        ):
            raise GeospatialResolutionError("existing geocoder cache metadata conflicts")
        validate_url(entry.final_url)
        expected_object_key = (
            f"geocoder/{PROVIDER.lower()}/{PROVIDER_VERSION}/"
            f"{entry.request_fingerprint}-{entry.raw_artifact.sha256_digest[:16]}.json"
        )
        try:
            raw_bytes = self.raw_store.read_bytes(entry.raw_artifact.object_key)
        except (OSError, ValueError) as exc:
            raise GeospatialResolutionError("existing geocoder RAW object conflicts") from exc
        if (
            entry.raw_artifact.object_key != expected_object_key
            or len(entry.raw_artifact.sha256_digest) != 64
            or len(raw_bytes) != entry.raw_artifact.byte_size
            or sha256_hex(raw_bytes) != entry.raw_artifact.sha256_digest
        ):
            raise GeospatialResolutionError("existing geocoder RAW object conflicts")
        try:
            payload = json.loads(raw_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GeospatialResolutionError("existing geocoder RAW JSON is invalid") from exc
        candidates(payload)
        if payload != entry.response_payload:
            raise GeospatialResolutionError("existing geocoder cache payload conflicts")

    @staticmethod
    def _advisory_lock(*parts: str) -> None:
        if connection.vendor != "postgresql":
            return
        digest = hashlib.sha256(chr(31).join(parts).encode()).digest()
        lock_key = int.from_bytes(digest[:8], byteorder="big", signed=True)
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_key])

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
        resolved_bfs = evidence.pop("_resolved_bfs", None)
        resolved_municipality = observation.municipality
        if resolved_bfs is not None:
            resolved_municipality = Municipality.objects.get(pk=resolved_bfs)
        protected = privacy_context != LocationPrivacyContext.PUBLIC_OR_NON_RESIDENTIAL
        hidden = protected
        privacy = "HIDDEN" if hidden else "EXACT_ALLOWED"
        if self.resolver_version == RESOLVER_VERSION and not protected:
            if precision == "POSTCODE":
                privacy = "POSTCODE_CENTROID"
            elif precision == "MUNICIPALITY":
                privacy = "MUNICIPALITY_CENTROID"
        evidence["privacy"] = {
            "context": privacy_context.value,
            "policy_version": PRIVACY_POLICY_VERSION,
            "generalized": privacy != "EXACT_ALLOWED",
            "display_level": privacy,
        }
        with transaction.atomic():
            resolution = PostingLocationResolution.objects.create(
                posting_observation=observation,
                resolver_version=self.resolver_version,
                privacy_context=privacy_context.value,
                resolution_status=status,
                municipality=resolved_municipality,
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
