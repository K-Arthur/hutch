#!/usr/bin/env python3
"""Round 10: refine the canopy differentiator (D2) for R7-4.

Base front (liked R7-4): arch M4 28 V15 A12 12 0 0 1 28 15 V28 Z with two
knocked-out residents r3.4 at (11.5,17.5) / (20.5,17.5).
Variants differ only in the furniture structure around that front:
  D2a canopy            cap h3.4, top 6.5..25.5 @ y1.2, eaves 1.5..30.5 @ y4.6
  D2b canopy + base     D2a plus a base board 2..30 @ y28..30.4, r1.2
  D2c deep-eaves canopy eaves 0.8..31.2, cap top 7..25 @ y1.4
Selection evidence only.
"""
import pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent
FONTS, SHEETS, RASTER = ROOT / "fonts", ROOT / "sheets", ROOT / "raster10"
INK, PAPER, EMERALD = "#09090b", "#ededf0", "#34d399"

ARCH = "M4 28 V15 A12 12 0 0 1 28 15 V28 Z"
ARCH_S = "M3 28.5 V15 A13 13 0 0 1 29 15 V28.5 Z"

def hole(cx, cy, r):
    return f"M{cx - r} {cy} a {r} {r} 0 1 0 {2 * r} 0 a {r} {r} 0 1 0 {-2 * r} 0 Z"

def front():
    return '<path fill-rule="evenodd" fill="currentColor" d="' + ARCH + " " + hole(11.5, 17.5, 3.4) + " " + hole(20.5, 17.5, 3.4) + '"/>'

def front_s():
    return '<path fill-rule="evenodd" fill="currentColor" d="' + ARCH_S + " " + hole(11.2, 17.4, 3.8) + " " + hole(20.8, 17.4, 3.8) + '"/>'

CAP_A  = '<path fill="currentColor" d="M6.5 1.2 H25.5 L30.5 4.6 H1.5 Z"/>'
CAP_AS = '<path fill="currentColor" d="M4.5 0.6 H27.5 L31 4.4 H1 Z"/>'
CAP_C  = '<path fill="currentColor" d="M7 1.4 H25 L31.2 4.8 H0.8 Z"/>'
BASE   = '<rect x="2" y="28" width="28" height="2.4" rx="1.2" fill="currentColor"/>'
BASE_S = '<rect x="1" y="28.5" width="30" height="2.6" rx="1.3" fill="currentColor"/>'

def D2a(): return CAP_A + front()
def D2a_s(): return CAP_AS + front_s()
def D2b(): return CAP_A + front() + BASE
def D2b_s(): return CAP_AS + front_s() + BASE_S
def D2c(): return CAP_C + front()
def D2c_s(): return CAP_C + front_s()

CONCEPTS = [
    ("R7-4 base (reference)", front, front_s),
    ("D2a Canopy (cap h3.4, overhang 2.5)", D2a, D2a_s),
    ("D2b Canopy + base board", D2b, D2b_s),
    ("D2c Deep-eaves canopy (overhang 3.2)", D2c, D2c_s),
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
                raster(b, f"r10-{i}", m(), bg, fg)
                raster(b, f"r10-{i}s", s(), bg, fg)
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
    <td class="cell white zoom"><img src="../raster10/r10-{i}s-16-{PAPER.lstrip('#')}.png" width="140" height="140"><div class="cap">16 light x8.75</div></td>
    <td class="cell ink zoom"><img src="../raster10/r10-{i}s-16-{INK.lstrip('#')}.png" width="140" height="140"><div class="cap d">16 dark x8.75</div></td>
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
<h1>R7-4 differentiation - canopy family, 2026-10-29. Selection evidence only; collision screen still owed.</h1>
<table><tbody>{''.join(rows)}</tbody></table></body></html>"""
    apath = SHEETS / "round10-applied.html"
    apath.write_text(applied, encoding="utf-8")

    scale, ox, oy = 11.0, 60, 70
    def L(x1, y1, x2, y2, label, tx, ty, anchor="middle"):
        return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#c026d3" stroke-width="0.5"/>'
                f'<line x1="{x1}" y1="{y1-1.4}" x2="{x1}" y2="{y1+1.4}" stroke="#c026d3" stroke-width="0.5"/>'
                f'<line x1="{x2}" y1="{y2-1.4}" x2="{x2}" y2="{y2+1.4}" stroke="#c026d3" stroke-width="0.5"/>'
                f'<text x="{tx}" y="{ty}" font-size="4.2" fill="#86198f" text-anchor="{anchor}" font-family="monospace">{label}</text>')
    ann = "".join([
        L(ox + 1.5*scale, oy + 34*scale, ox + 30.5*scale, oy + 34*scale, "eaves 29.0", ox + 16*scale, oy + 35.6*scale),
        L(ox + 6.5*scale, oy + 34*scale - 0.9*scale, ox + 25.5*scale, oy + 34*scale - 0.9*scale, "cap top 19.0", ox + 16*scale, oy + 33.2*scale),
        L(ox + 32.2*scale, oy + 1.2*scale, ox + 32.2*scale, oy + 28*scale, "27.6 tall", ox + 33.6*scale, oy + 15*scale, "start"),
        L(ox + 4*scale, oy + 31*scale, ox + 11.5*scale, oy + 31*scale, "2.5 overhang", ox + 4*scale, oy + 32.2*scale, "start"),
        L(ox + 9*scale, oy + 20.9*scale, ox + 9*scale, oy + 28*scale, "7.1", ox + 7.6*scale, oy + 25*scale, "end"),
        L(ox + 15*scale, oy + 14.1*scale, ox + 17*scale, oy + 14.1*scale, "2.2", ox + 16*scale, oy + 12.6*scale),
    ])
    construction = f"""<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:0;padding:18px;background:#fff;font-family:monospace;color:#111}}
h1{{font-size:16px}} .row{{display:flex;gap:24px;align-items:flex-start}}
.box{{border:1px solid #ddd;padding:8px}} .note{{font-size:11px;line-height:1.6;color:#333;max-width:480px}}
table.spec{{border-collapse:collapse;font-size:10px;margin-top:8px}} table.spec td{{border:1px solid #ddd;padding:3px 6px}}
</style></head><body>
<h1>D2a Canopy - construction, 32-unit grid at 11x</h1>
<div class="row"><div class="box">
<svg width="{32*scale+220}" height="{32*scale+120}" viewBox="0 0 {32*scale+220} {32*scale+120}" xmlns="http://www.w3.org/2000/svg" style="color:{INK}">
  <g transform="translate({ox} {oy}) scale({scale})">
    {CAP_A}
    <path fill-rule="evenodd" fill="currentColor" d="{ARCH} {hole(11.5,17.5,3.4)} {hole(20.5,17.5,3.4)}"/>
    <g stroke="#e5e7eb" stroke-width="0.1">
      <line x1="0" y1="16" x2="32" y2="16"/><line x1="16" y1="0" x2="16" y2="32"/>
      <line x1="0" y1="24" x2="32" y2="24"/><line x1="8" y1="0" x2="8" y2="32"/>
      <line x1="24" y1="0" x2="24" y2="32"/>
    </g>
  </g>
  {ann}
</svg></div>
<div class="note">
<b>D2a Canopy</b> keeps the liked R7-4 front and gives it the one thing a mask or ghost silhouette cannot have: a roof.
<table class="spec">
<tr><td>cap top edge</td><td>x 6.5 to 25.5, y 1.2</td></tr>
<tr><td>cap eaves</td><td>x 1.5 to 30.5, y 4.6 (h 3.4, overhang 2.5 per side)</td></tr>
<tr><td>front arch</td><td>M4 28 V15 A12 12 0 0 1 28 15 V28 Z (r12 crown, apex y3, tucks 1.6 under the cap)</td></tr>
<tr><td>residents</td><td>holes r3.4 at (11.5,17.5) and (20.5,17.5); 2.2 apart; 4.1 to the arch sides; 7.1 above the floor</td></tr>
<tr><td>small master</td><td>cap 4.5 to 27.5 @ y0.6, eaves 1 to 31 @ y4.4; arch 3 to 29 with r13 crown; holes r3.8 at 11.2/17.4 and 20.8/17.4</td></tr>
</table>
<br>
Why this is the differentiator, precisely: the cap is a separate, wider horizontal mass with a visible
underside line at the eaves. A mask, ghost, tombstone or app-tile silhouette has no projecting cap; the
cap also stops the "floating head" read because it grounds the front as a built structure. It survives
16px as a 1.7px roof band above the mass, which is the first thing the eye resolves at tab size.
<br><br>
Colour: single-colour mark. The residents are true holes, so background shows through and no second
colour is needed; emerald stays reserved for the wordmark period and the UI accent.
</div></div></body></html>"""
    cpath = SHEETS / "round10-construction.html"
    cpath.write_text(construction, encoding="utf-8")

    with sync_playwright() as p:
        b = p.chromium.launch()
        for name, path in (("round10-applied", apath), ("round10-construction", cpath)):
            page = b.new_page(viewport={"width": 1600, "height": 900})
            page.goto(path.as_uri(), wait_until="load"); page.wait_for_timeout(600)
            page.screenshot(path=str(SHEETS / (name + ".png")), full_page=True)
            page.close()
        b.close()
    print("wrote round10-applied.png, round10-construction.png")

if __name__ == "__main__":
    main()
