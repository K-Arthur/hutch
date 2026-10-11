# Architecture

Schema v46 separates reference facts, durable typed chat questions, explicit specialist-result references, task-only selected-fact snapshots, content-free workspace task checkpoints, an owner-approved specialist roster, immutable safe-continuation lineage, owner-reviewed local OpenCode coding handoffs, per-Bot Google Calendar event-creation grants, and separate Outlook Mail send grants from canonical chat messages, workspace files, execution receipts
and provider credential stores. It stores credential-free Google and Outlook Calendar/Mail account references and one selected-calendar, mailbox, or send-only mailbox grant per Bot;
refresh credentials remain in Linux Secret Service. Outlook Calendar, Mail read, and Mail send use separate OAuth callbacks, token namespaces and scopes. Model proposals inherit persisted chat/run scope and execution fencing;
human review binds immutable revision/scope hashes. Explicit sharing creates a bot-wide reference.
Facts are retrieved as bounded JSON tool data through SQLite FTS5, never automatically placed in system
instructions. During a reviewed coordinator handoff only, the owner may explicitly select up to eight current approved facts
from the coordinator Bot or exact chat; immutable snapshots are attached to that task and enter the specialist run as untrusted
context, not specialist memory. Archived/replaced/unreviewed versions are excluded. Retained versions/reviews remain
private persistent data; archive is not erasure. See ADR-0008 and the continuation ledger for actual checks.
Bot settings can export one consistent, bounded SQLite snapshot of that Bot's complete fact history,
review decisions and explicit share records. The downloadable JSON is unencrypted; credentials, transcripts,
action receipts and workspaces remain outside the export.

Bots retain a stable machine address (`name`) for routes, files and old links, with a separate human-facing
`display_name`. Older records receive a readable label derived from their address. Guided creation suggests a
professional label from the owner's stated purpose using a deterministic local heuristic; the owner can edit
both label and address before confirming. The CLI also accepts `--display-name`. This naming step does not call a model,
change permissions or start a run.
When creating a Bot from Studio chat, the owner can also select up to eight earlier user messages from that same conversation.
The exact selection is reviewed and saved as background in the Bot's instructions; assistant messages, other chats and
permissions are not carried over. The saved context may be included in future model calls.
Schema v28 stores the owner's selected workspace coordinator. Bot settings can assign the role, the selected Bot opens as the default Studio chat, and the roster labels it. Schema v41 stores the owner's explicit specialist list, initially empty; promotion removes the new coordinator, and task admission checks membership atomically before writing the task/run. The prior coordinator is not auto-authorized. Schema v29 records a reviewed handoff from a completed coordinator turn to one approved specialist: the original request, coordinator draft, user-edited brief and assumptions, specialist identity/settings snapshot, child conversation/run, current status and latest response remain linked in the parent chat. Schema v32 permits an unchecked-by-default, bounded selection of reviewed coordinator facts for that task's untrusted run context; the snapshot is not added to specialist memory. The specialist's own enabled memory and workspace still apply. A changed specialist route, instruction, permission or workspace fails before its worker starts. Schema v30 records a user-selected successful specialist message attached to a coordinator follow-up, bound to the task and source message in the same parent conversation. A 4,000-character immutable snapshot appears in the transcript/export and a JSON-escaped form enters only that run as explicitly untrusted context. Schema v31 adds an ordered journal of selected committed child-run event markers, bounded to the latest 16 per task in the API projection; it stores no event content, prompts, reasoning, action arguments or tool output. The linked child run remains the authority for its capability snapshot and decision records. Schema v34 permits one owner-confirmed fresh attempt from a failed/stopped built-in task only when no action or child run was recorded, the specialist chat has no later work or pending question, the coordinator chat remains active, and the exact capability snapshot is unchanged. The new attempt gets the reviewed brief/constraints and bounded committed assistant text as untrusted progress; it never replays actions, receipts, selected facts, prior tool results or credentials. `outcome_unknown`, external runtimes and process restoration remain unavailable. This remains one explicit handoff at a time, not an autonomous team planner; parent cancellation and live external-provider verification remain incomplete.

Schema v50 adds durable generated documents: a `documents` row carries one stable identity per document and
`document_versions` rows carry immutable versions with filename, MIME, byte count, SHA-256, storage path,
provenance (run and generator), validation state and findings, preview mode and the typed source specification.
Bytes live under `<state>/documents/<doc id>/vNNN-<sha8>/` behind a staging-and-journal commit protocol whose
crash windows reconcile on startup (a promoted version without a row is invisible, so reconciliation deletes it;
a row whose bytes changed fails the serve-time hash check instead of serving unverified content). Tools draft
typed specifications; deterministic renderers in `hutch.documents.docgen` produce and validate bytes; `create_document`,
`revise_document` (compare-and-swap on the expected version) and `inspect_document` expose the capability behind the
`documents:create` ask-by-default sticky key with the standard intent/receipt bracketing. Downloads re-verify size and
hash on every request through `/api/v1/documents/...` routes; previews are derived, bounded assets (PDFium page images
or extracted structure) and never stand in for the exact file. See `docs/file-formats.md` for the verified capability
matrix and the research file for the failure classes each defence answers.

hutch is a local-first multi-bot agent platform: one Python process family that stores everything
in one state directory, drives LLM agents through a policy-gated tool layer, and exposes both a CLI
and a local web dashboard.

## Component map

```mermaid
flowchart LR
  subgraph Clients
    CLI["hutch CLI<br/>(typer)"]
    UI["Dashboard<br/>(FastAPI + static SPA)"]
    API["REST API<br/>legacy + partial v1"]
  end

  subgraph Core
    ENG["Engine<br/>dispatch · caps · transcripts · stop"]
    SCH["Scheduler<br/>croniter + IANA tz · catch-up"]
    SCHED_STORE[("SQLite (WAL)<br/>bots · tasks · runs · events<br/>usage · reservations · conversations · approvals · devices · code_handoffs")]
    POL["Policy engine<br/>compound-command parser · path jail · URL guards"]
    GATE["Approval gate<br/>fail-closed · sticky allows"]
  end

  subgraph Runtimes
    BUILTIN["builtin loop<br/>(OpenAI-compatible)"]
    EXT["Pi / OpenCode bot runtime<br/>(disabled)"]
    CODE["Reviewed coding handoff<br/>local OpenCode CLI + pinned worktree"]
  end

  subgraph Tools
    SH["shell (workspace-jailed)"]
    FI["files (path jail)"]
    ME["memory (sqlite)"]
    WF["web_fetch (ssrf-guarded)"]
    BR["browser (playwright, optional)"]
  end

  CLI --> ENG
  CLI --> CODE
  UI --> API
  API --> ENG
  API --> CONV["Conversation service<br/>bounded history · idempotency"]
  CONV --> SCHED_STORE
  SCH --> ENG
  ENG --> SCHED_STORE
  ENG --> BUILTIN & EXT
  BUILTIN --> POL
  BUILTIN --> SH & FI & ME & WF & BR
  SH & FI & WF --> POL
  SH & FI & BR --> GATE
  GATE --> SCHED_STORE
  BUILTIN --> LLM["model provider<br/>openai · ollama · llama.cpp · lmstudio"]
  API --> CODE
  CODE --> SCHED_STORE
```

The code-handoff API validates and records an immutable review; it does not launch an executor process. The owner later starts the
local OpenCode CLI from `hutch code run` in an interactive Linux terminal. That terminal path uses the saved commit and a separate
Git worktree. OpenCode command approvals, account usage and shell effects stay outside Hutch's executor, sandbox and usage ledger.
The Bot's normal Pi/OpenCode runtime value remains disabled. See the [reviewed handoff contract](realignment/contracts.md#reviewed-opencode-coding-handoff-experimental-schema-v39).

## State layout

Everything lives under one directory (default `~/.local/state/hutch`, override `HUTCH_STATE_DIR`):

```
hutch.db                      # SQLite (WAL): bots, tasks, runs, events, usage/reservations, conversations/questions, approvals, memory, receipts, artifact-share grants
bots/<bot>/runs/<run_id>/
  transcript.jsonl              # append-only run transcript (mirror of events)
  artifacts/<version>-<tool>.txt # immutable clipped outputs and write_file snapshots
  workspace/                    # the bot's jailed world for this run
bots/<bot>/browser-profile/     # persistent Chromium profile (logins survive runs)
workspaces/<bot_id>/            # optional private folder shared across one bot's runs/chats
code-worktrees/<handoff-id>/     # retained local coding-task branch; managed outside database backup
```

Large tool outputs and files created with `write_file` are linked to their committed `tool_result`
event by run and event sequence. The event stores the byte size and SHA-256; the typed API lists
these bounded run-scoped artifacts, and a download verifies the bytes again before sending them as
plain text. The chat offers file downloads beside the write result; snapshots are capped at 4 MB
per file and 16 MB per run. Studio shows write-file downloads outside the collapsed tool details.
Each tool can also set a model-visible character limit (12,000 by default). Clipped output stays
as a verified run artifact; the expanded tool row places its download and readable source card
outside the scroll-bounded preview so the full result remains easy to reach on a phone.
The composer menu also pages verified files and saved tool output across runs attached to the
current conversation, so the operator can find an earlier result without leaving the chat. The
query checks both conversation and bot ownership; downloads still resolve to the source run and
verify its recorded size and hash. The owner may explicitly grant another selected conversation a
reference to one verified artifact. That grant is stored in SQLite, appears with source-chat
provenance, and has its own target-bound download URL so revocation blocks later downloads. The
originating chat lists active recipients beside the file and can revoke a grant there; the receiving
chat can also stop its access. The file bytes stay in the source run: the reference neither copies
them into the other workspace nor adds them to that chat's model context. This is not a general
artifact library or implicit bot-to-bot sharing. Schema v18 adds durable invalidations for the source
conversation when a grant is created or revoked, including changes made from another device.
Schema v19 adds a one-use resume record bound to the active `human_needed` event sequence. An old
resume retry returns its original result without setting a flag for a later challenge.
Arbitrary shell-created files are not attached automatically. Bots
default to a fresh workspace per run; operators may select a private Hutch-managed directory
shared only by that bot, or an existing validated user folder.
These choices do not move files. Managed workspaces are separate from SQLite backups and survive
bot deletion. A run with persisted parent lineage always gets its own private 0700 run workspace,
regardless of the bot's managed or host-folder setting; an unexpected workspace symlink fails closed.
Schema v24 captures a credential-free capability snapshot in the same transition that starts each new
root run. Internal child admission copies the parent's immutable snapshot, so editing the bot cannot
silently widen a future child. An opt-in `delegate_task` tool now admits a same-bot child only for a
supervised built-in Strict Offline run. The worker reconstructs execution authority from the saved
snapshot, removes browser and memory tools, and uses a private per-run workspace. The child receives
only its explicit task string, not the parent conversation or workspace contents. Its run remains
attached to the same conversation for operator visibility, while the parent model receives only the
child's final text. Artifacts remain attributed to the child run; no workspace copy or automatic file
transfer occurs. Every child request asks for human approval, even in `auto` mode. Depth, fan-out,
child duration and steps are bounded, usage reserves against the inherited root limit, and Stop
persists cancellation across the lineage. With the default global limit of two, only one child can
run beneath a root at a time; deeper work requires additional configured global slots. See
[`delegation.md`](realignment/delegation.md). External runtimes and parallel public child execution
remain unavailable.

## Key decisions

### D1 — Own the agent loop; keep ungoverned runtimes disabled

The original proposal (see `docs/research/orchestrators.md`) put OpenCode at the core. Research
changed that:

- **OpenCode's server is project-scoped**: N isolated bot workspaces would need N server processes
  on N ports, its Python SDK is alpha, and its HTTP API ships no stability promise.
- **Frameworks (CrewAI/LangGraph/AutoGen)** abstract the agent loop (the easy ~300 lines) and none
  of what actually matters here: scheduling, approvals, budgets, isolation, transcripts. 2026
  post-mortems consistently call them overkill for cron-style dispatch.

Result: `runtime/builtin.py` owns the governed production tool loop. The deterministic execution
scenario under `tests/support/` exists only to exercise the tool and policy pipeline in tests;
it is not installed or selectable by an application user.
Legacy `pi` and `opencode` enum values fail closed before process creation. Their old adapters bypassed
Hutch approvals and budgets, so they remain unavailable until sandboxing, permission brokering,
provider reservations and protocol tests are complete.

### D2 — Bots are configs, runs are executions

A **Bot** is a stored config (model, tools, up to 100 optional recurring tasks, limits). A **Run** is one execution with its
own workspace directory, transcript, step/token accounting, and terminal status. Tasks are the
queue between scheduler and engine. One active run per bot at a time (single-instance lock);
global concurrency default 2.

Each recurring task has a stable, globally reserved ID, name, cron expression, IANA timezone,
catch-up policy, and optional prompt separate from standing bot instructions. Its due window,
last-fire marker and visible skip record are independent from the bot's other tasks. A blank task
prompt preserves legacy behavior by using the bot instructions, then a generic workspace-report
task if the instructions are empty. Prompts are limited to 4,000 characters. Settings, the typed
schedule API and `hutch bot schedules` manage individual tasks. Older `schedule` fields and
`hutch bot update` schedule options remain aliases for the first task. Tasks on one bot share its
tools, workspace, limits and permissions, and that bot still never runs two attempts at once. The
dashboard's Schedules overview lists next occurrences in each task's timezone. A durable workspace
pause affects future schedule admission only; queued/running work and Bot-specific pause settings
remain independent.

### D3 — Scheduling correctness is a feature, not a detail

All timestamps are ISO-8601 UTC-with-offset. Calendar cron math happens in the task's IANA zone via
croniter, with a round-trip check that drops DST-gap times (spring-forward) and de-duplicates
ambiguous times (fall-back) — Vixie-cron semantics. Invalid IANA zones never fall back to UTC;
admission is blocked until repaired. Fixed-rate `interval` triggers keep exact second periods
(65/90 minutes are not hourly cron approximations). After downtime the scheduler finds the *true*
newest eligible occurrence (not the last element of a capped prefix); coalesced `missed_windows`
may be marked uncertain when the count hits the bound. Progress markers advance to the claimed
occurrence instant. Catch-up `skip` grace scales with the estimated period. Overlap policies
(`queue` / `skip` / `buffer_one`), skip-next, and run-now (manual, marker-preserving) are first-class.
Schema v21 retains schedule identities after removal. The workspace-wide pause is rechecked in the
same transaction that claims the occurrence and creates its run.

### D4 — Policy before execution, transcripts regardless of outcome

Every tool call passes the policy engine (see `docs/safety.md`) *before* subprocess/file/network
execution. Every event — prompts, tool calls, results, approvals, errors — is appended to SQLite
and to `transcript.jsonl` on disk. A run becomes terminal (`succeeded`, `failed`, `stopped`, …) only after execution cleanup is
verified; otherwise `cancelling` or `recovering` remains visible with a reason. Terminal `exit_reason` values include `completed`,
`timeout`, `steps_exceeded`, `token_cap`, `approval_expired`, and `error`.

SQLite's event writer batches commits through a bounded queue. Failed batches remain queued and do
not advance the commit acknowledgement; a full queue refuses new events. Workflow-owned event
callbacks wait for that canonical acknowledgement before the interpreter can advance. If enqueue or
commit fails, the attempt stops with `event_delivery_failed` and recovery starts a new attempt;
completed effect receipts are reused only when their immutable operation identity still matches.
The JSONL transcript is a separate recoverable mirror and does not stand in for canonical history.

### D5 — Caps are enforced by the engine, not by model behavior

- `max_steps` — agent turns per run
- `timeout_seconds` — wall clock. `serve`, `daemon`, and `hutch run` execute one owned OS worker process per attempt. Cleanup verifies boot/start identities and keeps a run in `Stopping` or `Cleaning up` until no owned process remains. Admission also treats unreaped `run_procs` as occupying capacity so a peer cannot start while descendants may still act. `HUTCH_EXECUTOR=thread` is for tests and compatibility; a stuck thread is joined before persistence closes, so it cannot be declared terminal while still running.
- Tool capture is bounded before allocation (`MAX_TOOL_OUTPUT`); the model sees a smaller per-tool view (PF-2) with optional artifacts. Unlimited `tool_limits=0` is rejected.
- `daily_token_cap` — actual response usage plus pre-call prompt/reply estimates and unresolved reservations;
  admission reserves the next estimate atomically across processes. Currency caps also reserve a price-based estimate;
  provider-side billing can differ, so this is not an exact dollar guarantee.

### D6 — Web dashboard and CLI are the same engine

`hutch serve` runs FastAPI with a background supervisor loop, serving a dependency-free static SPA that polls `/api`. A durable
SQLite lease elects one scheduler/recovery supervisor across dashboard workers and `hutch daemon`; web workers submit work
and wait for state changes. The CLI drives the same `Engine`.
No separate daemon is required for dashboard-driven usage; `hutch daemon` is the headless
equivalent.

### D7 — A database restore transfers history, not execution authority

Schema v14 records offline restore quarantine and process detachment. `hutch state backup`
creates a private standalone SQLite snapshot and manifest. Restore validates copied bytes and
history in a new directory without background workers, then holds submissions/claims and
records old attempts as Needs review. Source processes are never signalled. Device sessions,
standing grants and schedules are revoked/paused; an explicit local operator review permits
new work without resuming old work. Files and credentials require separate preservation.
See [ADR-0015](adr/0015-held-database-restoration.md) and [Operations](operations.md).

## Concurrency model

> **Updated (realignment, slices S2-S3).** Ownership is no longer process memory. A run is *claimed* by one atomic SQL statement
> that also enforces the per-bot rule across processes; the owner heartbeats a lease; every owner write carries a fence;
> expired leases already refuse owner writes and cannot be revived by heartbeat; recovery bumps the fence; status changes only through `Store.transition_run` against the
> table in `lifecycle.py`; schedule occurrences are claimed in the same transaction as the run they create. Stop is an intent in
> the database and marks persisted descendants before any cleanup or process signal. Under `serve` and `daemon` each run is its own OS process (`hutch.worker`) in its own session, so a kill is a real
> kill, and a worker outlives a dead supervisor and is adopted by the next one (`HUTCH_EXECUTOR=thread` is an explicit
> compatibility/test mode; `hutch run`, `serve`, and `daemon` use process workers). Event sequence numbers and hash chains are assigned at commit time from the
> database tail, so several processes can safely write one run's transcript. Recovery atomically takes the expired owner and
> increments the fence before process cleanup. Worker and tool records include boot/start identities, and cleanup uses pidfds;
> incomplete cleanup remains nonterminal. Design: `docs/adr/0001-...`, `docs/adr/0003-...`, `docs/adr/0004-...`.
> The measured problems with the old design are in `docs/realignment/baseline.md`.

Each production run has an owned worker process and a supervisor watcher. The worker holds a cancel `Event` and a reference to
the run's approval gate so `stop` unblocks an approval wait immediately. In-process thread execution is only an explicit
compatibility/test mode. The browser owns a distinct persistent profile per bot. A cross-process OS file lease prevents two workers
from opening the same profile; an opted-in local handoff also reserves Hutch's visible-browser lease until that session closes.
Agent typing into conventional sensitive fields is intercepted before input or durable action creation; browser type values are
redacted from event/receipt records. Native HTML form submissions show a bounded destination/method/field-label review and bind
the approval to a page-side digest of current form state, including secret values that never leave the page. A changed form refuses
to submit; selected file uploads and forms without secure digest support fail closed. A visible sensitive field blocks screenshots.
Human password/CAPTCHA/MFA steps pause in the same live profile; Resume checks the page without reloading it. Field detection is heuristic, the Linux desktop handoff is
  experimental, and no real challenge or computer-input handoff is verified. Paired-phone supervision now supports status/transcript
  viewing, approval review, Stop/Resume, and locally enabled starts through passkeys and an explicit route capability inventory; live
  mobile/network validation remains open. Remote computer input and live/non-HTTP browser egress validation remain open. HTTP(S)/WebSocket browser connections use a locally tested DNS-pinning proxy. SQLite access is serialized by an RLock in `Store`, and migration startup is additionally serialized across
processes. Schema v9 stores canonical conversations, user/assistant messages, run links and revocable device sessions; old runs are imported one per legacy
conversation to avoid guessing continuity. Versioned conversation writes and run admission are idempotent and transactional. The
builtin runtime receives a capped snapshot of earlier messages; Studio uses the versioned conversation endpoints. Versioned stop and
approval decisions are also idempotent. Studio message search accepts a bounded query in the body of `POST /api/v1/search/messages`,
returns excerpts rather than full message rows, excludes archived and imported conversations, and filters by Bot; paired Monitor
sessions may search only with the normal origin and CSRF checks. The legacy GET search remains available to local clients. Schema v26
stores a Bot-authored choice prompt and its options with the assistant message and
hash-chained `choice_requested` event in one fenced transaction. A selected answer atomically records the chosen option IDs, adds a
user message linked to the question, and admits the next conversation run under the normal idempotency key. Questions are separate
from approvals and browser/CAPTCHA handoff: they do not change run authority or permissions. A provider response that combines a
choice prompt with other tool calls is rejected as a batch before any of those calls run.

Worker signal listeners and asynchronous process cleanup are owned work: listeners wake on normal
completion as well as Stop, and finalization joins earlier cleanup before its final process check.
The database closes only after the event writer exits. If the writer exceeds the shutdown wait,
closure fails visibly, keeps the connection open and refuses new buffered events; a later close
can complete after the writer unblocks. A completed close is idempotent.

`admission.py` owns one local-inference caller and eight waiters with kernel locks across worker
processes sharing the state directory. Tickets order calls, not entire runs, and never survive
their lock owner's exit as authority. Startup/self-check and generation hold capacity; tools and
human waits do not. Queue position/reason and admitted wait time are persisted. Native Ollama
checks current hardware headroom before generation; estimated fit and resident-allocation credit
are qualified in `docs/models.md`. This is not strict-offline enforcement or control of other
clients of the same model server. `HUTCH_MODEL_SLOTS` no longer widens inference concurrency.

## Purpose-first Bot creation

When the owner has a validated workspace model default or an eligible source-chat model
route, New Bot presents a one-screen quick path. In an active chat, the latest user
request is already the draft instruction; **Make a bot** binds the exact message the
owner selected. The owner reviews the request and suggested Bot name without having
to describe the same work again. Editing instructions stays optional. From an empty
chat, the owner can describe a new responsibility. Browser-local naming suggests a
professional name and stable address; it makes no model request. Quick creation stores
managed workspace, no tools, no schedule and ask-first actions. Saving is idempotent
and starts no run. If no route is configured, the owner must choose one before
creation; Hutch has no implicit provider fallback.

**Customize** enters the existing full editor for model/inference/workspace, tools,
memory, schedules, usage limits, optional browser handoff, YAML and final review.
Import still fills an unsaved draft and requires the explicit creation action. A
source-chat request remains linked as provenance. Only earlier messages explicitly
selected by the owner become saved context, and context content never changes Bot
authority. This split shortens the common path without removing controls or silently
granting a tool, connection, credential, schedule or background task.

## Review-only Bot-purpose drafting

New Bot setup may submit one optional refinement to the workspace coordinator. Hutch supplies the exact source user message,
the owner's current purpose draft and only earlier user messages the owner selected from that conversation. The request is bounded
and labelled as untrusted data. It runs as a normal conversation attempt, so existing admission, model routing and budget
reservation apply; it is restricted at the run level to the built-in runtime with an empty tool registry. A provider tool call,
prompt truncation or second response ends the attempt without invoking a tool or silently escalating. The coordinator may ask one
concise choice question for a material missing work detail, then return an editable instruction draft. The owner can answer at most
five questions, one at a time; after that the prompt requires a draft. Choice options and free text are supported. The same browser
can restore the unsent answer, bounded history, or review draft for seven days; this is local browser storage, not server-side or
cross-device synchronization. Expired state is discarded. The source, prior answers and selected context are untrusted data, the run
has no tools. The prompt forbids credential or authority questions, and the client rejects a denylisted set of terms; this is not a
complete detector. The result remains a proposal: the owner edits and explicitly applies it. Bot creation remains a separate confirmation, and this flow cannot alter the proposed Bot's model, account,
memory, workspace or permissions. Required response fields and limits are validated, and malformed output stays unapplied.

## What is deliberately NOT here (yet)

Vector retrieval, webhook triggers, multi-user roles, bounded agent-to-agent collaboration, a cross-run artifact library, remote
browser handoff, authenticated PTY/physical desktop controls and Windows/macOS support — tracked in `docs/roadmap.md`.
Remote phone supervision is optional and remains disabled unless `hutch serve --allow-remote` is explicitly launched. It uses one-use
enrollment, passkey credentials, bounded sessions, a deny-by-default route inventory and per-Bot local Start opt-in. Direct remote
access requires a private interface and trusted HTTPS certificate; a proxy requires exact proxy IP and public-host allowlists. The
recommended Tailscale path forwards Serve to a loopback Hutch listener and still requires Hutch passkey authentication. These boundaries
have automated local and real-Uvicorn HTTPS coverage, but not live tunnel, private-network, iOS/Android, or certificate-renewal
validation. No production remote-support claim exists. Remote computer control and phone browser handoff remain unavailable. The Linux shell has optional,
fail-closed bubblewrap containment; it is not a VM and does not contain every tool or the browser.

The conversation-first shell keeps the bot roster and configuration ownership in one place.
Approvals appear in their transcript and in an explicit cross-bot drawer, using the same card and
v1 decision command. The drawer offers opt-in browser alerts with generic text when the tab is
backgrounded. They omit bot, chat and action details, open the Needs you drawer when selected,
and work only while the Hutch tab stays open; there is no service-worker or push delivery.
Activity and run history are secondary monitoring surfaces; Fleet adds search/state filtering at
ten bots. [Navigation rationale](realignment/navigation.md) records compatibility, evidence and the
limits of the threshold heuristic.

Schema v11 commits resource invalidations with SQLite mutations through AFTER triggers. Typed
`/api/v1/changes` pages/SSE replay identifiers from a durable epoch/committed-ID chain; gaps
require a bounded snapshot whose resource state and cursor share one read transaction. A
one-second safety poll catches silent cross-process commits. Targeted UI refreshes preserve
drafts/settings rather than routing the page. Approval admission includes its review event;
canonical decision summaries cover a missing worker response. Connection-file changes are
excluded. The elected supervisor prunes the content-free invalidation outbox to 50,000 retained
rows every five minutes; older cursors receive `snapshot_required`. Transcript events and user
records are not removed by that policy. Schema v12 introduced recoverable transcript-file delivery. Schema v16 records one durable
delivery intent per committed event batch in the same transaction as canonical events, instead of
running an insert trigger per event. A locked, bounded worker verifies prefixes, preserves damaged files, fsyncs before acknowledgement and
retries after restart. File errors remain visible without changing executor completion; all
SQLite connections use FULL WAL synchronization. See
[ADR-0012](adr/0012-resource-outbox-and-reconciliation.md) and restore precautions in operations.
File-delivery design and limits are in [ADR-0013](adr/0013-recoverable-transcript-files.md).

Schema v13 retains immutable action argument/authority snapshots. Owned writes require an
unexpired fence; terminal transition and uncertain receipt sealing commit together. Reconciliation
is a once-only operator statement with reviewed intent hash, evidence and idempotency, preserving
original status and transcript. Chat surfaces these records inline; the paginated Needs you drawer
keeps older/cross-bot uncertainty reachable. Bounded current model guidance supplements a same-
conversation effect guard. Legacy arguments are not inferred. See
[ADR-0014](adr/0014-immutable-action-review.md).

Builtin provider sessions carry per-run route authority separately from model choice. The
primary selection authorizes its receiving service; a configured hop that changes account,
endpoint, protocol or revision requires outward review. Each call revalidates that authority
and refreshes credential-aware clients. Streaming recovery keeps the first uncertain usage
and reserves another attempt before retrying, using the same transactional account ledger.

Provider protocol claims are published in the versioned `GET /api/v1/compatibility` matrix
([details](realignment/provider-compatibility.md)). Its `supported` state describes a common
request/response contract with recorded fixtures. It is not a live connection or model capability
check: endpoint variants and models can differ in tool use, context, usage and retention. Schema v37
records positive function-tool-call observations only when an owned Bot run with settled or uncertain
usage receives a declared call with valid arguments. `GET /api/v1/model-capabilities` returns that
immutable evidence, bound to a hash of the exact connection/account/protocol/endpoint revision and
model. It is a historical observation, not a future guarantee; no record means unknown. Hutch makes
no extra model probe, and tool-call evidence does not grant action authority.

Each bot stores an inference route mode. `local` filters hosted choices and refuses hosted
per-message overrides, fallback and escalation calls; configured tools keep their own network
policy. `hybrid` retains route review and usage reservations for hosted calls. Experimental
`offline` requires fresh Linux bubblewrap network/PID namespaces that pass a local probe before
configuration or dispatch. Each worker has no host TCP interface, a scrubbed environment, and
read-only empty views over saved connection/key files; a private Unix-socket broker forwards model
requests only to configured numeric loopback endpoints.
Hosted routes, external runtimes, browser and web-fetch tools are refused; shell requires
bubblewrap's private no-network namespace. systemd user scopes enforce resource caps only.
`GET /api/v1/capabilities` reports whether the current host passes. The current Linux development
host passes the local probe and a fake Ollama request completed through the broker inside an
isolated worker. No live local model was available, and Hutch still cannot constrain the separate
model-server process or prove model provenance. See
[ADR-0009](adr/0009-local-inference-and-resource-admission.md).

Owner mutations check both the fence and lease expiry in the write transaction, including the gap
before recovery. Worker events retain their fence through buffering; commit rejects stale events
before projecting replies into canonical history. Recovery and terminal receipts remain uncertain
when a late owner returns; finishing an old action cannot overwrite that outcome.
Provider settlement and unsent-call release use the same ownership boundary. Reservation
identity is immutable, changed duplicate settlements conflict, and uncertain records require
explicit terminal-run reconciliation. All unresolved holds consume the current allowance;
clock rollover cannot establish whether a provider charged the request.
Worker approval admission commits the request and run wait together, draining prior buffered
events through the same ownership check. Failed admission rolls back both without losing
the buffer. Expired execution cannot receive a new approval or standing grant; decisions still
resolve once through compare-and-swap, and full-request rewrites are refused.

## Dynamic workflows (schema migration v59)

A workflow is a **saved, validated plan**, not generated code. The plan schema, the bounded
evaluator and the compiler live in `src/hutch/workflow/`; `plan` is strict data, `expr`
resolves references and conditions without `eval`, and `compile` lowers a plan to stable
site ids, checked references, an envelope and a worst-case node count. Nothing in a plan can
import, read a file or call a function by name.

Identity is layered so that work can be continued without ever being replayed:

```
definition → immutable revision (plan_hash) → instance (wrun_…, stable across attempts)
           → node instance (site_id, instance_key) → step attempt (an ordinary run)
```

`site_id` names the call site (`shape.then.pack`, `each.size`); `instance_key` names *this*
invocation (`item:vendor-7`, `iter:2`). A repeated call site is therefore never one
invocation, and a reordered collection produces the same keys because map identity comes
from the declared `item_key`. A settled node record is reused; it is never re-executed. An
orchestration attempt that crashes is continued by a **new** attempt that skips settled
records - attempts themselves still never resume mid-flight (ADR-0003).

Routines use the existing elected schedule supervisor. A schedule may explicitly pin an
activated workflow definition, one immutable revision, and a validated input object in its
existing JSON record. Linking, activating the saved method, and enabling the routine are
separate owner decisions; saving a later workflow revision does not move an existing pin. At a
due occurrence, one transaction rechecks the routine and pin, writes the occurrence and first
workflow attempt, and advances the existing markers. An idempotent Run now uses ordinary
admission for the same pin and does not consume the next occurrence. The schedule still requires
the local supervisor and host to be running.

Deterministic nodes (transforms, governed tool calls, joins, verification, publication,
questions) run inside the orchestration process through the canonical `steps.call_tool`
seam, so receipts, approvals, artifacts and transcripts are the ordinary ones. Model nodes
become ordinary step runs executed by the existing worker/claim machinery with a frozen
contract: an intersected tool allowlist, validated skill bindings, explicit limits and a
model binding. `Engine._step_bot` re-checks that contract at start, so a Bot edited after
admission cannot widen an old step.

Capacity: an orchestration attempt and its steps form a **workflow lane** (`runs.kind` is
`workflow`/`step`). The claim statement admits a Bot's workflow beside its interactive work
and keeps one workflow per Bot; step runs share their attempt's global slot and are bounded
by the workflow's declared logical concurrency ceiling. When claiming a step, the global-capacity
check discounts that candidate's occupying workflow parent, so `max_live=1` can admit the child
needed to advance the workflow. The parent still counts for unrelated work, which must wait for
an available slot. The current interpreter advances
ordinary nodes and map items sequentially, so that ceiling is not evidence of concurrent
branch dispatch. Inference admission remains the model-concurrency limiter, so a waiting
workflow node never holds an inference seat. Each provider request
reserves against the root workflow's request and token budgets in the same transaction as
the ordinary account reservation. A durable request-start marker distinguishes a released
pre-send hold from a possibly billed request; retries, child steps and continuations all use
the same workflow id. An uncached local model context self-check uses that same reservation
path. Settled calls charge reported tokens; unresolved calls retain their reservation estimate.

When an attempt waits for a person or a child step, it transitions to `waiting_workflow`:
the run remains visible and nonterminal, while its lease and capacity are released. The
supervisor creates a new attempt after the pending question is answered or all children and
owned processes are verified settled. Node and question creation/settlement verifies the
current workflow revision, attempt, run fence and lease in the same database transaction.
The interpreter may collect independent top-level `ask` nodes during one pass, publishing each
under its own durable ID before parking. It holds later work and dependent asks until the current
questions are answered. Studio and paired-phone review project every active question; an answer
is scoped to its ID and does not grant action authority. The owner API returns each question's
revision and attempt identity. Studio derives a waiting ask instance from that record until a node
settles, counts it separately from the planned graph, and ignores question records from an older
revision or attempt. Each question is paired transactionally with a durable `ask` node: creation
commits both the question and `waiting` node state; answer settlement records the answer result on
that node; Stop cancels both records together. This makes pending asks visible in discovered
instances and preserves their terminal outputs. Answer acceptance also updates the durable wait
reason to the remaining question count (or the paused/resume state), so the queue explanation cannot
lag the **Needs you** count. A bounded map can expose independent asks from up to its declared
number of unresolved items while it visits items in stable order; it does not dispatch those items in
parallel. A body can collect independent asks within each item; dependent asks are held, and asks
inside a branch or repeat remain serial.
The process worker permits a child step to remain under its matching parked workflow attempt;
a stop or replacement still fences that child. Stable effect receipts across a crash after
an external effect but before node settlement use a stable identity derived from workflow
revision, site, instance and action slot. Completed receipts replay their bounded result
without dispatch; uncertain receipts refuse a retry until an operator records that the effect
was not applied. Workflow questions also carry revision/attempt identity, so old answers
cannot change a stopped or replaced instance.

Workflow Stop commits cancellation intent for the orchestration attempt and every existing
descendant before any run transitions or process signals. A queued, unclaimed step is stopped
before dispatch, and child admission that races afterward sees the cancelled parent and fails.
Active attempts and children remain nonterminal until their own supervisors verify cleanup.

Dynamic-plan submissions may be bound to a chat by `conversation_id`. The API verifies that the
conversation exists and belongs to the selected assistant before admission, and stores the ID
on the workflow instance. Studio then projects the run only into its owning chat. This prevents
otherwise valid API submissions from disappearing from the chat card because their conversation
metadata was ignored.

Schema v59 adds `workflow_runs.pause_requested`. The owner can request Pause during a running
attempt or a parked wait. Node admission checks the flag in the same transaction as opening a new
node, so the current node may settle but a subsequent node cannot slip through the pause boundary.
Already-owned child work is not cancelled; the workflow remains **Pause requested** until the
attempt releases its lease and the complete child/process tree is verified quiet. Only then does
the projection report **Paused** and enable Resume. A pause request also blocks ordinary continuation
and recovery. If an active attempt disappears during the request, recovery admits one fenced
parking attempt that checks the flag before interpreting a node, then releases its lease. A paused
wait whose children finish stays parked until Resume. Answers remain accepted by durable question
ID while paused; resuming clears the bit and wakes the supervisor to create a fresh attempt when
all ordinary wait conditions are satisfied. Adopting an amendment also clears the bit because the
owner's explicit adoption starts the reviewed revision. Stop clears pause intent and cancels owned
work. Pause/resume mutations require an idempotency key plus the current revision and attempt
generation. The paired-phone projection shows **Pause requested** or **Paused**, but the phone
cannot pause or resume workflows.

Terminal workflow results store node-state counts separately from `output_outcomes`. The
latter groups declared outputs by the evidence and completion available (`verified`,
`partial`, `skipped`, `failed` or `uncertain`); each group points to its durable node record,
which remains the source of the value. `all_settled` joins can continue past their explicitly
named failed or skipped targets and return an incomplete aggregate. `first_success` is rejected
until execution can race branches and cancel and drain discarded work safely.

The owner-only amendment-preview route is read-only. It compares a compiled candidate against
the run's immutable revision and the active attempt ID (the opaque generation token), then
returns field/site changes, refreshed role checks, budgets, parked-attempt and owned child/process quiescence, and per-instance
reuse/invalidation reasons. It currently reuses only settled pure transforms with unchanged
inputs, capability envelope, node semantics and dependencies, and only when every upstream
result is also safe to reuse. Tools, agents, verification, publication, questions and control or
container results are invalidated because the runtime does not yet snapshot enough binding,
evidence or nested-output provenance to prove they remain applicable. A preview neither saves
the candidate nor mutates a run; adoption and history inspection use separate routes.

`workflow_amendment_history` (schema v58) snapshots the prior graph, question records and terminal
result categories before adoption retires invalidated node rows. Adoption is a separate,
idempotent local-owner command that succeeds only after an attempt is parked and its child tree
and recorded processes are gone. Pending questions require an explicit cancellation choice. The
revision update and question/node archival are one transaction; changing the revision fences any
late callback from the prior attempt. The supervisor then admits a normal continuation under the
new revision, retaining only preview-approved pure-transform rows. Adoption currently refuses
live children rather than killing them. The owner-local Studio exposes a declarative plan editor,
read-only preview, reuse/invalidation and budget sections, explicit pending-question cancellation,
and an idempotent adopt action. Paired-phone sessions do not receive these controls.

Roles are gated by evidence, not by a model name: `workflow/qualify.py` resolves the same
route identity the runtime records observations under (`route_identity.route_tuple`). Runtime
tool profiles fingerprint backend/version, checkpoint digest, quantization, full template and
tokenizer hashes, protocol/parser, effective context, decoding settings and reported modalities;
that profile participates in compiler identity and in role-qualification records. Schema v56
adds the exact profile hash to qualification records and stores probe campaigns, runs and
requests separately so dispatch reservations survive process restart. The bounded
probe runner accepts only a complete profile for a loopback Ollama 0.40.3 Q4_K_M model, checks
four held-out cases per author/selector role, and records a pass only when all four dimensions
settle successfully. A shared durable ledger limits the campaign to 80 requests, 60,000
estimated/reported tokens and two hours; uncertain dispatches retain their reservations. The
initial profile uses 4,096 context, a 2,048 output cap, streamed JSON requests and CPU-residency
verification. Authoring and selection require evidence for the exact active profile; a changed
setting blocks admission. Worker and verifier roles use their scoped evidence and recorded
caveats; negative evidence blocks. The model-facing `draft_workflow` tool validates and explains
but cannot start anything, and a guessed direct call is refused with its options.

Schema v57 changes only new-assistant defaults: new Bots are Suggest, while migration pins
older Bot documents that omitted the setting to Off. Per-conversation workflow policy is a
separate revisioned record (`conversation_workflow_policies`); a missing override inherits the
Bot mode. Updates are idempotent and compare the expected revision before commit. Auto requires
an activated saved definition and explicit limits for nodes, model requests, tokens, wall time
and fan-out. The conversation override cannot widen that Bot-level scope. Policy changes start
no workflow and the policy route remains owner-local.

Routing (`workflow/routing.py`) is explainable and abstains by default. A `recommend_workflow`
tool is offered only during an eligible local-owner chat turn when the active model's exact
execution profile has selector authority. It rechecks that profile and the live conversation
policy when invoked, then uses task structure and explicit signals; no compulsory classifier
call is added. `off` never proposes or starts; `suggest` returns a review card and never starts;
`auto` may start only a matching activated saved definition inside the Bot's preauthorized
definitions and budget caps. Newly generated plans are not auto-started. The current tested
Qwen3 local profiles have negative selector evidence, so the runtime does not offer this tool
to those profiles.

Studio projects the selected conversation's saved workflow runs through a compact card: the
planned structure comes from the immutable compiled revision, discovered instances and
questions come from durable node/question records, and terminal labels distinguish completed
from independently verified output. Answers address one displayed question ID; saved runs
record the conversation they belong to; Stop compares the run revision before changing state.
Those writes are idempotent. A changed conversation mode is stored separately from the
assistant default and cannot widen it. A route-card projection carries the decision, rationale
and review action into chat; Auto's saved-workflow submission remains idempotent and goes through
ordinary input, role, scope and approval checks. The routing card and its keyboard review action
are browser-tested at 1440, 768, 360 and 320 CSS pixels. The paired-phone workflow projection
uses the existing `monitor` permission for run summaries, safe plan structure, and redacted
instance status; question IDs, question text/options, answers and Stop use the separate `review`
permission. It omits inputs, node results, artifacts, usage ledgers and dynamic expansion keys.
Paired sessions cannot plan, launch, probe, change policy, amend, pause or resume workflows. A monitor-only
session does not request approval or question data. Phone answer and Stop requests use the
existing CSRF and per-credential idempotency checks; browser evidence is in
`docs/realignment/artifacts/workflow-studio/phone/`.

The plan defaults are 40 node instances, 12 actual provider requests, 64,000 reported or
reserved tokens, 900 seconds, fan-out 8 and two repair rounds. The logical worker default is
two; local inference still admits one request at a time. An Auto scope can set a lower cap
for each of nodes, requests, tokens, wall time and fan-out.
