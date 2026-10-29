#!/usr/bin/env python3
"""Render the S-c og:image card (Route A, human-approved 2026-10-28, DECISION.md S-c-03).

Outputs:
  website/assets/og-card-1200x630.png          the committed share-card asset
  evidence/audit/shots/s-c-card-preview-desktop.png  card in a share-unfurl context at 1440
  evidence/audit/shots/s-c-card-preview-mobile.png   same at 390

Self-contained by contract (website/src/input.css:5): the render references only
committed assets (Geist woff2 via file://) and uses only committed brand tokens
(website/tokens.css). Zero external URLs. Run with:
  uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/s_c_render_card.py
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[5]
WEBSITE = REPO / "website"
FONT = WEBSITE / "assets" / "fonts" / "geist-latin-var.woff2"
OUT_PNG = WEBSITE / "assets" / "og-card-1200x630.png"
SHOTS = Path(__file__).resolve().parent / "shots"

HEX_MARK = (
    '<svg width="52" height="52" viewBox="0 0 32 32" fill="none" '
    'xmlns="http://www.w3.org/2000/svg">'
    '<path d="M16 2 28 9v14L16 30 4 23V9z" stroke="#34d399" stroke-width="2.5"/>'
    '<circle cx="16" cy="16" r="4" fill="#34d399"/></svg>'
)

CARD_HTML = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<style>
@font-face {{
  font-family: 'Geist';
  src: url('{FONT.as_uri()}') format('woff2');
  font-weight: 100 900; font-style: normal;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html, body {{ width: 1200px; height: 630px; overflow: hidden; }}
body {{ background: #09090b; font-family: 'Geist', sans-serif; position: relative; }}
.glow {{ position: absolute; top: -280px; right: -200px; width: 760px; height: 760px;
  background: radial-gradient(circle, rgba(52,211,153,0.13) 0%, rgba(52,211,153,0) 62%); }}
.mark-row {{ position: absolute; top: 60px; left: 72px; display: flex;
  align-items: center; gap: 18px; }}
.wordmark {{ font-size: 44px; font-weight: 620; color: #ededf0; letter-spacing: -0.5px; }}
.statement {{ position: absolute; left: 72px; top: 206px; }}
.statement div {{ font-size: 72px; font-weight: 700; line-height: 1.08;
  letter-spacing: -1.5px; }}
.l1 {{ color: #ededf0; }}
.l2 {{ color: #34d399; }}
.footer {{ position: absolute; left: 72px; bottom: 58px; font-size: 26px;
  font-weight: 460; color: #8e8e99; letter-spacing: 0.2px; }}
</style></head><body>
<div class="glow"></div>
<div class="mark-row">{HEX_MARK}<span class="wordmark">Hutch</span></div>
<div class="statement"><div class="l1">Local-first AI assistants</div
  ><div class="l2">that run on your machine.</div></div>
<div class="footer">MIT-licensed &middot; open source &middot; Linux &middot; Development preview</div>
</body></html>
"""

UNFURL_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #09090b; font-family: sans-serif; padding: 40px; }
.card { border: 1px solid rgba(255,255,255,0.07); border-radius: 12px;
  overflow: hidden; background: #0f0f12; }
.card img { display: block; width: 100%; height: auto; }
.meta { padding: 18px 20px 22px; }
.meta .site { color: #8e8e99; font-size: 13px; text-transform: uppercase;
  letter-spacing: 0.6px; }
.meta .title { color: #ededf0; font-size: 22px; font-weight: 600; margin-top: 8px; }
.meta .desc { color: #a3a3ae; font-size: 15px; margin-top: 8px; line-height: 1.45; }
</style></head><body>
<div class="card">
  <img src="CARD_URL" alt="Hutch — local-first AI assistants that run on your machine">
  <div class="meta">
    <div class="site">HUTCH</div>
    <div class="title">Hutch — local-first AI assistants that run on your machine</div>
    <div class="desc">Local-first, MIT-licensed AI assistants that run on your own
      Linux computer. Choose the models; assistants ask before important actions.
      Development preview.</div>
  </div>
</div>
</body></html>
"""


def render_card(browser) -> None:
    scratch = Path("/tmp/opencode/s-c-research")
    scratch.mkdir(parents=True, exist_ok=True)
    card_doc = scratch / "card.html"
    card_doc.write_text(CARD_HTML, encoding="utf-8")
    page = browser.new_page(viewport={"width": 1200, "height": 630})
    page.goto(card_doc.as_uri(), wait_until="load")
    page.evaluate("async () => { await document.fonts.ready; }")
    page.screenshot(path=str(OUT_PNG), type="png")
    page.close()
    print(f"card_rendered: {OUT_PNG}")


def render_unfurl_previews(browser) -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    scratch = Path("/tmp/opencode/s-c-research")
    html = UNFURL_HTML.replace("CARD_URL", OUT_PNG.as_uri())
    unfurl_doc = scratch / "unfurl.html"
    unfurl_doc.write_text(html, encoding="utf-8")
    for label, width, height in (("desktop", 1440, 900), ("mobile", 390, 844)):
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(unfurl_doc.as_uri(), wait_until="load")
        out = SHOTS / f"s-c-card-preview-{label}.png"
        page.screenshot(path=str(out), full_page=True, type="png")
        print(f"unfurl_preview_{label}: {out}")
        page.close()


def main() -> None:
    if not FONT.is_file():
        raise SystemExit(f"missing committed font: {FONT}")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            render_card(browser)
            render_unfurl_previews(browser)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
