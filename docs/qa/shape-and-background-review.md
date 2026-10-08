# QA review — corner radius + background (Oct 2026)

Scope: two reported problems on the authenticated app (the studio SPA and the
server-rendered settings pages):

1. the square-corner geometry "gives the app a weird feel";
2. the page background is "all over the place" because of the gradient effect.

This document is the scorecard for the fix. It separates **aesthetic** from
**functional** scores and gives a **combined** result, with the evidence for each.
It is a project-internal engineering review, not a certification; the "not
verified" list at the end is real.

## What was wrong (measured, not eyeballed)

Computed styles captured with Playwright on the running app before the change:

- **Radii were a mixture of six shape languages**: primary buttons `0px`, nav
  links and inputs `5px`, panels/composer `8px`, status chips `100px`, the send
  button `50%`, avatars hexagons. A `border-radius: 0` blanket rule on *every*
  button sat directly beside circular icon buttons and pill chips.
- **Background mixed two wrong hues.** `html, body` painted an **emerald**
  radial glow (top-left) and a **blue** radial glow (top-right), while the live
  accent is blue (#52a8ff). Panels were translucent `rgba(10,14,21,.78)` +
  `backdrop-filter: blur(10px)` over it, so the mismatch showed through.
- Leftover emerald hardcodes (the user-prompt bubble `rgba(52,211,153,.08)`, the
  active-avatar glow, the first avatar hue) reinforced the "off" feeling.

## The decision

**Rounded, one coherent scale** — not square, and not full-pill everywhere.
Research (bounded, cited in `docs/research/reference-map.md` conventions):

- Material 3 shape scale (`none 0 / xs 4 / sm 8 / md 12 / lg 16 / full`) and its
  caution against large/full radii on information-dense components;
- Atlassian radius tokens (interactive 6, containment 8, page/modals 12, full
  for circular);
- the shape-perception literature: rounded reads as friendly/approachable,
  sharp as precise/formal, and **inconsistency is what reads as poor quality** —
  "problems start when the radius is inconsistent or fights the content".

Applied as one role map in both `style.css` and `hutch.css`:
controls **8**, containers **12**, composer/modal **16**, pills **999**, micro
affordances **4**, circles for avatars/icon-only buttons/dots. Sharp corners stay
only for dense table cells inside a rounded wrapper. Background: **one** faint
centred top wash (`rgba(82,168,255,.045)`), solid panels, no universal blur.

## Automated metrics (Playwright + axe-core 4.10.2, 7 views × 2 widths)

| Metric | Before | After |
|---|---|---|
| Shape coherence (role-invariant radius) | 6.0 | **10.0** |
| Background calm (gradient layers / peak alpha) | 2 layers, mixed hue | **1 layer, α 0.043** → **10.0** |
| Color coherence (accent hues / emerald-as-accent) | emerald hardcodes present | **one blue family, 0 emerald** → **10.0** |
| Accessibility — axe critical/serious nodes | 2 critical + 9 serious | **0** |
| Console errors across views | 0 | **0** |
| Full test suite (`pytest`) | 715 passed | **715 passed** |

## Functional checks (19 automated journey assertions → 19/19)

Routes render a visible `h1`; no body overflow at 390 px on five routes; the
new-bot dialog opens with `role=dialog`, moves focus inside, closes on Escape and
restores focus to the trigger; runs filters update the shareable hash; keyboard
Tab reaches the nav with a visible 2 px focus ring; the composer textarea and
send button are present and named.

## Scoring

Rubric: each dimension 0–10; "present as final" requires **combined ≥ 8.5 and
every dimension ≥ 8**. Aesthetic sub-scores marked *(human)* are my visual
judgement of the opened screenshots; the rest are computed.

**Aesthetic — 9.5 / 10**

| Dimension | Score | Basis |
|---|---|---|
| Shape coherence | 10 | computed: one radius per role, 0 zero-radius controls |
| Background calmness | 10 | computed: 1 gradient layer, low alpha |
| Color coherence | 10 | computed: single accent family, no emerald accents |
| Hierarchy & density *(human)* | 9 | clear sectioning; chat column readable; KPI tiles a touch airy |
| Detail polish *(human)* | 9 | consistent borders/focus/states; small uppercase metadata is dense |
| Cross-surface consistency *(human)* | 9 | SPA + server pages now share one shape/atmosphere language |

**Functionality — 10 / 10**: 19/19 journey checks pass, axe critical/serious 0,
console errors 0, 715 tests pass.

**Combined — 9.8 / 10** (aesthetic 45% + functionality 40% + regression health 15%).
Above the 8.5 bar with no dimension below 8 → acceptable to present as the
increment. The result is **not** presented as a full accessibility or
performance certification.

## Not verified (honest gaps)

- No real screen-reader pass (NVDA/VoiceOver/TalkBack unavailable); axe + manual
  keyboard only.
- No physical phone test; Chromium emulation at 320–428 px only.
- Forced-colors / high-contrast mode and RTL/logical-property rendering were not
  exercised.
- Aesthetic sub-scores are a designer judgement on synthetic demo data, not an
  external benchmark.

## Evidence

- `docs/qa/img/chat-desktop-{before,after}.png`
- `docs/qa/img/runs-desktop-{before,after}.png`
- `docs/qa/img/chat-phone-after.png`, `connections-after.png`

## Truthfulness note on the accent

The repo moved from the emerald accent (`#34d399`) to the "brutalist-modern"
blue (`#52a8ff`) in an earlier approved pass; the SPA, the server pages and the
website share the blue contract. This change **keeps** that contract (it does not
re-litigate the hue) and removes the last emerald leftovers that made the blue UI
look inconsistent.
