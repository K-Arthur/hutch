# Bot roster and mascot review (2026-10-09)

## Decision

Keep Studio as the normal place to work. Preserve the workspace coordinator at the
top, let an owner pin the task Bots they return to, and keep the rest in the same
searchable roster. Pinning changes navigation only. It does not hide a Bot, pause it,
change its work, or create a second management surface. Keep the existing Fleet view
for larger workspaces; ten Bots remains the owner's starting heuristic, not a proven
usability threshold.

Use simple flat 2D characters in the working app: a distinct coloured silhouette
with a matched pair of softly curved, solid ink eyes and no pupils or highlights.
Each pair follows its head's usable area, center, spacing, proportions and slant;
the shape chooser must show the same face
geometry as the selected avatar. Detached marks are avoided. Keep the more
detailed original 3D artwork on the marketing site. The mascot and its colour
never indicate whether a Bot is
running, waiting, paused, or failed; those states remain separately labeled.

## Shape-specific face follow-up (2026-10-10)

An earlier desktop and phone review found that narrow diagonal eyes looked like
repeated slashes and obscured differences between head forms. That review changed
the design to upright ink ovals with an individual face-safe area for each
silhouette. A later owner review found the heavier ink ovals still felt rigid;
the current treatment below replaces them with lighter swept shapes.

## Evidence and limits

- The user's seven supplied mobile screenshots show a coordinator with a star-like
  marker, a short roster of direct Bot chats with simple coloured silhouettes, and
  requests, choices, human checkpoints, and account confirmations shown in the chat.
  They are a visual and interaction brief, not independent product research.
- Grok Bot's current official guide explicitly supports pinning active Bots at the top
  of its sidebar and separately supports hiding. The distinction matters for Hutch:
  our app only implements pinning, because hiding could make ongoing or scheduled local
  work harder to notice. ([Create and manage Bots](https://docs.x.ai/grok-bot/bots))
- In one Character.AI community report, a user said frequently visited Bots were pushed
  out of recents and asked for a favorite/saved list. This is a useful findability
  scenario, not evidence of how common the problem is. ([Individual report](https://www.reddit.com/r/CharacterAI/comments/1j6uf88/i_wish_there_was_a_way_to_organize_the_bots/))
- An Open WebUI mobile issue documented a race where opening the mobile sidebar could
  replace visible chat history with an empty later page; search still found the records.
  That issue is closed and its reproduction belongs to Open WebUI v0.10.2. We use it
  only as a Hutch regression scenario: reopening and searching the phone roster must
  preserve access to every returned Bot. ([Issue #27014](https://github.com/open-webui/open-webui/issues/27014))
- The Grok Bot and Hutch product details are researched from public docs, not a live
  Grok Bot account trial. Community reports are anecdotes, not prevalence estimates.
  The supplied screenshots are not treated as proof about Grok Bot implementation.
- The Figma Community [100+ Organic Shapes file](https://www.figma.com/community/file/1121566033735107642/100-organic-shapes-brix-templates)
  groups varied forms as blobs, dots, lines and leaves. It was reviewed only as a
  shape-variety reference; no Community artwork was copied into Hutch.
- Mobbin's public Explore page surfaced an AI assistant collection, but opening
  individual screens required signing in and its screen-search connector returned
  an argument error. No screen-specific Mobbin pattern is claimed from this pass.

## Implementation and acceptance

The pinned flag is a Bot profile preference, defaults to false for existing records,
and is persisted in the existing Bot JSON. The workspace coordinator remains first;
pinned Bots follow in a labeled group; remaining Bots appear in “All bots”. Search
filters both groups. Unpinning returns a Bot to the ordinary list. There is no hide
control, so scheduled and active Bots remain visible in the same roster.

The responsive browser scenario verifies pin and unpin, persistence after reload,
coordinator order, search of a pinned Bot, keyboard focus restoration, 44px phone touch
targets, absence of horizontal overflow, distinct flat silhouettes, and no browser
errors. It saves desktop, tablet, and phone captures and a trace under
`docs/realignment/artifacts/pinned-roster/`. API coverage verifies that pinning leaves
the Bot's existing tools and approval mode unchanged. The visual acceptance record and
inspection results are documented in `docs/realignment/visual-validation.md`.

Manual mascot overrides continue to use browser-local view storage; they are not
synced between browsers. Pinning is persisted with the Bot and survives app reloads.

## Face refinement after owner review (2026-10-10)

The owner rejected the matched-looking dark ovals as heavy and poorly integrated
with the different silhouettes. A later trial of pale eyes with outlined pupils
looked googly at preview size. The current design uses broad, curved dark shapes
without pupils or highlights, with individualized placement and slant. The drop and triangle sit lower where
their heads are widest. They remain simple flat app artwork and are not copied
from a Grok Bot asset.

The provider artwork decision was revisited after checking current official
guidelines. ChatGPT keeps OpenAI's exact, unaltered white Blossom beside its
name. Microsoft bars product-icon use without an express license, so the
**Microsoft Outlook** account tile uses Hutch's original inbox glyph and keeps
the full product name. Gmail and Google Calendar also keep original category
glyphs until Google's approval process grants product-icon access. The visual
and usage boundaries are detailed in
[`icon-and-chat-interface-references-2026-10-10.md`](icon-and-chat-interface-references-2026-10-10.md).
User-supplied reference screens guide hierarchy and interaction only; they do
not grant rights to copy logos.
