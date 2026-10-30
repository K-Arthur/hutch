"""The Models page shows what first run shows: a detected service and a one-click route.

Fresh state, no saved route. The OpenCode status call is a labelled fixture (the real
call can start a private OpenCode server), so this is not live detection proof; a live
OpenCode journey is recorded as not run. Saving goes through the real `/models/set-default`.
"""

from __future__ import annotations

import json

import pytest

pw = pytest.importorskip("playwright.sync_api")

from hutch.server.app import create_app  # noqa: E402
from tests.support.browser import launch_browser, wait_for_page  # noqa: E402
from tests.support.live_app import PageWatch, horizontal_overflow, serve  # noqa: E402

STATUS = "**/api/v1/opencode/status"


def ready(models, authenticated=False):
    return {"version": "fixture", "integrations": [], "authenticated": authenticated, "ready": bool(models),
            "models": [{"spec": spec, "provider_id": "mock", "model_id": spec.split("/", 1)[1], "name": name,
                        "context": 0, "output": 0, "capabilities": []} for spec, name in models]}


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


def _open(browser, base, handler, size=(1440, 900)):
    page = browser.new_context(viewport={"width": size[0], "height": size[1]}).new_page()
    watch = PageWatch(page)
    page.route(STATUS, handler)
    page.goto(f"{base}/models", wait_until="domcontentloaded")
    return page, watch


def test_ready_service_is_offered_with_first_run_copy_and_saves_in_one_click(browser, base):
    body = ready([("mock/demo", "Demo model"), ("mock/other", "Other model")])
    page, watch = _open(browser, base, lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(body)))
    try:
        panel = page.locator("#detected-service")
        panel.get_by_text("OpenCode is ready with 2 model options.").wait_for(timeout=15_000)
        assert "Its available models can be used without a separate account." in panel.inner_text()
        button = panel.get_by_role("button", name="Use Demo model")
        button.click()
        page.wait_for_url("**/models")
        wait_for_page(page, "document.body.innerText.includes('mock/demo')")
        text = page.locator("main").inner_text()
        assert "No model routes saved yet" not in text and "No model routes configured" not in text
        assert page.locator("#detected-service").count() == 0 or page.locator("#detected-service").is_hidden()
        assert not [e for e in watch.errors if "opencode/status" not in e], watch.errors
    finally:
        page.context.close()


def test_connected_account_copy_matches_first_run(browser, base):
    body = ready([("mock/demo", "Demo model")], authenticated=True)
    page, watch = _open(browser, base, lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(body)))
    try:
        panel = page.locator("#detected-service")
        panel.get_by_text("OpenCode is ready with 1 model option.").wait_for(timeout=15_000)
        assert "A provider account is connected." in panel.inner_text()
    finally:
        page.context.close()


def test_nothing_ready_says_so_and_a_failed_check_offers_retry(browser, base):
    page, watch = _open(browser, base, lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(ready([]))))
    try:
        panel = page.locator("#detected-service")
        panel.get_by_text("No ready AI service was found.").wait_for(timeout=15_000)
        assert panel.get_by_role("button", name="Use ").count() == 0
    finally:
        page.context.close()
    page, watch = _open(browser, base, lambda route: route.fulfill(status=503, content_type="application/json", body='{"detail":"opencode unavailable"}'))
    try:
        panel = page.locator("#detected-service")
        panel.get_by_text("Hutch could not check for AI services.").wait_for(timeout=15_000)
        assert panel.get_by_role("button", name="Check again").is_visible()
    finally:
        page.context.close()


@pytest.mark.parametrize("size", [(1440, 900), (900, 900), (360, 800)])
def test_panel_fits_every_viewport(browser, base, size):
    body = ready([("mock/demo", "A model with a rather long display name that must wrap instead of overflowing")])
    page, watch = _open(browser, base, lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(body)), size)
    try:
        page.locator("#detected-service").get_by_role("button", name="Use ").wait_for(timeout=15_000)
        assert horizontal_overflow(page) == 0, size
        box = page.locator("#detected-service").get_by_role("button", name="Use ").bounding_box()
        assert box["x"] + box["width"] <= size[0] + 0.5 and box["height"] >= 40
    finally:
        page.context.close()
