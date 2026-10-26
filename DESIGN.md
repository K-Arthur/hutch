---
name: Hutch
description: A personal assistant for everyday work, with optional specialist helpers and clear control over apps, models, and actions.
colors:
  primary: "#34d399"
  primary-ink: "#052e21"
  primary-deep: "#10b981"
  surface-ground: "#09090b"
  surface-panel: "#101013"
  surface-raised: "#17171b"
  surface-sidebar: "#070709"
  surface-sunken: "#060608"
  bubble-user: "#1c1c21"
  selection: "rgba(96, 165, 250, 0.30)"
  line: "rgba(255, 255, 255, 0.07)"
  line-strong: "rgba(255, 255, 255, 0.12)"
  edge: "rgba(255, 255, 255, 0.38)"
  border-emphasis: "rgba(255, 255, 255, 0.22)"
  hairline-top: "rgba(255, 255, 255, 0.06)"
  track: "rgba(255, 255, 255, 0.09)"
  text-primary: "#ededf0"
  text-secondary: "#a3a3ae"
  text-tertiary: "#8e8e99"
  focus: "#60a5fa"
  focus-ink: "#05070a"
  success: "#34d399"
  warning: "#fbbf24"
  error: "#f87171"
typography:
  display:
    fontFamily: 'Geist, ui-sans-serif, system-ui, "Segoe UI", sans-serif'
    fontSize: "clamp(1.75rem, 3vw, 2.25rem)"
    fontWeight: 700
    lineHeight: 1.12
    letterSpacing: "-0.035em"
  page-title:
    fontFamily: 'Geist, ui-sans-serif, system-ui, "Segoe UI", sans-serif'
    fontSize: "1.5rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.02em"
  section-title:
    fontFamily: 'Geist, ui-sans-serif, system-ui, "Segoe UI", sans-serif'
    fontSize: "1.125rem"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "-0.02em"
  body:
    fontFamily: 'Geist, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif'
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "normal"
  reading:
    fontFamily: 'Geist, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif'
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: 1.65
  label:
    fontFamily: 'Geist, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif'
    fontSize: "0.875rem"
    fontWeight: 650
    lineHeight: 1.4
  caption:
    fontFamily: 'Geist, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif'
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.45
  brand:
    fontFamily: 'Geist, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif'
    fontSize: "1.25rem"
    fontWeight: 700
    lineHeight: 1
  marketing-display:
    fontFamily: "Geist, ui-sans-serif, system-ui, sans-serif"
    fontSize: "clamp(44px, 5.8vw, 80px)"
    fontWeight: 800
    lineHeight: "0.99"
  marketing-display-min:
    fontSize: "clamp(40px, 10.5vw, 44px)"
  metadata:
    fontFamily: 'Geist, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif'
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.45
  mono:
    fontFamily: '"Geist Mono", ui-monospace, SFMono-Regular, "SF Mono", "Cascadia Mono", Menlo, Consolas, monospace'
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: "1.5"
    letterSpacing: "normal"
rounded:
  micro: "4px"
  control: "8px"
  panel: "12px"
  chat: "20px"
  chip: "100px"
spacing:
  xs: "4px"
  sm: "8px"
  snug: "12px"
  md: "16px"
  lg: "24px"
  xl: "32px"
  xxl: "40px"
  section: "56px"
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
- A helper's work is a **thread**: its avatar anchors a spine, every tool call is a
  step on it, and a request for permission is a **gate** the thread stops at until
  a person decides. The avatar's face carries state (calm, scanning, looking for
  you, worried, asleep); identity colour tints the thread and never means status.
- Mono type is for code, commands, file paths, identifiers and measured values
  (Geist Mono, tabular). Prose, labels and instructions use Geist.

**The Measure Rule.** Reading text caps at ~72ch; anything wider is layout debt.
**The One-Ink Rule.** Emerald fills always carry near-black ink (#052e21); white on
emerald is forbidden (≈2.5:1).
**The Amber Rule.** Amber appears only where a person must act now — pending
approvals, expiring deadlines under two minutes, the attention nav badge. Never as
decoration, never on "done" or "failed".
**The Scale Rule.** Every corner radius comes from `rounded.*`, every text size from the type scale and every
padding or gap from the spacing scale; no ad-hoc values.
**The Mono Rule.** Mono type is for code, commands, paths, identifiers and values the
server measured — never for prose, labels, or marketing.
**The Edge Rule.** A control that is identified by its boundary (text field, select,
composer) uses `edge` (≥3:1 on every surface, WCAG 1.4.11). Cards and dividers keep
the quiet hairline; they are decoration, not identification.
**The One-Home Rule.** Each fact lives in one place: state in the avatar and the turn's
status word; "needs you" in the gate, the reminder strip and the nav badge; run counts
on Activity. The header repeats none of them.

## Colors

- **Emerald `#34d399`** (lineage through `#10b981`/`#6ee7b7`) — brand, primary
  buttons, live state, the mascot family. On-fill ink `#052e21` (7.7:1).
- **Azure `#60a5fa`** — interaction only: focus rings, selection, links. It is never
  a brand statement and never a status colour.
- **Amber `#fbbf24`** — person-needed-now only (The Amber Rule).
- **Rose `#f87171`** — failure: errors, denied outcomes, destructive actions.
- **Neutrals** — neutral graphite: ground `#09090b` → panel `#101013` → raised
  `#17171b` (sidebar `#070709`, code wells `#060608`), text `#ededf0` / `#a3a3ae` /
  `#8e8e99`, hairlines `rgba(255,255,255,0.07/0.12/0.22)` and the control `edge`
  `rgba(255,255,255,0.38)`. Every text token is ≥5.0:1 on every workspace surface
  (verified by `scripts/build_site_tokens.py --check` and a pixel-sampled audit).
  Shared semantic values live in `website/tokens.json`, compile into the app and
  server pages, and are mapped into each DaisyUI theme. Marketing can use deeper
  layers, but it keeps the same ground, surface, panel, brand, focus, and borders.

## Typography

- **Family:** Geist (variable, SIL OFL, Latin subset) for interface text, headings
  and the wordmark, and Geist Mono for code, commands, paths and measured values.
  Both are bundled locally (`static/fonts/`, `website/assets/fonts/`, licence beside
  them); neither app nor site fetches a remote font. The hierarchy scales with
  browser text settings.
- **Display:** clamp(1.75rem, 3vw, 2.25rem), weight 700, 1.12 leading and
  −0.035em tracking for occasional welcome or feature emphasis.
- **Page title:** 1.5rem/1.25 weight 700, −0.02em tracking. **Section title:**
  1.125rem/1.25 weight 650. Routine settings pages keep a restrained hierarchy.
- **Body:** 1rem/1.55 for interface prose; longer reading and conversation
  passages use 1.0625rem/1.65. Labels use 0.875rem/1.4; compact metadata uses
  0.75rem/1.45. Composer text stays at 1rem or above.
- **Labels:** Geist with medium/semibold weight and restrained uppercase tracking
  only for compact group labels.
- **The type scale.** Product text sets in six steps and nothing between them:
  **12** caption and metadata (kbd, chips, group labels), **13** small copy and
  mono, **14** labels and interface text (navigation, buttons, table cells),
  **16** body, **18** section titles, modal titles and the wordmark, **24** page
  titles and figures; **17** is reserved for long reading and the display band
  (28–36, fluid) for occasional welcome emphasis. 11, 12.5, 13.5, 15 and 20px do
  not exist in the product; `font-size: 0` is only how a header button collapses
  to its icon on a narrow screen. Enforced by
  `tests/e2e/test_type_and_spacing_scale.py`.
- **Wordmark:** 1.125rem/1 weight 650, tight tracking.
- **Mono:** commands, paths, code, ids, durations, tokens, budgets — tabular
  numerals, ligatures disabled. Prose never uses mono (The Mono Rule).
- **Shared voice:** one family across app, supporting pages and marketing site, so the
  product feels related; hierarchy comes from weight, size and tracking, not from a
  second display face.
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
  state persists per browser. Expanded, it reads top to bottom: logo with the two global
  round actions (search opens the command palette, plus starts a conversation), quiet
  navigation rows, the assistant roster, and two pill links (Apps & AI, Settings).
- **Spacing rhythm.** Everything sits on the 4px grid (4, 8, 12, 16, 24, 32, 40,
  56; 1–2px only for hairlines and optical nudges). Roles, not taste, pick the step:
  cards and panels pad **16** (12 for dense rows and nested blocks, 24 for hero,
  empty and first-run surfaces); stacked cards are **16** apart, dense list rows
  12 (8 on phones), page sections 32; a heading sits 8–12 above its content; a
  control's icon-to-label gap is 8. Control heights form one ladder: **32** small
  and inline, **36** header and toolbar controls, **40** primary and decision
  actions, **44** fields and every control on a coarse pointer. A stack that already
  has a row gap never also gives its children a bottom margin (that doubled the
  space between connection cards). Geometry derived from a component (the avatar
  gutter, an icon-input indent, composer clearance) is computed from that component,
  not hand-tuned.
- Conversation column: max 760px, composer pinned 24px above the safe area;
  feed scrolls internally (app frame never page-scrolls).
- First run follows the width of its own pane (container query), not the window: at
  **660px and wider** the request card sits left and a rail (AI service, how Hutch
  works, note) sits right; narrower, everything stacks in reading order. The phone
  layout keeps the setup action in the initial viewport and exposes the readiness
  heading before the fold; landscape phones go single-column so the request and its
  action fit above the fold.
- On short windows the first-run hero and spacing compress so the initial setup action
  stays in the first screen.
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
language after explicit user direction ("right angles feel too off"). Five steps,
chosen by the role of the shape and not by taste:

- **`rounded.micro` 4px** — keycaps, inline code and the user bubble's tail corner.
- **`rounded.control` 8px** — buttons, text fields, selects, icon buttons, filter
  pills, navigation rows up to ~40px, icon tiles, and blocks nested inside a panel
  (tool output, command previews).
- **`rounded.panel` 12px** — cards, menus, popovers, modals, the command palette,
  toasts, table wrappers, code blocks, approval cards, and rows from ~48px (the
  roster, run and chat-library rows).
- **`rounded.chat` 20px** — conversation bubbles and the composer box.
- **`rounded.chip` 100px** — status chips, badges, counts, the model pill, round
  header buttons, jump-to-latest, meter tracks. Perfect circles (avatars, status
  dots, spinner) use `50%`.
- **Nesting steps down, never up.** A shape inside another uses the same step or the
  next one down (chat → panel → control → micro) so inner and outer corners stay
  concentric; a control never has a larger radius than the panel that holds it.
- Mascot identity shapes (sigils and faces) are artwork and may be any
  silhouette — they are not containers.
- Enforced by `tests/e2e/test_radius_scale.py`, which fails with the selector of
  any painted corner or stylesheet literal that is off the scale.

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
  Popup panels use the shared raised graphite surface, emphasis border and 4px inset
  (the model menu is a 12px panel with 8px rows and a 32px icon tile); rows are
  40px (44px on phone/coarse pointers; the model menu's two-line rows are 52px).
  Labels are 14px system sans, field values at least 16px, secondary copy 12px.
  Selection reserves a check lane; focus is azure and distinct from selection.
  One popup tree is open at a time; Escape closes the innermost layer and restores
  its trigger, while outside press does not steal the new target's focus. Keep
  panels in their owner's DOM and use the browser top layer where supported,
  with viewport-aware placement and bounded internal scrolling. An inline
  disclosure, FAQ or navigation list is not an ARIA menu. Research, user approval
  and validation scope: [dropdown standardization](docs/research/dropdown-standardization-2026-10-23.md).
- **Status chip** — pill, 12px, dot + word always together (`● working`,
  `● needs you`, `✕ failed`); colour never carries state alone. Inside a turn header
  it drops the pill and reads as a quiet word with a dot.
- **Avatar state** — the face is the status: eyes scan while working, look out and
  widen while waiting for a person, droop when blocked, close when paused. Motion is
  compositor-only, gated on reduced motion and Reduce effects; static states (asleep,
  worried) still read without motion, and a pip carries the state's colour.
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
- **Bot roster** — a row is a 40px avatar, the name on one line, and a one-line status
  or role, with soft fills for hover and selection (a thin brand marker on the current
  row) instead of outlines. The workspace coordinator is the home card: a 44px avatar in
  a bordered tile at the top of the list. One always-visible, low-emphasis options button
  per Bot (pin/unpin, settings) sits in its own 28px column so ordinary names stay whole
  at the 272px sidebar; hover and focus add contrast. Long names end with an ellipsis
  while the full name remains in the row title; idle Bots collapse into a searchable
  group in workspaces with ten or more Bots. Once something is pinned, the group
  below it gets its own **All assistants** heading so the gap reads as a division. The roster filter hides
  until a first assistant exists.
- **Model picker** — a pill beside the composer actions shows the model in use (brand
  tint when it is a one-message override). Its menu groups choices by where they run
  (**On this machine**, **Hosted · leaves this machine**), each row an icon tile, the
  model name, a default tag and one quiet line; a check marks the one in use. The
  "Choose a model" dialog uses the same tile on card rows with the selection control at
  the far edge, a search field with an icon, and the cost and fit line under each name.
- **Fleet card** — lead with the assistant's name, readiness, plain-language role,
  run cadence and action expectation. Keep provider/model identifiers, exact
  schedule, run recency, estimated tokens and memory counts together under one
  **More details** disclosure. Do not repeat machine-oriented telemetry on every
  card by default; pause/resume and settings remain together in the card menu.
- **Assistant settings** — seven panes behind a section rail: **Profile** (name,
  look, role), **Behavior** (standing directions, response style, specialists),
  **AI model**, **Tools and access**, **Schedule**, **Safety** (approvals,
  command rules, always-allowed actions) and **Limits and memory**. The rail is an
  ARIA tablist: vertical beside the pane from 760px of pane width, a scrolling
  row (sticky, with `scroll-padding` so a focused field is never hidden under it)
  below; arrows, Home and End move and select; the selected tab is always fully
  visible; the choice survives the re-render a save triggers and is remembered
  per assistant for the session. Every pane stays in the DOM so each form keeps
  its id and handlers; only the selected pane is painted. A pane has one heading
  and a line saying what it holds, then ordinary panels. The 1040px rail and
  panel-width-responsive fields still apply; range inheritance and its
  slider/value occupy separate rows.
- **Chat and assistant options** — a popover of four labelled groups, each naming
  what it acts on: **This chat** (rename, pin, mark unread, section, and under More
  the export, reusable-request and archive actions), **Workflow** (the per-chat
  mode as a labelled row with its explanation), **This assistant** (response
  style, assistant settings) and **Go to** (main chat, conversation history).
  Settings never hide among conversation actions, and a select is never a card
  inside a menu.
- **Needs-you reminder** — the strip under the header states the count once; its action wears the amber
  wash and outline because a person is needed now, not the neutral ghost outline of other secondary actions.
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
- **First-run request and AI readiness** — a left-aligned hero (mascot beside the
  eyebrow, headline and one line of copy), the request card (inset field, starter
  chips, primary action with its "Nothing runs until you ask." line), and a rail with
  the AI-service panel and a short "How Hutch works" list whose last row shows the
  service marks. On wide panes they sit side by side; below that they stack in reading
  order. State the actual service or saved workspace choice, not a
  claim that inference has been tested. Use the words **Ready**, **Saved**,
  **Choose AI**, and **Check failed** with a decorative dot; color never carries
  the state alone. A missing service keeps the action on choosing or connecting
  one instead of opening the technical model form. Keep the request in
  tab-scoped storage through navigation, reload, Cancel, and connection setup;
  expose **Clear request** while it has content and clear the draft only after
  successful assistant creation or that explicit action. Announce readiness
  changes in one polite status region without moving focus, and reserve stable
  space so late checks do not push the primary action.
- **Composer** — 20px rounded box (`rounded.chat`, shared with bubbles) with an `edge`
  border, 17px textarea in a full-width writing area above a toolbar: 34px `+`
  utility left; skills, model trigger and 38px emerald send (rose outlined stop)
  right. A quiet keyboard hint sits under it on pointer devices. The `+` popover holds only real
  capabilities (suggestions, rehearsal, Enter-behaviour, live budget).
  Attachment chips are 8px rows with real thumbnails; only genuine status
  badges keep the pill radius.
- **Gate (approval card)** — a bordered card with an amber wash (rose for high risk)
  while pending: kicker + assistant + honest countdown, the plain-language action
  (commands in a mono well), the reason, the **exact content up front** (a file
  write shows its path, "New file / Replaces an existing file" and a clipped preview),
  scope tags (tool, risk, stays on this computer / leaves machine), details behind a
  disclosure, then Allow once (primary), Always allow (only when the server offers
  it) and Deny. There is no single-key approve shortcut: approval is always a focused
  button. Once decided it flattens to one ledger row on the thread.
- **Thread and steps** — a turn is avatar → spine → steps → answer. A "Worked for 14s ·
  5 steps" row (elapsed time minus recorded waits for a person, which it names) opens
  the steps; each step is a quiet row (tool icon with a state badge, plain-language
  title, mono subject, exit code, measured duration) that opens into a card showing the
  exact request (commands as `$ cmd`, files with a content preview, arguments as a
  table, raw JSON on request) and the full output with Copy. Errors and waits carry a
  word, not only a colour. When output was truncated the step carries a `source` flag
  and a source card linking the saved artifact.
- **Chat bubbles** — your message is a soft 20px bubble (one corner at 4px) on a
  graphite gradient with an inset highlight; very long requests clamp to ~14 lines
  with Show more. Time and the secondary "Make a bot" action share one meta row (the
  action appears on hover/focus, always on touch). The assistant's answer is not a
  bubble: it is Markdown text on the thread, 16px/1.7, ≤70ch.
- **Answer text** — rendered by the in-house escape-first Markdown subset
  (`static/markdown.js`): paragraphs, headings (h2–h4 under the page h1), lists,
  tasks, tables, quotes, rules, links (http/https/mailto only; images are never
  fetched) and fenced code with a language label and Copy.
- **Welcome** — avatar, name and role, "What would you like to work on?", honest
  trust chips (how it asks before acting, which tools it can use) and up to four
  starting points offered only for tools the assistant has. A starting point fills the
  composer; it never sends.
- **KPI strip** — one bordered row of four measurements, mono, compact.
- **Header** — one row: avatar (state-bearing), name and role; the conversation picker
  as a title chip (a customizable-select `<button><selectedcontent>` so long titles
  truncate), search, a menu, and Review/Stop only while actionable. A quiet "N working"
  link appears only while something runs. Needs-you lives in the reminder strip (in
  flow under the header, never over content) and the nav badge, not in the header.
- **Activity and task review** — show only sections that contain active work.
  Use one clear-state with chat/history links when all sections are empty. Keep
  usage, timing, machine references, and transcript checks in optional details;
  do not repeat a run ID in the visible conversation header.

## Do's and Don'ts

**Do**
- Take every radius from `rounded.*`; keep the pill only for chips and round buttons.
- Pair every icon with a word for state; give every control a visible focus ring.
- Use mono for code, commands, paths and machine-measured values — not prose.
- Give every control an accessible name that contains its visible text (WCAG 2.5.3).
- Show real server state: if the API cannot confirm it, say "unknown".
- Keep motion short, functional and state-linked; honour reduced motion and the
  Reduce effects override (the typing dots are the one live animation).

**Don't**
- Never put white on emerald, or amber on something that isn't person-needed.
- Never wrap a *decided* approval in a card (it becomes a ledger row), and never hide
  a pending gate behind a disclosure or a collapsed summary.
- Never animate text opacity (it drops contrast below AA mid-animation); animate the
  avatar, the spine node or an icon instead.
- Never run ambient loops, pulsing dots on idle state, or animated backgrounds
  behind work.
- Never show a count, status or receipt the server did not produce.
- Never add a radius outside the scale, or a colour outside the palette.
