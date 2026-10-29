# CONCEPTS-D1-D2.md - text-first concept elaboration (no assets, no renders)

Project: Hutch - Run 3 (continued on maintainer instruction) - Date: 2026-10-28 (America/Vancouver)
Author: DSH session "lead"
Status: SPECIFICATION TEXT ONLY. No mark, icon, wordmark, lockup, favicon or render was generated,
drawn, exported or rendered for this document. It describes rules and test plans in words and
numbers. It is not an asset file and creates no asset file.

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
that Run 4 can build a master file and a test harness without re-deciding design questions.
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

Rule to be confirmed by evidence in Run 4 (B1 needed):
- At output sizes of 20px and above: use the master as-is (stroke 2.5 units).
- At output sizes below 20px: use a "small master" with stroke 3.0 units (1.5px at 16px) and dot
  radius 4.5 units (2.25px), OR snap to the nearest whole-pixel stroke. Choose whichever wins the
  16px test below; record the winner as the rule.
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
- Typeface: Geist (variable, OFL, self-hosted). Tracking -0.02em. Weight is an open item: the social
  renderer uses 620, DESIGN.md says 650, the shipped CSS uses extrabold. Proposed: 620 as the
  reproducible spec, to be confirmed visually in Run 4; do not fork a second weight.
- Title and metadata: the shipped "hutch - hutch" title is a defect. Proposed replacement:
  "hutch - local-first AI assistants" on product surfaces, and the existing marketing title kept
  unless the copy owner changes it. Terminology follows the one-lexicon rule (bot vs assistant is a
  separate copy decision; this document does not settle it).

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

## 4. Open items this document hands to Run 4

1. Confirm the wordmark weight (620 proposed) and tracking once a rendered comparison is possible.
2. Decide the small-size master by the 16px test (stroke 3.0 vs pixel-snapped) and write the winner
   into the master spec.
3. Reconcile the desktop icon colour (#28cd9d) to the emerald token or record it as an approved
   variant with evidence (U07).
4. Collapse the three colour aliases (--accent, --brand, --color-semantic-brand) to one semantic
   brand token in the implementation phase.
5. Fix the "hutch - hutch" title and the notices-file drift (PROVENANCE-REGISTER NTC-01).
6. Elaborate D3 "Quiet Chrome" and D4 "Character Tiering" as the third and fourth shortlist
   territories (D29); no assets in Run 4 without a separate decision.
7. Trademark class check remains the maintainer's follow-up (D28). If it later shows a class 9/42
   overlap, this specification is evidence only - it does not make the mark usable.

## 5. What this document does not do

- It does not generate, draw, render or export any asset.
- It does not clear anything: pre-screen, not clearance; no distinctiveness or non-infringement claim.
- It does not change product UI, tokens, source or docs outside .pipeline/brand/**.
- It does not decide D3/D4, the product wordmark implementation, or any filing/watch question.
