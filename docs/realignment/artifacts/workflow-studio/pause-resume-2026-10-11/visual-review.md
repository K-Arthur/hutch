# Workflow pause and resume visual review

Date: 2026-10-11. Surface: owner Studio chat card, paired-phone supervision view,
and the private-preview marketing teaser/availability row. This is a human review of
opened Chromium captures, not a full accessibility certification.

## Owner Studio

The browser suite captured and opened owner views at 1440×960, 768×1024, 360×800
and 320×800 CSS pixels in Chromium 153.0.8010.12. The active-pause path used the real
SQLite store, workflow supervisor and versioned HTTP API, with a test event holding a
real in-flight transform. It made no model-provider calls and raised no page errors.

The **Running** card offers **Pause after current work** beside Stop and Refresh. A
long, slug-form plan name is rendered as a readable title. After the owner requests a
pause, **Pause requested** stays visible and a short note explains that current work
will settle before the next step is held. The Pause control disappears while the
request drains; the interface does not imply that work has already stopped. At 360px
and 320px, that note wraps cleanly above Stop and Refresh. The browser observed the
first transform settle, confirmed that the second step had not started, then resumed
and observed successful completion.

At desktop and tablet sizes, the card actions remain grouped in the header. At phone
and compact-phone sizes they wrap into a vertical stack. The Pause and Resume targets
measure 44px high at 360px and 320px; each tested viewport has 0px horizontal overflow.
At 768px the long title wraps without colliding with the action group. The 1440px
parked card keeps the title readable alongside Amend, Resume, Stop and Refresh. The
inspector retains its bounded internal scroll, so later discovered instances remain
available without displacing the chat composer.

The separate parked-question browser journey verified answering while paused,
no downstream progress until Resume, a fresh attempt after Resume, and Stop clearing
pause intent. It also checked keyboard focus as the action changes. The paired-phone
workflow view shows **Pause requested** while a child remains active and **Paused** after
it settles, lists durable questions, and does not expose owner-only Pause/Resume actions.
The opened pause-requested view is `docs/realignment/artifacts/workflow-studio/phone/workflow-pause-requested-390.png`;
phone credentials receive 403 for owner Pause/Resume mutations.

## Marketing site

The updated workflow teaser and availability row were opened at 1440, 768, 360 and
320px. The “How it helps” sequence and dark/green Hutch styling remain intact. The
additional private-preview explanation is legible in the desktop card and stacks into
one column at phone sizes; the 320px capture has no horizontal clipping. The
availability row marks workflows **Experimental** and keeps the provider/model limits
in copy. The browser test observed no page errors or external requests.

## Evidence and scorecard

The test run uses the real browser and API paths, but test-controlled transforms and
phone credentials; it does not establish provider quality, production performance,
screen-reader behavior or public availability. Source hashes, per-state bounds, result
transitions and screenshot/trace hashes are in `active-pause-results.json`; the parked
question journey remains recorded in `results.json`. Website screenshot and source
hashes are in `docs/realignment/artifacts/dynamic-workflows/marketing/results.json`.

Scores follow the project's shape-and-background review weighting (aesthetic 45%,
functionality 40%, regression health 15%). Human judgments are marked as such.

| Dimension | Score | Basis |
|---|---:|---|
| Aesthetic *(human)* | 8.8/10 | The existing card hierarchy, type and colors remain consistent; humanized titles and the pause explanation improve scanning. The compact panel still relies on its established internal scroll. |
| Functionality | 9.5/10 | Real browser flow covers a running-node pause, parked pause/resume, answer-while-paused, Stop, owner/phone boundary, conversation-bound plan display, website claims, and all four CSS widths. |
| Regression health | 9.2/10 | Focused API, migration, phone and browser checks pass; captures record 0px overflow, 44px phone actions and no page errors/provider calls. |
| **Combined** | **9.1/10** | Weighted score; this supports local behavior and layout only. |

Not covered: real screen readers, physical devices, browser-chrome zoom, actual text
spacing overrides, forced-colors behavior for this new pause state, slow/offline
reconnect, or public website availability. The one-shot Impeccable detector reported
only existing advisory findings outside the edited rules and copy.
