#!/usr/bin/env python3
"""Render brand concept candidates for direction selection.

Pipeline-only evidence for the Run 5 direction gate. These are candidate
renders for the human to choose from, NOT production assets: nothing here is
adopted by the product, site, docs or desktop until a dated authorisation
names the surfaces. Provenance: authored 2026-10-29 by the DSH "lead" session
(geometry constructed on the 32-unit grid, no tracing, no stock sources).

Run from repo root: .venv/bin/python .pipeline/brand/2026-10/assets/concepts/render_concepts.py
Requires: .venv with playwright (chromium verified 2026-10-29).
"""
import pathlib

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent
RASTER = ROOT / "raster"
SHEETS = ROOT / "sheets"

INK = "#09090b"
PAPER = "#ededf0"
EMERALD = "#34d399"

# Candidate geometry: 32-unit grid, stroke 2.5, centre dot r4 at (16,16),
# same doctrine as CONCEPTS-D1-D2.md 1.2 (one path family, no gradients).
# Each body is (label, svg inner markup, small-size variant markup or None).
CONCEPTS = [
    ("N1 Hutch Front (arch + dot)",
     '<path d="M4 28 V15 A12 12 0 0 1 28 15 V28 Z" fill="none" stroke="currentColor" '
     'stroke-width="2.5" stroke-linejoin="miter"/>'
     '<circle cx="16" cy="16" r="4" fill="currentColor"/>',
     '<path d="M4 28 V15 A12 12 0 0 1 28 15 V28 Z" fill="none" stroke="currentColor" '
     'stroke-width="3" stroke-linejoin="miter"/>'
     '<circle cx="16" cy="16" r="4.5" fill="currentColor"/>'),
    ("N2 H-Frame (uprights + stub bar + dot)",
     '<path d="M6 2 V30 M26 2 V30 M6 16 H9.5 M26 16 H22.5" fill="none" stroke="currentColor" '
     'stroke-width="2.5" stroke-linecap="butt"/>'
     '<circle cx="16" cy="16" r="4" fill="currentColor"/>',
     '<path d="M6.5 2.5 V29.5 M25.5 2.5 V29.5 M6.5 16 H9.5 M25.5 16 H22.5" fill="none" '
     'stroke="currentColor" stroke-width="3" stroke-linecap="butt"/>'
     '<circle cx="16" cy="16" r="4.5" fill="currentColor"/>'),
    ("N3 Local Shell (angle brackets + dot)",
     '<path d="M11 6 L4 16 L11 26 M21 6 L28 16 L21 26" fill="none" stroke="currentColor" '
     'stroke-width="2.5" stroke-linejoin="miter"/>'
     '<circle cx="16" cy="16" r="4" fill="currentColor"/>',
     '<path d="M11 6 L4 16 L11 26 M21 6 L28 16 L21 26" fill="none" stroke="currentColor" '
     'stroke-width="3" stroke-linejoin="miter"/>'
     '<circle cx="16" cy="16" r="4.5" fill="currentColor"/>'),
    ("N4 Threshold (square portal + dot)",
     '<path d="M5 28 V8 H27 V28" fill="none" stroke="currentColor" stroke-width="2.5" '
     'stroke-linejoin="miter"/>'
     '<circle cx="16" cy="16" r="4" fill="currentColor"/>',
     '<path d="M5.25 28 V8.25 H26.75 V28" fill="none" stroke="currentColor" stroke-width="3" '
     'stroke-linejoin="miter"/>'
     '<circle cx="16" cy="16" r="4.5" fill="currentColor"/>'),
    ("N6 Threshold (arch + resident dot in doorway)",
     '<path d="M4 26 V15 A12 12 0 0 1 28 15 V26 M4 26 H9.5 M22 26 H28" fill="none" '
     'stroke="currentColor" stroke-width="2.5" stroke-linejoin="miter"/>'
     '<circle cx="16" cy="26" r="4" fill="currentColor"/>',
     '<path d="M4 26 V15 A12 12 0 0 1 28 15 V26 M4 26 H9.5 M22 26 H28" fill="none" '
     'stroke="currentColor" stroke-width="3" stroke-linejoin="miter"/>'
     '<circle cx="16" cy="26" r="4.5" fill="currentColor"/>'),
    ("N5 Two-Bot Front (small-size risk probe)",
     '<path d="M4 28 V15 A12 12 0 0 1 28 15 V28 Z" fill="none" stroke="currentColor" '
     'stroke-width="2.5" stroke-linejoin="miter"/>'
     '<circle cx="12.5" cy="17" r="3" fill="currentColor"/>'
     '<circle cx="19.5" cy="17" r="3" fill="currentColor"/>',
     None),
    ("C0 Control (shipped hexagon + dot)",
     '<path d="M16 2 L28 9 L28 23 L16 30 L4 23 L4 9 Z" fill="none" stroke="currentColor" '
     'stroke-width="2.5" stroke-linejoin="miter"/>'
     '<circle cx="16" cy="16" r="4" fill="currentColor"/>',
     '<path d="M16 2 L28 9 L28 23 L16 30 L4 23 L4 9 Z" fill="none" stroke="currentColor" '
     'stroke-width="3" stroke-linejoin="miter"/>'
     '<circle cx="16" cy="16" r="4.5" fill="currentColor"/>'),
]


def svg_markup(body: str, size: int, color: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="{size}" '
            f'height="{size}" style="color:{color};display:block">{body}</svg>')


def raster_16(browser, slug: str, body: str, bg: str, fg: str, dpr: int) -> None:
    ctx = browser.new_context(viewport={"width": 16, "height": 16}, device_scale_factor=dpr)
    page = ctx.new_page()
    page.set_content(
        f'<!doctype html><html><body style="margin:0;background:{bg}">'
        f'<div style="width:16px;height:16px;color:{fg}">'
        f'{svg_markup(body, 16, fg)}</div></body></html>',
        wait_until="load")
    out = RASTER / f"{slug}-16{'-dpr2' if dpr == 2 else ''}-{bg.lstrip('#')}.png"
    page.screenshot(path=str(out), clip={"x": 0, "y": 0, "width": 16, "height": 16})
    ctx.close()


def main() -> None:
    RASTER.mkdir(parents=True, exist_ok=True)
    SHEETS.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # Pass A: honest 16px rasters (DPR 1 and 2, light and dark surfaces).
        for slug_label, body, _small in CONCEPTS:
            slug = slug_label.split(" ")[0].lower()
            for bg, fg in ((PAPER, INK), (INK, PAPER)):
                for dpr in (1, 2):
                    raster_16(browser, slug, body, bg, fg, dpr)
            # colour intent on ink (emerald), DPR 1
            raster_16(browser, slug + "-emerald", body, INK, EMERALD, 1)
        browser.close()

    # Pass B: contact sheet (vector cells + pixel-honest 16px zoom cells).
    rows = []
    for slug_label, body, small in CONCEPTS:
        slug = slug_label.split(" ")[0].lower()
        zoom_l = f"../raster/{slug}-16-{PAPER.lstrip('#')}.png"
        zoom_d = f"../raster/{slug}-16-{INK.lstrip('#')}.png"
        zoom_dpr2 = f"../raster/{slug}-16-dpr2-{PAPER.lstrip('#')}.png"
        small_cell = (svg_markup(small, 16, INK) if small else '<span class="na">n/a</span>')
        rows.append(f"""
  <tr>
    <td class="label">{slug_label}</td>
    <td class="cell ink"><div class="big">{svg_markup(body, 120, EMERALD)}</div></td>
    <td class="cell paper"><div class="mid">{svg_markup(body, 48, INK)}</div></td>
    <td class="cell white"><div class="s32">{svg_markup(body, 32, INK)}</div></td>
    <td class="cell white"><div class="s20">{svg_markup(body, 20, INK)}</div></td>
    <td class="cell white"><div class="s16">{svg_markup(body, 16, INK)}</div></td>
    <td class="cell white"><div class="s16">{small_cell}</div><div class="cap">small master 16px</div></td>
    <td class="cell white zoom"><img src="{zoom_l}" width="128" height="128" alt=""><div class="cap">16px x8, light</div></td>
    <td class="cell ink zoom"><img src="{zoom_d}" width="128" height="128" alt=""><div class="cap d">16px x8, dark</div></td>
    <td class="cell white zoom"><img src="{zoom_dpr2}" width="64" height="64" alt=""><div class="cap">16px dpr2 x4</div></td>
  </tr>""")

    html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:0;padding:16px;background:#fff;font-family:monospace;font-size:12px;color:#111}}
h1{{font-size:16px}} table{{border-collapse:collapse}}
td{{border:1px solid #bbb;padding:6px;vertical-align:middle;text-align:center}}
.label{{text-align:left;width:230px;vertical-align:top}}
.cell{{padding:4px}} .ink{{background:{INK}}} .paper{{background:{PAPER}}} .white{{background:#fff}}
.big{{display:flex;justify-content:center}} .mid{{display:flex;justify-content:center}}
.s32,.s20,.s16{{display:flex;justify-content:center;color:{INK}}}
.zoom img{{image-rendering:pixelated;display:block;margin:0 auto}}
.cap{{font-size:10px;color:#555;margin-top:4px}} .cap.d{{color:#aaa}}
.na{{color:#999;font-size:10px}}
td.ink .cap{{color:#888}}
</style></head><body>
<h1>Hutch concept candidates - direction-selection evidence, 2026-10-29 (not production assets)</h1>
<table><thead><tr><th>concept</th><th>128px emerald/ink</th><th>48px</th><th>32px</th><th>20px</th>
<th>16px master</th><th>16px small</th><th>16px zoom light</th><th>16px zoom dark</th><th>16px dpr2</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
</body></html>"""

    sheet_src = SHEETS / "contact-sheet.html"
    sheet_src.write_text(html, encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1560, "height": 1200})
        page.goto(sheet_src.as_uri(), wait_until="load")
        page.screenshot(path=str(SHEETS / "contact-sheet.png"), full_page=True)
        browser.close()
    print("wrote", SHEETS / "contact-sheet.png")


if __name__ == "__main__":
    main()
