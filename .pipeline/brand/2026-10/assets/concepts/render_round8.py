#!/usr/bin/env python3
"""Round 8: ONE precise direction, drawn atomically (hutch front, two size tiers).

Design brief (D43-D48): a constructed hutch-front mark, not a stock primitive.
Geometry is specified on the 32-unit grid; master and small master are separate
drawings (not scaled), and every number below is the drawing.

  MASTER (used >=32px)                      SMALL (16-24px, redrawn)
  x: 2.2..29.8  (w 27.6)                    x: 1.0..31.0  (w 30.0)
  y: 2.5..30.8  (h 28.3)                    y: 1.5..31.2  (h 29.7)
  roof  : trapezoid, top 6.5..25.5 @ y2.5,   roof  : trapezoid, top 4.5..27.5 @ y1.5,
          eaves 2.2..29.8 @ y6.4, h 3.9             eaves 1.0..31.0 @ y5.4, h 3.9
  body  : 5..27 x 6.2..29, r 2.6             body  : 3.5..28.5 x 5.0..29.2, r 2.4
  door  : 7.5..24.5, springing y19,          door  : 8.5..23.5, springing y18.5,
          crown r 8.5 (apex y10.5)                  crown r 7.5 (apex y11.0)
  residents: two, r 3.0 @ (12,23.8),(20,23.8) resident: one, r 4.1 @ (16,22.9)
  step  : 6.5..25.5 x 28.2..30.8, r 1.2      step  : 5.5..26.5 x 28.6..31.2, r 1.3
  gaps  : residents 2.0 apart, 1.5 to door   gaps  : resident 3.4 to door sides,
          sides, 2.2 to floor                      2.2 to floor, 7.8 to crown

Colour: enclosure = currentColor; residents = emerald-400 (two-tone) or
currentColor (mono). The doorway is a real hole, so the mark never needs a
background colour. Selection evidence only.
"""
import pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent
FONTS, SHEETS, RASTER = ROOT / "fonts", ROOT / "sheets", ROOT / "raster8"
INK, PAPER, EMERALD = "#09090b", "#ededf0", "#34d399"

ROOF_M = "M6.5 2.5 H25.5 L29.8 6.4 H2.2 Z"
BODY_M = ("M7.6 6.2 H24.4 A2.6 2.6 0 0 1 27 8.8 V26.4 A2.6 2.6 0 0 1 24.4 29 "
          "H7.6 A2.6 2.6 0 0 1 5 26.4 V8.8 A2.6 2.6 0 0 1 7.6 6.2 Z")
DOOR_M = "M7.5 29 V19 A8.5 8.5 0 0 1 24.5 19 V29 Z"
STEP_M = '<rect x="6.5" y="28.2" width="19" height="2.6" rx="1.2" fill="currentColor"/>'

ROOF_S = "M4.5 1.5 H27.5 L31 5.4 H1 Z"
BODY_S = ("M5.9 5 H26.1 A2.4 2.4 0 0 1 28.5 7.4 V26.8 A2.4 2.4 0 0 1 26.1 29.2 "
          "H5.9 A2.4 2.4 0 0 1 3.5 26.8 V7.4 A2.4 2.4 0 0 1 5.9 5 Z")
DOOR_S = "M8.5 29.2 V18.5 A7.5 7.5 0 0 1 23.5 18.5 V29.2 Z"
STEP_S = '<rect x="5.5" y="28.6" width="21" height="2.6" rx="1.3" fill="currentColor"/>'

def dot(cx, cy, r, two_tone=True):
    if two_tone:
        return f'<circle class="dotc" cx="{cx}" cy="{cy}" r="{r}"/>'
    return f'<circle fill="currentColor" cx="{cx}" cy="{cy}" r="{r}"/>'

def master(two_tone=True):
    return ('<path fill="currentColor" d="' + ROOF_M + '"/>'
            + '<path fill-rule="evenodd" fill="currentColor" d="' + BODY_M + ' ' + DOOR_M + '"/>'
            + STEP_M + dot(12, 23.8, 3.0, two_tone) + dot(20, 23.8, 3.0, two_tone))

def small(two_tone=True):
    return ('<path fill="currentColor" d="' + ROOF_S + '"/>'
            + '<path fill-rule="evenodd" fill="currentColor" d="' + BODY_S + ' ' + DOOR_S + '"/>'
            + STEP_S + dot(16, 22.9, 4.1, two_tone))

def svg(b, size, color):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="{size}" '
            f'height="{size}" style="color:{color};display:block">{b}</svg>')

def raster(browser, slug, b, bg, fg, px=16):
    ctx = browser.new_context(viewport={"width": px, "height": px}, device_scale_factor=1)
    page = ctx.new_page()
    page.set_content(f'<!doctype html><head><style>.dotc{{fill:{EMERALD}}}</style></head>'
                     f'<body style="margin:0;background:{bg}">'
                     f'<div style="width:{px}px;height:{px}px;color:{fg}">{svg(b,px,fg)}</div></body>',
                     wait_until="load")
    page.screenshot(path=str(RASTER / f"{slug}-{px}-{bg.lstrip('#')}.png"),
                    clip={"x":0,"y":0,"width":px,"height":px})
    ctx.close()

def dim(x1, y1, x2, y2, label, off=(0, -6)):
    mx, my = (x1 + x2) / 2 + off[0], (y1 + y2) / 2 + off[1]
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#c026d3" stroke-width="0.6"/>'
            f'<line x1="{x1}" y1="{y1-1.6}" x2="{x1}" y2="{y1+1.6}" stroke="#c026d3" stroke-width="0.6"/>'
            f'<line x1="{x2}" y1="{y2-1.6}" x2="{x2}" y2="{y2+1.6}" stroke="#c026d3" stroke-width="0.6"/>'
            f'<text x="{mx}" y="{my}" font-size="4.6" fill="#86198f" text-anchor="middle" '
            f'font-family="monospace">{label}</text>')

def main():
    RASTER.mkdir(parents=True, exist_ok=True); SHEETS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        for bg, fg in ((PAPER, INK), (INK, PAPER)):
            raster(b, "master", master(True), bg, fg, 16)
            raster(b, "small", small(True), bg, fg, 16)
            raster(b, "mono", small(False), bg, fg, 16)
        raster(b, "master32", master(True), PAPER, INK, 32)
        b.close()

    face = ('@font-face{font-family:"Bricolage";src:url("' +
            (FONTS / "BricolageGrotesque-var.ttf").as_uri() +
            '") format("truetype");font-weight:1 1000;font-display:block}')

    # ---------- sheet 1: construction -------------------------------------
    scale = 11.0
    ox, oy = 40, 30
    def P(x, y):
        return (ox + x * scale, oy + y * scale)
    m = master(True)
    annotations = "".join([
        dim(ox + 2.2 * scale, oy + 31.6 * scale, ox + 29.8 * scale, oy + 31.6 * scale, "27.6 overall", (0, 5)),
        dim(ox + 31.4 * scale, oy + 2.5 * scale, ox + 31.4 * scale, oy + 30.8 * scale, "28.3 overall", (9, 0)),
        dim(ox + 2.2 * scale, oy + 0.6 * scale, ox + 29.8 * scale, oy + 0.6 * scale, "eaves 27.6 h3.9", (0, -3)),
        dim(ox + 5 * scale, oy + 8.2 * scale, ox + 5 * scale, oy + 29 * scale, "body 22x22.8", (-14, 0)),
        dim(ox + 7.5 * scale, oy + 33.0 * scale, ox + 24.5 * scale, oy + 33.0 * scale, "door 17", (0, 3)),
        dim(ox + 28.5 * scale, oy + 19 * scale, ox + 28.5 * scale, oy + 29 * scale, "r8.5", (8, 0)),
        dim(ox + 8.5 * scale, oy + 23.8 * scale, ox + 11.0 * scale, oy + 23.8 * scale, "1.5", (0, -2)),
        dim(ox + 15.0 * scale, oy + 21.6 * scale, ox + 17.0 * scale, oy + 21.6 * scale, "2.0", (0, -2)),
        dim(ox + 11.4 * scale, oy + 26.8 * scale, ox + 11.4 * scale, oy + 29 * scale, "2.2", (-4, 0)),
    ])
    construction = f"""<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:0;padding:18px;background:#fff;font-family:monospace;color:#111}}
h1{{font-size:16px}} h2{{font-size:12px;margin:10px 0 4px}}
.row{{display:flex;gap:28px;align-items:flex-start}}
.box{{border:1px solid #ddd;padding:8px}}
.note{{font-size:11px;color:#444;max-width:520px;line-height:1.5}}
.rule{{height:1px;background:#c026d3;margin:3px 0}}
</style></head><body>
<h1>Hutch front - master construction (32-unit grid, 11x)</h1>
<div class="row">
  <div class="box"><svg width="{32*scale+80}" height="{32*scale+60}" viewBox="0 0 {32*scale+80} {32*scale+60}"
    xmlns="http://www.w3.org/2000/svg" style="color:{INK}">
    <g transform="translate({ox} {oy}) scale({scale})">
      <path fill="currentColor" d="{ROOF_M}"/>
      <path fill-rule="evenodd" fill="currentColor" d="{BODY_M} {DOOR_M}"/>
      {STEP_M}
      <circle class="dotc" cx="12" cy="23.8" r="3"/><circle class="dotc" cx="16" cy="23.8" r="0"/>
      <circle class="dotc" cx="20" cy="23.8" r="3"/>
      <g stroke="#e5e7eb" stroke-width="0.12">
        <line x1="0" y1="0" x2="32" y2="0"/><line x1="0" y1="0" x2="0" y2="32"/>
        <line x1="16" y1="0" x2="16" y2="32"/><line x1="0" y1="16" x2="32" y2="16"/>
      </g>
    </g>
    {annotations}
  </svg></div>
  <div class="note">
    <b>Master (>=32px)</b><br>
    27.6 x 28.3 units; roof trapezoid h3.9 with 2.8 overhang; body 22 x 22.8 r2.6; doorway 17 wide,
    springing 10 from the floor, crown r8.5; two residents r3.0, 2.0 apart, 1.5 from the door sides,
    2.2 above the floor; threshold step 19 wide, 2.6 high, r1.2.<br><br>
    <b>Small master (16-24px)</b><br>
    30.0 x 29.7 units; roof 30 wide h3.9; body 25 x 24.2 r2.4; doorway 15 wide, crown r7.5;
    one resident r4.1, 3.4 from the door sides, 2.2 above the floor; step 21 wide, 2.6 high.<br><br>
    The small mark is a redraw, not a scale: the doorway widens 2 units, the door crown rises, the
    residents collapse from two to one, and the roof overhang grows so the silhouette reads at 16 px.
    <div class="rule"></div>
    Colour: enclosure = currentColor; residents = emerald-400. The doorway is a real hole, so the mark
    never needs a background colour; mono uses currentColor residents on the hole.
  </div>
</div></body></html>"""
    cpath = SHEETS / "round8-construction.html"
    cpath.write_text(construction, encoding="utf-8")

    # ---------- sheet 2: applied ------------------------------------------
    rows = f"""
  <tr>
    <td class="label">MASTER (>=32px)<br>roof / body / door / 2 residents / step</td>
    <td class="cell ink"><div class="lk">{svg(master(True), 56, PAPER)}<span class="wm light">hutch<span class="pd">.</span></span></div></td>
    <td class="cell paper"><div class="lk">{svg(master(True), 56, INK)}<span class="wm">hutch<span class="pd">.</span></span></div></td>
    <td class="cell white">{svg(master(True), 180, INK)}<div class="cap">on paper</div></td>
    <td class="cell ink">{svg(master(True), 180, PAPER)}<div class="cap d">on ink</div></td>
    <td class="cell white"><div class="sizes">
      <div>{svg(master(True), 64, INK)}<span class="cap">64</span></div>
      <div>{svg(master(True), 32, INK)}<span class="cap">32</span></div>
      <div>{svg(master(False), 32, INK)}<span class="cap">32 mono</span></div></div></td>
    <td class="cell white zoom"><img src="../raster8/master32-32-{PAPER.lstrip('#')}.png" width="160" height="160"><div class="cap">32 x5</div></td>
  </tr>
  <tr>
    <td class="label">SMALL (16-24px)<br>roof / body / door / 1 resident / step</td>
    <td class="cell ink"><div class="lk">{svg(small(True), 56, PAPER)}<span class="wm light">hutch<span class="pd">.</span></span></div></td>
    <td class="cell paper"><div class="lk">{svg(small(True), 56, INK)}<span class="wm">hutch<span class="pd">.</span></span></div></td>
    <td class="cell white">{svg(small(True), 180, INK)}<div class="cap">on paper</div></td>
    <td class="cell ink">{svg(small(True), 180, PAPER)}<div class="cap d">on ink</div></td>
    <td class="cell white"><div class="sizes">
      <div>{svg(small(True), 48, INK)}<span class="cap">48</span></div>
      <div>{svg(small(True), 24, INK)}<span class="cap">24</span></div>
      <div>{svg(small(False), 24, INK)}<span class="cap">24 mono</span></div></div></td>
    <td class="cell white zoom"><img src="../raster8/small-16-{PAPER.lstrip('#')}.png" width="160" height="160"><div class="cap">16 x10 light</div></td>
  </tr>
  <tr>
    <td class="label">SMALL, 16px on ink + mono</td>
    <td class="cell ink zoom"><img src="../raster8/small-16-{INK.lstrip('#')}.png" width="160" height="160"><div class="cap d">16 x10 dark</div></td>
    <td class="cell paper zoom"><img src="../raster8/mono-16-{PAPER.lstrip('#')}.png" width="160" height="160"><div class="cap">16 mono x10</div></td>
    <td class="cell paper">{svg(small(False), 96, INK)}<div class="cap">mono, paper</div></td>
    <td class="cell ink">{svg(small(False), 96, PAPER)}<div class="cap d">mono, ink</div></td>
    <td class="cell white">{svg(small(True), 20, INK)}<div class="cap">20</div></td>
    <td class="cell white">{svg(small(True), 16, INK)}<div class="cap">16 actual</div></td>
  </tr>"""
    applied = f"""<!doctype html><html><head><meta charset="utf-8"><style>
.dotc{{fill:{EMERALD}}}
{face}
.wm{{font-family:'Bricolage';font-weight:800;font-size:42px;letter-spacing:-0.02em;color:{INK};line-height:1}}
.wm.light{{color:{PAPER}}} .pd{{color:{EMERALD}}}
body{{margin:0;padding:16px;background:#fff;font-family:monospace;font-size:12px}}
h1{{font-size:15px}} table{{border-collapse:collapse}}
td{{border:1px solid #bbb;padding:8px;vertical-align:middle;text-align:center}}
.label{{width:240px;text-align:left;font-size:11px;vertical-align:top}}
.ink{{background:{INK}}} .paper{{background:{PAPER}}} .white{{background:#fff}}
.lk{{display:flex;align-items:center;gap:14px}}
.sizes{{display:flex;gap:14px;align-items:flex-end;justify-content:center}}
.sizes>div{{display:flex;flex-direction:column;align-items:center;gap:4px}}
.zoom img{{image-rendering:pixelated}}
.cap{{font-size:10px;color:#555}} .cap.d{{color:#999}}
</style></head><body>
<h1>Hutch front - applied tests (master and small master), 2026-10-29. Selection evidence only.</h1>
<table><tbody>{rows}</tbody></table></body></html>"""
    apath = SHEETS / "round8-applied.html"
    apath.write_text(applied, encoding="utf-8")

    with sync_playwright() as p:
        b = p.chromium.launch()
        for name, path in (("round8-construction", cpath), ("round8-applied", apath)):
            page = b.new_page(viewport={"width": 1500, "height": 900})
            page.goto(path.as_uri(), wait_until="load"); page.wait_for_timeout(700)
            page.screenshot(path=str(SHEETS / (name + ".png")), full_page=True)
            page.close()
        b.close()
    print("wrote round8-construction.png, round8-applied.png")

if __name__ == "__main__":
    main()
