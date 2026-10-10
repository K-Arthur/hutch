# Continuation ledger

This is the evidence and integration log for the platform realignment. It records verified behavior separately from work that is
implemented but not yet exercised against a live dependency.

## Ownership and integration

The early realignment work was developed on `realign/platform` in `.worktrees/realign`, based on the last coherent pre-realignment
history and merged with local `main` through `0ab3058`, `cf82f73` (main `44ca869`), and `fdf6592` (main `307ce1d`). The merges
preserve both histories. After the user's 2026-10-09 direction to continue on `main`, application and marketing work continued in
the shared `/home/kevina/CodingProjects/hutch` checkout; the schedule-control slice is committed there as `8a87ac9`. Main's PF-2
tool-output source-card change (`c0ebc21`) was integrated through merge `6fab391`; its direct file route was adapted to Hutch's
recorded size/hash verifier instead of retaining an unchecked path-only `FileResponse`. No push or publication is authorized.

Continue in the requested shared local `main` checkout. Preserve unrelated tooling paths and inspect/stage only reviewed task
files. The shared design-system slice is now committed as `462a374`; remaining slices will be committed directly to local `main`
after their tests and visual review. Do not push or publish.

## Current slices

S5 continuation, 2026-10-09: schema v37 now stores one immutable positive `function_tool_calls` observation per exact
connection/account/model/route revision. The record is made only after an owned run's shared-account usage reservation is
settled or retained as uncertain and Hutch validates a declared tool call's arguments. Invalid calls and draft-only runs do not
count; no record remains unknown. `GET /api/v1/model-capabilities` exposes bounded keyset pages without prompts, arguments or
credentials. This is passive fixture-backed evidence, not a live provider guarantee or an extra paid probe. The effective
`OLLAMA_HOST` is included in built-in route identity, correcting the local endpoint mismatch exposed by pinning this route.

S6 continuation, 2026-10-09: schema v38 adds explicit, participant-revocable snapshots for one current reviewed memory fact
shared with one named Bot. Source revisions, archive and memory-disable state block new recall; the content-free change feed
exposes only participant IDs. Runtime recall carries provenance and an untrusted-data label. Local backup/restore retains the
grant for held operator review. Desktop, tablet and phone share/revoke flows are covered by synthetic Chromium fixtures.

| Slice | State | Evidence boundary |
|---|---|---|
| S0 research, baseline and claims audit | Landed before integration | The evidence ledger distinguishes direct observations, individual reports, fixed historical defects and unverified claims. Reported failures are design scenarios, not prevalence data. |
| S1 credential routing and SSRF | Landed | Provider keys are host-scoped. Fetch checks resolved addresses, rejects non-public results, pins the connection and checks each redirect. Browser HTTP(S)/WebSocket requests now use the pinned loopback proxy. A loopback STUN fixture verifies that Hutch's Chromium does not send direct WebRTC UDP; other non-HTTP traffic and live public destinations remain unverified. |
| S2 lifecycle, claims, leases and recovery | Implemented; focused tests pass | Pending claims reserve global capacity. Recovery fences expired ownership before cleanup. SQLite migrations serialize and create SQLite-backup-API snapshots. Schema v14 restores to a held new directory, detaches source process authority and quarantines old work. Cleanup failure remains visible and nonterminal. |
| S3 supervised run processes and teardown | Implemented; focused tests pass | Production CLI/daemon/web execution uses owned processes, recorded boot/start identity and verified cleanup. Incomplete cleanup stays nonterminal. |
| S4 shell containment and approval CAS | Implemented; focused tests pass | Bubblewrap tests pass on the present Linux host. This is namespace containment, not a VM; legacy bots retain their previous setting. Browser/external runtime tools remain outside this guarantee. |
| S5 providers, budgets and external runtimes | Partial; shared usage reservations, provider compatibility matrix, and per-bot Hybrid/Local/host-gated Offline routing; adapters still fail closed | OpenCode Go uses the provider-issued API-key handoff; it does not import OpenCode's private sign-in state. Conversation-backed runs now reuse their Hutch conversation ID as OpenCode's session header; standalone scheduled runs use their run ID. ChatGPT's local SIWC route matches the current preview tool contract by sending Hutch functions through `additional_tools` input items. Reauthorization retains the selected client/host IDs and uses the saved ID token only as `id_token_hint`; `login_hint` and displayed account email require a verified claim. A browser fixture intercepts the authorization destination locally; eligibility and live account authorization remain unverified. OpenCode v2.0.24's authenticated loopback OpenAPI contract was inspected in isolated temporary state; a minimal schema fixture and bounded SSE parser now capture the installed API's experimental and volatile event-stream limits. Pi's published JSONL framing, response correlation, streamed deltas, `agent_settled` completion and `abort` command have bounded offline helper coverage. These remain protocol helpers, not process adapters: stdout/stderr drainers, brokered permission round-trips, model/instruction/session propagation and sandbox ownership remain. Local permits online tools; experimental Offline uses verified Linux bubblewrap network/PID namespaces and a per-run Unix-socket broker to reach only configured numeric loopback model endpoints, removes browser/web-fetch, scrubs provider/proxy environment, and requires process execution plus strict shell containment. This host's IPv4/IPv6/PID namespace checks and fixture Ollama request pass; no live model or backend provenance was verified. Historical systemd user-scope IP filtering failed and is recorded in D13; it is not used for network enforcement. Local Ollama/LM Studio/vLLM server provenance remains outside Hutch's worker boundary. Schema v10 reserves estimates atomically across Hutch runs and accounts, settles reported use once, and holds uncertain requests for terminal-only reconciliation. No paid/provider request or Pi invocation was made. Local calls now use one kernel-owned slot and eight FIFO waiters; human waits release the slot. Native Ollama checks current headroom before generation; other local backends lack validated memory admission. Experimental Outlook Mail search was added in commit `1e6b73b` with explicit per-Bot mailbox grants and read-only Graph search; fixture and responsive checks pass, but live Microsoft registration, consent and Graph access remain unverified. |
| S6 conversations and bounded collaboration | Partial; conversation foundation, chat-sourced Bot creation, workspace model-default seeding, artifact discovery/sharing, scoped facts and schema-v38 reusable owner-granted Bot references, alerts, workspaces, recurring-task streams, same-bot delegation, reviewed coordinator handoff/result return, selected task-only coordinator facts, content-free task checkpoints and a narrow no-effect fresh-attempt path are implemented; general recovery and broader collaboration remain open | Schema v8 stores conversations/messages and imports each old run separately. Schema v15 adds immutable versioned reference facts, private chat/run scope, human review, bounded FTS5 recall and paginated history; schema v38 adds immutable one-fact/one-recipient cross-Bot grants, provenance-labelled recall, bilateral revocation, content-free invalidation and backup/restore coverage. Source revisions/archives and either Bot's disabled memory block new recall. Schema v17 adds owner-selected artifact references across chats, including across bots: references retain source provenance, have target-bound downloads and a one-way revocation audit. Both source and target Files lists show active grants and can revoke them. Schema v18 transactionally invalidates both conversations when a grant is created or revoked. Workspaces default to fresh per run; optional 0700 Hutch-managed directories persist across one bot's runs/chats, or an operator may choose a validated user folder. Successful `write_file` actions attach bounded immutable text snapshots; shell-created files are not attached. The composer menu pages run artifacts for its conversation. Schema v22–v24 add bounded same-bot lineage, tree-budget reservations and immutable root capability snapshots. `delegate_task` runs only through the supervised built-in Strict Offline Linux process executor, requires fresh human approval, receives task text only and uses a private child workspace. Child files stay attributed to child runs and are never auto-copied into parent context. Stop cascades through lineage. The exposed call is serial; the default global limit supports one child. Schema v29 adds one coordinator-to-existing-specialist handoff after user review, with separate child chat, capability snapshot, idempotent admission, linked source/brief/assumptions and parent status/latest-response card. Schema v30 exposes the exact successful specialist result message; the user can explicitly attach that source-bound, bounded text snapshot to a coordinator follow-up, where it is marked untrusted. Schema v31 backfills and records immutable, content-free event markers per task, with a bounded latest-16 timeline and materialized count in the coordinator card/API; it is an audit journal and does not resume a worker. Schema v32 lets an owner optionally select up to eight current coordinator facts during the handoff review; immutable 6,000-character-bounded snapshots with source/revision remain attached only to that task and enter as untrusted run context, never specialist saved memory. Provider copies cannot be recalled. The task card reports result message identity. Schema v34 permits one owner-confirmed fresh run from a failed/stopped built-in task only when no tool action or child run was recorded, the specialist chat has no newer run or pending question, the parent chat is active, and the exact capability snapshot is unchanged. The new attempt carries only the reviewed brief/constraints and bounded prior assistant text marked untrusted; actions, receipts, selected facts, credentials and prior tool results never cross. `outcome_unknown`, process restore and external-runtime continuation remain blocked. Open gaps include general recovery, specialist allowlists, multi-step/parallel plans, task cancellation and live model verification. See `delegation.md`. Optional browser alerts are generic and tab-open only; no push delivery. |
| S7 browser ownership and handoff | Partial | Persistent profiles are per bot and protected by cross-process OS leases. A bot can opt into an experimental, same-session visible browser handoff on a Linux desktop; local fixtures cover configuration, persistence, challenge recheck, and setup cleanup. An owned loopback proxy resolves every HTTP(S)/WebSocket connection, rejects any non-public answer, connects to a checked numeric address, and overrides Chromium's implicit local-address proxy bypass. Service workers are blocked; denial events omit paths and query strings. Local Chromium covers ordinary HTTP, DNS rebinding on redirect, and suppression of unproxied WebRTC UDP against a loopback STUN fixture. HTTPS CONNECT tunnel forwarding and raw WebSocket upgrade are fixture-tested. Live public destinations, other non-HTTP traffic, a headed challenge, remote phone handoff, and dedicated browser descendant cleanup remain open. |
| S8 versioned API and remote supervision | Partial; schema-v42 passkey phone supervision is implemented in this checkout; live-network and physical-device gates remain open | The `/api/v1` contract includes bounded bot/run/approval resources, transcript streams, snapshot/change reconciliation, typed commands and idempotent admission/resolution. Schema v42 replaces legacy broad device bearer authentication with one-use enrollment, WebAuthn credentials, challenge-bound authentication, hash-only sessions, revocation and per-Bot remote-start opt-in. Paired phones have an exact Monitor/Review/optional Start route inventory; owner settings, connections, schedules, artifacts/exports and computer interaction remain local-only. Remote stays disabled by default. Tailscale Serve to a loopback listener or direct private-interface HTTPS is documented; no public ingress is supported. Focused verification is recorded in the 2026-10-09 checkpoint below. See ADR-0010 and the phone-supervision contract; physical iOS/Android, live Tailscale/LAN, and network-isolation checks remain open. |
| S9 product integration, performance and visual validation | Partial; evidence captured in `896a774`, `ba1e297`, and later device/workspace/browser checkpoints; schema-v16 event-throughput gate passes | Screenshots and traces cover desktop/tablet/phone and compact phone, plus fixture-driven empty/loading/error/approval/cancelling/reconnecting, pairing, workspace defaults, local browser handoff, coordinator specialist dispatch/result return and its checkpoint timeline. Workspace model-default preferences, new-Bot setup and the reviewed handoff were inspected at 1440×960, 900×1024 and 390×844; the anonymous workflow card was inspected at 1440×900, 900×1024 and 390×844. Provider Connections also has an enabled-preview fixture capture at 1440×960 and 390×844; the official authorization URL is intercepted locally, not contacted. Internal site CTA targets, overflow, page errors, reduced motion, tablist arrows, menu focus, pairing focus, device revocation, workspace focus/validation, browser-setting focus/availability, coordinator handoff and safe-checkpoint review/status, checkpoint readability and result attachment/removal/provenance were checked. The no-mock slice removes seeded-run screenshots and scripted approval controls; the marketing proof is now the actual empty first-run screen. Executor health remains text-labeled and changes with health polling, without decorative pulsing between checks. Schema v16's matched event median is 1.3% above `f5696ce`, below the 20% gate. This is not screen-reader, real-device, live remote, or full workflow certification. See `visual-validation.md`, `device-pairing-visual-validation.md`, `no-mock-validation.md`, and `performance.md`. |

## Commits

| Commit | Change |
|---|---|
| `53a2dc9` | Baseline, evidence ledger, ADRs and continuation ledger |
| `acc2261` | Claims audit and evidence-aligned safety/research/website copy |
| `522eeaf` | Provider-scoped credentials and resolved-address SSRF guard |
| `e227297` | Lifecycle, atomic claims, leases, fencing and recovery |
| `34589ee` | Owned run processes, teardown and event sequencing |
| `bf42b77` | S4 approval compare-and-swap and partial sandbox checkpoint |
| `433981e` | Explicit cross-Bot reviewed fact grants, bounded recall/API, responsive UI and marketing card spacing |
| `eee309c`, `23cb0c4`, `6378dd3`, `5196655`, `309a7d3` | Local main: templates, approval reconciliation, website, Studio and research map |
| `0ab3058` | Merge local `main` into `realign/platform` |
| `cf82f73` | Merge newer main navigation, layout and template changes into `realign/platform` |
| `73d58b6` | Refresh empty-state marketing proof images and content-hash site asset URLs |
| `fdf6592` | Merge main `307ce1d` sigil, responsive modal/card and switcher styling changes |
| `02b0092` | Refresh integrated desktop/tablet/phone screenshots after main merge, fix capture wait and pin updated evidence |
| `ed82ce1` | S2–S4 audit repairs, docs, test corrections and truthful marketing copy |
| `98c630d` | Correct shell-test escapes and record full-suite verification boundary |
| `a148b29` | Fail-closed Pi/OpenCode, per-bot browser profile ownership, safety docs and truthful website claims |
| `4a242af` | Phone menu focus handling, responsive visual validation report, screenshots and traces |
| `31b25f8` | Schema v8 conversations, migration, bounded context, FTS5, idempotency, Studio thread UI, readable status labels, evidence corrections and updated visual captures |
| `99bade2` | Schema v9 device pairing, revocable sessions, explicit TLS binding and expanded typed `/api/v1` resources |
| `bf09d97` | Raw repeated benchmark samples, p50/p90 summary, machine/revision metadata and regression checks |
| `a83aac1` | Schema-v29 coordinator-to-specialist reviewed handoff, durable status/result card, API contract, safety boundaries, responsive browser evidence and honest website copy |
| `4eb4e6d` | Schema-v30 exact, user-selected specialist result return to the coordinator; immutable source provenance, untrusted context, explicit removal, export support, updated app/website contracts and inspected responsive evidence |
| `9d2f589` | Schema-v31 immutable, content-free cross-Bot checkpoint journal with migration backfill, bounded/latest timeline, API/UI/site updates and responsive evidence; safe restart continuation was still open at that commit |
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
| `32f98e2` | Offer the active chat Bot's configured non-mock model route as an editable default suggestion when creating a Bot from chat; document and capture desktop/tablet/phone behavior |
| `fd001c3` | Add validated workspace model/inference defaults for new Bot drafts, API/browser coverage, truthful public copy, and inspected desktop/tablet/phone captures |
| `1367516` | Schema v16 replaces per-event transcript mirror triggers with transactionally batched intent writes; adds legacy-trigger migration/backup tests, matched performance diagnosis, refreshed captures, and corrected ADR/operations/safety guidance |
| `e711e7d` | Add explicitly trusted HTTPS reverse-proxy forwarding, host/Origin validation, source-IP propagation, capability reporting, docs and local security regressions; no real network path claimed |
| `6ee3e29` | Opt-in per-bot local Linux browser handoff, cross-process profile/desktop leases, fail-closed headless behavior, host-aware settings, setup cleanup regression, updated support claims and inspected viewport evidence |
| `6e91e95` | Add a bounded task prompt for each bot's existing recurring schedule across settings, creation, CLI and API; preserve legacy fallback and capture responsive browser evidence |
| `2964567` | Align ChatGPT sign-in and Responses tool framing with the current preview, retain verified reauthorization hints, use conversation-stable OpenCode session headers, and record fixture/browser evidence |
| `ec16d5c` | Add explicit, verified cross-chat artifact references with target-bound downloads, one-way revocation, Studio sharing controls, API regressions and desktop/tablet/phone captures |
| `cf3f98d` | Show active artifact recipients in the source chat, allow revocation from either chat, and invalidate both source and target views durably; add responsive captures and API/migration/browser regressions |
| `c4f2cf4` | Add `POST /api/v1/tasks/runs` with atomic run/task/idempotency persistence, exact replay, changed-request conflicts, restore-hold behavior and cross-connection race coverage |
| `3a1951a` | Add a bounded, scoped conversation JSON export through API and Studio, including excluded-data disclosure, oversize refusal, focused browser download tests and inspected desktop/tablet/phone evidence |
| `18b9b7b` | Add versioned human resume bound to the latest active human-needed event and owner lease; enforce one resume per wait sequence, idempotent replay and schema-v19 migration coverage |
| `ee3f179` | Add event-bound, idempotent Resume directly to the active Studio chat; keep historical waits read-only and capture desktop/tablet/phone behavior |
| `4a3e5c0` | Keep Studio work feedback steady and increase shared server-page heading line-height; inspect the computed design at desktop/tablet/phone widths |
| `a167865` | Add up to 100 independently scheduled, named task streams per bot with migration-safe IDs, API/CLI/settings management, and responsive visual evidence |
| `652274d` | Persist bounded same-bot delegation lineage with atomic depth/fan-out admission and idempotent child creation |
| `3a68422` | Add immutable inherited delegation-tree cost ceilings and atomic reservations across measured spend and unresolved holds; full suite 1,420 passed |
| `53a3c24` | Record the v23 shared delegated-budget checkpoint in the continuation ledger |
| `976138b` | Cascade Stop intent through persisted descendants atomically, signal owned descendant workers, and keep cleanup visible; full suite 1,423 passed |
| `85cdf83` | Record the S6 descendant-cancellation checkpoint in the continuation ledger |
| `690d3ca` | Keep persisted delegated runs pending until a dedicated executor can enforce their permissions and workspace boundary |
| `6db26ff` | Record the S6 fail-closed dispatcher checkpoint in the continuation ledger |
| `48fdf92` | Bound the content-free resource-change outbox to 50,000 rows with boundary-safe snapshot recovery |
| `095ccc0` | Record resource-change retention implementation and focused verification |
| `b21ec5d` | Force internal lineage runs into a private per-run workspace and fail closed on symlinks |
| `b5e0034` | Recover idle legacy Pi/OpenCode bot records to Hutch's built-in runtime after route validation; close the active-run race, document provider sign-in boundaries, correct the stale marketing CSS cache key, and add API/browser/cache regression evidence |
| `6017f35` | Record the legacy runtime recovery commit in this continuation ledger |
| `ec73e1e` | Persist credential-free root execution capabilities atomically and inherit the immutable snapshot for bounded lineage; schema-v24 focused regressions pass |
| `8063243` | Fail directly invoked delegated workers from the authoritative persisted lineage before runtime or tool setup; focused lifecycle/workspace suite 90 passed |
| `35c045c` | Reject delegated worker processes before recording their process group; 84 worker/delegation/lifecycle tests passed |
| `536c892` | Record the worker-entrypoint guard; full offline suite 1,333 passed |
| `c352d22` | Add the approved, same-bot Strict Offline child-task preview, responsive Settings opt-in, documentation and inspected app/site captures; focused suite 230 passed |
| `c0ebc21` | Main: per-tool output limits, full-output artifact card and compatibility serving route (adapted during integration to verified no-follow serving) |
| `6fab391` | Merge main PF-2 with the realignment branch; preserve versioned APIs and safer artifact verification, add responsive source-card test/captures and update public/configuration contracts |
| `b5227a9` | Record merged PF-2 verification boundary and final offline/browser suite results |
| `657e9b8` | Record local `main` fast-forward completion without pushing |
| `264f828` | Add experimental Outlook Calendar with local PKCE, Secret Service token storage, one-calendar-per-Bot grants, bounded read-only Graph access, truthful public availability copy, and inspected responsive app/site evidence; live Microsoft access remains unverified |
| `63b29bc` | Add schema-v34 safe checkpoint continuation, review/confirmation UI, truthful public copy, regression coverage and inspected desktop/tablet/phone evidence; live model recovery remains unverified |
| `5cdd65f` | Recheck same-page human browser challenges before actions and after waits/effects; add async Chromium regression and document retry/verification boundaries |
| `28bf0ac` | Record the no-mock/product-availability audit and verify OpenCode Go is a provider API-key flow rather than OAuth session sharing |
| `2bba9c8` | Add schema-v37 passive model tool-call evidence, exact effective route identity, bounded `/api/v1/model-capabilities`, support docs and full offline validation (1,471 passed, 2 skipped) |
| `236dd99` | Show newest route-specific tool-call observations in Connections with honest loading/unknown/error states, bidirectional keyset paging, updated Bot-name guidance and inspected responsive evidence; focused API/browser suite 4 passed |
| `6b3d643` | Record the Connections capability-evidence implementation and verification boundary |
| `e47b193` | Reconcile the current Google Calendar, Gmail, Outlook Calendar, and Outlook Mail support matrix; correct typed API documentation and record focused fixture verification |
| `fc8bb20` | Add schema-v39 reviewed OpenCode coding handoffs, pinned Git worktrees, local CLI launch/reconciliation, terminal-session identity, and PTY/process regressions |
| `a976357` | Add Studio coding-task review/status cards, anonymous marketing disclosure, responsive UI/site checks and inspected screenshot evidence |
| `6ba8ab9` | Classify terminal Ctrl+C exits as stopped only after process cleanup is verified |
| `a79aed2` | Add persistent Bot pinning, searchable roster and flat 2D product mascots while retaining detailed 3D marketing art |
| `38e20e0` | Record mascot and Bot-roster research, design and visual verification |
| `8a87ac9` | Add schema-v40 workspace schedule overview/control, atomic pause fencing, responsive app/site UI, docs and inspected evidence |
| `462a374` | Align the shared design system across Studio, Connections and marketing; retain the main-branch visual tokens |
| `f80b3f9` | Record the shared design-system checkpoint |
| `dffe717` | Simplify Bot creation and roster management while retaining advanced configuration paths |
| `3c19866` | Record the Bot setup and roster checkpoint |
| `0b6cbe8` | Align server-rendered pages with the shared design tokens |
| `257ef10` | Add phone supervision and richer chat workflows, including durable conversation actions and reviewed chat options |
| `e1bd3b9` | Capture responsive UI validation evidence |
| `2a30ee2` | Record integrated UI and validation commits |
| `0b76808` | Polish app mascot eyes across all silhouettes and capture the shape-specific visual check |
| `66c0b3c` | Add bounded, Bot-filterable Studio message search with excerpt-only responses, responsive screenshots and route authorization coverage |
| `0b2875a` | Record the conversation-search checkpoint in the continuation ledger |
| `32d5e69` | Refine all eight app-mascot faces with shape-specific diagonal eyes; verify conversation-search empty, error and escaped-text states with updated responsive evidence; offline suite 1,532 passed |
| `fcefc5c` | Refresh the scoped UI audit to distinguish the historical failure run from the verified offline suite and separately passed browser journeys |

## Dashboard polish continuation (2026-10-09)

The Studio typing indicator no longer animates continuously; its visible label and run-status state communicate work. The shared
server-rendered heading rule now uses a 1.4 line-height. Chromium **153.0.8010.12** / Playwright **1.63.0** verified the computed
styles at 1440×960, 900×1024 and 390×844 with no page errors or horizontal overflow. Screens and trace are in
`artifacts/dashboard-polish/`; the working indicator is a visual-only fixture rather than an active execution. The base-template
source detector does not resolve its linked stylesheet, so the existing path-scoped `tight-leading` exception remains with an updated
reason reflecting the browser measurements. See `visual-validation.md` for the exact command and captures.

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
| Provider sign-in wire contract and UI | `tests/test_openai_responses.py tests/test_chatgpt_auth.py tests/test_chatgpt_integration.py tests/test_connections.py tests/test_compat.py tests/test_runtime_builtin.py`; two Connections browser checks | **104 fixture tests passed in 43.97s; 2 browser checks passed in 2.56s.** Coverage includes OpenCode conversation-stable session headers and standalone run-ID fallback, ChatGPT `additional_tools`, account reauthorization through the saved registration and verified identity hints, and hiding unverified legacy email. The opt-in UI's auth destination is intercepted locally; desktop/phone screenshots have no overflow or browser errors. No real OpenAI or OpenCode sign-in was completed, no credentials or paid calls were used, and Hutch's SIWC eligibility remains unconfirmed. Impeccable detector reported no findings for the changed Connections UI. |

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
challenge, physical phone, remote control, or cross-browser matrix was exercised. Remote phone
handoff, PTY/physical desktop access and other non-HTTP browser egress remain open. UI audit limitations
are recorded in `visual-validation.md`.

## Post-merge screenshot refresh (2026-10-08)

Marketing screenshots are generated artifacts; merging source code does not regenerate their PNG/WebP pixels. The marketing page
now content-hashes every local asset URL, but that only invalidates browser caches after a screenshot file itself changes. The
embedded app screenshots had last been refreshed before main `307ce1d` was merged. After that merge, the real first-run app was
captured again from empty temporary state, converted to WebP, and the static asset URLs were re-stamped. The app images were visually
inspected against the post-build PNGs and the anonymous marketing page was recaptured at desktop, tablet and phone sizes, including
full-page views. There are no seeded records, provider calls or external requests in these captures.

The current captures identify realignment revision `fdf6592dd1d659904b71770845954f7284eb8316`, Chromium 153.0.8010.12 and
Playwright 1.63.0. All inspected sizes report zero horizontal overflow and no page errors; marketing requests stay same-origin.
The full browser suite passed **83 tests in 206.27s** with background-thread and syntax warnings treated as errors. After the final
WebP refresh and URL re-stamp, the focused anonymous-site/token suite passed **27 tests in 27.17s**. The older navigation sheet was
also found to contain a prior marketing-site image; its independent generator was updated to wait for the visible status chip rather
than a hidden duplicate, then refreshed all **39** app/site captures at desktop, tablet and phone sizes with no page errors or
overflow. Captures and source hashes are under `artifacts/no-mock-setup/`, `artifacts/marketing-top/` and `artifacts/navigation/`.
They remain local fixture evidence, not provider or device tests.

The root checkout's local `main` remains at `307ce1d`; this branch contains the newer merges and refreshed evidence. Final fast-forward
is still gated on the unfinished S5-S9 implementation and release checks above.

## S5 restricted-runtime reassessment (2026-10-08)

The current Pi CLI can start RPC with `--no-tools`, which disables built-in, extension, custom and MCP tools. That creates a possible
future text-only capability profile, but it still sends model traffic outside Hutch's `ConnectionBook` and atomic `SpendGuard`
reservations, and Hutch has not verified Pi's process behavior with an installed binary. The installed OpenCode v2.0.24 server API
has message/session endpoints, but its event stream is volatile; no adapter yet proves recovery of every action and receipt or wires
the once-only approval decision into Hutch's immutable intent record. Neither runtime is enabled. This avoids launching an
ungoverned direct-provider process or claiming approval and spend guarantees that have not been verified.

The assessment is recorded in ADR-0007 and the provider matrix with links to the current [Pi RPC](https://pi.dev/docs/latest/rpc),
[Pi CLI](https://pi.dev/docs/latest/cli), [OpenCode permissions](https://docs.opencode.ai/docs/permissions/) and
[OpenCode server API](https://opencode.ai/docs/server/) references. A regression now replaces `subprocess.Popen` with a failure in
the adapter refusal test, proving both unsupported runtimes stop before process creation. `tests/test_runtime.py tests/test_compat.py`
passed **14 tests in 0.83s**; compatibility JSON parsing, JavaScript syntax and `git diff --check` passed. No Pi binary, provider
request, paid call or external runtime process was used. S5 remains open for governed adapters; this checkpoint does not complete it.
Checkpoint commit: `59a75f1`.

The visual review also confirmed the pulsing working indicator is driven by live active-run status and is refreshed from API data.
Its detector false positive is ignored only for `src/hutch/server/static/index.html`; other design checks remain enabled.

## Integrated offline-suite checkpoint (2026-10-08)

After the post-merge website capture commits and S5 runtime-gate documentation, the complete non-browser suite passed **1,272 tests
in 283.53s** with `PytestUnhandledThreadExceptionWarning` and `SyntaxWarning` promoted to errors. The separate browser suite at the
post-merge source boundary passed **83 tests in 206.27s**, and the final anonymous-site/token suite passed **27 tests in 27.17s**;
their capture and source details remain in the preceding visual checkpoint. These are distinct invocations, not one combined suite.
No Pi process, live model, paid provider, physical device, or remote deployment was used. This closes the latest integrated offline
regression pass, not the remaining S5-S9 capability and live-verification gates.

## Dashboard style and design-sidecar follow-up (2026-10-09)

Commit `49e6976` removes the 2px transcript tool-row rail and stops animating progress-meter width. Labels, indentation and status
text remain intact. `.impeccable/design.json` now reflects the current `DESIGN.md` tokens and narrative; the human-authored guide was
left unchanged. The hook's website and active-run-dot findings were already covered by narrow, evidence-backed ignores in the
worktree config. They resurfaced because the root stop hook scanned nested `.worktrees/realign/...` files without loading that
worktree's config; no broader ignore was added.

The focused dashboard/view tests passed **39 tests**. Firefox 155.0 fixture captures at desktop, tablet and phone widths showed the
actual stylesheet with a 0px tool-row rail, retained 10px inset, no meter transition, exact 72% fill and no horizontal overflow or
page errors. Captures and trace are in `artifacts/ui-style-review/`; reproduction details are in `visual-validation.md`. The fixture
is synthetic and does not represent a live run. JSON/sidecar consistency, Python compilation, the targeted Impeccable scan and
`git diff --check` passed.

## S6 Conversation-scoped file discovery (2026-10-09)

OpenBot issue [370](https://github.com/CopilotKit/openbot/issues/370) reports one user's difficulty finding generated files; it remains
an acceptance scenario, not evidence of prevalence. Studio's composer options now contain “Browse files in this chat.” The paged v1
resource returns verified tool outputs and generated text files from runs linked to that conversation. Its SQLite query checks the
conversation-run link, conversation bot and run bot; the API rechecks ownership before rendering. Available entries link to the existing
run-scoped downloader, which still opens files without following symlinks and verifies recorded size and SHA-256. Missing and older
unverified entries remain visible without a download action. This adds discovery across a conversation's runs; it does not copy files,
share them with another conversation, or create a cross-chat library.

API regression coverage exercises two artifact kinds from one tool event, stable cursor pages while a newer artifact is inserted, verified bytes, an adjacent conversation
for the same bot, a second bot, invalid bounds and an unknown conversation. The focused `tests/test_api.py` suite passed **15 tests
in 3.92s**. Browser coverage creates a fixture file, opens the conversation list, downloads with Enter at desktop (1440×1000), tablet
(768×1024) and phone (390×844), then verifies Done restores focus to composer options. A separate phone empty-state check verifies Escape
close, focus return and the explicit no-files message. A 51-item phone fixture also traverses the Load more cursor and confirms every
item appears once without overflow. The latest browser run passed **3 tests in 8.57s**. Browser: Firefox **155.0**;
Playwright **1.63.0**; all captures record no page errors or horizontal overflow. The screenshots, result JSON and source hashes are in
`artifacts/generated-files/`. The captures were visually inspected. The large-list phone state and source/runtime metadata are in
`artifacts/generated-files/large-list-phone.png` and `artifacts/generated-files/cursor-list.json`.

The marketing-site State card now says where conversation files can be found and qualifies that shell-created files are not attached;
`docs/marketing-site.md`, `README.md`, `docs/architecture.md`, and the v1 contract were updated with the same boundary. Anonymous site
checks passed **22 tests in 28.46s**, and the full marketing feature section was recaptured at all three widths in a focused pass
(**1 passed in 3.29s**). No external model/provider call was used. Screen-reader and physical-phone behavior remain unverified. A
shared cross-chat artifact library, standing tasks and delegation remain open. The screenshot metadata was refreshed after switching
the conversation page to a newest-first keyset cursor; captures were visually reinspected. Source, documentation, tests and scoped
visual evidence are committed in `273efa4` (`feat(studio): browse files across a conversation`), `dc641b0`
(`style(studio): finish conversation file browser`), and `d0024f3` (`test(studio): cover conversation file pagination`). The
stylesheet follow-up was required because a final staged-diff review found the visual rules had been left out of the feature commit.

## S6 Per-bot recurring-task prompt (original slice, 2026-10-09)

Each bot's existing single cron schedule now has an optional, separately editable task prompt, up to 4,000 characters. It is
available in the creation dialog, bot settings, CLI (`--schedule-prompt`) and the schedule API resource. A nonempty task prompt
requires a cron schedule. Blank preserves legacy behavior by using the bot's standing instructions, then the generic workspace
report task if those are empty. The schedule is saved with the bot config; no migration is required. This supports one recurring
task per bot and does not add multiple independent task streams or bounded delegation.

The API/engine/CLI focused suites passed **34 tests in 23.04s**. They cover typed schedule output, persistence/update/reset, invalid
task-without-schedule requests, the 4,000-character limit and separation from standing bot instructions. The browser journey passed
**1 test in 3.14s**: create a fixture bot with the modal, reject a prompt without cron, save the cron and prompt, edit both from
settings, and verify they survive reload. Chromium **153.0.8010.12**, Playwright **1.63.0**; desktop, tablet and phone captures have
no page errors or horizontal overflow, and the phone dialog keeps its title and Create action visible while the task field is in
view. Screenshots, trace, source hashes and viewport measurements are under `artifacts/scheduled-task/`; they were visually
inspected. `node --check`, Python compilation, `git diff --check` and the targeted Impeccable detector passed. No provider or model
call was made. The feature and its API/CLI/engine regression tests are committed in `6e91e95` (`feat(schedule): add per-bot recurring task prompts`).

## S6 Multiple independent recurring tasks (schema v20/v21, 2026-10-09)

Each bot can now hold up to 100 named task streams, each with independent cron, timezone,
catch-up choice and task prompt. The `/api/v1/schedules` listing is bounded and paginated;
per-ID PUT/DELETE and `hutch bot schedules list|add|update|remove` manage streams without
overwriting siblings. Legacy `schedule` JSON, creation fields and bot-update options remain
aliases for the first stream. All streams share their bot's resources and serialize through the
existing one-run-per-bot rule. Schema v20 creates per-task occurrence claims and markers; schema v21
reserves task identities after removal so an ID cannot be recycled even if it was deleted before
its first due window. Existing runs and occurrence provenance survive removal.

The first full offline run completed **1,405 passed, 3 failed** in 474.75s. It exposed migration
normalization creating synthetic bot-change entries, two historical migration fixtures that had
not been scoped after later schema additions, and a phone browser assertion that read before the
transcript finished rendering. The migration now reinstalls the bot invalidation triggers around
normalization without recording a user edit; the v16 fixture explicitly exercises v15→v16; and the
phone journey waits for its rendered transcript. All three exact failures passed on isolated rerun.
The focused scheduler/claims/migration/API/CLI/store/durable-change/transcript tests plus the
schedule, resume and anonymous marketing journeys passed **131 tests in 47.57s**. After those
corrections the complete offline suite passed **1,408 tests in 475.88s**.

The schedule browser journey adds two streams, edits each independently, verifies reload, removes a
secondary task, then removes the primary and confirms promotion. At 1440×960, 900×1024 and 390×844,
both expanded task forms fit without horizontal overflow, task cards measured about 511 px on
desktop/tablet and 748 px on phone, the Add task control measured 44 px, and there were no page
errors. Six card captures, full trace, source hashes and measurements are recorded in
`artifacts/scheduled-tasks/` and visually inspected. The public workflow copy now says named
recurring tasks. `node --check`, Python compilation and `git diff --check` pass. No model/provider
request was made.

## S6 Explicit cross-chat artifact references (2026-10-09)

Schema v17 now lets an operator grant one selected, active conversation a reference to a verified
artifact from another chat, including a different bot. The grant records its source event and
provenance, requires the original bytes to match their recorded size and SHA-256, and is immutable
except for a one-way revocation. The receiving chat gets a target-bound download that stops working
after revocation. No bytes are copied to its workspace or added to model context; the source run's
own download remains available. A new destination must be deliberately selected before the Studio
enables Share. The current marketing site now describes this boundary.

`.venv/bin/python -m pytest -q tests/test_api.py tests/test_migration.py` passed **29 tests in
5.05s**. The regressions cover cross-bot access, idempotent replay/conflict, byte integrity at grant
and download, immutable history, durable change notifications, target binding and revocation. The
focused browser journey passed **1 test in 5.53s** with Chromium **153.0.8010.12** and Playwright
**1.63.0**. At desktop (1440×960), tablet (768×1024) and phone (390×844), sharing, download and
revocation worked; all captures report zero horizontal/dialog overflow and no page errors. The Done
button is visible on phone. Screenshots, trace and source hashes are in
`artifacts/artifact-sharing/`; those captures were visually inspected. The public feature section
was also refreshed at all three sizes; the anonymous marketing suite had passed **22 tests** after
the copy/layout edits, with current source hashes in `artifacts/provider-signin/marketing-validation.json`.
The targeted Impeccable detector returned no findings, JavaScript/Python syntax checks and
`git diff --check` passed. No provider, paid request or physical device was used. This limited
cross-chat reference feature does not complete the general artifact library, delegated artifact
transfer or S6 bounded collaboration. Implementation and evidence commit: `ec16d5c`.

## S6 Source-side artifact grant management (2026-10-09)

The originating chat now lists each active recipient beside its verified file and can stop sharing
without opening the recipient chat. The receiving chat retains its own revoke control. Schema v18
adds transactional source-conversation outbox invalidations for share creation and revocation, and
the in-process change bus refreshes both open views. A revoke from either side removes the other
chat's grant view and disables the target-bound download; the source-run download remains intact.

`.venv/bin/python -m pytest -q tests/test_api.py tests/test_migration.py` passed **29 tests in
5.68s**. The focused Chromium browser journey passed **1 test in 6.69s** (Chromium
**153.0.8010.12**, Playwright **1.63.0**) with source and recipient grant/revoke behavior at desktop
(1440×960), tablet (768×1024), and phone (390×844). Results report zero horizontal/dialog overflow
and no page errors. The source-share screenshots, result JSON and trace are in
`artifacts/artifact-sharing/`; screenshots were visually inspected. Python compilation,
`node --check`, `git diff --check`, and the targeted Impeccable detector (no findings) passed. This
used local fixture data only; no provider, phone, or screen-reader check was performed. The
implementation/evidence commit is `cf3f98d`.

## S8 Idempotent standalone run creation (2026-10-09)

`POST /api/v1/tasks/runs` now creates a standalone run only with an `Idempotency-Key`; the run,
task, and stored replay response commit in one SQLite transaction. Exact retries return the same run
with `replayed: true`, while changed bodies and cross-command key reuse return 409. Replays are
checked before mutable provider-route validation and restore holds; new commands still obey both.
The existing `/api/bots/{ref}/run` route remains as an unversioned compatibility alias and has no
idempotency guarantee.

`.venv/bin/python -m pytest -q tests/test_api.py tests/test_migration.py` passed **31 tests in
5.27s**. Coverage includes missing keys, success/replay, changed prompt/bot, cross-command key
reuse, restore hold, unchanged legacy behavior, and two separate SQLite connections racing the
same key: one run/task is committed and both callers receive its ID. Python compilation and
`git diff --check` passed. This API-only slice did not change the UI or marketing site; live model,
provider, process execution and remote-device behavior were not exercised. Implementation commit:
`c4f2cf4`.

## S8 Human-resume command authority (schema v19, 2026-10-09)

`POST /api/v1/tasks/runs/{run_id}/resume` now requires `Idempotency-Key` and the current
`human_event_seq`. It accepts only a `waiting_human` run with a live owner lease, and schema v19
records one accepted resume per `human_needed` event. The wait marker and idempotency response
commit together. A replay returns its saved response without setting the marker again; a stale
sequence, inactive wait, expired owner, or second command for the same event is rejected. The
unversioned resume aliases remain for compatibility. At this API implementation checkpoint, the
Studio client had not migrated; commit `ee3f179` now submits the versioned command from chat.

`.venv/bin/python -m pytest -q -W error::pytest.PytestUnhandledThreadExceptionWarning
-W error::SyntaxWarning tests/test_api.py tests/test_migration.py` passed **34 tests in 4.83s**.
The regressions cover missing keys, current and stale sequences, one-use replay, ended waits,
expired leases, concurrent commands on two SQLite connections, replay from a fresh Store connection,
and migration of the new table. Python compilation and `git diff --check` passed. No UI/marketing
code changed in this API-only slice, so it had no visual captures; real phone/provider
validation remains open. Implementation commit: `18b9b7b`.

## S8 Studio human-resume control (2026-10-09)

The active Studio chat now shows an inline Resume button only on the latest `human_needed` event
for a run whose current status is `waiting_human`. It sends that event sequence to the versioned
endpoint with a stable per-run/per-event idempotency key. After acceptance, the button becomes a
disabled “Resume requested” state; stale historical challenges stay visible without an active
button. The older server-rendered compatibility routes remain on the legacy alias. Code, tests and
captures are in `ee3f179`.

`.venv/bin/python -m pytest -q -W error::pytest.PytestUnhandledThreadExceptionWarning
-W error::SyntaxWarning tests/e2e/test_browser.py::test_studio_resumes_only_the_active_human_wait_with_v1_command`
passed **3 tests in 3.70s** at desktop, tablet and phone. The fixture included an earlier challenge
and verified that only the current event receives a button. Each click reached
`POST /api/v1/tasks/runs/{run_id}/resume` with the expected sequence and deterministic key; every
response succeeded, and the browser showed the requested state. Captures, zero-overflow checks and
source hashes are recorded in `artifacts/human-resume/`. The API/migration suite passed **34 tests
in 5.01s**; `node --check` and `git diff --check` passed. The fixture kept the scheduler idle, so
request acceptance is verified but live worker consumption and completion after a real human
challenge are not. No live provider, external browser, physical phone or screen reader was used.

## S7 Browser egress: WebRTC and local-file boundaries (2026-10-09)

The BrowserTool's existing Chromium launch policy now has an end-to-end loopback fixture with a
negative control. Plain Chromium sent a UDP STUN datagram to a local fixture; Chromium launched by
Hutch with `--force-webrtc-ip-handling-policy=disable_non_proxied_udp` sent none. The fixture is
local-only and confirms this WebRTC path in the installed Chromium; it does not prove that all
browser protocols are contained, that proxied WebRTC works, or that browser traffic is confined by
an OS network namespace. Google's Chrome Enterprise policy describes this setting in terms of
using a UDP SOCKS proxy or falling back to a TCP proxy; Hutch does not provide a UDP SOCKS proxy.

A second Chromium fixture follows an HTTP redirect to a temporary `file:` URL and confirms the
private marker is not exposed. That navigation ends on Chromium's own error page before Hutch's
request guard emits an event. This is recorded as installed-browser behavior, not as Hutch's SSRF
guard or audit log decision.

`.venv/bin/python -m pytest -q -W error::pytest.PytestUnhandledThreadExceptionWarning
-W error::SyntaxWarning tests/test_browser_proxy.py tests/test_netguard.py
tests/e2e/test_browser_egress.py` passed **112 tests in 15.82s** on Chromium **153.0.8010.12**
and Playwright **1.63.0**. No public destination, model or provider was contacted. The two new
regressions were committed as `bb5e4b9`; the updated support boundary is in `docs/safety.md`,
ADR-0006, `docs/realignment/tests.md`, and the evidence ledger. Other non-HTTP egress and live
public-destination validation remain open.

## Dashboard motion and readability follow-up (2026-10-09)

The Studio's working dots and the server-rendered live-connection mark remain static; “Working…”, “live” and “reconnecting” carry
the state. Shared page headings retain the 1.4 line-height fixed in `4a3e5c0`. The responsive browser regression checks both status
marks and computed heading styles across desktop, tablet and phone. No provider or model request is involved.

## Packaged test-runtime boundary (2026-10-08)

An accidental `HUTCH_TESTING=1` in a wheel install previously let a legacy mock route fall through
to an uncaught import failure because the test-only runtime is intentionally excluded from the
wheel. It now fails closed with an actionable `RuntimeUnavailable` asking the operator to configure
a real model route. The source test harness still loads its fixture unchanged. Regression commit:
`fc8fa5e`.

`.venv/bin/python -m pytest -q -W error::pytest.PytestUnhandledThreadExceptionWarning
-W error::SyntaxWarning tests/test_runtime.py` passed **8 tests in 0.33s**. `uv build --wheel
--out-dir /tmp/hutch-test-runtime-boundary` succeeded; a clean `/tmp` process importing only that
wheel with `HUTCH_TESTING=1` printed the intended error and exited normally. No marketing change is
needed because this is a packaged test-flag edge, not a public capability or product flow.

## Provider sign-in capture integrity (2026-10-09)

The enabled ChatGPT sign-in browser test could pass its DOM assertions while taking a blank desktop
full-page screenshot before the first view paint had been composited. The test now waits for fonts
and stable animation frames, checks the primary action stays inside each viewport, and captures
desktop (1440×960), tablet (900×1024) and phone (390×844). The desktop and phone image initially
proved the issue; the corrected desktop, tablet and phone captures were opened and inspected. The
separate OpenCode Go Connections capture was also rechecked: it describes the vendor's actual
provider-issued API-key sign-in flow, not shared OpenCode CLI credentials.

The focused contract and browser group passed **66 tests in 15.73s** with unhandled thread warnings
and `SyntaxWarning`s treated as errors. Chromium **153.0.8010.12** / Playwright **1.63.0** used
local fixtures; the OpenAI authorization hostname was intercepted in the browser, with no real
account sign-in, provider credentials or model calls. Artifacts are under
`artifacts/provider-signin/`.

## S6 durable delegation admission foundation (schema v22, 2026-10-08)

Delegated-run lineage now persists in an indexed, database-guarded immutable `runs.parent_run_id` column and survives the normal run projection. A single
`BEGIN IMMEDIATE` admission transaction requires the parent's current live fence, the same bot identity, and a bounded non-empty
prompt; it atomically creates the child task/run, conversation attachment when present, lineage link and replay receipt. Exact retries
return the original child even if the parent has since finished; reusing the key for changed arguments conflicts. A recursive ancestor
walk rejects depth beyond two. Each parent is limited to three direct children for its lifetime and two active direct children at once.
Ordinary run-submission paths reject caller-supplied parent links, so they cannot bypass this admission boundary; a database trigger
also prevents changing a recorded parent link. The v21 migration
backup test confirms historic runs receive a null parent link.

Focused verification: `.venv/bin/python -m pytest -q -W error::pytest.PytestUnhandledThreadExceptionWarning
-W error::SyntaxWarning tests/test_delegation.py tests/test_migration.py tests/test_conversations.py tests/test_claims.py
tests/test_store_events.py tests/test_sse_resume.py tests/test_api.py tests/test_lease_authority.py` passed **108 tests in 23.54s**.
The fan-out contention case uses eight independent SQLite connections and admits exactly two direct children.
This does not yet execute a child, add a chat tool or public endpoint, cancel by lineage, snapshot capabilities across bot edits,
isolate child workspaces, or transfer child artifacts. These are required before bounded delegation is available to users.

## S6 delegated-tree budget reservation (schema v23, 2026-10-08)

Each admitted child now stores the immutable currency ceiling inherited from its top-level parent's execution-time settings.
Deeper descendants read that persisted ceiling and cannot replace it with a larger cap. Before any provider request, the existing
`BEGIN IMMEDIATE` usage reservation totals measured costs per run (using the larger of the usage ledger or legacy Run document to
avoid double counting), then adds every `reserved` or `uncertain` hold in the same root subtree and tests the proposed hold against
the shared ceiling. This runs alongside per-run, bot, account, and quota controls. A missing ceiling stays unlimited; the v23 migration
does not invent a budget for v22 history. The database trigger makes the ceiling immutable, and ordinary submission methods reject
caller-supplied delegation fields.

Focused verification: `.venv/bin/python -m pytest -q -W error::pytest.PytestUnhandledThreadExceptionWarning
-W error::SyntaxWarning tests/test_delegation.py tests/test_reservations.py tests/test_migration.py
tests/test_state_snapshot.py tests/test_provider_authority.py tests/test_lease_authority.py` passed **80 tests in 7.08s**.
Coverage includes settled parent spend, uncertain child holds, descendant inheritance despite a larger supplied value, refusal just
above the tree ceiling, immutable-column enforcement, v21-to-v23 and v22-to-v23 backup migrations, and existing provider/account
reservation behavior. The public delegation path remains unavailable; budget snapshots still need to be wired to a user-visible,
permission-bounded child executor before release.

The complete repository test run after this slice passed **1,420 tests in 486.15s** with unhandled-thread and syntax warnings treated
as errors. `git diff --check` passed. This suite is fixture-based; it does not certify live providers or make delegation user-available.

## S6 descendant cancellation intent

Stopping a run now records `cancel_requested` for that run and its already-admitted descendants in one SQLite write transaction,
before transitioning visible statuses or signaling processes. Admission and stop serialize on the same write lock: a racing child is
either committed before the stop and included in its recursive tree query, or sees the cancelled parent and is rejected. Queued,
unclaimed descendants finish as stopped; claimed or active descendants remain cancelling until their owner verifies cleanup. The
engine takes its fast path for every owned descendant process, while other workers observe their own persisted stop bit. Stopping a
child affects only that child's descendants, not its parent or siblings. No user-facing delegation control is exposed.

Focused verification: `.venv/bin/python -m pytest -q -W error::pytest.PytestUnhandledThreadExceptionWarning
-W error::SyntaxWarning tests/test_delegation.py tests/test_cancel.py tests/test_claims.py tests/test_engine.py
tests/test_engine_loop.py tests/test_approval_cas.py tests/test_receipts.py tests/test_worker.py tests/test_procguard.py
tests/test_lease_authority.py tests/test_api.py` passed **140 tests in 64.13s**. This includes a separate-connection race between child
admission and parent stop, plus a supervisor check that signals the owned descendant process and stops its queued child.

The complete repository suite then passed **1,423 tests in 487.65s** with unhandled-thread and syntax warnings treated as errors.
This does not test live providers or a user-visible child executor.

## S6 fail-closed delegated dispatch

The regular `Engine.dispatch_pending` path now excludes runs with a persisted parent link. Such rows remain pending until a
dedicated child executor enforces the inherited capability snapshot and artifact contract. A direct call to the internal worker boundary now
fails a pending child as `delegation_unavailable` before runtime resolution or tool construction. Workspace preparation for lineage
runs still selects a private 0700 per-run directory and rejects a planted symlink. Existing single-run and scheduled work continues
through the same dispatcher. Direct internal claim primitives remain useful to migration and lifecycle tests; no public request can
create or launch delegated work.

Focused verification: `.venv/bin/python -m pytest -q -W error::pytest.PytestUnhandledThreadExceptionWarning
-W error::SyntaxWarning tests/test_delegation.py tests/test_engine.py tests/test_engine_loop.py
tests/test_local_admission_runtime.py tests/test_admission.py tests/test_slots.py tests/test_workdir.py` passed **86 tests in
34.11s**. It confirms a child ignores a missing bot-selected host folder, gets a mode-0700 run-scoped path, refuses a planted
workspace symlink, and remains out of ordinary dispatch.

The direct-worker regression supplies a stale Run projection with the immutable parent link removed and confirms the engine reloads
the authoritative row, fails the child as `delegation_unavailable`, and never resolves a runtime. The process worker also rejects a
validly fenced child before recording a process group. `.venv/bin/python -m pytest -q
-W error::pytest.PytestUnhandledThreadExceptionWarning -W error::SyntaxWarning tests/test_delegation.py tests/test_worker.py
tests/test_engine.py tests/test_engine_loop.py tests/test_claims.py tests/test_cancel.py` passed **84 tests in 51.83s**. The later
full offline suite at `536c892` passed **1,333 tests in 251.04s** with unhandled-thread and syntax warnings treated as errors; browser
end-to-end checks remain a separate release gate after main integration.

## S6 immutable capability snapshot (schema v24, 2026-10-09)

Root runs now persist a canonical, credential-free policy and route snapshot in the same fenced transaction that moves the run from
pending to running. A database trigger permits only that initial capture and rejects later changes. The snapshot includes the
expanded tool set and relevant execution policy, and removes browser/network tools and shell egress from Offline bots. Child admission
requires a valid parent snapshot and copies it unchanged into the child row, so editing a bot after its parent began cannot widen a
delegation tree. Existing rows receive an empty snapshot; they cannot start new delegated admission. The snapshot is stored groundwork,
not yet a child runtime: delegated rows remain out of ordinary dispatch until the dedicated executor and artifact boundary exist.

Focused verification: `.venv/bin/python -m pytest -q -W error::pytest.PytestUnhandledThreadExceptionWarning
-W error::SyntaxWarning tests/test_delegation.py tests/test_migration.py tests/test_engine.py tests/test_claims.py` passed **65 tests
in 25.30s**. This covers v21/v22/v23 upgrade backups, empty legacy snapshots, immutable parent-to-child copying after bot edits,
credential-free Offline policy capture and a completed Engine run saving its start-time snapshot. No provider, account credential, or
delegated runtime was contacted or started. `git diff --check` passed before commit.

## S6 scoped conversation export (2026-10-08)

The Studio composer menu offers a JSON export after showing its scope: whitelisted conversation metadata plus ordered message text and
run provenance. Stored provider/connection credentials, tool/action receipts, workspace contents, artifact bytes and memory records
are excluded. Message text is verbatim and may contain sensitive user-entered material; the dialog and manifest say to review it before
sharing. A consistent SQLite read snapshot counts before loading messages, refuses histories above 10,000 messages or 2 MiB of source
data, and the endpoint enforces a 16 MiB encoded response cap. Oversized exports point back to the paginated API.

Focused verification: `.venv/bin/python -m pytest -q -W error::pytest.PytestUnhandledThreadExceptionWarning
-W error::SyntaxWarning tests/test_conversations.py tests/test_api.py` passed **31 tests in 6.54s**; the export cases also pass in
isolation (**3 tests**). `node --check src/hutch/server/static/app.js` and `git diff --check` passed. Chromium **153.0.8010.12** /
Playwright **1.63.0** passed the download, scope, error, and overflow checks at 1440×960, 900×1024 and 390×844 (**3 browser cases in
4.31s**). No provider calls were made and page errors/overflow were zero. Inspected screenshots, traces and source-hash records are in
`docs/realignment/artifacts/conversation-export/`. This slice does not add permanent deletion; archiving remains the reversible default.

## S6 approved Strict Offline delegation preview (2026-10-08)

The per-bot `delegate_task` opt-in now starts a same-bot child through the supervised process
executor, and only for the built-in Strict Offline Linux route. Every tool call needs an outward
human approval, including under the bot's automatic approval setting. Admission inherits the
immutable credential-free root capability and tree budget, but passes only explicit task text; the
child has a private workspace, no browser or memory tools, and no parent transcript or workspace
contents. The child run stays visible on the same conversation; only its final text returns to the
parent, and child artifacts are not copied. Stop cascades to descendants and cleanup status remains
visible. The tool call is serial, with depth 2, three lifetime children per parent, eight steps, ten
minutes, parent deadline, and the global worker cap. The default concurrency of two permits one
child alongside its root.

Focused API, CLI, engine, worker, claim, approval, reservation, offline and delegation regressions
passed **230 tests in 106.77s**, with unhandled-thread exceptions and `SyntaxWarning`s treated as
errors. The real-process delegation journey used a FakeOllama fixture through the isolated local
broker; this does not verify live Ollama/model provenance. The responsive Settings journey passed
**1 Chromium test in 3.37s** after keyboard opt-in/save and reload. Its emulated-touch phone header
keeps Delete recognizable at 44×44; desktop (1440×960), tablet (900×1024), phone (390×844), and
scrolled/saved phone captures were visually inspected with zero horizontal overflow and no page
errors. The anonymous website suite passed **23 tests in 30.41s**; inspected workflow screenshots at
desktop (1440×900), tablet (900×1024), and phone (390×844) had no overflow, external requests or
page errors. Chromium **153.0.8010.12**, Playwright **1.63.0**. Detector findings for changed UI
targets: none. See `delegation.md` and `visual-validation.md` for boundaries and artifact links.

Commit `c352d22` contains the delegation slice. The subsequent main integration and current verification boundary are recorded
below; no live hosted provider, paid call, physical phone or screen-reader run was used.

## Main PF-2 integration and regression checkpoint (2026-10-08)

Main's newer `c0ebc21` source-card and per-tool output limit change is now integrated in merge commit `6fab391`. The source card
links to the full run artifact, and its compatibility route verifies the recorded file size and SHA-256 through the existing
no-follow reader before returning readable `text/plain` inline. Versioned artifact downloads remain attachment responses. The
reviewed main implementation's direct `FileResponse` path-only serving was not retained. Tool details now keep both artifact
actions outside the scroll-limited preview, and on narrow screens keep long names on one line with ellipsis and a full-name title.

The complete offline suite after the merge passed **1,346 tests in 281.29s**, with unhandled background-thread exceptions and
`SyntaxWarning`s treated as failures. The full local app and website browser suite passed **102 tests in 240.02s**. This includes
the source-card route's SHA-256/size checks, script-inert plain-text opening, and desktop (1440×960), tablet (768×1024), and
phone (390×844) layouts. I inspected all three final captures under `artifacts/tool-source-card/`; there is no horizontal
overflow or browser page error. API artifact integrity and patch tests passed **3 tests**; `node --check`, Python compilation,
`git diff --check`, and the Impeccable detector (dashboard JS/CSS plus marketing HTML) passed, with the detector returning `[]`.

Merge commit `6fab391` has both `realign/platform` and main `c0ebc21` as parents. After the offline and browser suites passed,
local `main` was fast-forwarded to verified checkpoint `b5227a9`; this documentation follow-up records that integration. The
end-to-end local suite does not close the live
release gates in S5–S9: process adapters for OpenCode/Pi remain disabled, model/provider and SIWC eligibility were not verified
live, general delegation and transferred artifacts remain unavailable, and remote PTY/physical desktop control, trusted tunnel,
screen reader and physical-device checks remain unavailable or unverified. Current support boundaries remain as stated in the
slice table; this checkpoint does not promote experimental or unverified capabilities to supported.

## S0 packaged mock boundary and legacy model-picker truth (2026-10-09)

The test-only `HUTCH_TESTING` switch no longer changes product runtime selection, model-choice availability, or model override
validation. Pytest now injects its deterministic scenario through test fixtures; subprocess cancellation and worker tests opt in
explicitly, so production code does not regain a mock route to make tests pass. The installed wheel excludes `tests/` and rejects
`mock/demo` with an actionable `RuntimeUnavailable` even when that environment flag is present.

Visual review of the legacy model picker exposed a separate misleading badge: retired `mock/demo` records were labeled as sending
the chat off-machine. The real model-choice state now marks the route unavailable, gives the real-route repair, and does not claim
that the route is hosted. Chromium **153.0.8010.12** / Playwright **1.63.0** passed the rendered legacy-picker regression. The
1280×800 capture was opened and inspected at `artifacts/no-mock-setup/legacy-mock-picker.png`; the disabled row has a visible
“needs setup” status and repair guidance, no false hosted badge, and no page error. The browser fixture made no provider call.

Focused verification after the final product/UI correction passed **37 tests in 27.80s** with unhandled thread exceptions and
`SyntaxWarning`s treated as errors. The existing schedule-settings browser journey had one timeout in the initial whole-suite
run; it passed alone, and its navigation was made explicit so the browser test does not depend on a hash-only transition during
pending UI updates. The final complete offline suite then passed **1,449 tests, 2 skipped in 518.16s**, again treating unhandled
thread exceptions and `SyntaxWarning`s as failures. The final wheel build and isolated `HUTCH_TESTING=1` import passed. No live
provider, paid call, or publication was used.

## S5 legacy external-runtime recovery (2026-10-09)

Idle legacy bots saved with Pi or OpenCode can now be moved to Hutch's built-in runtime from Bot Settings. The patch API accepts only
`runtime=builtin`; it validates the bot's existing model through Hutch's built-in route before changing the record. A bot with no
usable Hutch model route remains unchanged. Any pending or active run blocks the migration: the handler checks first for a clear
message, then `Store.upsert_bot` repeats the check inside its write transaction so a concurrently admitted run cannot race the
runtime change. The Settings view identifies the saved executor as unavailable, explains that Hutch will not launch it or import
another app's private sign-in/credentials, and exposes the switch only when its preconditions hold.

`tests/test_api.py::test_unavailable_external_runtime_can_be_migrated_to_builtin_only` covers OpenCode and Pi migration, rejects a
request to migrate to another external runtime, rejects a missing model route, and blocks a bot with an active run. It also checks
the transaction guard directly. `tests/e2e/test_browser.py::test_legacy_external_runtime_can_move_to_hutch_and_run_a_real_local_route`
changes an OpenCode record through the visible Settings action, then completes a conversation with the Hutch built-in runtime using
the local FakeOllama fixture. This makes **22 fixture requests and no external provider requests**. Chromium **153.0.8010.12** /
Playwright **1.63.0** passed at desktop 1440×960, tablet 900×1024 and phone 390×844; the recovery explanation and action were visible,
with zero horizontal overflow and no page errors. Opened screenshots and the exact source hashes are in
[`artifacts/runtime-recovery/`](artifacts/runtime-recovery/). No external executor, credential, sign-in state, or live model was
used. This repairs saved-bot reachability; it does not implement OpenCode or Pi process adapters.

The compatibility guide now points to current OpenCode Go and Sign in with ChatGPT documentation. OpenCode Go is an API-key
handoff: the user signs in to OpenCode Go, copies its provider-issued key, and adds it to Hutch. Hutch does not read OpenCode's
private `auth.json`. ChatGPT uses the official, opt-in local token-sharing preview and remains eligibility-gated; its route and
limits remain experimental. A browser fixture intercepts the official authorization destination; no live account sign-in or
provider request was made.

Focused migration/API and real-browser tests passed **2 tests in 10.54s**. A clean full suite passed **1,451 tests, 2 skipped in
520.36s**, with unhandled-thread exceptions and `SyntaxWarning`s treated as errors. Afterward, responsive marketing review found
that the site's `styles.css` link still used `?v=b614bd35` although the current stylesheet hash began `2c79db7e`; browsers could
reuse the previous CSS and make the updated site appear stale. The existing asset-stamping script corrected the URL, and the new
`test_local_asset_urls_use_current_content_hashes` checks all local references against current file bytes. The copy and cache-key
updates were verified by the full anonymous-site suite: **24 tests passed in 30.28s**, including internal-link/CTA, external-request,
and overflow checks. The desktop/tablet/phone screenshots now match the final source hashes. Chromium **153.0.8010.12** /
Playwright **1.63.0**. A single Impeccable scan returned no website HTML finding. It reported advisory type/radius/color differences
in the unchanged server-rendered stylesheet; those are outside this slice and no ignore was added. Visual evidence is recorded in
`visual-validation.md`. No live provider, paid call, external executor, or public site was used.

## S8 trusted HTTPS proxy boundary (2026-10-09)

`--allow-remote` can now serve the existing paired dashboard behind an operator-managed HTTPS reverse proxy. Hutch accepts a single
`X-Forwarded-Host` and `X-Forwarded-Proto: https` only from an explicitly configured IP/CIDR in `HUTCH_TRUSTED_PROXIES`, and only
when the forwarded hostname exactly matches an entry in `HUTCH_ALLOWED_HOSTS`. It parses and bounds `X-Forwarded-For`, sets the
validated client address before pairing source-rate limits run, and strips proxy metadata received from untrusted peers. Invalid
public-host syntax and duplicate required headers fail before authentication. HTTP and WebSocket Origin scheme/host must match the
normalized HTTPS request. Cookies retain the `Secure` flag after forwarded HTTPS normalization; the existing HTTP and WebSocket
device-auth checks still apply.

`GET /api/v1/capabilities` reports `trusted_https_proxy` as unavailable until remote access, a trusted proxy and an explicit public
host allowlist are configured. Configured support is labeled experimental because this evidence is local ASGI fixture coverage only.
`tests/test_remote_pairing.py tests/test_api.py` passed **40 tests in 6.76s**, with unhandled-thread exceptions and syntax warnings
promoted to errors. The tests cover pairing/Origin/cookie behavior, host allowlisting, untrusted-header stripping, malformed ports,
duplicate-header rejection, source-IP attribution, a device-authenticated WebSocket and capability configuration. `git diff --check` and Python compilation
passed. No real reverse proxy, tunnel, network, phone or browser session was used; no UI changed, so this backend slice adds no new
visual capture. Existing desktop/tablet/phone evidence remains in the prior S9 checkpoints and is not a live remote test.

The implementation is not a managed tunnel and does not change the marketing support claim. Setup requirements and limitations are
in [operations](../operations.md#phone-supervision-over-private-https), [safety](../safety.md#remote-dashboard-access-is-experimental), the
[API contract](contracts.md#6-phone-supervision-partial-experimental), and [ADR-0010](../adr/0010-api-transport-and-remote-supervision.md).
S8 still has open PTY, physical desktop, remote-browser-control, replay-retention and live-network gates.

## Dashboard motion and readable leading (2026-10-09)

Commit `56402af` removes the running-state pulse from both the legacy dashboard's source/generated CSS and its workflow/status indicators.
The server-rendered dashboard body leading is 1.6; the legacy console remains at 1.55. “Working”, “running”, “live” and
“reconnecting” labels communicate state without an animated status dot. The source/generated-CSS check prevents a later Tailwind build
from restoring the legacy pulse. `DESIGN.md`, its sidecar, the design-system guide, and detector exceptions now describe the rendered
behavior; the obsolete pulse ignore and stale worktree-path leading ignore were removed.

The focused Chromium/Playwright dashboard test passed at desktop **1440×960**, tablet **900×1024** and phone **390×844** in
**4.40s**. Studio body metrics were 14px/21.7px (1.55); server-rendered body metrics were 14px/22.4px (1.6); headings measured
1.3 and 1.4 respectively. Studio typing/workflow/running dots and the server-rendered live mark computed to no animation. All captures
had zero page errors and horizontal overflow. I inspected Studio and Connections captures at each width. Evidence, hashes and trace are
in [`artifacts/dashboard-polish/`](artifacts/dashboard-polish/). The Impeccable scan of the website, legacy app and server template
returned no findings after evidence-based exceptions; JSON validation and `git diff --check` passed. This is a local visual check, not
a screen-reader or physical-device audit.

## Durable resource-change retention (2026-10-09)

Commit `48fdf92` bounds only the content-free `/api/v1/changes` invalidation outbox to 50,000 rows.
The elected supervisor prunes it on the first tick and every five minutes thereafter, inside the
store's write transaction. The retained boundary row preserves its predecessor link, so an exact
boundary cursor can replay; an older cursor returns `snapshot_required`. Source rows, conversations,
messages, approvals, transcripts and the global run-event stream are not deleted by this policy.

The focused durable-change, SSE-resume and supervisor-loop suite passed **40 tests in 10.94s** with
unhandled-thread exceptions and `SyntaxWarning`s treated as errors; `git diff --check` passed. Tests
cover boundary replay, stale and absent cursor reconciliation, source-resource preservation, invalid
retention values and the five-minute pruning cadence. This backend-only slice changes no rendered
view, so it adds no new screenshots; existing responsive captures remain in the preceding visual
checkpoints.

## Compact bot navigation and in-chat approvals recheck (2026-10-09)

The recheck confirmed Studio remains the primary surface for a small setup and Fleet becomes
available at ten bots. Pending action details stay reviewable in the active conversation, with the
decision button retaining focus across transcript refresh. Fleet still surfaces both queued action
reviews and a human-needed browser wait when approval-list discovery fails.

Five Chromium/Playwright browser checks passed in **8.88s**, covering the one-bot path, the ten-bot
threshold and filters, inline approval review/resolution, and Fleet attention at desktop and phone
sizes. I inspected the generated **1440×1000** and **390×844** Fleet screenshots; they have no page
errors or horizontal overflow. Source hashes and captures are in `artifacts/fleet-attention/`.
Synthetic states were used; no provider, real action or device was exercised.

## Strict-offline delegation regression checkpoint (2026-10-09)

The first full offline rerun exposed one fixture failure: the host had less available memory than
the test's default inference preset required, so the truthful memory-headroom admission rejected
the child before it started. The fixture now asks for a 4,096-token context, which fits the
measured host headroom; the admission rule remains unchanged. The isolated journey passed, then
the complete non-browser suite passed **1,364 tests in 286.69s** with unhandled background-thread
exceptions and `SyntaxWarning`s treated as errors. Browser and anonymous-site suites remain separate
gates. No real model, provider, paid account or external runtime was used.

## Grok Bot product-reference checkpoint (2026-10-09)

Reviewed the current public Grok Bot documentation for Bot profiles, message-first setup, direct and group chats,
asynchronous handoffs, Team Bots, computer access, approvals, skills/routines, and recovery. Its most transferable
patterns are a durable named role, task-specific messages that state outcome and boundary, one owner per handoff
stage, direct conversation with individual Bots, visible asynchronous return messages, and a small roster of
specialists. The documentation warns that too many parallel handoffs can duplicate work and create noisy updates.

Hutch's extension is a user-named workspace coordinator with a durable conversation and explicit cross-Bot task
lineage. The coordinator will improve a task brief using the user's current request and selected context, preserve
the original text/provenance, show assumptions for correction, and ask only for unresolved details. Prompt text may
not grant additional permissions, accounts, data, budgets, or change a standing Bot role. User confirmation remains
required for persistent Bot creation and standing-role edits. Task completion and result delivery are separate,
durable states so a lost notification cannot replay a completed effect. Users retain direct conversations with each
task Bot. A full fleet-management page remains secondary until the roster grows; roughly ten Bots is the user's
starting heuristic, not a research result.

Grok Bot's official docs say all personal Bots share one account computer, including files, browser sign-ins and
command credentials; individual screens are not isolation boundaries. Hutch retains its per-Bot browser profiles,
managed workspaces, capability snapshots and explicit artifact sharing instead. Its docs also keep approval, login,
secret and external-message draft cards out of group conversations, so Hutch's human-required actions remain in an
accountable one-to-one chat. Public user reports of concurrent-task organization confusion and shared-computer
concerns were reviewed as anecdotes only. Recovery docs also disclose that restoring the last saved snapshot can
lose recent unsynced work; Hutch's status/recovery UI must distinguish waiting, recovery and result-delivery failure.

Research is in `docs/research/grok-bot-product-review-2026-10-09.md`; source citations are there. Documentation was
reviewed on 2026-10-09, but Grok Bot was not run or connected. Hutch's guided creation wizard is implemented and
fixture-captured; latest-user-message draft reuse is now a narrow UI-15 increment, while full configuration inference,
asking only unresolved questions, named coordinator, cross-Bot routing and durable result delivery remain open. Acceptance:
UI-15 and CO-12/13 in `docs/requirements.md`, the planned coordinator contract in
`docs/realignment/contracts.md`, and T-COORDINATOR-BRIEF/T-CROSS-BOT-DELIVERY in `docs/realignment/tests.md`.

## Browser credential entry, human checkpoints and owner additions (2026-10-09)

Commit `0e7ef76` implements the local browser handoff and guided setup slice. The browser tool now blocks `type` before browser input when conventional password, passcode/OTP, payment-secret,
or token field metadata matches. Safe-to-record arguments replace typed values with a redacted marker and opaque
reference. The approval detail contains a process-keyed value fingerprint and character count rather than text;
navigation records remove URL userinfo, secret-like query values, and fragments. Screenshots fail closed while a
conventional sensitive field is visible. A bot with the opt-in Linux local browser handoff pauses the same owned
profile for a person to enter sensitive data or complete a detected CAPTCHA/MFA/login step, then resumes without
reloading the live page. Detection remains heuristic, and no live account challenge or physical-phone handoff was
tested.

Focused browser profile, proxy and NetGuard regressions passed **115 tests in 6.08s** with background-thread and
syntax warnings treated as errors. The guided creation fixture passed **1 Chromium journey in 5.19s** at desktop
(1440×960), tablet (900×1024) and phone (390×844); its 13 setup/review captures and source hashes are in
`artifacts/bot-setup/`. The anonymous website suite passed **24 tests in 29.03s**. I inspected the current marketing
feature section at desktop, tablet and phone sizes; the new handoff claim is labeled experimental/desktop-only and
does not produce horizontal overflow. Captures and hashes are in `artifacts/provider-signin/`; the inspected
`website/index.html` SHA-256 is `011d718edfd980d0c7250ba07fe91c5f5987f54c034963ad5e4cb1b06248531d`.

Three further owner requirements remain unimplemented: editable workspace/per-Bot model defaults with explicit
per-run overrides and visible actual routes (CO-14), durable cross-Bot safe-progress checkpoints (CO-15), and
separately controlled Bot memory with explicit provenance-carrying sharing (CO-16). Existing ordinary Bot model
settings, run events/action receipts and Bot-scoped reviewed facts are foundations only. Message-anchored replies
are now implemented as UI-19; see the next checkpoint. The marketing site does not claim unsupported coordinator,
model-default, checkpoint or memory-sharing behavior.

## S6 message-anchored replies (schema v25, 2026-10-09)

Commit `104fe62` adds a message-level **Reply to this** action in Studio and a removable composer reference. The
selected reference is scoped to the current conversation and survives reload with the user's unsent draft. The
versioned send command preserves it through exact idempotent retries; reusing the key for a different target conflicts.
The transcript and JSON export retain the message ID. The API returns only an assistant message in the requested
conversation; absence and cross-chat attempts share a 404. Transactional admission and database triggers repeat the
same role/conversation checks. The explicitly referenced text is labelled untrusted, fits inside the bounded context
budget, truncates at 4,000 characters and cannot alter stored Bot permissions, account, approval policy or budget.

`tests/test_conversations.py tests/test_migration.py` passed **22 tests** with unhandled-thread and syntax warnings
as errors. This includes schema-v24-to-v25 migration, legacy rows, role and conversation isolation, update/insert
guards, 4,000-character context bounds, history/export persistence, exact replay through an application restart,
and conflicting-target rejection. `tests/e2e/test_browser.py::test_bot_message_reply_is_keyboard_accessible_editable_and_persisted`
passed **3 Chromium viewport cases** at 1440×1000, 900×1024 and touch 390×844. Keyboard selection/removal and focus,
reload restoration, anchored sending, 44px touch targets, no page errors and no horizontal overflow were checked.
Chromium **153.0.8010.12** / Playwright **1.63.0** screenshots, traces and matching source hashes are in
`artifacts/message-replies/`; I inspected both preview and sent states at all three sizes. The Impeccable detector
returned no findings for `app.js` and `style.css`. There was no live model/provider call; physical phone and
screen-reader behavior remain unverified. The whole repository suite was not rerun for this slice.

## S6 conversation-sourced Bot creation (2026-10-09)

Studio's New Bot wizard now fetches only the most recent user-authored message from the active conversation and presents it as an
editable purpose draft with a checked opt-out. Older turns, including the fixture's unrelated private message, are not copied. The
review identifies the source Bot, conversation and message sequence, and can show the original request alongside the edited Bot
instructions. `POST /api/v1/bots` accepts paired conversation/message identifiers only for a user message in that exact chat;
the durable Bot document keeps original text and provenance, while Bot API views expose metadata but not a second copy of the
message body. Source identifiers participate in the idempotency digest. The operation still creates no conversation turn or run.

`tests/test_api.py::test_bot_creation_records_only_an_explicit_user_message_source` passed. Chromium **153.0.8010.12** /
Playwright **1.63.0** passed `tests/e2e/test_browser.py::test_bot_creation_reuses_only_the_selected_chat_request_and_keeps_provenance` at desktop 1440×960, tablet 900×1024 and phone 390×844. It verified opt-out, edit, exclusion of an older private turn, persisted exact provenance, no run, no page errors and no horizontal overflow. I inspected the purpose and review screenshots at all three sizes; the modal, source choice, quote and footer fit the phone layout. Artifacts, trace and source hashes are in `artifacts/bot-setup-context/`. No provider/model call, physical phone or screen reader was used.

The marketing workflow now describes the same editable, latest-message draft and says Bot creation does not run work. The anonymous
Chromium check passed at the same three widths with no external requests, page errors or overflow; I inspected the step card captures
in `artifacts/bot-setup-context/site/`. The Impeccable detector returned no findings for the edited Studio JavaScript, stylesheet or
marketing HTML.

This is a narrow UI-15 increment, not completion: the wizard still asks for the name, template, model/mode, workspace, tools, limits
and schedule, and it does not infer safe configuration or ask only unresolved questions. No new permissions, accounts, tools,
budgets, runs or conversation history are authorized by the source message. Implementation commit: `8445134`.

## S6 chat-sourced Bot model suggestion (2026-10-09)

Commit `32f98e2` carries the active chat Bot's configured non-mock route into the New Bot wizard as an explicitly named, editable
suggestion. The user can replace it; review makes clear that the confirmed route becomes the new Bot's saved default and that
creating the Bot starts no run. This is a per-Bot suggestion, not a workspace-wide default or a provider/account switch. The
inference-mode choices are shortened so they remain readable in the phone-sized modal.

The app/API/marketing focused verification passed **3 tests in 7.24s** with background-thread and syntax warnings treated as
errors: `test_bot_creation_reuses_only_the_selected_chat_request_and_keeps_provenance`,
`test_public_bot_setup_copy_matches_reviewed_chat_sourced_creation`, and
`test_bot_creation_records_only_an_explicit_user_message_source`. The Chromium flow checked the inherited suggestion, editable
route, compact inference labels, saved route and no-run behavior at 1440×960, 900×1024 and 390×844. I inspected the model-step
screenshots and the anonymous marketing card at each size; the route, description and footer remain in view without page overflow.
The anonymous site had no page errors or external requests. `node --check`, JSON artifact validation, and `git diff --check`
passed. The Impeccable detector returned no findings for the changed app and marketing files. No model/provider call or live
account was used.

CO-14 remains partial: this does not add a workspace-wide default, coordinator/specialist configuration, explicit per-run versus
save-as-default control, or actual-route identity on future cross-Bot runs. CO-15 safe progress checkpoints and CO-16 separately
controlled Bot memory grants also remain open.

## S6 workspace model defaults for new Bots (2026-10-09)

Commit `fd001c3` adds `GET/PUT /api/v1/preferences/model-defaults` and Preferences → Model defaults for new Bots. A validated
workspace route and inference mode seed new Bot drafts only; each explicit route or mode independently takes precedence. A route
suggested by the active chat Bot remains editable and takes priority over the workspace route. Existing Bots, conversations and
runs are unchanged. Strict Offline still requires verified local host isolation. Leaving the route blank lets the user select one
in setup, while the selected workspace mode continues to seed that draft. The preference cannot make an unconfigured Bot runnable.

`tests/test_api.py` passed **31 tests** with unhandled-thread and syntax warnings treated as errors. The browser and anonymous
website checks passed **3 tests** in **7.99s**: workspace preference persistence/new-Bot seeding, chat-sourced route suggestion,
and truthful site copy. Test-only credentials were not sent to a provider. The model-default journey generated screenshots and a
trace at desktop 1440×960, tablet 900×1024, and phone 390×844; the public card was captured at 1440×900, 900×1024, and 390×844.
I inspected the preference dialog, the new-Bot model step, and all three public-card sizes. The site made zero external requests;
there were no browser errors or horizontal overflow. `node --check`, `git diff --check`, JSON evidence checks, and Impeccable
detector passed. No live provider/model, physical device or screen reader was used.

CO-14 remains partial: this setting does not implement coordinator/specialist model controls or route identity for cross-Bot runs.
CO-15 recovery-safe coordinator checkpoints and CO-16 explicit cross-Bot memory grants remain open. Implementation commit:
`fd001c3`.

## S6 one-message model choice and explicit Bot default (2026-10-09)

Commit `3d36c3c` changes the Studio model picker from a sticky per-Bot selection to a one-message override scoped to the
current conversation. The selected route survives reload for that conversation, does not bleed into a new conversation,
and is consumed only after the message endpoint accepts the command; a rejected send retains the selection for retry.
The resulting run stores `model_override` while the saved Bot model and scheduled route remain unchanged. **Save as Bot
default** is a separate model-only Bot update through the existing server validation. It clears the pending override,
creates no run, and applies to later chats and scheduled runs.

Six focused Chromium/Playwright checks passed in **29.71s**, covering conversation isolation, one-message consumption,
explicit saved-default persistence, no-run-on-save, the all-models dialog, phone fit, workspace-default Bot setup and
anonymous marketing copy. The test used FakeOllama and made no provider/model call. I inspected the new model-menu and
public inference-card captures at **1440px, 900px and 390px** widths; the menu/action stayed inside the viewport, the
public card wrapped without horizontal overflow, and both browser runs recorded zero page errors. Source-hash metadata
matches the tested picker files. `node --check`, `git diff --check`, artifact JSON validation and the Impeccable detector
passed; the detector returned no findings. This verifies the ordinary-Bot picker only. CO-14 remains partial because
workspace-coordinator/specialist model controls and actual model identity on cross-Bot runs are not implemented. No
live provider, physical phone or screen-reader check was performed.

## S6 typed chat choices (2026-10-09)

Schema v26 adds immutable single- and multi-select questions to built-in conversation runs. The conversation-only
`ask_user_choice` tool is separate from the bot action allowlist and approval path. The runtime stops after saving the question;
mixed provider batches containing that tool are rejected before any sibling tool runs. The Studio renders a keyboard-selectable
question card and labels its parent conversation “Waiting for your choice,” while the execution run remains terminal. One answer
transaction links the selected option IDs to the question, records a normal user message referencing the exact assistant question,
and creates an idempotent next run. Choices cannot approve or authorize actions. Questions and pending decisions survive restart;
the answer is one-use, scoped to the same conversation, and changed requests on a reused idempotency key conflict.

Focused persistence, runtime, API and migration checks passed **66 tests** across `tests/test_conversations.py`,
`tests/test_runtime_builtin.py` and `tests/test_migration.py`. The browser journey passed at desktop **1440×960**, tablet
**900×1024** and phone **390×844** using Chromium **153.0.8010.12** / Playwright **1.63.0**. It exercised keyboard selection,
multi-select, the real answer API, persisted answered state and zero horizontal overflow; I inspected pending, selected and
answered captures. `node --check` and the Impeccable detector passed with no findings. Artifacts and source hashes are in
[`artifacts/structured-choices/`](artifacts/structured-choices/); the test is
`tests/e2e/test_browser.py::test_chat_choice_question_is_selectable_and_readable_at_all_viewports`.
The full offline suite passed **1,379 tests in 334.17s** (`.venv/bin/python -m pytest -q --ignore=tests/e2e`); the final browser
journey passed separately in **4.72s**. The migration tests now also cover replaying v25/v26 upgrades against a current fixture.

The browser uses SQLite-seeded questions and makes **zero model/provider calls**; a newly submitted answer run is queued in this
fixture because its engine tick is disabled. No live OpenCode/Pi adapter, provider, physical phone or screen-reader check was
performed. External runtimes do not expose the tool yet; CAPTCHA and other browser human-control events remain a separate,
unimplemented handoff capability. The anonymous marketing workflow now says the built-in chat can ask for a preference and that
the response is not approval. `tests/e2e/test_website.py` passed **25 tests**; I inspected the workflow at **1440×900**,
**900×1024** and **390×844**. Its browser made no external requests and reported no errors or page overflow; updated captures and
the page hash are in [`artifacts/scheduled-tasks/site-validation.json`](artifacts/scheduled-tasks/site-validation.json) and the
adjacent `site-workflow-*.png` files. Implementation commit: `c0acf26`.

## S5 local Google Calendar read path (experimental, 2026-10-09)

Schema v27 stores a named account reference and one selected-calendar grant per Bot. The new
`GoogleCalendarBook` uses Google's installed-app authorization-code flow with S256 PKCE and an exact
loopback callback. It keeps the refresh token in Linux Secret Service via `secret-tool` and the
short-lived access token only in process memory; callback code/state are removed from the ASGI query
before access logging. The Connections UI opens Google in an isolated browser tab, confirms the
account-wide read-only permission boundary, and requires a separate selection before the built-in
runtime exposes the typed `google_calendar_events` tool. That tool can only access the Bot's selected
calendar, returns bounded titles/times/locations, excludes descriptions/attendees, and is omitted in
Strict Offline mode. Returned fields remain in that Bot's run history. No Calendar write or Gmail/
Outlook operation is available.

Official Google documentation was rechecked on 2026-10-09: installed apps should open the system
browser and support PKCE; `calendar.events.readonly` is account-wide, while CalendarList has its own
read-only scope. The Gmail API lists body-reading scopes such as `gmail.readonly` as restricted and
requires public-app verification; applicable restricted-data server storage/transmission also
requires security assessment. See [Calendar scopes](https://developers.google.com/workspace/calendar/api/auth),
[installed-app OAuth](https://developers.google.com/identity/protocols/oauth2/native-app),
[Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes), and
[restricted-scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification).

Google's Calendar API partial-response fields now ask for only calendar IDs/names/roles and event
titles/start/end/location, so descriptions and attendees are not fetched by Hutch. Google documents
the `fields` parameter as a way to limit returned fields in its [Calendar performance guide](https://developers.google.com/workspace/calendar/api/guides/performance).

Focused Calendar/API/migration/ChatGPT-auth/API/tool tests passed **87 tests in 8.66s**. The browser
journey passed in Chromium **153.0.8010.12** / Playwright **1.63.0** in **2.57s**: it exercised account metadata,
calendar selection, persisted Bot grant, consent disclosures, and a fixture-captured isolated-tab
OAuth URL; the provider was not contacted. It captured overview and granted-account states at desktop
**1440×960**, tablet **900×1024**, and phone **390×844**, with no page errors, external requests or
horizontal overflow. I inspected phone/tablet/desktop captures; all controls fit and the account-wide
Google scope warning is visible before connection. Evidence is in `artifacts/google-calendar/`.
`node --check src/hutch/server/static/app.js` and `git diff --check` passed. No real Google user,
consent screen, token, event data, Gmail/Outlook account, or live provider request was used; public
OAuth verification and Windows/macOS credential stores remain unavailable. This code therefore
remains opt-in behind `HUTCH_GOOGLE_OAUTH_CLIENT_ID` and Linux Secret Service, not a publicly verified
integration. Implementation commit: `ce5d99c`.

## Purpose-derived professional Bot names and coordinator selection foundation (2026-10-09)

Commit `1e6b1ab` separates a Bot's human-facing `display_name` from its stable address. New Bot
setup derives an editable professional name and address locally from the user's stated purpose, shows
both again for review, and does not make an additional model/provider request or start a run. Names
are normalized and persisted through API, CLI, dashboard settings, chat, approvals, schedules, and
history while legacy Bot addresses and links remain unchanged. Existing records get a readable
fallback such as `QA Review Bot` from their stable slug. The CLI accepts `--display-name` and shows
both name and address.

Schema v28 and `/api/v1/workspace/coordinator` add one durable workspace coordinator selection and
Bot-list identity metadata. This is selection groundwork only: the coordinator still has no direct
conversation view, task-brief review, cross-Bot dispatch, correlated replies, or delegation controls.
Those remain part of the open S6 collaboration acceptance.

Focused API/migration checks passed **17 tests**, the responsive Bot-setup journey passed **3 browser
tests in 15.45s**, and the full CLI suite passed **12 tests in 8.40s**. `node --check`, Python
compilation and `git diff --check` passed. Anonymous marketing and token checks passed **31 tests**;
the revised professional-name/no-extra-model-call/editability claim passed its targeted site test.
I inspected the Bot identity, review and chat captures at desktop **1440×960**, tablet **900×1024**
and phone **390×844**, plus the marketing workflow at desktop/tablet/phone sizes. Captures and
Playwright trace are in `artifacts/bot-naming/`; updated public workflow captures and source hashes
are in `artifacts/scheduled-tasks/`. Browser fixtures made no provider calls; no live provider,
physical phone or screen-reader check was performed.

## Named workspace coordinator direct chat (2026-10-09)

Commit `22fdf6b` turns the persisted coordinator selection into an accessible product role. Bot
Settings can make one Bot the workspace coordinator, replace the existing selection or clear it;
Studio orders that Bot first in the roster, marks the role, and selects it as the initial chat on a
fresh visit. The coordinator remains an ordinary Bot with its own canonical conversation and saved
model/policy. Other Bots remain available for direct chat. Replacing the role changes no Bot
permissions or account grants. Cross-Bot dispatch and coordinator task-brief refinement remain open.

The API selection/restart/deletion check and responsive Chromium journey passed; the browser test
passed **1 test in 6.08s** on Chromium **153.0.8010.12** / Playwright **1.63.0**. It confirmed initial
default-chat selection, role replacement through Settings, specialist direct chat, and no horizontal
overflow at desktop **1440×960**, tablet **900×1024**, and phone **390×844**. I inspected all three
captures; the role label compacts on phone. `node --check` and `git diff --check` passed. Captures,
trace and source hashes are under `artifacts/workspace-coordinator/`. No provider/model call,
physical-device or screen-reader check was used.

## Reviewed coordinator-to-specialist handoff (2026-10-09)

Commit `a83aac1` adds one explicit, user-reviewed handoff from a completed coordinator response to
an existing specialist Bot. The user can edit the proposed purpose-based brief and assumptions,
inspect the specialist's saved model/tools/action policy/workspace, and confirm before admission.
The specialist receives a new independent conversation with only that reviewed brief and
assumptions; its own enabled memory and workspace still apply. The coordinator timeline retains
request/draft provenance, owner, reviewed constraints, capability snapshot, durable status and the
latest result, with a direct link to the specialist chat. Exact retries return the same task and
changed retry bodies conflict. Capability changes after review fail before worker creation. This
is a narrow handoff; reusable specialist allowlists, autonomous multi-step planning, restart-safe
cross-Bot checkpoints, task cancellation, artifact transfer and live provider verification remain
open.

Focused migration/conversation/engine/browser/site validation passed **32 tests in 17.36s**; the
JavaScript syntax and staged diff checks passed. Chromium **153.0.8010.12** / Playwright **1.63.0**
covered the review, edited brief/constraints, completion card and direct-chat route at desktop
**1440×960**, tablet **900×1024** and phone **390×844**. The anonymous website workflow was checked
at **1440×900**, **900×1024** and **390×844**. Screenshots and trace are in
`artifacts/workspace-task-dispatch/`. Fixtures used local SQLite/mock execution only; no provider,
paid call, remote device or screen-reader check was performed. Full-suite verification remains a
release gate.

## Explicit specialist-result return (schema v30, 2026-10-09)

Commit `4eb4e6d` adds a user-selected result reference from a completed specialist task to a normal coordinator follow-up. The
server binds the reference to the specialist task, successful assistant message and original coordinator conversation, and stores
an immutable 4,000-character snapshot plus source Bot name on the user message. The coordinator gets only JSON-escaped, explicitly
untrusted text; files, other history, memory, credentials and permissions are not transferred. The reference survives transcript
reload/export and an exact request retry. The composer displays the source and preview, supports removal before send, and restores
only while the task and exact result message still exist.

The API/store regression covers invalid and cross-chat references, incompatible reply types, exact replay and changed-payload
conflicts, hostile markup, bounded snapshots, and export provenance. Migration, conversation, API, engine-boundary, app-browser and
anonymous website checks passed **65 tests in 29.45s**; after improving the phone evidence scroll and explicitly exercising Remove,
the responsive browser journey passed again (**1 test in 17.76s**). `node --check`, Python compilation and `git diff --check` passed.
I inspected the coordinator follow-up at **1440×960**, **900×1024** and **390×844**, plus the composer attachment on phone. The site
copy was refreshed and inspected anonymously at desktop/tablet/phone with local-only requests and no overflow. Evidence and trace are
under `artifacts/workspace-task-dispatch/`. Fixtures used local SQLite/mock execution; no live provider, physical device or
screen-reader check was performed. The full suite remains a release gate.

## S6 Content-free cross-Bot checkpoint timeline (schema v31, 2026-10-09)

Commit `9d2f589` adds an append-only journal of selected specialist-run event markers, atomically derived from committed events.
The v31 migration backfills existing tasks without copying event content and uses the nearest preceding status marker. Each row
is linked to its task and child run; the child remains the source of the captured capability snapshot and full decision/effect
record. Checkpoint rows reject in-place update or deletion while their task exists, and task removal cascades its own timeline.
The task projection reports a materialized total and fetches only the newest 16 markers for each of at most 100 tasks. The UI
labels statuses in text, discloses that the timeline stores no reasoning/action text, and says restart continuation is unavailable.
No resume or retry from a checkpoint was introduced; uncertain effects still require reconciliation.

Migration/backfill and transactional redaction regressions passed, including a historical event with private prompt/action fields;
the coordinator conversation test covers exact ordering, content-free fields, materialized totals and latest-16 behavior. Three
previously failing downgrade tests now construct the actual pre-v25 database shape before lowering `user_version`, and the lazy
provider-import check removes the test-only `sitecustomize` environment from its child process. After these test-fixture repairs,
`.venv/bin/python -m pytest -q --ignore=tests/e2e` passed **1,404 tests in 304.33s**. The responsive specialist-task browser test
passed **1 test in 18.16s**, and the combined browser/anonymous-site run passed **2 tests in 20.08s** before the final phone-scroll
assertion; the browser test then passed again with that assertion. Browser and website checks use local mock/SQLite fixtures; the
anonymous site made zero external requests. Chromium **153.0.8010.12** / Playwright **1.63.0** screenshots were inspected at app
desktop **1440×960**, tablet **900×1024**, phone **390×844**, and site desktop **1440×900**, tablet **900×1024**, phone **390×844**.
The last phone checkpoint was scrolled above the sticky composer, and all three app sizes have zero horizontal overflow. Node syntax,
Python compilation and `git diff --check` passed. Evidence and trace are in `artifacts/workspace-task-dispatch/`. No live provider,
physical phone or screen-reader validation occurred. CO-15 remains partial because these markers do not continue execution after
restart; S6 collaboration and full S9/release gates remain open.

## S6 Optional task-only reviewed coordinator facts (schema v32, 2026-10-09)

Commit `3728baf` lets the owner select up to eight current, approved facts from the workspace coordinator or the exact
coordinator chat while reviewing one specialist handoff. Nothing is selected by default. The server rechecks ownership,
scope, approval, latest revision and content hash in the same transaction that creates the child task, then freezes the
selected values and provenance in an immutable task-only table. A bounded JSON form enters the specialist attempt as
untrusted run context; it is not written into specialist memory or copied to another task. The serialized limit measures
the exact HTML-sensitive escaped payload sent to the model. Review UI shows the source, revisions and size, limits selection,
and discloses provider retention and that submitted copies cannot be recalled. The task card shows exactly which references
were shared and their provenance. Older Bot records without `display_name` retain a slug-derived source label. Pre-v25
migration fixtures now also remove the v32 trigger/table before lowering schema versions.

The focused API/migration tests passed **3 tests in 1.03s**, including escaped-size and slug-only Bot regressions; the three
pre-v25 delegation migration tests passed **3 tests in 0.60s** after fixture correction. The fresh offline suite passed
**1,404 tests in 300.27s**, with unhandled thread exceptions and syntax warnings treated as errors. The responsive handoff
and anonymous website journey passed **2 browser tests in 20.19s** using Chromium **153.0.8010.12** / Playwright **1.63.0**.
I inspected the phone review, shared-fact cards at desktop/phone, and the public phone workflow; the expanded review fits
above its fixed footer, the cards expose exact source and scope, and the marketing copy discloses the boundary. Automated
overflow checks cover **1440×960**, **900×1024**, and **390×844**. `node --check`, Python compilation and `git diff --check`
passed. Screenshots and trace are under `artifacts/workspace-task-dispatch/`. The fixtures use local SQLite and mock execution;
no live provider, human account, screen reader or physical phone was used. Provider-side copies cannot be recalled. This
closes only the optional task-only fact-sharing contract, not general cross-Bot memory grants, safe task continuation, or
the remaining S6/S9 release gates.

## S9 Coordinator quote/source side-tab cleanup

Commit `8052655` replaces the left-edge stripes on assistant quote blocks and the coordinator's quoted request with a uniform
1px neutral outline and the existing sunken surface. The source card remains a semantic blockquote, but its role is communicated
through content and a full surface boundary rather than a side-tab accent. The responsive browser test checks matching top/left
border widths and colors, captures the source card at desktop/tablet/phone sizes, and retains the existing no-overflow and task-flow
assertions. The scoped CSS detector reports no side-tab findings after the change; pre-existing radius advisories were not changed.

Chromium **153.0.8010.12** / Playwright **1.63.0** passed
`tests/e2e/test_browser.py::test_coordinator_specialist_dispatch_is_reviewable_at_all_viewports` in **19.01s** using local mock/SQLite.
I inspected the request block at **1440×960**, **900×1024** and **390×844**; the outline is quiet at all sizes, and the phone modal
keeps the content reachable above its sticky footer. The first browser attempt crashed while `/tmp` had only **444 MiB** free; the
disk-backed temporary-directory rerun passed. `node --check` and `git diff --check` passed. Evidence is in
`artifacts/workspace-task-dispatch/review-source-{desktop,tablet,phone}.png`, `validation.json` and the Playwright trace. No
screen-reader or physical-device check was performed.

The Impeccable hook later flagged the quote/source cards as side-tab accents. Inspection confirmed both use neutral, uniform 1px
outlines, and a fresh exact-file scan found zero anti-patterns. A file-scoped false-positive exception records that evidence in
`.impeccable/config.json`; the cards retain their full outline treatment.

## S6 four-screen chat-driven Bot creation

Commit `7578d99` reduces the Studio Bot-creation flow from six screens to four. The exact latest user request remains editable and
provenance-linked. Hutch suggests a professional display name/address locally and updates the suggestion as the request changes
until the user edits it. A configured source-chat or workspace model route carries forward; if neither exists, the user still
chooses a route. The remaining defaults are a managed workspace, blank starter, no tools, ask-first actions, no schedule, and
bounded execution defaults. Starter, tool, schedule, limit and browser-handoff controls are optional disclosures. The last screen
still shows the complete reviewed draft; creation remains idempotent and starts no run. A semicolon clause boundary regression in
the name suggestion was found by the browser test and corrected.

The focused run passed **5 tests in 13.19s** with unhandled-thread and deprecation warnings treated as errors: four Bot-creation
journeys and the anonymous marketing-copy journey. Chromium **153.0.8010.12** / Playwright **1.63.0** verified desktop **1440×960**,
tablet **900×1024** and phone **390×844**; I inspected the purpose, optional-settings and final-review captures at those sizes.
The marketing card was checked at **1440×900**, **900×1024** and **390×844**, with zero external requests, page errors or overflow.
Evidence is in `artifacts/bot-setup/` and `artifacts/bot-setup-context/site/`. `node --check`, artifact JSON/source-hash checks and
`git diff --check` passed. No model/provider request, live account, physical phone or screen-reader check was performed.

UI-15 remains partial: the user must review the whole draft and select a model when no route is configured. Hutch does not rewrite
the request using a model or ask follow-up questions conversationally; it does not infer tools, accounts, or authority from context.

## S5 Experimental Outlook Calendar (schema v33, 2026-10-09)

Commit `264f828` adds local Microsoft public-client authorization-code + S256 PKCE for read-only Outlook Calendar. Hutch stores
refresh tokens in Linux Secret Service, keeps credential-free account metadata outside the SQLite/transcript secret boundary,
strips callback secrets from access-log scope, and uses a fixed Microsoft Graph host with redirects disabled and validated
continuation links. The only delegated Graph scope is `Calendars.ReadBasic` plus `offline_access`; each Bot gets one owner-selected
calendar grant, and the tool returns at most 25 titles, start/end times and locations for a range no longer than 366 days. Strict
Offline removes this tool. The registration's supported account types must match the accounts an operator permits; `/common` does
not widen that registration. Local disconnect clears Hutch's credential/grants and tells the owner to revoke provider consent
separately. Mail and calendar writes remain unavailable.

The HTTP/OAuth, API, migration, tool and offline regression group passed **83 tests in 7.10s**. The responsive Connections journey
passed **1 test in 2.65s** with synthetic account/calendar data and zero provider calls. The complete anonymous website suite passed
**26 tests**; the availability table and public naming claim were checked at desktop **1440×900**, tablet **900×1024** and phone
**390×844**. Phone layout hides the duplicate status column and no viewport requires horizontal scrolling. I inspected app overview/
granted captures and full desktop/tablet/phone support-table captures. No page errors or external requests occurred; website source
and style hashes and app viewport metadata are recorded under `artifacts/outlook-calendar/`. Python compilation, JavaScript syntax,
`git diff --check`, and Impeccable exact-target scans passed; the app stylesheet scan found **0 anti-patterns** and three advisory
radius-token notes, not side-tab findings. Fresh offline fixtures do not verify an Entra registration, Microsoft account, consent
screen, live Graph behavior, physical device or screen reader. Implementation commit: `264f828`.

## S6 Safe checkpoint continuation (schema v34, 2026-10-09)

Commit `63b29bc` adds an immutable link from a new specialist task to the exact prior no-effect attempt and committed checkpoint.
One failed/stopped built-in task can create at most one fresh linked run, after the owner reviews the brief, constraints and bounded
assistant checkpoint and confirms. The store rechecks under its write transaction: no tool action or child run exists, there is no
newer run in that specialist chat or pending typed question, the coordinator chat is active, the Bot is unpaused, and its complete
model/instruction/tool/limit/runtime capability snapshot is unchanged. External runtimes, missing or oversized checkpoints, and
`outcome_unknown` remain blocked. The new conversation receives only the reviewed task brief/constraints and the committed
assistant response as explicitly untrusted progress. It carries no selected facts, previous tool results, old chat history,
credentials, approvals or receipts. The old worker is not resumed and no prior action is repeated. Idempotency returns the same new
task on exact retries; changed keys/payloads conflict. Additional model quota may be used.

The Store/API/schema-migration group passed **81 tests in 41.19s**. The responsive continuation, coordinator handoff and anonymous
workflow browser group passed **3 tests in 22.21s**; after shortening the public workflow copy, its focused anonymous-site rerun
passed **1 test in 2.74s**. Chromium **153.0.8010.12** / Playwright **1.63.0** covered app desktop **1440×960**, tablet
**900×1024**, phone **390×844**, and site desktop **1440×900**, tablet **900×1024**, phone **390×844**. I inspected the fresh-run
confirmation on phone and desktop, completed-task checkpoint status on phone, and shortened public workflow copy on phone and
desktop. All browser checks reported zero horizontal overflow and page errors; the anonymous site made no external requests.
Screenshots and traces are in `artifacts/safe-task-continuation/` and the refreshed `artifacts/workspace-task-dispatch/` captures.
`node --check`, Python compilation and `git diff --check` passed. Fixtures used local SQLite and a mock runtime only; no provider
call, physical phone or screen-reader check was made. This is no-effect retry support, not process restoration or general recovery.

## Purpose-derived naming quality follow-up

Commit `f23c2e5` improves the deterministic New Bot name suggestion: it keeps “follow-up” as a compound, shortens “tasks” to a
name-form “Task,” trims source/target clauses such as “from each meeting” and “into monthly folders,” and uses “Organizer” for
organize/organise/sort requests. Purpose updates still refresh both suggested fields only until the user edits them; names remain
reviewable, addresses stay stable after edits, and the local naming step makes no provider call or run.

The responsive naming journey first failed on the intended regression: “Follow Up Each Monitor” instead of the expected
“Follow-up Task Monitor.” After the fix it passed **1 test in 4.13s**; the public-workflow truth check passed **1 test in 2.96s**.
The new automatic suggestions were captured and inspected at desktop **1440×960**, tablet **900×1024** and phone **390×844**.
No overflow/page errors were reported; `node --check` and `git diff --check` passed. Evidence and updated source hashes are in
`artifacts/bot-naming/`. This remains a deterministic English-language naming heuristic; it is not model-generated semantic
understanding, and users review or edit the suggestion before creation.

## Coordinator task-brief refinement (2026-10-09)

Commit `8336335` gives the selected workspace coordinator scoped drafting guidance: preserve intent, organize only provided or
explicitly selected context, ask about material gaps, and never imply new authority. The review sheet keeps the source request linked,
lets the operator refine the goal and constraints or add an optional expected deliverable, shows the selected specialist's saved
settings, and requires an explicit send. The combined task brief is checked against its 20,000-character server boundary before the
request leaves the browser. No schema or hidden model call was added.

`tests/test_runtime_builtin.py::test_workspace_coordinator_gets_scoped_task_brief_guidance` passed; the focused
`tests/test_runtime_builtin.py tests/test_conversations.py` group passed **56 tests in 36.64s**. The responsive handoff journey passed
**1 test in 18.99s**, including over-limit rejection, original-request provenance, optional deliverable, selected facts, result return
and the bounded task timeline at **1440×960**, **900×1024**, and **390×844**. The anonymous workflow copy test passed **1 test in
2.73s** at **1440×900**, **900×1024**, and **390×844**; validation records zero external requests, browser errors or overflow. I
inspected the original-request/saved-settings and edited-task views at desktop/tablet/phone, plus the anonymous workflow card at the
same public-site sizes. Captures and trace are in `artifacts/workspace-task-dispatch/`. `node --check`, `git diff --check`, and
`impeccable detect --json src/hutch/server/static/app.js website/index.html` passed; the detector returned no findings. Tests use
mock/SQLite fixtures and do not verify live model draft quality, screen readers or physical devices. T-COORDINATOR-BRIEF is partial:
the prompt boundary and review UI work in fixtures, but live draft quality and end-to-end clarification remain unverified.

## S6 Optional same-chat context in Bot creation (2026-10-09)

Commit `382670d` extends chat-sourced Bot setup so the owner may select up to eight earlier user-authored messages from the same
conversation as saved background. Nothing is selected by default; assistant messages, other chats and unrelated same-chat turns
are never copied unless explicitly chosen. The final review shows each exact selected message and explains that it becomes part of
saved instructions and may be sent to the selected model on later runs. Selection does not grant tools, accounts or permissions.
The API checks exact conversation and role, rejects duplicates/cross-chat references and over-limit payloads, persists source ids
and provenance without repeating `original_request` in Bot API metadata, and treats a changed context selection under a reused
idempotency key as a conflict. The shared instructions cap remains 20,000 characters. Bot records are JSON-backed and the new
context-provenance list has an empty default for older records, so no SQLite schema migration was needed. The same change fixes
system-prompt formatting in route estimates when the selected Bot is the workspace coordinator.

`uv run pytest -q tests/test_api.py tests/test_usage.py` passed **53 tests in 12.34s**; the responsive context-selection browser
journey passed **1 test in 6.73s**; and the anonymous marketing check passed **1 test in 2.64s**. JavaScript syntax, Python
compilation and `git diff --check` passed. Chromium **153.0.8010.12** / Playwright **1.63.0** captured and I inspected desktop
**1440×960**, tablet **900×1024**, and phone **390×844**, including a scrolled phone review with the selected text above the fixed
footer. Marketing-card screenshots were inspected at desktop **1440×900**, tablet **900×1024**, and phone **390×844**; the
anonymous test recorded no external requests, page errors or horizontal overflow. Screens, trace and source hashes are under
`artifacts/bot-setup-context/`. No model/provider call, screen-reader session or physical phone was used. The latest exact-target
Impeccable scan reported three advisory radius-token mismatches and no side-tab anti-pattern. The path-scoped side-tab exception
records that the cited lines are a neutral full-outline blockquote and text alignment, not accent borders.

This advances but does not complete `owner-chat-bot-creation`: the owner can preserve selected existing context, but the wizard
still requires review of its full configuration and does not infer safe settings or ask conversationally only for unresolved
details. Implementation commit: `382670d`.

## S9 Reviewed browser form submissions (2026-10-09)

Implementation commit: `adbaaa6`.

Native HTML submit controls receive a one-time outward approval that names the destination origin, method, submit label and visible
field labels. A digest is computed in a Chromium isolated execution world over the current form state, including values,
checked/selected state, submitter value and form overrides. The digest and sanitized target summary leave that world; the digest is
process-keyed before persistence.
The worker recomputes the digest after approval and refuses detected changes before clicking. Sensitive values never enter Hutch's
approval, event or transcript records. Selected file uploads, oversized forms, and forms on pages without secure SubtleCrypto
support fail closed. Generic clicks and typing still require outward review. This is not an atomic transaction with a remote site
and does not recognize every JavaScript-specific submit action.

The initial regression test failed against the old behavior because the approval contained no native-form identity. The Chromium
fixture also replaces `crypto.subtle.digest` in the page's main world; the isolated review still detects a changed recipient. The
focused profile and real-browser tests passed **14 tests in 5.21s**, covering stable-submit, changed-recipient,
tampered-page-crypto, selected-file and insecure-page cases. The responsive approval UI test passed for desktop **1440×960**, tablet **900×1024** and phone **390×844** in Chromium
**153.0.8010.12** / Playwright **1.63.0**. I inspected the expanded review at all sizes and the phone decision view after scrolling; all automated
checks report zero page errors or horizontal overflow, and the phone's Allow button stays above the composer. Evidence and hashes
are under `docs/realignment/artifacts/browser-form-review/`. Node syntax, Python compilation and diff checks passed. No real site,
provider, account, human challenge, screen reader or physical device was used. This strengthens `SR-4`; it does not complete `UI-17`
or `UI-18` because credential-field heuristics, live handoff and third-party challenges remain unverified.

## Purpose-derived reminder, filing, and coordinator names (2026-10-09)

Implementation commit: `a43c4fa`.
Coordinator-name follow-up commit: `ff63a71`.

The local naming rule now recognizes reminder/alert requests, file/archive/categorize requests, and coordinator requests that refer to
Bots, agents or specialists. Reminder action and alert-condition phrasing is normalized into professional name nouns (for example,
“renew my passport” becomes “Passport Renewal Reminder” and “alert me when an invoice is overdue” becomes “Invoice Reminder”);
common time/status words are omitted, “receipts” becomes “receipt” in a filing role (“Expense Receipt Organizer”), and a Bot-team
request becomes “Workspace Coordinator.” Names and local addresses remain suggestions that owners can edit; setup still makes no
model/provider request and starts no run.

The regression journey first failed on the reminder request because it fell back to “Workspace Assistant,” on the alert condition
with “Workspace Reminder,” and on Bot coordination with the awkward “Across Bots Coordinator.” After the rule change,
`tests/e2e/test_browser.py::test_purpose_derived_bot_name_is_editable_and_reviewed_at_responsive_sizes` passed (**1 test in
6.56s**). Fresh Chromium captures at **1440×960**, **900×1024**, and **390×844** were inspected; the suggested names remain visible,
the address stays readable, and the dialog fits without horizontal overflow. Node syntax and the exact-target Impeccable scan passed.
No provider calls were made. This remains a small deterministic English-language naming vocabulary, not general semantic
understanding.


## S5 Experimental Outlook Mail search (schema v35, 2026-10-09)

Implementation commit: `1e6b73b`.

Outlook Mail is a separate local OAuth connection from Outlook Calendar. The owner explicitly
grants one mailbox to a Bot; only then is the read-only `outlook_mail_search` tool offered, and
the grant is checked again when the tool runs. Search returns at most ten message previews from
Microsoft Graph and escapes message content as untrusted text. It does not read attachments or
change, send, forward or delete mail. The connection notice says that search covers the connected
mailbox, including Deleted Items and Clutter, and that previews are sent to the selected model and
retained in conversation history. Disconnect removes Hutch's credential and Bot grants; Microsoft
consent revocation remains a separate Microsoft account action.

The focused regression command
`uv run pytest -q tests/test_outlook_mail.py tests/test_outlook_mail_api.py tests/test_outlook_calendar.py tests/test_outlook_calendar_api.py tests/test_migration.py`
passed **45 tests**. The fixture-only Outlook Mail journey passed at **1440×960**, **900×1024**
and **390×844**; the anonymous marketing workflow passed at **1440×900**, **900×1024** and
**390×844**. I inspected the responsive screenshots. The browser records show no external requests,
page errors or horizontal overflow; evidence is in `artifacts/outlook-mail/`. `node --check`,
`python -m compileall -q src/hutch`, `git diff --check` and the exact-target Impeccable scan passed.
The UI test uses a local Microsoft authorization interception and fixture Graph response. No live
Microsoft registration, user consent, mailbox, or Graph request was available, so this is an
experimental implementation and live-provider support remains unverified. Gmail remains unavailable
pending its restricted-scope verification path.


## Purpose-derived report names and conversational Bot requests (2026-10-09)

A test-first browser regression showed that “Create a weekly project status update for leadership” produced the generic “Workspace
Assistant.” The local naming rule now recognizes report/update/brief/summary creation verbs and suggests “Project Status Reporter”; it
also removes a leading conversational wrapper such as “I need a bot that…” before deriving the name. This remains a concise deterministic
English heuristic. It adds neither model inference nor permissions, and the user can edit the proposed display name and address.

`uv run pytest -q tests/e2e/test_browser.py::test_purpose_derived_bot_name_is_editable_and_reviewed_at_responsive_sizes -x` first failed on the
fallback assertion, then passed **1 test in 6.68s** after the change. Chromium **153.0.8010.12** / Playwright **1.63.0** checked desktop
**1440×960**, tablet **900×1024** and phone **390×844**; I inspected the suggested names and a phone screenshot with the address field
scrolled above the sticky footer. The journey confirmed no model/provider request and no run on creation. `node --check` and
`git diff --check` passed. Evidence and source hashes are in `artifacts/bot-naming-quality/`. This does not provide general semantic
understanding or non-English naming.


## S5 Gmail unavailable-state disclosure (2026-10-09)

Hutch's Connections page now explicitly states that Gmail is unavailable and that there is no Gmail OAuth route or requested scope.
The notice explains why: message search would need `gmail.readonly`, which Google classifies as restricted; public apps require the
applicable scope verification, and restricted data accessed from or through a third-party server triggers Google's security-assessment
requirement. It clarifies that Google Calendar consent does not grant Gmail access, links to Google's scope table, and offers no inert
Connect button. The marketing site continues to label Gmail unavailable pending scope verification. This is a truthful support boundary,
not Gmail integration implementation.

Test-first: `tests/e2e/test_browser.py::test_gmail_unavailability_is_explicit_and_has_no_dead_connect_control` first failed because the
Connections page had no Gmail status. After adding the informational card, the fixture-only test passed at desktop **1440×960**, tablet
**900×1024** and phone **390×844**, with no external requests, page errors or horizontal overflow. Captures and source hashes are in
`artifacts/gmail-availability/`; no client ID, Google account, scope request, or live provider call was used. Research checked Google's
[Gmail scope table](https://developers.google.com/workspace/gmail/api/auth/scopes) and
[restricted-scope verification rules](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification).


## S7 Late browser human checkpoints (2026-10-09)

Implementation commit: `5cdd65f`.

The browser tool now checks for CAPTCHA, login, identity, and 2FA markers before page actions and after navigation, waits, clicks, and
text entry. When a check appears in the same live page, local handoff pauses until explicit human resume; Hutch reinspects that page
without reloading it. If a click or text entry already ran before the challenge was detected, the error tells the operator that it
happened and warns against retrying blindly. The existing sensitive-field guard still blocks agent entry and screenshots.

Before the fix, a local Playwright case let the tool read a page after a human-check marker was present without pausing. The updated
Chromium fixture makes the marker appear asynchronously during a wait, verifies that the same JavaScript page state survives two human
resumes, and then confirms that the cleared page can be read. The focused browser/profile/form suite passed **17 tests in 7.62s**;
`python -m compileall -q src/hutch`, `node --check src/hutch/server/static/app.js`, and `git diff --check` passed. No UI source changed,
so this backend guard required no new screenshots. The challenge and human responses are fixture-controlled: no real account, live
third-party challenge, headed desktop, physical phone, or screen reader was tested. UI-18 remains partial until those support limits
are exercised and the wider handoff release gate passes.


## S9 User-facing no-mock and provider sign-in audit (2026-10-09)

The production path still has no `MockRuntime` or public demo seeder. Test-only `TestScenarioRuntime` remains under
`tests/support/` and is excluded from packaged wheels. Retired `mock/*` routes fail before any tool starts, while the model picker
labels old records for repair. Legacy Pi/OpenCode runtime records display an explicit unavailable state and an actionable switch to
Hutch's governed runtime; Hutch does not import another application's private auth files. The anonymous marketing page has no fake
approval controls and identifies OpenCode/Pi harnesses as unavailable.

The official OpenCode account flow was rechecked: OpenCode Go requires the user to sign in on OpenCode, subscribe if needed, create
an API key, and copy it into the application. That is not OAuth session sharing. Hutch's existing OpenCode Go connection is the
provider-issued key route; the separate ChatGPT sign-in remains an opt-in preview with eligibility caveats. See the official
[OpenCode Go setup](https://docs.opencode.ai/docs/go/) and [provider connection guide](https://opencode.ai/v2/docs/providers/).

The focused runtime/CLI/mock-picker/legacy-runtime-recovery/anonymous-site check passed **13 tests in 12.93s**. It confirmed the
retired route is unavailable, the demo command is absent, the no-mock marketing copy is intact, the old-runtime recovery action
works in a fixture, and a built-in local model path completes through the fake provider harness. This does not verify a real local
model or provider account. The separate OpenCode/Pi execution adapters remain deliberately unavailable until permission, sandbox,
budget and recovery guarantees are enforced.


## Bot display-name browser journey selectors (2026-10-09)

Test-alignment commit: `47e5f38`.

A full `tests/e2e/test_browser.py` run after purpose-derived display names were introduced completed with **89 passed, 13 failed,
5 errors**. The failing UI journeys had not followed the product's human-facing identity contract: they expected slug text such as
`workspace-helper settings`, `draft-a`, and `local-handoff settings`, even though the UI correctly presents “Workspace Helper,”
“Draft A,” and “Local Handoff.” The Outlook Calendar test also selected both the Calendar and Mail card because those surfaces share
a styling class. Test selectors now use the human-facing names and Outlook Calendar's explicit accessible region.

Reran the previously affected Outlook Calendar, small-workspace navigation, four workspace-mode sizes, three browser-handoff setting
sizes, Bot/conversation draft switching, and three resource-replay sizes: **13 passed in 80.36s**. No account/provider call was made.
This focused recovery confirms the affected cases; the full browser file still needs a rerun before the browser-suite gate can pass.


## S7 Sensitive browser fields revealed during a run (2026-10-09)

Implementation commit: `7b5f42e`.

The browser tool previously checked sensitive fields at navigation and blocked agent typing into fields already present, but could
continue after a page revealed a password field in response to a click or delayed transition. It now compares visible sensitive-field
state around clicks, text entry, and waits. When one appears, Hutch pauses in that bot's live browser for the person to complete it;
the action result records that the triggering action already happened and warns against blindly retrying. A text value used before a
new field appeared is not echoed in the result. The tool still cannot recognize every custom-rendered credential widget.

Before the fix, `uv run pytest -q tests/e2e/test_browser.py::test_browser_hands_off_when_a_click_reveals_a_sensitive_field --no-header`
failed because no handoff occurred. The focused click, wait, text-entry, asynchronous human-challenge, and existing sensitive-input
tests now pass: **5 passed in 3.72s** using local Chromium **153.0.8010.12** / Playwright **1.63.0**. `python -m compileall -q
src/hutch` and `git diff --check` passed. No site, provider, account, or secret was used. This validates fixture behavior only; live
third-party forms and nonstandard credential widgets remain unverified.


## S9 Browser-suite follow-up: provider disclosure state (2026-10-09)

Implementation commit: `f8c71f0`.

The next full browser-file run passed **101 tests** and exposed one remaining failure in Outlook Calendar. The access grant was
persisted, but `renderConnections()` replaced the page contents and collapsed the currently open details panel, hiding the newly
granted calendar from the operator. Connections now preserves the expanded Outlook Calendar and Outlook Mail access panels when
refreshing provider state. The E2E test scopes the calendar region by its accessible label and ensures the disclosure is open before
checking the persisted grant. `uv run pytest -q tests/e2e/test_browser.py::test_outlook_calendar_uses_account_consent_and_one_bot_grant_at_all_viewports --no-header`
then passed **1 test in 2.35s**; `node --check src/hutch/server/static/app.js` and `git diff --check` passed.

The full browser suite was not repeated after this targeted fix; the prior run had 101 passes and this final focused rerun covers its
sole failing journey. The journey uses local account/calendar fixtures and intercepted sign-in, with no Microsoft account, consent,
or live Graph request.


## Final browser-file pass after naming and provider UI alignment (2026-10-09)

Follow-up commits: `47e5f38` (human-facing display-name selectors), `f8c71f0` (preserve expanded Outlook Calendar/Mail access panels),
`2675934` (Mail grant visibility), and `4b0dc81` (wait for the new grant toast among stacked notices).

The 102-case `tests/e2e/test_browser.py` suite now passes cleanly: **102 passed in 263.26s**, with no failures or teardown errors.
It exercises the professional purpose-derived Bot naming flow, all directly affected responsive settings and replay cases, the full
Outlook Calendar/Mail account grant journeys, dynamic sensitive-field handoffs, and other local-fixture browser acceptance journeys.
The final run refreshed the tracked responsive screenshots, traces and JSON/source-hash records under `artifacts/`; the naming,
calendar and mail captures were inspected at desktop, tablet and phone sizes. `node --check src/hutch/server/static/app.js`,
`python -m compileall -q src/hutch` and `git diff --check` passed in the associated focused slices. No live provider credentials,
account consent, paid call, or external request was used. This is not the entire Python test suite, the anonymous marketing site suite,
or the final performance gate.

## Use Bot display names throughout provider access (2026-10-09)

The Connections page now resolves each provider grant's stable Bot ID against the current Bot list and displays the editable human-facing
name in Google Calendar, Outlook Calendar and Outlook Mail selectors, grant rows, orphan-grant rows, and replace/revoke/disconnect
confirmations. Internal addresses remain unchanged for API targeting. The provider browser journeys assert that a display name is shown
where access is selected and summarized, and that its machine address is absent from the saved grant summary; the Outlook Mail journey
also checks the disconnect confirmation. The focused command
`uv run pytest -q tests/e2e/test_browser.py -k 'google_calendar_read_grant_is_clear_at_desktop_tablet_and_phone or outlook_calendar_uses_account_consent_and_one_bot_grant_at_all_viewports or outlook_mail_grant_and_consent_boundary_fit_all_viewports' --no-header`
passed **3 tests, 99 deselected, in 6.15s** on Chromium **153.0.8010.12**. `node --check src/hutch/server/static/app.js` and
`git diff --check` passed. No provider credentials, consent, or external requests were used. Updated responsive captures and source hashes
are under [`artifacts/google-calendar/`](artifacts/google-calendar/), [`artifacts/outlook-calendar/`](artifacts/outlook-calendar/), and
[`artifacts/outlook-mail/`](artifacts/outlook-mail/).

## Run-detail transcript verification (2026-10-09)

The run detail now calls the real `/api/v1/tasks/runs/{id}/verify` endpoint and reports the number of chained events checked,
older unhashed events as partial verification, or the first detected mismatch as an alert. The check is read-only. A responsive browser
journey verifies an intact stored chain at desktop, tablet and phone sizes, modifies a committed event payload in its isolated test
database, then confirms that the page identifies event 1 as tampered. Its fixture run is terminal so the live test supervisor cannot
start execution while the history is inspected; no model/provider request occurs. The new `hutch runs verify <run-id>` command reports
the same verified, partial-legacy, or tampered result, exits with status 1 for a mismatch, and closes its store cleanly. Historic rows
without hashes remain explicitly unverified; SR-11 now has both CLI and UI audit surfaces.

`node --check src/hutch/server/static/app.js`, `git diff --check`, and
`.venv/bin/pytest -q tests/test_store_events.py tests/test_cli.py::test_runs_verify_reports_intact_legacy_and_tampered_event_history tests/e2e/test_browser.py::test_run_detail_reports_transcript_chain_verification_and_tampering --no-header`
passed (**18 tests in 4.44s** on Chromium **153.0.8010.12**). Inspected desktop **1440×960**, tablet **900×1024**, and phone
**390×844** captures showed no horizontal overflow; the event-verification controls stack on compact layouts. Tamper alert, screenshots,
Playwright trace, request/result metadata and source hashes are recorded in [`artifacts/transcript-integrity/`](artifacts/transcript-integrity/).
The complete CLI and store-event suites also passed **29 tests in 7.85s** with thread/syntax warnings treated as errors.

## Bot display name in message replies (2026-10-09)

The message-reference composer now identifies the Bot by its editable human-facing display name while retaining the internal address
for routing. A test-first browser regression used `Project Delivery Partner` as the display name and `reply-fixture` as the address;
the prior UI exposed the latter. The fixed reply journey passed at desktop, tablet and phone sizes (**3 passed in 5.01s**) on
Chromium **153.0.8010.12** / Playwright **1.63.0**. I inspected the refreshed preview captures: the display name is readable at all
three widths, the source excerpt and remove control remain visible, and no horizontal overflow or page errors occurred. `node --check`
and `git diff --check` passed. Evidence and traces are in [`artifacts/message-replies/`](artifacts/message-replies/). This used only a
synthetic local conversation; no model/provider request, screen reader or physical device was used.

## Gmail search private preview (2026-10-09)

Implementation commit: `502eabf`.

Connections now offers a clearly labelled, owner-configured Gmail search preview. It requests Google's restricted,
account-wide `gmail.readonly` scope through a local installed-app PKCE flow and Linux Secret Service. Search is limited to
ten results with sender, subject, received date, and a bounded provider snippet. No send or mailbox-write tool exists.
Only built-in Bots whose primary, fallback, and escalation routes remain loopback Local can receive a grant; the route is
checked again when the tool registry is built and immediately before a search. The local model service itself is outside
Hutch's verification boundary. Public availability remains blocked on Google's applicable scope verification and any
required security assessment. See [connections.md](../connections.md) for owner setup and the linked Google requirements.

The focused command `.venv/bin/pytest -q tests/test_google_calendar.py tests/test_google_mail.py tests/test_google_mail_api.py tests/e2e/test_browser.py::test_gmail_preview_discloses_restricted_scope_and_requires_local_setup tests/e2e/test_browser.py::test_gmail_local_grant_and_oauth_flow_at_desktop_tablet_and_phone tests/e2e/test_website.py::test_provider_availability_is_readable_without_horizontal_page_scroll tests/e2e/test_website.py::test_outlook_calendar_and_mail_support_row_is_truthful_and_reachable_at_all_viewports --no-header`
passed **29 tests in 8.67s**. The browser fixtures verified the fixed Google authorization origin/path, opener isolation, local-only Bot grant, hybrid-Bot exclusion, no external requests, and desktop/tablet/phone layouts. The anonymous marketing captures confirm the same release boundary; I inspected the final phone table and viewport screenshots. `node --check src/hutch/server/static/app.js` and `git diff --check` passed. Captures, trace and validation records are in [`artifacts/google-mail/`](artifacts/google-mail/).

This evidence is fixture-only. No Google account, consent, OAuth client, live Gmail API request, or secret was used. Google currently documents `gmail.readonly` as restricted, applies testing-user/authorization limits to projects in Testing, and requires verification for public use; applicable restricted-data access may also require a third-party security assessment. See [Gmail API scopes](https://developers.google.com/workspace/gmail/api/auth/scopes), [restricted-scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification), and [OAuth audience/testing limits](https://support.google.com/cloud/answer/15549945?hl=en). These constraints are not prevalence claims and do not establish public approval.

## S6 exact-message Bot setup from Studio chat (2026-10-09)

Implementation commit: `7ec16b8`.

Every user-authored request in the current Studio conversation now offers **Make a bot**. It opens the existing
four-step, user-reviewed Bot setup with that exact request as its source. The top-bar New action continues to use the
latest request. Only earlier user messages can be separately selected as saved background; later messages, assistant
replies and other conversations are excluded. The server still checks the source message's conversation and role on
creation, and the user must review/confirm before any Bot is saved. Suggested professional display name/address stay
editable and locally derived. This action does not perform natural-language prompt rewriting, create a run, or grant
permissions; request refinement and asking follow-up questions remain open.

The focused browser and anonymous marketing batch passed **5 tests in 13.44s** on Chromium **153.0.8010.12** /
Playwright **1.63.0**. It checked keyboard activation, exact-source provenance, later-message exclusion, no Bot/run
creation, a 44px touch target under coarse-pointer emulation, no page errors/external requests, and no horizontal
overflow at desktop, tablet and phone widths. I inspected the actual app and website screenshots at each size. Captures,
trace and source hashes are in `artifacts/bot-from-message/`; no real model/provider call, physical phone, or
screen-reader session was used. `node --check` and `git diff --check` passed.

The newly surfaced side-tab report is stale: those accents were already removed by `654ca75` and `8052655`, and the
current stylesheet lines in the report are not one-sided borders. The current detector reports no side-tab finding.

## Offline regression gate after schema v36 (2026-10-09)

Commit `1703434` removes two brittle exact-current-schema assertions from historical migration tests. The
Outlook Mail grant test now requires schema v35 or newer, and the reply-reference test requires v26 or newer;
both still execute and assert the specific migration behavior. The complete offline suite then passed **1,456
tests in 303.37s** with unhandled thread exceptions and syntax warnings treated as errors. The first run had
only these two stale assertions failing against current schema v36; the rerun was fully green. Browser/live
provider/performance release gates are not implied by this offline result.

## S6 coordinator-assisted Bot-purpose refinement (2026-10-09)

Implementation commit: `ec7ccf1`.

New Bot setup can request an optional purpose refinement from the built-in workspace coordinator. Each request returns one draft;
the owner can edit the purpose and request another. The server accepts only the exact source user message, the current editable
purpose, and up to eight explicitly selected earlier user messages from that same chat. It excludes later messages, assistant
replies and all other chat history. Source values are encoded as bounded untrusted data; if safe encoding exceeds the 24,000
character window, the request receives an actionable `422` before run admission. Idempotent retry is exact-payload-bound and
changed content conflicts.

The refinement is a normal admitted conversation run, using the coordinator's saved route and configured fallback under normal
usage reservations. Run-level `tool_access=none` selects the built-in runtime with an empty tool registry, disables saved Bot
memory/browser/shell capabilities in its snapshot, rejects any returned tool calls without execution, and fails on truncation
rather than escalating or dropping context. Its system guidance forbids answering or carrying out the underlying request. The
model's text remains a suggestion in a separate editor; the original purpose and inferred professional name stay unchanged until
the owner applies the result, after which the local name suggestion updates from the revised purpose. Bot settings review and
creation remain separate, and draft generation does not grant authority or start a new Bot.

`tests/test_conversations.py tests/test_runtime_builtin.py` passed **58 tests in 38.16s**, including selected-context boundaries,
idempotent replay/conflict, oversized escaped payload rejection, empty tools, and a malicious provider tool-call attempt with no
file effect. Responsive application validation passed **1 test in 3.69s**; anonymous marketing copy validation passed **2 tests
in 4.47s** on Chromium **153.0.8010.12** / Playwright **1.63.0**. The app was captured and inspected at desktop **1440×960**,
tablet **900×1024**, and phone **390×844**, both before application and after applying on phone. The marketing site was captured
and inspected at desktop **1440×900**, tablet **900×1024**, and phone **390×844**; there were no horizontal overflows, page errors,
or external requests. Evidence is under [`artifacts/bot-purpose-refinement/`](artifacts/bot-purpose-refinement/).

No live model/provider call, provider retention behavior, screen reader or physical phone was tested. Multi-round clarification
is not implemented: answers to open questions must be added to the editable purpose and submitted in a new explicit request.
Naming remains a local deterministic suggestion rather than model-generated, and live semantic quality remains unverified.

## ChatGPT background plan consent (2026-10-09)

Implementation commit: `a91aebf`.

OpenAI's current [SIWC terms](https://openai.com/policies/sign-in-with-chatgpt-terms/) require express consent before an
automation or background process uses a connected plan and require requests to originate from a user-controlled runtime.
Hutch now records an explicit permission per Bot and connected ChatGPT account. It binds to the Bot's current model,
fallback, escalation, inference mode, runtime and endpoint configuration. Any route change makes the grant stale. The
runtime re-reads the current Bot record before each provider request, so revoking consent prevents later requests even if a
run began while consent was active; an in-flight request may finish. Disconnecting or removing the ChatGPT connection
removes its grants. Direct messages retain their existing per-request authorization. No ChatGPT connection is silently
selected as a paid fallback.

The API uses an expected-route fingerprint for compare-and-swap, returns only safe consent state, and excludes stored
consent records from ordinary Bot resources and resynchronization snapshots. A grant is not shared across accounts. The
current preview's output-token ceiling remains unenforced by OpenAI; local usage remains an estimate. Eligibility and live
account support have not been verified.

The focused contract batch passed **13 tests in 2.82s**, covering scheduled/specialist denials, fallback denial, account
binding, route-change invalidation, disconnect races, per-request revocation observation, and snapshot redaction. The local
synthetic-account browser pair passed **2 tests in 10.39s**; anonymous marketing copy passed **2 tests in 4.20s**. Desktop,
tablet and phone captures were opened and inspected; keyboard trap/return focus, overflow, no provider requests and no
external requests were checked. See [`visual-validation.md`](visual-validation.md#chatgpt-background-use-permission-2026-10-09).

The first broad run after this slice reported **1,606 passed and one failed** because a legacy executor-recovery browser
test still expected the text `hutch doctor` after the fixture had verified isolation successfully. The stale assertion was
changed to check the verified state, and that browser test passed by itself (**1 test in 8.60s**). This full-suite result is
not green; rerun the full suite after later slices and before integration.

## Bot identity and Fleet visual recheck (2026-10-09)

CSS cleanup, documentation and evidence commit: `93b744e`.

The owner asked for automatic, more human and professional Bot names. The current flow is already automatic: it derives a concise
professional role name and editable stable address from the user's stated purpose, refreshes both while they remain untouched,
and keeps the human-facing label separate from the stable local Bot address. I retained work-descriptive titles rather than inventing a personal identity;
that keeps the bot's role obvious in the roster, approvals and message references. The rule runs locally without model usage, and
the owner can edit either value. A fresh browser journey with the prefix “I need a bot that…” passed (**1 test in 6.07s**) at
desktop, tablet and phone sizes. I inspected the screenshots; see [`visual-validation.md`](visual-validation.md#professional-names-and-fleet-state-labels-2026-10-09).

The two running/paused side accents in the legacy Bot-card CSS were removed. The active Fleet already states each condition in a
text chip, so the decoration carried no extra information. Its synthetic queue-failure browser check passed at desktop and phone
(**2 tests in 2.30s**), and I inspected both captures for readable status labels, unobscured content and overflow. The old
`/bots` server route redirects to the Fleet; this cleanup does not change the live SPA or state semantics.

For OpenCode, the current v2.0.24 CLI exposes `auth login`, which can store provider credentials in OpenCode's private auth
store, but Hutch does not import that file or reuse the CLI session. The supported OpenCode Go path is the vendor-documented
Console sign-in followed by copying a provider-issued API key into Hutch's scoped connection; it is clearly labelled key-based,
not OAuth token sharing. ChatGPT has a separate supported Sign in with ChatGPT preview path in Hutch. OpenCode Go's current
official instructions confirm the Console/key flow: [OpenCode Go](https://docs.opencode.ai/docs/go/) and
[provider setup](https://docs.opencode.ai/docs/providers/). These are provider-account setup flows; OpenCode/Pi execution
adapters remain unavailable until permission, process, budget and recovery contracts pass.

After the latest marketing-copy edit, the anonymous Plans & keys and expanded FAQ browser check passed **1 test in 2.76s** at
desktop, tablet and phone widths. I inspected the refreshed phone captures; no page error, overflow or external request occurred.

## Friendly purpose-derived Bot names (2026-10-09)

The owner asked for automatic Bot names that feel more human and professional. Guided setup now pairs a deterministic friendly
teammate name with the role derived from the request; the separate local address remains role-based. An existing teammate identity
is skipped when a name is reused, both fields stay editable, and the chat header presents the generated human-facing name alongside
“AI bot · [role]” at desktop, tablet and phone sizes. Naming stays local and starts no run. The naming form, contract, test matrix,
anonymous marketing copy, and OpenBot reference review now document this behavior. Current OpenBot docs model profile name/title/role
separately and treat capabilities as separately governed; this was used as a design reference only, with no OpenBot code or live
service run. The supplied video still could not be played in the browser and was not treated as evidence.

`uv run pytest -q tests/e2e/test_browser.py::test_purpose_derived_bot_name_is_editable_and_reviewed_at_responsive_sizes tests/e2e/test_website.py::test_public_workflow_describes_named_recurring_tasks --no-header` passed **2 tests in 9.56s** on Chromium **153.0.8010.12** / Playwright **1.63.0**. The browser test checked that a roster collision gets a different name, the role-based address remains stable, name edits persist, and no model request/run occurs. I inspected generated chat labels and the creation review at desktop/tablet/phone and the anonymous site workflow at those site sizes. No overflow, browser error or external website request occurred. Fixtures only: no real provider, OpenBot account or physical device. See [`visual-validation.md`](visual-validation.md#friendly-bot-names-with-visible-roles-2026-10-09) and the named evidence directories there.

`tests/test_api.py::test_bot_display_name_is_durable_editable_and_keeps_legacy_address` and
`tests/test_cli.py::test_bot_create_and_validation` passed (**2 tests in 0.81s**). The exact-chat-request Bot-setup journey also
passed (**1 test in 5.56s**) after replacing its fixed 300 ms check with a condition-based wait for the wizard heading; the
previous assertion ran before setup finished its local requests. The responsive coordinator direct-chat journey passed separately
in the paired check (**1 test in 5.14s**). These are local browser/store fixtures and use no model inference.

Naming implementation, documentation and inspected desktop/tablet/phone evidence were committed as `9a186ff`.

## Dashboard notices and marketing workflow polish (2026-10-09)

The owner-approved dashboard polish removes the success/error side rails from the legacy Connections banners. A neutral full border
keeps the panel boundary quiet; the existing check and alert icons retain their semantic color, while their visible text and
`role=status` / `role=alert` announcements remain unchanged. The responsive browser test injects visual-only banner fixtures and
checks border widths/colors, icon distinction, semantics and overflow. In the marketing workflow, I shortened the setup and review
copy without removing selected-message provenance, the review-before-create boundary, approval separation, checkpoint conditions,
uncertain-effect handling, or provider-retention and cross-Bot context limits. The public skip link now animates with `transform`
and has a keyboard path that reveals it before activating `#main`.

The focused responsive browser/site run passed **4 tests in 8.75s**, followed by a final refreshed dashboard capture pass (**1 test
in 4.25s**) on Chromium **153.0.8010.12** / Playwright **1.63.0**. Desktop, tablet and phone screenshots were inspected; there were
no page errors or horizontal overflow, and the anonymous site made no external requests. Current Impeccable exceptions are narrow
and already recorded in `.impeccable/config.json`: website padding/contrast/layout-transition checks are static-scanner false
positives confirmed against rendered captures, the template line-height rule cannot follow its linked stylesheet (browser values
show 1.6 body leading), and `side-tab` reports in `style.css` point to a code-block reset and a text-only checkpoint state label.
The manual target scan found no side-tab pattern. No new ignore was added. See `visual-validation.md` and
[`artifacts/dashboard-polish/`](artifacts/dashboard-polish/) / [`artifacts/bot-purpose-refinement/marketing/`](artifacts/bot-purpose-refinement/marketing/).

The last public-copy revision also retained route/fallback boundaries and the exact safe-checkpoint eligibility conditions; its two
anonymous-site tests passed again (**2 tests in 4.27s**) and the refreshed desktop/tablet/phone captures were inspected.
Dashboard/site polish and responsive evidence were committed as `9084d71`.

## Remove unreserved chat requests from connection diagnostics (2026-10-09)

The legacy `hutch connections test --chat <model>` option issued a paid model request directly from the connection helper, outside
the normal shared-account token/currency reservation and uncertain-charge receipt path. A test-first fake-endpoint reproduction
confirmed the command returned success; source inspection showed it went straight to `provider.chat` without a reservation. The CLI now keeps a hidden compatibility argument only to
  return a clear refusal before network access. The check helper no longer accepts a model-chat parameter or reports untracked
`spent_tokens`; model-list authentication stays token-free, and endpoints without a model list clearly remain unverified. The docs
and ADR-0005 now direct model behavior checks through a normal Bot run and reserve future persisted capability probes for the
governed request and reconciliation path. The code, docs and regression coverage were committed as `653c20e`.

`uv run pytest -q tests/test_connections.py tests/test_compat.py tests/test_provider_authority.py tests/test_reservations.py --no-header`
passed **84 tests in 18.36s**. The additional focused CLI/diagnostic check passed **3 tests in 1.52s**. All requests used local
fixtures; no provider credential, live model or paid request was used. No visual change was made.

## External executor gate rechecked (2026-10-09)

Reviewed the installed OpenCode CLI (`v2.0.24`) and current official OpenCode/Pi protocol and security documentation before
considering S5 adapter work. OpenCode's installed API fixture still marks the server event stream experimental and volatile; its
permission schema includes persistent `always`, while Hutch maps only a single reviewed action to `once` or `reject`. The runtime
remains unavailable. Official Pi CLI documentation confirms `--no-tools` can disable built-in, extension, custom and MCP tools,
but Pi would still own the direct model request and credentials. Its security guidance says project trust is not a sandbox, and
headless RPC cannot show interactive trust prompts. There is no Pi binary installed here. These checks do not authorize enabling
either executor; both still need Hutch-owned provider routing/usage reservations and governed recovery.
This research, compatibility update and fail-closed test are committed as `4ddcef0`.

Added a regression guard proving that both executor entry points fail as `unsupported` before `subprocess.Popen` can run and return
the permission/capability and provider-budget limitation. `uv run pytest -q tests/test_runtime.py::test_external_executor_refuses_before_creating_a_process tests/test_runtime_opencode.py tests/test_runtime_pi.py --no-header`
passed **17 tests in 0.26s**. Protocol tests are offline fixtures; no provider request or model call occurred. See the updated
[provider compatibility matrix](provider-compatibility.md) and [`tests.md`](tests.md). The expanded adapter/runtime/matrix batch
also passed **33 tests in 0.89s**; this remains fixture coverage, not a live Pi or provider check.

## Passive per-model tool-call evidence (schema v37, 2026-10-09)

The provider matrix previously knew whether a route spoke the expected protocol, but not whether one configured model could
return a usable function call. Rather than send an additional capability probe outside the normal budget path, Hutch now
records the first positive, declared, argument-valid tool call observed during a live fenced Bot run. The write happens only
after `finish_step` settles or retains Hutch's shared-account reservation as uncertain and before the tool can execute. The
immutable row stores the run, provider route/account, model, route identity hash, safe tool name and timestamp, never prompt text,
tool arguments, credentials or response content. Duplicate observations for the same exact route revision are ignored. Invalid,
unknown, tool-free draft and unreserved calls do not create evidence. A route change produces a different revision and no
capability is inferred for it. The record is still only a past response, not a future guarantee; absent evidence is unknown.
`GET /api/v1/model-capabilities` provides typed keyset pagination capped at 100 rows. Connections now shows up to five newest records,
using descending ID cursors, and explicitly separates observed, unknown, and history-unavailable states. Naming setup copy calls the
generated role/name pair a suggested Bot label, says both values are editable, and preserves the AI Bot label elsewhere. This private
operational evidence does not change marketing claims. Provider/model evidence remains fixture-only.

The first full-suite run exposed that built-in route identity omitted the effective `OLLAMA_HOST` override. That made production
route pinning reject local Ollama connections despite their configured host. `_route_identity` now includes that effective
endpoint; focused model-switcher, rehearsal, risk-policy and workspace tests pass. Final checks: the focused migration/runtime/API
suite passed **183 tests in 62.39s**; the complete non-browser suite with thread-exception and syntax warnings promoted to errors
passed **1,471 tests, 2 skipped, in 276.71s**. Python compilation and `git diff --check` passed. No live provider, paid call or
visual UI change occurred.

## Connections capability evidence and naming clarity (2026-10-09)

Connections now displays the five newest immutable model tool-call observations with provider/model, safe tool name, time and a
short route-revision fingerprint. It does not display account identifiers. Copy explains that a record applies only to that exact
route revision and is evidence from a past response, not a guarantee. An empty page means unknown; a failed evidence request is
shown separately and does not block connection management. Descending keyset pagination uses the exclusive `after_id` cursor to
continue toward older records while ascending pagination remains compatible.

The setup wizard already derives an editable professional role and human-friendly name locally from the user's stated request. Its
copy now calls the result a suggested Bot name, clarifies that the role and label can be changed, and retains the visible AI Bot label
in chat and lists. The naming generator remains deterministic, deduplicates current roster names and makes no model call.

The API pagination regression and four-state browser journey were added; the latter captures loading, empty, unavailable and populated
evidence at 1440×960, 900×1024, 390×844 and 320×740. It also checks nested/page overflow, page errors, and absence of external
requests, using a synthetic API response only. Captures and validation metadata are in [`artifacts/model-capabilities/`](artifacts/model-capabilities/).
The exact focused run `node --check src/hutch/server/static/app.js && uv run pytest -q tests/test_api.py::test_versioned_connections_schedules_and_capabilities_are_typed_and_secret_free tests/e2e/test_browser.py::test_model_capability_observations_show_unknown_and_latest_evidence tests/e2e/test_browser.py::test_provider_connections_fit_phone_viewports_and_capture_signin_states tests/e2e/test_browser.py::test_purpose_derived_bot_name_is_editable_and_reviewed_at_responsive_sizes --no-header`
passed **4 tests in 10.95s** on Chromium **153.0.8010.12**; `git diff --check` passed. I inspected the loading, empty, unavailable,
and observed card captures on representative desktop, tablet, phone and compact-phone views. No provider credentials or live model call
were used. The side-tab detector report on `style.css` was a false positive: its two
referenced selectors are a padded code block and uniformly outlined checkpoint rows. A file-scoped `side-tab` value ignore was
already present in shared Impeccable configuration and was retained after a direct detector scan returned no such issue; other
detector rules remain enabled for the stylesheet.

## Account integration support matrix and API contract correction (2026-10-09)

The current provider compatibility guide now has a separate account-integration matrix for Google Calendar, Gmail, Outlook Calendar,
and Outlook Mail. It distinguishes experimental fixture-tested behavior from live account/consent verification, records the exact
OAuth scope and per-Bot grant boundary, and explains what account data reaches the selected model and run history. It calls out the
public-release restriction for Gmail's account-wide `gmail.readonly` scope and its built-in, loopback-Local-only model route gate.
The API contract now includes Google Calendar and Gmail resources, lists the passive model-capability and workspace-default routes,
and no longer says capability evidence is unavailable. General workspace filesystem management is still not a v1 API.

Official Google scope and restricted-data policies and Microsoft Graph delegated permission descriptions were checked on 2026-10-09.
The focused account/API contract run
`uv run pytest -q tests/test_google_calendar.py tests/test_google_mail.py tests/test_google_mail_api.py tests/test_outlook_calendar.py tests/test_outlook_calendar_api.py tests/test_outlook_mail.py tests/test_outlook_mail_api.py tests/test_compat.py tests/test_api.py::test_versioned_connections_schedules_and_capabilities_are_typed_and_secret_free --no-header`
passed **60 tests in 4.31s**. `git diff --check` passed. These are local HTTP/OAuth fixtures; no account, consent, provider request,
new screenshot, or visual UI change was involved. Prior inspected desktop/tablet/phone connection captures remain in the named
Google Calendar, Gmail, Outlook Calendar and Outlook Mail artifact directories.

## Explicit Bot-to-Bot reference grants (schema v38, 2026-10-09)

One Bot owner can grant an exact current, reviewed fact snapshot to one named memory-enabled recipient. The API is typed and
idempotent; incoming/outgoing pages are bounded and report a next offset only when another row exists. Runtime recall exposes
provenance as untrusted reference data and never adds tools, credentials, accounts, workspace files or other chats. Either Bot can
revoke, source revisions/archive and disabled memory stop retrieval, and the content-free invalidation includes participant IDs
only. A held SQLite backup/restore test confirms the grant survives for operator review. The public workflow copy explains the
scope and revocation.

The focused implementation batch passed **68 tests in 10.99s**. It includes schema/migration, API, pagination, cross-connection
restart, runtime recall, held restore and responsive Chromium review/revoke. `node --check`, Python compilation and
`git diff --check` passed. After visually reviewing the marketing cards at **1440×900**, **900×1024** and **390×844**, I fixed
paragraph stretching that left large gaps; the refreshed anonymous-site test then passed **1 test in 2.78s**. Captures are in
[`artifacts/fact-sharing/`](artifacts/fact-sharing/) and [`artifacts/bot-purpose-refinement/marketing/`](artifacts/bot-purpose-refinement/marketing/).
No live provider, personal account or external request was used. The implementation checkpoint is `433981e`; this ledger entry
documents its verification boundary and visual evidence.

## Full offline regression checkpoint (2026-10-09)

The first suite run after schema v38 found three failures in the v21-v23 migration tests. Their helper lowered `user_version`
after opening a current database but did not remove the v38 `memory_fact_shares` table, so those cases did not model a database
from the claimed historical schema. The helper now removes that later table before replaying migrations. All three legacy
migration cases passed, and `tests/test_delegation.py` passed **29 tests, 1 skipped**. The complete non-browser suite with
unhandled-thread and syntax warnings promoted to errors then passed **1,476 tests, 2 skipped, in 284.69s** using
`uv run python -m pytest -vv --tb=short -W error::pytest.PytestUnhandledThreadExceptionWarning -W error::SyntaxWarning --ignore=tests/e2e`.
Browser/anonymous-site checks are separate; this run made no provider or model calls. The test-fixture correction and recorded
verification are in `3f78e00`.

## Main continuation: OpenCode coding-task handoff (2026-10-09)

Work continued directly on local `main` from `4af8002`, per the user's direction. The reviewed handoff was split into backend/schema
commit `fc8bb20` and Studio/marketing commit `a976357`. Hutch now gives OpenCode its own process group while keeping the current
controlling terminal session, receives Ctrl+C in that foreground group, verifies process-group and session identity before
cleanup, and restores the terminal to Hutch. Reconciliation checks the saved session identity as well as boot ID and process
start time. A PTY fixture reads terminal input, receives Ctrl+C in the foreground group, and confirms terminal restoration; it
starts no OpenCode process. OpenCode config loading, account usage and task completion remain live-verification gaps.

The full offline run passed **1,483 tests, 2 skipped in 341.75s**, with `PytestUnhandledThreadExceptionWarning` and `SyntaxWarning`
promoted to errors. The CLI interrupt-state mapping and final PTY test expansion followed the start of that full run; the final
focused backend/migration/process batch passed **39 tests in 5.27s**. JavaScript syntax, Python compilation and `git diff --check`
passed on the focused state. The Studio handoff browser check passed **1 test in 5.45s**; the anonymous marketing-site suite
passed **27 tests in 36.65s** with no external requests. No OpenCode task or model call was started.

The final UI uses `DESIGN.md` and main's CSS tokens as the styling authority. I inspected the Studio task card and OpenCode FAQ at
desktop and phone sizes; the full capture sets include tablet and compact-phone widths. Screenshots, trace and validation data
are in [`artifacts/opencode-handoff/`](artifacts/opencode-handoff/), and the OpenCode FAQ captures are with the ChatGPT consent
marketing evidence. No push or publication was performed.

## Searchable Bot roster and mascot split (2026-10-09)

Commit `a79aed2` adds a persistent pin preference to the existing Bot record. Studio
keeps the named workspace coordinator first, then lists pinned Bots and all remaining
Bots in one searchable roster. Pinning affects navigation only; it does not hide,
pause, or alter permissions. Stable alphabetical ordering makes both groups consistent
across backend response order. On narrow screens the roster can be reopened repeatedly,
closed accessibly, and pin controls keep 44px touch targets. The implementation also
replaces product-app 3D sprites with distinct flat 2D Bot silhouettes; detailed 3D
mascot artwork remains on the public marketing site.

The decisions and bounded research evidence are in
[`docs/research/bot-roster-and-mascot-review-2026-10-09.md`](../research/bot-roster-and-mascot-review-2026-10-09.md).
The operator-app design system, product guide, README, roadmap, website copy and
Impeccable design sidecar were updated. `docs/realignment/visual-validation.md` records
manual inspection and the fixture-only visual acceptance boundary. Screenshot sets,
source hashes, metadata and the browser trace are stored in `artifacts/pinned-roster/`,
`artifacts/workspace-coordinator/` and
`artifacts/bot-purpose-refinement/marketing/`.

Verification after the final implementation change: `uv run pytest -q tests/test_api.py`
passed **36 tests in 14.31s**; the focused pin/roster Playwright test passed **1 test in
3.83s**; the coordinator responsive browser test passed **1 test in 2.84s**; and the
anonymous website suite passed **27 tests in 35.03s**. The nearby naming-picker plus
pin browser checks passed **2 tests in 6.76s**. JavaScript syntax, Python compilation,
JSON parsing for the design sidecar and `git diff --check` passed. Desktop, tablet and
phone renders were inspected for Studio/chat, the open phone/tablet roster, marketing
workflow copy and the detailed marketing mascot. No external browser requests or live
provider calls were made. No full end-to-end product suite, screen reader, physical
phone, or live provider was exercised in this slice; those remain separate gates.

## Workspace schedules overview and durable pause (schema v40)

Commit `8a87ac9` completes UI-9 on local `main`. The Monitor navigation now opens a bounded,
chronologically ordered view of recurring tasks across Bots, with each next occurrence formatted in
its configured time zone, catch-up policy, last-skip record, effective pause status and direct Bot
settings links. The workspace-wide pause is a separate durable control from each Bot's pause. The
scheduler checks it before producing due claims and again inside the transaction that claims an
occurrence and creates its run; a due snapshot read before pause cannot start work afterward. Queued
and running work continues, and missed windows follow each task's catch-up policy after resume.
Schema v40 adds the checked pause flag/timestamp and replaces the workspace outbox trigger so device
reconnects refresh the view.

The main app visual test uses temporary SQLite state and a configured local model route but makes no
model call. API, migration and scheduler coverage passed **11 focused tests** after the final pause
and missed-window assertions; the broader affected-module run passed **66 tests** before those final
assertion-only changes. The responsive app test passed **1 test in 4.24s**, and the anonymous
marketing test passed **1 in 3.67s**, both with Chromium **153.0.8010.12** / Playwright **1.63.0**.
Screenshots cover populated and empty views at **1440×960**, **900×1024**, and **390×844**; the phone
also has top and bottom scroll captures. The marketing Scheduling card was inspected at desktop,
tablet and phone sizes. Tests report no page errors or external requests. Node syntax, Python
compilation, JSON parsing and `git diff --check` passed. Evidence and trace are in
[`artifacts/schedules/`](artifacts/schedules/) and the marketing captures are in
[`artifacts/bot-purpose-refinement/marketing/`](artifacts/bot-purpose-refinement/marketing/).
These checks do not exercise a live provider schedule, physical phone or screen reader.

## Bot-scoped memory export (2026-10-09)

Commit `ba39ba7` adds **Download memory JSON** to each Bot's existing settings instead of introducing a separate all-Bot
memory page. The latter stays deferred unless the roster approaches ten Bots or actual navigation friction supports it. The
versioned `GET /api/v1/bots/{ref}/memory/export` reads a consistent SQLite snapshot containing the Bot label, every immutable
fact revision and scope (including proposed, legacy and archived records), review/archive decisions, and incoming/outgoing
explicit share snapshots with their current status. The export excludes conversations, provider credentials, run events,
action receipts, workspace files and artifact bytes. It is `no-store`, unencrypted plaintext; the modal warns that fact values
and review notes may be sensitive and tells users not to store passwords there. Export rejects, rather than truncates, more
than 10,000 revisions, 5,000 shares in either direction, 2 MiB of source content, or 16 MiB of serialized JSON. Permanent
deletion remains unavailable; archive retains history.

The API test checks historical revisions, review decisions, a share made stale by source revision, and separation from another
Bot's private fact. The store test verifies completeness and revision/byte bounds. The final affected API/store/browser batch
passed **61 tests in 15.99s**, including desktop, tablet and phone Chromium **153.0.8010.12** / Playwright **1.63.0** download
journeys. JavaScript syntax, Python compilation, and `git diff --check` passed. The design detector reported zero anti-patterns;
it repeated three radius advisories on unchanged CSS lines 558, 580 and 591. Captures, source hashes and traces are in
[`artifacts/bot-memory-export/`](artifacts/bot-memory-export/). I inspected all three final captures; the phone sheet keeps the
download action visible, meets the 44px target and has no horizontal overflow. Fixtures used synthetic SQLite data and made no
model/provider calls. No screen reader or physical phone was used.

## Guided Bot setup YAML preview and download (2026-10-09)

Commit `c960215` completes the UI-7 YAML view with a versioned, sanitized preview and download from the final Bot-setup review.
The preview reuses Bot-create validation and returns a typed response marked `no-store`; it never persists configuration or
starts work. Endpoint URLs, local paths and source-message identifiers are omitted. The normal explicit **Create bot** action is
still required to save. Documentation distinguishes this unsaved setup export from importing YAML or snapshotting an existing
Bot, which remain open roadmap work.

The focused API + browser batch, `uv run pytest -q tests/test_api.py tests/e2e/test_browser.py::test_guided_bot_creation_reviews_configuration_at_desktop_tablet_and_phone --no-header`, passed **41 tests in 16.48s**. The browser ran on Chromium **153.0.8010.12** / Playwright **1.63.0** at desktop **1440×960**, tablet **900×1024**, and phone **390×844**. Enter builds the preview and downloads identical YAML. I inspected each final capture and fixed horizontal overflow from long YAML lines. `node --check src/hutch/server/static/app.js`, `uv run python -m compileall -q src/hutch`, and `git diff --check` passed. Tests used local fixtures and a test-only credential marker; no model call or external request occurred. No screen reader or physical phone was used. Screenshots, trace, downloaded sample and validation metadata are in [`artifacts/bot-setup/`](artifacts/bot-setup/).

## Guided Bot setup YAML import (2026-10-09)

Commit `c551483` adds a bounded `POST /api/v1/bot-configs/import` route and a first-step file picker in the guided Bot wizard. The parser accepts only the `hutch.ai/v1` `BotConfig` shape, up to 64 KiB, and rejects YAML aliases, duplicate keys, unsafe tags, excessive nesting, unknown fields, endpoint URLs, local folder paths, chat sources, command rules and unsupported authority. It returns a sanitized unsaved draft with `Cache-Control: no-store`; import has no persistence, run or provider side effect. Credentials, terms acknowledgement and Strict Offline host readiness are deferred until normal Bot creation; route syntax, provider identity, inference-mode policy and the remaining Bot fields are checked during import. The setup then exposes the imported values through the same editable wizard and explicit final **Create bot** action.


## S8 passkey phone supervision (schema v42, 2026-10-09)

This checkout replaces the legacy remote device bearer path with one-use pairing enrollment, WebAuthn passkeys, separate revocable
sessions, an exact phone route/capability inventory, and a local-owner opt-in for each Bot's remote Start capability. The supported
CLI launch clears any inherited internal remote-enable environment value and sets it only after `--allow-remote` configuration passes.
Passkey registration and assertions require the configured RP ID, exact HTTPS origin and challenge, a valid signature, and user verification;
multi-device passkeys remain supported without claiming that one credential identifies one physical phone. Login ceremony creation
is rate-limited per client. Session idle/absolute deadlines are enforced server-side and background polling does not renew idle time.
Remote starts use the Bot's saved model and policy; the Store checks credential Start capability and current Bot opt-in at admission
and claim, while revocation or owner opt-out cancels unclaimed phone work. Claimed work remains visible for an explicit Stop.

Paired phones can read bot/run status and transcripts, review an exact action hash and choose Allow once or Deny, and Stop/Resume
through existing server checks. Route aliases, exports/artifacts, device administration, Bot/provider/schedule settings and computer
interaction remain owner-only. Private responses are no-store, browser mutations require same-origin/CSRF checks, and phone streams
close after authorization expires or is revoked. Hutch remains loopback-only by default; the documented remote paths are Tailscale
Serve to loopback or an explicitly selected private LAN interface with trusted HTTPS. This implementation did not configure public
ingress or Funnel; the current Hutch socket is loopback-only, with `HUTCH_REMOTE_ENABLED` and `HUTCH_TRUSTED_PROXIES` unset in its
process environment. The Tailscale CLI and interface are unavailable here, so pre-existing Serve/Funnel configuration is unverified.
CLI regression coverage rejects wildcard and public-address binds even when TLS file paths
are provided.

The broader combined focused verification passed **178 tests in 59.55s** across passkey, pairing/authority, store, API, conversation,
approval-CAS, SSE-resume, migration, state-snapshot, engine and six browser journeys. Trusted-proxy coverage includes rejecting
Tailscale's Funnel marker before even the anonymous pairing surface. The paired-phone command journey covers Stop and
Resume bound to the active human-wait event; another journey simulates a committed approval whose response is dropped and confirms
the phone retries with the same idempotency key. Browser coverage includes status/transcript/revocation, exact-action
approval, pair/unlock pages and a Chromium virtual-authenticator journey. The latter performs real WebAuthn enrollment,
lock, unlock and an opt-in phone Start in Chromium over a real loopback Uvicorn HTTPS socket, including a Bot whose scheduled tasks
are paused; the resulting on-demand run keeps the paired credential as its origin and the Bot's saved model. Local Ed25519/CBOR
fixtures also exercise WebAuthn verification. The verifier caps each credential object at 256 KiB and rejects passkey verification
request bodies above that cap plus 4 KiB at the ASGI boundary, before FastAPI parses JSON. A monitor-only passkey sees no Start
control even when the Bot itself is enabled. Snapshot, change-feed and idempotent replay tests check that owner-only conversation and
run metadata are withheld. These are synthetic local proofs and browser fixtures, not physical-phone or public-network validation.
Live iOS Safari, Android Chrome, Tailscale Serve,
LAN certificate renewal, and network-isolation checks remain release gates. Python compilation, JavaScript syntax and `git diff --check`
were rerun at the final source state. Remote access remains disabled by default.

The current official Tailscale pages disagree about Funnel's default state: the [Serve feature page](https://tailscale.com/docs/features/tailscale-serve)
says enabled, while the [Funnel feature](https://tailscale.com/docs/features/tailscale-funnel) and [CLI pages](https://tailscale.com/docs/reference/tailscale-cli/funnel)
say disabled. The operations guide therefore requires checking the actual Serve and Funnel status plus the
effective tailnet policy instead of relying on a default. The Tailscale CLI is unavailable on this host, so those live statuses remain
unverified; the Hutch listener observed during this audit is loopback-only at `127.0.0.1:8787`. Review of Tailscale's current
[Serve proxy source](https://github.com/tailscale/tailscale/blob/main/ipn/ipnlocal/serve.go#L1014-L1036) confirms it forwards Host
and client address, sets Proto for HTTPS, and adds a Funnel marker. Hutch now rejects that marker from its configured proxy. This
source inspection and synthetic regression do not validate the unavailable installed client or a live Serve connection.

Follow-up hardening on 2026-10-09 corrected `/api/v1/capabilities` to report phone supervision as experimental, describe its
status/transcript, approval, Stop, current-human-wait Resume, and opt-in Start scope, and state that remote computer interaction is
unavailable. The API regression failed on the stale capability value before the correction. The auth lifecycle audit also found
that an enrollment cookie could mint unbounded registration challenges. The Store now caps each flow at 16 in the same transaction;
the 17th options request returns 429 and does not create another row. A concurrent 32-request regression confirms exactly 16
challenges are stored under contention. The focused phone/auth/approval/SSE/browser batch passed **180 tests in 64.52s** on this
source state. Python compilation, dashboard JavaScript syntax, and `git diff --check` also passed.
A Playwright WebKit launch could not run because the installed package expects the missing `webkit-2359` executable; no browser was
installed. A fresh listener check found Hutch PID 1895954 bound only to `127.0.0.1:8787`, with `HUTCH_REMOTE_ENABLED` and
`HUTCH_TRUSTED_PROXIES` unset. The Tailscale CLI is absent, so actual Serve/Funnel state and network policy remain unverified.

Phone visual follow-up on 2026-10-09 inspected seeded approval and run-detail screens in Chromium 153 using 390×844 mobile
emulation. The screens had no horizontal overflow; approval details and Allow once/Deny controls stayed visible, and status plus
transcript content remained readable. The audit caught raw ISO timestamps in the phone run view; these now render in the browser's
local date/time format. The paired-phone browser regression failed before the fix and passed after it. This emulation does not
replace physical iOS Safari, Android Chrome, or private-network validation. The complete focused phone/auth/approval/SSE batch
passed **180 tests in 63.08s** on the final source state.

An integration audit found that WebAuthn-on-HTTPS and the phone controls had been tested separately. The
`test_virtual_passkey_pairs_locks_and_unlocks_over_https` journey now enrolls and unlocks a virtual passkey over real Uvicorn TLS,
approves an exact action with its hash, CSRF token and idempotency key, starts the opted-in Bot, Stops that run, and Resumes a
separate run at its current human-wait event. The focused phone/auth/approval/SSE batch passed **180 tests in 75.81s** with this
combined flow. The operations guide now has a pre-enable iOS/Android, recovery, revocation, and ingress checklist. This host has a
private Wi-Fi address but no Tailscale CLI, Android device bridge, or Apple simulator; no listener or network exposure was changed.

The private-certificate check was strengthened with `test_chromium_trusts_a_private_https_certificate_chain`: it imports a
temporary CA into an isolated Chromium NSS profile and loads an exact-host HTTPS site with Playwright certificate-error bypass
disabled. The full focused phone/auth/approval/SSE batch, now including this test, passed **181 tests in 67.75s**. This validates
Chromium's private-CA path on this host; it does not prove iOS/Android trust-store setup or a live LAN/Tailscale route.

## Shared design system across Studio, Connections, and marketing (2026-10-09)

Commit `462a374` makes `website/tokens.json` the shared semantic source for the operator app, supporting server pages, and static
marketing build. Studio and the in-app `/#/connections` surface use the same shell, controls, surface ramp, body type, focus color,
and radius scale; marketing keeps its editorial layout and 3D mascot while sharing the core palette, body type, and component
geometry. `DESIGN.md` on `main` remains authoritative. The earlier `/connections` capture was a legacy HTML route and was excluded
from the product comparison.

`npm run build:css`, `python scripts/build_site_tokens.py --check`, and
`.venv/bin/python -m pytest -q tests/test_site_tokens.py tests/e2e/test_design_system.py --no-header` passed; the focused tests
reported **8 passed**. The anonymous marketing browser suite reported **27 passed**. Twelve screenshots were inspected: Studio and
Connections at desktop **1440×960**, tablet **900×1024**, and phone **390×844**, plus marketing viewport and full-page captures at
each size. The 320×740 reflow check found no horizontal overflow. Chromium **153.0.8010.12** / Playwright **1.63.0** made no
external requests and no provider calls. These are local fixture checks, not screen-reader or physical-device validation; the
screenshots, trace, and validation JSON are in [`artifacts/design-system/`](artifacts/design-system/).

## Bot setup and roster usability (2026-10-09)

Commit `dffe717` simplifies the routine setup path and the Studio roster. Creating a Bot from a chat request carries the selected
user request forward as its standing instructions, with an optional edit and an editable role-based name; it does not ask the owner
to retype the request, start a run, add tools, or schedule work. Empty-chat setup uses safe defaults and shows advanced options only
when requested. The roster keeps one options button per Bot for pinning and settings, wraps names to two lines before clamping, and
collapses idle Bots at ten or more in a searchable, keyboard-operable section. Flat 2D app mascots retain distinct fills and use
rounded ink eyes positioned for each silhouette; the larger marketing mascot remains separate.

The `bot-setup-patterns-2026-10-09.md` research note records official Grok Bot, OpenAI Dots and GPT Builder behavior separately from
individual user reports. It treats reported failures as acceptance scenarios, not prevalence claims; Dots availability and GPT
Builder policy are explicitly time-bounded to the reviewed documentation. Mobbin screen galleries were unavailable behind their
account/paywall boundary, so no inaccessible captures are represented as inspected research. Figma Community references remain
inspiration, not a source of adopted assets or an imported design system.

The focused setup/roster browser batch passed **5 tests in 17.08s** and the separate small-workspace Bot-settings menu regression
passed **1 test in 5.17s**. Chromium **153.0.8010.12** / Playwright **1.63.0** captures were visually inspected at desktop
**1440×960**, tablet **900×1024**, and phone **390×844**. The name field and action footer stayed visible; the sidebar menu fit the
phone drawer; and the 10-Bot example kept idle Bots reachable by search and keyboard. Browser tests made no external requests or
provider calls. No physical phone or screen reader was used. Evidence and traces are in
[`artifacts/simple-bot-setup/`](artifacts/simple-bot-setup/), [`artifacts/pinned-roster/`](artifacts/pinned-roster/), and
[`artifacts/compact-roster/`](artifacts/compact-roster/).

## Bot/chat options and UI regression follow-through (2026-10-09)

The conversation overflow menu adds persistent rename, pin, unread/read, named sections,
reviewed local export and recoverable archive/restore. The single Bot overflow menu keeps
pin, section, hide/show, settings, safe template download and editable safe duplication.
Duplicate setup carries the existing standing instructions, model route, inference mode,
workspace type and limits; it leaves connected account/tool authority, schedules, memory
values, history, external endpoints and local paths behind. The research note records
current Grok Bot management documentation and Open WebUI organization patterns, while
treating individual user reports as scenarios rather than prevalence claims. Mobbin remained
plan-gated and the Figma preview remained too zoomed out for component-level inspection.

The focused persistence/template/duplicate/roster/quick-create batch passed **42 tests in
22.51s**. A broader diagnostic run was stopped after **516 passed and 6 failed in 582.18s**;
the failures were schedule focus restoration, running-status animation/heading leading,
roster-menu interaction verification, and three old-schema migration fixtures. The schedule
control now stays focusable while busy and restores focus after overlapping refreshes;
running status no longer pulses; server page headings use a 1.4 line-height; the roster
browser check verifies the actual menu click, Escape close and focus return; and the v21–v23
fixture helper removes the v43 columns and invalidation triggers before replaying migrations.
After those repairs, the migration tests passed **3**, schedule/dashboard/roster browser tests
passed **3**, and conversation/duplicate checks passed **4**. The full suite remains
unverified after these changes.

Final screenshots and traces are under [`artifacts/conversation-options/`](artifacts/conversation-options/)
and [`artifacts/bot-chat-options/`](artifacts/bot-chat-options/). Menu screenshots cover
1440×960 desktop, 900×1024 tablet, 390×844 phone, and 320×844 compact phone; safe-duplicate
setup/review covers desktop, tablet and phone. The captures report no horizontal overflow,
page errors or provider calls; the conversation and duplicate tests also recorded no external
requests. Dashboard captures were inspected at all three viewports. These are local Chromium
**153.0.8010.12** / Playwright **1.63.0** fixtures; there was no live provider, external
account, physical-phone or screen-reader test.

## Conversation templates and shared typography token check (2026-10-10)

The conversation menu keeps the frequent actions visible and groups template, export and archive under a nested **More** disclosure.
Saving a task template reviews an editable name and only the first user request; importing the versioned local JSON fills the composer
draft and starts no run. The exported document excludes assistant replies, tools, files, account grants and conversation identifiers.
The public docs now distinguish this local file workflow from Grok's link sharing and record Open WebUI's prompt-library pattern and
its persistent typed-variable/slash-command capability as a future product option.

The scoped browser batch passed **6 tests in 25.45s** after the final CSS and task-template changes: conversation options, Bot template,
safe duplicate, recoverable roster hide/section, dashboard status/heading, and schedule focus restoration. The conversation-options test
also captured review at desktop **1440×960**, tablet **900×1024**, phone **390×844** and More at compact phone **320×844**. Chromium
**153.0.8010.12** / Playwright **1.63.0**; no provider calls or external requests. `scripts/build_site_tokens.py --check`, scoped design
detection, JavaScript syntax, Python compilation and `git diff --check` passed. The Impeccable sidecar now agrees with the main-branch
`DESIGN.md` heading, section, brand and steady-status roles. Token alignment and the sidecar refresh are committed as `0b6cbe8`.
The full test suite has not been rerun after the previous interrupted
diagnostic run and is not a release pass. Screen-reader, physical-phone, and performance-profile evidence remain open; see
[`ui-audit-2026-10-10.md`](ui-audit-2026-10-10.md).

## Saved request library and stable command replay (2026-10-10)

The local saved-request feature is now reachable both from a conversation's **More** menu and the chat composer. Reuse fills only
the draft. The marketing workflow card now explains that local behavior and is covered by an anonymous browser assertion plus
responsive screenshots. The original saved-request API/UI checks remain in `tests/test_task_templates.py` and
`tests/e2e/test_saved_requests.py`.

A test-first regression exposed that create/update idempotency entries stored only a resource ID, so a lost-response retry after a
later edit returned the newer version, and a retry after deletion raised an internal error. Create/update now persist and replay the
original resource snapshot. The regression first failed on the changed revision and content, then passed after the fix. Latest
verification for this slice: API/migration tests **23 passed** (including both saved-request API cases); saved-request browser journey
**1 passed**; anonymous marketing suite **27 passed**; JS syntax, Python compilation, and `git diff --check` passed. The all-tests
diagnostic completed with **1,689 passed, 4 failed, and 1 teardown error in 872.90s**. Three legacy migration fixtures retained the
v44 saved-request table while simulating v21–v23; the remaining browser test clicked Archive before opening nested **More**. After
fixing those test fixtures and ensuring browser-context cleanup, the affected cases passed targeted reruns (**3 migration, 1
browser**). The full suite has not been rerun after these corrections. Visual evidence is under
[`artifacts/saved-requests/`](artifacts/saved-requests/). No changes are pushed or published.
The application, schema, documentation and tests are committed on local `main` as `257ef10`; the refreshed screenshot, validation JSON,
and trace evidence is committed as `e1bd3b9`.

## Mascot face correction across all silhouettes (2026-10-10)

The owner screenshot showed white tapered marks perched outside a pointed drop mascot, where they looked detached rather than like eyes.
The shared 2D app renderer now uses two dark, tapered oval eyes; their spacing, proportions, and tilt are selected per head shape, with the
drop and triangle eyes moved lower into the wider face area. Bot-name identity and the separate status pip are unchanged. Marketing's
detailed 3D mascot is not affected.

The new browser regression renders all eight silhouettes in all eight identity colours and checks each eye pair's centers and sampled
98%-perimeter lie inside its exact SVG head path. It also checks each silhouette has its own eye proportions. Dark eye ink measures at
least **5.81:1** against every identity colour. The combined
roster/design-system browser batch passed **3 tests in 11.98s** in Chromium **153.0.8010.12** / Playwright **1.63.0**. Screenshots at
desktop **1440×960**, tablet **900×1024**, and phone **390×844** (Studio with roster closed/open) plus the Playwright trace and validation
JSON are in [`artifacts/mascot-eye-review/`](artifacts/mascot-eye-review/); refreshed shared-shell examples are in
[`artifacts/design-system/`](artifacts/design-system/) and [`artifacts/pinned-roster/`](artifacts/pinned-roster/). The page produced no
browser errors or horizontal overflow and made no provider calls. This is fixture-based visual validation, not physical-device or
screen-reader testing.

After the first owner review, the faces were refined again because their proportions still looked too uniform across distinct head shapes.
The orb, capsule, bean, drop, pebble, shield, triangle, and hex now each have a separately tuned pair of diagonal oval eye marks. The updated
shape-containment browser test passed **1 test in 2.24s**; its desktop and phone screenshots were individually inspected. The 2D mascot
language stays deliberately simple in the app, while the 3D illustration remains marketing-only.

## In-Studio conversation search (2026-10-10)

The chat header now has one search action beside the conversation selector, keeping search out of the crowded Bot roster and
conversation-options menu. Its accessible dialog filters across active chats or one Bot, shows a short context excerpt and opens the
chosen conversation. Archived and imported conversations remain excluded, matching the existing FTS5 scope. The new POST route keeps
the query out of the browser URL and returns at most 30 excerpt-only rows to Studio by default; the server bounds query length and
result count, and paired Monitor sessions still require the standard origin and CSRF checks. The old GET route remains compatible.

Placement was informed by separately inspected Figma mobile frames, where search is a compact header action; the wide preview collage
was treated only as an index. Mobbin captures remain unavailable behind its account-plan gate, so none are cited as inspected.

The unit, authorization and initial browser batch passed **24 tests in 17.37s**; the phone search trigger measures **44×44 CSS pixels** in a
touch-enabled Chromium context. JS syntax, Python compilation, CSS-token generation check,
design detection and `git diff --check` passed. Chromium **153.0.8010.12** / Playwright **1.63.0** screenshots were captured and
individually inspected at desktop **1440×960**, tablet **900×1024**, phone **390×844** and compact phone **320×740**. Search returned
two all-Bot results and one Bot-filtered result, opened the selected chat, restored keyboard focus, had no horizontal overflow, page
errors, external requests or provider calls. Images, trace and machine-readable validation are in
[`artifacts/conversation-search/`](artifacts/conversation-search/). A follow-up browser pass added empty-result, service-error, and HTML-like
message content checks; that focused journey passed **1 test**. The populated desktop, tablet, phone, and compact-phone captures, plus
desktop empty/error states, were inspected individually. The full offline non-E2E suite passed **1,532 tests** using warnings-as-errors
for unhandled thread and syntax warnings. These are local fixtures; there was no physical-phone, screen-reader, or live provider test.
