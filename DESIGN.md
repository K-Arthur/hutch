---
name: Hutch
description: Local-first multi-bot agent workspace — a conversation-first console for supervising, approving and reviewing bot work.
colors:
  primary: "#34d399"
  primary-ink: "#052e21"
  primary-deep: "#10b981"
  surface-ground: "#05070a"
  surface-panel: "#080c12"
  surface-raised: "#10161f"
  surface-sidebar: "#030508"
  surface-sunken: "#020406"
  bubble-user: "#1d2735"
  selection: "rgba(96, 165, 250, 0.30)"
  line: "rgba(255, 255, 255, 0.07)"
  line-strong: "rgba(255, 255, 255, 0.14)"
  border-emphasis: "rgba(255, 255, 255, 0.22)"
  hairline-top: "rgba(255, 255, 255, 0.06)"
  track: "rgba(255, 255, 255, 0.09)"
  text-primary: "#f0f4f9"
  text-secondary: "#9daebf"
  text-tertiary: "#7d8ea4"
  focus: "#60a5fa"
  focus-ink: "#05070a"
  success: "#34d399"
  warning: "#fbbf24"
  error: "#f87171"
typography:
  body:
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans", Arial, sans-serif, "Apple Color Emoji"'
    fontSize: "14px"
    fontWeight: 400
    lineHeight: "1.55"
    letterSpacing: "normal"
  heading:
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans", Arial, sans-serif'
    fontSize: "22px"
    fontWeight: 700
    lineHeight: "1.4"
    letterSpacing: "-0.02em"
  section:
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans", Arial, sans-serif'
    fontSize: "16px"
    fontWeight: 650
    lineHeight: "1.55"
    letterSpacing: "-0.005em"
  brand:
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans", Arial, sans-serif'
    fontSize: "16px"
    fontWeight: 700
    lineHeight: "1.55"
  marketing-display:
    fontFamily: "Archivo, ui-sans-serif, system-ui, sans-serif"
    fontSize: "176px"
    fontWeight: 800
    lineHeight: "1"
  marketing-display-min:
    fontSize: "88px"
  micro-label:
    fontSize: "11px"
  metadata:
    fontSize: "12px"
  mono:
    fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", "Cascadia Mono", "JetBrains Mono", Menlo, Consolas, monospace'
    fontSize: "13px"
    fontWeight: 400
    lineHeight: "1.5"
    letterSpacing: "normal"
rounded:
  control: "8px"
  panel: "12px"
  chat: "18px"
  composer: "22px"
  chip: "100px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-ink}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "32px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.text-secondary}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "32px"
  input-text:
    backgroundColor: "{colors.surface-ground}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
  status-chip:
    backgroundColor: "transparent"
    textColor: "{colors.text-secondary}"
    rounded: "{rounded.chip}"
    padding: "4px 9px"
  chat-bubble-user:
    backgroundColor: "{colors.bubble-user}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.chat}"
    padding: "9px 14px"
  card:
    backgroundColor: "{colors.surface-panel}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.panel}"
    padding: "16px"
---

# Hutch design system

## Overview

Hutch is a local-first multi-bot agent workspace: an operator console where a person
sends tasks to bots, watches real execution, and decides consequential approvals.
The design job is **trust under time pressure** — every pixel either helps someone
understand what the machine is actually doing, or it is chrome that should shrink.

**Creative North Star: "An instrument that never lies, and never shouts."**

**Key Characteristics:**
- Layered graphite surfaces with elevation by offset+blur shadow and a top hairline — never glow.
- One conversation column (760px) carries the story; operational ledgers (runs, usage,
  approvals) support it as tables, not as the homepage.
- Colour does jobs: emerald is the brand and the primary action; azure is interaction
  only; amber means a human must act now; rose means failure. Everything else is
  neutral so those four stay legible.
- Mono type is reserved for measured values (ids, durations, counts, budgets) —
  it signals "this number came from the machine".
- The operator workspace uses simple, flat 2D Bot characters: one coloured
  silhouette and two inset ink oval eyes. Each head shape has its own face center,
  spacing, proportions and tilt; pointed silhouettes place the eyes in the wider
  lower face. The shape chooser previews the same geometry used by the avatar, and
  every eye remains inside its silhouette. Identity is stable by Bot name and
  editable by the owner.
  Detailed original 3D mascot artwork belongs to marketing pages; the product
  and marketing characters are related brand work, not a shared UI asset.

**The Measure Rule.** Reading text caps at ~72ch; anything wider is layout debt.
**The One-Ink Rule.** Emerald fills always carry near-black ink (#052e21); white on
emerald is forbidden (≈2.5:1).
**The Amber Rule.** Amber appears only where a person must act now — pending
approvals, expiring deadlines under two minutes, the attention nav badge. Never as
decoration, never on "done" or "failed".
**The Scale Rule.** Every corner radius comes from `rounded.*`; no ad-hoc values.
**The Measured Rule.** Mono type is only for values the server measured — never for
prose, labels, or marketing.

## Colors

- **Emerald `#34d399`** (lineage through `#10b981`/`#6ee7b7`) — brand, primary
  buttons, live state, the mascot family. On-fill ink `#052e21` (7.7:1).
- **Azure `#60a5fa`** — interaction only: focus rings, selection, links. It is never
  a brand statement and never a status colour.
- **Amber `#fbbf24`** — person-needed-now only (The Amber Rule).
- **Rose `#f87171`** — failure: errors, denied outcomes, destructive actions.
- **Neutrals** — ground `#05070a` → panel `#080c12` → raised `#10161f`, text
  `#f0f4f9` / `#9daebf` / `#7d8ea4`, lines `rgba(255,255,255,0.07/0.14/0.22)`.
  Shared semantic values live in `website/tokens.json`, compile into the app and
  server pages, and are mapped into each DaisyUI theme. Marketing can use deeper
  layers, but it keeps the same ground, surface, panel, brand, focus, and borders.

## Typography

- **Body:** system sans, 14px/1.55 default; conversation text 15px/1.65;
  editor text (composer, instructions) 16px+.
- **Headings:** 22px/1.4 weight 700, tracking −0.02em; section heads 16px/650/1.55;
  the wordmark uses 16px/700;
  micro-labels 11px mono uppercase, tracking +0.07em — used only as data labels,
  never as decorative eyebrows.
- **Mono:** ids, durations, tokens, budgets, code, timestamps — always with tabular
  numerals and ligatures disabled. Prose never uses mono (The Measured Rule).
- **Marketing display:** the locally bundled Archivo variable font gives the site’s
  oversized hero and section headings their voice; body copy stays system sans.
- **Marketing micro type:** 11px is limited to compact table labels and numbered
  proof captions; 12px is the smallest metadata size. Both remain secondary.

## Layout

- Desktop shell: `272px sidebar | 56px top bar | 1fr content`, optional
  `380px` context drawer (fixed overlay below 1100px, auto-opened above).
- Sidebar docks to a 64px icon rail (logo becomes the expand control);
  state persists per browser.
- Conversation column: max 760px, composer pinned 24px above the safe area;
  feed scrolls internally (app frame never page-scrolls).
- Operational pages: 1240px container, 32px gutters, 4px spacing rhythm.
- Phone (≤900px): single surface + overlay navigation; ≤640px hides header meta
  and contextual labels; 44×44px touch targets.

## Elevation & Depth

- `--sh-1` (panels): top hairline + `0 2px 8px rgba(0,0,0,.5)`.
- `--sh-2` (composer/bubbles): `0 10px 28px rgba(0,0,0,.55)`.
- `--sh-pop` (modals/popovers): `0 24px 64px rgba(0,0,0,.7)`.
- Every elevation pairs an offset+blur shadow with a 1px top hairline — a
  zero-offset coloured halo is decoration and is not used as depth.
- Elevation is never the only state signal; colour and text carry meaning.

## Shapes

One rounded scale, applied honestly — this replaced an earlier all-square
language after explicit user direction ("right angles feel too off"):

- **`rounded.control` 8px** — buttons, inputs, rows, icon buttons, filter pills.
- **`rounded.panel` 12px** — cards, panels, menus, popovers, modals, toasts,
  table wrappers, approval cards.
- **`rounded.chat` 18px** — conversation bubbles (user bubble tail corner 6px);
  composer 22px (`--r-composer`) as the one larger surface.
- **`rounded.chip` 100px** — status chips, badges, counts, jump-to-latest, meter tracks.
- Mascot identity shapes (sigils, avatar glints) are artwork and may be any
  silhouette — they are not containers.

## Components

- **Primary button** — emerald fill, `primary-ink` text, 8px radius, 32px tall;
  hover lifts to `#6ee7b7`; ghost variant is transparent with a hairline border;
  danger is a rose outline. Icon buttons are 32px squares (circles only inside
  the composer: send/stop/+).
- **Status chip** — pill, mono 11px, dot + word always together (`● working`,
  `● needs you`, `✕ failed`); colour never carries state alone.
- **App avatar/sigil** — one flat silhouette from a curated set in one of eight
  identity colours with a pair of soft ink oval eyes. Each silhouette has its own
  eye center, spacing, proportions and tilt; pointed heads place the eyes lower in
  the wider face. The identity picker uses the exact same face geometry as the
  selected avatar. Derived from the Bot name and overridable
  at creation and in settings. Identity colours are decorative only, never status;
  the separate state pip sits beside it with its word. The marketing site's 3D art
  is a separate, larger brand illustration.
- **Identity picker** — colour and shape options use 44px touch targets. On phone
  widths, each eight-option row becomes a balanced four-by-two grid; the colour
  remains a 26px swatch inside its larger button.
- **Bot roster controls** — one always-visible, low-emphasis options button per
  Bot contains pin/unpin and settings. Hover and focus add contrast; display
  names wrap to two lines before the clamp; idle Bots collapse into a searchable
  group in workspaces with ten or more Bots.
- **Composer** — 22px rounded box, 16–18px textarea, circular emerald send and
  rose stop, a "+" popover holding only real capabilities (suggestions, rehearsal,
  Enter-behaviour, live budget).
- **Approval card** — a bordered system card while pending (plain-language
  action first, exact detail behind a disclosure, honest countdown); once decided
  it flattens to a single ledger row — history is text, not another box.
- **Tool lines** — borderless monospace rows under a collapsed "N steps" summary;
  every command and result is visible, expansion adds raw input/output in place.
  When output was truncated, the row carries a `source` flag and a rounded source
  card linking the saved artifact — the full output the model was not shown.
- **KPI strip** — one bordered row of four measurements, mono, compact.
- **Workflow header status** — counts real activity (working/queued/needs-you)
  from `/api/stats`; hidden when idle, spoken loudly only when the executor is
  degraded.

## Do's and Don'ts

**Do**
- Take every radius from `rounded.*`; keep the pill only for chips.
- Pair every icon with a word for state; give every control a visible focus ring.
- Use mono only for machine-measured values.
- Show real server state: if the API cannot confirm it, say "unknown".
- Keep motion short, functional and state-linked; honour reduced motion and the
  Reduce effects override (the typing dots are the one live animation).

**Don't**
- Never put white on emerald, or amber on something that isn't person-needed.
- Never box tool calls, or wrap decided approvals in cards.
- Never run ambient loops, pulsing dots on idle state, or animated backgrounds
  behind work.
- Never show a count, status or receipt the server did not produce.
- Never add a radius outside the scale, or a colour outside the palette.
