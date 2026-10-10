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
| Chat / empty Studio | Individually reviewed at desktop and phone | Open |
| Chat / populated, choices, replies, attachments, waits | Existing interaction evidence available; refresh after shell redesign | Open |
| Assistant roster and one-action menu | Independently reviewed in app captures and user references | Open |
| Assistant creation and identity | Request-preserving setup already implemented; visual simplification remains | Open |
| Assistant settings / advanced controls | Individually reviewed at desktop and phone | Open |
| Needs you / approvals / human checkpoints | Existing responsive evidence; refresh after component redesign | Open |
| Activity / schedules / history / task details | Activity independently reviewed; remaining pages to inspect | Open |
| Apps & AI / local and hosted model settings | Apps & AI independently reviewed at desktop and phone | Open |
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

The app's 2D faces now use upright oval eyes fitted to each silhouette. The
mascot containment, picker-parity, roster, and shared-token browser checks pass
(3 focused tests total). The face previews were individually inspected. The
marketing site's original 3D mascot remains separate.

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
