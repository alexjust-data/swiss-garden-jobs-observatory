from __future__ import annotations

import base64
from urllib.parse import parse_qs, urlparse

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from playwright.sync_api import Route, sync_playwright

from dashboard.models import DashboardSnapshot
from dashboard.services import build_dashboard_snapshot

from .factories import create_dashboard_upstream


class DashboardBrowserAcceptance(StaticLiveServerTestCase):
    snapshot: DashboardSnapshot

    def setUp(self) -> None:
        super().setUp()
        data = create_dashboard_upstream(
            location_status="RESOLVED",
            public_coordinates=(47.501, 8.701),
            description="<p>Public green-space maintenance</p>",
        )
        self.snapshot, _ = build_dashboard_snapshot(
            as_of=data["as_of"],
            dedup_run=data["dedup"],
            premium_run=data["premium_run"],
        )

    def test_map_table_filter_and_shared_accessible_drawer_without_external_network(self) -> None:
        local_host = urlparse(self.live_server_url).netloc
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            external_requests: list[str] = []
            swisstopo_requests: list[str] = []
            browser_errors: list[str] = []
            page.on(
                "console",
                lambda message: browser_errors.append(message.text)
                if message.type == "error"
                else None,
            )
            page.on("pageerror", lambda error: browser_errors.append(str(error)))
            page.on(
                "response",
                lambda response: browser_errors.append(f"{response.status} {response.url}")
                if response.status >= 400
                else None,
            )

            def route_request(route: Route) -> None:
                host = urlparse(route.request.url).netloc
                if host == "wmts.geo.admin.ch":
                    swisstopo_requests.append(route.request.url)
                    route.fulfill(
                        status=200,
                        content_type="image/png",
                        body=base64.b64decode(
                            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
                        ),
                    )
                elif host and host != local_host:
                    external_requests.append(route.request.url)
                    route.abort()
                else:
                    route.continue_()

            page.route("**/*", route_request)
            page.goto(self.live_server_url + "/jobs/", wait_until="networkidle")
            assert page.get_by_text("Observed sources, not a market census.").is_visible()
            assert page.get_by_text("Pending GATE-011 Day-0").is_visible()
            assert page.evaluate("typeof window.dashboardApp") == "object", browser_errors
            assert page.get_by_text("Map library unavailable.", exact=False).count() == 0

            page.get_by_label("Search").fill("Gardener")
            page.get_by_role("button", name="Apply filters").click()
            page.wait_for_function("window.location.search === '?q=Gardener'")
            row = page.locator("#results-body tr").first
            row.wait_for(state="visible")
            row.focus()
            row.press("Enter")
            drawer = page.locator("#job-drawer")
            drawer.wait_for(state="visible")
            assert drawer.get_by_text("Gardener", exact=True).is_visible()
            assert drawer.get_by_text("Open original advert", exact=True).is_visible()
            page.keyboard.press("Escape")
            assert drawer.is_hidden()
            assert row.evaluate("node => document.activeElement === node")

            geojson = page.evaluate(
                "async id => await (await fetch('/api/v1/dashboard/snapshots/' + id + "
                "'/vacancies.geojson')).json()",
                str(self.snapshot.pk),
            )
            assert len(geojson["features"]) == 1
            maps_url = page.evaluate(
                "coordinates => window.dashboardApp.googleMapsUrl(coordinates)",
                geojson["features"][0]["geometry"]["coordinates"],
            )
            parsed_maps_url = urlparse(maps_url)
            assert parsed_maps_url.netloc == "www.google.com"
            assert parsed_maps_url.path == "/maps/search/"
            assert parse_qs(parsed_maps_url.query) == {
                "api": ["1"],
                "query": ["47.501,8.701"],
            }
            page.evaluate(
                "feature => window.dashboardApp.openMapFixture(feature)",
                geojson["features"][0],
            )
            drawer.wait_for(state="visible")
            assert drawer.get_by_text("Gardener", exact=True).is_visible()
            assert "Confidentialstrasse" not in page.content()
            page.keyboard.press("Escape")

            table_payload = page.evaluate(
                "async id => await (await fetch('/api/v1/dashboard/snapshots/' + id + "
                "'/vacancies/')).json()",
                str(self.snapshot.pk),
            )
            table_payload["results"][0]["mapping_status"] = "LOCATION_UNRESOLVED"
            page.evaluate(
                "records => window.dashboardApp.renderRowsFixture(records)",
                table_payload["results"],
            )
            unmapped_row = page.locator(
                '#results-body tr[data-mapping-status="LOCATION_UNRESOLVED"]'
            )
            unmapped_row.wait_for(state="visible")
            assert unmapped_row.get_by_text(
                "Not shown on map · Location unresolved", exact=True
            ).is_visible()
            assert unmapped_row.evaluate(
                "node => getComputedStyle(node).backgroundColor"
            ) != "rgba(0, 0, 0, 0)"
            browser.close()

        assert swisstopo_requests
        assert external_requests == []

    @override_settings(DASHBOARD_MAP_PROVIDER="google", GOOGLE_MAPS_API_KEY="")
    def test_google_provider_without_key_fails_visibly_without_external_request(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            external_requests: list[str] = []
            page.on(
                "request",
                lambda request: external_requests.append(request.url)
                if urlparse(request.url).netloc not in {"", urlparse(self.live_server_url).netloc}
                else None,
            )
            page.goto(self.live_server_url + "/jobs/", wait_until="networkidle")
            assert page.get_by_text(
                "Google Maps is selected but GOOGLE_MAPS_API_KEY is not configured.",
                exact=False,
            ).is_visible()
            assert external_requests == []
            browser.close()

    @override_settings(
        DASHBOARD_MAP_PROVIDER="google",
        GOOGLE_MAPS_API_KEY="test-browser-restricted-key",
    )
    def test_google_provider_uses_public_geojson_with_stubbed_maps_api(self) -> None:
        local_host = urlparse(self.live_server_url).netloc
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            maps_requests: list[str] = []

            def route_request(route: Route) -> None:
                parsed = urlparse(route.request.url)
                if parsed.netloc == "maps.googleapis.com":
                    maps_requests.append(route.request.url)
                    callback = parse_qs(parsed.query)["callback"][0]
                    stub = """
(() => {
  class GoogleMap {
    constructor() { this.zoom = 7; window.__googleMapConstructed = true; }
    getZoom() { return this.zoom; }
    addListener() { return { remove() {} }; }
    panTo() {}
    setZoom(value) { this.zoom = value; }
    setCenter() {}
    fitBounds() {}
  }
  class Marker {
    constructor() {
      window.__googleMarkerCount = (window.__googleMarkerCount || 0) + 1;
    }
    setMap() {}
    addListener() { return { remove() {} }; }
  }
  class InfoWindow { setContent() {} open() {} }
  class LatLngBounds { extend() {} }
  window.google = {
    maps: {
      Map: GoogleMap,
      Marker,
      InfoWindow,
      LatLngBounds,
      SymbolPath: { CIRCLE: "circle" }
    }
  };
  window["__CALLBACK__"]();
})();
""".replace("__CALLBACK__", callback)
                    route.fulfill(
                        status=200,
                        content_type="application/javascript",
                        body=stub,
                    )
                elif parsed.netloc in {"", local_host}:
                    route.continue_()
                else:
                    route.abort()

            page.route("**/*", route_request)
            page.goto(self.live_server_url + "/jobs/", wait_until="networkidle")
            page.wait_for_function("window.__googleMapConstructed === true")
            page.wait_for_function("window.__googleMarkerCount === 1")

            assert len(maps_requests) == 1
            query = parse_qs(urlparse(maps_requests[0]).query)
            assert query["key"] == ["test-browser-restricted-key"]
            assert query["callback"] == ["__swissGardenGoogleMapsReady"]
            assert "Confidentialstrasse" not in page.content()
            browser.close()
