# ADR-0016: Rust process supervisor deferred

Status: accepted (2026-10-10). Evidence: performance hardening slices A–E on commit lineage from `f2b8b009`.

## Context

After correcting Python/JavaScript paths for dashboard query cost, SPA subscription ownership, capacity held by unreaped `run_procs`, event-driven dispatch, and bounded tool capture, the remaining question was whether a narrowly scoped Rust supervisor is justified for spawn/supervision, cancellation escalation, descendant accounting, and bounded stream capture.

## Decision

**Keep the Python process supervisor.** Do not add a Rust crate or second execution path.

Measured and structural reasons:

1. **Inference dominates.** Control-plane step overhead remains sub-millisecond on the mock fixture (`docs/performance.md`, `docs/realignment/performance.md`). Rewriting the supervisor cannot speed model inference.
2. **Lifecycle contract is already process-based.** ADR-0001/0004 already require one owned OS worker per production attempt, pidfd/boot-start identity checks, and verified cleanup before capacity honesty. The residual capacity race (terminal status before unreaped `run_procs`) was fixed in SQLite claim accounting without a new language boundary.
3. **IPC cost and packaging.** A versioned local IPC contract, dual packaging, and parent/supervisor death reconciliation would add startup latency, copies, and platform surface without a measured gap that Python cannot close.
4. **OpenCode orphan reports** ([anomalyco/opencode#20899](https://github.com/anomalyco/opencode/issues/20899)) motivate descendant accounting for *future* adapters; Hutch’s Pi/OpenCode bot runtimes remain fail-closed before spawn (ADR-0007).

## Consequences

- Revisit only if a measured gap remains after Python fixes: e.g. cancellation-to-exit p95 for stubborn process trees exceeds an agreed budget that Python escalation cannot meet, or non-privileged containment requires a helper Hutch cannot implement safely in-process.
- Any future Rust path must stay limited to spawn/supervise/capture/report; product policy, scheduling, approvals, and persistence stay in Python.
- Fallback must never restore false cancellation or unbounded buffering.

## Rejected alternatives

| Option | Why rejected now |
|---|---|
| Rewrite orchestrator in Rust | No evidence; idle RSS already within PF-13; ADR-0001 option D |
| Placeholder crate / dual path | Migration risk; unfinished second executor |
| Aggressive poll instead of wake | PF-5 already event-driven; burns idle CPU |
