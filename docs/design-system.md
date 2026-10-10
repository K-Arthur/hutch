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
| UI body / measured data | system sans / system mono | Language versus machine values |
| App type roles | `0.9375rem` body / `1rem` reading / `1.5rem` page title | Responsive hierarchy that respects browser text scaling |
| App icon family | `16 / 20 / 24px`, `24px` view box | Local category vectors in 48px service-tinted tiles; names and states stay visible |

The marketing site keeps Archivo for display and section headings and uses the
locally bundled 3D Hutch mascot. Product body text uses the same system sans as
Studio. The app uses compact flat 2D assistant characters; each distinct head
shape gets a matched pair of softly tapered light eyes with a fine dark edge.
Round, leaning, tapered and pointed forms therefore get different eye size,
spacing and height while keeping one shared tilt and rhythm. The picker previews
the same face. There are no separate pupils or mouth. Status is shown separately.
Brand art, assistant identity, and runtime state never substitute for one another.

## Surface roles

### Chats and assistants

The chat is the daily workspace. Keep the active conversation and current work
prominent, with approvals and human waits visible in context. Use a searchable
Bot roster with the coordinator and attention states first. Each Bot has one
options menu for pinning and settings; idle, unpinned Bots collapse only when a
workspace has ten or more Bots. Long custom names stay on one line and end with
an ellipsis in the roster; the full name remains available on the assistant row.

The large **Fleet** view keeps the default card human-readable: assistant name,
readiness, description, schedule cadence, and the action-approval expectation.
Provider/model identifiers, exact schedules, last-run information, estimated
tokens, and saved-note counts are grouped under one **More details** disclosure.
Pause/resume and settings stay in one options menu, so a large roster does not
turn into a wall of controls or infrastructure metrics.

Assistant creation should reuse the request that led to the creation flow,
suggest a short role-based name that the owner can edit, and keep the first path brief.
Advanced model, permissions, schedule, workspace, and memory controls remain
available as optional customization. Do not ask users to restate a task already
present in the source conversation.

The empty first-run screen offers a few illustrated starter requests, such as
planning a week, catching up on email, or organizing a project. Selecting one
fills the request field; it never starts work or creates an assistant by itself.
Use a consistent local outline-icon family for actions and categories, with
plain-language labels beside them. Apps & AI uses original Hutch-colored
calendar, mail, inbox, sparkle, cloud, and monitor category glyphs in softly
colored 48px tiles beside exact service names. Microsoft Outlook is named fully.
These are not provider logos; branded artwork stays out until permission for app
and marketing use is documented. Keep provider, model,
permission, and runtime terminology in the relevant optional detail layer.

Assistant settings lead with the editable name and what the assistant helps with.
Standing directions and the rest of the controls sit behind one clearly named
disclosure with a meaningful icon, so people do not face a long technical form
when they only want to rename an assistant. AI, app access, scheduling, safety,
workspace, memory, and usage remain available when they choose to customize.
A workspace with only one assistant does not show a coordinator choice.

For an empty conversation in an existing assistant, lead the template gallery
with familiar jobs such as organizing files, following up after a meeting, and
reviewing the week. Give cards short task names instead of exposing internal
template IDs; preserve the IDs only in the action and saved configuration.

Approvals appear in the chat where the action was requested and remain available
in the dedicated queue for review at scale. Lead with the action and consequence;
keep exact arguments and destination reviewable; never hide an approval behind a
generic notification or rely on color alone.

### Apps, activity, and settings

Chats and the in-app Apps & AI, Models, Usage, and other views share one
workspace sidebar, contextual header, system type, emerald actions, azure focus,
solid graphite surfaces, and 8px/12px control-panel geometry. Sign-in, pairing,
and remaining server-rendered pages load the same generated semantic tokens and
map their components to that contract. Service categories use the same locally
drawn outline glyphs across the app and marketing site. Provider names and
connection states remain explicit; provider artwork requires documented rights
before it is bundled. The AI tile uses Hutch's generic sparkle rather than an
imitation of the OpenAI Blossom ([OpenAI brand guidance](https://openai.com/brand/)).
The first layer explains the useful choice; detailed scopes, OAuth setup, and
account controls stay inside the optional **More account settings** disclosure.
Never make a provider mark the only label. Avoid a separate brand palette, blue
primary actions, glass panels, or square-button overrides.

### Marketing site

The site keeps its editorial page composition and larger original 3D mascot.
System sans body text, brand/focus/status colors, controls, panel corners, and
semantic labels carry through from the app. Use Archivo where display hierarchy
needs its distinctive voice. Marketing claims, screenshots, CTAs, and support
labels must reflect verified product behavior; do not use executor credentials,
local-host access, or fixture-only states in public flows.

## Typography, spacing, and behavior

- The app uses a system-sans stack and named type roles: `0.9375rem` interface
  body at `1.55` leading; `1rem` reading text at `1.65`; `1.5rem` page titles;
  and `1.125rem` section titles. Use rem units so user text scaling remains
  effective.
- App captions start at `0.75rem/1.45`. Do not use mono for prose, labels, chips,
  or decorative eyebrows. Use it for measured values, code, and identifiers.
- The app icon family uses local `24px`-viewBox outline vectors, `16/20/24px`
  roles, and one current-color stroke. Keep exact provider names beside generic
  category glyphs; do not draw lookalike provider logos.
- Display and section headings may use Archivo on the marketing site. IDs,
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
