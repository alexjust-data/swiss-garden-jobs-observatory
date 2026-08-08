from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol

from sources.models import Source


class PlatformAdapterError(RuntimeError):
    pass


class UnsupportedPlatformError(PlatformAdapterError):
    pass


@dataclass(frozen=True)
class FetchRequest:
    url: str
    accept: str = "text/html"
    role: str = "AUXILIARY"


@dataclass(frozen=True)
class FetchedPage:
    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    body: bytes


@dataclass(frozen=True)
class ListingEntry:
    source_posting_id: str
    url: str
    title: str = ""
    listing_metadata: dict[str, object] = field(default_factory=dict)

    @property
    def detail_url(self) -> str:
        return self.url


@dataclass(frozen=True)
class ListingPage:
    entries: list[ListingEntry]
    next_request: FetchRequest | None
    discovery_complete: bool
    total_reported: int | None = None


@dataclass(frozen=True)
class ParsedSourcePosting:
    source_posting_id: str
    canonical_url: str
    title: str
    published_at_raw: str | None
    date_posted: date | None
    valid_through: date | None
    employment_type: str
    hiring_organization: str
    description_html: str
    responsibilities_html: str
    qualifications_html: str
    benefits_html: str
    raw_location: str
    location_street: str
    location_locality: str
    location_region: str
    location_postal_code: str
    location_country: str
    structured_payload: dict[str, object]
    source_published_at: datetime | None = None
    source_updated_at: datetime | None = None
    published_at_precision: str = "UNKNOWN"
    published_at_parse_method: str = "MISSING"


class PlatformAdapter(Protocol):
    platform_family: str

    def initial_listing_request(self, source: Source) -> FetchRequest: ...

    def parse_listing_page(
        self, page: FetchedPage, request: FetchRequest, source: Source
    ) -> ListingPage: ...

    def detail_request(self, entry: ListingEntry, source: Source) -> FetchRequest: ...

    def parse_detail(
        self, page: FetchedPage, entry: ListingEntry, source: Source
    ) -> ParsedSourcePosting: ...
