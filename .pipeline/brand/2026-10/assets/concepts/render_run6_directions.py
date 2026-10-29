#!/usr/bin/env python3
"""Run 6 clean-sheet mark construction sheets and full surface test matrix.
Synthesizes the maintainer's triad brief:
  1. Grokbot (minimalist mouthless bot, expressive inward-tilted +/-8 deg oval eyes / recessed visor)
  2. Pac-Man Ghost (domed/hooded silhouette with tangent-continuous 3-post / 2-arch scalloped skirt)
  3. Meaning of "hutch" (protective timber shelter/coop/burrow raised on stile legs housing the colony)
Built to PRINCIPLES.md R1-R11 on a 32-unit grid (4-unit module) with Bricolage Grotesque 800 lockups.
Outputs:
  - sheets/run6-direction-a-construction.png
  - sheets/run6-direction-b-construction.png
  - sheets/run6-test-matrix.png
"""
from __future__ import annotations

import base64
import math
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
FONT_PATH = HERE / "fonts" / "BricolageGrotesque-var.ttf"
SHEETS_DIR = HERE / "sheets"
SHEETS_DIR.mkdir(parents=True, exist_ok=True)


def oval_path(cx: float, cy: float, rx: float, ry: float, deg: float = 0.0) -> str:
    """Cubic-bezier closed path for an ellipse rotated by `deg` degrees around (cx, cy)."""
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
    """Tangent-continuous 3-foot / 2-burrow-arch Pac-Man/hutch base from (x_right, y_start) to (x_left, y_start).
    Total span = x_right - x_left = 3 * foot_w + 2 * arch_w.
    Each foot has radius rf = foot_w / 2; each burrow arch has radius ra = arch_w / 2.
    """
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


# ---------------------------------------------------------------------------
# DIRECTION A: "Gable Ghost" (Pitched Hutch Eaves + Knocked-Out Grokbot Eyes + 3-Foot Burrow Skirt)
# ---------------------------------------------------------------------------

def dir_a_master_d() -> str:
    # Wall span x = 4.40 .. 27.60 (23.20u = 3 * 4.40u feet + 2 * 5.00u burrow arches)
    # Roof peak optical overshoot to y=3.65 (quadratic apex Q 16.00 3.00 -> peak y=3.65, 0.35u overshoot above y=4.0)
    # Foot tips optical overshoot to y=28.30 (0.30u overshoot below y=28.0)
    base_skirt = skirt_bottom_d(x_left=4.40, x_right=27.60, y_foot=28.30, foot_w=4.40, arch_top_y=22.60)
    outer = (
        "M 13.80 4.30 "
        "Q 16.00 3.00 18.20 4.30 "
        "L 28.90 10.65 "
        "C 29.65 11.10 29.40 12.20 28.50 12.20 "
        "L 27.60 12.20 "
        f"{base_skirt}"
        "L 4.40 12.20 "
        "L 3.50 12.20 "
        "C 2.60 12.20 2.35 11.10 3.10 10.65 "
        "Z"
    )
    # Grokbot inward-tilted (-8 / +8 deg) vertical oval eyes nestled in the upper gable loft
    left_eye = oval_path(11.40, 14.10, 2.35, 3.05, -8.0)
    right_eye = oval_path(20.60, 13.80, 2.35, 3.05, 8.0)
    return f"{outer} {left_eye} {right_eye}"


def dir_a_small_d() -> str:
    # Small master (16-24px): fuller bleed (walls x=4.00..28.00 = 24.00u: 3 * 4.40u feet + 2 * 5.40u arches)
    # Roof ridge overshoot to y=2.80, foot tips to y=29.20, enlarged eyes (rx=2.65, ry=3.35)
    base_skirt = skirt_bottom_d(x_left=4.00, x_right=28.00, y_foot=29.20, foot_w=4.40, arch_top_y=22.40)
    outer = (
        "M 13.50 3.50 "
        "Q 16.00 2.10 18.50 3.50 "
        "L 29.40 10.20 "
        "C 30.20 10.70 29.90 12.00 28.90 12.00 "
        "L 28.00 12.00 "
        f"{base_skirt}"
        "L 4.00 12.00 "
        "L 3.10 12.00 "
        "C 2.10 12.00 1.80 10.70 2.60 10.20 "
        "Z"
    )
    left_eye = oval_path(11.20, 13.90, 2.65, 3.35, -8.0)
    right_eye = oval_path(20.80, 13.60, 2.65, 3.35, 8.0)
    return f"{outer} {visor_or_empty()} {left_eye} {right_eye}".replace("  ", " ")


def visor_or_empty() -> str:
    return ""


# ---------------------------------------------------------------------------
# DIRECTION B: "Visor Hutch" (Domed Ghost-Hutch Shell + Recessed Loft Visor + Positive Grokbot Eyes)
# ---------------------------------------------------------------------------

def dir_b_master_d() -> str:
    # Outer shell x = 4.00 .. 28.00 (24.00u = 3 * 4.40u feet + 2 * 5.40u burrow arches)
    # Dome crown at (16.00, 3.70) [0.30u optical overshoot above y=4.0], feet at y=28.30 [0.30u below y=28.0]
    base_skirt = skirt_bottom_d(x_left=4.00, x_right=28.00, y_foot=28.30, foot_w=4.40, arch_top_y=22.60)
    outer = (
        "M 16.00 3.70 "
        "C 23.10 3.70 28.00 8.50 28.00 15.20 "
        f"{base_skirt}"
        "L 4.00 15.20 "
        "C 4.00 8.50 8.90 3.70 16.00 3.70 Z"
    )
    # Recessed hutch loft / Grokbot visor cutout: x=6.80..25.20 (18.40u wide), y=8.60..18.40 (9.80u tall)
    visor = rounded_visor_path(6.80, 8.60, 25.20, 18.40, 5.40, 3.60)
    # Positive-space Grokbot inward-tilted oval eyes gleaming inside the dark visor loft
    left_eye = oval_path(12.20, 13.70, 2.05, 2.65, -8.0)
    right_eye = oval_path(19.80, 13.40, 2.05, 2.65, 8.0)
    return f"{outer} {visor} {left_eye} {right_eye}"


def dir_b_small_d() -> str:
    # Small master (16-24px): fuller bleed x=3.00..29.00 (26.00u = 3 * 4.80u feet + 2 * 5.80u arches)
    # Visor x=6.20..25.80 (19.60u wide), y=7.60..18.60 (11.00u tall) -> >=2.85u moat around both eyes
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


def build_grid_svg(path_d: str, annotations_svg: str, size: int = 380) -> str:
    """Render a 32x32 construction grid (1-unit minor lines, 4-unit module lines, optical bounds, and annotations)."""
    grid_lines = []
    for i in range(33):
        is_mod = (i % 4 == 0)
        is_center = (i == 16)
        stroke = "rgba(52, 211, 153, 0.38)" if is_center else ("rgba(255,255,255,0.16)" if is_mod else "rgba(255,255,255,0.05)")
        sw = "0.14" if is_center else ("0.10" if is_mod else "0.05")
        grid_lines.append(f'<line x1="{i}" y1="0" x2="{i}" y2="32" stroke="{stroke}" stroke-width="{sw}"/>')
        grid_lines.append(f'<line x1="0" y1="{i}" x2="32" y2="{i}" stroke="{stroke}" stroke-width="{sw}"/>')
    # Nominal 4..28 box
    grid_lines.append(
        '<rect x="4" y="4" width="24" height="24" fill="none" stroke="rgba(96, 165, 250, 0.45)" '
        'stroke-width="0.12" stroke-dasharray="0.5 0.4"/>'
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="-2 -2 36 36" '
        f'style="background:#09090b;border:1px solid rgba(255,255,255,0.12);border-radius:10px">'
        f'{"".join(grid_lines)}'
        f'<path d="{path_d}" fill="rgba(52, 211, 153, 0.24)" stroke="#34d399" stroke-width="0.22" fill-rule="evenodd"/>'
        f'{annotations_svg}'
        f'</svg>'
    )


def render_construction_sheet(
    title: str,
    subtitle: str,
    master_d: str,
    small_d: str,
    master_annot: str,
    small_annot: str,
    spec_rows: list[tuple[str, str, str, str]],
    out_path: Path,
) -> None:
    rows_html = "".join(
        f"<tr><td>{param}</td><td><code>{m_val}</code></td><td><code>{s_val}</code></td><td>{note}</td></tr>"
        for param, m_val, s_val, note in spec_rows
    )
    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{
    margin: 0; padding: 28px 32px; background: #09090b; color: #ededf0;
    font-family: ui-sans-serif, system-ui, -apple-system, sans-serif;
  }}
  h1 {{ margin: 0 0 6px 0; font-size: 20px; font-weight: 700; color: #ededf0; }}
  .sub {{ margin: 0 0 20px 0; font-size: 13px; color: #a3a3ae; }}
  .top {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 22px; }}
  .panel {{ background: #16161a; border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 18px; }}
  .panel h2 {{ margin: 0 0 12px 0; font-size: 14px; color: #34d399; text-transform: uppercase; letter-spacing: 0.06em; }}
  .panel-body {{ display: flex; gap: 18px; align-items: center; }}
  .legend {{ font-size: 12px; color: #a3a3ae; line-height: 1.55; }}
  .legend strong {{ color: #ededf0; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12.5px; background: #16161a; border-radius: 10px; overflow: hidden; }}
  th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid rgba(255,255,255,0.07); }}
  th {{ background: #1c1c21; color: #ededf0; font-weight: 600; }}
  code {{ font-family: ui-monospace, monospace; color: #34d399; font-size: 12px; }}
</style>
</head>
<body>
  <h1>{title}</h1>
  <p class="sub">{subtitle}</p>
  <div class="top">
    <div class="panel">
      <h2>Master Tier (&gt;= 32px) — 32x32 Grid (4u Module)</h2>
      <div class="panel-body">
        {build_grid_svg(master_d, master_annot, 360)}
        <div class="legend">
          <p><strong>Blue dashed box:</strong> Nominal 24x24 metric frame (<code>x=4..28, y=4..28</code>)</p>
          <p><strong>Optical overshoots (R3):</strong> Crown peaks above <code>y=4.0</code>; rounded feet extend to <code>y=28.30</code> (+0.30u)</p>
          <p><strong>Grokbot eye tilt:</strong> Left <code>-8°</code>, Right <code>+8°</code> with <code>0.30u</code> upward right-eye offset (attentive gaze toward wordmark)</p>
          <p><strong>Pac-Man / Hutch base:</strong> 3 grounded timber posts (<code>x=16</code> center post down) + 2 concave burrow arches</p>
        </div>
      </div>
    </div>
    <div class="panel">
      <h2>Small Tier (16–24px, Redrawn R6) — 32x32 Grid</h2>
      <div class="panel-body">
        {build_grid_svg(small_d, small_annot, 360)}
        <div class="legend">
          <p><strong>Redrawn, never scaled (R6):</strong> Expanded outer bleed and widened interior counterforms</p>
          <p><strong>Counterform floor (R5):</strong> Every interior gap &gt;= <code>2.85u</code> on 32u grid (&gt;= <code>1.42px</code> at 16x16px)</p>
          <p><strong>Compound path:</strong> Single <code>&lt;path fill-rule="evenodd"&gt;</code>, zero stroke dependency, 1-colour mono ready (R8)</p>
        </div>
      </div>
    </div>
  </div>
  <table>
    <thead>
      <tr><th>Geometric Parameter</th><th>Master Tier (&gt;=32px)</th><th>Small Tier (16–24px)</th><th>Rule / Rationale (R1–R11)</th></tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
</body>
</html>
"""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1380, "height": 860}, device_scale_factor=2)
        page.set_content(html)
        page.wait_for_timeout(120)
        page.screenshot(path=str(out_path), full_page=True)
        browser.close()
    print("Wrote", out_path)


def svg_inline(d: str, w: int, h: int, fg: str, bg: str | None = None, rx: float = 0, extra_style: str = "") -> str:
    bg_el = f'<rect width="32" height="32" rx="{rx}" fill="{bg}"/>' if bg else ""
    style_attr = f' style="{extra_style}"' if extra_style else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 32 32"{style_attr}>'
        f'{bg_el}<path d="{d}" fill="{fg}" fill-rule="evenodd"/></svg>'
    )


def svg_maskable(d: str, w: int, fg: str, bg: str, show_guide: bool = False) -> str:
    # Maskable icon: mark scaled to 72% inside 32x32 so it sits comfortably inside the 40%-radius (r=12.8) W3C safe zone
    guide = (
        '<circle cx="16" cy="16" r="12.8" fill="none" stroke="#fbbf24" stroke-width="0.35" stroke-dasharray="0.8 0.6"/>'
        if show_guide else ""
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{w}" viewBox="0 0 32 32">'
        f'<rect width="32" height="32" fill="{bg}"/>'
        f'<g transform="translate(4.48, 4.48) scale(0.72)"><path d="{d}" fill="{fg}" fill-rule="evenodd"/></g>'
        f'{guide}</svg>'
    )


def main() -> None:
    a_m, a_s = dir_a_master_d(), dir_a_small_d()
    b_m, b_s = dir_b_master_d(), dir_b_small_d()

    # Annotations for Direction A
    a_m_annot = (
        '<line x1="2.6" y1="12.2" x2="29.4" y2="12.2" stroke="#fbbf24" stroke-width="0.12" stroke-dasharray="0.4 0.3"/>'
        '<circle cx="16.0" cy="3.65" r="0.35" fill="#fbbf24"/>'
        '<circle cx="11.4" cy="14.1" r="0.30" fill="#60a5fa"/>'
        '<circle cx="20.6" cy="13.8" r="0.30" fill="#60a5fa"/>'
        '<line x1="4.4" y1="28.3" x2="27.6" y2="28.3" stroke="#f87171" stroke-width="0.12" stroke-dasharray="0.4 0.3"/>'
    )
    a_s_annot = (
        '<circle cx="16.0" cy="2.80" r="0.35" fill="#fbbf24"/>'
        '<circle cx="11.2" cy="13.9" r="0.30" fill="#60a5fa"/>'
        '<circle cx="20.8" cy="13.6" r="0.30" fill="#60a5fa"/>'
        '<line x1="4.0" y1="29.2" x2="28.0" y2="29.2" stroke="#f87171" stroke-width="0.12" stroke-dasharray="0.4 0.3"/>'
    )
    a_specs = [
        ("Canvas / Module", "32x32 (4u module)", "32x32 (4u module)", "R3 grid discipline"),
        ("Roof Ridge Peak (Overshoot)", "(16.00, 3.65) [Q 16.0, 3.0]", "(16.00, 2.80) [Q 16.0, 2.1]", "R1 hutch gable + R3 +0.35u optical overshoot"),
        ("Projecting Eaves Span", "x = 2.60 .. 29.40 (y = 12.20)", "x = 2.00 .. 30.00 (y = 12.00)", "R2 bold move: timber hutch eaves overhang (1.8u step)"),
        ("Body Wall Span", "x = 4.40 .. 27.60 (w = 23.20u)", "x = 4.00 .. 28.00 (w = 24.00u)", "1:1 square optical balance alongside Bricolage 800"),
        ("Grokbot Left Eye (cx, cy, rx, ry, rot)", "(11.40, 14.10), 2.35 x 3.05, -8°", "(11.20, 13.90), 2.65 x 3.35, -8°", "Grokbot / app.js ID_FACES inward tilt; knocked out"),
        ("Grokbot Right Eye (cx, cy, rx, ry, rot)", "(20.60, 13.80), 2.35 x 3.05, +8°", "(20.80, 13.60), 2.65 x 3.35, +8°", "+0.30u upward gaze offset toward wordmark"),
        ("Inter-Eye Bridge / Wall Margin", "4.50u bridge / 4.65u wall", "4.30u bridge / 4.55u wall", "R5 counterform >= 2.0u master, >= 2.5u small"),
        ("3-Post Foot Width / Tip Y", "3 x 4.40u (rf=2.20u), y=28.30", "3 x 4.40u (rf=2.20u), y=29.20", "Matches Bricolage 800 stem weight; center post prevents mouth read"),
        ("Twin Burrow Arches (Span / Apex)", "2 x 5.00u (ra=2.50u), y=22.60", "2 x 5.40u (ra=2.70u), y=22.40", "Pac-Man ghost skirt + twin hutch burrow openings"),
    ]
    render_construction_sheet(
        "Direction A — 'Gable Ghost' (Construction Sheet)",
        "Synthesis: Timber hutch pitched gable & eaves + Grokbot inward-tilted oval eyes + Pac-Man ghost 3-post/2-burrow skirt",
        a_m,
        a_s,
        a_m_annot,
        a_s_annot,
        a_specs,
        SHEETS_DIR / "run6-direction-a-construction.png",
    )

    # Annotations for Direction B
    b_m_annot = (
        '<rect x="6.80" y="8.60" width="18.40" height="9.80" rx="3.60" fill="none" stroke="#fbbf24" stroke-width="0.12" stroke-dasharray="0.4 0.3"/>'
        '<circle cx="16.0" cy="3.70" r="0.35" fill="#fbbf24"/>'
        '<circle cx="12.2" cy="13.7" r="0.30" fill="#60a5fa"/>'
        '<circle cx="19.8" cy="13.4" r="0.30" fill="#60a5fa"/>'
        '<line x1="4.0" y1="28.3" x2="28.0" y2="28.3" stroke="#f87171" stroke-width="0.12" stroke-dasharray="0.4 0.3"/>'
    )
    b_s_annot = (
        '<rect x="6.20" y="7.60" width="19.60" height="11.00" rx="3.80" fill="none" stroke="#fbbf24" stroke-width="0.12" stroke-dasharray="0.4 0.3"/>'
        '<circle cx="16.0" cy="2.80" r="0.35" fill="#fbbf24"/>'
        '<circle cx="12.0" cy="13.25" r="0.30" fill="#60a5fa"/>'
        '<circle cx="20.0" cy="13.00" r="0.30" fill="#60a5fa"/>'
        '<line x1="3.0" y1="29.2" x2="29.0" y2="29.2" stroke="#f87171" stroke-width="0.12" stroke-dasharray="0.4 0.3"/>'
    )
    b_specs = [
        ("Canvas / Module", "32x32 (4u module)", "32x32 (4u module)", "R3 grid discipline"),
        ("Hooded Dome Crown (Overshoot)", "(16.00, 3.70), w = 24.00u", "(16.00, 2.80), w = 26.00u", "Pac-Man ghost / hooded hutch dome (+0.30u overshoot)"),
        ("Recessed Loft Visor Cutout", "x=6.80..25.20, y=8.60..18.40", "x=6.20..25.80, y=7.60..18.60", "R2 bold move: hutch upper loft / Grokbot visor bay"),
        ("Visor Corner Radii (Top / Bottom)", "r_top = 5.40u, r_bot = 3.60u", "r_top = 5.80u, r_bot = 3.80u", "Follows outer dome curve above and horizontal rail below"),
        ("Positive Grokbot Left Eye", "(12.20, 13.70), 2.05 x 2.65, -8°", "(12.00, 13.25), 2.15 x 2.65, -8°", "Positive island inside evenodd visor hole; 1-colour mono safe"),
        ("Positive Grokbot Right Eye", "(19.80, 13.40), 2.05 x 2.65, +8°", "(20.00, 13.00), 2.15 x 2.65, +8°", "+0.30u upward gaze offset toward wordmark"),
        ("Visor Moat Clearances", "3.50u bridge / 3.35u side / 2.45u vert", "3.70u bridge / 3.65u side / 2.85u vert", "R5 counterform survives 16px cleanly without plugging"),
        ("3-Post Foot Width / Tip Y", "3 x 4.40u (rf=2.20u), y=28.30", "3 x 4.80u (rf=2.40u), y=29.20", "Matches Bricolage 800 stem weight; grounded center post"),
        ("Twin Burrow Arches (Span / Apex)", "2 x 5.40u (ra=2.70u), y=22.60", "2 x 5.80u (ra=2.90u), y=22.50", "Tangent-continuous Pac-Man ghost skirt + twin hutch burrows"),
    ]
    render_construction_sheet(
        "Direction B — 'Visor Hutch' (Construction Sheet)",
        "Synthesis: Hooded ghost-hutch shell + recessed hutch-loft/Grokbot visor + twin positive bot eyes + 3-post/2-burrow skirt",
        b_m,
        b_s,
        b_m_annot,
        b_s_annot,
        b_specs,
        SHEETS_DIR / "run6-direction-b-construction.png",
    )

    # Now build the comprehensive Test Matrix comparing Direction A and Direction B across all required cells
    font_b64 = base64.b64encode(FONT_PATH.read_bytes()).decode("ascii")

    def matrix_row_html(name: str, tag: str, m_d: str, s_d: str) -> str:
        return f"""
        <div class="dir-block">
          <div class="dir-head">
            <h2>{name}</h2>
            <span>{tag}</span>
          </div>
          <div class="matrix-grid">
            <div class="cell dark">
              <div class="cell-title">16px Dark + Light (Small Tier)</div>
              <div class="inline-pair">
                <div class="swatch-dark">{svg_inline(s_d, 16, 16, "#34d399")}</div>
                <div class="swatch-light">{svg_inline(s_d, 16, 16, "#09090b")}</div>
                <div class="swatch-dark">{svg_inline(s_d, 24, 24, "#34d399")}</div>
              </div>
              <div class="caption">16px dark (#34d399), 16px light (#09090b), 24px small</div>
            </div>
            <div class="cell dark">
              <div class="cell-title">32px &amp; 48px (Master Tier)</div>
              <div class="inline-pair">
                {svg_inline(m_d, 32, 32, "#34d399")}
                {svg_inline(m_d, 48, 48, "#34d399")}
              </div>
              <div class="caption">Dashboard header (22-26px) &amp; launcher sizes</div>
            </div>
            <div class="cell dark">
              <div class="cell-title">512px App Icon (Scaled)</div>
              <div class="inline-pair">
                {svg_inline(m_d, 84, 84, "#34d399", "#09090b", 7)}
              </div>
              <div class="caption">512x512 master on ink-950 (#09090b)</div>
            </div>
            <div class="cell dark">
              <div class="cell-title">Maskable Crop (40%r Safe Zone)</div>
              <div class="inline-pair">
                {svg_maskable(m_d, 76, "#34d399", "#09090b", True)}
                <div style="border-radius:50%;overflow:hidden;width:68px;height:68px;display:flex">{svg_maskable(m_d, 68, "#34d399", "#09090b", False)}</div>
              </div>
              <div class="caption">W3C 80% safe circle + full circle mask</div>
            </div>
            <div class="cell dark">
              <div class="cell-title">Mono &amp; Squint Blur (R7/R8)</div>
              <div class="inline-pair">
                <div class="swatch-dark">{svg_inline(m_d, 44, 44, "#ededf0")}</div>
                <div class="swatch-light">{svg_inline(m_d, 44, 44, "#09090b")}</div>
                <div class="swatch-dark">{svg_inline(m_d, 44, 44, "#ededf0", extra_style="filter:blur(2.2px)")}</div>
              </div>
              <div class="caption">1-colour currentColor + squint blur</div>
            </div>
            <div class="cell light">
              <div class="cell-title" style="color:#09090b">Print &amp; Grayscale Proxy (R8)</div>
              <div class="inline-pair">
                {svg_inline(m_d, 44, 44, "#047857")}
                {svg_inline(m_d, 44, 44, "#065f46")}
                {svg_inline(m_d, 44, 44, "#27272a")}
              </div>
              <div class="caption" style="color:#52525b">emerald-700, emerald-800, grayscale</div>
            </div>
          </div>
          <div class="lockup-strip">
            <div class="lockup-dark">
              {svg_inline(m_d, 38, 38, "#34d399")}
              <span class="wm-text">hutch<span class="wm-dot-dark">.</span></span>
            </div>
            <div class="lockup-dark">
              {svg_inline(m_d, 38, 38, "#ededf0")}
              <span class="wm-text">hutch<span class="wm-dot-dark">.</span></span>
            </div>
            <div class="lockup-light">
              {svg_inline(m_d, 38, 38, "#09090b")}
              <span class="wm-text-light">hutch<span class="wm-dot-light">.</span></span>
            </div>
            <div class="lockup-light">
              {svg_inline(m_d, 38, 38, "#047857")}
              <span class="wm-text-light">hutch<span class="wm-dot-light">.</span></span>
            </div>
          </div>
        </div>
        """

    matrix_html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
@font-face {{
  font-family: 'Bricolage';
  src: url(data:font/ttf;base64,{font_b64}) format('truetype');
  font-weight: 100 900;
}}
body {{
  margin: 0; padding: 28px 32px; background: #09090b; color: #ededf0;
  font-family: ui-sans-serif, system-ui, -apple-system, sans-serif;
}}
h1 {{ margin: 0 0 4px 0; font-size: 20px; }}
.lead {{ margin: 0 0 22px 0; font-size: 13px; color: #a3a3ae; }}
.dir-block {{
  background: #16161a; border: 1px solid rgba(255,255,255,0.08);
  border-radius: 14px; padding: 20px; margin-bottom: 24px;
}}
.dir-head {{ display: flex; align-items: baseline; gap: 14px; margin-bottom: 14px; }}
.dir-head h2 {{ margin: 0; font-size: 17px; color: #34d399; }}
.dir-head span {{ font-size: 13px; color: #a3a3ae; }}
.matrix-grid {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin-bottom: 14px; }}
.cell {{ border-radius: 10px; padding: 12px; display: flex; flex-direction: column; justify-content: space-between; min-height: 128px; }}
.cell.dark {{ background: #09090b; border: 1px solid rgba(255,255,255,0.07); }}
.cell.light {{ background: #ededf0; border: 1px solid rgba(0,0,0,0.1); }}
.cell-title {{ font-size: 11px; font-weight: 600; color: #a3a3ae; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 8px; }}
.inline-pair {{ display: flex; align-items: center; justify-content: center; gap: 12px; flex: 1; }}
.swatch-dark {{ background: #09090b; padding: 8px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.08); display: flex; }}
.swatch-light {{ background: #ededf0; padding: 8px; border-radius: 6px; display: flex; }}
.caption {{ font-size: 11px; color: #8e8e99; margin-top: 8px; text-align: center; }}
.lockup-strip {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }}
.lockup-dark {{
  background: #09090b; border: 1px solid rgba(255,255,255,0.07); border-radius: 10px;
  padding: 14px 18px; display: flex; align-items: center; justify-content: center; gap: 12px;
}}
.lockup-light {{
  background: #ededf0; border-radius: 10px;
  padding: 14px 18px; display: flex; align-items: center; justify-content: center; gap: 12px;
}}
.wm-text {{ font-family: 'Bricolage', sans-serif; font-weight: 800; font-size: 34px; letter-spacing: -0.03em; color: #ededf0; line-height: 1; }}
.wm-text-light {{ font-family: 'Bricolage', sans-serif; font-weight: 800; font-size: 34px; letter-spacing: -0.03em; color: #09090b; line-height: 1; }}
.wm-dot-dark {{ color: #34d399; }}
.wm-dot-light {{ color: #047857; }}
</style>
</head>
<body>
  <h1>Run 6 — Clean-Sheet Mark Test Matrix (Grokbot + Pac-Man Ghost + Hutch Shelter)</h1>
  <p class="lead">Tested across 16px light/dark (DPR2), 24/32/48px, 512px app icon, W3C maskable 40%r safe zone, 1-colour mono, squint blur, Bricolage Grotesque 800 lockups, and print proxies.</p>
  {matrix_row_html("Direction A: 'Gable Ghost'", "Pitched timber-hutch eaves overhang + knocked-out tilted Grokbot oval eyes + 3-post/2-burrow Pac-Man skirt", a_m, a_s)}
  {matrix_row_html("Direction B: 'Visor Hutch'", "Hooded ghost-hutch dome + recessed Grokbot visor loft bay + twin positive bot eyes + 3-post/2-burrow skirt", b_m, b_s)}
</body>
</html>
"""
    out_matrix = SHEETS_DIR / "run6-test-matrix.png"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1420, "height": 780}, device_scale_factor=2)
        page.set_content(matrix_html)
        page.wait_for_timeout(150)
        page.screenshot(path=str(out_matrix), full_page=True)
        browser.close()
    print("Wrote", out_matrix)


if __name__ == "__main__":
    main()
