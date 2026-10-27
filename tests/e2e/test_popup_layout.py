"""A popover settles on one position and one layout, at every phone height.

`place()` chooses between an anchored panel and a bottom sheet from the panel's measured size. The sheet is capped so it
stays clear of its trigger, so measuring a panel that is already a sheet gave a smaller answer than measuring the same
panel anchored: the layout flipped on every resize notification and the panel jittered between two positions, so a tap
could land on the row that had just moved. The choice must come from the panel's natural size, never from the layout it
chose last time.
"""

from __future__ import annotations

import pytest

pw = pytest.importorskip("playwright.sync_api")

from tests.e2e.test_design_system import app_server, browser  # noqa: E402,F401
from tests.e2e.test_studio_transcript import ANSWER, _seed  # noqa: E402

PANEL = ".conversation-actions-panel"

# layout, top and height of the panel on 24 consecutive frames
FRAMES = """() => new Promise(resolve => {
  const panel = document.querySelector('%s');
  const seen = [];
  let left = 24;
  const tick = () => {
    const box = panel.getBoundingClientRect();
    seen.push([panel.dataset.popupLayout, Math.round(box.top), Math.round(box.height)].join(' '));
    if (--left) requestAnimationFrame(tick); else resolve(seen);
  };
  requestAnimationFrame(tick);
})""" % PANEL


def test_options_popover_holds_one_layout_at_every_phone_height(browser, app_server):
    base, app = app_server
    conversation, _ = _seed(app, "popup-settles", "Plan my week", answer=ANSWER)
    context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, reduced_motion="reduce")
    page = context.new_page()
    try:
        page.goto(f"{base}/#/conversation/{conversation}", wait_until="domcontentloaded")
        page.locator("#studio-conversation-options").wait_for()
        layouts, unstable = set(), {}
        for height in range(560, 1000, 8):          # spans the heights where the capped sheet is shorter than the room
            page.set_viewport_size({"width": 390, "height": height})
            page.locator("#studio-conversation-options").click()
            page.locator(PANEL).wait_for(state="visible")
            seen = page.evaluate(FRAMES)
            layouts.add(seen[0].split()[0])
            if len(set(seen)) != 1:
                unstable[height] = sorted(set(seen))
            page.keyboard.press("Escape")
            page.locator(PANEL).wait_for(state="hidden")
        assert not unstable, "the options popover moved between frames at these heights:\n" + "\n".join(
            f"  {height}px: {states}" for height, states in unstable.items())
        assert layouts == {"anchored", "sheet"}, f"the sweep should cross both layouts, saw {layouts}"
    finally:
        context.close()
