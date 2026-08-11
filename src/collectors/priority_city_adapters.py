from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from html import unescape
from html.parser import HTMLParser
from typing import cast
from urllib.parse import urlencode, urlsplit

from collectors.platforms import (
    FetchedPage,
    FetchRequest,
    ListingEntry,
    ListingPage,
    ParsedSourcePosting,
    PlatformAdapterError,
)
from sources.models import Source

BERN_API = "https://jobs.bern.ch/public/v1/medium/1840/jobs"
BERN_PAGE_SIZE = 96
LUZERN_LISTING = "https://job.stadtluzern.ch/stellen/stadtluzern/?lang=de"
SCHAFFHAUSEN_API = (
    "https://jobs.stadt-schaffhausen.ch/wp-json/wp/v2/jobs?per_page=100&_fields=id,slug,link,title"
)
SCHAFFHAUSEN_LISTING = "https://jobs.stadt-schaffhausen.ch/freie-stellen/"


def _text(value: object) -> str:
    return unescape(value) if isinstance(value, str) else ""


def _iso_datetime(value: object) -> datetime | None:
    raw = _text(value).strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _source_date(value: object) -> date | None:
    raw = _text(value).strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        pass
    match = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", raw)
    return date(int(match.group(3)), int(match.group(2)), int(match.group(1))) if match else None


def _job_posting(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        kind = value.get("@type")
        if kind == "JobPosting" or isinstance(kind, list) and "JobPosting" in kind:
            return value
        for child in value.values():
            found = _job_posting(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _job_posting(child)
            if found is not None:
                return found
    return None


def _load_json_ld(raw: str) -> tuple[object, bool]:
    try:
        return json.loads(raw), False
    except json.JSONDecodeError as original_error:
        match = re.search(
            r'("description"\s*:\s*")(.*?)(",\s*"hiringOrganization"\s*:)',
            raw,
            flags=re.DOTALL,
        )
        if match is None:
            raise PlatformAdapterError("detail contains malformed JSON-LD") from original_error
        description = re.sub(r'(?<!\\)"', r'\\"', match.group(2))
        repaired = raw[: match.start(2)] + description + raw[match.end(2) :]
        try:
            return json.loads(repaired), True
        except json.JSONDecodeError as repaired_error:
            raise PlatformAdapterError("detail contains malformed JSON-LD") from repaired_error


class _JobPostingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.canonical_url = ""
        self.payloads: list[object] = []
        self.description_repaired = False
        self._script = False
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "link" and "canonical" in (values.get("rel") or "").split():
            self.canonical_url = values.get("href") or ""
        if tag == "script" and (values.get("type") or "").casefold() == "application/ld+json":
            self._script = True
            self._chunks = []

    def handle_data(self, data: str) -> None:
        if self._script:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "script" or not self._script:
            return
        self._script = False
        payload, repaired = _load_json_ld("".join(self._chunks))
        self.payloads.append(payload)
        self.description_repaired = self.description_repaired or repaired

    @property
    def posting(self) -> dict[str, object]:
        for payload in self.payloads:
            found = _job_posting(payload)
            if found is not None:
                return found
        raise PlatformAdapterError("detail lacks JobPosting JSON-LD")


def _address(posting: dict[str, object]) -> dict[str, object]:
    location = posting.get("jobLocation")
    if isinstance(location, list):
        location = location[0] if location else None
    if not isinstance(location, dict):
        return {}
    address = location.get("address")
    return address if isinstance(address, dict) else {}


def _organization(posting: dict[str, object]) -> str:
    organization = posting.get("hiringOrganization")
    return _text(organization.get("name")) if isinstance(organization, dict) else ""


def _normalized_title(value: str) -> str:
    quote_equivalents = str.maketrans({"«": '"', "»": '"', "“": '"', "”": '"', "„": '"'})
    return " ".join(value.translate(quote_equivalents).split()).casefold()


def _parsed_from_json_ld(
    *,
    page: FetchedPage,
    entry: ListingEntry,
    published_raw: str | None = None,
    source_published_at: datetime | None = None,
    source_updated_at: datetime | None = None,
    parse_method: str = "STRUCTURED_DATA",
    extra_payload: dict[str, object] | None = None,
) -> ParsedSourcePosting:
    parser = _JobPostingParser()
    try:
        parser.feed(page.body.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise PlatformAdapterError("detail is not UTF-8") from exc
    posting = parser.posting
    title = re.sub(r"<br\s*/?>", " ", _text(posting.get("title")), flags=re.IGNORECASE)
    title = " ".join(title.split()) or entry.title
    if not title:
        raise PlatformAdapterError("detail title is missing")
    normalized_title = _normalized_title(title)
    normalized_listing_title = _normalized_title(entry.title)
    if entry.title and not (
        normalized_title == normalized_listing_title
        or normalized_title.startswith(f"{normalized_listing_title} - ")
    ):
        raise PlatformAdapterError("detail title does not match listing title")
    canonical = parser.canonical_url or page.final_url
    if urlsplit(canonical).hostname != urlsplit(entry.detail_url).hostname:
        raise PlatformAdapterError("detail canonical host does not match listing")
    address = _address(posting)
    raw_date = published_raw or _text(posting.get("datePosted")) or None
    posted_date = source_published_at.date() if source_published_at else _source_date(raw_date)
    valid_through = _source_date(posting.get("validThrough"))
    structured = {
        **posting,
        "json_ld_description_repaired": parser.description_repaired,
    }
    if extra_payload:
        structured = {
            "job_posting": posting,
            "json_ld_description_repaired": parser.description_repaired,
            **extra_payload,
        }
    location_parts = [
        _text(address.get("streetAddress")),
        _text(address.get("postalCode")),
        _text(address.get("addressLocality")),
    ]
    return ParsedSourcePosting(
        source_posting_id=entry.source_posting_id,
        canonical_url=canonical,
        title=title,
        published_at_raw=raw_date,
        date_posted=posted_date,
        valid_through=valid_through,
        employment_type=_text(posting.get("employmentType")),
        hiring_organization=_organization(posting),
        description_html=_text(posting.get("description")),
        responsibilities_html=_text(posting.get("responsibilities")),
        qualifications_html=_text(posting.get("qualifications")),
        benefits_html=_text(posting.get("jobBenefits")) or _text(posting.get("benefits")),
        raw_location=", ".join(part for part in location_parts if part),
        location_street=_text(address.get("streetAddress")),
        location_locality=_text(address.get("addressLocality")),
        location_region=_text(address.get("addressRegion")),
        location_postal_code=_text(address.get("postalCode")),
        location_country=_text(address.get("addressCountry")) or "CH",
        structured_payload=structured,
        source_published_at=source_published_at,
        source_updated_at=source_updated_at,
        published_at_precision=(
            "EXACT_DATETIME" if source_published_at else "EXACT_DATE" if posted_date else "UNKNOWN"
        ),
        published_at_parse_method=parse_method if posted_date else "MISSING",
    )


class _ProspectiveAdapterBase:
    vendor_family = "PROSPECTIVE"

    def detail_request(self, entry: ListingEntry, source: Source) -> FetchRequest:
        return FetchRequest(entry.detail_url, "text/html", "DETAIL")


def _bern_request(offset: int) -> FetchRequest:
    query = urlencode({"lang": "de", "offset": offset, "limit": BERN_PAGE_SIZE})
    return FetchRequest(
        f"{BERN_API}?{query}",
        "application/json",
        "LISTING_PAGE",
        context={"offset": offset},
    )


class BernProspectiveApiAdapter(_ProspectiveAdapterBase):
    platform_family = "JOBS_BERN_CH"

    def initial_listing_request(self, source: Source) -> FetchRequest:
        return _bern_request(0)

    def parse_listing_page(
        self, page: FetchedPage, request: FetchRequest, source: Source
    ) -> ListingPage:
        if page.content_type != "application/json":
            raise PlatformAdapterError("Bern listing must be JSON")
        try:
            payload = json.loads(page.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PlatformAdapterError("Bern listing contains invalid JSON") from exc
        if not isinstance(payload, dict):
            raise PlatformAdapterError("Bern listing root must be an object")
        total, jobs = payload.get("total"), payload.get("jobs")
        if not isinstance(total, int) or total < 0 or not isinstance(jobs, list):
            raise PlatformAdapterError("Bern listing lacks total/jobs")
        offset = cast(int, request.context.get("offset", 0))
        entries: list[ListingEntry] = []
        for item in jobs:
            if not isinstance(item, dict):
                raise PlatformAdapterError("Bern job must be an object")
            source_id = str(item.get("id", "")).strip()
            links = item.get("links")
            direct = _text(links.get("directlink")) if isinstance(links, dict) else ""
            title = _text(item.get("title"))
            if not source_id or not direct or not title:
                raise PlatformAdapterError("Bern job lacks id/directlink/title")
            if urlsplit(direct).hostname != "jobs.bern.ch":
                raise PlatformAdapterError("Bern direct link is outside the verified host")
            entries.append(ListingEntry(source_id, direct, title, {"api_job": item}))
        consumed = offset + len(entries)
        if consumed < total and not entries:
            raise PlatformAdapterError("Bern pagination ended before the reported total")
        next_request = _bern_request(consumed) if consumed < total else None
        return ListingPage(entries, next_request, next_request is None, total)

    def parse_detail(
        self, page: FetchedPage, entry: ListingEntry, source: Source
    ) -> ParsedSourcePosting:
        item = entry.listing_metadata.get("api_job")
        if not isinstance(item, dict):
            raise PlatformAdapterError("Bern detail lacks API listing provenance")
        return _parsed_from_json_ld(
            page=page,
            entry=entry,
            published_raw=_text(item.get("start_date")) or None,
            source_published_at=_iso_datetime(item.get("start_date")),
            source_updated_at=_iso_datetime(item.get("last_modification_timestamp")),
            parse_method="SOURCE_FIELD",
            extra_payload={"listing_api": item, "source_format": "PROSPECTIVE_PUBLIC_V1"},
        )


class _LuzernListingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: list[ListingEntry] = []
        self.next_offset: int | None = None
        self._entry: dict[str, str] | None = None
        self._title_chunks: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "a" and (values.get("id") or "").startswith("job-"):
            self._entry = {
                "id": (values.get("id") or "")[4:],
                "url": values.get("href") or "",
                "title": values.get("title") or "",
            }
        if tag == "h3" and self._entry is not None:
            self._in_title, self._title_chunks = True, []
        if tag == "a" and values.get("id") == "button-forward":
            classes = (values.get("class") or "").split()
            match = re.search(r"sendPagination\((\d+)\)", values.get("onclick") or "")
            if "disableClick" not in classes and match:
                self.next_offset = int(match.group(1))

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "h3" and self._entry is not None:
            title = " ".join("".join(self._title_chunks).split()) or self._entry["title"]
            if not self._entry["id"] or not self._entry["url"] or not title:
                raise PlatformAdapterError("Luzern listing entry is incomplete")
            self.entries.append(ListingEntry(self._entry["id"], self._entry["url"], title))
            self._in_title = False
        if tag == "a" and self._entry is not None and not self._in_title:
            self._entry = None


def _luzern_request(offset: int) -> FetchRequest:
    if offset == 0:
        return FetchRequest(LUZERN_LISTING, "text/html", "LISTING_PAGE", context={"offset": 0})
    fields: list[tuple[str, str]] = [
        ("query", ""),
        ("workload", "10,100"),
        ("offset", str(offset)),
    ]
    return FetchRequest(
        LUZERN_LISTING,
        "text/html",
        "LISTING_PAGE",
        method="POST",
        form_data=tuple(fields),
        context={"offset": offset},
    )


class LuzernProspectiveLegacyAdapter(_ProspectiveAdapterBase):
    platform_family = "CITY_LUZERN_PORTAL"

    def initial_listing_request(self, source: Source) -> FetchRequest:
        return _luzern_request(0)

    def parse_listing_page(
        self, page: FetchedPage, request: FetchRequest, source: Source
    ) -> ListingPage:
        parser = _LuzernListingParser()
        try:
            parser.feed(page.body.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise PlatformAdapterError("Luzern listing is not UTF-8") from exc
        if parser.next_offset is not None and parser.next_offset <= cast(
            int, request.context.get("offset", 0)
        ):
            raise PlatformAdapterError("Luzern pagination did not advance")
        next_request = (
            _luzern_request(parser.next_offset) if parser.next_offset is not None else None
        )
        return ListingPage(parser.entries, next_request, next_request is None)

    def parse_detail(
        self, page: FetchedPage, entry: ListingEntry, source: Source
    ) -> ParsedSourcePosting:
        return _parsed_from_json_ld(page=page, entry=entry)


def _schaffhausen_id(url: str) -> str:
    match = re.search(r"/Vacancies/(\d+)/", url, re.IGNORECASE)
    if match:
        return match.group(1)
    numbers = re.findall(r"(?:^|-)(\d{4,})(?=-|/|$)", urlsplit(url).path)
    return numbers[-1] if numbers else ""


def _parsed_from_wp_record(page: FetchedPage, entry: ListingEntry) -> ParsedSourcePosting:
    try:
        payload = json.loads(page.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PlatformAdapterError("Schaffhausen REST detail contains invalid JSON") from exc
    if not isinstance(payload, dict):
        raise PlatformAdapterError("Schaffhausen REST detail root must be an object")
    if _schaffhausen_id(_text(payload.get("slug"))) != entry.source_posting_id:
        raise PlatformAdapterError("Schaffhausen REST detail identity mismatch")
    title_value = payload.get("title")
    title = _text(title_value.get("rendered")) if isinstance(title_value, dict) else ""
    if not title or " ".join(title.split()).casefold() != " ".join(entry.title.split()).casefold():
        raise PlatformAdapterError("Schaffhausen REST detail title mismatch")
    canonical = _text(payload.get("link"))
    if canonical != entry.detail_url:
        raise PlatformAdapterError("Schaffhausen REST detail canonical mismatch")
    excerpt_value = payload.get("excerpt")
    excerpt = _text(excerpt_value.get("rendered")) if isinstance(excerpt_value, dict) else ""
    published_raw = _text(payload.get("date")) or None
    published_at = _iso_datetime(payload.get("date"))
    updated_at = _iso_datetime(payload.get("modified"))
    return ParsedSourcePosting(
        source_posting_id=entry.source_posting_id,
        canonical_url=canonical,
        title=title,
        published_at_raw=published_raw,
        date_posted=published_at.date() if published_at else None,
        valid_through=None,
        employment_type="",
        hiring_organization="",
        description_html=excerpt,
        responsibilities_html="",
        qualifications_html="",
        benefits_html="",
        raw_location="",
        location_street="",
        location_locality="",
        location_region="",
        location_postal_code="",
        location_country="CH",
        structured_payload={"wp_rest_job": payload, "listing_provenance": entry.listing_metadata},
        source_published_at=published_at,
        source_updated_at=updated_at,
        published_at_precision="EXACT_DATETIME" if published_at else "UNKNOWN",
        published_at_parse_method="SOURCE_FIELD" if published_at else "MISSING",
    )


class _SchaffhausenListingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.raw_entries: list[tuple[str, str]] = []
        self.next_url: str | None = None
        self.text: list[str] = []
        self._url = ""
        self._capture = False
        self._in_title = False
        self._title = ""
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = (values.get("class") or "").split()
        if tag == "a" and "job-post" in classes:
            self._url, self._capture, self._title = values.get("href") or "", True, ""
        if tag == "h2" and self._capture:
            self._in_title, self._chunks = True, []
        if tag == "br" and self._in_title:
            self._title = " ".join("".join(self._chunks).split())
            self._in_title = False
        if tag == "a" and "next" in classes and "page-numbers" in classes:
            self.next_url = values.get("href") or None

    def handle_data(self, data: str) -> None:
        self.text.append(data)
        if self._in_title:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2" and self._in_title:
            self._title = " ".join("".join(self._chunks).split())
            self._in_title = False
        if tag == "a" and self._capture:
            self.raw_entries.append((self._url, self._title))
            self._url, self._capture, self._title = "", False, ""


class SchaffhausenUmantisLinkedAdapter:
    platform_family = "UMANTIS_LINKED"

    def initial_listing_request(self, source: Source) -> FetchRequest:
        return FetchRequest(SCHAFFHAUSEN_API, "application/json", "LISTING_INDEX")

    def parse_listing_page(
        self, page: FetchedPage, request: FetchRequest, source: Source
    ) -> ListingPage:
        if request.role == "LISTING_INDEX":
            try:
                payload = json.loads(page.body)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise PlatformAdapterError("Schaffhausen index contains invalid JSON") from exc
            if not isinstance(payload, list):
                raise PlatformAdapterError("Schaffhausen index root must be a list")
            local_links: dict[str, dict[str, str]] = {}
            for item in payload:
                if not isinstance(item, dict):
                    raise PlatformAdapterError("Schaffhausen index item must be an object")
                link = _text(item.get("link"))
                source_id = _schaffhausen_id(_text(item.get("slug"))) or _schaffhausen_id(link)
                wp_id = item.get("id")
                if not source_id or not link or not isinstance(wp_id, int):
                    continue
                record = {
                    "link": link,
                    "api_url": f"https://jobs.stadt-schaffhausen.ch/wp-json/wp/v2/jobs/{wp_id}",
                }
                previous = local_links.get(source_id)
                if previous and previous != record:
                    raise PlatformAdapterError("Schaffhausen index has conflicting local mirrors")
                local_links[source_id] = record
            return ListingPage(
                [],
                FetchRequest(
                    SCHAFFHAUSEN_LISTING,
                    "text/html",
                    "LISTING_PAGE",
                    context={"local_links": local_links},
                ),
                False,
            )
        parser = _SchaffhausenListingParser()
        try:
            parser.feed(page.body.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise PlatformAdapterError("Schaffhausen listing is not UTF-8") from exc
        links = request.context.get("local_links", {})
        if not isinstance(links, dict):
            raise PlatformAdapterError("Schaffhausen listing lost its mirror index")
        entries: list[ListingEntry] = []
        for original_url, title in parser.raw_entries:
            source_id = _schaffhausen_id(original_url)
            if not source_id or not title:
                raise PlatformAdapterError("Schaffhausen listing entry lacks stable identity")
            detail_url = original_url
            detail_api_url = ""
            if urlsplit(original_url).hostname != "jobs.stadt-schaffhausen.ch":
                mirror = links.get(source_id)
                if not isinstance(mirror, dict):
                    raise PlatformAdapterError(
                        f"Schaffhausen external vacancy {source_id} lacks a local mirror"
                    )
                detail_url = _text(mirror.get("link"))
                detail_api_url = _text(mirror.get("api_url"))
                if not detail_url or not detail_api_url:
                    raise PlatformAdapterError(
                        f"Schaffhausen external vacancy {source_id} lacks REST evidence"
                    )
            entries.append(
                ListingEntry(
                    source_id,
                    detail_url,
                    title,
                    {
                        "observed_listing_url": original_url,
                        "local_mirror_url": detail_url,
                        "detail_api_url": detail_api_url,
                    },
                )
            )
        all_text = " ".join(" ".join(parser.text).split())
        total_match = re.search(r"Inserate:\s*(\d+)", all_text)
        if not total_match:
            raise PlatformAdapterError("Schaffhausen listing lacks reported total")
        total = int(total_match.group(1))
        next_request = None
        if parser.next_url:
            next_request = FetchRequest(
                parser.next_url,
                "text/html",
                "LISTING_PAGE",
                context={"local_links": links},
            )
        return ListingPage(entries, next_request, next_request is None, total)

    def detail_request(self, entry: ListingEntry, source: Source) -> FetchRequest:
        api_url = entry.listing_metadata.get("detail_api_url")
        if isinstance(api_url, str) and api_url:
            return FetchRequest(api_url, "application/json", "DETAIL")
        return FetchRequest(entry.detail_url, "text/html", "DETAIL")

    def parse_detail(
        self, page: FetchedPage, entry: ListingEntry, source: Source
    ) -> ParsedSourcePosting:
        if page.content_type == "application/json":
            return _parsed_from_wp_record(page, entry)
        if entry.source_posting_id not in urlsplit(page.final_url).path:
            raise PlatformAdapterError("Schaffhausen detail URL does not retain vacancy ID")
        return _parsed_from_json_ld(
            page=page,
            entry=entry,
            extra_payload={
                "source_format": "STADT_SCHAFFHAUSEN_WORDPRESS_UMANTIS_LINKED_V1",
                "listing_provenance": entry.listing_metadata,
            },
        )
