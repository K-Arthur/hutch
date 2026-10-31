"""Activity tells current failures and demo-era history apart (owner report R3).

The owner saw a mock-runtime "Failed" row under "Needs you" next to a schedule check. Legacy failures now
appear in their own section with a repair action, do not count as needs-you, and History labels them.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

pw = pytest.importorskip("playwright.sync_api")

from hutch.models import Bot, Run, RunStatus, iso, utcnow  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from tests.support.browser import launch_browser  # noqa: E402
from tests.support.live_app import PageWatch, serve  # noqa: E402


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
    retired = store.create_bot(Bot(name="research-briefing", display_name="Research Briefing",
                                   model="mock/demo", tools=[]))
    runnable = store.create_bot(Bot(name="repo-sweeper", display_name="Repo Sweeper",
                                    model="ollama/llama3.2:3b", tools=[]))
    created = iso(utcnow() - timedelta(days=5))
    store.create_run(Run(bot_id=retired.id, prompt="Weekly research briefing from the demo era",
                         status=RunStatus.failed, exit_reason="error",
                         error="The mock runtime was removed. Select a configured route.",
                         created_at=created, finished_at=created))
    store.create_run(Run(bot_id=runnable.id, prompt="Sweep the repository for TODOs",
                         status=RunStatus.failed, exit_reason="timeout", error="timed out",
                         created_at=created, finished_at=created))
    with serve(app) as url:
        yield url


def test_needs_you_counts_only_current_failures_and_legacy_has_its_own_section(browser, base):
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    watch = PageWatch(page)
    try:
        page.goto(f"{base}/#/activity", wait_until="domcontentloaded")
        needs = page.locator(".ov-col.loud")
        needs.wait_for(timeout=20_000)
        text = needs.inner_text()
        assert "Needs you" in text and "1" in text
        assert "Sweep the repository" in text
        assert "Weekly research briefing" not in text
        legacy = page.locator(".ov-col", has_text="Legacy runs")
        legacy.wait_for(timeout=20_000)
        assert "Weekly research briefing" in legacy.inner_text()
        assert "retired demo runtime" in legacy.inner_text()
        page.goto(f"{base}/#/activity/history", wait_until="domcontentloaded")
        legacy_card = page.locator(".run-card", has_text="Weekly research briefing").first
        legacy_card.wait_for(timeout=20_000)
        assert "Legacy" in legacy_card.inner_text()
        current_card = page.locator(".run-card", has_text="Sweep the repository").first
        assert "Legacy" not in current_card.inner_text()
        assert not watch.errors, watch.errors
    finally:
        page.context.close()
