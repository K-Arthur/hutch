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
`tests/e2e/test_design_system.py`. The familiar `/connections` URL redirects
into the current Apps & AI screen in the shared workspace shell. Retired
server-rendered forms remain at `/legacy/connections` for older clients; their
POST handlers stay available while the app uses the versioned API.

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

### Dropdowns and selection

The [approved dropdown direction](research/dropdown-standardization-2026-10-23.md)
uses `src/hutch/server/static/controls.css` and `controls.js` for both the SPA
and Jinja pages. Native `<select>` remains the form authority; customizable
browser pickers enhance its appearance without replacing names, values, reset,
validation or `change` events. Unsupported engines keep their native picker.
Action menus, selected-value pickers, multi-select checklists, form popovers,
and inline disclosures share visual roles but retain distinct semantics.

The editable setup route progressively enhances its datalist into a combobox:
DOM focus stays in the input, suggestions keep full provider-qualified route
values, Arrow keys explore and Enter explicitly accepts. Tab/Escape never
silently choose a suggestion. A persistent result announcement sits outside the
listbox; lists render at most 100 matches and state when typing can narrow them.
Popup and field edges reuse the design system's shared white-alpha hairline
tokens: `--color-semantic-border-strong` (`rgba(255,255,255,0.14)`) for outer
edges and `--color-semantic-border` (`0.07`) for internal separators, so dropdowns
match buttons, inputs and cards rather than carrying a one-off outline. Controls
are identified by fill, azure focus ring and this shared hairline together.

The marketing site deliberately does not load application popup JavaScript.
Its native modal navigation and inline FAQ disclosures share surface, radius,
focus and touch sizing, not application-menu roles. The first-run proof image
contains none of the changed pickers, so it remains the existing genuine empty
app capture; no synthetic chat screenshot is substituted for marketing proof.

Use `hutchControls.popup({trigger, panel, kind, side, onClose})` for floating
controls. Callers own data and actions; the controller owns placement, bounded
scrolling, focus entry, menu arrows, dismissal and teardown. Keep the panel
inside its owner, including a native modal; do not body-portal it or disable a
modal focus trap to make it clickable. `destroy()` releases node listeners;
detached open panels are cleaned up automatically. Normal inline `<details>`
and marketing disclosures are not popup menus.

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
| Hairline / strong / emphasis border | `rgba(255,255,255,.07)` / `.12` / `.22` | Card boundaries and hovered edges (decorative) |
| Control edge | `rgba(255,255,255,.38)` | Boundary of text fields, selects and the composer; ≥3:1 on every surface (WCAG 1.4.11) |
| Micro / control / panel / chat / pill radius | `4 / 8 / 12 / 20 / 100px` (`50%` for circles) | One shared scale for the dashboard and the site, chosen by role and stepping down when nested; no surface owns a private radius (`tests/e2e/test_radius_scale.py` enforces it) |
| UI and headings / code and measured data | local Geist / Geist Mono | One family for language; mono for code, commands, paths and machine values |
| App type roles | `1rem` body / `1.0625rem` reading / `1.5rem` page title | Responsive hierarchy that respects browser text scaling |
| Product text steps | `12 / 13 / 14 / 16 / 18 / 24px` (17 for long reading, a 28–36 display band) | Caption, small, label, body, section, page title; nothing between them (`tests/e2e/test_type_and_spacing_scale.py`) |
| Spacing scale | `4 / 8 / 12 / 16 / 24 / 32 / 40 / 56px` | Cards pad 16 (12 dense, 24 hero), stacked cards sit 16 apart, sections 32; 1–2px only for hairlines |
| Control heights | `32 / 36 / 40 / 44px` | Small and inline / header and toolbar / primary and decisions / fields and coarse pointers |
| App icon family | `16 / 20 / 24px`, `24px` view box | Local category vectors in 48px desktop/tablet tiles and compact 40px phone rows; exact service names and states stay visible |

The app and marketing site share locally bundled Geist (and Geist Mono for code and
measured values). Both are SIL OFL Latin subsets served from `static/fonts/` and
`website/assets/fonts/` with their licence beside them; neither surface makes a remote
font request. The neutral graphite palette and the control `edge` come from
`website/tokens.json` like every other shared value. The site keeps the
locally bundled 3D Hutch mascot. The app uses compact flat 2D assistant characters.
Each head shape has two balanced, near-round ink eyes directly on its colour;
eye size, spacing, height, and subtle inward tilt follow that shape's usable
face area. The picker previews the same geometry. Do not add a visor or extra
facial marks. Status is shown separately.
Brand art, assistant identity, and runtime state never substitute for one another.

## Surface roles

### Chat recovery and workspace settings

Chats remain the daily workspace. The compact conversation selector is a recent
switcher, not a history browser: the **Chat library** is the canonical recovery
path for active, archived, and imported conversation titles across assistants.
It pages results, opens the selected conversation exactly, and keeps message
search scoped to active chats so its disclosure remains true. Do not replace a
missing selected conversation with a newer one.

**Settings** is the single workspace-level destination for defaults used by new
assistants and the nonessential-motion preference. Assistant-specific model,
tool, schedule, memory, and approval controls remain in that assistant's
settings. Keep the dark theme as the shared visual contract; effects can follow
the operating system or be explicitly reduced/restored without changing theme.

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

Assistant creation is a task page (`#/assistant/new`), not a modal. It keeps
one step visible at a time, a primary Continue/Create action, and explicit
Save draft and leave and Discard draft actions. The unsaved form is restored
only in the same tab and cleared after creation or discard. Short decisions
may still use dialogs.

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
action target. Use exact, locally bundled OpenAI, Anthropic, OpenRouter, Google
Workspace, and Outlook artwork only beside the named service it identifies;
generic app categories keep the original service-category glyphs. Follow the
asset-specific constraints in [brand asset provenance](brand-assets.md): do not
alter the marks or imply endorsement, and use Microsoft's Outlook icon only as
a functional access cue on a neutral field beside “Microsoft Outlook.” Keep
provider, model,
permission, and runtime terminology in the relevant optional detail layer.

First run keeps the request beside one AI-service panel at wide widths and
stacks the panel after the request card below that breakpoint. The panel names
the saved, ready, missing, failed, or partially checked state in words and
offers the next connection action. A saved model is not described as a measured
readiness result. The request is stored for that tab, survives the provider
detour and setup Cancel, and is cleared after creation or through **Clear
request**. At phone widths the setup action stays in the initial viewport; the
readiness status is announced without taking focus.

Assistant settings lead with the editable name and what the assistant helps with.
Standing directions and the rest of the controls sit behind one clearly named
disclosure with a meaningful icon, so people do not face a long technical form
when they only want to rename an assistant. AI, app access, scheduling, safety,
workspace, memory, and usage remain available when they choose to customize.
A second-level **Usage and time limits** disclosure keeps token and cost fields
out of the way until requested; its summary states work steps and task duration,
and the UI expresses duration in minutes while preserving `timeout_seconds` in
the stored configuration. Label estimates as estimates and do not imply they
guarantee provider billing.
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
decisions and uncertain outcomes first. At scale it orders requests by the soonest
decision deadline, then risk and outward effect, and keeps a sticky summary with
counts and filters for due-soon, high-risk, and leaves-machine requests. The close
control remains reachable while the queue scrolls. There is still no bulk approval;
each decision stays bound to the exact request shown. Optional browser notifications stay in a
collapsed **Browser notifications** disclosure with their current state visible
in its summary; recently decided requests remain collapsed until someone asks to
review them.

### Apps, activity, and settings

Chats and the in-app Apps & AI, Models, Usage, and other views share one
workspace sidebar, contextual header, system type, emerald actions, azure focus,
solid graphite surfaces, and 8px/12px control-panel geometry. Sign-in, pairing,
and remaining server-rendered pages load the same generated semantic tokens and
map their components to that contract. Service categories use the same locally
drawn outline glyphs across the app and marketing site. Apps & AI uses the
unaltered official artwork documented in [brand asset provenance](brand-assets.md)
for named functional connections. Keep the full service name and connection
state visible beside every mark, keep the mark subordinate to the name, and do
not imply endorsement; generic categories keep their shared outline glyph.
The first layer explains the useful choice;
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
semantic labels carry through from the app. Display hierarchy comes from Geist
weight, size and tracking. Marketing claims, screenshots, CTAs, and support
labels must reflect verified product behavior; do not use executor credentials,
local-host access, or fixture-only states in public flows.

## Typography, spacing, and behavior

- The app uses locally bundled Geist for interface text and headings, and Geist Mono
  for code. Named roles include `1rem` interface
  body at `1.55` leading; `1.0625rem` reading text at `1.65`; `1.5rem` page titles;
  and `1.125rem` section titles. Use rem units so user text scaling remains
  effective.
- App captions start at `0.75rem/1.45`. Do not use mono for prose, labels, chips,
  or decorative eyebrows. Use it for measured values, code, and identifiers.
- The app action family uses local `24px`-viewBox outline vectors, `16/20/24px`
  roles, and one current-color stroke. Provider art is a separate asset with
  provider-specific usage rules; do not draw lookalike logos or recolor official
  marks.
- Display and section headings use Geist in both app and marketing. Commands, paths,
  code, IDs, budgets and measured values use Geist Mono; prose does not.
- Use the 4px spacing rhythm, preserving compact field groups and clear space
  between separate sections. Share alignment edges across repeated cards and
  page headings.
- Repeated settings rows and collapsible sections use the shared disclosure-row
  skeleton (`.summary-row` / `.summary-row-sm` in `style.css`): one grid of
  icon slot, copy, and trailing action, so peer rows keep identical left
  edges, copy sizes, and action placement, and a summary's padding matches the
  panel content it opens. Skins (borders, fills, radius) stay with the
  surface. Never nest a disclosure inside a disclosure: depth is capped at
  two levels (screen → disclosure → flat content), and a separate connection
  with its own sign-in is a peer of the access it relates to, never its child.
  A fallback-less `var()` reference must resolve to a defined token; the
  stylesheet token guard fails the build when it does not.
- Use real buttons, links, labels, headings, and landmarks. Keep keyboard focus
  visible, target 44px touch comfort for primary phone actions, and honor reduced
  motion. Use full-page or local scrolling deliberately; do not mask overflow.
- Hutch intentionally ships a fixed dark theme. It does not currently add a
  separate `prefers-contrast` palette; this is a product decision, not an
  unrecorded audit failure. Keep the existing visible focus treatment and
  `forced-colors` overrides, and reassess this choice if theme support changes.
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
### Setup recovery boundaries

Assistant setup stays in the current tab through navigation and reload. Flush the
latest edit before page exit, cancel pending persistence on discard/create, and
ask before replacing an existing draft with a template, duplicate or chat source.
A delayed create result must not take over the next page. Blank setups and runtime
switches do not grant tools; only explicit selections or reviewed templates do.
