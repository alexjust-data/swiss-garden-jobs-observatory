from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from collectors.platforms import FetchedPage, FetchRequest
from sources.models import Source, SourceEndpoint

USER_AGENT = (
    "SwissGardenJobsObservatory/0.1 "
    "(+https://github.com/alexjust-data/swiss-garden-jobs-observatory)"
)
MAX_RESPONSE_BYTES = 5 * 1024 * 1024


class GovernedHttpError(RuntimeError):
    pass


def origin(url: str) -> tuple[str, str, int]:
    parsed = urlsplit(url)
    if parsed.username is not None or parsed.password is not None:
        raise GovernedHttpError("credential-bearing URLs are forbidden")
    return parsed.scheme.lower(), (parsed.hostname or "").lower(), parsed.port or 443


def allowed_origins(source: Source) -> set[tuple[str, str, int]]:
    return {
        (endpoint.scheme.lower(), endpoint.host.lower(), 443)
        for endpoint in SourceEndpoint.objects.filter(source=source, enabled=True)
    }


def validate_authorized_url(source: Source, url: str) -> None:
    scheme, host, port = origin(url)
    if scheme != "https" or port != 443 or (scheme, host, port) not in allowed_origins(source):
        raise GovernedHttpError(f"URL origin is not authorized for {source.pk}: {url}")


class _AuthorizedRedirectHandler(HTTPRedirectHandler):
    def __init__(self, source: Source) -> None:
        self.source = source
        super().__init__()

    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Request | None:
        validate_authorized_url(self.source, urljoin(req.full_url, newurl))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class GovernedHttpClient:
    def __init__(self, source: Source, *, timeout_seconds: float = 30.0) -> None:
        self.source = source
        self.timeout_seconds = timeout_seconds
        self._opener = build_opener(_AuthorizedRedirectHandler(source))

    def fetch_request(self, request_spec: FetchRequest) -> FetchedPage:
        validate_authorized_url(self.source, request_spec.url)
        request = Request(
            request_spec.url,
            headers={"User-Agent": USER_AGENT, "Accept": request_spec.accept},
        )
        with self._opener.open(request, timeout=self.timeout_seconds) as response:
            final_url = response.geturl()
            validate_authorized_url(self.source, final_url)
            status = int(response.status)
            content_type = response.headers.get_content_type()
            body = response.read(MAX_RESPONSE_BYTES + 1)
        if status != 200:
            raise GovernedHttpError(f"expected HTTP 200, found {status}")
        if len(body) > MAX_RESPONSE_BYTES:
            raise GovernedHttpError(f"response exceeds {MAX_RESPONSE_BYTES} bytes")
        return FetchedPage(request_spec.url, final_url, status, content_type, body)

    def fetch(self, url: str) -> FetchedPage:
        return self.fetch_request(FetchRequest(url=url))


def ensure_default_endpoints(source: Source) -> None:
    definitions: dict[str, tuple[tuple[str, str, str, str], ...]] = {
        "SRC-OFF-CITY-WINTERTHUR": (
            ("LANDING", "REXX_SYSTEMS", "jobs.winterthur.ch", "https://jobs.winterthur.ch/"),
            (
                "LISTING",
                "REXX_SYSTEMS",
                "jobs.winterthur.ch",
                "https://jobs.winterthur.ch/stellenangebote.html",
            ),
            ("DETAIL", "REXX_SYSTEMS", "jobs.winterthur.ch", "https://jobs.winterthur.ch/"),
        ),
        "SRC-OFF-CITY-ZURICH": (
            (
                "LANDING",
                "CITY_SITE_SUCCESSFACTORS_LINKED",
                "jobs.stadt-zuerich.ch",
                "https://jobs.stadt-zuerich.ch/",
            ),
            (
                "LISTING",
                "CITY_SITE_SUCCESSFACTORS_LINKED",
                "www.stadt-zuerich.ch",
                "https://www.stadt-zuerich.ch/de/politik-und-verwaltung/arbeiten-bei-der-stadt/jobs.html",
            ),
            (
                "API",
                "CITY_SITE_SUCCESSFACTORS_LINKED",
                "www.stadt-zuerich.ch",
                "https://www.stadt-zuerich.ch/stzh/jobsearch",
            ),
            (
                "DETAIL",
                "CITY_SITE_SUCCESSFACTORS_LINKED",
                "www.stadt-zuerich.ch",
                "https://www.stadt-zuerich.ch/de/politik-und-verwaltung/arbeiten-bei-der-stadt/jobs/",
            ),
        ),
    }
    for role, family, host, base_url in definitions.get(str(source.pk), ()):
        SourceEndpoint.objects.get_or_create(
            source=source,
            endpoint_role=role,
            base_url=base_url,
            defaults={
                "platform_family": family,
                "scheme": "https",
                "host": host,
                "enabled": True,
                "evidence": {
                    "decision": "docs/decisions/0003-gate-007-incremental-platform-reuse.md"
                },
            },
        )
