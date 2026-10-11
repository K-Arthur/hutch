# Unified outputs — lane plan and checkpoint (2026-10-11)

Task: real media generation/editing/playback; a contained native Python workspace with CSV
analysis, charts and debugging; interactive typed outputs (timeline, comparison, flowchart,
chart, table, receipt, media viewer, artifact card). Integration branch: `outputs/unified`.

## Coordination (read before editing)

* Worktrees: `.worktrees/outputs` (unified, integrator: migrations, outputblocks.py,
  store.py, app.js/shared CSS, tools/__init__.py), `.worktrees/outputs-media`,
  `.worktrees/outputs-workspace`, `.worktrees/outputs-widgets`.
* One integrator applies migrations, `store.py`, `app.js`, shared CSS, commits.
* Lane files never edit another lane's files; interfaces are frozen in
  `docs/research/outputs-block-contract-2026-10-10.md` (blocks), the signatures in
  `src/hutch/workspace/kernel.py` (execution), `src/hutch/media/store.py` (bytes).
* Test runs use private state dirs (`tests/support` helpers), never the operator's
  `~/.hutch`; kernel tests are skipped when `sandbox.status().ok` is false.

## Slices and status

| Slice | Files (owner) | State |
|---|---|---|
| Typed output blocks v1 + schema v51 | `outputblocks.py`, `store.py`, fixtures, tests (done @ c69fd9c) | implemented-and-verified (61 tests green) |
| Contained Python workspace | `workspace/`, `tools/workspace.py`, `sandbox.workspace_argv` (unified) | in progress |
| Media store + job service + renderers | `media/`, `tools/media.py`, routes (unified) | planned |
| Interactive widget renderers | `static/blocks.js`, `static/blocks.css`, `app.js` hook, tests | planned (design gate first) |
| Uploads intake | route + composer (unified, last) | planned |
| Evidence + docs + packaging | docs, capture scripts, CHANGELOG | planned |

## Frozen interfaces (this session)

1. **Blocks**: unchanged from `outputs-block-contract-2026-10-10.md`. Tools put raw dicts on
   `ToolResult.data["blocks"]`; `call_tool` validates once.
2. **Kernel protocol v1** (JSON lines, stdin/stdout; child is stdlib-only CPython):
   host→child `{"v":1,"op":"execute","id":<str>,"code":<str>}`, `{"op":"ping"}`,
   `{"op":"shutdown"}`; child→host events `ready|started|stdout|stderr|display|result|error|done|pong`
   with the request `id`. `display` payloads are block dicts (validated host-side).
   Interrupt: SIGINT to the process group; confirmation = a terminal `done` with
   `status:"interrupted"`; otherwise the kernel is killed, generation bumps, state loss is
   reported.
3. **Sessions**: one kernel per (conversation_id, generation) in
   `state_dir/workspace-sessions/<conversation_id>/gen-<N>/`; `inputs/` is mounted
   read-only; `out/` is scanned and promoted to the media store after each run.
   `workspace_sessions` rows (v51) record generation/status/fingerprint/dir.
4. **Blob access**: every produced asset is a `media_assets` row (migration v52) served by
   `/api/v1/media/{id}/v{version}/content`, hash-verified at serve time, scoped by
   conversation; blocks reference `media_id` + `version` only.
5. **Deterministic vs provider**: `generated_by` is `deterministic` or `provider`. A
   deterministic figure/animation never claims to be a provider result; a provider job is
   only `succeeded` after verified bytes are stored.

## Budgets (initial, local reference machine; measure, then revise)

* bounded view-only interaction p95 ≤ 100 ms; received event → visible block p95 ≤ 250 ms.
* kernel cold start ≤ 2.5 s; warm execute round-trip (1-line print) ≤ 300 ms p95.
* interrupt → confirmed exit ≤ 3 s (SIGINT), escalation ≤ 6 s (SIGKILL + reap verify).
* chart render ≤ 2000 points × 8 series, first render ≤ 150 ms; table preview ≤ 500 rows.
* per-execution captured stdout/stderr ≤ 200k chars each; session disk budget 512 MB;
  single file ≤ 1 GiB (fsize); kernel memory 4 GiB, cpu 3600 s, processes 256.
* media: single asset ≤ 64 MB; per-run media ≤ 256 MB; thumbnails ≤ 512 KB.

## What this plan refuses to fake

* No generative-provider success without verified bytes and a stored asset; without a
  configured/available provider the capability reports `blocked` with setup steps.
* No unrestricted `exec()` in the server; no uncontained Python fallback when bwrap is
  unavailable (fail closed, show diagnostics).
* No widget from prose, partial JSON, or a failed render; text fallback always present.
