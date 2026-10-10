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

The marketing site keeps Archivo for display and section headings and uses the
locally bundled 3D Hutch mascot. Product body text uses the same system sans as
Studio. The app uses compact flat 2D assistant characters; each distinct head
shape gets a slightly uneven pair of dark oval eyes fitted to its face. Round,
leaning, tapered and pointed forms therefore get different eye size, spacing,
height and tilt, and the picker previews that same face. The app face stays
minimal, with no separate pupils, white eye highlights, or mouth. Status is
shown separately. Brand art, assistant identity, and runtime state never
substitute for one another.

## Surface roles

### Chats and assistants

The chat is the daily workspace. Keep the active conversation and current work
prominent, with approvals and human waits visible in context. Use a searchable
Bot roster with the coordinator and attention states first. Each Bot has one
options menu for pinning and settings; idle, unpinned Bots collapse only when a
workspace has ten or more Bots. Long custom names remain available to assistive
technology and are clamped to two lines in the roster.

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
Use recognizable local service marks and small line icons as helpful cues, with
plain-language labels beside them. Keep provider, model, permission, and runtime
terminology in the relevant optional detail layer.

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
map their components to that contract. Familiar local vector marks identify
calendar, mail, and AI choices beside plain-language names and connection states.
The AI tile uses Hutch's generic spark mark rather than a recolored imitation of
the OpenAI Blossom; provider marks must remain accurate, secondary, and within
their owner's brand rules ([OpenAI brand guidance](https://openai.com/brand/)).
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

- Body text uses the shared system sans. Operator prose defaults to 14px with
  1.55 leading; longer marketing copy can use its larger editorial scale.
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
