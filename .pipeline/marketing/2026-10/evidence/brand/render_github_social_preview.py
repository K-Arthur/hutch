#!/usr/bin/env python3
"""Render the Hutch GitHub repository social preview card (1280x640 PNG).

Adapted from the committed og-card renderer at
.pipeline/marketing/2026-10/evidence/audit/s_c_render_card.py (S-c, 2026-10-28).
GitHub's documented social preview size is 1280x640 (2:1); this card keeps the
og-card brand language (same background, hexagon mark, statement, muted footer)
but widens the edge-safe margin because several link surfaces crop the sides.

Inputs are committed files only: website/tokens.css is inlined at render time and
the committed Geist woff2 is loaded over file://. The renderer makes zero network
requests; that is asserted after load (every page request must be file://).

Usage:
  uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/brand/render_github_social_preview.py

Add --thumbnail to also write a 320 px wide legibility thumbnail next to this
script. Add --out PATH to write the PNG somewhere else.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import string
import tempfile
from pathlib import Path

from playwright.sync_api import Browser, sync_playwright

REPO = Path(__file__).resolve().parents[5]
WEBSITE = REPO / "website"
TOKENS = WEBSITE / "tokens.css"
FONT = WEBSITE / "assets" / "fonts" / "geist-latin-var.woff2"
DEFAULT_OUT = WEBSITE / "assets" / "github-social-preview-1280x640.png"
DEFAULT_THUMBNAIL = Path(__file__).resolve().parent / "github-social-preview-1280x640-thumb-320w.png"

CANVAS_W = 1280
CANVAS_H = 640
# Content stays inside this inset on every side so a 1.91:1 or 16:9 surface crop
# cannot cut the mark, the statement or the footer.
SAFE_INSET = 112

# Brand tokens the card depends on. Failing loudly here beats rendering an
# unstyled card if website/tokens.css ever renames a token.
REQUIRED_TOKENS = (
    "--color-semantic-bg",
    "--color-semantic-brand",
    "--color-semantic-text",
    "--color-semantic-text-3",
    "--font-display",
)

HEX_MARK = (
    '<svg width="56" height="56" viewBox="0 0 32 32" fill="none" aria-hidden="true">'
    '<path d="M16 2 28 9v14L16 30 4 23V9z" stroke="currentColor" stroke-width="2.5"/>'
    '<circle cx="16" cy="16" r="4" fill="currentColor"/></svg>'
)

CARD_TEMPLATE = string.Template("""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<style>
$TOKENS
@font-face {
  font-family: 'Geist';
  src: url('$FONT_URI') format('woff2');
  font-weight: 100 900; font-style: normal;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { width: ${WIDTH}px; height: ${HEIGHT}px; overflow: hidden; }
body {
  position: relative;
  background: var(--color-semantic-bg);
  color: var(--color-semantic-text);
  font-family: var(--font-display);
}
.glow {
  position: absolute; top: -300px; right: -220px; width: 820px; height: 820px;
  background: radial-gradient(circle,
    color-mix(in srgb, var(--color-semantic-brand) 13%, transparent) 0%,
    transparent 62%);
}
.mark-row {
  position: absolute; top: 74px; left: ${INSET}px;
  display: flex; align-items: center; gap: 20px;
  color: var(--color-semantic-brand);
}
.mark-row svg { display: block; }
.wordmark {
  font-size: 46px; font-weight: 620; letter-spacing: -0.6px;
  color: var(--color-semantic-text);
}
.statement { position: absolute; left: ${INSET}px; top: 224px; }
.statement div {
  font-size: 80px; font-weight: 700; line-height: 1.07; letter-spacing: -1.6px;
  white-space: nowrap;
}
.l1 { color: var(--color-semantic-text); }
.l2 { color: var(--color-semantic-brand); }
.footer {
  position: absolute; left: ${INSET}px; bottom: 66px;
  font-size: 27px; font-weight: 460; letter-spacing: 0.2px;
  color: var(--color-semantic-text-3);
}
</style></head><body>
<div class="glow"></div>
<div class="mark-row">$HEX_MARK<span class="wordmark">Hutch</span></div>
<div class="statement"><div class="l1">Local-first AI assistants</div><div class="l2">that run on your machine.</div></div>
<div class="footer">MIT-licensed &middot; open source &middot; Linux &middot; Development preview</div>
</body></html>
""")

THUMBNAIL_TEMPLATE = string.Template("""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { width: ${WIDTH}px; height: ${HEIGHT}px; overflow: hidden;
  background: #09090b; }
img { display: block; width: 100%; height: 100%; }
</style></head><body><img src="$CARD_URI" alt="Hutch GitHub social preview"></body></html>
""")


def load_tokens() -> str:
    if not TOKENS.is_file():
        raise SystemExit(f"missing committed token file: {TOKENS}")
    css = TOKENS.read_text(encoding="utf-8")
    missing = [token for token in REQUIRED_TOKENS if token not in css]
    if missing:
        raise SystemExit(f"tokens.css is missing required tokens: {missing}")
    return css


def card_html(tokens_css: str) -> str:
    return CARD_TEMPLATE.substitute(
        TOKENS=tokens_css,
        FONT_URI=FONT.as_uri(),
        WIDTH=CANVAS_W,
        HEIGHT=CANVAS_H,
        INSET=SAFE_INSET,
        HEX_MARK=HEX_MARK,
    )


def png_size(data: bytes) -> tuple[int, int]:
    """Read width/height from a PNG IHDR chunk without third-party tooling."""
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise SystemExit("rendered file is not a PNG")
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    return width, height


def sha256_hex(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_layout(page) -> None:
    """Assert the card stayed inside the edge-safe area and font loaded."""
    result = page.evaluate(
        """() => {
          const box = (selector) => {
            const rect = document.querySelector(selector).getBoundingClientRect();
            return {left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom};
          };
          const out = {
            font_ready: document.fonts.check('700 80px Geist'),
            scroll: [document.documentElement.scrollWidth, document.documentElement.scrollHeight],
            mark: box('.mark-row'),
            statement: box('.statement'),
            footer: box('.footer'),
          };
          return out;
        }"""
    )
    if not result["font_ready"]:
        raise SystemExit("Geist did not load; refusing to render a fallback-font card")
    if result["scroll"] != [CANVAS_W, CANVAS_H]:
        raise SystemExit(f"card content overflows the canvas: {result['scroll']}")
    for name in ("mark", "statement", "footer"):
        box = result[name]
        if box["left"] < SAFE_INSET - 1 or box["right"] > CANVAS_W - SAFE_INSET + 1:
            raise SystemExit(f"{name} leaves the {SAFE_INSET}px safe inset: {box}")
    if result["footer"]["bottom"] > CANVAS_H - 40:
        raise SystemExit(f"footer sits too close to the bottom edge: {result['footer']}")
    print(
        "layout_ok:"
        f" mark={result['mark']['left']:.1f}..{result['mark']['right']:.1f}"
        f" statement={result['statement']['left']:.1f}..{result['statement']['right']:.1f}"
        f" footer={result['footer']['left']:.1f}..{result['footer']['right']:.1f}"
        f" footer_bottom={result['footer']['bottom']:.1f}"
    )


def render_card(browser: Browser, out: Path) -> None:
    tokens_css = load_tokens()
    if not FONT.is_file():
        raise SystemExit(f"missing committed font: {FONT}")
    scratch = Path(tempfile.mkdtemp(prefix="hutch-github-preview-"))
    try:
        doc = scratch / "card.html"
        doc.write_text(card_html(tokens_css), encoding="utf-8")
        page = browser.new_page(
            viewport={"width": CANVAS_W, "height": CANVAS_H}, device_scale_factor=1
        )
        requests: list[str] = []
        page.on("request", lambda request: requests.append(request.url))
        page.goto(doc.as_uri(), wait_until="load")
        page.evaluate("async () => { await document.fonts.ready; }")
        verify_layout(page)
        out.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out), type="png")
        page.close()
        external = [url for url in requests if not url.startswith("file://")]
        if external:
            raise SystemExit(f"unexpected network requests while rendering: {external}")
        print(f"requests: {len(requests)} (all file://, no network)")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    data = out.read_bytes()
    width, height = png_size(data)
    if (width, height) != (CANVAS_W, CANVAS_H):
        raise SystemExit(f"expected {CANVAS_W}x{CANVAS_H}, got {width}x{height}: {out}")
    if len(data) >= 1_000_000:
        raise SystemExit(f"PNG is not under 1 MB: {len(data)} bytes: {out}")
    print(f"card: {out}")
    print(f"dimensions: {width}x{height}")
    print(f"bytes: {len(data)}")
    print(f"sha256: {sha256_hex(out)}")


def render_thumbnail(browser: Browser, card_png: Path, out: Path, width: int) -> None:
    height = round(width / 2)
    scratch = Path(tempfile.mkdtemp(prefix="hutch-github-thumb-"))
    try:
        doc = scratch / "thumbnail.html"
        doc.write_text(
            THUMBNAIL_TEMPLATE.substitute(
                WIDTH=width, HEIGHT=height, CARD_URI=card_png.as_uri()
            ),
            encoding="utf-8",
        )
        page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
        page.goto(doc.as_uri(), wait_until="load")
        page.evaluate(
            "async () => { const img = document.querySelector('img'); await img.decode(); }"
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out), type="png")
        page.close()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    data = out.read_bytes()
    thumb_width, thumb_height = png_size(data)
    if (thumb_width, thumb_height) != (width, height):
        raise SystemExit(f"expected {width}x{height}, got {thumb_width}x{thumb_height}: {out}")
    print(f"thumbnail: {out}")
    print(f"thumbnail_dimensions: {thumb_width}x{thumb_height}")
    print(f"thumbnail_bytes: {len(data)}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output PNG path")
    parser.add_argument(
        "--thumbnail",
        action="store_true",
        help="also write a 320 px wide legibility thumbnail next to this script",
    )
    parser.add_argument(
        "--thumbnail-width",
        type=int,
        default=320,
        help="thumbnail width in px (default: 320)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            render_card(browser, args.out)
            if args.thumbnail:
                thumb_out = DEFAULT_THUMBNAIL
                if args.thumbnail_width != 320:
                    thumb_out = DEFAULT_THUMBNAIL.with_name(
                        f"github-social-preview-1280x640-thumb-{args.thumbnail_width}w.png"
                    )
                render_thumbnail(browser, args.out, thumb_out, args.thumbnail_width)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
