"""Capture Providers, Models and first-run pages at four widths in light and dark.

Phase 0 of the 2026-11 provider expansion. Start Hutch against a fresh temporary
HUTCH_STATE_DIR first, then run:

  uv run --frozen --no-sync python docs/realignment/capture_provider_pages.py \
    --url http://127.0.0.1:18890

Records console errors, failed requests, horizontal overflow and the visible
heading text for each capture, and refuses to run if provider/account records
exist in the state (this is a first-run audit, not a populated-state pass).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import urllib.request

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "docs/realignment/artifacts/provider-expansion-2026-11/phase0"
VIEWPORTS = (("360", 360, 800), ("768", 768, 1000), ("1280", 1280, 900), ("1920", 1920, 1080))
PAGES = (("providers", "/providers"), ("models", "/models"), ("connections", "/legacy/connections"),
         ("first-run", "/#/chat"))


def _get_json(origin: str, path: str):
    with urllib.request.urlopen(origin.rstrip("/") + path, timeout=5) as response:
        return json.loads(response.read())


def _source_hash() -> str:
    digest = hashlib.sha256()
    for path in sorted((ROOT / "src/hutch").rglob("*")):
        if path.is_file() and path.suffix in {".py", ".js", ".css", ".html"}:
            digest.update(path.relative_to(ROOT).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


async def capture(origin: str, out: Path, *, require_empty: bool = True) -> dict:
    connections = _get_json(origin, "/api/v1/connections")
    accounts = _get_json(origin, "/api/v1/provider-accounts")
    populated = {"connections": connections, "accounts": accounts}
    if require_empty and (connections or accounts.get("provider_count")):
        raise SystemExit(f"Refusing capture: {populated} contains configured records")

    out.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        for page_name, path in PAGES:
            for scheme in ("light", "dark"):
                for label, width, height in VIEWPORTS:
                    page = await browser.new_page(
                        viewport={"width": width, "height": height},
                        color_scheme=scheme,
                        device_scale_factor=1,
                    )
                    errors: list[str] = []
                    failed: list[str] = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.on(
                        "console",
                        lambda message: errors.append(message.text) if message.type == "error" else None,
                    )
                    page.on(
                        "requestfailed",
                        lambda request: failed.append(f"{request.method} {request.url}"),
                    )
                    response = await page.goto(origin + path, wait_until="networkidle", timeout=30_000)
                    await page.wait_for_timeout(400)
                    overflow = await page.evaluate("document.documentElement.scrollWidth - innerWidth")
                    seen = await page.evaluate(
                        """() => ({
                          headings: [...document.querySelectorAll('h1,h2,h3')].slice(0, 12).map(h => h.innerText.trim()),
                          title: document.title,
                          body: document.body.innerText.slice(0, 4000),
                        })"""
                    )
                    name = f"{page_name}-{scheme}-{label}"
                    image = out / f"{name}.png"
                    await page.screenshot(path=str(image), full_page=True, animations="disabled")
                    records.append(
                        {
                            "page": page_name,
                            "scheme": scheme,
                            "viewport": [width, height],
                            "url": page.url,
                            "status": response.status if response else None,
                            "title": seen["title"],
                            "headings": seen["headings"],
                            "text": seen["body"],
                            "overflow_px": overflow,
                            "console_errors": errors,
                            "failed_requests": failed,
                            "screenshot": image.name,
                            "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                        }
                    )
                    await page.close()
        version = browser.version
        await browser.close()

    result = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "origin": origin,
        "browser": {"name": "chromium", "version": version},
        "git_revision": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
        ).stdout.strip(),
        "source_sha256": _source_hash(),
        "records": records,
        "scope": "first-run empty state; no provider calls, credentials or external effects",
    }
    (out / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:18890")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--allow-populated", action="store_true",
                        help="Capture a state with configured accounts instead of refusing it")
    args = parser.parse_args()
    parts = urlsplit(args.url)
    origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
    result = asyncio.run(capture(origin, args.output, require_empty=not args.allow_populated))
    for record in result["records"]:
        print(
            f"{record['page']}/{record['scheme']}/{record['viewport'][0]}: "
            f"status={record['status']} overflow={record['overflow_px']} "
            f"errors={len(record['console_errors'])} failed={len(record['failed_requests'])}"
        )


if __name__ == "__main__":
    main()
