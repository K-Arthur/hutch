"""The Models page leads with one honest authority: services, assistant routing, the default (S6a).

No hardware-first wall, no display-only preset fallback, no always-failing add option: the top of the page
answers which services can run work and which route each assistant uses, and links accounts to Apps & AI.
"""

from __future__ import annotations

import pytest

pw = pytest.importorskip("playwright.sync_api")

from hutch.models import Bot  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from tests.support.browser import launch_browser  # noqa: E402
from tests.support.live_app import PageWatch, horizontal_overflow, serve  # noqa: E402


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
    app = create_app()
    store = app.state.store
    store.create_bot(Bot(name="design-partner", display_name="Design Partner", model="demo", tools=[]))
    good = store.create_bot(Bot(name="repo-sweeper", display_name="Repo Sweeper",
                                model="ollama/llama3.2:3b", tools=[]))
    store.set_workspace_coordinator(good.id)
    with serve(app) as url:
        yield url


@pytest.mark.parametrize("width,height", [(1440, 900), (900, 1024), (360, 800)])
def test_models_leads_with_services_and_assistant_routing(browser, base, width, height):
    page = browser.new_context(viewport={"width": width, "height": height}).new_page()
    watch = PageWatch(page)
    try:
        page.goto(f"{base}/models", wait_until="domcontentloaded")
        authority = page.locator("#routes-authority")
        authority.wait_for(timeout=20_000)
        text = authority.inner_text()
        assert "AI services and assistant routing" in text
        assert "Design Partner" in text and "Needs a model route" in text
        assert "Repo Sweeper" in text and "Runnable" in text
        assert page.locator('#routes-authority a[href="/#/bot/design-partner"]').count() == 1
        assert "No default route for new built-in assistants" in text
        assert horizontal_overflow(page) == 0
        assert page.locator("text=Hosted fallback:").count() == 0
        assert page.locator('option[value="chatgpt"]').count() == 0
        assert not watch.errors, watch.errors
    finally:
        page.context.close()


def test_settings_names_the_single_default_writer_and_links_models(browser, base):
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    try:
        page.goto(f"{base}/#/settings", wait_until="domcontentloaded")
        page.locator("#workspace-settings-form").wait_for(timeout=20_000)
        text = page.locator(".workspace-settings-page").inner_text()
        assert "one place the new-assistant default is written" in text
        link = page.locator('.workspace-settings-page a[href="/models"]')
        assert link.count() == 1
        link.click()
        page.wait_for_url("**/models")
        page.locator("#routes-authority").wait_for(timeout=20_000)
    finally:
        page.context.close()
