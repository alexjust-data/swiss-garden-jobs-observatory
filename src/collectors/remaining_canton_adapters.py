from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import cast
from urllib.parse import urlsplit

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
    _JobPostingParser,
    _parsed_from_json_ld,
    _text,
)
from collectors.required_canton_adapters import _ConfiguredProspectiveLegacyAdapter
from sources.models import Source

GRAUBUENDEN_TENANT = "https://apply.refline.ch/514915"
GRAUBUENDEN_SURFACES = (
    ("ordinary", f"{GRAUBUENDEN_TENANT}/search.html"),
    ("apprenticeships", f"{GRAUBUENDEN_TENANT}/apprentice.html"),
    ("trial_apprenticeships", f"{GRAUBUENDEN_TENANT}/stage.html"),
)
SOLOTHURN_LISTING = "https://job.so.ch/"
SCHWYZ_LISTING = "https://jobs.sz.ch/"
_REFLINE_DETAIL = re.compile(
    r"^/514915/(?P<id>\d+)/pub/(?P<channel>\d+)/index\.html$", re.IGNORECASE
)
_UUID_DETAIL = re.compile(
    r"/(?P<id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/?$",
    re.IGNORECASE,
)


def _parse_new_json_ld_detail(
    page: FetchedPage, entry: ListingEntry, *, source_format: str
) -> ParsedSourcePosting:
    parser = _JobPostingParser()
    try:
        parser.feed(page.body.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise PlatformAdapterError("detail is not UTF-8") from exc
    raw_date = _text(parser.posting.get("datePosted")).strip() or None
    timestamp = (
        _iso_datetime(raw_date)
        if raw_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date)
        else None
    )
    return _parsed_from_json_ld(
        page=page,
        entry=entry,
        published_raw=raw_date,
        source_published_at=timestamp,
        parse_method="STRUCTURED_DATA",
        extra_payload={
            "source_format": source_format,
            "surface_name": entry.listing_metadata.get("surface_name", "unified"),
        },
    )


class _ReflineListingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: list[ListingEntry] = []
        self.refline_seen = False
        self.table_contract_seen = False
        self.empty_contract_seen = False
        self._text: list[str] = []
        self._entry: tuple[str, str, list[str]] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag != "a":
            return
        parsed = urlsplit(values.get("href") or "")
        if parsed.hostname and parsed.hostname != "apply.refline.ch":
            return
        match = _REFLINE_DETAIL.fullmatch(parsed.path)
        if match is not None:
            self._entry = (
                match.group("id"),
                f"https://apply.refline.ch{parsed.path}",
                [],
            )

    def handle_data(self, data: str) -> None:
        self._text.append(data)
        if self._entry is not None:
            self._entry[2].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._entry is None:
            return
        source_id, url, chunks = self._entry
        self._entry = None
        title = " ".join(" ".join(chunks).split())
        if not title:
            raise PlatformAdapterError("Graubünden Refline entry lacks title")
        self.entries.append(ListingEntry(source_id, url, title))

    def close(self) -> None:
        super().close()
        text = " ".join(" ".join(self._text).split())
        self.refline_seen = "powered by Refline" in text
        self.table_contract_seen = all(
            marker in text for marker in ("Stellentitel", "Amt", "Arbeitsort", "Anmeldefrist")
        )
        self.empty_contract_seen = "Derzeit liegen keine Stellenausschreibungen vor" in text


class GraubuendenReflineAdapter:
    platform_family = "CANTON_GR_PORTAL"

    def _request(self, surface_index: int) -> FetchRequest:
        try:
            surface_name, url = GRAUBUENDEN_SURFACES[surface_index]
        except IndexError as exc:
            raise PlatformAdapterError("Invalid Graubünden Refline surface") from exc
        return FetchRequest(
            url,
            "text/html",
            "LISTING_PAGE",
            context={"surface_index": surface_index, "surface_name": surface_name},
        )

    def initial_listing_request(self, source: Source) -> FetchRequest:
        return self._request(0)

    def parse_listing_page(
        self, page: FetchedPage, request: FetchRequest, source: Source
    ) -> ListingPage:
        if page.content_type != "text/html":
            raise PlatformAdapterError("Graubünden Refline listing must be HTML")
        parser = _ReflineListingParser()
        try:
            parser.feed(page.body.decode("utf-8"))
            parser.close()
        except UnicodeDecodeError as exc:
            raise PlatformAdapterError("Graubünden Refline listing is not UTF-8") from exc
        if not parser.refline_seen or not parser.table_contract_seen:
            raise PlatformAdapterError("Graubünden Refline listing contract marker is missing")
        if not parser.entries and not parser.empty_contract_seen:
            raise PlatformAdapterError("Graubünden Refline surface lacks entries or empty marker")
        surface_index = cast(int, request.context.get("surface_index", 0))
        surface_name = cast(str, request.context.get("surface_name", ""))
        entries = [
            ListingEntry(
                item.source_posting_id,
                item.detail_url,
                item.title,
                {"surface_name": surface_name},
            )
            for item in parser.entries
        ]
        next_request = (
            self._request(surface_index + 1)
            if surface_index + 1 < len(GRAUBUENDEN_SURFACES)
            else None
        )
        return ListingPage(entries, next_request, next_request is None)

    def detail_request(self, entry: ListingEntry, source: Source) -> FetchRequest:
        return FetchRequest(
            entry.detail_url,
            "text/html",
            "DETAIL",
            context={"surface_name": entry.listing_metadata.get("surface_name", "")},
        )

    def parse_detail(
        self, page: FetchedPage, entry: ListingEntry, source: Source
    ) -> ParsedSourcePosting:
        expected_path = urlsplit(entry.detail_url).path.rstrip("/")
        final_path = urlsplit(page.final_url).path.rstrip("/")
        match = _REFLINE_DETAIL.fullmatch(final_path)
        if match is None or match.group("id") != entry.source_posting_id:
            raise PlatformAdapterError("Graubünden Refline detail identity mismatch")
        if final_path != expected_path:
            raise PlatformAdapterError("Graubünden Refline canonical detail changed")
        return _parse_new_json_ld_detail(page, entry, source_format="REFLINE_JOBPOSTING_V1")


class _C3ProspectiveAdapter(_ConfiguredProspectiveLegacyAdapter):
    def parse_detail(
        self, page: FetchedPage, entry: ListingEntry, source: Source
    ) -> ParsedSourcePosting:
        return _parse_new_json_ld_detail(
            page,
            entry,
            source_format="PROSPECTIVE_CAREERCENTER_JSONLD_V1",
        )


class _SolothurnListingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.contract_seen = False
        self.entries: list[ListingEntry] = []
        self.reported_total: int | None = None
        self._entry: tuple[str, str, list[str]] | None = None
        self._capture_title = False
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "form" and values.get("id") == "careercenter-form":
            self.contract_seen = True
        if tag == "a" and "job" in (values.get("class") or "").split():
            parsed = urlsplit(values.get("href") or "")
            match = _UUID_DETAIL.search(parsed.path)
            if parsed.hostname == "job.so.ch" and match is not None:
                self._entry = (
                    match.group("id").lower(),
                    f"https://job.so.ch{parsed.path}",
                    [],
                )
        if tag == "h2" and self._entry is not None:
            self._capture_title = True

    def handle_data(self, data: str) -> None:
        self._text.append(data)
        if self._capture_title and self._entry is not None:
            self._entry[2].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2":
            self._capture_title = False
        if tag != "a" or self._entry is None:
            return
        source_id, url, chunks = self._entry
        self._entry = None
        title = " ".join(" ".join(chunks).split())
        if not title:
            raise PlatformAdapterError("Solothurn listing entry lacks title")
        self.entries.append(ListingEntry(source_id, url, title))

    def close(self) -> None:
        super().close()
        text = " ".join(" ".join(self._text).split())
        match = re.search(r"\b(\d+)\s+offene\s+Stellen\b", text, re.IGNORECASE)
        self.reported_total = int(match.group(1)) if match else None


class SolothurnProspectiveAdapter(_C3ProspectiveAdapter):
    platform_family = "CANTON_SO_PORTAL"
    listing_surfaces = (("unified", SOLOTHURN_LISTING),)
    detail_host = "job.so.ch"
    contract_form_id = "careercenter-form"
    page_size = 1000

    def parse_listing_page(
        self, page: FetchedPage, request: FetchRequest, source: Source
    ) -> ListingPage:
        if page.content_type != "text/html":
            raise PlatformAdapterError("Solothurn listing must be HTML")
        parser = _SolothurnListingParser()
        try:
            parser.feed(page.body.decode("utf-8"))
            parser.close()
        except UnicodeDecodeError as exc:
            raise PlatformAdapterError("Solothurn listing is not UTF-8") from exc
        if not parser.contract_seen:
            raise PlatformAdapterError("Solothurn listing contract marker is missing")
        if parser.reported_total is None:
            raise PlatformAdapterError("Solothurn listing lacks a reported total")
        if parser.reported_total > self.page_size:
            raise PlatformAdapterError("Solothurn reported total exceeds verified feed capacity")
        entries = [
            ListingEntry(
                item.source_posting_id,
                item.detail_url,
                item.title,
                {"surface_name": "unified"},
            )
            for item in parser.entries
        ]
        return ListingPage(entries, None, True, parser.reported_total)


class SchwyzProspectiveAdapter(_C3ProspectiveAdapter):
    platform_family = "CANTON_SZ_PORTAL"
    listing_surfaces = (("unified", SCHWYZ_LISTING),)
    detail_host = "jobs.sz.ch"
    contract_form_id = "oh-form"
    page_size = 8

    def parse_listing_page(
        self, page: FetchedPage, request: FetchRequest, source: Source
    ) -> ListingPage:
        current = cast(int, request.context.get("offset", 0))
        parsed = super().parse_listing_page(page, request, source)
        if len(parsed.entries) > self.page_size:
            raise PlatformAdapterError("Schwyz listing exceeded its verified page size")
        if parsed.next_request is not None:
            next_offset = cast(int, parsed.next_request.context.get("offset", -1))
            if next_offset != current + self.page_size:
                raise PlatformAdapterError("Schwyz pagination did not advance monotonically")
        return parsed
