"""Capture repeatable local app/site screenshots and check basic browser behavior.

Usage (start the isolated servers as shown in visual-validation.md first):
  .venv/bin/python docs/realignment/capture_visual_validation.py \
    --site http://127.0.0.1:8001/ --app http://127.0.0.1:18787/
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


OUT = Path(__file__).parent / "artifacts" / "visual-validation"
SIZES = {"desktop": (1440, 1000), "tablet": (900, 1024), "phone": (390, 844)}


def capture(browser, target: str, url: str) -> list[dict]:
    records = []
    for size, (width, height) in SIZES.items():
        context = browser.new_context(viewport={"width": width, "height": height}, reduced_motion="reduce")
        if size == "desktop":
            context.tracing.start(screenshots=True, snapshots=True, sources=False)
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        response = page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUT / f"{target}-{size}.png"), full_page=True, animations="disabled")
        if target == "site":
            page.screenshot(path=str(OUT / f"site-{size}-fold.png"), animations="disabled")
        record = page.evaluate("""() => ({
          title: document.title,
          viewportWidth: innerWidth,
          documentWidth: document.documentElement.scrollWidth,
          documentHeight: document.documentElement.scrollHeight,
          mainPresent: Boolean(document.querySelector('main'))
        })""")
        record.update(target=target, size=size, httpStatus=response.status if response else None,
                      screenshot=f"{target}-{size}.png", pageErrors=errors)
        if target == "site":
            ctas = page.locator("a.btn").evaluate_all("els => els.map(e => ({text:e.innerText.trim(), href:e.getAttribute('href')}))")
            record["ctas"] = ctas
            record["internalCtaTargetsExist"] = all(
                page.locator(item["href"]).count() > 0
                for item in ctas if item["href"] and item["href"].startswith("#")
            )
            if size == "phone":
                menu = page.locator("#menu-btn")
                menu.click()
                opened = menu.get_attribute("aria-expanded")
                page.keyboard.press("Escape")
                record["mobileMenu"] = {
                    "opened": opened,
                    "closed": menu.get_attribute("aria-expanded"),
                    "focusRestored": page.evaluate("document.activeElement.id") == "menu-btn",
                }
        elif target == "app":
            if size == "phone":
                toggle = page.locator("#nav-toggle")
                toggle.click()
                page.wait_for_timeout(100)
                first_focus = page.evaluate("document.activeElement.getAttribute('data-nav')")
                page.locator("#primary-nav a").last.focus()
                page.keyboard.press("Tab")
                wrapped = page.evaluate("document.activeElement.getAttribute('data-nav')")
                page.keyboard.press("Escape")
                record["mobileMenu"] = {
                    "firstFocus": first_focus,
                    "tabWrapped": wrapped,
                    "focusRestored": page.evaluate("document.activeElement.id") == "nav-toggle",
                }
        records.append(record)
        if size == "desktop":
            context.tracing.stop(path=str(OUT / f"{target}-desktop-trace.zip"))
        context.close()
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default="http://127.0.0.1:8001/")
    parser.add_argument("--app", default="http://127.0.0.1:18787/")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        records = (capture(browser, "site", args.site) + capture(browser, "app", args.app)
                   + capture(browser, "connections", args.app.rstrip("/") + "/connections")
                   + capture(browser, "usage", args.app.rstrip("/") + "/usage"))
        browser_version = browser.version
        browser.close()
    report = {"browser": "Firefox", "browserVersion": browser_version, "screenshots": records}
    (OUT / "capture-results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
