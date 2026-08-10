from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser
from typing import cast
from urllib.parse import urljoin, urlsplit

from collectors.platforms import (
    FetchedPage,
    FetchRequest,
    ListingEntry,
    ListingPage,
    ParsedSourcePosting,
    PlatformAdapterError,
)
from collectors.priority_city_adapters import (
    _iso_datetime,
    _parsed_from_json_ld,
    _ProspectiveAdapterBase,
    _text,
)
from sources.models import Source

ZURICH_CANTON_API = "https://live.solique.ch/KTZH/de/api/v1/data/"
ZURICH_CANTON_BASE = "https://live.solique.ch"
APPENZELL_AR_API = "https://live.solique.ch/kanton-appenzell-ausserrhoden/api/json/"
ZUG_LISTING = "https://zg.prospective.ch/"
ZUG_APPRENTICESHIP_LISTING = "https://zg.prospective.ch/lernende/"
BASEL_LANDSCHAFT_LISTING = "https://ohws.prospective.ch/public/v1/careercenter/1571/"

_UUID_PATH = re.compile(
    r"/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/?$",
    re.IGNORECASE,
)


def _object_text(value: object, key: str = "value") -> str:
    if isinstance(value, dict):
        return _text(value.get(key))
    return _text(value)


def _unix_datetime(value: object) -> datetime | None:
    if not isinstance(value, int | float):
        return None
    try:
        return datetime.fromtimestamp(value, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


class ZurichCantonSoliqueAdapter:
    platform_family = "SOLIQUE_LINKED"

    def initial_listing_request(self, source: Source) -> FetchRequest:
        return FetchRequest(ZURICH_CANTON_API, "application/json", "LISTING_PAGE")

    def parse_listing_page(
        self, page: FetchedPage, request: FetchRequest, source: Source
    ) -> ListingPage:
        if page.content_type != "application/json":
            raise PlatformAdapterError("Zurich canton Solique listing must be JSON")
        try:
            payload = json.loads(page.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PlatformAdapterError(
                "Zurich canton Solique listing contains invalid JSON"
            ) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise PlatformAdapterError("Zurich canton Solique listing lacks jobs")
        jobs = cast(list[object], payload["jobs"])
        entries: list[ListingEntry] = []
        for raw in jobs:
            if not isinstance(raw, dict):
                raise PlatformAdapterError("Zurich canton Solique job must be an object")
            title_value = raw.get("title")
            source_id = _object_text(title_value, "id")
            title = _object_text(title_value)
            link = _text(raw.get("link"))
            if not source_id or not title or not link:
                raise PlatformAdapterError("Zurich canton Solique job lacks id/title/link")
            detail_url = urljoin(ZURICH_CANTON_BASE, link)
            if urlsplit(detail_url).hostname != "live.solique.ch":
                raise PlatformAdapterError("Zurich canton Solique detail is outside verified host")
            entries.append(ListingEntry(source_id, detail_url, title, {"api_job": raw}))
        filters = payload.get("filters")
        position = filters.get("position") if isinstance(filters, dict) else None
        reported = position.get("count") if isinstance(position, dict) else None
        if reported is not None and (not isinstance(reported, int) or reported < 0):
            raise PlatformAdapterError("Zurich canton Solique reported count is invalid")
        total = cast(int | None, reported)
        return ListingPage(entries, None, True, total)

    def detail_request(self, entry: ListingEntry, source: Source) -> FetchRequest:
        return FetchRequest(entry.detail_url, "text/html", "DETAIL")

    def parse_detail(
        self, page: FetchedPage, entry: ListingEntry, source: Source
    ) -> ParsedSourcePosting:
        item = entry.listing_metadata.get("api_job")
        if not isinstance(item, dict):
            raise PlatformAdapterError("Zurich canton detail lost Solique API evidence")
        if entry.source_posting_id not in urlsplit(page.final_url).path:
            raise PlatformAdapterError("Zurich canton detail identity mismatch")
        html_content = _text(item.get("htmlContent"))
        title = _object_text(item.get("title"))
        if not html_content or title != entry.title:
            raise PlatformAdapterError("Zurich canton detail evidence is incomplete")
        location = _object_text(item.get("location"))
        organization = _object_text(item.get("organization"))
        office = _object_text(item.get("office"))
        updated_at = _unix_datetime(item.get("timestamp"))
        return ParsedSourcePosting(
            source_posting_id=entry.source_posting_id,
            canonical_url=page.final_url,
            title=title,
            published_at_raw=None,
            date_posted=None,
            valid_through=None,
            employment_type="",
            hiring_organization=office or organization,
            description_html=html_content,
            responsibilities_html="",
            qualifications_html="",
            benefits_html="",
            raw_location=location,
            location_street="",
            location_locality="",
            location_region="",
            location_postal_code="",
            location_country="CH",
            structured_payload={"source_format": "SOLIQUE_KTZH_API_V1", "api_job": item},
            source_updated_at=updated_at,
            published_at_precision="UNKNOWN",
            published_at_parse_method="MISSING",
            contract_raw_text=html_content,
        )


class AppenzellAusserrhodenSoliqueAdapter:
    platform_family = "SOLIQUE_EMBEDDED"

    def initial_listing_request(self, source: Source) -> FetchRequest:
        return FetchRequest(APPENZELL_AR_API, "application/json", "LISTING_PAGE")

    def parse_listing_page(
        self, page: FetchedPage, request: FetchRequest, source: Source
    ) -> ListingPage:
        if page.content_type != "application/json":
            raise PlatformAdapterError("Appenzell AR Solique listing must be JSON")
        try:
            payload = json.loads(page.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PlatformAdapterError(
                "Appenzell AR Solique listing contains invalid JSON"
            ) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise PlatformAdapterError("Appenzell AR Solique listing lacks jobs")
        entries: list[ListingEntry] = []
        for raw in cast(list[object], payload["jobs"]):
            if not isinstance(raw, dict):
                raise PlatformAdapterError("Appenzell AR Solique job must be an object")
            source_id = _text(raw.get("sPublicationId"))
            title = _text(raw.get("jobtitle"))
            deep_link = _text(raw.get("deepLink"))
            if not source_id or not title or not deep_link:
                raise PlatformAdapterError(
                    "Appenzell AR Solique job lacks publication ID/title/link"
                )
            if urlsplit(deep_link).hostname != "live.solique.ch":
                raise PlatformAdapterError("Appenzell AR Solique detail is outside verified host")
            entries.append(ListingEntry(source_id, deep_link, title, {"api_job": raw}))
        return ListingPage(entries, None, True, len(entries))

    def detail_request(self, entry: ListingEntry, source: Source) -> FetchRequest:
        return FetchRequest(entry.detail_url, "text/html", "DETAIL")

    def parse_detail(
        self, page: FetchedPage, entry: ListingEntry, source: Source
    ) -> ParsedSourcePosting:
        item = entry.listing_metadata.get("api_job")
        if not isinstance(item, dict):
            raise PlatformAdapterError("Appenzell AR detail lost Solique API evidence")
        workload_from = _text(item.get("workload-from"))
        workload_to = _text(item.get("workload-to"))
        workload = ""
        if workload_from and workload_to:
            workload = (
                f" {workload_from}%"
                if workload_from == workload_to
                else f" {workload_from}% - {workload_to}%"
            )
        elif workload_from or workload_to:
            workload = f" {workload_from or workload_to}%"
        detail_entry = ListingEntry(
            entry.source_posting_id,
            entry.detail_url,
            f"{entry.title}{workload}",
            entry.listing_metadata,
        )
        return _parsed_from_json_ld(
            page=page,
            entry=detail_entry,
            published_raw=_text(item.get("startDate")) or None,
            source_published_at=_iso_datetime(item.get("startDate")),
            source_updated_at=_iso_datetime(item.get("dateModified")),
            parse_method="SOURCE_FIELD",
            extra_payload={"source_format": "SOLIQUE_LEGACY_JSON_V1", "listing_api": item},
        )


class _ProspectiveListingParser(HTMLParser):
    def __init__(self, detail_host: str, contract_form_id: str) -> None:
        super().__init__(convert_charrefs=True)
        self.detail_host = detail_host
        self.contract_form_id = contract_form_id
        self.contract_seen = False
        self.entries: list[ListingEntry] = []
        self.page_offsets: set[int] = set()
        self.reported_total: int | None = None
        self._text_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "form" and values.get("id") == self.contract_form_id:
            self.contract_seen = True
        if tag == "a":
            href = values.get("href") or ""
            match = _UUID_PATH.search(urlsplit(href).path)
            if match and urlsplit(href).hostname == self.detail_host:
                title = unescape(values.get("title") or "").strip()
                if not title:
                    raise PlatformAdapterError("Prospective listing entry lacks title")
                self.entries.append(ListingEntry(match.group(1).lower(), href, title))
            page_match = re.search(r"sendPagination\((\d+)\)", values.get("onclick") or "")
            classes = (values.get("class") or "").split()
            if page_match and "disableClick" not in classes:
                self.page_offsets.add(int(page_match.group(1)))

    def handle_data(self, data: str) -> None:
        self._text_chunks.append(data)

    def close(self) -> None:
        super().close()
        text = " ".join(" ".join(self._text_chunks).split())
        match = re.search(r"\b(\d+)\s+offene\s+Stellen\b", text, re.IGNORECASE)
        self.reported_total = int(match.group(1)) if match else None


class _ConfiguredProspectiveLegacyAdapter(_ProspectiveAdapterBase):
    platform_family = ""
    listing_surfaces: tuple[tuple[str, str], ...] = ()
    detail_host = ""
    contract_form_id = ""
    page_size = 0
    include_workload = False

    def _request(self, offset: int, surface_index: int = 0) -> FetchRequest:
        try:
            surface_name, listing_url = self.listing_surfaces[surface_index]
        except IndexError as exc:
            raise PlatformAdapterError("Invalid Prospective listing surface") from exc
        context = {
            "offset": offset,
            "surface_index": surface_index,
            "surface_name": surface_name,
        }
        if offset == 0:
            return FetchRequest(
                listing_url, "text/html", "LISTING_PAGE", context=context
            )
        fields = [
            ("offset", str(offset)),
            ("limit", str(self.page_size)),
            ("lang", "de"),
            ("query", ""),
        ]
        if self.include_workload:
            fields.append(("workload", "10,100"))
        return FetchRequest(
            listing_url,
            "text/html",
            "LISTING_PAGE",
            method="POST",
            form_data=tuple(fields),
            context=context,
        )

    def initial_listing_request(self, source: Source) -> FetchRequest:
        return self._request(0, 0)

    def parse_listing_page(
        self, page: FetchedPage, request: FetchRequest, source: Source
    ) -> ListingPage:
        parser = _ProspectiveListingParser(self.detail_host, self.contract_form_id)
        try:
            parser.feed(page.body.decode("utf-8"))
            parser.close()
        except UnicodeDecodeError as exc:
            raise PlatformAdapterError("Prospective listing is not UTF-8") from exc
        if not parser.contract_seen:
            raise PlatformAdapterError("Prospective listing contract marker is missing")
        current = cast(int, request.context.get("offset", 0))
        surface_index = cast(int, request.context.get("surface_index", 0))
        next_offset = min(
            (offset for offset in parser.page_offsets if offset > current), default=None
        )
        if next_offset is not None:
            next_request = self._request(next_offset, surface_index)
        elif surface_index + 1 < len(self.listing_surfaces):
            next_request = self._request(0, surface_index + 1)
        else:
            next_request = None
        return ListingPage(
            parser.entries,
            next_request,
            next_request is None,
            parser.reported_total,
        )

    def detail_request(self, entry: ListingEntry, source: Source) -> FetchRequest:
        return FetchRequest(entry.detail_url, "text/html", "DETAIL")

    def parse_detail(
        self, page: FetchedPage, entry: ListingEntry, source: Source
    ) -> ParsedSourcePosting:
        return _parsed_from_json_ld(page=page, entry=entry)


class ZugProspectiveLegacyAdapter(_ConfiguredProspectiveLegacyAdapter):
    platform_family = "PROSPECTIVE"
    listing_surfaces = (
        ("ordinary", ZUG_LISTING),
        ("apprenticeships", ZUG_APPRENTICESHIP_LISTING),
    )
    detail_host = "www.zg.ch"
    contract_form_id = "careercenter-form"
    page_size = 10


class BaselLandschaftProspectiveLegacyAdapter(_ConfiguredProspectiveLegacyAdapter):
    platform_family = "PROSPECTIVE_UMANTIS_LINKED"
    listing_surfaces = (("all_vacancies", BASEL_LANDSCHAFT_LISTING),)
    detail_host = "jobs.baselland.ch"
    contract_form_id = "oh-form"
    page_size = 15
    include_workload = True
