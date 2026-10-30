"""Overlay layout contract: flip/shift at every edge, re-anchor, internal scroll.

Split from test_overlays.py to stay inside the repo's 400-line source budget.
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


def test_popover_flips_shifts_and_reanchors(browser, app_server):
    base, _ = app_server
    page = browser.new_page(viewport={"width": 700, "height": 500})
    try:
        page.goto(base + "/#/chat/design-system-review", wait_until="domcontentloaded")
        page.locator("#chat-prompt").wait_for()
        page.evaluate("""() => {
          const wrap = document.createElement('div');
          wrap.id = 'anchors';
          wrap.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:1';
          document.body.append(wrap);
          const spots = {top: [300, 6], bottom: [300, 470], left: [6, 250], right: [660, 250]};
          window.__panels = {};
          for (const [name, [x, y]] of Object.entries(spots)) {
            const trigger = document.createElement('button');
            trigger.id = 'edge-' + name;
            trigger.textContent = name;
            trigger.style.cssText = 'position:fixed;left:' + x + 'px;top:' + y + 'px;pointer-events:auto;';
            wrap.append(trigger);
            const panel = document.createElement('div');
            panel.id = 'edge-panel-' + name;
            panel.setAttribute('aria-label', 'Edge menu ' + name);
            panel.innerHTML = Array.from({length: 8}, (_, i) => '<button type="button" role="menuitem" tabindex="-1">Item ' + i + '</button>').join('');
            document.body.append(panel);
            const control = HutchOverlay.popover({ trigger, panel, kind: 'menu', menu: true, side: name === 'top' ? 'bottom' : 'bottom' });
            window.__panels[name] = control;
          }
        }""")
        for name in ("top", "bottom", "left", "right"):
            page.evaluate(f"window.__panels['{name}'].open()")
            locator = page.locator(f"#edge-panel-{name}")
            locator.wait_for(state="visible")
            assert_fits(page, locator)
            page.evaluate(f"window.__panels['{name}'].close()")
        # Re-anchor inside a scrolling container.
        page.evaluate("""() => {
          const scroller = document.createElement('div');
          scroller.id = 'scroller';
          scroller.style.cssText = 'position:fixed;left:20px;top:100px;width:240px;height:180px;overflow:auto;';
          const before = document.createElement('div');
          before.style.height = '40px';
          const trigger = document.createElement('button');
          trigger.id = 'scroll-trigger';
          trigger.textContent = 'scroll anchor';
          const after = document.createElement('div');
          after.style.height = '600px';
          scroller.append(before, trigger, after);
          document.body.append(scroller);
          const panel = document.createElement('div');
          panel.id = 'scroll-panel';
          panel.setAttribute('aria-label', 'Scroller menu');
          panel.innerHTML = '<button type="button" role="menuitem" tabindex="-1">Item</button>';
          document.body.append(panel);
          window.__scrollControl = HutchOverlay.popover({ trigger, panel, kind: 'menu', menu: true });
          window.__scrollControl.open();
        }""")
        panel = page.locator("#scroll-panel")
        panel.wait_for(state="visible")
        before = panel.bounding_box()["y"]
        page.evaluate("document.getElementById('scroller').scrollTop = 120")
        page.wait_for_timeout(120)
        after = panel.bounding_box()["y"]
        assert after < before - 20, f"panel did not follow its anchor on scroll ({before} -> {after})"
        page.evaluate("window.__scrollControl.close()")
    finally:
        page.close()


def test_modal_long_content_scrolls_internally_and_double_submit_is_guarded(browser, app_server):
    base, _ = app_server
    page = browser.new_page(viewport={"width": 900, "height": 600})
    try:
        page.goto(base + "/#/chat/design-system-review", wait_until="domcontentloaded")
        page.locator("#chat-prompt").wait_for()
        page.evaluate("""() => {
          window.__confirmCalls = 0;
          const paragraphs = Array.from({length: 80}, (_, i) => '<p>Paragraph ' + i + ' of a long review body.</p>').join('');
          HutchOverlay.modal({
            title: 'Long review',
            body: paragraphs,
            confirmLabel: 'Save',
            onConfirm: () => new Promise(resolve => { window.__confirmCalls += 1; window.__settleModal = resolve; }),
          });
        }""")
        dialog = page.get_by_role("dialog", name="Long review")
        dialog.wait_for()
        body = dialog.locator(".modal-body")
        page_page_scroll = page.evaluate("document.querySelector('#view')?.scrollTop || 0")
        body.evaluate("el => { el.scrollTop = el.scrollHeight; }")
        assert body.evaluate("el => el.scrollTop > 0")
        assert page.evaluate("document.querySelector('#view')?.scrollTop || 0") == page_page_scroll, "page scrolled behind a long modal"
        page.locator("#modal-confirm").click()
        page.locator("#modal-confirm").click(force=True)
        page.wait_for_timeout(120)
        assert page.evaluate("window.__confirmCalls") == 1, "double submit reached the action twice"
        assert page.locator("#modal-confirm").is_disabled()
        page.evaluate("window.__settleModal(true)")
        dialog.wait_for(state="detached", timeout=3000)
    finally:
        page.close()
