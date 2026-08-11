from __future__ import annotations

import html
import json
import re
from datetime import UTC, datetime
from html import escape
from html.parser import HTMLParser
from io import BytesIO
from typing import cast
from urllib.parse import urljoin, urlsplit

from pypdf import PdfReader
from pypdf.errors import PdfReadError

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
GLARUS_COURT_LISTING = (
    "https://www.gl.ch/rechtspflege/gerichte/"
    "offene-stellen-der-gerichte.html/4714"
)
SCHAFFHAUSEN_CANTON_LISTING = (
    "https://recruitingapp-2876.umantis.com/Jobs/1?lang=ger&Reset=G"
)
ST_GALLEN_CITY_API = "https://live.solique.ch/STSG/de/api/v1/data/"

_UMANTIS_DETAIL = re.compile(r"^/Vacancies/(?P<id>\d+)/Description/1/?$", re.I)
_GLARUS_COURT_ASSET = re.compile(
    r"^/public/upload/assets/(?P<id>\d+)/[^/]+\.pdf$",
    re.I,
)


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


class _GlarusCourtListingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: list[ListingEntry] = []
        self.non_vacancy_urls: list[str] = []
        self._text_chunks: list[str] = []
        self._anchor: tuple[str, list[str]] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href") or ""
        parsed = urlsplit(href)
        if parsed.hostname not in {None, "www.gl.ch"}:
            return
        if _GLARUS_COURT_ASSET.fullmatch(parsed.path) is None:
            return
        self._anchor = (href, [])

    def handle_data(self, data: str) -> None:
        self._text_chunks.append(data)
        if self._anchor is not None:
            self._anchor[1].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._anchor is None:
            return
        href, chunks = self._anchor
        self._anchor = None
        parsed = urlsplit(href)
        match = _GLARUS_COURT_ASSET.fullmatch(parsed.path)
        if match is None:
            return
        title = " ".join(" ".join(chunks).split())
        title = re.sub(r"\s*\[pdf.*$", "", title, flags=re.I).strip()
        if not title:
            raise PlatformAdapterError("Glarus court publication lacks a title")
        canonical_url = urljoin(GLARUS_COURT_LISTING, href)
        if "volont" in _normalized_title(title):
            self.non_vacancy_urls.append(canonical_url)
            return
        self.entries.append(
            ListingEntry(
                f"court:{match.group('id')}",
                canonical_url,
                title,
                {
                    "surface_name": "courts",
                    "court_asset_id": match.group("id"),
                },
            )
        )

    @property
    def text(self) -> str:
        return " ".join(" ".join(self._text_chunks).split())


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

    def initial_listing_request(self, source: Source) -> FetchRequest:
        request = super().initial_listing_request(source)
        request.context["surface_name"] = "umantis"
        return request

    def parse_listing_page(
        self, page: FetchedPage, request: FetchRequest, source: Source
    ) -> ListingPage:
        if request.context.get("surface_name") == "courts":
            return self._parse_court_listing(page, request)
        parsed = super().parse_listing_page(page, request, source)
        if parsed.next_request is not None:
            parsed.next_request.context["surface_name"] = "umantis"
            return parsed
        if not parsed.discovery_complete or parsed.total_reported is None:
            raise PlatformAdapterError("Glarus Umantis surface did not prove completeness")
        court_request = FetchRequest(
            GLARUS_COURT_LISTING,
            "text/html",
            "LISTING_PAGE",
            context={
                "surface_name": "courts",
                "umantis_total": parsed.total_reported,
            },
        )
        return ListingPage(parsed.entries, court_request, False)

    def _parse_court_listing(
        self, page: FetchedPage, request: FetchRequest
    ) -> ListingPage:
        if page.content_type != "text/html":
            raise PlatformAdapterError("Glarus court listing must be HTML")
        parser = _GlarusCourtListingParser()
        try:
            parser.feed(page.body.decode("utf-8"))
            parser.close()
        except UnicodeDecodeError as exc:
            raise PlatformAdapterError("Glarus court listing is not UTF-8") from exc
        normalized = _normalized_title(parser.text)
        heading_seen = "offene stellen der gerichte" in normalized
        open_contract = "zurzeit sind folgende stellen" in normalized and "offen" in normalized
        empty_contract = (
            "zurzeit sind keine stellen" in normalized
            or "keine offenen stellen" in normalized
        )
        if not heading_seen or not (open_contract or empty_contract):
            raise PlatformAdapterError("Glarus court listing contract is missing")
        if open_contract and not parser.entries and not parser.non_vacancy_urls:
            raise PlatformAdapterError("Glarus court listing exposes no classified publications")
        if empty_contract and (parser.entries or parser.non_vacancy_urls):
            raise PlatformAdapterError("Glarus court empty state conflicts with publications")
        umantis_total = request.context.get("umantis_total")
        if isinstance(umantis_total, bool) or not isinstance(umantis_total, int):
            raise PlatformAdapterError("Glarus court listing lost Umantis total evidence")
        return ListingPage(
            parser.entries,
            None,
            True,
            umantis_total + len(parser.entries),
        )

    def detail_request(self, entry: ListingEntry, source: Source) -> FetchRequest:
        if entry.listing_metadata.get("surface_name") == "courts":
            return FetchRequest(
                entry.detail_url,
                "application/pdf",
                "DETAIL",
                context={"surface_name": "courts"},
            )
        return FetchRequest(
            entry.detail_url,
            "text/html",
            "DETAIL",
            context={"surface_name": "umantis"},
        )

    def parse_detail(
        self, page: FetchedPage, entry: ListingEntry, source: Source
    ) -> ParsedSourcePosting:
        if entry.listing_metadata.get("surface_name") == "courts":
            return self._parse_court_detail(page, entry)
        return super().parse_detail(page, entry, source)

    def _parse_court_detail(
        self, page: FetchedPage, entry: ListingEntry
    ) -> ParsedSourcePosting:
        parsed = urlsplit(page.final_url)
        match = _GLARUS_COURT_ASSET.fullmatch(parsed.path)
        asset_id = entry.listing_metadata.get("court_asset_id")
        if (
            parsed.scheme != "https"
            or parsed.hostname != "www.gl.ch"
            or match is None
            or match.group("id") != asset_id
            or entry.source_posting_id != f"court:{asset_id}"
        ):
            raise PlatformAdapterError("Glarus court detail identity mismatch")
        if page.content_type != "application/pdf" or not page.body.startswith(b"%PDF-"):
            raise PlatformAdapterError("Glarus court detail must be PDF")
        try:
            reader = PdfReader(BytesIO(page.body))
            text = " ".join(
                " ".join((pdf_page.extract_text() or "").split())
                for pdf_page in reader.pages
            ).strip()
        except (PdfReadError, OSError, ValueError) as exc:
            raise PlatformAdapterError("Glarus court PDF is malformed") from exc
        normalized = _normalized_title(text)
        if (
            "wir suchen" not in normalized
            or "bewerbung" not in normalized
            or not any(
                marker in normalized
                for marker in ("pensum", "stellenantritt", "anstellungsbedingungen")
            )
        ):
            raise PlatformAdapterError("Glarus court PDF lacks vacancy evidence")
        if (
            "ganzjahrig" in normalized
            and "ohne entlohnung" in normalized
            and "zwei wochen" in normalized
        ):
            raise PlatformAdapterError("Glarus court non-vacancy reached detail promotion")
        location_match = re.search(
            r"Arbeitsort\s+([^,.]+?)(?:,|\.|\s+Stellenantritt)",
            text,
            flags=re.I,
        )
        locality = " ".join(location_match.group(1).split()) if location_match else ""
        return ParsedSourcePosting(
            source_posting_id=entry.source_posting_id,
            canonical_url=page.final_url,
            title=entry.title,
            published_at_raw=None,
            date_posted=None,
            valid_through=None,
            employment_type="Praktikum",
            hiring_organization="Gerichte des Kantons Glarus",
            description_html=f"<p>{escape(text)}</p>",
            responsibilities_html="",
            qualifications_html="",
            benefits_html="",
            raw_location=locality,
            location_street="",
            location_locality=locality,
            location_region="",
            location_postal_code="",
            location_country="CH",
            structured_payload={
                "source_format": "GLARUS_COURT_PDF_V1",
                "publication_id": entry.source_posting_id,
                "court_asset_id": asset_id,
                "surface_name": "courts",
            },
            published_at_precision="UNKNOWN",
            published_at_parse_method="MISSING",
            contract_raw_text=text,
        )


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
