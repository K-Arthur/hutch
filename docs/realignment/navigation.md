# Conversation-first navigation

Decision: chat is the daily workspace. A single sidebar roster selects bots and opens their
settings; Studio owns conversation history and action decisions. The duplicate bot catalog
and Context configuration panel are removed from the small-workspace path. Memory,
permissions, instructions, schedules and defaults have one editing destination: bot settings.

The operator can answer approvals inline. “Needs you” opens the same cards in a modal drawer
without leaving the conversation or losing its draft. Requests from other bots remain
visible through a count, roster state and app-wide reminder; opening the drawer is explicit.
There is no bulk approve. The exact request, expiry, scope, irreversible/outward effects and
server-authoritative decision remain visible. New inline events carry the immutable action
hash; approvals use idempotent v1 commands. Old events without a hash first refresh the
persisted request for another review. Client expiry disables decisions without inventing a
server receipt. Refresh failures preserve requests and show an actionable error.

Monitor contains Activity and Run history. These answer different questions (what needs
attention now versus what happened), so combining them with conversation history would lose
useful inspection. At ten bots a searchable Fleet view also appears, with active, paused and
needs-you filters. Ten is a reversible product heuristic suggested by the operator, **not**
a measured cognitive threshold. Nine/ten fixtures verify the boundary; they do not establish
usability at hundreds of bots. No available customer telemetry establishes prevalence or
task-completion gains. Observe discoverability, bot-selection errors, missed requests and
queue handling in future real-user sessions before claiming those gains.

## Sources and acceptance scenarios

| Source (checked 2026-10-07) | Evidence class | Hutch response and verification |
|---|---|---|
| [Carbon UI shell guidance](https://www.carbondesignsystem.com/building-blocks/core/components/ui-shell-left-panel/guidelines) | Official design guidance; optional navigation panels, frequent switching, shallow hierarchy | One roster; secondary monitoring disclosure; no nested configuration tree. This supports the structure, not the ten-bot threshold. |
| [Open WebUI 27477](https://github.com/open-webui/open-webui/issues/27477) | Individual report of browser Back being trapped after navigation to forwarding routes | Small-workspace `#/bots` and `#/approvals` aliases replace their history entry. Browser Back returns to the prior Activity view. |
| [Open WebUI 30055](https://github.com/open-webui/open-webui/issues/30055) | Open request reporting an approval hidden under a mobile call overlay | Explicit queue above application overlays, reachable reminder and native dialog focus. Phone fixture answers inline and from the drawer. No voice/desktop overlay capability is claimed. |
| [Open WebUI 29050](https://github.com/open-webui/open-webui/issues/29050) | Closed, confirmed historical report of tool/skill selections accumulating when switching models | Bot and conversation switches isolate drafts and selected conversation; the existing model-override journey verifies the default remains unchanged. Hutch does not bind tools to models, so it does not reproduce the reported implementation. |

These reports establish concrete failure scenarios, not current comparative quality or rates
of affected users. The decision also follows observed Hutch redundancy: the prior Bots
cards exposed create/open/pause/settings already available through the roster and settings;
Context repeated settings memory and permissions. The previous welcome incorrectly said
“Nothing has run yet” in a new conversation, and roster status collapsed all active states
into “working.” Both now refer to authoritative conversation/run state.

## Compatibility and validation

Existing hash bookmarks and server redirect routes remain valid. A small `#/bots` workspace
opens Studio; `#/approvals` opens the drawer over Studio. Fleet retains individual actions;
pause and delete remain in settings for all workspace sizes. An approval link opens its
canonical conversation when available, or the historical run otherwise.

Browser checks are in `tests/e2e/test_browser.py`: legacy Back, nine/ten boundary, state/search
filters, immediate draft switches, inline phone approval, drawer focus/poll preservation,
refresh error/retry and server decision. Visual captures and inspection are recorded in
`navigation-visual-validation.md`. No real-phone, screen-reader, paid-provider or human timing
study was performed.
