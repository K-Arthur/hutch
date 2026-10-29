# CONCEPTS-D3-D4.md - text-first elaboration of D3 "Quiet Chrome" and D4 "Character Tiering"

Project: Hutch - Run 4 - Date: 2026-10-28 (America/Vancouver) - Author: DSH session "lead"
Companion: CONCEPTS-D1-D2.md (the retained base system; this file assumes its sections 1-2).
Status: SPECIFICATION TEXT ONLY. No mark, icon, wordmark, lockup, favicon, manifest icon, render or
image was generated, drawn, exported or edited for this document. It describes rules, numbers and
test plans in words. It creates no asset file and changes no product or source file.

Basis:
- D19: D1 "Centre Dot" is the repair base and D2 "Local Hub" the lead territory.
- D29: D3 "Quiet Chrome" and D4 "Character Tiering" join the Run 4 shortlist. This document elaborates
  them in text only; it does not select one.
- D28: text/spec work proceeds under the maintainer's written risk ownership (D20/D23). That is a
  risk position, not a clearance.
- D24: the browser capability now exists (Playwright Chromium 153.0.8010.12 verified in-session,
  2026-10-28; see IP-CLEARANCE.md section 11.1 and DECISION.md D30). It makes the described tests
  executable later; it does not authorise any render or asset in this run.
- D25: the mascot character stays marketing-only until its licence, copyright holder and usage rules
  are documented (C27). D4 below writes that position into tiering rules.
- D16: the PWA manifest and icons are in scope as a product-behaviour change; the manifest itself is
  not edited in this run.
- Register probe (Run 4, same day): the UKIPO records were reached and two live HUTCH registrations
  were confirmed to cover Nice classes 9 and 42 in the United Kingdom (IP-CLEARANCE section 0 addendum
  and 11.3). That is a confirmed core-class overlap and is escalated as B10. It changes no doctrine
  below (this document is text only) and it reinforces the rule that no asset may be produced before a
  new dated human decision.
- D12: website/tokens.json governs the colour ramp. Token names and values quoted here were read from
  that file on 2026-10-28.

Non-claims: pre-screen, not clearance; risk rated only. No clearance, distinctiveness or
non-infringement claim is made for the name, the mark or the character. Nothing in this file
authorises asset generation: that needs a new dated human decision.

## 0. What this document is and is not

Is: written doctrine for two shortlist territories, at the level of rules, taxonomy, numbers and test
plans, so that a human can compare the four directions and, if they choose, a later run can produce
assets against a fixed spec.

Is not: a drawing, a master file, a render, a preview, a product change, a token change, a trademark
conclusion or a licence opinion. No file under website/, src/, desktop/ or docs/brand/ is touched.

## 1. D3 "Quiet Chrome" - engineering the identity for colour-absent contexts

### 1.1 Thesis, restated

The identity is designed first for the contexts where colour is unavailable (16 px favicon, terminal,
forced-colours mode, one-colour print, maskable/monochrome platform icons) and only then given the
emerald accent. Emerald keeps the jobs it already has in the shipped token contract; identity never
depends on it.

Why this is not decoration: it converts three shipped debts into one rule - (a) no favicon,
apple-touch or manifest icon exists today (FINDINGS 4.6, carried in CONCEPT-LOG D3), (b) the mark is
inlined six times in three HTML roots with no master (PROVENANCE-REGISTER HX-01/HX-02), and (c) the
same colour name reaches the UI through three CSS aliases. A mono-first master fixes all three at the
source instead of per surface.

### 1.2 Rule D3-R1: mono-first production order

Every identity asset is produced in this order, and the next step starts only if the previous passes:

1. Monochrome master: one ink colour on a known background, no alpha tricks, no gradient, no
   second colour. At 16 CSS px this must read as the mark.
2. Two-colour light/dark variants derived from the same master: emerald mark on ink background, and a
   light-context variant (ink mark on paper) that is explicitly allowed to be a separate rendition.
3. Only then the coloured accents (emerald dot or stroke) and any surface-specific treatment.

Consequence: a coloured version that cannot be reproduced in mono is rejected. Mono is not a fallback
delivered afterwards; it is the proof that the geometry carries the identity.

### 1.3 Rule D3-R2: colour job reservation

Colour is a signal, not decoration. The shipped contract already assigns jobs; identity must respect
the assignment and must not add jobs.

| Token (website/tokens.json, read 2026-10-28) | Value | Job in the product | Identity use |
|---|---|---|---|
| color.semantic.brand (emerald 400) | #34d399 | brand accent, link, and (by token reuse) success | the only colour the identity may use, as an accent |
| color.semantic.brand-strong (emerald 300) | #6ee7b7 | hover/emphasis on brand surfaces | accent variant only, never a second identity colour |
| color.semantic.brand-deep (emerald 600) | #10b981 | pressed/deep state | not for identity |
| color.semantic.on-brand (emerald ink) | #052e21 | text on brand fill | not for identity |
| color.semantic.info / focus-ring (blue 400) | #60a5fa | information and keyboard focus | never used in the mark, favicon, icons or character |
| color.semantic.warning (amber 400) | #fbbf24 | warning state only | never used in identity |
| color.semantic.danger (red 400) | #f87171 | error/danger only | never used in identity |
| color.semantic.bg (ink 950) | #09090b | the dark background | identity background, not part of the mark |

Reservation rules:

- D3-R2a: emerald = brand + action + link (and the product's success semantics, which reuse the
  brand token). Azure = focus/info only. Amber = warning only. Red = danger only.
- D3-R2b: status colours (azure, amber, red) never appear in identity artwork: not in the mark, not
  in a favicon, not in a manifest icon, not in the character.
- D3-R2c: colour never carries meaning alone (WCAG 1.4.1). Every state that uses a colour job also
  carries a word, an icon shape or a position change.
- D3-R2d: identity survives the removal of every colour. If a surface can only show the mark in one
  ink, that ink is chosen for contrast (paper #ededf0 on ink #09090b, or ink #09090b on paper), not
  for brand expression.
- D3-R2e: no new brand colour is introduced by D3. The token ramp is the contract (D12).

Note recorded, not resolved here: success and brand share the same emerald value in tokens.json.
That is a product-semantics choice, not an identity rule; the identity simply never uses status
semantics as decoration.

### 1.4 Monochrome-first favicon (16 px)

The favicon is the hardest colour-absent test because it is tiny by definition.

- D3-R3a: the favicon is the monochrome master first: hexagon outline plus centre dot in one ink.
  The emerald accent version is an enhancement chosen by the platform context, not the default test
  target.
- D3-R3b: three renditions, one master: (1) one-colour on dark (paper ink), (2) one-colour on light
  (ink), (3) brand accent (emerald on ink) for contexts where the surrounding chrome already carries
  the brand. All three derive from the same geometry; no redraw.
- D3-R3c: SVG favicon may switch ink with `prefers-color-scheme` inside the SVG, but the switch must
  only swap the ink, never the geometry and never add elements.
- D3-R3d: the current three inline data-URI favicons collapse to one encoded master plus one light
  variant (PROVENANCE-REGISTER HX-01). No fourth copy.
- D3-R3e: no text, no letter "h", no character in the favicon. The character is marketing tier (D4)
  and was already rejected as a favicon/icon in CONCEPT-LOG section 3.
- Pass criteria (executed later, needs an asset decision): at 16 CSS px, DPR 1, the hexagon
  silhouette is recognisable at a glance, the dot is a separate object with at least one pixel of
  gap, no corner fill-in. Under one-colour conditions the same test passes. The plan is in
  CONCEPTS-D1-D2.md section 1.3; D3 adds the mono-first order as a gate.

### 1.5 PWA layers: any, maskable, monochrome

The manifest does not exist today; this is the spec it would be built to, when the manifest change is
approved as a product change (D16 accepted in principle, not implemented).

| Layer | Size | What it must contain | Rules |
|---|---|---|---|
| any | 192, 512 | the master, coloured or mono depending on the chosen default | transparent background is allowed for "any"; the dot must survive |
| maskable | 512 (also 192 if produced) | full-bleed ink #09090b square, mark centred inside the safe zone | content confined to the central circle of diameter 80% (409.6 px of 512; radius 204.8); no text; no border; background is part of the asset |
| monochrome | 512, alpha only | single-colour silhouette of the mark (hexagon outline plus dot) with alpha as the mask | no colour at all; the platform tints it; the dot must be a hole or a separate positive shape that survives tinting |
| apple-touch-icon | 180 | opaque square, ink background, mark centred | no transparency: iOS composites black behind alpha; the ink background is the deliberate choice |

Rules: one manifest entry per purpose (do not merge any and maskable into one file); the maskable
safe zone is a hard constraint, not a suggestion; the monochrome layer is generated from the same
master, not traced separately; no manifest icon carries text or a wordmark. The PWA splash/background
colour is the ink token. Windows/macOS/Tauri icon sets are a separate packaging decision and stay
open under U07 (desktop colour #28cd9d is unreconciled).

### 1.6 Forced-colours, high-contrast and non-text contrast

- D3-R4a: identity SVG uses `currentColor` for ink and `fill`/`stroke` only; no hard-coded emerald
  in the default path. A coloured instance is a separate named variant, not the master.
- D3-R4b: under `forced-colors: active` the mark must map to the system text colour and must not
  disappear: do not use background-image techniques for the mark in product chrome; keep
  `forced-color-adjust: auto`.
- D3-R4c: the focus ring is azure in normal rendering and the system Highlight colour in forced
  colours; it must keep 3:1 non-text contrast against its adjacent background (WCAG 1.4.11) and must
  never be the only difference between states.
- D3-R4d: test matrix (later): Windows High Contrast (both themes), Firefox HCM, Edge forced colours,
  `prefers-contrast: more`, and a monochrome e-ink-style render. Pass: mark visible, dot visible,
  focus visible, nothing relies on emerald.

### 1.7 Terminal, README and plain-text contexts

- D3-R5a: in plain text the identity is the wordmark as text: lowercase `hutch`, optionally the
  terminal period `hutch.` when it is a standalone signature, never "Hutch" mid-sentence unless
  grammar requires a sentence start. One casing rule plus one accent variant (CONCEPTS-D1-D2 1.5).
- D3-R5b: no ASCII-art logo and no Unicode box-drawing mark. There is no master for a text glyph, and
  a hand-typed one would be a fourth copy by another name.
- D3-R5c: README uses the SVG mark with a light/dark source switch (`<picture>`/media) and
  `alt="Hutch"`; the mark is decorative beside the name, informative when alone.
- D3-R5d: CLI and log output use the wordmark text only; colour in a terminal is reserved for status
  semantics (success/warning/error), never for identity. No ANSI truecolor assumption: the identity
  must read in a 16-colour or no-colour terminal.
- D3-R5e: no emoji anywhere, including as a stand-in for the dot.

### 1.8 Colour-absent contexts to design for (checklist)

| Context | Form | Pass criteria |
|---|---|---|
| 16 px favicon, DPR 1 | mono master | silhouette + dot readable; no fill-in |
| browser tab, light theme | mono on light | ink mark on paper reads; contrast >= 3:1 non-text |
| OS dark/light app icon | mono/any | no alpha halo, no reliance on emerald |
| PWA maskable/monochrome | full-bleed / alpha | safe zone respected; tint survives |
| forced-colours mode | currentColor | mark and focus visible; no invisible state |
| one-colour print / laser etch / single-thread embroidery | one ink | geometry alone carries identity; no detail below 1 px stroke |
| terminal / README / changelog | text wordmark | lowercase rule; no faux glyph |
| social card at small size | mono or colour | mark not the only carrier of the account name |

### 1.9 What D3 fixes, and what it does not decide

Fixes: the production order (mono first), the colour-job reservation rules, the variant matrix
(favicon 3 renditions, PWA 4 layers, forced-colours expectations, terminal rule).

Does not decide: which variant becomes the default, the actual files, the manifest edit, token
renames (alias collapse is CONCEPTS-D1-D2 section 6), a new colour, or any product behaviour change.

### 1.10 D3 test plan (described; executable only after an asset decision)

1. Produce the mono master (16 px test first) - NOT in this run.
2. Raster/serve at 16, 20, 24, 32 CSS px at DPR 1/2/3 on ink and paper backgrounds.
3. Run the favicon, maskable and monochrome checks in a real browser (Playwright is available now).
4. Run the forced-colours matrix in Edge/Firefox; record screenshots under the protocol evidence
   rules.
5. Record pass/fail per row of 1.8 with the exact environment (browser, version, OS theme).
Until step 1 is authorised, the only recorded status is "not captured - no asset decision".

### 1.11 D3 risk and gates

- Risk: LOW as a direction. It changes no mark geometry, no colour value, no typeface; it specifies
  variants of assets that do not exist yet.
- Dependencies: D1's master (section 1.1 of CONCEPTS-D1-D2); the PWA manifest change is a product
  change (D16 principle accepted, implementation later); every icon file is an identity asset and
  therefore needs the same dated decision.
- IP: D3 adds no new mark. The Vienna coding and the observed HUTCH overlap concern the hexagon+dot
  device itself and are unchanged by variants; see IP-CLEARANCE.md section 11.

## 2. D4 "Character Tiering" - two-tier imagery doctrine

### 2.1 Thesis, restated

Two tiers, one rule: the rendered 3D character owns marketing, social and call-to-action warmth; the
product keeps the simple 2D identity (mark, wordmark, line icons). The character is never the product,
and the product is never rendered as the character.

Product basis: PRODUCT.md:82 (as cited in CONCEPT-LOG D4 and FINDINGS 4.4) keeps the detailed
character for marketing and a simple 2D identity in product; 21 sprite frames ship and the render
script exists; the licence terms are not stated (C27). The byte-identical duplicate frame set under
src/hutch/server/static/agent/ (PROVENANCE-REGISTER MSC-03) is the second debt tiering resolves.

### 2.2 The tiers

| Tier | Asset family | Where it may appear | Where it may not appear |
|---|---|---|---|
| M - marketing | the 3D character still (website/assets/hutch-agent.webp, 620x880 alpha; MSC-01) and the 21 frames (website/assets/agent/, MSC-02) | marketing hero, CTA area, social/OG cards, docs illustrations, press imagery once terms exist | product UI of any kind; icons; favicon; manifest; app icon; CLI; captures |
| P - product | the hexagon+dot mark, the wordmark, the line-icon families, the D2 hub motif | dashboard, Studio, server pages, CLI output, README, empty states | 3D renders; character frames; any raster character |
| X - partner/press | none yet | nothing until the C27 terms statement exists and the maintainer approves a press kit | everywhere else |

The tier boundary is a rule, not a taste: an asset belongs to exactly one tier, and a surface belongs
to exactly one tier. Combining tiers inside one region (character behind copy, character inside a
product screenshot, character in an empty state) is a violation even if it looks good.

### 2.3 Written usage rules

- D4-U1: the character never appears in product chrome: no dashboard, Studio, settings, chat, empty
  state, error, modal, toast, onboarding step, icon, favicon, manifest or CLI.
- D4-U2: the character is never the mark and never merged with it: no character holding the hexagon,
  no character used as a letter, no mark placed on the character as a badge.
- D4-U3: no recolour, hue shift, gradient map, filter, shadow, outline, rotation, flip or
  silhouette change of the shipped renders. The render script is the only generator.
- D4-U4: no text, tagline, logo or UI mock baked into a character image; captions live in HTML.
- D4-U5: at most one character instance per viewport; no tiled or repeated character patterns,
  borders or backgrounds.
- D4-U6: never place the character under or over text; keep clear space of at least 24 CSS px around
  the rendered silhouette for decorative use, and never crop the silhouette in a way that changes
  what the character is doing.
- D4-U7: no new poses, expressions, props or camera angles without a recorded provenance entry and a
  dated asset decision. The 21 frames are the canonical set; extra frames are new assets.
- D4-U8: animation, if used, replays only the shipped frame sequence; it is decorative, pauses when
  offscreen or on `prefers-reduced-motion`, and the static frame is the still (MSC-01). No character
  animation in product, ever. No flashing or strobing.
- D4-U9: accessibility: decorative character gets `alt=""` (or aria-hidden); if the character carries
  meaning, the alt describes the action in words; meaning is never carried by the image alone.
- D4-U10: product screenshots never include the character; marketing captures are allowed only if the
  capture is a real sanitized product state (CAP-01) and the character is not composited into it.
- D4-U11: no AI-generated or third-party character imagery, no style transfer, no "close enough"
  re-render. Provenance is per-asset and recorded; unknown provenance means no use.
- D4-U12: no expanded use (press kit, partner, merchandise, conference, social profile image, app
  store listing) until the C27 terms statement exists and D25's marketing-only limit is lifted by a
  dated decision.

### 2.4 Duplicate-copy resolution (MSC-02 / MSC-03)

Facts: 21 WebP frames, byte-identical, in website/assets/agent/ and
src/hutch/server/static/agent/; no tracked doc mentions the second copy; no reference to it was found
in src/hutch or tests when the register was written (PROVENANCE-REGISTER MSC-02/MSC-03, 2026-10-28).

Resolution:

1. Canonical set = website/assets/agent/ because the character is marketing tier (M). The product
   copy is therefore a duplicate with no permitted consumer.
2. Implementation phase (needs a product-change approval, not this run): re-run a repo-wide reference
   check, then delete src/hutch/server/static/agent/ as part of the same commit that records the
   decision in PROVENANCE-REGISTER. Never delete first and check later.
3. If a future product need is ever approved against D4-U1, assets are generated by the render script
   into that target as a build step; they are never hand-copied. Two copies of the same bytes with no
   recorded purpose is the failure mode this rule removes.
4. The still (MSC-01) is the centre frame of the same render, not an independent asset; treat the
   still and the frames as one provenance family.

### 2.5 Provenance and licence position (C27), marketing-only per D25

Recorded state (PROVENANCE-REGISTER MSC-01/02/03): render pipeline documented (Blender bpy 5.0.1,
Cycles CPU, 96 samples, webp q82; script scripts/render_hutch_agent.py); author not named; copyright
holder not stated; licence not stated; usage rules not written. FINDINGS 4.4 records the same gap.

Position, in force until a terms statement exists:

- The character is marketing-only (D25). Its use is limited to the placements already shipped
  (website hero/CTA and social card source) plus non-expansive maintenance of those placements.
- No expansion, no derivative work, no licensing to third parties, no press kit, no merchandise, no
  product use, no favicon/app icon use, no sublicensing.
- A terms statement is the close condition: copyright holder named; licence/terms for the shipped
  artwork; permitted contexts; approval path; recorded in PROVENANCE-REGISTER and referenced from
  docs/brand-assets.md. Owner: maintainer. Counsel only if provenance stays unclear (D20 posture;
  gate 3 stays OPEN).
- This document makes no licence or ownership claim; it only states what may happen while the record
  is missing.

### 2.6 Tier boundary in practice

| Surface | Tier | Allowed form | Not allowed |
|---|---|---|---|
| Marketing hero | M | character + mark + headline, character on one side | character behind the headline; two characters |
| CTA block | M | character beside the action, static or shipped loop | character as the button; character with baked text |
| Social/OG card | M | character or mark, never both competing | character + wordmark + tagline stacked into one asset |
| README | P | mark + wordmark text | character render |
| Dashboard header / Studio sidebar | P | mark, wordmark, icons | any raster character |
| Empty states | P | D2 hub motif, line icon, text | character |
| App icon / favicon / manifest | P | mark (D3 variants) | character (already rejected, CONCEPT-LOG 3) |
| Product captures | P | sanitized product state | character composited in |

### 2.7 Anti-patterns this prevents

- "Identity louder than the task": a mascot in the product competes with the work the user is doing
  (plan R.1 anti-pattern; PRODUCT.md principle 4).
- Mascot creep: a character that spreads from marketing to product to icon to notifications is a
  rights and coherence liability with no product fact behind it.
- 3D style drift: new poses rendered ad hoc, each with its own lighting and proportions.
- Duplicate divergence: two copies of the same 21 frames edited independently.
- Rights exposure: expanding an asset whose licence and holder are unrecorded.

### 2.8 Audit checklist for existing surfaces (no renders; check later)

1. Find every reference to hutch-agent.webp and assets/agent/ in the repo (done for the register:
   website/site.js:104, docs/marketing-site.md:239; re-run before any change).
2. Confirm no reference to src/hutch/server/static/agent/ exists in product code or tests.
3. Confirm the OG/Twitter card (SOC-01) does not composite the character with the wordmark in a way
   that violates D4-U5; if it does, it is a fix queue item, not a redesign.
4. Confirm no product template, JS bundle or CSS references a raster character.
5. Record the result in PROVENANCE-REGISTER; close MSC-03 by deletion only with approval.

### 2.9 D4 risk and gates

- Risk: LOW visually (no geometry change), MEDIUM on rights (C27 open) and MEDIUM on product
  discipline (tiering must be enforceable in review, not just written).
- Gate: C27 terms statement before any expansion; D25 marketing-only stands; any new asset needs a
  dated decision. No trademark implication beyond the mark itself.

## 3. How D3 and D4 compose with D1 and D2

- D1 is the base: the master mark, the wordmark rule, the casing rule and the 16 px test are the
  prerequisite for both D3 (variants) and D4 (product-tier identity).
- D2 is a product-tier motif (tier P): it can use D3's mono-first order for diagrams and must obey
  D4's tier rules (no character in product diagrams).
- D3 is a variant-engineering layer, not a competing territory: it can accompany any direction. It is
  the only direction that addresses the favicon/manifest/forced-colours debt directly.
- D4 is an imagery doctrine, not a competing territory: it can accompany any direction and is the
  only one that addresses the character's rights position and the duplicate frame copy.
- Composition test: D1 + D2 + D3 + D4 is a coherent system (mark system, product motif, variant set,
  imagery tiering). The human selection is therefore primarily "which territory leads" (D2 vs D3),
  with D1 always retained as the base and D4 available as a companion or deferred.

## 4. Selection aid - comparing D1-D4 on the evidence (no invented scores)

Ratings are qualitative and evidence-bound: STRONG = the evidence in this pipeline supports the
criterion; ADEQUATE = supported with a named gap; WEAK = the evidence contradicts or under-supports
it; NOT EVIDENCED = no evidence exists in this pipeline, so the rating cannot be given. No numeric
score is calculated and no ranking is asserted; the human decides.

| Criterion | D1 Centre Dot | D2 Local Hub | D3 Quiet Chrome | D4 Character Tiering |
|---|---|---|---|---|
| Legibility (mark reads at 16 px and at distance) | ADEQUATE - geometry is shipped and in use; the 16 px pass is described but not yet captured | NOT EVIDENCED - the motif is new; no render exists to test | STRONG by design - it forces the 16 px mono test to pass before colour exists | ADEQUATE - the character is a marketing-scale asset; legibility at small sizes is not its job |
| Monochrome adaptability | ADEQUATE - one stroke plus one dot is structurally mono-capable; test plan in 1.3/3 | ADEQUATE - hub/satellite is stroke-based; the state accent must be re-expressed without colour | STRONG - this is the direction's definition; the mono master is the first artifact | ADEQUATE - the 3D render is inherently tonal; it is never asked to be mono in identity contexts |
| Category distinction (does it read as "local-first multi-bot platform" and not another AI app) | ADEQUATE - the mark is already distinctive in form but carries no category signal alone; category lives in the copy | STRONG - the hub/satellite motif is the only direction that pictures the product thesis (one machine, several bots) | WEAK - it is a quality doctrine, not a category signal; it makes the identity better engineered, not more distinctive | ADEQUATE - the character adds warmth (PO-2) but is a generic mascot device; it does not explain the category |
| Accessibility | ADEQUATE - contrast 10.35:1 verified for the shipped pair; focus and forced-colours rules pending | ADEQUATE - decorative vs state-bearing use must be enforced; D2 2.2 already requires a text equivalent | STRONG - forced-colours, contrast, non-text contrast and reduced-colour contexts are designed in | ADEQUATE - decorative by default; meaning must not rest on the image |
| Migration cost | LOW - near-zero visual change; docs, master asset and copy/metadata fixes (CONCEPT-LOG D1) | LOW-MEDIUM - new illustration layer only; any product application needs flags and do-no-harm evidence | LOW - asset variants plus rules; depends on the D1 master | NEAR ZERO visually - documentation, duplicate-copy removal and a terms statement |
| Risk (IP, rights, execution) | HIGH-OBSERVED for the name - two live UK HUTCH registrations confirmed at classes 9 and 42 (B10); the device itself is unassessed (no figurative search); text work unblocked, asset work gated | HIGH-OBSERVED for the name, as D1; the new motif adds no separate register exposure | HIGH-OBSERVED for the name, as D1; adds platform icon variants only | HIGH-OBSERVED for the name, as D1, plus MEDIUM-HIGH on rights (C27 terms missing) |

Reading of the evidence (not a decision):

- D1 is not optional: every other direction derives from its master and rules. The selection question
  is not "D1 or not"; it is "what leads alongside D1".
- D2 is the strongest on category distinction and is the only territory that pictures the product
  thesis. Its evidence gap is that nothing has been rendered or tested; its cost is an illustration
  layer.
- D3 is the strongest on monochrome adaptability and accessibility, and it closes the concrete
  favicon/manifest/forced-colours debt (FINDINGS 4.6). Its weakness is that it does not increase
  category distinction.
- D4 is the strongest on rights discipline and duplicate-copy hygiene, but its licence position (C27)
  is unresolved and D25 limits it to marketing. It is a companion doctrine rather than a lead.
- The confirmed UK class 9/42 overlap (Run 4) raises the name risk for every direction equally, so it
  does not discriminate between D1 and D4. It moves one decision upstream of the direction choice:
  whether the name is retained for the UK/global offering is a human decision (B10) that precedes, and
  may override, the territory selection. That upstream decision was taken on 2026-10-29: the maintainer
  retains the name (DECISION D38) after the confirmed UK evidence. It removes the rename branch and
  leaves the direction selection as the open decision; it authorises no asset.
- Combination the evidence favours, stated as a recommendation for the human to accept or reject:
  D1 base + D2 lead + D3 as the variant layer, D4 kept as the imagery doctrine with its rights gate
  (C27) still owed. This is a recommendation, not a selection; the Run 5 direction decision is the
  human's.

## 5. Evidence and method log

- Files read locally on 2026-10-28 (repo root): .pipeline/brand/2026-10/CONCEPTS-D1-D2.md,
  DECISION.md, IP-CLEARANCE.md, CLEARANCE-PROTOCOL.md, PROVENANCE-REGISTER.md, STRATEGY.md,
  HANDOFF.md, CONCEPT-LOG.md, website/tokens.json. Code evidence checked by grep on the same date:
  website/index.html (mark paths 235-236; wordmark markup 238, 264, 966), website/styles.css,
  DESIGN.md (wordmark lines 45, 62, 250), src/hutch/server/templates/base.html:7 (title defect).
- Capability: Playwright Chromium 153.0.8010.12 verified headless in-session (IP-CLEARANCE section
  11.1). No render was produced.
- External data used: none in the doctrine above. The Run 4 U21 checks and register probes are in
  IP-CLEARANCE.md section 11 (raw logs U21-FREE-CHECKS-RAW.md and REGISTER-PROBE-RAW.md); the confirmed
  UK class 9/42 overlap is recorded there and escalated as B10.

## 6. What this document does not do

- It does not generate, draw, render, resize or export any asset, including favicons, manifest icons
  and character images.
- It does not clear anything: pre-screen, not clearance; no distinctiveness or non-infringement
  claim; no licence or ownership conclusion for the character.
- It does not change the product, tokens, manifest, source or docs outside .pipeline/brand/**.
- It does not select a direction, lift the C27 marketing-only limit, or authorise the duplicate-copy
  deletion.
