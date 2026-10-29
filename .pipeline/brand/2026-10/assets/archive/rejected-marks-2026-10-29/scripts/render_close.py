#!/usr/bin/env python3
"""Close-look sheet: W-A variants at large size + W-B/W-C craft review."""
import pathlib
from fontTools.misc.transform import Transform
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent
FONTS = ROOT / "fonts"
SHEETS = ROOT / "sheets"
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
    return pen.getCommands(), s, (x0, y0, x1, y1)

def slab(x0, y0, x1, y1, r):
    return (f"M{x0 + r} {y0} H{x1 - r} A{r} {r} 0 0 1 {x1} {y0 + r} V{y1 - r} "
            f"A{r} {r} 0 0 1 {x1 - r} {y1} H{x0 + r} A{r} {r} 0 0 1 {x0} {y1 - r} "
            f"V{y0 + r} A{r} {r} 0 0 1 {x0 + r} {y0} Z")

hp, s, bb = h_glyph()
print("h bbox(32grid): x %.2f..%.2f y %.2f..%.2f scale %.4f" % (
    s*bb[0]+0, 0, 0, 0, s))  # rough

CONCEPTS = [
    ("WA1 h + dot r2.5 @y22",
     f'<path fill="currentColor" d="{hp}"/><circle class="dotc" cx="16" cy="22" r="2.5"/>'),
    ("WA2 h + dot r3.0 @y21.5 (round3)",
     f'<path fill="currentColor" d="{hp}"/><circle class="dotc" cx="16" cy="21.5" r="3"/>'),
    ("WA3 h + burrow notch in leg",
     f'<path fill-rule="evenodd" fill="currentColor" d="{hp} M19.5 19 m -4.6 0 a 4.6 4.6 0 1 0 9.2 0 a 4.6 4.6 0 1 0 -9.2 0 Z"/>'),
    ("WB cabinet (round3)",
     '<path fill-rule="evenodd" fill="currentColor" d="' + slab(3,3,29,29,5) +
     ' M10 29 V22 A6 6 0 0 1 22 22 V29 Z"/><circle class="dotc" cx="16" cy="23" r="3.5"/>'),
    ("WC rack (round3)",
     '<path fill-rule="evenodd" fill="currentColor" d="' + slab(4,4,28,28,4) +
     ' M11 10 H21 A2 2 0 0 1 23 12 A2 2 0 0 1 21 14 H11 A2 2 0 0 1 9 12 A2 2 0 0 1 11 10 Z"/>'
     '<circle class="dotc" cx="16" cy="21" r="4"/>'),
]

def svg(body, size, color):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="{size}" '
            f'height="{size}" style="color:{color};display:block">{body}</svg>')

rows = []
for label, body in CONCEPTS:
    lock = (f'<div class="lk">{svg(body, 64, EMERALD)}'
            f'<span class="wm light">hutch<span class="pd">.</span></span></div>')
    rows.append(f"""<tr><td class="label">{label}</td>
    <td class="cell ink">{lock}</td>
    <td class="cell white">{svg(body, 256, INK)}</td>
    <td class="cell ink">{svg(body, 256, EMERALD)}</td></tr>""")

face = ('@font-face{font-family:"Bricolage";src:url("' +
        (FONTS / "BricolageGrotesque-var.ttf").as_uri() +
        '") format("truetype");font-weight:1 1000;font-display:block}')
html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
{face}
.wm{{font-family:'Bricolage';font-weight:800;font-size:48px;letter-spacing:-0.02em;color:{INK};line-height:1}}
.wm.light{{color:{PAPER}}} .pd{{color:{EMERALD}}}
body{{margin:0;padding:14px;background:#fff;font-family:monospace;font-size:12px}}
h1{{font-size:15px}} table{{border-collapse:collapse}}
td{{border:1px solid #bbb;padding:8px;vertical-align:middle}}
.label{{width:230px;text-align:left;font-size:11px;vertical-align:top}}
.ink{{background:{INK}}} .white{{background:#fff}}
.lk{{display:flex;align-items:center;gap:16px}}
</style></head><body>
<h1>Round 3 close-look: W-A variants vs W-B/W-C - 2026-10-29, selection evidence only</h1>
<table>{''.join(rows)}</table></body></html>"""
out = SHEETS / "round3-close.html"
out.write_text(html, encoding="utf-8")
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1200, "height": 900})
    page.goto(out.as_uri(), wait_until="load"); page.wait_for_timeout(600)
    page.screenshot(path=str(SHEETS / "round3-close.png"), full_page=True)
    b.close()
print("wrote", SHEETS / "round3-close.png")
