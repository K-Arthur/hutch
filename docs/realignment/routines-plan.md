# Routines implementation plan (evidence-backed)

Integrator: this worktree (`routines/durable`). Shared contracts: `Schedule` / occurrence keys / `submit_scheduled` / schedule API. Other lanes must not edit `scheduler.py`, schedule migrations, or `/api/v1/schedules*` without re-read.

## Root causes (confirmed)

1. Long-downtime catch-up claims a **stale capped** occurrence, not the true newest.
2. Invalid zones silently become UTC.
3. Skip grace is a fixed 1800s (breaks daily schedules).
4. Dispatch marker written as processing `now` rather than occurrence.
5. Product gap vs mission: cron-only triggers, no draft/enable lifecycle separate from bot pause, thin result/notification model, UI is schedule list not full routine editor.

## Architecture (smallest that meets requirements)

Extend existing Bot-attached `Schedule` streams into **routines** semantics without a second engine:

| Concept | Representation |
|---|---|
| Routine definition | `Schedule` (+ later lifecycle/trigger fields) |
| Trigger | cron now; `interval` / `once` next; manual run-now via existing submit |
| Occurrence | `(schedule_id, occurrence_iso)` in `schedule_occurrences_v20` |
| Attempt | `Run` with `origin=schedule`, `schedule_id`, `missed_windows` |
| Marker | kv `{schedule_id}:last_fire` = last **claimed or skipped** occurrence |
| Workspace fence | `schedules_paused` (exists) |

No Temporal, Redis, Rust, or frontend rewrite.

## Dependency order

1. **Slice A** — recurrence evaluator: true newest, bounded uncertain counts, zone fail-closed, period-scaled skip grace, marker=occurrence, interval triggers, exact tests (Vancouver 2026, DST fold/gap, 65/90m).
2. **Slice B** — overlap/missed/retry policy fields; skip-next; run-now without consuming occurrence; crash-boundary tests.
3. **Slice C** — result record, delivery intent, approval wait resume (reuse approvals), readiness recheck.
4. **Slice D** — routine library/editor/detail UI + API/CLI parity (draft/enable).
5. **Slice E** — legacy mapping docs, soak, visual, perf budgets.

## Cutover

- Single dispatch path remains `Engine.scheduler_claims` → `Store.submit_scheduled`.
- Marker semantics change to occurrence time: after upgrade, next due math is unchanged for healthy markers; stale wrong claims self-heal on next tick once newest logic ships.
- No dual legacy/new scheduler loops.

## Acceptance budgets (pre-impl)

| Metric | Budget |
|---|---|
| Due detection for 100 routines | < 50ms in-process injected clock |
| Due detection for 1000 routines | < 500ms |
| Catch-up after months (minute cron) | claims true newest; count capped+uncertain; no year enumeration |
| Schedule preview | ≤ 32 occurrences; compute ≤ 100ms |

## Rollback

Revert branch commits; schema additive only in later slices. Marker values remain ISO UTC instants.

## Numeric validation gaps until run

Live provider, paid APIs, overnight soak, physical phone — mark blocked when reached.

## Phase 2 update (2026-11-06)

Shipped on `main` for the personal-ops initiative:

- **Revision journal** (schema v92): `schedule_revisions` plus SQL triggers on the assistant
  document; append-only, no-op saves write zero rows, and `GET .../schedules/{id}/revisions`
  returns bounded field diffs and hashes. Prompt and workflow-input values are hash-only.
- **Policy sidecar** (schema v93): `schedule_policies` with its own revision and a cleanup trigger;
  `schedule_approval_requests` maps a parked run to exactly one approval.
- **Pre-run approval**: a due prompt schedule with `approval_required` is inserted as
  `waiting_approval` before any model/tool call. Approval releases it to `pending`; denial or expiry
  skips it. Reconciliation is immediate and retried on the next scheduler beat; an orphaned parked
  run fails closed with `schedule_approval_missing`.
- **Bounded conditions**: eight literal comparisons over allowlisted schedule/occurrence facts, no
  expression language. False conditions skip the window with `condition_not_met` and create no run.
- **`#/schedules`**: fleet roll call, needs-attention filter, per-routine history/policy disclosure,
  linked workflow-run status, and a policy toggle. The surface is dark-only by design.
- **Limit**: linked saved workflows keep their own per-step approvals; a schedule-level pre-check
  returns 422 with an explicit reason.

Evidence: `docs/research/2026-11-personal-ops-workflows/06-VALIDATION-LEDGER.md` and
`docs/research/2026-11-personal-ops-workflows/artifacts/phase2/report.json`.
