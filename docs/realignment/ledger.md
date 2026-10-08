# Continuation ledger

This is the evidence and integration log for the platform realignment. It records verified behavior separately from work that is
implemented but not yet exercised against a live dependency.

## Ownership and integration

The implementation branch is `realign/platform` in `.worktrees/realign`. It was based on the last coherent pre-realignment
history, then merged with the local `main` history in commit `0ab3058` on 2026-10-07. The merge includes the website redesign,
dashboard/Studio work, approvals reconciliation and role-based templates. It preserves both histories. Marketing copy is owned in
this worktree. Application contracts and code are reconciled here with the merged UI. No push or publication is authorized.

The main checkout may contain unrelated local tooling artifacts; preserve them during final integration. The final integration step
is a local `main` fast-forward only after all implementation and verification gates pass.

## Current slices

| Slice | State | Evidence boundary |
|---|---|---|
| S0 research, baseline and claims audit | Landed before integration | The evidence ledger distinguishes direct observations, individual reports, fixed historical defects and unverified claims. Reported failures are design scenarios, not prevalence data. |
| S1 credential routing and SSRF | Landed | Provider keys are host-scoped. Fetch checks resolved addresses, rejects non-public results, pins the connection and checks each redirect. Browser DNS is still not pinned. |
| S2 lifecycle, claims, leases and recovery | Implemented; focused tests pass | Pending claims reserve global capacity. Recovery fences expired ownership before cleanup. SQLite migrations serialize and create SQLite-backup-API snapshots. Cleanup failure remains visible and nonterminal. |
| S3 supervised run processes and teardown | Implemented; focused tests pass | Production CLI/daemon/web execution uses owned processes, recorded boot/start identity and verified cleanup. Incomplete cleanup stays nonterminal. |
| S4 shell containment and approval CAS | Implemented; focused tests pass | Bubblewrap tests pass on the present Linux host. This is namespace containment, not a VM; legacy bots retain their previous setting. Browser/external runtime tools remain outside this guarantee. |
| S5 providers and external runtimes | Partial; adapters fail closed | OpenCode v2.0.24 is installed and its CLI contract was inspected. Existing OpenCode/Pi adapters bypassed Hutch approvals and budgets, so execution now fails before process creation. Re-enable only after sandboxing, brokered permissions, usage reservations and protocol tests. Pi is unavailable; no live run or paid/provider request has been made. |
| S6 conversations and bounded collaboration | Not started | Current persistent conversational model and restart behavior still need implementation and integration tests. |
| S7 browser ownership and handoff | Partial | Browser context state is instance-owned and persistent profile paths are per-bot; fixture test verifies no profile crossover. Live handoff, pinned egress and browser process supervision remain unavailable. |
| S8 versioned API and remote supervision | Partial / not release-ready | Legacy routes and run SSE exist. `/api/v1`, durable global cursor replay, idempotency and safe phone pairing still need implementation. |
| S9 product integration, performance and visual validation | In progress | Merged desktop/tablet/mobile UI exists. The final screenshots, journey checks, accessibility review and comparable performance measurements remain open. |

## Commits

| Commit | Change |
|---|---|
| `53a2dc9` | Baseline, evidence ledger, ADRs and continuation ledger |
| `acc2261` | Claims audit and evidence-aligned safety/research/website copy |
| `522eeaf` | Provider-scoped credentials and resolved-address SSRF guard |
| `e227297` | Lifecycle, atomic claims, leases, fencing and recovery |
| `34589ee` | Owned run processes, teardown and event sequencing |
| `bf42b77` | S4 approval compare-and-swap and partial sandbox checkpoint |
| `eee309c`, `23cb0c4`, `6378dd3`, `5196655`, `309a7d3` | Local main: templates, approval reconciliation, website, Studio and research map |
| `0ab3058` | Merge local `main` into `realign/platform` |
| `ed82ce1` | S2–S4 audit repairs, docs, test corrections and truthful marketing copy |
| `98c630d` | Correct shell-test escapes and record full-suite verification boundary |
| _next commits_ | External-runtime safety gate, per-bot browser profile ownership, website and visual-validation work; hashes recorded after commit |

## Verified behavior before this checkpoint

| Check | Evidence | Result |
|---|---|---|
| Schedule occurrence race | `docs/realignment/race_schedule.py` | Six competing processes create one scheduled run; baseline created six. |
| Run claims and shared capacity | `tests/test_claims.py` | Cross-process claim uniqueness and reservation-aware global admission. |
| Cross-process Stop | `tests/test_cancel.py` | Stop from another process is persisted and reaches terminal state only after owned execution exits. |
| Lost lease fencing | `tests/test_cancel.py` | A stale worker cannot mutate state or start a new side effect. |
| Crash after effect, before receipt | `tests/test_cancel.py` | Recovery records an uncertain outcome and does not replay the action. |
| Legacy database migration and restore | `tests/test_migration.py` | Version-4 state upgrades, SQLite backup is created, and restoration retains expected state. |
| SSRF | `tests/test_netguard.py` | Hostile address forms and redirect targets are rejected; public requests use the validated address. |
| Process teardown | `tests/test_procguard.py`, `tests/test_worker.py` | Boot/start identities and pidfds are used; survivor cleanup remains visible and retryable. |
| Sandbox | `tests/test_sandbox.py` | **16 passed** on the present Linux host with bubblewrap and delegated systemd cgroups. |
| Focused core, safety, and worker suites | `tests/test_claims.py tests/test_cancel.py tests/test_procguard.py tests/test_engine_loop.py tests/test_migration.py tests/test_tools.py tests/test_sandbox.py tests/test_engine.py tests/test_runtime.py` | **100 passed** after correcting the thread-mode timeout assertion and joining the approval test helper. |
| Merged UI and templates | `tests/test_worker.py tests/test_api.py tests/test_dashboard.py tests/test_templates.py tests/test_studio_shell.py` | **98 passed**. |

The first post-merge full-suite run reported **972 passed, 1 failed, 2 warnings**. The failure was the thread-mode timeout test
expecting a terminal status before an uncooperative Python thread ended; that test now asserts the run stays `cancelling`, releases
its controlled blocker, and verifies the eventual timeout. The PytestUnhandledThreadExceptionWarning was from a polling test helper
that survived fixture close; it now has an explicit stop event and is joined. The next full-suite run reported **973 passed, 1
warning**; the warning was invalid Python string escaping in shell parser fixtures, corrected and verified with
`.venv/bin/python -W error::SyntaxWarning -m pytest -q tests/test_shellparse.py` (**111 passed**). A final full suite is required
after the remaining implementation slices.

## Support and verification boundary

Linux is the only supported process/sandbox executor platform. macOS and Windows executor support is unavailable. The web interface is
responsive for desktop and phone; a phone is not a remote supervisor until authentication and pairing are implemented. Strict shell
containment currently depends on bubblewrap, Linux namespaces, `prlimit`, and user systemd cgroups. Existing bots migrated from older
versions remain `sandbox=off` until an operator changes the setting.

No live paid-provider call, Ollama inference, Pi run, Playwright browser, portal permission, screen-reader, or physical-device test has
been performed in this environment. These are gaps, not passes. The installed OpenCode binary reports `opencode v2.0.24`; only its
version and help output have been inspected.

## Reproduction

```bash
cd .worktrees/realign
.venv/bin/python -m pytest -q --ignore=tests/e2e
.venv/bin/python -m benchmarks.run
bash docs/realignment/journeys.sh
```
