"""Scheduled work: roll call, attention filter, history and policy in a real browser.

The test uses a real FastAPI server, a real SQLite state directory and the shipped
dashboard. Seeded rows are test state in a temporary directory, never product data.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

pw = pytest.importorskip("playwright.sync_api")

from playwright.sync_api import expect  # noqa: E402

from hutch.engine import Engine  # noqa: E402
from hutch.models import Bot, Run, RunStatus, Schedule, iso, utcnow  # noqa: E402
from hutch.schedule_policy import put_policy  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from tests.support.browser import launch_browser  # noqa: E402
from tests.support.live_app import PageWatch, horizontal_overflow, serve  # noqa: E402

VIEWPORTS = ((360, 800), (768, 1024), (1280, 800), (1920, 1080))


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as playwright:
        instance = launch_browser(playwright)
        yield instance
        instance.close()


def _seed(app) -> None:
    store = app.state.store
    now = utcnow()

    failed_bot = store.create_bot(Bot(
        name="release-watch", display_name="Release Watch", tools=[],
        schedule=Schedule(name="Nightly release check", cron="0 3 * * *", timezone="UTC",
                          enabled=False, prompt="Check releases."),
    ))
    store.put_schedule(failed_bot.id, Schedule(
        id=failed_bot.schedule.id, name="Nightly release check", cron="0 4 * * *",
        timezone="UTC", enabled=False, prompt="Check the release feed.",
    ))
    failed_run = store.create_run(Run(
        bot_id=failed_bot.id, prompt="Check releases.", origin="schedule",
        schedule_id=failed_bot.schedule.id, status=RunStatus.failed,
        exit_reason="model_unavailable", missed_windows=1,
        created_at=iso(now - timedelta(hours=1)), finished_at=iso(now - timedelta(hours=1)),
    ))
    with store._tx() as db:
        db.execute(
            "INSERT INTO schedule_occurrences_v20 "
            "(schedule_id, occurrence, bot_id, run_id, claimed_at, claimed_by) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (failed_bot.schedule.id, iso(now - timedelta(hours=1)), failed_bot.id,
             failed_run.id, iso(now - timedelta(hours=1)), "browser-test"),
        )

    approval_bot = store.create_bot(Bot(
        name="approval-watch", display_name="Approval Watch", tools=[],
        schedule=Schedule(name="Morning approval check", cron="0 3 * * *", timezone="UTC",
                          prompt="Check the morning queue."),
    ))
    store.kv_set(f"{approval_bot.schedule.id}:last_fire", iso(now - timedelta(days=1)))
    put_policy(store, approval_bot.id, approval_bot.schedule.id, approval_required=True, conditions=[])
    Engine(store.config, store).scheduler_claims()

    healthy = store.create_bot(Bot(
        name="healthy-watch", display_name="Healthy Watch", tools=[],
        schedule=Schedule(name="Healthy routine", cron="0 5 * * *", timezone="UTC",
                          prompt="Check the healthy queue."),
    ))
    store.kv_set(f"{healthy.schedule.id}:last_fire", iso(now))


@pytest.fixture()
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    _seed(app)
    with serve(app) as url:
        yield url


def test_roll_call_filter_and_keyboard_history(browser, base):
    context = browser.new_context(viewport={"width": 1280, "height": 900},
                                  color_scheme="dark", reduced_motion="reduce")
    page = context.new_page()
    watch = PageWatch(page)
    try:
        page.goto(f"{base}/#/schedules", wait_until="domcontentloaded")
        page.locator(".schedule-overview-row").first.wait_for(timeout=20_000)
        roll = page.locator(".schedule-roll-call")
        roll.wait_for(timeout=20_000)
        expect(roll).to_contain_text("Fleet roll call")
        expect(roll).to_contain_text("Pending approvals")
        expect(roll).to_contain_text("Failed last 24h")
        expect(roll).to_contain_text("Next due")

        toggle = page.locator("#schedule-attention-only")
        expect(toggle).to_be_enabled()
        toggle.check()
        expect(page.locator(".schedule-overview-row:visible")).to_have_count(2)
        toggle.uncheck()
        expect(page.locator(".schedule-overview-row:visible")).to_have_count(3)

        row = page.locator(".schedule-overview-row", has_text="Release Watch")
        summary = row.locator(".schedule-history > summary")
        summary.focus()
        page.keyboard.press("Enter")
        body = row.locator(".schedule-history-body")
        body.wait_for(timeout=20_000)
        expect(body).to_contain_text("Recent runs")
        expect(body).to_contain_text("Schedule changes")
        expect(body).to_contain_text("cron")
        expect(body).to_contain_text("Created")
        expect(body).to_contain_text("value hidden")
        expect(body).not_to_contain_text("Check releases.")
        expect(body).not_to_contain_text("Check the release feed.")
        expect(row.locator("[data-schedule-approval]")).to_be_visible()
        expect(row.locator("[data-schedule-approval]")).not_to_be_checked()

        approval_row = page.locator(".schedule-overview-row", has_text="Approval Watch")
        approval_row.locator(".schedule-history > summary").focus()
        page.keyboard.press("Enter")
        expect(approval_row.locator(".schedule-history-body")).to_contain_text("Ask before each run")
        expect(approval_row.locator("[data-schedule-approval]")).to_be_checked()

        assert watch.errors == [], watch.errors
    finally:
        context.close()


def test_policy_toggle_saves_against_the_real_api(browser, base):
    context = browser.new_context(viewport={"width": 1280, "height": 900},
                                  color_scheme="dark", reduced_motion="reduce")
    page = context.new_page()
    watch = PageWatch(page)
    try:
        page.goto(f"{base}/#/schedules", wait_until="domcontentloaded")
        row = page.locator(".schedule-overview-row", has_text="Release Watch")
        row.wait_for(timeout=20_000)
        row.locator(".schedule-history > summary").click()
        body = row.locator(".schedule-history-body")
        body.wait_for(timeout=20_000)
        schedule_id = row.get_attribute("data-schedule-id")
        policy = row.locator("[data-schedule-approval]")
        expect(policy).not_to_be_checked()
        with page.expect_response(
                lambda response: response.url.endswith(f"/schedules/{schedule_id}/policy")
                and response.request.method == "PUT") as saved:
            policy.check()
        assert saved.value.ok, saved.value.text()
        expect(policy).to_be_checked()
        response = page.request.get(
            f"{base}/api/v1/bots/release-watch/schedules/{schedule_id}/policy")
        assert response.ok, response.text()
        assert response.json()["approval_required"] is True
        assert response.json()["revision"] == 1
        with page.expect_response(
                lambda response: response.url.endswith(f"/schedules/{schedule_id}/policy")
                and response.request.method == "PUT"):
            policy.uncheck()
        expect(policy).not_to_be_checked()
        assert watch.errors == [], watch.errors
    finally:
        context.close()


def test_schedules_surface_has_no_overflow_at_every_width_and_theme(browser, base):
    for width, height in VIEWPORTS:
        for scheme in ("dark", "light"):
            context = browser.new_context(viewport={"width": width, "height": height},
                                          color_scheme=scheme, reduced_motion="reduce")
            page = context.new_page()
            watch = PageWatch(page)
            try:
                page.goto(f"{base}/#/schedules", wait_until="domcontentloaded")
                if scheme == "light":
                    page.evaluate("document.documentElement.dataset.hutchTheme = 'light'")
                page.locator(".schedule-roll-call").wait_for(timeout=20_000)
                page.locator(".schedule-history > summary").first.click()
                page.locator(".schedule-history-body").first.wait_for(timeout=20_000)
                assert horizontal_overflow(page) <= 1, (width, scheme, horizontal_overflow(page))
                assert watch.errors == [], (width, scheme, watch.errors)
            finally:
                context.close()
