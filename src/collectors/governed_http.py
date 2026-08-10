from __future__ import annotations

from typing import Any
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.utils import timezone

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
        method = request_spec.method.upper()
        if method not in {"GET", "POST"}:
            raise GovernedHttpError(f"unsupported governed HTTP method: {method}")
        if method == "GET" and request_spec.form_data:
            raise GovernedHttpError("GET requests cannot carry form data")
        data = urlencode(request_spec.form_data).encode("ascii") if method == "POST" else None
        request = Request(
            request_spec.url,
            data=data,
            method=method,
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
        "SRC-OFF-CITY-BERN": (
            ("LANDING", "JOBS_BERN_CH", "www.bern.ch", "https://www.bern.ch/themen/arbeiten-fuer-die-stadt-bern/offene-stellen"),
            ("API", "JOBS_BERN_CH", "jobs.bern.ch", "https://jobs.bern.ch/public/v1/medium/1840/jobs"),
            ("DETAIL", "JOBS_BERN_CH", "jobs.bern.ch", "https://jobs.bern.ch/offene-stellen/"),
        ),
        "SRC-OFF-CITY-LUZERN": (
            ("LANDING", "CITY_LUZERN_PORTAL", "jobs.stadtluzern.ch", "https://jobs.stadtluzern.ch/stellen/offene-stellen-stadt-luzern/"),
            ("LISTING", "CITY_LUZERN_PORTAL", "job.stadtluzern.ch", "https://job.stadtluzern.ch/stellen/stadtluzern/"),
            ("DETAIL", "CITY_LUZERN_PORTAL", "job.stadtluzern.ch", "https://job.stadtluzern.ch/stellen/stadtluzern/offene-stellen/"),
        ),
        "SRC-OFF-CITY-SCHAFFHAUSEN": (
            ("LANDING", "UMANTIS_LINKED", "jobs.stadt-schaffhausen.ch", "https://jobs.stadt-schaffhausen.ch/freie-stellen/"),
            ("LISTING", "UMANTIS_LINKED", "jobs.stadt-schaffhausen.ch", "https://jobs.stadt-schaffhausen.ch/freie-stellen/"),
            ("API", "UMANTIS_LINKED", "jobs.stadt-schaffhausen.ch", "https://jobs.stadt-schaffhausen.ch/wp-json/wp/v2/jobs"),
            ("DETAIL", "UMANTIS_LINKED", "jobs.stadt-schaffhausen.ch", "https://jobs.stadt-schaffhausen.ch/jobs/"),
        ),
        "SRC-OFF-CANTON-ZH": (
            ("LANDING", "SOLIQUE_LINKED", "www.zh.ch", "https://www.zh.ch/de/arbeiten-beim-kanton.html"),
            ("API", "SOLIQUE_LINKED", "live.solique.ch", "https://live.solique.ch/KTZH/de/api/v1/data/"),
            ("DETAIL", "SOLIQUE_LINKED", "live.solique.ch", "https://live.solique.ch/ktzh/job/details/"),
        ),
        "SRC-OFF-CANTON-AR": (
            ("LANDING", "SOLIQUE_EMBEDDED", "ar.ch", "https://ar.ch/verwaltung/departement-finanzen/personalamt/freie-stellen/"),
            ("API", "SOLIQUE_EMBEDDED", "live.solique.ch", "https://live.solique.ch/kanton-appenzell-ausserrhoden/api/json/"),
            ("DETAIL", "SOLIQUE_EMBEDDED", "live.solique.ch", "https://live.solique.ch/Microsites/showPublication/"),
        ),
        "SRC-OFF-CANTON-ZG": (
            ("LANDING", "PROSPECTIVE", "zg.ch", "https://zg.ch/de/offene-stellen"),
            ("LISTING", "PROSPECTIVE", "zg.prospective.ch", "https://zg.prospective.ch/"),
            ("LISTING", "PROSPECTIVE", "zg.prospective.ch", "https://zg.prospective.ch/lernende/"),
            ("DETAIL", "PROSPECTIVE", "www.zg.ch", "https://www.zg.ch/jobs/offene-stellen/"),
            ("DETAIL", "PROSPECTIVE", "www.zg.ch", "https://www.zg.ch/jobs/lernende/offene-stellen/"),
        ),
        "SRC-OFF-CANTON-BL": (
            ("LANDING", "PROSPECTIVE_UMANTIS_LINKED", "www.baselland.ch", "https://www.baselland.ch/politik-und-behorden/direktionen/finanz-und-kirchendirektion/personalamt/jobs/offene-stellen"),
            ("LISTING", "PROSPECTIVE_UMANTIS_LINKED", "ohws.prospective.ch", "https://ohws.prospective.ch/public/v1/careercenter/1571/"),
            ("DETAIL", "PROSPECTIVE_UMANTIS_LINKED", "jobs.baselland.ch", "https://jobs.baselland.ch/offene-stellen/"),
        ),
    }
    gate_011c1 = str(source.pk) in {
        "SRC-OFF-CANTON-ZH",
        "SRC-OFF-CANTON-AR",
        "SRC-OFF-CANTON-ZG",
        "SRC-OFF-CANTON-BL",
    }
    gate_011b = str(source.pk) in {
        "SRC-OFF-CITY-BERN",
        "SRC-OFF-CITY-LUZERN",
        "SRC-OFF-CITY-SCHAFFHAUSEN",
    }
    decision = (
        "docs/decisions/0009-gate-011c1-canton-platform-reuse.md"
        if gate_011c1
        else "docs/decisions/0008-gate-011b-priority-city-expansion.md"
        if gate_011b
        else "docs/decisions/0003-gate-007-incremental-platform-reuse.md"
    )
    verification = (
        "GATE-011C-1 live technical reconnaissance"
        if gate_011c1
        else "GATE-011B live technical reconnaissance"
        if gate_011b
        else "GATE-007 live technical reconnaissance"
    )
    for role, family, host, base_url in definitions.get(str(source.pk), ()):
        endpoint, _ = SourceEndpoint.objects.get_or_create(
            source=source,
            endpoint_role=role,
            base_url=base_url,
            defaults={
                "platform_family": family,
                "scheme": "https",
                "host": host,
                "enabled": True,
                "verified_at": timezone.now(),
                "evidence": {
                    "decision": decision,
                    "verification": verification,
                },
            },
        )
        if endpoint.verified_at is None:
            SourceEndpoint.objects.filter(pk=endpoint.pk, verified_at__isnull=True).update(
                verified_at=timezone.now(),
                evidence={
                    "decision": decision,
                    "verification": verification,
                },
            )
