# SLICE-7C.md — Product Dashboard (`src/hutch/server/`), "The Hutch Colony" Avatar & 5-State Motion Drop-in, and Tauri Desktop Icons (`desktop/icons/`)

- **Slice ID:** `SLICE-7C`
- **Run:** Master Prompt Run 4 / Pipeline Run 7
- **Date:** `2026-10-29`
- **Status:** **Verified -> Pending local commit**
- **Blockers addressed:**
  - `B6` — Repository integration gate: executes the product-dashboard (`src/hutch/server/`) half of the integration.
  - `B10` — Surface drift dashboard/desktop: reconciles dashboard icons, manifest, font, and lockup with `BRAND-GUIDELINES.md` Section 8; reconciles the desktop host icons with the selected "Visor Hutch" mark.
  - `U07` (`ASSET-INVENTORY.md`) — legacy `desktop/icons/` marked drift (`#28cd9d` on `#0f151e`, different hexagon geometry) replaced with the approved `#34d399` on `#09090b rx=7` plate family.

---

## 1. Exact Write Scope (3 seams, no generated CSS)

### 1.1 Avatar & 5-State Motion Seam (zero line-count growth)

| File | Before | After | Rule |
| :--- | :--- | :--- | :--- |
| `src/hutch/server/static/app.js` (`ID_HEADS` + `ID_FACES`, lines 1438-1461) | `14,266` lines | `14,262` lines (`-4`) | Replaced with the byte-identical 20-line block from `AVATAR-SYSTEM.md` Section 3 (8 Hutch Colony silhouettes, 8 shape-fitted `#0b1511` eye pairs); frozen baseline `14,532` respected, shrink-only. |
| `src/hutch/server/static/studio.css` (sigil motion block, lines 21-30) | `1,016` lines | `1,016` lines (`0`) | Replaced with the byte-identical 10-line block from `AVATAR-SYSTEM.md` Section 5.2 (idle / running / waiting / blocked / paused choreography, `body-work`, `eyes-scan`, `body-wait`, `eyes-wait`); frozen baseline `1,115` respected. |

Both blocks were extracted programmatically from `AVATAR-SYSTEM.md` and written with assertion guards on the exact target windows; the written regions were re-read and compared byte-for-byte to the documented blocks (`drop-in-evidence.json`).

### 1.2 Dashboard Brand Seam (`src/hutch/server/`)

1. **Staged byte-identical production assets** (`cp`, all `cmp` exit 0):
   - `src/hutch/server/static/`: `favicon.svg`, `favicon-32x32.png`, `favicon.ico`, `apple-touch-icon.png`, `site.webmanifest` (verbatim production manifest; `start_url: "/"` is correct for the dashboard).
   - `src/hutch/server/static/icons/`: `icon-192.png`, `icon-512.png`, `icon-192-maskable.png`, `icon-512-maskable.png`, `icon-192-monochrome.png`, `icon-512-monochrome.png`, `icon-monochrome.svg`.
2. **New `src/hutch/server/static/brand.css` (`19` lines):** `@font-face` for `"Bricolage Grotesque"` (`800`, `font-display: swap`) from the Slice 7A subset `/static/fonts/bricolage-grotesque-latin-800.woff2`; `.brand-wordmark` (Bricolage 800, `18px`, `-0.03em` tracking); and the documented lockup geometry (`BRAND-GUIDELINES.md` 3.2): `.ws-brand .brand, .topbar .brand { gap: 8px; }` so both headers render the `22px` Small-tier mark + `8px` gap + `18px` wordmark. Not generated CSS; `brand-tokens.css` remains the untouched generated token sheet.
3. **`src/hutch/server/static/index.html` (`184` -> `188` lines):** replaced the legacy data-URI favicon with the Section 8 icon/manifest links (absolute `/static` paths with 8-hex content-hash queries); `brand.css` is the **last stylesheet** in `<head>`; the sidebar lockup is now the `22px` "Visor Hutch" Small-tier single compound path (`fill="var(--brand)" fill-rule="evenodd"`, no stroke/circle) with `<span class="brand-name brand-wordmark">hutch</span>`.
4. **`src/hutch/server/templates/base.html` (`66` -> `71` lines):** same icon/manifest head links and `brand.css`; the topbar lockup is the same `22px` Small-tier single path (`fill="var(--accent)"`) with `<span class="brand-wordmark">hutch</span>`. Server-page titles, nav, footer, and CSRF markup are unchanged.

Content-hash queries: `favicon.svg?v=cada88dd`, `favicon-32x32.png?v=2d2d3d2c`, `favicon.ico?v=9096fd72`, `apple-touch-icon.png?v=2351b1e0`, `site.webmanifest?v=187682d3`, `brand.css?v=581315bf` (the four favicon hashes match the Slice 7B marketing-site values exactly; the `brand.css` hash changed from `3b517691` to `581315bf` when the lockup geometry was aligned, and both HTML references were re-stamped).

### 1.3 Tauri Desktop Seam (`desktop/icons/`)

1. **New deterministic generator** `.pipeline/brand/2026-10/assets/build_desktop_icons.py` (sha256 `3bd9c1104cdfe108…`): Playwright Chromium rasters of the approved composition — full-bleed `#09090b` `rx=7` plate + `hutch-mark-master.svg` compound path `#34d399` `evenodd` at `translate(2.88, 2.88) scale(0.82)`, `device_scale_factor=1`, opaque plate with transparent corners outside the plate (Lead-approved Option A). Two consecutive runs are byte-identical.
2. **Generated** into `.pipeline/brand/2026-10/assets/production/desktop/` (the source directory the slice prompt expected; it did not exist yet and was produced here) and **staged byte-identically** into `desktop/icons/`:
   - `32x32.png` `1,091 B`, `128x128.png` `4,216 B`, `128x128@2x.png` (256x256) `8,682 B`, `icon.png` (1024x1024) `39,016 B`, all 8-bit RGBA;
   - `icon.ico` `18,481 B` with PNG payloads at 16/32/48/64/128/256;
   - `icon.icns` `104,223 B` with 11 entries (`icp4` 16, `icp5` 32, `icp6` 64, `ic07` 128, `ic08` 256, `ic09` 512, `ic10` 1024, `ic11` 32, `ic12` 64, `ic13` 256, `ic14` 512);
   - `icon.svg` `1,096 B` (1024x1024, `viewBox 0 0 32 32`, plate + master path) replacing the stale legacy hexagon vector.
3. `desktop/tauri.conf.json` and `desktop/tauri.bundle.conf.json` are unchanged (the bundle list already names `icons/icon.png`, `icons/icon.ico`, `icons/icon.icns`).
4. `PACKAGE-MANIFEST.json` refreshed with the generator's exact `production/`+`press-kit/` walk: `86` entries, including the `7` new `production/desktop/*` hashes (and the pre-existing `press-kit/README.md` that the previous commit's manifest had not indexed).

**Parity proofs:** `icon.icns` `ic14` (512 px) payload is byte-identical to the approved `production/icons/icon-512.png` (`ce3da0b9…`); `icon.svg` rendered at 1024 by Chromium is byte-identical to `icon.png`; every staged file is `cmp`-identical to its generated source.

---

## 2. Acceptance Criteria & Results

| # | Criterion | Result |
| :--- | :--- | :--- |
| 1 | `app.js` `ID_HEADS`/`ID_FACES` and `studio.css` sigil-motion block are byte-identical to `AVATAR-SYSTEM.md` Sections 3 / 5.2, with zero line growth and frozen-baseline compliance | **PASS** — 20-line JS block inserted at 1438 (`app.js` `14,266` -> `14,262`), 10-line CSS block inserted at 21 (`studio.css` `1,016` -> `1,016`); `node --check` passes; `drop-in-evidence.json` records doc/inserted-block hashes. |
| 2 | Dashboard head/icon/manifest/font/lockup wiring correct on both the SPA root and server-rendered pages | **PASS** — 5 icon/manifest links `200` with correct content types; production manifest 6 icons resolve; `document.fonts.check('800 16px "Bricolage Grotesque"')` true; computed `.brand-wordmark` = Bricolage Grotesque 800 `18px`, `-0.54px` tracking on both surfaces; lockup geometry measured as `22px` mark + `8px` gap + `18px` wordmark on both (BRAND-GUIDELINES 3.2); 22px Small-tier mark is one path, zero circles/strokes; wordmark text `hutch`; no page errors; no horizontal overflow. |
| 3 | Avatar/identity-picker e2e invariants (8 distinct silhouettes/colours, 2 ink `#0b1511` eyes each, 48-point `Path2D` containment, >=6 distinct face rows, balanced inward tilt, 44px controls, picker/preview parity, no browser errors) | **PASS** — `tests/e2e/test_design_system.py::test_flat_mascot_eyes_stay_inside_every_silhouette` **1 passed** (Chromium 153.0.8010.12, minimum eye contrast 5.95). |
| 4 | Shared-token and roster identity invariants | **PASS** — `test_shared_design_tokens_render_consistently_across_all_surfaces` **1 passed** (`#workspace .brand-name` still `hutch`); `tests/e2e/test_browser.py::test_bot_roster_pins_persist_and_simple_mascots_stay_distinct` **1 passed**. |
| 5 | Focused non-browser tests and hygiene audits | **PASS (with one known-unrelated pre-existing finding)** — `tests/test_site_tokens.py` **8 passed** (`brand-tokens.css` remains byte-identical to `website/tokens.css`); `tests/test_context_hygiene.py` passed; `scripts/audit_emoji.py` clean; `scripts/audit_context_hygiene.py` reports only `tests/test_commit_attribution.py` (419 lines, concurrent session's untracked file — untouched by this slice). Slice files: `app.js` 14,262 <= 14,532, `studio.css` 1,016 <= 1,115, `brand.css` 19 new, `index.html` 188 < 400. |
| 6 | Whole-file `tests/e2e/test_design_system.py` | **PASS for slice** — run 1: 2 failed / 17 passed (204.48s); run 2: 1 failed / 18 passed (213.86s). The only deterministic failure is `test_persona_live_preview_is_explicit_isolated_cancellable_and_responsive` (40px button vs 44px) caused by the concurrent session's uncommitted `hutch-form-controls.css` form migration, not this slice; the run-1 `test_answer_feedback…` timeout is a flake (passes isolated and in run 2). No avatar, token, dashboard or lockup failure. |
| 7 | Desktop icon family is valid, deterministic, and matches the approved plate | **PASS** — PNG dimensions/channels verified with `file`/`identify`; ICO 6 payloads and ICNS 11 entries parsed with matching IHDR dimensions and declared lengths; `cmp` parity generated vs staged; `icon-grid.png` visually inspected (no white corners, no legacy hexagon). |
| 8 | Rendered dashboard/desktop evidence visually inspected via image reads | **PASS** — see Section 4. |

---

## 3. Verification-Discovered Defect (found, fixed, re-verified before sign-off)

- **Symptom (verifier):** the SPA wordmark computed to `Geist` 650, not Bricolage Grotesque: `brand.css` loaded before `studio.css`, whose `.brand-name { font: 650 var(--fs-lg)/1 var(--font-ui); }` shorthand reset `font-family`/weight at equal specificity.
- **Fix (Lead, dashboard scope):** moved `brand.css` from after `style.css` to the **last stylesheet** in `src/hutch/server/static/index.html` (with an explanatory comment); `brand.css` content and its `?v=3b517691` hash are unchanged; `index.html` is now 188 lines (still < 400).
- **Re-verification (Lead):** SPA and `/models` both compute `font-family: "Bricolage Grotesque", …`, `font-weight: 800`, `font-size: 18px`; `document.fonts.check(...)` true; single 22px path per lockup; all icon links 200; manifest 6 icons; no page errors; no overflow. Verifier re-ran its capture against the fixed file and recorded the PASS.

**Follow-up F2 — lockup geometry aligned to the governing docs:** the verifier's report noted the measured headers were `22px` mark + `12px` gap + `18px` wordmark (SPA) and `+ 16px` wordmark (server pages), while `BRAND-GUIDELINES.md` 3.2 and `docs/brand-assets.md:53` specify the Studio sidebar / Jinja header as `22px` mark + `8px` gap + `18px` wordmark. Fixed in `brand.css` (gap rule + `font-size: 18px`; `brand.css` now `19` lines, sha256 `581315bf…`) and both `?v=` references re-stamped. Lead re-measured both surfaces: mark `22x22`, CSS and visual gap `8px`, wordmark Bricolage Grotesque `800` `18px`, `-0.54px` tracking, font loaded, no page errors, no overflow. Verifier re-ran its extended capture against the final tree: **65/65 checks PASS** (its report now records `SLICE-7C-F1` and `SLICE-7C-F2` as fixed-and-re-verified, zero slice-caused failures).

---

## 4. Evidence

- `.pipeline/brand/2026-10/evidence/slice-7c/avatar-motion/drop-in-evidence.json` — before/after line counts, file and inserted-block SHA-256, byte-identical round-trip proof, frozen baselines, keys/keyframes.
- `.pipeline/brand/2026-10/evidence/slice-7c/desktop-icons/` — `desktop-icons-evidence.json` (hashes, container listings, payload parity, alpha, determinism, environment, Option A decision note, U07 resolution), `sha256sums.txt`, `parity.txt`, `file-identify.txt`, `containers.txt`, `alpha-pixels.txt`, `generator-run.log`, `legacy-before.json`, `icon-grid.png` (2607x1428).
- `.pipeline/brand/2026-10/evidence/slice-7c/verification/` — `VERIFICATION.md`, `verification-report.json`, `capture-results.json` (**65/65 checks PASS after F2**: 54/55 initial -> 55/55 after F1 -> 65/65 after F2 with the added lockup-geometry checks), `capture_slice_7c.py`, `spa-brand-closeup.png`, `server-page-brand.png`, plus the e2e artifact trees:
  - `artifacts/mascot-eye-review-2026-10-10/` — `desktop.png` (1440x960), `shape-picker-{desktop,tablet,phone,compact-phone}.png`, `face-{orb,capsule,bean,drop,pebble,shield,triangle,hex}.png`, `phone-studio.png`, `phone-roster.png`, `validation.json`;
  - `artifacts/design-system/` — shared-token Studio/Connections/marketing screenshots (1440x960, 900x1024, 390x844);
  - `artifacts/` — whole-file design-system e2e screenshots for the other surfaces.
- **Visual inspection record (Lead and verifier):** `mascot-eye-review-2026-10-10/desktop.png` shows the 22px Visor Hutch mark + `hutch` wordmark in the sidebar and all 8 Hutch Colony residents in the roster (Ghost Bell, Gable Hutch, Hopper Hare, Lantern Cowl, Transceiver Pod, Bastion Keep, Beacon Spire, Mecha Chassis) with eyes inside each silhouette; `shape-picker-desktop.png` shows the 8 distinct colony shapes and two-row 44px controls; the desktop `icon-grid.png` shows the approved plate at 1024/512/256/128/32 px with transparent corners and no legacy hexagon.

---

## 5. Residual Follow-ups (out of this slice's write scope)

1. **Title drift (pre-existing, `APP-BRAND-AUDIT.md`):** `static/index.html` still uses `hutch — your personal assistant`, and `templates/base.html` still renders `<View> - hutch`; `BRAND-GUIDELINES.md` Section 8 specifies `<View> — Hutch`. Left untouched here because this slice is scoped to icons/mark/wordmark/font and changing page titles alters every server page's label; queue as a small follow-up slice.
2. **Canonical-doc reconciliation:** `docs/brand-assets.md` and `docs/design-system.md` (updated in Slice 7A) still describe the website/mark surfaces; add the dashboard (`/static/favicon*`, `site.webmanifest`, `brand.css`, 22px lockup) and desktop (`desktop/icons/` plate family) rows in a docs follow-up (`B10` residue).
3. **Commit:** no local commit was made in this session. The shared working tree carries a concurrent session's uncommitted changes across many of the same files (including `app.js`); committing only this slice's files would also stage that session's hunks, which `AGENTS.md` forbids. The slice is verified and commit-ready once the concurrent session's work is committed or cleared.
