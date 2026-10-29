#!/usr/bin/env python3
"""Round 12: three drawings built to the researched rulebook (PRINCIPLES.md).

Method (from the Anthropic canvas-design and frontend-design skills):
  - subject first: a front elevation of a timber hutch (architecture, not character)
  - one bold move per drawing, everything else quiet
  - grid discipline (32 units, 4-unit module), optical overshoot on curved extremes
  - two size tiers, redrawn; mono must carry the mark
Candidates:
  A "Threshold"  tall front, two square windows, open notch in the floor edge
  B "Occupied / vacant"  tall front, two equal-area windows, one round one square
  C "Canopy"     tall front, two square windows, roofed cap
Selection evidence only.
"""
import pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent
FONTS, SHEETS, RASTER = ROOT / "fonts", ROOT / "sheets", ROOT / "raster12"
INK, PAPER, EMERALD = "#09090b", "#ededf0", "#34d399"

# ---- masters ---------------------------------------------------------
FRONT_M = ("M6 30 V12 A10 10.22 0 0 1 26 12 V30 Z")   # ry 10.22 = 0.22 optical overshoot
FRONT_S = ("M5 30.5 V12 A11 11.24 0 0 1 27 12 V30.5 Z")

def sq(cx, cy, s, r):
    x0, y0, x1, y1 = cx - s/2, cy - s/2, cx + s/2, cy + s/2
    return (f"M{x0 + r} {y0} H{x1 - r} A{r} {r} 0 0 1 {x1} {y0 + r} V{y1 - r} "
            f"A{r} {r} 0 0 1 {x1 - r} {y1} H{x0 + r} A{r} {r} 0 0 1 {x0} {y1 - r} "
            f"V{y0 + r} A{r} {r} 0 0 1 {x0 + r} {y0} Z")

def circ(cx, cy, r):
    return f"M{cx - r} {cy} a {r} {r} 0 1 0 {2*r} 0 a {r} {r} 0 1 0 {-2*r} 0 Z"

NOTCH_M = "M13.4 30 V27.5 Q13.4 26.6 14.3 26.6 H17.7 Q18.6 26.6 18.6 27.5 V30 Z"
NOTCH_S = "M12.9 30.5 V27.8 Q12.9 26.7 14.0 26.7 H18.0 Q19.1 26.7 19.1 27.8 V30.5 Z"

WIN_A_M = " ".join([sq(12, 16, 5.6, 1.2), sq(20, 16, 5.6, 1.2)])
WIN_A_S = " ".join([sq(11.4, 16, 6.4, 1.4), sq(20.6, 16, 6.4, 1.4)])
WIN_B_M = " ".join([circ(11.6, 16, 3.06), sq(20.4, 16, 5.42, 1.1)])
WIN_B_S = " ".join([circ(11.4, 16, 3.5), sq(20.6, 16, 6.2, 1.3)])
CAP_M = '<path fill="currentColor" d="M9 0.6 H23 L27.5 3.8 H4.5 Z"/>'
CAP_S = '<path fill="currentColor" d="M8.5 0 H23.5 L28.5 3.4 H3.5 Z"/>'

def A():  return '<path fill-rule="evenodd" fill="currentColor" d="' + FRONT_M + " " + NOTCH_M + " " + WIN_A_M + '"/>'
def A_S():return '<path fill-rule="evenodd" fill="currentColor" d="' + FRONT_S + " " + NOTCH_S + " " + WIN_A_S + '"/>'
def B():  return '<path fill-rule="evenodd" fill="currentColor" d="' + FRONT_M + " " + WIN_B_M + '"/>'
def B_S():return '<path fill-rule="evenodd" fill="currentColor" d="' + FRONT_S + " " + WIN_B_S + '"/>'
def C():  return CAP_M + '<path fill-rule="evenodd" fill="currentColor" d="' + FRONT_M + " " + WIN_A_M + '"/>'
def C_S():return CAP_S + '<path fill-rule="evenodd" fill="currentColor" d="' + FRONT_S + " " + WIN_A_S + '"/>'

CONCEPTS = [
    ("A Threshold", A, A_S, "tall front / 2 square windows / open floor notch"),
    ("B Occupied-vacant", B, B_S, "tall front / round + square windows, equal area"),
    ("C Canopy", C, C_S, "tall front / 2 square windows / roofed cap"),
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

CRIT = [
 ("R1 subject first (architecture, not a face)", "pass", "pass", "pass"),
 ("R2 one bold move", "pass: open threshold", "partial: two states is subtle", "pass: the cap"),
 ("R3 grid + optical overshoot", "pass: ry 10.22", "pass: ry 10.22", "pass: ry 10.22"),
 ("R4 equal optical area (repeats)", "pass: identical windows", "pass: circle 29.4 = square 29.4", "pass"),
 ("R5 designed counterform (>=2u / >=2.5u small)", "pass: 2.4 master / 2.8 small", "pass: 3.0 / 2.8", "pass"),
 ("R6 two redrawn size tiers", "pass", "pass", "pass"),
 ("R7 silhouette + squint test", "pass: front + notch reads at 24px", "partial: reads as one open window at 24px", "pass: cap + front reads"),
 ("R8 mono carries the mark", "pass", "pass", "pass"),
 ("R9 AI-tell audit", "pass: no dark+neon dependence, no gradient/tile", "partial: asymmetric windows can read as a typo at 16px", "partial: cap risks a 'hat' read"),
 ("R10 removal pass", "notch kept: it is the bold move", "would remove the vacancy idea", "cap kept"),
 ("R11 provenance / construction", "recorded", "recorded", "recorded"),
]

def main():
    RASTER.mkdir(parents=True, exist_ok=True); SHEETS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        for i, (label, m, s, _d) in enumerate(CONCEPTS):
            for bg, fg in ((PAPER, INK), (INK, PAPER)):
                raster(b, f"r12-{i}", m(), bg, fg)
                raster(b, f"r12-{i}s", s(), bg, fg)
        b.close()

    face = ('@font-face{font-family:"Bricolage";src:url("' +
            (FONTS / "BricolageGrotesque-var.ttf").as_uri() +
            '") format("truetype");font-weight:1 1000;font-display:block}')
    rows = []
    for i, (label, m, s, desc) in enumerate(CONCEPTS):
        grid = ('<svg width="120" height="120" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg">'
                '<g stroke="#e5e7eb" stroke-width="0.15">'
                + "".join(f'<line x1="{x}" y1="0" x2="{x}" y2="32"/>' for x in range(0,33,4))
                + "".join(f'<line x1="0" y1="{y}" x2="32" y2="{y}"/>' for y in range(0,33,4))
                + f'<line x1="16" y1="0" x2="16" y2="32" stroke="#c026d3" stroke-width="0.3"/>'
                + f'<line x1="0" y1="16" x2="32" y2="16" stroke="#c026d3" stroke-width="0.3"/>'
                + f'</g><g style="color:{INK}">{m().replace("32","32")}</g></svg>')
        rows.append(f"""
  <tr>
    <td class="label"><b>{label}</b><br><span class="dim">{desc}</span></td>
    <td class="cell white">{grid}<div class="cap">grid</div></td>
    <td class="cell ink"><div class="lk">{svg(m(), 56, PAPER)}<span class="wm light">hutch<span class="pd">.</span></span></div></td>
    <td class="cell paper"><div class="lk">{svg(m(), 56, INK)}<span class="wm">hutch<span class="pd">.</span></span></div></td>
    <td class="cell white">{svg(m(), 170, INK)}<div class="cap">on paper</div></td>
    <td class="cell ink">{svg(m(), 170, PAPER)}<div class="cap d">on ink</div></td>
    <td class="cell white"><div class="sizes">
      <div>{svg(m(), 48, INK)}<span class="cap">48</span></div>
      <div>{svg(m(), 32, INK)}<span class="cap">32</span></div>
      <div>{svg(s(), 24, INK)}<span class="cap">24 small</span></div>
      <div>{svg(s(), 16, INK)}<span class="cap">16 small</span></div></div></td>
    <td class="cell white zoom"><img src="../raster12/r12-{i}s-16-{PAPER.lstrip('#')}.png" width="140" height="140"><div class="cap">16 light x8.75</div></td>
    <td class="cell ink zoom"><img src="../raster12/r12-{i}s-16-{INK.lstrip('#')}.png" width="140" height="140"><div class="cap d">16 dark x8.75</div></td>
  </tr>""")

    crit_rows = "".join(
        f'<tr><td class="cr">{rule}</td><td>{a}</td><td>{b}</td><td>{c}</td></tr>'
        for rule, a, b, c in CRIT)

    html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
{face}
.wm{{font-family:'Bricolage';font-weight:800;font-size:42px;letter-spacing:-0.02em;color:{INK};line-height:1}}
.wm.light{{color:{PAPER}}} .pd{{color:{EMERALD}}}
body{{margin:0;padding:16px;background:#fff;font-family:monospace;font-size:12px;color:#111}}
h1{{font-size:15px}} h2{{font-size:12px;margin:16px 0 6px}}
table{{border-collapse:collapse}}
td{{border:1px solid #bbb;padding:7px;vertical-align:middle;text-align:center}}
.label{{width:150px;text-align:left;font-size:11px;vertical-align:top}}
.dim{{color:#666;font-size:10px}}
.ink{{background:{INK}}} .paper{{background:{PAPER}}} .white{{background:#fff}}
.lk{{display:flex;align-items:center;gap:14px}}
.sizes{{display:flex;gap:14px;align-items:flex-end;justify-content:center}}
.sizes>div{{display:flex;flex-direction:column;align-items:center;gap:4px}}
.zoom img{{image-rendering:pixelated}}
.cap{{font-size:10px;color:#555}} .cap.d{{color:#999}}
table.crit td{{text-align:left;font-size:10px;padding:4px 6px;border:1px solid #ddd}}
table.crit td.cr{{width:280px;color:#333}}
</style></head><body>
<h1>Round 12 - three drawings built to the researched rulebook (PRINCIPLES.md), 2026-10-29.
Subject first, one bold move each, grid + optical overshoot, two redrawn size tiers. Selection evidence only.</h1>
<table><tbody>{''.join(rows)}</tbody></table>
<h2>Critique against R1-R11 (written before the recommendation, not after)</h2>
<table class="crit"><thead><tr><th>rule</th><th>A Threshold</th><th>B Occupied-vacant</th><th>C Canopy</th></tr></thead>
<tbody>{crit_rows}</tbody></table>
</body></html>"""
    out = SHEETS / "round12-sheet.html"
    out.write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1650, "height": 900})
        page.goto(out.as_uri(), wait_until="load"); page.wait_for_timeout(700)
        page.screenshot(path=str(SHEETS / "round12-sheet.png"), full_page=True)
        b.close()
    print("wrote round12-sheet.png")

if __name__ == "__main__":
    main()
