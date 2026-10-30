#!/usr/bin/env python3
"""Construct, mathematically verify (via Chromium Path2D + SVG DOM), and render
the Hutch 8-Resident Bot Avatar Family ('The Hutch Colony').
"""

from __future__ import annotations

import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path("/home/kevina/CodingProjects/hutch")
OUT_DIR = ROOT / ".pipeline/brand/2026-10/evidence/avatars"
OUT_DIR.mkdir(parents=True, exist_ok=True)

ID_COLORS = [
    "#3DE8C5",  # 0 Mint
    "#35C3F0",  # 1 Sky
    "#5B9BFF",  # 2 Azure
    "#9B7CFF",  # 3 Iris
    "#C77DFF",  # 4 Orchid
    "#FF6FA5",  # 5 Rose
    "#FFA83C",  # 6 Amber-Gold
    "#7BD85A",  # 7 Meadow
]

OLD_HEADS = [
    {"key": "orb", "d": "M32 8C45 8 55 18 55 32S45 56 32 56 9 46 9 32 19 8 32 8Z"},
    {"key": "capsule", "d": "M32 7c12 0 19 8 19 19v12c0 11-7 19-19 19s-19-8-19-19V26C13 15 20 7 32 7Z"},
    {"key": "bean", "d": "M13 28c0-12 11-19 23-17 11 1 19 10 18 21-1 12-9 21-21 22-12 1-21-9-20-26Z"},
    {"key": "drop", "d": "M32 8c8 10 21 21 21 32a21 18 0 0 1-42 0C11 29 24 18 32 8Z"},
    {"key": "pebble", "d": "M12 29c1-12 10-20 22-19 12 0 20 8 19 20 0 12-7 24-20 25-13 1-21-9-21-26Z"},
    {"key": "shield", "d": "M32 9c7 4 15 6 21 7v17c0 12-8 19-21 23-13-4-21-11-21-23V16c6-1 14-3 21-7Z"},
    {"key": "triangle", "d": "M27 12c2-4 8-4 10 0l19 32c2 4-1 8-5 8H13c-5 0-7-4-5-8l19-32Z"},
    {"key": "hex", "d": "M22 9h20l13 23-13 23H22L9 32 22 9Z"},
]

OLD_FACES = [
    [[24.7, 30, 4.05, 4.55, -8], [39.2, 29.3, 4.05, 4.55, 8]],
    [[25.2, 29.6, 3.9, 4.45, -8], [38.8, 29.2, 3.9, 4.45, 8]],
    [[24.9, 30.8, 3.95, 4.45, -10], [39, 30, 3.95, 4.45, 10]],
    [[25.3, 36.7, 3.85, 4.35, -8], [38.8, 36.1, 3.85, 4.35, 8]],
    [[24.5, 30.9, 4, 4.5, -9], [39.3, 30.1, 4, 4.5, 9]],
    [[24.8, 31.4, 3.8, 4.3, -7], [39.1, 30.8, 3.8, 4.3, 7]],
    [[27, 37.4, 3.75, 4.25, -8], [38.3, 36.9, 3.75, 4.25, 8]],
    [[24.5, 31.8, 3.95, 4.45, -9], [39.3, 31, 3.95, 4.45, 9]],
]

# New 8-Resident Hutch Colony Family (keys preserved for backward compatibility with
# saved localStorage["hutch:sigils"] indices 0..7 and test_design_system.py)
NEW_HEADS = [
    {
        "key": "orb",
        "title": "Ghost Bell",
        "archetype": "Domed ghost-hutch bell with 3 grounded posts & 2 burrow arches",
        "d": (
            "M32 7C44.7 7 53 15.6 53 28.5V49.5C53 52.8 50.8 55 48 55"
            "C45.2 55 43.2 52.8 43.2 49.5C43.2 46.8 41.8 45.2 40 45.2"
            "C38.2 45.2 36.8 46.8 36.8 49.5C36.8 52.8 34.8 55 32 55"
            "C29.2 55 27.2 52.8 27.2 49.5C27.2 46.8 25.8 45.2 24 45.2"
            "C22.2 45.2 20.8 46.8 20.8 49.5C20.8 52.8 18.8 55 16 55"
            "C13.2 55 11 52.8 11 49.5V28.5C11 15.6 19.3 7 32 7Z"
        ),
    },
    {
        "key": "capsule",
        "title": "Gable Hutch",
        "archetype": "Pitched roof with overhanging eaves & arched burrow base",
        "d": (
            "M28.5 8.2C30.4 6.6 33.6 6.6 35.5 8.2L54.2 22.8C56.2 24.4 55.2 27.5 52.6 27.5"
            "H50.5V50C50.5 53.3 48.2 55.5 45 55.5H40.5C38.3 55.5 36.8 53.8 36.8 51.2"
            "C36.8 48.2 34.8 46.5 32 46.5C29.2 46.5 27.2 48.2 27.2 51.2"
            "C27.2 53.8 25.7 55.5 23.5 55.5H19C15.8 55.5 13.5 53.3 13.5 50"
            "V27.5H11.4C8.8 27.5 7.8 24.4 9.8 22.8L28.5 8.2Z"
        ),
    },
    {
        "key": "bean",
        "title": "Hopper Hare",
        "archetype": "Twin sculpted hutch ears over a plush rounded burrow body",
        "d": (
            "M20.2 6.5C23.6 6.5 25.8 9.2 26.6 14.5L27.1 17.8C27.3 18.8 28.2 19.4 29.2 19.2"
            "C30.1 19 31.1 18.9 32 18.9C32.9 18.9 33.9 19 34.8 19.2"
            "C35.8 19.4 36.7 18.8 36.9 17.8L37.4 14.5C38.2 9.2 40.4 6.5 43.8 6.5"
            "C47.2 6.5 49.4 9.6 48.8 15L48 21.8C47.8 23.1 48.3 24.3 49.3 25.2"
            "C52.5 28.4 54.2 33.2 54.2 38.8C54.2 49 46 55.5 32 55.5"
            "C18 55.5 9.8 49 9.8 38.8C9.8 33.2 11.5 28.4 14.7 25.2"
            "C15.7 24.3 16.2 23.1 16 21.8L15.2 15C14.6 9.6 16.8 6.5 20.2 6.5Z"
        ),
    },
    {
        "key": "drop",
        "title": "Lantern Cowl",
        "archetype": "Peaked lantern hood flaring into a twin-footed guardian mantle",
        "d": (
            "M32 6.8C35 6.8 37.5 8.6 39.5 11.8L51.8 31C54.3 34.8 55.3 38.8 54.6 43.4"
            "L53.6 50C53.1 53.5 50.5 55.5 47 55.5H40.6C38.1 55.5 36.6 53.7 36.4 50.8"
            "C36.1 47.8 34.4 46.2 32 46.2C29.6 46.2 27.9 47.8 27.6 50.8"
            "C27.4 53.7 25.9 55.5 23.4 55.5H17C13.5 55.5 10.9 53.5 10.4 50"
            "L9.4 43.4C8.7 38.8 9.7 34.8 12.2 31L24.5 11.8C26.5 8.6 29 6.8 32 6.8Z"
        ),
    },
    {
        "key": "pebble",
        "title": "Transceiver Pod",
        "archetype": "Grokbot-inspired cranial hull with lateral acoustic ear pods",
        "d": (
            "M23.5 9.5H40.5C46.2 9.5 49.8 13.1 49.8 18.8V20.5H52.2C55.2 20.5 57.2 22.5 57.2 25.5"
            "V37.5C57.2 40.5 55.2 42.5 52.2 42.5H49.8V44.8C49.8 50.5 46 54.8 39.8 54.8"
            "H24.2C18 54.8 14.2 50.5 14.2 44.8V42.5H11.8C8.8 42.5 6.8 40.5 6.8 37.5"
            "V25.5C6.8 22.5 8.8 20.5 11.8 20.5H14.2V18.8C14.2 13.1 17.8 9.5 23.5 9.5Z"
        ),
    },
    {
        "key": "shield",
        "title": "Bastion Keep",
        "archetype": "Three-merlon gatehouse crown over a vaulted approval-keep body",
        "d": (
            "M14.8 8.5H20.8C22.6 8.5 23.8 9.7 23.8 11.5V15.2C23.8 16.6 24.8 17.6 26.2 17.6"
            "C27.6 17.6 28.6 16.6 28.6 15.2V11.5C28.6 9.7 29.8 8.5 31.6 8.5H32.4"
            "C34.2 8.5 35.4 9.7 35.4 11.5V15.2C35.4 16.6 36.4 17.6 37.8 17.6"
            "C39.2 17.6 40.2 16.6 40.2 15.2V11.5C40.2 9.7 41.4 8.5 43.2 8.5H49.2"
            "C51.6 8.5 53.2 10.1 53.2 12.5V31.2C53.2 43.8 44.6 52.2 33.6 55.6"
            "C32.6 55.9 31.4 55.9 30.4 55.6C19.4 52.2 10.8 43.8 10.8 31.2V12.5"
            "C10.8 10.1 12.4 8.5 14.8 8.5Z"
        ),
    },
    {
        "key": "triangle",
        "title": "Beacon Spire",
        "archetype": "Radar-crested delta scout with wide wing stabilizers & notched base",
        "d": (
            "M32 6.2C35.8 6.2 38.6 8.9 38.6 12.5C38.6 14.4 37.7 16 36.3 17.1"
            "C35.6 17.7 35.5 18.7 36 19.5L54.6 44.2C57.2 47.7 55.1 53.5 50.4 53.5"
            "H40.8C38.3 53.5 36.9 52 36.1 50.1C35.3 48.3 33.8 47.2 32 47.2"
            "C30.2 47.2 28.7 48.3 27.9 50.1C27.1 52 25.7 53.5 23.2 53.5"
            "H13.6C8.9 53.5 6.8 47.7 9.4 44.2L28 19.5C28.5 18.7 28.4 17.7 27.7 17.1"
            "C26.3 16 25.4 14.4 25.4 12.5C25.4 8.9 28.2 6.2 32 6.2Z"
        ),
    },
    {
        "key": "hex",
        "title": "Mecha Chassis",
        "archetype": "Shouldered hex-bot with stepped cheek waist & twin mechanical feet",
        "d": (
            "M21.5 8.5H42.5C44.8 8.5 46.8 9.7 47.9 11.7L55 24.2C56.2 26.3 56 28.9 54.4 30.8"
            "L51.2 34.6C50.4 35.5 50 36.7 50 37.9V49.5C50 52.8 47.8 55 44.6 55"
            "H39.8C37.5 55 36.1 53.3 35.9 50.6C35.7 47.9 34.2 46.3 32 46.3"
            "C29.8 46.3 28.3 47.9 28.1 50.6C27.9 53.3 26.5 55 24.2 55"
            "H19.4C16.2 55 14 52.8 14 49.5V37.9C14 36.7 13.6 35.5 12.8 34.6"
            "L9.6 30.8C8 28.9 7.8 26.3 9 24.2L16.1 11.7C17.2 9.7 19.2 8.5 21.5 8.5Z"
        ),
    },
]

# 8 distinct vertical face-row heights (mean cy: 27.4, 32.4, 36.2, 38.2, 29.2, 30.8, 39.8, 25.6)
# All 8 unique -> len(face_rows) == 8 (exceeds >= 6 test requirement).
NEW_FACES = [
    [[25.2, 27.7, 3.95, 4.50, -8], [38.8, 27.1, 3.95, 4.50, 8]],   # 0 orb (Ghost Bell) -> mean 27.4
    [[25.4, 32.7, 3.90, 4.45, -7], [38.6, 32.1, 3.90, 4.45, 7]],   # 1 capsule (Gable Hutch) -> mean 32.4
    [[24.8, 36.6, 4.00, 4.50, -10], [39.2, 35.8, 4.00, 4.50, 10]], # 2 bean (Hopper Hare) -> mean 36.2
    [[25.3, 38.5, 3.85, 4.40, -8], [38.7, 37.9, 3.85, 4.40, 8]],   # 3 drop (Lantern Cowl) -> mean 38.2
    [[25.0, 29.5, 4.05, 4.55, -9], [39.0, 28.9, 4.05, 4.55, 9]],   # 4 pebble (Transceiver Pod) -> mean 29.2
    [[25.1, 31.1, 3.85, 4.35, -6], [38.9, 30.5, 3.85, 4.35, 6]],   # 5 shield (Bastion Keep) -> mean 30.8
    [[25.8, 40.1, 3.80, 4.30, -8], [38.2, 39.5, 3.80, 4.30, 8]],   # 6 triangle (Beacon Spire) -> mean 39.8
    [[24.9, 25.9, 3.95, 4.45, -9], [39.1, 25.3, 3.95, 4.45, 9]],   # 7 hex (Mecha Chassis) -> mean 25.6
]


def render_eye_path(name: str, spec: list[float]) -> str:
    cx, cy, rx, ry, angle = spec
    k = 0.55228475
    d = (
        f"M{cx} {cy - ry}"
        f"C{cx + rx * k} {cy - ry} {cx + rx} {cy - ry * k} {cx + rx} {cy}"
        f"C{cx + rx} {cy + ry * k} {cx + rx * k} {cy + ry} {cx} {cy + ry}"
        f"C{cx - rx * k} {cy + ry} {cx - rx} {cy + ry * k} {cx - rx} {cy}"
        f"C{cx - rx} {cy - ry * k} {cx - rx * k} {cy - ry} {cx} {cy - ry}Z"
    )
    meta = f'data-cx="{cx}" data-cy="{cy}" data-rx="{rx}" data-ry="{ry}" data-angle="{angle}"'
    transform = f"rotate({angle} {cx} {cy})"
    return (
        f'<path data-sigil-eye="{name}" data-contrast-ink="#0b1511" '
        f'd="{d}" {meta} transform="{transform}" fill="#0b1511" aria-hidden="true"/>'
    )


def render_svg(head_d: str, faces: list[list[float]], color: str, show_grid: bool = False) -> str:
    left, right = faces
    grid = ""
    if show_grid:
        lines = []
        for g in range(8, 64, 8):
            lines.append(f'<line x1="{g}" y1="0" x2="{g}" y2="64" stroke="rgba(255,255,255,0.06)" stroke-width="0.5"/>')
            lines.append(f'<line x1="0" y1="{g}" x2="64" y2="{g}" stroke="rgba(255,255,255,0.06)" stroke-width="0.5"/>')
        cy_mean = (left[1] + right[1]) / 2
        lines.append(f'<line x1="4" y1="{cy_mean}" x2="60" y2="{cy_mean}" stroke="#34d399" stroke-width="0.6" stroke-dasharray="2 2"/>')
        grid = "".join(lines)
    eyes = f'<g class="sig-eyes" aria-hidden="true">{render_eye_path("left", left)}{render_eye_path("right", right)}</g>'
    return f'<svg class="sig" viewBox="0 0 64 64">{grid}<path d="{head_d}" fill="{color}"/>{eyes}</svg>'


def main() -> None:
    old_cards = []
    new_cards = []
    roster_rows = []
    bot_names = [
        ("workspace-coordinator", "Workspace Coordinator", "Ready · Local Ollama", 0, 0, "running"),
        ("code-reviewer", "Code Reviewer", "Idle · Claude 3.7 Sonnet", 1, 1, ""),
        ("research-scout", "Research Scout", "Needs approval · Web fetch", 2, 2, "waiting"),
        ("night-watch", "Night Watch", "Idle · Local llama.cpp", 3, 3, ""),
        ("comms-relay", "Comms Relay", "Idle · Gmail + Calendar", 4, 4, ""),
        ("policy-gate", "Policy Gate", "Always checks before actions", 5, 5, ""),
        ("signal-finder", "Signal Finder", "Paused · Scheduled 08:00", 6, 6, "paused"),
        ("build-runner", "Build Runner", "Blocked · Exit code 1", 7, 7, "blocked"),
    ]

    for i in range(8):
        c = ID_COLORS[i]
        old_svg = render_svg(OLD_HEADS[i]["d"], OLD_FACES[i], c)
        new_svg_grid = render_svg(NEW_HEADS[i]["d"], NEW_FACES[i], c, show_grid=True)
        new_svg_clean = render_svg(NEW_HEADS[i]["d"], NEW_FACES[i], c, show_grid=False)
        mean_cy = round((NEW_FACES[i][0][1] + NEW_FACES[i][1][1]) / 2, 1)

        old_cards.append(f"""
        <div class="old-cell">
          <div class="av-box av-56">{old_svg}</div>
          <div class="cell-key">{OLD_HEADS[i]['key']}</div>
        </div>
        """)

        new_cards.append(f"""
        <div class="new-card" data-test-sigil="{i}">
          <div class="new-card-top">
            <span class="slot-badge">#{i} · {NEW_HEADS[i]['key']}</span>
            <span class="cy-badge">cy {mean_cy}</span>
          </div>
          <div class="stage-row">
            <div class="av-stage" title="96px Construction">{new_svg_grid}</div>
            <div class="scale-col">
              <div class="scale-item"><div class="av-40">{new_svg_clean}</div><span>40px</span></div>
              <div class="scale-item"><div class="av-28">{new_svg_clean}</div><span>28px</span></div>
              <div class="scale-item"><div class="av-20">{new_svg_clean}</div><span>20px</span></div>
            </div>
          </div>
          <div class="new-title">{NEW_HEADS[i]['title']}</div>
          <div class="new-desc">{NEW_HEADS[i]['archetype']}</div>
        </div>
        """)

    for slug, label, meta, ci, si, state in bot_names:
        svg = render_svg(NEW_HEADS[si]["d"], NEW_FACES[si], ID_COLORS[ci])
        pip = f'<span class="pip {state}"></span>' if state else ""
        roster_rows.append(f"""
        <div class="roster-row" data-state="{state or 'idle'}">
          <div class="roster-av">{svg}{pip}</div>
          <div class="roster-txt">
            <div class="roster-name">{label}</div>
            <div class="roster-meta">{meta}</div>
          </div>
        </div>
        """)

    picker_shapes = []
    for i in range(8):
        svg = render_svg(NEW_HEADS[i]["d"], NEW_FACES[i], "currentColor")
        pressed = "true" if i == 0 else "false"
        picker_shapes.append(f'<button class="shp-btn" aria-pressed="{pressed}">{svg}</button>')

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
  width: 1480px;
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
.old-strip {{
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 10px;
  background: #0f0f12;
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 12px;
  padding: 14px;
  margin-bottom: 22px;
}}
.old-cell {{
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}}
.av-56 {{ width: 52px; height: 52px; }}
.cell-key {{ font-family: monospace; font-size: 11px; color: #8e8e99; }}
.main-layout {{
  display: grid;
  grid-template-columns: 1fr 360px;
  gap: 20px;
}}
.new-grid {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
}}
.new-card {{
  background: #0f0f12;
  border: 1px solid rgba(255,255,255,0.14);
  border-radius: 12px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}}
.new-card-top {{
  display: flex;
  justify-content: space-between;
  font-family: monospace;
  font-size: 11px;
}}
.slot-badge {{ color: #a3a3ae; }}
.cy-badge {{ color: #34d399; }}
.stage-row {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #16161a;
  border-radius: 8px;
  padding: 12px;
}}
.av-stage {{ width: 96px; height: 96px; }}
.scale-col {{
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}}
.scale-item {{
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: monospace;
  font-size: 10px;
  color: #8e8e99;
}}
.av-40 {{ width: 40px; height: 40px; }}
.av-28 {{ width: 28px; height: 28px; }}
.av-20 {{ width: 20px; height: 20px; }}
.new-title {{ font-size: 14px; font-weight: 650; color: #ededf0; }}
.new-desc {{ font-size: 11.5px; line-height: 1.35; color: #a3a3ae; }}
.side-col {{
  display: flex;
  flex-direction: column;
  gap: 16px;
}}
.roster-card, .picker-card {{
  background: #0f0f12;
  border: 1px solid rgba(255,255,255,0.14);
  border-radius: 12px;
  padding: 14px;
}}
.roster-list {{
  display: flex;
  flex-direction: column;
  gap: 6px;
}}
.roster-row {{
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  border-radius: 8px;
  background: #16161a;
}}
.roster-av {{
  position: relative;
  width: 36px;
  height: 36px;
  flex: none;
}}
.roster-row[data-state="paused"] .sig-eyes {{ transform: scaleY(0.14); transform-origin: 32px 32px; }}
.roster-row[data-state="blocked"] .sig-eyes {{ transform: translateY(1.6px) scaleY(0.7); transform-origin: 32px 32px; }}
.pip {{
  position: absolute;
  right: -2px;
  bottom: -2px;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  border: 2px solid #16161a;
}}
.pip.running {{ background: #34d399; }}
.pip.waiting {{ background: #fbbf24; }}
.pip.paused {{ background: transparent; border: 2px solid #8e8e99; }}
.pip.blocked {{ background: #f87171; }}
.roster-name {{ font-size: 13px; font-weight: 600; color: #ededf0; }}
.roster-meta {{ font-size: 11px; color: #8e8e99; }}
.picker-grid {{
  display: grid;
  grid-template-columns: repeat(4, 44px);
  gap: 8px;
  justify-content: center;
  margin-top: 8px;
}}
.shp-btn {{
  width: 44px;
  height: 44px;
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.14);
  background: #16161a;
  color: #a3a3ae;
  display: grid;
  place-items: center;
}}
.shp-btn[aria-pressed="true"] {{
  color: #ededf0;
  border-color: #60a5fa;
  background: rgba(96,165,250,0.14);
}}
.shp-btn svg {{ width: 30px; height: 30px; }}
svg.sig {{ width: 100%; height: 100%; display: block; }}
</style>
</head>
<body>
  <div class="hdr">
    <h1>Hutch Bot Avatar System — "The Hutch Colony" (8 Architectural &amp; Creature Residents vs. Legacy Primitives)</h1>
    <span>64x64 Grid · 8 Unique Face Rows · Path2D Verified</span>
  </div>
  <div class="sec-lbl">Legacy Primitives (Before — generic circle, pill, bean, drop, pebble, shield, triangle, hexagon)</div>
  <div class="old-strip">
    {''.join(old_cards)}
  </div>
  <div class="main-layout">
    <div>
      <div class="sec-lbl">Redesigned 8-Resident Hutch Colony (After — 96px construction + 40px / 28px / 20px downscale ladder)</div>
      <div class="new-grid">
        {''.join(new_cards)}
      </div>
    </div>
    <div class="side-col">
      <div class="roster-card">
        <div class="sec-lbl">Live Operator Roster Simulation (36px + State Pips)</div>
        <div class="roster-list">
          {''.join(roster_rows)}
        </div>
      </div>
      <div class="picker-card">
        <div class="sec-lbl">44x44px Identity Shape Picker (`currentColor`)</div>
        <div class="picker-grid">
          {''.join(picker_shapes)}
        </div>
      </div>
    </div>
  </div>
</body>
</html>
"""

    out_png = OUT_DIR / "avatar-family-sheet.png"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1480, "height": 920}, device_scale_factor=2)
        page.set_content(html, wait_until="networkidle")

        # Run the exact Path2D + getBBox + eye geometry checks from tests/e2e/test_design_system.py
        identity = page.locator("[data-test-sigil] .av-40 svg.sig").evaluate_all("""svgs => svgs.map(svg => {
          const body = svg.querySelector(':scope > path');
          const shape = new Path2D(body.getAttribute('d'));
          const canvas = document.createElement('canvas');
          const ctx = canvas.getContext('2d');
          const points = element => {
            const length = element.getTotalLength();
            const transform = element.transform.baseVal.consolidate()?.matrix;
            return Array.from({length:48}, (_, index) => {
              const point = element.getPointAtLength(length * index / 48);
              const local = new DOMPoint(point.x, point.y);
              return transform ? local.matrixTransform(transform) : local;
            });
          };
          const eyes = [...svg.querySelectorAll('[data-sigil-eye]')];
          const contained = eyes.map(eye => {
            const eyePoints = points(eye);
            return {
              inHead: eyePoints.every(point => ctx.isPointInPath(shape, point.x, point.y)),
            };
          });
          return {
            head: body.getAttribute('d'),
            color: body.getAttribute('fill'),
            eyes: eyes.map(eye => ({
              name: eye.dataset.sigilEye,
              tag: eye.tagName.toLowerCase(),
              rx: Number(eye.dataset.rx),
              ry: Number(eye.dataset.ry),
              cx: Number(eye.dataset.cx),
              cy: Number(eye.dataset.cy),
              width: eye.getBBox().width,
              height: eye.getBBox().height,
              angle: Number(eye.dataset.angle),
              fill: eye.getAttribute('fill'),
              contrastInk: eye.dataset.contrastInk
            })),
            contained
          };
        })""")

        assert len(identity) == 8
        assert len({item["color"] for item in identity}) == 8
        assert all(len(item["eyes"]) == 2 for item in identity)
        assert all(
            eye["tag"] == "path"
            and eye["fill"] == "#0b1511"
            and eye["contrastInk"] == "#0b1511"
            and 1.0 <= eye["height"] / eye["width"] <= 1.35
            for item in identity
            for eye in item["eyes"]
        ), "Eye aspect ratio or fill failed!"
        assert all(
            abs(item["eyes"][0]["rx"] - item["eyes"][1]["rx"]) <= 0.3
            and abs(item["eyes"][0]["ry"] - item["eyes"][1]["ry"]) <= 0.3
            for item in identity
        )
        assert all(item["eyes"][0]["cx"] < item["eyes"][1]["cx"] for item in identity)
        assert all(-12 <= eye["angle"] <= 12 for item in identity for eye in item["eyes"])
        assert all(abs(item["eyes"][0]["angle"] + item["eyes"][1]["angle"]) <= 4 for item in identity)
        assert all(abs(item["eyes"][0]["cx"] - item["eyes"][1]["cx"]) <= 16 for item in identity)
        face_rows = {round(sum(eye["cy"] for eye in item["eyes"]) / 2, 1) for item in identity}
        assert len(face_rows) == 8, f"Expected 8 distinct face rows, got {face_rows}"
        assert all(part == {"inHead": True} for item in identity for part in item["contained"]), (
            f"Eye containment failed: {[item['contained'] for item in identity]}"
        )

        page.screenshot(path=str(out_png), full_page=True)
        browser.close()

    print("ALL Path2D + getBBox + face_rows (8/8 unique) e2e invariants PASSED!")
    print("Rendered:", out_png, out_png.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
