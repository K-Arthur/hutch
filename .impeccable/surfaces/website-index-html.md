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

THESIS: "A personal assistant that can keep useful work moving." The page should make sense to someone who has never configured an AI model: show the kind of help Hutch offers, what the person remains in control of, and how to take the honest next step. Technical details support the story instead of leading it.

OWN-WORLD: architectural dark system on near-black mineral ground (cool-tinted, no purple, no beige identity); emerald #34d399 as brand accent with deep-inventory surfaces; one expanded editorial grotesque (Archivo, width axis live) for display, system UI sans for prose, one system mono stack for specimens; square 0px controls, 8px panels, 100px pills, hairline rings kept decorative; sparse static dot-grid; bounded radial glow only at the hero; evidence rows and monospace "specimen" tables carry the page's texture.

STORY: what Hutch helps with (ongoing personal tasks and focused helpers) → proof from the real application → a complete request-to-result conversation → the connected apps and chosen AI models → how permissions and approvals work → clear fit and current support limits → access truth (private preview, no public install) → FAQ → one final CTA repeating the real action. Belief is earned through real screenshots, plain language, and explicit capability status.

FIRST VIEWPORT: an editorial split with a clear people-first promise, one sentence explaining the machine and model choice, an honest preview action, and the original detailed 3D Hutch character. The app remains simpler and more familiar; brand color, icon language, wordmark, and character family connect the site to the product without copying its layout.

FORM: pinned by the assignment brief — dark-tech/brutalist-modern, square geometry, registered type/subject weave as the one signature device, two supporting motifs (sparse dot-grid; monospace specimen rows). No concept roll: a brief-pinned direction beats the dice. Code-led build (no image-generation tool; impeccable context reports magick/ffmpeg converters only).

SIGNATURE INTERACTION: on load, the orb drifts into the weave once and the front glyph settles (≤1s, expressive curve, then still); scroll reveals fire once via IntersectionObserver from a readable default; a persistent "Effects: full/reduced" control in the header, stored, applied live without reload. All motion stops under prefers-reduced-motion.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.

## Open decisions

Production URL/canonical domain: none exists — leave meta og:url unset rather than invent; revisit at deploy. App-capture regeneration cadence when app UI changes.
