# Hutch design system

Hutch uses one shared design language across its assistant workspace, supporting
settings pages, and public marketing site. Chats and Apps & AI share the same
application shell; Apps & AI, Models, Usage, and other settings views share its
semantic colors, focus states, control and panel geometry, and body type. The
marketing site keeps its editorial composition while reusing those same semantic
foundations. The app should feel like a personal assistant first; deeper provider,
permission, model, workspace, and resource controls remain available as optional
settings. The rules in
[`DESIGN.md`](../DESIGN.md) take precedence whenever this guide or an older
surface brief conflicts with them.

## Token source and builds

[`website/tokens.json`](../website/tokens.json) is the shared semantic token
source. The generator writes `website/tokens.css` for the static marketing site
and `src/hutch/server/static/brand-tokens.css` for Hutch's packaged UI. Studio's
compiled `ui.css` imports the generated tokens; the server-rendered templates
load the same generated file before `hutch.css`. Both Tailwind themes map their
component roles to these values. The semantic meanings are reviewed in
`DESIGN.md` and tested in `tests/test_site_tokens.py` and
`tests/e2e/test_design_system.py`. The browser test deliberately opens the
in-app `/#/connections` route; `/connections` is a legacy-compatible HTML page
and is not a substitute for the current screen.

Keep semantic button variants intact after CSS generation: primary actions use
the emerald fill and dark ink, ghost actions stay transparent with a hairline
border, danger actions use the rose outline, and warning actions use the warning
fill. Check computed browser styles for each role when changing or rebuilding
utility CSS; a neutral `.btn` base must not erase a named variant.

After changing a shared token, run:

```sh
python scripts/build_site_tokens.py
npm run build:css
.venv/bin/python -m pytest -q tests/test_site_tokens.py tests/e2e/test_design_system.py
```

Do not hand-edit generated CSS. The generator's `--check` mode verifies both
generated token files and the declared WCAG text pairs.

## Shared visual contract

| Role | Shared value | Use |
|---|---|---|
| Ground | `#05070a` | App frame and site background |
| Surface | `#080c12` | Studio panels, server cards, marketing proof panels |
| Panel | `#10161f` | Inputs, raised controls, secondary layers |
| Raised | `#171f2b` | Optional higher layer and hover surfaces |
| Main text | `#f0f4f9` | Headings and primary content |
| Secondary / muted text | `#9daebf` / `#7d8ea4` | Supporting content and metadata; keep contrast readable |
| Brand | `#34d399` with ink `#052e21` | Primary action and Hutch identity |
| Focus / information | `#60a5fa` | Focus rings, selection and informational emphasis |
| Warning / danger | `#fbbf24` / `#f87171` | Human attention and failure/destructive states |
| Hairline / strong / emphasis border | `rgba(255,255,255,.07)` / `.14` / `.22` | Card boundaries, controls, and hovered edges |
| Control / panel / chat / composer / pill radius | `8 / 12 / 18 / 22 / 100px` | Shared geometry scale |
| Display / UI body / measured data | local Archivo / system sans / system mono | Brand headings, readable language, and machine values |
| App type roles | `1rem` body / `1.0625rem` reading / `1.5rem` page title | Responsive hierarchy that respects browser text scaling |
| App icon family | `16 / 20 / 24px`, `24px` view box | Local category vectors in 48px desktop/tablet tiles and compact 40px phone rows; exact service names and states stay visible |

The app and marketing site share locally bundled Archivo for display, page, and
section headings, and system sans for interface and reading text. The app loads
the same licensed font locally, without a remote request. The site keeps the
locally bundled 3D Hutch mascot. The app uses compact flat 2D assistant characters.
Each head shape has two balanced, near-round ink eyes directly on its colour;
eye size, spacing, height, and subtle inward tilt follow that shape's usable
face area. The picker previews the same geometry. Do not add a visor or extra
facial marks. Status is shown separately.
Brand art, assistant identity, and runtime state never substitute for one another.

## Surface roles

### Chats and assistants

The chat is the daily workspace. Keep the active conversation and current work
prominent, with approvals and human waits visible in context. Use a searchable
Bot roster with the coordinator and attention states first. Each Bot has one
options menu for pinning and settings; idle, unpinned Bots collapse only when a
workspace has ten or more Bots. Long custom names stay on one line and end with
an ellipsis only when the available width requires it; familiar names such as
**Workspace Coordinator** stay whole at the default sidebar width. The full name
remains available on the assistant row.
An open approval review remains readable and actionable through feed refresh; if
the card has nested detail panels, preserve the open state of each panel
independently.

The large **Fleet** view keeps each assistant card scannable: one-line name,
current status, a short description, and a clear way to open its chat. Avoid
repeating schedule and action-access chips on every card. Place the service,
schedule, action-access setting, recent activity, token estimate, and saved-note
count behind one **Details** disclosure. Pause/resume and settings stay in one
options menu, so a large roster does not turn into a wall of controls or
infrastructure metrics. Long names shorten with an ellipsis and retain their
full text for assistive technology and hover.

Assistant creation should reuse the request that led to the creation flow,
suggest a short role-based name that the owner can edit, and keep the first path brief.
Advanced model, permissions, schedule, workspace, and memory controls remain
available as optional customization. Do not ask users to restate a task already
present in the source conversation.

The empty Studio chat keeps the message field primary. Reusable-helper examples
sit behind a collapsed **Create a helper from an example** disclosure, use
compact rows with small shape-aware 2D identities, and say that selecting one
opens setup rather than starting work. Keep their names result-focused and hide
storage IDs. Use a consistent local outline-icon family for actions and
categories, with plain-language labels beside them. Apps & AI uses 48px service
tiles on broad layouts and compact phone rows with a 40px category mark and 44px
action target.
ChatGPT uses OpenAI's exact, unaltered white Blossom mark under its
published brand terms. Microsoft Outlook, Gmail, and Google Calendar use
original service-category marks until product-icon use is permitted. Microsoft
guidance requires an express license for Outlook product artwork. Google's
current Partner Marketing Hub guidance directs product-icon use through its
approval form; Hutch has no permission recorded. See
[Google's product-icon guidance](https://partnermarketinghub.withgoogle.com/brands/google/branding-guidelines/how-to-show-googles-brand/)
and [Microsoft's trademark guidance](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks).
Never present a category icon as a provider logo. Keep provider, model,
permission, and runtime terminology in the relevant optional detail layer.

Assistant settings lead with the editable name and what the assistant helps with.
Standing directions and the rest of the controls sit behind one clearly named
disclosure with a meaningful icon, so people do not face a long technical form
when they only want to rename an assistant. AI, app access, scheduling, safety,
workspace, memory, and usage remain available when they choose to customize.
A workspace with only one assistant does not show a coordinator choice.
Keep the assistant name on one line in the settings header. Put secondary
navigation and destructive actions in one labeled **Assistant options** menu;
deletion should not compete visually with ordinary page navigation.

Scheduled work uses a filled primary **Choose an assistant** action when the
empty state offers multiple assistants. Keep each choice at a 44px minimum
height, one line, with an actual ellipsis on long visible labels and the complete
name in its accessible label. Bound and internally scroll larger choice lists
on phones so the menu does not become a page-length wall of options.

For an empty conversation in an existing assistant, lead the template gallery
with familiar jobs such as organizing files, following up after a meeting, and
reviewing the week. Give cards short task names instead of exposing internal
template IDs; preserve the IDs only in the action and saved configuration.

Approvals appear in the chat where the action was requested and remain available
in the dedicated queue for review at scale. Lead with the action and consequence;
keep exact arguments and destination reviewable; never hide an approval behind a
generic notification or rely on color alone. The **Needs you** queue puts pending
decisions and uncertain outcomes first. Optional browser notifications stay in a
collapsed **Browser notifications** disclosure with their current state visible
in its summary; recently decided requests remain collapsed until someone asks to
review them.

### Apps, activity, and settings

Chats and the in-app Apps & AI, Models, Usage, and other views share one
workspace sidebar, contextual header, system type, emerald actions, azure focus,
solid graphite surfaces, and 8px/12px control-panel geometry. Sign-in, pairing,
and remaining server-rendered pages load the same generated semantic tokens and
map their components to that contract. Service categories use the same locally
drawn outline glyphs across the app and marketing site. Apps & AI shows the exact,
unaltered OpenAI Blossom beside the named ChatGPT service under OpenAI's published
brand terms. Microsoft Outlook, Gmail, and Google Calendar use original
service-category glyphs beside their full names: Microsoft requires an express
license for its product icons, and Google directs product-icon requests through
Partner Marketing Hub. Hutch has no recorded approval for those marks.
Names and
connection states stay visible beside every mark; a category glyph is never
presented as a provider logo. The first layer explains the useful choice;
detailed scopes, OAuth setup, and account controls stay inside the optional
**More account settings** disclosure. Avoid a separate brand palette, blue
primary actions, glass panels, or square-button overrides.

Activity and task review follow the same first-layer rule: lead with the
assistant, request, status, and conversation. Keep reported tokens, recorded
cost, timing, run references, and transcript checks together in a clearly named
optional details layer. Hide empty activity buckets; when no task needs
attention, use one compact clear-state with direct links to chat and past work.
Past work uses the same task cards at desktop and phone widths. Never imply
recorded usage is a guaranteed bill or that an accepted send was delivered.

### Marketing site

The site keeps its editorial page composition and larger original 3D mascot.
System sans body text, brand/focus/status colors, controls, panel corners, and
semantic labels carry through from the app. Use Archivo where display hierarchy
needs its distinctive voice. Marketing claims, screenshots, CTAs, and support
labels must reflect verified product behavior; do not use executor credentials,
local-host access, or fixture-only states in public flows.

## Typography, spacing, and behavior

- The app uses system sans for interface text and locally bundled Archivo for
  display and heading roles. Named roles include `1rem` interface
  body at `1.55` leading; `1.0625rem` reading text at `1.65`; `1.5rem` page titles;
  and `1.125rem` section titles. Use rem units so user text scaling remains
  effective.
- App captions start at `0.75rem/1.45`. Do not use mono for prose, labels, chips,
  or decorative eyebrows. Use it for measured values, code, and identifiers.
- The app action family uses local `24px`-viewBox outline vectors, `16/20/24px`
  roles, and one current-color stroke. Provider art is a separate asset with
  provider-specific usage rules; do not draw lookalike logos or recolor official
  marks.
- Display and section headings use Archivo in both app and marketing. IDs,
  timestamps, budgets, code, and measured values use the mono stack; prose does
  not.
- Use the 4px spacing rhythm, preserving compact field groups and clear space
  between separate sections. Share alignment edges across repeated cards and
  page headings.
- Use real buttons, links, labels, headings, and landmarks. Keep keyboard focus
  visible, target 44px touch comfort for primary phone actions, and honor reduced
  motion. Use full-page or local scrolling deliberately; do not mask overflow.
- Status always has a readable word or sentence and any needed icon. Color is a
  secondary cue; Bot colors identify people or tasks, never run state.
- Keep animation tied to actual state or an explicitly chosen marketing moment.
  Idle liveness indicators stay still; reduced-motion preferences disable
  decorative movement.

## Research and user feedback

The documented reference and access limits are in
[`docs/research/ui-reference-patterns-2026-10-09.md`](research/ui-reference-patterns-2026-10-09.md).
Hutch's `DESIGN.md` on `main` remains the authority for code changes. The user's
supplied mobile screens informed familiar chat and per-assistant action patterns;
Figma Community references are useful when their individual nodes can be inspected.
Do not copy assets or imply that a broad preview verifies individual screen details.

Prioritize defects with direct evidence: clipped names, hidden approval work,
focus loss after refresh, crowded controls, duplicate setup questions, unclear
data movement, and status that overstates what the server confirmed. The
complaint evidence and its confidence boundaries are in
[`docs/research/complaints.md`](research/complaints.md). Treat individual reports
as acceptance scenarios, not estimates of how common a problem is.
