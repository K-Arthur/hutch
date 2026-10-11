"""Capture and inspect the Runtime & background work page at four widths.

Run against an isolated instance (never the owner's live state):
  HUTCH_STATE_DIR=/path/state HUTCH_EXECUTOR=thread python -m hutch.cli serve --port 18790
  python docs/realignment/capture_runtime_page.py

Writes screenshots + validation.json into
docs/realignment/artifacts/runtime-page-2026-10-11/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:18790"
OUT = Path(__file__).resolve().parent / "artifacts" / "runtime-page-2026-10-11"
SIZES = (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844), ("compact-phone", 320, 740))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {"screens": [], "console_errors": [], "page_errors": [], "failed_requests": []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for name, width, height in SIZES:
            context = browser.new_context(viewport={"width": width, "height": height},
                                          reduced_motion="reduce", device_scale_factor=1)
            page = context.new_page()
            page.on("console", lambda msg: report["console_errors"].append(f"{name}: {msg.text}")
                    if msg.type == "error" else None)
            page.on("pageerror", lambda err: report["page_errors"].append(f"{name}: {err}"))
            page.on("requestfailed", lambda req: report["failed_requests"].append(f"{name}: {req.url}"))
            page.goto(f"{BASE}/#/runtime", wait_until="networkidle")
            page.wait_for_selector("h1:has-text('Runtime')", timeout=10000)
            page.wait_for_timeout(400)
            screen = {
                "size": name, "width": width, "height": height,
                "nav_current": page.locator('a[data-nav="runtime"]').get_attribute("aria-current"),
                "heading": page.locator("h1").first.inner_text(),
                "overflow_x": page.evaluate(
                    "Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth)"),
                "sections": page.locator(".runtime-card h2").all_inner_texts(),
                "attention_rows": page.locator(".runtime-attention-row").count(),
                "source_rows": page.locator(".runtime-source").count(),
                "focusable_controls": page.locator(
                    ".runtime-page button:visible, .runtime-page summary:visible, .runtime-page a:visible").count(),
            }
            page.screenshot(path=str(OUT / f"runtime-{name}.png"), full_page=True)
            if width <= 900:
                page.click("#nav-toggle")
                page.wait_for_timeout(250)
                page.screenshot(path=str(OUT / f"runtime-{name}-menu.png"), full_page=False)
                page.keyboard.press("Escape")
                page.wait_for_timeout(150)
            if name == "desktop":
                # confirm dialog (opening it is inert; Cancel never executes the action)
                page.click('[data-runtime-action="install"]')
                page.wait_for_selector(".modal-card", timeout=5000)
                page.wait_for_timeout(200)
                page.screenshot(path=str(OUT / "runtime-install-confirm.png"), full_page=False)
                page.keyboard.press("Escape")
                page.wait_for_timeout(150)
                # source events disclosure (lazy load)
                page.click(".runtime-source-events summary")
                page.wait_for_timeout(600)
                page.screenshot(path=str(OUT / "runtime-source-events.png"), full_page=True)
                # add-source modal
                page.click('[data-runtime-action="add-source"]')
                page.wait_for_selector("#runtime-source-kind", timeout=5000)
                page.wait_for_timeout(200)
                page.screenshot(path=str(OUT / "runtime-add-source.png"), full_page=False)
                page.keyboard.press("Escape")
                page.wait_for_timeout(150)
                # keyboard focus on the primary service control
                page.focus('[data-runtime-action="install"]')
                focused = page.evaluate("document.activeElement?.dataset?.runtimeAction || null")
                screen["keyboard_focus"] = focused
                page.screenshot(path=str(OUT / "runtime-keyboard-focus.png"), full_page=False)
                # accessibility facts (roles/labels present; no fake widget roles)
                screen["a11y"] = page.evaluate("""() => ({
                    headings: Array.from(document.querySelectorAll('h1,h2,h3')).map(h => h.textContent.trim()),
                    buttons: document.querySelectorAll('.runtime-page button').length,
                    labelled_sections: document.querySelectorAll('.runtime-card[aria-labelledby]').length,
                    status_regions: document.querySelectorAll('[role="status"]').length,
                })""")
            report["screens"].append(screen)
            context.close()
        browser.close()
    (OUT / "validation.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    problems = [screen for screen in report["screens"] if screen["overflow_x"] > 1
                or screen["nav_current"] != "page" or screen["source_rows"] < 2]
    if problems or report["console_errors"] or report["page_errors"] or report["failed_requests"]:
        print("PROBLEMS:", json.dumps(problems))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
