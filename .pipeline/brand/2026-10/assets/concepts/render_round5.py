#!/usr/bin/env python3
"""Round 5: WB cabinet refinements + the bot-family (N5 lineage / shelter read).

Brief 2026-10-29: develop WB and the two-resident "bot family", taking the
friendly-enclosure archetype as inspiration (not copying any character: no
ghost outline, no wavy skirt, no eye treatment; the form is a shelter/hutch with
residents, original geometry). Selection evidence only.
"""
import pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent
FONTS, SHEETS, RASTER = ROOT / "fonts", ROOT / "sheets", ROOT / "raster5"
INK, PAPER, EMERALD = "#09090b", "#ededf0", "#34d399"

def slab(x0, y0, x1, y1, r):
    return (f"M{x0 + r} {y0} H{x1 - r} A{r} {r} 0 0 1 {x1} {y0 + r} V{y1 - r} "
            f"A{r} {r} 0 0 1 {x1 - r} {y1} H{x0 + r} A{r} {r} 0 0 1 {x0} {y1 - r} "
            f"V{y0 + r} A{r} {r} 0 0 1 {x0 + r} {y0} Z")

def em(cx, cy, r):
    return f'<circle class="dotc" cx="{cx}" cy="{cy}" r="{r}"/>'

def body(*parts):
    return "".join(parts)

# ---- masters ----
WB_A  = body('<path fill-rule="evenodd" fill="currentColor" d="'
             + slab(3, 3, 29, 29, 6) + ' M9 29 V22 A7 7 0 0 1 23 22 V29 Z"/>', em(16, 23.2, 3.8))
WB_B  = body(WB_A, '<rect x="11" y="28.4" width="10" height="2.4" rx="1.2" fill="currentColor"/>')
BF1   = body('<rect x="1" y="3" width="30" height="7" rx="3.5" fill="currentColor"/>',
             '<rect x="3" y="9" width="3.5" height="20" fill="currentColor"/>',
             '<rect x="25.5" y="9" width="3.5" height="20" fill="currentColor"/>',
             em(11.5, 20.5, 3.5), em(20.5, 20.5, 3.5))
BF2   = body('<path fill="currentColor" d="M3 29 V12 A6 6 0 0 1 15 12 V29 Z"/>',
             '<path fill="currentColor" d="M17 29 V12 A6 6 0 0 1 29 12 V29 Z"/>',
             em(9, 20, 3), em(23, 20, 3))
BF3   = body('<path fill-rule="evenodd" fill="currentColor" d="'
             + slab(2, 2, 30, 30, 6) + ' M5 30 V20 A11 11 0 0 1 27 20 V30 Z"/>',
             em(11.5, 24.2, 3.4), em(20.5, 24.2, 3.4))

# ---- small masters (<=20px) ----
WB_A_S = body('<path fill-rule="evenodd" fill="currentColor" d="'
              + slab(2, 2, 30, 30, 6) + ' M8.5 30 V22 A7.5 7.5 0 0 1 23.5 22 V30 Z"/>', em(16, 23.6, 4.2))
WB_B_S = body(WB_A_S, '<rect x="11" y="29.4" width="10" height="2.4" rx="1.2" fill="currentColor"/>')
BF1_S  = body('<rect x="0.5" y="2.5" width="31" height="7.5" rx="3.7" fill="currentColor"/>',
              '<rect x="2" y="9.5" width="4" height="20.5" fill="currentColor"/>',
              '<rect x="26" y="9.5" width="4" height="20.5" fill="currentColor"/>',
              em(11.3, 20.8, 3.9), em(20.7, 20.8, 3.9))
BF2_S  = body('<path fill="currentColor" d="M2 30 V12 A6.5 6.5 0 0 1 15 12 V30 Z"/>',
              '<path fill="currentColor" d="M17 30 V12 A6.5 6.5 0 0 1 30 12 V30 Z"/>',
              em(8.5, 20.5, 3.4), em(23.5, 20.5, 3.4))
BF3_S  = body('<path fill-rule="evenodd" fill="currentColor" d="'
              + slab(1, 1, 31, 31, 6.5) + ' M5 31 V20 A11 11 0 0 1 27 20 V31 Z"/>',
              em(11.3, 24.6, 3.8), em(20.7, 24.6, 3.8))

CONCEPTS = [
    ("WB-A Cabinet refined", WB_A, WB_A_S),
    ("WB-B Cabinet + step", WB_B, WB_B_S),
    ("BF-1 Awning Shelter (two residents)", BF1, BF1_S),
    ("BF-2 Twin Hutches", BF2, BF2_S),
    ("BF-3 Wide Porch (shelter, two residents)", BF3, BF3_S),
]

def svg(b, size, color):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="{size}" '
            f'height="{size}" style="color:{color};display:block">{b}</svg>')

def raster(browser, slug, b, bg, fg, which="m"):
    ctx = browser.new_context(viewport={"width": 16, "height": 16}, device_scale_factor=1)
    page = ctx.new_page()
    page.set_content(f'<!doctype html><body style="margin:0;background:{bg}">'
                     f'<div style="width:16px;height:16px;color:{fg}">{svg(b,16,fg)}</div></body>',
                     wait_until="load")
    page.screenshot(path=str(RASTER / f"{slug}-{which}-16-{bg.lstrip('#')}.png"),
                    clip={"x":0,"y":0,"width":16,"height":16})
    ctx.close()

def main():
    RASTER.mkdir(parents=True, exist_ok=True); SHEETS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        for label, master, small in CONCEPTS:
            slug = label.split(" ")[0].lower()
            for bg, fg in ((PAPER, INK), (INK, PAPER)):
                raster(b, slug, master, bg, fg, "m")
                raster(b, slug, small, bg, fg, "s")
        b.close()

    face = ('@font-face{font-family:"Bricolage";src:url("' +
            (FONTS / "BricolageGrotesque-var.ttf").as_uri() +
            '") format("truetype");font-weight:1 1000;font-display:block}')
    rows = []
    for label, master, small in CONCEPTS:
        slug = label.split(" ")[0].lower()
        rows.append(f"""
  <tr>
    <td class="label">{label}</td>
    <td class="cell ink"><div class="lk">{svg(master, 56, EMERALD)}<span class="wm light">hutch<span class="pd">.</span></span></div></td>
    <td class="cell white">{svg(master, 150, INK)}<div class="cap">master 150px</div></td>
    <td class="cell ink">{svg(master, 150, EMERALD)}<div class="cap d">emerald on ink</div></td>
    <td class="cell white"><div class="sizes">
      <div>{svg(master, 48, INK)}<span class="cap">48</span></div>
      <div>{svg(master, 32, INK)}<span class="cap">32</span></div>
      <div>{svg(master, 24, INK)}<span class="cap">24</span></div>
      <div>{svg(small, 16, INK)}<span class="cap">16 small</span></div></div></td>
    <td class="cell white zoom"><img src="../raster5/{slug}-m-16-{PAPER.lstrip('#')}.png" width="112" height="112"><div class="cap">16 light x7</div></td>
    <td class="cell ink zoom"><img src="../raster5/{slug}-m-16-{INK.lstrip('#')}.png" width="112" height="112"><div class="cap d">16 dark x7</div></td>
    <td class="cell white zoom"><img src="../raster5/{slug}-s-16-{PAPER.lstrip('#')}.png" width="112" height="112"><div class="cap">16 small x7</div></td>
  </tr>""")

    html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
{face}
.wm{{font-family:'Bricolage';font-weight:800;font-size:42px;letter-spacing:-0.02em;color:{INK};line-height:1}}
.wm.light{{color:{PAPER}}} .pd{{color:{EMERALD}}}
body{{margin:0;padding:14px;background:#fff;font-family:monospace;font-size:12px}}
h1{{font-size:15px}} table{{border-collapse:collapse}}
td{{border:1px solid #bbb;padding:7px;vertical-align:middle;text-align:center}}
.label{{width:235px;text-align:left;font-size:11px;vertical-align:top}}
.ink{{background:{INK}}} .white{{background:#fff}}
.lk{{display:flex;align-items:center;gap:14px}}
.sizes{{display:flex;gap:10px;align-items:flex-end;justify-content:center}}
.sizes>div{{display:flex;flex-direction:column;align-items:center;gap:3px}}
.zoom img{{image-rendering:pixelated}}
.cap{{font-size:10px;color:#555}} .cap.d{{color:#999}}
</style></head><body>
<h1>Round 5 - WB cabinet refinements + bot family (shelter read; no character copied) - 2026-10-29.
Selection evidence; the collision screen is partial and nothing is cleared.</h1>
<table><tbody>{''.join(rows)}</tbody></table></body></html>"""
    out = SHEETS / "round5-sheet.html"
    out.write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1600, "height": 900})
        page.goto(out.as_uri(), wait_until="load"); page.wait_for_timeout(500)
        page.screenshot(path=str(SHEETS / "round5-sheet.png"), full_page=True)
        b.close()
    print("wrote", SHEETS / "round5-sheet.png")

if __name__ == "__main__":
    main()
