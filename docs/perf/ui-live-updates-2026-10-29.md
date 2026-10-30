# Dashboard incremental live updates (2026-10-29)

Status: implemented and committed (`perf(ui): apply live run event batches incrementally`, plus the
browser journey in `test(ui): cover incremental live-update apply and full-refresh fallback`).
Measurements below are filled from the paired browser A/B run recorded in the performance ledger.

## The problem that was actually there

The earlier performance programme measured that a live run page refetched `/runs/:id` and replaced
the whole run-detail DOM after coalesced event bursts. Investigation for this slice found a second,
latent bug behind that behaviour: the server streams committed batches as a *named* SSE event
(`event: batch`), but `app.js` subscribed with `runStream.onmessage`, which only receives unnamed
`message` events. The run SSE payload was therefore never consumed; live refreshes came from
`/api/v1/changes/stream` -> `refreshChangedResources` (250 ms debounce) -> `scheduleFeedRender`
(250 ms debounce) -> full `/runs/:id` GET -> full `innerHTML` rebuild, on every burst.

## What changed

| File | Change |
|---|---|
| `src/hutch/server/static/live-updates.js` (new, 278 lines) | Binds the named `batch` event; parses the committed events; merges them into a cached authoritative `/runs/:id` snapshot; rebuilds only the transcript block with the existing `runBlockHtml` renderer; preserves scroll and `<details>` state. Loaded after `app.js` so it reuses the classic-script globals instead of duplicating rendering logic. |
| `src/hutch/server/static/app.js` (1 line changed; frozen at 14,532 lines) | The run-stream subscription calls `window.HutchLive.bindRunStream(...)` when present, with the previous `onmessage` behaviour as fallback. |
| `src/hutch/server/static/index.html` (1 line) | Loads `live-updates.js`. |
| `tests/e2e/test_live_updates_incremental.py` (new) | Real app + Chromium journey: a safe four-event batch applies in place (no per-burst refetch) and an approval request forces the authoritative full refresh. |

## Safety model (why it is allowed to skip a full render)

- Safe batch: only `message`, `tool_call`, `tool_result`, `step` and `log` events, on a run that is
  still active, with contiguous sequence numbers and within the server's bounded transcript window.
- Full authoritative render is forced for: approval/choice/human/status/terminal events, status
  transitions, sequence gaps (the server replays from SQLite on reconnect), window overflow, an open
  technical-details panel whose exact stats would go stale, computer-control sessions, any render or
  DOM error, and navigation away from the run.
- The cache base is every authoritative `/runs/:id` response the page already receives (captured at
  the `api` boundary; no extra request); a changed-content batch rebuild is done by the same
  `runBlockHtml` function the full render uses, so the markup and accessibility structure are identical.
- A change-stream refresh arriving within 2.5 s of an applied batch is suppressed as redundant, but a
  forced fallback sets a flag so it can never be skipped. The 4 s belt-and-braces poll still refreshes
  when nothing arrives through SSE.

## Measured result

Paired interleaved A/B (baseline `wins-base` at main 362e1d75 vs candidate `wins` at bafe5d85), headless
Chromium 153, three reps per viewport, load 1.6-3.3 (ceiling 6), 20 bots / 210-event completed run / live
run seeded per rep; 18/18 pairs retained, no discarded reps:

| Metric | Baseline A (3 viewports) | Candidate B (3 viewports) | Effect |
|---|---|---|---|
| `/api/runs/:id` refetches per steady-state burst | **1.0** | **0.0** | eliminated |
| commit -> rendered event latency | **1517-1519 ms** | **88-92 ms** | **~16.9x lower** |
| full innerHTML replacements per burst | 0.75-0.85 ms | **0.0 ms** | no full rebuild |
| DOM nodes after bursts | 726 | 727 | unchanged-order |
| horizontal overflow | 0 px | 0 px | none |
| scroll frame p95 | 16.7-16.8 ms | 16.7-16.8 ms | no regression |

Long tasks were 0 ms in both sides on the quiet host; the dominant win is removing the 1.5 s
change-stream -> debounce -> refetch -> full-rebuild cascade (the observed latency includes the two
250 ms debounces plus the GET and render). A=A noise-floor run was recorded in the same session and is
kept alongside; all raw reps, medians/p95 and the browser/machine metadata are in
`.dsh/long-horizon/hutch-wins/artifacts/ui/paired/ui-ab-20261029-202442.json`.

## Limitations

- The optimisation applies to the run-detail view only; the chat feed's larger refetch pattern is
  unchanged in this slice (it has its own bounded render and no equivalent named-event payload).
- The 2.5 s suppression window is a timing heuristic; the authoritative paths (forced fallbacks,
  polling, navigation) still re-render, and a missed event would appear on the next poll.
- Server code and payload shapes are unchanged; no API, schema or safety boundary was touched.