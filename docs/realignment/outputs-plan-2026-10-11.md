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

## Integration record (2026-10-11, second session)

The first integration session's uncommitted tree was salvaged by a concurrent lane into
`outputs/unified-stray-wip` (09e9645) and the worktree was cleaned. The fleet's three
lane branches were then complete/committed; this session integrated them:

| Lane | Branch / commit | Integrated state |
|---|---|---|
| Typed blocks + schema v51 | `0fb87c2` (base) | as committed; 61 tests green |
| Media (store, jobs, providers, renders, tools, router) | `outputs-media` 214e0c1, 2f307f9 | merged; router mounted in `create_app`; `create_media`/`render_diagram` registered; **range support added** to the content route (video seek) |
| Widgets (renderers + uPlot 1.6.32 + app.js hook) | `outputs-widgets` f9addcc, a553fcb, 2ea6648 | merged as committed |
| Workspace (contained kernel, `run_python`, `reset_workspace`, router) | `outputs-workspace` (uncommitted at copy time; tests green at 02:13) | sources + tests copied with attribution; tools registered; router mounted |
| Integration glue + tests | this branch | `tests/test_outputs_integration.py` (7 tests: catalog, mounts, real diagram render + verified serving + range, fail-closed, real sandboxed run_python with state persistence) |

The first session's parallel implementation of the same three areas (complete, 1886-test
green) is preserved on `outputs/unified-stray-wip`; the fleet's lane implementations won
integration because they were the concurrent workstream's committed design. Its design
research (`outputs-widgets-design-research-2026-10-11.md`) supplied the approved
widget direction.

## Slices and status

| Slice | Files (owner) | State |
|---|---|---|
| Typed output blocks v1 + schema v51 | `outputblocks.py`, `store.py`, fixtures, tests (done @ c69fd9c) | implemented-and-verified (61 tests green) |
| Media pipeline | `media/`, `tools/media.py`, routes (media lane) | merged; lane tests + integration tests green; live provider gate unverified (no configured backend) |
| Contained Python workspace | `workspace/`, `tools/python_exec.py`, routes (workspace lane) | merged; 85 lane tests + real sandbox integration test green |
| Interactive widget renderers | `static/widgets.js`, `static/widgets.css`, `app.js` hook, tests (widgets lane) | merged; static tests green; visual verification pending |
| Integration | `tools/__init__.py`, `server/app.py`, `tests/test_outputs_integration.py` | done on this branch |
| Evidence + docs + packaging | docs, capture scripts, CHANGELOG | pending |

## Frozen interfaces (this session)

1. **Blocks**: unchanged from `outputs-block-contract-2026-10-10.md`. Tools put raw dicts on
   `ToolResult.data["blocks"]`; `call_tool` validates once.
2. **Kernel protocol v1**: the workspace lane's `workspace/protocol.py` is authoritative
   (JSON-lines over stdio; state per generation; fail-closed without containment).
3. **Sessions**: `workspace_sessions` rows (v51) are the durable identity; one kernel per
   conversation; generations bump on reset/cold start.
4. **Blob access**: media versions are content-addressed with a per-version manifest; the
   serving router re-verifies size+SHA-256 and now supports verified single ranges.
5. **Deterministic vs provider**: `generated_by` distinguishes deterministic renders from
   provider results; a provider job succeeds only with verified stored bytes.

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
