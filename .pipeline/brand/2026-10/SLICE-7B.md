# SLICE-7B.md — Marketing Site (`website/`) Brand, Icon, Manifest & Wordmark Integration

- **Slice ID:** `SLICE-7B`
- **Run:** Master Prompt Run 4 / Pipeline Run 7
- **Date:** `2026-10-29`
- **Status:** In Progress -> Verified
- **Blockers Addressed:**
  - `B6` (Executes the marketing site `website/` integration slice)
  - `B10` (Replaces legacy inline hexagon marks and Geist wordmark in `website/index.html` with the two-tier `"Visor Hutch"` mark and Bricolage Grotesque 800 `"hutch."` wordmark, and wires `favicon.svg`, `favicon.ico`, `favicon-32x32.png`, `apple-touch-icon.png`, `site.webmanifest`, and updated `og-card-1200x630.png` / `github-social-preview-1280x640.png`)

---

## 1. Exact Write Scope (2 Edited Source Files + 1 Asset Seam + Built `website/app.css`)

1. **Asset Seam (`website/`, `website/icons/`, `website/assets/`):**
   - Stage from `.pipeline/brand/2026-10/assets/production/icons/` into `website/`:
     - `favicon.svg`, `favicon.ico`, `favicon-16x16.png`, `favicon-32x32.png`, `favicon-48x48.png`, `apple-touch-icon.png`
   - Stage `site.webmanifest` into `website/site.webmanifest` (with subpath-safe `"start_url": "./"`).
   - Stage PWA icons into `website/icons/`:
     - `icon-192.png`, `icon-512.png`, `icon-192-maskable.png`, `icon-512-maskable.png`, `icon-192-monochrome.png`, `icon-512-monochrome.png`, `icon-monochrome.svg`
   - Stage social cards into `website/assets/`:
     - `og-card-1200x630.png`, `github-social-preview-1280x640.png`
2. **Source File 1 — `website/src/input.css`:**
   - Declare `@font-face` for `"Bricolage Grotesque"` (`weight 800`, `src: url("assets/fonts/bricolage-grotesque-latin-800.woff2") format("woff2")`) and `.brand-wordmark` styling (`font-family: "Bricolage Grotesque", var(--font-display); font-weight: 800; letter-spacing: -0.03em;`).
3. **Source File 2 — `website/index.html`:**
   - Wire `<link rel="icon">`, `<link rel="apple-touch-icon">`, `<link rel="manifest">`, and updated `og-card-1200x630.png?v=2cf67f59` URLs in `<head>`.
   - Replace the `26px` header mark with the `"Visor Hutch"` **Master tier** (`>= 25px`) SVG path and the `22px` mobile drawer and `22px` footer marks with the `"Visor Hutch"` **Small tier** (`16–24px`) SVG path, paired with `.brand-wordmark` (`hutch.`).
4. **Build Step:**
   - Run `npm run build:css:site` to compile `website/app.css` and stamp all local asset references in `website/index.html` via `scripts/stamp_site_assets.mjs`.

---

## 2. Acceptance Criteria

1. `tests/e2e/test_website.py::test_local_asset_urls_use_current_content_hashes`, `test_landing_initial_transfer_stays_within_review_budget_and_art_loads_on_demand`, and `test_structured_data_and_discovery_metadata_match_the_page` pass.
2. `tests/test_site_tokens.py` passes (`8/8`).
3. Live desktop (`1440x900`) and mobile (`390x844`, including open mobile navigation drawer) renders of `website/index.html` are captured via headless Chromium and visually inspected via `read_file`.

