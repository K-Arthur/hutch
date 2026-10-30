"""Activity is one destination with three views: Now, History, Conversations.

Merged from Overview/Activity, Work history and Conversation history (spine,
decision 1). The old hashes keep working as redirects. Real local server, real
browser, one saved assistant, no model call.
"""

from __future__ import annotations

import pytest

pw = pytest.importorskip("playwright.sync_api")

from hutch.models import Bot  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from tests.support.browser import launch_browser, wait_for_page  # noqa: E402
from tests.support.live_app import PageWatch, horizontal_overflow, serve  # noqa: E402

VIEWPORTS = ((1440, 900), (900, 900), (360, 800))
TABS = (("Now", "#/activity"), ("History", "#/activity/history"), ("Conversations", "#/activity/conversations"))
REDIRECTS = (
    ("#/overview", "#/activity"),
    ("#/chats", "#/activity/conversations"),
    ("#/runs", "#/activity/history"),
    ("#/runs?status=failed&q=tidy", "#/activity/history?status=failed&q=tidy"),
)


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as playwright:
        b = launch_browser(playwright)
        yield b
        b.close()


@pytest.fixture()
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    app.state.store.create_bot(Bot(name="activity-check", display_name="Activity Check", tools=[]))
    with serve(app) as url:
        yield url


def _open(browser, base, route, size=(1440, 900)):
    page = browser.new_context(viewport={"width": size[0], "height": size[1]}).new_page()
    watch = PageWatch(page)
    page.goto(f"{base}/{route}", wait_until="domcontentloaded")
    wait_for_page(page, "!!document.querySelector('#view .activity-tabs')", timeout=20_000)
    return page, watch


def test_sidebar_has_one_activity_row_and_no_retired_history_rows(browser, base):
    page, watch = _open(browser, base, "#/activity")
    try:
        rows = page.locator(".ws-nav a, .ws-nav button").all_inner_texts()
        rows = [" ".join(text.split()) for text in rows]
        assert rows.count("Activity") == 1, rows
        for retired in ("Conversation history", "Work history", "Manage assistants"):
            assert retired not in rows, (retired, rows)
        assert "Assistants" in rows
        assert not watch.errors, watch.errors
    finally:
        page.context.close()


@pytest.mark.parametrize("old,new", REDIRECTS)
def test_old_hashes_redirect_to_the_merged_destination(browser, base, old, new):
    page, watch = _open(browser, base, old)
    try:
        assert page.evaluate("location.hash") == new
        assert page.title() == "Activity — Hutch"
        assert not watch.errors, watch.errors
    finally:
        page.context.close()


def test_tabs_are_links_with_one_current_page_and_one_heading(browser, base):
    page, watch = _open(browser, base, "#/activity")
    try:
        for label, hash_ in TABS:
            if page.evaluate("location.hash") != hash_:
                page.locator(".activity-tabs a", has_text=label).click()
            wait_for_page(page, "([hash, label]) => location.hash === hash && "
                          "document.querySelector('#view .activity-tabs a[aria-current=page]')?.textContent.trim() === label",
                          arg=[hash_, label])
            tabs = page.locator(".activity-tabs a")
            assert [t.strip() for t in tabs.all_inner_texts()] == [name for name, _ in TABS]
            current = page.locator(".activity-tabs a[aria-current='page']")
            assert current.count() == 1 and current.inner_text().strip() == label
            assert page.locator("nav.activity-tabs").get_attribute("aria-label") == "Activity views"
            assert page.locator("main h1, #app-top-context h1").count() == 1
            assert page.locator("h1").first.inner_text().strip() == "Activity"
            assert page.title() == "Activity — Hutch"
            assert page.locator(".ws-nav a[data-nav='activity']").get_attribute("aria-current") == "page"
        assert not watch.errors, watch.errors
    finally:
        page.context.close()


def test_history_filters_survive_inside_the_merged_route(browser, base):
    page, watch = _open(browser, base, "#/activity/history?q=nothing-matches")
    try:
        assert page.locator("#run-search").input_value() == "nothing-matches"
        page.locator("#run-search").fill("tidy")
        wait_for_page(page, "location.hash.startsWith('#/activity/history') && location.hash.includes('q=tidy')")
        assert not watch.errors, watch.errors
    finally:
        page.context.close()


@pytest.mark.parametrize("size", VIEWPORTS)
@pytest.mark.parametrize("route", [hash_ for _, hash_ in TABS])
def test_each_view_fits_the_viewport_without_errors(browser, base, route, size):
    page, watch = _open(browser, base, route, size)
    try:
        page.wait_for_timeout(300)
        assert horizontal_overflow(page) == 0, (route, size)
        box = page.locator(".activity-tabs").bounding_box()
        assert box and box["x"] >= 0 and box["x"] + box["width"] <= size[0] + 0.5, (route, size, box)
        assert box["height"] >= 40, "tabs keep a touch-sized target"
        assert not watch.errors, watch.errors
    finally:
        page.context.close()
