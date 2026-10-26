"""Existing-login selection in the real dialog; credentials stay server-side."""

import json

from playwright.sync_api import expect

from tests.e2e.test_composer import browser  # noqa: F401
from tests.e2e.test_runtime_page import live  # noqa: F401
from tests.test_opencode_api import FakeServer
from tests.support.artifacts import artifact_path
from tests.support.browser import wait_for_page


def test_existing_login_dialog_is_scoped_and_responsive(live, browser, tmp_path, monkeypatch):
    base, _app = live
    fake = FakeServer()
    integrations = fake.integrations
    def connected_integrations():
        rows = integrations()
        if fake.keys:
            rows[0]["connections"] = [{"id": "fixture-connection", "label": "Existing local login"}]
        return rows
    fake.integrations = connected_integrations
    monkeypatch.setattr("hutch.runtime.opencode_server.OpenCodeServer", lambda *args, **kwargs: fake)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "local-data"))
    auth = tmp_path / "local-data" / "opencode" / "auth.json"
    auth.parent.mkdir(parents=True)
    auth.write_text(json.dumps({"openai": {"type": "api", "key": "browser-test-private-key"},
                                "other-oauth": {"type": "oauth", "access": "must-not-copy"}}))
    auth.chmod(0o600)
    page = browser.new_page(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    out = artifact_path("opencode-existing-login")
    out.mkdir(parents=True, exist_ok=True)
    try:
        page.goto(base, wait_until="domcontentloaded")
        wait_for_page(page, "typeof openOpenCodeSetupDialog === 'function'")
        page.evaluate("openOpenCodeSetupDialog()")
        page.get_by_role("button", name="Use an existing OpenCode login").click()
        expect(page.locator("#oc-local-logins")).to_contain_text("openai")
        assert "browser-test-private-key" not in page.content()
        assert page.locator("[data-oc-local]").count() == 1
        for width, height in ((1440, 960), (768, 1024), (320, 780)):
            page.set_viewport_size({"width": width, "height": height})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            button = page.get_by_role("button", name="Use this login", exact=True)
            button.scroll_into_view_if_needed()
            assert button.is_visible()
            page.screenshot(path=str(out / f"local-login-{width}.png"))
        page.get_by_role("button", name="Use this login", exact=True).focus()
        page.keyboard.press("Enter")
        expect(page.locator("#oc-setup-status")).to_contain_text("Connected.")
        assert fake.keys == [("openai", "browser-test-private-key")]
        assert "browser-test-private-key" not in page.content()
        assert not errors
    finally:
        page.close()
