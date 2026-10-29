#!/usr/bin/env python3
"""Validation sheet: the candidate pack mocked on real surfaces."""
import pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent
SHEETS = ROOT.parent / "concepts" / "sheets"
INK, PAPER, EMERALD = "#09090b", "#ededf0", "#34d399"

def img(name, w, h=None, cls=""):
    h = h or w
    return f'<img src="../../front-candidate/{name}" width="{w}" height="{h}" class="{cls}" alt="">'

html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:0;padding:18px;background:#f4f4f5;font-family:monospace;font-size:12px;color:#111}}
h1{{font-size:15px}} h2{{font-size:11px;margin:16px 0 6px;color:#555}}
.sec{{background:#fff;border:1px solid #ddd;padding:14px;margin-bottom:14px}}
.row{{display:flex;gap:20px;align-items:center;flex-wrap:wrap}}
.cap{{font-size:10px;color:#666;margin-top:4px}}
.tab{{display:flex;align-items:center;gap:8px;background:#e7e7ea;padding:7px 12px;border-radius:9px 9px 0 0;
       box-shadow:0 1px 0 #d4d4d8;width:210px}}
.tab .t{{font-family:'Bricolage',monospace;font-size:12px;color:#3f3f46}}
.tab.dark{{background:#232327;box-shadow:0 1px 0 #333}}
.tab.dark .t{{color:#e4e4e7}}
.zoom16{{image-rendering:pixelated}}
.phone{{width:300px;background:linear-gradient(160deg,#1e1b4b,#0f172a);padding:22px;border-radius:26px;display:flex;flex-direction:column;align-items:center;gap:8px}}
.tile{{width:60px;height:60px;border-radius:13.5px;overflow:hidden;box-shadow:0 4px 12px rgba(0,0,0,.4)}}
.tile img{{display:block}}
.label{{font-family:'Bricolage';color:#e4e4e7;font-size:11px}}
.crop{{width:150px;height:150px;overflow:hidden;background:#000}}
.circle{{border-radius:50%}} .squircle{{border-radius:33px}}
.social{{width:600px;border:1px solid #ddd;border-radius:10px;overflow:hidden}}
.print{{filter:grayscale(1)}}
.grid2{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}}
</style></head><body>
<h1>Candidate pack - real-surface validation (pipeline-only, 2026-10-29)</h1>

<div class="sec"><h2>1. Browser tab, 16px favicon (light and dark), native and 8x</h2>
<div class="row">
  <div><div class="tab">{img("favicon-16.png",16)}<span class="t">hutch</span></div><div class="cap">light tab, native</div></div>
  <div><div class="tab dark">{img("favicon-16-dark.png",16)}<span class="t">hutch</span></div><div class="cap">dark tab, native</div></div>
  <div>{img("favicon-16.png",128,128,"zoom16")}<div class="cap">left: 16px x8</div></div>
  <div>{img("favicon-16-dark.png",128,128,"zoom16")}<div class="cap">dark: 16px x8</div></div>
  <div>{img("favicon-32.png",128,128,"zoom16")}<div class="cap">32px x4</div></div>
</div></div>

<div class="sec"><h2>2. Home screen / app tile (180px icon in a 60px tile)</h2>
<div class="row">
  <div class="phone"><div class="tile">{img("apple-touch-icon-180.png",60,60)}</div><div class="label">hutch</div></div>
  <div class="phone"><div class="tile"><img src="../../front-candidate/icon-512.png" width="60" height="60"></div><div class="label">hutch</div></div>
  <div>{img("apple-touch-icon-180.png",180,180)}<div class="cap">apple-touch 180</div></div>
  <div>{img("icon-512.png",96,96)}<div class="cap">PWA 512 at 96</div></div>
</div></div>

<div class="sec"><h2>3. Maskable safe-zone crops (circle, squircle, full) and monochrome</h2>
<div class="row">
  <div class="crop circle"><img src="../../front-candidate/icon-512-maskable.png" width="150" height="150"></div>
  <div class="crop squircle"><img src="../../front-candidate/icon-512-maskable.png" width="150" height="150"></div>
  <div>{img("icon-512-maskable.png",150,150)}<div class="cap">maskable full</div></div>
  <div style="background:#0f172a;padding:14px;border-radius:10px">{img("icon-512-monochrome.png",96,96)}<div class="cap" style="color:#aaa">monochrome (tintable)</div></div>
</div></div>

<div class="sec"><h2>4. Social card (OG 1200x630)</h2>
<div class="social"><img src="../../front-candidate/og-card-1200x630.png" width="600" height="315"></div></div>

<div class="sec"><h2>5. Lockups (press, 2x) and print check</h2>
<div class="grid2">
  <div><img src="../../front-candidate/lockup-dark.png" width="330"><div class="cap">lockup dark</div></div>
  <div><img src="../../front-candidate/lockup-light.png" width="330"><div class="cap">lockup light</div></div>
  <div class="print"><img src="../../front-candidate/lockup-light.png" width="330"><div class="cap">greyscale (print proxy)</div></div>
  <div class="print" style="background:#111;padding:10px"><img src="../../front-candidate/lockup-dark.png" width="330"><div class="cap" style="color:#aaa">greyscale on dark</div></div>
</div></div>

<div class="sec"><h2>6. GitHub social preview 1280x640</h2>
<img src="../../front-candidate/github-social-preview-1280x640.png" width="640" height="320"></div>
</body></html>"""
out = SHEETS / "candidate-validation.html"
out.write_text(html, encoding="utf-8")
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1100, "height": 900})
    page.goto(out.as_uri(), wait_until="load"); page.wait_for_timeout(700)
    page.screenshot(path=str(SHEETS / "candidate-validation.png"), full_page=True)
    b.close()
print("wrote candidate-validation.png")
