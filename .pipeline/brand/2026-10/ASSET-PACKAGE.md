# ASSET-PACKAGE.md - candidate "Canopy" front (pipeline-only)

Status: **candidate, not adopted**. Built under the D42 authorisation (full package, pipeline-only);
the human's pick from D49/round 12 is still pending. Nothing here is referenced by the website, docs,
dashboard or desktop app. Not legal advice; no clearance implied.

## Files (assets/front-candidate/)

| File | Size | Use |
|---|---|---|
| hutch-mark-master.svg | 32-grid vector | master mark, all outputs >=32px |
| hutch-mark-small.svg | 32-grid vector | small master for 16-24px (redrawn, not scaled) |
| favicon.svg | 32-grid vector | favicon with prefers-color-scheme ink/paper switch |
| favicon-16.png / favicon-16-dark.png | 16x16 | tab icon, light / dark scheme |
| favicon-32.png / favicon-32-dark.png | 32x32 | tab icon, 2x |
| apple-touch-icon-180.png | 180x180 | iOS home screen (system masks corners) |
| icon-192.png / icon-512.png | 192, 512 | PWA purpose any |
| icon-512-maskable.png | 512 | PWA purpose maskable, mark at 72% for the r40% safe zone |
| icon-512-monochrome.png | 512 | PWA purpose monochrome, transparent, tintable |
| og-card-1200x630.png | 1200x630 | Open Graph / X card |
| github-social-preview-1280x640.png | 1280x640 | repo social preview (manual upload, owner step) |
| lockup-dark.png / lockup-light.png | 700x180 @2x | press lockup, emerald mark + Bricolage wordmark |
| build_candidate_pack.py | generator | deterministic regeneration |
| render_validation.py | generator | real-surface validation sheet |

## Construction (the drawing, not a description)

Master (>=32px): cap trapezoid, top edge x8.5-23.5 at y0.6, eaves x4-28 at y3.8; front arch sides
x5.5-26.5, floor y30, crown rx10.5 / ry10.73 (0.23 optical overshoot); windows 6.0 squares r1.3 at
(11.4,16.2) and (20.6,16.2) - 3.2 apart, 2.9 to the arch sides, 10.8 above the floor.
Small (16-24px): cap top x7.5-24.5 at y0, eaves x3-29 at y3.4; front sides x4.5-27.5, floor y30.5,
crown rx11.5/ry11.75; windows 7.0 squares r1.5 at (11.2,16.4)/(20.8,16.4).

Colour (COLOUR-SYSTEM.md): mark is single-colour currentColor; on ink the mark is emerald-400
(10.35:1), on paper ink-950 (17.03:1); light-surface lockup uses emerald-700 (4.69:1) for the mark and
period; monochrome icon is transparent and tintable; PWA/theme background ink-950.

## Validation done (2026-10-29)

- candidate-validation.png: browser tab 16px light+dark (native and x8), 32px x4; home-screen tile
  (60px), apple-touch 180; maskable circle / squircle / full crops; PWA 192 and 512; monochrome;
  OG card; lockups dark/light; greyscale print proxy; GitHub social preview.
- 16px and 32px outputs are produced from the small master only.

## Observed limitations (open)

1. At 16px the cap reads as a 1.6px band and the two windows as two light squares - legible in the x8
   zoom but the cap detail is lost; the mark still silhouettes as "roofed front".
2. Below ~20px the two windows approach each other; the small master opens the gap to 2.6 units
   (1.3px at 16) - measured, not assumed.
3. ICO fallback not built (PNG + SVG cover current targets; ICO owed if legacy support is required).
4. Bricolage is not yet subset or licence-filed for shipping; lockups are 2x PNG only, no outlined
   vector wordmark yet.
5. The similarity screen for this exact drawing is still owed (see IP-CLEARANCE). The cap "hat" read
   is the main aesthetic risk.
6. No light-mode product surface exists; the light lockup is for press/docs only.

## Provenance (to be added to PROVENANCE-REGISTER Appendix C)

Authored 2026-10-29 by the DSH "lead" session; geometry constructed on the 32-unit grid from the
round-12 drawing, no tracing, no stock source. Rasterisation: Playwright Chromium 153.0.8010.12;
deterministic generator checked into this directory. Wordmark: Bricolage Grotesque (OFL 1.1,
google/fonts, instanced at wght 800) - production must self-host a subset plus the licence text.
