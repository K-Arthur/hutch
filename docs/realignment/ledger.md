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
| S5 providers, budgets and external runtimes | Partial; shared usage reservations implemented, adapters fail closed | OpenCode v2.0.24 is installed and its CLI contract was inspected. Existing OpenCode/Pi adapters bypassed Hutch approvals and budgets, so execution now fails before process creation. Schema v10 reserves estimated tokens/currency atomically across Hutch runs and configured accounts, settles reported use once, and holds uncertain requests for terminal-only reconciliation. Price-based currency limits are estimates, not provider-billing guarantees. Re-enable external runtimes only after sandboxing, brokered permissions and protocol tests. Pi is unavailable; no live run or paid/provider request has been made. Local calls now use one kernel-owned slot and eight FIFO waiters; human waits release the slot. Native Ollama checks current headroom before generation; other local backends lack validated memory admission, and strict modes/provenance remain pending. Latest offline suite: 1,056 passed; browser/site suite: 29 passed. |
| S6 conversations and bounded collaboration | Conversation foundation partial; collaboration pending | Schema v8 stores conversations/messages, imports each old run separately, uses bounded context snapshots in builtin runs and explicit FTS5 message search. Studio supports thread switching, durable history and archive. Transactional idempotency is tested across restart. Standing tasks, workspaces/artifacts, scoped fact memory, notifications and delegation remain. |
| S7 browser ownership and handoff | Partial | Browser context state is instance-owned and persistent profile paths are per-bot; fixture test verifies no profile crossover. Live handoff, pinned egress and browser process supervision remain unavailable. |
| S8 versioned API and remote supervision | Partial; API replay improvements in `cd4f402`; remote remains experimental | `/api/v1` covers health/status labels, bounded bot/run/approval pages, conversations/search, cross-run transcript cursors, snapshot reconciliation, usage, connection metadata, schedules and capability records. Conversation create/message/archive, stop, and approval resolve commands are idempotent; changed arguments conflict. Schema v9 adds one-use pairing codes, hash-only revocable device sessions and per-source rate limits. Direct remote binding requires explicit TLS. A durable outbox for non-run resource changes, automatic event pruning, workspaces/artifacts, phone UI, interactive control routes, trusted tunnel and live device/network checks remain. |
| S9 product integration, performance and visual validation | Partial; evidence captured in `896a774` | Final screenshots and traces cover desktop/tablet/phone, plus fixture-driven empty/loading/error/approval/cancelling/reconnecting UI states. Internal site CTA targets, phone overflow, page errors, reduced motion, tablist arrows and mobile-menu focus were checked. A misleading static `LIVE` badge is now `DEMO`. Same-harness baseline/current measurements retain raw repetitions. The full regression suite still needs to run after the latest slices. This is not screen-reader, real-device or full workflow certification. See `visual-validation.md` and `performance.md`. |

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
| `33ac3ba` | Schema-v10 usage reservations, account-shared admission, uncertain-charge reconciliation, estimates and marketing copy; offline suite 1,003 passed, provider/reservation 45 passed, browser suite 15 passed |

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

The first post-merge full-suite run reported **972 passed, 1 failed, 2 warnings**. The failure was the thread-mode timeout test
expecting a terminal status before an uncooperative Python thread ended; that test now asserts the run stays `cancelling`, releases
its controlled blocker, and verifies the eventual timeout. The PytestUnhandledThreadExceptionWarning was from a polling test helper
that survived fixture close; it now has an explicit stop event and is joined. The next full-suite run reported **973 passed, 1
warning**; the warning was invalid Python string escaping in shell parser fixtures, corrected and verified with
`.venv/bin/python -W error::SyntaxWarning -m pytest -q tests/test_shellparse.py` (**111 passed**). A final full suite is required
after the remaining implementation slices.

## Support and verification boundary

Linux is the only supported process/sandbox executor platform. macOS and Windows executor support is unavailable. The web interface is
responsive for desktop and phone; a phone is not a supported remote supervisor yet. Pairing and sessions have fixture coverage only;
the phone control UI, live control routes and physical-device validation remain open. Strict shell
containment currently depends on bubblewrap, Linux namespaces, `prlimit`, and user systemd cgroups. Existing bots migrated from older
versions remain `sandbox=off` until an operator changes the setting.

No live paid-provider call, Ollama inference, Pi run, real browser handoff, portal permission, screen-reader, or physical-device test has
been performed in this environment. Playwright covered local fixture-server journeys and synthetic UI states only. These are gaps,
not passes. The installed OpenCode binary reports `opencode v2.0.24`; only its version and help output have been inspected.

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
