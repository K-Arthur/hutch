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
    EXT["OpenCode assistant<br/>(owned private server)"]
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
The OpenCode Bot runtime is enabled through an owned private server; see ADR-0007. Pi remains disabled. The reviewed coding handoff remains a separate interactive contract; see the [reviewed handoff contract](realignment/contracts.md#reviewed-opencode-coding-handoff-experimental-schema-v39).

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
tools, workspace, limits and permissions. Runs in the same lane take turns; workflow work may
progress beside interactive chat. The dashboard's Schedules overview lists next occurrences in each task's timezone. A durable workspace
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

### D7b — Grounding is evidence with roles, not a search wrapper

Schema v51 stores investigations, adapter attempts with distinct outcomes, source items with
revisions, claims, evidence links, media artifacts/observations, answer revisions and versioned
stream cursors. Timestamps keep their role (occurred / announced / published / seen / retrieved):
run and transcript timestamps are never the occurrence time of an external event, relative
phrases anchor to their own document or request, and unknown zones stay unknown. Mirrors,
reposts and syndicated headlines collapse into one origin cluster before any corroboration
count; popularity is never treated as independence. The `live_search` and `inspect_media` tools
are opt-in per Bot, read-only outward, and report blocked/rate-limited/disabled/zero-result
states separately. Media frames reach the model only through routes that accept images, with a
record of what was transmitted; C2PA presence is a provenance fact about the file, never a
truth badge. See [Grounding](grounding.md) and the evidence record in
[realignment/grounding-evidence.md](realignment/grounding-evidence.md).

## Concurrency model

> **Updated (realignment, slices S2-S3).** Ownership is no longer process memory. A run is *claimed* by one atomic SQL statement
> that enforces one active run per Bot and execution lane across processes; interactive and workflow lanes are separate, while
> workflow attempts and their step runs share the workflow lane. The owner heartbeats a lease; every owner write carries a fence;
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
compatibility/test mode. The browser owns a distinct persistent profile per immutable bot ID, so rename and name reuse cannot select another account. Legacy name profiles are retained but not automatically imported. A cross-process OS file lease prevents two workers
from opening the same profile; an opted-in local handoff also reserves Hutch's visible-browser lease until that session closes.
Agent typing into conventional sensitive fields is intercepted before input or durable action creation; browser type values are
redacted from event/receipt records. Native HTML form submissions show a bounded destination/method/field-label review and bind
the approval to a page-side digest of current form state, including secret values that never leave the page. A changed form refuses
to submit; selected files need the separate reviewed upload grant and exact byte/destination match. Unsupported forms fail closed. Cookie-state changes invalidate review without exposing cookies. A visible sensitive field in any child frame blocks screenshots. Managed HTTP text downloads are bounded at the pinned proxy before Chromium or disk; ordinary downloads are disabled. See [computer-use](computer-use.md#profiles-iframe-scope-and-governed-files).
Human password/CAPTCHA/MFA steps pause in the same live profile; Resume checks the page without reloading it. Field detection is heuristic, the Linux desktop handoff is
  experimental; controlled login and real native input are verified in disposable sessions, with no live third-party challenge claim. Paired-phone supervision now supports status/transcript
  viewing, approval review, Stop/Resume, and locally enabled starts through passkeys and an explicit route capability inventory; live
  mobile/network validation remains open. Bounded HTTP human step input is locally verified; physical-phone, live-network and non-HTTP browser egress validation remain open. HTTP(S)/WebSocket browser connections use a locally tested DNS-pinning proxy. SQLite access is serialized by an RLock in `Store`, and migration startup is additionally serialized across
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

## Response style (persona)

The owner can save a response style for each assistant beside its standing directions, and choose
this-conversation or next-reply styles from a chat's options. Version 2 profiles separate named
presets (Direct, Warm, Dry Wit), depth (Auto, Brief, Standard, Detailed), and humor (Off, Subtle,
Playful). Presets establish voice and humor defaults but never change depth. `thorough` remains a
readable alias for Detailed; v1 `tone` and `banter` values remain compatible. Existing defaults keep
the prior neutral, lightly playful behavior, and profanity stays off unless someone explicitly selects
careful mirroring. Bounded customization uses 0–100 warmth, directness and formality values; a small
format choice; and a fixed list of habits to avoid rather than arbitrary prompt text.

Unset fields inherit by precedence — current turn, then conversation, then the owner's saved style
for the assistant, then its shipped preset, then Hutch's default — and an explicit "Inherited" clears
a saved value back to that chain. Assistant settings expose preset, depth and humor selectors plus
bounded optional customization for warmth, directness, formality, profanity, answer format and a fixed
set of habits to avoid. Per-field help identifies the effective source; revision-guarded saves refuse a
stale write (409), reload the latest profile and retain only this form's edits for review. Conversation
controls use the same conflict recovery. A next-reply choice applies to one message only, stays in that
browser's conversation-scoped local storage until the next send or removal, and never becomes a durable
preference. Changing a control makes no model request. Fixed written examples show independent voice and depth
choices. **Preview this draft** is a separate explicit action that sends a fixed fictional sample and the visible
candidate style to the configured model; the form keeps the unsaved draft and does not change the saved profile. A
local-only budget endpoint estimates one response before the preview button becomes available.

Each Bot document carries a response-style profile version; legacy documents without the version are read as
version 1. A future-version or invalid style is isolated to that assistant: Hutch keeps the original profile
data for a compatible build, marks the assistant with a readable profile error, does not apply the style, and
fails a new run with `persona_unavailable`. Unrelated assistant data remains readable and saveable, and profile
errors do not take down the assistant roster. Conversation-scoped state also carries its own version and
revision.

Run purpose is recorded separately from tool authority, and `tool_access=none` requires an explicit tool-free
purpose. Review-only Bot drafts retain their restricted proposal instructions and one-response rule. A tool-free
conversational purpose has its own prompt and rejects unexpected provider tool calls without running them; an
answer-rewrite purpose and a persona-preview purpose are separate from both drafts and ordinary conversation.
The engine uses this purpose only for explicit low-risk banter in an interactive conversation when the contextual
plan needs no retrieval or action, and no skill, rehearsal, structured output, recipient draft or delegated run is
active. That path has no tool schemas and skips pending-action context lookup; analytical, current-fact, sensitive,
personal-context and output-constrained requests keep the normal task route. Availability recovery remains governed
by the provider ladder, so this describes the ordinary one-response path rather than a promise of exactly one network
attempt. Answer rewrites require a typed correction (`shorter`, `go_deeper`, or `less_banter`) and a selected
assistant message from a succeeded run in the same conversation. The store snapshots that answer with its original
user request as untrusted, bounded reference data; oversized, pending, failed, missing and cross-conversation targets
are rejected. The rewrite purpose is available only to the built-in runtime, exposes no tool schemas, skips action
context and workspace paths, and refuses any provider tool call. It preserves the original request's safety cues and
output contract, and does not repeat tools or external actions. A completed built-in answer in chat exposes
Shorter, Go deeper and Less banter actions; pending-choice, failed and non-built-in answers do not. The browser
regression verifies answer targeting, keyboard activation, draft and selection retention, reader scroll retention,
and 44px touch targets. It uses a mock route with engine work disabled, so it makes no provider call and says
nothing about provider adherence.

An explicit style preview is admitted through its own idempotency scope and snapshots the draft style with the saved
profile revision it was based on. Revision checks are repeated in the run-admission transaction so a concurrent save
cannot quietly make a stale draft appear current. The built-in preview path uses only the fixed sample, neutral
preview instructions and candidate style; it omits conversation, standing directions, workspace, skills, action
context and tool schemas. It is limited to one non-streaming request, the lower of 128 tokens or the assistant's
configured per-turn output limit, and the configured model only; it does not retry, escalate or fall back. A local
budget endpoint uses a 1,024-token input ceiling and blocks unknown hosted prices and routes without an enforceable
output cap. The output and run record remain local; a hosted model still receives the fixed prompt and style under its
normal provider terms. The browser test uses a fixture runtime to verify explicit admission, unchanged saved settings,
no conversation attachment, responsive layout, focus retention and cancellation. Adapter tests inspect the exact local
payload boundary for Ollama, OpenAI-compatible chat, OpenAI Responses and Anthropic (the first three through captured
HTTP bodies, Anthropic through the SDK message arguments); they verify the response-style system guidance reaches each
adapter without asking a model what it saw. Preview calls opt in to a redacted adapter receipt
that contains only adapter/model, request roles/counts, serialized output cap, tool-schema and structured-output
flags, plus the saved-profile revision and measured step timing. Prompt/response text, credentials, account data,
endpoints and hidden reasoning are omitted. The receipt describes Hutch's serialized request shape before send and
does not prove provider acceptance. Real model adherence and response quality remain unverified.

At run start the engine resolves the layers once and writes a versioned, write-once plan into the
run; a retried start reuses the recorded plan, and unreadable or newer state fails the run with a
`persona_unavailable` reason instead of silently restyling it. The built-in runtime renders the plan
into its system prompt locally — no extra model call is spent on style — and the guidance is
subordinate wording: it never overrides safety, permissions, tool rules, the task, explicit operator
requests or detail needed to act correctly, keeps sensitive topics plain and steady, and lets
playfulness apply only to turns that are themselves clearly playful, re-decided each turn. The v3
run snapshot also records locally resolved intent, depth, audience, grounding needs, humor eligibility,
output contract, bounded diagnostic labels, and the saved-profile revisions. Classification examines
at most 8,000 characters from the current request and whether a prior assistant response exists;
diagnostic labels never copy request text and put sensitive/action cues first. Low-risk eligibility preserves
the selected preset's discretion, while the prompt still asks the model to use humor only when the request
itself is clearly playful. This is deterministic guidance, not a provider-enforced guarantee. Regular corrections can
shape the current response plan when conversation context exists; typed answer rewrites also resolve against their
explicit selected request, including when the answer is older than the recent context window. The rewrite route keeps
existing citations and contracts as references and never performs new retrieval. The
chain is covered by fixture and API tests, a real-engine plan-capture test, and actual-app browser regressions
at 320, 360, 768 and 1440 CSS pixels plus a 720 × 480 effective viewport for 200% reflow at 1440 × 960.
Settings evidence is retained in `docs/realignment/artifacts/persona-ui-v2-2026-10-11/`; rewrite-action
screenshots, a browser trace and request/network checks are in
`docs/realignment/artifacts/persona-rewrite-ui-2026-10-11/`; live-preview captures and a trace are in
`docs/realignment/artifacts/persona-live-preview-2026-10-11/`. Manually inspected screenshots and the exact
evidence boundaries are recorded in `docs/realignment/persona-ui-visual-review.md`. Browser zoom itself was
not controllable through the headless test runner, so the 720px case checks the corresponding effective CSS
viewport rather than claiming a native zoom gesture. Live-model humor, boundary calibration, and provider-side
request receipt remain unverified.

The local rollback switch `HUTCH_ENABLE_ADAPTIVE_PERSONA=0` disables profile resolution and persona guidance
for new runs, leaves ordinary task routing and tool authority intact, and rejects persona edits, previews,
answer rewrites, and feedback. Read endpoints continue to show saved profiles and revisions; the settings UI
becomes read-only. A write-once plan already attached to a run is reused during recovery even if the operator
restarts with the feature disabled. No profile or database repair is reverted, so enabling the flag again
restores saved behavior without migration or data loss. `get_config()` accepts `0/false/no/off` and
`1/true/yes/on`; it defaults to enabled and rejects other values.

## Response style and answer feedback

Schema v53 stores one current, versioned feedback record per assistant message. The owner may rate a completed,
bounded answer Helpful or Needs work and optionally choose one fixed reason. Writes are local-owner-only, require an
idempotency key and expected revision, and never create a run or change response-style settings. A stale revision
returns a conflict; only the latest record is kept, and the owner can clear its rating. Feedback is attached to
paginated conversation messages, excluded from conversation exports, and contains no free text. The built-in chat
shows the controls only for completed built-in answers; disabled external runtime adapters gain no execution path.
See [response-style help](response-style.md) for owner-facing scope and privacy details.

## What is deliberately NOT here (yet)

Vector retrieval, webhook triggers, multi-user roles, bounded agent-to-agent collaboration, a cross-run artifact library, authenticated PTY/personal-desktop controls and Windows/macOS support — tracked in `docs/roadmap.md`.
Remote phone supervision is optional and remains disabled unless `hutch serve --allow-remote` is explicitly launched. It uses one-use
enrollment, passkey credentials, bounded sessions, a deny-by-default route inventory and per-Bot local Start opt-in. Direct remote
access requires a private interface and trusted HTTPS certificate; a proxy requires exact proxy IP and public-host allowlists. The
recommended Tailscale path forwards Serve to a loopback Hutch listener and still requires Hutch passkey authentication. These boundaries
have automated local and real-Uvicorn HTTPS coverage, but not live tunnel, private-network, iOS/Android, or certificate-renewal
validation. No production remote-support claim exists. Bounded human step control uses an owner-only Linux Unix socket to a private worker-thread queue, ephemeral viewer/generation tokens and an independent expiry/revocation watchdog. Human frames/text are excluded from planner history. HTTP threads fence control but never touch Playwright/native objects. Physical-phone and live-network input remain unverified. The Linux shell has optional,
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
bubblewrap's private no-network namespace. systemd user scopes enforce resource caps only. A nested
Offline shell probe and command inherit the outer worker's memory/task scope and add `prlimit` plus
fresh bubblewrap namespaces; neither can reach the host user bus. This avoids a probe requesting a
new host scope from inside the isolated worker.
`GET /api/v1/capabilities` reports whether the current host passes. The current Linux development
host passes the local probe and a scripted Ollama protocol fixture completed a real file-write →
contained shell → file-read workflow through the broker inside an isolated process worker. This
tests transport/tool integration rather than model intelligence. No live local model was available, and Hutch still cannot constrain the separate
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

The computer resource boundary lives in `computer/resources.py` (fresh authority and whole-clean-workspace grant),
`computer/budgets.py` (independent sampled limits), `native/virtual.py` (owned capture/app process lifecycle) and
`computer/frames.py` (cross-instance serialization). Readiness distinguishes implemented isolated KWin prerequisites from
host portal/library discovery: clipboard/AT-SPI actions and other compositor adapters remain absent. The run-state API
binds preview pixels to their recorded surface and that surface's owner; another surface's control event cannot relabel it.
