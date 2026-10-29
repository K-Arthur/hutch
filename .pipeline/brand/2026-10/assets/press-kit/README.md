# Hutch Press & Brand Kit (Run 6 — 2026-10-29)

Status: **Pipeline-only brand and press package** (`.pipeline/brand/2026-10/assets/press-kit/`).
Selected identity:
- **Name:** Hutch ("Your bots. Your machine. Your rules.") — retained by maintainer decision (`DECISION.md` D38).
- **Mark:** "Visor Hutch" (Direction B, selected 2026-10-29, `DECISION.md` D54) — hooded ghost-hutch shelter with a recessed upper loft visor, twin inward-tilted (`-8° / +8°`) bot eyes, and a 3-post / 2-burrow scalloped base.
- **Wordmark:** Lowercase `hutch.` set in **Bricolage Grotesque** weight `800` (`-0.03em` tracking) with an emerald period (`DECISION.md` D42). Outlined `<path>` SVGs require no installed fonts.

## 1. Directory Contents

### `svg/` — Vector Masters & Outlined Lockups
All SVG files use `fill-rule="evenodd"` single-path or pure `<path>` outlines (zero stroke or external font dependency):
- `hutch-mark-master.svg` — Primary mark (`>= 32px` tier), `emerald-400` (`#34d399`) for dark surfaces (`10.35:1` on `ink-950`).
- `hutch-mark-small.svg` — Redrawn small-size master (`16–24px` tier) with widened counterforms (`>= 2.85u` on `32x32` grid).
- `hutch-mark-light.svg` — Light-surface mark in `emerald-700` (`#047857`, `4.69:1` on `paper`). Never use `#34d399` on light backgrounds (`1.65:1` fail).
- `hutch-mark-mono-dark.svg` — Monochrome mark in `paper` (`#ededf0`, `17.03:1` on `ink-950`).
- `hutch-mark-mono-light.svg` — Monochrome mark in `ink-950` (`#09090b`, `17.03:1` on `paper`).
- `hutch-mark-currentcolor.svg` — Inline UI mark with `fill="currentColor"`.
- `hutch-wordmark-dark.svg` — Outlined `hutch.` wordmark (`#ededf0` text + `#34d399` period).
- `hutch-wordmark-light.svg` — Outlined `hutch.` wordmark (`#09090b` text + `#047857` period).
- `hutch-wordmark-mono-dark.svg` / `hutch-wordmark-mono-light.svg` — Single-colour outlined wordmarks.
- `hutch-lockup-dark.svg` — Outlined horizontal lockup (`Visor Hutch` mark + `hutch.`) for dark surfaces.
- `hutch-lockup-light.svg` — Outlined horizontal lockup for light/print surfaces (`#047857` + `#09090b`).
- `hutch-lockup-mono-dark.svg` / `hutch-lockup-mono-light.svg` — Single-colour outlined horizontal lockups.

### `png/` — High-Resolution (`@2x` & `512px`) Rasters & Social Cards
- `hutch-icon-512.png` — `512x512` app icon (`#34d399` mark on `#09090b` rounded square).
- `hutch-mark-emerald-512.png`, `hutch-mark-mono-dark-512.png`, `hutch-mark-mono-light-512.png` — Transparent `512x512` mark rasters.
- `hutch-lockup-dark@2x.png`, `hutch-lockup-light@2x.png`, `hutch-lockup-mono-dark@2x.png`, `hutch-lockup-mono-light@2x.png` — `696x192` (`4x` nominal `48px` height) transparent lockup PNGs.
- `hutch-wordmark-dark@2x.png`, `hutch-wordmark-light@2x.png`, `hutch-wordmark-mono-dark@2x.png`, `hutch-wordmark-mono-light@2x.png` — `512x192` transparent wordmark PNGs.
- `og-card-1200x630.png` — Open Graph social card (`1200x630`).
- `github-social-preview-1280x640.png` — GitHub repository social preview (`1280x640`).

### `fonts/` — Production Wordmark Font Subsets & Licence
- `bricolage-grotesque-latin-800.woff2` — Static weight-800 Latin WOFF2 subset (`47,260 B`).
- `bricolage-grotesque-latin-var.woff2` — Variable Latin WOFF2 subset (`238,808 B`).
- `OFL-bricolage-grotesque.txt` — SIL Open Font License 1.1 text ("Copyright 2022 The Bricolage Grotesque Project Authors (https://github.com/ateliertriay/bricolage)"). Must travel with any redistribution of the font files.

## 2. Usage & Legal Notice

- Use provided files unmodified. Do not stretch, rotate, add drop shadows, apply gradients, or place `emerald-400` (`#34d399`) on light backgrounds.
- Clear space around the mark or lockup must be at least `25%` of the mark's height (`8u` on the `32u` grid) on all sides.
- Minimum sizes: `16px` for `hutch-mark-small.svg`; `32px` for `hutch-mark-master.svg`; `22px` mark height (`18px` wordmark height) for horizontal lockups.
- **No trademark grant or clearance claim:** Hutch source code is MIT-licensed; brand marks and identity assets are documented separately. Nothing in this kit represents a legal opinion, trademark registration, or clearance conclusion (`IP-CLEARANCE.md`, `DECISION.md` D20/D23/D28/D38).

