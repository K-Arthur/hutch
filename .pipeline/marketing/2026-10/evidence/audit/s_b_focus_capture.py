#!/usr/bin/env python3
"""Slice S-b — focus-state + hero-actions close-up captures (closes P1-06 gap).

Fresh page, keyboard Tab traversal to the hero primary CTA, then:
- shots/s-b-focus-hero.png        focus ring on the named hero control (desktop)
- shots/s-b-hero-actions-clip-*.png  2x-DPI clips of trust line + buttons (desktop/mobile)

Re-run: uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/s_b_focus_capture.py
"""
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots"
REPO = HERE.parents[4]
SITE = REPO / "website"
PORT = 8897
BASE = f"http://127.0.0.1:{PORT}"


def tab_to_hero(page, max_tabs=25):
    for i in range(max_tabs):
        page.keyboard.press("Tab")
        info = page.evaluate(
            "() => { const a = document.activeElement;"
            " return a ? {tag: a.tagName, cls: a.className, text: (a.textContent||'').trim().slice(0,40)} : null; }")
        if info and "btn-primary" in str(info.get("cls", "")) and "See the app" in info.get("text", ""):
            in_hero = page.evaluate("() => !!document.activeElement.closest('section.hero')")
            if in_hero:
                return i + 1
    return -1


def main():
    SHOTS.mkdir(exist_ok=True)
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PORT), "-d", str(SITE)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.0)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            # desktop: keyboard focus ring on the hero primary CTA
            ctx = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="dark")
            page = ctx.new_page()
            page.goto(BASE + "/", wait_until="networkidle")
            page.wait_for_timeout(1200)
            tabs = tab_to_hero(page)
            print("tabs to hero primary:", tabs)
            page.screenshot(path=str(SHOTS / "s-b-focus-hero.png"))
            # 2x clip of the trust line + button row
            box = page.locator("section.hero .hero-actions").bounding_box()
            page.screenshot(path=str(SHOTS / "s-b-hero-actions-clip-desktop.png"),
                            clip={"x": max(box["x"] - 16, 0), "y": max(box["y"] - 48, 0),
                                  "width": box["width"] + 32, "height": box["height"] + 64})
            ctx.close()
            # mobile: same clip
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, color_scheme="dark")
            page = ctx.new_page()
            page.goto(BASE + "/", wait_until="networkidle")
            page.wait_for_timeout(1200)
            box = page.locator("section.hero .hero-actions").bounding_box()
            page.screenshot(path=str(SHOTS / "s-b-hero-actions-clip-mobile.png"),
                            clip={"x": max(box["x"] - 12, 0), "y": max(box["y"] - 40, 0),
                                  "width": box["width"] + 24, "height": box["height"] + 56})
            ctx.close()
            browser.close()
    finally:
        proc.terminate()
    print("s-b captures written to", SHOTS)


if __name__ == "__main__":
    main()
