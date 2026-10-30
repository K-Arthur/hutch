# SLICE-7A.md — Licence, Font & Brand Docs Reconciliation

- **Slice ID:** `SLICE-7A`
- **Run:** Master Prompt Run 4 / Pipeline Run 7
- **Date:** `2026-10-29`
- **Status:** In Progress -> Verified
- **Blockers Addressed:**
  - `B6` (Partial — authorises and executes Slice 7A repository integration of fonts, licences, and brand docs)
  - `B9` (Resolves stale `Archivo variable font` / `OFL-archivo.txt` attribution in `THIRD_PARTY_NOTICES.md` and its distributed `.txt` mirrors)
  - `B10` (Partial — resolves `docs/brand-assets.md` and `docs/design-system.md` documentation drift: legacy hexagon vs `"Visor Hutch"` mark, Geist wordmark vs Bricolage Grotesque 800 `"hutch."` wordmark, and blue-tinted `#05070a`/`#080c12` table vs governing `website/tokens.json` `#09090b`/`#0f0f12` graphite ramp)

---

## 1. Exact Write Scope (3 Edited Docs + 1 Font Asset Seam)

### Seam: Bundled Wordmark Font Subset & Licence (`SIL OFL 1.1`)
- Copy from `.pipeline/brand/2026-10/assets/production/fonts/`:
  - `bricolage-grotesque-latin-800.woff2` (`47,260 B`, SHA-256 `55d3acddbb67185090064db83950341bda78539dd5fbaab3cbb02c7cfd270b9c`) -> `website/assets/fonts/bricolage-grotesque-latin-800.woff2` and `src/hutch/server/static/fonts/bricolage-grotesque-latin-800.woff2`
  - `OFL-bricolage-grotesque.txt` (`4,403 B`, SHA-256 `4b5a7d8f37f5602621c8a8d7358a6a2e71317e6c231c661e15aef0275d3e07ba`) -> `website/assets/fonts/OFL-bricolage-grotesque.txt` and `src/hutch/server/static/fonts/OFL-bricolage-grotesque.txt`

### File 1: `THIRD_PARTY_NOTICES.md` (+ exact mirrors `website/THIRD_PARTY_NOTICES.txt` and `src/hutch/server/static/THIRD_PARTY_NOTICES.txt`)
- Replace the stale `- Archivo variable font: SIL Open Font License 1.1; full license in src/hutch/server/static/fonts/OFL-archivo.txt and website/assets/fonts/OFL-archivo.txt.` bullet with accurate entries for:
  - **Geist and Geist Mono variable fonts** (`geist-latin-var.woff2`, `geist-mono-latin-var.woff2`, copyright 2023 Vercel in collaboration with basement.studio, SIL OFL 1.1 in `OFL-geist.txt` in both font directories).
  - **Bricolage Grotesque font subset** (`bricolage-grotesque-latin-800.woff2`, copyright 2023 Mathieu Triay, SIL OFL 1.1 in `OFL-bricolage-grotesque.txt` in both font directories).
- Ensure `website/THIRD_PARTY_NOTICES.txt` and `src/hutch/server/static/THIRD_PARTY_NOTICES.txt` remain byte-identical to `THIRD_PARTY_NOTICES.md` (matching `scripts/stamp_site_assets.mjs:22-24`).

### File 2: `docs/brand-assets.md`
- Under `## Typefaces`: Add the `Bricolage Grotesque` row documenting `bricolage-grotesque-latin-800.woff2` and `OFL-bricolage-grotesque.txt` in both font directories (`SIL Open Font License 1.1`, copyright 2023 Mathieu Triay, used strictly for the lowercase `hutch` wordmark at weight `800`, `-0.03em` tracking; UI and body copy remain `Geist` / `Geist Mono`).
- Under `## Hutch identity assets`: Update the logomark (`"Visor Hutch"` two-tier compound vector mark: Master `>= 25px` and Small `16-24px`, `fill-rule="evenodd"`), wordmark (lowercase `hutch` set in Bricolage Grotesque 800 with an emerald period `hutch.` on marketing/standalone surfaces and compact `hutch` in operator headers), standard lockups (`26px` mark in marketing header, `22px` in mobile drawer/footer and operator chrome), platform icon/manifest inventory, and canonical pipeline reference (`.pipeline/brand/2026-10/BRAND-GUIDELINES.md`).
- Under `### Identity colors`: Document both dark-surface tokens (`ink-950` `#09090b`, `paper` `#ededf0`, `emerald-400` `#34d399`, `emerald-ink` `#052e21`, `mist` `#a3a3ae`, `faint` `#8e8e99`) and the light-surface accessibility rule (`emerald-700` `#047857` on `#ededf0` paper at `4.69:1` AA, since `#34d399` on `#ededf0` is `1.65:1` and fails WCAG).
- Preserve all third-party vendor mark rules and explicit non-clearance / non-trademark disclaimers verbatim.

### File 3: `docs/design-system.md`
- Reconcile the `## Shared visual contract` table (lines 82–96), which previously listed stale blue-tinted hexes (`#05070a`, `#080c12`, `#10161f`, `#171f2b`, `#f0f4f9`, `#9daebf`, `#7d8ea4`, `.12` border-strong), so it matches `website/tokens.json` (`D12`: `#09090b` ground, `#0f0f12` surface, `#16161a` panel, `#1c1c21` raised, `#ededf0` main text, `#a3a3ae` / `#8e8e99` secondary/muted text, `.14` border-strong) and notes Bricolage Grotesque 800 for the wordmark alongside Geist / Geist Mono for UI and code.
- Reconcile the prose paragraph at lines 103–114 to mention `Bricolage Grotesque` (`OFL-bricolage-grotesque.txt`) for the wordmark and the `"Visor Hutch"` brand mark while keeping the in-app 2D assistant avatar rule clear and distinct from the brand mark.

---

## 2. Acceptance Criteria

1. `website/assets/fonts/` and `src/hutch/server/static/fonts/` both contain `bricolage-grotesque-latin-800.woff2` and `OFL-bricolage-grotesque.txt`, byte-identical (`cmp`) to `.pipeline/brand/2026-10/assets/production/fonts/`.
2. `THIRD_PARTY_NOTICES.md`, `website/THIRD_PARTY_NOTICES.txt`, and `src/hutch/server/static/THIRD_PARTY_NOTICES.txt` are byte-identical (`cmp`), contain zero stale `Archivo` / `OFL-archivo.txt` references, and accurately cite `OFL-geist.txt` and `OFL-bricolage-grotesque.txt`.
3. `docs/brand-assets.md` and `docs/design-system.md` match `BRAND-GUIDELINES.md`, `COLOUR-SYSTEM.md`, and `website/tokens.json`, and preserve non-clearance legal language.
4. `uv run --frozen --no-sync pytest -q --no-header --tb=line tests/test_site_tokens.py` passes.
5. Visual specimen proof of the staged repository font files + reconciled tables is rendered via headless Chromium and visually inspected via `read_file`.

---

## 3. Rollback Plan

- Remove `bricolage-grotesque-latin-800.woff2` and `OFL-bricolage-grotesque.txt` from `website/assets/fonts/` and `src/hutch/server/static/fonts/`.
- `git checkout -- THIRD_PARTY_NOTICES.md website/THIRD_PARTY_NOTICES.txt src/hutch/server/static/THIRD_PARTY_NOTICES.txt docs/brand-assets.md docs/design-system.md`.
