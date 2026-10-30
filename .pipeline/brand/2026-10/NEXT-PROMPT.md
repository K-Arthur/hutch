# NEXT-PROMPT.md - paste-ready continuation: Run 7, Slice 7C (Product Dashboard `src/hutch/server/` + Avatar & Motion Drop-in + `desktop/icons/`)

## Session input block

```
PROJECT:              Hutch - local-first, open-source multi-bot agent platform
                      ("Your bots. Your machine. Your rules."), MIT code, development preview, Linux-first
REPO_ROOT:            /home/kevina/CodingProjects/hutch
SITE_APP_PATH:        website/ (completed in Slice 7B), src/hutch/server/ (dashboard), desktop/icons/ (Tauri)
DOCS_PATH:            docs/ (completed in Slice 7A)
NATIVE_TARGETS:       desktop (Tauri) + web
EXISTING_BRAND_DOCS:  docs/brand-assets.md, docs/design-system.md, DESIGN.md, PRODUCT.md,
                      website/tokens.json, docs/brand/03-CLEARANCE-PROTOCOL.md, THIRD_PARTY_NOTICES.md
ARTIFACT_DIR:         .pipeline/brand/2026-10
TODAY:                2026-10-29
RUN:                  4 (Master Prompt stage 4; Pipeline Run 7, Slice 7C)
HUMAN_AUTHORITY:      Local commits only; never push/deploy/merge without explicit instruction.
CONCURRENCY:          Respect the 3-File / 1-Seam rule per slice; never revert another session's uncommitted
                      work; respect frozen line counts in .file-size-baseline.json.
JURISDICTIONS:        US + EU + UK + Canada; Nice classes 9 and 42 (D13)
LICENCE_POSTURE:      open source (MIT code, SIL OFL 1.1 fonts), zero external spend (D15); IP risk owned
                      by the maintainer in writing (D20/D23/D28/D38/D57); no funded counsel
BUDGET:               <=15 files read per pass; one slice per session
```

## Completed in Slices 7A & 7B - do not reopen

1. **Slice 7A (`D58`):** Staged `bricolage-grotesque-latin-800.woff2` and `OFL-bricolage-grotesque.txt` into `website/assets/fonts/` and `src/hutch/server/static/fonts/`; reconciled `THIRD_PARTY_NOTICES.md` + `.txt` mirrors; updated `docs/brand-assets.md` and `docs/design-system.md`.
2. **Avatar System & 5-State Motion (`D60`, `D62`):** Completed `"The Hutch Colony"` 8-resident bot avatar system and 5-state motion choreography in `.pipeline/brand/2026-10/AVATAR-SYSTEM.md` (`evidence/avatars/avatar-family-sheet.png` and `evidence/avatars/avatar-motion-sheet.png`).
3. **Slice 7B (`D63`):** Integrated `"Visor Hutch"` Master/Small marks, `Bricolage Grotesque 800` wordmark, favicons, `site.webmanifest`, and social cards into `website/`.

## Scope for Next Session — Slice 7C: Product Dashboard (`src/hutch/server/`) + Avatar/Motion Drop-in + Desktop (`desktop/icons/`)

1. **Drop in "The Hutch Colony" 8-Resident Avatars & 5-State Motion (Zero Line-Count Growth):**
   - Replace `ID_HEADS` and `ID_FACES` in `src/hutch/server/static/app.js:1438-1461` (`24` lines -> `24` lines) with the exact block from `.pipeline/brand/2026-10/AVATAR-SYSTEM.md` Section 3.
   - Replace the sigil motion block in `src/hutch/server/static/studio.css:21-30` (`10` lines -> `10` lines) with the exact 5-state choreography block from `.pipeline/brand/2026-10/AVATAR-SYSTEM.md` Section 5.2.
2. **Wire Dashboard & Server-Rendered Templates (`src/hutch/server/`):**
   - Stage `favicon.svg`, `favicon.ico`, `apple-touch-icon.png`, and `site.webmanifest` into `src/hutch/server/static/`.
   - Declare `@font-face` (`Bricolage Grotesque` 800) and wire the `"Visor Hutch"` Small tier mark (`22px`) + compact `"hutch"` wordmark into `src/hutch/server/static/index.html` and `src/hutch/server/templates/base.html`.
3. **Stage Tauri Desktop Icons (`desktop/icons/`):**
   - Copy `32x32.png`, `128x128.png`, `128x128@2x.png`, `icon.png`, `icon.ico`, and `icon.icns` from `.pipeline/brand/2026-10/assets/production/desktop/` into `desktop/icons/`.
4. **Verify:**
   - Run `tests/e2e/test_design_system.py` (avatar/identity picker assertions), `tests/test_site_tokens.py`, and `scripts/audit_context_hygiene.py`, and visually inspect rendered dashboard screenshots via `read_file`.
