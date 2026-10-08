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
| `pending` | Queued | queued; an atomic startup reservation may already own a lease |
| `loading_model` | Loading the model | owner is bringing a local model up |
| `running` | Working | owner is executing |
| `waiting_approval` | Waiting for you | an approval request is pending |
| `waiting_human` | Needs you | login / CAPTCHA / MFA / inaccessible UI |
| `waiting_resources` *(new)* | Waiting for a free slot or quota | resource admission or an allowance reset |
| `recovering` *(new)* | Recovering | lease expired; recovery decides the outcome |
| `cancelling` *(new)* | Stopping | cancel requested; not yet verified stopped |
| `succeeded` | Done | executor finished; task expectation verification is not implemented yet |
| `failed` | Failed | run ended with an error |
| `stopped` | Cancelled | cancel completed and descendants verified gone |
| `outcome_unknown` *(new)* | Needs review | an effect started but its receipt is missing, including receipt storage failure |
| `skipped` | Skipped | a scheduled occurrence was deliberately not run |

`stopped` keeps its stored name so existing data and clients keep working; the label is "Cancelled". Terminal states
(`succeeded failed stopped outcome_unknown skipped`) are **absorbing**: no transition leaves them.

### Transitions are a table, applied in SQL

`lifecycle.TRANSITIONS` is the only definition. `Store.transition_run(run_id, to, fence=…)` checks the current lifecycle, fence and
unexpired owned lease inside `BEGIN IMMEDIATE`, then updates the row and appends the `status` event in the **same
transaction**. A rejected transition raises `IllegalTransition` or `LeaseLost`; callers treat `LeaseLost` as "stop now".
Progress writes (`steps`, `tokens`, cost) go through `update_run`, which is also fenced and refuses to touch a terminal row.
Cancel is a separate column (`cancel_requested`) so a client can set it without racing the owner's document writes.

### Fencing

Each claim and each recovery increments `runs.fence`. Recovery compares the observed owner, status, fence and lease expiry and
claims the run in one transaction **before it signals anything**. The owner's `Run` object carries the fence. A worker that lost
its lease gets `LeaseLost` on its next write and cannot start another effect, even before another
supervisor takes over. Heartbeat extends only an unexpired lease; it cannot revive a paused owner.
Progress, process-group assignment, approval creation and usage reservation check the same authority.
Settlement, unsent-call release and uncertainty writes also require the worker fence; uncertain
holds require explicit reconciliation and cannot disappear at allowance rollover. Worker gates
commit their request, waiting state and inline review event together. Requests cannot be rewritten, and expired/stopped
execution cannot receive a late approval or standing grant.
Worker events carry their fence through buffering and validate it when committed, preventing stale
replies from entering either transcript or canonical conversation history. Process records pair PID and start ticks with the
kernel boot id; cleanup uses pidfds and checks the recorded process-group identity, never a raw PID or PGID after a check race.
A run remains `cancelling` or `recovering` while cleanup is incomplete or unverifiable; it becomes terminal only after owned
processes are confirmed gone. Thread-mode test helpers are joined before persistence closes.

### Receipts, recovery, and "outcome unknown"

Before a tool with an external or filesystem effect runs, the runtime writes an immutable *intent*
with arguments, reviewed authority, scope and fence (`tool_actions`, status `started`); after it
returns, the worker saves a receipt (`done` / `failed`, result digest). The argument fingerprint
is a correlation key, not remote exactly-once delivery or deduplication of successful calls.
When a lease expires:

* no `started` action -> `failed` with reason `interrupted`;
* a `started` action without a receipt -> `outcome_unknown`; the action is marked `unknown`, shown to the operator with
  its retained intent, and **never replayed automatically**. Terminal transition seals uncertain
  receipts in the same transaction as status/events, including receipt storage failure after a
  runtime return. A late worker cannot replace them. Schema v13 records reconciliation as a
  separate immutable human report with evidence, reviewed hash and transactional idempotency;
  original statuses, receipts and transcript hashes remain unchanged. Legacy arguments are
  explicitly unknown. See [ADR-0014](0014-immutable-action-review.md).

Hutch never resumes a run in the middle. New messages can start new attempts in their canonical
conversation. Matching uncertain effects in that same conversation require reconciliation before
repetition. Builtin execution reads bounded current receipt guidance, without raw arguments or
operator evidence. These notes supplement the transactional guard and grant no permission.

### Succeeded versus verified

`succeeded` records executor completion. `Run.verified` exists as an optional field, but the engine
has no task-expectation evaluator yet. Artifact/receipt/command expectations and an
`expectation_unmet` outcome are planned; do not describe a Done label as independent task verification.

### Audit writes

**Current implementation:** event rows are batched to SQLite, with status transitions and their buffered events committed together;
the JSONL transcript follows committed events through schema v12's durable delivery queue.
Prefix checking and fsync-before-acknowledgement recover missing, partial or unacknowledged files;
pending errors remain visible. SQLite uses FULL WAL synchronization before acknowledging
permission/action/budget prerequisites. This is tested process-crash recovery, not live power-loss
certification. [ADR-0013](0013-recoverable-transcript-files.md) records bounds and limitations.
Schema v11's separate resource-invalidation outbox serves reconnecting clients
([ADR-0012](0012-resource-outbox-and-reconciliation.md)).

## Alternatives rejected

* **Full event sourcing**: the event stream already exists for display; replaying events to rebuild state is more machinery than lease+fence+receipt need.
* **LangGraph checkpoints** for run state: see ADR-0001 option C.

## Consequences

Migration: ownership/receipt fields began in schema v5; process boot identities and the elected supervisor lease are added by
schema v7. Migrations are serialized and a pre-migration backup is made with SQLite's backup API. Restore from the matching
`.db.bak-vN` file before rolling back. Older code ignores new columns but does not honour fences, so do not run old and new
supervisors against one database at the same time. Ordered transcript events and resource
invalidations commit with state; the separate JSONL mirror follows committed events.
