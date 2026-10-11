# Runtime, background execution, monitoring, and durable jobs — plan (2026-10-11)

Owner: `runtime/monitoring` worktree (`.worktrees/runtime`), branch `runtime/monitoring`, based on local
`main` `55f551b` (which contains `routines/durable` `c869a5a`, `wcag22-audit-fixes`, documents/schema v50).
No push or publication. Shared-contract lanes: database migrations, service lifecycle, event contracts,
runtime UI — this branch is the integrator for its own slice and must re-read `main` before integrating.

## Verified starting state (evidence)

- `src/hutch/service.py` installs/starts/stops a Linux user unit (`hutch.service`) that runs
  `hutch serve` on loopback; custom units are preserved; no readiness handshake, no restart command,
  no linger handling, no UI. `hutch service status` reports systemd process state only
  (`docs/operations.md:16-21` says explicitly "not an HTTP health check").
- `GET /api/health` (both `/api/health` and `/api/v1/health`) returns `{status, version, schema,
  execution_held}`; no instance identity, pid, scheduler role, or service state.
- Engine (`src/hutch/engine.py`) elects one supervisor per state dir (`supervisor_leases`), runs the
  cron/interval/once scheduler (true-newest catch-up, drafts, overlap policy), lease-fenced runs,
  receipts, `outcome_unknown`. Runs never resume in the middle (ADR-0003) — by design.
- No event/source monitoring exists anywhere (no watch/feed/webhook/cursor registry; verified by
  exhaustive search). The only "monitoring" is prompt-based cron templates.
- No step-level job layer; the only continuation is `workspace_task_continuations` (v34) for
  reviewed cross-Bot delegation, and new runs after terminal states.
- Notifications are in-app only (Needs you) plus tab-open browser alerts.
- Host facts: `pdftotext`, `pdftoppm` (poppler) and `tesseract 5.5.3` are installed; no Ollama
  listener; no `hutch.service` installed for this user; `Linger=no`; two live `hutch serve`
  processes (ports 8787, 18789) belong to the user and must not be touched.

## Decision (ADR-0018) being implemented

Local-first, single-owner engine managed as a **separate background service** (Linux user unit now,
macOS/Windows contracts documented, not implemented); the web interface (and later an optional thin
desktop shell that attaches to the one engine) is a client; a personal headless profile is the same
core on a chosen always-on host; shared multi-tenant hosting is rejected as a separate release gate.

## Slices (bounded, each with tests)

- **R0 docs** — ADR-0018, this plan, operations/architecture updates. Research report R1–R11/F1–F3.
- **R1 service lifecycle** — `restart`; HTTP readiness + instance-identity handshake after
  install/start; distinct states (not installed / inactive / failed / active-not-ready / ready);
  linger reported, never silently enabled; doctor refinement. Tests: FakeSystemd + real uvicorn probe.
- **R2 runtime identity/status** — `/api/health` additive `instance` + `scheduler` fields;
  local-owner `GET /api/v1/runtime` with service/linger/exposure/queue/readiness; engine supervisor state.
- **R3 event sources** — schema v51: `event_sources`, `source_events`; adapters filesystem, git,
  RSS/Atom + conditional GET; deterministic check loop owned by the elected supervisor; durable
  cursor/receipt ordering; dedupe by (source, event key, content hash); bounded rescans; zero model
  calls on unchanged sources; admission of one logical run per material change with per-source
  cooldown; revision fencing so edits/deletes stop admitting work.
- **R4 durable jobs** — schema v52: `jobs`, `job_steps`; step states queued/running/succeeded/
  failed/blocked/unknown/skipped; input hashes; typed outputs (artifact refs); deterministic
  handlers and run-backed steps; restart resumes only from verified checkpoints; unknown external
  effects hold the job; changed inputs invalidate downstream steps; new attempts are linked, never
  reopens history.
- **R5 PDF→summary workflow** — job template: watch folder → changed PDF discovery (history hash
  rule) → immutable ingest copy → bounded `pdftotext` extraction under resource limits → OCR only
  pages without a text layer (`pdftoppm`+`tesseract`, bounded) → chunk with provenance into a
  scoped local FTS5 index with index generations → grounded summary step (model route; blocked
  honestly when unavailable) → artifact + notification. Interrupt after each boundary; no duplicate
  vectors/work; prior good index retained.
- **R6 runtime UI** — compact Runtime & Background Work area in Settings: engine location,
  version/instance, service states + readiness, startup/logout behavior, exposure, latest source
  check/freshness, queue/backlog, pending human action, and deliberate controls (enable background
  work, pause automation, uninstall, cancel run, reconcile). Remote monitor clients never receive
  local-admin controls. Requires the mandatory frontend research + route approval gate before
  implementation.
- **R7 verification** — deterministic tests + real-process integration tests; broker/daemon
  duplicate checks; service state matrix; monitoring fixtures (temp dirs, local RSS server, git);
  interruption/restart resume tests; unknown-effect sink test; browser journeys for the UI.

## Explicit non-goals this session

- macOS/Windows service implementations (contracts and guidance only, marked unverified).
- Multi-tenant work of any kind.
- Installing a service unit on the user's live machine or touching live processes.
- Paid inference; live provider calls; physical-phone tests.

## Integration risks

- Schema numbering: `outputs`, `mcp-s0`, `grounding` lanes each claim v51 on separate branches.
  This branch writes v51/v52 and renumbers mechanically if another lane lands first.
- `store.py` and `server/app.py` are shared; keep edits in new modules where possible.
- `main` moves; re-read before integrating and re-run the affected suites.

## Status (2026-10-11, branch `runtime/monitoring`)

| Slice | State | Evidence boundary |
|---|---|---|
| R0 ADR + plan | Landed in this branch (`docs/adr/0018`, this file) | References R1–R11/F1–F3 verified online; no fabricated precision |
| R1 service lifecycle | Implemented; focused tests pass | FakeSystemd matrix + real-uvicorn readiness handshake; no unit was installed on this host |
| R2 runtime identity/status | Implemented; focused tests pass | `/api/health` + `/api/v1/runtime`; paired-phone 403 asserted |
| R3 event sources | Implemented; focused tests pass | Adapter fixtures (temp dirs, real git repo, local HTTP transport); zero-model quiet path asserted; no live public feed |
| R4 durable jobs | Implemented; focused tests pass | Restart resume, retry policy, unknown-effect block, definition fence |
| R5 document pipeline | Implemented; focused tests pass | Real poppler text extraction and real tesseract OCR of an image-only page; summarize step uses the deterministic test runtime (no live model) |
| R6 runtime UI | Implemented; captures inspected | Desktop/tablet/phone/compact + dialogs + keyboard focus; zero console errors; browser regression |
| R7 verification | Partial | Full offline suite running; live systemd install/stop/linger, live feeds, physical devices and screen-reader passes remain unverified |
