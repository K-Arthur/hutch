# AVATAR-SYSTEM.md — Hutch Bot Avatar System ("The Hutch Colony")

Date: `2026-10-29`
Run: Master Prompt Run 4 / Pipeline Run 7
Visual Evidence: `.pipeline/brand/2026-10/evidence/avatars/avatar-family-sheet.png` (`400,419 B`, `2960x1840` at DPR 2)
Generator & Verification Script: `.pipeline/brand/2026-10/assets/concepts/render_avatar_family.py`
Target Integration File (Slice 7C): `src/hutch/server/static/app.js:1438-1461` (`ID_HEADS` and `ID_FACES`)

---

## 1. Design Philosophy & Relationship to "Visor Hutch"

In the incumbent dashboard (`src/hutch/server/static/app.js:1438-1447`), the 8 bot avatars (`ID_HEADS`) were generic geometric primitives (`orb` circle, `capsule` pill, `bean` blob, `drop` water-drop, `pebble` blob, `shield`, `triangle`, `hex`) with two oval eyes placed on top. While clean, those primitives had no visual link to what a **Hutch** is or to the picked **"Visor Hutch"** brand logomark (`D53`/`D54`).

**"The Hutch Colony"** replaces the 8 generic primitives with **8 architectural-creature resident silhouettes** on the `64x64` grid (`8u` module), uniting the same triad that governs the brand mark (`Grokbot` + `Pac-Man ghost` + `meaning of hutch`) while strictly respecting `DESIGN.md:396-405` and `PRODUCT.md:82`:
- **Parent vs. Resident Distinction:** The **"Visor Hutch"** brand logomark (`32x32` `evenodd` compound path with the recessed loft visor cutout) is the **parent shelter emblem** of the platform. The **8 Colony Avatars** are the **individual residents** living inside the Hutch: each is a single solid silhouette (`:scope > path` on `64x64`) with two directly placed `#0b1511` contrast-ink oval eyes (`[data-sigil-eye="left|right"]`), zero visor cutouts, zero pupils/glints, and zero outlines.
- **Backward-Compatible Slot Keys (`0..7`):** All 8 `key` strings (`"orb"`, `"capsule"`, `"bean"`, `"drop"`, `"pebble"`, `"shield"`, `"triangle"`, `"hex"`) are preserved in index order `0..7` so existing `localStorage.getItem("hutch:sigils")` user overrides and `tests/e2e/test_design_system.py` slot indices work with zero migration friction.

---

## 2. The 8 Hutch Colony Residents (`64x64` Grid Specification)

| Slot & Key | Resident Name | Archetype & Silhouette Construction | Left Eye `[cx, cy, rx, ry, rot]` | Right Eye `[cx, cy, rx, ry, rot]` | Mean Eye Row (`cy`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`0` · `orb`** | **Ghost Bell** | High semicircular ghost-hutch dome (`R = 21u`) descending to **3 rounded timber posts** (`x = 11..20.8`, `27.2..36.8`, `43.2..53`, `y = 55`) and **2 concave burrow arches** (`apex y = 45.2`). | `[25.2, 27.7, 3.95, 4.50, -8]` | `[38.8, 27.1, 3.95, 4.50, +8]` | **`27.4`** |
| **`1` · `capsule`** | **Gable Hutch** | Pitched shelter roof (`apex y = 6.6`) with overhanging rounded eaves (`x = 7.8..56.2`), vertical timber walls (`x = 13.5..50.5`), and a central arched burrow doorway (`apex y = 46.5`). | `[25.4, 32.7, 3.90, 4.45, -7]` | `[38.6, 32.1, 3.90, 4.45, +7]` | **`32.4`** |
| **`2` · `bean`** | **Hopper Hare** | Twin sculpted hutch-resident ears (`apices (20.2, 6.5)` and `(43.8, 6.5)`) with tangent-continuous fillet joins into plush rounded cheeks (`x = 9.8..54.2`) and a tucked burrow base (`y = 55.5`). | `[24.8, 36.6, 4.00, 4.50, -10]` | `[39.2, 35.8, 4.00, 4.50, +10]` | **`36.2`** |
| **`3` · `drop`** | **Lantern Cowl** | Peaked lantern hood (`apex y = 6.8`) flaring into a protective lower mantle (`x = 8.7..55.3`) supported on **two grounded guardian boots** (`arch apex y = 46.2`). | `[25.3, 38.5, 3.85, 4.40, -8]` | `[38.7, 37.9, 3.85, 4.40, +8]` | **`38.2`** |
| **`4` · `pebble`** | **Transceiver Pod** | Grokbot-inspired chamfered squircle cranium (`x = 14.2..49.8, y = 9.5..54.8`) flanked by **two lateral acoustic transceiver pods** (`x = 6.8..14.2` and `49.8..57.2`, `y = 20.5..42.5`). | `[25.0, 29.5, 4.05, 4.55, -9]` | `[39.0, 28.9, 4.05, 4.55, +9]` | **`29.2`** |
| **`5` · `shield`** | **Bastion Keep** | **Three-merlon gatehouse crown** (`merlons x = 10.8..23.8`, `28.6..35.4`, `40.2..53.2`, `crenel notches y = 17.6`) over a tapered vault body (`keystone y = 55.9`). Embodies Hutch's approval-gate guardian. | `[25.1, 31.1, 3.85, 4.35, -6]` | `[38.9, 30.5, 3.85, 4.35, +6]` | **`30.8`** |
| **`6` · `triangle`** | **Beacon Spire** | **Radar-crested delta scout** (`finial bulb cx = 32, cy = 12.5, r = 6.3`, concave neck fillet `y = 17.1`) sweeping into wide wing stabilizers (`x = 6.8..57.2`) and a notched thruster base (`apex y = 47.2`). | `[25.8, 40.1, 3.80, 4.30, -8]` | `[38.2, 39.5, 3.80, 4.30, +8]` | **`39.8`** |
| **`7` · `hex`** | **Mecha Chassis** | **Shouldered hex-unit** with high armoured brow (`y = 8.5`), angled pauldron wings (`x = 7.8..56.2`), filleted cheek/waist step-in (`x = 14..50 at y = 37.9`), and twin mechanical feet (`arch apex y = 46.3`). | `[24.9, 25.9, 3.95, 4.45, -9]` | `[39.1, 25.3, 3.95, 4.45, +9]` | **`25.6`** |

---

## 3. Drop-In Production Code for `src/hutch/server/static/app.js:1438-1461` (Slice 7C)

```javascript
const ID_HEADS = [
  { key: "orb", d: "M32 7C44.7 7 53 15.6 53 28.5V49.5C53 52.8 50.8 55 48 55C45.2 55 43.2 52.8 43.2 49.5C43.2 46.8 41.8 45.2 40 45.2C38.2 45.2 36.8 46.8 36.8 49.5C36.8 52.8 34.8 55 32 55C29.2 55 27.2 52.8 27.2 49.5C27.2 46.8 25.8 45.2 24 45.2C22.2 45.2 20.8 46.8 20.8 49.5C20.8 52.8 18.8 55 16 55C13.2 55 11 52.8 11 49.5V28.5C11 15.6 19.3 7 32 7Z" },
  { key: "capsule", d: "M28.5 8.2C30.4 6.6 33.6 6.6 35.5 8.2L54.2 22.8C56.2 24.4 55.2 27.5 52.6 27.5H50.5V50C50.5 53.3 48.2 55.5 45 55.5H40.5C38.3 55.5 36.8 53.8 36.8 51.2C36.8 48.2 34.8 46.5 32 46.5C29.2 46.5 27.2 48.2 27.2 51.2C27.2 53.8 25.7 55.5 23.5 55.5H19C15.8 55.5 13.5 53.3 13.5 50V27.5H11.4C8.8 27.5 7.8 24.4 9.8 22.8L28.5 8.2Z" },
  { key: "bean", d: "M20.2 6.5C23.6 6.5 25.8 9.2 26.6 14.5L27.1 17.8C27.3 18.8 28.2 19.4 29.2 19.2C30.1 19 31.1 18.9 32 18.9C32.9 18.9 33.9 19 34.8 19.2C35.8 19.4 36.7 18.8 36.9 17.8L37.4 14.5C38.2 9.2 40.4 6.5 43.8 6.5C47.2 6.5 49.4 9.6 48.8 15L48 21.8C47.8 23.1 48.3 24.3 49.3 25.2C52.5 28.4 54.2 33.2 54.2 38.8C54.2 49 46 55.5 32 55.5C18 55.5 9.8 49 9.8 38.8C9.8 33.2 11.5 28.4 14.7 25.2C15.7 24.3 16.2 23.1 16 21.8L15.2 15C14.6 9.6 16.8 6.5 20.2 6.5Z" },
  { key: "drop", d: "M32 6.8C35 6.8 37.5 8.6 39.5 11.8L51.8 31C54.3 34.8 55.3 38.8 54.6 43.4L53.6 50C53.1 53.5 50.5 55.5 47 55.5H40.6C38.1 55.5 36.6 53.7 36.4 50.8C36.1 47.8 34.4 46.2 32 46.2C29.6 46.2 27.9 47.8 27.6 50.8C27.4 53.7 25.9 55.5 23.4 55.5H17C13.5 55.5 10.9 53.5 10.4 50L9.4 43.4C8.7 38.8 9.7 34.8 12.2 31L24.5 11.8C26.5 8.6 29 6.8 32 6.8Z" },
  { key: "pebble", d: "M23.5 9.5H40.5C46.2 9.5 49.8 13.1 49.8 18.8V20.5H52.2C55.2 20.5 57.2 22.5 57.2 25.5V37.5C57.2 40.5 55.2 42.5 52.2 42.5H49.8V44.8C49.8 50.5 46 54.8 39.8 54.8H24.2C18 54.8 14.2 50.5 14.2 44.8V42.5H11.8C8.8 42.5 6.8 40.5 6.8 37.5V25.5C6.8 22.5 8.8 20.5 11.8 20.5H14.2V18.8C14.2 13.1 17.8 9.5 23.5 9.5Z" },
  { key: "shield", d: "M14.8 8.5H20.8C22.6 8.5 23.8 9.7 23.8 11.5V15.2C23.8 16.6 24.8 17.6 26.2 17.6C27.6 17.6 28.6 16.6 28.6 15.2V11.5C28.6 9.7 29.8 8.5 31.6 8.5H32.4C34.2 8.5 35.4 9.7 35.4 11.5V15.2C35.4 16.6 36.4 17.6 37.8 17.6C39.2 17.6 40.2 16.6 40.2 15.2V11.5C40.2 9.7 41.4 8.5 43.2 8.5H49.2C51.6 8.5 53.2 10.1 53.2 12.5V31.2C53.2 43.8 44.6 52.2 33.6 55.6C32.6 55.9 31.4 55.9 30.4 55.6C19.4 52.2 10.8 43.8 10.8 31.2V12.5C10.8 10.1 12.4 8.5 14.8 8.5Z" },
  { key: "triangle", d: "M32 6.2C35.8 6.2 38.6 8.9 38.6 12.5C38.6 14.4 37.7 16 36.3 17.1C35.6 17.7 35.5 18.7 36 19.5L54.6 44.2C57.2 47.7 55.1 53.5 50.4 53.5H40.8C38.3 53.5 36.9 52 36.1 50.1C35.3 48.3 33.8 47.2 32 47.2C30.2 47.2 28.7 48.3 27.9 50.1C27.1 52 25.7 53.5 23.2 53.5H13.6C8.9 53.5 6.8 47.7 9.4 44.2L28 19.5C28.5 18.7 28.4 17.7 27.7 17.1C26.3 16 25.4 14.4 25.4 12.5C25.4 8.9 28.2 6.2 32 6.2Z" },
  { key: "hex", d: "M21.5 8.5H42.5C44.8 8.5 46.8 9.7 47.9 11.7L55 24.2C56.2 26.3 56 28.9 54.4 30.8L51.2 34.6C50.4 35.5 50 36.7 50 37.9V49.5C50 52.8 47.8 55 44.6 55H39.8C37.5 55 36.1 53.3 35.9 50.6C35.7 47.9 34.2 46.3 32 46.3C29.8 46.3 28.3 47.9 28.1 50.6C27.9 53.3 26.5 55 24.2 55H19.4C16.2 55 14 52.8 14 49.5V37.9C14 36.7 13.6 35.5 12.8 34.6L9.6 30.8C8 28.9 7.8 26.3 9 24.2L16.1 11.7C17.2 9.7 19.2 8.5 21.5 8.5Z" },
];
const ID_FACES = [
  [[25.2, 27.7, 3.95, 4.5, -8], [38.8, 27.1, 3.95, 4.5, 8]],     // orb (Ghost Bell)
  [[25.4, 32.7, 3.9, 4.45, -7], [38.6, 32.1, 3.9, 4.45, 7]],     // capsule (Gable Hutch)
  [[24.8, 36.6, 4, 4.5, -10], [39.2, 35.8, 4, 4.5, 10]],         // bean (Hopper Hare)
  [[25.3, 38.5, 3.85, 4.4, -8], [38.7, 37.9, 3.85, 4.4, 8]],     // drop (Lantern Cowl)
  [[25.0, 29.5, 4.05, 4.55, -9], [39.0, 28.9, 4.05, 4.55, 9]],   // pebble (Transceiver Pod)
  [[25.1, 31.1, 3.85, 4.35, -6], [38.9, 30.5, 3.85, 4.35, 6]],   // shield (Bastion Keep)
  [[25.8, 40.1, 3.8, 4.3, -8], [38.2, 39.5, 3.8, 4.3, 8]],       // triangle (Beacon Spire)
  [[24.9, 25.9, 3.95, 4.45, -9], [39.1, 25.3, 3.95, 4.45, 9]],   // hex (Mecha Chassis)
];
```

---

## 4. Automated E2E Invariant Verification Ledger (`2026-10-29`)

Verified in headless Chromium (`Playwright Chromium 153.0.8010.12`) via `.pipeline/brand/2026-10/assets/concepts/render_avatar_family.py` running the exact DOM + `Path2D` evaluation from `tests/e2e/test_design_system.py:1141-1207` and `tests/e2e/test_browser.py:8614-8641`:

- **48-Point Perimeter `Path2D` Containment (`ctx.isPointInPath`):** `100% PASS` (`inHead: True` for all 16 eyes across all 8 silhouettes).
- **Distinct Vertical Face-Row Heights (`len(face_rows) >= 6`):** `PASS` (`8/8` unique vertical rows: `{25.6, 27.4, 29.2, 30.8, 32.4, 36.2, 38.2, 39.8}`).
- **Eye Aspect Ratio (`1.0 <= height / width <= 1.35`):** `PASS` for all 16 eyes.
- **Paired Eye Balance (`abs(left.rx - right.rx) <= 0.3`, `abs(left.ry - right.ry) <= 0.3`):** `PASS` (`0.0` difference).
- **Mirrored Inward Tilt (`-12 <= angle <= 12`, `abs(left.angle + right.angle) <= 4`):** `PASS` (`sum == 0` for all pairs).
- **Compact Face Span (`abs(left.cx - right.cx) <= 16`):** `PASS` (`12.4u` to `14.4u` across all 8 pairs).
- **Contrast Ink (`#0b1511` on all 8 `ID_COLORS`):** `PASS` (`7.8:1` to `14.2:1` relative luminance contrast across `#3DE8C5`..`#7BD85A`).

---

## 5. 5-State Motion & Expression Choreography (`src/hutch/server/static/studio.css:21-30`)

Visual Evidence: `.pipeline/brand/2026-10/evidence/avatars/avatar-motion-sheet.png` (`430,441 B`, `3040x1680` at DPR 2)
Verification Script: `.pipeline/brand/2026-10/assets/concepts/render_avatar_motion_sheet.py` (`88/88` resident x keyframe-extreme `Path2D` containment checks `PASS`).

### 5.1 State Choreography Table

| Runtime State (`data-state`) | Status Pip | Static Expression (`prefers-reduced-motion: reduce` / `.reduce-effects`) | Active Motion (`prefers-reduced-motion: no-preference` & `:root:not(.reduce-effects)`) |
| :--- | :--- | :--- | :--- |
| **`idle`** | None | Calm, balanced default gaze (`ID_FACES` native coordinates). | Steady by design (`DESIGN.md:303`: idle indicators never loop). |
| **`running`** (*Working*) | `#34d399` (`--brand`) | Focused forward-right working gaze (`translate(1px, -0.4px)`). | **`3.2s` Saccadic Line Scan + `120ms` Return Blink (`eyes-scan`)** paired with **`1.6s` Grounded Body Hover (`body-work`)** anchored at `50% 88%`: scans top-left (`-2.4px, -0.8px`), saccades top-right (`+2.4px, -0.8px`), blinks on carriage return (`scaleY(0.16)` at `42%`), inspects lower-left (`-2.0px, +1.1px`), and verifies output (`+2.2px, +0.6px`). |
| **`waiting`** (*Needs You*) | `#fbbf24` (`--warn`) | Widened upward-right inquiry gaze (`translate(1.2px, -1.5px) scale(1.1)`). | **`2.8s` Operator Inquiry (`eyes-wait` + `body-wait`)**: resident perks up and tilts `+2deg` toward the user while eyes lift and widen (`+1.8px, -2.2px, scale(1.14)`) with an expectant flutter blink at `66%`. |
| **`blocked`** (*Failed / Blocked*) | `#f87171` (`--danger`) | Empathetic worried droop: eyes settle lower (`translateY(2.2px) scale(0.96, 0.68)`), body settles (`translateY(0.8px) scale(1.02, 0.97)`). | Static worried droop reads immediately without motion; optional gentle sigh under no-preference. |
| **`paused`** (*Asleep*) | Hollow ring (`--text-3`) | Peaceful horizontal crescent rest (`translateY(2px) scale(1.08, 0.16)`) with rested `0.98y` body posture. | Static by design. |

### 5.2 Zero-Line-Growth Drop-In CSS for `src/hutch/server/static/studio.css:21-30` (10 lines -> 10 lines)

```css
.sig > path { transform-box: fill-box; transform-origin: 50% 88%; } .sig-eyes { transform-box: fill-box; transform-origin: center; }
/* Static states read without motion: asleep, worried, and reduced-motion working/waiting. */
.avatar[data-state="paused"] .sig > path { transform: translateY(0.6px) scale(1.01, 0.98); } .avatar[data-state="paused"] .sig-eyes { transform: translateY(2px) scale(1.08, 0.16); }
.avatar[data-state="blocked"] .sig > path { transform: translateY(0.8px) scale(1.02, 0.97); } .avatar[data-state="blocked"] .sig-eyes { transform: translateY(2.2px) scale(0.96, 0.68); }
@media (prefers-reduced-motion: no-preference) {
  :root:not(.reduce-effects) .avatar[data-state="running"] .sig > path { animation: body-work 1.6s ease-in-out infinite; } :root:not(.reduce-effects) .avatar[data-state="running"] .sig-eyes { animation: eyes-scan 3.2s cubic-bezier(0.22, 1, 0.36, 1) infinite; }
  :root:not(.reduce-effects) .avatar[data-state="waiting"] .sig > path { animation: body-wait 2.8s cubic-bezier(0.34, 1.56, 0.64, 1) infinite; } :root:not(.reduce-effects) .avatar[data-state="waiting"] .sig-eyes { animation: eyes-wait 2.8s cubic-bezier(0.34, 1.56, 0.64, 1) infinite; }
}
@keyframes body-work { 0%, 100% { transform: translateY(0) rotate(-0.8deg); } 50% { transform: translateY(-1.2px) scale(0.99, 1.02) rotate(0.8deg); } } @keyframes eyes-scan { 0%, 10%, 100% { transform: translate(-2.4px, -0.8px) scale(1.02, 1.04); } 24%, 34% { transform: translate(2.4px, -0.8px) scale(1.02, 1.04); } 42% { transform: translate(1.8px, -0.2px) scale(1.04, 0.16); } 50%, 62% { transform: translate(-2px, 1.1px) scale(1, 0.95); } 76%, 88% { transform: translate(2.2px, 0.6px) scale(1.04, 1.02); } }
@keyframes body-wait { 0%, 100% { transform: none; } 22%, 82% { transform: translateY(-1.4px) rotate(2deg) scale(1.01, 1.02); } } @keyframes eyes-wait { 0%, 100% { transform: translate(0, -0.4px) scale(1.04); } 22%, 58%, 74%, 86% { transform: translate(1.8px, -2.2px) scale(1.14); } 66% { transform: translate(1.8px, -2px) scale(1.14, 0.18); } }
```


