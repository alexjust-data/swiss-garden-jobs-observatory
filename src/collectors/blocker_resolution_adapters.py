from __future__ import annotations

import html
import json
import re
from datetime import UTC, datetime
from html import escape
from html.parser import HTMLParser
from typing import cast
from urllib.parse import urlencode, urljoin, urlsplit

from collectors.platforms import (
    FetchedPage,
    FetchRequest,
    ListingEntry,
    ListingPage,
    ParsedSourcePosting,
    PlatformAdapterError,
)
from collectors.priority_city_adapters import _normalized_title
from collectors.remaining_canton_adapters import _parse_new_json_ld_detail
from sources.models import Source

LUZERN_TENANT = "https://apply.refline.ch/891537"
LUZERN_APPRENTICESHIP_API = "https://lehre.lu/api/web/jobs"
LUZERN_APPRENTICESHIP_PROFILE = "https://lehre.lu/map"
LUZERN_CANTON_SURFACES = (
    ("administration", f"{LUZERN_TENANT}/positions_verwaltung.html"),
    (
        "cantonal_schools",
        f"{LUZERN_TENANT}/positions_lehrpersonen.html?businessUnit=lehrpersonal",
    ),
    ("apprenticeships", LUZERN_APPRENTICESHIP_API),
)

ST_GALLEN_COMPANY_IDS = (
    "1|24|25|26|27|28|29|30|31|32|33|34|35|36|37|38|39|40|41|42|43|44|"
    "45|46|47|48|49|50|51|52|53|54|55|56|57|58|59|61|62|63|64|65|66|67|"
    "68|69|70|71|72|73|75|76|77|78|79|80|81|82|83|84|85|86|87|88|89|90|"
    "91|92|94|96|98|100|102|104|106|108|110|132|134|136"
)
ST_GALLEN_LISTING = (
    "https://recruitingapp-2800.umantis.com/Jobs/All?"
    + urlencode({"CompanyID": ST_GALLEN_COMPANY_IDS, "DesignID": "00"})
)
ST_GALLEN_PAGE_SIZE = 25

THURGAU_LISTING = "https://stellen.tg.ch/"
THURGAU_EXTERNAL_CATEGORY = "28"
THURGAU_EXTERNAL_LABEL = "Externe Institutionen"

_REFLINE_LU_DETAIL = re.compile(
    r"^/891537/(?P<id>\d+)/pub/(?P<channel>\d+)/index\.html$", re.IGNORECASE
)
_REFLINE_LU_APPLICATION = re.compile(r"^/891537/(?P<id>\d+)/?$", re.IGNORECASE)
_UMANTIS_DETAIL = re.compile(r"^/Vacancies/(?P<id>\d+)/Description/1/?$", re.IGNORECASE)
_TG_DETAIL = re.compile(
    r"^/public/v1/jobs/(?P<id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12})/?$",
    re.IGNORECASE,
)


class _LuzernReflineListingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: list[ListingEntry] = []
        self.contract_seen = False
        self.empty_seen = False
        self._entry: tuple[str, str, list[str]] | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag != "a":
            return
        parsed = urlsplit(values.get("href") or "")
        if parsed.hostname and parsed.hostname != "apply.refline.ch":
            return
        match = _REFLINE_LU_DETAIL.fullmatch(parsed.path)
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
            raise PlatformAdapterError("Luzern Refline entry lacks title")
        self.entries.append(ListingEntry(source_id, url, title))

    def close(self) -> None:
        super().close()
        text = " ".join(" ".join(self._text).split())
        self.contract_seen = all(marker in text for marker in ("Kanton Luzern", "Stelle", "Pensum"))
        self.empty_seen = "Derzeit liegen keine Stellenausschreibungen vor" in text


class LuzernCantonReflineAdapter:
    platform_family = "CANTON_LU_PORTAL"

    def _request(self, surface_index: int) -> FetchRequest:
        try:
            surface_name, url = LUZERN_CANTON_SURFACES[surface_index]
        except IndexError as exc:
            raise PlatformAdapterError("Invalid Luzern canton Refline surface") from exc
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
        surface_index = cast(int, request.context.get("surface_index", 0))
        surface_name = cast(str, request.context.get("surface_name", ""))
        next_request = (
            self._request(surface_index + 1)
            if surface_index + 1 < len(LUZERN_CANTON_SURFACES)
            else None
        )
        if surface_name == "apprenticeships":
            return self._parse_apprenticeship_listing(page, next_request)
        if page.content_type != "text/html":
            raise PlatformAdapterError("Luzern canton Refline listing must be HTML")
        parser = _LuzernReflineListingParser()
        try:
            parser.feed(page.body.decode("utf-8"))
            parser.close()
        except UnicodeDecodeError as exc:
            raise PlatformAdapterError("Luzern canton Refline listing is not UTF-8") from exc
        if not parser.contract_seen:
            raise PlatformAdapterError("Luzern canton Refline contract marker is missing")
        if not parser.entries and not parser.empty_seen:
            raise PlatformAdapterError(
                "Luzern canton Refline surface lacks entries or empty marker"
            )
        entries = [
            ListingEntry(
                item.source_posting_id,
                item.detail_url,
                item.title,
                {"surface_name": surface_name},
            )
            for item in parser.entries
        ]
        return ListingPage(entries, next_request, next_request is None)

    def _parse_apprenticeship_listing(
        self, page: FetchedPage, next_request: FetchRequest | None
    ) -> ListingPage:
        if page.content_type != "application/json":
            raise PlatformAdapterError("Luzern apprenticeship listing must be JSON")
        try:
            payload = json.loads(page.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PlatformAdapterError("Luzern apprenticeship listing is invalid JSON") from exc
        if not isinstance(payload, dict):
            raise PlatformAdapterError("Luzern apprenticeship listing must be an object")
        total, rows = payload.get("total"), payload.get("rows")
        if isinstance(total, bool) or not isinstance(total, int) or total < 0:
            raise PlatformAdapterError("Luzern apprenticeship profile total is invalid")
        if not isinstance(rows, list) or len(rows) != total:
            raise PlatformAdapterError("Luzern apprenticeship profile total changed")
        entries: list[ListingEntry] = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                raise PlatformAdapterError("Luzern apprenticeship profile is invalid")
            profile_id, free = row.get("id"), row.get("free")
            if not isinstance(profile_id, str) or not profile_id or not isinstance(free, bool):
                raise PlatformAdapterError(
                    "Luzern apprenticeship profile identity/state is invalid"
                )
            if profile_id in seen:
                raise PlatformAdapterError("Luzern apprenticeship profile ID is duplicated")
            seen.add(profile_id)
            if not free:
                continue
            title = row.get("title")
            entries.append(
                ListingEntry(
                    f"lehre:{profile_id}",
                    f"{LUZERN_APPRENTICESHIP_API}/{profile_id}",
                    title if isinstance(title, str) else "",
                    {"surface_name": "apprenticeships", "profile_id": profile_id},
                )
            )
        return ListingPage(entries, next_request, next_request is None)

    def detail_request(self, entry: ListingEntry, source: Source) -> FetchRequest:
        surface_name = entry.listing_metadata.get("surface_name", "")
        return FetchRequest(
            entry.detail_url,
            "application/json" if surface_name == "apprenticeships" else "text/html",
            "DETAIL",
            context={"surface_name": surface_name},
        )

    def parse_detail(
        self, page: FetchedPage, entry: ListingEntry, source: Source
    ) -> ParsedSourcePosting:
        if entry.listing_metadata.get("surface_name") == "apprenticeships":
            return self._parse_apprenticeship_detail(page, entry)
        expected = urlsplit(entry.detail_url).path.rstrip("/")
        final = urlsplit(page.final_url).path.rstrip("/")
        match = _REFLINE_LU_DETAIL.fullmatch(final)
        if match is None or match.group("id") != entry.source_posting_id or final != expected:
            raise PlatformAdapterError("Luzern canton Refline detail identity mismatch")
        return _parse_new_json_ld_detail(page, entry, source_format="REFLINE_JOBPOSTING_V1")

    def _parse_apprenticeship_detail(
        self, page: FetchedPage, entry: ListingEntry
    ) -> ParsedSourcePosting:
        if page.content_type != "application/json" or page.final_url != entry.detail_url:
            raise PlatformAdapterError("Luzern apprenticeship detail identity mismatch")
        try:
            payload = json.loads(page.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PlatformAdapterError("Luzern apprenticeship detail is invalid JSON") from exc
        if not isinstance(payload, dict):
            raise PlatformAdapterError("Luzern apprenticeship detail must be an object")
        profile_id = entry.listing_metadata.get("profile_id")
        if payload.get("id") != profile_id or payload.get("free") is not True:
            raise PlatformAdapterError("Luzern apprenticeship is not an active opportunity")
        application_url = payload.get("link_job")
        parsed_application = urlsplit(application_url if isinstance(application_url, str) else "")
        application_match = _REFLINE_LU_APPLICATION.fullmatch(parsed_application.path)
        if (
            parsed_application.scheme != "https"
            or parsed_application.hostname != "apply.refline.ch"
            or application_match is None
        ):
            raise PlatformAdapterError(
                "Luzern active apprenticeship lacks a governed application identity"
            )
        type_data = payload.get("type")
        location_data = payload.get("location")
        if not isinstance(type_data, dict) or not isinstance(location_data, dict):
            raise PlatformAdapterError("Luzern apprenticeship detail lacks type/location")
        title, location = type_data.get("title"), location_data.get("title")
        if not isinstance(title, str) or not title or not isinstance(location, str) or not location:
            raise PlatformAdapterError("Luzern apprenticeship detail lacks title/location")
        locality = location_data.get("city")
        postal_code = location_data.get("zip")
        description = payload.get("description")
        updated_at = payload.get("updated_at")
        source_updated_at: datetime | None = None
        if isinstance(updated_at, str):
            try:
                source_updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            except ValueError:
                source_updated_at = None
            if source_updated_at is not None and source_updated_at.tzinfo is None:
                source_updated_at = source_updated_at.replace(tzinfo=UTC)
        structured = dict(payload)
        structured["vacancy_boundary"] = {
            "active": True,
            "application_id": application_match.group("id"),
            "profile_is_evergreen": True,
            "schnupper_content_promoted": False,
        }
        raw_location = ", ".join(
            value
            for value in (
                location,
                str(postal_code) if isinstance(postal_code, str | int) else "",
                locality if isinstance(locality, str) else "",
            )
            if value
        )
        description_html = description if isinstance(description, str) else ""
        return ParsedSourcePosting(
            source_posting_id=entry.source_posting_id,
            canonical_url=f"{LUZERN_APPRENTICESHIP_PROFILE}/{profile_id}",
            title=f"Lehrstelle {title}",
            published_at_raw=None,
            date_posted=None,
            valid_through=None,
            employment_type="Lehrstelle",
            hiring_organization="Kanton Luzern",
            description_html=description_html,
            responsibilities_html="",
            qualifications_html="",
            benefits_html="",
            raw_location=raw_location,
            location_street="",
            location_locality=locality if isinstance(locality, str) else "",
            location_region="",
            location_postal_code=(
                str(postal_code) if isinstance(postal_code, str | int) else ""
            ),
            location_country="CH",
            structured_payload=structured,
            source_updated_at=source_updated_at,
            published_at_precision="UNKNOWN",
            published_at_parse_method="MISSING",
            contract_raw_text=" ".join((title, location, description_html)),
        )


class _StGallenListingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: list[ListingEntry] = []
        self.page_state: dict[str, object] | None = None
        self.contract_seen = False
        self._row: dict[str, str] | None = None
        self._capture = ""
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = (values.get("class") or "").split()
        if tag == "div" and values.get("id") == "connectortable_1":
            self.contract_seen = values.get("data-one-item-chunk") == str(ST_GALLEN_PAGE_SIZE)
        if tag == "table-navigation" and self.page_state is None:
            raw = values.get("initial-data-string") or ""
            if "TableCurrentPage" in raw:
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise PlatformAdapterError("St. Gallen pagination state is invalid") from exc
                if isinstance(parsed, dict):
                    self.page_state = parsed
        if tag == "tr" and any(name.startswith("tableaslist_contentrow") for name in classes):
            self._row = {}
        if self._row is None:
            return
        if tag == "a" and "HSTableLinkSubTitle" in classes:
            match = _UMANTIS_DETAIL.fullmatch(urlsplit(values.get("href") or "").path)
            if match is None:
                raise PlatformAdapterError("St. Gallen listing entry lacks native ID")
            self._row.update(
                {
                    "id": match.group("id"),
                    "url": urljoin(
                        "https://recruitingapp-2800.umantis.com", values.get("href") or ""
                    ),
                }
            )
            self._capture, self._chunks = "title", []
        elif tag == "span":
            mapping = {
                "tableaslist_element_1152491": "employment_type",
                "tableaslist_element_1152494": "organization",
                "tableaslist_element_1152495": "location",
            }
            for class_name, field_name in mapping.items():
                if class_name in classes:
                    self._capture, self._chunks = field_name, []
                    break

    def handle_data(self, data: str) -> None:
        if self._row is not None and self._capture:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._row is not None and self._capture and tag in {"a", "span"}:
            self._row[self._capture] = " ".join("".join(self._chunks).split())
            self._capture, self._chunks = "", []
        if tag != "tr" or self._row is None:
            return
        row, self._row = self._row, None
        if not all(row.get(field) for field in ("id", "url", "title")):
            raise PlatformAdapterError("St. Gallen listing row is incomplete")
        self.entries.append(
            ListingEntry(
                row["id"],
                row["url"],
                row["title"],
                {
                    "surface_name": "unified",
                    "organization": row.get("organization", ""),
                    "location": row.get("location", ""),
                    "employment_type": row.get("employment_type", ""),
                },
            )
        )


class _StGallenDetailParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.text_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "meta" and values.get("property") == "og:title":
            self.title = values.get("content") or ""

    def handle_data(self, data: str) -> None:
        self.text_chunks.append(data)

    @property
    def text(self) -> str:
        return " ".join(" ".join(self.text_chunks).split())


def _umantis_page_integer(value: object, field: str, *, allow_none: bool = False) -> int | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool):
        raise PlatformAdapterError(f"St. Gallen Umantis {field} is invalid")
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str) and value.isascii() and value.isdigit():
        return int(value)
    raise PlatformAdapterError(f"St. Gallen Umantis {field} is invalid")


class StGallenCantonUmantisAdapter:
    platform_family = "CANTON_SG_PORTAL"

    def initial_listing_request(self, source: Source) -> FetchRequest:
        return FetchRequest(
            ST_GALLEN_LISTING,
            "text/html",
            "LISTING_PAGE",
            context={"page_number": 1, "surface_name": "unified"},
        )

    def parse_listing_page(
        self, page: FetchedPage, request: FetchRequest, source: Source
    ) -> ListingPage:
        if page.content_type != "text/html":
            raise PlatformAdapterError("St. Gallen Umantis listing must be HTML")
        parser = _StGallenListingParser()
        try:
            parser.feed(page.body.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise PlatformAdapterError("St. Gallen Umantis listing is not UTF-8") from exc
        if not parser.contract_seen or parser.page_state is None:
            raise PlatformAdapterError("St. Gallen Umantis listing contract is missing")
        state = parser.page_state
        expected_page = cast(int, request.context.get("page_number", 1))
        current = _umantis_page_integer(state.get("TableCurrentPage"), "current page")
        start = _umantis_page_integer(state.get("TableFrom"), "range start")
        end = _umantis_page_integer(state.get("TableTo"), "range end")
        total = _umantis_page_integer(state.get("TableTotalLines"), "total", allow_none=True)
        if current is None or start is None or end is None:
            raise PlatformAdapterError("St. Gallen Umantis pagination state is incomplete")
        prior_total = request.context.get("reported_total")
        if current != expected_page:
            raise PlatformAdapterError(
                "St. Gallen Umantis pagination did not advance monotonically"
            )
        if prior_total is not None and total != prior_total:
            raise PlatformAdapterError("St. Gallen Umantis total changed during pagination")
        stable_total = total if total is not None else prior_total
        if stable_total == 0 and not parser.entries:
            if expected_page != 1 or (start, end) not in {(0, 0), (1, 0)}:
                raise PlatformAdapterError("St. Gallen Umantis empty range is inconsistent")
        else:
            expected_start = (expected_page - 1) * ST_GALLEN_PAGE_SIZE + 1
            if start != expected_start or end != start + len(parser.entries) - 1:
                raise PlatformAdapterError("St. Gallen Umantis page range is inconsistent")
        if not parser.entries and stable_total != 0:
            raise PlatformAdapterError("St. Gallen Umantis pagination ended without entries")
        complete = isinstance(stable_total, int) and end == stable_total
        if isinstance(stable_total, int) and end > stable_total:
            raise PlatformAdapterError("St. Gallen Umantis page exceeded reported total")
        next_request: FetchRequest | None = None
        if not complete:
            next_link = state.get("NextLink")
            next_url = next_link.get("EnhancedUrl") if isinstance(next_link, dict) else None
            if not isinstance(next_url, str) or not next_url:
                raise PlatformAdapterError("St. Gallen Umantis lacks a next-page contract")
            decoded = html.unescape(next_url).split("#", 1)[0]
            if f"tc1152481=p{expected_page + 1}" not in decoded:
                raise PlatformAdapterError("St. Gallen Umantis next page skipped an offset")
            next_request = FetchRequest(
                urljoin(ST_GALLEN_LISTING, decoded),
                "text/html",
                "LISTING_PAGE",
                context={
                    "page_number": expected_page + 1,
                    "surface_name": "unified",
                    "reported_total": stable_total,
                },
            )
        return ListingPage(
            parser.entries,
            next_request,
            complete,
            cast(int | None, stable_total) if complete else None,
        )
    def detail_request(self, entry: ListingEntry, source: Source) -> FetchRequest:
        return FetchRequest(
            entry.detail_url,
            "text/html",
            "DETAIL",
            context={"surface_name": "unified"},
        )

    def parse_detail(
        self, page: FetchedPage, entry: ListingEntry, source: Source
    ) -> ParsedSourcePosting:
        match = _UMANTIS_DETAIL.fullmatch(urlsplit(page.final_url).path)
        if match is None or match.group("id") != entry.source_posting_id:
            raise PlatformAdapterError("St. Gallen Umantis detail identity mismatch")
        parser = _StGallenDetailParser()
        try:
            parser.feed(page.body.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise PlatformAdapterError("St. Gallen Umantis detail is not UTF-8") from exc
        if not parser.title or not parser.text:
            raise PlatformAdapterError("St. Gallen Umantis detail lacks title/body")
        if _normalized_title(parser.title) != _normalized_title(entry.title):
            raise PlatformAdapterError("St. Gallen Umantis detail title mismatch")
        organization = str(entry.listing_metadata.get("organization", ""))
        location = str(entry.listing_metadata.get("location", ""))
        employment_type = str(entry.listing_metadata.get("employment_type", ""))
        return ParsedSourcePosting(
            source_posting_id=entry.source_posting_id,
            canonical_url=page.final_url,
            title=parser.title,
            published_at_raw=None,
            date_posted=None,
            valid_through=None,
            employment_type=employment_type.removeprefix("| Art:").strip(),
            hiring_organization=organization,
            description_html=f"<p>{escape(parser.text)}</p>",
            responsibilities_html="",
            qualifications_html="",
            benefits_html="",
            raw_location=location,
            location_street="",
            location_locality=location,
            location_region="",
            location_postal_code="",
            location_country="CH",
            structured_payload={
                "source_format": "UMANTIS_PUBLIC_HTML_V1",
                "publication_id": entry.source_posting_id,
                "surface_name": "unified",
                "organization": organization,
                "location": location,
            },
            published_at_precision="UNKNOWN",
            published_at_parse_method="MISSING",
            contract_raw_text=parser.text,
        )


class _ThurgauListingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: list[ListingEntry] = []
        self.reported_total: int | None = None
        self.next_urls: set[str] = set()
        self.external_filter_seen = False
        self._option_capture = False
        self._entry: tuple[str, str, list[str]] | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "option" and values.get("value") == THURGAU_EXTERNAL_CATEGORY:
            self._option_capture = True
        if tag != "a":
            return
        href = values.get("href") or ""
        parsed = urlsplit(href)
        match = _TG_DETAIL.fullmatch(parsed.path)
        if parsed.hostname == "ohws.prospective.ch" and match is not None:
            self._entry = (match.group("id").lower(), href, [])
        page_match = re.search(r"/pjobpage/(\d+)(?:/|$)", parsed.path)
        if page_match is not None:
            self.next_urls.add(urljoin(THURGAU_LISTING, href))

    def handle_data(self, data: str) -> None:
        self._text.append(data)
        if self._entry is not None:
            self._entry[2].append(data)
        if getattr(self, "_option_capture", False):
            if THURGAU_EXTERNAL_LABEL in data:
                self.external_filter_seen = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "option":
            self._option_capture = False
        if tag != "a" or self._entry is None:
            return
        source_id, url, chunks = self._entry
        self._entry = None
        title = " ".join(" ".join(chunks).split())
        if not title:
            raise PlatformAdapterError("Thurgau listing entry lacks title")
        self.entries.append(ListingEntry(source_id, url, title))

    def close(self) -> None:
        super().close()
        text = " ".join(" ".join(self._text).split())
        match = re.search(r"Offene Stellen:\s*(\d+)", text, re.IGNORECASE)
        self.reported_total = int(match.group(1)) if match else None


def _entry_rows(entries: list[ListingEntry]) -> tuple[tuple[str, str, str], ...]:
    return tuple((entry.source_posting_id, entry.detail_url, entry.title) for entry in entries)


def _rows_entries(rows: object) -> list[ListingEntry]:
    if not isinstance(rows, tuple):
        raise PlatformAdapterError("Thurgau listing lost accumulated identity evidence")
    entries: list[ListingEntry] = []
    for row in rows:
        if not isinstance(row, tuple) or len(row) != 3 or not all(isinstance(v, str) for v in row):
            raise PlatformAdapterError("Thurgau accumulated entry is invalid")
        entries.append(ListingEntry(row[0], row[1], row[2], {"surface_name": "cantonal"}))
    return entries


class ThurgauCantonProspectiveAdapter:
    platform_family = "CANTON_TG_PORTAL"

    def initial_listing_request(self, source: Source) -> FetchRequest:
        return FetchRequest(
            THURGAU_LISTING,
            "text/html",
            "LISTING_INDEX",
            context={"phase": "cantonal", "page_number": 1, "surface_name": "cantonal"},
        )

    def _parse(self, page: FetchedPage) -> _ThurgauListingParser:
        if page.content_type != "text/html":
            raise PlatformAdapterError("Thurgau listing must be HTML")
        parser = _ThurgauListingParser()
        try:
            parser.feed(page.body.decode("utf-8"))
            parser.close()
        except UnicodeDecodeError as exc:
            raise PlatformAdapterError("Thurgau listing is not UTF-8") from exc
        if parser.reported_total is None:
            raise PlatformAdapterError("Thurgau listing lacks a reported total")
        return parser

    @staticmethod
    def _merge_entries(
        prior: list[ListingEntry], current: list[ListingEntry]
    ) -> list[ListingEntry]:
        merged: dict[str, ListingEntry] = {entry.source_posting_id: entry for entry in prior}
        for entry in current:
            previous = merged.get(entry.source_posting_id)
            if previous is not None and previous.detail_url != entry.detail_url:
                raise PlatformAdapterError("Thurgau pagination changed a detail identity")
            merged.setdefault(entry.source_posting_id, entry)
        return list(merged.values())

    def _next_page(
        self,
        parser: _ThurgauListingParser,
        *,
        page_number: int,
        phase: str,
        accumulated: list[ListingEntry],
        total: int,
        all_rows: tuple[tuple[str, str, str], ...] = (),
    ) -> FetchRequest | None:
        if len(accumulated) == total:
            return None
        candidates = [
            url
            for url in parser.next_urls
            if re.search(rf"/pjobpage/{page_number + 1}(?:/|$)", urlsplit(url).path)
        ]
        if len(candidates) != 1:
            raise PlatformAdapterError("Thurgau pagination lacks one monotonic next page")
        return FetchRequest(
            candidates[0],
            "text/html",
            "LISTING_PAGE",
            context={
                "phase": phase,
                "page_number": page_number + 1,
                "surface_name": phase,
                "reported_total": total,
                "accumulated": _entry_rows(accumulated),
                "all_rows": all_rows,
            },
        )

    def parse_listing_page(
        self, page: FetchedPage, request: FetchRequest, source: Source
    ) -> ListingPage:
        parser = self._parse(page)
        phase = cast(str, request.context.get("phase", "cantonal"))
        page_number = cast(int, request.context.get("page_number", 1))
        prior_total = request.context.get("reported_total")
        if prior_total is not None and parser.reported_total != prior_total:
            raise PlatformAdapterError("Thurgau surface total changed during pagination")
        prior = _rows_entries(request.context.get("accumulated", ()))
        accumulated = self._merge_entries(prior, parser.entries)
        reported_total = parser.reported_total
        if reported_total is None:  # Narrowed by _parse; retained as fail-closed defence.
            raise PlatformAdapterError("Thurgau listing lacks a reported total")
        if len(accumulated) > reported_total:
            raise PlatformAdapterError("Thurgau surface exceeded its reported total")
        all_rows = cast(tuple[tuple[str, str, str], ...], request.context.get("all_rows", ()))
        next_page = self._next_page(
            parser,
            page_number=page_number,
            phase=phase,
            accumulated=accumulated,
            total=reported_total,
            all_rows=all_rows,
        )
        if next_page is not None:
            return ListingPage([], next_page, False)
        if phase == "cantonal":
            if not parser.external_filter_seen:
                raise PlatformAdapterError("Thurgau external-employer filter contract is missing")
            external_request = FetchRequest(
                THURGAU_LISTING,
                "text/html",
                "LISTING_PAGE",
                method="POST",
                form_data=(
                    ("prospectivejobSearchParams.searchQuery", ""),
                    ("prospectivejobSearchParams.dynamic_group.4", THURGAU_EXTERNAL_CATEGORY),
                    ("prospectivejobSearchParams.dynamic_group.3", "-1"),
                ),
                context={
                    "phase": "separate_employers",
                    "page_number": 1,
                    "surface_name": "separate_employers",
                    "all_rows": _entry_rows(accumulated),
                },
            )
            return ListingPage([], external_request, False)
        all_entries = _rows_entries(all_rows)
        external_ids = {entry.source_posting_id for entry in accumulated}
        all_ids = {entry.source_posting_id for entry in all_entries}
        if not external_ids <= all_ids:
            raise PlatformAdapterError("Thurgau external-employer surface escaped unified listing")
        included = [entry for entry in all_entries if entry.source_posting_id not in external_ids]
        return ListingPage(included, None, True, len(included))

    def detail_request(self, entry: ListingEntry, source: Source) -> FetchRequest:
        return FetchRequest(
            entry.detail_url,
            "text/html",
            "DETAIL",
            context={"surface_name": "cantonal"},
        )

    def parse_detail(
        self, page: FetchedPage, entry: ListingEntry, source: Source
    ) -> ParsedSourcePosting:
        match = _TG_DETAIL.fullmatch(urlsplit(page.final_url).path)
        if match is None or match.group("id").lower() != entry.source_posting_id:
            raise PlatformAdapterError("Thurgau Prospective detail identity mismatch")
        return _parse_new_json_ld_detail(
            page,
            entry,
            source_format="PROSPECTIVE_PUBLIC_JOBPOSTING_V1",
        )
