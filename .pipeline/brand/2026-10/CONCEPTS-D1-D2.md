# CONCEPTS-D1-D2.md - text-first concept elaboration (no assets, no renders)

Project: Hutch - Run 3 (continued on maintainer instruction) - Date: 2026-10-28 (America/Vancouver)
Author: DSH session "lead"
Status: SPECIFICATION TEXT ONLY. No mark, icon, wordmark, lockup, favicon or render was generated,
drawn, exported or rendered for this document. It describes rules and test plans in words and
numbers. It is not an asset file and creates no asset file.

Revision: Run 4 (2026-10-28) - section 6 added with the refinements; B1 (no browser) is resolved.
Sections 1-5 are retained except where section 6 explicitly supersedes a value, and each superseded
value is named there.

Basis:
- Direction D19: D1 "Centre Dot" repair base + D2 "Local Hub" lead territory.
- Signed clearance protocol v0.1 (D22): plan gate G1 fulfilled; creation was paused by the gate 1
  stop condition (observed HUTCH marks, classes unverified).
- Maintainer instruction 2026-10-28 (D28): proceed under the written risk ownership (D20/D23); the
  maintainer will check the trademark classes later. This is a dated human decision that the
  protocol's stop-condition row allows. It is a risk position, not a clearance: nothing here is
  cleared, distinctive or non-infringing.
- Secondary territories D3 "Quiet Chrome" and D4 "Character Tiering" join the Run 4 shortlist
  (D29). They are not elaborated here.

Non-claims: pre-screen, not clearance; risk rated only. Plan G6 vocabulary applies.

## 0. What this document is and is not

Is: written geometry, lockup, casing, clear-space and test-plan rules for the retained identity, so
that a later asset run (Run 5 at the earliest, and only after a new dated human decision) can build a
master file and a test harness without re-deciding design questions.
Is not: a drawing, a master file, a render, a product change, or a clearance opinion. No file under
website/, src/, desktop/ or docs/brand/evidence/ is touched or produced.

## 1. D1 "Centre Dot" - the retained system, written down

### 1.1 Master geometry (taken from the shipped mark, verified 2026-10-28)

- Artboard: 32 x 32 units.
- Hexagon: pointy-top (vertices at top and bottom), path
  M16 2 L28 9 L28 23 L16 30 L4 23 L4 9 Z
- Hexagon outer path box: x 4 to 28 (width 24), y 2 to 30 (height 28); ratio width:height = 6:7.
- Stroke: 2.5 units, centred on the path, no fill, joins as shipped (miter).
- Stroke colour: brand emerald #34d399 (website/tokens.json emerald 400); ink background #09090b;
  contrast 10.35:1 (plan A.3 E05).
- Centre dot: circle centre (16,16), radius 4 (diameter 8 = one third of the hexagon width).
- Outer stroke bounds: x 2.75 to 29.25, y 0.75 to 31.25, so the drawn mark fits the 32-unit artboard.

### 1.2 Non-negotiable rules

- One master path. Every surface copy (3 data-URI favicons, 3-4 header/footer lockups, desktop
  icon, future manifest icons) derives from it; no redraw, no "close enough" retrace.
- No fill inside the hexagon, no gradients, shadows, glows, inner strokes, rotation, stretch or
  squeeze. The dot stays at centre with radius 4 on the 32 grid.
- Colour: emerald only as the brand colour; monochrome versions inherit currentColor (section 3).
- Stroke width is a property of output size, not taste (section 1.3).
- The mark is never used as a button, never carries text inside it, and never sits on a photographic
  or gradient background without the containment rule (section 1.5).

### 1.3 Small-size rule (16px and 20px) - test plan, not a drawing

The 32-unit artboard scales by size/32. At 16px the shipped 2.5-unit stroke becomes 1.25px, which
commonly renders as a broken or grey 1-2px line; the dot becomes 4px.

Rule (decided Run 4, section 6.3; the 16px test can only confirm it or switch to the master):
- At output sizes of 20px and above: use the master as-is (stroke 2.5 units).
- At output sizes below 20px: use the "small master" - stroke 3.0 units, dot radius 4.5 units, all
  other geometry unchanged. 3.0 units is 1.5px at 16px, which rasterises without the grey
  sub-pixel line the 2.5-unit stroke produces; pixel-snapping is a renderer concern, not a geometry
  change.
- The 16px test below can override this only by showing the master passes every criterion at 16px;
  if it does, record that and keep one master. The dot never moves.
- Do not move the dot, change the hexagon path, or drop the dot at small sizes. Losing the dot loses
  the identity.

16px test plan (described, to be executed when a browser/capture harness exists - B1):
1. Raster the mark at 16, 20, 24 and 32 CSS px on #09090b and on #ffffff; DPR 1 and DPR 2.
2. View each at 100% and at 400% zoom; record whether the hexagon silhouette is recognisable at a
   glance and whether the dot reads as a separate object with a visible gap.
3. Inspect for vertex fill-in (the 6 corners turning into blobs), broken strokes and colour bleed.
4. Pass criteria: hexagon recognisable at 16px without a caption; dot visible with at least one
   clear pixel of gap from the stroke at DPR 1; no fill-in at the top and bottom vertices.
5. Evidence: named screenshots per the protocol's evidence rules; until B1 works, record "not
   captured - no browser" and do not claim a visual result.

### 1.4 Clear space and minimum sizes

- Clear space: 8 units (25% of the 32 artboard) measured from the outer stroke bounds on all sides.
  No text, edge, border or other mark enters that space.
- Minimum sizes: favicon 16px; inline monochrome icon 16px; inline colour icon 20px; header 24px;
  footer/drawer 22px; desktop icon 256px source. Below 16px the mark is not used.
- Do not put the mark in a box or circle to "protect" it; the clear space does that.

### 1.5 Horizontal lockup architecture

- Default is icon-only. The horizontal lockup is used only where the name must be read: marketing
  header, footer, page titles, social cards, README/OG where the mark is not already adjacent.
- Proportion: wordmark type size = 0.75 x mark box size (e.g. 26px mark + 20px wordmark, 24px mark +
  18px wordmark). Gap between mark and wordmark = 8 units = 0.25 x mark box size.
- Vertical alignment: wordmark x-height centred on the mark's centre line; do not bottom-align.
- Casing rule (resolves the drift): the wordmark is always lowercase "hutch". The emerald full stop
  "." is a terminal accent used in standalone wordmark contexts (marketing header/footer, social
  cards, text-only mentions). It is omitted where the wordmark sits directly beside the mark inside
  dense product chrome. This is one casing rule plus one documented accent variant - not three
  casings.
- Typeface: Geist (variable, OFL, self-hosted). Tracking -0.02em. Weight: 650 on the variable axis,
  resolved in Run 4 (section 6.2). DESIGN.md:45,62,250 state 650; the social renderer's 620 is the
  drift to correct, not a second spec; the shipped CSS `font-extrabold` (800) is drift to fix at
  implementation. One weight only; no fork.
- Title and metadata: the shipped "hutch - hutch" title is a defect. Proposed replacement:
  "hutch - local-first AI assistants" on product surfaces, and the existing marketing title kept
  unless the copy owner changes it. Terminology follows the one-lexicon rule (bot vs assistant is a
  separate copy decision; this document does not settle it). Exact defect:
  `src/hutch/server/templates/base.html:7` renders `<title>{% block title %}hutch{% endblock %} -
  hutch</title>`, so the default title is "hutch - hutch". Replacement rule in section 6.6.

### 1.6 Surface register (where the rules land)

| Surface | Current size | Rule that applies | Action phase |
|---|---|---|---|
| Marketing header | 26px mark + wordmark | Lockup 1.5, casing rule | Run 4 spec, later implementation |
| Marketing footer/drawer | 22px mark + wordmark | Lockup 1.5, clear space | Run 4 spec |
| Server header (templates) | 24px mark | Icon-only default, clear space | Run 4 spec |
| Studio sidebar | 22px mark | Icon-only default | Run 4 spec |
| Favicon (data-URI) | 16px intent | Small-size rule 1.3, monochrome plan 3 | Run 4 spec |
| Desktop icon | 256px source | Master geometry, colour reconcile (#28cd9d vs #34d399) | Run 4 decision |
| Social/OG cards | raster | Lockup 1.5, casing rule | Run 4 spec |

### 1.7 Do-not list

No fill, gradient, shadow, glow, 3D, rotation, outline duplicates, dot repositioning, added letters,
taglines baked into the mark, mascot merged with the mark, or colour-only meaning.

## 2. D2 "Local Hub" - the supporting motif

Thesis: the hexagon is the hub; each bot or assistant is a satellite tile in the same geometry. This
is a drawing language for rosters, empty states, diagrams and cards - not a navigation or product
structure change.

### 2.1 Motif geometry

- Same 32-unit grid. The centre tile is the master mark at 100%.
- A satellite is the hexagon outline only (no dot), drawn in a 16-unit box, stroke 1.5 units
  (= 2.5 scaled, rounded up for legibility), same pointy-top orientation.
- Placement: up to 6 satellites on the six hexagon axes, centre-to-centre distance 26 units from the
  hub centre. Minimum 1. Keep the distance constant; never hand-place satellites.
- One accent: at most one satellite carries the emerald dot or emerald stroke to mean "needs you";
  all others are neutral (border colour). State must never be colour-only - pair with a label or a
  badge.

### 2.2 Use and limits

- Allowed: bot roster illustration, empty states, docs diagrams, social cards, marketing
  #workflow/#cases sections, onboarding explanation of "one machine, several bots".
- Not allowed: as navigation, as a loading spinner, as a chart substitute, more than 6 satellites,
  animation as decoration, or replacing the master mark in a lockup.
- The PRODUCT principle applies: decoration must communicate structure or state, or it is deleted.
- Accessibility: if decorative, aria-hidden; if it conveys state, provide a text equivalent and do
  not rely on colour.

### 2.3 Test plan (described, not drawn)

- At 320 CSS px wide: satellites still distinguishable, labels readable, no overlap.
- Monochrome: the hub/satellite relationship must survive with one colour (stroke weight and
  position carry it, not colour).
- Density: with 6 satellites the composition must not compete with the page heading; test beside the
  marketing hero copy at 1440 and 390px widths.

## 3. Monochrome, colour-absent and forced-colours test plan

- The mark inherits currentColor in monochrome contexts; no hard-coded emerald.
- Test contexts: one-colour print, terminal/README (no colour), dark UI, light UI, Windows
  forced-colours/high-contrast mode, and a tinted OS icon context.
- Pass criteria: silhouette and dot survive with a single colour; no reliance on emerald to be
  recognised; in forced-colours mode the mark must not disappear or invert into the background.
- The favicon must work as a single-colour 16px rendition before a multi-colour one is preferred.
- Record results with the same evidence rules as 1.3.

## 4. Open items this document hands to the next runs

1. Wordmark weight and tracking: RESOLVED as a spec in 6.2 (650, -0.02em); a rendered comparison can
   still refine it, but it no longer blocks a master file.
2. Small-size master: DECIDED in 6.3 (small master below 20px); the 16px capture can only override it
   by passing every criterion with the master.
3. Reconcile the desktop icon colour (#28cd9d) to the emerald token or record it as an approved
   variant with evidence (U07).
4. Collapse the three colour aliases (--accent, --brand, --color-semantic-brand) to one semantic
   brand token in the implementation phase.
5. Fix the "hutch - hutch" title and the notices-file drift (PROVENANCE-REGISTER NTC-01).
6. Elaborate D3 "Quiet Chrome" and D4 "Character Tiering" as the third and fourth shortlist
   territories (D29); no assets in Run 4 without a separate decision. DONE in Run 4:
   CONCEPTS-D3-D4.md, text only; its section 4 is the selection aid for D1-D4.
7. Trademark class check remains the maintainer's follow-up (D28). If it later shows a class 9/42
   overlap, this specification is evidence only - it does not make the mark usable.

## 5. What this document does not do

- It does not generate, draw, render or export any asset.
- It does not clear anything: pre-screen, not clearance; no distinctiveness or non-infringement claim.
- It does not change product UI, tokens, source or docs outside .pipeline/brand/**.
- It does not decide D3/D4, the product wordmark implementation, or any filing/watch question.

## 6. Run 4 refinement (2026-10-28)

This section records what Run 4 learned and fixes the values that sections 1-5 left open. It adds no
asset, no render and no source change; browser capability exists (IP-CLEARANCE 11.1) but no render was
authorised.

### 6.1 What changed

- B1 resolved: headless Chromium 153.0.8010.12 verified in-session. The test plans in 1.3 and 3 are
  therefore executable as soon as a new dated asset decision permits renders; until then their status
  stays "not captured - no asset decision". A working browser is not permission to render.
- D3/D4 delivered: CONCEPTS-D3-D4.md, text only; its section 4 is the D1-D4 selection aid.
- Register probe (Run 4): the UKIPO records were reached and two live HUTCH registrations confirmed at
  classes 9 and 42 -> confirmed core-class overlap, escalated as B10 (IP-CLEARANCE section 0 addendum;
  DECISION D36). B7 is no longer "classes unverified" for the UK. Asset work stays gated.
- Values resolved below: wordmark weight and size (6.2), small-size rule (6.3), lockup numbers (6.4),
  alignment (6.5), title strings (6.6), colour-alias collapse (6.7), D2 coordinates (6.8).

### 6.2 Wordmark: one weight, one size rule

Evidence, read locally 2026-10-28:

| Source | Value observed | Disposition |
|---|---|---|
| DESIGN.md:45,62,250 | weight 650; standalone wordmark 18px with tight tracking | 650 adopted as the weight; 18px is the standalone size, not the lockup size |
| website/index.html:238,264,966 | `text-xl font-extrabold tracking-tight` -> weight 800, size 20px | drift: weight corrected to 650 at implementation; the 20px size is accepted at a 26px mark (6.4, ratio 0.77) |
| social renderer (recorded in 1.5, from the Run 1 audit) | 620 | drift: corrected to 650 in the renderer |

Decision: Geist variable `wght` 650 for the wordmark on every surface (CSS `font-weight: 650`);
tracking -0.02em; size in a lockup = 0.75 x mark box, rounded to whole CSS px (6.4); the shipped 20px
at a 26px mark is within the rounding tolerance. No positive tracking, no uppercase, no italic, no
second weight. If Geist fails to load, the fallback inherits 650 and the lockup geometry, not an
approximation of the wordmark.

### 6.3 Small-size rule - decided

- Below 20px output: use the small master (stroke 3.0 units, dot radius 4.5 units, everything else
  unchanged). At 16px that is a 1.5px stroke and a 2.25px dot.
- 20px and above: use the master as-is (2.5 units).
- Override path: the 16px test (1.3) runs with both renditions. If the master passes every criterion
  at 16px, use the master everywhere and record that; otherwise the small master stands.
- Never: drop the dot, fill the hexagon, add a halo or outline, or produce an 8/12px micro mark.

### 6.4 Lockup numbers (fixed)

Rule: wordmark size = 0.75 x mark box; gap = 0.25 x mark box; clear space = 0.25 x mark box (8 units on
the 32-unit artboard).

| Surface | Mark box | Wordmark | Gap | Clear space, all sides |
|---|---|---|---|---|
| Marketing header | 26px | 19.5 -> 20px (shipped) | 6.5 -> 6px | 6.5px |
| Marketing footer/drawer | 22px | 16.5 -> 17px | 5.5px | 5.5px |
| Server header | 24px | 18px | 6px | 6px |
| Studio sidebar | 22px | 17px | 5.5px | 5.5px |
| Social/OG lockup | 26-32px | 19.5-24px | 6.5-8px | as generated |

Rounding: round the wordmark and the gap to whole CSS px; keep the proportional error under 4%. A
vertical lockup (mark above wordmark, same gap ratio, centred) is proposed for a future square surface
such as a splash or print page; no current surface requires it.

### 6.5 Alignment

- Horizontal lockup: the wordmark's lowercase x-height is centred on the mark's centre line (16 of 32).
  Never bottom-align and never centre the cap height.
- Measure x-height from the rendered Geist at the chosen size during implementation; the rule is the
  alignment relationship, not a pixel offset.
- The mark and the wordmark never scale independently inside one lockup.

### 6.6 Title and metadata strings (fixed)

| Surface | Current | Spec |
|---|---|---|
| Product default title | `src/hutch/server/templates/base.html:7` -> "hutch - hutch" | "hutch - local-first AI assistants" |
| Product page titles | the block default | "{page} - hutch" (page names lowercase, e.g. "settings - hutch") |
| Dashboard shell | `src/hutch/server/static/index.html:6` "hutch — your personal assistant" | keep, or align to "hutch — local-first AI assistants"; copy-owner call, not required by this spec |
| Marketing | `website/index.html:6` "Hutch — local-first AI assistants that run on your machine" | keep verbatim (copy and SEO); the capital H is intentional there |

The "hutch - hutch" duplication is a defect, not a brand form. The fix is implementation-phase work;
no source file is edited in this run.

### 6.7 Colour aliases (collapse rule)

Evidence (PROVENANCE-REGISTER HX-02 evidence cell, read 2026-10-28): the marketing site uses
`var(--color-semantic-brand)`, the dashboard uses `var(--brand)`, and the server templates use
`var(--accent)`.

| Alias (surface) | Canonical target | Action |
|---|---|---|
| `--color-semantic-brand` (website) | `color.semantic.brand` = emerald 400 #34d399 (tokens.json:43) | keep as canonical |
| `--brand` (dashboard) | same token | deprecated shim -> canonical at implementation |
| `--accent` (templates) | same token | deprecated shim -> canonical at implementation |

Rules: no value change (the three names are intended to resolve to the same emerald; if any does not,
that is a bug to record in the implementation phase, not a new colour); no new alias; the canonical
name is the one the token generator emits; removal happens in one commit with a visual check of the
surfaces in 1.6. The desktop icon's #28cd9d (U07) is a separate decision and is not folded into this
mapping.

### 6.8 D2 composition canvas and coordinates (fixed)

Section 2.1 fixed the motif geometry but not the canvas. Fixed here, in the same 32-unit language:

- Canvas: 100 x 100 units, transparent; the hub (the 32-unit master artboard) is centred at (50,50).
- Satellites: hexagon outline only, 16-unit box, stroke 1.5 units, pointy-top, no dot. Centre-to-centre
  distance 26 units on the six hexagon axes. Exact centres:

| Position | Centre (x, y) | Order when fewer than 6 |
|---|---|---|
| top | (50.00, 24.00) | 1st |
| lower-right | (72.52, 63.00) | 2nd |
| lower-left | (27.48, 63.00) | 3rd |
| upper-right | (72.52, 37.00) | 4th |
| upper-left | (27.48, 37.00) | 5th |
| bottom | (50.00, 76.00) | 6th |

- Subsets are taken in the order column: 1 satellite = top; 3 = top, lower-right, lower-left (120
  degrees apart); 6 = all. Two, four and five are allowed only by that order; never hand-placed, never
  rotated, never a different distance.
- Extents: content box x 19.5-80.5, y 16-84 units; clear space around the composition 8 units.
- No connecting lines (they would imply order or navigation), no perspective, no animation as
  decoration. Labels sit outside the satellite boxes and take the host page's text style.
- Accessibility is unchanged from 2.2: decorative -> aria-hidden; state-bearing -> text equivalent and
  never colour alone.

### 6.9 Open after this refinement (next runs)

1. The 16px capture and the small-master confirmation (needs a dated asset decision).
2. Wordmark x-height/measurement at the shipped size (needs a render).
3. Desktop icon colour reconciliation, #28cd9d vs #34d399 (U07): a decision, not a measurement.
4. Actual per-surface resolution of the three colour aliases (needs a rendered or generated-CSS check;
   not done in this run).
5. Everything in section 1.6's action column remains implementation-phase work.
