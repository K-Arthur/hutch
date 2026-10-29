# MARK-DIRECTIONS-RUN6.md — Clean-sheet mark design (Run 6, 2026-10-29)

Date: 2026-10-29 (America/Vancouver)
Run: 6 (Task A — clean-sheet mark design to `PRINCIPLES.md` R1–R11)
Status: **SELECTED BY HUMAN (2026-10-29): Direction B ("Visor Hutch").** Recorded in `DECISION.md` D54. Production assets and press kit generated under `.pipeline/brand/2026-10/assets/production/` and `assets/press-kit/` (pipeline-only per D42; no adoption into `website/`, `docs/`, `src/` or `desktop/` without its own dated authorisation).
Legal boundary: Pre-screen only; nothing in this document is a clearance, validity, distinctiveness or non-infringement conclusion. All trademark and figurative questions remain **unresolved** and require **counsel/owner decision** (`DECISION.md` D20/D23/D28/D38, B6, B10). Not legal advice.

---

## 1. Visual Philosophy — "Sheltered Presence" (per `PRINCIPLES.md` 1.1)

A hutch is not an abstract geometric container and not a suburban house; in carpentry and animal keeping, a hutch is a **raised timber shelter with a protective roof and open lower burrows**, built to house living creatures safely inside one frame. In Hutch the software platform, that physical structure maps directly to the product truth (`STRATEGY.md` T1–T15): **one local machine that houses and governs a colony of named bots** ("Your bots. Your machine. Your rules.").

Earlier iterations (Rounds 1–12, archived as non-candidates under D51/D52) failed because they treated the mark either as a sterile outline primitive or as a tall, vertical-walled gravestone (`20x24` aspect ratio) with flat circular or square holes punched at the vertical midpoint—triggering either a "wall socket" read or, when a single notch was cut in the bottom center, a "screaming mouth" pareidolia read.

Following the maintainer's Run 6 creative brief—**synthesizing Grokbot, the Pac-Man ghost archetype, and the meaning of the word "hutch"**—the "Sheltered Presence" philosophy fuses three structural disciplines into a single `fill-rule="evenodd"` compound silhouette on a `32x32` grid (4-unit module):

1. **The Meaning of "Hutch" (Protective Shelter & Burrow Architecture):** The upper silhouette provides physical shelter (either via a pitched timber gable roof with projecting eaves in Direction A, or an enclosing hooded hutch shell with a recessed upper loft bay in Direction B), while the base raises the structure on **three grounded timber stile posts flanking two concave burrow arches**.
2. **The Pac-Man Ghost Archetype (Grounded Scalloped Rhythm & Attentive Motion):** By placing a **solid center post at `x = 16.0` touching the floor (`y = 28.30`)** flanked by two tangent-continuous semicircular burrow arches (`x = 8.8..13.8` and `x = 18.2..23.2`), the base captures the iconic footed/scalloped rhythm of a classic arcade ghost without copying Bandai Namco's jagged zig-zag skirt, and mathematically eliminates the center-mouth pareidolia that broke Round 7.
3. **Grokbot (`grokbot` / Hutch In-App Bot Sigil Language):** Consistent with the minimalist mouthless bot philosophy and Hutch's own `ID_FACES` avatar system (`src/hutch/server/static/app.js:1452-1507`), personality is carried entirely by **paired, slightly inward-tilted (`-8°` left, `+8°` right) vertical oval eyes** (`rx : ry ≈ 1 : 1.29`) with a subtle `+0.30u` upward offset on the right eye so the mark glances attentively toward the lowercase `hutch.` wordmark in **Bricolage Grotesque 800**.

Every stroke weight (`4.40u` foot posts and loft rails) is locked to the heavy stem thickness of **Bricolage Grotesque 800**, and curved extremes carry `0.30u–0.35u` of optical overshoot beyond the nominal `24x24` (`x = 4..28, y = 4..28`) metric frame so the mark sits at equal optical height and mass beside the wordmark.

---

## 2. Direction A — "Gable Ghost" (Pitched Hutch Eaves + Knocked-Out Grokbot Eyes + 3-Post Burrow Skirt)

Evidence files:
- Construction sheet: `.pipeline/brand/2026-10/assets/concepts/sheets/run6-direction-a-construction.png`
- Test matrix: `.pipeline/brand/2026-10/assets/concepts/sheets/run6-test-matrix.png`

### 2.1 One-Page Rationale (Product Truth & Surface Map)

- **Subject & Triad Grounding (R1):** Direction A leads with the unmistakable silhouette of a **pitched timber hutch roof with projecting eaves (`x = 2.60..29.40`)** sheltering a compact ghost-bot body (`x = 4.40..27.60`) that stands on **three sturdy timber posts with two concave burrow arches** at the floor. Inside the upper loft, two **Grokbot inward-tilted (`-8° / +8°`) vertical oval eyes** are knocked out in negative space, glancing toward the wordmark.
- **One Bold Move (R2):** The **pitched gable eaves overhang combined with the 3-post / 2-burrow ghost skirt**. A generic house icon has a flat base and square windows; a generic ghost or bot has a round head and no eaves. Combining the projecting timber hutch roof with the scalloped ghost-burrow skirt creates a single silhouette that says *"a bot that lives in your local hutch"* in under two seconds.
- **Removal Pass (R10):** An earlier sketch included a horizontal collar seam below the eaves; deleting that seam left a single unbroken compound contour (`1` outer contour + `2` eye contours = `3` closed subpaths total), dramatically improving 16px clarity.
- **Surface-by-Surface Fit:**
  - **Favicon (16px / 32px, light & dark):** Only 3 closed subpaths; the projecting eaves tips (`x = 2.00..30.00` in the redrawn small tier) and two large knocked-out eyes (`5.30u x 6.70u`) remain crisp down to `16x16px` (`>= 1.42px` counterforms).
  - **Dashboard Header & Server Pages (22–26px):** Pairs directly with lowercase `hutch.` (Bricolage Grotesque 800); the `30°` pitched roof slope echoes the diagonal terminal shear of Bricolage's lowercase `t`.
  - **Desktop Icon (Tauri 32–1024px) & PWA (192/512 any, maskable, monochrome):** Fits inside the W3C `40%`-radius maskable safe zone at `72%` scale with zero clipping of the eaves or feet; pure `fill-rule="evenodd"` works natively as a single-layer `currentColor` monochrome icon.
  - **OG (1200x630) & GitHub Social Preview (1280x640):** High-contrast emerald-400 (`#34d399`, `10.35:1` on `ink-950`) or `paper` (`#ededf0`, `17.03:1`) emblem anchors the card beside the Bricolage 800 headline.
  - **README / Terminal / Docs / Press:** Single-colour SVG requires no gradients, strokes or secondary colours; renders in `emerald-700` (`#047857`, `4.69:1`) or `ink-950` (`#09090b`, `17.03:1`) on light press/print sheets.

### 2.2 Construction Specification Table (Direction A)

| Parameter | Master Tier (`>= 32px`) | Small Tier (`16–24px`, Redrawn R6) | Rule / Optical Purpose |
|---|---|---|---|
| Canvas & Grid Module | `32 x 32` (`4.00u` module) | `32 x 32` (`4.00u` module) | R3 grid discipline |
| Nominal Metric Box | `x = 4.40..27.60`, `y = 4.00..28.00` | `x = 4.00..28.00`, `y = 3.00..29.00` | `1:1` square optical balance (`23.2u x 24.6u`) |
| Roof Ridge Peak (Overshoot) | `(16.00, 3.65)` via `Q 16.00 3.00` | `(16.00, 2.80)` via `Q 16.00 2.10` | R3 `+0.35u` optical overshoot at pointed apex |
| Eaves Overhang Span | `x = 2.60..29.40` at `y = 12.20` (`1.80u` step) | `x = 2.00..30.00` at `y = 12.00` (`2.00u` step) | R1/R2 timber hutch roof overhang |
| Left Eye `(cx, cy, rx, ry, rot)` | `(11.40, 14.10)`, `2.35 x 3.05`, `-8.0°` | `(11.20, 13.90)`, `2.65 x 3.35`, `-8.0°` | Grokbot / `ID_FACES` inward-tilted oval cutout |
| Right Eye `(cx, cy, rx, ry, rot)` | `(20.60, 13.80)`, `2.35 x 3.05`, `+8.0°` | `(20.80, 13.60)`, `2.65 x 3.35`, `+8.0°` | `+0.30u` upward gaze offset toward wordmark |
| Minimum Interior Counterform | `4.50u` inter-eye bridge; `4.65u` wall | `4.30u` inter-eye bridge; `4.55u` wall | R5 (`>= 2.0u` master, `>= 2.5u` small -> `2.15px` at 16px) |
| 3-Post Foot Width & Base Y | `3 x 4.40u` (`rf = 2.20u`), `y = 28.30` | `3 x 4.40u` (`rf = 2.20u`), `y = 29.20` | Matches Bricolage 800 stem; `x=16` post prevents mouth read |
| Twin Burrow Arches | `2 x 5.00u` (`ra = 2.50u`), apex `y = 22.60` | `2 x 5.40u` (`ra = 2.70u`), apex `y = 22.40` | Tangent-continuous Pac-Man ghost skirt + twin hutch burrows |

---

## 3. Direction B — "Visor Hutch" (Hooded Ghost-Hutch Shell + Recessed Loft Visor + Twin Positive Bot Eyes)

Evidence files:
- Construction sheet: `.pipeline/brand/2026-10/assets/concepts/sheets/run6-direction-b-construction.png`
- Test matrix: `.pipeline/brand/2026-10/assets/concepts/sheets/run6-test-matrix.png`

### 3.1 One-Page Rationale (Product Truth & Surface Map)

- **Subject & Triad Grounding (R1):** Direction B interprets the hutch as an **enclosing hooded shelter with an open upper loft bay (`visor`) and twin lower burrow arches**, inside which **two positive-space Grokbot eyes gleam side by side**. It unifies all three references in nested layers of positive and negative space:
  1. **Outer contour (positive):** The classic **Pac-Man ghost dome + 3-post / 2-burrow hutch base** (`x = 4.00..28.00`, `y = 3.70..28.30`).
  2. **Middle contour (negative cutout):** A wide **recessed hutch loft / Grokbot visor window** (`x = 6.80..25.20`, `y = 8.60..18.40`, `r_top = 5.40u`, `r_bot = 3.60u`).
  3. **Inner contours (positive islands):** **Two inward-tilted (`-8° / +8°`) Grokbot oval eyes** floating inside the dark visor recess—representing both the expressive bot face AND the colony residents looking out from inside their sheltered hutch loft.
- **One Bold Move (R2):** The **nested positive-inside-negative loft visor (`outer shell -> dark loft cutout -> positive gleaming eyes`)** built as a single `fill-rule="evenodd"` compound path. It directly bridges Hutch's 3D marketing mascot (`website/assets/hutch-agent.webp`, which features a dark rounded visor with glowing eyes) and Hutch's 2D in-app bot avatars (`app.js` `ID_FACES`) into one cohesive vector mark.
- **Removal Pass (R10):** Removed any separate roof cap or ear protrusions so the outer dome stays pure and uninterrupted, letting the recessed visor loft and 3-post scalloped skirt carry the entire silhouette.
- **Surface-by-Surface Fit:**
  - **Favicon (16px / 32px, light & dark):** The redrawn small tier (`16–24px`) expands the outer dome to `x = 3.00..29.00` and widens the dark visor moat around the positive eyes to `>= 2.85u` (`1.42px` at 16px) vertically and `>= 3.65u` (`1.82px` at 16px) horizontally so the eyes never plug or merge at 16x16px.
  - **Dashboard Header & Server Pages (22–26px):** The rounded dome (`r = 12u`) and interior visor arch echo the warm bowls and shoulders of `h`, `u`, `c` in **Bricolage Grotesque 800**.
  - **Desktop Icon (Tauri) & PWA (192/512 any, maskable, monochrome):** At `512px`, the three-layer depth (emerald shell -> ink visor -> emerald eyes) looks rich and dimensional while remaining a single flat 1-colour SVG path.
  - **OG (1200x630), GitHub Social (1280x640), README/Terminal, Press:** Works in `1-colour` monochrome (`currentColor`) on any light, dark or print surface without needing a two-tone palette override.

### 3.2 Construction Specification Table (Direction B)

| Parameter | Master Tier (`>= 32px`) | Small Tier (`16–24px`, Redrawn R6) | Rule / Optical Purpose |
|---|---|---|---|
| Canvas & Grid Module | `32 x 32` (`4.00u` module) | `32 x 32` (`4.00u` module) | R3 grid discipline |
| Outer Dome Span & Crown Y | `x = 4.00..28.00` (`24.0u`), `y = 3.70` | `x = 3.00..29.00` (`26.0u`), `y = 2.80` | R3 `+0.30u` top overshoot; `1:1` square proportion |
| Recessed Loft Visor Cutout | `x = 6.80..25.20`, `y = 8.60..18.40` | `x = 6.20..25.80`, `y = 7.60..18.60` | R2 bold move: hutch loft bay / Grokbot visor |
| Visor Corner Radii | `r_top = 5.40u`, `r_bot = 3.60u` | `r_top = 5.80u`, `r_bot = 3.80u` | Concentric with outer dome above (`2.80u` wall) |
| Positive Left Eye `(cx, cy, rx, ry, rot)` | `(12.20, 13.70)`, `2.05 x 2.65`, `-8.0°` | `(12.00, 13.25)`, `2.15 x 2.65`, `-8.0°` | Positive island inside `evenodd` visor hole |
| Positive Right Eye `(cx, cy, rx, ry, rot)` | `(19.80, 13.40)`, `2.05 x 2.65`, `+8.0°` | `(20.00, 13.00)`, `2.15 x 2.65`, `+8.0°` | `+0.30u` upward gaze offset toward wordmark |
| Visor Moat Clearances | `3.50u` bridge / `3.35u` side / `2.45u` vert | `3.70u` bridge / `3.65u` side / `2.85u` vert | R5 (`>= 2.0u` master, `>= 2.5u` small -> `1.42px` at 16px) |
| 3-Post Foot Width & Base Y | `3 x 4.40u` (`rf = 2.20u`), `y = 28.30` | `3 x 4.80u` (`rf = 2.40u`), `y = 29.20` | Matches Bricolage 800 stem; `x=16` post prevents mouth read |
| Twin Burrow Arches | `2 x 5.40u` (`ra = 2.70u`), apex `y = 22.60` | `2 x 5.80u` (`ra = 2.90u`), apex `y = 22.50` | Tangent-continuous Pac-Man ghost skirt + twin hutch burrows |

---

## 4. Self-Critique Against `PRINCIPLES.md` R1–R11 (Written Before the Recommendation)

| Rule | Direction A ("Gable Ghost") | Direction B ("Visor Hutch") |
|---|---|---|
| **R1 Subject first** (grounded in the hutch + product truth, combined with the user's Grokbot + Pac-Man ghost + hutch triad) | **PASS (Strongest architectural read).** The pitched gable roof with `1.80u` projecting eaves and twin lower burrow arches immediately reads as a built timber hutch that is simultaneously an alive ghost-bot. | **PASS (Strongest bot/visor + shelter read).** The hooded shell with a recessed upper loft bay and twin lower burrow arches houses the glowing Grokbot eyes inside the shelter, directly echoing the 3D mascot (`hutch-agent.webp`) and 2D bot sigils (`app.js`). |
| **R2 One bold move** | **PASS.** The pitched gable eaves overhang fused with the 3-post scalloped ghost skirt. | **PASS.** The nested `evenodd` loft visor (`solid shell -> knocked-out visor bay -> positive tilted eyes`) over the 3-post skirt. |
| **R3 Grid discipline & optical overshoot** | **PASS.** `32x32` grid (`4u` module); ridge apex overshoots to `y = 3.65` (`+0.35u`), rounded feet overshoot to `y = 28.30` (`+0.30u`). | **PASS.** `32x32` grid (`4u` module); dome crown overshoots to `y = 3.70` (`+0.30u`), rounded feet overshoot to `y = 28.30` (`+0.30u`). |
| **R4 Equal optical area for repeats** | **PASS.** Paired oval eyes have identical area (`pi * 2.35 * 3.05 = 22.52 sq u`), mirrored `±8°` tilt; outer feet match center post width (`4.40u`). | **PASS.** Paired positive oval eyes have identical area (`pi * 2.05 * 2.65 = 17.07 sq u`), mirrored `±8°` tilt; all three feet equal width (`4.40u`). |
| **R5 Designed counterform** (`>= 2u` master, `>= 2.5u` small) | **PASS.** Master minimum counterform is `4.50u` (inter-eye bridge) and `5.00u` (burrow arch width); Small minimum is `4.30u` (`2.15px` at 16px). | **PASS.** Master minimum counterform is `2.45u` (vertical visor moat above/below eyes); Small tier widens vertical moat to `2.85u` (`1.42px` at 16px) and horizontal moat to `3.65u`. |
| **R6 Two size tiers, redrawn** | **PASS.** Separate `dir_a_master_d` (`>=32px`) and `dir_a_small_d` (`16–24px`) with widened bleed, steeper eaves, and larger eyes. | **PASS.** Separate `dir_b_master_d` (`>=32px`) and `dir_b_small_d` (`16–24px`) with expanded `26u` width and enlarged visor moat. |
| **R7 Silhouette & squint-blur test** | **PASS (Edge to A).** Outer contour has both the pitched gable eaves at top AND the 3-post scalloped skirt at bottom—making the outer silhouette alone completely unique even under heavy blur. | **PASS.** Under `2.2px` squint blur, the dark recessed visor band and the 3-post skirt remain clearly distinct; outer contour alone is a domed ghost-hutch. |
| **R8 Mono test** (`1-colour` carries the mark) | **PASS.** Pure `evenodd` single path; zero dependence on emerald vs ink two-tone fills. | **PASS.** Because the eyes are positive islands inside the negative visor hole, `1-colour` mono renders the full 3-layer depth (`shell -> visor -> eyes`) automatically. |
| **R9 AI-tell audit** | **PASS.** No gradient, no neon-only dependence, no rounded-square tile wrapper, no sparkle/node motif, no generic monogram. | **PASS.** No gradient, no neon-only dependence, no rounded-square tile wrapper, no sparkle/node motif. |
| **R10 Remove one accessory** | **PASS.** Removed roof collar seam and base plinth; only 3 closed subpaths remain. | **PASS.** Removed external roof cap/ears; only 4 closed subpaths remain (`1` shell, `1` visor, `2` eyes). |
| **R11 Provenance** | **PASS.** 100% parametric Python bezier/arc construction recorded in `render_run6_directions.py`; zero tracing, zero stock, zero AI image gen. | **PASS.** 100% parametric Python bezier/arc construction recorded in `render_run6_directions.py`; zero tracing, zero stock, zero AI image gen. |

---

## 5. Pre-Screen Notes on Both Shapes (2026-10-29 — Not Clearance)

Executed 2026-10-29 via web search (3 targeted queries logged below; full trademark register figurative searches remain owed under B8/B10):

| Query (2026-10-29) | Scope | Result as observed | Legal status (risk rated, not clearance) |
|---|---|---|---|
| `logo gable roof ghost three legs two eyes OR house character scalloped bottom` | Web / design discovery | **Not found in the sources searched.** No existing software, AI, or commercial mark combining a pitched gable roof with projecting eaves, tilted oval eyes, and a 3-post/2-arch scalloped ghost base surfaced. | **Screened (web discovery only); unresolved.** Figurative register search under Vienna classes 26.4/26.5/07.01/04.05 not executed; counsel/owner decision required. |
| `logo domed ghost visor two eyes three legs OR hooded robot visor scalloped skirt` | Web / design discovery | Generic stock-icon descriptions of tripod sci-fi droids surfaced (`streamlinehq.com`); no specific software/AI brand mark matching the nested visor + 3-post burrow skirt geometry was found in the sources searched. | **Screened (web discovery only); unresolved.** Shares the broader "domed ghost / visor bot" cultural archetype (alongside Pac-Man ghosts, Phantom Wallet, Ghost CMS, Discord Clyde); figurative register search not executed; counsel/owner decision required. |
| `"Phantom wallet" logo OR "Ghost CMS" logo OR "Discord Clyde" logo shape geometry` | Category reference comparison | Phantom uses an asymmetrical side-swept ghost tail with circular eyes and no visor or gable; Discord Clyde uses a squircle controller body with top antenna bumps and no bottom burrow arches; Bandai Namco's Pac-Man ghost uses a 3-wave jagged triangular skirt and circular eyes with pupils. | **Screened; unresolved.** Neither Direction A nor Direction B copies any contour, proportion, eye treatment or skirt waveform from those marks. Not legal advice. |

---

## 6. Recommendation (Awaiting Human Pick)

**Lead Recommendation: Direction B ("Visor Hutch") — with Direction A ("Gable Ghost") as a close, high-distinctiveness alternative.**

- **Why Direction B ("Visor Hutch") is recommended first:**
  1. It achieves the richest synthesis of all three parts of the maintainer's brief (**Grokbot** visor + inward-tilted eyes, **Pac-Man ghost** domed 3-post/2-arch silhouette, and **Hutch** as an enclosing shelter with an upper loft window housing the bots inside).
  2. It visually unifies Hutch's existing product surfaces: the 3D marketing mascot (`website/assets/hutch-agent.webp`, which has a dark recessed visor and glowing eyes) and the 2D in-app bot avatars (`src/hutch/server/static/app.js` `ID_FACES`, which use `±8°` inward-tilted oval eyes) now clearly belong to the same family as the brand mark.
  3. Its nested `evenodd` construction (`outer shell -> dark visor loft -> positive gleaming eyes`) gives the mark unmistakable craft and depth in a single colour (`#34d399`, `#ededf0`, `#09090b`, or `#047857`), avoiding the flat "punched slab" feel of Rounds 1–12.
- **When to choose Direction A ("Gable Ghost") instead:**
  - Choose **Direction A** if you want the **outer silhouette alone** (through the projecting pitched timber-hutch eaves) to carry the "hutch" architecture at 16px, with maximum counterform openness (`only 3 subpaths`) and the strongest structural separation from any domed ghost mark.

### Human Pick Record (Gate for Task B Mark Deliverables)

- **Picked direction:** **Direction B — "Visor Hutch"** (hooded ghost-hutch dome + recessed Grokbot visor loft bay + twin gleaming tilted bot eyes + 3-post/2-burrow skirt)
- **Date:** `2026-10-29` (America/Vancouver), recorded via `ask_question` in Run 6 (`DECISION.md` D54)
- **Notes / refinement requested:** Maintainer Run 6 brief (`DECISION.md` D53): *"Take inspiration from grokbot, the ghost from pacman and the maining of the word hutch"* [sic]; selected recommended Direction B without further modification.
