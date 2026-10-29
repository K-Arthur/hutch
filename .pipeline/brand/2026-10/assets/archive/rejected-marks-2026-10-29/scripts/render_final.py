#!/usr/bin/env python3
"""Final mini-compare: tuned WA, WB, WB+step, WC before direction request."""
import pathlib
from fontTools.misc.transform import Transform
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent
FONTS, SHEETS, RASTER = ROOT / "fonts", ROOT / "sheets", ROOT / "raster3"
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

hp = h_glyph()
DOOR = " M10 29 V22 A6 6 0 0 1 22 22 V29 Z"
CAB = '<path fill-rule="evenodd" fill="currentColor" d="' + slab(3,3,29,29,5) + DOOR + '"/>'
STEP = '<rect x="11" y="28" width="10" height="2.6" rx="1.2" fill="currentColor"/>'
RACK = ('<path fill-rule="evenodd" fill="currentColor" d="' + slab(4,4,28,28,4) +
        ' M11 10 H21 A2 2 0 0 1 23 12 A2 2 0 0 1 21 14 H11 A2 2 0 0 1 9 12 A2 2 0 0 1 11 10 Z"/>')

CONCEPTS = [
    ("WA1b h + tuned dot (cx14.8 r2.6)",
     f'<path fill="currentColor" d="{hp}"/><circle class="dotc" cx="14.8" cy="21.5" r="2.6"/>'),
    ("WB cabinet", CAB + '<circle class="dotc" cx="16" cy="23" r="3.5"/>'),
    ("WB-S cabinet + threshold step", CAB + STEP + '<circle class="dotc" cx="16" cy="23" r="3.5"/>'),
    ("WC rack", RACK + '<circle class="dotc" cx="16" cy="21" r="4"/>'),
]

def svg(body, size, color):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="{size}" '
            f'height="{size}" style="color:{color};display:block">{body}</svg>')

# 16px rasters
with sync_playwright() as p:
    b = p.chromium.launch()
    RASTER.mkdir(parents=True, exist_ok=True)
    for label, body in CONCEPTS:
        slug = label.split(" ")[0].lower()
        for bg, fg in ((PAPER, INK), (INK, PAPER)):
            ctx = b.new_context(viewport={"width": 16, "height": 16}, device_scale_factor=1)
            page = ctx.new_page()
            page.set_content(f'<!doctype html><body style="margin:0;background:{bg}">'
                             f'<div style="width:16px;height:16px;color:{fg}">{svg(body,16,fg)}</div>'
                             f'</body>', wait_until="load")
            page.screenshot(path=str(RASTER / f"{slug}-16-{bg.lstrip('#')}.png"),
                            clip={"x":0,"y":0,"width":16,"height":16})
            ctx.close()
    b.close()

face = ('@font-face{font-family:"Bricolage";src:url("' +
        (FONTS / "BricolageGrotesque-var.ttf").as_uri() +
        '") format("truetype");font-weight:1 1000;font-display:block}')
rows = []
for label, body in CONCEPTS:
    slug = label.split(" ")[0].lower()
    lock = (f'<div class="lk">{svg(body, 60, EMERALD)}'
            f'<span class="wm light">hutch<span class="pd">.</span></span></div>')
    rows.append(f"""<tr><td class="label">{label}</td>
    <td class="cell ink">{lock}</td>
    <td class="cell white">{svg(body, 240, INK)}</td>
    <td class="cell white zoom"><img src="../raster3/{slug}-16-{PAPER.lstrip('#')}.png" width="144" height="144"></td>
    <td class="cell ink zoom"><img src="../raster3/{slug}-16-{INK.lstrip('#')}.png" width="144" height="144"></td></tr>""")

html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
{face}
.wm{{font-family:'Bricolage';font-weight:800;font-size:44px;letter-spacing:-0.02em;color:{INK};line-height:1}}
.wm.light{{color:{PAPER}}} .pd{{color:{EMERALD}}}
body{{margin:0;padding:14px;background:#fff;font-family:monospace;font-size:12px}}
h1{{font-size:15px}} table{{border-collapse:collapse}}
td{{border:1px solid #bbb;padding:8px;vertical-align:middle;text-align:center}}
.label{{width:210px;text-align:left;font-size:11px;vertical-align:top}}
.ink{{background:{INK}}} .white{{background:#fff}}
.lk{{display:flex;align-items:center;gap:14px}}
.zoom img{{image-rendering:pixelated}}
</style></head><body>
<h1>Round 3 final mini-compare - 2026-10-29 (selection evidence; 16px x6 real pixels)</h1>
<table>{''.join(rows)}</table></body></html>"""
out = SHEETS / "round3-final.html"
out.write_text(html, encoding="utf-8")
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1150, "height": 900})
    page.goto(out.as_uri(), wait_until="load"); page.wait_for_timeout(500)
    page.screenshot(path=str(SHEETS / "round3-final.png"), full_page=True)
    b.close()
print("wrote", SHEETS / "round3-final.png")
