"""Normal account connection reuses the system-browser OAuth flow without setup forms."""
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import expect

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


@pytest.mark.parametrize("service,title", [("drive", "Google Drive"), ("docs", "Google Docs"), ("sheets", "Google Sheets")])
def test_workspace_connection_exposes_scope_and_opens_real_pkce_without_nickname(browser, live, publisher_apps, monkeypatch, service, title):
    base, _ = live
    monkeypatch.setattr("hutch.gsuite.client.WorkspaceSecretToolStore", MemorySecrets)
    context = browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
    context.route("https://accounts.google.com/**", lambda route: route.fulfill(body="Fixture Google consent"))
    page = context.new_page()
    try:
        page.goto(base + "/#/connections")
        page.locator(f'[data-connection-open="google-{service}"]').click()
        card = page.locator(f"#connection-google-{service}")
        card.wait_for()
        assert page.locator("#connection-detail-heading h2").inner_text() == title
        assert "your approval of its exact account" in card.inner_text()
        card.locator(".google-file-permissions").get_by_text("Permissions and shared sign-in", exact=True).click()
        assert "only drive.file" in card.inner_text()
        assert "Disabling this service keeps the others connected." in card.inner_text()
        with page.expect_popup() as popup_info:
            card.get_by_role("button", name=f"Connect {title}").click()
        popup = popup_info.value
        popup.wait_for_url("https://accounts.google.com/**")
        query = parse_qs(urlsplit(popup.url).query)
        assert query["code_challenge_method"] == ["S256"]
        assert query["scope"] == ["https://www.googleapis.com/auth/drive.file"]
        assert popup.evaluate("window.opener === null")
        assert query["redirect_uri"][0].endswith("/api/v1/connections/google-workspace/callback")
        popup.close()
        out = artifact_path("workspace-connect")
        out.mkdir(parents=True, exist_ok=True)
        for width, height in ((1440, 900), (768, 1024), (320, 900)):
            page.set_viewport_size({"width": width, "height": height})
            card.scroll_into_view_if_needed()
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
            page.screenshot(path=str(out / f"{service}-{width}.png"), animations="disabled")
    finally:
        context.close()


def test_workspace_connected_account_can_be_revoked_and_callback_status_is_consumed(browser, live, publisher_apps, monkeypatch):
    from hutch.gsuite.client import WorkspaceAccount
    base, _ = live
    rows = [WorkspaceAccount("gws_0123456789abcdef01234567", "Work <account>", ("drive.file",))]
    removed = []
    monkeypatch.setattr("hutch.gsuite.client.WorkspaceSecretToolStore", MemorySecrets)
    monkeypatch.setattr("hutch.gsuite.client.GoogleWorkspaceClient.accounts", lambda self: list(rows))
    def disconnect(self, account_id):
        removed.append(account_id)
        rows.clear()
    monkeypatch.setattr("hutch.gsuite.client.GoogleWorkspaceClient.disconnect", disconnect)
    context = browser.new_context()
    page = context.new_page()
    try:
        page.goto(base + "/?google_workspace_result=connected#/connections")
        page.locator('[data-connection-open="google-drive"]').click()
        page.locator("#connection-google-drive").wait_for()
        assert "google_workspace_result" not in page.url
        assert page.locator("#connection-google-drive .google-file-account h3").inner_text() == "Work <account>"
        page.locator("#connection-google-drive .google-file-account-details summary").click()
        page.get_by_role("button", name="Disconnect shared Google account", exact=True).click()
        page.locator("#modal-confirm").click()
        page.wait_for_function("() => document.querySelector('#connection-google-drive')?.textContent.includes('No Google Drive accounts connected.')")
        assert removed == ["gws_0123456789abcdef01234567"]
    finally:
        context.close()


def test_phone_entry_explains_direction_and_requires_host_setup(browser, live, monkeypatch):
    base, _ = live
    monkeypatch.delenv("HUTCH_REMOTE_ENABLED", raising=False)
    context = browser.new_context(viewport={"width": 320, "height": 900}, reduced_motion="reduce")
    page = context.new_page()
    try:
        page.goto(base + "/#/connections")
        tile = page.locator('[data-connection-open="phone"]')
        tile.scroll_into_view_if_needed()
        assert "does not read phone apps or messages" in tile.locator("..").inner_text()
        tile.click()
        dialog = page.get_by_role("dialog")
        assert "stays local" in dialog.inner_text()
        assert page.locator("#modal-confirm").inner_text() == "Close"
        assert page.locator("#phone-pair-start").count() == 0
        assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
        page.locator("#modal-confirm").click()
    finally:
        context.close()


def test_phone_pairing_code_is_deliberate_ephemeral_and_never_in_a_url(browser, live, monkeypatch):
    base, app = live
    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "hutch.example")
    monkeypatch.setenv("HUTCH_WEBAUTHN_RP_ID", "hutch.example")
    monkeypatch.setenv("HUTCH_WEBAUTHN_ORIGIN", "https://hutch.example")
    context = browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(base + "/#/connections")
        page.locator('[data-connection-open="phone"]').click()
        assert not page.locator("#phone-pair-start").is_checked()
        assert not app.state.store._db.execute("SELECT 1 FROM pairing_codes").fetchall()
        out = artifact_path("phone-pairing-setup")
        out.mkdir(parents=True, exist_ok=True)
        for width, height in ((1440, 900), (768, 1024), (320, 900)):
            page.set_viewport_size({"width": width, "height": height})
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
            page.screenshot(path=str(out / f"setup-{width}.png"), animations="disabled")
        page.locator("#modal-confirm").click()
        page.get_by_text("Code created", exact=True).wait_for()
        code = page.locator("#phone-pair-result strong").inner_text()
        assert len(code.replace("-", "")) == 14
        assert page.locator("#phone-pair-result a").get_attribute("href") == "https://hutch.example/pair"
        assert code not in page.url
        assert code not in page.evaluate("JSON.stringify({...localStorage, ...sessionStorage})")
        assert page.locator("#modal-confirm").is_disabled()
        page.locator("#modal-close").click()
        assert page.locator("#phone-pair-result").count() == 0
        assert not errors
    finally:
        context.close()


@pytest.mark.parametrize("width", [1440, 390, 320])
def test_google_services_reuse_connection_and_disable_independently(browser, live, publisher_apps, monkeypatch, width):
    from hutch.gsuite.client import FILE_SCOPE, _atomic_private_json
    base, app = live
    aid = "gws_0123456789abcdef01234567"
    _atomic_private_json(app.state.config.state_dir / "google-workspace-accounts.json", {
        aid: {"label": "Work account", "scopes": [FILE_SCOPE], "services": ["drive"], "revision": 0}})
    monkeypatch.setattr("hutch.gsuite.client.WorkspaceSecretToolStore", MemorySecrets)
    context = browser.new_context(viewport={"width": width, "height": 950}, reduced_motion="reduce")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(base + "/#/connections?app=google-docs")
        card = page.locator("#connection-google-docs")
        card.get_by_role("button", name="Use this account", exact=True).click()
        expect(card.get_by_role("button", name="Disable Google Docs", exact=True)).to_be_visible()
        assert "Also enabled: Google Drive" in card.inner_text()
        assert not app.state.store.list_google_calendar_grants()
        card.get_by_role("button", name="Disable Google Docs", exact=True).click()
        expect(card.get_by_role("button", name="Use this account", exact=True)).to_be_visible()
        page.goto(base + "/#/connections?app=google-drive")
        expect(page.get_by_role("button", name="Disable Google Drive", exact=True)).to_be_visible()
        out = artifact_path("google-file-services")
        out.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out / f"drive-normal-{width}.png"), full_page=True, animations="disabled")
        page.add_style_tag(content=".connections-workspace * { letter-spacing: .12em !important; word-spacing: .16em !important; line-height: 1.5 !important; }")
        assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
        out = artifact_path("google-file-services")
        out.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out / f"drive-connected-{width}.png"), full_page=True, animations="disabled")
        assert not errors
    finally:
        context.close()
