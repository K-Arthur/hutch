"""Capture onboarding and getting-started visual validation artifacts.

Captures all required pages across the 8 required viewport dimensions:
1440x1000, 1280x800, 1024x768, 900x1024, 768x1024, 390x844, 375x812, 320x740,
plus 200% zoom, text spacing, reduced motion, and keyboard focus states.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import sync_playwright

from hutch.models import Bot, iso, utcnow
from hutch.onboarding import apply_request_edit, default_setup, encode_setup
from hutch.onboarding_store import SETUP_KEY
from hutch.server.app import create_app

OUTPUT_DIR = Path("/home/kevina/CodingProjects/hutch/.worktrees/onboarding-2026-10/docs/realignment/onboarding-2026-10/artifacts")

VIEWPORTS = [
    ("1440x1000", 1440, 1000),
    ("1280x800", 1280, 800),
    ("1024x768", 1024, 768),
    ("900x1024", 900, 1024),
    ("768x1024", 768, 1024),
    ("390x844", 390, 844),
    ("375x812", 375, 812),
    ("320x740", 320, 740),
]


def run_server(state_dir: str):
    os.environ["HUTCH_STATE_DIR"] = state_dir
    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    return f"http://127.0.0.1:{port}", server, thread, app


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp_state = tempfile.mkdtemp(prefix="hutch-visuals-")

    try:
        base_url, server, thread, app = run_server(tmp_state)

        # Seed initial request
        now = utcnow()
        res = apply_request_edit(
            default_setup(now),
            expected_revision=0,
            request_text="Organize research papers, verify claims, and extract citations",
            now=now,
        )
        setup = res.setup.model_copy(update={
            "step": "ai_service",
            "route_kind": "opencode",
            "connection_name": "opencode",
        })
        app.state.store.kv_set(SETUP_KEY, encode_setup(setup))

        # Seed sample bot for later steps
        bot = app.state.store.create_bot(Bot(name="researcher", display_name="Research Assistant", model="opencode/opencode-go/beam-free"))
        setup_with_bot = setup.model_copy(update={"assistant_id": bot.id, "step": "first_request"})

        manifest = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            # 1. Capture across viewports for key pages
            pages_to_test = [
                ("01-request-step", f"{base_url}/onboarding"),
                ("02-chooser-step", f"{base_url}/onboarding/ai-service"),
                ("03-hosted-key-step", f"{base_url}/onboarding/hosted-key?provider=openai"),
                ("04-local-service-step", f"{base_url}/onboarding/local-service"),
                ("05-opencode-step", f"{base_url}/onboarding/opencode"),
                ("06-assistant-step", f"{base_url}/onboarding/assistant"),
                ("07-first-request-step", f"{base_url}/onboarding/first-request"),
            ]

            # Set setup with bot for assistant & first-request
            app.state.store.kv_set(SETUP_KEY, encode_setup(setup_with_bot))

            for vp_name, width, height in VIEWPORTS:
                context = browser.new_context(viewport={"width": width, "height": height})
                page = context.new_page()

                for page_slug, url in pages_to_test:
                    page.goto(url, wait_until="networkidle")
                    filename = f"{page_slug}-{vp_name}.png"
                    filepath = OUTPUT_DIR / filename
                    page.screenshot(path=str(filepath), full_page=True)
                    manifest.append({
                        "name": filename,
                        "viewport": vp_name,
                        "width": width,
                        "height": height,
                        "url": url,
                        "mode": "standard",
                    })

                context.close()

            # 2. Accessibility: 200% zoom (1280x800 at 2x device scale factor)
            zoom_context = browser.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=2)
            zoom_page = zoom_context.new_page()
            for page_slug, url in pages_to_test:
                zoom_page.goto(url, wait_until="networkidle")
                filename = f"{page_slug}-zoom-200.png"
                zoom_page.screenshot(path=str(OUTPUT_DIR / filename), full_page=True)
                manifest.append({"name": filename, "viewport": "1280x800", "mode": "zoom-200", "url": url})
            zoom_context.close()

            # 3. Accessibility: Text spacing override
            text_context = browser.new_context(viewport={"width": 1280, "height": 800})
            text_page = text_context.new_page()
            for page_slug, url in pages_to_test:
                text_page.goto(url, wait_until="networkidle")
                text_page.add_style_tag(content="* { line-height: 1.5 !important; letter-spacing: 0.12em !important; word-spacing: 0.16em !important; }")
                filename = f"{page_slug}-text-spacing.png"
                text_page.screenshot(path=str(OUTPUT_DIR / filename), full_page=True)
                manifest.append({"name": filename, "viewport": "1280x800", "mode": "text-spacing", "url": url})
            text_context.close()

            # 4. Accessibility: Reduced motion
            motion_context = browser.new_context(viewport={"width": 1280, "height": 800}, reduced_motion="reduce")
            motion_page = motion_context.new_page()
            for page_slug, url in pages_to_test:
                motion_page.goto(url, wait_until="networkidle")
                filename = f"{page_slug}-reduced-motion.png"
                motion_page.screenshot(path=str(OUTPUT_DIR / filename), full_page=True)
                manifest.append({"name": filename, "viewport": "1280x800", "mode": "reduced-motion", "url": url})
            motion_context.close()

            # 5. Accessibility: Keyboard focus state
            focus_context = browser.new_context(viewport={"width": 1280, "height": 800})
            focus_page = focus_context.new_page()
            focus_page.goto(f"{base_url}/onboarding", wait_until="networkidle")
            focus_page.keyboard.press("Tab")
            focus_page.keyboard.press("Tab")
            focus_filename = "01-request-step-keyboard-focus.png"
            focus_page.screenshot(path=str(OUTPUT_DIR / focus_filename), full_page=True)
            manifest.append({"name": focus_filename, "viewport": "1280x800", "mode": "keyboard-focus", "url": f"{base_url}/onboarding"})
            focus_context.close()

            # 6. Desktop Startup Captures
            desktop_file = Path("/home/kevina/CodingProjects/hutch/.worktrees/onboarding-2026-10/desktop/web/index.html").resolve()
            desktop_context = browser.new_context(viewport={"width": 800, "height": 600})
            desktop_page = desktop_context.new_page()
            desktop_page.goto(f"file://{desktop_file}")
            desktop_healthy = "desktop-startup-healthy.png"
            desktop_page.screenshot(path=str(OUTPUT_DIR / desktop_healthy))
            manifest.append({"name": desktop_healthy, "viewport": "800x600", "mode": "desktop", "url": "desktop/web/index.html"})

            # Simulate error in desktop
            desktop_page.evaluate("document.getElementById('startup-status').textContent = 'The private startup handshake failed. Quit and reopen Hutch to retry.';")
            desktop_err = "desktop-startup-error.png"
            desktop_page.screenshot(path=str(OUTPUT_DIR / desktop_err))
            manifest.append({"name": desktop_err, "viewport": "800x600", "mode": "desktop-error", "url": "desktop/web/index.html"})
            desktop_context.close()

            browser.close()

        with open(OUTPUT_DIR / "manifest.json", "w") as f:
            json.dump(manifest, f, indent=2)

        print(f"Captured {len(manifest)} visual validation artifacts to {OUTPUT_DIR}")

    finally:
        server.should_exit = True
        thread.join(timeout=5)
        shutil.rmtree(tmp_state, ignore_errors=True)


if __name__ == "__main__":
    main()
