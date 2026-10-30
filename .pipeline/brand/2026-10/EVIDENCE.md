# EVIDENCE.md — Validation Evidence (Run 4 / Pipeline Run 7, Slice 7A)

Date: `2026-10-29`
Slice: `SLICE-7A` — Licence, Font & Brand Docs Reconciliation
Visual Proof Artifact: `.pipeline/brand/2026-10/evidence/slice-7a/slice-7a-font-and-doc-proof.png` (`172,201 B`, `2400x1080` at DPR 2)

---

## 1. Checksum & Byte-Parity Verification (`2026-10-29`)

| Path | Bytes | SHA-256 | Parity Check |
| :--- | :--- | :--- | :--- |
| `website/assets/fonts/bricolage-grotesque-latin-800.woff2` | `47,260` | `55d3acddbb67185090064db83950341bda78539dd5fbaab3cbb02c7cfd270b9c` | Matches `.pipeline/brand/2026-10/assets/production/fonts/bricolage-grotesque-latin-800.woff2` (`cmp` exit 0) |
| `src/hutch/server/static/fonts/bricolage-grotesque-latin-800.woff2` | `47,260` | `55d3acddbb67185090064db83950341bda78539dd5fbaab3cbb02c7cfd270b9c` | Matches `website/assets/fonts/bricolage-grotesque-latin-800.woff2` (`cmp` exit 0) |
| `website/assets/fonts/OFL-bricolage-grotesque.txt` | `4,403` | `4b5a7d8f37f5602621c8a8d7358a6a2e71317e6c231c661e15aef0275d3e07ba` | Matches `.pipeline/brand/2026-10/assets/production/fonts/OFL-bricolage-grotesque.txt` (`cmp` exit 0) |
| `src/hutch/server/static/fonts/OFL-bricolage-grotesque.txt` | `4,403` | `4b5a7d8f37f5602621c8a8d7358a6a2e71317e6c231c661e15aef0275d3e07ba` | Matches `website/assets/fonts/OFL-bricolage-grotesque.txt` (`cmp` exit 0) |
| `THIRD_PARTY_NOTICES.md` | `6,073` | `8a457f7389e10364f5d26deed0dbff0c47cd75ba3dfc19a80b18d9171139a4c8` | Source of truth for `scripts/stamp_site_assets.mjs:22-24` |
| `website/THIRD_PARTY_NOTICES.txt` | `6,073` | `8a457f7389e10364f5d26deed0dbff0c47cd75ba3dfc19a80b18d9171139a4c8` | Matches `THIRD_PARTY_NOTICES.md` (`cmp` exit 0) |
| `src/hutch/server/static/THIRD_PARTY_NOTICES.txt` | `6,073` | `8a457f7389e10364f5d26deed0dbff0c47cd75ba3dfc19a80b18d9171139a4c8` | Matches `THIRD_PARTY_NOTICES.md` (`cmp` exit 0) |
| `docs/brand-assets.md` | `9,913` | `d84b41648403db47ec41fdb93e70f2c57dc563df583784a4b41d3ec4e2b6308a` | Updated (`86` lines, `< 400` line ceiling) |
| `docs/design-system.md` | `21,796` | `c473e12192a30bf9d33598dde365e320e4cd1acc45847323861214384cd70557` | Updated (`331` lines, `< 400` line ceiling) |

---

## 2. Automated Test & Audit Results (`2026-10-29`)

1. **Token & CSS Parity Test Suite:**
   - Command: `uv run --frozen --no-sync pytest -q --no-header --tb=line tests/test_site_tokens.py`
   - Result: **`8 passed in 4.25s`** (exit code `0`).
2. **Tool Contract & Constitution Audits:**
   - Command: `uv run --frozen --no-sync python scripts/audit_tool_contracts.py && uv run --frozen --no-sync python scripts/audit_constitution.py`
   - Result:
     - `Tool contract check passed (40 registered tools; canonical schemas certifiable; specs match).`
     - `Constitution check passed (3 roles, 14 rules; every rule maps to existing enforcement).`
3. **Emoji Audit:**
   - Command: `uv run --frozen --no-sync python scripts/audit_emoji.py`
   - Result: **`audit:emoji — clean`** (exit code `0`).
4. **Note on `npm run check:agent` in the shared dirty tree:**
   - The shared working tree contains untracked/modified files from another active session (`.file-size-baseline.json`, `scripts/audit_context_hygiene.py`, `scripts/generate_agent_map.py`, `.ai/`). In that session's work-in-progress state, `audit_context_hygiene.py` flags pre-existing `tests/test_commit_attribution.py` (`419` lines, untouched by our session) and `generate_agent_map.py --check` reports `.ai/repo-map.generated.md` stale. Per `AGENTS.md` ("Never revert, clean or reformat another task's uncommitted work"), those untracked other-session files were not modified or staged. Every file touched by Slice 7A passes the `< 400`-line rule (`THIRD_PARTY_NOTICES.md` = `112` lines, `docs/brand-assets.md` = `86` lines, `docs/design-system.md` = `331` lines).

---

## 3. Visual Inspection Record (`read_file` on Rendered PNG)

- **File opened and visually inspected:** `.pipeline/brand/2026-10/evidence/slice-7a/slice-7a-font-and-doc-proof.png` (`2400x1080` at DPR 2, rendered with headless Playwright Chromium `153.0.8010.12`).
- **What was verified visually:**
  1. **Box 1 (`website/assets/fonts/bricolage-grotesque-latin-800.woff2`):** Loaded directly from the staged repository path; renders `hutch.` at `20px` weight `800` (`-0.03em` tracking, `#34d399` period) beside the `26px` `"Visor Hutch"` Master mark on `#16161a` panel over `#0f0f12` surface. Ink-trapped joins on `h`/`u`/`c` and baseline alignment with the mark's outer posts are crisp.
  2. **Box 2 (`src/hutch/server/static/fonts/bricolage-grotesque-latin-800.woff2`):** Loaded directly from the staged server static font path; renders the compact operator variant `hutch` at `18px` beside the `22px` `"Visor Hutch"` Small-tier redraw. The widened visor moat (`2.85u` vertical, `3.65u` horizontal) keeps the twin tilted eyes completely distinct at `22px`.
  3. **Box 3 (Light-surface rule from `docs/brand-assets.md` & `docs/design-system.md`):** Verifies the `#047857` (`emerald-700`) mark and period beside `#09090b` (`ink-950`) `hutch` wordmark on light surfaces (`4.69:1` on `#ededf0`, `5.48:1` on `#ffffff`).
  4. **Box 4 (Reconciled `docs/design-system.md` Shared Visual Contract table):** Renders all eight neutral/brand swatches from `website/tokens.json` (`#09090b`, `#0f0f12`, `#16161a`, `#1c1c21`, `#ededf0`, `#a3a3ae`, `#8e8e99`, `#34d399` + `#052e21`), confirming visual step separation and legible contrast.

---

## 4. "The Hutch Colony" 8-Resident Bot Avatar System Verification (`D59`/`D60`)

- **File opened and visually inspected:** `.pipeline/brand/2026-10/evidence/avatars/avatar-family-sheet.png` (`400,419 B`, `2960x1840` at DPR 2, generated by `.pipeline/brand/2026-10/assets/concepts/render_avatar_family.py`).
- **Chromium `Path2D` + SVG DOM Invariant Check (`tests/e2e/test_design_system.py:1141-1207` & `tests/e2e/test_browser.py:8614-8641`):**
  - Command: `uv run --frozen --no-sync python .pipeline/brand/2026-10/assets/concepts/render_avatar_family.py`
  - Result: **`ALL Path2D + getBBox + face_rows (8/8 unique) e2e invariants PASSED!`**
  - All 8 resident silhouettes (`Ghost Bell`, `Gable Hutch`, `Hopper Hare`, `Lantern Cowl`, `Transceiver Pod`, `Bastion Keep`, `Beacon Spire`, `Mecha Chassis`) verified visually at `96px` (with `8u` grid and `cy` face-row axis), `40px`, `28px`, `20px`, in a `36px` live operator roster simulation with status pips (`running`, `waiting`, `paused`, `blocked`), and in a `44x44px` `currentColor` identity shape picker.
- **5-State Motion & Working Choreography Verification (`2026-10-29`):**
  - `.pipeline/brand/2026-10/evidence/avatars/avatar-motion-sheet.png` (`430,441 B`, `3040x1680` at DPR 2) rendered via `.pipeline/brand/2026-10/assets/concepts/render_avatar_motion_sheet.py` and visually inspected via `read_file`.
  - `88/88` resident × keyframe-extreme `Path2D.isPointInPath` eye-containment checks passed across all 11 motion offsets (`idle`, `working` scan `-3.2px/+3.2px`, `waiting` perk `-2.2px`, `alert` squint, `paused` rest).
  - Exact 10-line replacement for `src/hutch/server/static/studio.css:21-30` documented in `AVATAR-SYSTEM.md` Section 5.2 (`0` line-count growth on frozen `studio.css`).

---

## 3. Slice 7B Validation Evidence (`website/` Marketing Site Integration)

- **Commands Executed & Passed:**
  - `npm run build:css:site` -> compiled `website/app.css` (`362ms`), `website/styles.min.css` (`478ms`), and stamped `18` local asset references in `website/index.html`.
  - `uv run --frozen --no-sync pytest -q --no-header --tb=line tests/test_site_tokens.py` -> `8 passed in 1.31s`.
  - `uv run --frozen --no-sync pytest -q --no-header --tb=line tests/e2e/test_website.py -k "test_local_asset_urls_use_current_content_hashes or test_landing_initial_transfer_stays_within_review_budget_and_art_loads_on_demand or test_structured_data_and_discovery_metadata_match_the_page"` -> `3 passed in 8.95s`.
  - `uv run --frozen --no-sync python scripts/audit_emoji.py` -> `audit:emoji — clean (scanned 2895 files, 10 waiver(s))`.
- **Visual Captures Rendered & Inspected via `read_file`:**
  - `.pipeline/brand/2026-10/evidence/slice-7b/website-desktop-hero.png` (`1440x900` @ DPR 2): Verified `26px` `"Visor Hutch"` Master mark + Bricolage Grotesque 800 `hutch.` wordmark in sticky navbar (`getComputedStyle(.brand-wordmark).fontFamily` starts with `"Bricolage Grotesque"`).
  - `.pipeline/brand/2026-10/evidence/slice-7b/website-mobile-drawer.png` (`390x844` @ DPR 2, `#menu-drawer` open): Verified `22px` `"Visor Hutch"` Small tier mark + `hutch.` wordmark in mobile navigation dialog header.
  - `.pipeline/brand/2026-10/evidence/slice-7b/website-desktop-footer.png` (`1440x900` @ DPR 2): Verified `22px` `"Visor Hutch"` Small tier mark + `hutch.` wordmark in site footer.

---

## 4. Slice 7C Validation Evidence (`src/hutch/server/` Dashboard + Colony Avatars/Motion + `desktop/icons/` Tauri Icons)

- **Independent verification record:** `.pipeline/brand/2026-10/evidence/slice-7c/verification/VERIFICATION.md` and `verification-report.json` (verifier verdict **PASS**; extended capture **65/65 checks PASS** after follow-up fixes F1 and F2: 54/55 initial -> 55/55 after F1 -> 65/65 after F2).
- **Commands Executed & Passed:**
  - `UV_CACHE_DIR=/tmp/hutch-uv-cache uv run --frozen --no-sync pytest -q --no-header --tb=line tests/test_site_tokens.py` -> `8 passed in 1.12s` (shared `brand-tokens.css` byte-identical to `website/tokens.css`).
  - `... python scripts/audit_emoji.py` -> clean (2901 files, 10 waivers).
  - `... python scripts/audit_context_hygiene.py --report` -> `637` source files, `118` over 400, `117` frozen; only known-unrelated `tests/test_commit_attribution.py` (`419` lines) finding; `app.js` `14,262` (cap `14,532`), `studio.css` `1,016` (cap `1,115`), `brand.css` `19` new.
  - `... pytest -q --no-header --tb=line tests/e2e/test_design_system.py::test_flat_mascot_eyes_stay_inside_every_silhouette` -> `1 passed` (`validation.json`: 8 silhouettes, 8 colours, minimum eye contrast `5.95`, no page errors).
  - `... pytest -q --no-header --tb=line tests/e2e/test_design_system.py::test_shared_design_tokens_render_consistently_across_all_surfaces` -> `1 passed`.
  - `... pytest -q --no-header --tb=line tests/e2e/test_browser.py::test_bot_roster_pins_persist_and_simple_mascots_stay_distinct` -> `1 passed`.
  - Whole-file `tests/e2e/test_design_system.py` -> `1 failed / 18 passed` post-fix (245.23s); only failure is the known-unrelated concurrent-session persona form-migration item (40px run button vs 44px); the run-1 `test_answer_feedback…` timeout did not reproduce.
  - Desktop generator (deterministic, two runs byte-identical): `32x32.png` `000e12e9…`, `128x128.png` `7cca93c2…`, `128x128@2x.png` `56dd8a83…`, `icon.png` `68196a9c…`, `icon.ico` `992bd364…` (6 PNG payloads), `icon.icns` `330eb42e…` (11 entries; `ic14` == approved `icon-512.png` `ce3da0b9…`), `icon.svg` `aa7dde57…`; `cmp` parity generated vs staged for all 7.
- **Visual Captures Inspected via `read_file` (Lead and verifier):**
  - `.pipeline/brand/2026-10/evidence/slice-7c/verification/artifacts/mascot-eye-review-2026-10-10/desktop.png` (`1440x960`): sidebar `22px` Visor Hutch Small-tier mark + Bricolage `hutch` wordmark; all 8 colony residents in the roster with two ink eyes inside each silhouette.
  - `.../shape-picker-desktop.png` (`736x414`): 8 distinct colony silhouettes (Ghost Bell, Gable Hutch, Hopper Hare, Lantern Cowl, Transceiver Pod, Bastion Keep, Beacon Spire, Mecha Chassis) with 44px shape/colour controls and live preview.
  - `.../spa-desktop.png`, `spa-brand-closeup.png`, `server-page-topbar.png`, `server-page-brand.png`, `server-page-full.png`: computed wordmark family/weight/size and `22px` mark measured on both surfaces; no layout breakage.
  - `.pipeline/brand/2026-10/evidence/slice-7c/desktop-icons/icon-grid.png` (`2607x1428`): approved `#09090b` `rx=7` plate with `#34d399` Visor Hutch master mark at 1024/512/256/128/32 px, transparent corners, no white blocks and no legacy hexagon.


