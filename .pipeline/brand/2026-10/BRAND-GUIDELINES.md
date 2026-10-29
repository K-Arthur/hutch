# BRAND-GUIDELINES.md — Hutch Brand & Identity Guidelines (Run 6 — 2026-10-29)

Version: 1.0 (Pipeline baseline, 2026-10-29)
Status: **Complete specification for decided elements** — Name ("Hutch", D38), Tagline ("Your bots. Your machine. Your rules.", D11), Wordmark (Bricolage Grotesque 800, D42), Colour System (`COLOUR-SYSTEM.md`, D12/D46), and Mark ("Visor Hutch" — Direction B, picked by maintainer 2026-10-29, D54).
Scope note: Stored in `.pipeline/brand/2026-10/`. Integration into `website/`, `src/hutch/server/`, `docs/`, and `desktop/` requires its own dated authorisation (Run 7).
Legal disclaimer: **Not legal advice.** Nothing in these guidelines claims or implies that "Hutch", the wordmark, or the "Visor Hutch" mark is cleared, registered, distinctive, or non-infringing in any jurisdiction. See Section 11 and `IP-CLEARANCE.md`.

---

## 1. Foundation

### 1.1 Product Truth
Hutch is a local-first, open-source multi-bot agent platform in development preview, built Linux-first ("Your bots. Your machine. Your rules.").
- **Core promise:** Control state, run transcripts, per-bot workspaces, and browser profiles stay on the user's computer; the user chooses local or hosted model routes (`Ollama`, `llama.cpp`, `LM Studio`, `OpenAI`, `Anthropic`, `OpenRouter`, `OpenCode`) with explicit action approvals and spend ceilings (`STRATEGY.md` T1–T5).
- **UI hierarchy:** Conversation is the primary workspace; governance (approvals, human checkpoints, spend boundaries) is the loudest signal on screen; chrome stays quiet and evidence-dense (`PRODUCT.md:108-118`).

### 1.2 Positioning & Voice (`STRATEGY.md` Section 6, D19)
- **Foundation (PO-1 — "Own the stack you run on"):** Lead with concrete, verifiable proof (local state, model routes, approval gates, immutable run receipts) rather than AI hype or superlatives.
- **Execution (PO-2 — "Plain-language control"):** The everyday path works without runtime or executor jargon.
- **Terminology contract (`docs/marketing-site.md:26-29`):**
  - Stage term: **"development preview"** only (never "alpha", "beta", or "private preview").
  - Public marketing prose refers to **"assistants"** (or pairs "bots / assistants" via the tagline); CLI, operator dashboard, and technical documentation refer to **"bots"**.
  - Never imply a hosted cloud service or published native installers until `website/downloads.json` artifacts are populated.

---

## 2. Mark System — "Visor Hutch" (Selected 2026-10-29, D54)

### 2.1 Concept & Anatomy
The Hutch mark ("Visor Hutch") synthesizes three ideas into a single `fill-rule="evenodd"` compound vector path on a `32x32` grid (`4-unit` module):
1. **The Hutch (Protective Shelter & Burrows):** An enclosing hooded dome standing on **three grounded timber posts** (`4.40u` wide) flanking **two concave semicircular burrow arches** (`5.40u` wide, apex `y = 22.60`), with a wide **recessed upper loft window** (`x = 6.80..25.20`, `y = 8.60..18.40`).
2. **The Pac-Man Ghost Archetype:** A compact `1:1` domed upper body flowing into a tangent-continuous scalloped base whose center post touches the floor at `x = 16.00, y = 28.30` (eliminating center-mouth pareidolia while providing an iconic footed silhouette).
3. **Grokbot / Hutch Bot Sigil Language:** Inside the dark recessed loft visor sit **two positive-space, inward-tilted (`-8°` left, `+8°` right) vertical oval eyes** with a `+0.30u` upward offset on the right eye, glancing attentively toward the wordmark and echoing Hutch's in-app bot avatars (`src/hutch/server/static/app.js` `ID_FACES`).

### 2.2 Two Redrawn Size Tiers (`PRINCIPLES.md` R6)
Never scale the master SVG down below `24px` without switching tiers; use the dedicated small-tier redraw so interior counterforms survive `16x16px` rasterisation:

| Tier | Target Sizes | Master File | Outer Span (`32x32` Grid) | Visor Cutout (`x`, `y`) | Positive Eyes `(cx, cy, rx, ry, rot)` | Min Visor Moat |
|---|---|---|---|---|---|---|
| **Master Tier** | `>= 25px` (headers `26px`, icons `32–512px`, social, print) | `assets/production/svg/hutch-mark-master.svg` | `x = 4.00..28.00` (`24.0u`), `y = 3.70..28.30` (`+0.30u` overshoots) | `x = 6.80..25.20`, `y = 8.60..18.40` (`r_top=5.4u`, `r_bot=3.6u`) | L: `(12.20, 13.70, 2.05, 2.65, -8°)`<br>R: `(19.80, 13.40, 2.05, 2.65, +8°)` | `2.45u` vert, `3.35u` side, `3.50u` bridge |
| **Small Tier** | `16px–24px` (browser favicons, compact `22px` sidebar header) | `assets/production/svg/hutch-mark-small.svg` | `x = 3.00..29.00` (`26.0u`), `y = 2.80..29.20` | `x = 6.20..25.80`, `y = 7.60..18.60` (`r_top=5.8u`, `r_bot=3.8u`) | L: `(12.00, 13.25, 2.15, 2.65, -8°)`<br>R: `(20.00, 13.00, 2.15, 2.65, +8°)` | `2.85u` vert (`1.42px` at `16px`), `3.65u` side |

### 2.3 Clear Space & Minimum Sizes
- **Clear space:** Maintain a minimum clear margin of **`0.25X`** (`25%` of the mark's height = `8u` on the `32u` grid) on all four sides of the mark or lockup. Inside app headers (`68px` nav height), vertical padding must be at least `12px`.
- **Minimum size:** `16x16px` using `hutch-mark-small.svg` (or `favicon-16x16*.png`); `22x22px` in horizontal UI lockups; `32x32px` for `hutch-mark-master.svg`.

### 2.4 Approved Mark Colourways
Because the mark is a single `fill-rule="evenodd"` compound path, the recessed visor and burrow arches take the background colour automatically, while the positive eyes take the mark fill:

| Surface Context | Mark Fill | Background Surface | Measured WCAG Contrast | File |
|---|---|---|---|---|
| **Primary Dark (Product & Site)** | `emerald-400` (`#34d399`) | `ink-950` (`#09090b`) or `ink-900` (`#0f0f12`) | `10.35:1` / `9.95:1` (AAA) | `hutch-mark-master.svg` |
| **Monochrome Dark (Reversed)** | `paper` (`#ededf0`) | `ink-950` (`#09090b`) | `17.03:1` (AAA) | `hutch-mark-mono-dark.svg` |
| **Light Surface (Docs, Press, Print)** | `emerald-700` (`#047857`) | `paper` (`#ededf0`) or `#ffffff` | `4.69:1` / `5.48:1` (AA) | `hutch-mark-light.svg` |
| **Monochrome Light / Print** | `ink-950` (`#09090b`) | `paper` (`#ededf0`) or `#ffffff` | `17.03:1` / `19.86:1` (AAA) | `hutch-mark-mono-light.svg` |
| **Brand Accent Block** | `emerald-ink` (`#052e21`) | `emerald-400` (`#34d399`) | `7.70:1` (AAA) | Inline via `currentColor` |

### 2.5 Mark Misuse Rules (Do Not Do)
1. **Never use `emerald-400` (`#34d399`) on `paper` (`#ededf0`) or white:** It measures `1.65:1` and fails WCAG contrast (`COLOUR-SYSTEM.md` F1). Always switch to `emerald-700` (`#047857`) or `ink-950` (`#09090b`) on light surfaces.
2. **Never recolour the eyes separately from the outer shell:** The mark is a single-colour `evenodd` path; two-tone fills inside the mark are not part of the system.
3. **Never flip the mark horizontally:** The `+0.30u` upward offset on the right eye is calibrated to glance right toward the wordmark.
4. **Never add strokes, drop shadows, neon outer glows, or gradients.**
5. **Never revive archived Round 1–12 concepts or the legacy `#28cd9d` / `#34d399` hexagon (`DECISION.md` D51/D52).**

---

## 3. Wordmark & Lockup Architecture (`DECISION.md` D42)

### 3.1 Wordmark Specification
- **Typeface:** **Bricolage Grotesque** (SIL Open Font License 1.1), pinned at `font-weight: 800`, `wdth: 100`, `opsz: 48`.
- **Letterform & Casing:** Strictly lowercase **`hutch`** in logo lockups. In running prose, page `<title>` tags, JSON-LD, and Open Graph metadata, write **"Hutch"** in standard title case.
- **Letter-spacing (Tracking):** `-0.03em` (`-3%`), with an optical kerning adjustment of `-0.01em` before the period.
- **The Period Rule (Reconciling Surface Drift):**
  - **Marketing site, social cards, press kit, and standalone brand lockups:** Include the period (`hutch.`), coloured in the brand signal (`#34d399` on dark surfaces; `#047857` on light surfaces; matching monochrome in 1-colour contexts).
  - **Operator dashboard (`src/hutch/server/static/index.html`) and server-rendered Jinja headers (`base.html`):** The no-period form (`hutch`) is an approved compact operator-chrome variant so the header stays quiet beside live status and approval pills.

### 3.2 Horizontal Lockup Geometry
- **Proportion (`48px` master canvas):**
  - Mark height: `38px` (`0.792` of canvas height, placed at `x = 0, y = 4.2px` so the rounded feet at `y = 40.0px` optically align with the `y = 38.0px` typographic baseline of `hutch`).
  - Gap between mark and `h` stem: `12px` (`0.316` of mark width = `10u` on the `32u` mark grid).
  - Wordmark font size: `44px` (`cap-height = 29.04px`, `ascender = 31.30px`, `x-height = 23.23px`).
- **Component-scale mappings:**
  - Marketing header: `26px` mark + `9px` gap + `20px` wordmark (`hutch.`).
  - Studio sidebar / Jinja header: `22px` mark + `8px` gap + `18px` wordmark (`hutch`).
  - Social cards (`1200x630` / `1280x640`): `48px` mark + `16px` gap + `46px` wordmark (`hutch.`).

---

## 4. Colour System (`COLOUR-SYSTEM.md`, `website/tokens.json` Governing per D12)

### 4.1 Dark Surface Palette (Primary Product & Marketing Surface)

| Token (`website/tokens.json`) | Hex / Value | Role | Measured Contrast (WCAG 2.x) |
|---|---|---|---|
| `color.primitive.ink.950` (`--bg`) | `#09090b` | Page canvas, icon tile background, maskable background | Base (`1.00:1`) |
| `color.primitive.ink.900` (`--surface`) | `#0f0f12` | Primary elevated surface, card frames | `16.38:1` vs `paper` |
| `color.primitive.ink.800` (`--panel`) | `#16161a` | Panels, drawers, pills | `15.10:1` vs `paper` |
| `color.primitive.ink.750` (`--raised`) | `#1c1c21` | Hover/raised controls, active tabs | `14.12:1` vs `paper` |
| `color.primitive.paper` (`--text`) | `#ededf0` | Primary text, reversed monochrome mark | **`17.03:1`** on `ink-950` (AAA) |
| `color.primitive.mist` (`--text-2`) | `#a3a3ae` | Secondary body copy | **`7.97:1`** on `ink-950` (AAA) |
| `color.primitive.faint` (`--text-3`) | `#8e8e99` | Tertiary / metadata text (never use dimmer text) | **`6.14:1`** on `ink-950` (AA) |
| `color.primitive.emerald.400` (`--brand`) | `#34d399` | Primary brand mark, wordmark period, primary links/actions | **`10.35:1`** on `ink-950` (AAA) |
| `color.primitive.emerald.300` (`--link`) | `#6ee7b7` | Interactive link hover/text accent | **`13.05:1`** on `ink-950` (AAA) |
| `color.primitive.emerald.600` (`--brand-strong`) | `#10b981` | Pressed/active brand state (never set `paper` text on `#10b981`: `2.17:1` FAIL) | **`7.84:1`** on `ink-950` (AAA) |
| `color.primitive.emerald.ink` (`--on-brand`) | `#052e21` | Text/icons placed ON `#34d399` brand fills | **`7.70:1`** on `emerald-400` (AAA) |
| `color.primitive.blue.400` (`--info`, `--focus-ring`) | `#60a5fa` | Keyboard focus ring (`2px` solid, `2px` offset) & info state | **`7.83:1`** on `ink-950` (AAA) |
| `color.primitive.amber.400` (`--warning`) | `#fbbf24` | Approval-needed / warning state (always pair with icon + label) | **`11.92:1`** on `ink-950` (AAA) |
| `color.primitive.red.400` (`--danger`) | `#f87171` | Destructive / error state (always pair with icon + label) | **`7.19:1`** on `ink-950` (AAA) |
| `color.primitive.white.a38` (`--border-edge`) | `rgba(255,255,255,0.38)` | Meaningful control boundaries (hairlines `a07`/`a14` are decorative only) | **`3.47:1`** on `ink-950` (UI pass) |

### 4.2 Light Surface Palette (Docs, Press Sheets, Print & Derived `[data-hutch-theme="light"]`)
Because `emerald-400` (`1.65:1`), `blue-400` (`2.18:1`), `amber-400` (`1.43:1`), and `red-400` (`2.37:1`) all fail WCAG AA on `paper` (`#ededf0`), light surfaces must substitute darker tokens (`COLOUR-SYSTEM.md` F1, F3, F5):

| Light Role | Proposed Hex | Measured Contrast on `paper` (`#ededf0`) | Notes |
|---|---|---|---|
| Light Brand Signal (`emerald-700`) | `#047857` | **`4.69:1`** (AA normal text & graphics) | Use for mark, wordmark period, and links on light surfaces |
| Deep Print Brand (`emerald-800`) | `#065f46` | **`6.58:1`** (AA) | Use for small print typography and uncoated stock |
| Primary Light Text (`ink-950`) | `#09090b` | **`17.03:1`** (AAA) | Body copy and monochrome mark on `paper` |
| Light Focus & Info (`blue-700`) | `#1d4ed8` | **`5.74:1`** (AA) | Replaces `blue-400` on light surfaces |
| Light Warning (`amber-800`) | `#92400e` | **`6.07:1`** (AA) | Replaces `amber-400` on light surfaces |
| Light Danger (`red-700`) | `#b91c1c` | **`5.54:1`** (AA) | Replaces `red-400` on light surfaces |

### 4.3 Print CMYK Briefing Approximations (Zero-Spend Posture D15 — Proof Owed)
- `emerald-700` (`#047857`) -> `C 85  M 25  Y 65  K 15` (approx)
- `emerald-800` (`#065f46`) -> `C 88  M 35  Y 70  K 25` (approx)
- `ink-950` (`#09090b`) -> Rich Black `C 60  M 40  Y 40  K 100` (for large fills; use `100% K` for body text)

### 4.4 Brand vs. Success Token Collision Rule (`COLOUR-SYSTEM.md` F2)
In `website/tokens.json`, `color.semantic.brand` and `color.semantic.success` both resolve to `emerald.400` (`#34d399`). Until a product token split is authorised:
- Never use an unlabelled green dot alone to mean "online/succeeded" adjacent to the brand mark.
- Every status indicator (`success`, `warning`, `danger`, `waiting_approval`) must pair colour with an explicit shape/icon (`check`, `clock`, `alert`, `x`) and a visible text label.

---

## 5. Typography

### 5.1 Three-Font Architecture
Zero remote font requests (`fonts.googleapis.com` or CDNs are prohibited by `PRODUCT.md:69-74`). Every font is self-hosted as a WOFF2 subset with its SIL Open Font License 1.1 text file alongside it:

| Role | Family | Weights / Axes | Self-Hosted Asset (`production/fonts/` & `website/assets/fonts/`) | Licence |
|---|---|---|---|---|
| **Brand Wordmark** | **Bricolage Grotesque** | `800` (`wdth 100`, `opsz 48`), tracking `-0.03em` | `bricolage-grotesque-latin-800.woff2` (`47,260 B`) + `OFL-bricolage-grotesque.txt` | SIL OFL 1.1 |
| **UI Display & Prose** | **Geist** (variable) | `400–700` (`--font-display`, `--font-body`) | `geist-latin-var.woff2` (`37,832 B`) + `OFL-geist.txt` | SIL OFL 1.1 |
| **Code, Receipts & IDs** | **Geist Mono** (variable) | `400–600` (`--font-mono`) | `geist-mono-latin-var.woff2` (`38,508 B`) + `OFL-geist.txt` | SIL OFL 1.1 |

### 5.2 Type Scale & Line Heights (`website/tokens.json:96-115`)
- **Sizes:** `2xs` (`12px`), `xs` (`13px`), `sm` (`14px`), `base` (`16px`), `lg` (`18px`), `xl` (`20px`), `2xl` (`24px`), `3xl` (`30px`), `4xl` (`36px`), `5xl` (`48px`), `6xl` (`60px`), `hero` (`clamp(40px, 6vw, 76px)`), `poster` (`clamp(88px, 12.5vw, 260px)`).
- **Line heights:** `tight` (`1.04` for display headlines), `snug` (`1.16` for section titles), `body` (`1.65` for long-form prose; measure capped at `62ch`).

---

## 6. Iconography & Character Tiering

### 6.1 Product UI Iconography
- **24x24 Outline System:** Functional UI icons (`src/hutch/server/templates/_icons.html` and `app.js` `icon()`) use a `24x24` `viewBox`, `stroke="currentColor"`, `stroke-width="2"`, `stroke-linecap="round"`, `stroke-linejoin="round"`, `fill="none"`.
- **Ban on Emoji (`AGENTS.md` Hard Rule):** Never use Unicode emoji or dingbat characters in source code, documentation, or UI surfaces (`scripts/audit_emoji.py`).

### 6.2 Two-Tier Character & Avatar Doctrine (`CONCEPT-LOG.md` D4, `DECISION.md` D25)
1. **Operator App Tier (2D Bot Sigils):** Inside the Studio dashboard (`app.js:1432-1523`), each bot receives a deterministic 2D geometric silhouette (`ID_HEADS`: orb, capsule, bean, drop, pebble, shield, triangle, hex) paired with two inward-tilted oval eyes (`ID_FACES`, contrast ink `#0b1511`). The brand mark ("Visor Hutch") is the parent emblem of this 2D family—never assign the brand mark itself as an individual bot's avatar.
2. **Marketing Tier (3D Rendered Mascot):** The Blender Cycles 3D character (`website/assets/hutch-agent.webp` and the 21-frame grid `website/assets/agent/f{0-6}-p{0-2}.webp`, generated by `scripts/render_hutch_agent.py`) is decorative marketing art only (`docs/brand-assets.md:74-76`). Never use the 3D render as an app icon, favicon, or operator UI chrome, and do not expand its use outside the marketing site until copyright/licence terms (`C27`) are recorded (`DECISION.md` D25).

---

## 7. Motion & Interaction (`website/tokens.json:151-160`)

- **Durations:** `fast` (`120ms` micro-hover/focus), `base` (`200ms` panel/drawer transitions), `slow` (`360ms` page reveals), `ambient` (`600ms`).
- **Easings:** `out` (`cubic-bezier(0.16, 1, 0.3, 1)`), `in-out` (`cubic-bezier(0.65, 0, 0.35, 1)`), `reveal-shift` (`20px`).
- **Reduced Motion (Hard Requirement):** Every animation, sprite look-at-cursor handler (`website/site.js`), and transition must respect `@media (prefers-reduced-motion: reduce)` by disabling spatial shifts and collapsing durations to instant state changes.
- **No Intro Overlays:** The retired `2.05s` intro overlay (`tokens.json:175`) must never be reintroduced.

---

## 8. Surface Applications

| Surface | Asset(s) to Apply | Size & Placement Rules |
|---|---|---|
| **Browser Favicon (`<head>`)** | `favicon.svg` (primary) + `favicon-32x32.png` + `favicon.ico` | `<link rel="icon" href="/favicon.svg" type="image/svg+xml">` + `<link rel="icon" href="/favicon.ico" sizes="48x48">` |
| **Apple iOS Home Screen** | `apple-touch-icon.png` (`180x180`) | Opaque `#09090b` background; `<link rel="apple-touch-icon" href="/apple-touch-icon.png">` |
| **PWA Web App Manifest** | `site.webmanifest` + `icon-192.png`, `icon-512.png`, `icon-192-maskable.png`, `icon-512-maskable.png`, `icon-192-monochrome.png`, `icon-512-monochrome.png` | Keep `any`, `maskable`, and `monochrome` as separate icon objects in `site.webmanifest`; `theme_color` and `background_color` = `#09090b` |
| **Marketing Header & Footer** | Inline `hutch-mark-master.svg` (`26px` header, `22px` footer/drawer) + `hutch.` in Bricolage Grotesque 800 | Mark fill `var(--color-semantic-brand)` (`#34d399`); wordmark `#ededf0` with `#34d399` period |
| **Studio SPA & Server Pages** | Inline `hutch-mark-small.svg` (`22px`) or `hutch-mark-master.svg` (`24px`) + `hutch` (no period) | Quiet header lockup; page `<title>` uses `<View> — Hutch` (reconciling the `"hutch - hutch"` title drift noted in `APP-BRAND-AUDIT.md`) |
| **Desktop Host (`desktop/icons/`)** | `icon-512.png` / `hutch-mark-master.svg` on `#09090b` `rx="7"` plate | Reconciles the undocumented `#28cd9d` / `#0f151e` hexagon drift (`ASSET-INVENTORY.md` U07) during the desktop integration slice |
| **Open Graph & Twitter/X Card** | `og-card-1200x630.png` (`1200x630`) | Include `og:image:width="1200"`, `og:image:height="630"`, and descriptive `og:image:alt` (`RESEARCH.md` row 3) |
| **GitHub Social Preview** | `github-social-preview-1280x640.png` (`1280x640`) | Upload manually in GitHub repository `Settings > General > Social preview` |

---

## 9. Accessibility

1. **Contrast Floor:** Normal text `>= 4.5:1` (WCAG 2.2 AA); large text (`>= 18pt` / `24px` or bold `>= 14pt` / `18.66px`) and meaningful non-text UI components/icons `>= 3.0:1`. All primary dark-surface brand pairs exceed `7.0:1` (`10.35:1` brand, `17.03:1` text).
2. **Focus Visibility:** Interactive elements use a `2px` solid focus ring (`#60a5fa` `blue-400` on dark at `7.83:1`; `#1d4ed8` `blue-700` on light at `5.74:1`) with a `2px` offset.
3. **Forced-Colors & High-Contrast Mode:** Inline marks use `fill="currentColor"` (`hutch-mark-currentcolor.svg`) or explicit SVG paths so Windows High Contrast / `forced-colors: active` preserves the `evenodd` silhouette and eyes without disappearing.
4. **Target Size:** Interactive controls including the header brand home link maintain a minimum hit target of `44x44px` (`size.target` in `website/tokens.json:139`).

---

## 10. Governance & Quality Gates

- **Single Token Source (`DECISION.md` D12):** `website/tokens.json` governs all colour, spacing, radius, typography, and motion tokens. Run `uv run --frozen --no-sync python scripts/build_site_tokens.py --check` before any commit touching styles or tokens.
- **Risk-Tier Separation (`STRATEGY.md` Section 5):**
  - *Low-risk tier (mark/wordmark/asset swap):* Replacing the inline hexagon with the "Visor Hutch" mark, adding `bricolage-grotesque-latin-800.woff2`, and shipping icons/social cards.
  - *High-risk tier (navigation/hierarchy/reskin):* Must never be bundled into an identity asset commit; requires feature flags, rollback drills, and pre-registered first-click/first-run verification (`DECISION.md` D17).
- **Visual Quality Bar (`PRODUCT.md:102-106`):** Every user-facing change must meet aesthetic `>= 90` and functionality `>= 95` judged on opened desktop and phone screenshots, plus `npm run check:agent`.

---

## 11. Legal, Attribution & Third-Party Marks

### 11.1 Open Font License (OFL 1.1) Attribution
When redistributing font subsets in `website/assets/fonts/` or `src/hutch/server/static/fonts/`, both licence files (`OFL-geist.txt` and `OFL-bricolage-grotesque.txt`) must travel beside the `.woff2` files, and `website/THIRD_PARTY_NOTICES.txt` must list both families (closing gap `NTC-01` in `PROVENANCE-REGISTER.md`):
- **Bricolage Grotesque:** Copyright 2022 The Bricolage Grotesque Project Authors (`https://github.com/ateliertriay/bricolage`), licensed under the SIL Open Font License, Version 1.1 (`OFL-bricolage-grotesque.txt`). No Reserved Font Name declared.
- **Geist & Geist Mono:** Copyright 2023 Vercel, in collaboration with basement.studio, licensed under the SIL Open Font License, Version 1.1 (`OFL-geist.txt`). No Reserved Font Name declared.

### 11.2 Code Licence vs. Brand Posture (`RESEARCH.md` rows 13, 15, 7a)
Following the standard open-source separation model (Python PSF, Go, Rust Foundation), the MIT licence covering Hutch's source code does not grant a licence to use the Hutch name, wordmark, or "Visor Hutch" mark to endorse third-party forks or commercial services, nor does it assert trademark registration.

### 11.3 Third-Party Service Marks (`docs/brand-assets.md:10-33`)
Third-party connector marks (`OpenAI`, `Anthropic`, `OpenRouter`, `Gmail`, `Google Calendar`, `Google Drive`, `Google Docs`, `Google Sheets`, `Microsoft Outlook`, `Microsoft Sign-In`, `Notion`) are used solely for functional account/model identification beside the visible vendor name, bundled locally unchanged, and never altered, recoloured, or used in Hutch marketing cards.

### 11.4 Pre-Screen Non-Clearance Statement (`DECISION.md` D20/D23/D28/D38, B6, B10)
The name "Hutch" has a confirmed UK Nice class 9/42 registration overlap (`UK00003791602`, `UK00902129492`) and unresolved US/EU/CA register checks (`IP-CLEARANCE.md`); the maintainer retained the name under written risk ownership (`D38`). The "Visor Hutch" mark has been web-screened (`IP-CLEARANCE.md` Section 13), not figurative-register searched. **Nothing in this document or repository is cleared, and nothing is legal advice; counsel/owner decision is required before any commercial filing or warranty.**

---

## 12. Assets & Downloads Manifest

All production and press-kit files are generated deterministically by `.pipeline/brand/2026-10/assets/build_production_package.py` and indexed with full SHA-256 hashes in `.pipeline/brand/2026-10/assets/production/PACKAGE-MANIFEST.json`:

| Category | Directory | Key Files |
|---|---|---|
| **Master & Variant Mark SVGs** | `assets/production/svg/` | `hutch-mark-master.svg`, `hutch-mark-small.svg`, `hutch-mark-light.svg`, `hutch-mark-mono-dark.svg`, `hutch-mark-mono-light.svg`, `hutch-mark-currentcolor.svg` |
| **Outlined Wordmarks & Lockups** | `assets/production/lockups/` | `hutch-wordmark-{dark,light,mono-dark,mono-light}.svg` + `@2x.png`; `hutch-lockup-{dark,light,mono-dark,mono-light}.svg` + `@2x.png` |
| **Platform Icons & Manifest** | `assets/production/icons/` & `assets/production/` | `favicon.svg`, `favicon.ico`, `favicon-{16x16,32x32,48x48}.png`, `favicon-{16x16,32x32}-{dark,light}.png`, `apple-touch-icon.png` (`180x180`), `icon-{192,512}.png`, `icon-{192,512}-maskable.png`, `icon-{192,512}-monochrome.png`, `icon-monochrome.svg`, `site.webmanifest` |
| **Social Preview Cards** | `assets/production/social/` | `og-card-1200x630.png` (`1200x630`), `github-social-preview-1280x640.png` (`1280x640`) |
| **Production Wordmark Fonts** | `assets/production/fonts/` | `bricolage-grotesque-latin-800.woff2`, `bricolage-grotesque-latin-var.woff2`, `OFL-bricolage-grotesque.txt` |
| **Standalone Press Kit** | `assets/press-kit/` | `README.md`, `svg/` (14 SVGs), `png/` (14 high-res PNGs), `fonts/` (2 WOFF2 + OFL text) |
| **Validation Evidence** | `assets/production/` | `validation-sheet.png`, `PACKAGE-MANIFEST.json` |

---

## 13. Changelog

| Date | Run | Summary of Changes |
|---|---|---|
| `2026-10-28` | Runs 1–4 | Audited product/site surfaces (`APP-BRAND-AUDIT.md`, `ASSET-INVENTORY.md`), verified sources (`RESEARCH.md`), established strategy (`STRATEGY.md`), executed free-check & UKIPO trademark pre-screen (`IP-CLEARANCE.md`, `PROVENANCE-REGISTER.md`). |
| `2026-10-29` | Run 5 | Maintainer retained name "Hutch" under written risk ownership (`D38`), selected **Bricolage Grotesque 800** wordmark (`D42`), established measured colour system (`COLOUR-SYSTEM.md`) and design rulebook (`PRINCIPLES.md`), and archived Rounds 1–12 mark concepts as non-candidates (`D51/D52`). |
| `2026-10-29` | Run 6 | Designed two clean-sheet mark directions synthesizing Grokbot, the Pac-Man ghost archetype, and the hutch shelter (`MARK-DIRECTIONS-RUN6.md`, `D53`); maintainer selected **Direction B ("Visor Hutch")** (`D54`); produced full platform icon package, outlined wordmark/lockups, Bricolage Grotesque 800 WOFF2 subset + OFL text, social cards, validation matrix (`VALIDATION-MATRIX.md`), press kit, and these brand guidelines (`BRAND-GUIDELINES.md`). |

