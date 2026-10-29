# NEXT-PROMPT.md - paste-ready continuation: Run 7 (product, site, docs & desktop integration of the decided Hutch identity)

## Session input block

```
PROJECT:              Hutch - local-first, open-source multi-bot agent platform
                      ("Your bots. Your machine. Your rules."), MIT code, development preview, Linux-first
REPO_ROOT:            /home/kevina/CodingProjects/hutch
SITE_APP_PATH:        website/ (marketing site), src/hutch/server/ (dashboard)
DOCS_PATH:            docs/
NATIVE_TARGETS:       desktop (Tauri) + web
EXISTING_BRAND_DOCS:  docs/brand-assets.md, docs/design-system.md, DESIGN.md, PRODUCT.md,
                      website/tokens.json, docs/brand/03-CLEARANCE-PROTOCOL.md, THIRD_PARTY_NOTICES.txt
ARTIFACT_DIR:         .pipeline/brand/2026-10
TODAY:                <YYYY-MM-DD>
RUN:                  7
HUMAN_AUTHORITY:      REQUIRES EXPLICIT DATED HUMAN AUTHORISATION BEFORE WRITING OUTSIDE .pipeline/brand/**.
                      Local commits only; never push/deploy/merge without explicit instruction.
CONCURRENCY:          Respect the 3-File / 1-Seam rule per slice; never read .worktrees/; stage only files
                      this session wrote; never touch generated CSS directly (rebuild via npm run build:css
                      only when app/src or website/src changed).
JURISDICTIONS:        US + EU + UK + Canada; Nice classes 9 and 42 (D13)
LICENCE_POSTURE:      open source (MIT code, OFL fonts), zero external spend (D15); IP risk owned by
                      the maintainer in writing (D20/D23/D28/D38); no funded counsel
BUDGET:               <=15 files read per pass; <=20 external fetches; one session per slice
```

## Decided - do not reopen

1. Name RETAINED: `"Hutch"` (D38, 2026-10-29), decided with the confirmed UK class 9/42 overlap (`UK00003711474`) in front of the maintainer. Pre-screen only; nothing is clearance.
2. Wordmark DECIDED: lowercase `"hutch"` + emerald period (`.`), set in `Bricolage Grotesque` weight `800` (`D42`). `Geist` remains the product UI font. Production subset (`bricolage-grotesque-latin-800.woff2`) and verbatim OFL 1.1 licence (`OFL-bricolage-grotesque.txt`) are ready in `.pipeline/brand/2026-10/assets/production/fonts/`.
3. Colour DECIDED (measured): `COLOUR-SYSTEM.md` (`D43`). `#34d399` (`emerald-400`) on `#0a0a0c` = `10.35:1`; light surfaces use `#047857` (`emerald-700`, `4.69:1` on `#eef2f6`, `5.32:1` on `#f8fafc`).
4. Mark DECIDED: **Direction B — "Visor Hutch"** (`D54`, picked by the human on `2026-10-29`). Built in two redrawn size tiers (`Master >=32px` and `Small 16–24px`) with full production assets in `.pipeline/brand/2026-10/assets/production/` and press kit in `.pipeline/brand/2026-10/assets/press-kit/`.
5. Archived Rounds 1–12 marks in `.pipeline/brand/2026-10/assets/archive/rejected-marks-2026-10-29/` remain NON-candidates (`D51`/`D52`) and must never be referenced or used.

## Read first, in this order

1. `.pipeline/brand/2026-10/HANDOFF.md` - Run 6 summary, artifact inventory, and active blockers `B6–B10`
2. `.pipeline/brand/2026-10/BRAND-GUIDELINES.md` - canonical geometry, size-tier switching (`>=32px` vs `16–24px`), colour tokens, and typography rules
3. `.pipeline/brand/2026-10/VALIDATION-MATRIX.md` - verified platform asset specs and integration limitations (`L1–L5`)
4. `.pipeline/brand/2026-10/DECISION.md` - `D38–D56` and blockers `B6–B10`
5. `.pipeline/brand/2026-10/APP-BRAND-AUDIT.md` and `ASSET-INVENTORY.md` - exact product/site/desktop files to update

## Gate check (mandatory before any edit outside `.pipeline/brand/**`)

- Confirm that the user prompt invoking Run 7 includes an **explicit dated authorisation** to integrate the Run 6 brand package into repository surfaces (`website/`, `src/hutch/server/`, `docs/`, `desktop/icons/`, `THIRD_PARTY_NOTICES.txt`), resolving blocker `B6`.
- If explicit authorisation is missing, ask the user for confirmation and do not modify files outside `.pipeline/brand/2026-10/`.

## Planned integration slices (respect the 3-File / 1-Seam rule per task slice)

### Slice 7A — Licence, Font & Brand Docs Reconciliation (`B9` + `docs/brand-assets.md`)
- Copy `.pipeline/brand/2026-10/assets/production/fonts/bricolage-grotesque-latin-800.woff2` and `OFL-bricolage-grotesque.txt` into the canonical web/server font directories (`website/assets/fonts/` and `src/hutch/server/static/fonts/`).
- Reconcile `THIRD_PARTY_NOTICES.txt` (`B9`) so it accurately attributes shipped `Geist`, `Geist Mono`, and `Bricolage Grotesque` (OFL 1.1) and removes stale `Inter` / `JetBrains Mono` references.
- Update `docs/brand-assets.md` and `docs/design-system.md` to reference the decided `"Visor Hutch"` mark, `"hutch."` wordmark, and `COLOUR-SYSTEM.md` token rules.

### Slice 7B — Marketing Site (`website/`) Brand & Icon Integration
- Copy the platform icon pack (`favicon.ico`, `favicon.svg`, `favicon-16x16.png`, `favicon-32x32.png`, `apple-touch-icon.png`, `icon-192.png`, `icon-512.png`, `icon-192-maskable.png`, `icon-512-maskable.png`, `icon-192-monochrome.png`, `icon-512-monochrome.png`, `site.webmanifest`, `og-card-1200x630.png`) from `.pipeline/brand/2026-10/assets/production/` into `website/` / `website/assets/`.
- Update `website/index.html`, `website/src/input.css`, and `website/tokens.json` (`B10`: align `#0a0a0c` canvas token, wire `<link rel="icon">`, `<link rel="apple-touch-icon">`, `<link rel="manifest">`, Open Graph `<meta>` tags, and the navbar `"Visor Hutch"` mark + `"hutch."` wordmark lockup).
- Run `npm run build:css --silent` if `website/src/` changed.

### Slice 7C — Product Dashboard (`src/hutch/server/`) & Tauri Desktop (`desktop/icons/`)
- Copy the favicons, PWA icons, and SVG mark/lockup into `src/hutch/server/static/` and wire them in `src/hutch/server/templates/` / `src/hutch/server/pages.py` (using `hutch-mark-small-emerald.svg` at `16–24px` and `hutch-mark-master-emerald.svg` at `>=32px`, and reconciling the document title drift logged in `B10`).
- Generate/update `desktop/icons/` (`32x32.png`, `128x128.png`, `128x128@2x.png`, `icon.icns`, `icon.ico`, `icon.png`) from the picked `"Visor Hutch"` mark and record provenance in `docs/brand-assets.md`.
- Run focused tests (`npm run test:agent` on any touched server routes/templates) and `npm run check:agent`.

## Hard rules

- Legal voice: `"screened"`, `"found"`, `"not found in the sources searched"`, `"unresolved"`, `"counsel/owner decision required"`, `"not legal advice"`. Never: `safe`, `cleared`, `trademarkable`, `non-infringing`.
- Never edit generated CSS (`src/hutch/server/static/ui.css`, `model-switcher.css`, `website/app.css`, `website/styles.min.css`) by hand; edit sources and run `npm run build:css --silent`.
- No emoji (`uv run --frozen --no-sync python scripts/audit_emoji.py`).
- Never read `.worktrees/`; never stage other workstreams' uncommitted files; local commit only (no push).
