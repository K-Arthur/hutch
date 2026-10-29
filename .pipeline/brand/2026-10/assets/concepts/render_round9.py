#!/usr/bin/env python3
"""Round 9: differentiate R7-4 (solid front, two knocked-out residents).

R7-4 is kept as the base (human liked it). Three precise differentiators are
drawn, each on the 32-unit grid, each with its own small master:
  D1 plinth  - the front stands on a wider base board (cabinet read)
  D2 canopy  - a trapezoid roof cap overhangs the arch (hutch/awning read)
  D3 seam    - a door seam splits the lower front into two leaves (double-door read)
None of these copies or traces any existing mark; geometry is constructed.
Selection evidence only.
"""
import pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent
FONTS, SHEETS, RASTER = ROOT / "fonts", ROOT / "sheets", ROOT / "raster9"
INK, PAPER, EMERALD = "#09090b", "#ededf0", "#34d399"

ARCH = "M4 28 V15 A12 12 0 0 1 28 15 V28 Z"
ARCH_S = "M3 28.5 V15 A13 13 0 0 1 29 15 V28.5 Z"

def hole(cx, cy, r):
    return f"M{cx - r} {cy} a {r} {r} 0 1 0 {2 * r} 0 a {r} {r} 0 1 0 {-2 * r} 0 Z"

# R7-4 base ------------------------------------------------------------
BASE = lambda: ('<path fill-rule="evenodd" fill="currentColor" d="' + ARCH + " "
                + hole(11.5, 17.5, 3.4) + " " + hole(20.5, 17.5, 3.4) + '"/>')
BASE_S = lambda: ('<path fill-rule="evenodd" fill="currentColor" d="' + ARCH_S + " "
                  + hole(11.2, 17.4, 3.8) + " " + hole(20.8, 17.4, 3.8) + '"/>')

# D1 plinth ------------------------------------------------------------
D1 = lambda: (BASE() + '<rect x="1.5" y="28" width="29" height="2.6" rx="1.2" fill="currentColor"/>')
D1_S = lambda: (BASE_S() + '<rect x="1" y="28.5" width="30" height="2.6" rx="1.3" fill="currentColor"/>')

# D2 canopy ------------------------------------------------------------
D2 = lambda: ('<path fill="currentColor" d="M7 1.4 H25 L30.5 4.6 H1.5 Z"/>' + BASE())
D2_S = lambda: ('<path fill="currentColor" d="M5 0.8 H27 L31 4.4 H1 Z"/>'
                + '<path fill-rule="evenodd" fill="currentColor" d="' + ARCH_S + " "
                + hole(11.2, 17.4, 3.8) + " " + hole(20.8, 17.4, 3.8) + '"/>')

# D3 seam --------------------------------------------------------------
SEAM = "M15.2 28 V13.6 Q15.2 12.9 15.9 12.9 H16.1 Q16.8 12.9 16.8 13.6 V28 Z"
D3 = lambda: ('<path fill-rule="evenodd" fill="currentColor" d="' + ARCH + " "
              + hole(11.5, 17.5, 3.4) + " " + hole(20.5, 17.5, 3.4) + " " + SEAM + '"/>')
D3_S = lambda: BASE_S()

CONCEPTS = [
    ("R7-4 base (reference)", BASE, BASE_S),
    ("D1 Plinth (cabinet base board)", D1, D1_S),
    ("D2 Canopy (roof cap overhang)", D2, D2_S),
    ("D3 Door seam (two leaves)", D3, D3_S),
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

def dim(x1, y1, x2, y2, label, off=(0, -5)):
    mx, my = (x1 + x2) / 2 + off[0], (y1 + y2) / 2 + off[1]
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#c026d3" stroke-width="0.55"/>'
            f'<line x1="{x1}" y1="{y1-1.5}" x2="{x1}" y2="{y1+1.5}" stroke="#c026d3" stroke-width="0.55"/>'
            f'<line x1="{x2}" y1="{y2-1.5}" x2="{x2}" y2="{y2+1.5}" stroke="#c026d3" stroke-width="0.55"/>'
            f'<text x="{mx}" y="{my}" font-size="4.4" fill="#86198f" text-anchor="middle" '
            f'font-family="monospace">{label}</text>')

def main():
    RASTER.mkdir(parents=True, exist_ok=True); SHEETS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        for i, (label, m_fn, s_fn) in enumerate(CONCEPTS):
            slug = "r9-" + str(i)
            for bg, fg in ((PAPER, INK), (INK, PAPER)):
                raster(b, slug, m_fn(), bg, fg)
                raster(b, slug + "s", s_fn(), bg, fg)
        b.close()

    face = ('@font-face{font-family:"Bricolage";src:url("' +
            (FONTS / "BricolageGrotesque-var.ttf").as_uri() +
            '") format("truetype");font-weight:1 1000;font-display:block}')

    rows = []
    for i, (label, m_fn, s_fn) in enumerate(CONCEPTS):
        slug = "r9-" + str(i)
        rows.append(f"""
  <tr>
    <td class="label">{label}</td>
    <td class="cell ink"><div class="lk">{svg(m_fn(), 56, PAPER)}<span class="wm light">hutch<span class="pd">.</span></span></div></td>
    <td class="cell paper"><div class="lk">{svg(m_fn(), 56, INK)}<span class="wm">hutch<span class="pd">.</span></span></div></td>
    <td class="cell white">{svg(m_fn(), 170, INK)}<div class="cap">on paper</div></td>
    <td class="cell ink">{svg(m_fn(), 170, PAPER)}<div class="cap d">on ink</div></td>
    <td class="cell white"><div class="sizes">
      <div>{svg(m_fn(), 48, INK)}<span class="cap">48</span></div>
      <div>{svg(m_fn(), 32, INK)}<span class="cap">32</span></div>
      <div>{svg(s_fn(), 24, INK)}<span class="cap">24 small</span></div>
      <div>{svg(s_fn(), 16, INK)}<span class="cap">16 small</span></div></div></td>
    <td class="cell white zoom"><img src="../raster9/{slug}s-16-{PAPER.lstrip('#')}.png" width="140" height="140"><div class="cap">16 light x8.75</div></td>
    <td class="cell ink zoom"><img src="../raster9/{slug}s-16-{INK.lstrip('#')}.png" width="140" height="140"><div class="cap d">16 dark x8.75</div></td>
  </tr>""")

    applied = f"""<!doctype html><html><head><meta charset="utf-8"><style>
{face}
.wm{{font-family:'Bricolage';font-weight:800;font-size:42px;letter-spacing:-0.02em;color:{INK};line-height:1}}
.wm.light{{color:{PAPER}}} .pd{{color:{EMERALD}}}
body{{margin:0;padding:16px;background:#fff;font-family:monospace;font-size:12px}}
h1{{font-size:15px}} table{{border-collapse:collapse}}
td{{border:1px solid #bbb;padding:8px;vertical-align:middle;text-align:center}}
.label{{width:220px;text-align:left;font-size:11px;vertical-align:top}}
.ink{{background:{INK}}} .paper{{background:{PAPER}}} .white{{background:#fff}}
.lk{{display:flex;align-items:center;gap:14px}}
.sizes{{display:flex;gap:14px;align-items:flex-end;justify-content:center}}
.sizes>div{{display:flex;flex-direction:column;align-items:center;gap:4px}}
.zoom img{{image-rendering:pixelated}}
.cap{{font-size:10px;color:#555}} .cap.d{{color:#999}}
</style></head><body>
<h1>R7-4 differentiation round, 2026-10-29 - base vs plinth vs canopy vs door seam. Selection evidence only.</h1>
<table><tbody>{''.join(rows)}</tbody></table></body></html>"""
    apath = SHEETS / "round9-applied.html"
    apath.write_text(applied, encoding="utf-8")

    # construction for D2 (the most structural differentiator)
    scale, ox, oy = 11.0, 50, 60
    ann = "".join([
        dim(ox + 1.5 * scale, oy - 6, ox + 30.5 * scale, oy - 6, "eaves 29.0", (0, -4)),
        dim(ox + 31.5 * scale, oy + 1.4 * scale, ox + 31.5 * scale, oy + 28 * scale, "27.6 tall", (10, 0)),
        dim(ox + 7 * scale, oy + 30.6 * scale, ox + 25 * scale, oy + 30.6 * scale, "cap top 18", (0, 4)),
        dim(ox + 1.5 * scale, oy + 34.2 * scale, ox + 30.5 * scale, oy + 34.2 * scale, "cap eaves 29", (0, 4)),
        dim(ox + 2 * scale, oy + 12 * scale, ox + 4 * scale, oy + 12 * scale, "gap", (0, -2)),
        dim(ox + 15 * scale, oy + 21 * scale, ox + 17 * scale, oy + 21 * scale, "2.2", (0, -2)),
    ])
    construction = f"""<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:0;padding:18px;background:#fff;font-family:monospace;color:#111}}
h1{{font-size:16px}} .row{{display:flex;gap:26px;align-items:flex-start}}
.box{{border:1px solid #ddd;padding:8px}} .note{{font-size:11px;line-height:1.55;color:#333;max-width:470px}}
</style></head><body>
<h1>D2 Canopy - construction (32-unit grid, 11x)</h1>
<div class="row"><div class="box">
<svg width="{32*scale+150}" height="{32*scale+90}" viewBox="0 0 {32*scale+150} {32*scale+90}" xmlns="http://www.w3.org/2000/svg" style="color:{INK}">
  <g transform="translate({ox} {oy}) scale({scale})">
    <path fill="currentColor" d="M7 1.4 H25 L30.5 4.6 H1.5 Z"/>
    <path fill-rule="evenodd" fill="currentColor" d="{ARCH} {hole(11.5, 17.5, 3.4)} {hole(20.5, 17.5, 3.4)}"/>
    <g stroke="#e5e7eb" stroke-width="0.12">
      <line x1="0" y1="16" x2="32" y2="16"/><line x1="16" y1="0" x2="16" y2="32"/>
    </g>
  </g>
  {ann}
</svg></div>
<div class="note">
<b>D2 Canopy.</b> A trapezoid cap (top 7..25 @ y1.4, eaves 1.5..30.5 @ y4.6, h3.2, overhang 2.5
beyond the arch) sits over the liked R7-4 front. The arch keeps its r12 crown, which tucks 0.6 under
the cap; the two residents stay r3.4 knocked out at (11.5,17.5) and (20.5,17.5), 2.2 apart, 1.5 above
the cap line and 7.1 above the floor. The cap is the hutch roof: it reads as a structure with a roof
rather than a face, and it is the one part a stock mask/ghost silhouette cannot copy.
<br><br><b>Small master (16-24px):</b> cap 5..27 @ y0.8, eaves 1..31 @ y4.4; arch widened to
3..29 with r13 crown; residents r3.8 at 11.2/17.4 and 20.8/17.4 (2.0 apart, 4.4 to the sides).
The cap is deliberately wider at small size so the roof line survives the 16px render.
<br><br><b>Colour:</b> single-colour mark; residents are real holes, so the background always shows
through and no second colour is required. Emerald is reserved for the wordmark period and UI accent.
</div></div></body></html>"""
    cpath = SHEETS / "round9-construction.html"
    cpath.write_text(construction, encoding="utf-8")

    with sync_playwright() as p:
        b = p.chromium.launch()
        for name, path in (("round9-applied", apath), ("round9-construction", cpath)):
            page = b.new_page(viewport={"width": 1500, "height": 900})
            page.goto(path.as_uri(), wait_until="load"); page.wait_for_timeout(600)
            page.screenshot(path=str(SHEETS / (name + ".png")), full_page=True)
            page.close()
        b.close()
    print("wrote round9-applied.png, round9-construction.png")

if __name__ == "__main__":
    main()
