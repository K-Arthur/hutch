"""A person with nothing set up starts with a real route, and is told where their words go.

Real local server and browser. The OpenCode status and the route list are labelled fixtures (a live OpenCode call
can start a private server); the decision under test is made by the real `starter-route.js`. Nothing is saved
by choosing a starter: it is preselected, shown with its notice, and confirmed only by creating the assistant.
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit

import pytest

pw = pytest.importorskip("playwright.sync_api")

from hutch.models import Bot  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from tests.support.browser import launch_browser  # noqa: E402
from tests.support.live_app import PageWatch, horizontal_overflow, serve  # noqa: E402

FREE = {"ready": True, "authenticated": False, "integrations": [], "version": "fixture", "models": [
    {"spec": "opencode/opencode/glm-flash-free", "provider_id": "opencode", "model_id": "glm-flash-free", "name": "GLM Flash",
     "context": 64000, "output": 0, "capabilities": ["toolcall"]},
    {"spec": "opencode/opencode/plain-free", "provider_id": "opencode", "model_id": "plain-free", "name": "Plain",
     "context": 128000, "output": 0, "capabilities": []}]}
LOCAL = [{"spec": "ollama/llama3.2:3b", "label": "llama3.2:3b", "group": "On this machine", "state": "ready", "hosted": False,
          "note": "", "fix": "", "default": False, "worst_case_usd": None, "detail": [], "catalog_search": False}]
NOTHING_SAVED = {"model": "", "inference_mode": "hybrid", "configured": False, "route_problem": None}


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as playwright:
        b = launch_browser(playwright)
        yield b
        b.close()


@pytest.fixture()
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    with serve(create_app()) as url:
        yield url


def _page(browser, *, opencode, routes, size=(1440, 900), opencode_status=200):
    context = browser.new_context(viewport={"width": size[0], "height": size[1]})
    seen = []

    def handle(route):
        path = urlsplit(route.request.url).path
        bodies = {"/api/v1/opencode/status": opencode, "/api/v1/model-routes": routes,
                  "/api/v1/preferences/model-defaults": NOTHING_SAVED}
        seen.append(path)
        if path == "/api/v1/opencode/status" and opencode_status != 200:
            route.fulfill(status=opencode_status, content_type="application/json", body=json.dumps(opencode))
        elif path in bodies:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(bodies[path]))
        else:
            route.continue_()

    context.route("**/api/v1/**", handle)
    page = context.new_page()
    return page, PageWatch(page), seen


def test_first_run_starts_on_a_free_model_and_says_what_that_means(browser, base):
    page, watch, _ = _page(browser, opencode=FREE, routes=[])
    try:
        page.goto(f"{base}/#/chat", wait_until="domcontentloaded")
        notice = page.locator("#first-run-route-notice .route-notice")
        notice.wait_for(timeout=20_000)
        text = notice.inner_text()
        assert "Free starter model, hosted by OpenCode" in text and "leaves this computer" in text
        assert "Settings" in text and "AI model tab" in text
        assert page.locator("#first-run-ai-meta").inner_text() == "opencode/opencode/glm-flash-free", "tool-capable model first"
        assert "Set up my assistant" in page.locator("#first-run-submit").inner_text()
        assert not [e for e in watch.errors if "opencode" not in e.lower()], watch.errors
    finally:
        page.context.close()


@pytest.mark.parametrize("size", [(1440, 900), (360, 800)])
def test_the_notice_fits_at_desktop_and_phone_widths(browser, base, size):
    page, watch, _ = _page(browser, opencode=FREE, routes=[], size=size)
    try:
        page.goto(f"{base}/#/chat", wait_until="domcontentloaded")
        notice = page.locator("#first-run-route-notice .route-notice")
        notice.wait_for(timeout=20_000)
        box = notice.bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= size[0] + 0.5
        assert horizontal_overflow(page) == 0, size
    finally:
        page.context.close()


def test_a_model_on_this_computer_wins_and_carries_no_notice(browser, base):
    page, _, _ = _page(browser, opencode=FREE, routes=LOCAL)
    try:
        page.goto(f"{base}/#/chat", wait_until="domcontentloaded")
        page.locator("#first-run-ai-meta", has_text="ollama/llama3.2:3b").wait_for(timeout=20_000)
        assert page.locator("#first-run-route-notice .route-notice").count() == 0
    finally:
        page.context.close()


def test_the_quick_setup_names_the_model_and_keeps_the_notice_until_it_is_changed(browser, base):
    page, _, _ = _page(browser, opencode=FREE, routes=[])
    try:
        page.goto(f"{base}/#/chat", wait_until="domcontentloaded")
        page.locator("#first-run-route-notice .route-notice").wait_for(timeout=20_000)
        page.fill("#first-run-request", "Summarise my notes every Friday")
        page.click("#first-run-submit")
        summary = page.locator(".setup-quick-summary")
        summary.wait_for(timeout=20_000)
        assert "Uses the selected AI service: glm-flash-free" in summary.inner_text()
        assert page.locator(".setup-quick-summary").locator("xpath=preceding-sibling::aside[contains(@class,'route-notice')]").count() == 1
        assert page.locator("#setup-page-confirm").inner_text().strip() == "Create assistant", "one step, not four"
    finally:
        page.context.close()


def test_a_second_assistant_starts_where_the_main_one_works_and_asks_nothing_new(browser, tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    app = create_app()
    main = app.state.store.create_bot(Bot(name="juno", display_name="Juno", model="ollama/llama3.2:3b", tools=[]))
    app.state.store.set_workspace_coordinator(main.id)
    with serve(app) as url:
        page, _, seen = _page(browser, opencode=FREE, routes=[])
        try:
            page.goto(f"{url}/#/chat", wait_until="domcontentloaded")
            page.locator("#roster-list [data-switch-bot]").first.wait_for(timeout=20_000)
            page.evaluate("promptNewBot()")
            summary = page.locator(".setup-quick-summary")
            summary.wait_for(timeout=20_000)
            assert "Uses the selected AI service: llama3.2:3b" in summary.inner_text()
            assert page.locator(".route-notice").count() == 0
            assert "/api/v1/opencode/status" not in seen, "no detection when the main assistant already has a working route"
        finally:
            page.context.close()


def test_without_the_opencode_tool_first_run_says_what_to_install_and_offers_the_private_choice(browser, base):
    page, _, _ = _page(browser, opencode={"detail": "OpenCode CLI is not installed or is not on this device's PATH"}, routes=[], opencode_status=503)
    try:
        page.goto(f"{base}/#/chat", wait_until="domcontentloaded")
        copy = page.locator("#first-run-ai-state")
        copy.get_by_text("install the OpenCode command-line tool", exact=False).wait_for(timeout=20_000)
        assert "install Ollama" in copy.inner_text() and "connect a provider you already use" in copy.inner_text()
        assert page.locator("#first-run-route-notice .route-notice").count() == 0, "no route chosen, so no data-sharing notice"
        assert page.locator("#first-run-ai-retry").is_visible()
    finally:
        page.context.close()
