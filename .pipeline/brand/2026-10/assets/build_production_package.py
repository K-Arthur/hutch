#!/usr/bin/env python3
"""Build the complete Run 6 production asset package, press kit, outlined wordmark/lockups,
Bricolage Grotesque 800 woff2 subset, platform icons, social cards, and validation matrix sheet
for the maintainer-picked mark: Direction B ("Visor Hutch", picked 2026-10-29).

Write scope: .pipeline/brand/2026-10/assets/{production,press-kit}/ only.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import shutil
import struct
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
FONT_SRC = HERE / "concepts" / "fonts" / "BricolageGrotesque-var.ttf"
OFL_SRC = HERE / "concepts" / "fonts" / "OFL-bricolage-grotesque.txt"

PROD_DIR = HERE / "production"
PRESS_DIR = HERE / "press-kit"

for d in [
    PROD_DIR / "svg",
    PROD_DIR / "icons",
    PROD_DIR / "lockups",
    PROD_DIR / "social",
    PROD_DIR / "fonts",
    PRESS_DIR / "svg",
    PRESS_DIR / "png",
    PRESS_DIR / "fonts",
]:
    d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 1. Picked Mark Geometry: Direction B ("Visor Hutch")
# ---------------------------------------------------------------------------

def oval_path(cx: float, cy: float, rx: float, ry: float, deg: float = 0.0) -> str:
    k = 0.55228475
    rad = math.radians(deg)
    ca, sa = math.cos(rad), math.sin(rad)

    def pt(x: float, y: float) -> tuple[float, float]:
        return (cx + x * ca - y * sa, cy + x * sa + y * ca)

    p0 = pt(0, -ry)
    c0a, c0b = pt(rx * k, -ry), pt(rx, -ry * k)
    p1 = pt(rx, 0)
    c1a, c1b = pt(rx, ry * k), pt(rx * k, ry)
    p2 = pt(0, ry)
    c2a, c2b = pt(-rx * k, ry), pt(-rx, ry * k)
    p3 = pt(-rx, 0)
    c3a, c3b = pt(-rx, -ry * k), pt(-rx * k, -ry)

    return (
        f"M {p0[0]:.2f} {p0[1]:.2f} "
        f"C {c0a[0]:.2f} {c0a[1]:.2f} {c0b[0]:.2f} {c0b[1]:.2f} {p1[0]:.2f} {p1[1]:.2f} "
        f"C {c1a[0]:.2f} {c1a[1]:.2f} {c1b[0]:.2f} {c1b[1]:.2f} {p2[0]:.2f} {p2[1]:.2f} "
        f"C {c2a[0]:.2f} {c2a[1]:.2f} {c2b[0]:.2f} {c2b[1]:.2f} {p3[0]:.2f} {p3[1]:.2f} "
        f"C {c3a[0]:.2f} {c3a[1]:.2f} {c3b[0]:.2f} {c3b[1]:.2f} {p0[0]:.2f} {p0[1]:.2f} Z"
    )


def skirt_bottom_d(x_left: float, x_right: float, y_foot: float, foot_w: float, arch_top_y: float) -> str:
    span = x_right - x_left
    arch_w = (span - 3.0 * foot_w) / 2.0
    rf = foot_w / 2.0
    ra = arch_w / 2.0
    y_foot_arc_start = y_foot - rf
    y_arch_arc_start = arch_top_y + ra

    x_r1 = x_right - foot_w
    x_c2 = x_r1 - arch_w
    x_c1 = x_c2 - foot_w
    x_l2 = x_c1 - arch_w

    return (
        f"L {x_right:.2f} {y_foot_arc_start:.2f} "
        f"A {rf:.2f} {rf:.2f} 0 0 1 {x_r1:.2f} {y_foot_arc_start:.2f} "
        f"L {x_r1:.2f} {y_arch_arc_start:.2f} "
        f"A {ra:.2f} {ra:.2f} 0 0 0 {x_c2:.2f} {y_arch_arc_start:.2f} "
        f"L {x_c2:.2f} {y_foot_arc_start:.2f} "
        f"A {rf:.2f} {rf:.2f} 0 0 1 {x_c1:.2f} {y_foot_arc_start:.2f} "
        f"L {x_c1:.2f} {y_arch_arc_start:.2f} "
        f"A {ra:.2f} {ra:.2f} 0 0 0 {x_l2:.2f} {y_arch_arc_start:.2f} "
        f"L {x_l2:.2f} {y_foot_arc_start:.2f} "
        f"A {rf:.2f} {rf:.2f} 0 0 1 {x_left:.2f} {y_foot_arc_start:.2f} "
    )


def rounded_visor_path(x0: float, y0: float, x1: float, y1: float, r_top: float, r_bot: float) -> str:
    return (
        f"M {x0 + r_top:.2f} {y0:.2f} "
        f"L {x1 - r_top:.2f} {y0:.2f} "
        f"A {r_top:.2f} {r_top:.2f} 0 0 1 {x1:.2f} {y0 + r_top:.2f} "
        f"L {x1:.2f} {y1 - r_bot:.2f} "
        f"A {r_bot:.2f} {r_bot:.2f} 0 0 1 {x1 - r_bot:.2f} {y1:.2f} "
        f"L {x0 + r_bot:.2f} {y1:.2f} "
        f"A {r_bot:.2f} {r_bot:.2f} 0 0 1 {x0:.2f} {y1 - r_bot:.2f} "
        f"L {x0:.2f} {y0 + r_top:.2f} "
        f"A {r_top:.2f} {r_top:.2f} 0 0 1 {x0 + r_top:.2f} {y0:.2f} Z"
    )


def mark_master_d() -> str:
    """Master tier (>= 32px): Direction B 'Visor Hutch'."""
    base_skirt = skirt_bottom_d(x_left=4.00, x_right=28.00, y_foot=28.30, foot_w=4.40, arch_top_y=22.60)
    outer = (
        "M 16.00 3.70 "
        "C 23.10 3.70 28.00 8.50 28.00 15.20 "
        f"{base_skirt}"
        "L 4.00 15.20 "
        "C 4.00 8.50 8.90 3.70 16.00 3.70 Z"
    )
    visor = rounded_visor_path(6.80, 8.60, 25.20, 18.40, 5.40, 3.60)
    left_eye = oval_path(12.20, 13.70, 2.05, 2.65, -8.0)
    right_eye = oval_path(19.80, 13.40, 2.05, 2.65, 8.0)
    return f"{outer} {visor} {left_eye} {right_eye}"


def mark_small_d() -> str:
    """Small tier (16-24px, redrawn R6): Direction B 'Visor Hutch'."""
    base_skirt = skirt_bottom_d(x_left=3.00, x_right=29.00, y_foot=29.20, foot_w=4.80, arch_top_y=22.50)
    outer = (
        "M 16.00 2.80 "
        "C 23.80 2.80 29.00 7.90 29.00 14.80 "
        f"{base_skirt}"
        "L 3.00 14.80 "
        "C 3.00 7.90 8.20 2.80 16.00 2.80 Z"
    )
    visor = rounded_visor_path(6.20, 7.60, 25.80, 18.60, 5.80, 3.80)
    left_eye = oval_path(12.00, 13.25, 2.15, 2.65, -8.0)
    right_eye = oval_path(20.00, 13.00, 2.15, 2.65, 8.0)
    return f"{outer} {visor} {left_eye} {right_eye}"


# ---------------------------------------------------------------------------
# 2. Subset Bricolage Grotesque 800 woff2 + ship OFL licence text
# ---------------------------------------------------------------------------

def build_font_subsets() -> None:
    # 1. Static weight-800 Latin subset (for ultra-light wordmark/display embedding)
    var_font = TTFont(str(FONT_SRC))
    inst_800 = instantiateVariableFont(var_font, {"wght": 800, "wdth": 100, "opsz": 48})
    opts = Options()
    opts.flavor = "woff2"
    opts.layout_features = ["kern", "liga", "calt"]
    opts.name_IDs = ["*"]
    opts.drop_tables += ["DSIG"]
    # Full Basic Latin + Latin-1 Supplement + General Punctuation
    unicodes = list(range(0x0020, 0x007F)) + list(range(0x00A0, 0x0180)) + [0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2026]
    subsetter = Subsetter(options=opts)
    subsetter.populate(unicodes=unicodes)
    subsetter.subset(inst_800)

    out_800 = PROD_DIR / "fonts" / "bricolage-grotesque-latin-800.woff2"
    inst_800.save(str(out_800))

    # 2. Variable Latin subset (retaining weight axis for display flexibility if ever needed)
    var_font2 = TTFont(str(FONT_SRC))
    subsetter2 = Subsetter(options=opts)
    subsetter2.populate(unicodes=unicodes)
    subsetter2.subset(var_font2)
    out_var = PROD_DIR / "fonts" / "bricolage-grotesque-latin-var.woff2"
    var_font2.save(str(out_var))

    # Copy OFL text and subsets to both production/fonts/ and press-kit/fonts/
    shutil.copyfile(OFL_SRC, PROD_DIR / "fonts" / "OFL-bricolage-grotesque.txt")
    shutil.copyfile(out_800, PRESS_DIR / "fonts" / "bricolage-grotesque-latin-800.woff2")
    shutil.copyfile(out_var, PRESS_DIR / "fonts" / "bricolage-grotesque-latin-var.woff2")
    shutil.copyfile(OFL_SRC, PRESS_DIR / "fonts" / "OFL-bricolage-grotesque.txt")


# ---------------------------------------------------------------------------
# 3. Extract Outlined Wordmark ("hutch" + ".") from Bricolage Grotesque 800
# ---------------------------------------------------------------------------

def extract_outlined_wordmark(font_size: float = 48.0, tracking_em: float = -0.03) -> tuple[str, str, float, float]:
    """Return (letters_path_d, period_path_d, total_width, baseline_y) for lowercase 'hutch.'
    converted to true SVG <path> outlines at `font_size` px (baseline at y = 38.0 on a 48px-tall canvas).
    """
    var_font = TTFont(str(FONT_SRC))
    inst = instantiateVariableFont(var_font, {"wght": 800, "wdth": 100, "opsz": 48})
    gs = inst.getGlyphSet()
    upm = inst["head"].unitsPerEm
    scale = font_size / upm
    tracking = tracking_em * font_size
    baseline_y = 38.0

    # Extract kerning pairs if GPOS/kern present; Bricolage spacing at -0.03em tracking is uniform
    letters = ["h", "u", "t", "c", "h"]
    x_cursor = 0.0
    letters_cmds: list[str] = []

    for idx, gname in enumerate(letters):
        pen = SVGPathPen(gs, lambda v: f"{v:.2f}")
        # Font Y is up; SVG Y is down -> matrix (scale, 0, 0, -scale, x_cursor, baseline_y)
        tpen = TransformPen(pen, (scale, 0.0, 0.0, -scale, x_cursor, baseline_y))
        gs[gname].draw(tpen)
        letters_cmds.append(pen.getCommands())
        x_cursor += gs[gname].width * scale + (tracking if idx < len(letters) - 1 else 0.0)

    # Slight optical kerning before period (-0.01em)
    x_cursor += -0.01 * font_size
    period_pen = SVGPathPen(gs, lambda v: f"{v:.2f}")
    tpen_p = TransformPen(period_pen, (scale, 0.0, 0.0, -scale, x_cursor, baseline_y))
    gs["period"].draw(tpen_p)
    period_d = period_pen.getCommands()
    total_w = math.ceil(x_cursor + gs["period"].width * scale)
    return " ".join(letters_cmds), period_d, float(total_w), baseline_y


# ---------------------------------------------------------------------------
# 4. Write Master & Variant SVGs (Marks, Outlined Wordmarks, Outlined Lockups)
# ---------------------------------------------------------------------------

def write_svg_files() -> dict[str, str]:
    m_d = mark_master_d()
    s_d = mark_small_d()
    letters_d, period_d, wm_w, _ = extract_outlined_wordmark(font_size=44.0, tracking_em=-0.03)

    svgs: dict[str, str] = {}

    # Mark SVGs
    svgs["hutch-mark-master.svg"] = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">\n'
        f'  <path d="{m_d}" fill="#34d399" fill-rule="evenodd"/>\n'
        '</svg>\n'
    )
    svgs["hutch-mark-small.svg"] = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">\n'
        f'  <path d="{s_d}" fill="#34d399" fill-rule="evenodd"/>\n'
        '</svg>\n'
    )
    svgs["hutch-mark-light.svg"] = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">\n'
        f'  <path d="{m_d}" fill="#047857" fill-rule="evenodd"/>\n'
        '</svg>\n'
    )
    svgs["hutch-mark-mono-dark.svg"] = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">\n'
        f'  <path d="{m_d}" fill="#ededf0" fill-rule="evenodd"/>\n'
        '</svg>\n'
    )
    svgs["hutch-mark-mono-light.svg"] = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">\n'
        f'  <path d="{m_d}" fill="#09090b" fill-rule="evenodd"/>\n'
        '</svg>\n'
    )
    svgs["hutch-mark-currentcolor.svg"] = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">\n'
        f'  <path d="{m_d}" fill="currentColor" fill-rule="evenodd"/>\n'
        '</svg>\n'
    )

    for name, content in svgs.items():
        (PROD_DIR / "svg" / name).write_text(content, encoding="utf-8")
        (PRESS_DIR / "svg" / name).write_text(content, encoding="utf-8")

    # Favicon SVG with prefers-color-scheme (uses redrawn Small tier for 16-24px browser tabs)
    favicon_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">\n'
        '  <style>\n'
        '    path { fill: #09090b; }\n'
        '    @media (prefers-color-scheme: dark) { path { fill: #34d399; } }\n'
        '  </style>\n'
        f'  <path d="{s_d}" fill-rule="evenodd"/>\n'
        '</svg>\n'
    )
    (PROD_DIR / "icons" / "favicon.svg").write_text(favicon_svg, encoding="utf-8")
    (PROD_DIR / "icons" / "icon-monochrome.svg").write_text(
        svgs["hutch-mark-currentcolor.svg"], encoding="utf-8"
    )

    # Outlined Wordmark SVGs (height 48, width wm_w + 8)
    wm_vb_w = int(wm_w + 8)
    wordmarks = {
        "hutch-wordmark-dark.svg": ("#ededf0", "#34d399"),
        "hutch-wordmark-light.svg": ("#09090b", "#047857"),
        "hutch-wordmark-mono-dark.svg": ("#ededf0", "#ededf0"),
        "hutch-wordmark-mono-light.svg": ("#09090b", "#09090b"),
    }
    for name, (text_col, dot_col) in wordmarks.items():
        content = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {wm_vb_w} 48">\n'
            f'  <g transform="translate(4, 0)">\n'
            f'    <path d="{letters_d}" fill="{text_col}"/>\n'
            f'    <path d="{period_d}" fill="{dot_col}"/>\n'
            f'  </g>\n'
            f'</svg>\n'
        )
        (PROD_DIR / "lockups" / name).write_text(content, encoding="utf-8")
        (PRESS_DIR / "svg" / name).write_text(content, encoding="utf-8")

    # Outlined Horizontal Lockup SVGs:
    # 38x38 mark at (0, 5) + 12px gap (x=50) + outlined wordmark (baseline y=38.0 aligns with mark feet at y=5 + 38*(28.3/32) = 38.6!)
    lockup_vb_w = int(50 + wm_w + 4)
    mark_scale = 38.0 / 32.0
    lockups = {
        "hutch-lockup-dark.svg": ("#34d399", "#ededf0", "#34d399"),
        "hutch-lockup-light.svg": ("#047857", "#09090b", "#047857"),
        "hutch-lockup-mono-dark.svg": ("#ededf0", "#ededf0", "#ededf0"),
        "hutch-lockup-mono-light.svg": ("#09090b", "#09090b", "#09090b"),
    }
    for name, (mark_col, text_col, dot_col) in lockups.items():
        content = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {lockup_vb_w} 48">\n'
            f'  <g transform="translate(0, 4.2) scale({mark_scale:.5f})">\n'
            f'    <path d="{m_d}" fill="{mark_col}" fill-rule="evenodd"/>\n'
            f'  </g>\n'
            f'  <g transform="translate(50, 0)">\n'
            f'    <path d="{letters_d}" fill="{text_col}"/>\n'
            f'    <path d="{period_d}" fill="{dot_col}"/>\n'
            f'  </g>\n'
            f'</svg>\n'
        )
        (PROD_DIR / "lockups" / name).write_text(content, encoding="utf-8")
        (PRESS_DIR / "svg" / name).write_text(content, encoding="utf-8")

    return {"m_d": m_d, "s_d": s_d, "letters_d": letters_d, "period_d": period_d, "wm_vb_w": str(wm_vb_w), "lockup_vb_w": str(lockup_vb_w)}


# ---------------------------------------------------------------------------
# 5. Pack Multi-Size .ICO (16x16, 32x32, 48x48 PNG frames)
# ---------------------------------------------------------------------------

def write_ico(out_ico: Path, png_paths: list[tuple[int, Path]]) -> None:
    """Write a standard Windows/web ICO container embedding PNG payloads."""
    num = len(png_paths)
    header = struct.pack("<HHH", 0, 1, num)
    offset = 6 + 16 * num
    entries = []
    payloads = []
    for dim, p in png_paths:
        data = p.read_bytes()
        w_byte = 0 if dim >= 256 else dim
        h_byte = 0 if dim >= 256 else dim
        entry = struct.pack("<BBBBHHII", w_byte, h_byte, 0, 0, 1, 32, len(data), offset)
        entries.append(entry)
        payloads.append(data)
        offset += len(data)
    out_ico.write_bytes(header + b"".join(entries) + b"".join(payloads))


# ---------------------------------------------------------------------------
# 6. Render All Rasters (Icons, 2x Lockup PNGs, Social Cards, Validation Sheet)
# ---------------------------------------------------------------------------

def render_all_rasters(meta: dict[str, str]) -> None:
    m_d = meta["m_d"]
    s_d = meta["s_d"]
    font_b64 = base64.b64encode((PROD_DIR / "fonts" / "bricolage-grotesque-latin-800.woff2").read_bytes()).decode("ascii")
    repo_root = HERE.parent.parent.parent.parent
    geist_path = repo_root / "website" / "assets" / "fonts" / "geist-latin-var.woff2"
    geist_mono_path = repo_root / "website" / "assets" / "fonts" / "geist-mono-latin-var.woff2"
    geist_b64 = base64.b64encode(geist_path.read_bytes()).decode("ascii")
    geist_mono_b64 = base64.b64encode(geist_mono_path.read_bytes()).decode("ascii")

    with sync_playwright() as p:
        browser = p.chromium.launch()

        def shot_svg(svg_markup: str, w: int, h: int, out_file: Path, omit_bg: bool = True) -> None:
            page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
            page.set_content(
                f"<!doctype html><html><body style='margin:0;padding:0;overflow:hidden;background:transparent'>{svg_markup}</body></html>"
            )
            page.screenshot(path=str(out_file), omit_background=omit_bg)
            page.close()

        # --- A. Favicons (16, 32, 48) ---
        # Dark transparent (for dark browser tabs), Light transparent (for light tabs), and plated default (for .ico fallback)
        for sz in (16, 32):
            d_use = s_d if sz <= 24 else m_d
            shot_svg(
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{sz}" height="{sz}" viewBox="0 0 32 32">'
                f'<path d="{d_use}" fill="#34d399" fill-rule="evenodd"/></svg>',
                sz, sz, PROD_DIR / "icons" / f"favicon-{sz}x{sz}-dark.png", omit_bg=True
            )
            shot_svg(
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{sz}" height="{sz}" viewBox="0 0 32 32">'
                f'<path d="{d_use}" fill="#09090b" fill-rule="evenodd"/></svg>',
                sz, sz, PROD_DIR / "icons" / f"favicon-{sz}x{sz}-light.png", omit_bg=True
            )
        # Plated favicons (16, 32, 48) on #09090b rounded tile so .ico and any tab background always has 10.35:1 contrast!
        for sz in (16, 32, 48):
            d_use = s_d if sz <= 24 else m_d
            shot_svg(
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{sz}" height="{sz}" viewBox="0 0 32 32">'
                f'<rect width="32" height="32" rx="7" fill="#09090b"/>'
                f'<g transform="translate(2.56, 2.56) scale(0.84)"><path d="{d_use}" fill="#34d399" fill-rule="evenodd"/></g></svg>',
                sz, sz, PROD_DIR / "icons" / f"favicon-{sz}x{sz}.png", omit_bg=True
            )

        write_ico(
            PROD_DIR / "icons" / "favicon.ico",
            [
                (16, PROD_DIR / "icons" / "favicon-16x16.png"),
                (32, PROD_DIR / "icons" / "favicon-32x32.png"),
                (48, PROD_DIR / "icons" / "favicon-48x48.png"),
            ],
        )

        # --- B. Apple Touch Icon (180x180, opaque #09090b background) ---
        shot_svg(
            '<svg xmlns="http://www.w3.org/2000/svg" width="180" height="180" viewBox="0 0 32 32">'
            '<rect width="32" height="32" fill="#09090b"/>'
            f'<g transform="translate(3.52, 3.52) scale(0.78)"><path d="{m_d}" fill="#34d399" fill-rule="evenodd"/></g></svg>',
            180, 180, PROD_DIR / "icons" / "apple-touch-icon.png", omit_bg=False
        )

        # --- C. PWA Icons: 192 & 512 (any, maskable, monochrome) ---
        for sz in (192, 512):
            # purpose: "any" (rounded ink-950 tile with emerald-400 mark)
            shot_svg(
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{sz}" height="{sz}" viewBox="0 0 32 32">'
                f'<rect width="32" height="32" rx="7" fill="#09090b"/>'
                f'<g transform="translate(2.88, 2.88) scale(0.82)"><path d="{m_d}" fill="#34d399" fill-rule="evenodd"/></g></svg>',
                sz, sz, PROD_DIR / "icons" / f"icon-{sz}.png", omit_bg=True
            )
            # purpose: "maskable" (opaque #09090b full-bleed background; mark scaled to 0.72 inside the 40%-radius W3C safe zone)
            shot_svg(
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{sz}" height="{sz}" viewBox="0 0 32 32">'
                f'<rect width="32" height="32" fill="#09090b"/>'
                f'<g transform="translate(4.48, 4.48) scale(0.72)"><path d="{m_d}" fill="#34d399" fill-rule="evenodd"/></g></svg>',
                sz, sz, PROD_DIR / "icons" / f"icon-{sz}-maskable.png", omit_bg=False
            )
            # purpose: "monochrome" (transparent background, white #ffffff silhouette so OS tints via alpha channel)
            shot_svg(
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{sz}" height="{sz}" viewBox="0 0 32 32">'
                f'<path d="{m_d}" fill="#ffffff" fill-rule="evenodd"/></svg>',
                sz, sz, PROD_DIR / "icons" / f"icon-{sz}-monochrome.png", omit_bg=True
            )

        # Copy 512px mark PNGs to press-kit/png/
        shutil.copyfile(PROD_DIR / "icons" / "icon-512.png", PRESS_DIR / "png" / "hutch-icon-512.png")
        shot_svg(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 32 32">'
            f'<path d="{m_d}" fill="#34d399" fill-rule="evenodd"/></svg>',
            512, 512, PRESS_DIR / "png" / "hutch-mark-emerald-512.png", omit_bg=True
        )
        shot_svg(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 32 32">'
            f'<path d="{m_d}" fill="#ededf0" fill-rule="evenodd"/></svg>',
            512, 512, PRESS_DIR / "png" / "hutch-mark-mono-dark-512.png", omit_bg=True
        )
        shot_svg(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 32 32">'
            f'<path d="{m_d}" fill="#09090b" fill-rule="evenodd"/></svg>',
            512, 512, PRESS_DIR / "png" / "hutch-mark-mono-light-512.png", omit_bg=True
        )

        # --- D. 2x PNG exports of Outlined Wordmarks and Lockups ---
        wm_w2x = int(meta["wm_vb_w"]) * 4
        wm_h2x = 48 * 4
        for svg_name in ["hutch-wordmark-dark.svg", "hutch-wordmark-light.svg", "hutch-wordmark-mono-dark.svg", "hutch-wordmark-mono-light.svg"]:
            raw_svg = (PROD_DIR / "lockups" / svg_name).read_text(encoding="utf-8")
            sized_svg = raw_svg.replace('<svg ', f'<svg width="{wm_w2x}" height="{wm_h2x}" ')
            png_name = svg_name.replace(".svg", "@2x.png")
            shot_svg(sized_svg, wm_w2x, wm_h2x, PROD_DIR / "lockups" / png_name, omit_bg=True)
            shutil.copyfile(PROD_DIR / "lockups" / png_name, PRESS_DIR / "png" / png_name)

        lk_w2x = int(meta["lockup_vb_w"]) * 4
        lk_h2x = 48 * 4
        for svg_name in ["hutch-lockup-dark.svg", "hutch-lockup-light.svg", "hutch-lockup-mono-dark.svg", "hutch-lockup-mono-light.svg"]:
            raw_svg = (PROD_DIR / "lockups" / svg_name).read_text(encoding="utf-8")
            sized_svg = raw_svg.replace('<svg ', f'<svg width="{lk_w2x}" height="{lk_h2x}" ')
            png_name = svg_name.replace(".svg", "@2x.png")
            shot_svg(sized_svg, lk_w2x, lk_h2x, PROD_DIR / "lockups" / png_name, omit_bg=True)
            shutil.copyfile(PROD_DIR / "lockups" / png_name, PRESS_DIR / "png" / png_name)

        # --- E. Social Cards: OG 1200x630 & GitHub Social Preview 1280x640 ---
        def build_social_card_html(w: int, h: int, pad_x: int, pad_y: int) -> str:
            return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
@font-face {{
  font-family: 'Bricolage';
  src: url(data:font/woff2;base64,{font_b64}) format('woff2');
  font-weight: 800;
}}
@font-face {{
  font-family: 'Geist';
  src: url(data:font/woff2;base64,{geist_b64}) format('woff2');
  font-weight: 100 900;
}}
@font-face {{
  font-family: 'GeistMono';
  src: url(data:font/woff2;base64,{geist_mono_b64}) format('woff2');
  font-weight: 100 900;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; width: {w}px; height: {h}px; overflow: hidden;
  background: #09090b; color: #ededf0;
  font-family: 'Geist', system-ui, sans-serif;
  padding: {pad_y}px {pad_x}px;
  display: flex; justify-content: space-between; align-items: stretch;
  position: relative;
}}
.frame {{
  width: 100%; height: 100%;
  background: #0f0f12;
  border: 1px solid rgba(255,255,255,0.10);
  border-radius: 20px;
  padding: 52px 60px;
  display: flex; justify-content: space-between; align-items: center;
  gap: 48px;
}}
.left {{
  display: flex; flex-direction: column; justify-content: space-between;
  height: 100%; max-width: 680px;
}}
.lockup {{
  display: flex; align-items: center; gap: 16px;
}}
.wm {{
  font-family: 'Bricolage', sans-serif; font-weight: 800;
  font-size: 46px; letter-spacing: -0.03em; color: #ededf0; line-height: 1;
}}
.wm .dot {{ color: #34d399; }}
.headline {{
  font-family: 'Geist', sans-serif; font-weight: 700;
  font-size: 62px; line-height: 1.06; letter-spacing: -0.035em;
  color: #ededf0; margin: 0 0 16px 0;
}}
.headline .accent {{ color: #34d399; }}
.sub {{
  font-size: 24px; line-height: 1.45; color: #a3a3ae; margin: 0;
}}
.meta {{
  font-family: 'GeistMono', monospace; font-size: 16px; color: #8e8e99;
  display: flex; align-items: center; gap: 12px;
}}
.pill {{
  display: inline-flex; align-items: center; gap: 8px;
  background: #16161a; border: 1px solid rgba(255,255,255,0.14);
  color: #ededf0; padding: 6px 14px; border-radius: 100px; font-size: 15px;
}}
.pill-dot {{ width: 8px; height: 8px; border-radius: 50%; background: #34d399; }}
.right {{
  width: 280px; height: 280px; border-radius: 36px;
  background: #09090b; border: 1px solid rgba(255,255,255,0.10);
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}}
</style>
</head>
<body>
  <div class="frame">
    <div class="left">
      <div class="lockup">
        <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 32 32">
          <path d="{m_d}" fill="#34d399" fill-rule="evenodd"/>
        </svg>
        <span class="wm">hutch<span class="dot">.</span></span>
      </div>
      <div>
        <h1 class="headline">Your bots. Your machine.<br><span class="accent">Your rules.</span></h1>
        <p class="sub">Local-first AI assistants that run on your computer with explicit approvals and spend ceilings.</p>
      </div>
      <div class="meta">
        <span class="pill"><span class="pill-dot"></span>Development preview</span>
        <span>MIT-licensed &middot; Open source &middot; Linux</span>
      </div>
    </div>
    <div class="right">
      <svg xmlns="http://www.w3.org/2000/svg" width="196" height="196" viewBox="0 0 32 32">
        <path d="{m_d}" fill="#34d399" fill-rule="evenodd"/>
      </svg>
    </div>
  </div>
</body>
</html>
"""

        for fname, w, h, px, py in [
            ("og-card-1200x630.png", 1200, 630, 44, 42),
            ("github-social-preview-1280x640.png", 1280, 640, 64, 48),
        ]:
            page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
            page.set_content(build_social_card_html(w, h, px, py))
            page.wait_for_timeout(150)
            out_p = PROD_DIR / "social" / fname
            page.screenshot(path=str(out_p), omit_background=False)
            page.close()
            shutil.copyfile(out_p, PRESS_DIR / "png" / fname)

        # --- F. Comprehensive Validation Matrix Sheet (Surfaces, Themes, 200% Zoom, CVD, Print Proxy) ---
        og_b64 = base64.b64encode((PROD_DIR / "social" / "og-card-1200x630.png").read_bytes()).decode("ascii")
        gh_b64 = base64.b64encode((PROD_DIR / "social" / "github-social-preview-1280x640.png").read_bytes()).decode("ascii")
        fav16_dark_b64 = base64.b64encode((PROD_DIR / "icons" / "favicon-16x16-dark.png").read_bytes()).decode("ascii")
        fav16_light_b64 = base64.b64encode((PROD_DIR / "icons" / "favicon-16x16-light.png").read_bytes()).decode("ascii")
        apple180_b64 = base64.b64encode((PROD_DIR / "icons" / "apple-touch-icon.png").read_bytes()).decode("ascii")
        mask512_b64 = base64.b64encode((PROD_DIR / "icons" / "icon-512-maskable.png").read_bytes()).decode("ascii")

        val_html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
@font-face {{
  font-family: 'Bricolage';
  src: url(data:font/woff2;base64,{font_b64}) format('woff2');
  font-weight: 800;
}}
@font-face {{
  font-family: 'Geist';
  src: url(data:font/woff2;base64,{geist_b64}) format('woff2');
  font-weight: 100 900;
}}
@font-face {{
  font-family: 'GeistMono';
  src: url(data:font/woff2;base64,{geist_mono_b64}) format('woff2');
  font-weight: 100 900;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; padding: 28px 32px; background: #09090b; color: #ededf0;
  font-family: 'Geist', system-ui, sans-serif;
}}
h1 {{ margin: 0 0 4px 0; font-size: 20px; }}
.sub {{ margin: 0 0 20px 0; font-size: 13px; color: #a3a3ae; }}
.grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-bottom: 18px; }}
.grid-3 {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 18px; margin-bottom: 18px; }}
.card {{ background: #16161a; border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 16px; }}
.card h2 {{ margin: 0 0 12px 0; font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: #34d399; }}
.mock-nav-dark {{
  background: #09090b; border: 1px solid rgba(255,255,255,0.09); border-radius: 8px;
  padding: 12px 16px; display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px;
}}
.mock-nav-light {{
  background: #ededf0; color: #09090b; border: 1px solid rgba(0,0,0,0.12); border-radius: 8px;
  padding: 12px 16px; display: flex; align-items: center; justify-content: space-between;
}}
.wm-sm {{ font-family: 'Bricolage', sans-serif; font-weight: 800; font-size: 20px; letter-spacing: -0.03em; line-height: 1; }}
.tab-row {{ display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }}
.browser-tab-dark {{
  background: #1c1c21; border: 1px solid rgba(255,255,255,0.1); border-radius: 8px 8px 0 0;
  padding: 7px 14px; display: inline-flex; align-items: center; gap: 8px; font-size: 12px; color: #ededf0;
}}
.browser-tab-light {{
  background: #ededf0; border: 1px solid rgba(0,0,0,0.15); border-radius: 8px 8px 0 0;
  padding: 7px 14px; display: inline-flex; align-items: center; gap: 8px; font-size: 12px; color: #09090b;
}}
.pixel-inspect {{ image-rendering: pixelated; width: 64px; height: 64px; border: 1px solid rgba(255,255,255,0.2); border-radius: 4px; }}
.cvd-strip {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }}
.cvd-box {{ background: #09090b; border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 10px; text-align: center; }}
.cvd-box > span {{ display: block; font-size: 11px; color: #a3a3ae; margin-top: 6px; }}
</style>
</head>
<body>
  <!-- SVG CVD colour-matrix filters (Machado/Vienot approximations) -->
  <svg width="0" height="0" style="position:absolute">
    <defs>
      <filter id="protanopia"><feColorMatrix type="matrix" values="0.567,0.433,0,0,0 0.558,0.442,0,0,0 0,0.242,0.758,0,0 0,0,0,1,0"/></filter>
      <filter id="deuteranopia"><feColorMatrix type="matrix" values="0.625,0.375,0,0,0 0.7,0.3,0,0,0 0,0.3,0.7,0,0 0,0,0,1,0"/></filter>
      <filter id="tritanopia"><feColorMatrix type="matrix" values="0.95,0.05,0,0,0 0,0.433,0.567,0,0 0,0.475,0.525,0,0 0,0,0,1,0"/></filter>
      <filter id="achromatopsia"><feColorMatrix type="matrix" values="0.299,0.587,0.114,0,0 0.299,0.587,0.114,0,0 0.299,0.587,0.114,0,0 0,0,0,1,0"/></filter>
    </defs>
  </svg>

  <h1>Validation Matrix — Picked Mark: Direction B ("Visor Hutch") + Bricolage Grotesque 800</h1>
  <p class="sub">Real-surface simulations across dark (#09090b) &amp; light (#ededf0) themes, 16px pixel inspection, 200% zoom, OS maskable shapes, CVD matrices, print proxy, and social cards.</p>

  <div class="grid-3">
    <div class="card">
      <h2>1. Marketing &amp; Studio Header Lockups (Dark &amp; Light)</h2>
      <div class="mock-nav-dark">
        <div style="display:flex;align-items:center;gap:9px">
          <svg width="26" height="26" viewBox="0 0 32 32"><path d="{m_d}" fill="#34d399" fill-rule="evenodd"/></svg>
          <span class="wm-sm">hutch<span style="color:#34d399">.</span></span>
        </div>
        <span style="font-size:12px;color:#a3a3ae">Marketing header (26px)</span>
      </div>
      <div class="mock-nav-dark">
        <div style="display:flex;align-items:center;gap:8px">
          <svg width="22" height="22" viewBox="0 0 32 32"><path d="{m_d}" fill="#34d399" fill-rule="evenodd"/></svg>
          <span class="wm-sm" style="font-size:18px">hutch</span>
        </div>
        <span style="font-size:12px;color:#a3a3ae">Studio sidebar (22px, no dot)</span>
      </div>
      <div class="mock-nav-light">
        <div style="display:flex;align-items:center;gap:9px">
          <svg width="26" height="26" viewBox="0 0 32 32"><path d="{m_d}" fill="#047857" fill-rule="evenodd"/></svg>
          <span class="wm-sm">hutch<span style="color:#047857">.</span></span>
        </div>
        <span style="font-size:12px;color:#52525b">Light surface (emerald-700)</span>
      </div>
    </div>

    <div class="card">
      <h2>2. Browser Tabs (16px) &amp; 4x Pixel Inspection + 200% Zoom</h2>
      <div class="tab-row" style="margin-bottom:14px">
        <div class="browser-tab-dark">
          <img src="data:image/png;base64,{fav16_dark_b64}" width="16" height="16">
          <span>Hutch &mdash; Local AI Assistants</span>
        </div>
        <div class="browser-tab-light">
          <img src="data:image/png;base64,{fav16_light_b64}" width="16" height="16">
          <span>Hutch &mdash; Docs</span>
        </div>
      </div>
      <div style="display:flex;align-items:center;gap:14px">
        <div style="text-align:center">
          <img class="pixel-inspect" style="background:#09090b" src="data:image/png;base64,{fav16_dark_b64}">
          <div style="font-size:10px;color:#8e8e99;margin-top:4px">16px dark (4x)</div>
        </div>
        <div style="text-align:center">
          <img class="pixel-inspect" style="background:#ededf0" src="data:image/png;base64,{fav16_light_b64}">
          <div style="font-size:10px;color:#8e8e99;margin-top:4px">16px light (4x)</div>
        </div>
        <div style="background:#09090b;padding:10px 14px;border-radius:8px;border:1px solid rgba(255,255,255,0.08);display:flex;align-items:center;gap:12px">
          <svg width="52" height="52" viewBox="0 0 32 32"><path d="{m_d}" fill="#34d399" fill-rule="evenodd"/></svg>
          <span class="wm-sm" style="font-size:40px">hutch<span style="color:#34d399">.</span></span>
        </div>
      </div>
    </div>

    <div class="card">
      <h2>3. Apple Touch (180px) &amp; PWA Maskable OS Crops</h2>
      <div style="display:flex;align-items:center;justify-content:space-around;padding-top:8px">
        <div style="text-align:center">
          <img src="data:image/png;base64,{apple180_b64}" width="72" height="72" style="border-radius:16px;border:1px solid rgba(255,255,255,0.12)">
          <div style="font-size:11px;color:#a3a3ae;margin-top:6px">iOS 180px</div>
        </div>
        <div style="text-align:center">
          <img src="data:image/png;base64,{mask512_b64}" width="72" height="72" style="border-radius:50%;border:1px solid rgba(255,255,255,0.12)">
          <div style="font-size:11px;color:#a3a3ae;margin-top:6px">Circle mask</div>
        </div>
        <div style="text-align:center">
          <img src="data:image/png;base64,{mask512_b64}" width="72" height="72" style="border-radius:28%;border:1px solid rgba(255,255,255,0.12)">
          <div style="font-size:11px;color:#a3a3ae;margin-top:6px">Squircle mask</div>
        </div>
        <div style="text-align:center">
          <img src="data:image/png;base64,{mask512_b64}" width="72" height="72" style="border-radius:50% 50% 14% 50%;border:1px solid rgba(255,255,255,0.12)">
          <div style="font-size:11px;color:#a3a3ae;margin-top:6px">Teardrop mask</div>
        </div>
      </div>
    </div>
  </div>

  <div class="grid-2">
    <div class="card">
      <h2>4. Colour Vision Deficiency (CVD) Simulation — Silhouette &amp; Non-Colour Redundancy</h2>
      <div class="cvd-strip">
        <div class="cvd-box">
          <div style="filter:url(#protanopia);display:flex;align-items:center;justify-content:center;gap:8px">
            <svg width="36" height="36" viewBox="0 0 32 32"><path d="{m_d}" fill="#34d399" fill-rule="evenodd"/></svg>
            <span class="wm-sm">hutch<span style="color:#34d399">.</span></span>
          </div>
          <span>Protanopia</span>
        </div>
        <div class="cvd-box">
          <div style="filter:url(#deuteranopia);display:flex;align-items:center;justify-content:center;gap:8px">
            <svg width="36" height="36" viewBox="0 0 32 32"><path d="{m_d}" fill="#34d399" fill-rule="evenodd"/></svg>
            <span class="wm-sm">hutch<span style="color:#34d399">.</span></span>
          </div>
          <span>Deuteranopia</span>
        </div>
        <div class="cvd-box">
          <div style="filter:url(#tritanopia);display:flex;align-items:center;justify-content:center;gap:8px">
            <svg width="36" height="36" viewBox="0 0 32 32"><path d="{m_d}" fill="#34d399" fill-rule="evenodd"/></svg>
            <span class="wm-sm">hutch<span style="color:#34d399">.</span></span>
          </div>
          <span>Tritanopia</span>
        </div>
        <div class="cvd-box">
          <div style="filter:url(#achromatopsia);display:flex;align-items:center;justify-content:center;gap:8px">
            <svg width="36" height="36" viewBox="0 0 32 32"><path d="{m_d}" fill="#34d399" fill-rule="evenodd"/></svg>
            <span class="wm-sm">hutch<span style="color:#34d399">.</span></span>
          </div>
          <span>Achromatopsia</span>
        </div>
      </div>
    </div>

    <div class="card">
      <h2>5. Print &amp; Grayscale Proxy (Light Document Surface #ededf0 / #ffffff)</h2>
      <div style="background:#ffffff;color:#09090b;border-radius:8px;padding:12px 18px;display:flex;align-items:center;justify-content:space-around">
        <div style="display:flex;align-items:center;gap:8px">
          <svg width="34" height="34" viewBox="0 0 32 32"><path d="{m_d}" fill="#047857" fill-rule="evenodd"/></svg>
          <span class="wm-sm">hutch<span style="color:#047857">.</span></span>
        </div>
        <div style="display:flex;align-items:center;gap:8px">
          <svg width="34" height="34" viewBox="0 0 32 32"><path d="{m_d}" fill="#065f46" fill-rule="evenodd"/></svg>
          <span class="wm-sm">hutch<span style="color:#065f46">.</span></span>
        </div>
        <div style="display:flex;align-items:center;gap:8px">
          <svg width="34" height="34" viewBox="0 0 32 32"><path d="{m_d}" fill="#09090b" fill-rule="evenodd"/></svg>
          <span class="wm-sm">hutch.</span>
        </div>
      </div>
    </div>
  </div>

  <div class="grid-2" style="margin-bottom:0">
    <div class="card">
      <h2>6. Open Graph Social Card (1200x630 Rendered Asset)</h2>
      <img src="data:image/png;base64,{og_b64}" style="width:100%;border-radius:8px;border:1px solid rgba(255,255,255,0.08)">
    </div>
    <div class="card">
      <h2>7. GitHub Repository Social Preview (1280x640 Rendered Asset)</h2>
      <img src="data:image/png;base64,{gh_b64}" style="width:100%;border-radius:8px;border:1px solid rgba(255,255,255,0.08)">
    </div>
  </div>
</body>
</html>
"""
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page.set_content(val_html)
        page.wait_for_timeout(150)
        page.screenshot(path=str(PROD_DIR / "validation-sheet.png"), full_page=True)
        page.close()

        browser.close()


# ---------------------------------------------------------------------------
# 7. Write Web App Manifest (site.webmanifest) & Measure Inventory Hashes
# ---------------------------------------------------------------------------

def write_manifest_and_summary() -> None:
    manifest = {
        "name": "Hutch",
        "short_name": "Hutch",
        "description": "Local-first AI assistants. Your bots. Your machine. Your rules.",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#09090b",
        "theme_color": "#09090b",
        "icons": [
            {"src": "icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": "icons/icon-192-maskable.png", "sizes": "192x192", "type": "image/png", "purpose": "maskable"},
            {"src": "icons/icon-512-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
            {"src": "icons/icon-192-monochrome.png", "sizes": "192x192", "type": "image/png", "purpose": "monochrome"},
            {"src": "icons/icon-512-monochrome.png", "sizes": "512x512", "type": "image/png", "purpose": "monochrome"},
        ],
    }
    (PROD_DIR / "site.webmanifest").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    # Compute sha256 and byte sizes of all generated production and press-kit files
    records = []
    for root in [PROD_DIR, PRESS_DIR]:
        for f in sorted(root.rglob("*")):
            if f.is_file():
                rel = f.relative_to(HERE)
                h = hashlib.sha256(f.read_bytes()).hexdigest()
                records.append((str(rel), f.stat().st_size, h[:16], h))

    summary_path = PROD_DIR / "PACKAGE-MANIFEST.json"
    summary_path.write_text(
        json.dumps(
            [{"path": r[0], "bytes": r[1], "sha256_prefix": r[2], "sha256": r[3]} for r in records],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Generated {len(records)} files across production/ and press-kit/.")
    for r in records:
        print(f"  {r[0]:52s} {r[1]:8d} B  {r[2]}")


def main() -> None:
    build_font_subsets()
    meta = write_svg_files()
    render_all_rasters(meta)
    write_manifest_and_summary()


if __name__ == "__main__":
    main()
