# VALIDATION-MATRIX.md — Surface, Theme, Zoom, CVD & Print Validation (Run 6 — 2026-10-29)

Date: 2026-10-29 (America/Vancouver)
Run: 6 (Task B — validation of the human-picked mark Direction B "Visor Hutch" and Bricolage Grotesque 800 wordmark)
Composite visual evidence: `.pipeline/brand/2026-10/assets/production/validation-sheet.png` (`370,437 B`, sha256 `0aa61eec9b2de1b5...`)
Generator script: `.pipeline/brand/2026-10/assets/build_production_package.py`
Legal boundary: Technical and visual validation only. Nothing in this file is a trademark clearance, registrability or non-infringement conclusion (`IP-CLEARANCE.md`, `DECISION.md` D38/D54).

---

## 1. Execution-Time Platform Specification Re-Verification (2026-10-29)

Per Task B instructions, platform icon and social-card numbers were re-verified at execution time on `2026-10-29` using headless Chromium (`Playwright Chromium 153.0.8010.12`) so client-rendered documentation pages that returned shell-only bodies in Run 1 (`RESEARCH.md`) were read from their rendered DOM:

| Platform / Spec | Source URL (Accessed 2026-10-29) | HTTP / Render Status | Specification Read From Source (2026-10-29) | Package Deliverable & Compliance |
|---|---|---|---|---|
| Google Search Favicon | `https://developers.google.com/search/docs/appearance/favicon-in-search` | HTTP 200 (DOM rendered) | Square (`1:1`), minimum `8x8px`, recommends `> 48x48px` (or SVG) at a stable crawlable URL | `favicon.svg` (scalable), `favicon.ico` (`16/32/48` embedded), `favicon-48x48.png` (`48x48`), `favicon-32x32.png`, `favicon-16x16.png` |
| W3C / Chrome Maskable PWA Icons | `https://web.dev/articles/maskable-icon` and `https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/How_to/Define_app_icons` | HTTP 200 (DOM rendered) | Opaque full-bleed background required; minimum safe zone is a centered circle of radius `40%` of icon width (`80%` diameter); declare `"purpose": "maskable"` separately from `"any"` | `icon-192-maskable.png` (`192x192` RGB), `icon-512-maskable.png` (`512x512` RGB); mark scaled to `72%` (`23.04u` inside `25.60u` safe circle); `site.webmanifest` separates `any`, `maskable`, `monochrome` |
| Apple iOS Home Screen Icon | `https://developer.apple.com/design/human-interface-guidelines/app-icons` (plus MDN PWA icon reference) | HTTP 200 | `180x180px` PNG (`apple-touch-icon.png`), opaque background (no alpha transparency; system applies rounded-rect mask) | `apple-touch-icon.png` (`180x180`, opaque `#09090b` background, `3,978 B`, sha256 `2351b1e0a2136a98...`) |
| Open Graph Protocol (`og:image`) | `https://ogp.me/` | HTTP 200 (full body) | `og:image` required; `og:image:width`, `og:image:height`, `og:image:alt` recommended; `1200x630` (`1.91:1`) is the cross-platform high-DPI convention | `og-card-1200x630.png` (`1200x630`, `46,515 B`, sha256 `2cf67f59cfd46a79...`) |
| GitHub Repository Social Preview | `https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/customizing-your-repositorys-social-media-preview` | HTTP 200 (DOM rendered) | PNG/JPG/GIF `< 1 MB`; at least `640x320px`, recommends `1280x640px` (`2:1`) for best display | `github-social-preview-1280x640.png` (`1280x640`, `47,004 B` = `0.045 MB`, sha256 `5289a49e1c2cfe49...`) |

---

## 2. Visual Inspection Ledger (Every Rendered Image Opened & Inspected)

Every generated PNG asset and composite sheet was opened and inspected visually in session on `2026-10-29`. During initial inspection of `validation-sheet.png`, one CSS defect was caught in Box 4 (an unqualified `.cvd-box span` selector caused the emerald period `<span style="color:#34d399">.</span>` inside `.wm-sm` to wrap to a new line); the selector was tightened to `.cvd-box > span`, the sheet was regenerated, and re-inspection confirmed inline alignment.

| Asset Path (under `.pipeline/brand/2026-10/assets/`) | Dimensions | Bytes | SHA-256 Prefix | Visual Inspection Verdict (2026-10-29) |
|---|---|---|---|---|
| `concepts/sheets/run6-direction-a-construction.png` | `2760x1720` (`@2x`) | `272,718` | `6f41a28c5c701164` | Pass: 32x32 grid, 4u modules, blue 24x24 metric box, overshoots, and parameter table crisp and legible. |
| `concepts/sheets/run6-direction-b-construction.png` | `2760x1720` (`@2x`) | `282,115` | `c852e7e576db5863` | Pass: Master (`>=32px`) and Small (`16–24px`) redrawn tiers clearly show the nested visor moat and 3-post/2-burrow skirt. |
| `concepts/sheets/run6-test-matrix.png` | `2840x1560` (`@2x`) | `303,952` | `8c187630d0594d72` | Pass: All 6 test cells and 4 lockup colourways rendered cleanly for both Direction A and Direction B. |
| `production/validation-sheet.png` | `2880x1800` (`@2x`) | `370,437` | `0aa61eec9b2de1b5` | Pass (after `.cvd-box > span` fix): All 7 validation panels (headers, 16px tabs + 4x pixel zoom + 200% zoom, iOS/maskable crops, 4 CVD filters, light print proxy, OG card, GitHub card) verified clean. |
| `production/icons/favicon-16x16.png` | `16x16` | `636` | `ccfda3afafaeade4` | Pass: Redrawn Small tier on `#09090b` rounded tile; visor recess, twin positive eyes, and 3 feet / 2 burrow arches remain distinct at 16x16px. |
| `production/icons/favicon-16x16-dark.png` | `16x16` | `589` | `9c953bfd317aa0de` | Pass: Transparent `#34d399` Small tier for dark browser tabs; `>= 1.42px` counterform moat prevents eye plugging. |
| `production/icons/favicon-16x16-light.png` | `16x16` | `528` | `cd2051a37e927367` | Pass: Transparent `#09090b` Small tier for light browser tabs (`17.03:1` on paper). |
| `production/icons/favicon-32x32.png` | `32x32` | `1,124` | `2d2d3d2cef7dedcd` | Pass: Master tier on `#09090b` tile; inward `-8° / +8°` eye tilt and burrow arches crisp. |
| `production/icons/favicon-48x48.png` | `48x48` | `1,723` | `83cb4000a437cd7b` | Pass: Meets Google Search `>= 48x48px` recommendation. |
| `production/icons/apple-touch-icon.png` | `180x180` | `3,978` | `2351b1e0a2136a98` | Pass: Full-bleed opaque `#09090b` field, centered `#34d399` mark at `78%` scale, zero alpha channel. |
| `production/icons/icon-192.png` & `icon-512.png` | `192x192` / `512x512` | `6,408` / `18,232` | `b15885c5e60bd3d5` / `ce3da0b9be7a4ee6` | Pass: Smooth bezier curves on dome, visor, tilted oval eyes, and tangent-continuous 3-post base. |
| `production/icons/icon-192-maskable.png` & `icon-512-maskable.png` | `192x192` / `512x512` | `4,337` / `11,880` | `16750592cf77937a` / `2b5735d77d1acd6c` | Pass: Full-bleed opaque `#09090b`; mark scaled to `72%` (`4.48u` margin on `32u` canvas > `3.20u` W3C `10%` crop zone); survives circle, squircle, and teardrop masks with generous breathing room. |
| `production/icons/icon-192-monochrome.png` & `icon-512-monochrome.png` | `192x192` / `512x512` | `4,250` / `12,581` | `c9e8e5d1d52a534e` / `1aba42a1e71cf8c2` | Pass: Pure white `#ffffff` silhouette on alpha; `evenodd` visor hole and positive eyes preserve full facial and structural recognition in 1-channel tinting. |
| `production/lockups/hutch-lockup-dark@2x.png` | `696x192` | `15,288` | `acfdaa172926a615` | Pass: Outlined Bricolage Grotesque 800 `hutch.` in `#ededf0` with `#34d399` mark and period; baseline of `hutch` aligns optically with the outer feet of the mark. |
| `production/lockups/hutch-lockup-light@2x.png` | `696x192` | `14,673` | `48e43d8da5914ab2` | Pass: `#09090b` wordmark (`17.03:1`) + `#047857` `emerald-700` mark and period (`4.69:1` AA pass on paper). |
| `production/lockups/hutch-wordmark-dark@2x.png` | `512x192` | `10,587` | `9d6b364c28b444e0` | Pass: Pure path-outlined Bricolage Grotesque 800 wordmark; characteristic ink traps on `h`/`u` and angled `t` terminal sharp. |
| `production/social/og-card-1200x630.png` | `1200x630` | `46,515` | `2cf67f59cfd46a79` | Pass: Exact `1200x630` dimensions; approved tagline, local-first subcopy, and `Development preview` badge; contrast `17.03:1` (paper on ink) and `10.35:1` (emerald-400 on ink). |
| `production/social/github-social-preview-1280x640.png` | `1280x640` | `47,004` | `5289a49e1c2cfe49` | Pass: Exact `1280x640` dimensions (`47 KB << 1 MB` limit); `>= 64px` outer safety frame prevents GitHub mobile/feed edge clipping. |

---

## 3. Surface, Theme, Zoom, CVD & Print Matrix Summary

| Validation Dimension | Method | Result | Evidence Panel in `validation-sheet.png` |
|---|---|---|---|
| **Dark theme (`#09090b` ink-950)** | WCAG 2.x relative luminance + visual render | **PASS.** Mark & period `#34d399` = `10.35:1`; wordmark `#ededf0` = `17.03:1`; secondary copy `#a3a3ae` = `7.97:1`; muted metadata `#8e8e99` = `6.14:1`. | Panels 1, 2, 6, 7 |
| **Light theme (`#ededf0` paper / `#ffffff` white)** | WCAG 2.x relative luminance + visual render | **PASS.** Uses `emerald-700` (`#047857`, `4.69:1` on paper, `5.48:1` on `#ffffff`) and `ink-950` (`#09090b`, `17.03:1` on paper). `emerald-400` (`1.65:1` on paper) is prohibited on light surfaces. | Panels 1, 2, 5 |
| **16px Favicon & 200% Zoom** | Separate redrawn Small tier (`mark_small_d`) + 4x nearest-neighbour pixel inspection + 200% lockup render | **PASS.** Visor moat widened to `2.85u` vertical / `3.65u` horizontal in Small tier; eyes remain separated from visor walls at `16x16px` (`1x` and `DPR2`). | Panel 2 |
| **OS Maskable Crops** | Circle (`50%` radius), Squircle (`28%`), Teardrop (`50% 50% 14% 50%`), iOS (`180x180`) | **PASS.** Mark occupies central `72%` (`23.04u` of `32u`), inside the `80%` (`25.60u`) W3C safe circle with `1.28u` (`4%`) extra buffer inside the safe boundary. | Panel 3 |
| **Colour Vision Deficiency (CVD)** | SVG `feColorMatrix` linear approximations for Protanopia, Deuteranopia, Tritanopia, Achromatopsia | **PASS.** Under all four deficiencies (including full monochrome Achromatopsia), the nested `shell -> visor -> eyes` silhouette and the wordmark period remain unmistakable; colour is never the sole carrier of identity or state. | Panel 4 |
| **Print & Grayscale Proxy** | `emerald-700` (`#047857`), `emerald-800` (`#065f46`), and `ink-950` (`#09090b`) on white | **PASS.** Single-path `evenodd` vector artwork prints cleanly in 1-colour black or deep green without halftoning artifacts from gradients or alpha blends. | Panel 5 |

---

## 4. Honest Limitations Recorded

1. **Pipeline-only state (D42):** All assets are validated inside `.pipeline/brand/2026-10/assets/production/` and `assets/press-kit/`. They have **not** been wired into `website/`, `src/hutch/server/`, `docs/`, or `desktop/icons/`, which still carry the legacy inline hexagon until a separate dated integration authorisation is given (Run 7).
2. **CVD simulation is mathematical, not clinical:** The Protanopia, Deuteranopia, Tritanopia, and Achromatopsia panels use standard 3x3 sRGB colour-matrix approximations (`COLOUR-SYSTEM.md` section 5), not human observer trials.
3. **Print proxy is screen-rendered sRGB, not a physical press proof:** Under the zero-external-spend constraint (`DECISION.md` D15), no physical CMYK offset or digital press proof was printed; CMYK values in `COLOUR-SYSTEM.md` and `BRAND-GUIDELINES.md` are conversions for briefing only.
4. **APCA (WCAG 3 working draft) not computed:** Contrast verification uses the normative WCAG 2.2 AA relative-luminance formula required by the repository's existing token test suite (`scripts/build_site_tokens.py --check`).
5. **No native macOS `.icns` regeneration in this slice:** Because `desktop/` is outside the authorised write scope (`.pipeline/brand/**` only) and Tauri bundling is currently inactive (`APP-BRAND-AUDIT.md` 5), `.icns` packaging belongs to the later desktop integration slice.
6. **Not legal clearance:** Visual and technical validation establishes legibility, contrast, and format compliance only; trademark and figurative clearance remain unresolved (`IP-CLEARANCE.md`).

