# PROVENANCE-REGISTER - Hutch brand and visual assets

Purpose: per-asset provenance register for the assets Hutch ships, turning the Run 1 inventory
(`.pipeline/brand/2026-10/ASSET-INVENTORY.md`, 2026-10-28) into an evidence-cited register under
plan gate G1. Date: **2026-10-28** (America/Vancouver). Run: **3** (IP pre-screen, clearance
protocol, provenance).

Non-claims: this is a **pre-screen, not clearance**. Assets are **risk rated**, not approved by
this register. No asset is recorded as **cleared to the extent documented**; the register records
evidence and gaps only, adjudicates nothing, and draws no licence, ownership, registration, distinctiveness
or non-infringement conclusion. It is not legal advice.

Evidence convention: every evidence cell cites a repo `file:line` or a commit, read locally on
**2026-10-28** against `main` at commit `f00a330a0b` (the workspace HEAD at the time of writing;
Run 1 measured `577e1154`). No external fetch was made in this run; vendor URLs are quoted from
tracked docs with the retrieval dates those docs record (Google/Notion: 2026-10-26), not
re-verified on 2026-10-28. Hashes are sha256 prefixes; full hashes are in ASSET-INVENTORY.md.
Generated CSS was not read, per repo rules.

Register status: DOCUMENTED = provenance and licence record both exist in tracked files;
PARTIAL = one of the two exists; UNKNOWN = neither exists; MISSING = a record the repo's own
convention requires is absent. Risk ratings are evidence-register operational ratings (how exposed
the asset is to an unrecorded-rights question), not legal risk opinions. Gate: all rows sit under
G1; the phase and plan item that must close the gap are named per row.

## Asset register

| ID | Asset / location | Type | Provenance known (author / tool / date / source) | Licence status as recorded | Evidence (file:line or commit; read 2026-10-28) | Status | Risk rating | Owner action | Gate / phase |
|---|---|---|---|---|---|---|---|---|---|
| HX-01 | Hexagon logomark, favicon inline copy x3: `website/index.html`, `src/hutch/server/static/index.html`, `src/hutch/server/templates/base.html` | inline SVG data-URI | Hutch-own by form; author, tool, date not recorded; no master file | Not stated. Doc gives form/colour/usage rules and says it is not a legal opinion | `website/index.html:24`; `src/hutch/server/static/index.html:9`; `src/hutch/server/templates/base.html:9`; `docs/brand-assets.md:48` | PARTIAL | Medium | Record author, tool, date and a master copy; keep all 3 copies byte-identical | G1 / Phase 1 |
| HX-02 | Hexagon logomark, header lockup inline copy x3 (plus footer instance): same 3 roots | inline SVG | Hutch-own by form; documented as the 22px standard lockup; author, tool, date not recorded | Not stated | `website/index.html:263` and `website/index.html:965`; `src/hutch/server/static/index.html:46-49`; `src/hutch/server/templates/base.html:37`; `docs/brand-assets.md:50` | PARTIAL | Medium | Record master and approver; resolve token drift: site uses `var(--color-semantic-brand)`, dashboard `var(--brand)`, templates `var(--accent)` | G1 / Phase 1 |
| WM-01 | Wordmark (`hutch.` site; `hutch` dashboard) | CSS text in Geist, extrabold, tight tracking | Hutch-own; form documented; site sets lowercase plus emerald period x3, dashboard renders lowercase with no period x2; approver not recorded | Not stated for the wordmark itself; Geist font files are OFL 1.1 (FNT-01) | `docs/brand-assets.md:49`; `website/index.html:238,264,966`; `src/hutch/server/static/index.html:50`; `src/hutch/server/templates/base.html:38` | PARTIAL | Low | Confirm the dashboard no-period casing is an intended variant and record it; record approver | G1 / Phase 4 (wordmark rules) |
| DSK-01 | Desktop app icon source: `desktop/icons/icon.svg` (295 B) | SVG; `#28cd9d` stroke and dot on `#0f151e` rounded square | PARTIAL: doc says "icon derived from the existing Hutch brand mark"; author, tool, date UNKNOWN; `#28cd9d` is not the `#34d399` token and the path geometry differs from the web favicon | UNKNOWN. No licence or provenance record for these files in `docs/brand-assets.md`, which covers only the web inline mark | `desktop/icons/icon.svg:1-6`; `docs/realignment/desktop-production-2026-10-26.md:83`; `docs/repository-hygiene.md:52`; commit `7a38cb1f` (2026-10-26) | PARTIAL | High (U07) | Record author, tool, date and licence; reconcile `#28cd9d` to the emerald token or record it as an approved variant with evidence | G1 / Phase 4 (U07) |
| DSK-02 | Desktop icon raster family: `desktop/icons/icon.png`, `icon.ico`, `icon.icns` | PNG 256x256; ICO 6 sizes; ICNS 8 entries | Same unknown chain as DSK-01; PNG depicts the mark concept; ICO embeds the PNG verbatim; bundled per `tauri.bundle.conf.json` (SVG is not bundled) | UNKNOWN, as DSK-01 | `desktop/tauri.bundle.conf.json:6`; `docs/realignment/desktop-production-2026-10-26.md:83`; commit `7a38cb1f` (2026-10-26) | PARTIAL | High (U07) | Same as DSK-01; record the build tool and date for each raster format | G1 / Phase 4 (U07) |
| MSC-01 | Mascot still: `website/assets/hutch-agent.webp` (620x880 alpha) | WebP | Original Blender render via `scripts/render_hutch_agent.py` (bpy 5.0.1, Cycles CPU, 96 samples, denoise, webp q82); still is the centre frame f3-p1; author not named | UNKNOWN. No licence, copyright-holder line or published usage rules for the artwork in tracked docs | `docs/marketing-site.md:207-209,239-240`; sha256 `da73ea5e...`; commit `51896f46` (2026-10-08) | PARTIAL | High (C27) | Record copyright holder, licence and usage rules; name an approver for the artwork | G1 / Phase 1 (C27) |
| MSC-02 | Mascot sprite grid: `website/assets/agent/f{0-6}-p{0-2}.webp` (21 files) | WebP 620x880 alpha | Same render pipeline and script as MSC-01; consumed as `data-frames` base `assets/agent/f` | UNKNOWN, as MSC-01 | `website/site.js:104`; `docs/marketing-site.md:239`; per-frame hashes in `ASSET-INVENTORY.md:75-97` | PARTIAL | High (C27) | Same as MSC-01; record one usage-rules statement covering still and frames | G1 / Phase 1 (C27) |
| MSC-03 | Mascot sprite duplicate: `src/hutch/server/static/agent/` (21 files) | WebP, byte-identical to MSC-02 | Same bytes as MSC-02; no tracked doc mentions this copy; no reference found in `src/hutch` or `tests` on this tree | UNKNOWN, as MSC-01 | `src/hutch/server/static/agent/f0-p0.webp` (dir, 21 files); `diff` of both sha256 lists empty (2026-10-28); commit `c6614d4b` (2026-10-08) | PARTIAL (usage UNVERIFIED) | Medium | Decide the canonical copy; delete the duplicate or record its purpose; record intent and approver | G1 / hygiene |
| FNT-01 | Geist + Geist Mono variable subsets, both copies: `website/assets/fonts/` and `src/hutch/server/static/fonts/` | WOFF2 | Vercel Geist, npm package `geist` 1.8.2, Latin subset via fontTools `pyftsubset` (variable axis and OpenType features kept); subset date not stated; both copies byte-identical | OFL 1.1 per doc; copyright 2023 Vercel in collaboration with basement.studio; licence text `OFL-geist.txt` beside each pair | `docs/brand-assets.md:39`; `docs/marketing-site.md:243`; `OFL-geist.txt:1-3`; commit `3f2a8bc0` (2026-10-26) | DOCUMENTED (record present) | Medium | Phase 1: verify OFL notice and redistribution/subset terms (C01); keep both copies and notices in step | G1 / Phase 1 (C01) |
| FNT-02 | OFL licence text x2: `website/assets/fonts/OFL-geist.txt`, `src/hutch/server/static/fonts/OFL-geist.txt` | text | Copy of the OFL 1.1 text with the Vercel copyright line; both copies byte-identical | OFL 1.1 text present | `website/assets/fonts/OFL-geist.txt:1,3,8` (identical copy in `src/hutch/server/static/fonts/`); `docs/brand-assets.md:39` | DOCUMENTED | Low | None beyond FNT-01/C01 | G1 / Phase 1 (C01) |
| NTC-01 | `website/THIRD_PARTY_NOTICES.txt` font notice drift | notices file | Still lists "Archivo variable font" and `OFL-archivo.txt` paths that no longer exist; contains no Geist entry while Geist ships | Missing record: shipped notices do not match shipped fonts | `website/THIRD_PARTY_NOTICES.txt:104`; `ASSET-INVENTORY.md:199` (absent-path finding, 2026-10-28) | MISSING | Medium | Replace the Archivo entry with Geist/Geist Mono and both `OFL-geist.txt` locations | G1 / Phase 1 (C01) |
| BRD-01 | Third-party service marks, 10 of 11 documented: `src/hutch/server/static/brands/` | mixed SVG, PNG, ICO | Vendor-published. Doc records sources; Google/Notion retrieval date 2026-10-26 and matching hashes for drive/docs/sheets/notion; OpenAI, Anthropic, OpenRouter, Outlook sources named without per-file dates | Vendor terms; not bundled. Use boundaries recorded (service name visible, no endorsement, no recolour/remix, local only) | `docs/brand-assets.md:12-21,25-33`; `src/hutch/server/static/app.js:1374-1385`; `ASSET-INVENTORY.md:134-136,139` (hash matches) | DOCUMENTED (10 of 11) | Medium (C19) | Recheck vendor guidance before any change; keep doc table, hashes and retrieval dates current | G1 / Phase 4-7 (C19) |
| BRD-02 | Microsoft "Sign in with Microsoft" lockup: `src/hutch/server/static/brands/ms-symbollockup_signin_dark.svg` (7,414 B) | SVG 215x41 | UNKNOWN. Not in the brand-assets table; no source URL, retrieval date or use-boundary note. Renders in four places in `app.js` | UNKNOWN. No per-file source or licence record in tracked docs | `src/hutch/server/static/brands/ms-symbollockup_signin_dark.svg`; `src/hutch/server/static/app.js:9863,9879,9899,9914`; `docs/brand-assets.md:12-21` (absent); commit `8059efd0` (2026-10-10) | MISSING | High (C19) | Add a doc row with source URL, retrieval date and use boundary, or remove the asset | G1 / Phase 1 (C19) |
| SOC-01 | Open Graph / Twitter card: `website/assets/og-card-1200x630.png` | PNG 1200x630 | Hutch-own identity asset; referenced as `og:image` and `twitter:image`; how the card was rendered is NOT recorded in tracked docs | Not stated. Treated as a Hutch identity asset by doc convention | `docs/brand-assets.md:51`; `website/index.html:16,23`; sha256 `b905c417...`; commit `f152b9b6` (2026-10-28) | PARTIAL | Medium | Record render method, script, author and date, or link the evidence copy | G1 / Phase 4 |
| SOC-02 | GitHub social preview: `website/assets/github-social-preview-1280x640.png` | PNG 1280x640 | Render script and README retained at `.pipeline/marketing/2026-10/evidence/brand/` (listed, not read); doc says manual upload to repo settings | Not stated | `docs/brand-assets.md:52`; `.pipeline/marketing/2026-10/evidence/brand/render_github_social_preview.py` (listed 2026-10-28); commit `b44e62fd` (2026-10-28) | PARTIAL | Medium | Move or link the render provenance into a tracked doc; record approver | G1 / Phase 4 |
| TOK-01 | Colour ramp and token source: `website/tokens.json` | JSON design tokens | Hutch-own; file self-documents generation to tokens CSS via `scripts/build_site_tokens.py`; emerald 400 = `#34d399` is the brand accent | Not applicable as artwork; in-repo configuration, no licence record needed | `website/tokens.json:2,21-23,43`; `docs/brand-assets.md:60` | DOCUMENTED | Low | Use the emerald token as the colour source when reconciling DSK-01 | G1 |
| ICN-01 | Dashboard icon families: Jinja macro, JS path map, inline shell and site glyphs | embedded inline SVG, 24x24 | UNKNOWN. No per-glyph provenance recorded; JS glyph names resemble a common outline set (UNVERIFIED; naming is not evidence of origin) | Not stated | `src/hutch/server/templates/_icons.html:1`; `src/hutch/server/static/app.js:1370-1372`; `website/index.html:234` | UNKNOWN | Medium | Record whether glyphs are hand-drawn or library-derived; add attribution if a library is confirmed | G1 / Phase 1 |
| CAP-01 | Product captures: `website/assets/captures/setup-desktop.webp`, `setup-phone.webp`, `response-style-desktop.webp`, `response-style-phone.webp` | WebP | Sanitized captures of the real app from an empty temporary state dir; scripts and dates recorded; `Design Partner` is fictional, no model route | Not stated; product screenshots | `docs/marketing-site.md:203,241-242`; commit `c1ad66ab` (2026-10-26) | DOCUMENTED (provenance) | Low | None; recapture when UI changes and keep the doc dates current | G1 |

## Licence-record gaps

1. **Font notice drift (NTC-01).** `website/THIRD_PARTY_NOTICES.txt:104` names Archivo and
   `OFL-archivo.txt` files that do not exist, and never names Geist. The shipped notices do not
   match the shipped fonts. Close: one Geist/Geist Mono entry pointing at both `OFL-geist.txt`
   copies (Phase 1, C01).
2. **Vendor marks (BRD-01, BRD-02).** Ten of eleven files have a doc row; the Microsoft sign-in
   lockup has none, and per-file retrieval dates are recorded only for the Google and Notion
   assets. Vendor terms are not bundled in the repo. Close: a complete, dated table row per file
   plus a rechecked-guidance note (Phase 1, C19).
3. **Mascot terms (MSC-01, MSC-02, MSC-03).** Provenance of the render is now recorded; licence,
   copyright holder and published usage rules are not, and the second shipped copy under
   `src/hutch/server/static/agent/` has no mention anywhere in tracked docs. Close: a terms and
   usage statement covering still, frames and both copies (Phase 1, C27).
4. **Unrecorded lockup (BRD-02).** The file ships and renders in four `app.js` locations with no
   source URL and no retrieval date. Close: source URL plus retrieval date in
   `docs/brand-assets.md`, or removal (Phase 1, C19).
5. **Desktop icon (DSK-01, DSK-02).** "Derived from the existing Hutch brand mark" is the only
   provenance line; author, tool, date and licence are absent, and the `#28cd9d` colour is
   undocumented. Close: a provenance record plus a colour decision (Phase 4, U07).
6. **Identity marks (HX-01, HX-02, WM-01).** No standalone master exists for the logomark or
   wordmark, and the dashboard wordmark drops the emerald period without a recorded variant rule.
   Close: a master copy and an approved-forms note (Phase 1/4).

## Unknowns carried into later runs

| ID | Unknown carried forward | Close condition | Evidence |
|---|---|---|---|
| U07 | Author, tool, date and licence for `desktop/icons/*`; whether `#28cd9d` is an approved variant | Recorded provenance plus a colour decision, or replacement with token-derived artwork | `desktop/icons/icon.svg:1-6`; `docs/realignment/desktop-production-2026-10-26.md:83`; commit `7a38cb1f` |
| C27 | Licence, copyright holder and usage rules for the mascot still, frames and duplicate copy | A terms/usage statement naming holder and permitted uses | `docs/marketing-site.md:207-209,239-240`; commit `51896f46`; `src/hutch/server/static/agent/` |
| C19 | Source URL, retrieval date and use boundary for the Microsoft sign-in lockup; per-file dates for non-Google marks | Complete dated rows and a recheck note in `docs/brand-assets.md` | `src/hutch/server/static/app.js:9863,9879,9899,9914`; `docs/brand-assets.md:12-21`; commit `8059efd0` |
| C01 | OFL notice travel and subset/redistribution terms; notices-file drift | Phase 1 check recorded and `THIRD_PARTY_NOTICES.txt` corrected | `docs/brand-assets.md:39`; `website/THIRD_PARTY_NOTICES.txt:104`; `OFL-geist.txt:1-3`; commit `3f2a8bc0` |

## What this register does not establish

- It does not clear any asset or conclude any licence question; it is a pre-screen, not clearance.
- It does not establish ownership, registration status, chain of title or distinctiveness of the
  Hutch logomark or wordmark.
- It does not establish that vendor terms are satisfied, that use is permitted, or that no
  third-party rights attach to any file.
- It does not verify vendor guidance: no vendor URL was fetched in this run; retrieval dates are
  those recorded in `docs/brand-assets.md`.
- It does not assess visual similarity to third-party marks; no identity asset was generated,
  drawn or rendered for this run.
- It does not replace the Phase 1 licence checks for C01/C19 or the Phase 4 decision on U07; the
  gaps above remain open until their named close conditions are met.

## Appendix A - provenance fields applied per plan

Plan G6 requires these fields per asset: source type (human-drawn / font-derived / AI-assisted
with human redraw / vendor), tool and version, date, licence, approver, master file. Recorded
values below; UNKNOWN means the repo does not state it.

| ID | Source type | Tool and version | Date | Licence | Approver | Master file |
|---|---|---|---|---|---|---|
| HX-01 | UNKNOWN (inline SVG authored in repo) | UNKNOWN | UNKNOWN | not stated | not recorded | none (inline only) |
| HX-02 | UNKNOWN (inline SVG authored in repo) | UNKNOWN | UNKNOWN | not stated | not recorded | none (inline only) |
| WM-01 | font-derived (CSS text set in Geist) | UNKNOWN (rendered by browser) | UNKNOWN | not stated for the wordmark | not recorded | none (CSS text) |
| DSK-01 | UNKNOWN (doc: derived from the brand mark) | UNKNOWN | UNKNOWN (commit 7a38cb1f, 2026-10-26) | UNKNOWN | not recorded | `desktop/icons/icon.svg` |
| DSK-02 | UNKNOWN (derived from DSK-01) | UNKNOWN | UNKNOWN (commit 7a38cb1f, 2026-10-26) | UNKNOWN | not recorded | raster exports of DSK-01 |
| MSC-01 | human-authored 3D render (scripted) | Blender bpy 5.0.1, Cycles CPU, 96 samples, webp q82 | UNKNOWN (commit 51896f46, 2026-10-08) | UNKNOWN | not recorded | `scripts/render_hutch_agent.py` (generator); no scene file recorded |
| MSC-02 | human-authored 3D render (scripted) | as MSC-01 | as MSC-01 | UNKNOWN | not recorded | `scripts/render_hutch_agent.py` |
| MSC-03 | duplicate of MSC-02 bytes | n/a (copy) | UNKNOWN (commit c6614d4b, 2026-10-08) | UNKNOWN | not recorded | canonical copy undecided |
| FNT-01 | vendor (Vercel) then font-derived subset | npm `geist` 1.8.2; fontTools `pyftsubset` (version not stated) | subset date not stated (commit 3f2a8bc0, 2026-10-26) | OFL 1.1 | not recorded | upstream package plus tracked subsets |
| FNT-02 | vendor licence text | n/a | not stated (commit 3f2a8bc0, 2026-10-26) | OFL 1.1 | not recorded | `OFL-geist.txt` x2 |
| NTC-01 | n/a (notices file) | n/a | stale relative to shipped fonts | mismatch, not a term | not recorded | `website/THIRD_PARTY_NOTICES.txt` |
| BRD-01 | vendor | vendor artwork; no build tool | retrieval 2026-10-26 for Google/Notion; others not stated | vendor terms, not bundled | not recorded | vendor files as shipped |
| BRD-02 | vendor | UNKNOWN | UNKNOWN (commit 8059efd0, 2026-10-10) | UNKNOWN | not recorded | vendor file as shipped |
| SOC-01 | UNKNOWN render method (Hutch-own content) | UNKNOWN | UNKNOWN (commit f152b9b6, 2026-10-28) | not stated | not recorded | raster only |
| SOC-02 | UNKNOWN render method (Hutch-own content) | Python render script (version not stated) | commit b44e62fd, 2026-10-28 | not stated | not recorded | raster plus script under `.pipeline/marketing/2026-10/evidence/brand/` |
| TOK-01 | n/a (in-repo token config) | `scripts/build_site_tokens.py` (version not stated) | UNKNOWN | n/a | not recorded | `website/tokens.json` |
| ICN-01 | UNKNOWN (embedded SVG) | UNKNOWN | UNKNOWN | not stated | not recorded | embedded in templates/JS |
| CAP-01 | human capture (screenshot) | capture scripts (versions not stated) | 2026-10-26 per doc | not stated | not recorded | capture scripts plus tracked WebP |

End of register. Nothing in this file grants rights, clears an asset, or states a legal conclusion.
