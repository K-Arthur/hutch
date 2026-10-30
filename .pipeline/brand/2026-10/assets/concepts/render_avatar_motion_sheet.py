#!/usr/bin/env python3
"""Verify (via Chromium Path2D at every keyframe extreme) and render the 5-State
Motion & Expression Choreography Sheet for 'The Hutch Colony' 8-resident avatar system.
"""

from __future__ import annotations

from pathlib import Path
from playwright.sync_api import sync_playwright

from render_avatar_family import ID_COLORS, NEW_FACES, NEW_HEADS, render_eye_path

ROOT = Path("/home/kevina/CodingProjects/hutch")
OUT_DIR = ROOT / ".pipeline/brand/2026-10/evidence/avatars"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def render_posed_svg(
    shape_idx: int,
    color: str,
    body_tx: float = 0.0,
    body_ty: float = 0.0,
    body_rot: float = 0.0,
    body_sx: float = 1.0,
    body_sy: float = 1.0,
    eyes_tx: float = 0.0,
    eyes_ty: float = 0.0,
    eyes_sx: float = 1.0,
    eyes_sy: float = 1.0,
    left_extra_rot: float = 0.0,
    right_extra_rot: float = 0.0,
    right_extra_scale: float = 1.0,
    show_motion_vectors: bool = False,
) -> str:
    head_d = NEW_HEADS[shape_idx]["d"]
    left, right = [list(x) for x in NEW_FACES[shape_idx]]
    left[4] += left_extra_rot
    right[4] += right_extra_rot
    right[2] = round(right[2] * right_extra_scale, 3)
    right[3] = round(right[3] * right_extra_scale, 3)

    cx_mid = (left[0] + right[0]) / 2.0
    cy_mid = (left[1] + right[1]) / 2.0

    body_transform = (
        f"translate({32 + body_tx} {55 + body_ty}) "
        f"rotate({body_rot}) scale({body_sx} {body_sy}) translate(-32 -55)"
    )
    eyes_transform = (
        f"translate({cx_mid + eyes_tx} {cy_mid + eyes_ty}) "
        f"scale({eyes_sx} {eyes_sy}) translate({-cx_mid} {-cy_mid})"
    )

    vectors = ""
    if show_motion_vectors and (abs(eyes_tx) > 0.1 or abs(eyes_ty) > 0.1):
        vectors = (
            f'<circle cx="{cx_mid}" cy="{cy_mid}" r="1.3" fill="none" stroke="rgba(255,255,255,0.45)" stroke-width="0.7" stroke-dasharray="1.5 1.5"/>'
            f'<line x1="{cx_mid}" y1="{cy_mid}" x2="{cx_mid + eyes_tx}" y2="{cy_mid + eyes_ty}" stroke="#0b1511" stroke-width="1.1" stroke-linecap="round"/>'
        )

    return (
        f'<svg class="sig" viewBox="0 0 64 64">'
        f'<path data-body="1" d="{head_d}" fill="{color}" transform="{body_transform}"/>'
        f'{vectors}'
        f'<g class="sig-eyes" transform="{eyes_transform}" aria-hidden="true">'
        f'{render_eye_path("left", left)}{render_eye_path("right", right)}'
        f'</g></svg>'
    )


# Keyframe extremes to verify Path2D containment across ALL 8 silhouettes
KEYFRAME_POSES = [
    ("idle", dict()),
    ("running_k1_scan_tl", dict(body_ty=-0.6, body_rot=-0.8, body_sx=0.995, body_sy=1.01, eyes_tx=-2.4, eyes_ty=-0.8, eyes_sx=1.02, eyes_sy=1.04)),
    ("running_k2_saccade_tr", dict(body_ty=-1.2, body_rot=0.8, body_sx=0.99, body_sy=1.02, eyes_tx=2.4, eyes_ty=-0.8, eyes_sx=1.02, eyes_sy=1.04)),
    ("running_k3_blink", dict(body_ty=-0.8, body_rot=0.4, eyes_tx=1.8, eyes_ty=-0.2, eyes_sx=1.04, eyes_sy=0.16)),
    ("running_k4_scan_bl", dict(body_ty=-0.3, body_rot=-0.6, eyes_tx=-2.0, eyes_ty=1.1, eyes_sx=1.0, eyes_sy=0.95)),
    ("running_k5_verify_r", dict(body_ty=-1.0, body_rot=0.6, eyes_tx=2.2, eyes_ty=0.6, eyes_sx=1.04, eyes_sy=1.02)),
    ("waiting_k1_calm", dict(eyes_tx=0.0, eyes_ty=-0.4, eyes_sx=1.04, eyes_sy=1.04)),
    ("waiting_k2_perk_up", dict(body_ty=-1.4, body_rot=2.0, body_sx=1.01, body_sy=1.02, eyes_tx=1.8, eyes_ty=-2.2, eyes_sx=1.14, eyes_sy=1.14, right_extra_scale=1.04)),
    ("waiting_k3_flutter", dict(body_ty=-1.4, body_rot=2.0, body_sx=1.01, body_sy=1.02, eyes_tx=1.8, eyes_ty=-2.0, eyes_sx=1.14, eyes_sy=0.18)),
    ("blocked_worried", dict(body_ty=0.8, body_sx=1.02, body_sy=0.97, eyes_tx=0.0, eyes_ty=2.2, eyes_sx=0.96, eyes_sy=0.68, left_extra_rot=18.0, right_extra_rot=-18.0)),
    ("paused_asleep", dict(body_ty=0.6, body_sx=1.01, body_sy=0.98, eyes_tx=0.0, eyes_ty=2.0, eyes_sx=1.08, eyes_sy=0.16)),
]


def main() -> None:
    # 1. Build Running 5-keyframe strip (shown on Resident #0 Ghost Bell & Resident #2 Hopper Hare)
    running_frames_spec = [
        ("0%–10%", "1. Scan Line Start", "eyes: (-2.4px, -0.8px) · body: -0.8°", "running_k1_scan_tl"),
        ("24%–34%", "2. Saccade Across", "eyes: (+2.4px, -0.8px) · body: +0.8° lift", "running_k2_saccade_tr"),
        ("42%", "3. Thought Blink", "eyes: scaleY(0.16) · 120ms return", "running_k3_blink"),
        ("50%–62%", "4. Inspect Next Line", "eyes: (-2.0px, +1.1px) · focused 0.95y", "running_k4_scan_bl"),
        ("76%–88%", "5. Verify Output", "eyes: (+2.2px, +0.6px) · scale(1.04)", "running_k5_verify_r"),
    ]
    pose_map = dict(KEYFRAME_POSES)

    run_strip_html = []
    for pct, title, sub, pose_key in running_frames_spec:
        svg0 = render_posed_svg(0, ID_COLORS[0], show_motion_vectors=True, **pose_map[pose_key])
        svg2 = render_posed_svg(2, ID_COLORS[2], show_motion_vectors=True, **pose_map[pose_key])
        svg7 = render_posed_svg(7, ID_COLORS[7], show_motion_vectors=True, **pose_map[pose_key])
        run_strip_html.append(f"""
        <div class="kf-card">
          <div class="kf-hdr"><span class="kf-pct">{pct}</span><span class="kf-tag">running</span></div>
          <div class="kf-trio">
            <div class="av-68">{svg0}<span class="pip running"></span></div>
            <div class="av-52">{svg2}<span class="pip running"></span></div>
            <div class="av-52">{svg7}<span class="pip running"></span></div>
          </div>
          <div class="kf-title">{title}</div>
          <div class="kf-sub">{sub}</div>
        </div>
        """)

    # 2. Build Waiting 4-keyframe strip
    waiting_frames_spec = [
        ("0% / 100%", "1. Attentive Notice", "eyes: (0, -0.4px) scale(1.04)", "waiting_k1_calm"),
        ("22%–58%", "2. Perk Up & Look to You", "eyes: (+1.8px, -2.2px) 1.14x · body +2° tilt", "waiting_k2_perk_up"),
        ("66%", "3. Expectant Flutter", "eyes: scaleY(0.18) while tilted up", "waiting_k3_flutter"),
        ("74%–86%", "4. Held Inquiry Gaze", "lead right eye +4% wider · amber pip", "waiting_k2_perk_up"),
    ]
    wait_strip_html = []
    for pct, title, sub, pose_key in waiting_frames_spec:
        svg1 = render_posed_svg(1, ID_COLORS[1], show_motion_vectors=True, **pose_map[pose_key])
        svg4 = render_posed_svg(4, ID_COLORS[4], show_motion_vectors=True, **pose_map[pose_key])
        svg5 = render_posed_svg(5, ID_COLORS[5], show_motion_vectors=True, **pose_map[pose_key])
        wait_strip_html.append(f"""
        <div class="kf-card">
          <div class="kf-hdr"><span class="kf-pct amber">{pct}</span><span class="kf-tag amber">waiting</span></div>
          <div class="kf-trio">
            <div class="av-68">{svg1}<span class="pip waiting"></span></div>
            <div class="av-52">{svg4}<span class="pip waiting"></span></div>
            <div class="av-52">{svg5}<span class="pip waiting"></span></div>
          </div>
          <div class="kf-title">{title}</div>
          <div class="kf-sub">{sub}</div>
        </div>
        """)

    # 3. Build 8 Residents x 5 States Full Matrix (40 cells + all 11 poses hidden or visible for Path2D check)
    matrix_rows = []
    state_cols = [
        ("idle", "Idle (Calm)", ""),
        ("running_k2_saccade_tr", "Working (Scan)", "running"),
        ("waiting_k2_perk_up", "Needs You (Wait)", "waiting"),
        ("blocked_worried", "Blocked (Worried)", "blocked"),
        ("paused_asleep", "Paused (Asleep)", "paused"),
    ]
    for i in range(8):
        cells = []
        for pose_key, col_lbl, pip_cls in state_cols:
            svg = render_posed_svg(i, ID_COLORS[i], **pose_map[pose_key])
            pip = f'<span class="pip {pip_cls}"></span>' if pip_cls else ""
            cells.append(f'<div class="m-cell" data-pose="{pose_key}" data-shape="{i}"><div class="av-48">{svg}{pip}</div></div>')
        matrix_rows.append(f"""
        <div class="m-row">
          <div class="m-name"><span class="m-idx">#{i}</span> {NEW_HEADS[i]['title']}</div>
          {''.join(cells)}
        </div>
        """)

    # Hidden verification container holding all 8 shapes x all 11 keyframe extremes = 88 SVGs
    verify_svgs = []
    for i in range(8):
        for pose_key, pose_kwargs in KEYFRAME_POSES:
            svg = render_posed_svg(i, ID_COLORS[i], **pose_kwargs)
            verify_svgs.append(f'<div data-verify-shape="{i}" data-verify-pose="{pose_key}">{svg}</div>')

    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: #09090b;
  color: #ededf0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  padding: 28px;
  width: 1520px;
}}
.hdr {{
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  border-bottom: 1px solid rgba(255,255,255,0.14);
  padding-bottom: 14px;
  margin-bottom: 20px;
}}
.hdr h1 {{ font-size: 20px; font-weight: 700; letter-spacing: -0.02em; }}
.hdr span {{ font-family: monospace; font-size: 12px; color: #34d399; }}
.sec-lbl {{
  font-family: monospace;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #8e8e99;
  margin-bottom: 10px;
}}
.top-grid {{
  display: grid;
  grid-template-columns: 1fr 620px;
  gap: 20px;
}}
.strips-col {{
  display: flex;
  flex-direction: column;
  gap: 18px;
}}
.strip-5 {{
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 10px;
}}
.strip-4 {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}}
.kf-card {{
  background: #0f0f12;
  border: 1px solid rgba(255,255,255,0.14);
  border-radius: 12px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}}
.kf-hdr {{
  display: flex;
  justify-content: space-between;
  font-family: monospace;
  font-size: 10.5px;
}}
.kf-pct {{ color: #34d399; font-weight: 600; }}
.kf-pct.amber {{ color: #fbbf24; }}
.kf-tag {{ color: #8e8e99; }}
.kf-tag.amber {{ color: #fbbf24; }}
.kf-trio {{
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: 8px;
  background: #16161a;
  border-radius: 8px;
  padding: 12px 8px;
}}
.av-68 {{ position: relative; width: 64px; height: 64px; flex: none; }}
.av-52 {{ position: relative; width: 46px; height: 46px; flex: none; }}
.av-48 {{ position: relative; width: 44px; height: 44px; flex: none; }}
.kf-title {{ font-size: 12.5px; font-weight: 650; color: #ededf0; }}
.kf-sub {{ font-family: monospace; font-size: 10px; line-height: 1.35; color: #a3a3ae; }}
.pip {{
  position: absolute;
  right: -2px;
  bottom: -2px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 2px solid #16161a;
}}
.pip.running {{ background: #34d399; }}
.pip.waiting {{ background: #fbbf24; }}
.pip.blocked {{ background: #f87171; }}
.pip.paused {{ background: transparent; border: 2px solid #8e8e99; }}
.matrix-card {{
  background: #0f0f12;
  border: 1px solid rgba(255,255,255,0.14);
  border-radius: 12px;
  padding: 16px;
}}
.m-head {{
  display: grid;
  grid-template-columns: 140px repeat(5, 1fr);
  gap: 8px;
  font-family: monospace;
  font-size: 10.5px;
  color: #8e8e99;
  text-align: center;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(255,255,255,0.08);
  margin-bottom: 8px;
}}
.m-head div:first-child {{ text-align: left; }}
.m-row {{
  display: grid;
  grid-template-columns: 140px repeat(5, 1fr);
  gap: 8px;
  align-items: center;
  padding: 5px 0;
  border-bottom: 1px solid rgba(255,255,255,0.05);
}}
.m-row:last-child {{ border-bottom: 0; }}
.m-name {{ font-size: 12.5px; font-weight: 600; color: #ededf0; }}
.m-idx {{ font-family: monospace; font-size: 11px; color: #8e8e99; margin-right: 4px; }}
.m-cell {{
  display: flex;
  justify-content: center;
  align-items: center;
  background: #16161a;
  border-radius: 8px;
  padding: 5px;
}}
.spec-footer {{
  margin-top: 14px;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}}
.spec-pill {{
  background: #0f0f12;
  border: 1px solid rgba(255,255,255,0.10);
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 11.5px;
  color: #a3a3ae;
  line-height: 1.4;
}}
.spec-pill b {{ color: #ededf0; }}
svg.sig {{ width: 100%; height: 100%; display: block; }}
#verify-pool {{ position: fixed; left: -9999px; top: -9999px; width: 64px; height: 64px; }}
</style>
</head>
<body>
  <div class="hdr">
    <h1>"The Hutch Colony" — 5-State Avatar Choreography &amp; Expression System (`studio.css`)</h1>
    <span>88/88 Keyframe Extremes Path2D Verified · Compositor-Only · Reduced-Motion Safe</span>
  </div>
  <div class="top-grid">
    <div class="strips-col">
      <div>
        <div class="sec-lbl">1. `data-state="running"` — Working Choreography (`3.2s` Saccadic Line Scan + 120ms Return Blink + Grounded Body Hover)</div>
        <div class="strip-5">
          {''.join(run_strip_html)}
        </div>
      </div>
      <div>
        <div class="sec-lbl">2. `data-state="waiting"` — Approval / Needs-You Choreography (`2.8s` Upward Operator Gaze + +2° Head Tilt + Expectant Flutter)</div>
        <div class="strip-4">
          {''.join(wait_strip_html)}
        </div>
      </div>
      <div class="spec-footer">
        <div class="spec-pill"><b>3. `data-state="blocked"` (Worried):</b> Eyes settle lower (`+2.2px`) and cant outward (`±18°` empathetic furrow) with a `0.97y` body settle. Reads immediately with zero motion.</div>
        <div class="spec-pill"><b>4. `data-state="paused"` (Asleep):</b> Eyes close into calm horizontal crescents (`translateY(2px) scale(1.08, 0.16)`) with a rested `0.98y` posture. Static by design.</div>
        <div class="spec-pill"><b>5. Accessibility &amp; Perf Gate:</b> GPU compositor `transform` only. Gated on `@media (prefers-reduced-motion: no-preference)` and `:root:not(.reduce-effects)`.</div>
      </div>
    </div>
    <div class="matrix-card">
      <div class="sec-lbl">All 8 Colony Residents Across All 5 Runtime States (44px Live Preview)</div>
      <div class="m-head">
        <div>Resident</div>
        <div>Idle</div>
        <div style="color:#34d399;">Working</div>
        <div style="color:#fbbf24;">Needs You</div>
        <div style="color:#f87171;">Blocked</div>
        <div>Paused</div>
      </div>
      {''.join(matrix_rows)}
    </div>
  </div>
  <div id="verify-pool">{''.join(verify_svgs)}</div>
</body>
</html>
"""

    out_png = OUT_DIR / "avatar-motion-sheet.png"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1520, "height": 840}, device_scale_factor=2)
        page.set_content(html, wait_until="networkidle")

        # Verify that for ALL 88 (shape x keyframe_pose) combinations, every transformed eye point
        # remains strictly inside the transformed head Path2D!
        results = page.locator("#verify-pool > div").evaluate_all("""nodes => nodes.map(node => {
          const svg = node.querySelector('svg');
          const body = svg.querySelector('[data-body]');
          const shape = new Path2D(body.getAttribute('d'));
          const bodyMat = body.transform.baseVal.consolidate()?.matrix;
          const bodyInv = bodyMat ? bodyMat.inverse() : null;
          const canvas = document.createElement('canvas');
          const ctx = canvas.getContext('2d');
          const g = svg.querySelector('.sig-eyes');
          const gMat = g.transform.baseVal.consolidate()?.matrix;

          const checkEye = eye => {
            const len = eye.getTotalLength();
            const eMat = eye.transform.baseVal.consolidate()?.matrix;
            for (let i = 0; i < 48; i++) {
              const pt = eye.getPointAtLength(len * i / 48);
              let p = new DOMPoint(pt.x, pt.y);
              if (eMat) p = p.matrixTransform(eMat);
              if (gMat) p = p.matrixTransform(gMat);
              if (bodyInv) p = p.matrixTransform(bodyInv);
              if (!ctx.isPointInPath(shape, p.x, p.y)) return false;
            }
            return true;
          };
          const eyes = [...svg.querySelectorAll('[data-sigil-eye]')];
          return {
            shape: node.dataset.verifyShape,
            pose: node.dataset.verifyPose,
            ok: eyes.every(checkEye)
          };
        })""")

        failures = [r for r in results if not r["ok"]]
        assert not failures, f"Keyframe containment failures: {failures}"

        page.screenshot(path=str(out_png), full_page=True)
        browser.close()

    print(f"ALL {len(results)}/88 (8 residents x 11 keyframe extremes) Path2D containment checks PASSED!")
    print("Rendered:", out_png, out_png.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
