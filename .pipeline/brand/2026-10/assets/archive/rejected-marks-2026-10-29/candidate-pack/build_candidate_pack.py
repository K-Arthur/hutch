#!/usr/bin/env python3
"""Build the candidate asset pack for the round-12 "Canopy" front (pipeline-only).

All outputs derive from hutch-mark-master.svg / hutch-mark-small.svg; no redraw.
Colour rules from COLOUR-SYSTEM.md: enclosure is the mark colour (emerald-400 on ink,
ink-950 on paper), PWA/theme background ink-950, monochrome transparent.
"""
import base64
import pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT
DATA = ROOT.parents[0]  # assets/
SHEETS = DATA.parent / "sheets"
INK, PAPER, EMERALD, MIST, EM7 = "#09090b", "#ededf0", "#34d399", "#a3a3ae", "#047857"
FONT = pathlib.Path(".pipeline/brand/2026-10/assets/concepts/fonts/BricolageGrotesque-var.ttf").resolve()
FONT_B64 = "data:font/truetype;base64," + base64.b64encode(FONT.read_bytes()).decode()

def svg(src_name, size, color):
    src = (OUT / src_name).read_text(encoding="utf-8")
    body = src.split(">", 1)[1].rsplit("</svg>", 1)[0]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="{size}" '
            f'height="{size}" style="color:{color};display:block">{body}</svg>')

def page_html(inner, w, h, bg):
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>'
            f'html,body{{margin:0;padding:0;width:{w}px;height:{h}px;background:{bg};overflow:hidden}}'
            f'.c{{width:{w}px;height:{h}px;display:flex;align-items:center;justify-content:center}}'
            f'</style></head><body><div class="c">{inner}</div></body></html>')

def shot(browser, name, inner, w, h, bg, dsf=1, clip=None, omit=False):
    ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=dsf)
    page = ctx.new_page()
    page.set_content(page_html(inner, w, h, bg), wait_until="load")
    page.screenshot(path=str(OUT / name), clip=clip, omit_background=omit)
    ctx.close()
    print("wrote", name)

def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        MS, SS = "hutch-mark-master.svg", "hutch-mark-small.svg"

        # favicons: transparent, ink for light tabs and paper for dark tabs
        for px in (16, 32):
            shot(b, f"favicon-{px}.png", svg(SS, px, INK), px, px, "transparent", omit=True)
            shot(b, f"favicon-{px}-dark.png", svg(SS, px, PAPER), px, px, "transparent", omit=True)

        # apple touch 180, PWA 192/512, maskable, monochrome
        shot(b, "apple-touch-icon-180.png", f'<div style="width:180px;height:180px;background:{INK};display:flex;align-items:center;justify-content:center">{svg(MS,126,EMERALD)}</div>', 180, 180, INK)
        shot(b, "icon-192.png", f'<div style="width:192px;height:192px;background:{INK};display:flex;align-items:center;justify-content:center">{svg(MS,134,EMERALD)}</div>', 192, 192, INK)
        shot(b, "icon-512.png", f'<div style="width:512px;height:512px;background:{INK};display:flex;align-items:center;justify-content:center">{svg(MS,358,EMERALD)}</div>', 512, 512, INK)
        shot(b, "icon-512-maskable.png", f'<div style="width:512px;height:512px;background:{INK};display:flex;align-items:center;justify-content:center">{svg(MS,369,EMERALD)}</div>', 512, 512, INK)
        shot(b, "icon-512-monochrome.png", svg(MS, 358, "#ffffff"), 512, 512, "transparent", omit=True)

        # social cards: mark + Bricolage wordmark, tagline verbatim (D11)
        face = ('@font-face{font-family:"Bricolage";src:url("' + FONT_B64 +
                '") format("truetype");font-weight:1 1000;font-display:block}')
        def card(w, h, mark_px, word_px, pad):
            inner = (f'<div style="width:{w}px;height:{h}px;background:{INK};display:flex;'
                     f'align-items:center;padding:0 {pad}px;box-sizing:border-box;gap:{int(word_px*0.22)}px">'
                     f'{svg(MS, mark_px, EMERALD)}'
                     f'<div style="font-family:Bricolage;font-weight:800;font-size:{word_px}px;'
                     f'letter-spacing:-0.02em;color:{PAPER};line-height:1">hutch<span style="color:{EMERALD}">.</span></div></div>'
                     f'<div style="position:absolute;left:{pad}px;bottom:{int(h*0.10)}px;font-family:Bricolage;'
                     f'font-size:{int(word_px*0.24)}px;color:{MIST};letter-spacing:0.01em">'
                     f'Your bots. Your machine. Your rules.</div>')
            return f'<style>{face}</style>' + inner
        shot(b, "og-card-1200x630.png", card(1200, 630, 150, 96, 80), 1200, 630, INK)
        shot(b, "github-social-preview-1280x640.png", card(1280, 640, 150, 96, 90), 1280, 640, INK)

        # lockups (transparent, for press), 2x
        def lockup(bg, fg):
            return (f'<style>{face}</style><div style="display:flex;align-items:center;gap:24px;padding:40px">'
                    f'{svg(MS, 96, EMERALD if bg == INK else EM7)}'
                    f'<div style="font-family:Bricolage;font-weight:800;font-size:72px;letter-spacing:-0.02em;'
                    f'color:{fg};line-height:1">hutch<span style="color:{EMERALD if bg == INK else EM7}">.</span></div></div>')
        shot(b, "lockup-dark.png", lockup(INK, PAPER), 700, 180, INK)
        shot(b, "lockup-light.png", lockup("#ffffff", INK), 700, 180, "#ffffff")
        b.close()
    print("done")

if __name__ == "__main__":
    main()
