"""First run shows the setup check and offers the background service, never installing it silently.

Fresh state, real browser. `/api/v1/runtime` and the service install are labelled fixtures:
the real install would write a systemd user unit on this machine, and an installed unit on
the developer machine would change what `GET /api/v1/runtime` reports. The setup check itself
is the real endpoint except where a finding is injected to show the failing state.
"""

from __future__ import annotations

import json

import pytest

pw = pytest.importorskip("playwright.sync_api")

from hutch.server.app import create_app  # noqa: E402
from tests.support.browser import launch_browser, wait_for_page  # noqa: E402
from tests.support.live_app import PageWatch, horizontal_overflow, serve  # noqa: E402

RUNTIME = "**/api/v1/runtime"
INSTALL = "**/api/v1/runtime/service/install"
CHECK = "**/api/v1/setup/check"


def service(installed=False, active=False, state="inactive", supported=True):
    return {"engine": {}, "scheduler": {}, "queue": {}, "service": {
        "supported": supported, "installed": installed, "state": state, "active": active, "ready": active,
        "detail": "", "port": 8787, "linger": "unknown", "unit_path": "", "main_pid": None}}


def check(status="ok", title="Database", detail="fine", fix=""):
    return {"worst": status, "checks": [{"id": "database", "title": title, "status": status, "detail": detail, "fix": fix}]}


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as playwright:
        b = launch_browser(playwright)
        yield b
        b.close()


@pytest.fixture()
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    with serve(create_app()) as url:
        yield url


def fulfil(body, status=200):
    return lambda route: route.fulfill(status=status, content_type="application/json", body=json.dumps(body))


def _open(browser, base, runtime, size=(1440, 900), check_handler=None):
    page = browser.new_context(viewport={"width": size[0], "height": size[1]}).new_page()
    watch = PageWatch(page)
    posts = []
    page.on("request", lambda req: posts.append(req) if req.method == "POST" and req.url.endswith("/service/install") else None)
    state = {"runtime": runtime}   # the fixture flips to "running" only after the install request is answered
    page.route(RUNTIME, lambda route: fulfil(state["runtime"])(route))
    if check_handler:
        page.route(CHECK, check_handler)

    def installed(route):
        state["runtime"] = service(installed=True, active=True, state="active")
        fulfil(state["runtime"]["service"])(route)

    page.route(INSTALL, installed)
    page.goto(f"{base}/#/chat", wait_until="domcontentloaded")
    page.locator("#first-run-setup-check").wait_for(timeout=20_000)
    return page, watch, posts


def test_service_is_offered_and_installing_needs_an_explicit_confirmed_click(browser, base):
    page, watch, posts = _open(browser, base, service())
    try:
        panel = page.locator("#first-run-setup-check")
        panel.get_by_text("Nothing is installed until you choose.").wait_for(timeout=15_000)
        assert "Scheduled work runs only while Hutch is running" in panel.inner_text()
        page.wait_for_timeout(500)
        assert posts == [], "viewing first run must never install anything"
        button = panel.get_by_role("button", name="Install background service")
        button.click()
        dialog = page.get_by_role("dialog", name="Install the background service?")
        dialog.wait_for()
        dialog.get_by_role("button", name="Cancel").click()
        page.wait_for_timeout(300)
        assert posts == [], "cancelling installs nothing"
        button.click()
        dialog.wait_for()
        dialog.get_by_role("button", name="Install", exact=True).click()
        panel.get_by_text("Background service is running.").wait_for(timeout=15_000)
        assert len(posts) == 1
        assert json.loads(posts[0].post_data) == {"confirm": "install", "port": 8787}
        assert not watch.errors, watch.errors
    finally:
        page.context.close()


def test_an_installed_service_is_reported_not_offered_again(browser, base):
    page, watch, posts = _open(browser, base, service(installed=True, active=True, state="active"))
    try:
        panel = page.locator("#first-run-setup-check")
        panel.get_by_text("Background service is running.").wait_for(timeout=15_000)
        assert panel.get_by_role("button", name="Install background service").count() == 0
    finally:
        page.context.close()


def test_an_unsupported_host_does_not_offer_a_service(browser, base):
    page, watch, posts = _open(browser, base, service(supported=False))
    try:
        panel = page.locator("#first-run-setup-check")
        panel.get_by_text("not available on this system", exact=False).wait_for(timeout=15_000)
        assert panel.get_by_role("button", name="Install background service").count() == 0
    finally:
        page.context.close()


def test_findings_that_need_attention_show_their_fix(browser, base):
    body = check("fail", "Database", "integrity check failed", "restore from a snapshot with `hutch state`")
    page, watch, posts = _open(browser, base, service(installed=True, active=True, state="active"), check_handler=fulfil(body))
    try:
        panel = page.locator("#first-run-setup-check")
        panel.get_by_text("1 thing needs attention").wait_for(timeout=15_000)
        text = panel.inner_text()
        assert "Database" in text and "integrity check failed" in text and "restore from a snapshot" in text
    finally:
        page.context.close()


def test_a_healthy_install_says_nothing_needs_attention(browser, base):
    page, watch, posts = _open(browser, base, service(installed=True, active=True, state="active"),
                               check_handler=fulfil(check("ok")))
    try:
        page.locator("#first-run-setup-check").get_by_text("Nothing needs attention.").wait_for(timeout=15_000)
    finally:
        page.context.close()


def test_a_failed_check_offers_retry(browser, base):
    page, watch, posts = _open(browser, base, service(installed=True, active=True, state="active"),
                               check_handler=fulfil({"detail": "setup check failed"}, status=503))
    try:
        panel = page.locator("#first-run-setup-check")
        panel.get_by_text("Hutch could not run the setup check.").wait_for(timeout=15_000)
        assert panel.get_by_role("button", name="Check again").is_visible()
    finally:
        page.context.close()


@pytest.mark.parametrize("size", [(1440, 900), (900, 900), (360, 800)])
def test_panel_fits_every_viewport(browser, base, size):
    page, watch, posts = _open(browser, base, service(), size)
    try:
        page.locator("#first-run-setup-check").get_by_role("button", name="Install background service").wait_for(timeout=15_000)
        assert horizontal_overflow(page) == 0, size
        box = page.locator("#first-run-setup-check").get_by_role("button", name="Install background service").bounding_box()
        assert box["x"] + box["width"] <= size[0] + 0.5 and box["height"] >= 36
    finally:
        page.context.close()
