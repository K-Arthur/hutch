# Performance / lifecycle hardening evidence (2026-10-10)

## Environment

- Host: Linux 7.2.7-1-cachyos, 8 logical CPUs, 22 GiB RAM
- Python: 3.14.7 (`.venv`)
- Starting commit: `f2b8b009f691a54ca7bfa41f2c7618753e52b2a0` (branch `main`; no `master` ref)
- Isolated state dirs only; no live user bots or paid inference

## Budgets (chosen before fixes)

| Metric | Budget |
|---|---|
| SQL for `roster_aggregates` | constant in bot count N; ≤ ~20 statements |
| `/api/bots`-shaped nest (pre-fix) | must not be Θ(N²) |
| Eligibility→start p95 (mock, idle) | < 250 ms |
| SPA in-flight reads / subscription | ≤ 1 |
| Tool capture | ≤ `MAX_TOOL_OUTPUT` (1_000_000 chars) before `ToolResult` |

## Defect outcomes

| # | Problem | Outcome | Evidence |
|---|---|---|---|
| 1 | Dashboard quadratic in bot count | **Fixed** | Baseline N=100 → 10,801 SQL / 322 ms; after → **10 SQL / 16 ms**. Tests: `tests/test_bot_stats_scaling.py`. Raw: `dashboard-sql-baseline-f2b8b00.json`, `dashboard-sql-after-slice-a.json` |
| 2 | Approval refresh timer/request accumulation | **Fixed** (residual path) | Classic `stopPolling` already gone; added `RouteOwner`/`singleFlight`/`AbortController`, approvals poll-after-settle, feed render single-flight, hidden-tab pause. Files: `src/hutch/server/static/app.js` |
| 3 | Work continues after slot free | **Fixed** (residual) | `claim_run` capacity now includes unreaped `run_procs` even after terminal status; `end_proc`/`close_procs` notify `work`. Tests: `tests/test_capacity_procs.py` |
| 4 | 15–20 s queue delay after capacity | **Already resolved** (PF-5) | Wake bus + WakeHub; regression `tests/test_dispatch_fairness.py` (p95 < 250 ms on mock). Residual missed-wake bound remains `lease/3` (~10 s), not a 15–20 s poll |
| 5 | Clip after full load | **Fixed** | Stream-bounded `read_file`/`list_files`; browser `read` slices in page context; `tool_limits=0` rejected. Tests: `tests/test_bounded_file_read.py` |

## Ownership diagram

See plan mermaid / ADR-0001/0004. Capacity release requires: terminal status **and** no open `run_procs` (and local `_threads` reaped for the dispatcher process).

## Rust

Deferred — [ADR-0016](../../../adr/0016-rust-process-supervisor-deferred.md).

## Commands run (representative)

```bash
.venv/bin/python -m pytest tests/test_bot_stats_scaling.py tests/test_capacity_procs.py \
  tests/test_dispatch_fairness.py tests/test_bounded_file_read.py \
  tests/test_dashboard.py tests/test_local_day.py tests/test_claims.py -q
```

## Limits

- Browser soak of 100 nav cycles and Playwright traces not run in this write-up session if marked separately in the completion report.
- Windows Job Objects unexecuted (Linux host).
- Pi/OpenCode live process supervision unexecuted (adapters fail-closed).
