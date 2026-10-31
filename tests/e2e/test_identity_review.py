"""Reviewed identity: the person's profile and each assistant's boundaries are reviewed before saving.

The data is local JSON rendered into the prompt; this pins the surface only — the card appears in the
assistant's Behavior settings and in workspace Settings, the save goes through a confirmation that shows
the exact text, and the saved document comes back from the API with a new revision.
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
    app.state.store.create_bot(Bot(name="identity-bot", display_name="Identity Bot",
                                   model="ollama/llama3.2:3b", tools=[]))
    with serve(app) as url:
        yield url, app


def test_assistant_boundaries_are_reviewed_before_they_are_saved(browser, base):
    url, _ = base
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    watch = PageWatch(page)
    try:
        page.goto(f"{url}/#/bot/identity-bot", wait_until="domcontentloaded")
        page.get_by_role("tab", name="Behavior").click()
        card = page.locator("[data-identity-slot='assistant'] #identity-assistant-form")
        card.wait_for(timeout=20_000)
        assert "Identity and boundaries" in card.inner_text()
        card.locator("#identity-signature").fill("Done — reporting back.")
        card.locator("#identity-boundaries").fill("Never publish without review")
        card.get_by_role("button", name="Review and save identity").click()
        dialog = page.get_by_role("dialog")
        dialog.wait_for()
        assert "exact text" in dialog.inner_text() and "Never publish without review" in dialog.inner_text()
        dialog.get_by_role("button", name="Save identity").click()
        page.wait_for_function("""async () => {
          const response = await fetch("/api/v1/bots/identity-bot/identity");
          const body = await response.json();
          return body.identity.revision === 1 && body.identity.boundaries[0] === "Never publish without review";
        }""", timeout=20_000)
        assert "Never publish without review" in card.text_content()
        assert horizontal_overflow(page) == 0
        assert not watch.errors, watch.errors
    finally:
        page.context.close()


def test_the_person_profile_lives_in_settings_and_is_shared(browser, base):
    url, _ = base
    page = browser.new_context(viewport={"width": 390, "height": 844}).new_page()
    watch = PageWatch(page)
    try:
        page.goto(f"{url}/#/settings", wait_until="domcontentloaded")
        card = page.locator("[data-identity-slot='person'] #identity-person-form")
        card.wait_for(timeout=20_000)
        assert "every assistant" in card.inner_text()
        card.locator("#identity-preferred-name").fill("Kev")
        card.locator("#identity-about").fill("Builds local-first tools.")
        card.get_by_role("button", name="Review and save profile").click()
        dialog = page.get_by_role("dialog")
        dialog.wait_for()
        dialog.get_by_role("button", name="Save profile").click()
        page.wait_for_function("""async () => {
          const body = await (await fetch("/api/v1/identity/person")).json();
          return body.profile.revision === 1 && body.profile.preferred_name === "Kev";
        }""", timeout=20_000)
        assert horizontal_overflow(page) == 0
        assert not watch.errors, watch.errors
    finally:
        page.context.close()
