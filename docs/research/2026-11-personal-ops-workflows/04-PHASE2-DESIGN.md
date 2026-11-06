# Phase 2 design: automation trust and observability (G03, G06)

Status: design written before implementation. Requirement ids are in
`03-REQUIREMENTS-AND-DECISIONS.md`; failure ids are in `02-FAILURES-AND-COMPLAINTS.md`;
sources are in `01-SOURCES.md`.

## Objective

Close the two open automation gaps:

- G03: an append-only schedule revision journal, an approval checkpoint before a scheduled
  occurrence executes, and bounded declarative conditions.
- G06 remainder: a needs-attention filter, occurrence and revision history, linked workflow-run
  status, and a fleet roll-call on `#/schedules`.

The phase must not grow a frozen file. `src/hutch/store.py`, `src/hutch/models.py`,
`src/hutch/server/app.py`, `src/hutch/engine.py`, `src/hutch/scheduler.py` and
`src/hutch/server/static/app.js` are over the baseline cap.

## Task split

### Task 2A - schedule revision journal

**Targets**

| Target | Change |
|---|---|
| `src/hutch/schedule_history_schema.py` (new) | `schedule_revisions` table, insert/update triggers on `bots`, no-op guard, append-only triggers, backfill for existing bots |
| `src/hutch/schedule_history.py` (new) | Snapshot parsing, per-schedule field diffs, bounded redaction and hashes |
| `src/hutch/server/schedule_history_api.py` (new) | `GET /api/v1/bots/{ref}/schedules/{id}/revisions` and the shared route registration used by 2B and 2C |
| `@src/hutch/store.py:37` | Append `schedule_history_schema` to the existing `from . import ...` line (same line count) |
| `@src/hutch/store.py:2453` | Append `schedule_history_schema.migrate` to the existing `_MIGRATIONS` tail (same line count) |
| `@src/hutch/server/app.py` | One registration call near `@src/hutch/server/app.py:3207-3213`, replacing a blank line so the file does not grow; append the import to an existing import line |
| `tests/test_schedule_history.py` (new) | Real Store/SQLite migration, trigger, no-op, append-only, diff and API tests |

**Schema**

`schedule_revisions(id, bot_id, bot_name, revision, change_type, schedules_json,
prev_schedules_json, changed_at)` with `UNIQUE(bot_id, revision)` and a bounded index. The
trigger stores the extracted `schedule`/`schedules` JSON only, not the whole bot document. It fires
on `INSERT` and on `UPDATE OF doc` when either JSON value changed; a no-op save writes zero rows.
`UPDATE` and `DELETE` are refused by trigger. Existing bots get one baseline row during migration.

**API**

`GET /api/v1/bots/{ref}/schedules/{id}/revisions?limit=50&offset=0` returns newest first:

```json
{
  "revision": 3,
  "change_type": "updated",
  "changed_at": "2026-11-06T12:00:00+00:00",
  "bot_id": "bot_...",
  "bot_name": "release-watch",
  "schedule_id": "schedule_...",
  "changes": [
    {"field": "cron", "before": "0 3 * * *", "after": "0 4 * * *",
     "before_hash": "...", "after_hash": "...", "redacted": false}
  ],
  "before_hash": "...",
  "after_hash": "..."
}
```

`prompt`, `workflow_inputs` and unknown nested values are hash-only with `redacted: true`. No host
paths. A missing schedule returns 404 only when the schedule is absent from both the current bot and
`schedule_identities`; an existing schedule with no journal rows returns `[]`.

### Task 2B - approval checkpoints and bounded conditions

**Targets**

| Target | Change |
|---|---|
| `src/hutch/schedule_policy_schema.py` (new) | `schedule_policies` and `schedule_approval_requests` tables, cleanup trigger, indexes |
| `src/hutch/schedule_conditions.py` (new) | Closed condition schema and evaluator; no `eval`/`exec` |
| `src/hutch/schedule_policy.py` (new) | Policy read/upsert with revision CAS and schedule-existence checks |
| `src/hutch/schedule_admission.py` (new) | Moved `scheduler_claims` body plus condition skip and approval parking/reconciliation |
| `@src/hutch/engine.py:1467-1537` | Replace the body of `scheduler_claims` with a delegation to `schedule_admission.claim_due_schedules` (net shrink of the frozen file) |
| `@src/hutch/lifecycle.py:24-36` | Add `waiting_approval -> pending` so an approved pre-run occurrence can be dispatched |
| `@src/hutch/approvals.py:251-287` | After a won decision or expiry, reconcile the schedule approval (local import, no cycle) |
| `@src/hutch/store.py:6818` | Add `condition_not_met` to the allowed skip-reason set (same line count) |
| `@src/hutch/server/schedule_history_api.py` | Add history, policy and roll-call routes to the same registration function |
| `tests/test_schedule_conditions.py` (new) | Every operator, rejected field/operator/nesting/size, AND semantics |
| `tests/test_schedule_policy.py` (new) | CAS, schedule cleanup, policy API, no-op and validation |
| `tests/test_schedule_approvals.py` (new) | Park before execution, approve -> pending, deny/expiry -> skipped, one notification |

**Policy table**

`schedule_policies(bot_id, schedule_id, approval_required, conditions_json, revision, updated_at)`
keyed by `(bot_id, schedule_id)`, foreign key to `bots(id)` with cascade. A trigger deletes policy
rows for schedules removed from the bot document. This avoids growing frozen `models.py`.

**Approval table and flow**

`schedule_approval_requests(run_id, approval_id, bot_id, schedule_id, occurrence, created_at,
reconciled_at)` keyed by `run_id`, unique `approval_id`.

The admission path is:

1. Evaluate conditions. On failure, claim the window as skipped with reason
   `condition_not_met` and create no run.
2. If `approval_required`, build the run with `status=waiting_approval` before
   `store.submit_scheduled`, so no dispatcher can see it as pending.
3. After the claim wins, insert an `ApprovalRequest` with `tool="schedule"` and a bounded detail
   (bot, schedule, occurrence, trigger, timezone, prompt length; no prompt text) using
   `store.create_approval(..., begin_wait=False)`, emit one `approval_request` event, and record the
   mapping in `schedule_approval_requests`.
4. On approval, `reconcile_decision` moves the run `waiting_approval -> pending`; the normal
   dispatcher claims it. On denial or expiry, it moves the run to `skipped` with a visible reason.
   The marker is idempotent, so a crash between the transition and the marker is safe.

`run-now` stays an explicit owner action and is not gated by `approval_required`.

**Conditions**

A list of at most 8 objects `{field, op, value}`. Allowed fields are schedule/bot metadata and the
occurrence facts: `schedule_name`, `schedule_timezone`, `schedule_trigger`, `schedule_enabled`,
`bot_name`, `bot_paused`, `occurrence_weekday` (0=Monday), `occurrence_hour`, `missed_windows`.
Allowed operators are `eq`, `ne`, `in`, `not_in`, `lt`, `lte`, `gt`, `gte`, `contains`. Values are
scalars or a list of at most 20 scalars; strings are at most 200 characters; nested objects are
rejected. All conditions must pass. No regular expressions, no `eval`, no expression language.

**API**

- `GET /api/v1/bots/{ref}/schedules/{id}/policy`
- `PUT /api/v1/bots/{ref}/schedules/{id}/policy` with `{approval_required, conditions,
  expected_revision}`; 422 on condition errors, 409 on CAS conflict.
- `GET /api/v1/schedule-policies` (bounded 500) for the schedules page.
- `GET /api/v1/bots/{ref}/schedules/{id}/history?limit=20` returning policy, revisions and
  occurrences enriched with `workflow_run_id`.
- `GET /api/v1/schedules/roll-call` returning totals and a bounded routine list.

The roll-call is computed from stored rows: active/blocked counts, pending schedule approvals,
failures in the last 24 hours, next due, measured/reserved spend and configured caps. It never
returns fabricated zeros on an error; the route fails and the UI says unavailable.

### Task 2C - schedules surface

**Targets**

| Target | Change |
|---|---|
| `src/hutch/server/static/schedules.js` (new) | MutationObserver enhancement of the shipped schedules view: roll-call, needs-attention filter, history disclosure, policy toggle |
| `app/src/schedules.css` (new) and `@app/src/input.css` | Source CSS for the roll-call and history layout; build `src/hutch/server/static/ui.css` |
| `@src/hutch/server/static/index.html:216` | Load `schedules.js` after `app.js` (one line) |
| `tests/e2e/test_schedule_history.py` (new) | Real server and browser: filter, history, revision redaction, roll-call, keyboard, 360/768/1280/1920 px, light/dark, zero overflow |
| `docs/research/2026-11-personal-ops-workflows/06-VALIDATION-LEDGER.md` (new) | Exact commands, HTTP statuses, DB state and screenshot metrics |

`app.js` is not edited. The new module observes `#view` for `.schedule-overview`, fetches the new
APIs, inserts a roll-call section and a filter, and appends a native `<details>` history panel to
each row. Native details/summary and ordinary buttons keep the keyboard path. No new polling timer;
the enhancement runs on render and on user action, and history is fetched lazily on open.

## Verification

- Focused tests: `npm run test:agent -- tests/test_schedule_history.py tests/test_schedule_policy.py
  tests/test_schedule_conditions.py tests/test_schedule_approvals.py`.
- Migration: real `Store` against a temporary SQLite file; `SCHEMA_VERSION` increments; triggers are
  present and refuse mutation. Coverage lives in the new test file because `tests/test_migration.py`
  is frozen at 1,210 lines.
- Real stack: real FastAPI app on a loopback port, real SQLite, a real scheduled claim, real
  approval resolution, and the real dashboard.
- Browser: 360, 768, 1280 and 1920 px in light and dark; keyboard traversal of the filter, history
  and policy toggle; `scrollWidth <= clientWidth`; zero console/page errors; screenshots inspected.
- Audits: `npm run check:agent`, `npm run audit:context`, `python scripts/audit_emoji.py`.
- Review: full phase diff for god functions, frozen-file growth, naive timestamps, prompt leakage
  and vocabulary drift.

## Risks and rollback

- **Frozen-file growth.** Store and app registrations replace existing lines; engine's
  `scheduler_claims` is moved to a new module and shrinks. Verify line counts against
  `.file-size-baseline.json` before each commit.
- **Approval race.** The run is inserted as `waiting_approval`, never pending. If approval creation
  fails, the run is marked skipped with an event rather than left runnable.
- **Double execution.** Approval reconciliation is idempotent and checks the run's current status
  before any transition. The scheduler claim remains the single occurrence winner.
- **Journal size.** The journal stores schedule JSON only, bounded by the number of schedule edits.
  The API reads at most 2,000 recent revisions and returns at most 100.
- **UI seam drift.** The enhancement depends on `.schedule-overview` and `data-schedule-id`, which
  are shipped attributes. If app.js changes them, the e2e test fails visibly rather than silently.
- **Rollback.** Revert the three commits; the migrations are additive, and old code ignores the new
  tables. No existing column or row is rewritten.
