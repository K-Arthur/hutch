# ADR-0001: One authoritative control plane; every run is an owned OS process

Status: accepted (2026-10-07). Slice: S3 (claims/leases), S4 (executor). Evidence: baseline leads 1-3, D1, D2, C1.

## Context

`hutch serve`, `hutch daemon` and `hutch run` each build their own `Engine`. Ownership is an in-process lock plus a PID
on the run row. Measured consequences: cross-process Stop is a no-op (D1); the `tasks` table records nothing about
execution (D2); two schedulers can dispatch the same occurrence; a timed-out run is recorded terminal while its worker
thread keeps running (the OpenClaw #138499 shape, C1).

## Options

| Option | For | Against |
|---|---|---|
| A. Keep threads, add more locks | Smallest diff | A thread cannot be killed; the locks are still per process; cannot honestly satisfy Stop |
| B. **SQLite as the single coordinator (atomic claims, leases, fencing) plus one worker OS process per run** | Real cancellation (kill the process group); crash isolation; no new infrastructure; dormant bots cost nothing; works with several client processes | A Python start-up per run (about 0.25 s measured for the CLI); more moving parts to test |
| C. Adopt a durable-execution engine (LangGraph checkpointer, Temporal, Celery) | Mature retry/resume | Solves a different problem (graph state), adds a second state store and a service to run; the hard parts here - approvals, receipts, OS process ownership, local-first install - are not provided (B9) |
| D. Rewrite the control plane in Rust (ZeroClaw-style) | Smaller idle footprint | No evidence it helps: Hutch's measured control-plane cost is 0.24 ms/step and 41-66 MB idle (baseline); inference, not the orchestrator, dominates. ZeroClaw publishes no method for its footprint claims (B7) |

## Decision

B. Specifically:

1. **SQLite is the only coordinator.** A run is *claimed* by one atomic `UPDATE ... WHERE status='pending'` that also bumps a
   `fence` counter and sets `lease_owner` / `lease_expires_at`. Every later write by the run's owner carries the fence; a
   write with a stale fence is rejected (`LeaseLost`). A recovered run gets a new fence, so a stale worker cannot mutate state.
2. **Supervisor and client are separate roles, not separate programs.** Any process (`serve`, `daemon`) may run the dispatch
   loop; claims make several of them safe. CLI/API clients never execute for each other; they write *intents* (submit,
   cancel, resolve approval) to the database and the owner acts on them.
3. **Execution happens in a worker process** (`python -m hutch.worker`) in its own session. The in-process thread executor
   stays for `hutch run` (the terminal is the owner), the test-suite and explicit `HUTCH_EXECUTOR=thread`.
4. **Scheduled occurrences are rows** (`schedule_occurrences(bot_id, occurrence_utc)` unique): the claimant inserts the row and
   creates the run in one transaction, so two schedulers and a crash between steps cannot double-dispatch.
5. **Shutdown order:** stop admission, request cancel on owned runs, wait for settle, kill process groups, release leases,
   flush the outbox, close the DB.

## Consequences

* Migration: additive columns and tables (schema v5+). Existing rows are valid (`fence=0`, empty lease). Pre-upgrade backup already exists in `Store._upgrade`.
* Resource: a worker costs one interpreter (about 40-60 MB RSS) only while a run is live. An approval wait still holds that process; the model slot is released while waiting (ADR-0009).
* Failure modes: worker dies silently -> lease expires -> run becomes `recovering` -> terminal `failed/interrupted` (or `outcome_unknown`, ADR-0003). Supervisor dies -> workers keep their lease and finish; the next supervisor adopts them (it never re-runs a live lease).
* Rollback: `HUTCH_EXECUTOR=thread` restores the old execution model; new columns are ignored by old code, and the backup `hutch.db.bak-vN` is created before migration.
