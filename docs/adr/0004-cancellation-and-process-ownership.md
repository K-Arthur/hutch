# ADR-0004: Cancellation that controls execution

Status: accepted (2026-10-07). Slice: S4. Evidence: baseline leads 1 and 7, D1, C1.

## Decision

* **Cancel is an intent in the database** (`runs.cancel_requested`, plus status `cancelling`). Any client process can set it; the
  run's owner (and the supervisor, for a dead owner) acts on it. A "stop" that only flips an in-memory flag in the calling
  process is removed.
* **Ladder, with a deadline for each rung** (defaults: cooperative 3 s, terminate 3 s, kill 2 s):
  1. cooperative: the worker sees the flag (DB poll every 0.5 s while idle, the in-process event while busy) and unwinds; model I/O is
     aborted through the existing `cancel_hooks`; approval/handoff waits are woken;
  2. SIGTERM the run's **process group** (workers and every tool child start with `start_new_session=True`);
  3. SIGKILL the group.
* **Verified cleanup**: the run only leaves `cancelling` for `stopped` after the group is confirmed empty
  (`killpg(pgid, 0)` raises `ProcessLookupError`) or the failure to reap is itself recorded (`stopped` with a `cleanup_incomplete` event naming the surviving PIDs). The group id is stored in `runs.pgid`, so a supervisor that was not the spawner can still finish the job.
* **Wall-clock deadlines are enforced by the supervisor on the process, not by abandoning a thread.** A run that exceeds `timeout_seconds` goes `cancelling` -> `failed/timeout`.
* **Late workers are fenced** (ADR-0003): after terminal state, DB writes raise `LeaseLost`, tools refuse (`ctx.closed`), and the event sink drops writes.
* **External runtimes**: stdout and stderr are drained by concurrent reader threads into bounded buffers (stderr tail 64 KiB), reads never block the cancel loop, and the child is the head of its own session so the same ladder applies. OpenCode through a shared background service is a separate case (ADR-0007).
* **Global stop** (`stop-all`, UI) sets `cancel_requested` for every active run; **parent cancellation** propagates to delegated child runs through lineage (ADR-0008). Neither signals a PID that is not recorded as owned by a Hutch run.
* "Stopping" stays visible while `cancelling`. Docs state what Stop cannot do: undo an effect already committed, or refund a provider call that continues after the client disconnects.

## Consequences

Cost: a poll of one indexed column per owned run every 0.5 s while waiting (negligible; measured in the budget). Rollback: the thread executor keeps the previous behaviour but still reads `cancel_requested`, so cross-process Stop works even there.
