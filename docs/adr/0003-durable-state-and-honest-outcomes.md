# ADR-0003: An explicit run state machine, fenced writes, receipts, and honest outcomes

Status: accepted (2026-10-07), amended during realignment. Slices: S2-S3. Evidence: baseline leads 1-3, "Audit writes fail silently", C1.

## Context

Status is assigned in scattered places (`run.status = ...; store.update_run(run)`) from several threads. `update_run` rewrites the
whole JSON document, so concurrent writers lose updates and a late worker can overwrite a terminal state. Audit-write failures
are swallowed. "Succeeded" currently means "the model stopped calling tools".

## Decision

### States

| Stored value | Label shown to people | Meaning |
|---|---|---|
| `pending` | Queued | admitted, nobody owns it yet |
| `loading_model` | Loading the model | owner is bringing a local model up |
| `running` | Working | owner is executing |
| `waiting_approval` | Waiting for you | an approval request is pending |
| `waiting_human` | Needs you | login / CAPTCHA / MFA / inaccessible UI |
| `waiting_resources` *(new)* | Waiting for a free slot or quota | resource admission or an allowance reset |
| `recovering` *(new)* | Recovering | lease expired; recovery decides the outcome |
| `cancelling` *(new)* | Stopping | cancel requested; not yet verified stopped |
| `succeeded` | Done | run finished and (where an expectation exists) it was verified |
| `failed` | Failed | run ended with an error |
| `stopped` | Cancelled | cancel completed and descendants verified gone |
| `outcome_unknown` *(new)* | Needs review | the process died after an effect started but before its receipt |
| `skipped` | Skipped | a scheduled occurrence was deliberately not run |

`stopped` keeps its stored name so existing data and clients keep working; the label is "Cancelled". Terminal states
(`succeeded failed stopped outcome_unknown skipped`) are **absorbing**: no transition leaves them.

### Transitions are a table, applied in SQL

`lifecycle.TRANSITIONS` is the only definition. `Store.transition_run(run_id, to, fence=…, expect=…)` runs
`UPDATE runs SET status=? WHERE id=? AND status IN (<allowed from>) AND fence=?` and appends the `status` event in the **same
transaction**. A rejected transition raises `IllegalTransition` or `LeaseLost`; callers treat `LeaseLost` as "stop now".
Progress writes (`steps`, `tokens`, cost) go through `update_run`, which is also fenced and refuses to touch a terminal row.
Cancel is a separate column (`cancel_requested`) so a client can set it without racing the owner's document writes.

### Fencing

Each claim and each recovery increments `runs.fence`. Recovery compares the observed owner, status, fence and lease expiry and
claims the run in one transaction **before it signals anything**. The owner's `Run` object carries the fence. A worker that lost
its lease gets `LeaseLost` on its next write and cannot start another effect. Process records pair PID and start ticks with the
kernel boot id; cleanup uses pidfds and checks the recorded process-group identity, never a raw PID or PGID after a check race.
A run remains `cancelling` or `recovering` while cleanup is incomplete or unverifiable; it becomes terminal only after owned
processes are confirmed gone. Thread-mode test helpers are joined before persistence closes.

### Receipts, recovery, and "outcome unknown"

Before a tool with an external or filesystem effect runs, the runtime writes an *intent* row
(`tool_actions`: run, idempotency key = hash(run, tool, canonical args), status `started`); after it returns, the receipt
(`done` / `failed`, result digest). When a lease expires:

* no `started` action -> `failed` with reason `interrupted`;
* a `started` action without a receipt -> `outcome_unknown`; the action is marked `unknown`, shown to the operator with
  its exact arguments, and **never replayed automatically**. Local idempotency keys prevent a duplicate *from Hutch*; they are
  not a promise of exactly-once effects at a remote service, and the UI says so.

Hutch never resumes a run in the middle. "Continue" starts a new run in the same conversation with a system note listing
unknown actions.

### Succeeded versus verified

`succeeded` records execution. A task may declare expectations (an artifact path exists and is non-empty, a receipt of a given
kind, a command exit code). The engine evaluates them after the run and stores `verified: true|false|n/a`; a model saying
"done" with a failed expectation ends as `failed` with `exit_reason=expectation_unmet`, a partial result is kept and labelled.

### Audit writes

Event persistence is an outbox: the event row is committed with the state change; the JSONL mirror and notifications are derived
from committed rows by a drainer and are retried. A failure to persist an event for a *consequential* action blocks that action
(fail closed). For other events the run continues in a visibly **degraded** mode (a `log` event and a banner), never silently.
`Store._commit_batch` stops dropping events after five tries; it raises and the run degrades.

## Alternatives rejected

* **Full event sourcing**: the event stream already exists for display; replaying events to rebuild state is more machinery than lease+fence+receipt need.
* **LangGraph checkpoints** for run state: see ADR-0001 option C.

## Consequences

Migration: ownership/receipt fields began in schema v5; process boot identities and the elected supervisor lease are added by
schema v7. Migrations are serialized and a pre-migration backup is made with SQLite's backup API. Restore from the matching
`.db.bak-vN` file before rolling back. Older code ignores new columns but does not honour fences, so do not run old and new
supervisors against one database at the same time. There is no `outbox` table yet; ordered durable events are committed with the
state transition and the JSONL mirror follows committed rows.
