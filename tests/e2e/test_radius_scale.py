"""One corner scale across the dashboard and the marketing site (DESIGN.md, "The Scale Rule").

Every corner a person can see must come from the shared scale: micro 4, control 8, panel 12, chat 20,
chip 100px, plus 50% for perfect circles (avatars, status dots, round buttons). The audit walks the
computed style of every painted element, so a new private radius -- a literal in a stylesheet, a stray
Tailwind class, an inline style -- fails here with the selector that introduced it.
"""

from __future__ import annotations

import re

import pytest

pw = pytest.importorskip("playwright.sync_api")

from tests.e2e.test_design_system import app_server, browser, site_server  # noqa: E402,F401
from tests.e2e.test_studio_transcript import ANSWER, _seed  # noqa: E402

SCALE = {"0px", "4px", "8px", "12px", "20px", "100px", "50%"}

# Computed corners of every painted element: a fill, a border, a shadow or an image. Pseudo-elements are
# not reachable from getComputedStyle on the element, so the stylesheet audit below covers them.
PAINTED_CORNERS = """() => {
  const corners = ['borderTopLeftRadius', 'borderTopRightRadius', 'borderBottomRightRadius', 'borderBottomLeftRadius'];
  const found = [];
  for (const el of document.querySelectorAll('body *')) {
    const box = el.getBoundingClientRect();
    if (box.width < 6 || box.height < 6) continue;
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') continue;
    const painted = style.backgroundColor !== 'rgba(0, 0, 0, 0)' || style.boxShadow !== 'none' || el.tagName === 'IMG'
      || ['borderTopWidth', 'borderBottomWidth', 'borderLeftWidth', 'borderRightWidth'].some(k => parseFloat(style[k]) > 0);
    if (!painted) continue;
    const radii = corners.map(k => style[k]);
    found.push({radii, name: el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + '.' + String(el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className).trim().split(/\\s+/).slice(0, 2).join('.')});
  }
  return found;
}"""

# Every literal radius a stylesheet declares, wherever the rule lives (this catches :before/:after and
# states the page is not in when the audit runs).
STYLESHEET_RADII = """() => {
  const found = [];
  const walk = (rules, href) => {
    for (const rule of rules) {
      if (rule.cssRules) walk(rule.cssRules, href);
      if (!rule.style) continue;
      for (const prop of ['border-radius', 'border-top-left-radius', 'border-top-right-radius', 'border-bottom-left-radius', 'border-bottom-right-radius']) {
        const value = rule.style.getPropertyValue(prop).trim();
        if (value) found.push({value, selector: rule.selectorText, href});
      }
    }
  };
  for (const sheet of document.styleSheets) {
    try { walk(sheet.cssRules, sheet.href || 'inline'); } catch (e) { /* cross-origin sheet */ }
  }
  return found;
}"""


LENGTH = re.compile(r"(-?\d*\.?\d+(?:e[+-]?\d+)?)(px|rem|em|%)")
SCALE_PX = {0, 4, 8, 12, 20, 100}


def _off_scale_literal(value):
    """True when a declared radius spells a length that is not on the scale (var() fallbacks count)."""
    for number, unit in LENGTH.findall(value):
        amount = float(number)
        if amount > 1e6:           # Tailwind's rounded-full, calc(infinity * 1px): a circle or a pill
            continue
        if unit == "%":
            if amount not in (0, 50):
                return True
        elif amount * (16 if unit in ("rem", "em") else 1) not in SCALE_PX:
            return True
    return False


def _off_scale(page):
    return sorted({
        f"{', '.join(sorted(set(r for r in item['radii'] if r not in SCALE)))}  {item['name']}"
        for item in page.evaluate(PAINTED_CORNERS)
        if any(r not in SCALE for r in item["radii"])
    })


def test_dashboard_corners_use_the_shared_scale(browser, app_server):
    base, app = app_server
    conversation, _ = _seed(app, "radius-answer", "Plan my week", answer=ANSWER)
    gated, _ = _seed(app, "radius-gate", "Save the brief", [("list_files", {"path": "."}, "(empty)", True, 0.1)],
                     approval=dict(tool="files", action="write q3-brief.md (24 chars)", rule="ask:file-write", risk="medium",
                                   sticky_key="files:write", detail={"path": "q3-brief.md", "content": "Hello", "revision": {"exists": False}}))
    routes = [f"#/conversation/{conversation}", f"#/conversation/{gated}", "#/chat", "#/chats", "#/overview", "#/runs",
              "#/skills", "#/connections", "#/settings", "#/bots", "#/schedules", "#/assistant/new", "#/bot/design-system-review"]
    offenders: dict[str, list[str]] = {}
    for label, size, mobile in (("desktop", {"width": 1440, "height": 900}, False), ("phone", {"width": 390, "height": 844}, True)):
        context = browser.new_context(viewport=size, is_mobile=mobile, has_touch=mobile, reduced_motion="reduce")
        page = context.new_page()
        for route in routes:
            page.goto(f"{base}/{route}", wait_until="domcontentloaded")
            page.wait_for_timeout(900)
            if mobile and route == "#/chat":
                page.locator("#nav-toggle").click()           # the sheet is a surface of its own
                page.wait_for_timeout(300)
            bad = _off_scale(page)
            if bad:
                offenders[f"{label} {route}"] = bad
        page.goto(f"{base}/#/chat", wait_until="domcontentloaded")
        page.wait_for_timeout(600)
        sheets = page.evaluate(STYLESHEET_RADII)
        context.close()
        literals = sorted({f"{item['value']}  {item['selector']}" for item in sheets if _off_scale_literal(item['value'])})
        if literals:
            offenders[f"{label} stylesheet literals"] = literals[:25]
    assert not offenders, "corners outside the scale (micro 4 / control 8 / panel 12 / chat 20 / chip 100 / 50%):\n" + "\n".join(
        f"  {where}:\n    " + "\n    ".join(items[:12]) for where, items in offenders.items())


def test_command_palette_and_model_menu_use_the_shared_scale(browser, app_server):
    base, app = app_server
    context = browser.new_context(viewport={"width": 1280, "height": 900}, reduced_motion="reduce")
    page = context.new_page()
    page.goto(f"{base}/#/chat", wait_until="domcontentloaded")
    page.wait_for_timeout(900)
    page.keyboard.press("Control+K")
    page.locator("dialog.palette[open]").wait_for(timeout=5_000)
    assert not _off_scale(page), _off_scale(page)
    page.keyboard.press("Escape")
    context.close()


def test_marketing_site_corners_use_the_shared_scale(browser, site_server):
    offenders: dict[str, list[str]] = {}
    for label, size in (("desktop", {"width": 1440, "height": 900}), ("phone", {"width": 390, "height": 844})):
        context = browser.new_context(viewport=size, reduced_motion="reduce")
        page = context.new_page()
        page.goto(site_server, wait_until="load")
        page.wait_for_timeout(500)
        bad = _off_scale(page)
        if bad:
            offenders[label] = bad
        context.close()
    assert not offenders, "marketing-site corners outside the scale:\n" + "\n".join(
        f"  {where}:\n    " + "\n    ".join(items[:12]) for where, items in offenders.items())
