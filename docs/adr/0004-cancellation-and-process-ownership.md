# ADR-0004: Cancellation that controls execution

Status: accepted (2026-10-07), amended during realignment. Slices: S2-S4. Evidence: baseline leads 1 and 7, D1, C1.

## Decision

* **Cancel is an intent in the database** (`runs.cancel_requested`, plus status `cancelling`). Any client process can set it; the
  run's owner (and the supervisor, for a dead owner) acts on it. A "stop" that only flips an in-memory flag in the calling
  process is removed.
* **Ladder, with a deadline for each rung** (defaults: cooperative 3 s, terminate, then kill):
  1. cooperative: the worker sees the flag (DB poll every 0.5 s while idle, the in-process event while busy) and unwinds; model I/O is
     aborted through the existing `cancel_hooks`; approval/handoff waits are woken;
  2. signal only process identities recorded for this run, after checking boot id and start ticks; Linux pidfds avoid the PID reuse
     race. Process-group membership is checked against the recorded leader identity; Hutch never signals a raw numeric PGID. If
     the recorded leader identity no longer matches, cleanup remains unverifiable and is retried; the replacement PID is never
     signalled or treated as proof that the old process tree is gone.
* **Verified cleanup**: a run leaves `cancelling` for `stopped` only after owned processes are confirmed gone. An incomplete or
  unverifiable cleanup stays visibly `cancelling` or `recovering`, records the PIDs/reason, relinquishes its lease briefly, and is
  retried. It is never reported as a successful cancellation while a recorded process may remain.
* **Recovery authority**: recovery claims the expected expired owner/fence/lease with a compare-and-swap and increments the fence
  before signaling or changing process state. If cleanup cannot be verified, the run remains nonterminal.
* **Production attempts are owned processes.** `serve`, `daemon`, and `hutch run` start one worker process per run. A run that
  exceeds `timeout_seconds` stays `cancelling` until cleanup is verified, then records `failed/timeout`.
* **Late workers are fenced** (ADR-0003): after terminal state, DB writes raise `LeaseLost`, tools refuse (`ctx.closed`), and the event sink drops writes.
* **External runtimes**: required behavior for any future adapter is concurrent bounded drains of both pipes, nonblocking cancellation, a privately owned process session and the same verified cleanup ladder. The present Pi and OpenCode adapters fail closed before process creation; see ADR-0007.
* **Global stop** (`stop-all`, UI) sets `cancel_requested` for every active run; **parent cancellation** propagates to delegated child runs through lineage (ADR-0008). Neither signals a PID that is not recorded as owned by a Hutch run.
* "Stopping" stays visible while `cancelling`. Thread execution is an explicit test/compatibility mode; a non-cooperative test
  thread is joined before terminal status or database shutdown. Docs state what Stop cannot do: undo an effect already committed,
  or refund a provider call that continues after the client disconnects.

## Consequences

Cost: a poll of one indexed column per owned run every 0.5 s while waiting; pidfd cleanup adds no steady-state work. A single
database lease elects the scheduler/recovery supervisor across web workers and daemon processes. On Linux, verified cleanup uses
`/proc` boot/start identity and pidfds; platforms without these primitives are not supported for production execution.
