# Runtime, background execution, monitoring, and durable jobs — session report (2026-10-11)

Branch `runtime/monitoring` (worktree `.worktrees/runtime`), based on local `main` `55f551b`, merged with
`main` `6221cc2`. No push, publication, deployment, tunnel, paid service, or live-host service install.

## Decision (ADR-0018)

Local-first, single-owner engine as a separately managed daemon; the web interface (and any later thin
desktop shell) attaches to it; a personal headless host is the same core under the same boundaries; shared
multi-tenant hosting is rejected as a separate, fully gated product. Evidence and references (R1–R11,
F1–F3, verified 2026-10-11) are in `docs/adr/0018-deployment-topology-and-execution-lifetime.md`;
frontend research and the approved Route A are in `runtime-ui-research-2026-10-11.md`.

## Commits

| Commit | Change |
|---|---|
| `c42da03` | Service readiness handshake, instance identity, restart, runtime status endpoint |
| `fe38cec` | Durable event sources (schema v52): adapters, transactional cursors, revision fencing, bounded admission, API/CLI |
| `af25f36` | Runtime & background work page (approved Route A), service controls, linger handling, browser regression |
| `de2405a` | Durable jobs (schema v53) and the watched-documents pipeline (real poppler + real tesseract) |
| `01c8ac1` | Merge `main` `6221cc2`: migrations renumbered (delegation v51, sources v52, jobs v53); downgrade helper extended |
| `20ca377` | Seal an orphaned handler attempt; retry only under step policy |
| `257818d` | Docs: CHANGELOG, operations semantics, ledger, plan status |
| (this) | Due-source budget regression |

## Environment (exact)

Linux 7.2.7-1-cachyos x86_64 · Python 3.13.15 · SQLite 3.53.1 · poppler `pdftotext` 26.08.0 ·
tesseract 5.5.3 · Playwright 1.63.0 / Chromium 153.0.8010.12 · FastAPI 0.142.3 · 8 cores / 22 GB RAM.
No Ollama listener and no provider keys: every model path in this session is the deterministic test
runtime. The host's live `hutch serve` processes (ports 8787, 18789) and `hutch.service` were never
touched; the isolated UI instance ran on port 18790 with its own state directory.

## Research → design → test mapping

| Finding (source) | Design response | Regression |
|---|---|---|
| `systemctl stop` is not restarted by `Restart=on-failure`; linger is opt-in (R1) | explicit stop/start-at-login controls; readiness handshake | `tests/test_service.py` (23) |
| LaunchAgents are login-session lifetime (R2) | macOS contract documented, marked unverified | — (documented only) |
| No Tauri/Electron telemetry guarantee (R3/R4) | policy stated as code behavior, not packaging | existing claims tests |
| OWASP multi-tenant gate (R5) | tenancy rejected; routes absent from paired-phone inventory | `test_paired_route_inventory…` |
| SQLite WAL single writer, no NFS (R6) | one host, one store; no network-FS claims | migrations/backup tests (existing) |
| Gmail push drops/renews; device-sync recommended (R7) | feed adapter reconciles from the authoritative list; 304/429 paths | `test_monitoring.py::test_feed_*` |
| FSEvents are advisory; dropped events need full scan (R8) | stat+hash rescan; proven-scan-only deletions | `test_monitoring.py::test_folder_*` |
| n8n stale poller after edit (F2) | registration `revision` fences late results; disable retires pending | `test_monitoring.py::test_late_check_result…` |
| Open WebUI cross-user file advisory (F3) | "references are not grants" — no tenancy shipped | route inventory + existing artifact tests |

## Verification summary (labels are deliberate)

- **Verified in this environment**: service state/readiness matrix with FakeSystemd and a real-uvicorn
  handshake (instance + PID binding); sources adapters against temp folders, a real git repository and a
  local HTTP transport; crash re-scan dedupe; revision fencing; cooldown/hourly deferral; restart
  no-replay; zero-model-call quiet path; 100-source due-query < 50 ms; job restart resume, retry policy,
  unknown-effect blocking, definition-revision fence, orphaned-handler recovery; the document pipeline
  end-to-end with **real** poppler text extraction and **real** tesseract OCR of an image-only page,
  index generations published only when complete; browser journeys at 1440/900/390/320 with inspected
  screenshots, zero console errors, no overflow.
- **Implemented but unverified**: live systemd install/stop/linger on this host; live public feeds or
  real email/social push sources (none available without accounts); the summarize step against a live
  model (deterministic test runtime used); macOS/Windows service behavior; screen-reader passes.
- **Unsupported (by decision)**: multi-tenant hosting; remote administration from paired phones;
  Windows/macOS service management.
- **Blocked**: nothing required by this slice; the full offline suite was still running at report time
  (two concurrent full suites on the host; focused integrated batch: **338 passed, 2 e2e failures under
  resource exhaustion** `net::ERR_INSUFFICIENT_RESOURCES`, which pass when run alone).

## Migrations, rollback, and preserved work

- Schema v52 (event sources, source inbox) and v53 (jobs, step ledger, index generations) are additive;
  the positional renumbering is safe because neither version was ever released. Rollback: restore the
  pre-migration `.db.bak-vN` snapshot as documented in `docs/operations.md`; the source/job tables are
  inert without their code paths.
- Concurrent lanes: `main` moved during this session (delegation identity, v51). The merge kept their
  migration as v51 and taught their downgrade helper about the new tables. The shared checkout's
  modified artifacts and other worktrees were never staged or altered.
- The user's live services were not stopped, restarted, or reconfigured; no test unit was installed.

## Remaining gaps (precise)

1. A live systemd end-to-end (install → ready → stop → linger) on a disposable VM, plus macOS/Windows
   contracts implemented and tested.
2. A live feed/source soak with independent arrivals, sleep/recovery and storage pressure (the bounded
   soak the mission describes); no live provider was authorized or available.
3. Job-level UI retry/reconcile actions (cancel exists; retry-after-review is CLI/store level).
4. R5's "inspect figures" (image extraction) is not implemented; the pipeline reads text and OCR only.
5. Performance budgets beyond the due-source query (idle daemon CPU/RSS/IO/wakeups) were not measured
   under this session's resource contention; the numbers would be unreliable and are not claimed.
