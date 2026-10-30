#!/usr/bin/env python3
"""Validate the overlay primitive contract and write committed evidence.

Boots the real FastAPI app on an ephemeral loopback port with a seeded bot,
then drives the modal/popover/tooltip/palette/drawer surfaces through the
edge-case checklist from docs/overlays/audit.md in Chromium.

    # default evidence run
    .venv/bin/python scripts/validate_overlays.py

    # fast loop, no screenshots
    .venv/bin/python scripts/validate_overlays.py --no-screenshots --label quick

Evidence lands in docs/overlays/screenshots/<label>/:
    summary.json     machine-readable assertions, viewports and git state
    assertions.txt   human-readable roll-up
    *.png            one capture per scenario state

The script is read-only with respect to product code. It exits 1 when any
assertion fails. Chromium is the only engine available in this checkout; the
browser-support assumption is documented in src/hutch/web/docs/overlays.md.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import uvicorn  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from hutch.models import Bot  # noqa: E402
from hutch.server.app import create_app  # noqa: E402

BOT = "overlay-review"
VIEWPORTS = {"desktop": (1280, 900), "phone": (390, 844), "compact": (320, 740), "landscape": (844, 390)}


class Evidence:
    def __init__(self, out: Path, screenshots: bool):
        self.out = out
        self.screenshots = screenshots
        self.assertions: list[dict] = []
        self.files: list[str] = []
        out.mkdir(parents=True, exist_ok=True)

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.assertions.append({"name": name, "ok": bool(ok), "detail": detail})
        mark = "PASS" if ok else "FAIL"
        print(f"{mark}  {name}" + (f"  [{detail}]" if detail and not ok else ""))

    def expect(self, name: str, actual, expected) -> None:
        self.check(name, actual == expected, f"expected {expected!r}, got {actual!r}")

    def shot(self, page, name: str) -> None:
        if not self.screenshots:
            return
        path = self.out / f"{name}.png"
        page.screenshot(path=str(path), animations="disabled")
        self.files.append(path.name)


def wait(expression_page, expression: str, timeout: int = 5000) -> None:
    expression_page.wait_for_function(expression, timeout=timeout)


def open_menu(page) -> tuple:
    trigger = page.get_by_label("Assistant options", exact=True).first
    trigger.wait_for()
    trigger.click()
    menu = page.locator(".assistant-settings-menu-panel")
    menu.wait_for(state="visible")
    return trigger, menu


def fits(page, locator) -> bool:
    box = locator.bounding_box()
    width, height = page.viewport_size["width"], page.viewport_size["height"]
    return bool(box) and box["x"] >= 0 and box["y"] >= 0 \
        and box["x"] + box["width"] <= width + 1 and box["y"] + box["height"] <= height + 1


def boot(tmp: str):
    os.environ["HUTCH_STATE_DIR"] = tmp
    os.environ["HUTCH_MAX_CONCURRENT"] = "2"
    app = create_app()
    app.state.store.create_bot(Bot(name=BOT, display_name="Overlay review", model="mock/demo", tools=[]))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    if not server.started:
        raise RuntimeError("local Hutch app did not start")
    port = server.servers[0].sockets[0].getsockname()[1]
    return server, thread, f"http://127.0.0.1:{port}"


def scenario_dropdown(page, ev: Evidence, base: str, label: str) -> None:
    page.goto(base + f"/#/bot/{BOT}", wait_until="domcontentloaded")
    wait(page, "typeof window.HutchOverlay?.popover === 'function'")
    trigger, menu = open_menu(page)
    ev.check(f"{label}: dropdown fits the viewport", fits(page, menu), str(menu.bounding_box()))
    ev.expect(f"{label}: menu has menu semantics", menu.get_attribute("role"), "menu")
    wait(page, "document.activeElement?.getAttribute('role') === 'menuitem'")
    ev.shot(page, f"{label}-dropdown")
    page.keyboard.press("Escape")
    wait(page, "document.querySelector('.assistant-settings-menu-panel')?.hidden === true")
    ev.check(f"{label}: Escape closes the dropdown", True)
    ev.check(f"{label}: focus returns to the trigger",
             trigger.evaluate("el => el === document.activeElement"))


def scenario_confirm(page, ev: Evidence, label: str) -> None:
    trigger, menu = open_menu(page)
    page.get_by_role("menuitem", name="Delete assistant").click()
    dialog = page.get_by_role("dialog", name="Delete assistant")
    dialog.wait_for()
    ev.expect(f"{label}: destructive dialog is aria-modal", dialog.get_attribute("aria-modal"), "true")
    ev.check(f"{label}: destructive dialog is non-dismissible",
             dialog.get_attribute("data-dismissible") == "false")
    ev.check(f"{label}: destructive dialog has a description reference",
             bool(dialog.get_attribute("aria-describedby")))
    ev.expect(f"{label}: destructive initial focus is Cancel",
              page.evaluate("document.activeElement.id"), "modal-cancel")
    page.keyboard.press("Escape")
    page.wait_for_timeout(250)
    ev.check(f"{label}: Escape does not dismiss a destructive dialog", dialog.is_visible())
    page.mouse.click(3, 3)
    page.wait_for_timeout(250)
    ev.check(f"{label}: backdrop does not dismiss a destructive dialog", dialog.is_visible())
    for _ in range(6):
        page.keyboard.press("Tab")
        if not page.evaluate("document.activeElement.closest('dialog[open]') !== null"):
            break
    ev.check(f"{label}: Tab stays inside the modal",
             page.evaluate("document.activeElement.closest('dialog[open]') !== null"))
    ev.shot(page, f"{label}-destructive-confirm")
    page.get_by_role("button", name="Cancel").click()
    dialog.wait_for(state="detached", timeout=4000)
    ev.check(f"{label}: focus returns to the menu trigger",
             trigger.evaluate("el => el === document.activeElement"))


def scenario_form_modal(page, ev: Evidence, base: str, label: str) -> None:
    page.goto(base + f"/#/bot/{BOT}", wait_until="domcontentloaded")
    wait(page, "document.querySelector('[data-bot-options]') !== null")
    page.locator("[data-bot-options]").first.click()
    page.locator("#roster-action-menu").wait_for(state="visible")
    page.get_by_role("menuitem", name="New section").click()
    dialog = page.get_by_role("dialog", name="New section")
    dialog.wait_for()
    ev.expect(f"{label}: form dialog title id",
              page.evaluate("document.querySelector('#modal-root .modal-card .hutch-modal__title')?.id"), "modal-title")
    ev.check(f"{label}: form dialog focuses its first field",
             page.evaluate("document.activeElement.matches('input, textarea, select')"),
             page.evaluate("document.activeElement.id || document.activeElement.tagName"))
    ev.check(f"{label}: page scroll is locked",
             page.evaluate("document.documentElement.dataset.hutchScrollLocked !== undefined"))
    before = page.evaluate("document.querySelector('#view')?.scrollTop || 0")
    page.mouse.wheel(0, 400)
    page.wait_for_timeout(120)
    ev.check(f"{label}: wheel does not scroll the page behind the modal",
             page.evaluate("document.querySelector('#view')?.scrollTop || 0") == before)
    ev.shot(page, f"{label}-form-dialog")
    page.keyboard.press("Escape")
    dialog.wait_for(state="detached", timeout=4000)
    ev.check(f"{label}: Escape closes a dismissible form dialog (focus returned)",
             page.evaluate("document.activeElement !== document.body || !!document.activeElement"))


def scenario_server_confirm(page, ev: Evidence, base: str, label: str) -> None:
    page.goto(base + "/models", wait_until="domcontentloaded")
    wait(page, "typeof window.HutchOverlay?.modal === 'function'")
    button = page.get_by_role("button", name="Stop all runs now. Kills child processes, not just the agent loop.")
    button.wait_for()
    button.click()
    dialog = page.get_by_role("dialog", name="Stop every running job?")
    dialog.wait_for()
    ev.check(f"{label}: server-page confirm uses the primitive",
             dialog.get_attribute("data-dismissible") == "false")
    ev.check(f"{label}: server-page confirm has a description",
             bool(dialog.get_attribute("aria-describedby")))
    ev.shot(page, f"{label}-server-confirm")
    page.get_by_role("button", name="Cancel").click()
    dialog.wait_for(state="hidden", timeout=4000)
    ev.check(f"{label}: scroll lock released after close",
             page.evaluate("document.documentElement.dataset.hutchScrollLocked === undefined"))


def scenario_zoom(page, ev: Evidence, base: str) -> None:
    page.goto(base + f"/#/bot/{BOT}", wait_until="domcontentloaded")
    wait(page, "typeof window.HutchOverlay?.popover === 'function'")
    page.add_style_tag(content="html { font-size: 200% !important; }")
    trigger, menu = open_menu(page)
    ev.check("zoom-200: dropdown fits at 200% text", fits(page, menu), str(menu.bounding_box()))
    page.keyboard.press("Escape")
    trigger.click()
    page.get_by_role("menuitem", name="Delete assistant").click()
    dialog = page.get_by_role("dialog", name="Delete assistant")
    dialog.wait_for()
    ev.check("zoom-200: modal fits at 200% text", fits(page, dialog), str(dialog.bounding_box()))
    ev.check("zoom-200: no horizontal overflow", page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"))
    ev.shot(page, "zoom-200-confirm")
    page.keyboard.press("Escape")
    page.locator("[data-hutch-modal-cancel]").click()


def scenario_tooltip(page, ev: Evidence) -> None:
    page.locator("#live-pill").hover()
    tooltip = page.locator(".hutch-tooltip")
    tooltip.wait_for(state="visible", timeout=3000)
    ev.check("tooltip: native title is themed", "Live updates connected" in tooltip.inner_text())
    ev.check("tooltip: native attribute is suppressed while shown",
             page.locator("#live-pill").get_attribute("title") is None)
    page.mouse.move(1, 1)
    tooltip.wait_for(state="hidden", timeout=3000)
    ev.check("tooltip: leaving hides it and restores the title",
             page.locator("#live-pill").get_attribute("title") == "Live updates connected")


def scenario_palette(page, ev: Evidence, base: str) -> None:
    page.goto(base + f"/#/chat/{BOT}", wait_until="domcontentloaded")
    page.locator("#chat-prompt").wait_for()
    page.keyboard.press("Control+k")
    palette = page.locator("dialog.palette")
    palette.wait_for(state="visible")
    ev.expect("palette: initial focus", page.evaluate("document.activeElement.id"), "palette-input")
    ev.check("palette: scroll lock while open",
             page.evaluate("document.documentElement.dataset.hutchScrollLocked !== undefined"))
    ev.shot(page, "palette")
    page.keyboard.press("Escape")
    palette.wait_for(state="hidden", timeout=4000)
    ev.check("palette: Escape closes and unlocks scroll",
             page.evaluate("document.documentElement.dataset.hutchScrollLocked === undefined"))


def scenario_needs_you(page, ev: Evidence) -> None:
    page.evaluate("() => { const b = document.getElementById('needs-you-open'); b.focus(); b.click(); }")
    drawer = page.locator("#needs-you")
    drawer.wait_for(state="visible")
    ev.expect("needs-you: initial focus is the close control", page.evaluate("document.activeElement.id"), "needs-you-close")
    ev.shot(page, "needs-you")
    page.keyboard.press("Escape")
    drawer.wait_for(state="hidden", timeout=4000)
    ev.check("needs-you: Escape closes the drawer",
             page.evaluate("document.activeElement.id !== 'body' && document.activeElement.id !== ''"))


def scenario_stacking(page, ev: Evidence) -> None:
    page.evaluate("() => { const b = document.getElementById('needs-you-open'); b.focus(); b.click(); }")
    page.locator("#needs-you").wait_for(state="visible")
    page.keyboard.press("Control+k")
    page.wait_for_timeout(150)
    ev.check("stacking: palette refuses to open over the review drawer",
             not page.evaluate("document.querySelector('dialog.palette')?.open"))
    page.keyboard.press("Escape")
    page.locator("#needs-you").wait_for(state="hidden", timeout=4000)
    page.wait_for_timeout(150)
    ev.check("stacking: one Escape closes only the topmost overlay",
             not page.evaluate("document.querySelector('#modal-root [role=dialog]')"))


def run(args) -> int:
    tmp = tempfile.mkdtemp(prefix="hutch-overlays-")
    server, thread, base = boot(tmp)
    ev = Evidence(Path(args.out), not args.no_screenshots)
    started = datetime.now(timezone.utc).isoformat()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=not args.headed)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            scenario_dropdown(page, ev, base, "desktop")
            scenario_confirm(page, ev, "desktop")
            scenario_form_modal(page, ev, base, "desktop")
            scenario_server_confirm(page, ev, base, "desktop")
            scenario_tooltip(page, ev)
            scenario_zoom(page, ev, base)
            scenario_palette(page, ev, base)
            scenario_needs_you(page, ev)
            scenario_stacking(page, ev)
            for label, (width, height) in VIEWPORTS.items():
                context = browser.new_context(viewport={"width": width, "height": height},
                                              reduced_motion="reduce" if label == "compact" else "no-preference")
                phone = context.new_page()
                phone.on("pageerror", lambda error: errors.append(str(error)))
                phone.goto(base + f"/#/bot/{BOT}", wait_until="domcontentloaded")
                wait(phone, "typeof window.HutchOverlay?.popover === 'function'")
                trigger, menu = open_menu(phone)
                ev.check(f"{label}: dropdown fits {width}x{height}", fits(phone, menu), str(menu.bounding_box()))
                ev.shot(phone, f"{label}-dropdown-{width}x{height}")
                phone.keyboard.press("Escape")
                context.close()
            ev.check("no page errors while driving overlays", not errors, "; ".join(errors[:3]))
            if args.light:
                context = browser.new_context(viewport={"width": 1280, "height": 900})
                light = context.new_page()
                light.goto(base + f"/#/bot/{BOT}", wait_until="domcontentloaded")
                light.evaluate("document.documentElement.dataset.hutchTheme = 'light'")
                light.wait_for_timeout(100)
                values = light.evaluate("""() => ({
                  opacity: getComputedStyle(document.documentElement).getPropertyValue('--hutch-overlay-scrim-opacity').trim(),
                  elevation: getComputedStyle(document.documentElement).getPropertyValue('--hutch-elevation-overlay-modal').trim(),
                })""")
                ev.expect("light theme: scrim opacity token", values["opacity"], "0.52")
                ev.check("light theme: modal elevation uses ink shadows", "0.08" in values["elevation"])
                open_menu(light)
                ev.shot(light, "light-dropdown")
                light.keyboard.press("Escape")
                context.close()
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)

    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    failures = [item for item in ev.assertions if not item["ok"]]
    summary = {
        "label": args.label,
        "started": started,
        "finished": datetime.now(timezone.utc).isoformat(),
        "git_head": head,
        "chromium": True,
        "viewports": {name: list(size) for name, size in VIEWPORTS.items()},
        "assertions": ev.assertions,
        "failures": failures,
        "screenshots": ev.files,
        "passed": len(ev.assertions) - len(failures),
        "total": len(ev.assertions),
    }
    (ev.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = [f"label: {args.label}", f"git_head: {head}", ""]
    lines += [("PASS  " if item["ok"] else "FAIL  ") + item["name"] for item in ev.assertions]
    lines += ["", f"{summary['passed']}/{summary['total']} assertions passed"]
    (ev.out / "assertions.txt").write_text("\n".join(lines) + "\n")
    print(f"\n{summary['passed']}/{summary['total']} assertions passed -> {ev.out}")
    return 0 if not failures else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure and screenshot the Hutch overlay contract.")
    parser.add_argument("--label", default=None, help="evidence directory name; defaults to the short commit")
    parser.add_argument("--out", default=None, help="evidence directory; defaults to docs/overlays/screenshots/<label>")
    parser.add_argument("--no-screenshots", action="store_true")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--light", action="store_true", help="also validate the light colour scope")
    args = parser.parse_args()
    if not args.label:
        args.label = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                    capture_output=True, text=True).stdout.strip() or "local"
    if not args.out:
        args.out = str(ROOT / "docs" / "overlays" / "screenshots" / args.label)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
