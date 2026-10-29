# App-branch brand audit: independent cross-check of Phase 0 plan section A

Date: 2026-10-28. Repo: /home/kevina/CodingProjects/hutch, branch main at 577e1154
("docs(marketing): record the public launch session and link the live site").
Scope: read-only verification of the Phase 0 plan's current-state inventory
(`git show brand/plan:docs/brand/00-PLAN.md`, section A, plan lines 65-233) against the
repository as checked out on `main`, plus reconciliation of the six brand/design documents
Phase 0 deliberately never read (unknown U01, plan lines 179-195), and closure of unknowns
U02 (`website/tokens.json`), U06 (route/surface map), U07 (desktop icon equivalence) and
U26 (mark/name definition conflicts).

This document records what sources say, with dates. It makes no legal, clearance,
distinctiveness or non-infringement claims. No rendered or visual inspection was performed
(this session has no browser); every claim that would require looking at a rendered page or
image is marked UNVERIFIED. Conflicts are surfaced, not silently reconciled.

Verdict vocabulary: CONFIRMED (checked against `main`, evidence given), REFUTED (checked
against `main`, claim is wrong as stated), PARTIAL (claim mixes right and wrong parts),
UNVERIFIED (could not be checked with the operations available here; reason given).

---

## 1. Inputs read (exact paths with line ranges)

| Input | Range read | Notes |
|---|---|---|
| `git show brand/plan:docs/brand/00-PLAN.md` | lines 65-233, plus 179-213 re-read for A.8/A.9 | the artifact under review |
| `DESIGN.md` | 1-557 (whole file; frontmatter 1-140, body 142-557) | 33,293 B confirmed |
| `PRODUCT.md` | 1-126 (whole file) | 7,622 B confirmed |
| `docs/brand-assets.md` | 1-76 (whole file) | 7,587 B confirmed |
| `docs/design-system.md` | 1-327 (whole file) | 21,152 B confirmed |
| `docs/marketing-site.md` | 1-327 (whole file) | 33,404 B confirmed |
| `docs/research/icon-and-chat-interface-references-2026-10-10.md` | 1-105 (whole file) | 7,018 B confirmed |
| `.pipeline/marketing/2026-10/evidence/brand/README.md` | 1-126 (whole file) | 6,372 B |
| `.pipeline/marketing/2026-10/evidence/brand/render_github_social_preview.py` | grep skim of brand-relevant lines (tokens/font/hexagon/strings/colors); not read end-to-end | 299 lines, 11,426 B |
| `website/tokens.json` | 1-181 (FULL read; closes U02) | 181 lines confirmed |
| `website/tokens.css` | 1-120 (whole generated token sheet; not on the do-not-read list) | used to verify plan A.3 counts |
| `website/index.html` | head 1-130; header 229-283; footer 958-1007; grep passes elsewhere | 1,007 lines confirmed by `wc -l` |
| `src/hutch/server/static/index.html` | head 1-60; grep passes for the rest | 184 lines confirmed |
| `src/hutch/server/templates/base.html` | 1-66 (whole file; it is the head section) | 66 lines confirmed |
| `website/downloads.json` | 1-39 (whole file) | new fact for the plan |
| `website/src/input.css` | 1-90 (whole file) | 90 lines confirmed |
| `app/src/input.css` | 1-40 and 170-215 (imports, plugin lists, theme block) | 386 lines confirmed by `wc -l` |
| `src/hutch/web/styles/hutch-tokens.css` | header lines 1-20 only | namespace check |
| `src/hutch/web/styles/hutch-theme-overrides.css` | header lines 1-25 only | light-counterpart check |
| `desktop/icons/icon.svg` | whole file (295 B) | closes U07 at source level |
| `src/hutch/server/pages.py` | grep only: route decorators (lines 178-711), defs at 16/84 | not read end-to-end |
| `src/hutch/server/pages_models.py`, `src/hutch/server/pages_usage.py` | grep only (lines 18, 20) | route locations |
| `src/hutch/server/app.py` | grep only: route decorators, `create_app` (2062), `FastAPI(...)` (2107), redirects (6442-7258), `register_pages`/mount (7447-7453) | not read end-to-end |
| `src/hutch/server/static/hutch.css` | grep only: `--accent` definitions/usages (lines 35-330), `@font-face` count | variable-resolution check |
| `package.json` | grep only (lines 6, 30) | daisyUI pin |
| `README.md` | grep plus lines 85-118 | plan E01 claims |
| `.github/workflows/pages.yml` | grep only (lines 3-33) | trigger/deploy claims |
| `desktop/tauri.conf.json` | grep only (line 15) | bundle claims |
| Directories inventoried (listings only): `src/hutch/server/templates/`, `src/hutch/server/static/fonts/`, `website/assets/fonts/`, `src/hutch/server/static/brands/`, `website/assets/captures/`, `website/assets/agent/`, `website/.well-known/`, `desktop/icons/`, `src/hutch/web/styles/` | | |

Not read (per hard rules): `.worktrees/`, lockfiles, `node_modules/`, `.venv/`, `.state/`,
`*.db*`, `CHANGELOG.md`, generated CSS (`ui.css`, `model-switcher.css`, `website/app.css`,
`website/styles.min.css`). `website/site.js` was grep-sampled only (one "hutch" string, a
lowercase comment on line 1).

---

## 2. Plan-A claim verification table

Verified against `main`, not the `brand/plan` branch.

| # | Claim (plan section) | Verdict | Evidence |
|---|---|---|---|
| 1 | Marketing page `website/index.html` is 1007 lines, single page (A.1) | CONFIRMED | `wc -l` = 1007; `</html>` at line 1007 |
| 2 | `website/tokens.css` generated; `app.css`/`styles.min.css` committed builds (A.1) | CONFIRMED | `tokens.css:1-3` generator header "DO NOT EDIT"; `website/app.css`, `styles.min.css`, `styles.css`, `site.js` present; built-CSS bodies not read (rule) |
| 3 | GitHub Pages via `.github/workflows/pages.yml`, push to `main` touching `website/**` (A.1, A.7) | CONFIRMED | `pages.yml:3-7` (`branches: [main]`, `paths: ["website/**"]`), artifact path `website` at :33 |
| 4 | Deployed URL `https://k-arthur.github.io/hutch/` (A.1) | CONFIRMED as repo-declared; live deployment UNVERIFIED | canonical `index.html:10`; `docs/marketing-site.md:230` ("Shipped ... on 2026-10-28"); no network fetch performed |
| 5 | `base.html` 66 lines + 27 templates (A.1) | CONFIRMED | `wc -l` = 66; `templates/` holds 28 files including `base.html`, i.e. 27 others |
| 6 | `base.html` links **9** stylesheets (A.1) | **REFUTED** | `base.html:10-25` links 10: brand-tokens, hutch, hutch-pages, controls, hutch-forms, hutch-form-controls, hutch-select, hutch-composer, hutch-composer-context, hutch-messages |
| 7 | Legacy server stylesheet names (A.1) | CONFIRMED | same lines 10-25 |
| 8 | Studio shell 184 lines (A.1) | CONFIRMED | `wc -l` = 184 |
| 9 | Studio shell links **18** stylesheets (A.1) | **REFUTED** | `static/index.html:12-34` links 15 (ui, style, hutch-composer, hutch-composer-context, model-switcher, skills, computer, uPlot, widgets, controls, studio, hutch-forms, hutch-form-controls, hutch-select, hutch-messages) |
| 10 | `ui.css` built from `app/src/input.css` (A.1) | CONFIRMED | `app/src/input.css:3` build comment; `package.json` is build toolchain only |
| 11 | Desktop icons `icon.svg/.png/.ico/.icns`, no packaged installers (A.1) | CONFIRMED | `ls desktop/icons/`; `README.md:110` "no packaged desktop installers or hosted sign-up" |
| 12 | Product facts: MIT, development preview, Linux only, solo maintainer, model routes Ollama/llama.cpp/LM Studio/OpenAI/Anthropic/OpenRouter/OpenAI-compatible/OpenCode, "not a fit yet" segments (A.1) | CONFIRMED | `README.md:7,14,30,51,62,98-103,108-115` (maintainer table row "Solo maintainer, best effort") |
| 13 | Marketing anchors `#top #proof #workflow #runs #control #receipts #cases #get #faq` (A.2) | CONFIRMED | each `id=` present exactly once in `website/index.html` |
| 14 | Marketing files downloads.json, robots.txt, sitemap.xml, llms.txt, security.txt, `.well-known/security.txt`, THIRD_PARTY_NOTICES.txt (A.2) | CONFIRMED | `ls website/`; `website/.well-known/security.txt` (232 B); `index.html:995` links notices |
| 15 | Server-rendered pages home/login/pair/approvals/bots/bot_new/bot/models/runs/run/usage/connections/error + partials (A.2) | CONFIRMED | `templates/` listing (28 files incl. `_icons.html`, `_approval_card.html`); routes present (section 5) |
| 16 | Studio hash routes = the 10 listed (A.2) | CONFIRMED | grep of `static/index.html`: `#/chat #/chats #/overview #/schedules #/runs #/runtime #/skills #/bots #/connections #/settings` |
| 17 | Studio "server pages `/models`, `/usage`" (A.2) | CONFIRMED (new location detail) | `src/hutch/server/pages_models.py:18` (`@app.get("/models")`), `src/hutch/server/pages_usage.py:20` (`@app.get("/usage")`) - the plan did not name these two modules; the route table is not only in `pages.py`/`app.py` |
| 18 | Token source `website/tokens.json` 181 lines, DTCG-style, primitive -> semantic, header says generated to both stylesheets by `scripts/build_site_tokens.py` (A.3) | CONFIRMED | `tokens.json:1-2`, tier structure lines 4-167 |
| 19 | Plan (per task brief) claims tokens.json asserts a component tier it lacks | **CONFIRMED** | `tokens.json:2` `$description`: "... Primitive -> semantic -> component." but no `component` tier exists anywhere in `tokens.json` or `tokens.css` (section 4) |
| 20 | `tokens.css` 120 lines, byte-identical structure to `brand-tokens.css` (A.3, E03) | CONFIRMED (stronger) | `wc -l` = 120 both; `cmp website/tokens.css src/hutch/server/static/brand-tokens.css` -> identical bytes |
| 21 | 107 custom properties total (A.3) | CONFIRMED | counted from `tokens.css:4-119` (55 color + 3 font + 17 text + 12 space + 5 size + 5 radius + 7 motion + 3 layer = 107) |
| 22 | Breakdown "31 primitive colours (incl 8 alpha whites), 27 semantic, 3 fonts, 14 text sizes, 3 line heights, **10 spaces**, 5 sizes, 5 radii, **8 motion**, 3 layers" (A.3) | **REFUTED** on three tiers | actual: **28** primitives (not 31), **12** spaces (not 10), **7** motion tokens (not 8). Semantic 27, fonts 3, sizes 14+3, size 5, radius 5, layers 3 confirmed. The plan's own breakdown sums to 109, inconsistent with its correct 107 total |
| 23 | `website/src/input.css` 90 lines, Tailwind v4 CSS-first, daisyUI theme `hutch`, documented brand contract (near-black ground, emerald #34d399, 8/12/100 radii, one dark theme, amber = status only) (A.3) | CONFIRMED | `website/src/input.css:1,7-8` (contract comment verbatim), `:22-26` theme `hutch`, `:55-57` radii 100px/0.5rem/0.75rem, `:19` 10-component include list |
| 24 | `app/src/input.css` 386 lines, imports brand-tokens + hutch-tokens + surface rules, daisyUI theme block at line 180 (A.3) | CONFIRMED | `wc -l` = 386; imports at `:12,15,19,22,26`; `@plugin "daisyui/theme"` at `:180` |
| 25 | App comment says "daisyUI v6" while `package.json` pins `daisyui ^5.7.47` (C13 drift, A.3) | CONFIRMED | `app/src/input.css:1` "Tailwind v4 + daisyUI v6 source"; `package.json:30` `"daisyui": "^5.7.47"`; marketing source says v5 (`website/src/input.css:1`) |
| 26 | Hardcoded hex literals: 45 occurrences / 23 unique; tokens.css 39, website input 3, app input 2, index.html 1 (E04) | CONFIRMED on per-file counts (39/3/2/1 reproduced exactly); unique count 23 UNVERIFIED | `grep -oE '#[0-9a-fA-F]{3,8}'` per file |
| 27 | 251 `var(--...)` references across the four declared inputs (E04) | CONFIRMED | combined grep count = 251 |
| 28 | 39 literal `font-size` declarations in `app/src/input.css` (E04) | CONFIRMED | grep count = 39 |
| 29 | App consumes "a separate `--fs-*`/`--s-*` scale **from `hutch-tokens.css`**" (A.3, U03) | **REFUTED (attribution)** | `--fs-*`/`--s-*` are **defined in `src/hutch/server/static/style.css:113,118`** and consumed in `app/src/input.css:46,52,66,75,82,175`; `src/hutch/web/styles/hutch-tokens.css` has zero `--fs-` and zero `--s-<n>` tokens - it owns the `--hutch-*` namespace (`hutch-tokens.css:2,10-20`) |
| 30 | Contrast pairs (E05): brand/bg 10.35:1, text 17.03:1, text-2 7.97:1, text-3 6.14:1, on-brand 7.70:1 etc. | PARTIAL: corroborated, not recomputed | identical values independently recorded in `.pipeline/.../brand/README.md:111-113` (dated 2026-10-28) and `DESIGN.md:211` (7.7:1); formula not re-run here |
| 31 | `hutch-theme-overrides.css` imported by app input, provides a derived light counterpart; light contrast unmeasured (U05) (A.3) | CONFIRMED | `app/src/input.css:26`; `hutch-theme-overrides.css:1-25` ("explicit dark parity plus a derived light counterpart", `[data-hutch-theme="light"]` derived by role inversion); no light-theme contrast evidence found in any input |
| 32 | Mark = hexagon outline + centre circle, 32x32 viewBox, inline in 3 HTML roots, six-plus copies (A.4, C12) | CONFIRMED | exactly 6 inline instances: `website/index.html:24` (favicon), `:235` (header), `:263` (drawer), `:965` (footer); `base.html:9` (favicon), `:37` (header); `static/index.html:9` (favicon), `:46` (sidebar) |
| 33 | Mark sizes: marketing header/drawer/footer 26/22/22px, server header 24px, Studio sidebar 22px (A.4) | CONFIRMED | `index.html:234` `size-[26px]`, `:263`/`:965` `size-[22px]`; `base.html:37` `width="24"`; `static/index.html:46` `width="22"` |
| 34 | Literal #34d399 in data-URI favicons; `var(--color-semantic-brand)` in visible headers (A.4) | PARTIAL | favicons: CONFIRMED (`%2334d399` in all three roots). Header variable: marketing only (`index.html:235-236,263,965`); `base.html:37` uses `var(--accent)` which `hutch.css:35` defines as `var(--color-semantic-brand)` (same resolved colour; `tokens.json:172` records `--accent` as the retired Oct-2026 site blue); `static/index.html:47` uses `var(--brand)` (definition inside the ui.css build, not read - resolution UNVERIFIED) |
| 35 | Wordmark "hutch." with emerald stop on marketing; "hutch" without stop on server/Studio; `<title>` "hutch" on dashboards, "Hutch" in marketing/OG/JSON-LD; footer "(c) 2026 hutch" (A.4, C18) | CONFIRMED | `index.html:238,264,966` (`hutch<span class="text-brand">.</span>`), `:6` title "Hutch", `:999` "&copy; 2026 hutch", JSON-LD name "Hutch" `:33`; `base.html:7` `<title>{% block title %}hutch{% endblock %} - hutch</title>`, `:38`; `static/index.html:6,50` |
| 36 | "hutch - hutch" default page title on server pages (A.6, C18) | **CONFIRMED** | `base.html:7` renders "hutch - hutch" when a page sets no title block |
| 37 | Favicon inline SVG data URI only; no 16x16 raster/ICO, no apple-touch-icon, no SVG file, no fallback on web surfaces (A.4, A.6, C06) | CONFIRMED for web roots | grep: no manifest/apple-touch icon file in any root; `git ls-files` finds no service worker. Desktop `icon.ico` (6 sizes incl. 16x16 RGBA) and `icon.svg` exist but are Tauri-only and unreferenced by web pages |
| 38 | Desktop icons: icns 102,645 B; ico 6 sizes incl 16/32 RGBA; png 256x256 RGBA; svg 295 B (A.4, E08) | CONFIRMED | `ls -l` + `file`: icns 102645 B; ico "6 icons, 16x16 ... 32x32 ... RGBA"; png "256 x 256 ... RGBA"; svg 295 B |
| 39 | "no evidence [desktop icons] match the inline mark (U07)" (A.4) | CONFIRMED as mismatch at source level; rendered equivalence UNVERIFIED | `desktop/icons/icon.svg` uses a different hexagon path (`M16 3 27 9.5v13L16 29 5 22.5v-13z` vs web `M16 2 28 9v14L16 30 4 23V9z`), stroke `#28cd9d` (not `#34d399`), stroke-width 2.2 (not 2.5), plus a rounded-rect background plate `#0f151e` at 1024x1024 |
| 40 | Social/OG assets: og-card 1200x630 (118,901 B), github-social-preview 1280x640 (133,259 B) (A.4, E08) | CONFIRMED | `file`: 1200x630 RGB / 1280x640 RGB; `ls -l`: 118901 / 133259 B (social size also at evidence README:11) |
| 41 | Social/OG "static, no dark/light variants, not generated from source artwork (C12)" (A.4) | PARTIAL / partly REFUTED | single variant each: CONFIRMED. "Not generated from source artwork": REFUTED for the GitHub social preview - a reproducible renderer exists (`.pipeline/.../render_github_social_preview.py`, evidence README 2026-10-28, token-inlined, zero-network); the og-card's "S-c renderer" is referenced (evidence README:12,124) but not present in this tree - UNVERIFIED for the og-card |
| 42 | Mascot `hutch-agent.webp` 620x880 alpha + 21 sprite frames (A.4) | CONFIRMED | `file`: "WebP ... with alpha, 620x880"; `ls website/assets/agent/ | wc -l` = 21 |
| 43 | Mascot "no usage rules (C14)" (A.4) | **REFUTED** | usage rules exist: `docs/brand-assets.md:74-76` ("decorative product art, not a logo or application screenshot") and `docs/marketing-site.md:207-209,239-247` (Blender provenance, regeneration, pointer-behaviour rules). The "not mentioned in the brief" part stands |
| 44 | Third-party marks in `static/brands/` (Anthropic, Google Calendar/Docs/Drive/Gmail/Sheets, Microsoft Outlook + sign-in, Notion, OpenAI, OpenRouter) (A.4, C19) | CONFIRMED | directory holds exactly 11 files matching that list (`ms-symbollockup_signin_dark.svg` is the sign-in asset) |
| 45 | No press kit / brand download tracked (C13 in A.4) | CONFIRMED | no press-kit file and no `docs/brand/` directory (`ls docs/brand` -> not found); `website/downloads.json` is a release manifest, not a brand kit (Findings) |
| 46 | `desktop/tauri.conf.json` `bundle.active = false`, no icon list (A.4, E09) | CONFIRMED | `desktop/tauri.conf.json:15` `"bundle": { "active": false }`; no `"icon"` key in the file |
| 47 | Fonts: Geist/Geist Mono; files 37,832 B / 38,508 B duplicated in two directories; OFL text beside both pairs (A.5, E06) | CONFIRMED | `ls -la` of `website/assets/fonts/` and `src/hutch/server/static/fonts/`: identical sizes in both dirs, `OFL-geist.txt` 4,368 B in both |
| 48 | Marketing head preloads body woff2; Studio preloads with first-paint comment; `base.html` has no preload; mono not preloaded anywhere (A.5) | CONFIRMED | `index.html:25`; `static/index.html:10-11`; `base.html` head has no preload; no `geist-mono` preload in any root |
| 49 | `@font-face`: 0 in `brand-tokens.css`, 2 in `hutch.css` (E06) | CONFIRMED | `grep -c '@font-face'` -> brand-tokens 0 (identical to tokens.css), `hutch.css` = 2 |
| 50 | No Google Fonts/CDN references in declared inputs (A.5) | CONFIRMED for the three HTML roots | all asset URLs local; no external origins in any head read |
| 51 | Title/description/canonical/OG/Twitter complete on marketing; canonical and OG absent on server and Studio (A.6) | CONFIRMED | `index.html:6-23`; absent from `base.html` and `static/index.html` heads |
| 52 | JSON-LD: SoftwareApplication + FAQPage; "no logo/image property in the SoftwareApplication block" (A.6) | **REFUTED as stated** | the SoftwareApplication block carries `"screenshot": ".../assets/captures/setup-desktop.webp"` (`index.html:43`) - an image URL property added for the 2026-10-28 launch per `docs/marketing-site.md:226,230`. No `logo` property: CONFIRMED. FAQPage present; FAQ question count = 20, matching the 20/20 parity claim (`docs/marketing-site.md:310`) |
| 53 | theme-color #09090b marketing and Studio, absent on server pages (A.6) | CONFIRMED | `index.html:9`, `static/index.html:7`, absent in `base.html` |
| 54 | color-scheme: absent marketing, absent server, `dark` Studio (A.6) | CONFIRMED | grep of three roots; only `static/index.html:8` has it |
| 55 | Not a PWA: no manifest, service worker, maskable/monochrome icons, install assets (A.6) | CONFIRMED | greps of roots; `git ls-files | grep -i 'sw.js|service.worker'` empty. The `downloads.json` alternate link is a release manifest, not a web app manifest |
| 56 | `npm run build:css` builds the four sheets; `scripts/stamp_site_assets.mjs` hashes local URLs (A.7) | CONFIRMED | script exists; content hashes present throughout `index.html` (`?v=<8-hex>` on 12+ assets) |
| 57 | Visual regression: no screenshot tests tracked, e2e exists but no brand baselines (A.7, E07) | CONFIRMED | `git ls-files tests/e2e | grep -Ei 'visual|screenshot|snapshot'` -> empty (exit 1). Caveat: `tests/e2e/test_website.py`, `test_design_system.py`, `test_radius_scale.py`, `test_type_and_spacing_scale.py` all exist and enforce structural/scale rules; visual-validation evidence lives under `docs/realignment/` (referenced by docs, not read here) |
| 58 | Brief-input reconciliation: `src/app/layout.*`, `src/styles/globals.css`, `tailwind.config.*`, `public/manifest.json`, root `index.html`, favicon files all absent; `docs/brand/` does not exist (A.9) | CONFIRMED | `ls` of each path -> not found; `pyproject.toml` present |
| 59 | Plan A.8 byte sizes for the six unread documents | CONFIRMED | 33,293 / 7,622 / 7,587 / 21,152 / 33,404 / 7,018 B via `ls -l` |
| 60 | Feature flags "none found in declared inputs" (A.7) | UNVERIFIED here | not re-searched beyond the declared inputs; plan-scoped statement only |

---

## 3. U01 reconciliation: the six documents (plus the Phase 0 brand-evidence README)

### 3.1 `DESIGN.md` (557 lines)

Mandates the brand program must honor:

- `PRODUCT.md:78` declares this file "the visual source of truth"; `docs/design-system.md:10-12` grants it precedence over itself and older surface briefs.
- Palette and roles (`DESIGN.md:181-183,208-223`): emerald #34d399 brand/primary (lineage #10b981/#6ee7b7), azure #60a5fa interaction/focus only, amber #fbbf24 person-needed only ("The Amber Rule", 194-196), rose #f87171 failure, graphite neutrals.
- Named rules: One-Ink (no white on emerald; ink #052e21, 192-193), Measure (~72ch, 191), Scale (radii/text/spacing only from scales, 197-198), Mono (199-200), Edge (rgba(255,255,255,0.38) control boundary >= 3:1, 201-203), One-Home (204-206).
- Type (225-264): Geist + Geist Mono, local only; product scale six steps 12/13/14/16/18/24, 17 for reading, 28-36 display band; explicitly "11, 12.5, 13.5, 15 and 20px do not exist in the product" (246-248); wordmark 1.125rem/1 weight 650 tight tracking (250); icon family 24x24 outline, 16/20/24 roles, current-colour stroke (258-264).
- Layout/geometry (266-323): marketing native-modal nav at a 1024px breakpoint; desktop shell 304/272px sidebar + 56px top bar + optional 380px drawer; 4px spacing rhythm (4/8/12/16/24/32/40/56); control-height ladder 32/36/40/44; conversation column max 760px; operational container 1040px; phone <= 900px/640px rules with 44x44 targets.
- Radius scale 4/8/12/20/100 with "nesting steps down, never up" (334-357).
- Component contracts (359-535): primary button emerald/ink 8px/40px; shared `controls.css`/`controls.js` dropdown family; status chips dot+word; 2D assistant faces (two near-round ink eyes, no visor/pupils/highlights); roster, model picker with vendor marks (OpenAI/Anthropic bundled, others monogram tiles), fleet cards, seven-pane assistant settings, gate cards, thread/spine, bubbles, composer, header, activity rules.
- Motion (545-555): short, state-linked, reduced-motion honored; never animate text opacity; no ambient loops.
- Enforcement pointers that exist in the repo: `tests/e2e/test_type_and_spacing_scale.py`, `tests/e2e/test_radius_scale.py` (both verified present).

CONFLICTS surfaced (not reconciled):

| Conflict | Detail |
|---|---|
| Neutral ramp disagreement | `DESIGN.md:9-10,216-218` says panel #101013, raised #17171b; `website/tokens.json:36-37` says panel #16161a (ink.800), raised #1c1c21 (ink.750). The generated CSS follows tokens.json. No doc reconciles them; this audit does not choose |
| Hairline "strong" value | `DESIGN.md:16` line-strong rgba(255,255,255,0.12) vs `tokens.json:53` border-strong 0.14 |
| Wordmark spec | `DESIGN.md:250` weight 650 at 1.125rem vs `docs/brand-assets.md:49` "extrabold" vs rendered markup `font-extrabold text-xl` (`index.html:238`) |
| Type-scale exclusion vs token file | `DESIGN.md:246-248` says 15px "does not exist in the product"; `tokens.json:100` defines `text.size-sm: 15px` (and `size-lg: 19px`, also outside the six steps). The exclusion is worded for "the product"; the shared token file still carries the sizes |

### 3.2 `PRODUCT.md` (126 lines)

- Brand commitments (76-88): DESIGN.md is visual source of truth; recognizable app marks; simple 2D identity in-product with the original 3D mascot kept for marketing; shared graphite/emerald/azure/status/Geist/rounded system; service marks always beside their names; motion short and state-linked with reduced-motion and forced-colors respect; WCAG 2.2 AA target, 24x24 AA minimum with 44x44 touch comfort, focus independent of glow.
- Frontend stack constraint (69-71): zero build step and zero external assets for the app; vanilla ES hash-routed SPA at `/` plus Jinja2+HTMX pages; "introducing a framework or bundler is not" allowed. The marketing site is explicitly carved out as a separate surface with a shared token source (72-74) - which is why `website/` may have a build.
- Quality gates set by the user 2026-10-07 (102-106): aesthetic >= 90/100 and functionality >= 95/100, judged on opened screenshots at desktop and phone; "Screenshot creation alone is not validation."
- Evidence posture (90-100): the incumbent skin is "anti-reference"; marketing captures must come from the actual empty first-run product.
- Terminology: platform "web" (line 7) describes the product; the repo's Tauri host is unreleased, so this does not conflict with the plan's four-surface inventory.
- No mark/name definition conflicts with the hexagon logomark (PRODUCT.md does not describe the mark's form).

### 3.3 `docs/brand-assets.md` (76 lines)

- Third-party marks (1-33): provider artwork only beside the named service, bundled locally, unchanged, with connection state visible; never endorsement; "not a legal opinion or a grant of trademark rights." Per-asset provenance with sources, retrieval dates 2026-10-26 and SHA-256 for Drive/Docs/Sheets/Notion; model-picker marks are decorative (`aria-hidden`).
- Typeface (35-39): Geist/Geist Mono from npm `geist` 1.8.2, SIL OFL 1.1, copyright 2023 Vercel with basement.studio, pyftsubset Latin subsets, licence beside each pair; "Replaces the earlier Archivo files."
- Hutch identity assets (41-53): logomark = hexagon outline with centre dot, inline SVG in the `<head>` of `website/index.html`, #34d399; wordmark = lowercase `hutch` in Geist extrabold with an emerald period, logo-form only, public prose uses "Hutch"; standard lockup 22px; social card 1200x630; GitHub social preview requires manual repository upload.
- Identity colours (54-64): `ink-950` #09090b, `paper` #ededf0, `emerald` #34d399, `muted` #8e8e99.
- Usage rules (66-76): no endorsement implying; no recolouring third-party marks; do not present the Hutch marks as a registered trademark; mascot is decorative product art.

U26 answer (mark/name definition): `docs/brand-assets.md` defines the SAME hexagon-plus-dot mark as the inline SVG actually used on all three HTML roots - no document defines a different Hutch mark. Two qualifications for the human: (a) the desktop icon set contains a visually different variant (`desktop/icons/icon.svg`, claim 39); (b) the rendered GitHub social preview uses a capital-H "Hutch" wordmark (renderer line 107), which does not match the lowercase-with-period lockup defined at `brand-assets.md:49-50`.

CONFLICTS:

| Conflict | Detail |
|---|---|
| Lockup size | `brand-assets.md:50` says the 22px logomark lockup is used in "the site header, mobile drawer and footer", but the site header mark is 26px (`index.html:234`) |
| Token naming | "muted" (`brand-assets.md:61`) is not a token in `website/tokens.json`; the value #8e8e99 is `color.primitive.faint` / `color.semantic.text-3` |
| Bundled marks vs research doc | `brand-assets.md:15-16,20` documents bundled Gmail, Google Calendar and Microsoft Outlook artwork (retrieved 2026-10-26), while `docs/research/icon-and-chat-interface-references-2026-10-10.md:21-41` (2026-10-10) states those marks were deliberately NOT bundled for licence reasons. Chronology suggests supersession, but the research doc was never updated (see 3.6) |

### 3.4 `docs/design-system.md` (327 lines)

- Precedence (10-12): DESIGN.md wins any conflict.
- Token chain (14-43): tokens.json -> `tokens.css` (marketing) + `brand-tokens.css` (packaged UI); Studio ui.css imports the generated tokens; server pages load the same file before `hutch.css`; `/connections` redirects into the Apps & AI screen with retired forms at `/legacy/connections` (23-26, matches `pages.py:587,593`); build/check commands and "do not hand-edit generated CSS."
- Dropdown/selection contract (47-80): shared `controls.css`/`controls.js`, native select as form authority, popup via `hutchControls.popup(...)`, no body-portaling, marketing site deliberately does not load app popup JS.
- Shared visual contract table (82-101): full role/value table (see conflict below), radius 4/8/12/20/100, control heights 32/36/40/44, product text steps 12/13/14/16/18/24, spacing 4/8/12/16/24/32/40/56, app icon family 16/20/24 at 24px viewBox.
- Shared Geist, no remote fonts (103-106); 3D mascot on the site, flat 2D in-app (106-113).
- Surface roles (115-255): chat library as recovery path; `#/assistant/new` as a task page (155); fleet cards; approvals with no bulk approve (225); marketing keeps editorial composition and must reflect verified behaviour (256-263).
- Fixed dark theme, no `prefers-contrast` palette, described as a product decision (296-299).
- Status words over colour (300-301); motion tied to state (302-304).
- Research pointers (306-320): ui-reference-patterns-2026-10-09, complaints.md.

CONFLICTS:

| Conflict | Detail |
|---|---|
| Blue-tinted contract table (major) | `design-system.md:84-89` lists Ground #05070a, Surface #080c12, Panel #10161f, Raised #171f2b, Main text #f0f4f9, secondary/muted #9daebf/#7d8ea4. These match NEITHER `tokens.json` (#09090b/#0f0f12/#16161a/#1c1c21/#ededf0/#a3a3ae/#8e8e99) NOR `DESIGN.md` (#09090b/#101013/#17171b). The same document says at 106-107 that the graphite palette comes from tokens.json - self-conflict. The generated CSS and both daisyUI themes follow tokens.json |
| Internal border-strong contradiction | `design-system.md:63-64` states border-strong is 0.14 (matching tokens.json) while its own table at :93 states .12 |
| Theme currency | :296-299 describes a fixed dark theme, but the app now ships `src/hutch/web/styles/hutch-theme-overrides.css` (22,206 B) with an explicit derived light counterpart under `[data-hutch-theme="light"]`; the doc does not mention `data-hutch-theme` |
| Operational drift | :39 and :212 prescribe `.venv/bin/python`, while repo guidance prefers `uv run --frozen --no-sync` (AGENTS.md); recorded only |

### 3.5 `docs/marketing-site.md` (327 lines)

- Claims envelope (1-16, 31-174): development preview as the single stage term, "private preview/alpha" retired (27-28); "assistant" in site prose, "bot" in CLI/internal docs (28-29); external links are the GitHub repository only, no analytics (6-8); capability language table Supported/Experimental/Unavailable (33-37); strict limits on approval, cost, routing, document, delegation and connection claims; FAQ item parity enforced by test (`test_structured_data_and_discovery_metadata_match_the_page`, 227).
- Positioning (19-24): first screen must state category and deployment model; eyebrow "Local-first AI assistants . run on your own machine".
- Provenance rules (201-218): first-run captures from an empty state directory, refreshed 2026-10-26; mascot is an original Blender render via `scripts/render_hutch_agent.py` (7x3 frame grid; a `--palette emerald` variant exists); source merges do not regenerate images; recapture workflow documented.
- Discovery metadata (223-230): title/description lead with category and "local-first"; JSON-LD SoftwareApplication carries name, description, category, OS, version, MIT licence, `isAccessibleForFree`, feature list, `dateModified`, plus `url`, `sameAs`, `author` and `screenshot` "after the GitHub Pages launch"; deliberately no `offers`/`publisher`; shipped 2026-10-28 with canonical, og:url, absolute og:image/twitter:image, sitemap, `/.well-known/security.txt`; origin-root robots.txt caveat and custom-domain checklist in `docs/discoverability.md` (exists, not read).
- Visual system (232-297): tokens.json single source with contrast-pair validation and `--check` drift; asset provenance table (237-243); Tailwind v4 + DaisyUI v5 with a 10-component include list and the `hutch` theme (249-270); GitHub Pages specifics (subpath-relative links, `?v=<hash>`, ~10-minute cache) (272-280); adopted/rejected reference decisions (282-297) - adopted window-chrome product proof, receipts data table, icon feature cards, architecture block, workflow cards, model-route pills, poster wordmark, syntax-coloured code windows; rejected purple aurora heroes, gradient display type, warm-beige palettes, collage cards, translucent container look, page-level emerald hero wash, and a cropped poster wordmark; "The pinned brand contract (emerald accent, 0px controls / 8px panels / 100px chips, one dark theme) governs."
- Verification (299-327): test inventory, audit script `.pipeline/marketing/2026-10/evidence/audit/audit_site.py` (canonical, FAQ parity 20/20, JSON-LD parses, sitemap/security.txt 200), historical-capture caveats, known gaps (no screen-reader session; contrast computed for declared pairs).

CONFLICTS:

| Conflict | Detail |
|---|---|
| Internal radii contradiction | :255-256 says the theme maps "8px controls, 12px panels, 100px chips", while the pinned contract at :296 says "0px controls / 8px panels / 100px chips". The actual theme (`website/src/input.css:55-57`) is field 0.5rem (8px), box 0.75rem (12px), selector 100px - the :255-256 wording matches the code |
| vs plan A.6 | This doc asserts the JSON-LD `screenshot` property and the 2026-10-28 launch metadata; the plan's "no logo/image property" statement is contradicted by both this doc and `index.html:43` |

### 3.6 `docs/research/icon-and-chat-interface-references-2026-10-10.md` (105 lines)

- Dated 2026-10-10. Records: Lucide 24x24 outline vocabulary as reference only, no vendored Figma SVGs (7-17); Microsoft trademark guidance requires a licence, so no Outlook product icon was bundled and a local category glyph was used instead (19-26, 39-41); no Gmail or Google Calendar product icons bundled, older Google SVGs removed (28-36); OpenAI Blossom used exact and white only beside the named ChatGPT service (36-38); decision bullet "Share locally bundled Archivo display typography ... retain system sans for prose" (90-92); single overflow control per assistant, `aria-current` selection, one-line name truncation (57-61, 97-102); Figma/Mobbin retrieval limits (74-86); explicitly "does not establish market prevalence, provider endorsement, or permission" (3-5).

CONFLICTS (staleness, surfaced not reconciled):

- Typography: this doc's decision bullet (Archivo) is superseded by `brand-assets.md:39` ("Replaces the earlier Archivo files") and the shipped Geist subsets; the doc was never updated.
- Bundled provider marks: its "did not bundle" statements for Outlook, Gmail and Google Calendar are contradicted by the current `src/hutch/server/static/brands/` directory (microsoft-outlook.svg, google-gmail-2026q2.png, google-calendar-2026q2.png present) and by `brand-assets.md:15-20`, `DESIGN.md:175-177` and `design-system.md:172-179`, which all bless Outlook/Google Workspace artwork under documented conditions. The repo holds two mutually exclusive records of the same decision; which one governs is a human decision, not this audit's.

### 3.7 `.pipeline/marketing/2026-10/evidence/brand/README.md` (126 lines) and `render_github_social_preview.py` (299 lines, grep-skimmed)

- README (dated 2026-10-28): the 1280x640 GitHub social preview was rendered and "visually verified" by that task (this audit did not re-verify visually); exact render commands (lines 26, 33, including the `UV_CACHE_DIR` sandbox variant); zero network, Geist required or hard-fail (46-58); approved strings only - "Hutch", "Local-first AI assistants", "that run on your machine.", "MIT-licensed . open source . Linux . Development preview" (60-75); no emoji, no em dashes in the card (74-75); edge-safety arithmetic and measured contrast 17.03/10.35/6.14 on #09090b (83-113); wiring into repository settings/og tags was out of scope for that task (115-123).
- Renderer (grep evidence): inlines `website/tokens.css`, requires `--font-display` and other tokens or exits non-zero (lines 33-56, 130); hexagon path identical to the web mark (line 56); wordmark string "Hutch" (capital H, line 107) set at weight 620 / 46px (line 90) - the wordmark-form conflict noted under 3.3; statement at 80px/700 (line 95); fallback background hardcoded #09090b (line 118).

Conflicts: card wordmark casing ("Hutch") vs `brand-assets.md:49` (lowercase `hutch.`); otherwise this evidence set is consistent with tokens.json and the mark definition.

---

## 4. U02: `website/tokens.json` full map (tiers present vs claimed)

File: 181 lines, DTCG-style `$type`/`$value` with `{path.reference}` syntax.

| Tier / section | Lines | Type | Leaves | Notes |
|---|---|---|---|---|
| `color.primitive` | 6-32 | color | 28 | ink 9 (950/900/850/800/750/700/well/sunken/overlay), paper, mist, faint, emerald 5 (300/400/600/ink/deep), blue.400, amber.400, red.400, white alphas 8 (a06-a38) |
| `color.semantic` | 33-61 | color | 27 | bg/surface/panel/raised/well/sunken, text/text-2/text-3, brand/brand-strong/brand-deep/on-brand/link, info/success/warning/danger, border/border-strong/border-emphasis/border-edge/border-soft, ring-glass, focus-ring, scrim-nav, scrim-well |
| `color.verify` | 62-86 | `$extensions` only | 0 | `site.textPairs`: 19 declared contrast pairs - the pairs the plan's E05 and `scripts/build_site_tokens.py --check` consume |
| `font` | 89-94 | fontFamily | 3 | display, body (both Geist stacks), mono (Geist Mono stack) |
| `text` | 96-115 | custom | 17 | 14 sizes (2xs 12px .. poster clamp(88px,12.5vw,260px)) + 3 line heights (1.04/1.16/1.65) |
| `space` | 117-131 | dimension | 12 | 4px to 128px |
| `size` | 133-140 | dimension | 5 | content 1160px, measure 62ch, nav 68px, target 44px, rail 2px |
| `radius` | 142-149 | dimension | 5 | micro 4, control 8, panel 12, chat 20, chip 100 |
| `motion` | 151-160 | custom | 7 | 4 durations, 2 easings, reveal-shift 20px |
| `layer` | 162-167 | number | 3 | nav 100, dialog 200, live 210 |
| `deprecated` | 169-180 | `$extensions` only | 0 | `site.migration` ledger, 6 entries |
| **component tier** | - | - | **0** | **absent** |

Totals: 107 value leaves; generated `website/tokens.css` carries exactly 107 custom properties; `src/hutch/server/static/brand-tokens.css` is byte-identical.

Component-tier discrepancy (closes the brief's U02 question): `tokens.json:2` states "Primitive -> semantic -> component", but no component tier exists in the source file, in the generated output, or in any doc pointing to one. Component geometry instead lives in `DESIGN.md` frontmatter `components:` (lines 107-139) and in daisyUI theme blocks (`website/src/input.css:54-57`, `app/src/input.css` theme block ~206-210). The plan's claim that the file "asserts a component tier it lacks" is therefore CONFIRMED.

Extensions and deprecations present:

- `site.decorative: true` on `border`, `border-soft`, `ring-glass` (lines 52, 56, 57).
- `site.textPairs` (19 contrast pairs, lines 64-84) consumed by the generator's `--check` mode (`scripts/build_site_tokens.py:6,11,154`) and `tests/test_site_tokens.py`.
- `site.migration` ledger (lines 171-178): retirement of the `--accent` site blue (#52a8ff -> `--brand` #34d399, Oct-2026), glass `--bg-card` fills -> solid `--surface/--panel`, `--radius-lg` 16/24 -> `--radius-panel` 12px, the 2.05s intro overlay, the scripted approval demo, and the `pip install hutch` CTA.

Plan-count corrections (rows 21-22): primitives 28 not 31; spaces 12 not 10; motion 7 not 8; the plan's category breakdown sums to 109 while its 107 total is correct.

---

## 5. U06: route and surface map (from `main`)

Server-rendered page routes - `src/hutch/server/pages.py` (registered via `register_pages(app)`, called at `app.py:7447-7448`):

| Line | Method/path | Surface |
|---|---|---|
| 178-179 | GET `/legacy`, `/legacy/` | legacy SPA notice shell |
| 190 | GET `/` | Studio shell (`static/index.html`, FileResponse at :194) |
| 196 | GET `/overview` | server overview page |
| 200 | GET `/_home` | home fragment |
| 204 | GET `/api/overview` | overview JSON for server pages |
| 233 | GET `/_badge` | approval-badge fragment (live pill) |
| 237 | GET `/stream/live` | server-page live stream |
| 245 | GET `/bots` | bots list |
| 267 | GET `/bots/new` | new-bot form |
| 271 | POST `/bots` | create bot |
| 304 | GET `/bots/{name}` | bot detail |
| 313 | POST `/bots/{name}/run` | start run |
| 326 | POST `/bots/{name}/{action}` | bot actions |
| 393 | POST `/bots/{name}/memory/delete` | memory delete |
| 400 | POST `/bots/{name}/allows/revoke` | sticky-allow revoke |
| 409 | GET `/runs` | runs list |
| 421 | GET `/runs/{run_id}` | run detail |
| 426/444/452/461 | GET `/runs/{run_id}/events|meters|wait|stream` | run fragments/SSE |
| 480/489/496 | POST `/runs/{run_id}/stop|resume|dismiss` | run control |
| 504 | POST `/stop-all` | global stop |
| 527 | GET `/approvals` | approvals queue |
| 531 | GET `/_approvals` | approvals fragment |
| 535 | POST `/approvals/{approval_id}/decide` | approval decision |
| 587 | GET `/connections` | connections page (redirects into Apps & AI per design-system.md:23-26) |
| 593 | GET `/legacy/connections` | retired forms |
| 602/617 | POST `/connections/chatgpt/sign-in|disconnect` | ChatGPT connector |
| 633 | POST `/connections/add` | add connection |
| 645 | POST `/connections/{name}/{action}` | connection actions |
| 702/711 | GET/POST `/login` | sign-in |
| 706 | GET `/pair` | device pairing |

Additional page modules (not named by the plan): `src/hutch/server/pages_models.py:18` GET `/models`; `src/hutch/server/pages_usage.py:20` GET `/usage`.

`src/hutch/server/app.py`: `create_app()` at :2062; `FastAPI(title="hutch", ...)`; 241 route decorators total, all under `/api/*` in the sampled ranges - e.g. `/api/health`, `/api/v1/runtime`, `/api/v1/sources`, `/api/v1/jobs`, `/api/v1/events(/stream)`, `/api/v1/changes(/stream)`, `/api/v1/snapshot`, `/api/v1/pairing/*`, `/api/v1/passkeys/*`, `/api/v1/session*`, `/api/v1/devices`, `/api/v1/capabilities`, `/api/v1/compatibility`, `/api/v1/model-capabilities`, `/api/v1/connections`, `/api/v1/schedules*`, `/api/v1/bots/.../schedules*`, `/api/v1/task-templates`, `/api/v1/conversations*` (query, export, archive, title, persona, persona-feedback, bot-purpose-drafts), `/api/v1/search/messages`, `/api/bots*`, `/api/v1/model-routes`, `/api/bots/{ref}/models` (:5146), `/api/v1/usage` (:6177), Outlook Calendar/Mail/Send connection trees (:6914-7195), ChatGPT sign-in (:7202), `/auth/callback` (:7232), `/api/connections` (:7265), OpenCode status/logins/oauth (:7367-7429). OAuth completion handlers redirect to the SPA with result flags (`RedirectResponse("/?..._result=...#/connections")`, :6442-7258). Static mount at `/static` (:7453). Completeness caveat: other JSON API modules named in AGENTS.md (`workflows_api.py`, `channels_api.py`, `skills_api.py`, `notion_api.py`, `kdeconnect_api.py`) were not enumerated route-by-route - UNVERIFIED as a complete REST inventory; no `include_router` call was found in the `app.py` grep sample.

Studio hash routes (declared in `src/hutch/server/static/index.html`): `#/chat`, `#/chats`, `#/overview`, `#/schedules`, `#/runs`, `#/runtime`, `#/skills`, `#/bots`, `#/connections`, `#/settings` (10, matching the plan). Additionally `#/assistant/new` appears 7 times in `src/hutch/server/static/app.js` (mandated by DESIGN.md:318 and design-system.md:155) - the JS bundle registers at least one route the shell HTML does not list. Other app.js hash routes were not enumerated - UNVERIFIED.

Marketing surfaces: single page with anchors `#top #proof #workflow #runs #control #receipts #cases #get #faq` (each present once), plus files `downloads.json` (release manifest: contract_version 1, channel preview, 4 platform entries with empty artifacts arrays), `robots.txt`, `sitemap.xml`, `llms.txt`, `security.txt`, `.well-known/security.txt` (232 B), `THIRD_PARTY_NOTICES.txt`, `tokens.css`, `app.css`, `styles.css`/`styles.min.css`, `site.js`, and assets (`og-card-1200x630.png`, `github-social-preview-1280x640.png`, `hutch-agent.webp`, `agent/` 21 frames, `captures/` 4 webp, `fonts/` 3 files).

Desktop: no routes; Tauri bundle inactive (`desktop/tauri.conf.json:15`).

---

## 6. Findings

### 6.1 Plan claims REFUTED (stated plainly)

1. `base.html` links **9** stylesheets (plan A.1) - it links **10** (`base.html:10-25`).
2. Studio shell links **18** stylesheets (plan A.1) - it links **15** (`static/index.html:12-34`).
3. Token breakdown "31 primitive colours, 10 spaces, 8 motion" (plan A.3) - actual 28, 12, 7. The 107 total is right; the plan's own breakdown sums to 109.
4. "No logo/image property in the SoftwareApplication block" (plan A.6) - the block carries `"screenshot"` pointing at `website/assets/captures/setup-desktop.webp` (`index.html:43`), added for the 2026-10-28 launch (`docs/marketing-site.md:226,230`). The narrower "no `logo` property" statement remains true.
5. "`--fs-*`/`--s-*` scale from `hutch-tokens.css`" (plan A.3/U03) - those variables are defined in `src/hutch/server/static/style.css:113,118`; `hutch-tokens.css` owns the `--hutch-*` namespace and contains neither.
6. "`var(--color-semantic-brand)` in visible headers" as a blanket statement (plan A.4) - true only on the marketing page; `base.html` uses `var(--accent)` (aliased to the brand token at `hutch.css:35`, itself recorded as the retired blue in `tokens.json:172`) and the Studio shell uses `var(--brand)`.
7. Mascot "no usage rules" (plan C14) - usage and provenance rules exist in `docs/brand-assets.md:74-76` and `docs/marketing-site.md:207-209,239-247`.
8. Social card "not generated from source artwork" (plan C12) - a reproducible, token-driven renderer exists for the GitHub social preview (evidence README, 2026-10-28). For the og-card the referenced "S-c renderer" is not in this tree (UNVERIFIED).

### 6.2 New facts the plan missed

- `website/downloads.json` is a desktop **release manifest** (contract_version 1, channel preview; windows-x64, macos-arm64, macos-x64, ubuntu-x64 entries; every `artifacts` array empty) and is linked from the marketing head as "Hutch desktop release manifest" (`index.html:8`). The plan recorded only "not a PWA"; this manifest contract is a separate forward-looking surface.
- `website/assets/captures/` holds 4 committed screenshots (`setup-desktop.webp`, `setup-phone.webp`, `response-style-desktop.webp`, `response-style-phone.webp`), consumed by `README.md:16` and the JSON-LD `screenshot` property; the plan's asset inventory omitted the directory.
- Reproducible render pipelines exist for brand assets: `scripts/render_hutch_agent.py` (mascot, Blender) and `.pipeline/marketing/2026-10/evidence/brand/render_github_social_preview.py` (social card), plus a referenced-but-absent "S-c og-card renderer".
- The desktop icon (`desktop/icons/icon.svg`) is a **different mark variant**: different hexagon geometry, stroke #28cd9d, 2.2 stroke-width, dark rounded-rect background plate. The web mark family uses #34d399, path `M16 2 28 9v14L16 30 4 23V9z`, stroke-width 2.5, no plate.
- The route table is split across `pages.py`, `pages_models.py`, `pages_usage.py` and `app.py`; the FastAPI app is titled `hutch` (`app.py:2107`).
- `docs/design-system.md:84-89` carries a blue-tinted neutral ramp that matches neither tokens.json nor DESIGN.md (section 3.4) - the single largest documentation conflict found.
- Three documents contain internal or mutual contradictions on values: border-strong 0.12 vs 0.14 (`DESIGN.md:16`, `design-system.md:63-64` vs `:93`, `tokens.json:53`); marketing radii wording "8px controls" vs "0px controls" inside `marketing-site.md` (:255-256 vs :296); neutral ramp panel/raised values (`DESIGN.md` vs `tokens.json`).
- The wordmark renders in three casings today: lowercase `hutch.` with emerald stop (marketing lockup), lowercase `hutch` (server pages, Studio), capital `Hutch` (titles/OG/JSON-LD and the GitHub social-card lockup).
- The 2026-10-10 icon research doc's decisions (Archivo typography; no bundled Outlook/Gmail/Calendar marks) are stale relative to the shipped repo and the later docs; both records still stand in `docs/`.
- `hutch-theme-overrides.css` (22,206 B) provides an explicit derived light theme under `[data-hutch-theme="light"]`, beyond the "fixed dark theme" the docs describe; no light-theme contrast evidence exists (plan U05 remains open and accurate).
- Two daisyUI themes are both named `hutch` but differ: marketing sets `--radius-selector: 100px` and `--color-error-content: #2a0707`; the app sets `--radius-selector: 0.5rem` and `#2a0606`; include lists differ (10 vs 18 components).
- Plan-internal numbering clash: "C13" is used for both the daisyUI comment drift (A.3) and the missing press kit (A.4).
- Terminology mandates not inventoried by the plan: "development preview" is the only stage term ("private preview/alpha" retired); site prose says "assistant", CLI/docs say "bot" (`docs/marketing-site.md:26-29`).
- User-set quality gates exist that any brand change must satisfy: aesthetic >= 90, functionality >= 95, judged on opened desktop and phone screenshots (`PRODUCT.md:102-106`); the incumbent skin is on record as "anti-reference" (`PRODUCT.md:96-97`).

### 6.3 Conflicts requiring a human decision (surfaced, not resolved)

- Which neutral ramp is canonical: tokens.json (#09090b/#0f0f12/#16161a/#1c1c21) or the DESIGN.md frontmatter (#09090b/... /#101013/#17171b), given that design-system.md's table matches neither and DESIGN.md holds documented precedence.
- Whether the 2026-10-10 research doc's "did not bundle" decisions should be formally superseded (it conflicts with brand-assets.md, DESIGN.md, design-system.md and the shipped `brands/` files).
- Wordmark definition: DESIGN.md weight 650/1.125rem vs brand-assets.md extrabold vs the rendered 20px extrabold marketing lockup and the 46px/620 social-card "Hutch".
- Lockup size: brand-assets.md's 22px standard lockup vs the 26px marketing header mark.
- `tokens.json`'s own `$description` asserts a component tier that does not exist; either the description or the architecture needs correction by the owner.

### 6.4 UNVERIFIED (with reasons)

- Live GitHub Pages deployment state and the actual bytes served at `https://k-arthur.github.io/hutch/` (repository evidence only; no network fetch run).
- Every rendered/visual claim: page layouts, favicon rendering, desktop icon pixels, og-card and social-card appearance, mascot frames - no browser or image inspection in this session.
- The E05 contrast ratios were not recomputed with the WCAG formula; they are corroborated by two independent tracked sources (evidence README 2026-10-28; `DESIGN.md:211`).
- "23 unique" hex literals (per-file counts 39/3/2/1 reproduced; uniqueness not recomputed).
- Completeness of the REST route inventory (other API modules not enumerated) and of app.js hash routes (only `#/assistant/new` was grepped).
- Feature-flag absence beyond the plan's declared inputs.

---

## 7. Evidence: commands used

All commands run 2026-10-28 from the repository root on branch `main` (`git log -1`: `577e1154`), read-only except the creation of this one output file. No URLs were fetched; all evidence is repository-local, so no external access dates arise beyond dates recorded inside repository files (2026-10-07, 2026-10-09, 2026-10-10, 2026-10-20, 2026-10-22, 2026-10-23, 2026-10-26, 2026-10-28 as cited above).

```sh
git rev-parse --abbrev-ref HEAD && git log -1 --oneline
git show brand/plan:docs/brand/00-PLAN.md | sed -n '65,233p'
git show brand/plan:docs/brand/00-PLAN.md | sed -n '179,213p'

wc -l DESIGN.md PRODUCT.md docs/brand-assets.md docs/design-system.md \
  docs/marketing-site.md docs/research/icon-and-chat-interface-references-2026-10-10.md \
  .pipeline/marketing/2026-10/evidence/brand/README.md website/tokens.json \
  website/index.html src/hutch/server/static/index.html \
  src/hutch/server/templates/base.html website/tokens.css \
  src/hutch/server/static/brand-tokens.css website/src/input.css app/src/input.css

# line-ranged file reads (read tool) of every input listed in section 1

grep -nE '<header|</header>|<footer|</footer>|<nav|wordmark|poster|weave-agent' website/index.html
grep -c 'M16 2 28 9v14L16 30 4 23V9z' website/index.html                 # -> 4
grep -c '"@type": "Question"' website/index.html                         # -> 20
grep -n -- '--accent' website/tokens.css src/hutch/server/static/brand-tokens.css src/hutch/server/static/hutch.css
grep -n 'color-semantic-brand' website/index.html src/hutch/server/static/index.html src/hutch/server/templates/base.html

grep -nE '@router\.(get|post|...)|@app\.(get|post)' src/hutch/server/pages.py
grep -nE '@app\.(get|post|put|delete|patch)|include_router' src/hutch/server/app.py
grep -cE '@app\.(get|post|put|delete|patch)' src/hutch/server/app.py      # -> 241
grep -rnE '"/(models|usage)"' src/hutch/server/*.py
grep -nE 'RedirectResponse|app.mount|StaticFiles|register_pages' src/hutch/server/app.py
grep -oE '#/[a-z-]+' src/hutch/server/static/index.html | sort | uniq -c
grep -c '#/assistant/new' src/hutch/server/static/app.js                 # -> 7

ls src/hutch/server/templates/ ; ls -la website/assets/fonts/ src/hutch/server/static/fonts/
ls src/hutch/server/static/brands/ ; ls website/assets/captures/ ; ls website/assets/agent/ | wc -l
ls -d docs/brand ; ls -la desktop/icons/ ; grep -nE '"active"|icon|bundle' desktop/tauri.conf.json
file desktop/icons/icon.svg desktop/icons/icon.png desktop/icons/icon.ico desktop/icons/icon.icns \
     website/assets/og-card-1200x630.png website/assets/github-social-preview-1280x640.png \
     website/assets/hutch-agent.webp
cat desktop/icons/icon.svg

grep -nE 'daisyui|daisyUI' app/src/input.css website/src/input.css package.json
grep -n '@import' app/src/input.css ; ls src/hutch/web/styles/
grep -cE -- '--fs-' src/hutch/web/styles/hutch-tokens.css                # -> 0
grep -cE -- '--s-[0-9]' src/hutch/web/styles/hutch-tokens.css            # -> 0
grep -rnE -- '--fs-(xs|sm|base)[^a-z-]*:' app/src src/hutch/web/styles src/hutch/server/static/*.css
git ls-files tests/e2e | grep -Ei 'visual|screenshot|snapshot'            # -> empty (exit 1)
grep -n -- '--check' scripts/build_site_tokens.py ; ls tests/test_site_tokens.py
cmp website/tokens.css src/hutch/server/static/brand-tokens.css          # -> identical

for a in top proof workflow runs control receipts cases get faq; do printf '%s:%s ' "$a" "$(grep -c "id=$a" website/index.html)"; done
ls -la website/.well-known/
grep -nE 'branches|paths|website|on:|push|permissions|concurrency' .github/workflows/pages.yml
grep -nEi 'manifest|apple-touch|serviceWorker|color-scheme' website/index.html src/hutch/server/static/index.html src/hutch/server/templates/base.html
git ls-files | grep -iE '(^|/)sw\.js$|service-worker|service_worker'      # -> empty

grep -nE 'MIT|Development preview|Linux|solo|Ollama|llama|LM Studio|OpenRouter|OpenCode|not a fit' README.md
sed -n '85,118p' README.md
ls -l DESIGN.md PRODUCT.md docs/brand-assets.md docs/design-system.md docs/marketing-site.md \
  docs/research/icon-and-chat-interface-references-2026-10-10.md
ls -d src/app src/styles public tailwind.config.js tailwind.config.ts index.html pyproject.toml

# E04 recount (a first attempt carried a mis-escaped \b inside a JS string and
# returned 0; the corrected pattern is shown)
grep -oE '#[0-9a-fA-F]{3,8}' website/tokens.css | wc -l                  # -> 39
grep -oE '#[0-9a-fA-F]{3,8}' website/src/input.css | wc -l               # -> 3
grep -oE '#[0-9a-fA-F]{3,8}' app/src/input.css | wc -l                   # -> 2
grep -oE '#[0-9a-fA-F]{3,8}' website/index.html | wc -l                  # -> 1
cat website/tokens.css website/src/input.css app/src/input.css website/index.html | grep -oE 'var\(--' | wc -l   # -> 251
grep -cE 'font-size:' app/src/input.css                                  # -> 39
grep -c '@font-face' src/hutch/server/static/hutch.css                   # -> 2

grep -nE '#[0-9a-fA-F]{6}|34d399|Geist|hexagon|M16|tokens.css|Hutch|Local-first|Development preview' \
  .pipeline/marketing/2026-10/evidence/brand/render_github_social_preview.py
```