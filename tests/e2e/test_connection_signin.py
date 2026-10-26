"""Normal account connection reuses the system-browser OAuth flow without setup forms."""
from urllib.parse import parse_qs, urlsplit

from tests.e2e.test_browser import browser, live  # noqa: F401
from tests.test_google_calendar import MemorySecrets
from tests.test_oauth_apps import publisher_apps  # noqa: F401
from tests.support.artifacts import artifact_path


def test_google_calendar_tile_connects_without_a_nickname_or_write_escalation(browser, live, publisher_apps, monkeypatch):
    base, app = live
    monkeypatch.setattr("hutch.google_calendar.SecretToolStore", MemorySecrets)
    context = browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
    context.route("https://accounts.google.com/**", lambda route: route.fulfill(body="Fixture Google consent"))
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(base + "/#/connections")
        tile = page.locator('[data-connection-open="google-calendar"]')
        tile.wait_for()
        assert tile.inner_text().strip() == "Connect Google"
        assert not page.locator("#connection-management").evaluate("element => element.open")
        page.locator("#google-calendar-event-creation").evaluate("element => element.checked = true")
        with page.expect_popup() as popup_info:
            tile.click()
        popup = popup_info.value
        popup.wait_for_url("https://accounts.google.com/**")
        query = parse_qs(urlsplit(popup.url).query)
        assert query["code_challenge_method"] == ["S256"]
        assert all(scope.endswith("readonly") for scope in query["scope"][0].split())
        assert popup.evaluate("window.opener === null")
        assert not app.state.store.list_google_calendar_grants()
        popup.close()
        out = artifact_path("connection-signin")
        out.mkdir(parents=True, exist_ok=True)
        for width, height in ((1440, 900), (768, 1024), (320, 900)):
            page.set_viewport_size({"width": width, "height": height})
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
            page.screenshot(path=str(out / f"accounts-{width}.png"), animations="disabled")
        assert not errors
    finally:
        context.close()


def test_microsoft_tile_asks_purpose_then_opens_signin_without_nickname(browser, live, publisher_apps, monkeypatch):
    base, _ = live
    monkeypatch.setattr("hutch.outlook_calendar.OutlookCalendarBook.secret_store_type", MemorySecrets)
    context = browser.new_context()
    context.route("https://login.microsoftonline.com/**", lambda route: route.fulfill(body="Fixture Microsoft consent"))
    page = context.new_page()
    try:
        page.goto(base + "/#/connections")
        page.locator('[data-connection-open="outlook-calendar"]').click()
        page.get_by_role("dialog").wait_for()
        assert page.get_by_role("radio", name="Read a calendar").is_checked()
        with page.expect_popup() as popup_info:
            page.locator("#modal-confirm").click()
        popup = popup_info.value
        popup.wait_for_url("https://login.microsoftonline.com/**")
        query = parse_qs(urlsplit(popup.url).query)
        assert query["code_challenge_method"] == ["S256"]
        assert query["scope"] == ["Calendars.ReadBasic offline_access"]
        assert popup.evaluate("window.opener === null")
    finally:
        context.close()
