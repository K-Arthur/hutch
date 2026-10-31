"""An installation from an earlier version is recognised and reviewed, not ignored (owner report R4).

A non-empty/legacy state shows one small header control ("Review install") on any browser; it opens a
read-only review with the real actions. Recording the review writes one marker, changes nothing else, and
the control disappears. A new browser gets a one-time "Welcome back" instead; a fresh install keeps its
first-run onboarding and shows neither.
"""

from __future__ import annotations

import json
import urllib.request
from datetime import timedelta

import pytest

pw = pytest.importorskip("playwright.sync_api")

from hutch.models import Bot, Run, RunStatus, iso, utcnow  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from tests.support.browser import launch_browser  # noqa: E402
from tests.support.live_app import PageWatch, horizontal_overflow, serve  # noqa: E402


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as playwright:
        b = launch_browser(playwright)
        yield b
        b.close()


def _legacy_state(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    app = create_app()
    store = app.state.store
    bot = store.create_bot(Bot(name="research-briefing", display_name="Research Briefing",
                               model="mock/demo", tools=[]))
    created = iso(utcnow() - timedelta(days=5))
    store.create_run(Run(bot_id=bot.id, prompt="Weekly research briefing from the demo era",
                         status=RunStatus.failed, exit_reason="error",
                         error="The mock runtime was removed.", created_at=created, finished_at=created))
    return app


@pytest.fixture()
def legacy(tmp_path, monkeypatch):
    with serve(_legacy_state(tmp_path, monkeypatch)) as url:
        yield url


@pytest.fixture()
def clean(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    app = create_app()
    bot = app.state.store.create_bot(Bot(name="repo-sweeper", display_name="Repo Sweeper",
                                        model="ollama/llama3.2:3b", tools=[]))
    app.state.store.set_workspace_coordinator(bot.id)
    with serve(app) as url:
        yield url


@pytest.fixture()
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    with serve(create_app()) as url:
        yield url


def _installation(base):
    with urllib.request.urlopen(base + "/api/v1/installation", timeout=30) as response:
        return json.loads(response.read().decode())


def test_a_legacy_installation_is_reviewed_once_and_nothing_is_deleted(browser, legacy):
    state = _installation(legacy)
    assert state["state"] == "needs_review" and state["review_required"] is True
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    watch = PageWatch(page)
    try:
        page.goto(f"{legacy}/#/chat/research-briefing", wait_until="domcontentloaded")
        review = page.locator("#installation-review")
        review.wait_for(timeout=20_000)
        assert "Review install" in review.inner_text()
        review.click()
        dialog = page.get_by_role("dialog")
        dialog.wait_for()
        text = dialog.inner_text()
        assert "Review this installation" in text
        assert "Research Briefing" in text and "Choose a model route" in text and "Remove assistant" in text
        assert "Nothing is deleted, rewritten, sent or closed" in text
        dialog.get_by_role("button", name="This looks right — continue").click()
        page.wait_for_function("() => !document.querySelector('#installation-review')", timeout=20_000)
        assert _installation(legacy)["state"] == "ready"
        page.reload(wait_until="domcontentloaded")
        page.locator("#chat-prompt").wait_for(timeout=20_000)
        assert page.locator("#installation-review").count() == 0
        assert not watch.errors, watch.errors
    finally:
        page.context.close()


@pytest.mark.parametrize("width,height", [(900, 1024), (360, 800)])
def test_the_review_holds_at_narrow_widths(browser, legacy, width, height):
    page = browser.new_context(viewport={"width": width, "height": height}).new_page()
    watch = PageWatch(page)
    try:
        page.goto(f"{legacy}/#/chat/research-briefing", wait_until="domcontentloaded")
        review = page.locator("#installation-review")
        review.wait_for(timeout=20_000)
        review.click()
        dialog = page.get_by_role("dialog")
        dialog.wait_for()
        box = dialog.bounding_box()
        assert box and box["x"] >= 0 and box["x"] + box["width"] <= width + 1
        assert horizontal_overflow(page) == 0
        assert not watch.errors, watch.errors
    finally:
        page.context.close()


def test_a_new_browser_gets_a_one_time_welcome_back(browser, clean):
    assert _installation(clean)["state"] == "ready"
    first = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    try:
        first.goto(f"{clean}/#/chat/repo-sweeper", wait_until="domcontentloaded")
        welcome = first.locator("#installation-welcome")
        welcome.wait_for(timeout=20_000)
        assert "Welcome back" in welcome.inner_text()
        welcome.click()
        dialog = first.get_by_role("dialog")
        dialog.wait_for()
        assert "has not seen this Hutch before" in dialog.inner_text()
        assert "1 assistant" in dialog.inner_text()
        dialog.get_by_role("button", name="Continue to this Hutch").click()
        first.wait_for_function("() => !document.querySelector('#installation-welcome')", timeout=20_000)
        first.reload(wait_until="domcontentloaded")
        first.locator("#chat-prompt").wait_for(timeout=20_000)
        assert first.locator("#installation-welcome").count() == 0
    finally:
        first.context.close()
    # A genuinely new browser context has no local marker: it is welcomed once more, never blocked.
    second = browser.new_context(viewport={"width": 900, "height": 900}).new_page()
    try:
        second.goto(f"{clean}/#/activity", wait_until="domcontentloaded")
        second.locator("#installation-welcome").wait_for(timeout=20_000)
    finally:
        second.context.close()


def test_a_fresh_install_keeps_first_run_and_shows_no_review(browser, fresh):
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    watch = PageWatch(page)
    try:
        page.goto(f"{fresh}/#/chat", wait_until="domcontentloaded")
        page.locator("#first-run-request, #chat-prompt").first.wait_for(timeout=20_000)
        page.wait_for_timeout(1500)
        assert page.locator("#installation-review").count() == 0
        assert page.locator("#installation-welcome").count() == 0
        assert _installation(fresh)["state"] == "fresh"
        assert not watch.errors, watch.errors
    finally:
        page.context.close()


def test_the_settings_card_shows_the_installation_state(browser, legacy):
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    try:
        page.goto(f"{legacy}/#/settings", wait_until="domcontentloaded")
        card = page.locator('[data-installation-slot="settings"] section')
        card.wait_for(timeout=20_000)
        text = card.inner_text()
        assert "Installation" in text and "items need review" in text
        card.get_by_role("button", name="Review installation").click()
        page.get_by_role("dialog").wait_for()
        page.get_by_role("button", name="Cancel").click()
    finally:
        page.context.close()
