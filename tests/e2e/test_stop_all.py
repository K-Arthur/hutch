"""The global stop is reachable from the SPA header whenever work is running.

Spine item C2: `POST /api/stop-all` was reachable only from server-page headers.
It stays behind a confirmation, is absent when nothing runs, and keeps the header
inside the viewport at phone width. Real local server, real browser, no model call.
"""

from __future__ import annotations

import pytest

pw = pytest.importorskip("playwright.sync_api")

from hutch.models import Bot, Run, RunStatus  # noqa: E402
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
def app_and_base(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    app.state.store.create_bot(Bot(name="stop-check", display_name="Stop Check", tools=[]))
    with serve(app) as url:
        yield app, url


def _open(browser, base, size=(1440, 900)):
    page = browser.new_context(viewport={"width": size[0], "height": size[1]}).new_page()
    watch = PageWatch(page)
    stops = []
    page.on("request", lambda req: stops.append(req) if req.url.endswith("/api/stop-all") and req.method == "POST" else None)
    page.goto(f"{base}/#/chat/stop-check", wait_until="domcontentloaded")
    wait_for_page(page, "!!document.querySelector('#view') && !document.querySelector('#view .spinner')")
    return page, watch, stops


def test_no_stop_control_while_idle(browser, app_and_base):
    _app, base = app_and_base
    page, watch, stops = _open(browser, base)
    try:
        page.wait_for_timeout(800)
        assert page.locator("[data-stop-all]").count() == 0
        assert not watch.errors, watch.errors
    finally:
        page.context.close()


def test_stop_all_is_confirmed_and_sent_once(browser, app_and_base):
    app, base = app_and_base
    bot = app.state.store.get_bot("stop-check")
    app.state.store.create_run(Run(bot_id=bot.id, prompt="keep working", status=RunStatus.running))
    page, watch, stops = _open(browser, base)
    try:
        button = page.locator("#workflow [data-stop-all]")
        button.wait_for(timeout=20_000)
        assert button.inner_text().strip() == "Stop all"
        # Cancelling sends nothing.
        button.click()
        dialog = page.get_by_role("dialog", name="Stop all running work?")
        dialog.wait_for()
        dialog.get_by_role("button", name="Cancel").click()
        page.wait_for_timeout(300)
        assert stops == []
        # Confirming sends exactly one request, with the CSRF header.
        button.click()
        dialog.wait_for()
        dialog.get_by_role("button", name="Stop all", exact=True).click()
        wait_for_page(page, "true")
        page.wait_for_timeout(600)
        assert len(stops) == 1
        assert stops[0].headers.get("x-hutch-csrf"), "the stop request carries the CSRF token"
        assert not watch.errors, watch.errors
    finally:
        page.context.close()


@pytest.mark.parametrize("size", [(1440, 900), (900, 900), (360, 800)])
def test_header_with_the_stop_control_fits_the_viewport(browser, app_and_base, size):
    app, base = app_and_base
    bot = app.state.store.get_bot("stop-check")
    app.state.store.create_run(Run(bot_id=bot.id, prompt="keep working", status=RunStatus.running))
    page, watch, _stops = _open(browser, base, size)
    try:
        button = page.locator("#workflow [data-stop-all]")
        button.wait_for(timeout=20_000)
        box = button.bounding_box()
        assert box and box["x"] >= 0 and box["x"] + box["width"] <= size[0] + 0.5, (size, box)
        assert box["height"] >= 24, "meets the 24 px minimum target"
        assert horizontal_overflow(page) == 0, size
        assert not watch.errors, watch.errors
    finally:
        page.context.close()
