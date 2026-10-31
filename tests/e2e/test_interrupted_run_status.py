"""A run that stopped because its process disappeared reads "Interrupted", not "Failed".

The engine already records `exit_reason: interrupted` when nothing owns a live run any more (S8). The
chip used to keep saying "Failed", which reads as the assistant's or the person's mistake instead of an
open-ended stop. The word is now derived from that recorded reason in the transcript, Activity rows,
result cards and Task details, while a plain failure keeps "Failed". Real server, real browser.
"""

from __future__ import annotations

import pytest

pw = pytest.importorskip("playwright.sync_api")

from hutch.models import Bot, Run, RunStatus, iso, utcnow  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from tests.support.browser import launch_browser, wait_for_page  # noqa: E402
from tests.support.live_app import serve  # noqa: E402


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
    bot = store.create_bot(Bot(name="interrupted-check", display_name="Checkpoint Keeper",
                               model="ollama/llama3.2:3b", tools=[]))
    interrupted = store.create_run(Run(
        bot_id=bot.id, prompt="tidy the downloads folder", status=RunStatus.failed,
        exit_reason="interrupted", error="the process running this job exited before it finished",
        finished_at=iso(utcnow())))
    failed = store.create_run(Run(
        bot_id=bot.id, prompt="send the weekly note", status=RunStatus.failed,
        exit_reason="error", error="the provider refused the request", finished_at=iso(utcnow())))
    with serve(app) as url:
        yield url, interrupted.id, failed.id


def _chip(page):
    chip = page.locator(".ctx-meta .status")
    chip.wait_for(timeout=20_000)
    return chip


def test_task_details_and_history_say_interrupted_not_failed(browser, base):
    url, interrupted_id, failed_id = base
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    try:
        page.goto(f"{url}/#/run/{interrupted_id}", wait_until="domcontentloaded")
        chip = _chip(page)
        wait_for_page(page, "document.querySelector('.ctx-meta .status')?.classList.contains('interrupted')")
        assert chip.inner_text().strip() == "Interrupted"
        classes = chip.get_attribute("class") or ""
        assert "failed" in classes and "interrupted" in classes       # shape keeps the failure vocabulary

        page.goto(f"{url}/#/activity/history", wait_until="domcontentloaded")
        card = page.locator(".run-card").filter(has_text="tidy the downloads folder").first
        card.wait_for(timeout=20_000)
        assert card.locator(".status").inner_text().strip() == "Interrupted"

        plain = page.locator(".run-card").filter(has_text="send the weekly note").first
        plain.wait_for(timeout=20_000)
        assert plain.locator(".status").inner_text().strip() == "Failed"
    finally:
        page.context.close()


def test_the_word_holds_on_a_phone_width(browser, base):
    """The header hides its chips on a phone, so the history row is where the word must still hold."""
    url, _, _ = base
    page = browser.new_context(viewport={"width": 360, "height": 800}).new_page()
    try:
        page.goto(f"{url}/#/activity/history", wait_until="domcontentloaded")
        card = page.locator(".run-card").filter(has_text="tidy the downloads folder").first
        card.wait_for(timeout=20_000)
        assert card.locator(".status").inner_text().strip() == "Interrupted"
        assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
    finally:
        page.context.close()
