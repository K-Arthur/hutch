"""An assistant that cannot run does not look healthy.

Roster status and the composer chip follow the server's `route_problem`: a retired demo route reads
"Needs a model route" and "Choose a model", while a real route keeps "Idle" and its model name.
Real server, real browser, no model call.
"""

from __future__ import annotations

import pytest

pw = pytest.importorskip("playwright.sync_api")

from hutch.models import Bot  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from tests.support.browser import launch_browser, wait_for_page  # noqa: E402
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
    app.state.store.create_bot(Bot(name="old-demo", display_name="Old Demo", model="mock/demo", tools=[]))
    app.state.store.create_bot(Bot(name="real-one", display_name="Real One", model="ollama/llama3.2:3b", tools=[]))
    with serve(app) as url:
        yield url


@pytest.mark.parametrize("size", [(1440, 900), (360, 800)])
def test_roster_and_chip_tell_the_truth(browser, base, size):
    page = browser.new_context(viewport={"width": size[0], "height": size[1]}).new_page()
    watch = PageWatch(page)
    try:
        page.goto(f"{base}/#/chat/old-demo", wait_until="domcontentloaded")
        page.locator(".ms-btn").wait_for(timeout=20_000)
        assert page.locator(".ms-label").inner_text().strip() == "Choose a model"
        if size[0] > 900:
            row = page.locator(".roster-list a, .roster-list button, .roster-list [data-bot]").filter(has_text="Old Demo").first
            row.wait_for()
            assert "Needs a model route" in row.inner_text() and "Idle" not in row.inner_text()
            other = page.locator(".roster-list a, .roster-list button, .roster-list [data-bot]").filter(has_text="Real One").first
            assert "Idle" in other.inner_text() and "Needs a model route" not in other.inner_text()
        page.goto(f"{base}/#/chat/real-one", wait_until="domcontentloaded")
        page.locator(".ms-btn").wait_for(timeout=20_000)
        wait_for_page(page, "!!document.querySelector('.ms-label') && document.querySelector('.ms-label').textContent.includes('llama3.2')", timeout=20_000)
        assert horizontal_overflow(page) == 0
        assert not watch.errors, watch.errors
    finally:
        page.context.close()


def test_choosing_a_real_model_for_the_next_message_replaces_the_prompt(browser, base):
    """The chip only says "Choose a model" while the selected route is the broken saved one."""
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    try:
        page.goto(f"{base}/#/chat/old-demo", wait_until="domcontentloaded")
        page.locator(".ms-btn").click()
        items = page.locator(".ms-item")
        items.first.wait_for(timeout=20_000)
        real = page.locator(".ms-item[data-spec^='ollama/'], .ms-item[data-spec^='openai/'], .ms-item[data-spec^='opencode/']")
        if real.count() == 0:
            pytest.skip("no real route is offered by this host to choose")
        real.first.click()
        wait_for_page(page, "!!document.querySelector('.ms-label') && document.querySelector('.ms-label').textContent.trim() !== 'Choose a model'", timeout=20_000)
    finally:
        page.context.close()


def test_the_empty_chat_of_an_unusable_assistant_explains_and_offers_the_two_real_actions(browser, base):
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    try:
        page.goto(f"{base}/#/chat/old-demo", wait_until="domcontentloaded")
        notice = page.locator(".welcome-problem")
        notice.wait_for(timeout=20_000)
        assert "can't run yet" in notice.inner_text() and "retired demo route" in notice.inner_text()
        assert notice.get_by_role("link", name="Choose a model route").get_attribute("href") == "#/bot/old-demo"
        assert notice.get_by_role("link", name="Remove assistant").get_attribute("href") == "/bots/old-demo/delete"
        page.goto(f"{base}/#/chat/real-one", wait_until="domcontentloaded")
        page.locator(".welcome h2", has_text="Real One").wait_for(timeout=20_000)
        assert page.locator(".welcome-problem").count() == 0
    finally:
        page.context.close()


def test_setup_names_the_main_assistant_only_for_the_first_one(browser, tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state-empty"))
    with serve(create_app()) as empty_base:
        page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
        try:
            page.goto(f"{empty_base}/#/assistant/new", wait_until="domcontentloaded")
            note = page.locator(".setup-main-note")
            note.wait_for(timeout=20_000)
            assert "main assistant" in note.inner_text()
        finally:
            page.context.close()


def test_setup_has_no_main_note_once_an_assistant_exists(browser, base):
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    try:
        page.goto(f"{base}/#/assistant/new", wait_until="domcontentloaded")
        page.locator("#setup-purpose, #setup-display_name").first.wait_for(timeout=20_000)
        assert page.locator(".setup-main-note").count() == 0
    finally:
        page.context.close()
