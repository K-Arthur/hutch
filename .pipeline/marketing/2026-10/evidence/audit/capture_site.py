#!/usr/bin/env python3
"""Phase 1 audit — visual baseline captures of the built site (dark-only theme).

Re-run: uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/capture_site.py
Writes: evidence/audit/shots/*.png and focus-trace.txt (same dir as this script).
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
PORT = 8898
BASE = f"http://127.0.0.1:{PORT}"

VIEWPORTS = [
    ("desktop", 1440, 900),
    ("tablet", 768, 1024),
    ("mobile", 390, 844),
    ("narrow-zoom-proxy", 320, 568),  # ~200% text-enlargement proxy
]


def main():
    SHOTS.mkdir(exist_ok=True)
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PORT), "-d", str(SITE)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.0)
    trace = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for name, w, h in VIEWPORTS:
                ctx = browser.new_context(viewport={"width": w, "height": h},
                                          color_scheme="dark",
                                          reduced_motion="no-preference")
                page = ctx.new_page()
                page.goto(BASE + "/", wait_until="networkidle")
                page.wait_for_timeout(1200)  # let reveal watchdog settle
                page.screenshot(path=str(SHOTS / f"{name}-top.png"))
                page.screenshot(path=str(SHOTS / f"{name}-full.png"), full_page=True)
                if name == "desktop":
                    # FAQ open state
                    page.locator("#faq details").first.click()
                    page.wait_for_timeout(300)
                    page.locator("#faq").scroll_into_view_if_needed()
                    page.screenshot(path=str(SHOTS / "desktop-faq-open.png"))
                    # availability details open (decision content)
                    page.locator(".availability-details summary").click()
                    page.wait_for_timeout(300)
                    page.locator("#get").scroll_into_view_if_needed()
                    page.screenshot(path=str(SHOTS / "desktop-availability-open.png"))
                    # keyboard focus trace through the header
                    page.keyboard.press("Tab")
                    for _ in range(8):
                        el = page.evaluate("() => { const a = document.activeElement; return a ? (a.tagName + ':' + (a.textContent||'').trim().slice(0,30) + ':' + (a.id||a.className||'').toString().slice(0,40)) : 'none'; }")
                        trace.append(el)
                        page.keyboard.press("Tab")
                    # capture focus ring state on nav link
                    page.screenshot(path=str(SHOTS / "desktop-focus-nav.png"))
                if name == "mobile":
                    page.locator("#menu-btn").click()
                    page.wait_for_timeout(300)
                    page.screenshot(path=str(SHOTS / "mobile-drawer-open.png"))
                if name == "narrow-zoom-proxy":
                    # 200% text enlargement via root font-size
                    page.evaluate("() => document.documentElement.style.fontSize = '32px'")
                    page.wait_for_timeout(300)
                    page.screenshot(path=str(SHOTS / "narrow-text-200.png"))
                ctx.close()
            # reduced-motion context: nothing should be hidden
            ctx = browser.new_context(viewport={"width": 1440, "height": 900},
                                      reduced_motion="reduce")
            page = ctx.new_page()
            page.goto(BASE + "/", wait_until="networkidle")
            page.wait_for_timeout(600)
            hidden = page.evaluate("""() => {
              const els = document.querySelectorAll('.reveal, [style*="opacity"]');
              let n = 0;
              els.forEach(e => { const s = getComputedStyle(e); if (parseFloat(s.opacity) < 0.99) n++; });
              return n;
            }""")
            trace.append(f"reduced-motion: elements with opacity<0.99 = {hidden}")
            page.screenshot(path=str(SHOTS / "desktop-reduced-motion.png"))
            ctx.close()
            browser.close()
    finally:
        proc.terminate()
    (HERE / "focus-trace.txt").write_text("\n".join(trace) + "\n")
    print("captures written to", SHOTS)


if __name__ == "__main__":
    main()
