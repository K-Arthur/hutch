#!/usr/bin/env python3
"""Final two-up: P2 Offset Residents vs WB Cabinet, refined + small masters.

Selection evidence for the human pick. Masters at 32-grid; small masters for
<=20px use the same geometry with widened doorway, enlarged dot and fuller
bleed. Nothing here is adopted until the human records the pick.
"""
import pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent
FONTS, SHEETS, RASTER = ROOT / "fonts", ROOT / "sheets", ROOT / "raster_final"
INK, PAPER, EMERALD = "#09090b", "#ededf0", "#34d399"

def slab(x0, y0, x1, y1, r):
    return (f"M{x0 + r} {y0} H{x1 - r} A{r} {r} 0 0 1 {x1} {y0 + r} V{y1 - r} "
            f"A{r} {r} 0 0 1 {x1 - r} {y1} H{x0 + r} A{r} {r} 0 0 1 {x0} {y1 - r} "
            f"V{y0 + r} A{r} {r} 0 0 1 {x0 + r} {y0} Z")

def em(cx, cy, r):
    return f'<circle class="dotc" cx="{cx}" cy="{cy}" r="{r}"/>'

DOOR_MASTER = " M10 29 V22 A6 6 0 0 1 22 22 V29 Z"
DOOR_SMALL = " M9.5 30 V22 A6.5 6.5 0 0 1 22.5 22 V30 Z"
SLAB_MASTER = slab(3, 3, 29, 29, 5)
SLAB_SMALL = slab(2, 2, 30, 30, 5.5)

P2 = {
    "label": "P2 Offset Residents",
    "master": (f'<path fill-rule="evenodd" fill="currentColor" d="{SLAB_MASTER}{DOOR_MASTER}"/>'
               + em(16, 23.3, 3.4) + em(10, 10, 2.8)),
    "small": (f'<path fill-rule="evenodd" fill="currentColor" d="{SLAB_SMALL}{DOOR_SMALL}"/>'
              + em(16, 23.6, 3.8) + em(10, 10, 3.1)),
}
WB = {
    "label": "WB Cabinet",
    "master": (f'<path fill-rule="evenodd" fill="currentColor" d="{SLAB_MASTER}{DOOR_MASTER}"/>'
               + em(16, 23, 3.6)),
    "small": (f'<path fill-rule="evenodd" fill="currentColor" d="{SLAB_SMALL}{DOOR_SMALL}"/>'
              + em(16, 23.6, 3.9)),
}

def svg(body, size, color, cls=""):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="{size}" '
            f'height="{size}" class="{cls}" style="color:{color};display:block">{body}</svg>')

def raster(browser, slug, body, bg, fg, px=16, dpr=1):
    ctx = browser.new_context(viewport={"width": px, "height": px}, device_scale_factor=dpr)
    page = ctx.new_page()
    page.set_content(f'<!doctype html><body style="margin:0;background:{bg}">'
                     f'<div style="width:{px}px;height:{px}px;color:{fg}">{svg(body,px,fg)}</div>'
                     f'</body>', wait_until="load")
    out = RASTER / f"{slug}-{px}{'-small' if slug.endswith('-sm') else ''}-{bg.lstrip('#')}.png"
    page.screenshot(path=str(out), clip={"x":0,"y":0,"width":px,"height":px})
    ctx.close()

def main():
    RASTER.mkdir(parents=True, exist_ok=True)
    SHEETS.mkdir(parents=True, exist_ok=True)
    concepts = [P2, WB]
    with sync_playwright() as p:
        b = p.chromium.launch()
        for c in concepts:
            slug = c["label"].split(" ")[0].lower()
            raster(b, slug, c["master"], PAPER, INK)
            raster(b, slug, c["master"], INK, PAPER)
            raster(b, slug, c["master"], INK, EMERALD)
            raster(b, slug + "-sm", c["small"], PAPER, INK)
            raster(b, slug + "-sm", c["small"], INK, PAPER)
        b.close()

    rows = []
    for c in concepts:
        slug = c["label"].split(" ")[0].lower()
        rows.append(f"""
  <tr>
    <td class="label">{c["label"]}</td>
    <td class="cell ink"><div class="lk">{svg(c["master"], 56, EMERALD)}<span class="wm light">hutch<span class="pd">.</span></span></div></td>
    <td class="cell white">{svg(c["master"], 160, INK)}<div class="cap">master 160px</div></td>
    <td class="cell ink">{svg(c["master"], 160, EMERALD)}<div class="cap d">emerald on ink</div></td>
    <td class="cell white">
      <div class="sizes">
        <div>{svg(c["master"], 32, INK)}<span class="cap">32</span></div>
        <div>{svg(c["master"], 24, INK)}<span class="cap">24</span></div>
        <div>{svg(c["master"], 20, INK)}<span class="cap">20</span></div>
        <div>{svg(c["small"], 16, INK)}<span class="cap">16 small</span></div>
      </div>
    </td>
    <td class="cell white zoom"><img src="../raster_final/{slug}-16-{PAPER.lstrip('#')}.png" width="128" height="128"><div class="cap">16 light x8</div></td>
    <td class="cell ink zoom"><img src="../raster_final/{slug}-16-{INK.lstrip('#')}.png" width="128" height="128"><div class="cap d">16 dark x8</div></td>
    <td class="cell white zoom"><img src="../raster_final/{slug}-sm-16-small-{PAPER.lstrip('#')}.png" width="128" height="128"><div class="cap">16 small master x8</div></td>
    <td class="cell ink zoom"><img src="../raster_final/{slug}-16-{INK.lstrip('#')}.png" width="64" height="64" style="filter:none"><div class="cap d">dpr1</div></td>
  </tr>""")

    face = ('@font-face{font-family:"Bricolage";src:url("' +
            (FONTS / "BricolageGrotesque-var.ttf").as_uri() +
            '") format("truetype");font-weight:1 1000;font-display:block}')
    html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
{face}
.wm{{font-family:'Bricolage';font-weight:800;font-size:42px;letter-spacing:-0.02em;color:{INK};line-height:1}}
.wm.light{{color:{PAPER}}} .pd{{color:{EMERALD}}}
body{{margin:0;padding:14px;background:#fff;font-family:monospace;font-size:12px}}
h1{{font-size:15px}} table{{border-collapse:collapse}}
td{{border:1px solid #bbb;padding:8px;vertical-align:middle;text-align:center}}
.label{{width:170px;text-align:left;font-size:12px;vertical-align:top}}
.ink{{background:{INK}}} .white{{background:#fff}}
.lk{{display:flex;align-items:center;gap:14px}}
.sizes{{display:flex;gap:10px;align-items:flex-end}}
.sizes>div{{display:flex;flex-direction:column;align-items:center;gap:4px}}
.zoom img{{image-rendering:pixelated}}
.cap{{font-size:10px;color:#555}} .cap.d{{color:#999}}
</style></head><body>
<h1>Final two-up - P2 Offset Residents vs WB Cabinet (master + small master), 2026-10-29.
Selection evidence only; collision screen partial - not clearance.</h1>
<table><tbody>{''.join(rows)}</tbody></table></body></html>"""
    out = SHEETS / "final-two-up.html"
    out.write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1450, "height": 700})
        page.goto(out.as_uri(), wait_until="load"); page.wait_for_timeout(500)
        page.screenshot(path=str(SHEETS / "final-two-up.png"), full_page=True)
        b.close()
    print("wrote", SHEETS / "final-two-up.png")

if __name__ == "__main__":
    main()
