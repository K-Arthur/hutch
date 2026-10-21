"""Capture the application's real empty first-run screen at desktop/tablet/phone sizes.

Start Hutch against a new temporary HUTCH_STATE_DIR before invoking this script.
It refuses to capture if bots, runs, approvals, or a populated first-run screen exist.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "docs/realignment/artifacts/no-mock-setup"
VIEWPORTS = (("desktop", 1440, 960), ("tablet", 900, 1024),
             ("phone", 390, 844), ("compact-phone", 320, 740))
def source_hashes() -> dict[str, str]:
    """Tie screenshots to all shipped Hutch sources, including compiled UI styles."""
    paths = sorted(
        path for path in (ROOT / "src/hutch").rglob("*")
        if path.is_file() and path.suffix in {".py", ".js", ".css", ".html"}
    )
    return {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


def get_json(origin: str, path: str):
    with urllib.request.urlopen(origin.rstrip("/") + path, timeout=3) as response:
        return json.loads(response.read())


async def capture(url: str, out: Path) -> None:
    parts = urlsplit(url)
    origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
    checks = {
        "bots": "/api/bots",
        "runs": "/api/runs",
        "approvals": "/api/approvals",
        "conversations": "/api/v1/conversations",
        "configured_connections": "/api/v1/connections",
    }
    for endpoint in checks.values():
        value = get_json(origin, endpoint)
        if value != []:
            raise SystemExit(f"Refusing capture: {endpoint} contains product records")

    out.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        records = []
        for name, width, height in VIEWPORTS:
            page = await browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            await page.goto(url, wait_until="networkidle")
            await page.get_by_text("No assistants yet — create one.", exact=True).wait_for(state="visible")
            intro = page.get_by_text("If you need help choosing an AI service, Hutch can guide you.", exact=False)
            if not await intro.is_visible():
                raise SystemExit(f"Refusing capture: real first-run explanation missing at {name}")
            overflow = await page.evaluate("document.documentElement.scrollWidth - innerWidth")
            if overflow > 1 or errors:
                raise SystemExit(f"Visual capture failed at {name}: overflow={overflow}, errors={errors}")
            path = out / f"setup-{name}.png"
            await page.screenshot(path=str(path), animations="disabled")
            records.append({"name": name, "viewport": [width, height], "path": path.name,
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "overflow_px": overflow, "page_errors": errors})
            await page.close()
        await browser.close()
        result = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "url": url,
            "state_check": {name: [] for name in checks},
            "browser": {"name": "chromium", "version": browser.version,
                        "playwright": importlib.metadata.version("playwright")},
            "git_revision": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                                           capture_output=True, text=True).stdout.strip(),
            "source_sha256": source_hashes(),
            "screenshots": records,
            "scope": "real local first-run UI; empty temporary application database; no provider calls or external effects",
        }
        (out / "results.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:18789/#/chat")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    asyncio.run(capture(args.url, args.output))


if __name__ == "__main__":
    main()
