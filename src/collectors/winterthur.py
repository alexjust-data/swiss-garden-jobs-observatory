from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import parse_qs, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.hashing import sha256_file, sha256_hex
from core.models import RawArtifact
from core.storage import RawObjectStore
from observations.models import CollectionRun, PostingObservation
from reference_data.models import Municipality
from sources.models import Source

WINTERTHUR_HOST = "jobs.winterthur.ch"
WINTERTHUR_LISTING_URL = "https://jobs.winterthur.ch/stellenangebote.html?reset_search=1"
WINTERTHUR_SOURCE_ID = "SRC-OFF-CITY-WINTERTHUR"
WINTERTHUR_BFS_CODE = 230
USER_AGENT = (
    "SwissGardenJobsObservatory/0.1 "
    "(+https://github.com/alexjust-data/swiss-garden-jobs-observatory)"
)
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
_POSTING_PATH = re.compile(r"-j(?P<posting_id>\d+)\.html$")


class WinterthurCollectorError(RuntimeError):
    pass


@dataclass(frozen=True)
class FetchedPage:
    requested_url: str
    final_url: str
    body: bytes
    content_type: str


@dataclass(frozen=True)
class ListingEntry:
    source_posting_id: str
    url: str
    title: str


@dataclass(frozen=True)
class ParsedPosting:
    source_posting_id: str
    canonical_url: str
    title: str
    date_posted: date | None
    valid_through: date | None
    employment_type: str
    hiring_organization: str
    description_html: str
    responsibilities_html: str
    qualifications_html: str
    benefits_html: str
    location_street: str
    location_locality: str
    location_region: str
    location_postal_code: str
    location_country: str
    structured_payload: dict[str, object]


class PageFetcher(Protocol):
    def fetch(self, url: str) -> FetchedPage: ...


class _SameOriginRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Request | None:
        _validate_winterthur_url(urljoin(req.full_url, newurl))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class UrlLibPageFetcher:
    def __init__(self, *, timeout_seconds: float = 30.0) -> None:
        self.timeout_seconds = timeout_seconds
        self._opener = build_opener(_SameOriginRedirectHandler())

    def fetch(self, url: str) -> FetchedPage:
        _validate_winterthur_url(url)
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
        with self._opener.open(request, timeout=self.timeout_seconds) as response:
            final_url = response.geturl()
            _validate_winterthur_url(final_url)
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise WinterthurCollectorError(f"response exceeds {MAX_RESPONSE_BYTES} bytes")
            content_type = response.headers.get_content_type()
        if content_type != "text/html":
            raise WinterthurCollectorError(f"expected text/html, found {content_type!r}")
        return FetchedPage(url, final_url, body, content_type)


def _validate_winterthur_url(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != WINTERTHUR_HOST
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
    ):
        raise WinterthurCollectorError(f"URL is outside the Winterthur HTTPS origin: {url}")


def _posting_id(url: str) -> str | None:
    parsed = urlsplit(url)
    query_values = parse_qs(parsed.query).get("yid", [])
    if len(query_values) == 1 and query_values[0].isdigit():
        return query_values[0]
    match = _POSTING_PATH.search(parsed.path)
    return match.group("posting_id") if match else None


class _ListingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: list[ListingEntry] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._href = href
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._href is None:
            return
        url = urljoin(f"https://{WINTERTHUR_HOST}/", self._href)
        source_posting_id = _posting_id(url)
        if source_posting_id is not None:
            _validate_winterthur_url(url)
            title = " ".join("".join(self._text).split())
            self.entries.append(ListingEntry(source_posting_id, url, title))
        self._href = None
        self._text = []


class _DetailParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.json_ld_blocks: list[str] = []
        self.canonical_url = ""
        self._json_ld_chunks: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if (
            tag.lower() == "script"
            and (attributes.get("type") or "").lower() == "application/ld+json"
        ):
            self._json_ld_chunks = []
        if (
            tag.lower() == "meta"
            and (attributes.get("property") or "").lower() == "og:url"
            and attributes.get("content")
        ):
            self.canonical_url = cast(str, attributes["content"])

    def handle_data(self, data: str) -> None:
        if self._json_ld_chunks is not None:
            self._json_ld_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._json_ld_chunks is not None:
            self.json_ld_blocks.append("".join(self._json_ld_chunks))
            self._json_ld_chunks = None


def parse_listing(body: bytes) -> list[ListingEntry]:
    parser = _ListingParser()
    parser.feed(body.decode("utf-8"))
    deduplicated: dict[str, ListingEntry] = {}
    for entry in parser.entries:
        previous = deduplicated.get(entry.source_posting_id)
        if previous is not None and previous.url != entry.url:
            raise WinterthurCollectorError(
                f"posting {entry.source_posting_id} has conflicting listing URLs"
            )
        deduplicated[entry.source_posting_id] = entry
    if not deduplicated:
        raise WinterthurCollectorError("listing contains no posting links")
    return list(deduplicated.values())


def _find_job_posting(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        if value.get("@type") == "JobPosting":
            return cast(dict[str, object], value)
        graph = value.get("@graph")
        if graph is not None:
            return _find_job_posting(graph)
    if isinstance(value, list):
        for item in value:
            found = _find_job_posting(item)
            if found is not None:
                return found
    return None


def _optional_date(value: object, *, field: str) -> date | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise WinterthurCollectorError(f"{field} must be an ISO date string")
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise WinterthurCollectorError(f"{field} is not a valid ISO date: {value!r}") from exc


def _string(value: object) -> str:
    return value if isinstance(value, str) else ""


def _mapping(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def parse_detail(body: bytes, *, requested_url: str, expected_posting_id: str) -> ParsedPosting:
    parser = _DetailParser()
    parser.feed(body.decode("utf-8"))
    payload: dict[str, object] | None = None
    for block in parser.json_ld_blocks:
        try:
            candidate = _find_job_posting(json.loads(block))
        except json.JSONDecodeError as exc:
            raise WinterthurCollectorError("detail contains invalid JSON-LD") from exc
        if candidate is not None:
            if payload is not None:
                raise WinterthurCollectorError("detail contains multiple JobPosting payloads")
            payload = candidate
    if payload is None:
        raise WinterthurCollectorError("detail contains no JobPosting JSON-LD")

    canonical_url = parser.canonical_url or requested_url
    _validate_winterthur_url(canonical_url)
    canonical_posting_id = _posting_id(canonical_url)
    if canonical_posting_id is not None and canonical_posting_id != expected_posting_id:
        raise WinterthurCollectorError(
            f"expected posting {expected_posting_id}, "
            f"canonical URL identifies {canonical_posting_id}"
        )
    title = _string(payload.get("title")).strip()
    if not title:
        raise WinterthurCollectorError("JobPosting title is required")

    date_posted = _optional_date(payload.get("datePosted"), field="datePosted")
    valid_through = _optional_date(payload.get("validThrough"), field="validThrough")
    if date_posted is not None and valid_through is not None and valid_through < date_posted:
        raise WinterthurCollectorError("validThrough precedes datePosted")

    organization = _mapping(payload.get("hiringOrganization"))
    location_value = payload.get("jobLocation")
    if isinstance(location_value, list):
        location_value = location_value[0] if location_value else {}
    location = _mapping(location_value)
    address = _mapping(location.get("address"))

    return ParsedPosting(
        source_posting_id=expected_posting_id,
        canonical_url=canonical_url,
        title=title,
        date_posted=date_posted,
        valid_through=valid_through,
        employment_type=_string(payload.get("employmentType")),
        hiring_organization=_string(organization.get("name")),
        description_html=_string(payload.get("description")),
        responsibilities_html=_string(payload.get("responsibilities")),
        qualifications_html=_string(payload.get("qualifications")),
        benefits_html=_string(payload.get("jobBenefits")),
        location_street=_string(address.get("streetAddress")),
        location_locality=_string(address.get("addressLocality")),
        location_region=_string(address.get("addressRegion")),
        location_postal_code=_string(address.get("postalCode")),
        location_country=_string(address.get("addressCountry")),
        structured_payload=payload,
    )


class WinterthurCollector:
    def __init__(
        self,
        *,
        fetcher: PageFetcher | None = None,
        raw_store: RawObjectStore | None = None,
        delay_seconds: float = 1.0,
    ) -> None:
        if delay_seconds < 0:
            raise ValueError("delay_seconds must be nonnegative")
        self.fetcher = fetcher or UrlLibPageFetcher()
        self.raw_store = raw_store or RawObjectStore(settings.CORE_RAW_OBJECT_STORE_PATH)
        self.delay_seconds = delay_seconds

    def collect(
        self, *, posting_ids: set[str] | None = None, limit: int | None = None
    ) -> CollectionRun:
        if limit is not None and limit <= 0:
            raise ValueError("limit must be positive")
        source = Source.objects.get(source_id=WINTERTHUR_SOURCE_ID)
        municipality = Municipality.objects.get(bfs_code=WINTERTHUR_BFS_CODE)
        if municipality.municipality_name != "Winterthur":
            raise WinterthurCollectorError("BFS 230 must resolve to Winterthur")

        run = CollectionRun.objects.create(source=source, listing_url=WINTERTHUR_LISTING_URL)
        try:
            listing_page = self.fetcher.fetch(WINTERTHUR_LISTING_URL)
            run.listing_raw_artifact = self._persist_raw(
                run=run,
                kind="listing",
                identifier="current",
                page=listing_page,
                observed_at=run.started_at,
            )
            entries = parse_listing(listing_page.body)
            run.listings_discovered = len(entries)

            if posting_ids is not None:
                discovered_ids = {entry.source_posting_id for entry in entries}
                missing = posting_ids - discovered_ids
                if missing:
                    raise WinterthurCollectorError(
                        f"requested postings are not active in the listing: {sorted(missing)}"
                    )
                entries = [entry for entry in entries if entry.source_posting_id in posting_ids]
            if limit is not None:
                entries = entries[:limit]

            for index, entry in enumerate(entries):
                if index and self.delay_seconds:
                    time.sleep(self.delay_seconds)
                observed_at = timezone.now()
                detail_page = self.fetcher.fetch(entry.url)
                parsed = parse_detail(
                    detail_page.body,
                    requested_url=detail_page.final_url,
                    expected_posting_id=entry.source_posting_id,
                )
                artifact = self._persist_raw(
                    run=run,
                    kind="detail",
                    identifier=entry.source_posting_id,
                    page=detail_page,
                    observed_at=observed_at,
                )
                with transaction.atomic():
                    PostingObservation.objects.create(
                        collection_run=run,
                        source=source,
                        municipality=municipality,
                        raw_artifact=artifact,
                        observed_at=observed_at,
                        **asdict(parsed),
                    )
                run.details_fetched += 1
                run.observations_created += 1

            run.status = CollectionRun.Status.SUCCEEDED
            run.finished_at = timezone.now()
            run.save()
            return run
        except Exception as exc:
            run.status = CollectionRun.Status.FAILED
            run.finished_at = timezone.now()
            run.error_message = str(exc)
            run.save()
            raise

    def _persist_raw(
        self,
        *,
        run: CollectionRun,
        kind: str,
        identifier: str,
        page: FetchedPage,
        observed_at: datetime,
    ) -> RawArtifact:
        digest = sha256_hex(page.body)
        object_key = (
            f"winterthur/{observed_at:%Y/%m/%d}/{run.id}/{kind}-{identifier}-{digest[:16]}.html"
        )
        path: Path = self.raw_store.write_bytes(object_key, page.body)
        if sha256_file(path) != digest:
            raise WinterthurCollectorError(f"RAW SHA-256 verification failed for {object_key}")
        return RawArtifact.objects.create(
            object_key=object_key,
            sha256_digest=digest,
            byte_size=len(page.body),
            content_type=page.content_type,
        )
