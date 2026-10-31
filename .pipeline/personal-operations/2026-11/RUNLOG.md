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
  on a 12 GB tmpfs; see "Full non-e2e suite attempt #1 (void)" below.

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

## Full non-e2e regression (post-fix, disk-backed TMPDIR)

Command: `TMPDIR=~/.hutch-tmp/full3 UV_CACHE_DIR=/tmp/uv-cache uv run --frozen --no-sync pytest -q
--no-header --tb=line --ignore=tests/e2e -p no:cacheprovider`.

Result: **4,719 passed, 63 skipped, 3 xfailed, 6 failed** in 32m28s.

Every failure is attributed below; none is in this slice's files (`git diff --stat` at the time of
the run shows the concurrent session's work only: `cli.py`, `engine.py`, `providers/*`,
`modelview.py`, `pages_models.py`, `store.py`, `presets.json`, `tests/fakes.py`,
`tests/test_models_layer.py`).

| Failure | Attribution |
|---|---|
| `test_context_hygiene::test_real_repository_has_no_context_violations` | `cli.py`, `engine.py`, `providers/ollama.py`, `store.py` and `tests/fakes.py` are grown by the other session's uncommitted work at the time of the run. The same audit passes at a clean detached worktree of the committed tip; exact figures under "Gate status". |
| `test_emoji_audit::test_repository_is_emoji_clean` | The only violations are in `.codewhale/state/subagents.v1.json`, the agent runtime's own untracked state. That file is excluded by `.codewhale/state/.gitignore` and nothing under `.codewhale/` is tracked (`git ls-files .codewhale` -> 0). `scripts/audit_emoji.py` walks the tree with `rglob` and its `SKIP_DIRS` does not include that directory. Recorded as an audit-scope edge, not a content violation. |
| `test_models_layer::test_vision_needs_a_vision_model_and_is_hosted_only_on_small_machines` | The other session is editing `data/presets.json` (vision description), `providers/base.py`, `modelview.py` and `tests/test_models_layer.py` while the run was in flight. The file passes on its own (23 passed). |
| `test_remote_pairing` (two tests) | Port 8787 is held by a running `hutch serve` (PID 2171206), the same environment limit the 2026-10 RUNLOG records. |
| `test_routes::test_a_default_that_cannot_run_is_refused` | Fails standalone too, and asserts that `opencode/opencode/big-pickle` is refused with 422 while the tree answers 200 / `configured: true`. That is the other session's uncommitted route/capability change; the 2026-10 RUNLOG records the same failure for the same reason. |

## Full non-e2e suite attempt #1 (void)

The first attempt (before the review fixes) ran with `TMPDIR` on the 12 GB `/tmp` tmpfs. It
reported 140 failed / 294 errors, every one of them a fixture trying to write to a full disk. The
same files pass in isolation and in the disk-backed run above, so that run is recorded as void
rather than as a regression, and every later run uses `~/.hutch-tmp`.

## Gate status

`npm run check:agent` in the shared working tree fails context hygiene on frozen files grown by
another session's uncommitted work. At the tip as of this record that is five files: `cli.py`
(+91), `engine.py` (+30), `providers/ollama.py` (+82), `store.py` (+15) and `tests/fakes.py` (+52).
None is this slice's; this slice's only `store.py` change is line-neutral (two imports and the
migration-list entry swapped in place), and the committed `store.py` at `227b1c89` is still 12593
lines, its baseline.

Measured at the committed tip, in a clean detached worktree of `227b1c89` with its own environment:

| Check | Result |
|---|---|
| `python scripts/audit_context_hygiene.py` | passed (931 source files; 117 frozen over-cap files) |
| `python scripts/audit_constitution.py` | passed (3 roles, 14 rules; every rule maps to existing enforcement) |
| `python scripts/generate_agent_map.py --check` | passed (118 lines; 2333 tracked files scanned) |
| `python scripts/audit_tool_contracts.py` | passed in the main checkout (44 registered tools) |

So the committed tree is green and the working tree is not, because of work this slice never
touched. This is recorded as a gate blocked by concurrent uncommitted work, not as a green gate;
it goes green when that session's changes are staged or reverted.

## What was not verified

- No live Google or Microsoft account, and no live Telegram bot. The agenda's provider path and
  the alert send path are exercised with fakes and a fake transport.
- The working tree is not green and will not be until the other session's uncommitted growth is
  staged or reverted; the committed tip is green on every audit that can run there.
- No exactly-once claim for any external effect, and no claim that a delivered alert was read.
