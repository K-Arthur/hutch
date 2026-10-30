# benchmarks/ui - paired browser A/B for dashboard live updates

Reproducible, interleaved A/B measurement of the dashboard run-detail live-update path in
real headless Chromium, against one or two Hutch trees. No app source is modified and
nothing is committed; the harness only reads each tree and writes JSON/screenshots under
the requested output directory.

## Files

| File | Responsibility |
|---|---|
| `_serve.py` | Standalone script: serves one tree's real FastAPI app (in-process uvicorn thread) plus a loopback control API for seeding and scripted SSE bursts. Run by path with `cwd=<tree>`, `PYTHONPATH=<tree>/src`. |
| `measure.py` | CLI and orchestration: tree subprocesses, isolated state, interleaved reps, load gate, JSON payload. |
| `browser.py` | Playwright driver and injected instrumentation (fetch/innerHTML/MutationObserver/longtask/rAF/EventSource). |
| `report.py`, `stats.py` | Derivation and aggregation: per-burst metrics, medians/p95, paired B/A ratios, noise floor. |
| `summary.py` | Console summary table. |

## Exact commands

Pre-change baseline (use a pristine tree; do not benchmark a tree while it is being edited):

```bash
cd /home/kevina/CodingProjects/hutch/.agents/worktrees/wins
PYTHONPATH=$PWD/src /home/kevina/CodingProjects/hutch/.venv/bin/python -m benchmarks.ui.measure \
  --a-tree /home/kevina/CodingProjects/hutch/.agents/worktrees/wins-base \
  --single-tree --reps 3 --viewports 1440x900,900x900,360x800 \
  --out /home/kevina/CodingProjects/hutch/.dsh/long-horizon/hutch-wins/artifacts/ui/baseline
```

Paired candidate vs baseline (A = baseline, B = candidate; reps alternate A/B/B/A):

```bash
PYTHONPATH=$PWD/src /home/kevina/CodingProjects/hutch/.venv/bin/python -m benchmarks.ui.measure \
  --a-tree /home/kevina/CodingProjects/hutch/.agents/worktrees/wins-base \
  --b-tree /home/kevina/CodingProjects/hutch/.agents/worktrees/wins \
  --reps 3 --viewports 1440x900,900x900,360x800 \
  --out /home/kevina/CodingProjects/hutch/.dsh/long-horizon/hutch-wins/artifacts/ui/paired
```

Noise floor (same pristine tree passed as both sides; ratios are pure harness noise):

```bash
PYTHONPATH=$PWD/src /home/kevina/CodingProjects/hutch/.venv/bin/python -m benchmarks.ui.measure \
  --a-tree /home/kevina/CodingProjects/hutch/.agents/worktrees/wins-base \
  --b-tree /home/kevina/CodingProjects/hutch/.agents/worktrees/wins-base \
  --reps 3 --viewports 1440x900,900x900,360x800 \
  --out .../artifacts/ui/noise-floor
```

Useful flags: `--reps`, `--viewports WxH,WxH`, `--bursts`, `--burst-size`, `--seed-bots`,
`--completed-events`, `--load-ceiling`, `--python`, `--keep-state`, `--label`.
Output path defaults to `benchmarks/ui/results`.

## What one rep does

1. The control API creates a fresh live run seeded with `--seed-events` log events (each
   carrying a unique per-rep token) and returns its id.
2. Chromium opens a cold context (viewport, reduced motion) at `/#/run/<id>`; the harness
   waits for the run-detail DOM and for the seed token to be rendered, then waits for quiet.
3. For each of `--bursts` bursts: record the burst start in-page, append `--burst-size` log
   events through the app's own Store, flush the canonical event commit, and wait (up to 12 s)
   for a unique per-burst token to appear in `#chat-stream`. Then wait for 250 ms of quiet
   (no fetches, mutations, or DOM builds) so the next window is clean.
4. The last burst is accompanied by 20 scripted 400 px wheel steps; rAF timestamps give frame
   gaps. A forced-layout probe, DOM node count, and horizontal overflow are read after every
   burst. A screenshot is captured for the first rep of each viewport/side.

Each tree is served by its own subprocess with `PYTHONPATH=<tree>/src`, `cwd=<tree>`, and an
isolated `HUTCH_STATE_DIR`; nothing in either tree is written.

## Seeded state

`--seed-bots 20` assistants, one completed run with `--completed-events 210` events, and one
live run per rep (the run the page opens) receiving scripted bursts. Bursts use `log` events
so each renders one transcript row in the baseline render path.

## Metrics (per burst, then median per rep and median across retained reps)

| Metric | Source |
|---|---|
| `refetches` | `/api/runs/:id` requests in the commit-relative window (one full-window refetch per baseline rebuild; target 0). |
| `events_requests` | `/api/runs/:id/events` requests in window. |
| `commit_to_render_ms` | Server canonical commit mapped to page `performance.now()` -> first mutation after the burst token is rendered. |
| `data_to_dom_ms` | Last refetch response end (or commit if none) -> final mutation in window; the rebuild cost after data arrives. |
| `innerhtml_ms`, `insert_html_ms`, `json_parse_ms`, `dom_apply_ms` | Timed browser primitive wrappers (`innerHTML` setter, `insertAdjacentHTML`, `Response.json`). |
| `longtask_ms`, `longtask_count` | Buffered `PerformanceObserver` longtask entries overlapping the window. |
| `mutation_batches` | MutationObserver callback batch count in window. |
| `run_stream_opens`, `changes_stream_opens`, `run_batch_messages`, `change_messages`, `change_resources` | Wrapped `window.EventSource`: opens and message summaries in window. The pre-change refresh cadence is driven by `/api/v1/changes/stream` resource invalidations (the run SSE named-event bug), so the change resource (for example `transcript_mirrors`) is recorded. |
| `dom_nodes`, `overflow_px`, `forced_layout_ms` | Probe after every burst. |
| `frame_gap_median_ms`, `frame_gap_p95_ms`, `frame_gaps_over_50` | rAF timestamps while scrolling during the final burst. |
| `page_errors`, render timeouts | `pageerror` events; bursts whose token never rendered. |

Aggregates are medians of per-rep medians (plus p95 where meaningful), and in paired mode
`ratio = B / A` per pair with all raw ratios retained.

## Load gating

`/proc/loadavg` is recorded before and after every rep. A rep whose 1-minute load exceeds
`--load-ceiling` (default 24.0, i.e. 3x the 8 threads, because other agents run on this host)
is flagged `discarded` and retried once; both attempts stay in `raw_reps`, only retained
attempts enter the medians. The JSON records the gate value, all loads, and the start/end
machine load.

## Reading results

- `machine`: platform, CPU model, memory, Python/Playwright/Chromium versions, load at start/end.
- `config`: viewports, reps, burst cadence, viewport sequence, python.
- `sides`: tree paths and git head/branch/dirty state (a dirty tree makes the run invalid as
  evidence for a specific commit).
- `raw_reps`: every attempt, with the full in-page snapshot (fetches, streams, mutations,
  builds, longtasks, frames) and per-burst records.
- `analysis.per_side`: per-side/per-viewport metric summaries and change-resource totals.
- `analysis.paired`: per-viewport pairs with A, B, ratio and delta per metric.
- `analysis.noise_floor`: same-tree repeats (A=A) per-metric CV, or paired ratio spread when
  both sides are the same tree. Treat an effect as resolvable only when it exceeds this spread.

## Known limitations

- Headless Chromium with software rendering on a shared, noisy host; absolute milliseconds move
  with load even when interleaved. Load before/after and discarded reps are recorded.
- Commit timestamps are mapped from the harness monotonic clock into the page performance
  timeline with a midpoint offset sample; residual error is about 1-3 ms, small next to the
  ~1.5 s baseline commit-to-render latency it precedes.
- The 4 s belt-and-braces `statusTimer` refresh in the pre-change app can add a periodic
  refetch inside a window; the count is reported as measured, not corrected.
- Long tasks start at 50 ms; at the measured 200-event window the rebuild is a few ms, so
  long-task counts of 0 are expected and are not a claim of "no work".
- The baseline render path is inferred from the changes stream, not the run SSE: named SSE
  events do not fire the app's `onmessage` handler. The candidate's incremental path should
  show the run batch message being consumed and near-zero refetches.
- The rendered-event check uses a per-burst text token inside `#chat-stream`; it does not
  depend on the row markup, but an implementation that drops transcript log text entirely
  would time out and be reported as a render timeout.
