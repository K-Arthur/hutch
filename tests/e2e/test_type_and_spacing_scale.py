"""One type scale and one spacing rhythm across the dashboard (DESIGN.md, "The Scale Rule").

Text sets in six steps -- caption 12, small 13, label 14, body 16, reading 17 and section 18 -- plus 24 for page
titles and figures and a fluid band for the display headline. Surfaces breathe on the 4px grid (4, 8, 12, 16, 24, 32,
40) and stacked surfaces are separated by one of the same steps. The audit reads computed style from the painted
page, so a literal that sneaks into a stylesheet fails here with the selector that painted it.
"""

from __future__ import annotations

import pytest

pw = pytest.importorskip("playwright.sync_api")

from tests.e2e.settings_pane import open_assistant_customization  # noqa: E402
from tests.e2e.test_design_system import app_server, browser  # noqa: E402,F401
from tests.e2e.test_studio_transcript import ANSWER, _seed  # noqa: E402

TYPE_STEPS = {12, 13, 14, 16, 17, 18, 24}
DISPLAY_BAND = (28, 36)                       # clamp(1.75rem, 3vw, 2.25rem): the welcome headline
GRID = {0, 4, 8, 12, 16, 24, 32, 40}

TEXT_SIZES = """() => {
  const found = [];
  for (const el of document.querySelectorAll('body *')) {
    const box = el.getBoundingClientRect();
    if (box.width < 4 || box.height < 4) continue;
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') continue;
    let own = '';
    for (const node of el.childNodes) if (node.nodeType === 3) own += node.textContent;
    if (own.trim().length < 2) continue;
    found.push({px: Math.round(parseFloat(style.fontSize) * 100) / 100, name: el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + '.'
      + String(el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className).trim().split(/\\s+/).slice(0, 2).join('.'), text: own.trim().slice(0, 20)});
  }
  return found;
}"""

# A surface is a painted box (fill or border) big enough to hold content; its padding and its gap to the next
# stacked surface are the layout rhythm a person sees.
RHYTHM = """() => {
  const name = e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + '.' + String(e.className && e.className.baseVal !== undefined ? e.className.baseVal : e.className).trim().split(/\\s+/).slice(0, 2).join('.');
  const shown = e => { const r = e.getBoundingClientRect(), s = getComputedStyle(e); return r.width > 40 && r.height > 24 && s.display !== 'none' && s.visibility !== 'hidden'; };
  const surface = e => { const s = getComputedStyle(e); return ((parseFloat(s.borderTopWidth) > 0 && s.borderTopStyle !== 'none') || s.backgroundColor !== 'rgba(0, 0, 0, 0)') && s.display !== 'inline'; };
  const pads = [], gaps = [];
  const scope = document.querySelector('.page-scroll') || document.body;
  for (const e of scope.querySelectorAll('section, article, form, div, details, a')) {
    if (!shown(e) || !surface(e)) continue;
    const r = e.getBoundingClientRect(); if (r.width < 160 || r.height < 56) continue;
    const s = getComputedStyle(e);
    pads.push({v: [s.paddingTop, s.paddingRight, s.paddingBottom, s.paddingLeft].map(x => Math.round(parseFloat(x))), name: name(e)});
    const n = e.nextElementSibling;
    if (n && shown(n) && surface(n)) { const nr = n.getBoundingClientRect(); if (Math.abs(nr.left - r.left) < 4) gaps.push({v: Math.round(nr.top - r.bottom), name: name(e) + ' -> ' + name(n)}); }
  }
  return {pads, gaps};
}"""


def _routes(base, app):
    conversation, _ = _seed(app, "scale-answer", "Plan my week", answer=ANSWER)
    gated, _ = _seed(app, "scale-gate", "Save the brief", [("list_files", {"path": "."}, "(empty)", True, 0.1)],
                     approval=dict(tool="files", action="write q3-brief.md (24 chars)", rule="ask:file-write", risk="medium",
                                   sticky_key="files:write", detail={"path": "q3-brief.md", "content": "Hello", "revision": {"exists": False}}))
    return [f"#/conversation/{conversation}", f"#/conversation/{gated}", "#/chat", "#/chats", "#/overview", "#/runs", "#/skills",
            "#/connections", "#/settings", "#/schedules", "#/runtime", "#/assistant/new", "#/bot/design-system-review", "/models", "/usage"]


def _off_type(page):
    # font-size: 0 is how a header button collapses to its icon on a narrow screen; its name stays for assistive tech
    return sorted({f"{item['px']}px  {item['name']} '{item['text']}'" for item in page.evaluate(TEXT_SIZES)
                   if item["px"] and item["px"] not in TYPE_STEPS and not DISPLAY_BAND[0] <= item["px"] <= DISPLAY_BAND[1]})


def test_text_sizes_stay_on_the_type_scale(browser, app_server):
    base, app = app_server
    routes = _routes(base, app)             # seeded once: the idempotency keys are per conversation
    offenders: dict[str, list[str]] = {}
    for label, size, mobile in (("desktop", {"width": 1440, "height": 900}, False), ("phone", {"width": 390, "height": 844}, True)):
        context = browser.new_context(viewport=size, is_mobile=mobile, has_touch=mobile, reduced_motion="reduce")
        page = context.new_page()
        for route in routes:
            page.goto(f"{base}{route}" if route.startswith("/") else f"{base}/{route}", wait_until="domcontentloaded")
            page.wait_for_timeout(900)
            if route == "#/bot/design-system-review":
                for key in ("profile", "behavior", "model", "tools", "schedule", "safety", "limits"):
                    open_assistant_customization(page, key)
                    bad = _off_type(page)
                    if bad:
                        offenders[f"{label} settings/{key}"] = bad
                continue
            bad = _off_type(page)
            if bad:
                offenders[f"{label} {route}"] = bad
        page.goto(f"{base}/#/chat", wait_until="domcontentloaded")
        page.wait_for_timeout(700)
        page.locator("#studio-conversation-options").click()
        page.wait_for_timeout(300)
        bad = _off_type(page)
        if bad:
            offenders[f"{label} options popover"] = bad
        context.close()
    assert not offenders, "text outside the type scale (12 / 13 / 14 / 16 / 17 / 18 / 24, display band 28-36):\n" + "\n".join(
        f"  {where}:\n    " + "\n    ".join(items[:10]) for where, items in offenders.items())


def test_surface_padding_and_stack_gaps_stay_on_the_grid(browser, app_server):
    base, app = app_server
    routes = _routes(base, app)             # seeded once: the idempotency keys are per conversation
    offenders: dict[str, list[str]] = {}
    for label, size, mobile in (("desktop", {"width": 1440, "height": 900}, False), ("phone", {"width": 390, "height": 844}, True)):
        context = browser.new_context(viewport=size, is_mobile=mobile, has_touch=mobile, reduced_motion="reduce")
        page = context.new_page()
        for route in routes:
            if route.startswith("/"):
                continue                       # the server-rendered report pages keep their own table rhythm
            page.goto(f"{base}/{route}", wait_until="domcontentloaded")
            page.wait_for_timeout(900)
            data = page.evaluate(RHYTHM)
            bad = sorted({f"padding {item['v']}  {item['name']}" for item in data["pads"] if any(side not in GRID for side in item["v"])}
                         | {f"gap {item['v']}px  {item['name']}" for item in data["gaps"] if item["v"] not in GRID and item["v"] > 0})
            if bad:
                offenders[f"{label} {route}"] = bad
        context.close()
    assert not offenders, "surface padding or stack gaps off the 4px grid (0 / 4 / 8 / 12 / 16 / 24 / 32 / 40):\n" + "\n".join(
        f"  {where}:\n    " + "\n    ".join(items[:10]) for where, items in offenders.items())
