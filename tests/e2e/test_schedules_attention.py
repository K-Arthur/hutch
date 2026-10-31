"""Scheduled work says why the last run did not succeed, from persisted rows.

A real local server and a real browser read one assistant's schedule, one claimed
window and one failed run. Nothing here calls a model, and the page is the shipped
one: the assertion is that the failure and its reason are visible, not that a
fixture exists.
"""

from __future__ import annotations

import pytest

pw = pytest.importorskip("playwright.sync_api")

from playwright.sync_api import expect  # noqa: E402

from hutch.models import Bot, CatchUpPolicy, Run, RunStatus, Schedule, iso, utcnow  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from tests.support.browser import launch_browser  # noqa: E402
from tests.support.live_app import PageWatch, horizontal_overflow, serve  # noqa: E402
from tests.e2e.settings_pane import open_assistant_customization  # noqa: E402

VIEWPORTS = ((1440, 900), (834, 1000), (390, 844), (320, 720))


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as playwright:
        b = launch_browser(playwright)
        yield b
        b.close()


def _seed(app) -> Bot:
    """One routine whose last claimed window produced a failed run."""
    store = app.state.store
    now = utcnow()
    bot = store.create_bot(Bot(
        name="release-watch", display_name="Release Watch", tools=[],
        schedule=Schedule(name="Nightly release check", cron="0 3 * * *", timezone="UTC",
                          catch_up=CatchUpPolicy.coalesce, prompt="Check the release feed."),
        created_at=iso(now),
    ))
    # A current marker means no window is due while the live server runs.
    store.kv_set(f"{bot.schedule.id}:last_fire", iso(now))
    run = store.create_run(Run(
        bot_id=bot.id, prompt="Check the release feed.", origin="schedule",
        schedule_id=bot.schedule.id, status=RunStatus.failed, exit_reason="model_unavailable",
        missed_windows=1, created_at=iso(now), finished_at=iso(now),
    ))
    # The occurrence row the page reads. Its production writer is submit_scheduled and is
    # covered by tests/test_schedule_outcomes.py; this test's subject is the presentation.
    with store._tx() as db:
        db.execute(
            "INSERT INTO schedule_occurrences_v20 (schedule_id, occurrence, bot_id, run_id, claimed_at, claimed_by) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (bot.schedule.id, iso(now), bot.id, run.id, iso(now), "browser-test"))
    return bot


@pytest.fixture()
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    _seed(app)
    with serve(app) as url:
        yield url


def test_the_last_run_and_its_reason_are_on_the_scheduled_work_row(browser, base):
    context = browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
    page = context.new_page()
    watch = PageWatch(page)
    try:
        page.goto(f"{base}/#/schedules", wait_until="domcontentloaded")
        row = page.locator(".schedule-overview-row").first
        row.wait_for(timeout=20_000)

        last = row.locator(".schedule-last-attention")
        expect(last).to_be_visible()
        expect(last).to_contain_text("Last run")
        expect(last).to_contain_text("failed")
        expect(last).to_contain_text("model unavailable")
        expect(last).to_contain_text("1 missed window covered")
        expect(row.locator("a", has_text="open run")).to_be_visible()

        note = page.locator(".schedule-attention-note")
        expect(note).to_be_visible()
        expect(note).to_contain_text("1 recurring task needs attention")
        assert watch.errors == [], watch.errors
    finally:
        context.close()


def test_a_failed_run_is_distinguishable_on_every_viewport(browser, base):
    for width, height in VIEWPORTS:
        context = browser.new_context(viewport={"width": width, "height": height}, reduced_motion="reduce")
        page = context.new_page()
        watch = PageWatch(page)
        try:
            page.goto(f"{base}/#/schedules", wait_until="domcontentloaded")
            page.locator(".schedule-overview-row").first.wait_for(timeout=20_000)
            expect(page.locator(".schedule-last-attention").first).to_be_visible()
            expect(page.locator(".schedule-attention-note")).to_be_visible()
            assert horizontal_overflow(page) <= 1, (width, horizontal_overflow(page))
            assert watch.errors == [], (width, watch.errors)
        finally:
            context.close()


def test_the_bot_page_history_shows_the_same_outcome(browser, base):
    context = browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
    page = context.new_page()
    watch = PageWatch(page)
    try:
        page.goto(f"{base}/#/bot/release-watch", wait_until="domcontentloaded")
        open_assistant_customization(page, "schedule")
        page.locator("#form-schedule").wait_for(timeout=20_000)
        entry = page.locator("details.schedule-entry").first
        if not entry.evaluate("el => el.open"):
            entry.locator("summary").first.click()
        entry.locator("[data-schedule-advanced-toggle]").click()
        history = entry.locator("[data-show-occurrences]").first
        history.wait_for(timeout=20_000)
        history.click()
        entry = page.locator(".schedule-occurrence-attention").first
        expect(entry).to_be_visible()
        expect(entry).to_contain_text("failed")
        expect(entry).to_contain_text("model unavailable")
        assert watch.errors == [], watch.errors
    finally:
        context.close()
