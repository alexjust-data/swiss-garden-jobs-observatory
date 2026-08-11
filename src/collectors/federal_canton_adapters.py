from __future__ import annotations

import json
import re
from html import escape, unescape
from html.parser import HTMLParser
from typing import cast
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from collectors.platforms import (
    FetchedPage,
    FetchRequest,
    ListingEntry,
    ListingPage,
    ParsedSourcePosting,
    PlatformAdapterError,
)
from collectors.priority_city_adapters import _iso_datetime, _parsed_from_json_ld, _text
from sources.models import Source

FEDERAL_API = "https://ohws.prospective.ch/public/v1/medium/1000624/jobs"
FEDERAL_FEED_CAPACITY = 1000

BASEL_STADT_SURFACES = (
    ("ordinary", "https://stellenmarkt.bs.ch/kbs/"),
    ("apprenticeships", "https://stellenmarkt.bs.ch/kbs/lehrstellen/"),
)


def _federal_request(offset: int) -> FetchRequest:
    query = urlencode({"lang": "de", "offset": offset, "limit": FEDERAL_FEED_CAPACITY})
    return FetchRequest(
        f"{FEDERAL_API}?{query}",
        "application/json",
        "LISTING_PAGE",
        context={"offset": offset, "surface_name": "unified"},
    )


class FederalProspectiveAdapter:
    platform_family = "FEDERAL_JOB_PORTAL"

    def initial_listing_request(self, source: Source) -> FetchRequest:
        return _federal_request(0)

    def parse_listing_page(
        self, page: FetchedPage, request: FetchRequest, source: Source
    ) -> ListingPage:
        if page.content_type != "application/json":
            raise PlatformAdapterError("Federal listing must be JSON")
        try:
            payload = json.loads(page.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PlatformAdapterError("Federal listing contains invalid JSON") from exc
        if not isinstance(payload, dict):
            raise PlatformAdapterError("Federal listing root must be an object")
        total, jobs = payload.get("total"), payload.get("jobs")
        if not isinstance(total, int) or total < 0 or not isinstance(jobs, list):
            raise PlatformAdapterError("Federal listing lacks total/jobs")
        offset = cast(int, request.context.get("offset", 0))
        returned_offset = payload.get("offset")
        if returned_offset != offset:
            raise PlatformAdapterError("Federal listing offset did not match the request")
        entries: list[ListingEntry] = []
        for item in jobs:
            if not isinstance(item, dict):
                raise PlatformAdapterError("Federal job must be an object")
            source_id = str(item.get("id", "")).strip()
            links = item.get("links")
            direct = _text(links.get("directlink")) if isinstance(links, dict) else ""
            title = _text(item.get("title"))
            if not source_id or not direct or not title:
                raise PlatformAdapterError("Federal job lacks id/directlink/title")
            if urlsplit(direct).hostname != "jobs.admin.ch":
                raise PlatformAdapterError("Federal direct link is outside the verified host")
            entries.append(
                ListingEntry(
                    source_id,
                    direct,
                    title,
                    {"api_job": item, "surface_name": "unified"},
                )
            )
        if offset != 0:
            raise PlatformAdapterError("Federal discovery does not authorize unstable offsets")
        if len(entries) != total:
            raise PlatformAdapterError(
                "Federal complete feed did not equal its reported total; capacity review required"
            )
        return ListingPage(entries, None, True, total)

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
        item = entry.listing_metadata.get("api_job")
        if not isinstance(item, dict):
            raise PlatformAdapterError("Federal detail lacks API listing provenance")
        return _parsed_from_json_ld(
            page=page,
            entry=entry,
            published_raw=_text(item.get("start_date")) or None,
            source_published_at=_iso_datetime(item.get("start_date")),
            source_updated_at=_iso_datetime(item.get("last_modification_timestamp")),
            parse_method="SOURCE_FIELD",
            extra_payload={
                "listing_api": item,
                "source_format": "PROSPECTIVE_PUBLIC_V1",
                "surface_name": "unified",
            },
        )


class _BaselStadtListingParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.entries: list[ListingEntry] = []
        self.next_url: str | None = None
        self.reported_total: int | None = None
        self._entry: dict[str, str] | None = None
        self._capture = ""
        self._chunks: list[str] = []
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = (values.get("class") or "").split()
        if tag == "a" and re.search(r"(?:^|/)job/details/\d+/?$", values.get("href") or ""):
            url = urljoin(self.base_url, values.get("href") or "")
            match = re.search(r"/job/details/(\d+)/?$", urlsplit(url).path)
            if match is None:
                raise PlatformAdapterError("Basel-Stadt listing lacks publication identity")
            self._entry = {"id": match.group(1), "url": url, "title": "", "organization": ""}
        if self._entry is not None and ("jobtitle" in classes or "organization" in classes):
            self._capture = "title" if "jobtitle" in classes else "organization"
            self._chunks = []
        if tag == "a" and "nextbtn" in classes:
            self.next_url = urljoin(self.base_url, values.get("href") or "")
        if tag == "a" and self._capture == "next_container":
            self.next_url = urljoin(self.base_url, values.get("href") or "")
        if tag == "li" and "nextbtn" in classes:
            self._capture = "next_container"

    def handle_data(self, data: str) -> None:
        self._text.append(data)
        if self._capture in {"title", "organization"}:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._entry is not None and self._capture in {"title", "organization"} and tag == "div":
            self._entry[self._capture] = " ".join("".join(self._chunks).split())
            self._capture = ""
            self._chunks = []
        if tag == "a" and self._entry is not None:
            if not self._entry["title"]:
                raise PlatformAdapterError("Basel-Stadt listing entry lacks title")
            self.entries.append(
                ListingEntry(
                    self._entry["id"],
                    self._entry["url"],
                    self._entry["title"],
                    {"organization": self._entry["organization"]},
                )
            )
            self._entry = None
        if tag == "li" and self._capture == "next_container":
            self._capture = ""

    def close(self) -> None:
        super().close()
        text = " ".join(" ".join(self._text).split())
        match = re.search(
            r"\b(\d+)\s+offene(?:r|n)?\s+(?:Job|Jobs|Lehrstelle|Lehrstellen)\b", text, re.I
        )
        self.reported_total = int(match.group(1)) if match else None


class _BaselStadtDetailParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self._title = False
        self._body = False
        self._title_chunks: list[str] = []
        self._text_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "meta" and values.get("property") == "og:description":
            self.description = values.get("content") or ""
        if tag == "h1":
            self._title, self._title_chunks = True, []
        if tag == "body":
            self._body = True

    def handle_data(self, data: str) -> None:
        if self._title:
            self._title_chunks.append(data)
        if self._body:
            self._text_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1" and self._title:
            self.title = " ".join("".join(self._title_chunks).split())
            self._title = False
        if tag == "body":
            self._body = False

    def close(self) -> None:
        super().close()
        if not self.description:
            self.description = " ".join(" ".join(self._text_chunks).split())


class BaselStadtSoliqueAdapter:
    platform_family = "BS_EMPLOYER_PORTAL"

    def _request(
        self,
        surface_index: int,
        page_number: int,
        *,
        seen_entries: tuple[tuple[str, str], ...] = (),
        reported_total: int | None = None,
    ) -> FetchRequest:
        try:
            surface_name, root = BASEL_STADT_SURFACES[surface_index]
        except IndexError as exc:
            raise PlatformAdapterError("Invalid Basel-Stadt listing surface") from exc
        url = root if page_number == 1 else f"{root}?{urlencode({'page': page_number})}"
        return FetchRequest(
            url,
            "text/html",
            "LISTING_PAGE",
            context={
                "surface_index": surface_index,
                "surface_name": surface_name,
                "page_number": page_number,
                "surface_seen_entries": seen_entries,
                "surface_total": reported_total,
            },
        )

    def initial_listing_request(self, source: Source) -> FetchRequest:
        return self._request(0, 1)

    def parse_listing_page(
        self, page: FetchedPage, request: FetchRequest, source: Source
    ) -> ListingPage:
        parser = _BaselStadtListingParser(request.url)
        try:
            parser.feed(page.body.decode("utf-8"))
            parser.close()
        except UnicodeDecodeError as exc:
            raise PlatformAdapterError("Basel-Stadt listing is not UTF-8") from exc
        surface_index = cast(int, request.context.get("surface_index", 0))
        surface_name = cast(str, request.context.get("surface_name", ""))
        page_number = cast(int, request.context.get("page_number", 1))
        prior_entries = tuple(
            cast(
                tuple[tuple[str, str], ...],
                request.context.get("surface_seen_entries", ()),
            )
        )
        prior_by_id = dict(prior_entries)
        prior_total = cast(int | None, request.context.get("surface_total"))
        total = parser.reported_total if parser.reported_total is not None else prior_total
        if total is None:
            raise PlatformAdapterError("Basel-Stadt listing lacks a reported surface total")
        if prior_total is not None and total != prior_total:
            raise PlatformAdapterError("Basel-Stadt surface total changed during pagination")
        current_by_id: dict[str, str] = {}
        new_entries: list[ListingEntry] = []
        for entry in parser.entries:
            entry.listing_metadata.update({"surface_name": surface_name})
            previous_on_page = current_by_id.get(entry.source_posting_id)
            if previous_on_page is not None and previous_on_page != entry.detail_url:
                raise PlatformAdapterError("Basel-Stadt page has a conflicting identity")
            current_by_id[entry.source_posting_id] = entry.detail_url
            previous = prior_by_id.get(entry.source_posting_id)
            if previous is not None and previous != entry.detail_url:
                raise PlatformAdapterError("Basel-Stadt pagination changed a detail identity")
            if previous is None:
                new_entries.append(entry)
        seen_by_id = {**prior_by_id, **current_by_id}
        seen = tuple(seen_by_id.items())
        next_request: FetchRequest | None
        if len(seen_by_id) > total:
            raise PlatformAdapterError("Basel-Stadt surface exceeded its reported total")
        if len(seen_by_id) == total:
            next_request = (
                self._request(surface_index + 1, 1)
                if surface_index + 1 < len(BASEL_STADT_SURFACES)
                else None
            )
        elif parser.next_url:
            query = parse_qs(urlsplit(parser.next_url).query)
            next_page_raw = query.get("page", [""])[0]
            if not next_page_raw.isdigit() or int(next_page_raw) != page_number + 1:
                raise PlatformAdapterError("Basel-Stadt pagination did not advance monotonically")
            next_request = self._request(
                surface_index,
                int(next_page_raw),
                seen_entries=seen,
                reported_total=total,
            )
        else:
            raise PlatformAdapterError("Basel-Stadt surface ended before its reported total")
        return ListingPage(new_entries, next_request, next_request is None)

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
        if not re.search(
            rf"/job/details/{re.escape(entry.source_posting_id)}/?$", urlsplit(page.final_url).path
        ):
            raise PlatformAdapterError("Basel-Stadt detail identity mismatch")
        parser = _BaselStadtDetailParser()
        try:
            parser.feed(page.body.decode("utf-8"))
            parser.close()
        except UnicodeDecodeError as exc:
            raise PlatformAdapterError("Basel-Stadt detail is not UTF-8") from exc
        if not parser.title or not parser.description:
            raise PlatformAdapterError("Basel-Stadt detail lacks title/description")
        if " ".join(parser.title.split()).casefold() != " ".join(entry.title.split()).casefold():
            raise PlatformAdapterError("Basel-Stadt detail title does not match listing")
        surface_name = str(entry.listing_metadata.get("surface_name", ""))
        organization = str(entry.listing_metadata.get("organization", ""))
        structured: dict[str, object] = {
            "source_format": "BASEL_STADT_SOLIQUE_HTML_V1",
            "publication_id": entry.source_posting_id,
            "surface_name": surface_name,
            "organization": organization,
            "description_text": parser.description,
        }
        return ParsedSourcePosting(
            source_posting_id=entry.source_posting_id,
            canonical_url=page.final_url,
            title=parser.title,
            published_at_raw=None,
            date_posted=None,
            valid_through=None,
            employment_type="Lehrstelle" if surface_name == "apprenticeships" else "",
            hiring_organization=organization or "Kanton Basel-Stadt",
            description_html=f"<p>{escape(unescape(parser.description))}</p>",
            responsibilities_html="",
            qualifications_html="",
            benefits_html="",
            raw_location="",
            location_street="",
            location_locality="",
            location_region="",
            location_postal_code="",
            location_country="CH",
            structured_payload=structured,
            published_at_precision="UNKNOWN",
            published_at_parse_method="MISSING",
        )
