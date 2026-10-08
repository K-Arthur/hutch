---
version: 1
slug: "website-index-html"
primary_target: "website/index.html"
related_targets: []
---

# Surface brief — website/index.html (marketing)

Mode: Persuade. Visitor decides whether Hutch fits them and takes the honest next action.

## Scope & constraints

Static HTML/CSS + small JS, no external requests, no build framework. Public access is private-repo (no install path may be advertised). WCAG 2.2 AA target, budgets: JS ≤100KiB, CSS ≤40KiB, fonts ≤120KiB, hero mobile art ≤300KiB, initial ≤900KiB transfer.

## Direction contract

THESIS: "A home for AI bots that keep working — on your machine, under your thumb." The page refuses the category default (headline over subcopy, button, then a row of identical feature cards). Instead the visitor is shown a shift-handover: an agent at work, its receipts, the gate that needs a human, and the exact access state — as an editorial dossier Hutch keeps on itself.

OWN-WORLD: architectural dark system on near-black mineral ground (cool-tinted, no purple, no beige identity); emerald #34d399 as brand accent with deep-inventory surfaces; one expanded editorial grotesque (Archivo, width axis live) for display, system UI sans for prose, one system mono stack for specimens; square 0px controls, 8px panels, 100px pills, hairline rings kept decorative; sparse static dot-grid; bounded radial glow only at the hero; evidence rows and monospace "specimen" tables carry the page's texture.

STORY: what Hutch is (persistent named bots on your disk) → proof it runs (captured product states, demo transcript) → a complete delegated workflow (task → supervised work → approval → artifact) → what runs where (inference vs execution map) → the control model and honest limits (not-a-sandbox, host-alive requirement, plan-terms caveats) → who it fits (3 grounded use cases) → access truth (private source today, documented path) → FAQ → one final CTA repeating the real action. Belief is earned by specificity: each section cites docs or captures, never adjectives.

FIRST VIEWPORT: asymmetric split at 1440. Left column: kicker-free H1 in expanded Archivo ("A home for AI bots that keep working." / second line "On your machine. Under your rules." sized down), 2-line max, sub-paragraph ≤20 words, primary CTA "See how it works" (scroll to proof) + secondary "Source on GitHub (private)", a mono status strip "v0.1.0 · Linux · MIT · no hosted service". Right column: the signature weave scene — poster word "hutch" in 115wdth/800, the dimensional emerald agent-orb (original SVG asset, native alpha, upper-left illumination) passing through exactly one front letter, an annotated specimen frame ("agent · idle") borrowing the character-system notation. At <900px the weave collapses to a compact static lockup above the copy; nothing essential is cropped.

FORM: pinned by the assignment brief — dark-tech/brutalist-modern, square geometry, registered type/subject weave as the one signature device, two supporting motifs (sparse dot-grid; monospace specimen rows). No concept roll: a brief-pinned direction beats the dice. Code-led build (no image-generation tool; impeccable context reports magick/ffmpeg converters only).

SIGNATURE INTERACTION: on load, the orb drifts into the weave once and the front glyph settles (≤1s, expressive curve, then still); scroll reveals fire once via IntersectionObserver from a readable default; a persistent "Effects: full/reduced" control in the header, stored, applied live without reload. All motion stops under prefers-reduced-motion.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.

## Open decisions

Production URL/canonical domain: none exists — leave meta og:url unset rather than invent; revisit at deploy. App-capture regeneration cadence when app UI changes.
