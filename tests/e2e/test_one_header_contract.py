"""One header contract: every server page puts its title in the shell header.

The SPA shell carries the page title, a work status while runs are executing and the global stop only
while they run. Server pages used to differ: the title sat in the body, and "Stop all" plus a live chip
were permanent chrome. This pins the same contract on the real server at desktop, tablet and phone
widths, with a running run and with none.
"""

from __future__ import annotations

import pytest

pw = pytest.importorskip("playwright.sync_api")

from hutch.models import Bot, Run, RunStatus  # noqa: E402
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
    app.state.store.create_bot(Bot(name="header-check", display_name="Header Check",
                                   model="ollama/llama3.2:3b", tools=[]))
    with serve(app) as url:
        yield url, app


def test_every_server_page_titles_itself_in_the_shell_header(browser, base):
    url, _ = base
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    watch = PageWatch(page)
    try:
        expected = {"/models": "Models", "/usage": "Usage", "/bots/header-check": "Header Check",
                    "/legacy/connections": "Connections"}
        for width, height in ((1440, 900), (900, 1024), (390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            for route, title in expected.items():
                page.goto(f"{url}{route}", wait_until="domcontentloaded")
                heading = page.locator(".app-top-context h1")
                heading.wait_for(timeout=20_000)
                assert title in heading.inner_text(), (route, width, heading.inner_text())
                assert page.locator("main h1").count() == 0, f"{route} at {width}px keeps a body heading"
                assert page.evaluate("() => document.querySelector('.app-top').getBoundingClientRect().height") == 56
                assert horizontal_overflow(page) == 0, (route, width)
                # Idle: the global emergency stop belongs to running work only.
                assert page.locator("form[action='/stop-all']").count() == 0, (route, width)
        assert not watch.errors, watch.errors
    finally:
        page.context.close()


def test_running_work_shows_the_status_and_the_global_stop(browser, base):
    url, app = base
    bot = app.state.store.list_bots()[0]
    app.state.store.create_run(Run(bot_id=bot.id, prompt="long task", status=RunStatus.running, owner=""))
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    watch = PageWatch(page)
    try:
        page.goto(f"{url}/models", wait_until="domcontentloaded")
        work = page.locator(".app-top-work")
        work.wait_for(timeout=20_000)
        assert "1 working" in work.inner_text()
        stop = page.get_by_role("button", name="Stop all runs now. Kills child processes, not just the agent loop.")
        stop.wait_for()
        stop.click()
        dialog = page.get_by_role("dialog", name="Stop every running job?")
        dialog.wait_for()
        page.get_by_role("button", name="Cancel").click()
        dialog.wait_for(state="hidden", timeout=3_000)
        assert not watch.errors, watch.errors
    finally:
        page.context.close()
