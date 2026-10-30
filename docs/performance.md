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
its own on first run and caches it (`.github/workflows/ci.yml`: written, **not yet exercised on
GitHub from the development machine**).

The pytest event-writer throughput floor is a separate, lightweight regression check. Its temporary
database should use fast local storage: set `HUTCH_TEST_BENCHMARK_DIR` to a fresh directory when
running under a slow or contended filesystem. On Linux, a unique directory under `/dev/shm` avoids
measuring the host's disk queue instead of the writer. Do not share that directory between runs.
This setting affects only the throughput test's state database; pytest temp files and captured
artifacts retain their own roots.

## Phase 1 baseline

| Metric | Req | Proposed target | Measured | Notes |
|---|---|---|---|---|
| `hutch status` wall time | PF-6 | < 300 ms | **275 ms** | min of 11 cold-process runs |
| `hutch version` wall time | PF-6 | none | **255 ms** | |
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
changes what the loop should do: a bot created or paused, a run submitted or finished, an approval
resolved, notifies `work`. Other processes (`hutch approvals approve`, `hutch run`) reach a running
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
## 2026-10-29 selective optimisation programme

The programme's full measured record is in [perf/results-2026-10-29.md](perf/results-2026-10-29.md);
the plan, external research and the selective-Rust decision are in
[perf/plan-2026-10-29.md](perf/plan-2026-10-29.md),
[research/performance-rust-2026-10-29.md](research/performance-rust-2026-10-29.md) and
[ADR-0024](adr/0024-selective-rust-performance.md).

Adopted, paired before/after measurements on this machine:

| Change | Operation | Before | After | Paired delta |
|---|---|---|---|---|
| Cached tool-argument validation | `validate_call`, real 25-tool catalog | median 37.5 us / p95 40.7 us | median 18.8 us / p95 22.3 us | 1.98x median |
| Memoized transcript token accounting | `prompt_tokens`, 400-message transcript | 0.665 ms | 0.174 ms | -74% |
| Memoized transcript token accounting | cumulative sizing, 100 steps | 27.6 ms | 9.8 ms | -64% |
| Byte-framed global SSE batch | 200-event global frame (95 KB) | 0.717 ms | 0.518 ms | -27.5% |

Supporting changes: the PF-11 step-overhead benchmark fixture was repaired (the old mock runtime
was removed, so the metric silently measured 0.0 ms; it now runs the deterministic scenario
runtime and fails loudly if it produces no steps), and `benchmarks/hotpaths.py` was added as the
reproducible hot-path harness. The event insert rate is now measured at 5.4-6.2k events/s versus
the 52k events/s in the 2026-10-07 table: a per-event durable outbox commit was added since then
so an accepted append survives a restart. The documented 1,000 events/s sustained gate still has
more than 5x headroom; the crash-recovery contract was not weakened for throughput.

Deferred with measurements (not abandoned): lazy CLI imports (`hutch.tools` costs ~294 ms
cumulative import even for `hutch version`; landed on 2026-10-30, see below), and the dashboard's
per-batch refetch + full `innerHTML` rebuild (largest user-visible opportunity; landed on
2026-10-29, see below). A Rust XLSX-write prototype measured ~109 -> ~24 ms on the write stage but was deferred
in that release because it could not be shipped without packaging changes; see ADR-0024 and the
2026-10-29 section below, where it was subsequently built as an optional accelerator.
## 2026-10-29 dashboard live updates and optional native XLSX writer

Two measured follow-ups from the earlier performance programme, with full records in
[perf/ui-live-updates-2026-10-29.md](perf/ui-live-updates-2026-10-29.md) and
[perf/native-xlsx-2026-10-29.md](perf/native-xlsx-2026-10-29.md).

- **Dashboard live updates are incremental.** The run SSE listener had never consumed the server's
  named `batch` events; live refreshes came from the changes stream and replaced the whole run page
  after a ~1.5 s fetch/rebuild cascade. A new classic script applies safe event batches in place from
  a cached authoritative snapshot and forces the full authoritative render for approvals, status
  transitions, gaps, terminal states and errors. Paired browser A/B (three viewports): refetches per
  steady-state burst **1.0 -> 0.0**, commit-to-render **~1518 -> ~90 ms**, no full innerHTML rebuild,
  no overflow or page errors, unchanged DOM size and scroll frame time.
- **Optional native XLSX writer.** A pinned PyO3 + rust_xlsxwriter kernel is an opt-in build artifact
  with a pure-Python fallback; the independent openpyxl read-back gate is unchanged. One-driver A/B:
  write stage median **82.98 -> 44.34 ms** (-46.6%) in the loaded run and a -53.4% median gain in the
  quiet rerun; full 5000-row generation median **-18.6% to -22.2%**, p95 **-13.5% to -20.2%** depending
  on host load, with the absolute pre-registered p95 target met on the quiet run (178 ms) but not on the
  loaded one (274 ms). It is therefore documented as a host-dependent, operation-level accelerator rather
  than a stable >=20% p95 replacement. Build:
  `python scripts/build_native_docgen.py --check`; disable with `HUTCH_DISABLE_NATIVE_DOCGEN=1`.
  No mandatory Rust dependency or manifest change.
## 2026-10-30 CLI cold start

Measured continuation of the deferred CLI item above: the tool registry imported every tool family
at import time, so `hutch version` paid a tool-catalog import bucket that was the largest share of
import self time in every trace (44.6-56.2% across 5 independent traces; representative trace
500.6 ms of 890.2 ms total, models ~23%). Tool classes now
resolve on first use behind a read-only mapping, and `hutch bot destroy` imports its command layer
on use.

Paired A/B (interleaved samples, pristine HEAD 4c53c814 export vs the change, one driver/session,
host load 6.8-7.5): `hutch version` median **609 -> 331 ms (-45.7%, p95 854 -> 415 ms)**, `--help`
**864 -> 575 ms (-33.4%)**, `status` **1083 -> 600 ms (-44.6%)**, `bot list` **958 -> 584 ms
(-39.1%)**; stdout byte-identical, benchmark gate `--check` PASS. The remaining floor is
`hutch.models`/pydantic, Typer/Rich and the command table; a Rust entry-point rewrite was evaluated
and rejected (no bar-clearing kernel; ADR-0024, [research/cli-startup-2026-10-30.md](research/cli-startup-2026-10-30.md)).
Full record: [perf/cli-startup-2026-10-30.md](perf/cli-startup-2026-10-30.md). Reproduce:
`python -m benchmarks.cli_startup_ab --before <export>/src --after src`.
