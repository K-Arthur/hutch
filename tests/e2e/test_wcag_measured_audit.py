"""Measured UI audit fixes (docs/realignment/artifacts/ui-audit-2026-10-22/FINDINGS.md).

Each test pins one finding from the rendered-layout audit: F-01 legacy-button focus ring.
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
