#!/usr/bin/env python3
"""Round 4: expanded option set including N5 two-bot-front evolutions.

Per human instruction 2026-10-29: build on N5 ("two bot front"), keep it
unique, widen the option set, narrow later. All candidates use the resident-dot
system and Bricolage-harmonised heavy form. Selection evidence only.
"""
import pathlib
from fontTools.misc.transform import Transform
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent
FONTS, SHEETS, RASTER = ROOT / "fonts", ROOT / "sheets", ROOT / "raster4"
INK, PAPER, EMERALD = "#09090b", "#ededf0", "#34d399"

def h_glyph():
    font = TTFont(str(FONTS / "BricolageGrotesque-var.ttf"))
    instantiateVariableFont(font, {"wght": 800}, inplace=True)
    gs = font.getGlyphSet()
    glyph = gs["h"]
    bp = BoundsPen(gs); glyph.draw(bp)
    x0, y0, x1, y1 = bp.bounds
    s = 24.0 / (y1 - y0)
    tx = 16.0 - s * (x0 + x1) / 2.0
    ty = 28.0 + s * y0
    pen = SVGPathPen(gs)
    glyph.draw(TransformPen(pen, Transform(s, 0, 0, -s, tx, ty)))
    return pen.getCommands()

def slab(x0, y0, x1, y1, r):
    return (f"M{x0 + r} {y0} H{x1 - r} A{r} {r} 0 0 1 {x1} {y0 + r} V{y1 - r} "
            f"A{r} {r} 0 0 1 {x1 - r} {y1} H{x0 + r} A{r} {r} 0 0 1 {x0} {y1 - r} "
            f"V{y0 + r} A{r} {r} 0 0 1 {x0 + r} {y0} Z")

def circ(cx, cy, r):
    return f"M{cx - r} {cy} a {r} {r} 0 1 0 {2 * r} 0 a {r} {r} 0 1 0 {-2 * r} 0 Z"

hp = h_glyph()
SLAB5 = slab(3, 3, 29, 29, 5)
DOOR_WIDE = " M6 29 V21 A10 10 0 0 1 26 21 V29 Z"
DOOR_STD = " M10 29 V22 A6 6 0 0 1 22 22 V29 Z"
DOOR_TALL = " M11 29 V16 A5 5 0 0 1 21 16 V29 Z"

def em(cx, cy, r):
    return f'<circle class="dotc" cx="{cx}" cy="{cy}" r="{r}"/>'

CONCEPTS = [
    ("N5R Two-Bot Front outline (N5 refined)",
     '<path fill="none" stroke="currentColor" stroke-width="2.5" stroke-linejoin="miter" '
     'd="M4 28 V15 A12 12 0 0 1 28 15 V28 Z"/>' + em(11.5, 17.5, 3) + em(20.5, 17.5, 3),
     '<path fill="none" stroke="currentColor" stroke-width="3" stroke-linejoin="miter" '
     'd="M4 28 V15 A12 12 0 0 1 28 15 V28 Z"/>' + em(11, 17.5, 3.4) + em(21, 17.5, 3.4)),
    ("P1 Two-Door Cabinet (wide door, pair)",
     f'<path fill-rule="evenodd" fill="currentColor" d="{SLAB5}{DOOR_WIDE}"/>' + em(11.8, 23.5, 2.8) + em(20.2, 23.5, 2.8),
     f'<path fill-rule="evenodd" fill="currentColor" d="{SLAB5}{DOOR_WIDE}"/>' + em(11.6, 23.5, 3.1) + em(20.4, 23.5, 3.1)),
    ("P2 Offset Residents (door + upper window dot)",
     f'<path fill-rule="evenodd" fill="currentColor" d="{SLAB5}{DOOR_STD}"/>' + em(16, 23, 3.5) + em(9.5, 9.5, 3),
     f'<path fill-rule="evenodd" fill="currentColor" d="{SLAB5}{DOOR_STD}"/>' + em(16, 23, 3.5) + em(9.5, 9.5, 3.3)),
    ("P8 Stacked Pair (tall door, two floors)",
     f'<path fill-rule="evenodd" fill="currentColor" d="{SLAB5}{DOOR_TALL}"/>' + em(16, 17.2, 2.8) + em(16, 25.2, 2.8),
     f'<path fill-rule="evenodd" fill="currentColor" d="{SLAB5}{DOOR_TALL}"/>' + em(16, 17, 3.1) + em(16, 25.4, 3.1)),
    ("WB Cabinet reference (round 3)",
     f'<path fill-rule="evenodd" fill="currentColor" d="{SLAB5}{DOOR_STD}"/>' + em(16, 23, 3.5),
     f'<path fill-rule="evenodd" fill="currentColor" d="{SLAB5}{DOOR_STD}"/>' + em(16, 23, 3.5)),
    ("WB-S Cabinet + step reference",
     f'<path fill-rule="evenodd" fill="currentColor" d="{SLAB5}{DOOR_STD}"/>'
     '<rect x="11" y="28" width="10" height="2.6" rx="1.2" fill="currentColor"/>' + em(16, 23, 3.5),
     f'<path fill-rule="evenodd" fill="currentColor" d="{SLAB5}{DOOR_STD}"/>'
     '<rect x="11" y="28" width="10" height="2.6" rx="1.2" fill="currentColor"/>' + em(16, 23, 3.5)),
    ("WC Rack reference (round 3)",
     '<path fill-rule="evenodd" fill="currentColor" d="' + slab(4, 4, 28, 28, 4) +
     ' M11 10 H21 A2 2 0 0 1 23 12 A2 2 0 0 1 21 14 H11 A2 2 0 0 1 9 12 A2 2 0 0 1 11 10 Z"/>' + em(16, 21, 4),
     '<path fill-rule="evenodd" fill="currentColor" d="' + slab(4, 4, 28, 28, 4) +
     ' M11 10 H21 A2 2 0 0 1 23 12 A2 2 0 0 1 21 14 H11 A2 2 0 0 1 9 12 A2 2 0 0 1 11 10 Z"/>' + em(16, 21, 4)),
    ("WA1b wordmark-h reference (screen caveat)",
     f'<path fill="currentColor" d="{hp}"/>' + em(14.8, 21.5, 2.6),
     f'<path fill="currentColor" d="{hp}"/>' + em(14.8, 21.5, 2.6)),
]

def svg(body, size, color):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="{size}" '
            f'height="{size}" style="color:{color};display:block">{body}</svg>')

def raster16(browser, slug, body, bg, fg):
    ctx = browser.new_context(viewport={"width": 16, "height": 16}, device_scale_factor=1)
    page = ctx.new_page()
    page.set_content(f'<!doctype html><body style="margin:0;background:{bg}">'
                     f'<div style="width:16px;height:16px;color:{fg}">{svg(body,16,fg)}</div></body>',
                     wait_until="load")
    page.screenshot(path=str(RASTER / f"{slug}-16-{bg.lstrip('#')}.png"),
                    clip={"x":0,"y":0,"width":16,"height":16})
    ctx.close()

def main():
    RASTER.mkdir(parents=True, exist_ok=True)
    SHEETS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        for label, body, _small in CONCEPTS:
            slug = label.split(" ")[0].lower()
            for bg, fg in ((PAPER, INK), (INK, PAPER)):
                raster16(b, slug, body, bg, fg)
        b.close()

    face = ('@font-face{font-family:"Bricolage";src:url("' +
            (FONTS / "BricolageGrotesque-var.ttf").as_uri() +
            '") format("truetype");font-weight:1 1000;font-display:block}')
    rows = []
    for label, body, small in CONCEPTS:
        slug = label.split(" ")[0].lower()
        lock = (f'<div class="lk">{svg(body, 56, EMERALD)}'
                f'<span class="wm light">hutch<span class="pd">.</span></span></div>')
        rows.append(f"""
  <tr>
    <td class="label">{label}</td>
    <td class="cell ink"><div class="lk">{svg(body, 56, EMERALD)}<span class="wm light">hutch<span class="pd">.</span></span></div></td>
    <td class="cell paper"><div class="lk">{svg(body, 56, INK)}<span class="wm">hutch<span class="pd">.</span></span></div></td>
    <td class="cell white">{svg(body, 120, INK)}</td>
    <td class="cell white">{svg(small, 16, INK)}<div class="cap">small 16</div></td>
    <td class="cell white zoom"><img src="../raster4/{slug}-16-{PAPER.lstrip('#')}.png" width="128" height="128" alt=""><div class="cap">16px x8 light</div></td>
    <td class="cell ink zoom"><img src="../raster4/{slug}-16-{INK.lstrip('#')}.png" width="128" height="128" alt=""><div class="cap d">16px x8 dark</div></td>
  </tr>""")

    html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
{face}
.wm{{font-family:'Bricolage';font-weight:800;font-size:42px;letter-spacing:-0.02em;color:{INK};line-height:1}}
.wm.light{{color:{PAPER}}} .pd{{color:{EMERALD}}}
body{{margin:0;padding:14px;background:#fff;font-family:monospace;font-size:12px}}
h1{{font-size:15px}} table{{border-collapse:collapse}}
td{{border:1px solid #bbb;padding:6px;vertical-align:middle;text-align:center}}
.label{{width:235px;text-align:left;font-size:11px;vertical-align:top}}
.ink{{background:{INK}}} .paper{{background:{PAPER}}} .white{{background:#fff}}
.lk{{display:flex;align-items:center;gap:14px}}
.zoom img{{image-rendering:pixelated}}
.cap{{font-size:10px;color:#555;margin-top:3px}} .cap.d{{color:#888}}
</style></head><body>
<h1>Round 4 expanded set - N5 two-bot-front evolutions + round-3 references - 2026-10-29
(selection evidence; collision screen still owed; nothing cleared)</h1>
<table><thead><tr><th>concept</th><th>lockup ink</th><th>lockup paper</th><th>120px</th>
<th>small master</th><th>16px light</th><th>16px dark</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
</body></html>"""
    out = SHEETS / "round4-sheet.html"
    out.write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1400, "height": 1000})
        page.goto(out.as_uri(), wait_until="load"); page.wait_for_timeout(600)
        page.screenshot(path=str(SHEETS / "round4-sheet.png"), full_page=True)
        b.close()
    print("wrote", SHEETS / "round4-sheet.png")

if __name__ == "__main__":
    main()
