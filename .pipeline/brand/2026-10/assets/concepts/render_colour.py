#!/usr/bin/env python3
"""Colour system evidence: WCAG contrast audit, CVD simulation, mark colourways."""
import pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent
SHEETS, FONTS = ROOT / "sheets", ROOT / "fonts"
raster_dir = ROOT / "raster_colour"; raster_dir.mkdir(exist_ok=True)
SHEETS.mkdir(exist_ok=True)

def lin(c):
    c = c / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def lum(hexrgb):
    r, g, b = int(hexrgb[1:3], 16), int(hexrgb[3:5], 16), int(hexrgb[5:7], 16)
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)

def ratio(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)

INK, INK9, PANEL, WELL = "#09090b", "#0f0f12", "#16161a", "#0b0b0e"
PAPER, MIST, FAINT = "#ededf0", "#a3a3ae", "#8e8e99"
EM3, EM4, EM6 = "#6ee7b7", "#34d399", "#10b981"
EMINK, EMDEEP = "#052e21", "#073d31"
BLUE, AMBER, RED = "#60a5fa", "#fbbf24", "#f87171"
PROPOSED_EM7, PROPOSED_EM8 = "#047857", "#065f46"

def composite(fg_rgba, bg_hex):
    r, g, b, a = fg_rgba
    br, bg_, bb = int(bg_hex[1:3],16), int(bg_hex[3:5],16), int(bg_hex[5:7],16)
    return "#%02x%02x%02x" % (round(r*a+br*(1-a)), round(g*a+bg_*(1-a)), round(b*a+bb*(1-a)))

PAIRS = [
    ("paper on ink-950", PAPER, INK),
    ("paper on ink-900", PAPER, INK9),
    ("mist on ink-950", MIST, INK),
    ("faint on ink-950", FAINT, INK),
    ("faint on panel-800", FAINT, PANEL),
    ("emerald-400 on ink-950", EM4, INK),
    ("emerald-300 on ink-950", EM3, INK),
    ("emerald-600 on ink-950", EM6, INK),
    ("emerald-400 on paper", EM4, PAPER),
    ("emerald-600 on paper", EM6, PAPER),
    ("emerald-700(#047857) on paper", PROPOSED_EM7, PAPER),
    ("emerald-800(#065f46) on paper", PROPOSED_EM8, PAPER),
    ("emerald-ink on emerald-400", EMINK, EM4),
    ("emerald-ink on emerald-600", EMINK, EM6),
    ("paper on emerald-600", PAPER, EM6),
    ("info blue on ink-950", BLUE, INK),
    ("warning amber on ink-950", AMBER, INK),
    ("danger red on ink-950", RED, INK),
    ("danger red on paper", RED, PAPER),
    ("info blue on paper", BLUE, PAPER),
    ("warning amber on paper", AMBER, PAPER),
    ("border a07 on ink-950", composite((255,255,255,0.07), INK), INK),
    ("border a14 on ink-950", composite((255,255,255,0.14), INK), INK),
    ("border a38 on ink-950", composite((255,255,255,0.38), INK), INK),
]
print("=== WCAG 2.x contrast (computed 2026-10-29) ===")
for name, a, b in PAIRS:
    r = ratio(a, b)
    verdict = "PASS-AA-text" if r >= 4.5 else ("PASS-AA-large/nontext" if r >= 3.0 else "FAIL-3:1")
    print(f"{name:34s} {r:6.2f}:1  {verdict}")

print()
print("=== CIE-style CVD risk notes (computed deltas, not a substitute for simulation) ===")
def srgb_dist(a, b):
    la, lb = lum(a), lum(b)
    return abs(la - lb)
for name, a, b in [("emerald-400 vs danger red", EM4, RED), ("emerald-400 vs warning amber", EM4, AMBER),
                   ("emerald-400 vs info blue", EM4, BLUE), ("danger vs warning", RED, AMBER)]:
    print(f"{name:30s} luminance gap {srgb_dist(a,b):.3f}")

# ---------- render sheet ----------
CVDS = {
 "Protanopia": "0.567 0.433 0 0 0  0.558 0.442 0 0 0  0 0.242 0.758 0 0  0 0 0 1 0",
 "Deuteranopia": "0.625 0.375 0 0 0  0.7 0.3 0 0 0  0 0.3 0.7 0 0  0 0 0 1 0",
 "Tritanopia": "0.95 0.05 0 0 0  0 0.433 0.567 0 0  0 0.475 0.525 0 0  0 0 0 1 0",
}
filters = "".join(f'<filter id="{k}"><feColorMatrix type="matrix" values="{v}"/></filter>' for k, v in CVDS.items())

SW = [
 ("ink-950", INK, "app bg"), ("ink-900", INK9, "surface"), ("ink-800", PANEL, "panel"),
 ("ink-well", WELL, "well"), ("paper", PAPER, "text on ink"), ("mist", MIST, "text-2"),
 ("faint", FAINT, "text-3"), ("emerald-400", EM4, "brand / success (collision)"),
 ("emerald-300", EM3, "brand-strong"), ("emerald-600", EM6, "brand-deep"),
 ("emerald-ink", EMINK, "on-brand"), ("emerald-700 prop", PROPOSED_EM7, "brand on light"),
 ("emerald-800 prop", PROPOSED_EM8, "brand on light, deep"),
 ("info blue-400", BLUE, "semantic info / focus"), ("warning amber-400", AMBER, "semantic warning"),
 ("danger red-400", RED, "semantic danger"),
]
rows = []
for name, c, role in SW:
    rows.append(f"""<div class="sw"><div class="chip" style="background:{c}"></div>
      <div class="meta"><b>{name}</b><span>{c}</span><span>{role}</span></div></div>""")

sem_rows = []
for name, c in [("brand emerald-400", EM4), ("info blue-400", BLUE), ("warning amber-400", AMBER), ("danger red-400", RED)]:
    cells = "".join(f'<div class="cvdcell" style="filter:url(#{k})"><div class="cvddot" style="background:{c}"></div><span>{k}</span></div>'
                    for k in CVDS)
    sem_rows.append(f'<div class="cvdrow"><div class="cvdname">{name}</div>{cells}</div>')

mark_colourways = "".join([
 f'<div class="cw inkbg"><svg viewBox="0 0 32 32" width="72" height="72" style="color:{EM4}">'
 '<path fill-rule="evenodd" fill="currentColor" d="M9 3 H23 A6 6 0 0 1 29 9 V23 A6 6 0 0 1 23 29 H9 A6 6 0 0 1 3 23 V9 A6 6 0 0 1 9 3 Z M9 29 V22 A7 7 0 0 1 23 22 V29 Z"/></svg>'
 f'<span>emerald on ink</span></div>',
 f'<div class="cw whitebg"><svg viewBox="0 0 32 32" width="72" height="72" style="color:{INK}">'
 '<path fill-rule="evenodd" fill="currentColor" d="M9 3 H23 A6 6 0 0 1 29 9 V23 A6 6 0 0 1 23 29 H9 A6 6 0 0 1 3 23 V9 A6 6 0 0 1 9 3 Z M9 29 V22 A7 7 0 0 1 23 22 V29 Z"/></svg>'
 '<span>ink on paper</span></div>',
 f'<div class="cw emerbg"><svg viewBox="0 0 32 32" width="72" height="72" style="color:#052e21">'
 '<path fill-rule="evenodd" fill="currentColor" d="M9 3 H23 A6 6 0 0 1 29 9 V23 A6 6 0 0 1 23 29 H9 A6 6 0 0 1 3 23 V9 A6 6 0 0 1 9 3 Z M9 29 V22 A7 7 0 0 1 23 22 V29 Z"/></svg>'
 f'<span>emerald-ink on emerald-400 (7.70:1)</span></div>',
])

html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:0;padding:16px;background:#fff;font-family:monospace;font-size:12px;color:#111}}
h1{{font-size:16px}} h2{{font-size:13px;margin:18px 0 8px}}
.grid{{display:flex;flex-wrap:wrap;gap:10px}}
.sw{{width:150px;border:1px solid #ccc}}
.chip{{height:54px}}
.meta{{padding:6px;display:flex;flex-direction:column;gap:2px;font-size:10px}}
.meta b{{font-size:11px}}
.cvdrow{{display:flex;align-items:center;gap:8px;margin:6px 0}}
.cvdname{{width:150px}}
.cvdcell{{display:flex;flex-direction:column;align-items:center;gap:3px;font-size:9px;border:1px solid #ddd;padding:6px;width:110px}}
.cvddot{{width:40px;height:40px;border-radius:50%}}
.markrow{{display:flex;gap:16px;margin-top:8px}}
.cw{{display:flex;flex-direction:column;align-items:center;gap:6px;padding:14px;border:1px solid #ccc;font-size:10px}}
.inkbg{{background:{INK};color:#ccc}} .whitebg{{background:#fff;color:#333}} .emerbg{{background:{EM4};color:#052e21}}
</style></head><body>
<svg width="0" height="0" style="position:absolute">{filters}</svg>
<h1>Colour system evidence - computed contrast, CVD simulation, mark colourways (2026-10-29)</h1>
<h2>1. Palette and roles (values from website/tokens.json; two proposed light-surface emeralds marked "prop")</h2>
<div class="grid">{''.join(rows)}</div>
<h2>2. Semantic colours under simulated colour-vision deficiency (approximate matrices; not a diagnosis)</h2>
{''.join(sem_rows)}
<h2>3. Mark colourways (WB-A geometry)</h2>
<div class="markrow">{mark_colourways}</div>
</body></html>"""
out = SHEETS / "colour-sheet.html"
out.write_text(html, encoding="utf-8")
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1100, "height": 900})
    page.goto(out.as_uri(), wait_until="load"); page.wait_for_timeout(700)
    page.screenshot(path=str(SHEETS / "colour-sheet.png"), full_page=True)
    b.close()
print("wrote", SHEETS / "colour-sheet.png")
