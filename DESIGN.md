---
name: Hutch
description: A personal assistant for everyday work, with optional specialist helpers and clear control over apps, models, and actions.
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
  display:
    fontFamily: 'Archivo, ui-sans-serif, system-ui, "Segoe UI", sans-serif'
    fontSize: "clamp(1.75rem, 3vw, 2.25rem)"
    fontWeight: 700
    lineHeight: 1.12
    letterSpacing: "-0.035em"
  page-title:
    fontFamily: 'Archivo, ui-sans-serif, system-ui, "Segoe UI", sans-serif'
    fontSize: "1.5rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.02em"
  section-title:
    fontFamily: 'Archivo, ui-sans-serif, system-ui, "Segoe UI", sans-serif'
    fontSize: "1.125rem"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "-0.02em"
  body:
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif'
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "normal"
  reading:
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif'
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: 1.65
  label:
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif'
    fontSize: "0.875rem"
    fontWeight: 650
    lineHeight: 1.4
  caption:
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif'
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.45
  brand:
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif'
    fontSize: "1.25rem"
    fontWeight: 700
    lineHeight: 1
  marketing-display:
    fontFamily: "Archivo, ui-sans-serif, system-ui, sans-serif"
    fontSize: "clamp(44px, 5.8vw, 80px)"
    fontWeight: 800
    lineHeight: "0.99"
  marketing-display-min:
    fontSize: "clamp(40px, 10.5vw, 44px)"
  metadata:
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif'
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.45
  mono:
    fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", "Cascadia Mono", "JetBrains Mono", Menlo, Consolas, monospace'
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: "1.5"
    letterSpacing: "normal"
rounded:
  control: "8px"
  panel: "12px"
  chat: "18px"
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
    height: "40px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.text-secondary}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "40px"
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

Hutch is a personal assistant for everyday work. People begin in a conversation,
turn a request into a specialist when useful, and review important actions in plain
language. Model, integration, memory, and execution details are available when
someone wants to adjust them. The design job is **helpful at first glance, dependable
when it matters** — make the next useful step obvious without hiding what a service
can access or what the machine has actually confirmed.

**Creative North Star: "A capable companion, with the details in reach."**

**Key Characteristics:**
- Familiar chat and app patterns carry everyday tasks; advanced controls appear in
  clear, optional layers instead of defining the first impression.
- Activity and task review lead with assistant, task, status, and conversation.
  Hide empty activity buckets; when no work needs attention, show one compact
  clear-state with direct links to chat and past work. Reported tokens, recorded
  cost, timing, run references, and transcript checks remain available in a
  clearly labeled optional details layer.
- A simple, shape-aware 2D character gives the app a recognizable face. Each
  distinct silhouette gets two balanced, near-round ink eyes placed directly on
  its colour. Their spacing, height, size, and gentle inward tilt follow the
  shape; do not add a visor, slits, pupils, highlights, or extra marks. Larger
  original 3D character art belongs to marketing; both use the same friendly
  palette and visual family.
- Provider artwork uses a current, locally bundled mark only when the source
  and usage context are documented. Keep every mark unaltered and secondary to
  the full service name and connection state; use a category glyph when no
  appropriate provider asset is available. Never imply endorsement or a
  special partnership. Google Workspace assets may identify a connected Google
  service under Google's deployment guidance; preserve approved artwork and do
  not make it the page's most prominent element. Use Microsoft Outlook's full
  color app icon only as a functional access cue, on a neutral field, beside
  the full “Microsoft Outlook” name. See [brand asset provenance](docs/brand-assets.md).
- Apps & AI keeps connection choices scannable. On phones, app rows use 40px
  category marks, compact copy, and one 44px action; wider layouts use 48px marks
  in service tiles. Keep complete product names and availability labels visible.
- Layered graphite surfaces keep long sessions comfortable. Emerald is the brand
  and primary action; azure is interaction; amber means a person needs to act; rose
  means failure. Text and familiar icons reinforce each color's meaning.
- Mono type is reserved for measured values such as IDs, durations, and budgets.
  Prose and instructions use the familiar system sans.

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

- **App family:** system sans for interface text and locally bundled Archivo
  for display, page, and section headings. The type hierarchy scales with browser
  text settings; neither app nor site fetches a remote font.
- **Display:** clamp(1.75rem, 3vw, 2.25rem), weight 700, 1.12 leading and
  −0.035em tracking for occasional welcome or feature emphasis.
- **Page title:** 1.5rem/1.25 weight 700, −0.02em tracking. **Section title:**
  1.125rem/1.25 weight 650. Routine settings pages keep a restrained hierarchy.
- **Body:** 1rem/1.55 for interface prose; longer reading and conversation
  passages use 1.0625rem/1.65. Labels use 0.875rem/1.4; compact metadata uses
  0.75rem/1.45. Composer text stays at 1rem or above.
- **Labels:** system sans with medium/semibold weight and restrained uppercase
  tracking only for compact group labels. Mono is reserved for measured data.
- **Wordmark:** 1.25rem/1 weight 700, system sans.
- **Mono:** ids, durations, tokens, budgets, code, timestamps — always with tabular
  numerals and ligatures disabled. Prose never uses mono (The Measured Rule).
- **Shared voice:** locally bundled Archivo is used for display, page, and
  section headings in the app, supporting pages, and marketing site. Body copy
  remains system sans, so the product feels related without turning every screen
  into a display face.
- **Marketing micro type:** 11px is limited to compact table labels and numbered
  proof captions; 12px is the smallest metadata size. Both remain secondary.
- **Icons:** actions and categories use one local 24×24 outline-vector family,
  with 16/20/24px size roles, a shared current-color stroke, and round joins and
  caps. Apps & AI uses original category glyphs for generic app groups and
  official provider artwork for named connections when documented in
  [brand asset provenance](docs/brand-assets.md). Keep exact service names and
  states visible. Provider artwork is bundled locally and never fetched at
  runtime.

## Layout

- **Marketing navigation:** keep section links inside a native modal on compact
  screens, not an ARIA action menu. Use the same raised surface, panel radius,
  azure focus, and 44px link rows as the product. Bound and internally scroll
  the link region so Close and the availability action remain reachable; desktop
  and phone share the 1024px navigation breakpoint. FAQs remain native inline
  disclosures with a visible focus outline, not popover menus.

- **Marketing explanations:** keep the short request-to-result overview separate
  from long expandable explanations. Explanations occupy a shared reading-width
  region below the overview; expanding one must not stretch sibling overview
  cards. Use body-sized prose and keyboard-operable native disclosures, stacking
  overview steps in reading order on smaller screens.
  Technical boundaries also use body-sized shared-width rows; do not shrink
  important limitations to metadata or stretch a parallel code panel to match them.

- Desktop shell: `304px expanded sidebar above 1000px (272px on smaller layouts) | 56px top bar | 1fr content`, optional
  `380px` context drawer (fixed overlay below 1100px, auto-opened above).
  Reserve enough name width for wider native system fonts alongside the avatar
  and options control; keep the shared text scale instead of shrinking labels.
- Sidebar docks to a 64px icon rail (logo becomes the expand control);
  state persists per browser.
- Conversation column: max 760px, composer pinned 24px above the safe area;
  feed scrolls internally (app frame never page-scrolls).
- First run pairs the request card with the AI-service panel above the **1100px**
  shell/content breakpoint; below it, the panel stacks after the request in DOM
  and reading order. The phone layout keeps the setup action in the initial
  viewport and exposes the readiness heading before the fold.
- On short desktop windows, the first-run welcome compresses its decorative stage
  and spacing so the initial setup action stays in the first screen.
- Operational pages: one 1040px content container and 32px desktop gutters
  (24px or less on phones), shared by the workspace and server-rendered
  technical pages. Page titles live once in the context header; content starts
  with its subtitle or first task, not a duplicate title.
- Assistant setup is a task page at `#/assistant/new`, not a modal. Multi-step
  setup keeps the primary action and a clear Save draft and leave / Discard
  draft choice; the unsaved form is restored only within the same tab. Short
  confirmations and focused pickers may remain dialogs.
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
  table wrappers, approval cards, and the composer box (every request surface
  in the composer family shares this one shape).
- **`rounded.chat` 18px** — conversation bubbles (user bubble tail corner 6px).
- **`rounded.chip` 100px** — status chips, badges, counts, jump-to-latest, meter tracks.
- Mascot identity shapes (sigils and faces) are artwork and may be any
  silhouette — they are not containers.

## Components

- **Primary button** — emerald fill, `primary-ink` text, 8px radius, 40px tall;
  hover lifts to `#6ee7b7`; ghost variant is transparent with a hairline border;
  danger is a rose outline. Icon buttons are 32px squares at the same 8px radius.
  The composer's send and utility actions follow these exact proportions — the
  composer owns no private button shape (user direction, 2026-10-23: the earlier
  circular send/`+` exception was removed as inconsistent with the control scale).
- **Controls** — routine buttons are at least 40px tall, compact desktop actions
  are 32px with 14px labels, and coarse-pointer actions are 44px; form fields and
  selects are 44px with 16px text so phone browsers do not zoom. Native selects
  open dark surfaces with legible options, and every label, help line, and
  control uses the shared type roles rather than one-off sizes.
- **Dropdown family** — use shared `controls.css`/`controls.js`, not a local
  lookalike. Actions are menus with roving focus; selected values are native
  selects or searchable pickers; panels containing fields use normal form Tab
  order, not menu semantics. Native form selects progressively adopt a styled
  browser picker where `appearance: base-select` is supported; other engines
  retain their native picker, labels, validation, reset and form submission.
  Popup panels use the shared raised graphite surface, 12px radius, emphasis
  border, 4px inset, 8px row radius and 40px rows (44px on phone/coarse pointers).
  Labels are 14px system sans, field values at least 16px, secondary copy 12px.
  Selection reserves a check lane; focus is azure and distinct from selection.
  One popup tree is open at a time; Escape closes the innermost layer and restores
  its trigger, while outside press does not steal the new target's focus. Keep
  panels in their owner's DOM and use the browser top layer where supported,
  with viewport-aware placement and bounded internal scrolling. An inline
  disclosure, FAQ or navigation list is not an ARIA menu. Research, user approval
  and validation scope: [dropdown standardization](docs/research/dropdown-standardization-2026-10-23.md).
- **Status chip** — pill, mono 11px, dot + word always together (`● working`,
  `● needs you`, `✕ failed`); colour never carries state alone.
- **App avatar/sigil** — one flat silhouette from a varied, curated set in one of
  eight identity colours with two balanced, near-round ink eyes drawn directly
  on the colour. Every silhouette has a face-safe zone that determines the eye
  centers, spacing, proportions, height, and slight inward tilt. Pointed heads
  place the eyes lower in the wider face. Avoid a visor, pale slits, pupils,
  highlights, or detached marks. The identity picker uses the exact same face geometry as the
  selected avatar. Derived from the Bot name and overridable
  at creation and in settings. Identity colours are decorative only, never status;
  the separate state pip sits beside it with its word. The marketing site's 3D art
  is a separate, larger brand illustration.
- **Identity picker** — colour and shape options use 44px touch targets. On phone
  widths, each eight-option row becomes a balanced four-by-two grid; the colour
  remains a 26px swatch inside its larger button.
- **Bot roster controls** — one always-visible, low-emphasis options button per
  Bot contains pin/unpin and settings. Hover and focus add contrast; display
  names stay on one line and long names end with an ellipsis while the full name
  remains available in the row title; idle Bots collapse into a searchable group
  in workspaces with ten or more Bots.
- **Fleet card** — lead with the assistant's name, readiness, plain-language role,
  run cadence and action expectation. Keep provider/model identifiers, exact
  schedule, run recency, estimated tokens and memory counts together under one
  **More details** disclosure. Do not repeat machine-oriented telemetry on every
  card by default; pause/resume and settings remain together in the card menu.
- **Assistant settings** — start with the editable name and short description.
  Keep standing directions and technical controls under one optional
  **Customize how it works** disclosure; preserve its open state after a save so
  people can adjust several related choices in one visit.
  Use the shared 1040px rail, with fields responding to their panel's actual
  width. Range inheritance and its slider/value occupy separate rows so labels
  remain legible inside the secondary-column layout.
- **Settings disclosure row** — every collapsible settings row uses the shared
  skeleton: one grid of icon slot, copy, and trailing Show/Hide action, in a
  large panel-level size and a small in-panel size. Borders and fills belong to
  the surface, never the row. Never nest one disclosure inside another: a
  separate connection with its own sign-in is a peer of the access it relates
  to and sits at the same depth. The action word carries state; the chevron is
  decoration.
- **Template gallery** — keep reusable-helper examples collapsed below the
  direct message path. Label that opening an example enters setup and does not
  start work. Use compact rows with a small, shape-aware 2D assistant identity;
  prioritize everyday jobs with short result names and keep storage IDs such as
  `repo-sweeper` out of visible titles.
- **First-run request and AI readiness** — pair the first request with one
  quiet AI-service panel on wide layouts; stack them in reading order below the
  shell breakpoint. State the actual service or saved workspace choice, not a
  claim that inference has been tested. Use the words **Ready**, **Saved**,
  **Choose AI**, and **Check failed** with a decorative dot; color never carries
  the state alone. A missing service keeps the action on choosing or connecting
  one instead of opening the technical model form. Keep the request in
  tab-scoped storage through navigation, reload, Cancel, and connection setup;
  expose **Clear request** while it has content and clear the draft only after
  successful assistant creation or that explicit action. Announce readiness
  changes in one polite status region without moving focus, and reserve stable
  space so late checks do not push the primary action.
- **Composer** — 12px rounded box (panel shape, matching the first-run request
  box), 16–18px textarea in a full-width writing area above a toolbar of ordinary
  8px-radius controls: 32px `+` utility left; skills, model trigger and 40px
  emerald send (rose outlined stop) right. The `+` popover holds only real
  capabilities (suggestions, rehearsal, Enter-behaviour, live budget).
  Attachment chips are 8px rows with real thumbnails; only genuine status
  badges keep the pill radius.
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
- **Activity and task review** — show only sections that contain active work.
  Use one clear-state with chat/history links when all sections are empty. Keep
  usage, timing, machine references, and transcript checks in optional details;
  do not repeat a run ID in the visible conversation header.

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
