"""Capture the sign-in, pairing and Settings surfaces exactly as they ship today.

Start Hutch against a new temporary HUTCH_STATE_DIR first, then pass its origin:

    HUTCH_STATE_DIR=$(mktemp -d) hutch serve --port 8791 &
    python docs/realignment/capture_vault_signin_baseline.py http://127.0.0.1:8791 OUT_DIR

It reads nothing but what the server renders, creates no records, and writes screenshots plus a
``report.json`` of per-page console errors, horizontal overflow and the page heading. Hutch ships
one fixed dark theme (docs/design-system.md), so dark is captured at every width and an emulated
light colour scheme once, to show that nothing changes with the visitor's preference.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import Page, async_playwright

PAGES = (
    ("home", "/"),
    ("settings", "/#/settings"),
    ("connectors", "/connectors"),
    ("apps-and-ai", "/connections"),
    ("login", "/login"),
    ("pair", "/pair"),
)
WIDTHS = ((360, 800), (768, 1024), (1280, 800), (1920, 1080))
LIGHT_PROBE_WIDTH = 1280


async def measure(page: Page) -> dict:
    """Facts a reviewer needs that a screenshot alone does not give."""
    return await page.evaluate("""() => ({
        title: document.title,
        heading: (document.querySelector('h1') || {}).textContent?.trim() || '',
        overflow_x: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        focusable: document.querySelectorAll('a[href],button,input,select,textarea,[tabindex]').length,
        password_inputs: document.querySelectorAll('input[type=password]').length,
    })""")


async def capture_one(browser, origin: str, out: Path, name: str, path: str,
                      size: tuple[int, int], scheme: str) -> dict:
    context = await browser.new_context(viewport={"width": size[0], "height": size[1]},
                                        color_scheme=scheme, device_scale_factor=1)
    page = await context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
    page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
    await page.goto(origin + path, wait_until="networkidle")
    await page.wait_for_timeout(700)
    label = f"{name}-{size[0]}-{scheme}"
    await page.screenshot(path=str(out / f"{label}.png"))
    record = {"page": name, "path": path, "width": size[0], "scheme": scheme,
              "console_errors": errors, **await measure(page)}
    await context.close()
    return record


def plan() -> list[tuple[str, str, tuple[int, int], str]]:
    runs = [(n, p, size, "dark") for n, p in PAGES for size in WIDTHS]
    light = next(size for size in WIDTHS if size[0] == LIGHT_PROBE_WIDTH)
    return runs + [(n, p, light, "light") for n, p in PAGES]


async def capture(origin: str, out: Path) -> list[dict]:
    out.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        records = [await capture_one(browser, origin, out, *item) for item in plan()]
        await browser.close()
    return records


def head_commit() -> str:
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                          check=False).stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("origin")
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    records = asyncio.run(capture(args.origin.rstrip("/"), args.out))
    report = {"captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "head": head_commit(), "records": records}
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    bad = [r for r in records if r["console_errors"] or r["overflow_x"] > 0]
    print(f"captured {len(records)} views; {len(bad)} with console errors or horizontal overflow")


if __name__ == "__main__":
    main()
