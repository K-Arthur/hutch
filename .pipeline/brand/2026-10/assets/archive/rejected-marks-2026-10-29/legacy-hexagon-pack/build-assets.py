#!/usr/bin/env python3
"""Build the authorised Hutch mark asset package (pipeline-only).

Deterministic generator for the raster outputs and the visual test sheets. Text masters are
hand-authored SVGs in this directory; this script only rasterises them with Playwright Chromium and
composes labelled test sheets. See ../ASSET-PACKAGE.md for provenance and the test log.

Run from the repo root:  .venv/bin/python .pipeline/brand/2026-10/assets/build-assets.py
Requires: .venv with playwright installed and ~/.cache/ms-playwright chromium (verified 2026-10-29).
"""
import pathlib
import struct

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent
TESTS = ROOT / "tests"
INK = "#09090b"
PAPER = "#ededf0"
EMERALD = "#34d399"


def svg(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def html(mark: str, cw: int, ch: int, mw: int, mh: int, bg: str) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;padding:0;background:{bg};}}
body{{width:{cw}px;height:{ch}px;display:flex;align-items:center;justify-content:center;}}
.m{{width:{mw}px;height:{mh}px;}}
.m svg{{width:100%!important;height:100%!important;display:block;}}
</style></head><body><div class="m">{mark}</div></body></html>"""


def shot(page, mark: str, cw: int, ch: int, mw: int, mh: int, bg: str, out: pathlib.Path, omit: bool = False) -> None:
    page.set_viewport_size({"width": cw, "height": ch})
    page.set_content(html(mark, cw, ch, mw, mh, bg), wait_until="load")
    page.screenshot(path=str(out), omit_background=omit)
    print("wrote", out.name)


def dims(path: pathlib.Path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", path
    w, h = struct.unpack(">II", data[16:24])
    return w, h


def main() -> None:
    TESTS.mkdir(exist_ok=True)
    master = svg("hutch-mark.svg")
    small = svg("hutch-mark-small.svg")
    colour = svg("hutch-mark-colour.svg")

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # ---- product-shaped raster family (sizes only; adopting them is a product change) ----
        ctx = browser.new_context(device_scale_factor=1)
        page = ctx.new_page()
        shot(page, colour, 192, 192, 144, 144, "transparent", ROOT / "icon-192.png", omit=True)
        shot(page, colour, 512, 512, 384, 384, "transparent", ROOT / "icon-512.png", omit=True)
        shot(page, colour.replace("currentColor", EMERALD), 512, 512, 300, 300, INK, ROOT / "icon-512-maskable.png")
        shot(page, colour.replace("currentColor", "#ffffff"), 512, 512, 300, 300, "transparent", ROOT / "icon-512-monochrome.png", omit=True)
        shot(page, colour, 180, 180, 120, 120, INK, ROOT / "apple-touch-icon-180.png")
        shot(page, small.replace("currentColor", INK), 16, 16, 16, 16, "transparent", ROOT / "favicon-16.png", omit=True)
        shot(page, small.replace("currentColor", PAPER), 16, 16, 16, 16, "transparent", ROOT / "favicon-16-dark.png", omit=True)
        shot(page, master.replace("currentColor", INK), 32, 32, 32, 32, "transparent", ROOT / "favicon-32.png", omit=True)
        shot(page, master.replace("currentColor", PAPER), 32, 32, 32, 32, "transparent", ROOT / "favicon-32-dark.png", omit=True)
        # 16px comparison inputs
        shot(page, master.replace("currentColor", INK), 16, 16, 16, 16, "transparent", TESTS / "m16.png", omit=True)
        shot(page, small.replace("currentColor", INK), 16, 16, 16, 16, "transparent", TESTS / "s16.png", omit=True)
        shot(page, master.replace("currentColor", PAPER), 16, 16, 16, 16, "transparent", TESTS / "m16p.png", omit=True)
        shot(page, small.replace("currentColor", PAPER), 16, 16, 16, 16, "transparent", TESTS / "s16p.png", omit=True)

        # ---- 16px comparison sheets (1x actual and 8x pixelated), dark and light ----
        for bg, name, m, s in ((INK, "16px-dark.png", "m16p.png", "s16p.png"), (PAPER, "16px-light.png", "m16.png", "s16.png")):
            import base64
            def uri(f):
                return "data:image/png;base64," + base64.b64encode((TESTS / f).read_bytes()).decode()
            fg = PAPER if bg == INK else INK
            page.set_viewport_size({"width": 760, "height": 300})
            page.set_content(f"""<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:0;background:{bg};color:{fg};font:13px/1.4 Menlo,monospace;}}
.row{{display:flex;gap:34px;align-items:flex-end;padding:26px 30px;}}
.cell{{text-align:center}} .cell div{{margin-top:10px}}
img.pix{{image-rendering:pixelated;}}
</style></head><body>
<div class="row">
  <div class="cell"><img src="{uri(m)}" width="16" height="16" alt=""><div>master 16px, 1x</div></div>
  <div class="cell"><img src="{uri(s)}" width="16" height="16" alt=""><div>small 16px, 1x</div></div>
  <div class="cell"><img class="pix" src="{uri(m)}" width="128" height="128" alt=""><div>master 16px, 8x</div></div>
  <div class="cell"><img class="pix" src="{uri(s)}" width="128" height="128" alt=""><div>small 16px, 8x</div></div>
</div></body></html>""", wait_until="load")
            page.screenshot(path=str(TESTS / name))
            print("wrote", name)

        # ---- monochrome sheet: one ink on both backgrounds, sizes 32/24/16 ----
        page.set_viewport_size({"width": 760, "height": 300})
        page.set_content(f"""<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:0;background:{PAPER};color:{INK};font:13px/1.4 Menlo,monospace;}}
.half{{display:inline-flex;gap:40px;align-items:flex-end;padding:28px 34px;vertical-align:top}}
.dark{{background:{INK};color:{PAPER};}}
.cell{{text-align:center}} .cell div{{margin-top:8px}}
svg{{display:block}}
</style></head><body>
<div class="half">
  <div class="cell">{master.replace('currentColor', INK)}{''}<div>ink 32</div></div>
  <div class="cell">{master.replace('currentColor', INK).replace('width="32" height="32"','width="24" height="24"')}<div>ink 24</div></div>
  <div class="cell">{small.replace('currentColor', INK).replace('width="32" height="32"','width="16" height="16"')}<div>ink 16</div></div>
  <div class="cell">{colour}<div>emerald 32</div></div>
</div>
<div class="half dark">
  <div class="cell">{master.replace('currentColor', PAPER)}<div>paper 32</div></div>
  <div class="cell">{master.replace('currentColor', PAPER).replace('width="32" height="32"','width="24" height="24"')}<div>paper 24</div></div>
  <div class="cell">{small.replace('currentColor', PAPER).replace('width="32" height="32"','width="16" height="16"')}<div>paper 16</div></div>
  <div class="cell">{colour}<div>emerald 32</div></div>
</div></body></html>""", wait_until="load")
        page.screenshot(path=str(TESTS / "monochrome.png"))
        print("wrote monochrome.png")

        # ---- forced-colours emulation ----
        page.set_viewport_size({"width": 620, "height": 220})
        page.set_content(f"""<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:0;background:Canvas;color:CanvasText;font:13px/1.4 Menlo,monospace;padding:24px}}
.flex{{display:flex;gap:36px;align-items:center}}
</style></head><body>
<div class="flex">
  <div>{master.replace('currentColor','CanvasText')}<div>currentColor (CanvasText)</div></div>
  <div>{colour}<div>hard-coded #34d399</div></div>
</div></body></html>""", wait_until="load")
        page.emulate_media(forced_colors="active")
        matched = page.evaluate("matchMedia('(forced-colors: active)').matches")
        page.screenshot(path=str(TESTS / "forced-colours.png"))
        print("wrote forced-colours.png; forced-colors media matches:", matched)
        ctx.close()

        # ---- DPR 2 check: 16 CSS px becomes a 32 px raster ----
        ctx2 = browser.new_context(device_scale_factor=2)
        p2 = ctx2.new_page()
        shot(p2, small.replace("currentColor", INK), 16, 16, 16, 16, "transparent", TESTS / "dpr2-16.png", omit=True)
        ctx2.close()
        browser.close()

    # ---- dimension log ----
    log = []
    for name in ["icon-192.png","icon-512.png","icon-512-maskable.png","icon-512-monochrome.png",
                 "apple-touch-icon-180.png","favicon-16.png","favicon-16-dark.png",
                 "favicon-32.png","favicon-32-dark.png"]:
        log.append(f"{name}: {dims(ROOT / name)[0]}x{dims(ROOT / name)[1]}")
    log.append(f"tests/dpr2-16.png: {dims(TESTS / 'dpr2-16.png')[0]}x{dims(TESTS / 'dpr2-16.png')[1]}")
    (TESTS / "dimensions.txt").write_text("\n".join(log) + "\n", encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
