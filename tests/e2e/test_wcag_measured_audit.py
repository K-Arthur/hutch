"""Measured UI audit fixes (docs/realignment/artifacts/ui-audit-2026-10-22/FINDINGS.md).

Each test pins one finding from the rendered-layout audit: F-01 legacy-button focus ring,
F-02 phone sheet focus wrap, F-03 closed sheet out of the tab order, F-04/F-06 chat header and
reminder overlap, F-05 reminder clearance at the end of a page, F-13 reminder landmark.
"""
from __future__ import annotations

from hutch.models import ApprovalMode, Bot, Run, RunStatus
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


HEADER_OVERLAPS = """() => {
  const box = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 ? r : null; };
  const parts = [...document.querySelectorAll('.app-top .ctx-id .avatar, .app-top .ctx-id h1, .app-top .ctx-meta > *, '
    + '.app-top .ctx-actions > :not(.visually-hidden), .app-top-status .w')].map(e => ({e, r: box(e)})).filter(p => p.r);
  const meet = (a, b) => Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1 && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1;
  const label = e => e.id || e.className || e.tagName;
  const overlaps = [];
  for (const [i, a] of parts.entries()) for (const b of parts.slice(i + 1))
    if (!a.e.contains(b.e) && !b.e.contains(a.e) && meet(a.r, b.r)) overlaps.push(`${label(a.e)} x ${label(b.e)}`);
  const bar = document.getElementById('attention-bar'), barBox = bar.hidden ? null : box(bar);
  const covered = barBox ? parts.filter(p => meet(p.r, barBox)).map(p => label(p.e)) : [];
  return {overlaps, covered, reminder: !!barBox};
}"""


def start_waiting_conversation(page, base, store, name="audit-header"):
    """Drive a real deterministic conversation to an approval so Review/Stop and the reminder show."""
    store.create_bot(Bot(name=name, display_name="Research assistant", model="mock/demo",
                         description="Audit fixture with a description long enough to need truncation in the header.",
                         tools=["files", "memory"], approval_mode=ApprovalMode.ask))
    seed_pending_approval(store)  # a second request elsewhere keeps the reminder on screen
    page.goto(f"{base}/#/chat/{name}")
    page.locator("#chat-prompt").fill("write a report")
    page.locator("#chat-send").click()
    page.locator("#chat-stream [data-approval-card]").wait_for()


def test_chat_header_and_reminder_never_overlap_across_widths(audit_browser, audit_live):
    """F-04 + F-06: header parts and the reminder never cover each other from tablet to wide desktop."""
    base, app = audit_live
    page = audit_browser.new_page(viewport={"width": 1440, "height": 900})
    try:
        start_waiting_conversation(page, base, app.state.store)
        page.locator("#studio-stop-run").wait_for()
        for width in (768, 899, 901, 1024, 1280, 1440):
            page.set_viewport_size({"width": width, "height": 900})
            page.wait_for_timeout(150)
            result = page.evaluate(HEADER_OVERLAPS)
            assert result["reminder"], width
            assert result["overlaps"] == [] and result["covered"] == [], (width, result)
    finally:
        page.close()


def test_floating_reminder_leaves_the_last_page_control_uncovered(audit_browser, audit_live):
    """F-05: at desktop width the focused 'Show more' at the end of Work history is not under the reminder."""
    base, app = audit_live
    store = app.state.store
    bot = seed_pending_approval(store)
    for index in range(30):
        store.create_run(Run(bot_id=bot.id, prompt=f"Synthetic history entry {index}", status=RunStatus.succeeded))
    page = audit_browser.new_page(viewport={"width": 1024, "height": 900})
    try:
        wait_live(page, base)
        page.goto(base + "/#/runs")
        page.locator("#runs-more").wait_for()
        page.locator("#attention-bar:not([hidden])").wait_for()
        tab_to(page, "#runs-more", 160)
        page.wait_for_timeout(200)
        assert page.evaluate("""() => { const e = document.activeElement, r = e.getBoundingClientRect();
            const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
            return hit === e || e.contains(hit); }""")
        assert page.get_by_role("complementary", name="Pending work").count() == 1
    finally:
        page.close()


def test_service_tile_names_never_break_inside_a_word(audit_browser, audit_live):
    """F-07: narrow two-column tiles stack the state badge instead of squeezing the name."""
    base, _ = audit_live
    page = audit_browser.new_page(viewport={"width": 768, "height": 900})
    try:
        wait_live(page, base)
        page.goto(base + "/#/connections")
        page.locator("article.service-tile h3").first.wait_for()
        broken = page.evaluate("""() => [...document.querySelectorAll('article.service-tile h3')].filter(h => {
            const probe = document.createElement('span');
            probe.style.cssText = 'position:absolute;visibility:hidden;white-space:nowrap;font:' + getComputedStyle(h).font;
            document.body.append(probe);
            const longest = Math.max(...h.textContent.trim().split(/\\s+/).map(word => {
                probe.textContent = word; return probe.getBoundingClientRect().width; }));
            probe.remove();
            return h.getBoundingClientRect().width + 0.5 < longest; }).map(h => h.textContent.trim())""")
        assert broken == []
    finally:
        page.close()


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
