"""The SPA sets `<View> — Hutch` on first paint and after every route change.

A destination's title is its sidebar label. Runs against a real local server with
one saved assistant, in a real browser.
"""

from __future__ import annotations

import re

import pytest

pw = pytest.importorskip("playwright.sync_api")

from hutch.models import Bot  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from hutch.server.nav import FOOT, MORE, PRIMARY  # noqa: E402
from tests.support.browser import launch_browser, wait_for_page  # noqa: E402
from tests.support.live_app import PageWatch, serve  # noqa: E402

TITLE = re.compile(r"^[^—]+ — Hutch$")

# hash -> sidebar key whose label is the expected view name
DESTINATIONS = {
    "#/chat": "chat", "#/tasks": "tasks", "#/activity": "activity", "#/activity/history": "activity",
    "#/activity/conversations": "activity", "#/overview": "activity", "#/runs": "activity", "#/chats": "activity",
    "#/schedules": "schedules", "#/runtime": "runtime", "#/skills": "catalog", "#/catalog": "catalog",
    "#/bots": "bots", "#/connections": "connections", "#/settings": "settings",
}


def _label(key: str) -> str:
    for group in (PRIMARY, MORE, FOOT):
        for item_key, _href, label, _icon in group:
            if item_key == key:
                return label
    raise AssertionError(key)


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
    app.state.store.create_bot(Bot(name="title-check", display_name="Title Check", tools=[]))
    with serve(app) as url:
        yield url


def _open(browser, base, route):
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    watch = PageWatch(page)
    page.goto(f"{base}/{route}", wait_until="domcontentloaded")
    wait_for_page(page, "document.querySelector('#view') && !document.querySelector('#view .spinner')")
    return page, watch


@pytest.mark.parametrize("route,key", sorted(DESTINATIONS.items()))
def test_first_paint_title_is_the_nav_label(browser, base, route, key):
    page, watch = _open(browser, base, route)
    try:
        expected = f"{_label(key)} — Hutch"
        wait_for_page(page, "expected => document.title === expected", arg=expected)
        title = page.title()
        assert TITLE.match(title), title
        assert title == f"{_label(key)} — Hutch", (route, title)
        assert not watch.errors, watch.errors
    finally:
        page.context.close()


def test_title_follows_navigation_and_names_the_assistant(browser, base):
    page, watch = _open(browser, base, "#/tasks")
    try:
        assert page.title() == f"{_label('tasks')} — Hutch"
        page.evaluate("location.hash = '#/skills'")
        wait_for_page(page, "document.title.startsWith('Catalog')")
        assert page.title() == f"{_label('catalog')} — Hutch"      # Skills is a view of the Catalog
        page.evaluate("location.hash = '#/chat/title-check'")
        wait_for_page(page, "document.title.startsWith('Title Check')")
        assert page.title() == "Title Check — Hutch"
        assert "hutch — hutch" not in page.title().lower()
        assert not watch.errors, watch.errors
    finally:
        page.context.close()
