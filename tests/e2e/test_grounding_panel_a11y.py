"""Accessibility journey for the evidence panel: keyboard operation, visible focus,
alt text, reduced motion, and (when a local axe-core file is provided) an automated audit.

The axe run is opt-in because the audit library is a third-party ~550 KB script that this
repo does not vendor: set ``HUTCH_AXE_CORE=/path/to/axe.min.js`` to include it. The
keyboard/alt/reduced-motion checks always run.
"""

from __future__ import annotations

import os
from pathlib import Path

from tests.e2e.grounding_fixtures import (  # noqa: F401 - the fixtures are the point
    browser, live, open_panel, seed_grounded_run,
)


def test_panel_keyboard_alt_text_and_reduced_motion(browser, live):
    base, _app, state_dir = live
    run_id = seed_grounded_run(state_dir)
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    try:
        problems = open_panel(page, base, run_id)
        panel = page.locator("[data-evidence-panel]")

        # every inspected frame carries real alt text (it is the only readable form of the crop)
        alts = page.eval_on_selector_all(".evidence-frame img", "els => els.map(e => e.alt)")
        assert alts and all(a.strip() for a in alts), alts

        # a details summary is keyboard operable (Enter and Space) and takes visible focus
        summary = panel.locator("details.evidence-block summary").first
        summary.focus()
        page.keyboard.press("Tab")           # leave by keyboard...
        page.keyboard.press("Shift+Tab")     # ...and return, so :focus-visible applies
        assert page.evaluate("() => document.activeElement.tagName") == "SUMMARY"
        assert page.evaluate("() => document.activeElement.matches(':focus-visible')")
        outline = page.evaluate("() => getComputedStyle(document.activeElement).outlineStyle")
        assert outline != "none", "keyboard focus must be visible"
        state_before = summary.evaluate("el => el.parentElement.open")
        page.keyboard.press("Enter")
        assert summary.evaluate("el => el.parentElement.open") != state_before
        page.keyboard.press("Space")
        assert summary.evaluate("el => el.parentElement.open") == state_before

        # status chips carry text, never color alone
        chip = panel.locator(".evidence-claim-meta .ev-chip").first
        assert (chip.inner_text() or "").strip()

        # reduced motion zeroes the shared duration tokens (global handling, not per-widget)
        page.emulate_media(reduced_motion="reduce")
        duration = page.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--dur').trim()")
        assert duration in ("0ms", "0s"), duration

        assert not problems, problems

        axe_path = os.environ.get("HUTCH_AXE_CORE", "")
        if axe_path and Path(axe_path).is_file():
            page.add_script_tag(path=axe_path)
            result = page.evaluate(
                "async () => await axe.run(document.querySelector('#view') || document.body, {resultTypes: ['violations']})")
            serious = [v for v in result.get("violations", [])
                       if v.get("impact") in ("serious", "critical")]
            assert not serious, [(v["id"], v["impact"], v["nodes"][0]["target"]) for v in serious[:6]]
    finally:
        page.close()
