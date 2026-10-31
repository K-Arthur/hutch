"""The main assistant's suggestions are visible, reviewable and never created for the person (references: Grok Bot, OpenClaw).

Real server and browser. A suggestion is seeded the way the tool records it; the tool itself, its main-assistant-only gating and its
cap are covered in tests/test_assistant_proposals.py. Here: it shows in the sidebar, "Set up" opens the normal setup with the name and
job filled in (nothing created yet), "Not now" dismisses it, and creating the assistant makes the suggestion go away by itself.
"""

from __future__ import annotations

import pytest

pw = pytest.importorskip("playwright.sync_api")
expect = pw.expect

from hutch import proposals  # noqa: E402
from hutch.models import Bot  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from tests.support.browser import launch_browser  # noqa: E402
from tests.support.live_app import horizontal_overflow, serve  # noqa: E402

JOB = "Own my weekly research briefing: collect sources, summarise what changed, hand back one page."


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
    app = create_app()
    store = app.state.store
    main = store.create_bot(Bot(name="juno", display_name="Juno", model="ollama/llama3.2:3b", tools=[]))
    store.set_workspace_coordinator(main.id)
    proposals.propose(store, name="Research Briefing", job=JOB, why="It recurs every week.", from_bot_id=main.id)
    with serve(app) as url:
        yield url, store


def test_the_suggestion_shows_with_who_made_it_and_creates_nothing(browser, live):
    base, store = live
    page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    try:
        page.goto(f"{base}/#/chat/juno", wait_until="domcontentloaded")
        block = page.locator("#proposals-slot:not([hidden])")
        block.wait_for(timeout=20_000)
        expect(block).to_contain_text("Suggested by Juno", timeout=10_000)       # named once the roster has loaded
        text = block.inner_text()
        assert "Research Briefing" in text and "collect sources" in text and "It recurs every week." in text
        assert [bot.name for bot in store.list_bots()] == ["juno"], "a suggestion is not an assistant"
    finally:
        page.context.close()


def test_set_up_opens_the_normal_setup_with_the_name_and_job_filled_in(browser, live):
    base, store = live
    page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    try:
        page.goto(f"{base}/#/chat/juno", wait_until="domcontentloaded")
        page.locator("[data-proposal-open]").click()
        expect(page.locator("#setup-display_name")).to_have_value("Research Briefing", timeout=20_000)
        assert "collect sources" in page.locator("#setup-purpose").input_value() or "collect sources" in page.locator("body").inner_text()
        assert [bot.name for bot in store.list_bots()] == ["juno"], "nothing exists until the person creates it"
        page.locator("#setup-page-confirm").click()
        for _ in range(60):
            if len(store.list_bots()) == 2:
                break
            page.wait_for_timeout(250)
        made = [bot for bot in store.list_bots() if bot.name != "juno"]
        assert len(made) == 1 and made[0].display_name == "Research Briefing" and made[0].name == "research-briefing"
        assert made[0].model == "ollama/llama3.2:3b", "it starts on the main assistant's route"
        assert proposals.pending(store) == [], "creating it resolves the suggestion"
        assert store.workspace_coordinator_id() != made[0].id, "a second assistant never takes the main role"
    finally:
        page.context.close()


def test_not_now_dismisses_it_and_the_block_goes_away(browser, live):
    base, store = live
    page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    try:
        page.goto(f"{base}/#/chat/juno", wait_until="domcontentloaded")
        page.locator("[data-proposal-dismiss]").click()
        page.locator("#proposals-slot[hidden]").wait_for(state="attached", timeout=10_000)
        assert proposals.pending(store) == [] and [bot.name for bot in store.list_bots()] == ["juno"]
    finally:
        page.context.close()


def test_the_block_fits_a_phone(browser, live):
    base, _ = live
    page = browser.new_context(viewport={"width": 360, "height": 800}).new_page()
    try:
        page.goto(f"{base}/#/chat/juno", wait_until="domcontentloaded")
        page.locator("#nav-toggle, .app-menu-btn, [aria-controls='primary-nav']").first.click(timeout=3000)
    except Exception:
        pass
    try:
        assert horizontal_overflow(page) == 0
    finally:
        page.context.close()
