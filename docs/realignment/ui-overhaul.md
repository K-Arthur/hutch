# Hutch all-surface UI overhaul

## Goal

Rework Hutch's app and marketing surfaces into one approachable personal-assistant
family. Keep chats primary, make routine tasks legible without technical
knowledge, keep advanced choices available when wanted, and preserve honest
permission, connection, waiting, and completion states. The app uses simple 2D
assistant identities; the marketing site may use the detailed 3D character.

## Acceptance

- One shared source for display/body/mono typography, semantic colors, icon sizes,
  control/card geometry, spacing, focus, status, and motion across Studio,
  Connections, server-rendered pages, and the website.
- Review each materially distinct page on its own, not only in a contact sheet.
  Cover desktop, tablet when layout changes, phone, and narrow-phone behavior.
- Make the first-use and everyday chat journeys friendly; creation carries the
  selected request forward, names are automatic and editable, and the technical
  setup remains optional.
- Keep assistant names to one line in the roster, provide one options control per
  assistant, and keep approvals and human waits visible with exact request details.
- Make provider identity recognizable without shipping marks beyond their
  published permissions. Keep local assets, no CDN dependency, and make the
  current support level clear.
- Improve empty, populated, loading, error, waiting, stopping, reconnecting, and
  completed states. Preserve keyboard use, focus return, reduced motion, and
  narrow-screen reflow.
- Update `DESIGN.md`, the design-system guide, requirements, changelog, and this
  evidence record with the actual changes and validation boundaries.

## Surface inventory

| Surface | Current review | Overhaul state |
|---|---|---|
| Chat / empty Studio | Individually reviewed at desktop, tablet, phone and compact phone; helper examples are collapsed below the message path | In progress |
| Chat / populated, choices, replies, attachments, waits | Existing interaction evidence available; refresh after shell redesign | Open |
| Assistant roster and one-action menu | One-line names, full-row selection and one grouped options menu checked at responsive sizes | Open |
| Assistant management for larger rosters | Cards simplified; phone overflow and long names checked independently | In progress |
| Assistant creation and identity | Request-preserving setup already implemented; visual simplification remains | Open |
| Assistant settings / advanced controls | Individually reviewed at desktop and phone | Open |
| Needs you / approvals / human checkpoints | Approval-first queue; optional browser notifications collapsed by default and available from one disclosure | In progress |
| Activity / schedules / history / task details | Activity independently reviewed; remaining pages to inspect | Open |
| Apps & AI / local and hosted model settings | Source-aligned desktop, tablet, phone, and compact-phone review; compact phone cards | Open |
| Preferences, sign-in, pairing, and server pages | Route coverage exists; independent visual review remains | Open |
| Marketing website | Full desktop and phone pages individually inspected | Open |

## Research and visual direction

The supplied ChatGPT screenshots and the Figma Community Bobo preview were used
as interaction references. Individual mobile list, chat, and options-menu frames
were opened in the Figma canvas. We use their clear chat hierarchy, bottom-fixed
composer, short list rows, and grouped per-chat actions as patterns; Hutch keeps
its own colors, copy, icons, and mascot artwork. Mobbin was not used because its
screen search was gated on the available plan.

The latest app captures show a large empty area around the Studio welcome, a
narrow settings card inside a wide canvas, an Activity clear-state that can feel
empty despite a task having run that day, and service cards that are tall and
generic on phones. The marketing page is long and technical on desktop and much
harder to scan on a phone. The redesign will use task-first copy, clearer page
rhythm, more useful illustrations/screens, familiar local icons, and optional
technical detail instead of increasing decorative chrome.

## Progress and evidence

### Type-system foundation and first route refinements — verified

Changed the app display roles to use the locally bundled Archivo variable font,
matching marketing headings while retaining system sans for readable interface
copy and system mono for measured values. Added the font to the app's static
assets with its OFL license, and updated the app/server-page declarations and
cross-surface browser assertions. `tests/e2e/test_design_system.py::test_shared_design_tokens_render_consistently_across_all_surfaces`
passes, including checks for the rendered Archivo face and local font readiness.

The app's 2D faces use two near-round ink eyes directly on each colored
silhouette. There is no visor, pale slit, or detached decoration. A dedicated
browser check verifies the eyes remain inside all eight different heads, retain
at least 3:1 contrast against each identity color, and match the selected
identity-picker preview. The eight enlarged faces and picker were inspected
individually at full size; the roster was reviewed at phone width. The marketing
site's original 3D mascot remains separate. This corrects the face treatment but
does not close the still-open roster, settings, or all-surface design reviews.

Studio's first-use copy now explains the approval promise without an extra panel,
and common tasks use result-oriented names. Activity adds up to three recent
completed tasks when history exists, so a quiet workspace does not appear empty
after work has run. Scheduled work now leads with the next occurrence and moves
cron syntax, timezone, and the missed-time choice into **Timing details**. Its
pause action uses plain language, and its empty state is sized to the actual
content. The long-name roster check confirms one-line ellipsis behavior, a full
name in the accessible title, and a selection background that reaches its single
options control.

The sidebar now uses a compact label size so common names, including
**Workspace Coordinator**, fit on one line at the default width. Only long
custom names shorten with an ellipsis; each assistant still has one options
button, and the selected highlight reaches it.

The populated-chat header now gives the assistant title available width and
moves **Assistant settings** into the existing chat options menu, leaving the
permanent toolbar focused on the conversation, search, review, and stop actions.
The inline approval card stays above the floating jump-to-latest control so its
review details remain tappable on a phone. A 1440px header regression and the
desktop/tablet/phone approval journey verify the layout and one-click decision.
Both levels of an approval review now retain their expanded state through the
live transcript refresh, including the optional exact-request disclosure.
Apps & AI now distinguishes the original Outlook inbox cue from the Gmail mail
cue rather than repeating the same envelope for both tiles; each still carries
its full service name and state.

**Still open:** the broad UI overhaul. The route captures and screenshots are
being refreshed against the current source; live-provider states, screen-reader
checks, physical phone checks, and packaged-installation font requests remain
separate verification gaps. Apps & AI, approvals, assistant setup, settings,
history, Preferences, server pages, and the marketing website still need their
own redesign review and acceptance.

A separate send-only Gmail setup has since been added under Connections with
its own account rows, sender address, permission label and per-assistant grant.
The fixture journey was visually inspected at desktop, phone and compact-phone
sizes and is recorded in `visual-validation.md`. This integration-specific
check does not close the broader Apps & AI redesign or any other open surface.

### Everyday setup copy and roster recheck — verified

Quick assistant setup now says it uses the saved AI choice, has no apps or
recurring work connected, and checks with the user before important actions.
Internal model IDs and routing mode stay in **Fine-tune the details**, where the
selected workspace model remains editable. A responsive browser check confirms
that saving the assistant does not start work. Separately, the roster check
verifies one-line names, ellipses for overlong names, a full accessible name,
and one options control per assistant.

Individually inspected current screenshots at desktop, tablet, and phone sizes
in [`artifacts/quick-setup-language-2026-10-10/`](artifacts/quick-setup-language-2026-10-10/)
and the sidebar at desktop and phone sizes in
[`artifacts/pinned-roster/`](artifacts/pinned-roster/). The focused browser checks
passed **2 tests** with no provider calls, external requests, or browser errors.
This is a narrow improvement; the separate review and redesign of every app and
marketing surface remains open.

The populated chat no longer prints a shortened internal run identifier beside
each assistant reply. A compact, screen-reader-labeled **View work details**
control opens the existing task-detail page, where the technical identifiers can
be inspected when needed. Its touch target grows to 44px on phones; the assistant
name, live status and stop action retain their own space. Desktop, tablet and
phone captures were inspected individually. The screenshot and trace evidence
is in [`artifacts/message-replies-clean-chat-2026-10-10/`](artifacts/message-replies-clean-chat-2026-10-10/).
This chat refinement does not close the populated-chat redesign or the full
all-surface overhaul.

Connections now shortens its five app/model cards on narrow screens without
hiding their explanations or statuses: app marks shrink to 40px, descriptions
stay with the service name, and each action keeps a 44px target. The first
source-aligned desktop, short-desktop, tablet, phone, and compact-phone captures
also exposed that older `assistant-first-ui` screenshots lack source hashes and
show a shorter **Outlook** label and marks that do not match today's source.
Those older images remain historical context; the current capture set is
[`artifacts/app-catalog-source-aligned-2026-10-10/`](artifacts/app-catalog-source-aligned-2026-10-10/).
This improves phone scanning and fixes the evidence boundary, but Connections
and its deeper account flows still need a complete redesign review.

### Mascot face redraw after owner review — verified

Replaced the visor and slanted pale marks with two simple ink oval eyes, fitted
individually to the orb, capsule, bean, drop, pebble, shield, triangle, and hex
silhouettes. The owner-provided reference favored a plain 2D face; the separate
3D mascot remains on the marketing site. The picker and live avatar use the same
paths.

`tests/e2e/test_design_system.py::test_flat_mascot_eyes_stay_inside_every_silhouette`
passed **1 test in 7.84s** in Chromium **153.0.8010.12** / Playwright **1.63.0**.
The check measured eye paths against each head, verified balanced pairs and at
least 3:1 eye-to-body contrast, confirmed picker/avatar parity, and checked
44px choices and phone reflow. I inspected all eight enlarged shapes, the picker,
and the phone roster individually. Current captures, validation metadata, source
hashes, and trace are in
[`artifacts/mascot-eye-review-2026-10-10/`](artifacts/mascot-eye-review-2026-10-10/).
This is a mascot correction, not completion of the broader app and marketing
redesign.

The pinned sidebar roster was rechecked after the face change. Long custom names
stay on one line and truncate only as needed, short everyday names remain whole,
and the selected background reaches the one ellipsis control. Pin and settings
still share that menu. The focused browser journey passed **1 test in 7.75s**;
desktop, tablet and phone captures in
[`artifacts/pinned-roster/`](artifacts/pinned-roster/) show the long name and
selected row individually. This confirms the sidebar behavior; the wider
all-surface redesign remains open.

### Larger-roster card simplification — verified

Assistant cards now lead with a one-line name, status, short description and an
**Open** action. Repeated schedule and action-access chips were removed; model,
schedule, access, recent activity and usage remain available in one collapsed
**Details** section. The existing single ellipsis menu still groups pause/resume
and assistant settings. Long names ellipsize without wrapping and retain their
full `title` and text for accessibility.

The independent route capture exposed a real mobile sizing defect: an
assistant card's minimum-content width reached 617px inside a 390px phone
viewport while an outer scroller hid the overflow. A card-boundary regression
now verifies every card fits the viewport at desktop, tablet, phone and
compact-phone widths. The all-surface Chromium test passed **1 test in 16.65s**;
I inspected the roster at desktop, tablet, phone, plus the long-name card on
phone and compact phone individually. Updated route captures and source hashes
are in [`artifacts/ui-surface-review/`](artifacts/ui-surface-review/). No
external or provider requests were made. The separate Fleet search, pause/resume
and waiting-approval fixture journeys also passed **3 tests in 5.92s** after the
existing tests were updated to the current **Manage assistants** and **assistant**
labels. Desktop and phone attention captures are in
[`artifacts/fleet-attention/`](artifacts/fleet-attention/). This improves Fleet
but leaves the all-surface overhaul open.

The task-details fixture now includes a committed assistant reply with its
completed run, rather than showing a **Done** state without an answer. Desktop,
tablet and phone captures were inspected separately; the browser test confirms
the reply is read from the saved transcript. This is synthetic completion
content and makes no model or provider call.

### Empty Studio helper examples — verified slice

The empty chat now keeps messaging as its clear primary action. Reusable-helper
examples live in one collapsed **Create a helper from an example** disclosure;
its subtitle says messaging starts work, and the open state explains that an
example only opens setup. The previous six large gradient banners became compact
rows with small shape-aware 2D identities, short results-oriented names, and a
clear setup affordance.

The focused Chromium check passed **1 test in 10.76s** at desktop
**1440×960**, tablet **900×1024**, phone **390×844**, and compact phone
**320×740**. It verifies collapsed-by-default behavior, keyboard expansion,
the six expected helper names, no horizontal overflow, the final item remaining
above the composer, setup opening without creating an assistant or run, and the
gallery surviving background refresh. A 320px text-spacing override also
preserved reflow and composer access. I inspected the collapsed and expanded
captures individually and inspected the desktop setup dialog. The fixtures made
no provider or external requests. Evidence is in
[`artifacts/studio-helper-gallery-2026-10-10/`](artifacts/studio-helper-gallery-2026-10-10/).
This is one Studio improvement; the all-surface overhaul remains open.

### Approval queue hierarchy — verified

The **Needs you** drawer now leads with pending decisions and uncertain action
outcomes. Optional browser-notification controls sit in a collapsed
**Browser notifications** disclosure, whose summary still reports **On**,
**Off**, **Blocked**, or **Unavailable**. The review queue, notification setup,
and notification click-through retain their prior behavior; no chat or action
details enter the operating-system notification.

The focused approval and route batch passed **4 tests in 30.46s** with Chromium
**153.0.8010.12** and Playwright **1.63.0**. It checks that the settings
disclosure starts closed, its summary distinguishes On/Off/Blocked/Unavailable,
a notification opens the pending request, review focus survives refresh, chat
approval remains actionable, and the responsive route suite has no horizontal
overflow. I inspected the expanded settings and pending approval screenshots
independently at desktop and phone sizes. These use a local notification stub
and fixture approvals; there was no operating-system prompt, provider request,
or real notification. The approval and human-wait redesign remains open beyond
this queue refinement.

### Next

1. Finish Studio's initial and active-chat layouts, then separately review the
   phone composer, choice cards, replies, attachments, and human-wait states.
2. Review the app shell and assistant roster actions at wide and compact sizes;
   preserve the verified one-line name, single options menu, and full-row selection.
3. Redesign and individually validate Apps & AI, approvals, assistant
   setup/settings, Activity, schedules, history, Preferences, and server-rendered
   pages using the shared tokens.
4. Rework and validate the marketing page for a shorter, clearer consumer story while keeping
   the 3D mascot, public CTAs, and truthful support labels.
5. Re-run changed journeys and save current-source screenshots plus traces for
   each materially distinct page and key state. Update this matrix as each page
   is completed; the full overhaul remains open until then.
