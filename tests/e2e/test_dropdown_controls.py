"""Shared-control behavior against the running Hutch application, not a demo page."""
from __future__ import annotations

import pytest

pw = pytest.importorskip("playwright.sync_api")
from hutch.models import Bot
from tests.e2e.test_browser import live  # real isolated HTTP app fixture
from tests.support.artifacts import artifact_path
from tests.support.browser import launch_browser, wait_for_page


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as playwright:
        instance = launch_browser(playwright)
        yield instance
        instance.close()


def assert_fits(page, popup):
    bounds = popup.bounding_box()
    assert bounds and bounds["x"] >= 0 and bounds["y"] >= 0, bounds
    assert bounds["x"] + bounds["width"] <= page.viewport_size["width"] + 1, bounds
    assert bounds["y"] + bounds["height"] <= page.viewport_size["height"] + 1, bounds


@pytest.mark.parametrize("width,height", [(1440, 960), (900, 1024), (390, 844), (320, 740)])
def test_settings_select_retains_native_form_and_shared_picker(browser, live, width, height):
    base, app = live
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    out = artifact_path("dropdowns/select")
    out.mkdir(parents=True, exist_ok=True)
    try:
        page.goto(base + "/#/settings")
        control = page.locator("#workspace-settings-mode")
        control.wait_for()
        assert control.evaluate("el => el instanceof HTMLSelectElement")
        assert control.get_attribute("name") is None  # existing SPA value contract
        control.click()
        assert control.evaluate("el => el.matches(':open')")
        assert control.evaluate("el => getComputedStyle(el).fontSize") == "16px"
        assert control.locator("option").count() == 3
        page.screenshot(path=str(out / f"open-{width}.png"))
        page.keyboard.press("Escape")
        assert control.input_value() == "hybrid", "exploring must not change the saved routing"
        control.select_option("local")
        with page.expect_response(lambda response: response.url.endswith("/api/v1/preferences/model-defaults")
                                  and response.request.method == "PUT") as saved:
            page.get_by_role("button", name="Save workspace settings").click()
        assert saved.value.ok, saved.value.text()
        page.reload()
        page.locator("#workspace-settings-mode").wait_for()
        assert page.locator("#workspace-settings-mode").input_value() == "local"
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        assert not errors, errors
    finally:
        context.close()


def test_action_menu_keyboard_escape_and_tab_preserve_focus(browser, live):
    base, app = live
    app.state.store.create_bot(Bot(name="dropdown-helper", display_name="Research and project follow-through", model="ollama/local", tools=[]))
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    try:
        page.goto(base + "/#/bot/dropdown-helper")
        trigger = page.get_by_label("Assistant options", exact=True).first
        trigger.wait_for()
        trigger.focus()
        page.keyboard.press("ArrowDown")
        menu = page.locator(".assistant-settings-menu-panel")
        menu.wait_for(state="visible")
        assert menu.get_attribute("role") == "menu"
        assert_fits(page, menu)
        assert page.get_by_role("menuitem", name="Open chat").evaluate("el => el === document.activeElement")
        page.keyboard.press("End")
        assert page.get_by_role("menuitem", name="Delete assistant").evaluate("el => el === document.activeElement")
        page.keyboard.press("Escape")
        assert menu.is_hidden()
        assert trigger.evaluate("el => el === document.activeElement")
        trigger.click()
        menu.wait_for(state="visible")
        page.keyboard.press("Tab")
        assert menu.is_hidden()
        assert not page.evaluate("document.activeElement.closest('.hc-popup') !== null")
    finally:
        context.close()


def test_popup_in_native_dialog_accepts_pointer_and_scrolls_without_closing(browser, live):
    base, _ = live
    context = browser.new_context(viewport={"width": 390, "height": 500})
    page = context.new_page()
    try:
        page.goto(base + "/#/settings")
        page.locator("#workspace-settings-mode").wait_for()
        # Targeted hostile geometry fixture supplements the genuine settings
        # journey above: a native modal, clipped ancestor and 40 menu choices.
        page.evaluate("""() => {
          const dialog = document.createElement('dialog');
          dialog.innerHTML = '<div style="overflow:hidden;height:80px"><button id="nested-trigger">Choose a destination</button><div id="nested-popup" aria-label="Destinations"></div></div>';
          document.body.append(dialog); dialog.showModal();
          const panel = dialog.querySelector('#nested-popup');
          for (let i=0;i<40;i++) { const b=document.createElement('button'); b.type='button'; b.role='menuitem'; b.tabIndex=-1; b.textContent='Destination '+i; panel.append(b); }
          window.__nested = hutchControls.popup({trigger:dialog.querySelector('button'),panel,kind:'menu'});
          dialog.querySelector('button').onclick=()=>__nested.open();
          panel.onclick=e=>{ if(e.target.matches('button')) window.__chosen=e.target.textContent; };
        }""")
        page.locator("#nested-trigger").click()
        menu = page.locator("#nested-popup")
        assert_fits(page, menu)
        menu.hover()
        page.mouse.wheel(0, 500)
        wait_for_page(page, "document.querySelector('#nested-popup').scrollTop > 0")
        assert menu.is_visible()
        page.keyboard.press("End")
        page.get_by_role("menuitem", name="Destination 39", exact=True).click()
        assert page.evaluate("window.__chosen") == "Destination 39"
        page.keyboard.press("Escape")
        assert menu.is_hidden()
        assert page.locator("dialog:has(#nested-trigger)").evaluate("el => el.open"), "first Escape closes only the popup"
    finally:
        context.close()
