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
| S2 lifecycle, claims, leases and recovery | Implemented; focused tests pass | Pending claims reserve global capacity. Recovery fences expired ownership before cleanup. SQLite migrations serialize and create SQLite-backup-API snapshots. Schema v14 restores to a held new directory, detaches source process authority and quarantines old work. Cleanup failure remains visible and nonterminal. |
| S3 supervised run processes and teardown | Implemented; focused tests pass | Production CLI/daemon/web execution uses owned processes, recorded boot/start identity and verified cleanup. Incomplete cleanup stays nonterminal. |
| S4 shell containment and approval CAS | Implemented; focused tests pass | Bubblewrap tests pass on the present Linux host. This is namespace containment, not a VM; legacy bots retain their previous setting. Browser/external runtime tools remain outside this guarantee. |
| S5 providers, budgets and external runtimes | Partial; shared usage reservations, provider compatibility matrix, and per-bot Hybrid/Local/host-gated Offline routing; adapters still fail closed | OpenCode v2.0.24's authenticated loopback OpenAPI contract was inspected in isolated temporary state; a minimal schema fixture and bounded SSE parser now capture the installed API's experimental and volatile event-stream limits. Pi's published JSONL framing, response correlation, streamed deltas, `agent_settled` completion and `abort` command have bounded offline helper coverage. These remain protocol helpers, not process adapters: stdout/stderr drainers, brokered permission round-trips, model/instruction/session propagation and sandbox ownership remain. Local permits online tools; experimental Offline uses verified Linux bubblewrap network/PID namespaces and a per-run Unix-socket broker to reach only configured numeric loopback model endpoints, removes browser/web-fetch, scrubs provider/proxy environment, and requires process execution plus strict shell containment. This host's IPv4/IPv6/PID namespace checks and fixture Ollama request pass; no live model or backend provenance was verified. Historical systemd user-scope IP filtering failed and is recorded in D13; it is not used for network enforcement. Local Ollama/LM Studio/vLLM server provenance remains outside Hutch's worker boundary. Schema v10 reserves estimates atomically across Hutch runs and accounts, settles reported use once, and holds uncertain requests for terminal-only reconciliation. No paid/provider request or Pi invocation was made. Local calls now use one kernel-owned slot and eight FIFO waiters; human waits release the slot. Native Ollama checks current headroom before generation; other local backends lack validated memory admission. |
| S6 conversations and bounded collaboration | Conversation foundation, run-output and generated-file artifacts, scoped facts, alerts, and per-bot workspace mode implemented | Schema v8 stores conversations/messages and imports each old run separately. Schema v15 adds immutable versioned reference facts, private chat/run scope, explicit cross-chat sharing, human review, bounded FTS5 recall and paginated history. Workspaces default to fresh per run; optional 0700 Hutch-managed directories persist across one bot's runs/chats, or an operator may choose a validated user folder. They are not included in SQLite snapshots and survive bot deletion. Successful `write_file` actions can attach bounded immutable text snapshots; shell-created files are not attached. Cross-run artifact sharing, standing tasks and bounded delegation remain. Optional browser alerts are generic and tab-open only; no push delivery. |
| S7 browser ownership and handoff | Partial | Persistent profiles are per bot and protected by cross-process OS leases. A bot can opt into an experimental, same-session visible browser handoff on a Linux desktop; local fixtures cover configuration, persistence, challenge recheck, and setup cleanup. A live headed challenge has not been exercised. Browser DNS pinning and remote phone handoff remain open; browser child-process cleanup has only general worker process-group coverage. |
| S8 versioned API and remote supervision | Partial; API replay improvements in `cd4f402` and `f5696ce`; remote remains experimental | `/api/v1` covers health/status labels, bounded bot/run/approval pages, conversations/search, cross-run transcript cursors, snapshot reconciliation, usage, connection metadata, schedules, capability records, and typed device/pairing resources. Conversation create/message/archive, stop, and approval resolve commands are idempotent; changed arguments conflict. Schema v9 adds one-use pairing codes, hash-only revocable device sessions and per-source rate limits. `/pair` exchanges the code; Connections lists sessions, identifies the current device, and revokes sessions. Direct remote binding requires explicit TLS. Schema v11 adds transactional resource invalidations, history cursors, snapshot reconciliation and targeted Studio refresh. Schema v12 adds recoverable JSONL delivery and visible errors; v13 adds immutable action intents and separate outcome reconciliation; v14 adds a bounded authenticated restore report and execution-hold errors. Automatic event pruning, cross-run artifact sharing, authenticated PTY/physical desktop control, remote browser handoff, trusted tunnel and live device/network checks remain. |
| S9 product integration, performance and visual validation | Partial; evidence captured in `896a774`, `ba1e297`, and later device/workspace/browser checkpoints; schema-v16 event-throughput gate passes | Screenshots and traces cover desktop/tablet/phone and compact phone, plus fixture-driven empty/loading/error/approval/cancelling/reconnecting, pairing, workspace and local browser handoff states. Internal site CTA targets, overflow, page errors, reduced motion, tablist arrows, menu focus, pairing focus, device revocation, workspace focus/validation, and browser-setting focus/availability were checked. The no-mock slice removes seeded-run screenshots and scripted approval controls; the marketing proof is now the actual empty first-run screen. Executor health remains text-labeled and changes with health polling, without decorative pulsing between checks. Schema v16's matched event median is 1.3% above `f5696ce`, below the 20% gate. This is not screen-reader, real-device, live remote, or full workflow certification. See `visual-validation.md`, `device-pairing-visual-validation.md`, `no-mock-validation.md`, and `performance.md`. |

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
| `a148b29` | Fail-closed Pi/OpenCode, per-bot browser profile ownership, safety docs and truthful website claims |
| `4a242af` | Phone menu focus handling, responsive visual validation report, screenshots and traces |
| `31b25f8` | Schema v8 conversations, migration, bounded context, FTS5, idempotency, Studio thread UI, readable status labels, evidence corrections and updated visual captures |
| `99bade2` | Schema v9 device pairing, revocable sessions, explicit TLS binding and expanded typed `/api/v1` resources |
| `bf09d97` | Raw repeated benchmark samples, p50/p90 summary, machine/revision metadata and regression checks |
| `cd4f402` | Cross-run transcript event pages/SSE, Last-Event-ID replay, bounded snapshot reconciliation and focused real-socket tests |
| `896a774` | Same-harness baseline/current artifacts, data-quality notebook, final screenshots and demo-label correction |
| `4bdd936` | Schema-v12 recoverable transcript files, durable prerequisites, inspected UI errors and raw performance diagnosis |
| `e09e0fa` | Schema-v13 immutable action intents, once-only human reconciliation, inline/cross-bot review, migration/exception/crash tests, inspected proof and raw comparison |
| `8e1abae` | Retain exact comparison logs and the action-review commit in this ledger |
| `a5d2993` | Schema-v14 held database snapshots/restoration, no source cleanup authority, local review, restore UI, isolated migration tests, inspected screenshots and both raw performance pairs |
| `33ac3ba` | Schema-v10 usage reservations, account-shared admission, uncertain-charge reconciliation, estimates and marketing copy; offline suite 1,003 passed, provider/reservation 45 passed, browser suite 15 passed |
| `0161a7e` | Schema-v15 immutable scoped reference facts, human review/sharing, bounded FTS5 recall, chat/settings controls, truthful marketing copy and refreshed visual evidence; complete suite 1,220 passed |
| `ae3226d` | Bounded OpenCode SSE and Pi JSONL protocol helpers, installed v2.0.24 contract fixture, safer permission mapping, updated support/evidence records |
| `3a3b970` | Per-bot Local model route and Hybrid policy across Settings, API, CLI, model choices, fallback/escalation, cost estimates, docs, and marketing; known Ollama Cloud tags treated as hosted |
| `bc8d856` | Keep fixed overlays unclipped; replace strong side accents and bouncing typing dots with quieter status markers and pulse motion |
| `0a74f68` | Fix overlap between the marketing architecture diagram's connector text and model node |
| `dc14a13` | Fit architecture diagram node labels and explain tool destinations in the caption |
| `d33941b` | Versioned provider route matrix/API, evidence boundary docs, exact OpenAI endpoint field selection |
| `d6c4e83` | Narrow non-stream retries to streaming errors and verify auth/quota route approval |
| `73db64a` | Host-gated Offline inference with bubblewrap network/PID namespaces, run-scoped loopback broker, masked provider credential files, responsive route controls/captures and updated support evidence; full suite 1,297 passed (the final explanatory copy then received its focused browser recapture) |
| `ba1e297` | Remove user-facing mock execution and demo seeding, require real model routes, replace marketing mock journeys with actual empty-state captures, and verify wheel excludes test fixtures; offline suite 1,243 passed |
| `e5b9452` | Per-bot fresh/managed/folder workspace modes, isolated retained workspace directories, API/CLI/settings controls, refreshed truthful marketing copy and visual captures; 45 focused tests, five app-browser checks and eleven website checks passed |
| `0b98ebb` | Defer Studio chat-feed replacement while review dialogs are open; preserve focus across a background refresh, with refreshed file-download and fact-review captures |
| `a292608` | Correct the Stop all browser test to match the standalone login page |
| `1367516` | Schema v16 replaces per-event transcript mirror triggers with transactionally batched intent writes; adds legacy-trigger migration/backup tests, matched performance diagnosis, refreshed captures, and corrected ADR/operations/safety guidance |
| `6ee3e29` | Opt-in per-bot local Linux browser handoff, cross-process profile/desktop leases, fail-closed headless behavior, host-aware settings, setup cleanup regression, updated support claims and inspected viewport evidence |

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
| Conversation migration and API | `tests/test_migration.py tests/test_conversations.py` | Historic run histories stay separate; new conversations/messages/archive use transactional idempotency; bounded context and FTS search survive restart. **13 passed** in the focused run. |
| Run submission from web routes | `tests/test_api.py tests/test_dashboard.py tests/test_models_page.py` | Web handlers submit durable work; the elected background supervisor dispatches. **54 passed** with conversation/migration suites. |
| Full offline regression after S6/status work | `.venv/bin/python -m pytest -q --ignore=tests/e2e` | **978 passed in 241.56s**. One earlier run exposed a generated ambiguous arithmetic/substitution string that the parser correctly rejected; the property test now asserts fail-closed behavior for unreadable forms. |
| Studio conversation and status UI | `tests/e2e/test_browser.py::test_studio_conversation_survives_reload_and_archive tests/e2e/test_browser.py::test_stopping_status_uses_human_label_and_stays_nonterminal` | **2 passed** in Playwright/Chromium against the local fixture service. This does not exercise real providers or a physical phone. |
| Shell parser property suite | `.venv/bin/python -W error::SyntaxWarning -m pytest -q tests/test_shellparse.py` | **112 passed** after adding the ambiguous arithmetic fail-closed case. |
| Focused core, safety, and worker suites | `tests/test_claims.py tests/test_cancel.py tests/test_procguard.py tests/test_engine_loop.py tests/test_migration.py tests/test_tools.py tests/test_sandbox.py tests/test_engine.py tests/test_runtime.py` | **100 passed** after correcting the thread-mode timeout assertion and joining the approval test helper. |
| Merged UI and templates | `tests/test_worker.py tests/test_api.py tests/test_dashboard.py tests/test_templates.py tests/test_studio_shell.py` | **98 passed**. |
| Pairing, v1 API and approval CAS | `tests/test_remote_pairing.py tests/test_api.py tests/test_approval_cas.py tests/test_migration.py tests/test_dashboard.py tests/test_conversations.py tests/test_connections.py` | **60 passed** after schema-v9 changes; no full-suite run yet. |
| Global event cursor and reconciliation | `tests/test_sse_resume.py` | **5 passed** including cross-run ordered pagination, real-socket `Last-Event-ID` replay, bounded snapshot paging and cursor-gap handling. |
| Repeated performance comparison | `benchmarks.run` using the same harness SHA on Git-archive `b3e4b15` and clean `bf09d97` | Raw samples captured. CLI startup/status p50 are about 5% slower; mock step overhead is lower; RSS is +0.7 to +1.1 MB. CPU sampling is too coarse for a conclusion. See `performance.md`. |
| Final visual capture | `docs/realignment/capture_visual_validation.py` with Firefox 155 / Playwright 1.63.0 | Twelve page/viewport captures returned HTTP 200 with no page errors or horizontal overflow. Internal site CTAs resolve; phone navigation focus and Tab/Escape behavior pass. See `visual-validation.md`. |
| S5 full offline regression | `.venv/bin/python -m pytest -q --ignore=tests/e2e` | **1,003 passed in 224.28s** after schema-v10 reservations and shared-account admission. |
| S5 provider and reservation regressions | `.venv/bin/python -m pytest -q tests/test_providers.py tests/test_reservations.py` | **45 passed**; also exercised the fake HTTP server teardown change. |
| Per-bot workspace continuity and compatibility | `.venv/bin/pytest -q tests/test_workdir.py tests/test_api.py` | **45 passed**. Managed directories are private (0700), stable by immutable bot ID, isolated between bots and never followed through a bot-folder symlink. A reopened SQLite store resumes the same workspace, bot deletion retains it, legacy `workdir` JSON loads as folder mode, and API/CLI updates validate mode/path combinations. |
| Workspace UI, executor status and anonymous marketing site | `tests/e2e/test_browser.py::test_bot_workspace_modes_are_clear_and_persist_across_settings tests/e2e/test_browser.py::test_executor_health_status_uses_a_steady_indicator`; `tests/e2e/test_website.py` | **5 app-browser checks and 11 website checks passed**. Managed/folder settings were captured and inspected at desktop, tablet, phone and compact-phone sizes; there was no horizontal overflow or page error. The static site loaded anonymously with internal links/CTAs checked and no external requests. Fixtures only; no external folder content, model, paid provider, or remote device was used. |

The first post-merge full-suite run reported **972 passed, 1 failed, 2 warnings**. The failure was the thread-mode timeout test
expecting a terminal status before an uncooperative Python thread ended; that test now asserts the run stays `cancelling`, releases
its controlled blocker, and verifies the eventual timeout. The PytestUnhandledThreadExceptionWarning was from a polling test helper
that survived fixture close; it now has an explicit stop event and is joined. The next full-suite run reported **973 passed, 1
warning**; the warning was invalid Python string escaping in shell parser fixtures, corrected and verified with
`.venv/bin/python -W error::SyntaxWarning -m pytest -q tests/test_shellparse.py` (**111 passed**). A final full suite is required
after the remaining implementation slices.

## Support and verification boundary

Linux is the only supported process/sandbox executor platform. macOS and Windows executor support is unavailable. The web interface is
responsive for desktop and phone. The pairing page, paired dashboard and session-management UI now have local browser coverage. Remote
use remains experimental; network and physical-device validation are open, as are live browser/PTY/desktop controls. Strict shell
containment currently depends on bubblewrap, Linux namespaces, `prlimit`, and user systemd cgroups. Existing bots migrated from older
versions remain `sandbox=off` until an operator changes the setting.

No live paid-provider call, Ollama inference, Pi run, real browser handoff, portal permission, screen-reader, or physical-device test has
been performed in this environment. Playwright covered local fixture-server journeys and synthetic UI states only. These are gaps,
not passes. The installed OpenCode binary reports `opencode v2.0.24`; its authenticated loopback OpenAPI schema was inspected in isolated
temporary state without provider credentials. Its current event stream is volatile, so the external runtime remains disabled.

## Reproduction

```bash
cd .worktrees/realign
.venv/bin/python -m pytest -q --ignore=tests/e2e
.venv/bin/python -m benchmarks.run
bash docs/realignment/journeys.sh
```

The current same-harness captures and data-quality notebook are in `artifacts/performance/` and `../../benchmarks/quality_audit.ipynb`.

## Main interface integration checkpoint (2026-10-07)

Merge `70c0dae` integrated main prerequisite `6fd979f` into the realignment branch, preserving the redesigned
shell/site and canonical conversations, idempotent message submission, archived history and
authoritative lifecycle labels. Live run detail now refreshes the correct transcript; the
phone navigation sheet traps Tab and restores focus on Escape.

Verification at this merge boundary: 103 focused backend tests passed; 17 Playwright browser
and website tests passed; JavaScript syntax, generated site tokens/contrast and emoji audit
passed. The first full offline run was interrupted before producing a summary; the next run
finished with 1,009 passed in 228.41s. This checkpoint does not satisfy final release gates. Further navigation
consolidation requested by the user follows as a separate change.

## Exact-action and mount review checkpoint (2026-10-08)

The OpenBot reference review (`openbot-review.md`) led to concrete Hutch regressions and
repairs. File approvals now store the complete contents, workspace and reviewed destination
revision; the writer rejects revisions changed while waiting and uses descriptor-anchored
atomic replacement without following symlinks. Browser click/type reviews bind the destination
and profile, typing includes the text, and outward mutations always ask. Shell reviews include
effective timeout, workspace and containment. Approval events expose the persisted action hash.

A direct read-only-mount test reproduced hidden mounts under private `/tmp`. Mount order now
preserves the configured grant; read/write/unlink/create checks pass inside actual bubblewrap.
Grants reject credential descendants, outside symlinks, unreadable/oversized inspection and
covering the writable workspace. Equal-content legacy memory stays independently accessible
and deletable per bot. This does not finish reviewed/shared memory or browser account authority.

Focused verification: `tests/test_file_approval.py tests/test_browser_profiles.py
tests/test_sandbox.py tests/test_tools.py tests/test_approval_cas.py`: **50 passed in 5.79s**.
The first full run started before the mount repair and reported **1,020 passed, 1 failed in
219.06s** on the newly added mount regression. The repaired full run is pending at this
checkpoint. Browser coverage remains fixture-only; sandbox tests are actual local Linux
containment checks. No provider, real account, paid call or public exposure was used.

The repaired tree subsequently passed **1,022 offline tests in 240.14s** with background-thread
exceptions treated as failures. Commit `956b925` contains the exact-action and mount repairs.

## Conversation projection repair checkpoint (2026-10-08)

The next browser suite reported 23 passed and one failed archive/reload journey: a final
assistant event drained at completion was not projected into canonical conversation history.
Projection now shares the event/status transaction on every insertion path, and a repeated
terminal transition refuses a stale process's buffered reply. The deterministic regressions
hold the buffer and inspect a second connection. Focused conversations/claims/cancellation/
Store suite: **43 passed in 26.96s**. See `conversation-transactions.md`; no schema change,
historic automatic repair, paid call or new support claim is involved.

Commit `f4f8732` contains this transaction repair. The subsequent full offline suite passed
**1,024 tests in 261.64s**, promoting unhandled background-thread warnings to failures.

## Navigation consolidation checkpoint (2026-10-08)

Studio has one roster and one settings destination. Approval decisions share the same exact
request card in chat and a native Needs you drawer; Monitor contains Activity and run history,
with filtered Fleet available at ten bots. Ten is the operator's reversible product heuristic,
not a researched threshold. Alias history, scoped drafts, review/focus preservation, failed
refreshes, a 51-request queue, and two queued messages have browser regressions.

After the exact-action and terminal-history repairs, the complete local browser/website suite
passed **24 tests in 65.26s**. Capture produced **39 screenshots**, three traces and three
inspection sheets at desktop/tablet/phone sizes, with no page errors or horizontal overflow.
`navigation-visual-validation.md` distinguishes inspected layouts, actual mock journeys and
held synthetic states. Screenshots refresh four sanitized marketing illustrations; anonymous
CTA checks, JavaScript syntax, tokens/contrast and emoji audit pass. This remains fixture browser
evidence, not physical-device, live-provider, screen-reader or complete remote-control support.

The OpenBot repository was reviewed at `59e2889`; individual reports became concrete approval,
mount and memory regressions. The linked signed video could not be played and supplies no
visual evidence. No remote media was downloaded. Remaining S5–S8 work and release gates above
remain open; main is not advanced on the strength of this navigation checkpoint.

Navigation commit: `4bd0e0d`. A sequential same-harness baseline/current repeat reports CLI
status p50/p90 **251.5/272.2 → 261.1/271.8 ms**, dashboard RSS **59.5 → 61.3 MB**, and no
median regression beyond the harness noise gate. A heavily contended earlier capture is also
retained rather than discarded; `performance.md` records both and their inference limits.

Root main remains at `6fd979f`, with newer uncommitted composer/style work and unrelated
tooling files preserved. This branch is not a finished S5–S8 release and has not been pushed,
published or integrated by advancing main. Reconcile newer coherent main work before the
eventual final release validation and fast-forward.

## Provider authority and retries checkpoint (2026-10-08)

Audit found a hosted-to-hosted fallback bypassed the local-default-only approval rule, a
generic sticky hosted grant could span accounts, and the provider cache keyed only on key
presence. The repaired runtime approves each new hosted billing/destination authority within
the run, binds account/endpoint/protocol/revision/scope, rejects configuration changed during
review or provider creation, and refreshes credential-aware clients before calls. The unsafe
legacy credential-routing override is removed; connection/provider URLs refuse basic credentials.

The low-level stream retry also hid two model requests under one usage reservation. Builtin
recovery now retains the uncertain first attempt and reserves the non-streaming retry separately;
a constrained budget refuses that second request before sending it. No schema change is needed.
Focused provider/connection/runtime/reservation/credential suite: **138 passed in 52.74s**.
Two new retry tests initially used an unsupported fixture flag, not a broken HTTP stream; the
fake now actually closes a partial stream and both reservation scenarios pass. Full regression
verification follows this checkpoint. No live provider, paid call or new offline-mode claim.

Full offline verification subsequently passed **1,036 tests in 223.69s**, with unhandled
background-thread warnings promoted to failures. The navigation browser/capture boundary
remains `4bd0e0d`; no frontend behavior or image changed in this provider repair.

Provider repair commit: `03706f2`.

## Fleet attention refinement (2026-10-08)

Fleet previously depended on asynchronous request discovery, omitting human waits and losing
attention when that fetch failed. An older pending turn could mask already executing/waiting
work in the bot summary. Lifecycle-based attention now covers both wait states and the summary
prefers nonpending work. The legacy approval list currently returns all requests; this repair
does not assert that it was truncated at fifty. The versioned drawer remains bounded/paginated.

Desktop/phone fixtures persist 51 requests, fail queue discovery and include an older queued turn
plus a human wait. Both waiting bots remain selectable. Inspection also found the phone notice
covering Fleet metadata; it now occupies its own layout row, with 44px Review/Dismiss controls.
Focused Store suite: **10 passed in 0.24s**. Complete browser/site suite after the flow repair:
**26 passed in 53.76s**. The two new screenshots and browser/source metadata are in
`artifacts/fleet-attention/`; they are synthetic lifecycle states, not live human handoff.

The full offline suite passed **1,037 tests in 229.68s**, treating unhandled thread exceptions
as failures. The refreshed navigation capture at 08:28 UTC contains **39 screenshots**, three
traces and three current inspection sheets, with no page errors or horizontal overflow.
The two Fleet attention screenshots are separate from those 39. Source hashes pin the
`03706f2` plus refinement working tree; site derivatives now use these refreshed sources.

Fleet attention and refreshed evidence commit: `8659cb8`.

## Shutdown ownership follow-up (2026-10-08)

Code inspection found the worker's signal listener waited forever on normal completion, was not
joined, and could reach persistence after close if a late signal woke it. Cancellation cleanup
also used untracked threads, allowing cleanup to finish after final verification. Worker listeners
now wake and join on every exit; process registries coalesce and own cancellation cleanup, seal
new async cleanup at finalization, join earlier work and serialize survivor verification.

The Store also closed its connection after a timed join without checking the event writer.
It now reports a still-live writer, keeps the connection open, refuses new buffered events and
allows closure to be retried. Deterministic blockers cover this path, listener success/error/Stop
paths, cleanup coalescing and a run remaining Stopping until the prior cleanup finishes. The
first focused listener/writer/core suite passed **67 tests in 53.65s**; the expanded suite and
full verification follow. No schema, frontend or support-boundary change.

The expanded suite initially reported **82 passed, 1 failed in 85.99s**: Stop moved the run
to Cancelling before its pending request expired. This was repaired rather than weakening
the timing assertion. Cancellation now expires pending requests in the intent transaction;
new requests after cancellation persist as expired, and stale fences cannot create requests.
The repaired worker/writer/cleanup/approval/core suite passed **94 tests in 58.03s**.

Full offline verification passed **1,045 tests in 225.52s**, with background-thread warnings
treated as failures. The unreferenced admission module under development is not part of this
shutdown verification or commit; it needs its own contention and runtime integration checks.
After narrowing the new expiration guard to pending requests (preserving already decided import
records), the approval/writer/worker suite again passed **35 tests in 18.89s**.

Shutdown/Stop repair commit: `632add2`.

## Local inference admission checkpoint (2026-10-08)

The dispatcher previously let any number of same-model runs share its model reservation, counted
human waits as busy, and looked up the bot default instead of the per-message override. Admission
now uses one kernel-owned local caller and eight FIFO waiters across workers sharing the state
directory. It is per startup/call, including loading/self-check, released before tools and human
waits. Queue position/reason is persisted; Stop removes a waiter before usage reservation. Kernel
ownership releases on process death; stale ticket text grants nothing. The old slot env setting
cannot widen inference. Native Ollama rechecks current memory before generation, refuses unknown
GPU headroom and preserves measured zero. Resident-allocation credit and footprint estimates have
the limits documented in `models.md`; other local protocols lack validated memory admission.

The first four kernel tests passed after replacing a test-only multiprocessing Event with a pipe:
killing its waiting process could strand the Event's shared lock in test cleanup. The interrupted
test run was **1 passed, interrupted at 175.60s**, not a pass or a product-queue deadlock. The repaired
queue/same-model/crash/cancel/unreadable-ticket suite passed **4 tests in 0.68s**. Only the identified
test process was interrupted; unrelated operator processes were untouched.

The first runtime integration suite reported **65 passed, 1 failed in 31.06s**: moving reservations
into the admitted attempt left an outer error handler referring to an unset reservation. It now
marks uncertainty only around a sent request and preserves pre-call refusal/cancellation reasons.
The expanded suite passed **92 tests in 36.98s** and then **93 tests in 37.93s**, including human-wait
release, resumed-turn queuing, Stop without a second reservation, memory pressure and unknown/zero
GPU measurements. A separate shared-account test verifies a changed account's current policy is
used after a tool approval; provider/account snapshots refresh before each attempt.

The first queue visual fixture targeted a noncanonical legacy run through an invalid chat route:
**3 failed in 96.05s**. It now submits a canonical conversation/turn and exercises the real chat
route. The corrected desktop/tablet/phone checks passed **3 tests in 7.95s**, capturing six views
in `artifacts/inference-admission/`. These are synthetic queue/timing records, not real inference.
Full-size phone wait/timing captures were inspected: reason wraps, controls remain reachable,
there is no typing during a resource wait, and the queue segment/legend stays visible. Complete
regression, browser/site validation and refreshed navigation captures follow this checkpoint.

No schema upgrade: `queue_ms` defaults to zero in old run JSON and is now an owned progress field.
Recorded step timing excludes admitted queue wait from Hutch overhead and shows it separately.
Initial admission waits are included in the run total; interrupted waits without admission are not.
This is no strict-offline, backend-cancellation or unrelated-client concurrency guarantee. S5 modes,
provenance, browser/battery pressure and external adapter brokering remain open.

Complete offline verification passed **1,056 tests in 240.21s** and browser/site verification
passed **29 tests in 58.16s**. Full-size inspection also found the generic input width made the
desktop bot filter exceed the sidebar by its horizontal margins. A scoped width and geometry
regression repair that containment; the final viewport repeat and capture follow. This finding
was component overlap despite the page-wide overflow measure staying zero.

The final browser/site repeat passed **29 tests in 55.00s**. The 09:31 UTC capture
refreshed **39 navigation/site screenshots**, three traces and three inspected contact sheets,
with zero page errors or horizontal overflow. Source hashes pin `632add2` plus this admission
working tree. The two Fleet captures and six admission captures are separate; admission shots
use synthetic records. Full-size desktop queue inspection confirms the sidebar repair. Static
site derivatives come from the refreshed mock captures, not live provider runs.

Local inference admission and refreshed visual evidence commit: `819adf0`.

## Lease-expiry authority follow-up (2026-10-08)

Inspection found heartbeat could revive an expired lease before recovery; fence-only checks also
allowed actions, approvals, reservations, progress and status writes during that gap. Regression
setup initially reported nine failures in 0.41s: seven demonstrated current authority defects,
one required the new receipt-fence API, and one used the wrong conversation fixture signature.
The corrected event fixture separately reproduced a stale assistant reply entering canonical
history (**1 failed in 0.49s**). An initial focused command named a nonexistent test file and ran
no tests; the corrected suite passed **103 tests in 44.20s**.

Owner writes now check unexpired ownership in their transaction, heartbeat cannot revive an
expired owner, startup refuses expired process-group assignment, worker batches retain their
fence through commit, and late receipts cannot replace recovered uncertainty. Additional checks
hold a reply in the buffer across expiry and cover both writer and recovery-transition drains.
ADRs now distinguish executor completion from the still-unimplemented expectation evaluator and
receipt correlation fingerprints from deduplication/full immutable receipt arguments. No schema
upgrade or frontend change is included in this repair. Expanded/full verification follows.

The expanded authority/worker/history/reservation/provider suite passed **66 tests in 26.52s**.
Full offline verification passed **1,067 tests in 261.60s**, with unhandled background-thread
warnings treated as failures. Emoji audit is clean (244 files, nine retained waivers), and
`git diff --check` passes. No paid provider, live model or UI source changed for this repair.

Lease-expiry repair commit: `cb13791`.

## Shared composer integration (2026-10-08)

New shared-checkout frontend work was inspected before staging. Its rehearsal labels wrongly
claimed nothing executes; reads and model calls still happen. Those labels were corrected and
the old browser selector was updated to the existing thread structure, preserving completion
and error assertions. The first root browser run was **12 passed, 1 failed in 60.94s**; the
corrected run passed **13 tests in 36.20s**. Related changes only were committed on `main` as
`d7d0029`; unrelated tooling and ignore-file work was preserved. No full backend repeat there.

The merge retains canonical conversation submission, immutable approval hashes, idempotent
Stop, scoped drafts and authoritative waits. The shared options menu gained Escape/focus
restoration, viewport containment and 44px phone targets. The redundant composer Stop was
omitted; header and per-attempt Stop remain. Cancelled notices now use their actual label, and
recorded queue time is shown even without completed steps. No backend source changed.

The merged browser/site suite passed **29 tests in 63.29s**. Three new viewport journeys then
passed **3 tests in 8.18s**, exercising a real canonical mock rehearsal and synthetic cancellation
records. The final repeat passed **32 tests in 68.78s**; focused shell/conversation/approval
checks passed **22 tests in 4.54s**. The last full offline run remains `cb13791`'s 1,067 tests.
The 09:58 UTC capture refreshed **39 views**, three traces and contact sheets with zero page
errors/overflow. All three sheets and full-size desktop/tablet/phone options and tablet/phone
cancelled notices were inspected. Six composer captures are additional to the 39; Fleet and
admission fixtures were also refreshed. Website derivatives use the new isolated mock captures.
Source hashes and versions are retained. Physical devices, screen readers and live providers
remain separate verification gaps. This merge does not complete S5–S9 or permit final release.

Shared composer merge commit: `3561c89` (parents `cb13791`, `d7d0029`).

## Conversation control ownership (2026-10-08)

Follow-up inspection found a later queued message could redirect header Stop from an older
approval wait, and more than six turns could hide that request. Conversation resources now
choose active control across all attached runs, preferring executing/waiting work and excluding
other conversations. Chat binds Stop to this server target, retains its active attempt in the
bounded window, follows its live subscription and preserves review details with Retry on failure.

The initial Store regression reproduced the missing authority field (**1 failed in 0.49s**).
Focused shell/conversation checks passed **12 tests in 1.83s**, including 105 turns with the active
attempt outside message pagination. Two browser attempts each reported **1 passed, 2 failed**
(91.07s/90.94s): the synthetic fixture persisted a request without its transcript request event.
After supplying both, the real Stop/queue/failure journeys passed **3 tests in 20.47s**. The
desktop/phone captures in `artifacts/conversation-authority/` were inspected at full size;
failed refresh retains the inline request and primary Stop, with no page errors or overflow.
Waits are synthetic; the Stop command and expiration transaction are real. No schema change.
Full regression/browser repeats follow the next accounting checkpoint. Usage test additions in
the working tree are separate, currently failing baselines, and excluded from this UI commit.

Conversation authority commit: `b5848e0`.

Full-size inspection then showed the retained old request above the visible area because chat
follows the latest queued messages. A header Review control now scrolls/focuses the inline
request; unavailable details fall back to Needs you. The expanded browser journey passed
**4 tests in 24.11s** and refreshed both inspected captures. These demonstrate the actual
visible decision region, not merely a request present in the DOM. Full repeats remain next.

Phone inspection found the attempt's waiting label clipped in a tight row. It now wraps the
row without shrinking the status, and the final four journeys passed **4 tests in 25.91s**.
The refreshed full-size phone capture was inspected: complete waiting label, Review/Stop,
inline decision buttons and failed-refresh notice are all within their intended regions.

Review visibility refinement commit: `82885e4`.

## Provider settlement authority and rollover (2026-10-08)

Late settlement previously accepted a recovered/uncertain reservation, could rebind its usage
to another run/bot/model/provider, and silently ignored conflicting duplicates. Worker
accounting now supplies and checks unexpired ownership inside the settlement/release/uncertainty
transaction. Reservation identity remains fixed; an uncertain hold requires terminal-run
reconciliation. Normal duplicate settlement is exact and changed outcomes conflict. Legacy
diagnostic/import ledger rows remain separate from owned worker mutation.

The initial targeted baseline was **13 failed in 0.63s**: seven exercised existing identity,
uncertainty and missing-fence defects; six required the new accounting fence argument. A
mistyped focused filename ran no tests, then the corrected authority/accounting suite passed
**87 tests in 13.81s** and runtime suites passed **42 tests in 32.36s**. Further audit found
outstanding holds aged out at midnight/rolling-window boundaries. The rollover baseline was
**3 failed, 1 passed in 0.57s**; the passing case verifies atomic account admission in two
spawned processes. All unresolved holds now continue consuming each current allowance; only
measured ledger usage is windowed. The expanded suite passed **127 tests in 44.95s**.
No schema change or live billing claim. Full offline and browser/capture repeats follow.

The full run reported **1,084 passed, 1 failed in 257.91s**. It exposed request admission
before the run entered its human wait, so a reader saw a pending request alongside Working.
The gate now admits the request and wait in one transaction, with prior buffered events;
an invalid transition rolls back admission without losing the buffer. A deterministic second
connection verifies the boundary before the gate returns. Focused approval/admission/provider
checks passed **83 tests in 37.01s**. Follow-up checks refuse the obsolete full-request updater
and prevent an expired/stopped execution receiving approval or a sticky grant. No schema change.

Before that additional atomic-wait repair, browser/site verification passed **34 tests in 103.12s**
and the 10:17 UTC capture returned **39 views**, no page errors/overflow, three refreshed traces
and sheets. All three sheets and the full-size phone wait were inspected; the phone Review,
complete waiting label and decision region fit. Source hashes pin `82885e4` plus settlement
changes, excluding this later approval repair. New runtime/full/browser repeats follow; the
images are fixture evidence and do not prove live provider or physical-device behavior.

The expanded approval/admission/usage/history/cancellation suite passed **90 tests in 44.37s**.
The next full run reported **1,082 passed, 7 failed in 251.14s**, all obsolete test entry points:
two browser and four file review fixtures did not forward the new prior-state argument, and
one Store fixture still used the prohibited whole-request updater. They now preserve/forward
the real wait state and resolve through compare-and-swap, retaining their payload/revision
assertions. The corrected review suite passed **31 tests in 7.04s**. The final full offline
repeat passed **1,089 tests in 233.42s**, with background-thread warnings as failures. The
browser/site repeat passed **34 tests in 89.16s** after the atomic-wait source change.
Emoji audit and diff checks passed. The unreferenced durable-change module and its standalone
tests were added after full-suite collection; they are excluded from this verification and
commit and need their own Store/API integration. No paid call, push or final release.

Authority checkpoint commit: `c40336e`.

## Transactional resource replay and atomic review events (2026-10-08)

Schema v11 installs content-free invalidations in the same SQL transaction as material
resource changes. Chained committed IDs and a stable epoch detect missing ranges, including
an empty retained log, without assuming consecutive AUTOINCREMENT IDs. Typed pages/SSE share
the cursor; snapshots pin state/cursor together. A one-second poll catches silent writers.
Migration preserves v10 data with a SQLite-backup-API snapshot. Restoring/upgrading that copy
creates a distinct history. Existing resources require a fresh snapshot; connection-file
updates and automatic retention are excluded. This is not JSONL delivery or remote control.

The initial Store/API/migration integration passed **30 tests in 2.80s**. Process-death,
competing-writer, snapshot, v10 migration and real-socket replay checks passed **43 tests in
9.46s**, then crash/replay checks passed **20 tests in 6.81s**. Audit found review-event
publication still followed approval/wait admission; all three now commit together. Run/event
resources also return scoped canonical decisions, preventing a missing worker response
leaving a stale ask. The first expanded check reported **63 passed, 1 failed in 32.72s** due
to a missing json import in the new observer assertion, corrected without removing it.
The repeat passed **95 tests in 40.90s**. The full offline run passed **1,104 tests in 240.52s**
with unhandled thread warnings as failures. A later scoped-decision and v10 backup-restore
addition passed **24 tests in 1.49s** and **59 focused tests in 13.16s**; the full collection
predates that final added test, while production backend behavior is unchanged.

Three replay journeys passed **3 tests in 12.11s**, then added second-client decisions passed
**3 in 14.62s**. All three full-size captures were inspected. The browser/site run passed
**37 tests in 110.99s** before a visible-route guard. Diff review found old run-mode metadata
could refresh run detail after navigation to settings; the guard now checks the visible hash
and discards delayed run responses after navigation. The expanded run reported **36 passed,
1 failed in 129.41s** because the tablet fixture filled the old form before the new settings
response arrived. Waiting for the loaded heading keeps the late-response check meaningful;
all three corrected journeys passed **3 tests in 22.87s**. A corrected full repeat follows.

The corrected full browser/site repeat passed **37 tests in 118.02s**. Final source hashes
accompany the three refreshed replay views; the source-frozen navigation capture uses the
same application source. No source changed after its capture.

The 10:57 UTC source-frozen application/site capture returned **39 views**, no errors or
overflow, three traces and refreshed proof WebPs. All three inspection sheets and the
full-size phone wait were inspected. Captures use temporary mock state, not provider or
physical-device access. Operations now validates restore into an isolated directory and
documents epoch rotation, device revocation and uncertain post-backup effects; safe automatic
production rollback and recoverable JSONL delivery remain pending. Diff, JS syntax, token
contrast and emoji checks passed. No paid call, publication or final integration.

Resource replay checkpoint commit: `f5696ce`.

## Recoverable transcript delivery and FULL WAL synchronization (2026-10-08)

Schema v12 enqueues target sequence with canonical events and backfills historic delivery.
An owned, joined worker retries even after executor death; process file locks serialize
delivery and fsync precedes acknowledgement. Prefix verification reuses unacknowledged writes,
preserves damaged/ahead files and refuses damaged canonical hashes. File status has its own
resource invalidation, so a Done answer stays visible while a file error appears and later clears.
Startup checks missing acknowledged files, including restoration into a new directory. Delivery
has row/byte/cache bounds and fair retries; blocked shutdown keeps SQLite open. FULL WAL
synchronization now precedes acknowledgement of external-action prerequisites. No live power-cut
check was performed, and safe production rollback remains pending. ADR-0013 records boundaries.

Initial focused checks passed **28 tests in 14.14s**, **41 in 14.90s**, **43 in 15.92s** and
**91 in 27.58s**. Added byte limits/blocked shutdown passed **30 in 2.56s**. These checks precede
FULL synchronization and the cache-bound check. The initial full run reported **1,120 passed,
2 failed in 239.76s**: conversation/worker fixtures expected immediate callback delivery and
literal JSON spacing. FULL synchronization focused checks reported **90 passed, 1 failed in
38.22s**, with the same immediate worker-file assumption. Fixtures now explicitly wait for
confirmed asynchronous delivery and compare parsed transcript content; assertions remain.
The corrected full run and final browser/site capture follow below.

Three delivery-error browser journeys passed **3 tests in 7.57s**. All three full-size
desktop/tablet/phone captures in `artifacts/transcript-mirror/` were inspected. The fixture
injects IO failure; actual retry and resource replay remove the warning while retaining Done,
the canonical answer, draft and focus. No page error or horizontal overflow was observed.
This is not physical-device or live-provider evidence.

The corrected full offline run passed **1,123 tests in 240.60s**, with unhandled thread
exceptions treated as failures. The source-frozen 11:31 UTC capture returned **39 views**,
zero page errors/overflow, refreshed proof WebPs and three traces. All three inspection
sheets were reviewed after capture. JS syntax, diff, 94-token contrast and emoji checks passed.
The full browser/site run passed **40 tests in 124.66s**, including the three new mirror-error
journeys. The sequential repeated performance capture follows; no source changed after the
capture or successful full run.

The initial sequential performance comparison retained all repetitions. CLI/idle measures
were close to `f5696ce`, but event throughput fell from **72,973 to 45,107 events/s** median
(5 samples), exceeding the gate. Diagnostic running/paused/running fixtures at FULL sync
produced medians **45,077 / 44,844 / 44,817**, implicating enqueue/commit work rather than
file delivery as the dominant cost in that burst. Coalescing pending job updates improved
the subsequent fixture medians to **51,205 / 50,910 / 52,854**. These are diagnostic captures,
not a controlled release comparison; raw files are retained. A race regression checks events
committed before and after ACK remain due, and a deleted tail cannot clear a durable intent.
Focused integration passed **62 tests in 19.71s** before the final tail guard; the extended
mirror set passed **20 in 1.96s**.

Diff review also found event notifications ended the intended group-commit wait early.
The writer now accumulates until its existing size/deadline bound; FULL sync remains enabled.
A flush timeout now reports uncommitted events rather than claiming success, and shutdown
still refuses new events while retaining the database for retry. The expanded focused suite
passed **66 tests in 37.67s**. The full repeat and final recapture follow; the earlier 11:31
captures and 1,123-test run precede these refinements. The grouped diagnostic did not remove
the throughput regression; no durability protection was weakened.

The final offline repeat passed **1,126 tests in 243.33s** and all browser/site checks passed
**40 tests in 127.35s**. The source-frozen **11:48 UTC** capture returned 39 views and zero
page errors/overflow; three inspection sheets and three current full-size mirror-error views
were inspected. Final JS/diff/token/emoji checks passed. The final repeated performance
capture uses the unchanged production source from these checks and follows below.

The final repeated capture records CLI version/status medians **231.8/257.8 ms**, event
throughput **51,817/s**, mock step overhead **0.041 ms**, and idle daemon/dashboard RSS
**42.0/62.1 MB**. Compared with measured `f5696ce`, event throughput remains **29.0% lower**
and exceeds the 20% median gate. Raw repetitions, source/load context and diagnostic variants
are retained under `artifacts/performance/`; `performance.md` reports median/tail values and
the remaining regression. No safety protection was weakened to remove it. CPU remains too
coarsely sampled for an optimization claim. Captured source hashes match the final checked
tree. This is a local persistence checkpoint, not completion of S4–S9 or final integration.

### Immutable action review (schema v13; continuation of S4)

The prior persistence slice is committed as `4bdd936` (recoverable transcript files, FULL WAL
synchronization, file-delivery visibility and retained performance evidence). Schema v13 now
retains immutable tool arguments/review authority; owned action writes cannot omit a fence.
Receipt storage failure stops further tools, and uncertain receipts seal with terminal status
and its event atomically. An independent operator statement resolves review once with evidence,
reviewed intent hash and idempotency, without changing the original execution history.
Matching uncertain effects in the same conversation require reconciliation; current bounded
builtin receipt guidance also covers turns queued before uncertainty arose. Private conversations
are kept separate. Legacy arguments are not invented.

Chat review uses the existing dialog rather than a new page. Needs you also pages older and
cross-bot receipts. Source inspection/fixtures found two owned-action fixture defects, then two
new test errors (missing Path import and violating per-bot single admission); assertions were
corrected without relaxing ownership. Focused repeats passed **23 in 1.12s**, expanded runtime/
approval/usage/history/migration checks **95 in 33.35s**, then receipt/API/usage/history checks
**52 in 5.91s**. A mistyped nonexistent test path ran no tests before the corrected command.
The actual schema-v12 fixture was made using `git archive 4bdd936`; it preserves a historical
Done run with a started receipt and tests unknown arguments, original event hashes and backup.

The first four new browser journeys failed in **131.26s**. Three exposed real focus loss when
disabling the launch button before opening the dialog; the fourth attempted the phone sidebar
without opening its menu. Explicit return-focus ownership fixes the application bug, and the
fixture now uses real phone navigation. The repeat passed **4 in 10.38s**, including a server-
committed outcome with a lost response and idempotent retry, plus 22 older receipts over two
queue pages. Final source/visual/offline/browser repeats follow. These checks use isolated
fixture effects and Firefox; no paid provider, physical phone, portal or live browser handoff.

Before the exception repair, the full offline repeat passed **1,139 in 252.03s** and the
browser/site run passed **44 in 137.50s**. The 12:35 UTC navigation capture recorded 39 views
with no page errors/overflow. Nine full-size action-review views and three navigation inspection
sheets were inspected. The additional marketing-figure check passed **3 in 5.80s**; inspection
found the desktop screenshot unreadable at phone scale, so a real phone capture is now selected
at narrow widths. It does not substitute an illustration for application evidence.

Diff review then found an unhandled tool exception after effect admission could write a false
failed receipt from a placeholder result. The runtime now leaves the missing receipt uncertain
and closes tool admission. A real file effect followed by an exception is a regression fixture;
receipt/cancellation checks passed **24 in 7.46s**. Full/API/browser repeats follow. API validation
responses also omit raw arguments and serialize malformed Unicode safely instead of reflecting
private input or failing while returning an error. No validation or permission rule is relaxed.

The next repeat passed **1,140 offline tests in 253.42s** after exception handling. It precedes
the validation-response formatting guard. The concurrent browser run passed 44 and failed
three new marketing fixtures in **146.63s**: those fixtures had been collected before the
responsive `<picture>` change and still selected the image's immediate parent. They now select
the enclosing figure and assert the actual phone source. API/receipt/connection/pairing/history/
dashboard checks passed **93 in 19.80s** after the validation guard. Final source-frozen repeats
are running; earlier results are not presented as covering changes made during collection.

The frozen-source browser/site repeat passed **47 in 139.67s**. The matching 12:44 UTC capture
returned **39 views**, zero errors/overflow and three traces. All three inspection sheets and
current full-size phone action/dialog/report views were inspected; hashes match current source.
The responsive site figure was inspected at all three widths; phone selects the actual phone
capture. The figure screenshot includes the site's sticky navigation when scrolled.

The frozen offline run reported **1,139 passed, 1 failed in 248.72s**: a Usage-page fixture read
three buffered model-move events before their batch committed. The fixture now explicitly flushes
before checking committed history; no assertion or production read was weakened. Focused Usage/
receipt/writer checks passed **47 in 3.46s**, and the final full repeat passed **1,140 in 238.58s**.
All runs treat unhandled background-thread warnings as failures. JS syntax, diff, 94-token
contrast and emoji checks passed. Application/site capture hashes remain unchanged after the
fixture correction. Sequential repeated performance measurement follows, after tests/captures
finished, with the unchanged harness and a clean `4bdd936` archive. No paid or live provider call,
physical device, portal session or production restore is covered by this checkpoint.

Sequential measurements against clean `4bdd936` record CLI version/status medians
**236.4/255.1 ms**, **51,262 events/s**, mock overhead **0.066 ms**, and daemon/dashboard RSS
**42.1/63.6 MB**. No additional gate regression against that commit was observed; the prior
29.0% throughput loss against `f5696ce` remains a release limitation. CPU is too coarsely sampled
for an improvement claim. Raw samples/context are retained and validated. The final summary
import failed after both measurement subprocesses completed; its log is retained. A corrected
summary-only command validates the same captures without replacing or remeasuring them.

The new proof images now preserve their exact sanitized source PNGs and generation hashes in
`artifacts/action-receipts/proof-source*`; future fixture recaptures cannot silently change their
provenance. Website-only asset checks follow. No executor source changed after frozen tests,
captures or measurements. Main remains `d7d0029`; unrelated root work is preserved, and no
fast-forward, push, publication or production-state migration has occurred.

After regenerating receipt proof derivatives from preserved final fixture sources, all nine
anonymous website checks passed **9 in 11.32s**. The three figures were inspected. Firefox's
oversized element crop includes fixed navigation and an off-viewport skip link; a supplemental
physical-viewport capture verifies that this crop artifact is not visible skip-link behavior.
No application/site source was changed for that artifact check.

The supplemental anonymous site/viewport repeat passed **9 in 11.65s**. Physical phone view
was inspected: the receipt control and copy are readable, and the skip link remains offscreen
without keyboard focus. Source hashes still match. This completes verification for the local
schema-v13 slice; broader S5–S9 work and the throughput release gate remain open.

## Schema-v14 held database restoration, 2026-10-08

This slice adds database-only snapshots and an isolated, held restoration workflow. It does
not stop source services, restore user files or switch production service configuration.
The new directory cannot dispatch work until a local once-only review; old work remains
quarantined. Source PID/boot/start records are retained as detached evidence, never cleanup
authority. Completed run documents/transcript chains are preserved. Pending approvals expire,
devices/standing grants revoke, saved schedules pause and uncertain usage remains reserved.
See ADR-0015 and Operations for the actual commands and cutover boundaries.

Nine snapshot/restore tests cover committed WAL capture, a genuine schema-v4 fixture, manifest
damage, invalid history, linked inputs, SQLite sidecar rejection, restart, concurrent activation,
typed API errors and CLI review against changed installed code. The source-alive fixture launches
a real temporary Python process on this boot, confirms restoration neither signals it nor alters
the source state, and terminates/reaps it in `finally`. It is not a production restore test.

Initial restore checks found a raw-JSON hashing defect (fixed), a Pydantic field-name warning
(fixed by a schema alias), and fixture mistakes in process identity and cursor names (corrected).
An initial three-width browser repeat failed because button styling overrode the hidden Cancel
control. Inspection then found desktop header overlap and a phone toast obscuring Close. Those
defects were repaired and regression assertions cover unobscured controls, focus return and
44px phone targets. The dialog remains read-only and uses the existing layout rather than a
new page. Rejected submission preserves the draft; activation refreshes the hold through SSE.

The initial full offline run was **1,148 passed, 1 failed in 259.64s**. The failing filesystem
persistence fixture used fake inference with live hardware readings; its second run was correctly
refused when host headroom changed. The fixture now uses deterministic RAM while asserting
both successful status and written-file content. Production admission remains unchanged; low
headroom refusal has separate tests. The focused repeat passed **45 in 11.99s**. The final full
offline run passed **1,149 in 254.05s**, treating unhandled background-thread warnings as errors.

Frozen-source browser/site collection passed **50 in 150.85s**. Three additional anonymous site
scope checks initially failed on an incorrect metadata file name (`main.js` instead of the
actual `site.js`); after correcting that fixture, all **12 website checks passed in 15.57s**.
This is a 50-case full repeat plus a 12-case site repeat, not a claimed 53-case full repeat.
Raw initial/final logs are retained under `artifacts/restoration/`.

The matching 13:46 UTC navigation capture reports **39 views**, zero page errors/overflow and
three traces. Desktop/tablet/phone inspection sheets were inspected, as were restored details,
held/activated chat and the marketing State scope/physical viewport images at all three widths.
Restoration captures retain nine application PNGs, six site PNGs, three application traces,
versions and source hashes. Firefox 155.0, Playwright 1.63.0, Python 3.13.15 and Pillow 12.3
were recorded. Runtime/site hashes match the final frozen source; JS syntax, compile, diff
and emoji checks passed. Existing contrast tokens are reused. No screen-reader, physical-device,
live provider, portal, browser-handoff, power-loss or production-cutover certification follows.

Sequential repeated performance capture compares a clean `8e1abae` archive with this schema-v14
tree after tests and visual capture finish. The same harness and source/load context are retained.
Main remains `d7d0029`; unrelated root work is preserved. No fast-forward, paid call, push or
publication has occurred. Broader S5–S9 work and the prior throughput release gate remain open.

The first comparison crosses gates (CLI version/status +41%/+37%, events −30%). The next
unchanged pair reverses direction: previous/current CLI medians **479.9/234.7 ms** and
events **23,733/52,625 per second**. The unchanged archive itself became more than twice
as slow; substantial unrelated browser activity was observed on this shared host. Both raw
pairs and logs remain retained. This demonstrates variability, not a proved exclusive cause
or improvement. The first slowdown is not repeatable in the second pair, and the prior v12
29.0% throughput regression remains open. Current daemon/dashboard RSS is **42.4/64.1 MB**;
CPU is still too coarse for optimization claims. Samples, medians and frozen hashes validate.
See the performance report for p90, sample sizes, commands and all evidence boundaries.

The local slice commit is `a5d2993`. Its final staging check flags trailing spaces in retained
pytest/benchmark output; those raw logs are preserved byte-for-byte rather than reformatted.
The implementation/document diff was clean before adding the logs. No runtime source changed
after the frozen checks, captures or measurement pairs.

## Schema-v15 scoped reference facts and review, 2026-10-08

Schema v15 replaces the unscoped key/value memory behavior with immutable revision records in
conversation, isolated-run, bot-shared, or legacy scope. Old values migrate as unreviewed legacy
proposals; their chat ownership and prior user labels are not guessed. Exact content and revision
hashes bind human review. Only explicit sharing copies a chat fact to bot scope. Runtime recall
uses bounded literal FTS5 search over reviewed current revisions and never adds facts to system
instructions. Memory can be disabled for runtime proposal/retrieval while human review and history
remain available. Archive retains history and backups; permanent scoped deletion/export are still
unfinished. The legacy unscoped bot endpoint exposes only reviewed shared facts.

The regression set covers v14-to-v15 migration, content hashes, same-key revisions, stale-run
fences, private scope separation, explicit sharing, memory-off behavior, API idempotency and
conflicts, HTML escaping, desktop/tablet/phone review, a changed-revision conflict while the modal
is open, and focus restoration across an SSE refresh. Full review and sharing records are shown in
the chat and settings inventory. Historical Open WebUI/OpenClaw memory reports C8–C10 in the
evidence ledger became local acceptance scenarios; they are individual reports, not prevalence
claims.

Early full-suite runs exposed and fixed three real issues: the marketing proof grid expanded to
the screenshot's intrinsic width on phones, a usage API fixture could be claimed by the live test
supervisor, and an SSE refresh could detach the modal's original focus target. The site now uses a
zero-minimum responsive grid and wraps long code paths; the fixture remains outside the pending
queue; modal close resolves a fresh matching control before restoring focus. Escape on the
marketing phone drawer synchronously closes it and restores the opener. No layout, permission,
containment, or lifecycle assertion was relaxed.

The frozen-source complete command `.venv/bin/python -m pytest -q -W error::pytest.PytestUnhandledThreadExceptionWarning`
passed **1,220 tests in 386.90s**. The
three-width fact journey passed **3 tests**, then its desktop case passed **5 repeated runs**.
Chromium phone-menu/proof/state checks passed **7 tests**, the previously racing connection and
reservation fixture passed independently, and the final full run includes both fixes. The raw
full-suite and focused logs are retained in `artifacts/fact-memory/`.

Final application views for proposed, reviewed, stale-conflict, shared, and memory-disabled
history states were inspected at desktop (1440×1000), tablet (900×1024), and phone (390×844).
Chromium browser fixtures use synthetic values only. Anonymous marketing hero
views were captured with `.venv/bin/python docs/realignment/capture_marketing_top.py`; the
versioned `artifacts/marketing-top/capture.json` records Chromium **153.0.8010.12**, Playwright
**1.63.0**, Python **3.13.15**, exact source hashes, zero page errors/overflow, and local-only
requests at all three sizes. The phone proof/state and approval scenarios were also inspected.
Impeccable's final static scan found no unsuppressed findings; its three ignores are value-scoped
to `website/index.html` with recorded reasons for full-bleed dividers, decorative hero clipping,
and custom-property heading sizes.

This verification uses local fixtures and a static site only. It does not cover live models,
providers, Pi/OpenCode, screen readers, a physical phone, remote control, or deletion/restore of
production data. No new comparative performance result is claimed; the noisy historical
throughput gate remains open. S5 adapters, standing tasks/workspaces, delegation, phone control,
and final local-main integration remain incomplete.

The schema-v15 implementation and current screenshots are in `0161a7e`; this ledger's final
verification record is committed separately so it can name the completed implementation hash.

## S5 external adapter protocol boundary, 2026-10-08

An isolated `opencode serve` v2.0.24 process bound only to `127.0.0.1`, used a generated local
password plus temporary HOME/XDG directories and an empty project directory, and received no
provider credentials. `/doc` served HTML; `/openapi.json` returned OpenAPI 3.1.0 labelled
experimental API `0.0.1`. It describes `/api/event` as a volatile SSE stream that may fail on a
slow consumer and lose events during disconnects. Permission requests carry a server request id,
session id, action and resource list; replies include `once`, `always` and `reject`. Hutch's
mapping deliberately sends only `once` or `reject`. The process group was terminated and joined;
no session prompt, provider call, or external effect was issued. Current online routes differ from
the installed version, so this slice pins a minimal local contract fixture rather than treating
the online page as an installed binary specification.

The Pi helpers follow the current primary RPC docs: split raw stdout bytes only on LF, accept a
preceding CR, preserve U+2028/U+2029 inside JSON strings, correlate replies by unique id and
command, continuously consume records, collect bounded `text_delta` output, and regard only
`agent_settled` as completion. The `abort` command is framed, but no Pi executable is installed.
These helpers do not yet start a process, drain both pipes, verify sandbox/capabilities, reserve a
provider budget, or translate permission events. Both runtimes still fail before process creation.

Focused verification: `.venv/bin/python -m pytest -q tests/test_runtime_opencode.py
tests/test_runtime_pi.py tests/test_runtime.py` — **21 passed in 0.34s**. The installed schema
was queried again through an authenticated temporary loopback server; no provider connection was
made. The full command `.venv/bin/python -m pytest -q
-W error::pytest.PytestUnhandledThreadExceptionWarning` passed **1,235 tests in 361.62s**;
This is protocol-fixture evidence only; no end-to-end broker was exercised, and OpenCode event
loss is an explicit unresolved adapter gate.

## S5 local and hybrid model routes; responsive site correction, 2026-10-08

Bot settings now store an explicit `local` or `hybrid` inference policy. Local mode filters hosted
model choices and refuses hosted one-message overrides and hosted fallback/escalation before a
provider is constructed. API and CLI updates validate the selected route together with the bot's
default model. Shared route classification recognizes known Ollama `:cloud` and `-cloud` tags as
hosted for model choices, admission, estimates and currency caps; when pricing is unknown, a
configured currency cap refuses the route rather than treating it as free. Local mode only
recognizes known hosted routes: it does not enforce strict network isolation, constrain tools, or
prevent a custom local endpoint from proxying requests. Settings and marketing copy state this
limit. Strict Offline is implemented as a host-gated experiment; the later status in this checkpoint records the current host's failed isolation probe and the remaining verification gap.

The focused provider/API/CLI regression group
(`tests/test_providers.py tests/test_model_switcher.py tests/test_runtime_builtin.py tests/test_api.py tests/test_cli.py`)
passed **109 tests**. Strict Offline has since been implemented as a host-gated experimental mode:
it requires verified Linux systemd egress isolation, a process executor, loopback model routes,
and strict shell containment when shell is enabled. The current host failed the local-only
non-loopback isolation test, so the capability is unavailable here and the successful-host
end-to-end journey remains unverified. Local mode remains a routing preference and does not
isolate tools or local model services. The complete non-browser suite
`.venv/bin/python -m pytest -q --ignore=tests/e2e -W error::pytest.PytestUnhandledThreadExceptionWarning`
passed **1,189 tests in 251.93s**. The phone route-setting journey passed separately; no live
provider, local model, or paid call was used. After the site diagram correction, the anonymous
website browser tests passed **12 tests in 11.79s**, and the phone route-setting journey passed
**1 test in 1.90s**.

The final Firefox/Playwright capture at `dc14a13` records **42 screenshots**, including explicit
local-route Settings on desktop, tablet and phone, at 1440×1000, 900×1024 and 390×844. All
reported page-error lists and horizontal-overflow counts are empty. Desktop site-fold, tablet
architecture diagram, phone diagram and FAQ sections were visually inspected. The inspection
found and corrected overlapping connector and node labels; the recaptured architecture diagram
fits the narrower viewports. Metadata, source hashes, three traces and screenshots are under
`docs/realignment/artifacts/navigation/`; browser fixtures are local demo data, not live-device or
provider evidence. Impeccable's final static scan returned no findings for the application and
marketing files.

This closes the local/hybrid route-mode checkpoint only. At that point, provider compatibility and
failure matrices, verified external runtime adapters, enforceable strict-offline behavior, remaining
S5 work and S6–S9 release gates were open. The historical systemd-based Offline attempt is
superseded by the network-namespace repair below; its failed local probe remains recorded as D13.

## S5 provider compatibility route matrix, 2026-10-08

`GET /api/v1/compatibility` now returns a typed, versioned route matrix with request fields sent
and omitted, dated API/policy sources, implementation status and an explicit fixture/live
verification boundary. The matrix covers the built-in OpenAI, Anthropic and Ollama routes,
generic compatible connections, OpenCode Go, Sign in with ChatGPT, disabled OpenCode/Pi
executors, and the blocked consumer-session route. It is bundled in the wheel. `supported`
means a common protocol contract has fixture coverage; model and endpoint capabilities remain
unknown until separately probed. ADR-0005, architecture, connection/model configuration, tests,
roadmap and changelog now state that distinction.

The OpenAI-compatible adapter previously selected `max_completion_tokens` by looking for the
string `api.openai.com` anywhere in the URL. It now selects that field only for the exact official
HTTPS authority on the standard port; lookalike domains, proxy paths, HTTP and nonstandard ports
use the compatible `max_tokens` field. This corrects the field dialect decision; it does not
change provider credential routing.

Verification: `.venv/bin/python -m pytest -q tests/test_compat.py tests/test_providers.py
tests/test_api.py` — **53 passed in 17.27s**; `compileall` passed for the changed Python modules.
`uv build --wheel` succeeded, and archive inspection confirmed both `hutch/compat.py` and
`hutch/data/compat.json` are included. `git diff --check` passed. Live provider/model capability,
tool probes, provider failure journeys, strict offline enforcement, paid account behavior, and
external runtime adapters remain unverified or incomplete; the full regression gate remains open.
Implementation commit: `d33941b`.

## S5 provider rejection and paid-route approval, 2026-10-08

Review found that every 400/422 response was treated as a possible streaming failure. That caused
the builtin runtime to resend a provider's generic invalid-field response once with streaming
disabled, even though the invalid field remained in the body. The retry predicate now requires
the error to identify stream/SSE incompatibility; typed `stream` transport failures retain their
existing bounded retry. A generic field rejection stops after one request and leaves its usage
reservation `uncertain` for explicit reconciliation rather than assuming it was free.

Fixture integration also covers an OpenAI key rejection and a quota response. The quota case
exercises the existing single bounded retry on the same route; both cases reach an outward review
before a different paid account is constructed, and denial leaves it uncalled. No live provider,
paid account or billing behavior was tested. The existing hosted-to-hosted outage regression
also confirms the exact authority review cannot be bypassed with a generic sticky grant.

Focused command `.venv/bin/python -m pytest -q tests/test_providers.py
tests/test_provider_authority.py tests/test_runtime_builtin.py
-W error::pytest.PytestUnhandledThreadExceptionWarning` passed **85 tests in 47.40s**.
`git diff --check` passed. Implementation commit: `d6c4e83`.

## S5 Strict Offline network boundary repair, 2026-10-08

The initial systemd user-scope filter was not a usable boundary. On this host,
`IPAddressDeny=any` plus a loopback allowlist was accepted by `systemd-run --user --scope`, but a
child connected to a test TCP listener on the host's `10.0.0.109` address. This local-only negative
result is preserved as D13. Hutch starts the worker inside bubblewrap's fresh network/PID namespace
set. The only model traffic path is a private run-scoped Unix socket mounted read-only into that
worker; its supervisor-side broker forwards only to each validated numeric loopback model origin.
The broker rejects alternate authorities, methods, transfer-encoding, ambiguous lengths and
oversized requests, and caps concurrency and request size. Browser/web-fetch remain omitted, the
provider environment is scrubbed, saved `connections.json` and `keys/` are hidden with read-only
empty mounts, and shell uses strict nested containment without starting a separate host systemd
scope.

Fresh `offline_egress_status(refresh=True)` passed against IPv4/IPv6 loopback and host-interface
TCP listeners while completing a two-byte Unix-socket exchange. The integration test then fetched
fake Ollama version metadata from inside an isolated worker. A second test exercised the production
process engine, completed a fake Ollama chat through the per-run broker and confirmed the broker
was reclaimed after worker exit. `tests/test_offline_mode.py` passes **37 tests**, including a
real-process check that saved provider definitions and key files are hidden. Offline workers use
bubblewrap's full namespace set, and the host probe verifies that the process sees only PIDs 1 and
2. These checks use only listeners and fake model fixtures on this machine; they did not contact a
public host or a real model. The capability remains `experimental`, and the separate model service can still proxy
requests or download weights. This does not close the live-model portion of the S5 gate.

The route-setting visual scenario was recaptured with Chromium 153 / Playwright 1.63 at desktop
(1440×1000), tablet (900×1024) and phone (390×844), including the scrolled phone routing control.
All viewport captures fit without horizontal overflow, the page-error list is empty, and the phone
control remains visible. PNGs, the trace and capability/source metadata are stored under
`docs/realignment/artifacts/strict-offline/`; this is browser-fixture validation, not a physical
device or live-model check.

Full regression gate after the full-namespace probe, broker shutdown-race fix, endpoint validation,
credential-file masks, API capability label and docs update: `.venv/bin/python -m pytest -q
-W error::pytest.PytestUnhandledThreadExceptionWarning` passed **1,297 tests in 379.69s**. This
includes the browser suite and treats unhandled background-thread exceptions as failures. No
provider or model outside the local fake fixture was contacted. Incidental rewrites to prior visual
test artifacts were restored; the inspected Strict Offline captures remain recorded in their own
directory.

After that full run, only the static explanatory sentence in the responsive settings view and its
supporting documentation changed, to describe both network and PID isolation. The affected
Chromium/Playwright journey passed separately in **2.81s** and refreshed the desktop/tablet/phone
captures and trace. No other implementation behavior changed after the full-suite run.

## No user-facing mock execution and truthful first run (2026-10-08)

Commit `ba1e297` removes `MockRuntime`, `hutch demo seed`, and seeded run/transcript/approval
images from the product and marketing site. `hutch init` now creates only local state. CLI/API
creation requires a valid real provider/model route, checking hosted credentials and terms when
applicable; local service reachability is checked at execution. Migrated mock records remain
auditable but fail with `model_unavailable` before any worker or action. Test scenarios now live
under `tests/support/`, are gated by the explicit test harness and do not enter the built wheel.
Restore-held run requests check the review hold before route validation, including CLI submissions.

The marketing proof now uses a real empty first-run view. The capture script verified empty bots,
runs, approvals, conversations and configured connections, under a clean environment with no
provider credentials. Chromium 153.0.8010.12 / Playwright 1.63.0 captures at desktop 1440×1000,
tablet 768×1024 and phone 390×844 report no page errors or horizontal overflow. The anonymous
website suite passed **11 checks in 11.26s**, including CTA destinations, local assets, reduced
motion and mobile focus restoration. Desktop/tablet/phone site captures were visually inspected;
the corrected hero badge describes local control rather than a fictitious resident bot.

The full offline suite passed **1,243 tests in 258.74s** with `PytestUnhandledThreadExceptionWarning`
and `SyntaxWarning` treated as failures. `uv build --wheel` succeeded; archive inspection confirmed
the package excludes `tests/`, `src/hutch/runtime/mock.py` and `src/hutch/demo.py`. No live provider,
local model, Pi/OpenCode invocation, remote phone control or physical-device check was performed.
This closes the no-mock/product-truth slice only; the S5 adapter boundary, S6 workspaces/tasks and
delegation, S7 live browser handoff, S8 remote interactive control, and final S9 release gates remain.

## S6 Run-scoped, verifiable tool-output artifacts (2026-10-08)

Tool results that exceed model context are now saved under their source run as exclusive,
owner-read-only numbered files. The committed `tool_result` event records the run-relative path, byte
size, character count and SHA-256. A bounded typed endpoint pages these versions in event order;
the download endpoint verifies the recorded size and hash again, opens every path component through
no-follow directory descriptors, and rejects missing, oversized, symlinked or changed content.
Legacy artifact references without a recorded digest remain visible as `unverified` and cannot be
downloaded. The chat puts the download next to the clipped output, with the digest prefix and byte
size. This is per-run history, not yet a stable cross-run workspace or shared artifact library.

The regression scenario writes two outputs from the same tool and checks that they receive distinct
versions. API coverage checks ordered pagination, same-run scope, full downloads, event hashes,
tampered bytes, final-file and parent-directory symlinks, and an old unverified event. The browser
journey downloads the first version using keyboard activation at desktop (1440×1000), tablet
(768×1024), and phone (390×844). Chromium 153.0.8010.12 / Playwright 1.63.0 recorded zero page
errors, zero horizontal overflow and matching SHA-256 values. Screenshots and source hashes are in
`docs/realignment/artifacts/versioned-artifacts/`. These captures use
`tests.support.TestScenarioRuntime`; they make no Ollama or hosted-provider calls.

That acceptance work also repaired the restore-held conversation response to return the restore
review conflict before model-route validation, and uses a real local-model route in the settings
journey rather than a retired mock route. The focus-return test waits for the equivalent review
control after live transcript refresh replaces its DOM node.

Focused verification passed **3 tests in 3.60s** after descriptor-relative file access and the final
read-path cleanup. The complete offline suite, including all browser journeys, passed **1,301 tests
in 370.98s** with `PytestUnhandledThreadExceptionWarning` and `SyntaxWarning` treated as failures.
`git diff --check` passed. No real provider, model, phone or physical device was used.
Implementation commit: `b68ad95`.

## S6 Opt-in browser alerts for active review (2026-10-08)

The Needs you drawer now lets a person enable or disable browser notifications. Permission is
requested only from that click. When the Hutch page is backgrounded, a newly increased approval or
uncertain-action queue can produce one generic notification. Its title and body include no bot,
conversation, prompt, tool, destination or arguments. Selecting it focuses the page and opens Needs
you. Permission state remains browser-managed; the local opt-in lives in browser storage. Poll and
resource invalidations share a duplicate guard. Visible-tab changes remain covered by the existing
badge and live announcer.

This is explicitly tab-open notification only. There is no service worker, closed-tab push, webhook,
sleeping-host wakeup or phone-device delivery. The tested browser grants permission through a local
API stub and simulates background visibility; no OS notification was requested or shown. Chromium
153 / Playwright 1.63 captures of the Needs you drawer at desktop 1440×1000, tablet 768×1024 and
phone 390×844 report zero page errors and zero horizontal overflow. Anonymous marketing site tests
also pass after its copy was qualified. Capture and source-hash metadata are in
`docs/realignment/artifacts/browser-alerts/`.

Focused verification passed **14 tests in 23.87s**, covering opt-in/opt-out, private generic notice
text, deduplication, click-through to the queue, existing inline chat approval, unchanged review
focus, and the anonymous site suite with no broken CTA or overflow. The first subsequent full
run had **1,301 passed and 1 test-harness NameError** caused by a missing test import; the import
was restored, and the complete browser/website suite then passed **58 tests in 108.44s**.
Desktop/tablet/phone Needs you captures were inspected. Updated anonymous marketing captures and
their source metadata are retained under `artifacts/browser-alerts/website/`; all three show zero
page errors and horizontal overflow. The full repository suite then passed **1,302 tests in
368.81s** with `PytestUnhandledThreadExceptionWarning` and `SyntaxWarning` promoted to failures.
Implementation commit: `ceb9369`; verification checkpoint: `5b8ea61`.

## S4 rendered untrusted-content regression (2026-10-08)

The existing renderer escapes prompt text, assistant answers, tool arguments and tool output before
inserting the surrounding trusted UI markup. A hostile fixture containing an image `onerror`, SVG
`onload` and `javascript:` link stays literal text; no injected nodes or handler execution appear
before or after revealing clipped output. The browser check runs at desktop and phone sizes and
stores inspected captures plus browser/source metadata in `artifacts/untrusted-content/`.

Focused Chromium/Playwright verification passed **2 viewport cases in 2.86s**, with no page errors
or horizontal overflow. The full **1,302-test** run in `8ee8c45` predates this added test; a final
full rerun remains required. This proves transcript rendering for the tested fields only. It does
not establish browser-page egress safety, permission isolation, or immunity to every authority
escalation path. No application renderer code changed and no live page/provider was contacted.
Implementation/evidence commit: `17a041c`.

## Paired-device dashboard checkpoint (2026-10-08)

The experimental pairing code now has a usable `/pair` page and a paired-device disclosure in Connections. A successful exchange
stores the revocable device credential in an HttpOnly cookie; the typed device endpoint marks the current session server-side. The UI
can revoke another device or itself, returning a self-revoked browser to `/pair`. Anonymous visitors can reach the pairing form without
the app navigation or local state-directory disclosure. Marketing claims and operating instructions now describe this as experimental
and retain the private-network/TLS boundary.

Fixture coverage exercises invalid and single-use codes, current-device identification, both revocation paths, secure cookie flags,
and the login-to-pair route. Chromium 153.0.8010.12 / Playwright 1.63.0 covered desktop (1440×1000), tablet (900×1024), phone
(390×844), and compact phone (320×740), including keyboard focus, 44px touch targets, zero page errors and zero horizontal overflow.
The inspected screenshots and a redacted interaction trace are in `artifacts/device-pairing/`. A raw Playwright trace briefly captured
fixture credentials during development; it was removed before commit and is not retained. Anonymous website, templates and pairing
tests passed **76 tests in 42.91s**; the dedicated pairing browser journey passed **1 test in 3.00s**. These are local fixtures, not a
physical phone, remote-network or TLS deployment test. `git diff --check` passed. A full suite rerun follows this checkpoint.

Implementation commit: `6ef14d8`.

## S6 generated-file downloads checkpoint (2026-10-08)

OpenBot issue [370](https://github.com/CopilotKit/openbot/issues/370) is one user's report that generated files were difficult to find and download; it is treated as an acceptance scenario, not evidence of prevalence. Hutch now places a keyboard-accessible download beside successful `write_file` activity in the originating chat. It snapshots the exact successful text-write arguments (not a later read of a shared workspace path), records the immutable artifact reference, filename, size and SHA-256, and verifies size/hash again when serving the file. API pagination returns tool-output and generated-file records separately, including when both reference the same `tool_result` event. Rehearsed writes never attach an existing file. A failed snapshot leaves the successful workspace write intact and displays why no download is available.

Each text snapshot is limited to 4 MB and generated/output artifacts share a 16 MB per-run storage limit. Only `write_file` text contents are attached; arbitrary shell-created files remain in the workspace. This does not provide a stable cross-run artifact library. Oversize and exhausted-quota behavior have unit coverage; a live provider or model was not used.

Backend verification: `.venv/bin/pytest -q tests/test_runtime_builtin.py tests/test_api.py` passed **54 tests in 34.16s**. Browser/site verification: the two artifact journeys plus `tests/e2e/test_website.py` passed **13 tests in 14.65s**. Chromium 153.0.8010.12 / Playwright 1.63.0 captured keyboard downloads at desktop 1440×1000, tablet 768×1024 and phone 390×844; all three screenshots recorded matching content hashes, zero page errors and zero horizontal overflow in `artifacts/generated-files/`. The anonymous marketing site also passed its internal-link and CTA checks and had no external requests. Captures were visually inspected. `compileall`, JavaScript syntax, `git diff --check` and the Impeccable detector passed (`[]`). These are local fixtures, not a live-provider or physical-device test.

Implementation commit: `75a2641`.

## S6 Studio file-discovery refinement (2026-10-08)

The first generated-file link was inside the collapsed technical tool details. Studio now displays each verified write-file download as a compact attachment below the activity line, both for individual tool calls and for grouped calls. A snapshot failure also remains visible outside the collapsed details. This keeps file access in the ongoing chat and adds no separate navigation destination.

The browser journey now submits a conversation-backed fixture run and confirms the file link is visible while tool details remain collapsed. Keyboard activation downloads the expected filename and bytes. The refreshed desktop, tablet and phone captures are visually inspected in `artifacts/generated-files/`; Chromium 153.0.8010.12 / Playwright 1.63.0 reports matching hashes, zero page errors and zero horizontal overflow. Focused Studio checks passed **3 tests in 5.12s**, covering generated-file chat access, existing clipped-output downloads and conversation reload/archive. `node --check`, `git diff --check` and the Impeccable detector passed (`[]`). Fixture only; no provider call or physical device was used.

Implementation commit: `e39e51e`.

## Studio review focus and repository verification checkpoint (2026-10-08)

A background conversation/fact refresh could replace chat content while a reference-fact review dialog
was open. Closing the dialog then attempted to restore focus to an element that the refresh had
removed. Studio now defers the feed's DOM replacement while a modal is open and applies the pending
refresh after the modal restores focus. The browser regression triggers a real resource refresh while
the review dialog is visible, checks that the dialog stays open, and confirms Escape returns focus to
the review control. This guards dialog behavior when asynchronous chat data changes; it does not
replace the existing server-side compare-and-swap authority checks.

The latest offline suite passed **1,254 tests in 261.16s** using
`.venv/bin/python -m pytest -q --ignore=tests/e2e -W error::pytest.PytestUnhandledThreadExceptionWarning -W error::SyntaxWarning`.
The dashboard regression test now asserts that Stop all is present in the application header and
stops a run, while the standalone `/login` page has no application header. The latest full browser
and anonymous-site suite passed **67 tests in 153.70s** using
`.venv/bin/pytest -q tests/e2e -W error::pytest.PytestUnhandledThreadExceptionWarning -W error::SyntaxWarning`.
The first full browser attempt exposed the focus race; after adding the deferred-refresh behavior and
regression, the complete suite passed. These were separate full-suite invocations, for **1,321
passing test results combined**, not one single pytest run. A focused rerun of the generated-file and
fact-review captures then passed **4 viewport cases in 9.14s**.

Fresh Chromium 153.0.8010.12 / Playwright 1.63.0 captures and source hashes for generated-file chat
downloads and fact-review dialogs are retained under `artifacts/generated-files/` and
`artifacts/fact-memory/`. Desktop, tablet and phone captures were visually inspected; both journeys
record zero page errors and zero horizontal overflow. The browser suite uses local fixtures: there
were no paid-provider calls, live model requests, or physical-phone checks. These results close the
focused chat review/file-discovery checkpoint only; final integrated visual validation and live
provider, model, and device checks remain open.

Implementation commits: `0b98ebb` (refresh-safe dialog focus) and `a292608` (login-header test scope).

## Schema-v16 batched transcript mirror intents and performance repair (2026-10-08)

The matched event benchmark reconfirmed the schema-v12 throughput loss: with one current harness,
`f5696ce` measured **75,894 events/s** and the pre-fix schema-v15 tree measured **51,348 events/s**
(32.3% lower p50). A test-only running / trigger-disabled / running diagnostic measured medians of
**51,593 / 77,280 / 50,670 events/s** while keeping `synchronous=FULL`. It disabled the legacy
`transcript_delivery_insert` trigger only in one temporary database and intentionally had no durable
mirror intent, so that mode is diagnostic evidence and not a product configuration.

Schema v16 removes that per-event trigger. `_insert_events` now creates one pending transcript-file
delivery intent for each committed run batch in the same SQLite transaction as its hash-chained
canonical event rows. An existing pending intent still coalesces later batches; status reads derive
the latest target from committed event rows, and the acknowledger rechecks the canonical tail before
clearing pending. Migration preserves existing delivery rows and creates a SQLite backup before
dropping the old trigger. A regression constructs a v15 database, upgrades it, verifies that the
v15 backup still contains its trigger, and delivers both existing and newly appended events.

The full offline suite passed **1,255 tests in 261.04s**, promoting unhandled thread exceptions and
syntax warnings to failures. The full browser and anonymous-site suite passed **67 tests in
152.31s** under the same warning policy; those are separate invocations for **1,322 passing test
results combined**. Four focused generated-file/fact-review viewports passed in **13.04s** after
the full capture pass. Desktop, tablet and phone captures for both journeys were inspected under
`artifacts/generated-files/` and `artifacts/fact-memory/`; they report zero page errors and zero
horizontal overflow. All browser/provider behavior here uses local fixtures, not live models,
external providers, or a physical device.

The post-v16 matched repeat measured **77,997 events/s** versus **77,012 events/s** at `f5696ce`
(+1.3% p50); event p90 was **78,233 versus 78,544 events/s**. The comparison reports no regression
above its gates. Mock step overhead differs by 0.071 ms (below its 0.5 ms absolute noise floor),
and daemon/dashboard RSS differs by +0.6/+2.8 MB (below the 4 MB floor). FULL synchronization
remains enabled. Raw samples and source/load context are under `artifacts/performance/`; the 73
captured Python source hashes match implementation commit `1367516`. This resolves the historical
event-throughput release gate without weakening transcript durability.

Implementation commit: `1367516`.

## Local browser handoff checkpoint (2026-10-08)

Commit `6ee3e29` adds an opt-in per-bot `local_browser_handoff` setting through the model,
CLI, API, server-rendered form and Studio. The owned Playwright browser opens headed only when
enabled and host prerequisites are present. Profile and one-at-a-time local handoff leases use
cross-process OS locks. Login/CAPTCHA/MFA walls pause only when a person can use the same visible
browser; Resume reloads and rechecks the challenge. Headless runs return a clear failure instead
of entering a misleading human wait. Failed route setup tears down the browser/driver and releases
the profile lease; any failure during that cleanup is included in the setup error, and worker
process-group verification remains the authority for surviving browser children.

The full offline suite passed **1,258 tests in 267.35s** with thread exceptions and syntax warnings
treated as errors. Focused browser/profile/API/CLI/view tests passed **17 tests in 2.52s**. The
settings journey passed **3 Chromium 153.0.8010.12 / Playwright 1.63.0 viewport cases in 88.44s**
at desktop 1440×1000, tablet 900×1024 and phone 390×844. It checks API-backed capability text,
phone target size, keyboard Tab/focus, server-backed persistence, page/console errors and overflow.
The first phone pass found a 38px control; the final control is 44px. Screenshots and traces are
retained in `artifacts/local-browser-handoff/` and were inspected. The final Impeccable detector
returned `[]`; JavaScript/Python syntax and `git diff --check` passed.

This is local fixture evidence only. No model/provider was called and no real headed browser
challenge, physical phone, remote control, or cross-browser matrix was exercised. Browser egress
still has a DNS-rebinding window; remote phone handoff, PTY/physical desktop access and pinned
browser egress remain open. UI audit limitations are recorded in `visual-validation.md`.
