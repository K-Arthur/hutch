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

Fleet and roster attention use authoritative bot lifecycle metadata as well as request discovery.
A failed queue refresh cannot hide a waiting bot, and human waits remain visible without an
approval request. The bot summary prefers executing/waiting work over older queued turns.
On phones the reminder occupies a layout row instead of covering cards or conversation content.

The shared composer has one options menu for suggestions, rehearsal and Enter behavior.
Rehearsal labels disclose that reads and model calls still happen; requests use the canonical
conversation command with idempotency. Stop is available in the header and individual attempt,
without an additional composer duplicate. Escape closes options and restores trigger focus;
Send/options and Stop targets are 44px on phones. Cancelled attempts use the server label
instead of a generic failed label, and recorded queue time remains visible without completed steps.
The main Stop targets the server-selected active attempt within the conversation, even after
new messages queue. That attempt and its approval stay visible beyond the six-attempt display
window. Failed refresh retains the review with an explicit stale-details notice and Retry.
A waiting conversation also exposes Review in the header. It scrolls and focuses the inline
request without focusing the composer; if the request is unavailable, it opens Needs you.

Transactional resource replay now refreshes visible chat, attention and roster after missed
notifications or reconnect. A history gap reconciles a fresh snapshot. Automatic updates do
not rebuild the composer/settings form; draft, focus and expanded review details remain local.
Admission commits its review event with the wait, and canonical decisions replace stale asks
even if the worker never emits a response. Desktop/tablet/phone fixtures suppress periodic
fallback and transcript hints, inject a gap, then observe another client's decision. They
verify local recovery behavior, not physical-device reconnection or user-completion rates.

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
