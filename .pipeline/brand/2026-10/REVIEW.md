# REVIEW.md — Independent Slice Review Record (Run 4 / Pipeline Run 7, Slice 7A)

Date: `2026-10-29`
Slice Reviewed: `SLICE-7A` — Licence, Font & Brand Docs Reconciliation
Reviewer Role: Brand Identity Lead (post-execution verification against acceptance criteria, `BRAND-GUIDELINES.md`, legal rules, and `AGENTS.md`)

---

## 1. Acceptance Criteria Audit

| # | Criterion (`SLICE-7A.md`) | Verdict | Evidence |
| :--- | :--- | :--- | :--- |
| 1 | `bricolage-grotesque-latin-800.woff2` and `OFL-bricolage-grotesque.txt` staged in both `website/assets/fonts/` and `src/hutch/server/static/fonts/` with exact byte parity | **PASS** | `sha256sum` identical across all copies (`55d3acddbb67185090064db83950341bda78539dd5fbaab3cbb02c7cfd270b9c` for `.woff2`, `4b5a7d8f37f5602621c8a8d7358a6a2e71317e6c231c661e15aef0275d3e07ba` for `OFL-bricolage-grotesque.txt`). |
| 2 | `THIRD_PARTY_NOTICES.md`, `website/THIRD_PARTY_NOTICES.txt`, and `src/hutch/server/static/THIRD_PARTY_NOTICES.txt` byte-identical, zero stale `Archivo` references, accurate `Geist` + `Bricolage Grotesque` OFL 1.1 notices (`B9`) | **PASS** | All three files share SHA-256 `8a457f7389e10364f5d26deed0dbff0c47cd75ba3dfc19a80b18d9171139a4c8`; `grep -i archivo THIRD_PARTY_NOTICES.md website/THIRD_PARTY_NOTICES.txt src/hutch/server/static/THIRD_PARTY_NOTICES.txt` returns 0 matches. |
| 3 | `docs/brand-assets.md` and `docs/design-system.md` reconciled with `BRAND-GUIDELINES.md`, `COLOUR-SYSTEM.md`, and `website/tokens.json` (`B10` doc drift) | **PASS** | `docs/brand-assets.md` documents the two-tier `"Visor Hutch"` logomark (`>= 25px` Master, `16-24px` Small), Bricolage Grotesque 800 `"hutch."` / `"hutch"` wordmark, dark & light token table (`#047857` on light surfaces), and non-clearance rules. `docs/design-system.md` replaces the stale blue-tinted `#05070a`/`#080c12` table with the governing `#09090b`/`#0f0f12`/`#16161a`/`#1c1c21` `website/tokens.json` ramp (`D12`) and clarifies that in-app 2D assistant avatars remain visor-less while the product logomark is `"Visor Hutch"`. |
| 4 | Focused tests & hygiene checks pass | **PASS** | `tests/test_site_tokens.py` (`8 passed`), `audit_tool_contracts.py` (passed), `audit_constitution.py` (passed), `audit_emoji.py` (clean). |
| 5 | Visual evidence rendered and opened/inspected | **PASS** | `.pipeline/brand/2026-10/evidence/slice-7a/slice-7a-font-and-doc-proof.png` and `.pipeline/brand/2026-10/evidence/avatars/avatar-family-sheet.png` rendered at DPR 2 and inspected via `read_file`. |
| 6 | "The Hutch Colony" 8-resident bot avatar system (`AVATAR-SYSTEM.md`) verified against `DESIGN.md` and e2e invariants | **PASS** | All 8 silhouettes pass 48-point `Path2D` eye containment (`inHead: True`), `1.0 <= h/w <= 1.35`, mirrored tilt (`sum == 0`), `8/8` unique vertical face-row heights (`cy = 25.6..39.8`), and zero line-count growth for Slice 7C drop-in. |

---

## 2. Non-Negotiables & Guardrail Check

- **No legal clearance or non-infringement claim:** Verified in `docs/brand-assets.md:7-8,44,82-83` ("not a legal opinion or a grant of trademark rights"; "Do not present the Hutch logomark or wordmark as a registered trademark").
- **No unlicensed or unprovenanced assets:** `bricolage-grotesque-latin-800.woff2` is subset from upstream Bricolage Grotesque under SIL OFL 1.1 and shipped alongside verbatim `OFL-bricolage-grotesque.txt`.
- **No interference with other sessions' uncommitted work:** Verified via `git status --short`; only Slice 7A paths + `.pipeline/brand/2026-10/**` were touched.
- **Verdict:** **APPROVED FOR LOCAL COMMIT (`docs(brand): reconcile font subsets, notices and brand docs (slice 7a)`).**

---

## 2. Independent Review Record — Slice 7B (`website/` Brand, Icon, Manifest & Wordmark Integration) + Avatar 5-State Motion

- **Date:** `2026-10-29`
- **Scope Verified:**
  1. `website/src/input.css` adds `@font-face` (`Bricolage Grotesque` weight `800`) and `.brand-wordmark` without touching frozen `website/styles.css` (`591` lines unchanged).
  2. `website/index.html` wires `favicon.svg?v=cada88dd`, `favicon-32x32.png?v=9be9dd74`, `favicon.ico?v=9096fd72`, `apple-touch-icon.png?v=2351b1e0`, `site.webmanifest?v=c15b3838`, and `og-card-1200x630.png?v=2cf67f59`, and replaces all 3 legacy hexagon SVGs (`26px` navbar -> `"Visor Hutch"` Master path; `22px` mobile drawer and `22px` footer -> `"Visor Hutch"` Small path).
  3. All 18 local asset references in `website/index.html` pass `test_local_asset_urls_use_current_content_hashes`, initial transfer stays within the `900 KB` budget (`test_landing_initial_transfer_stays_within_review_budget_and_art_loads_on_demand`), and structured data / discovery metadata match (`test_structured_data_and_discovery_metadata_match_the_page`).
  4. Rendered PNGs (`website-desktop-hero.png`, `website-mobile-drawer.png`, `website-desktop-footer.png`, and `avatar-motion-sheet.png`) were opened and inspected with `read_file`.
- **Verdict:** **APPROVED FOR LOCAL COMMIT (`brand(website): integrate Visor Hutch mark, Bricolage wordmark, icons and social cards (slice 7b)`).**

---

## 3. Independent Review Record — Slice 7C (Product Dashboard `src/hutch/server/` + "The Hutch Colony" Avatar/Motion Drop-in + Tauri Desktop Icons)

- **Date:** `2026-10-29`
- **Reviewer role:** Brand Identity Lead post-execution review against `SLICE-7C.md`, `BRAND-GUIDELINES.md`, `AVATAR-SYSTEM.md`, `AGENTS.md`, and the independent verifier's `.pipeline/brand/2026-10/evidence/slice-7c/verification/VERIFICATION.md`.
- **Acceptance audit:**
  1. **Avatar/motion drop-in:** PASS — both blocks extracted programmatically from `AVATAR-SYSTEM.md` Sections 3 / 5.2 and written with target-window guards; round-trip byte-identical; `app.js` `14,266` -> `14,262` (`-4`), `studio.css` `1,016` -> `1,016` (`0`); `node --check` passes; frozen caps `14,532` / `1,115` respected.
  2. **Dashboard brand wiring:** PASS — 12 byte-identical staged assets; 5 icon/manifest links `200` with correct content types; production manifest 6 icons resolve; Bricolage Grotesque `800` `18px` computed on SPA and `/models`; lockup measured `22px` mark + `8px` gap + `18px` wordmark per `BRAND-GUIDELINES.md` 3.2; one compound path, no stroke/circle; no page errors or overflow; verifier's final extended capture **65/65 checks PASS** after fixes F1/F2.
  3. **Avatar/identity-picker e2e:** PASS — `test_flat_mascot_eyes_stay_inside_every_silhouette` `1 passed` (8 distinct silhouettes/colours, 2 ink `#0b1511` eyes each, 48-point `Path2D` containment, 8 distinct face rows, 44px controls, picker/preview parity, minimum eye contrast `5.95`).
  4. **Shared-token + roster e2e:** PASS — `test_shared_design_tokens_render_consistently_across_all_surfaces` `1 passed` (`#workspace .brand-name` = `hutch`); `test_bot_roster_pins_persist_and_simple_mascots_stay_distinct` `1 passed`.
  5. **Focused tests / audits:** PASS with one known-unrelated pre-existing finding — `tests/test_site_tokens.py` `8 passed`; `scripts/audit_emoji.py` clean; `scripts/audit_context_hygiene.py` flags only `tests/test_commit_attribution.py` (`419` lines, concurrent session). Slice files within caps.
  6. **Whole-file `tests/e2e/test_design_system.py`:** `1 failed / 18 passed` post-fix; the only deterministic failure is the concurrent session's form-migration persona-button height (40px vs 44px), attributed by file/rule/mtime; no Slice 7C failure.
  7. **Desktop icon family:** PASS — valid multi-size ICO (`6` PNG payloads) and ICNS (`11` entries); `ic14` payload byte-identical to the approved `production/icons/icon-512.png`; `icon.svg` render byte-identical to `icon.png`; deterministic generator; staged `cmp`-identical; `tauri.bundle.conf.json` untouched; `PACKAGE-MANIFEST.json` re-indexed (`86` entries).
  8. **Visual evidence:** PASS — SPA sidebar `22px` Visor Hutch mark + `hutch` wordmark and all 8 Hutch Colony residents inspected at roster size; shape-picker grid inspected; desktop icon contact sheet inspected (transparent corners, no legacy hexagon).
- **Verification-found fixes applied before sign-off:** `F1` brand.css cascade on the SPA (`brand.css` now loads last) and `F2` lockup geometry (`22px` / `8px` / `18px`); both re-measured green on SPA and server pages (details in `SLICE-7C.md` Section 3 and `HANDOFF.md` Section 3).
- **Non-negotiables:** no generated CSS edited; no emoji; no remote asset requests or provider calls; no commit/push/merge; concurrent session's uncommitted work untouched.
- **Verdict:** **APPROVED FOR LOCAL COMMIT** (suggested: `brand(app): integrate Visor Hutch dashboard identity, Colony avatars and motion (slice 7c)` + `brand(desktop): replace legacy Tauri icon family with Visor Hutch plate set (slice 7c)`), subject to `B6` tree clearance.


