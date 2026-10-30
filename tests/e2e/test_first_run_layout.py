"""First run lays out as designed: the hint under its form, the rail beside the form.

Audit finding S7: "Nothing runs until you ask." floated alone in the right column because the
composer foot and the rail were both auto-placed grid children. The first screen is also the
product's hero image, so its geometry is pinned at three widths. Real server, fresh state.
"""

from __future__ import annotations

import pytest

pw = pytest.importorskip("playwright.sync_api")

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
    with serve(create_app()) as url:
        yield url


def _boxes(page):
    page.goto(page.url, wait_until="domcontentloaded")
    page.locator("#first-run-request-form").wait_for(timeout=20_000)
    page.locator("#first-run-setup-check").wait_for(timeout=20_000)
    page.wait_for_timeout(700)
    return {
        "form": page.locator("#first-run-request-form").bounding_box(),
        "hint": page.locator("#first-run-request-hint").bounding_box(),
        "rail": page.locator(".first-run-rail").bounding_box(),
    }


@pytest.mark.parametrize("size", [(1440, 1000), (1100, 900), (900, 900)])
def test_wide_layout_puts_the_hint_under_the_form_and_the_rail_beside_it(browser, base, size):
    page = browser.new_context(viewport={"width": size[0], "height": size[1]}).new_page()
    watch = PageWatch(page)
    try:
        page.goto(f"{base}/#/chat", wait_until="domcontentloaded")
        box = _boxes(page)
        form, hint, rail = box["form"], box["hint"], box["rail"]
        assert rail["x"] >= form["x"] + form["width"] - 1, ("the rail sits beside the form", box)
        assert abs(rail["y"] - form["y"]) < 12, ("the rail starts level with the form", box)
        assert 0 <= hint["y"] - (form["y"] + form["height"]) < 48, ("the hint sits right under the form", box)
        assert form["x"] - 1 <= hint["x"] <= form["x"] + form["width"], ("the hint is in the form's column", box)
        assert horizontal_overflow(page) == 0
        assert not watch.errors, watch.errors
    finally:
        page.context.close()


@pytest.mark.parametrize("size", [(600, 800), (360, 800)])
def test_narrow_layout_is_one_column_in_reading_order(browser, base, size):
    page = browser.new_context(viewport={"width": size[0], "height": size[1]}).new_page()
    watch = PageWatch(page)
    try:
        page.goto(f"{base}/#/chat", wait_until="domcontentloaded")
        box = _boxes(page)
        form, hint, rail = box["form"], box["hint"], box["rail"]
        assert hint["y"] >= form["y"] + form["height"] - 1, ("the hint follows the form", box)
        assert rail["y"] >= hint["y"] + hint["height"] - 1, ("the rail follows the hint", box)
        assert horizontal_overflow(page) == 0
        assert not watch.errors, watch.errors
    finally:
        page.context.close()
