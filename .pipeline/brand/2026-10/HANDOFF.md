# HANDOFF.md — Session-End Handoff (Run 7 / Slices 7A, 7B & 7C, "The Hutch Colony", and Tauri Desktop Icons)

- **Pipeline root:** `.pipeline/brand/2026-10/`
- **Date:** `2026-10-29`
- **Repo HEAD during the session:** `135d8038 docs(brand): complete Run 6 Visor Hutch mark, guidelines, and asset package`
- **Commits made:** none (all slice work is staged in the working tree; see Section 2)
- **Runs / slices completed:**
  1. **Slice 7A — Licence, Font & Brand Docs Reconciliation (`D57`–`D58`):** font subsets + OFL text in both font directories, reconciled `THIRD_PARTY_NOTICES.md` + both `.txt` mirrors, updated `docs/brand-assets.md` and `docs/design-system.md`.
  2. **"The Hutch Colony" 8-Resident Avatars + 5-State Motion (`D59`–`D62`):** `AVATAR-SYSTEM.md` with `Path2D`-verified silhouettes/eyes and exact zero-line-growth drop-in blocks.
  3. **Slice 7B — Marketing Site (`website/`) Integration (`D63`):** Visor Hutch marks, Bricolage wordmark, favicons/manifest/icons, social cards.
  4. **Slice 7C — Product Dashboard + Avatar/Motion Drop-in + Desktop (`D64` candidate):**
     - `src/hutch/server/static/app.js` — `ID_HEADS`/`ID_FACES` replaced with the byte-identical `AVATAR-SYSTEM.md` Section 3 block (`14,266` -> `14,262` lines, `-4`; frozen cap `14,532`).
     - `src/hutch/server/static/studio.css` — sigil motion replaced with the byte-identical 10-line Section 5.2 choreography (`1,016` -> `1,016`, zero growth; frozen cap `1,115`).
     - Dashboard brand wiring: staged `favicon.svg`, `favicon-32x32.png`, `favicon.ico`, `apple-touch-icon.png`, `site.webmanifest`, `static/icons/` (6 PWA PNGs + monochrome SVG); new `src/hutch/server/static/brand.css` (`19` lines: Bricolage Grotesque 800 `@font-face` + `.brand-wordmark` + documented `22px` mark / `8px` gap / `18px` wordmark geometry); `static/index.html` `184` -> `188` and `templates/base.html` `66` -> `71` with the 22px "Visor Hutch" Small-tier single-path mark and compact `hutch` wordmark.
     - Tauri desktop: new deterministic generator `.pipeline/brand/2026-10/assets/build_desktop_icons.py`; `production/desktop/` asset family and `desktop/icons/` staged byte-identically (`32x32.png`, `128x128.png`, `128x128@2x.png`, `icon.png` 1024, `icon.ico` 16/32/48/64/128/256, `icon.icns` 11 entries, `icon.svg`), replacing the legacy hexagon family and closing `ASSET-INVENTORY.md` U07 drift; `PACKAGE-MANIFEST.json` refreshed (`86` entries).

---

## 1. Active Blockers & Remaining Work

| ID | Item | Status | Next Action |
| :--- | :--- | :--- | :--- |
| **B6** | **Repository integration gate** | **Slices 7A, 7B & 7C implementation complete and verified; commit pending** | Prepare the local commit(s) once the concurrent session's dirty tree clears. Suggested commits: `docs(brand): reconcile font subsets, notices and brand docs (slice 7a)`, `brand(website): integrate Visor Hutch mark, Bricolage wordmark, icons and social cards (slice 7b)`, `brand(app): integrate Visor Hutch dashboard identity, Colony avatars and motion (slice 7c)`, `brand(desktop): replace legacy Tauri icon family with Visor Hutch plate set (slice 7c)`. |
| **B7 / B8 / B10 (IP)** | **UK Class 9/42 registration (`UK00003791602`, `UK00902129492`), US serials, figurative register search** | **Active (owner-accepted risk, D38)** | Pre-screen only; nothing is trademark clearance. Counsel review owed before any commercial filing or representation. |
| **B9 (Notices)** | **`THIRD_PARTY_NOTICES` font attribution drift** | **RESOLVED (`2026-10-29`, Slice 7A)** | Kept in sync in the commit. |
| **B10 (Surface drift)** | **Dashboard & Desktop surface wiring** | **RESOLVED in Slice 7C (icons/manifest/font/lockup + desktop icon family)** | Residual docs-only follow-up: add dashboard/desktop rows to `docs/brand-assets.md` and `docs/design-system.md`. |
| **NEW — Title drift** | SPA `<title>` and server-page `<View> - hutch` do not yet follow `BRAND-GUIDELINES.md` Section 8 (`<View> — Hutch`) | **Queued (out of Slice 7C scope)** | Small follow-up slice; touches `static/index.html` and `templates/base.html` titles (and any title assertions). |
| **Flaky / unrelated CI signal** | `tests/e2e/test_design_system.py::test_persona_live_preview_is_explicit_isolated_cancellable_and_responsive` fails deterministically in the current dirty tree (40px run button vs 44px) due to the concurrent session's uncommitted `hutch-form-controls.css` + `persona.js` form migration | **Known-unrelated, not Slice 7C** | The concurrent session should resolve it; re-check after their commit. `test_answer_feedback…` timed out once under load and passes isolated. |

---

## 2. Commit Preparation Notes (`B6`)

- **Nothing was committed in this session.** The shared working tree carries a concurrent session's uncommitted changes across many of the same files (the same `app.js`, `index.html`, `base.html`, `studio.css` are modified from HEAD by that session), so staging "only Slice 7C files" would also stage their hunks. `AGENTS.md` forbids touching another task's uncommitted work.
- **Slice 7C files to review/stage when safe:**
  - modified: `src/hutch/server/static/app.js`, `src/hutch/server/static/studio.css`, `src/hutch/server/static/index.html`, `src/hutch/server/templates/base.html`, `desktop/icons/icon.png`, `desktop/icons/icon.ico`, `desktop/icons/icon.icns`, `desktop/icons/icon.svg` (desktop paths are Slice-7C only, but the four `src/hutch/server/` files mix both sessions' hunks).
  - new/untracked: `src/hutch/server/static/brand.css`, `favicon.svg`, `favicon-32x32.png`, `favicon.ico`, `apple-touch-icon.png`, `site.webmanifest`, `static/icons/`, `desktop/icons/32x32.png`, `128x128.png`, `128x128@2x.png`.
  - pipeline artefacts: `SLICE-7C.md`, `CHANGES.md`, `HANDOFF.md`, `REVIEW.md` (Slice 7C section), `EVIDENCE.md` (Slice 7C section), `.pipeline/brand/2026-10/evidence/slice-7c/**`, `.pipeline/brand/2026-10/assets/build_desktop_icons.py`, `.pipeline/brand/2026-10/assets/production/desktop/**`.
- **Verification commands (all run and green for Slice 7C; see `SLICE-7C.md` Section 2 and `.pipeline/brand/2026-10/evidence/slice-7c/verification/VERIFICATION.md`):**
  - `UV_CACHE_DIR=/tmp/hutch-uv-cache uv run --frozen --no-sync pytest -q --no-header --tb=line tests/test_site_tokens.py` -> `8 passed`.
  - `... pytest -q --no-header --tb=line tests/e2e/test_design_system.py::test_flat_mascot_eyes_stay_inside_every_silhouette` -> `1 passed`.
  - `... pytest -q --no-header --tb=line tests/e2e/test_design_system.py::test_shared_design_tokens_render_consistently_across_all_surfaces` -> `1 passed`.
  - `... pytest -q --no-header --tb=line tests/e2e/test_browser.py::test_bot_roster_pins_persist_and_simple_mascots_stay_distinct` -> `1 passed`.
  - `... python scripts/audit_emoji.py` -> clean; `... scripts/audit_context_hygiene.py --report` -> only the known-unrelated `tests/test_commit_attribution.py` finding (concurrent session).
  - Whole-file `tests/e2e/test_design_system.py`: `1 failed / 18 passed` post-fix; the single failure is the known-unrelated persona form-migration item above.

---

## 3. Slice 7C Verification-Discovered Fixes (both applied before sign-off)

1. **F1 — SPA wordmark cascade:** the new `brand.css` loaded before `studio.css`, whose `.brand-name { font: ... }` shorthand suppressed Bricolage Grotesque. Fixed by loading `brand.css` as the last stylesheet in `static/index.html`; re-verified `"Bricolage Grotesque"` `800` `18px` on SPA and server pages, and the verifier's final extended capture passes **65/65** checks (54/55 initial -> 55/55 after F1 -> 65/65 after F2).
2. **F2 — Lockup geometry:** headers measured `12px` gap and (server pages) a `16px` wordmark; `BRAND-GUIDELINES.md` 3.2 / `docs/brand-assets.md:53` specify `22px` mark + `8px` gap + `18px` wordmark. Fixed in `brand.css` (gap rule + `font-size: 18px`; sha256 `581315bf…`) with both `?v=` references re-stamped; re-measured both surfaces as `22x22` mark / `8px` gap / Bricolage `800` `18px`, no overflow/errors.

---

## 4. Next Session Handoff

1. **Do not reopen Slices 7A/7B/7C** unless verification regresses; their scope is committed to the ledger in `CHANGES.md`.
2. **First action for the next session:** check whether the concurrent session's dirty tree was committed. If it is clean, prepare the local commits above (never push/deploy/merge). If it is still dirty, do not stage shared files; continue with documentation-only follow-ups.
3. **Recommended next slice (7D, small, low risk):** page-title reconciliation to `BRAND-GUIDELINES.md` Section 8 (`<View> — Hutch`), plus the canonical-doc rows for the dashboard/desktop surfaces in `docs/brand-assets.md` and `docs/design-system.md`.
4. **IP items (B7/B8/B10) remain owner-accepted-risk pre-screen only** — no filing, no clearance claim, no legal representation.
