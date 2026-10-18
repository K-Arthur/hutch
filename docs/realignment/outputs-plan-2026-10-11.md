# Unified outputs — lane plan and checkpoint (2026-10-11)

Task: real media generation/editing/playback; a contained native Python workspace with CSV
analysis, charts and debugging; interactive typed outputs (timeline, comparison, flowchart,
chart, table, receipt, media viewer, artifact card). Integration branch: `outputs/unified`.

Integration note: this lane's historical schema-v51 label was lane-local. The consolidated
mainline already uses v51–v54, so uploads, media jobs and workspace sessions install at v55.
The migration is additive and idempotent; tests cover v54 upgrades and the divergent output-v51
database shape with existing upload rows.

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
| Uploads intake + CSV disclosure | `server/uploads.py`, `workspace/csvprobe.py`, composer menu + attachment chips, `tests/test_uploads.py` (integrator, 2026-10-11) | implemented-and-verified at route level (11 tests) + `inspect_csv` injected into the kernel namespace; browser journey pending wave 4 |
| Visual verification | `docs/realignment/capture_outputs_widgets.py`, `capture_widget_cards.py`, `artifacts/outputs-widgets/` | done (see below) |
| Evidence + docs + packaging | `CHANGELOG.md`, `README.md`, this plan | done on this branch |

## Gaps and blocked gates (honest inventory)

* **Upload composer journey is not yet exercised in the browser suite.** The upload
  routes, bounds, sniffing, hash re-verification, and the CSV disclosure are
  route-tested (11 tests), the attachment chips render in the composer, and
  `inspect_csv` is injected into the kernel — but a Playwright journey driving the
  real composer control (upload → analyze → interactive chart → verified download)
  lands with the wave-4 e2e work.
* **Provider-backed media is unverified.** No OpenAI key or ComfyUI server is configured
  here, so `create_media` for image/video reports the backend as unavailable with setup
  steps; only deterministic SVG output was produced and inspected. The adapter protocol
  logic is covered by fixture transports, which is not live evidence.
* **No real video container is produced.** The deterministic animation path emits SVG
  animations; an mp4/webm pipeline is not implemented, so the video acceptance row is
  `unsupported` rather than `implemented-but-unverified`.
* **Blocks are read-only.** Flowchart/timeline/comparison cards support inspection,
  filtering, sorting and selection, but there is no UI to edit a block's source and
  re-render it; the source payload is preserved in the event for a future editor.
* **The isolated rich-view path (MCP Apps-style)** is not implemented; ordinary output uses
  trusted host components only, which is the contract's default.
* **Physical-device and screen-reader checks were not run**; widget verification used
  Chromium viewport emulation at 360/390, 900 and 1440 CSS pixels with zero console/page
  errors and zero horizontal overflow.

## Visual verification (2026-10-11, real app, real outputs)

Method: `capture_outputs_widgets.py` seeds one run whose events come from the REAL tools
(contained `run_python` with `emit_block`, `render_diagram`, `create_media` animation),
serves it on loopback, and drives real Chromium (Playwright 1.64 / Chromium 1243) at
1440/900/390 CSS pixels. `capture_widget_cards.py` then screenshots each card and drives
one interaction per kind. Captures and `capture-results.json`/`card-results.json` are in
`docs/realignment/artifacts/outputs-widgets/`.

Observed (inspected as pixels):

* 9 cards across all kinds (code_receipt ×2, chart, table, timeline, comparison, media ×2,
  flowchart); zero console errors, zero page errors, zero horizontal overflow at all three
  widths.
* Chart: gridlines, two series (accent green + blue), hover crosshair tooltip
  ("Value: 11 · grid draw: 122.4 · solar: 253.5"), legend toggles, reset-zoom, notes, and a
  "Data table — exact values" disclosure with the same numbers.
* Table: sortable headers, right-aligned numbers, truncation note ("Showing first 8 of 24
  rows"), provenance note.
* Timeline: state filter + text filter ("1 of 5 events shown — filters are local to this
  browser, nothing is sent anywhere"), corrected chip with "corrected from event e2", ISO
  timestamp with precision + local time.
* Comparison: criterion rows, sortable item columns, unit chip, `unsupported` as a labeled
  pill, "no guess is filled in" note.
* Flowchart: layered SVG with edge labels and a retry cycle, node selection (detail panel
  shows label/group/node id), zoom controls, assumptions note; keyboard focus lands on a
  node.
* Code receipt: status row (execution #, generation, duration, stdout chars), Copy /
  Download, "exactly what executed — hash-bound, not editable", the exact source.
* Media: deterministic diagram SVG with hash caption; animation card with the SVG mount.
* Phone width: single column, no overflow; cards stack below the tool line.

Defect found and fixed during this pass: the media caption duplicated the generator label
("rendered by deterministic · deterministic"); the backend name is now shown only when it
differs from `generated_by` (`src/hutch/server/static/widgets.js`).

Not yet verified visually: video/audio media kinds (no provider backend configured; the
deterministic lane produces SVG animations), the isolated rich-view path (not implemented),
and a physical phone (viewport emulation only).

## Final verification (2026-10-11, integration branch `outputs/unified`)

* Full non-e2e suite on the integrated tree: **2072 passed, 2 skipped** (550 s,
  `pytest tests -q --ignore=tests/e2e`).
* Focused browser e2e (real Chromium via Playwright): `tests/e2e/test_design_system.py`
  plus `test_browser.py::test_dashboard_polish_keeps_work_feedback_steady_and_headings_readable`
  — **10 passed** (121 s).
* Lane test totals: workspace 85, media 137 (with widgets static), integration 7.
* The whole non-e2e suite was also green (1886) on the pre-integration foundation, so the
  integration added no regressions to existing behavior.

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
