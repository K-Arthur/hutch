"""Capture the Models page after a connection test, for four endpoint outcomes at four widths.

Phase 5 of the 2026-11 provider expansion. Start Hutch against an isolated HUTCH_STATE_DIR that holds five custom
connections (named below) pointing at a real local server, then run:

  uv run --frozen --no-sync python docs/realignment/capture_endpoint_test.py --url http://127.0.0.1:18893

For each connection the script submits the Models page's own test form pointed at it, waits for the redirect, and records the notice text, console errors, failed requests and horizontal overflow, with a screenshot.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/realignment/artifacts/provider-expansion-2026-11/phase5"
VIEWPORTS = (("360", 360, 800), ("768", 768, 1000), ("1280", 1280, 900), ("1920", 1920, 1080))
CASES = ("lms", "lmsroot", "lmstls", "closed", "ollamav1")   # works, missing /v1, https on a plain port, closed, Ollama on /v1


async def capture(origin: str, out: Path) -> list[dict]:
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        for label, width, height in VIEWPORTS:
            context = await browser.new_context(viewport={"width": width, "height": height})
            page = await context.new_page()
            console: list[str] = []
            failed: list[str] = []
            page.on("console", lambda m: console.append(m.text) if m.type == "error" else None)
            page.on("requestfailed", lambda r: failed.append(r.url))
            for name in CASES:
                await page.goto(origin + "/models")
                # Submit the Models page's own test form (its CSRF token and all), pointed at this connection.
                async with page.expect_navigation():
                    await page.evaluate("""(spec) => { const f = document.querySelector('form[action="/models/test"]');
                                           f.querySelector('[name=model]').value = spec;
                                           const pv = f.querySelector('[name=provider]'); if (pv) pv.value = spec.split('/')[0];
                                           f.requestSubmit(); }""", f"{name}/probe")
                notice = await page.evaluate("(document.querySelector('.flash span')||{}).innerText || ''")
                overflow = await page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
                shot = out / f"models-test-{name}-{label}.png"
                await page.screenshot(path=str(shot), full_page=False)
                rows.append({"case": name, "width": label, "overflow_px": overflow, "notice": notice.strip()[:600],
                             "console_errors": list(console), "failed_requests": list(failed),
                             "screenshot": shot.name})
            await context.close()
        await browser.close()
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    rows = asyncio.run(capture(args.url, args.out))
    (args.out / "results-endpoint-test.json").write_text(json.dumps(rows, indent=2) + "\n")
    bad = [r for r in rows if r["overflow_px"] > 0 or r["console_errors"] or r["failed_requests"]]
    print(f"{len(rows)} captures, {len(bad)} with overflow, console errors or failed requests")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
