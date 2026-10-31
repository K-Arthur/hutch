"""The first request carries honest guidance instead of invented prompt buttons (A8).

Two surfaces: the first-run request form explains what a useful request contains, and the empty-chat
welcome says the same thing where the person writes their first message. Copy only; no example prompt.
"""

from __future__ import annotations

import pytest

pw = pytest.importorskip("playwright.sync_api")

from hutch.models import Bot  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from tests.support.artifacts import artifact_path  # noqa: E402
from tests.support.browser import launch_browser  # noqa: E402
from tests.support.live_app import PageWatch, horizontal_overflow, serve  # noqa: E402

GUIDANCE = ("Say what you want to end up with, where to look, what to avoid, what to hand back, "
            "and when to stop and ask.")
ONBOARDING = ("A useful request names the outcome you want, where to look, what to avoid, what to hand "
              "back, and when the assistant should stop and ask you.")


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
    app.state.store.create_bot(Bot(name="guide-bot", display_name="Guide Bot",
                                   model="ollama/llama3.2:3b", tools=[]))
    with serve(app) as url:
        yield url


def test_the_first_run_form_explains_a_useful_request(browser, base):
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    watch = PageWatch(page)
    try:
        page.goto(f"{base}/onboarding", wait_until="domcontentloaded")
        guidance = page.locator("#request-guidance")
        guidance.wait_for(timeout=20_000)
        assert guidance.inner_text() == ONBOARDING
        textarea = page.locator("#request")
        assert "request-guidance" in (textarea.get_attribute("aria-describedby") or "")
        out = artifact_path("first-request-guidance")
        out.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out / "onboarding-1440.png"), animations="disabled")
        assert not watch.errors, watch.errors
    finally:
        page.context.close()


@pytest.mark.parametrize("width,height", [(1440, 900), (360, 800)])
def test_the_empty_chat_says_what_a_useful_first_message_contains(browser, base, width, height):
    page = browser.new_context(viewport={"width": width, "height": height}).new_page()
    watch = PageWatch(page)
    try:
        page.goto(f"{base}/#/chat/guide-bot", wait_until="domcontentloaded")
        guide = page.locator(".welcome-guide")
        guide.wait_for(timeout=20_000)
        assert guide.inner_text() == GUIDANCE
        assert horizontal_overflow(page) == 0
        assert not watch.errors, watch.errors
    finally:
        page.context.close()
