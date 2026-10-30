"""Every destination on a fresh, empty state: one title format, no errors, no overflow.

P2 acceptance of docs/realignment/release-readiness-progress.md, and the base for the
start-state work (P3). Real local server with an empty state directory, real browser,
no assistants and no model route. Screenshots go to the isolated test artifact root.
"""

from __future__ import annotations

import re

import pytest

pw = pytest.importorskip("playwright.sync_api")

from hutch.server.app import create_app  # noqa: E402
from tests.support.artifacts import artifact_path  # noqa: E402
from tests.support.browser import launch_browser, wait_for_page  # noqa: E402
from tests.support.live_app import PageWatch, horizontal_overflow, serve  # noqa: E402

VIEWPORTS = ((1440, 900), (900, 900), (360, 800))
TITLE = re.compile(r"^[^—<>]+ — Hutch$")
# (slug, path or hash route, expected title view or None when the page names its own)
ROUTES = (
    ("home", "/", None),
    ("chat", "/#/chat", "Chat"),
    ("tasks", "/#/tasks", "Tasks"),
    ("approvals", "/#/approvals", None),
    ("activity-now", "/#/activity", "Activity"),
    ("activity-history", "/#/activity/history", "Activity"),
    ("activity-conversations", "/#/activity/conversations", "Activity"),
    ("schedules", "/#/schedules", "Scheduled work"),
    ("runtime", "/#/runtime", "Runtime"),
    ("skills", "/#/skills", "Skills"),
    ("models", "/models", "Models"),
    ("usage", "/usage", "Usage"),
    ("assistants", "/#/bots", None),
    ("connections", "/#/connections", "Apps & AI"),
    ("settings", "/#/settings", "Settings"),
)


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as playwright:
        b = launch_browser(playwright)
        yield b
        b.close()


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    import os
    state = tmp_path_factory.mktemp("fresh-state")
    previous = os.environ.get("HUTCH_STATE_DIR")
    os.environ["HUTCH_STATE_DIR"] = str(state)
    try:
        app = create_app()
        with serve(app) as url:
            yield url
    finally:
        if previous is None:
            os.environ.pop("HUTCH_STATE_DIR", None)
        else:
            os.environ["HUTCH_STATE_DIR"] = previous


@pytest.mark.parametrize("size", VIEWPORTS, ids=lambda s: f"{s[0]}x{s[1]}")
@pytest.mark.parametrize("slug,route,view", ROUTES, ids=[r[0] for r in ROUTES])
def test_route_on_a_fresh_state(browser, base, slug, route, view, size):
    context = browser.new_context(viewport={"width": size[0], "height": size[1]})
    page = context.new_page()
    watch = PageWatch(page)
    try:
        page.goto(base + route, wait_until="domcontentloaded")
        wait_for_page(page, "document.readyState === 'complete'", timeout=20_000)
        page.wait_for_timeout(900)
        title = page.title()
        assert TITLE.match(title), f"{slug}: {title!r} is not '<View> — Hutch'"
        if view:
            assert title == f"{view} — Hutch", (slug, title)
        assert "hutch — hutch" not in title.lower(), title
        assert horizontal_overflow(page) == 0, (slug, size, page.url)
        assert not watch.errors, (slug, size, watch.errors)
        shot = artifact_path(f"fresh-state/{slug}-{size[0]}x{size[1]}.png")
        shot.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(shot), animations="disabled")
    finally:
        context.close()
