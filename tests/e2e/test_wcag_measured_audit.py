"""Measured UI audit fixes (docs/realignment/artifacts/ui-audit-2026-10-22/FINDINGS.md).

Each test pins one finding from the rendered-layout audit: F-01 legacy-button focus ring,
F-02 phone sheet focus wrap, F-03 closed sheet out of the tab order.
"""
from __future__ import annotations

from tests.e2e.test_wcag_fixes import (audit_browser, audit_live,  # noqa: F401 - pytest fixtures
                                       seed_pending_approval, wait_live)


def tab_to(page, selector, limit=120):
    """Press Tab until the focused element matches ``selector``; return the number of presses."""
    for presses in range(1, limit + 1):
        page.keyboard.press("Tab")
        if page.evaluate("(s) => !!document.activeElement?.matches(s)", selector):
            return presses
    raise AssertionError(f"{selector} was not reached within {limit} Tab presses")


def focus_ring(page):
    return page.evaluate("""() => { const cs = getComputedStyle(document.activeElement);
        return {style: cs.outlineStyle, width: parseFloat(cs.outlineWidth)}; }""")


def test_legacy_button_variants_keep_a_visible_focus_ring(audit_browser, audit_live):
    """F-01: `all: unset` on the shared variants must not remove the keyboard focus ring."""
    base, app = audit_live
    seed_pending_approval(app.state.store)
    page = audit_browser.new_page(viewport={"width": 1440, "height": 960})
    try:
        wait_live(page, base)
        page.goto(base + "/#/approvals")
        page.locator("#needs-you [data-approve]").first.wait_for()
        tab_to(page, "#needs-you [data-approve]")
        ring = focus_ring(page)
        assert ring["style"] == "solid" and ring["width"] >= 2
        tab_to(page, "#needs-you button.ghost, #needs-you a.ghost")
        ring = focus_ring(page)
        assert ring["style"] == "solid" and ring["width"] >= 2
    finally:
        page.close()


def test_closed_phone_sheet_leaves_the_tab_order(audit_browser, audit_live):
    """F-03: the off-canvas sheet is inert while closed, so Open menu follows the skip link."""
    base, _ = audit_live
    context = audit_browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page = context.new_page()
    try:
        wait_live(page, base)
        assert page.evaluate("document.getElementById('workspace').inert") is True
        assert tab_to(page, "#nav-toggle") == 2
    finally:
        context.close()


def test_open_phone_sheet_reaches_every_destination_and_wraps(audit_browser, audit_live):
    """F-02: Tab inside the open sheet reaches Needs you and the footer, then wraps."""
    base, app = audit_live
    seed_pending_approval(app.state.store)
    context = audit_browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page = context.new_page()
    try:
        wait_live(page, base)
        tab_to(page, "#nav-toggle")
        page.keyboard.press("Enter")
        page.locator("#workspace.open").wait_for()
        assert tab_to(page, "#needs-you-open", 10) <= 4
        previous = None
        for _ in range(40):
            current = page.evaluate("document.activeElement.className")
            page.keyboard.press("Tab")
            if page.evaluate("document.activeElement.classList.contains('brand')"):
                previous = current
                break
        assert previous and "ws-foot-link" in previous  # wrapped from the last footer link
        page.keyboard.press("Escape")
        assert page.evaluate("document.activeElement.id") == "nav-toggle"
        assert page.evaluate("document.getElementById('workspace').inert") is True
    finally:
        context.close()


def test_sheet_inertness_follows_resize_across_the_breakpoint(audit_browser, audit_live):
    """F-03: loading wide then narrowing (and back) matches loading at that width."""
    base, _ = audit_live
    page = audit_browser.new_page(viewport={"width": 1440, "height": 900})
    try:
        wait_live(page, base)
        inert = "document.getElementById('workspace').inert"
        assert page.evaluate(inert) is False
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_function(inert)
        page.set_viewport_size({"width": 1440, "height": 900})
        page.wait_for_function(f"!{inert}")
    finally:
        page.close()
