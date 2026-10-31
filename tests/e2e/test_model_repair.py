"""An assistant that cannot run is moved onto a model that can, with the cost said and the person's yes (owner report).

The report: with OpenCode installed the picker listed only hosted models that all said "needs setup", with no OpenCode
models and no way to add a provider, and assistants left on the removed demo route stayed broken. Real server and
browser; the OpenCode catalogue is a labelled fixture (the live run against the real OpenCode CLI is recorded in the
release checklist). Nothing is saved until the confirmation dialog is accepted.
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit

import pytest

pw = pytest.importorskip("playwright.sync_api")

from hutch import modelchoices  # noqa: E402
from hutch.models import Bot, RuntimeKind  # noqa: E402
from hutch.modelchoices import Choice  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from tests.support.browser import launch_browser  # noqa: E402
from tests.support.live_app import PageWatch, serve  # noqa: E402

CATALOGUE = [("opencode/opencode/plain-free", "Plain Free", 128000, []), ("opencode/opencode/glm-flash-free", "GLM Flash Free", 64000, ["toolcall"])]
STATUS = {"ready": True, "authenticated": False, "integrations": [], "version": "fixture", "models": [
    {"spec": spec, "provider_id": "opencode", "model_id": spec.split("/")[-1], "name": name, "context": ctx, "output": 0, "capabilities": caps}
    for spec, name, ctx, caps in CATALOGUE]}


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as playwright:
        b = launch_browser(playwright)
        yield b
        b.close()


@pytest.fixture()
def live(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    monkeypatch.setattr(modelchoices, "_opencode_choices", lambda config, bot: [
        Choice(spec=spec, label=name, group="OpenCode · opencode", state="ready", hosted=True, runtime="opencode", note="OpenCode-managed account")
        for spec, name, _ctx, _caps in CATALOGUE])
    app = create_app()
    store = app.state.store
    store.create_bot(Bot(name="tidy-downloads", display_name="Tidy Downloads", model="mock/demo", tools=[]))
    store.create_bot(Bot(name="steady", display_name="Steady", model="ollama/llama3.2:3b", tools=[]))
    with serve(app) as url:
        yield url, store


def _page(browser, size=(1280, 860)):
    context = browser.new_context(viewport={"width": size[0], "height": size[1]})

    def handle(route):
        path = urlsplit(route.request.url).path
        if path == "/api/v1/opencode/status":
            route.fulfill(status=200, content_type="application/json", body=json.dumps(STATUS))
        elif path == "/api/v1/model-routes":
            route.fulfill(status=200, content_type="application/json", body="[]")
        else:
            route.continue_()
    context.route("**/api/v1/**", handle)
    page = context.new_page()
    return page, PageWatch(page)


def _dialog(page):
    return page.locator("dialog[open]")


def test_the_cant_run_notice_offers_the_best_model_and_saves_it_only_when_confirmed(browser, live):
    base, store = live
    page, watch = _page(browser)
    try:
        page.goto(f"{base}/#/chat/tidy-downloads", wait_until="domcontentloaded")
        offer = page.locator(".welcome-problem button.btn.primary")
        offer.wait_for(timeout=20_000)
        assert offer.inner_text() == "Use GLM Flash Free", "the tool-capable model leads"
        offer.click()
        dialog = _dialog(page)
        dialog.wait_for()
        text = dialog.inner_text()
        assert "Free starter model, hosted by OpenCode" in text and "leaves this computer" in text
        assert "moves it to the OpenCode runtime" in text
        dialog.locator("#modal-cancel").click()
        assert store.get_bot("tidy-downloads").model == "mock/demo", "backing out saves nothing"
        offer.click()
        _dialog(page).locator("#modal-confirm").click()
        for _ in range(40):
            if store.get_bot("tidy-downloads").runtime is RuntimeKind.opencode:
                break
            page.wait_for_timeout(250)
        saved = store.get_bot("tidy-downloads")
        assert saved.runtime is RuntimeKind.opencode and saved.model == "opencode/opencode/glm-flash-free"
        page.locator(".welcome-problem").wait_for(state="detached", timeout=10_000)
        assert page.locator(".ms-btn").inner_text().strip() == "glm-flash-free", "the chip names the model, not the route"
        assert not [e for e in watch.errors if "opencode" not in e.lower()], watch.errors
    finally:
        page.context.close()


def test_the_picker_leads_with_what_can_run_offers_a_provider_link_and_saves_on_confirm(browser, live):
    base, store = live
    page, _ = _page(browser)
    try:
        page.goto(f"{base}/#/chat/tidy-downloads", wait_until="domcontentloaded")
        page.locator(".ms-btn").click()
        page.locator(".ms-more").click()
        page.locator(".ms-row").first.wait_for(timeout=20_000)
        assert page.locator('.ms-chip[data-filter="ready"]').get_attribute("aria-pressed") == "true", "lead with ready models"
        first = page.locator(".ms-row:visible").first.inner_text()
        assert "Plain Free" in first or "GLM Flash Free" in first
        assert page.locator(".ms-row:visible", has_text="needs setup").count() == 0
        assert page.locator(".ms-add-provider").is_visible()
        assert page.locator("#modal-confirm").inner_text() == "Use this model"
        page.locator('.ms-row:has(input[value="opencode/opencode/plain-free"])').click()
        page.locator("#modal-confirm").click()
        confirm = page.locator("dialog[open]:has-text('Free starter model')")      # the picker dialog may still be closing
        confirm.wait_for(timeout=10_000)
        assert store.get_bot("tidy-downloads").model == "mock/demo", "choosing is not saving"
        confirm.locator("#modal-confirm").click()
        for _ in range(40):
            if store.get_bot("tidy-downloads").model == "opencode/opencode/plain-free":
                break
            page.wait_for_timeout(250)
        assert store.get_bot("tidy-downloads").runtime is RuntimeKind.opencode
    finally:
        page.context.close()


def test_a_model_from_another_runtime_is_asked_about_not_silently_applied(browser, live):
    """A working assistant choosing an OpenCode model must confirm the runtime change, never send it as a one-message override."""
    base, store = live
    page, _ = _page(browser)
    try:
        page.goto(f"{base}/#/chat/steady", wait_until="domcontentloaded")
        page.locator(".ms-btn").click()
        page.locator(".ms-more").click()
        page.locator('.ms-row:has(input[value="opencode/opencode/glm-flash-free"])').wait_for(timeout=20_000)
        page.locator('.ms-row:has(input[value="opencode/opencode/glm-flash-free"])').click()
        page.locator("#modal-confirm").click()
        confirm = page.locator("dialog[open]:has-text('moves it to the OpenCode runtime')")
        confirm.wait_for(timeout=10_000)
        confirm.locator("#modal-cancel").click()
        steady = store.get_bot("steady")
        assert steady.runtime is RuntimeKind.builtin and steady.model == "ollama/llama3.2:3b"
    finally:
        page.context.close()
