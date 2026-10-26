"""Regenerate the marketing site's response-style captures from the real assistant settings panel.

Starts the actual Hutch app in-process against a new temporary state directory, creates the fictional
`Design Partner` assistant (no model route, request or output), saves the Warm / Detailed / Off response
style through the real controls, and crops the Response style panel at the two sizes the page embeds
(586x383 beside the copy, 340x544 on phones). Nothing is mocked or composited.

    PYTHONPATH=src python docs/realignment/capture_response_style.py
    node scripts/stamp_site_assets.mjs
"""
from __future__ import annotations

import io
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
from PIL import Image
from playwright.sync_api import sync_playwright

from hutch.models import Bot
from hutch.server.app import create_app

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "website/assets/captures"
# name, viewport, touch, crop size embedded by website/index.html
# The desktop viewport is chosen so the settings pane (viewport - 272px sidebar - 64px gutters - 240px rail) is exactly
# the 586px the page embeds; the phone pane is the viewport minus its 32px gutters.
SIZES = (("desktop", (1162, 960), False, (586, 383)), ("phone", (390, 844), True, (340, 544)))


def serve(state: str):
    import os
    os.environ["HUTCH_STATE_DIR"] = state
    app = create_app()
    app.state.store.create_bot(Bot(name="design-partner", display_name="Design Partner", model="mock/demo", tools=[]))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", lifespan="on"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.02)
    return server, f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}"


def open_behavior(page, base: str) -> None:
    page.goto(f"{base}/#/bot/design-partner", wait_until="domcontentloaded")
    page.locator('[data-settings-tab="behavior"]').click()
    page.locator("#persona-form-slot .persona-form").wait_for()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="hutch-response-style-") as state:
        server, base = serve(state)
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                saved = False
                for name, (width, height), touch, (crop_w, crop_h) in SIZES:
                    context = browser.new_context(viewport={"width": width, "height": height}, is_mobile=touch,
                                                  has_touch=touch, reduced_motion="reduce")
                    page = context.new_page()
                    open_behavior(page, base)
                    form = page.locator("#persona-form-slot .persona-form")
                    if not saved:                       # the first pass saves; later passes show the stored choice
                        form.locator('[data-persona-field="preset"]').select_option(label="Warm")
                        form.locator('[data-persona-field="depth"]').select_option(label="Detailed")
                        form.locator('[data-persona-field="humor"]').select_option(label="Off")
                        form.locator("[data-persona-save]").click()
                        page.get_by_text("Saved.", exact=True).wait_for()
                        saved = True
                        open_behavior(page, base)       # reload: the panel must show what was really saved
                    assert form.locator('[data-persona-origin="humor"]').inner_text().startswith("Saved for this assistant")
                    panel = form.bounding_box()
                    page.evaluate("document.fonts.ready")
                    page.locator("main#view > .page-scroll").evaluate("el => el.scrollTo(0, 0)")
                    page.evaluate(f"document.querySelector('#persona-form-slot').scrollIntoView({{block: 'start'}})")
                    page.wait_for_timeout(300)
                    panel = form.bounding_box()
                    assert panel["width"] >= crop_w - 20, f"{name}: the panel is narrower than the crop it must fill"
                    rail = page.locator(".settings-rail").bounding_box()
                    assert width >= 900 or panel["y"] >= rail["y"] + rail["height"] - 1, f"{name}: the sticky rail covers the panel title"
                    shot = Image.open(io.BytesIO(page.screenshot(clip={"x": panel["x"], "y": panel["y"], "width": crop_w, "height": crop_h})))
                    shot.convert("RGB").save(OUT / f"response-style-{name}.webp", "WEBP", quality=82, method=6)
                    print(f"{name}: panel {panel['width']:.0f}x{panel['height']:.0f} -> {crop_w}x{crop_h}")
                    context.close()
                browser.close()
        finally:
            server.should_exit = True


if __name__ == "__main__":
    main()
