from __future__ import annotations

import json
import re
from datetime import date
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from collectors.platforms import (
    FetchedPage,
    FetchRequest,
    ListingEntry,
    ListingPage,
    ParsedSourcePosting,
    PlatformAdapter,
    PlatformAdapterError,
    UnsupportedPlatformError,
)
from sources.models import Source

ZURICH_API = "https://www.stadt-zuerich.ch/stzh/jobsearch"
ZURICH_BASE = "https://www.stadt-zuerich.ch"
ZURICH_COMPONENT = (
    "/content/web/de/politik-und-verwaltung/arbeiten-bei-der-stadt/jobs/"
    "jcr:content/mainparsys/jobsearch"
)
ZURICH_PAGE_SIZE = 50
_ZURICH_DETAIL_ID = re.compile(r"job-detailseite\.(?P<id>\d+)\.html$")
_GERMAN_MONTHS = {
    "januar": 1,
    "februar": 2,
    "maerz": 3,
    "märz": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "dezember": 12,
}


class RexxAdapter:
    platform_family = "REXX_SYSTEMS"

    def initial_listing_request(self, source: Source) -> FetchRequest:
        from collectors.winterthur import WINTERTHUR_LISTING_URL

        return FetchRequest(WINTERTHUR_LISTING_URL, "text/html", "LISTING")

    def parse_listing_page(
        self, page: FetchedPage, request: FetchRequest, source: Source
    ) -> ListingPage:
        from collectors.winterthur import parse_listing

        entries = [
            ListingEntry(
                item.source_posting_id,
                item.url,
                item.title,
            )
            for item in parse_listing(page.body)
        ]
        return ListingPage(entries, None, True)

    def detail_request(self, entry: ListingEntry, source: Source) -> FetchRequest:
        return FetchRequest(entry.detail_url, "text/html", "DETAIL")

    def parse_detail(
        self, page: FetchedPage, entry: ListingEntry, source: Source
    ) -> ParsedSourcePosting:
        from collectors.winterthur import parse_detail

        parsed = parse_detail(
            page.body,
            requested_url=page.final_url,
            expected_posting_id=entry.source_posting_id,
        )
        values = dict(parsed.__dict__)
        values["published_at_precision"] = "EXACT_DATE" if parsed.published_at_raw else "UNKNOWN"
        values["published_at_parse_method"] = (
            "STRUCTURED_DATA" if parsed.published_at_raw else "MISSING"
        )
        return ParsedSourcePosting(**values)


def _zurich_request(offset: int) -> FetchRequest:
    query = urlencode(
        {
            "lang": "de",
            "limit": ZURICH_PAGE_SIZE,
            "offset": offset,
            "compResource": ZURICH_COMPONENT,
        }
    )
    return FetchRequest(f"{ZURICH_API}?{query}", "application/json", "LISTING_PAGE")


def _german_date(value: str) -> date | None:
    match = re.fullmatch(r"\s*(\d{1,2})\.\s+([^\s]+)\s+(\d{4})\s*", value)
    if not match:
        return None
    month = _GERMAN_MONTHS.get(match.group(2).casefold())
    return date(int(match.group(3)), month, int(match.group(1))) if month else None


class _ZurichDetailParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.canonical_url = ""
        self.title = ""
        self.leads: list[str] = []
        self.sections: dict[str, list[str]] = {}
        self.successfactors_requisition_id = ""
        self._capture: str | None = None
        self._chunks: list[str] = []
        self._section = "description"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "link" and values.get("rel") == "canonical":
            self.canonical_url = values.get("href") or ""
        if tag == "stzh-heading" and values.get("slot") == "heading":
            self._capture, self._chunks = "title", []
        elif tag == "stzh-text" and values.get("slot") == "lead":
            self._capture, self._chunks = "lead", []
        elif tag == "h2":
            self._capture, self._chunks = "section", []
        elif tag in {"p", "li"}:
            self._capture, self._chunks = "text", []
        href = values.get("href") or ""
        if "career_job_req_id=" in href:
            self.successfactors_requisition_id = parse_qs(urlsplit(href).query).get(
                "career_job_req_id", [""]
            )[0]

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        expected = {"title": "stzh-heading", "lead": "stzh-text", "section": "h2", "text": tag}
        if not self._capture or expected.get(self._capture) != tag:
            return
        value = " ".join("".join(self._chunks).split())
        if self._capture == "title" and not self.title:
            self.title = value
        elif self._capture == "lead" and value:
            self.leads.append(value)
        elif self._capture == "section":
            self._section = value.casefold()
        elif self._capture == "text" and value:
            self.sections.setdefault(self._section, []).append(value)
        self._capture, self._chunks = None, []


class ZurichCitySuccessFactorsLinkedAdapter:
    platform_family = "CITY_SITE_SUCCESSFACTORS_LINKED"

    def initial_listing_request(self, source: Source) -> FetchRequest:
        return _zurich_request(0)

    def parse_listing_page(
        self, page: FetchedPage, request: FetchRequest, source: Source
    ) -> ListingPage:
        if page.content_type != "application/json":
            raise PlatformAdapterError(f"Zürich listing expected JSON, found {page.content_type!r}")
        try:
            payload = json.loads(page.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PlatformAdapterError("Zürich listing contains invalid JSON") from exc
        total = payload.get("meta", {}).get("total")
        results = payload.get("results")
        if not isinstance(total, int) or total < 0 or not isinstance(results, list):
            raise PlatformAdapterError("Zürich listing lacks a valid total/results contract")
        offset = int(parse_qs(urlsplit(request.url).query).get("offset", ["0"])[0])
        entries: list[ListingEntry] = []
        for item in results:
            if not isinstance(item, dict):
                raise PlatformAdapterError("Zürich listing result must be an object")
            href = item.get("href")
            heading = item.get("heading")
            if not isinstance(href, str) or not isinstance(heading, str):
                raise PlatformAdapterError("Zürich listing result lacks href/heading")
            detail_url = urljoin(ZURICH_BASE, href)
            match = _ZURICH_DETAIL_ID.search(urlsplit(detail_url).path)
            if not match:
                raise PlatformAdapterError(f"Zürich detail URL lacks stable city ID: {detail_url}")
            entries.append(
                ListingEntry(
                    match.group("id"),
                    detail_url,
                    heading,
                    {"meta": item.get("meta", []), "listing_offset": offset},
                )
            )
        consumed = offset + len(entries)
        if consumed < total and not entries:
            raise PlatformAdapterError("Zürich pagination ended before reported total")
        next_request = _zurich_request(consumed) if consumed < total else None
        return ListingPage(entries, next_request, next_request is None, total)

    def detail_request(self, entry: ListingEntry, source: Source) -> FetchRequest:
        return FetchRequest(entry.detail_url, "text/html", "DETAIL")

    def parse_detail(
        self, page: FetchedPage, entry: ListingEntry, source: Source
    ) -> ParsedSourcePosting:
        parser = _ZurichDetailParser()
        parser.feed(page.body.decode("utf-8"))
        canonical = parser.canonical_url or page.final_url
        match = _ZURICH_DETAIL_ID.search(urlsplit(canonical).path)
        if not match or match.group("id") != entry.source_posting_id:
            raise PlatformAdapterError("Zürich canonical detail ID does not match listing ID")
        title = parser.title or entry.title
        if not title:
            raise PlatformAdapterError("Zürich detail title is missing")
        meta = entry.listing_metadata.get("meta", [])
        meta_values = [str(value) for value in meta] if isinstance(meta, list) else []
        organization = (
            meta_values[0] if meta_values else (parser.leads[1] if len(parser.leads) > 1 else "")
        )
        published_raw = meta_values[1] if len(meta_values) > 1 else None
        posted = _german_date(published_raw) if published_raw else None
        description = "\n".join(parser.sections.get("description", []))
        responsibilities = "\n".join(parser.sections.get("aufgaben", []))
        qualifications = "\n".join(parser.sections.get("profil", []))
        benefits = "\n".join(parser.sections.get("wir bieten", []))
        structured: dict[str, object] = {
            "source_format": "STADT_ZURICH_AEM_JOB_DETAIL_V1",
            "city_detail_id": entry.source_posting_id,
            "successfactors_requisition_id": parser.successfactors_requisition_id,
            "listing_metadata": entry.listing_metadata,
            "title": title,
            "hiringOrganization": organization,
            "description": description,
            "responsibilities": responsibilities,
            "qualifications": qualifications,
            "benefits": benefits,
        }
        return ParsedSourcePosting(
            source_posting_id=entry.source_posting_id,
            canonical_url=canonical,
            title=title,
            published_at_raw=published_raw,
            date_posted=posted,
            valid_through=None,
            employment_type=parser.leads[0] if parser.leads else "",
            hiring_organization=organization,
            description_html=description,
            responsibilities_html=responsibilities,
            qualifications_html=qualifications,
            benefits_html=benefits,
            raw_location="",
            location_street="",
            location_locality="",
            location_region="",
            location_postal_code="",
            location_country="CH",
            structured_payload=structured,
            published_at_precision="EXACT_DATE" if posted else "UNKNOWN",
            published_at_parse_method="STRUCTURED_DATA" if posted else "MISSING",
        )


_ADAPTERS: dict[str, PlatformAdapter] = {
    "REXX_SYSTEMS": RexxAdapter(),
    "CITY_SITE_SUCCESSFACTORS_LINKED": ZurichCitySuccessFactorsLinkedAdapter(),
}


def get_adapter(source: Source) -> PlatformAdapter:
    try:
        return _ADAPTERS[source.platform_family]
    except KeyError as exc:
        raise UnsupportedPlatformError(
            f"no adapter is registered for platform family {source.platform_family!r}"
        ) from exc
