"""Overlay primitive contract: modal, popover, dropdown menu and tooltip.

Every assertion here maps to one item of the edge-case checklist in
docs/overlays/audit.md. The tests boot the real app, so they exercise the same
markup, CSS and runtime the product ships.
"""

from __future__ import annotations

import pytest

pw = pytest.importorskip("playwright.sync_api")

from tests.e2e.test_design_system import app_server, browser  # noqa: E402,F401


def assert_fits(page, locator):
    box = locator.bounding_box()
    assert box, "element has no layout box"
    assert box["x"] >= 0 and box["y"] >= 0, box
    assert box["x"] + box["width"] <= page.viewport_size["width"] + 1, box
    assert box["y"] + box["height"] <= page.viewport_size["height"] + 1, box


def open_assistant_menu(page, base):
    page.goto(base + "/#/bot/design-system-review", wait_until="domcontentloaded")
    trigger = page.get_by_label("Assistant options", exact=True).first
    trigger.wait_for()
    trigger.click()
    menu = page.locator(".assistant-settings-menu-panel")
    menu.wait_for(state="visible")
    return trigger, menu


def test_dropdown_focus_return_escape_and_outside_click(browser, app_server):
    base, _ = app_server
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    try:
        trigger, menu = open_assistant_menu(page, base)
        assert menu.get_attribute("role") == "menu"
        assert_fits(page, menu)
        assert page.get_by_role("menuitem", name="Open chat").evaluate(
            "el => el === document.activeElement"), "opening a menu focuses its first item"
        page.keyboard.press("End")
        assert page.get_by_role("menuitem", name="Delete assistant").evaluate("el => el === document.activeElement")
        page.keyboard.press("Escape")
        assert menu.is_hidden()
        assert trigger.evaluate("el => el === document.activeElement"), "Escape returns focus to the trigger"
        trigger.click()
        menu.wait_for(state="visible")
        page.locator("#view").click(position={"x": 5, "y": 5})
        menu.wait_for(state="hidden")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    finally:
        context.close()


def test_destructive_confirm_is_not_dismissible_and_never_default_focus(browser, app_server):
    base, _ = app_server
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        trigger, menu = open_assistant_menu(page, base)
        page.get_by_role("menuitem", name="Delete assistant").click()
        dialog = page.get_by_role("dialog", name="Delete assistant")
        dialog.wait_for()
        assert dialog.get_attribute("aria-modal") == "true"
        assert dialog.get_attribute("data-dismissible") == "false"
        assert page.evaluate("document.querySelector('.hutch-modal__description')?.id") == dialog.get_attribute("aria-describedby")
        initial = page.evaluate("document.activeElement.id")
        assert initial == "modal-cancel", f"destructive dialog started on {initial}"
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        assert dialog.is_visible(), "Escape must not dismiss a destructive confirmation"
        page.mouse.click(4, 4)   # backdrop
        page.wait_for_timeout(300)
        assert dialog.is_visible(), "backdrop must not dismiss a destructive confirmation"
        # Tab stays inside the native dialog.
        for _ in range(6):
            page.keyboard.press("Tab")
            assert page.evaluate("document.activeElement.closest('dialog[open]') !== null")
        page.get_by_role("button", name="Cancel").click()
        dialog.wait_for(state="detached", timeout=3000)
        assert trigger.evaluate("el => el === document.activeElement"), "focus returns to the menu trigger"
        assert not errors, errors
    finally:
        context.close()


def test_server_page_confirm_form_and_tooltip(browser, app_server):
    base, _ = app_server
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    try:
        page.goto(base + "/models", wait_until="domcontentloaded")
        stop = page.get_by_role("button", name="Stop all runs now. Kills child processes, not just the agent loop.")
        stop.wait_for()
        page.wait_for_function("typeof window.HutchOverlay?.tooltip === 'function'")
        # The live pill carries a native title; the tooltip enhancement themes it.
        page.locator("#live-pill").hover()
        tooltip = page.locator(".hutch-tooltip")
        tooltip.wait_for(state="visible", timeout=2000)
        assert "Live updates connected" in tooltip.inner_text()
        page.mouse.move(0, 0)
        tooltip.wait_for(state="hidden", timeout=2000)
        stop.click()
        dialog = page.get_by_role("dialog", name="Stop every running job?")
        dialog.wait_for()
        assert dialog.get_attribute("data-dismissible") == "false"
        assert dialog.locator(".hutch-modal__description").inner_text().startswith("This kills child processes")
        page.keyboard.press("Escape")
        page.wait_for_timeout(250)
        assert dialog.is_visible()
        page.get_by_role("button", name="Cancel").click()
        dialog.wait_for(state="hidden", timeout=3000)
        assert "data-hutch-scroll-locked" not in page.evaluate("document.documentElement.outerHTML")
        assert page.url.rstrip("/").endswith("/models")
    finally:
        context.close()


def test_palette_and_needs_you_share_the_modal_contract(browser, app_server):
    base, _ = app_server
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    try:
        page.goto(base + "/#/chat/design-system-review", wait_until="domcontentloaded")
        page.locator("#chat-prompt").wait_for()
        page.keyboard.press("Control+k")
        palette = page.locator("dialog.palette")
        palette.wait_for(state="visible")
        assert page.evaluate("document.documentElement.dataset.hutchScrollLocked !== undefined")
        page.keyboard.press("Escape")
        palette.wait_for(state="hidden")
        assert page.evaluate("document.documentElement.dataset.hutchScrollLocked === undefined")
        # The review drawer is modal by contract and dismissible by Escape.
        page.evaluate("() => { const button = document.getElementById('needs-you-open'); button.focus(); button.click(); }")
        drawer = page.locator("#needs-you")
        drawer.wait_for(state="visible")
        assert page.evaluate("document.activeElement.id") == "needs-you-close"
        page.keyboard.press("Escape")
        drawer.wait_for(state="hidden")
        landed = page.evaluate("document.activeElement.id")
        # On a phone the sidebar trigger is off-canvas once the drawer closes, so
        # the documented fallback is the nav toggle; never <body>.
        assert landed in {"needs-you-open", "nav-toggle"}, landed
    finally:
        context.close()


def test_primitive_busy_error_success_and_focus_return(browser, app_server):
    base, _ = app_server
    page = browser.new_page(viewport={"width": 900, "height": 700})
    try:
        page.goto(base + "/#/chat/design-system-review", wait_until="domcontentloaded")
        page.locator("#chat-prompt").wait_for()
        page.evaluate("""() => {
          const trigger = document.createElement('button');
          trigger.id = 'overlay-test-trigger';
          trigger.textContent = 'Open test dialog';
          document.body.append(trigger);
          trigger.focus();
          window.__overlayTest = HutchOverlay.modal({
            title: 'Test dialog',
            description: 'One sentence about the consequence.',
            body: '<p>Body text</p>',
            confirmLabel: 'Save changes',
            onConfirm: () => new Promise((resolve, reject) => { window.__overlaySettle = { resolve, reject }; }),
          });
        }""")
        dialog = page.get_by_role("dialog", name="Test dialog")
        dialog.wait_for()
        assert page.evaluate("document.activeElement.id") == "modal-confirm"
        page.locator("#modal-confirm").click()
        page.wait_for_timeout(100)
        assert page.locator("#modal-confirm").is_disabled()
        assert dialog.get_attribute("aria-busy") == "true"
        page.evaluate("window.__overlaySettle.reject(new Error('The server said no. Try again.'))")
        error = dialog.locator(".hutch-modal__error")
        error.wait_for(state="visible")
        assert error.get_attribute("role") == "alert"
        assert "The server said no" in error.inner_text()
        assert dialog.is_visible(), "a failed action keeps the dialog open"
        page.locator("#modal-confirm").click()
        page.wait_for_timeout(100)
        page.evaluate("window.__overlaySettle.resolve(true)")
        dialog.wait_for(state="detached", timeout=3000)
        assert page.evaluate("document.activeElement.id") == "overlay-test-trigger"
    finally:
        page.close()


def test_nested_dialog_escape_only_closes_topmost_and_restores_focus(browser, app_server):
    base, _ = app_server
    page = browser.new_page(viewport={"width": 900, "height": 700})
    try:
        page.goto(base + "/#/chat/design-system-review", wait_until="domcontentloaded")
        page.locator("#chat-prompt").wait_for()
        page.evaluate("""() => {
          const trigger = document.createElement('button');
          trigger.id = 'nested-trigger';
          trigger.textContent = 'Open outer';
          document.body.append(trigger);
          trigger.focus();
          HutchOverlay.modal({
            title: 'Outer dialog',
            body: '<button id="open-inner" type="button">Open inner confirmation</button>',
            confirmLabel: 'Done',
            onConfirm: () => true,
          });
          document.getElementById('open-inner').addEventListener('click', () => {
            window.__inner = HutchOverlay.confirm({ title: 'Inner confirmation', descriptionHtml: 'Inner body' });
          });
        }""")
        outer = page.get_by_role("dialog", name="Outer dialog")
        outer.wait_for()
        page.locator("#open-inner").click()
        inner = page.get_by_role("dialog", name="Inner confirmation")
        inner.wait_for()
        assert page.evaluate("document.querySelectorAll('dialog[open]').length") == 2
        page.keyboard.press("Escape")
        inner.wait_for(state="detached", timeout=3000)
        assert outer.is_visible(), "Escape closes only the topmost dialog"
        assert page.evaluate("document.activeElement.id") == "open-inner", "focus returns to the nested trigger"
        page.get_by_role("button", name="Done").click()
        outer.wait_for(state="detached", timeout=3000)
        assert page.evaluate("document.activeElement.id") == "nested-trigger"
    finally:
        page.close()


def test_popover_fallback_portals_out_of_a_clipping_ancestor(browser, app_server):
    base, _ = app_server
    context = browser.new_context(viewport={"width": 390, "height": 700})
    context.add_init_script("HTMLElement.prototype.showPopover = undefined")
    page = context.new_page()
    try:
        page.goto(base + "/#/chat/design-system-review", wait_until="domcontentloaded")
        page.locator("#chat-prompt").wait_for()
        page.evaluate("""() => {
          const box = document.createElement('div');
          box.style.cssText = 'position:fixed;left:8px;top:80px;width:200px;height:36px;overflow:hidden;';
          const trigger = document.createElement('button');
          trigger.id = 'clip-trigger';
          trigger.textContent = 'Open menu';
          box.append(trigger);
          document.body.append(box);
          const panel = document.createElement('div');
          panel.id = 'clip-panel';
          panel.setAttribute('aria-label', 'Clipped menu');
          panel.innerHTML = Array.from({length: 20}, (_, i) => '<button type="button" role="menuitem" tabindex="-1">Destination ' + i + '</button>').join('');
          document.body.append(panel);
          window.__clip = HutchOverlay.popover({ trigger, panel, kind: 'menu', menu: true });
          window.__clip.open();
        }""")
        panel = page.locator("#clip-panel")
        panel.wait_for(state="visible")
        assert page.evaluate("document.getElementById('clip-panel').parentElement === document.body"), \
            "the no-Popover-API fallback portals the panel to body"
        assert_fits(page, panel)
        page.keyboard.press("Escape")
        panel.wait_for(state="hidden")
    finally:
        context.close()


def test_overlay_survives_text_zoom_at_200_percent(browser, app_server):
    base, _ = app_server
    page = browser.new_page(viewport={"width": 640, "height": 480})
    try:
        page.goto(base + "/#/bot/design-system-review", wait_until="domcontentloaded")
        page.add_style_tag(content="html { font-size: 200% !important; }")
        trigger = page.get_by_label("Assistant options", exact=True).first
        trigger.wait_for()
        trigger.click()
        menu = page.locator(".assistant-settings-menu-panel")
        menu.wait_for(state="visible")
        assert_fits(page, menu)
        page.get_by_role("menuitem", name="Delete assistant").click()
        dialog = page.get_by_role("dialog", name="Delete assistant")
        dialog.wait_for()
        assert_fits(page, dialog)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.keyboard.press("Escape")
        page.locator("[data-hutch-modal-cancel]").click()
    finally:
        page.close()


def test_overlay_survives_320px_reduced_motion_and_forced_colors(browser, app_server):
    base, _ = app_server
    context = browser.new_context(viewport={"width": 320, "height": 740}, reduced_motion="reduce", forced_colors="active")
    page = context.new_page()
    try:
        page.goto(base + "/#/bot/design-system-review", wait_until="domcontentloaded")
        trigger = page.get_by_label("Assistant options", exact=True).first
        trigger.wait_for()
        trigger.click()
        menu = page.locator(".assistant-settings-menu-panel")
        menu.wait_for(state="visible")
        assert_fits(page, menu)
        page.keyboard.press("Escape")
        trigger.click()
        page.get_by_role("menuitem", name="Delete assistant").click()
        dialog = page.get_by_role("dialog", name="Delete assistant")
        dialog.wait_for()
        assert_fits(page, dialog)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        styles = page.evaluate("""() => { const d = document.querySelector('dialog[open]');
          const s = getComputedStyle(d);
          return { border: s.borderTopColor, shadow: s.boxShadow, duration: s.transitionDuration }; }""")
        assert styles["shadow"] == "none", styles
        assert "1e-06s" in styles["duration"] or "0.001s" in styles["duration"], styles
        page.keyboard.press("Escape")
        page.locator("[data-hutch-modal-cancel]").click()
    finally:
        context.close()


def test_light_scope_adapts_scrim_and_elevation(browser, app_server):
    base, _ = app_server
    page = browser.new_page(viewport={"width": 900, "height": 700})
    try:
        page.goto(base + "/#/bot/design-system-review", wait_until="domcontentloaded")
        page.evaluate("document.documentElement.dataset.hutchTheme = 'light'")
        values = page.evaluate("""() => ({
          opacity: getComputedStyle(document.documentElement).getPropertyValue('--hutch-overlay-scrim-opacity').trim(),
          modalElevation: getComputedStyle(document.documentElement).getPropertyValue('--hutch-elevation-overlay-modal').trim(),
        })""")
        assert values["opacity"] == "0.52", values
        assert "rgb(6 6 8 / 0.08)" in values["modalElevation"] or "color-mix" in values["modalElevation"], values
    finally:
        page.close()
