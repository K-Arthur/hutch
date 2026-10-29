#!/usr/bin/env python3
"""Round 3: constructed mark candidates harmonised with the chosen wordmark.

Brief: D42 (wordmark = Bricolage Grotesque 800; full package, pipeline-only
authorisation) and D43 (marks must be constructed/composite, collision-conscious,
and must meld with the wordmark). W-A is derived from the Bricolage 'h' glyph
itself (OFL, instanced at wght 800, outlined - provenance to be registered).
Selection evidence only; nothing adopted.
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
FONTS = ROOT / "fonts"
SHEETS = ROOT / "sheets"
RASTER = ROOT / "raster3"

INK = "#09090b"
PAPER = "#ededf0"
EMERALD = "#34d399"


def h_glyph() -> str:
    """Outline Bricolage Grotesque 'h' at wght 800 onto the 32-unit grid.

    Ascender -> y 4, baseline -> y 28, width centred at x 16.
    """
    font = TTFont(str(FONTS / "BricolageGrotesque-var.ttf"))
    instantiateVariableFont(font, {"wght": 800}, inplace=True)
    gs = font.getGlyphSet()
    glyph = gs["h"]
    bp = BoundsPen(gs)
    glyph.draw(bp)
    x0, y0, x1, y1 = bp.bounds
    s = 24.0 / (y1 - y0)              # target height 24 units
    tx = 16.0 - s * (x0 + x1) / 2.0   # centre
    ty = 28.0 + s * y0                # baseline -> 28 (y' = -s*y + ty)
    pen = SVGPathPen(gs)
    glyph.draw(TransformPen(pen, Transform(s, 0, 0, -s, tx, ty)))
    return pen.getCommands()


def slab(x0, y0, x1, y1, r):
    return (f"M{x0 + r} {y0} H{x1 - r} A{r} {r} 0 0 1 {x1} {y0 + r} "
            f"V{y1 - r} A{r} {r} 0 0 1 {x1 - r} {y1} H{x0 + r} "
            f"A{r} {r} 0 0 1 {x0} {y1 - r} V{y0 + r} "
            f"A{r} {r} 0 0 1 {x0 + r} {y0} Z")


def sub(evenodd_body: str) -> str:
    return f'<path fill-rule="evenodd" fill="currentColor" d="{evenodd_body}"/>'


def dot(cx, cy, r) -> str:
    return f'<circle class="dotc" cx="{cx}" cy="{cy}" r="{r}"/>'


def build_concepts():
    h_path = h_glyph()
    cabinet = (slab(3, 3, 29, 29, 5)
               + " M10 29 V22 A6 6 0 0 1 22 22 V29 Z")
    rack = (slab(4, 4, 28, 28, 4)
            + " M11 10 H21 A2 2 0 0 1 23 12 A2 2 0 0 1 21 14 H11 "
            "A2 2 0 0 1 9 12 A2 2 0 0 1 11 10 Z")
    body = slab(5, 9, 27, 27, 3.5)
    crown = '<rect x="2" y="3" width="28" height="4.5" rx="2.2" fill="currentColor"/>'
    feet = ('<rect x="7" y="27" width="4.5" height="2.5" rx="1" fill="currentColor"/>'
            '<rect x="20.5" y="27" width="4.5" height="2.5" rx="1" fill="currentColor"/>')
    return [
        ("W-A Wordmark 'h' + resident dot",
         f'<path fill="currentColor" d="{h_path}"/>' + dot(16, 21.5, 3.0)),
        ("W-B Hutch cabinet (slab + door cut + dot)",
         sub(cabinet) + dot(16, 23, 3.5)),
        ("W-C Bot rack (slab + shelf slot + dot)",
         sub(rack) + dot(16, 21, 4)),
        ("W-E Crowned hutch (crown + body + feet + dot)",
         crown + body + feet + dot(16, 18, 4)),
        ("N1 control (round-1 arch outline)",
         '<path fill="none" stroke="currentColor" stroke-width="2.5" '
         'stroke-linejoin="miter" d="M4 28 V15 A12 12 0 0 1 28 15 V28 Z"/>'
         '<circle cx="16" cy="16" r="4" fill="currentColor"/>'),
        ("C0 control (shipped hexagon + dot)",
         '<path fill="none" stroke="currentColor" stroke-width="2.5" '
         'stroke-linejoin="miter" d="M16 2 L28 9 L28 23 L16 30 L4 23 L4 9 Z"/>'
         '<circle cx="16" cy="16" r="4" fill="currentColor"/>'),
    ]


def svg_markup(body, size, color):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="{size}" '
            f'height="{size}" style="color:{color};display:block">{body}</svg>')


def raster_16(browser, slug, body, bg, fg, dpr=1):
    ctx = browser.new_context(viewport={"width": 16, "height": 16}, device_scale_factor=dpr)
    page = ctx.new_page()
    page.set_content(
        f'<!doctype html><html><body style="margin:0;background:{bg}">'
        f'<div style="width:16px;height:{16}px;color:{fg}">{svg_markup(body, 16, fg)}</div>'
        f'</body></html>', wait_until="load")
    suffix = "-dpr2" if dpr == 2 else ""
    page.screenshot(path=str(RASTER / f"{slug}-16{suffix}-{bg.lstrip('#')}.png"),
                    clip={"x": 0, "y": 0, "width": 16, "height": 16})
    ctx.close()


def main():
    RASTER.mkdir(parents=True, exist_ok=True)
    SHEETS.mkdir(parents=True, exist_ok=True)
    concepts = build_concepts()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for label, body in concepts:
            slug = label.split(" ")[0].lower()
            for bg, fg in ((PAPER, INK), (INK, PAPER)):
                raster_16(browser, slug, body, bg, fg, 1)
                raster_16(browser, slug, body, bg, fg, 2)
        browser.close()

    face = ('@font-face{font-family:"Bricolage";src:url("' +
            (FONTS / "BricolageGrotesque-var.ttf").as_uri() +
            '") format("truetype");font-weight:1 1000;font-display:block}')
    rows = []
    for label, body in concepts:
        slug = label.split(" ")[0].lower()
        rows.append(f"""
  <tr>
    <td class="label">{label}</td>
    <td class="cell ink"><div class="lk">{svg_markup(body, 56, EMERALD)}<span class="wm light">hutch<span class="pd">.</span></span></div></td>
    <td class="cell paper"><div class="lk">{svg_markup(body, 56, INK)}<span class="wm">hutch<span class="pd">.</span></span></div></td>
    <td class="cell ink"><div class="big">{svg_markup(body, 96, EMERALD)}</div></td>
    <td class="cell white"><div class="s32">{svg_markup(body, 32, INK)}</div></td>
    <td class="cell white zoom"><img src="../raster3/{slug}-16-{PAPER.lstrip('#')}.png" width="128" height="128" alt=""><div class="cap">16px x8 light</div></td>
    <td class="cell ink zoom"><img src="../raster3/{slug}-16-{INK.lstrip('#')}.png" width="128" height="128" alt=""><div class="cap d">16px x8 dark</div></td>
    <td class="cell white zoom"><img src="../raster3/{slug}-16-dpr2-{PAPER.lstrip('#')}.png" width="64" height="64" alt=""><div class="cap">dpr2 x4</div></td>
  </tr>""")

    html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
{face}
.wm{{font-family:'Bricolage';font-weight:800;font-size:42px;letter-spacing:-0.02em;
color:{INK};line-height:1}} .wm.light{{color:{PAPER}}}
.pd{{color:{EMERALD}}}
body{{margin:0;padding:16px;background:#fff;font-family:monospace;font-size:12px;color:#111}}
h1{{font-size:16px}} table{{border-collapse:collapse}}
td{{border:1px solid #bbb;padding:6px;vertical-align:middle;text-align:center}}
.label{{text-align:left;width:250px;vertical-align:top;font-size:11px}}
.cell{{padding:6px}} .ink{{background:{INK}}} .paper{{background:{PAPER}}} .white{{background:#fff}}
.lk{{display:flex;align-items:center;gap:14px}}
.big,.s32{{display:flex;justify-content:center}}
.zoom img{{image-rendering:pixelated;display:block;margin:0 auto}}
.cap{{font-size:10px;color:#555;margin-top:4px}} .cap.d{{color:#888}}
td.ink .cap{{color:#888}}
</style></head><body>
<h1>Round 3 constructed marks vs the chosen Bricolage Grotesque 800 wordmark - selection evidence,
2026-10-29 (not production assets; collision screen still owed)</h1>
<table><thead><tr><th>concept</th><th>lockup on ink</th><th>lockup on paper</th><th>96px mark</th>
<th>32px</th><th>16px light x8</th><th>16px dark x8</th><th>16px dpr2</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
</body></html>"""
    out = SHEETS / "round3-sheet.html"
    out.write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        page.goto(out.as_uri(), wait_until="load")
        page.wait_for_timeout(700)
        page.screenshot(path=str(SHEETS / "round3-sheet.png"), full_page=True)
        browser.close()
    print("wrote", SHEETS / "round3-sheet.png")


if __name__ == "__main__":
    main()
