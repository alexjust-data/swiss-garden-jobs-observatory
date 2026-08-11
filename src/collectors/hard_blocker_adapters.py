from __future__ import annotations

import html
import json
import re
from datetime import UTC, datetime
from html import escape
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
from collectors.priority_city_adapters import _normalized_title
from collectors.required_canton_adapters import ZurichCantonSoliqueAdapter
from sources.models import Source

GLARUS_LISTING = "https://recruitingapp-2910.umantis.com/Jobs/All?CompanyID=1"
SCHAFFHAUSEN_CANTON_LISTING = (
    "https://recruitingapp-2876.umantis.com/Jobs/1?lang=ger&Reset=G"
)
ST_GALLEN_CITY_API = "https://live.solique.ch/STSG/de/api/v1/data/"

_UMANTIS_DETAIL = re.compile(r"^/Vacancies/(?P<id>\d+)/Description/1/?$", re.I)


def _nonnegative_integer(value: object, field: str, label: str) -> int:
    if isinstance(value, bool):
        raise PlatformAdapterError(f"{label} {field} is invalid")
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str) and value.isascii() and value.isdigit():
        return int(value)
    raise PlatformAdapterError(f"{label} {field} is invalid")


class _PublicUmantisListingParser(HTMLParser):
    def __init__(self, origin: str, label: str) -> None:
        super().__init__(convert_charrefs=True)
        self.origin = origin
        self.label = label
        self.entries: list[ListingEntry] = []
        self.page_state: dict[str, object] | None = None
        self.connector_chunks: dict[str, str] = {}
        self._row: dict[str, str] | None = None
        self._capture_title = False
        self._title_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = (values.get("class") or "").split()
        if tag == "div" and (values.get("id") or "").startswith("connectortable_"):
            self.connector_chunks[values.get("id") or ""] = values.get(
                "data-one-item-chunk"
            ) or ""
        if tag == "table-navigation" and self.page_state is None:
            raw = values.get("initial-data-string") or ""
            if "TableCurrentPage" in raw:
                try:
                    state = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise PlatformAdapterError(
                        f"{self.label} Umantis pagination state is invalid"
                    ) from exc
                if isinstance(state, dict):
                    self.page_state = state
        if tag == "tr" and any(name.startswith("tableaslist_contentrow") for name in classes):
            self._row = {}
        if self._row is None or tag != "a" or "HSTableLinkSubTitle" not in classes:
            return
        path = urlsplit(values.get("href") or "").path
        match = _UMANTIS_DETAIL.fullmatch(path)
        if match is None:
            raise PlatformAdapterError(f"{self.label} Umantis entry lacks native ID")
        self._row["id"] = match.group("id")
        self._row["url"] = urljoin(self.origin, values.get("href") or "")
        self._capture_title = True
        self._title_chunks = []

    def handle_data(self, data: str) -> None:
        if self._capture_title:
            self._title_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._capture_title and self._row is not None:
            self._row["title"] = " ".join("".join(self._title_chunks).split())
            self._capture_title = False
            self._title_chunks = []
        if tag != "tr" or self._row is None:
            return
        row, self._row = self._row, None
        if not all(row.get(field) for field in ("id", "url", "title")):
            raise PlatformAdapterError(f"{self.label} Umantis listing row is incomplete")
        self.entries.append(ListingEntry(row["id"], row["url"], row["title"]))


class _PublicUmantisDetailParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.heading = ""
        self._in_h1 = False
        self._heading_chunks: list[str] = []
        self.text_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "meta" and values.get("property") == "og:title":
            self.title = values.get("content") or ""
        if tag == "h1":
            self._in_h1 = True
            self._heading_chunks = []

    def handle_data(self, data: str) -> None:
        self.text_chunks.append(data)
        if self._in_h1:
            self._heading_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1" and self._in_h1:
            self.heading = " ".join(" ".join(self._heading_chunks).split())
            self._in_h1 = False

    @property
    def resolved_title(self) -> str:
        return self.heading or self.title

    @property
    def text(self) -> str:
        return " ".join(" ".join(self.text_chunks).split())


class _ConfiguredPublicUmantisAdapter:
    platform_family = ""
    listing_url = ""
    origin = ""
    contract_label = ""
    source_format = "UMANTIS_PUBLIC_HTML_V1"

    def initial_listing_request(self, source: Source) -> FetchRequest:
        return FetchRequest(
            self.listing_url,
            "text/html",
            "LISTING_PAGE",
            context={"page_number": 1, "surface_name": "unified"},
        )

    def parse_listing_page(
        self, page: FetchedPage, request: FetchRequest, source: Source
    ) -> ListingPage:
        if page.content_type != "text/html":
            raise PlatformAdapterError(f"{self.contract_label} Umantis listing must be HTML")
        parser = _PublicUmantisListingParser(self.origin, self.contract_label)
        try:
            parser.feed(page.body.decode("utf-8"))
            parser.close()
        except UnicodeDecodeError as exc:
            raise PlatformAdapterError(
                f"{self.contract_label} Umantis listing is not UTF-8"
            ) from exc
        if parser.page_state is None:
            raise PlatformAdapterError(
                f"{self.contract_label} Umantis listing contract is missing"
            )
        state = parser.page_state
        table_number = str(state.get("TableNr") or "")
        page_size = _nonnegative_integer(
            state.get("TableMaxEntries"), "page size", self.contract_label
        )
        if not table_number or page_size < 1:
            raise PlatformAdapterError(
                f"{self.contract_label} Umantis table contract is invalid"
            )
        if len(parser.connector_chunks) != 1 or next(iter(parser.connector_chunks.values())) != str(
            page_size
        ):
            raise PlatformAdapterError(
                f"{self.contract_label} Umantis connector contract is missing"
            )
        expected_page = cast(int, request.context.get("page_number", 1))
        current = _nonnegative_integer(
            state.get("TableCurrentPage"), "current page", self.contract_label
        )
        start = _nonnegative_integer(state.get("TableFrom"), "range start", self.contract_label)
        end = _nonnegative_integer(state.get("TableTo"), "range end", self.contract_label)
        total = _nonnegative_integer(state.get("TableTotalLines"), "total", self.contract_label)
        prior_total = request.context.get("reported_total")
        if current != expected_page:
            raise PlatformAdapterError(
                f"{self.contract_label} Umantis pagination did not advance monotonically"
            )
        if prior_total is not None and total != prior_total:
            raise PlatformAdapterError(
                f"{self.contract_label} Umantis total changed during pagination"
            )
        if total == 0:
            if parser.entries or expected_page != 1 or (start, end) not in {(0, 0), (1, 0)}:
                raise PlatformAdapterError(
                    f"{self.contract_label} Umantis empty range is inconsistent"
                )
        else:
            expected_start = (expected_page - 1) * page_size + 1
            if start != expected_start or end != start + len(parser.entries) - 1:
                raise PlatformAdapterError(
                    f"{self.contract_label} Umantis page range is inconsistent"
                )
        complete = end == total
        next_request: FetchRequest | None = None
        if not complete:
            next_link = state.get("NextLink")
            next_url = next_link.get("EnhancedUrl") if isinstance(next_link, dict) else None
            if not isinstance(next_url, str) or not next_url:
                raise PlatformAdapterError(
                    f"{self.contract_label} Umantis lacks a next-page contract"
                )
            decoded = html.unescape(next_url).split("#", 1)[0]
            if f"tc{table_number}=p{expected_page + 1}" not in decoded:
                raise PlatformAdapterError(
                    f"{self.contract_label} Umantis next page skipped an offset"
                )
            next_request = FetchRequest(
                urljoin(self.listing_url, decoded),
                "text/html",
                "LISTING_PAGE",
                context={
                    "page_number": expected_page + 1,
                    "surface_name": "unified",
                    "reported_total": total,
                },
            )
        return ListingPage(parser.entries, next_request, complete, total if complete else None)

    def detail_request(self, entry: ListingEntry, source: Source) -> FetchRequest:
        return FetchRequest(entry.detail_url, "text/html", "DETAIL")

    def parse_detail(
        self, page: FetchedPage, entry: ListingEntry, source: Source
    ) -> ParsedSourcePosting:
        parsed_url = urlsplit(page.final_url)
        match = _UMANTIS_DETAIL.fullmatch(parsed_url.path)
        if (
            parsed_url.scheme != "https"
            or parsed_url.hostname != urlsplit(self.origin).hostname
            or match is None
            or match.group("id") != entry.source_posting_id
        ):
            raise PlatformAdapterError(
                f"{self.contract_label} Umantis detail identity mismatch"
            )
        parser = _PublicUmantisDetailParser()
        try:
            parser.feed(page.body.decode("utf-8"))
            parser.close()
        except UnicodeDecodeError as exc:
            raise PlatformAdapterError(
                f"{self.contract_label} Umantis detail is not UTF-8"
            ) from exc
        title = parser.resolved_title
        if not title or not parser.text:
            raise PlatformAdapterError(
                f"{self.contract_label} Umantis detail lacks title/body"
            )
        if _normalized_title(title) != _normalized_title(entry.title):
            raise PlatformAdapterError(
                f"{self.contract_label} Umantis detail title mismatch"
            )
        return ParsedSourcePosting(
            source_posting_id=entry.source_posting_id,
            canonical_url=page.final_url,
            title=title,
            published_at_raw=None,
            date_posted=None,
            valid_through=None,
            employment_type="",
            hiring_organization="",
            description_html=f"<p>{escape(parser.text)}</p>",
            responsibilities_html="",
            qualifications_html="",
            benefits_html="",
            raw_location="",
            location_street="",
            location_locality="",
            location_region="",
            location_postal_code="",
            location_country="CH",
            structured_payload={
                "source_format": self.source_format,
                "publication_id": entry.source_posting_id,
                "surface_name": "unified",
            },
            published_at_precision="UNKNOWN",
            published_at_parse_method="MISSING",
            contract_raw_text=parser.text,
        )


class GlarusUmantisAdapter(_ConfiguredPublicUmantisAdapter):
    platform_family = "UMANTIS_LINKED"
    listing_url = GLARUS_LISTING
    origin = "https://recruitingapp-2910.umantis.com"
    contract_label = "Glarus canton"
    source_format = "UMANTIS_GL_PUBLIC_HTML_V1"


class SchaffhausenCantonUmantisAdapter(_ConfiguredPublicUmantisAdapter):
    platform_family = "OFFICIAL_WEB"
    listing_url = SCHAFFHAUSEN_CANTON_LISTING
    origin = "https://recruitingapp-2876.umantis.com"
    contract_label = "Schaffhausen canton"
    source_format = "UMANTIS_SH_PUBLIC_HTML_V1"




class StGallenCitySoliqueAdapter(ZurichCantonSoliqueAdapter):
    platform_family = "CITY_SG_PORTAL"
    api_url = ST_GALLEN_CITY_API
    base_url = "https://live.solique.ch/STSG/de/"
    source_format = "SOLIQUE_STADT_SG_API_V1"
    contract_label = "Stadt St. Gallen"

    def parse_detail(
        self, page: FetchedPage, entry: ListingEntry, source: Source
    ) -> ParsedSourcePosting:
        item = entry.listing_metadata.get("api_job")
        if not isinstance(item, dict):
            raise PlatformAdapterError("Stadt St. Gallen detail lost Solique API evidence")
        if entry.source_posting_id not in urlsplit(page.final_url).path:
            raise PlatformAdapterError("Stadt St. Gallen detail identity mismatch")
        parser = _PublicUmantisDetailParser()
        try:
            parser.feed(page.body.decode("utf-8"))
            parser.close()
        except UnicodeDecodeError as exc:
            raise PlatformAdapterError("Stadt St. Gallen detail is not UTF-8") from exc
        title_value = item.get("title")
        listing_title = (
            str(title_value.get("value") or "") if isinstance(title_value, dict) else ""
        )
        title = parser.resolved_title
        if (
            not listing_title
            or not title
            or not parser.text
            or not _normalized_title(title).startswith(_normalized_title(listing_title))
        ):
            raise PlatformAdapterError("Stadt St. Gallen detail evidence is incomplete")
        company = item.get("company")
        position = item.get("position")
        organization = str(company.get("value") or "") if isinstance(company, dict) else ""
        employment_type = (
            str(position.get("value") or "") if isinstance(position, dict) else ""
        )
        timestamp = item.get("timestamp")
        source_updated_at: datetime | None = None
        if isinstance(timestamp, int | float) and not isinstance(timestamp, bool):
            try:
                source_updated_at = datetime.fromtimestamp(timestamp, tz=UTC)
            except (OverflowError, OSError, ValueError):
                source_updated_at = None
        return ParsedSourcePosting(
            source_posting_id=entry.source_posting_id,
            canonical_url=page.final_url,
            title=title,
            published_at_raw=None,
            date_posted=None,
            valid_through=None,
            employment_type=employment_type,
            hiring_organization=organization,
            description_html=f"<p>{escape(parser.text)}</p>",
            responsibilities_html="",
            qualifications_html="",
            benefits_html="",
            raw_location="",
            location_street="",
            location_locality="",
            location_region="",
            location_postal_code="",
            location_country="CH",
            structured_payload={"source_format": self.source_format, "api_job": item},
            source_updated_at=source_updated_at,
            published_at_precision="UNKNOWN",
            published_at_parse_method="MISSING",
            contract_raw_text=parser.text,
        )
