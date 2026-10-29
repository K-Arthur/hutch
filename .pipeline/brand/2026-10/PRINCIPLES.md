# PRINCIPLES.md - researched design principles and the rulebook for the Hutch mark

Date: 2026-10-29 (America/Vancouver). This file exists because the human asked for research into how
Claude and other models are made to produce strong SVG/logo work, and for those principles to be
applied instead of another round of loose primitives (D48). Sources were fetched today; quotes are
short and attributed.

## 1. What the skill material actually says

### 1.1 Anthropic "canvas-design" skill (fetched 2026-10-29)
Source: https://raw.githubusercontent.com/anthropics/skills/main/skills/canvas-design/SKILL.md [snippet]
- Work in two steps: **create a visual philosophy first**, then **express it visually** ("artefacts that
  are 90% visual design, 10% essential text").
- The philosophy must be named (1-2 words) and written as 4-6 paragraphs about form, space, colour,
  scale, composition, hierarchy.
- **Craft is a stated requirement**: "the final work should appear as though it took countless hours",
  "meticulously crafted", "master-level execution".
- **A subtle conceptual reference** must be embedded: "a subtle, niche reference embedded within the
  art itself... someone familiar with the subject should feel it intuitively, while others simply
  experience a masterful abstract composition."
- **Refine, do not add**: the final pass says avoid adding graphics, instead "refine what has been
  created and make it extremely crisp"; the Chanel line: "before leaving the house, remove one
  accessory."
- Containment: "nothing falls off the page and nothing overlaps... proper margins... clear separation."

### 1.2 Anthropic "frontend-design" skill (fetched 2026-10-29)
Source: https://raw.githubusercontent.com/anthropics/skills/main/skills/frontend-design/SKILL.md [snippet]
- Position as a design lead at a studio whose client "has already rejected proposals that felt cliché
  or templated".
- **Ground the design in the subject matter**: industry, subject, materials, vernacular decide the
  visual choices, not a generic aesthetic.
- It names the current **AI design tells** (verbatim list in the source), including: "a near-black
  background with a single bright acid-green or vermilion accent"; warm cream + serif + terracotta;
  broadsheet hairline layouts; "the SaaS-card kit: content chopped into identical rounded cards";
  template chrome such as ALL-CAPS eyebrows and monospace data labels.
- Process: **plan first** (colour, type, layout, principles), **review the plan against the generic
  default**, then build, then critique with screenshots ("a picture is worth 1000 tokens").
- Restraint: "**Spend your boldness in one place.** Let one element be the memorable thing, keep
  everything around it quiet and disciplined, and cut any decoration that does not serve the brief."
- Quality floor is not announced: responsive, keyboard focus, reduced motion, accessible colour.

### 1.3 Anthropic "brand-guidelines" skill (fetched 2026-10-29)
Source: https://raw.githubusercontent.com/anthropics/skills/main/skills/brand-guidelines/SKILL.md [snippet]
- Brand artefacts are applied mechanically from a documented palette, type pairing and fallbacks; it
  contains no new craft principle beyond consistency and contrast. Useful as a format model for the
  final guidelines, not as a design method.

### 1.4 Logo-craft material found (search-level, 2026-10-29)
- Optical corrections at small sizes: metric spacing vs optical spacing ("why your logo looks off at
  small sizes") - https://www.rs999.in/blog/optical-kerning-drift-why-your-logo-looks-off-at-small-sizes-and-the-metric-vs-optical-fix-designers-botch [reported title]
- Logo construction and refinement practice: "Smashing Logo Design - The Art of Creating Visual
  Identities" (book record) - catalog listing [reported]
- Gap in the evidence: no single authoritative, fetchable spec for "logo craft" was retrieved; the
  rules below are therefore marked as practice-derived [inference] where they are not quotes.

## 2. Diagnosis of this engagement against those principles

- Rounds 1-11 failed the **subject-grounding** test: they rendered generic enclosure primitives
  (rounded square, arch, brackets, canopy) and only later added meaning. The subject's own materials
  and vernacular (a hutch: a timber box with a roofed front, an opening, and inhabitants) were not
  driving the geometry; shape-first came first.
- They failed the **one bold move** test: several rounds stacked equal-weight elements (cap + front +
  base + seam), so nothing was memorable and everything competed.
- They failed the **refine-don't-add** test: each round added variants instead of refining one drawing.
- They hit a named **AI tell**: near-black + single acid-green accent is explicitly listed in the
  frontend-design skill. The colour system has to answer for that (see COLOUR-SYSTEM F2/F6).
- They under-used the **hidden reference** idea: a mark that quietly says "the door is open, the
  residents are home" is stronger than a mark that shows a character.

## 3. The rulebook applied from the next round on

R1 Subject first. The mark is a front elevation of a timber hutch: roofed cap, solid front, an
   opening at the threshold, two windows. It is architecture, never a face or a mascot.
R2 One bold move per mark. Everything else quiet: single silhouette, no competing details.
R3 Grid discipline. 32-unit canvas, 4-unit module; every coordinate lands on the grid or on a
   documented optical offset; curved extremes get 0.2-0.4 units of overshoot (optical correction).
R4 Equal optical area for repeating elements (a circle and a square that repeat must be equal area,
   not equal bounding box) [inference from optical-correction practice].
R5 Counterform is designed. Interior gaps: >= 2 units at master, >= 2.5 units at small size (so they
   survive 16 px as >= 1.25 px).
R6 Two size tiers, redrawn. Master for >= 32 px, small for 16-24 px; the small tier may drop one
   element but must keep the silhouette and the bold move.
R7 Silhouette test. Solid fill: recognisable at 24 px in two seconds; squint-blur test at 5 px must
   keep the bold move.
R8 Mono test. One colour must carry the mark; emerald is the wordmark period and UI accent, never a
   structural dependency.
R9 AI-tell audit. No dark+neon-only reliance, no gradient, no blob, no uniform rounded tile, no
   sparkle/node motif, no letter monogram without a structural idea.
R10 Remove one accessory. After the first drawing, delete one element and see if the mark improves.
R11 Provenance. Every geometric decision recorded in a construction sheet; no tracing, no stock.

## 4. What the next round tests

Three drawings, each with one bold move, each with the two size tiers and a construction sheet:
- **A "Threshold"**: tall front, two square windows, and an open threshold notch in the floor edge.
  Bold move: the door is open; the front stands on the ground.
- **B "Occupied / vacant"**: tall front, two equal-area windows, one round (occupied) and one square
  (vacant). Bold move: the state of the colony is legible without a label.
- **C "Canopy"**: the D2a roofed cap redrawn to the tall proportion with square windows. Bold move:
  the roof, the one element a mask or ghost silhouette cannot have.

Each is critiqued against R1-R11 in the round sheet before the human sees a recommendation.

## 5. Limits

- These are design-practice principles, not law. No trademark conclusion is implied.
- The "logo craft" literature cited here was not retrievable in depth; where rules are inference they
  are marked. A professional identity-design retainer would supply the missing depth.
- The AI-tell list is Anthropic's skill text, applied as a self-critique, not as a rule about clients.
