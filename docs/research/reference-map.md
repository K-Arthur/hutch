# Reference map — Grok Bot, dots, and documented failures (verified Oct 7, 2026)

Four columns: **observed pattern → evidence → Hutch equivalent → intentional decision.**
Labels are used throughout: **[observed]** = seen in a primary source this session,
**[fixed]** = a change the vendor already shipped (not a current defect), **[inferred]** = a
reasonable reading of a primary source, **[Hutch]** = our own design decision.

Primary sources checked this session (fetched 2026-10-07; GitHub issue bodies, comments, and the linked mobile-fix PR rechecked directly through the GitHub connector):

- Grok Bot changelog — <https://x.ai/changelog/bot> (latest v0.68.1, Oct 7 2026)
- Open WebUI issue #31656 — iPhone keyboard on menu/dropdown — **Closed**; fix PR #31657 merged
  2026-09-30, iOS 26.4/Safari, `dev` @4ef7e35
- Open WebUI issue #30055 — mobile Call-mode overlay hides a pending `ask_user` — **Open**,
  enhancement, opened 2026-09-15, v0.11.3; maintainer confirmed the layout gap and clarified that the tool times out
  after 60–240 seconds rather than hanging indefinitely
- OpenClaw issue #138499 — a session-owned CLI task outlived its timed-out cron run — **Open**,
  one reported instance, reproduction conditions listed as insufficient information by the reporter

Not inspected this session: the authenticated Grok Bot desktop app, dots, or the guide pages
(no access / not fetched). Anything below that would require those is marked as a gap.

| # | Observed pattern | Evidence | Hutch equivalent | Intentional decision |
|---|---|---|---|---|
| 1 | Composer status avoids the Bot's name while working ("Thinking it through", "Working on your computer") **[observed]** | Grok Bot changelog v0.67.0 | Studio typing indicator previously read "`<bot>` is working…" | **[Hutch]** Drop the name from the indicator ("Working…") so a repeated name is not re-read while a busy region updates; the bot identity is already in the chat header. |
| 2 | Sending shows "sent right away"; a progress bar appears only after ~2s **[observed]** | Grok changelog v0.57.0 | Composer disables Send and swaps to "Running…" on submit | **[Hutch]** Keep the immediate local acknowledgement; the transcript's accepted/delivered distinction is a remaining backlog item (no fabricated "delivered"). |
| 3 | Switching chats no longer flashes an empty transcript; scrolled-back messages survive reconnect **[fixed]** | Grok changelog v0.68.0 | Studio re-renders the whole feed per poll and scrolls to bottom | **[Hutch]** Bounded live region + lifecycle announcer added; preserving scroll/draft across bot switches is a documented remaining item. |
| 4 | Chat + message box stay in a centered column on wide windows **[observed]** | Grok changelog v0.59.0 | 3-pane studio with a centered conversation column | **[Hutch]** Matches — conversation stays readable; the context inspector is optional. |
| 5 | Approval card states whether an Ask-first rule paused the action and quotes the instruction **[observed]** | Grok changelog v0.68.0 / v0.67.0 | Approval card: action text + detail JSON + TTL | **[Hutch]** Keep plain-language action first, technical detail one expand away; no change needed to match the pattern. |
| 6 | "Waiting for you" is a distinct state from working **[observed]** | Grok changelog v0.67.0–v0.68.0 | `waiting_approval` is active but not computing | **[Hutch]** The working indicator is suppressed for `waiting_approval`; approval is announced through the bounded live region. |
| 7 | Screen readers announce suggestions/new questions/authors; focus stays in full-screen viewers **[observed]** | Grok changelog v0.58.0 | Whole `<main>` was `aria-live`, re-announcing every poll | **[Hutch]** Replaced with a bounded `#live-status` region (lifecycle only); this is the core a11y fix of this pass. |
| 8 | Sidebar preview never goes blank for forms/photos/approvals **[fixed]** | Grok changelog v0.57.0 | Bot rail shows an avatar + status dot | **[Hutch]** Acceptable; rail previews are a possible enhancement, not a defect. |
| 9 | Mobile overlay (Call mode) can hide a pending human question even though the event arrived **[observed]** | Open WebUI #30055 (open; maintainer confirms layout gap) | SPA has no full-screen Call mode; approvals live in the feed and the Approvals view | **[Hutch]** Keep approvals reachable from any route; an app-wide attention model (badge + reachable queue) is present. Surfacing questions above a full-screen overlay remains an acceptance scenario, including the documented 60–240s cancel timeout. |
| 10 | Menus/dialogs must not summon the mobile keyboard by moving focus into a text field without a tap **[observed, fixed upstream]** | Open WebUI #31656 (closed by merged PR #31657) | SPA navigation drawer focus path | **[Hutch]** Escape closes the drawer and restores focus to its toggle; regression is in `tests/e2e/test_browser.py`. |
| 11 | Big images/JSON/Markdown must not freeze the app; long chats scroll to the top **[fixed]** | Grok changelog v0.68.0 / v0.51.0 | Tool output is clipped behind "Show more" | **[Hutch]** Capped output wells already match the pattern; long-history virtualization is a documented perf backlog item. |
| 12 | Stop ends a stuck step within ~30s; Stop also stops handed-off work **[observed]** | Grok changelog v0.68.0 / v0.56.0 | Per-run Stop; server-authoritative resolution | **[Hutch]** Stop is a plain, confirmed POST that must never silently fail — keep. |

## What this changed in the code

- **#1** → `typingHtml()` now renders "Working…" without the bot name.
- **#7** → `#live-status` bounded announcer; `<main>` is no longer a live region.
- **#6/#9** → the working indicator is suppressed for `waiting_approval`, which is announced instead.

## Gaps (not verified / blocked)

- Authenticated Grok Bot screens and the dots interface were not inspected; rows 1–7 rely on the
  vendor changelog, which records behaviour but not pixels.
- No screen-reader pass was run this session (NVDA/VoiceOver/TalkBack unavailable). Automated
  assertions (axe-style checks) and keyboard paths only.
