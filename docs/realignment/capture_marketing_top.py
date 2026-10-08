"""Capture anonymous marketing hero views at desktop, tablet, and phone widths."""

from __future__ import annotations

from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import hashlib
import importlib.metadata
import json
import platform
import subprocess

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs/realignment/artifacts/marketing-top"


class QuietSiteHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "website"), **kwargs)

    def log_message(self, *_args):
        pass


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), QuietSiteHandler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    captures = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            for width, height, size in (
                (1440, 1000, "desktop"),
                (900, 1024, "tablet"),
                (390, 844, "phone"),
            ):
                context = browser.new_context(
                    viewport={"width": width, "height": height}, reduced_motion="reduce"
                )
                page = context.new_page()
                errors: list[str] = []
                requests: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("request", lambda request: requests.append(request.url))
                base = f"http://127.0.0.1:{server.server_port}/"
                page.goto(base, wait_until="networkidle")
                page.evaluate("document.fonts.ready")
                overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
                assert overflow <= 1, (size, overflow)
                assert not errors, (size, errors)
                assert all(url.startswith(base) for url in requests), (size, requests)
                image = OUTPUT / f"{size}.png"
                page.screenshot(path=str(image), animations="disabled")
                full_image = OUTPUT / f"{size}-full.png"
                page.screenshot(path=str(full_image), full_page=True, animations="disabled")
                captures.append(
                    {
                        "size": size,
                        "viewport": [width, height],
                        "path": image.relative_to(ROOT).as_posix(),
                        "full_page_path": full_image.relative_to(ROOT).as_posix(),
                        "horizontal_overflow": overflow,
                        "page_errors": errors,
                        "requests_same_origin": True,
                    }
                )
                context.close()
            record = {
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "command": ".venv/bin/python docs/realignment/capture_marketing_top.py",
                "browser": "chromium",
                "browser_version": browser.version,
                "playwright_version": importlib.metadata.version("playwright"),
                "python_version": platform.python_version(),
                "git_revision": subprocess.run(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
                ).stdout.strip(),
                "site": "anonymous local static site; no credentials or external requests",
                "reduced_motion": True,
                "source_sha256": {
                    name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                    for name in (
                        "website/index.html",
                        "website/styles.css",
                        "website/site.js",
                        "website/app.css",
                        "website/tokens.css",
                        "website/assets/captures/setup-desktop.webp",
                        "website/assets/captures/setup-phone.webp",
                        "website/assets/hutch-agent.webp",
                        "website/assets/fonts/archivo-latin-var.woff2",
                    )
                },
                "captures": captures,
            }
            (OUTPUT / "capture.json").write_text(json.dumps(record, indent=2) + "\n")
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
        assert not worker.is_alive(), "marketing capture server did not stop"


if __name__ == "__main__":
    main()
