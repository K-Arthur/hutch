# COLOUR-SYSTEM.md - Run 5 colour work (2026-10-29)

Status: evidence + proposal. Nothing here changes product code, tokens.json or the site; this file is
pipeline-only. Not legal advice. Values are computed, not assumed: the contrast table below was
produced by `.pipeline/brand/2026-10/assets/concepts/render_colour.py` on 2026-10-29 using the WCAG
2.x relative-luminance formula on the sRGB values in `website/tokens.json`.

## 0. What this document is

The colour half of the identity, worked to the same evidence bar as the mark:
constraints, measured contrast, findings, the proposed system (dark, light, print, icon/OS), CVD and
non-colour redundancy, and the decisions still owed. It does not render final assets and does not
touch the product.

## 1. Constraints

- `website/tokens.json` is the governing token source (DECISION.md D12). Any brand palette must map
  onto it; new values are proposals, not tokens.
- The product is dark-first (ink-950 background, paper text). Light surfaces exist only as
  docs/print/press/social and as future light mode (not shipped).
- Zero external spend (D15): no spot colours, no Pantone licence, no paid font or asset services.
- Accessibility bar: WCAG 2.2 AA - text 4.5:1, large text and non-text UI 3:1
  (https://w3c.github.io/wcag/understanding/contrast-minimum.html [snippet-title],
  https://w3c.github.io/wcag21/understanding/21/user-interface-component-contrast-minimum.html
  [snippet-title]). WCAG 2.x is used because the repo's existing gates are WCAG-shaped; APCA is not
  computed here (listed as a limitation).

## 2. Measured contrast (2026-10-29, sRGB, WCAG 2.x formula)

| Pair | Ratio | Verdict |
|---|---|---|
| paper #ededf0 on ink-950 #09090b | 17.03:1 | AA text pass |
| paper on ink-900 #0f0f12 | 16.38:1 | AA text pass |
| mist #a3a3ae on ink-950 | 7.97:1 | AA text pass |
| faint #8e8e99 on ink-950 | 6.14:1 | AA text pass |
| faint on panel-800 #16161a | 5.57:1 | AA text pass |
| **emerald-400 #34d399 on ink-950** | **10.35:1** | AA text pass (brand signal on dark) |
| emerald-300 #6ee7b7 on ink-950 | 13.05:1 | AA text pass |
| emerald-600 #10b981 on ink-950 | 7.84:1 | AA text pass |
| **emerald-400 on paper** | **1.65:1** | FAIL - not usable on light |
| **emerald-600 on paper** | **2.17:1** | FAIL - not usable on light |
| emerald-700 #047857 (proposed) on paper | 4.69:1 | AA text pass |
| emerald-800 #065f46 (proposed) on paper | 6.58:1 | AA text pass (print/deep) |
| emerald-ink #052e21 on emerald-400 | 7.70:1 | AA text pass (on-brand) |
| emerald-ink on emerald-600 | 5.83:1 | AA text pass |
| paper on emerald-600 | 2.17:1 | FAIL (do not set paper on emerald-600) |
| info blue-400 #60a5fa on ink-950 | 7.83:1 | AA text pass |
| warning amber-400 #fbbf24 on ink-950 | 11.92:1 | AA text pass |
| danger red-400 #f87171 on ink-950 | 7.19:1 | AA text pass |
| danger red-400 on paper | 2.37:1 | FAIL on light |
| info blue-400 on paper | 2.18:1 | FAIL on light |
| warning amber-400 on paper | 1.43:1 | FAIL on light |
| red-700 #b91c1c (proposed) on paper | 5.54:1 | AA text pass |
| amber-800 #92400e (proposed) on paper | 6.07:1 | AA text pass |
| blue-700 #1d4ed8 (proposed) on paper | 5.74:1 | AA text pass |
| border white.a07 on ink-950 | 1.14:1 | decorative only (token marks it decorative) |
| border white.a14 on ink-950 | 1.41:1 | decorative only |
| border white.a38 on ink-950 | 3.47:1 | non-text pass (use for boundaries that carry meaning) |

## 3. Findings

- **F1 (blocking for light surfaces).** The brand emerald (emerald-400) is a dark-surface colour.
  On paper it measures 1.65:1 and even emerald-600 only reaches 2.17:1. Docs, press sheets, print and
  any future light mode need a light-surface brand (emerald-700 4.69:1, emerald-800 6.58:1).
- **F2 (token collision).** `semantic.brand` and `semantic.success` resolve to the SAME value
  (emerald-400). A brand-green product cannot use green as both "this is Hutch" and "this worked".
  Mitigation: success states must always carry a non-colour cue (check icon plus text); a product
  decision is owed on whether success moves to a distinct token.
- **F3 (deck-wide).** Semantic warning/info/danger are tuned for the dark surface and fail AA on
  paper (1.43 / 2.18 / 2.37). Light documents need darker variants (amber-800, blue-700, red-700).
- **F4 (borders).** The hairline border tokens are decorative by definition and fail 3:1, which is
  acceptable only because they are marked decorative; any border that carries meaning must use
  `border-edge` (3.47:1) or a solid value.
- **F5 (focus).** `focus-ring` (blue-400) passes on ink (7.83:1) and fails on paper (2.18:1); a light
  surface needs blue-700 (5.74:1).
- **F6 (CVD).** Under simulated protanopia/deuteranopia the brand emerald desaturates toward
  grey-violet and warning amber and danger red converge toward yellow-olive (see the simulation sheet).
  Colour alone can never carry state: icon plus label required, and charts need shape/dash redundancy.
- **F7 (print).** emerald-400 is outside typical CMYK gamut; print artwork should use emerald-700/800.
  No spot colour (zero spend, D15); CMYK values below are approximations pending a proof.

## 4. Proposed system

Dark surface (product, site, social, icons on ink):
- Signal: emerald-400 for the mark, the wordmark period, links, primary action emphasis.
- Text: paper; secondary mist; tertiary faint; never below faint for text.
- Surfaces: ink-950 bg, ink-900 surface, ink-800 panel, ink-750 raised, ink-well/ink-sunken for wells.
- On-brand text: emerald-ink.
- Semantics: info blue-400, warning amber-400, danger red-400, always with icon+label.
- Focus: blue-400 on ink; 2px ring, 2px offset.

Light surface (docs, press, print, future light mode):
- Signal: emerald-700 (#047857) for graphics and text-sized accents; emerald-800 (#065f46) for deep
  print fills; white paper text on emerald-700 measures 4.69:1 (AA for normal text) - verify per use.
- Text: ink-950 on paper (17.03:1); mist/faint do not transfer - light text tiers must be re-derived
  (owed; candidates ink-700/ink-600 families are product decisions).
- Semantics: info blue-700, warning amber-800, danger red-700.
- Borders: ink at 10-15% alpha (light equivalent, to be measured before use).

Icon/OS surfaces:
- PWA theme_color and maskable background: ink-950.
- Monochrome icons: currentColor; maskable safe zone per W3C/web.dev (see RESEARCH).
- Favicon: single colour, emerald-400 on dark and ink-950 on light by `prefers-color-scheme`; never
  rely on the emerald on light (F1).

Mark colourways (single-colour mark; the doorway and dot are background/counterform):
| Surface | Mark | Background |
|---|---|---|
| Product/site dark | emerald-400 or paper | ink-950 |
| Light documents | ink-950 | paper |
| Print | emerald-700/800 or black | paper |
| Reversed/mono | paper | ink-950 |
| Brand block | emerald-ink | emerald-400 (7.70:1) |

Print CMYK approximations (approximate; proof print owed, no spot colour):
- emerald-700 #047857 -> C 85 M 25 Y 65 K 15 (approx)
- emerald-800 #065f46 -> C 88 M 35 Y 70 K 25 (approx)
- ink-950 #09090b -> rich black C 60 M 40 Y 40 K 100 (approx; confirm with printer)
These are conversions for briefing only and are not measured output.

## 5. What is not decided

1. Keep emerald-400 as the dark-surface brand signal, or consider a hue change for differentiation
   (hue change is a product-wide change; the equity argument and F1/F2 are the evidence to weigh).
2. Whether `success` moves off the brand value (F2) - product decision, not brand-only.
3. Light-mode product surfaces do not exist; the light ramp is a proposal for docs/press/print only.
4. APCA not computed; CVD matrices are approximations; no printer proof.
5. Nothing here is clearance or legal advice; colour-level trademark similarity was not screened.

## 6. Evidence

- `assets/concepts/sheets/colour-sheet.png` - palette, CVD simulation, mark colourways.
- `assets/concepts/render_colour.py` - deterministic contrast calculations and the sheet.
- Contrast formula: WCAG 2.x relative luminance; sRGB channel linearisation.
