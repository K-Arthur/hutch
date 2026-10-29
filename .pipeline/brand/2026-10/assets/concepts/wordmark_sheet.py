#!/usr/bin/env python3
"""Render wordmark typeface candidates for selection (pipeline-only evidence).

Candidates are OFL-licensed families downloaded from the google/fonts
repository (URLs, dates and licence pages recorded in fonts/SOURCES.md).
The shipped Geist wordmark is a control only. Nothing here is adopted.
"""
import pathlib

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent
FONTS = ROOT / "fonts"
SHEETS = ROOT / "sheets"
GEIST = ROOT.parents[4] / "website/assets/fonts/geist-latin-var.woff2"

INK = "#09090b"
PAPER = "#ededf0"
EMERALD = "#34d399"

# (css class, label, file, weight, variation settings)
CANDIDATES = [
    ("c0", "Fraunces (serif, variable)", "Fraunces-var.ttf", 800,
     "'opsz' 144, 'SOFT' 40, 'WONK' 1"),
    ("c1", "Bricolage Grotesque", "BricolageGrotesque-var.ttf", 800,
     "'opsz' 96, 'wdth' 100"),
    ("c2", "Anybody", "Anybody-var.ttf", 800, "'wdth' 105"),
    ("c3", "Martian Mono", "MartianMono-var.ttf", 700, "'wdth' 100"),
    ("c4", "Gabarito", "Gabarito-var.ttf", 800, ""),
    ("c5", "Schibsted Grotesk", "SchibstedGrotesk-var.ttf", 800, ""),
    ("c6", "Darker Grotesque", "DarkerGrotesque-var.ttf", 800, ""),
    ("c7", "Azeret Mono", "AzeretMono-var.ttf", 700, ""),
    ("c8", "CONTROL: Geist (shipped)", "geist-latin-var.woff2", 800, ""),
]


def main() -> None:
    SHEETS.mkdir(parents=True, exist_ok=True)
    face_css, class_css, rows = [], [], []
    for cls, label, fname, weight, vary in CANDIDATES:
        src = GEIST if fname.startswith("geist") else (FONTS / fname)
        fmt = "woff2" if fname.endswith("woff2") else "truetype"
        face_css.append(
            '@font-face{font-family:"' + fname + '";src:url("' + src.as_uri()
            + '") format("' + fmt + '");font-weight:1 1000;font-display:block}')
        vary_css = ("font-variation-settings:" + vary + ";") if vary else ""
        class_css.append(
            "." + cls + "{font-family:'" + fname + "';font-weight:" + str(weight)
            + ";" + vary_css + "}")
        rows.append(f"""
  <tr>
    <td class="label">{label}</td>
    <td class="cell paper"><div class="xl {cls}">hutch<span class="dot">.</span></div></td>
    <td class="cell ink"><div class="xl {cls}">hutch<span class="dot">.</span></div></td>
    <td class="cell white"><div class="md {cls}">hutch<span class="dot">.</span></div></td>
    <td class="cell white"><div class="sm {cls}">hutch<span class="dot">.</span></div></td>
    <td class="cell ink"><div class="sm {cls}">hutch<span class="dot">.</span></div></td>
    <td class="cell white"><div class="xs {cls}">hutch<span class="dot">.</span></div><div class="cap">16px</div></td>
  </tr>""")

    html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
{''.join(face_css)}
{''.join(class_css)}
body{{margin:0;padding:16px;background:#fff;font-family:monospace;font-size:12px;color:#111}}
h1{{font-size:16px}} table{{border-collapse:collapse}}
td{{border:1px solid #bbb;padding:8px;vertical-align:middle}}
.label{{text-align:left;width:210px;vertical-align:top;font-size:11px}}
.cell{{padding:4px 10px}} .paper{{background:{PAPER}}} .ink{{background:{INK}}} .white{{background:#fff}}
.xl{{font-size:72px;letter-spacing:-0.03em;line-height:1.1}}
.md{{font-size:30px;letter-spacing:-0.02em;color:{INK}}}
.sm{{font-size:18px;letter-spacing:-0.02em;color:{INK}}}
.xs{{font-size:16px;letter-spacing:-0.02em;color:{INK}}}
.cell.ink .sm, .cell.ink .xl {{color:{PAPER}}}
.cell.paper .xl {{color:{INK}}}
.dot{{color:{EMERALD}}}
.cap{{font-size:10px;color:#666;margin-top:4px}}
</style></head><body>
<h1>Wordmark candidates ("hutch", lowercase, emerald period) - selection evidence, 2026-10-29 (not production assets)</h1>
<table><thead><tr><th>family</th><th>72px on paper</th><th>72px on ink</th><th>30px</th><th>18px</th>
<th>18px on ink</th><th>16px</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
</body></html>"""

    out = SHEETS / "wordmark-sheet.html"
    out.write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        page.goto(out.as_uri(), wait_until="load")
        page.wait_for_timeout(900)
        loaded = page.evaluate("[...document.fonts].map(f=>f.family+':'+f.status)")
        print("faces:", loaded)
        page.screenshot(path=str(SHEETS / "wordmark-sheet.png"), full_page=True)
        browser.close()
    print("wrote", SHEETS / "wordmark-sheet.png")


if __name__ == "__main__":
    main()
