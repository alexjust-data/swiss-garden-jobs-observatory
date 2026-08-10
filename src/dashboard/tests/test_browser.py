from __future__ import annotations

from typing import ClassVar
from urllib.parse import urlparse

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from playwright.sync_api import Route, sync_playwright

from dashboard.models import DashboardSnapshot
from dashboard.services import build_dashboard_snapshot

from .factories import create_dashboard_upstream


class DashboardBrowserAcceptance(StaticLiveServerTestCase):
    snapshot: ClassVar[DashboardSnapshot]

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        data = create_dashboard_upstream(
            location_status="RESOLVED",
            public_coordinates=(47.501, 8.701),
            description="<p>Public green-space maintenance</p>",
        )
        cls.snapshot, _ = build_dashboard_snapshot(
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
                if host and host != local_host:
                    external_requests.append(route.request.url)
                    route.abort()
                else:
                    route.continue_()

            page.route("**/*", route_request)
            page.goto(self.live_server_url + "/jobs/", wait_until="networkidle")
            assert page.get_by_text("Observed sources, not a market census.").is_visible()
            assert page.get_by_text("Pending GATE-011 Day-0").is_visible()
            assert page.evaluate("typeof window.dashboardApp") == "object", browser_errors

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
            page.evaluate(
                "feature => window.dashboardApp.openMapFixture(feature)",
                geojson["features"][0],
            )
            drawer.wait_for(state="visible")
            assert drawer.get_by_text("Gardener", exact=True).is_visible()
            assert "Confidentialstrasse" not in page.content()
            page.keyboard.press("Escape")
            browser.close()

        assert external_requests == []
