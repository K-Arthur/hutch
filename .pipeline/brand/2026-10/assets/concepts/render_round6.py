#!/usr/bin/env python3
"""Round 6: N5 (contact-sheet two-bot front) evolutions + WB cabinet reference.

The human clarified that "N5" means the arch-front-with-two-residents concept in
round-1 contact-sheet.png, and asked for the friendly-enclosure archetype as
inspiration (no character copied: no ghost outline, wavy skirt, eye treatment or
palette from any existing work). Selection evidence only.
"""
import pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent
FONTS, SHEETS, RASTER = ROOT / "fonts", ROOT / "sheets", ROOT / "raster6"
INK, PAPER, EMERALD = "#09090b", "#ededf0", "#34d399"

ARCH = "M4 28 V15 A12 12 0 0 1 28 15 V28 Z"
ARCH_S = "M3 29 V15 A13 13 0 0 1 29 15 V29 Z"

def em(cx, cy, r):
    return f'<circle class="dotc" cx="{cx}" cy="{cy}" r="{r}"/>'

def hole(cx, cy, r):
    return f"M{cx - r} {cy} a {r} {r} 0 1 0 {2 * r} 0 a {r} {r} 0 1 0 {-2 * r} 0 Z"

# N5e-1: solid front, two emerald residents (two-tone)
N5E1 = ('<path fill="currentColor" d="' + ARCH + '"/>'
        + em(11.5, 17.5, 3.2) + em(20.5, 17.5, 3.2))
# N5e-2: solid front, residents as knockouts (mono-first, no colour)
N5E2 = ('<path fill-rule="evenodd" fill="currentColor" d="' + ARCH
        + " " + hole(11.5, 17.5, 3.2) + " " + hole(20.5, 17.5, 3.2) + '"/>')
# N5e-3: thick outline front (meld with the heavy wordmark), two residents
N5E3 = ('<path fill="none" stroke="currentColor" stroke-width="3.4" stroke-linejoin="miter" d="'
        + ARCH + '"/>' + em(11.5, 17.5, 3.4) + em(20.5, 17.5, 3.4))
# N5e-4: solid front with a doorway gap in the floor, residents above it
N5E4 = ('<path fill-rule="evenodd" fill="currentColor" d="' + ARCH
        + ' M11 28 V27 H21 V28 Z"/>' + em(11.5, 15.5, 3.0) + em(20.5, 15.5, 3.0))
# WB-A reference (single resident cabinet)
WB_A = ('<path fill-rule="evenodd" fill="currentColor" d="M9 3 H23 A6 6 0 0 1 29 9 V23 A6 6 0 0 1 23 29 '
        'H9 A6 6 0 0 1 3 23 V9 A6 6 0 0 1 9 3 Z M9 29 V22 A7 7 0 0 1 23 22 V29 Z"/>')
WB_A_DOT = WB_A + em(16, 23.2, 3.8)
# N5 original for lineage comparison
N5_ORIG = ('<path fill="none" stroke="currentColor" stroke-width="2.5" stroke-linejoin="miter" d="'
           + ARCH + '"/>' + em(11.5, 17.5, 3.0) + em(20.5, 17.5, 3.0))

SMALLS = {
    "n5e1": ('<path fill="currentColor" d="' + ARCH_S + '"/>' + em(11.6, 17.6, 3.3) + em(20.4, 17.6, 3.3)),
    "n5e2": ('<path fill-rule="evenodd" fill="currentColor" d="' + ARCH_S
             + " " + hole(11.6, 17.6, 3.3) + " " + hole(20.4, 17.6, 3.3) + '"/>'),
    "n5e3": ('<path fill="none" stroke="currentColor" stroke-width="3.6" stroke-linejoin="miter" d="'
             + ARCH_S + '"/>' + em(11.6, 17.6, 3.4) + em(20.4, 17.6, 3.4)),
    "n5e4": ('<path fill-rule="evenodd" fill="currentColor" d="' + ARCH_S
             + ' M11 29 V28 H21 V29 Z"/>' + em(11.6, 15.6, 3.1) + em(20.4, 15.6, 3.1)),
    "wba":  ('<path fill-rule="evenodd" fill="currentColor" d="M8 2 H24 A7 7 0 0 1 31 9 V23 A7 7 0 0 1 24 30 '
             'H8 A7 7 0 0 1 1 23 V9 A7 7 0 0 1 8 2 Z M8.5 30 V22 A7.5 7.5 0 0 1 23.5 22 V30 Z"/>'
             + em(16, 3.2e1 - 6.4, 4.2)),
    "n5orig": ('<path fill="none" stroke="currentColor" stroke-width="3" stroke-linejoin="miter" d="'
               + ARCH_S + '"/>' + em(11.6, 17.6, 3.2) + em(20.4, 17.6, 3.2)),
}

CONCEPTS = [
    ("N5e-1 Solid Front, two residents (two-tone)", N5E1, "n5e1"),
    ("N5e-2 Solid Front, residents knocked out (mono)", N5E2, "n5e2"),
    ("N5e-3 Thick outline front (wordmark weight)", N5E3, "n5e3"),
    ("N5e-4 Solid Front + doorway, residents above", N5E4, "n5e4"),
    ("WB-A Cabinet (reference, single resident)", WB_A_DOT, "wba"),
    ("N5 original (lineage reference)", N5_ORIG, "n5orig"),
]

def svg(b, size, color):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="{size}" '
            f'height="{size}" style="color:{color};display:block">{b}</svg>')

def raster(browser, slug, b, bg, fg):
    ctx = browser.new_context(viewport={"width": 16, "height": 16}, device_scale_factor=1)
    page = ctx.new_page()
    page.set_content(f'<!doctype html><head><style>.dotc{{fill:{EMERALD}}}</style></head>'
                     f'<body style="margin:0;background:{bg}">'
                     f'<div style="width:16px;height:16px;color:{fg}">{svg(b,16,fg)}</div></body>',
                     wait_until="load")
    page.screenshot(path=str(RASTER / f"{slug}-16-{bg.lstrip('#')}.png"),
                    clip={"x":0,"y":0,"width":16,"height":16})
    ctx.close()

def main():
    RASTER.mkdir(parents=True, exist_ok=True); SHEETS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        for _label, body, slug in CONCEPTS:
            raster(b, slug, body, PAPER, INK)
            raster(b, slug, body, INK, PAPER)
            raster(b, slug + "s", SMALLS[slug], PAPER, INK)
        b.close()

    face = ('@font-face{font-family:"Bricolage";src:url("' +
            (FONTS / "BricolageGrotesque-var.ttf").as_uri() +
            '") format("truetype");font-weight:1 1000;font-display:block}')
    rows = []
    for label, body, slug in CONCEPTS:
        rows.append(f"""
  <tr>
    <td class="label">{label}</td>
    <td class="cell ink"><div class="lk">{svg(body, 56, PAPER)}<span class="wm light">hutch<span class="pd">.</span></span></div></td>
    <td class="cell paper"><div class="lk">{svg(body, 56, INK)}<span class="wm">hutch<span class="pd">.</span></span></div></td>
    <td class="cell white">{svg(body, 140, INK)}<div class="cap">on paper</div></td>
    <td class="cell ink">{svg(body, 140, PAPER)}<div class="cap d">on ink</div></td>
    <td class="cell white"><div class="sizes">
      <div>{svg(body, 48, INK)}<span class="cap">48</span></div>
      <div>{svg(body, 32, INK)}<span class="cap">32</span></div>
      <div>{svg(body, 24, INK)}<span class="cap">24</span></div>
      <div>{svg(SMALLS[slug], 16, INK)}<span class="cap">16 small</span></div></div></td>
    <td class="cell white zoom"><img src="../raster6/{slug}-16-{PAPER.lstrip('#')}.png" width="112" height="112"><div class="cap">16 light x7</div></td>
    <td class="cell ink zoom"><img src="../raster6/{slug}-16-{INK.lstrip('#')}.png" width="112" height="112"><div class="cap d">16 dark x7</div></td>
    <td class="cell white zoom"><img src="../raster6/{slug}s-16-{PAPER.lstrip('#')}.png" width="112" height="112"><div class="cap">16 small x7</div></td>
  </tr>""")

    html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
.dotc{{fill:{EMERALD}}}
{face}
.wm{{font-family:'Bricolage';font-weight:800;font-size:42px;letter-spacing:-0.02em;color:{INK};line-height:1}}
.wm.light{{color:{PAPER}}} .pd{{color:{EMERALD}}}
body{{margin:0;padding:14px;background:#fff;font-family:monospace;font-size:12px}}
h1{{font-size:15px}} table{{border-collapse:collapse}}
td{{border:1px solid #bbb;padding:6px;vertical-align:middle;text-align:center}}
.label{{width:250px;text-align:left;font-size:11px;vertical-align:top}}
.ink{{background:{INK}}} .paper{{background:{PAPER}}} .white{{background:#fff}}
.lk{{display:flex;align-items:center;gap:14px}}
.sizes{{display:flex;gap:10px;align-items:flex-end;justify-content:center}}
.sizes>div{{display:flex;flex-direction:column;align-items:center;gap:3px}}
.zoom img{{image-rendering:pixelated}}
.cap{{font-size:10px;color:#555}} .cap.d{{color:#999}}
</style></head><body>
<h1>Round 6 - N5 (contact-sheet two-bot front) evolutions + WB reference, 2026-10-29.
Two-tone = enclosure currentColor, residents emerald-400. Selection evidence; not cleared.</h1>
<table><tbody>{''.join(rows)}</tbody></table></body></html>"""
    out = SHEETS / "round6-sheet.html"
    out.write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1750, "height": 900})
        page.goto(out.as_uri(), wait_until="load"); page.wait_for_timeout(600)
        page.screenshot(path=str(SHEETS / "round6-sheet.png"), full_page=True)
        b.close()
    print("wrote", SHEETS / "round6-sheet.png")

if __name__ == "__main__":
    main()
