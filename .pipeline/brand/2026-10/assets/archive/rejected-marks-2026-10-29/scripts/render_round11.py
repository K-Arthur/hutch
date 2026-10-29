#!/usr/bin/env python3
"""Round 11: differentiate R7-4 by interior typology (window shape), not by adding a hat.

R7-4 kept: arch front M4 28 V15 A12 12 0 0 1 28 15 V28 Z.
The two circular residents read as eyes; replacing them with architectural windows
removes the mask/ghost read while keeping the silhouette the human liked.
  E1 two rounded-square windows 6.0 x 6.6, r1.5
  E2 two vertical slot windows 4.4 x 9.4, r2.2
  E3 two slot windows + thin base board
  E4 one wide window 12.0 x 7.0, r2.0 (single wire-door window)
Selection evidence only.
"""
import pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent
FONTS, SHEETS, RASTER = ROOT / "fonts", ROOT / "sheets", ROOT / "raster11"
INK, PAPER, EMERALD = "#09090b", "#ededf0", "#34d399"

ARCH = "M4 28 V15 A12 12 0 0 1 28 15 V28 Z"
ARCH_S = "M3 28.5 V15 A13 13 0 0 1 29 15 V28.5 Z"

def rrect(cx, cy, w, h, r):
    x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
    return (f"M{x0 + r} {y0} H{x1 - r} A{r} {r} 0 0 1 {x1} {y0 + r} V{y1 - r} "
            f"A{r} {r} 0 0 1 {x1 - r} {y1} H{x0 + r} A{r} {r} 0 0 1 {x0} {y1 - r} "
            f"V{y0 + r} A{r} {r} 0 0 1 {x0 + r} {y0} Z")

def front(holes):
    return '<path fill-rule="evenodd" fill="currentColor" d="' + ARCH + " " + " ".join(holes) + '"/>'

def front_s(holes):
    return '<path fill-rule="evenodd" fill="currentColor" d="' + ARCH_S + " " + " ".join(holes) + '"/>'

# masters
E1   = lambda: front([rrect(11.5, 17.5, 6.0, 6.6, 1.5), rrect(20.5, 17.5, 6.0, 6.6, 1.5)])
E2   = lambda: front([rrect(11.5, 17.5, 4.4, 9.4, 2.2), rrect(20.5, 17.5, 4.4, 9.4, 2.2)])
E3   = lambda: (E2() + '<rect x="2" y="28" width="28" height="2.2" rx="1.1" fill="currentColor"/>')
E4   = lambda: front([rrect(16, 17.8, 12.0, 7.0, 2.0)])
# small masters (redrawn: wider windows, thicker)
E1_S = lambda: front_s([rrect(11.2, 17.2, 7.0, 7.4, 1.8), rrect(20.8, 17.2, 7.0, 7.4, 1.8)])
E2_S = lambda: front_s([rrect(11.2, 17.2, 5.4, 10.6, 2.7), rrect(20.8, 17.2, 5.4, 10.6, 2.7)])
E3_S = lambda: (E2_S() + '<rect x="1" y="28.5" width="30" height="2.4" rx="1.2" fill="currentColor"/>')
E4_S = lambda: front_s([rrect(16, 17.6, 14.0, 8.0, 2.4)])

CONCEPTS = [
    ("R7-4 base (circular residents)", lambda: front([rrect(11.5,17.5,6.8,6.8,3.4), rrect(20.5,17.5,6.8,6.8,3.4)]),
     lambda: front_s([rrect(11.2,17.4,7.6,7.6,3.8), rrect(20.8,17.4,7.6,7.6,3.8)])),
    ("E1 rounded-square windows", E1, E1_S),
    ("E2 vertical slot windows", E2, E2_S),
    ("E3 slot windows + base board", E3, E3_S),
    ("E4 one wide window", E4, E4_S),
]

def svg(b, size, color):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="{size}" '
            f'height="{size}" style="color:{color};display:block">{b}</svg>')

def raster(browser, slug, b, bg, fg, px=16):
    ctx = browser.new_context(viewport={"width": px, "height": px}, device_scale_factor=1)
    page = ctx.new_page()
    page.set_content(f'<!doctype html><body style="margin:0;background:{bg}">'
                     f'<div style="width:{px}px;height:{px}px;color:{fg}">{svg(b,px,fg)}</div></body>',
                     wait_until="load")
    page.screenshot(path=str(RASTER / f"{slug}-{px}-{bg.lstrip('#')}.png"),
                    clip={"x":0,"y":0,"width":px,"height":px})
    ctx.close()

def main():
    RASTER.mkdir(parents=True, exist_ok=True); SHEETS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        for i, (_l, m, s) in enumerate(CONCEPTS):
            for bg, fg in ((PAPER, INK), (INK, PAPER)):
                raster(b, f"r11-{i}", m(), bg, fg)
                raster(b, f"r11-{i}s", s(), bg, fg)
        b.close()
    face = ('@font-face{font-family:"Bricolage";src:url("' +
            (FONTS / "BricolageGrotesque-var.ttf").as_uri() +
            '") format("truetype");font-weight:1 1000;font-display:block}')
    rows = []
    for i, (label, m, s) in enumerate(CONCEPTS):
        rows.append(f"""
  <tr>
    <td class="label">{label}</td>
    <td class="cell ink"><div class="lk">{svg(m(), 56, PAPER)}<span class="wm light">hutch<span class="pd">.</span></span></div></td>
    <td class="cell paper"><div class="lk">{svg(m(), 56, INK)}<span class="wm">hutch<span class="pd">.</span></span></div></td>
    <td class="cell white">{svg(m(), 170, INK)}<div class="cap">on paper</div></td>
    <td class="cell ink">{svg(m(), 170, PAPER)}<div class="cap d">on ink</div></td>
    <td class="cell white"><div class="sizes">
      <div>{svg(m(), 48, INK)}<span class="cap">48</span></div>
      <div>{svg(m(), 32, INK)}<span class="cap">32</span></div>
      <div>{svg(s(), 24, INK)}<span class="cap">24 small</span></div>
      <div>{svg(s(), 16, INK)}<span class="cap">16 small</span></div></div></td>
    <td class="cell white zoom"><img src="../raster11/r11-{i}s-16-{PAPER.lstrip('#')}.png" width="140" height="140"><div class="cap">16 light x8.75</div></td>
    <td class="cell ink zoom"><img src="../raster11/r11-{i}s-16-{INK.lstrip('#')}.png" width="140" height="140"><div class="cap d">16 dark x8.75</div></td>
  </tr>""")
    applied = f"""<!doctype html><html><head><meta charset="utf-8"><style>
{face}
.wm{{font-family:'Bricolage';font-weight:800;font-size:42px;letter-spacing:-0.02em;color:{INK};line-height:1}}
.wm.light{{color:{PAPER}}} .pd{{color:{EMERALD}}}
body{{margin:0;padding:16px;background:#fff;font-family:monospace;font-size:12px}}
h1{{font-size:15px}} table{{border-collapse:collapse}}
td{{border:1px solid #bbb;padding:8px;vertical-align:middle;text-align:center}}
.label{{width:230px;text-align:left;font-size:11px;vertical-align:top}}
.ink{{background:{INK}}} .paper{{background:{PAPER}}} .white{{background:#fff}}
.lk{{display:flex;align-items:center;gap:14px}}
.sizes{{display:flex;gap:14px;align-items:flex-end;justify-content:center}}
.sizes>div{{display:flex;flex-direction:column;align-items:center;gap:4px}}
.zoom img{{image-rendering:pixelated}}
.cap{{font-size:10px;color:#555}} .cap.d{{color:#999}}
</style></head><body>
<h1>R7-4 differentiation - interior typology, 2026-10-29. Selection evidence only.</h1>
<table><tbody>{''.join(rows)}</tbody></table></body></html>"""
    apath = SHEETS / "round11-applied.html"
    apath.write_text(applied, encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1600, "height": 900})
        page.goto(apath.as_uri(), wait_until="load"); page.wait_for_timeout(600)
        page.screenshot(path=str(SHEETS / "round11-applied.png"), full_page=True)
        b.close()
    print("wrote round11-applied.png")

if __name__ == "__main__":
    main()
