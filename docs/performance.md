# Performance

Hutch stays in Python. Model latency dominates every step, so the gains that matter are in
**tokens, model swaps and idle cost** (draft v0.2, *Performance*). The numbers below are
**measurements on one machine**, not guarantees; the draft's targets were proposals and are shown
next to each result.

**Measured on:** AMD Ryzen 3 5300U (4C/8T), 22 GiB RAM, no GPU, Linux, Python 3.13.15,
2026-10-07, test-only deterministic scenario fixture, a busy desktop (a second coding agent was running). This fixture measures
Hutch control-path overhead only; it is not a product model route and does not verify real inference latency or quality.

Reproduce: `python -m benchmarks.run` (print), `--record` (new baseline), `--check` (exit 1 on a
> 20% regression). Baselines live in `benchmarks/baselines/<name>.json`, keyed by
`$HUTCH_BENCH_BASELINE` (default `local`) because absolute numbers are machine-specific; CI records
its own on first run and caches it (`.github/workflows/ci.yml` — written, **not yet exercised on
GitHub from the development machine**).

## Phase 1 baseline

| Metric | Req | Proposed target | Measured | Notes |
|---|---|---|---|---|
| `hutch status` wall time | PF-6 | < 300 ms | **275 ms** | min of 11 cold-process runs |
| `hutch version` wall time | PF-6 | — | **255 ms** | |
| Event inserts per second | PF-7 | 1,000 sustained | **~52,000** | append + group-commit + flush, 20k events × 3 |
| Hutch overhead per step | PF-11 | < 50 ms | **0.25 ms** | deterministic test fixture; do not infer production inference or tool latency from this value |
| Idle daemon resident memory | PF-13 | < 150 MB | **39 MB** | `hutch daemon`, no browser, no model |
| Idle `hutch serve` resident memory | PF-13 | < 150 MB | **56 MB** | FastAPI + uvicorn |
| Idle daemon CPU | PF-5 | near zero | **0.0 s/hour** | below one 10 ms clock tick over an 8 s window |
| Idle `serve` CPU | PF-5 | near zero | **≈ 4.5 s/hour** | one clock tick in the window; 0.1% of one core |

All targets are met with large margins. That says the targets were conservative for this workload,
not that Hutch is "fast": a real model call is 1–60 s.

### What changed to get there

| Before (v0.1) | After |
|---|---|
| `import openai` at CLI start (~600 ms); `hutch version` = **820 ms** | Provider and `httpx` imports are lazy; `hutch version` = 255 ms, `status` = 275 ms |
| Scheduler ticked every 15–20 s forever; approvals polled the DB every 0.4 s | Loop sleeps until the next due run or a bus event; approval waits block on the bus |
| One `INSERT` + `COMMIT` per event on the agent thread | Events are queued; one writer thread commits batches (group commit, WAL, `synchronous=NORMAL`) |
| No per-step timing | Every step records model wait / tool time / Hutch overhead |
| `database is locked` possible between CLI and server | `busy_timeout`, batched retries, single writer per process |

### How the idle loop works (PF-5)

`Engine.run_loop` reads the `work` bus version, ticks, then sleeps for
`min(next scheduled fire, earliest approval expiry, 5 minutes)` or until `work` moves. Anything that
changes what the loop should do — a bot created or paused, a run submitted or finished, an approval
resolved — notifies `work`. Other processes (`hutch approvals approve`, `hutch run`) reach a running
`serve`/`daemon` through a per-process Unix datagram socket (`wake.py`), so cross-process actions are
immediate, not "within the next tick".

The five-minute cap is a deliberate safety net, **not** a poll: `CLOCK_MONOTONIC` does not advance
while a laptop is suspended, so an unbounded sleep could oversleep a due window after resume. At one
wake per five minutes the cost is unmeasurable above.

### Dashboard roster SQL (2026-10-10)

Nested `bot_stats()` inside each bot card made `/api/bots` Θ(N²) in SQL. Shared
`Store.roster_aggregates()` now computes run counts, active runs, last success, day budgets,
fact counts and sticky allows in a constant number of grouped queries (plus
`idx_runs_bot_status`). Isolated corpus on this machine:

| Bots N | SQL before (nested pattern) | SQL after (`roster_aggregates`) |
|---:|---:|---:|
| 1 | 10 | 10 |
| 10 | 181 | 10 |
| 50 | 2,901 | 10 |
| 100 | 10,801 | 10 |

Raw samples: `docs/realignment/artifacts/performance/dashboard-sql-*.json`. Full write-up:
`docs/realignment/artifacts/performance/hardening-2026-10-10.md`. These numbers are Hutch
control-path SQL counts, not model or network latency.

### Honest limits

- Measured once on one noisy machine. CLI timings varied by ~30% between back-to-back runs while
  another process was busy; the harness reports the *minimum* of 11 runs for that reason, and the
  gate uses a 20% tolerance plus absolute floors so a single clock tick cannot fail the build.
- `events_per_sec` measures the store, not the dashboard. UI-9's "run page usable at 10,000
  events" is tested separately (pagination + coalesced SSE) in the Phase 2 tests.
- The idle-memory numbers are for an empty state directory. Current `hutch init` creates no bots or sample activity.
- PF-1 (cached-token share) and PF-4/PF-10 (compaction, router residency) are model-layer items and
  are measured in the model-layer phases, not here.
