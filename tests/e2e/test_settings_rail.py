"""The assistant settings rail: behaviour that must hold for the page to stay usable, not only to look right.

Layout, roles and keyboard movement are covered in test_design_system.py (test_assistant_settings_keep_everyday_edits_up_front);
this file pins the three things a code review found could silently go wrong: the page jumping to the top when a tab
is chosen, a wrong orientation announced to assistive technology, and a save re-rendering the page back to Profile.
"""

from __future__ import annotations

import pytest

pw = pytest.importorskip("playwright.sync_api")
expect = pw.expect

from tests.e2e.settings_pane import open_assistant_customization  # noqa: E402
from tests.e2e.test_design_system import app_server, browser  # noqa: E402,F401


def _open(browser, base, width, height, touch):
    context = browser.new_context(viewport={"width": width, "height": height}, is_mobile=touch, has_touch=touch, reduced_motion="reduce")
    page = context.new_page()
    page.goto(f"{base}/#/bot/design-system-review", wait_until="domcontentloaded")
    page.get_by_role("tablist", name="Assistant settings sections").wait_for()
    return context, page


def test_choosing_a_tab_moves_the_rail_not_the_page(browser, app_server):
    """scrollIntoView on the tab would scroll the page container as well; only the rail may move."""
    base, _ = app_server
    context, page = _open(browser, base, 390, 640, True)
    try:
        scroller = page.locator("main#view > .page-scroll")
        rail = page.get_by_role("tablist", name="Assistant settings sections")
        page.locator("#persona-form-slot .persona-form").wait_for(state="attached")   # Behavior must have its full height
        scroller.evaluate("el => { el.scrollTop = 300; }")                 # Profile is taller than the screen
        before = scroller.evaluate("el => el.scrollTop")
        assert before >= 250, "the Profile pane must be taller than the screen for this test to mean anything"
        # dispatch the click: Playwright's own pre-click scrolling would move the page and hide what the app does
        page.locator('[data-settings-tab="behavior"]').dispatch_event("click")   # Behavior is tall too: no clamping
        page.locator("#settings-pane-behavior").wait_for(state="visible")
        assert abs(scroller.evaluate("el => el.scrollTop") - before) <= 2, "choosing a tab must not move the page"
        page.locator('[data-settings-tab="limits"]').dispatch_event("click")     # the last tab starts beyond the strip's edge
        page.locator("#settings-pane-limits").wait_for(state="visible")
        assert scroller.evaluate("el => el.scrollLeft") == 0, "the page must never scroll sideways"
        assert rail.evaluate("el => el.scrollLeft") > 0, "the strip itself scrolls the selected tab into view"
        tab, box = page.locator('[data-settings-tab="limits"]').bounding_box(), rail.bounding_box()
        assert tab["x"] >= box["x"] - 1 and tab["x"] + tab["width"] <= box["x"] + box["width"] + 1, "selected tab must be fully visible"
    finally:
        context.close()


@pytest.mark.parametrize("width,height,touch,orientation", [(1440, 900, False, "vertical"), (390, 844, True, "horizontal")])
def test_the_rail_announces_the_orientation_it_really_has(browser, app_server, width, height, touch, orientation):
    base, _ = app_server
    context, page = _open(browser, base, width, height, touch)
    try:
        rail = page.get_by_role("tablist", name="Assistant settings sections")
        assert rail.get_attribute("aria-orientation") == orientation
        direction = rail.evaluate("el => getComputedStyle(el).flexDirection")
        assert (direction == "column") == (orientation == "vertical")
        if not touch:                                       # narrowing the window flips it without a reload
            page.set_viewport_size({"width": 600, "height": 900})
            page.wait_for_function("() => document.querySelector('[role=tablist]').getAttribute('aria-orientation') === 'horizontal'")
    finally:
        context.close()


def test_saving_keeps_the_pane_you_were_on(browser, app_server):
    """Every save re-renders the settings page; the selected pane must survive it."""
    base, _ = app_server
    context, page = _open(browser, base, 1440, 900, False)
    try:
        open_assistant_customization(page, "behavior")
        page.locator("#form-instructions textarea[name=instructions]").fill("Keep answers short.")
        page.locator("#form-instructions").get_by_role("button", name="Save directions").click()
        page.get_by_text("Directions saved.", exact=True).wait_for()
        expect(page.locator("#settings-pane-behavior")).to_be_visible()
        assert page.locator('[data-settings-tab="behavior"]').get_attribute("aria-selected") == "true"
        assert page.locator("#form-instructions textarea[name=instructions]").input_value() == "Keep answers short."
        assert page.locator("#settings-pane-profile").is_hidden()
    finally:
        context.close()
