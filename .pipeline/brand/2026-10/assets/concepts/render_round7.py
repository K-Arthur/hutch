#!/usr/bin/env python3
"""Round 7: N5 family refinements (doorway and plinth variants) + WB reference.

Two-tone logic under test: enclosure = currentColor (ink/paper), residents = emerald-400.
The mark stays single-colour-capable via the knockout form. Selection evidence only.
"""
import pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent
FONTS, SHEETS, RASTER = ROOT / "fonts", ROOT / "sheets", ROOT / "raster7"
INK, PAPER, EMERALD = "#09090b", "#ededf0", "#34d399"

ARCH  = "M4 28 V15 A12 12 0 0 1 28 15 V28 Z"
ARCH_S = "M3 29 V15 A13 13 0 0 1 29 15 V29 Z"

def em(cx, cy, r):
    return f'<circle class="dotc" cx="{cx}" cy="{cy}" r="{r}"/>'

def hole(cx, cy, r):
    return f"M{cx - r} {cy} a {r} {r} 0 1 0 {2 * r} 0 a {r} {r} 0 1 0 {-2 * r} 0 Z"

# R7-1 solid front, two residents (round-6 N5e-1, control)
R7_1 = '<path fill="currentColor" d="' + ARCH + '"/>' + em(11.5, 17.5, 3.2) + em(20.5, 17.5, 3.2)
# R7-2 solid front + real doorway, residents above the door
R7_2 = ('<path fill-rule="evenodd" fill="currentColor" d="' + ARCH
        + ' M11 28 V22.5 A5 5 0 0 1 21 22.5 V28 Z"/>' + em(11.5, 12, 3.2) + em(20.5, 12, 3.2))
# R7-3 solid front + plinth (furniture base)
R7_3 = ('<path fill="currentColor" d="' + ARCH + '"/>'
        '<rect x="1.5" y="28" width="29" height="2.4" rx="1.2" fill="currentColor"/>'
        + em(11.5, 17, 3.2) + em(20.5, 17, 3.2))
# R7-4 solid front, residents knocked out (mono-first form of R7-1)
R7_4 = ('<path fill-rule="evenodd" fill="currentColor" d="' + ARCH + " "
        + hole(11.5, 17.5, 3.4) + " " + hole(20.5, 17.5, 3.4) + '"/>')
# R7-5 WB-A two-tone (single resident cabinet, reference)
R7_5 = ('<path fill-rule="evenodd" fill="currentColor" d="M9 3 H23 A6 6 0 0 1 29 9 V23 A6 6 0 0 1 23 29 '
        'H9 A6 6 0 0 1 3 23 V9 A6 6 0 0 1 9 3 Z M9 29 V22 A7 7 0 0 1 23 22 V29 Z"/>' + em(16, 23.2, 3.8))

SMALLS = {
 "r7-1": '<path fill="currentColor" d="' + ARCH_S + '"/>' + em(11.6, 17.6, 3.4) + em(20.4, 17.6, 3.4),
 "r7-2": ('<path fill-rule="evenodd" fill="currentColor" d="' + ARCH_S
          + ' M10.5 29 V22.5 A5.5 5.5 0 0 1 21.5 22.5 V29 Z"/>' + em(11.6, 12, 3.4) + em(20.4, 12, 3.4)),
 "r7-3": ('<path fill="currentColor" d="' + ARCH_S + '"/>'
          '<rect x="0.8" y="29" width="30.4" height="2.4" rx="1.2" fill="currentColor"/>'
          + em(11.6, 17, 3.4) + em(20.4, 17, 3.4)),
 "r7-4": ('<path fill-rule="evenodd" fill="currentColor" d="' + ARCH_S + " "
          + hole(11.6, 17.6, 3.6) + " " + hole(20.4, 17.6, 3.6) + '"/>'),
 "r7-5": ('<path fill-rule="evenodd" fill="currentColor" d="M8 2 H24 A7 7 0 0 1 31 9 V23 A7 7 0 0 1 24 30 '
          'H8 A7 7 0 0 1 1 23 V9 A7 7 0 0 1 8 2 Z M8.5 30 V22 A7.5 7.5 0 0 1 23.5 22 V30 Z"/>' + em(16, 23.8, 4.0)),
}
CONCEPTS = [
    ("R7-1 Solid front, two residents (round-6 pick candidate)", R7_1, "r7-1"),
    ("R7-2 Solid front + doorway, residents above", R7_2, "r7-2"),
    ("R7-3 Solid front + plinth", R7_3, "r7-3"),
    ("R7-4 Solid front, residents knocked out (mono form)", R7_4, "r7-4"),
    ("R7-5 WB-A two-tone (single resident)", R7_5, "r7-5"),
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
        for _l, body, slug in CONCEPTS:
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
    <td class="cell white zoom"><img src="../raster7/{slug}-16-{PAPER.lstrip('#')}.png" width="112" height="112"><div class="cap">16 light x7</div></td>
    <td class="cell ink zoom"><img src="../raster7/{slug}-16-{INK.lstrip('#')}.png" width="112" height="112"><div class="cap d">16 dark x7</div></td>
    <td class="cell white zoom"><img src="../raster7/{slug}s-16-{PAPER.lstrip('#')}.png" width="112" height="112"><div class="cap">16 small x7</div></td>
  </tr>""")
    html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
.dotc{{fill:{EMERALD}}}
{face}
.wm{{font-family:'Bricolage';font-weight:800;font-size:42px;letter-spacing:-0.02em;color:{INK};line-height:1}}
.wm.light{{color:{PAPER}}} .pd{{color:{EMERALD}}}
body{{margin:0;padding:14px;background:#fff;font-family:monospace;font-size:12px}}
h1{{font-size:15px}} table{{border-collapse:collapse}}
td{{border:1px solid #bbb;padding:6px;vertical-align:middle;text-align:center}}
.label{{width:270px;text-align:left;font-size:11px;vertical-align:top}}
.ink{{background:{INK}}} .paper{{background:{PAPER}}} .white{{background:#fff}}
.lk{{display:flex;align-items:center;gap:14px}}
.sizes{{display:flex;gap:10px;align-items:flex-end;justify-content:center}}
.sizes>div{{display:flex;flex-direction:column;align-items:center;gap:3px}}
.zoom img{{image-rendering:pixelated}}
.cap{{font-size:10px;color:#555}} .cap.d{{color:#999}}
</style></head><body>
<h1>Round 7 - N5 family refinements (doorway, plinth, mono form) + WB two-tone, 2026-10-29.
Selection evidence; collision screen partial; nothing cleared.</h1>
<table><tbody>{''.join(rows)}</tbody></table></body></html>"""
    out = SHEETS / "round7-sheet.html"
    out.write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1800, "height": 900})
        page.goto(out.as_uri(), wait_until="load"); page.wait_for_timeout(600)
        page.screenshot(path=str(SHEETS / "round7-sheet.png"), full_page=True)
        b.close()
    print("wrote", SHEETS / "round7-sheet.png")

if __name__ == "__main__":
    main()
