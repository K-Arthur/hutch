# Run log: agenda and notifications (2026-10-31)

Second pass on the personal-operations initiative, closing G01 (read-only agenda for Today) and
G05 (outbound notifications). Local main; nothing pushed. Another session was committing and
leaving uncommitted work in the same checkout throughout, so every number below says which tree
it was measured on.

## Baseline

| Check | Command | Result |
|---|---|---|
| Working tree | `git status --short` | 20 modified + 8 untracked from another session (model picker / assistant removal), preserved untouched |
| HEAD at start | `git log --oneline -1` | `5ad942ab` |
| Focused baseline | `pytest -q tests/test_personal_api.py` | 8 passed before any change; the only failure afterwards was this slice's own `not_included` wording assertion, updated deliberately |

## Milestones

### M1: agenda builder and adapters (bb992832)

- `src/hutch/personal/agenda.py` (258 lines) is a pure builder over injected readers. No model
  call, no store handle, no provider import, no write. Per-item and per-source source label, fetch
  time, age and stale flag; explicit `not_configured` / `grant_missing` / `grant_expired` /
  `mail_requires_local` / `provider_error` reason codes.
- `src/hutch/personal/agenda_sources.py` (168 lines) is the only adapter to grants, OAuth account
  records and provider clients; it reuses `GoogleCalendarBook.list_events` and
  `GoogleMailBook.list_messages` and applies the Gmail tool's Local-inference rule.
- `GET /api/v1/personal/agenda/sources` and `GET /api/v1/personal/agenda` are read-only: no
  idempotency key, no body, no store write. Unknown assistant 404, bad zone 422.
- Today's Agenda card carries the source label, the read time, and the stale / unavailable /
  not-configured states. `personal.css` keeps 320 px free of horizontal overflow.

Commands and results:

- `pytest -q tests/test_personal_agenda.py` -> 11 passed (14 after the review fixes).
- `pytest -q tests/test_personal_api.py tests/test_personal_agenda.py` -> 19 passed.
- `pytest -q tests/e2e/test_personal_today_agenda.py` with
  `HUTCH_TEST_ARTIFACTS_DIR=.pipeline/personal-operations/2026-11/evidence` -> 2 passed.

### M2: notifications through the existing outbox (614c331f)

- `src/hutch/notification_schema.py` adds `notifications` and rebuilds `channel_deliveries` so a
  row references an inbound event or a notification, never both. Three triggers write the row in
  the same transaction as the fact.
- `src/hutch/channels/outbox.py` holds the delivery half of `ChannelBook` (`OutboxMixin`): the
  module was over the 400-line cap after the additions, so it was split rather than extended.
- `ChannelService.once` reuses one lease and one sender for replies and alerts; `_deliver` is the
  single send path. `notification_id` is unique, an alert is queued only while recent and still
  true, and an uncertain send is never resent automatically.
- `GET /api/v1/notifications` and Today's "Alerts" section expose kind, subject id, machine reason
  code and outbox state.

Commands and results:

- `pytest -q tests/test_notifications.py` -> 7 passed, then 9, then 12 after added coverage.
- `pytest -q tests/test_channels.py tests/test_migration.py` -> 76 passed.
- `pytest -q tests/test_channels.py tests/test_migration.py tests/test_bot_deletion.py
  tests/test_bot_deletion_schema.py tests/test_durable_changes.py tests/test_state_snapshot.py`
  -> 9 failed, 118 passed; all 9 were the deletion fixture's missing `channel_id` and passed after
  the fixture fix (22 passed for the two deletion files).
- Full non-e2e suite attempt #1 (before the review fixes) was invalidated by `/tmp` reaching 100%
  on a 12 GB tmpfs: 140 failed / 294 errors, all of files whose fixtures write to `TMPDIR`. The
  same files pass in isolation and in a disk-backed run, so the run is recorded as void rather
  than as a regression.

### M3: docs, site and evidence (4a95f39e)

- `docs/commitments.md`, `docs/operations.md`, `docs/channels.md`, `docs/architecture.md`,
  `docs/roadmap.md`, `docs/marketing-site.md` and the site's Today section describe what exists
  and state the non-claims. The site's Today grid gained a fourth card and now has an explicit
  two-column variant (`.review-flow-pair`); `styles.min.css` was rebuilt and restamped.
- Evidence: `.pipeline/personal-operations/2026-11/evidence/personal-operations-agenda/`
  (1440, 834, 390, 320, stale, unavailable, alerts, 200 percent zoom).
- `pytest -q tests/e2e/test_website.py -k "today or responsive or section"` -> 2 passed, 1 failed.
  The failure is `test_dynamic_workflow_marketing_is_truthful_and_responsive`, which asserts site
  copy that the other session's commit `2ba2f7eb` changed (`git log -S` on
  `workflow execution itself remains unverified` -> `2ba2f7eb`). Pre-existing and out of scope.

## Independent verification

A read-only reviewer agent, in a separate context, ran the focused suites and inspected the diff.
It confirmed:

- one delivery path only; `sendMessage` appears only in `channels/telegram.py`;
- no automatic resend of an uncertain send;
- no path where provider text reaches a model or is interpreted as an instruction;
- `grant_missing` / `grant_expired` routing and the 404/422 route contract;
- the v86 rebuild is lossless and refuses an orphan.

It raised one MAJOR and eight MINOR findings. `ac5e6f04` fixes the code ones and corrects the docs
that overstated the rest:

| # | Finding | Resolution |
|---|---|---|
| 1 | MAJOR: a `grant_expired` fell back to `stale` **with items**, so a disconnected account kept rendering for an hour | Only a provider failure may reuse a snapshot; grant reasons discard it in the same request. Regression test covers all three grant reasons, a mid-read failure, and the one-hour bound. |
| 2 | MINOR: a non-JSON `doc` made the triggers abort the status write | Both document-reading triggers now require `json_valid(NEW.doc)`; test writes a malformed doc and asserts the status row changes with no alert. |
| 3 | MINOR: API said `pending` where Today said "Not sent" | Both surfaces now report `not_queued`; a test asserts equality. |
| 4 | MINOR: a deleted assistant's alerts stayed visible for 7 days | Both read paths require the assistant to still exist. |
| 5 | MINOR: the provider-supplied calendar name bypassed the text bound | Bounded and control-character stripped like every other provider string. |
| 6 | MINOR: "in memory for at most one hour" was not enforced | The cache now drops entries it can no longer show. |
| 7 | NIT: "Alerts Hutch sent" listed alerts never sent | Renamed to "Alerts". |
| 8 | NIT: untested 422 branch, page-scoped counts | Recorded as a known gap; not fixed here. |
| 9 | NIT: `recent()` did not select `channel_id` | Fixed (the column is selected). |

Post-fix runs:

- `pytest -q tests/test_personal_agenda.py tests/test_notifications.py` -> 29 passed.
- `pytest -q tests/test_channels.py tests/test_channels_api.py tests/test_personal_api.py
  tests/test_bot_deletion.py tests/test_bot_deletion_schema.py tests/test_migration.py
  tests/test_commitment_tools.py tests/test_commitments.py tests/test_spaces.py
  tests/test_navbar_consistency.py tests/test_approval_cas.py` -> 156 passed.
- `pytest -q tests/e2e/test_personal_today_agenda.py` -> 2 passed.

## Gate status

`npm run check:agent` in the shared checkout now reports four frozen files above their baseline
(`cli.py` +88, `engine.py` +33, `providers/ollama.py` +50, `store.py` +15). None of that growth is
this slice's:

- the working tree also holds another session's uncommitted model-picker and removal work in
  `cli.py`, `engine.py`, `ollama.py` and `store.py`;
- at a clean detached worktree of HEAD (`1f9aa0c3`), context hygiene passed (924 source files, 117
  frozen files), constitution passed and the agent map check passed. The tool-contract audit
  could not run there because that worktree has no installed environment; it passes in the main
  checkout (44 registered tools).

This is recorded as a gate blocked by concurrent uncommitted work, not as a green gate. It goes
green when that session's changes are staged or reverted.

## What was not verified

- No live Google or Microsoft account, and no live Telegram bot. The agenda's provider path and
  the alert send path are exercised with fakes and a fake transport.
- The full non-e2e suite post-fix is recorded in the run above only when it completes; anything
  short of a complete green run is reported as such, not extrapolated.
- No exactly-once claim for any external effect, and no claim that a delivered alert was read.
