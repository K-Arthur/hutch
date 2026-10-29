"""Capture committed HEAD marketing pages at desktop, tablet, and phone widths.

The working-tree copy of website/ is dirty with another session's uncommitted
brand work, so this script never reads or serves it. It exports committed HEAD
content with "git archive HEAD -- website" into a scratch directory, serves that
exported tree over loopback from an ephemeral port, and records normal and
full-page PNGs plus a JSON evidence file under
docs/realignment/artifacts/completion-2026-10-29/marketing/.
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlparse
import hashlib
import importlib.metadata
import io
import json
import os
import platform
import re
import shutil
import subprocess
import tarfile

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs/realignment/artifacts/completion-2026-10-29/marketing"
SCRATCH = ROOT / ".worktrees/completion-c-scratch/marketing-head"
COMMAND = ".venv/bin/python docs/realignment/capture_marketing_head.py"

VIEWPORTS = (
    ("desktop", 1440, 900),
    ("tablet", 900, 900),
    ("phone", 360, 800),
)

SOURCE_FILES = (
    "website/index.html",
    "website/styles.css",
    "website/styles.min.css",
    "website/app.css",
    "website/tokens.css",
    "website/site.js",
)

# HEAD commits the Geist fonts. The Bricolage and Archivo fonts exist only in
# other checkouts' dirty working trees, so candidates are ordered by what HEAD
# is expected to export; the first existing candidate is served and hashed.
FONT_CANDIDATES = (
    "website/assets/fonts/geist-latin-var.woff2",
    "website/assets/fonts/archivo-latin-var.woff2",
    "website/assets/fonts/bricolage-grotesque-latin-800.woff2",
)

OG_CARD = "website/assets/og-card-1200x630.png"

METADATA_JS = """() => {
  const canonical = document.querySelector('link[rel="canonical"]');
  const ogImage = document.querySelector('meta[property="og:image"]');
  const ogTitle = document.querySelector('meta[property="og:title"]');
  return {
    title: document.title,
    canonical_href: canonical === null ? null : canonical.getAttribute("href"),
    og_image_content: ogImage === null ? null : ogImage.getAttribute("content"),
    og_title_content: ogTitle === null ? null : ogTitle.getAttribute("content"),
  };
}"""

LAZY_IMAGES_JS = """async () => {
  const images = Array.from(document.images);
  const step = Math.max(200, Math.floor(innerHeight * 0.8));
  for (let y = 0; y < document.documentElement.scrollHeight; y += step) {
    window.scrollTo(0, y);
    await new Promise((resolve) => setTimeout(resolve, 40));
  }
  window.scrollTo(0, 0);
  await Promise.all(images.map((image) => {
    if (image.complete) return null;
    return new Promise((resolve) => {
      image.onload = resolve;
      image.onerror = resolve;
    });
  }));
}"""

WORKING_TREE_NOTE = (
    "The git working tree is dirty with other sessions' uncommitted work, so the "
    "working-tree copy of website/index.html and the rest of website/ was excluded. "
    "All served content is committed HEAD content exported with "
    "'git archive HEAD -- website' into "
    ".worktrees/completion-c-scratch/marketing-head/website; no working-tree "
    "website file was read, modified, staged or reverted."
)


def run_git(*args: str) -> bytes:
    """Run a git command at the repository root and return its stdout bytes."""
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True
    ).stdout


def sha256(path: Path) -> str:
    """Return the SHA-256 hex digest of one file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_head_website() -> Path:
    """Materialize committed HEAD website content under the scratch directory."""
    scratch = SCRATCH.resolve()
    worktrees = (ROOT / ".worktrees").resolve()
    assert scratch.is_relative_to(worktrees), scratch
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    archive = run_git("archive", "HEAD", "--", "website")
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        try:
            tar.extractall(scratch, filter="data")
        except TypeError:  # Python < 3.12 has no extraction filters
            tar.extractall(scratch)
    served = scratch / "website"
    assert (served / "index.html").is_file(), served
    return served


class QuietSiteHandler(SimpleHTTPRequestHandler):
    """Serve the exported HEAD website without writing access logs."""

    def __init__(self, *args, directory: str, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, _format: str, *_args) -> None:
        pass


def process_tree_children() -> dict[int, list[int]]:
    """Map parent process ids to their direct children via /proc."""
    children: dict[int, list[int]] = {}
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        try:
            stat = Path("/proc", name, "stat").read_text()
        except OSError:
            continue
        fields = stat.rsplit(")", 1)[-1].split()
        if not fields:
            continue
        children.setdefault(int(fields[1]), []).append(int(name))
    return children


def launched_browser_executable() -> str:
    """Return the executable path of the browser this process launched."""
    children = process_tree_children()
    pending = list(children.get(os.getpid(), []))
    seen: set[str] = set()
    while pending:
        pid = pending.pop()
        pending.extend(children.get(pid, []))
        try:
            executable = os.readlink(f"/proc/{pid}/exe")
        except OSError:
            continue
        if "ms-playwright" not in executable:
            continue
        if Path(executable).name in {"chrome", "chrome-headless-shell"}:
            seen.add(executable)
    assert seen, "could not identify the launched Playwright browser executable"
    return sorted(seen)[0]


def chromium_build(executable: str) -> tuple[str, str]:
    """Split an installed Chromium path into its build directory and revision."""
    match = re.search(r"(chromium(?:_headless_shell)?)-(\d+)", executable)
    assert match is not None, executable
    return match.group(0), match.group(2)


def is_absolute_url(value: str | None) -> bool:
    """Return True when value is an absolute http(s) URL."""
    if not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def assert_metadata(page) -> dict[str, object]:
    """Assert page-level canonical, Open Graph and title metadata in the serve page."""
    raw = page.evaluate(METADATA_JS)
    checks = {
        "title_present": bool(raw["title"]),
        "canonical_present": bool(raw["canonical_href"]),
        "canonical_absolute": is_absolute_url(raw["canonical_href"]),
        "og_image_present": bool(raw["og_image_content"]),
        "og_image_absolute": is_absolute_url(raw["og_image_content"]),
        "og_title_present": bool(raw["og_title_content"]),
    }
    assert all(checks.values()), (checks, raw)
    return {
        "source": "document head of the served HEAD page",
        "title": raw["title"],
        "canonical_href": raw["canonical_href"],
        "og_image_content": raw["og_image_content"],
        "og_title_content": raw["og_title_content"],
        "og_image_local_file": OG_CARD,
        "checks": checks,
    }


def main() -> None:
    """Export HEAD website content, capture three widths, and write evidence."""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    served = export_head_website()

    sources = {
        name: sha256(served / name.removeprefix("website/")) for name in SOURCE_FILES
    }
    font = next(
        (name for name in FONT_CANDIDATES if (served / name.removeprefix("website/")).is_file()),
        None,
    )
    assert font is not None, "no known HEAD font file was exported"
    sources[font] = sha256(served / font.removeprefix("website/"))
    sources[OG_CARD] = sha256(served / OG_CARD.removeprefix("website/"))

    tracked = {
        "website/sitemap.xml": served / "sitemap.xml",
        "website/robots.txt": served / "robots.txt",
    }
    sitemap_robots = {
        name: {
            "path": name,
            "exists": path.is_file(),
            "sha256": sha256(path) if path.is_file() else None,
        }
        for name, path in tracked.items()
    }
    assert all(entry["exists"] for entry in sitemap_robots.values()), sitemap_robots

    dirty_website = sorted(
        line.strip()
        for line in run_git("status", "--porcelain", "--", "website")
        .decode("utf-8")
        .splitlines()
        if line.strip()
    )

    captures: list[dict[str, object]] = []
    horizontal_overflow: dict[str, int] = {}
    page_errors: dict[str, list[str]] = {}
    requests_same_origin: dict[str, bool] = {}
    paths: dict[str, str] = {}
    viewports: dict[str, dict[str, int]] = {}
    metadata: dict[str, object] = {}
    browser_info: dict[str, object] = {}

    handler = partial(QuietSiteHandler, directory=str(served))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    origin = f"http://127.0.0.1:{server.server_port}"
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            executable = launched_browser_executable()
            build_directory, revision = chromium_build(executable)
            browser_info = {
                "engine": "chromium",
                "name": "Chrome for Testing",
                "version": browser.version,
                "headless": True,
                "executable_path": executable,
                "build_directory": build_directory,
                "revision": revision,
                "matching_full_chromium_build_directory": chromium_build(
                    playwright.chromium.executable_path
                )[0],
                "playwright_registry_executable_path": playwright.chromium.executable_path,
            }
            for size, width, height in VIEWPORTS:
                context = browser.new_context(
                    viewport={"width": width, "height": height},
                    reduced_motion="reduce",
                )
                page = context.new_page()
                errors: list[str] = []
                requests: list[str] = []
                page.on("pageerror", lambda error, sink=errors: sink.append(str(error)))
                page.on("request", lambda request, sink=requests: sink.append(request.url))
                response = page.goto(f"{origin}/", wait_until="networkidle")
                assert response is not None and response.status == 200, (
                    size,
                    None if response is None else response.status,
                )
                page.evaluate("() => document.fonts.ready")
                overflow = page.evaluate(
                    "() => document.documentElement.scrollWidth - innerWidth"
                )
                same_origin = all(url.startswith(f"{origin}/") for url in requests)
                assert overflow <= 1, (size, overflow)
                assert not errors, (size, errors)
                assert same_origin, (size, [url for url in requests if not url.startswith(origin)])
                metadata = assert_metadata(page)
                normal_path = OUTPUT / f"{size}.png"
                # Prime below-the-fold loading="lazy" images so the full-page
                # screenshots do not record blank image boxes.
                page.evaluate(LAZY_IMAGES_JS)
                full_path = OUTPUT / f"{size}-full.png"
                page.screenshot(path=str(normal_path), animations="disabled")
                page.screenshot(path=str(full_path), full_page=True, animations="disabled")
                assert normal_path.stat().st_size > 10_000, normal_path
                assert full_path.stat().st_size > 20_000, full_path
                viewports[size] = {"width": width, "height": height}
                horizontal_overflow[size] = overflow
                page_errors[size] = errors
                requests_same_origin[size] = same_origin
                normal_rel = normal_path.relative_to(ROOT).as_posix()
                full_rel = full_path.relative_to(ROOT).as_posix()
                paths[size] = normal_rel
                paths[f"{size}_full"] = full_rel
                captures.append(
                    {
                        "name": size,
                        "viewport": [width, height],
                        "url": f"{origin}/",
                        "path": normal_rel,
                        "full_page_path": full_rel,
                        "path_bytes": normal_path.stat().st_size,
                        "full_page_path_bytes": full_path.stat().st_size,
                        "horizontal_overflow": overflow,
                        "page_errors": errors,
                        "requests_same_origin": same_origin,
                        "request_count": len(requests),
                    }
                )
                context.close()
            browser.close()

        head_revision = run_git("rev-parse", "HEAD").decode("utf-8").strip()
        record = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "command": COMMAND,
            "page_url": f"{origin}/",
            "source": {
                "method": "git archive HEAD -- website",
                "git_head_revision": head_revision,
                "served_from": ".worktrees/completion-c-scratch/marketing-head/website",
                "served_from_scratch": True,
                "working_tree_used": False,
                "working_tree_note": WORKING_TREE_NOTE,
                "working_tree_dirty_website_paths": dirty_website,
                "font_note": (
                    "HEAD commits the Geist variable font ({font}); the Bricolage "
                    "font exists only as untracked working-tree brand work, so no "
                    "Bricolage file is served or hashed in this record."
                ).format(font=font),
            },
            "git_head_revision": head_revision,
            "browser": browser_info,
            "playwright_version": importlib.metadata.version("playwright"),
            "python_version": platform.python_version(),
            "reduced_motion": "reduce",
            "viewports": viewports,
            "captures": captures,
            "paths": paths,
            "horizontal_overflow": horizontal_overflow,
            "page_errors": page_errors,
            "requests_same_origin": requests_same_origin,
            "source_sha256": sources,
            "sitemap_robots": sitemap_robots,
            "metadata": metadata,
        }
        (OUTPUT / "capture.json").write_text(json.dumps(record, indent=2) + "\n")
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
        assert not worker.is_alive(), "marketing capture server did not stop"


if __name__ == "__main__":
    main()
