# Hutch agent / bot / conversation inventory (2026-10-30)

Worktree `/home/kevina/CodingProjects/hutch/.worktrees/agents-bots-conversations`, HEAD `02cf968b`, clean. Method:
`rg` plus bounded `read` ranges over the files and docs named in the brief. Every claim cites path:line. Evidence is
static code/doc reading: no server was started and no suite was run, so runtime behaviour is claimed only where code
or an existing test file states it. `(inference)` marks reasoning not executed; "working-verified" means a named
test asserts the behaviour (read, not run).

## 1. Persistent entities

Schema version is `SCHEMA_VERSION = 1 + len(_MIGRATIONS)` (`store.py:2461`); `_MIGRATIONS` lists `_migrate_2` through
`_migrate_81` plus three delegated modules (`store.py:2453-2460`), i.e. 84, matching `docs/operations.md:599`.
Cross-table rules are mostly enforced by triggers rather than `PRAGMA foreign_keys`.

| Store | Where | Key structure |
|---|---|---|
| `bots` | `store.py:66-70`; `models.py:378` | `id` PK, `name` UNIQUE, `doc` JSON; **no revision column** |
| `runs`, `tasks` | `store.py:79-87`, `269-275`, `331-332`, `584-603`; `71-78` | `id` PK; `status` (`RunStatus`, `models.py:49-64`), `fence`/lease/`sealed`, `conversation_id`, `parent_run_id`, `delegation_budget_cost_usd`, `capability_snapshot_json`; task `kind`/`done`/`state` |
| `events` | `store.py:89-94`, `231-232`, `2252` | `id` AUTOINCREMENT PK; per-run `seq` + `hash` chain (`chain_hash`, `store.py:224`); `event_key` outbox identity |
| `approvals` | `store.py:97-104`, `293-294` | `id` PK, `run_id`, `bot_id`, `status` (`models.py:769`), `action_hash`, `expires_at` |
| `conversations` | `store.py:313-317`, `1306-1309`, `1812` | `id` PK, `bot_id`, `archived`, `is_legacy`, `pinned`, `unread`, `read_seq`, `section`, `persona` |
| `messages` | `store.py:318-323`, `617`, `650`, `749`, `2317-2320` | `id` PK, `UNIQUE(conversation_id, seq)`, `role CHECK ('user','assistant')`, reply/choice/specialist-result refs, `incomplete` |
| `conversation_runs`, `idempotency_keys` | `store.py:324-332` | link PK `(conversation_id, run_id)`; idempotency PK `(scope, key)` + `request_hash`, `response_json` |
| `conversation_questions` | `store.py:631-673` | `status ('pending','answered')`; immutable-definition and resolve-once triggers |
| `workspace_tasks` (+ checkpoints, fact shares, continuations) | `store.py:714-731`, `800+`, `959+`, `1023+` | coordinator-to-specialist; parent conversation `ON DELETE CASCADE`, child conversation/run `RESTRICT` |
| `memory_facts`; `delegated_wait_continuations`; `assistant_home_conversations` | `fact_memory.py:36-58`; `store.py:2268-2279`, `2389-2403` | facts: `revision`, `content_hash`, status proposed/approved/archived, delete refused; wait state enum; home `bot_id` PK + unique conversation |

Pydantic models exist for `Bot`, `Task`, `Run`, `Event`, `ApprovalRequest`, `MemoryItem`, `Schedule`, `Limits`
(`models.py:115,178,378,593,601,754,776,807`); there is **no** `Conversation` or `Message` model, those rows are plain
dicts (`store.py:5131-5145`). Conversation writes buy retry safety from `idempotency_keys`, not a revision column;
`_idempotency_replay` rejects a key reused with another hash or scope (`store.py:4519-4527`).

## 2. Bot lifecycle

Create: `create_bot_idempotent` -> `_create_bot` (`store.py:3238-3301`) inserts bot and receipt in one transaction,
raises `BotConflict` on name/id collision (`store.py:3267-3270`) and re-keys colliding schedule IDs
(`store.py:3286-3301`). `POST /api/v1/bots` digests the body, replays before validation and returns 200 on replay
(`app.py:4304-4324`); legacy `POST /api/bots` remains (`app.py:4430`). Read: `get_bot`/`list_bots`
(`store.py:3583,3441`), `GET /api/bots` and `GET /api/v1/bots` (`app.py:3970,3981`).
Update: `upsert_bot` is a whole-document write — `INSERT ... ON CONFLICT(name) DO UPDATE SET id=excluded.id,
doc=excluded.doc` (`store.py:3393-3397`). There is no bot-level CAS: only `persona_revision` (compare-and-swap at
`store.py:3404-3430`) and `memory_revision` (conflict at `store.py:3321-3330`) are revision-guarded
(`models.py:393,405`). `PATCH /api/bots/{ref}` mutates the loaded `Bot` and calls
`upsert_bot(..., require_no_active_runs=changing_runtime)` (`app.py:4453-4614`, `4603-4607`), so only a runtime switch
is refused during an in-flight run (`app.py:4466-4470`, `store.py:3310-3316`, `docs/bot-config.md:204`). Execution is
snapshotted instead of revisioned: `capability_snapshot` hashes instructions, tools, sandbox, limits and routes
(`engine.py:625-677`), is written once on the move into `running` (`engine.py:1066-1080`) and is immutable by trigger
(`store.py:604-608`); delegated and reviewed specialist runs re-derive from it and fail closed on mismatch
(`engine.py:277-305`). `(inference)` a mid-run edit affects the next run, except persona style, re-read per run
(`engine.py:1040-1055`).

Delete: `delete_bot` removes the bot row, `tool_allows` and `memory`, archives facts and disables channels, keeping
conversations, messages, runs and events (`store.py:4141-4156`). Permanent erasure is the separate governed command
layer (`bot_deletion*`, typed `POST /api/v1/bots/{ref}/deletion-requests`, `docs/bot-config.md:34`).

Archive/restore for bots: **missing**. Nearest fields are `paused`, `pinned`, `sidebar_hidden`, `roster_section`
(`models.py:432-439`); the coordinator may not be hidden or sectioned (`app.py:4461-4467`,
`tests/test_bot_sidebar_preferences.py:42`). Clone/import/export: no server clone (`rg 'duplicat|clone'` finds only
client code and YAML duplicate-key checks); "Duplicate assistant" seeds the new-bot review in the browser
(`app.js:1791,11495-11601`), excluding tools, grants, schedules, memory, provider URLs, folders, browser handoff and
history (`docs/realignment/contracts.md:406`). Bot config YAML is returned **unsaved** (`app.py:4396-4415`); bot
memory has its own JSON export (`app.py:4781-4802`). Credentials live in per-bot grant tables such as
`google_calendar_grants(bot_id PK REFERENCES bots(id) ON DELETE CASCADE)` (`store.py:688-694`), so a duplicate with a
new `bot_id` inherits none (inference).

## 3. Conversations

Create: `create_conversation` writes the row and its idempotency receipt in one `BEGIN IMMEDIATE`
(`store.py:4528-4546`, `_tx` at `store.py:4164-4172`); `POST /api/v1/conversations` returns 201 then 200 on replay
(`app.py:3481-3493`). Assistant home binding is `ensure_assistant_home_conversation` (`store.py:4558-4596`), tested at
`tests/test_home_conversations.py:17-136`.

Submit: `submit_conversation_message` (`store.py:5542-5850`) does everything in one transaction: idempotent replay
(`5562-5565`), ownership/archive checks (`5568-5573`), rewrite/choice/specialist-result validation (`5575-5680`),
bounded context (`5787-5790`, helper `store.py:149`), then `seq = MAX(seq)+1` (`5792-5795`), `messages`,
`conversation_runs`, `tasks`, `runs` (`5815-5825`) and the user `message` event (`5826-5828`). User message, run row and
bounded `conversation_context` commit together (`contracts.md:371-374`). Ordering: `messages.seq` is unique per
conversation and allocated inside the write transaction (`store.py:318-322`, `5792`, `8825`); reads use
`WHERE seq > ? ORDER BY seq` (`store.py:5131-5145`).

Event->message projection: `_insert_events` projects each inserted `message` event whose `role` is `assistant` into
`messages` in the same transaction with the next conversation `seq` (`store.py:8823-8835`), and
`_insert_conversation_message` also writes `conversation_fts` and bumps `conversations.updated_at`
(`store.py:4201-4203`). `conversation-transactions.md` states: "Canonical assistant projection now happens inside
`_insert_events`, in the same SQLite write transaction as its event and any terminal status." Enforced at
`store.py:8823-8835`. Its second invariant, "A repeated terminal transition cannot admit late buffered events from a
stale process; terminal history remains sealed", is enforced by the sealed short-circuit in `append_event`
(`store.py:8715-8717`), by `_worker_events` dropping events for a terminal run or lost lease (`store.py:8922-8939`)
and by `runs.sealed` on terminal transitions (`store.py:7885`). The doc's third statement — that the repair "does
not silently reconstruct already missing historic conversation messages" — matches the code: no conversation-history
reconciliation command exists (`rg 'reconcil'` in `store.py` finds action, usage and session reconciliation only).
Reproduction test: `tests/test_conversations.py:786`.

History: `GET /api/v1/conversations/{id}` clamps `limit` to 100 and returns `messages`, `last_seq`, `has_more`
(`app.py:3546-3556`); single message at `app.py:3558-3566`. Organisation: archive/restore is one boolean endpoint
(`app.py:3878-3891`, `store.py:4786-4807`); `pinned`/`unread`/`section` preferences (`store.py:4809-4850`);
rename <=120 chars (`store.py:4895-4960`, route `app.py:3951-3968`); pagination and title search via
`list_conversations`/`query_conversations` (`store.py:5012-5071`, pinned first, literal substring). Unread compares
`read_seq` with the message high-water mark (`store.py:4836-4840`). Message search is FTS5 over non-archived,
non-legacy conversations (`store.py:5436-5462`); export is a consistent snapshot capped at 10k messages / 2 MiB /
16 MiB (`store.py:4609-4685`, `app.py:3516-3544`). Questions: `create_conversation_question` writes assistant message,
`choice_requested` event and question row in one fenced transaction (`store.py:5464-5520`); resolution is one-shot by
trigger (`store.py:668-673`) and the answer route re-enters submit with option IDs (`app.py:3834-3876`).

Interrupted runs: `_recover_one` fences the orphan, ends recorded processes and decides
`failed`/`stopped`/`outcome_unknown` (`engine.py:1376-1414`), leaving a parked `waiting_child` parent alone
(`engine.py:1404-1409`). No recovery path writes an assistant message (projection only runs from an assistant event),
so `(inference)` an interrupted turn leaves the prompt with no reply and no synthetic apology.

## 4. Runtime

Message -> run: the route builds `Run`/`Task` and calls `submit_conversation_message` (`app.py:3683-3725`). A second,
legacy path builds a run with no conversation through `engine.submit` (`engine.py:133-146`) from
`POST /api/bots/{ref}/run` (`app.py:4859-4870`), the dashboard bot page (`pages.py:286`) and `hutch run`
(`cli.py:1157`).

Admission/concurrency: dispatch claims pending runs under `max_concurrent` (`HUTCH_MAX_CONCURRENT`) with
`claim_run(..., max_live=...)` (`engine.py:181-262`); local-model runs serialise on model slots and parked parents
yield their slot (`engine.py:186-214`). Local inference is a cross-process FIFO of one active caller plus eight
waiters using kernel locks (`admission.py:12,70-150`). Budget: `Limits` (`models.py:178-188`) enforced per provider
call by `admit_and_reserve` in one `BEGIN IMMEDIATE` over run/tree/bot/account token and cost caps plus
warn/pause/ceiling bands (`store.py:10088-10240`).

States and cancellation: 14 `RunStatus` values (`models.py:49-64`), `TRANSITIONS` with absorbing terminals
(`lifecycle.py:17-45`), status changes only through `transition_run` (`store.py:7520-7600`). `request_cancel_tree`
marks every persisted descendant and expires pending approvals before any transition or signal
(`store.py:7957-8005`); the engine signals owned process groups (`engine.py:486-492,557-603`); runs stay
`cancelling` until cleanup is verified (`lifecycle.py:38`).

SSE: one run stream serves both routes (`app.py:5749-5765`) via `run_event_stream` (`sse.py:105-157`) with `retry`,
`batch` (events plus `first`/`last`/`status`), terminal `end`, `auth_expired` and keepalive comments. Resume prefers
`Last-Event-ID` over `?after=` (`sse.py:96-103`, `tests/test_sse_resume.py:82,126`). Also global `events`
(`sse.py:158-210`), resource `changes` with `snapshot_required` (`sse.py:212-260`) and a topic `refresh` stream
(`sse.py:262-278`). Event types are the `EventType` enum: `status`, `message`, `tool_call`, `tool_result`,
`approval_request`, `approval_resolved`, `error`, `log`, `step`, `human_needed`, `human_resumed`, `choice_requested`,
`choice_answered` (`models.py:738-751`). Final answer and duplicate prevention: the builtin runtime emits one assistant
`message` event per terminal answer path
(`runtime/builtin.py:1522,1590,1616,1660,1716,1735`). Duplicates are prevented by application-owned outbox identity
(`store.py:8775-8795`), fence/terminal filtering (`store.py:8922-8939`), the sealed set (`store.py:8717`) and
`cancel_wins` (`engine.py:1311-1320`). There is no content-level dedupe: projection reuses `data.message_id` when
present and otherwise mints an id (`store.py:8828-8830`), so correctness depends on the producer emitting once.

## 5. Delegation

Same-bot `delegate_task` (experimental) is offered only to a supervised process-executor builtin Strict Offline run
(`engine.py:802-805,1109-1112`) and always asks for outward approval, even in auto mode
(`tools/delegation.py:69-88`). `submit_delegated_run` (`store.py:4357-4499`) enforces: `kind='delegated'`, start
`pending`, fenced parent match (`4369-4380`), prompt <=4000 (`4386`), idempotency scope
`run:{parent}:delegations` (`4388`), live parent plus inherited capability snapshot (`4411-4421`), depth <= 2
(`4436`), lifetime children <= 3 (`4439`), active children <= 2 (`4443`), shared parent conversation with **empty**
context (`4466-4468`). The parent then parks: the continuation is written with the move to `waiting_child`
(`store.py:7576-7602`), the worker exits, and `continue_delegated_runs` resumes or cancels after the child tree
settles (`engine.py:1689-1706`). Surfacing returns only the child's final assistant text, refuses `outcome_unknown`
and reports `needs_input` if the child ended with a pending question (`engine.py:860-895`). Stop cancels the child
tree (`store.py:7957`, `engine.py:824-838`) and a child watches parent ownership (`engine.py:846-850`). A parent
cannot complete before its child on this path: the park/requeue handoff (`delegation.md`: the parent
"enters **Waiting for delegated work**, and exits its worker process") keeps it `waiting_child`.

Coordinator -> specialist (experimental, one or two assignments per plan): `POST /api/v1/workspace/tasks`
(`server/tasks_api.py:78-97`) -> `coordinator_tasks.submit_workspace_task` (`coordinator_tasks.py:216-257`). Guards:
parent conversation must be the selected coordinator's and not archived, target must be an approved specialist and
differ from the coordinator (`coordinator_tasks.py:137-155`); source must be a completed non-empty answer of the same
attempt with no pending question (`157-174`); brief <=20k, assumptions <=4k, at most two distinct targets
(`48-77`). Each assignment creates its own conversation, user message, task and `pending` run with the captured
snapshot plus a `workspace_tasks` row (`176-214`). The run is **independent**: `origin='workspace_task'` and
`parent_run_id IS NULL` (`coordinator_tasks.py:61`), so a coordinator answer never blocks on it; the card follows the
specialist conversation's newest run and derives `needs_input` from a pending question (`store.py:6294-6320`). Policy
drift fails the child visibly at worker start (`engine.py:294-305`); plan stop covers all plan runs
(`tests/test_coordinator_tasks.py:98`). Bounds: depth 2, 3 lifetime children, 2 active children
(`store.py:4436-4445`), child steps <=8 and 600 s in the approval detail (`tools/delegation.py:74-78`), inherited
root currency ceiling (`store.py:4424`).

## 6. Frontend

The shell is a static SPA: `/` serves `static/index.html` (`pages.py:179-182`), with `#workspace` aside,
`#roster-list`, `#view`, `#attention-bar`, `#approvals-overview`, `#toast-root`
(`index.html:63,109,148,155,167,185`). Routing: `route()` `app.js:2188-2240`.

- Conversation workspace: `renderChatStudio` `app.js:3229-4361` (shell/composer `3500-3560`, send `4157-4245`); `renderChatFeed` `4652-4904`; `runBlockHtml` `5252-5459`.
- Bot roster and profile: `refreshRoster` `2271-2284`, `renderRoster` `2293-2415`, `rosterRowHtml` `2426-2451`,
  `openRosterActionMenu` `1777-1853`, `editBotRosterSection` `1689-1724`, `promptNewBot` `11495-12710`,
  `renderBotDetail` `8256-9108` (settings, facts, schedules).
- Composer/drafts: `loadDraft`/`saveDraft` `1587-1590`, `messageIdempotencyKey` `203-214`,
  `choiceAnswerIdempotencyKey` `223-234`, `choiceDraftKey` `254-273`; draft keys are per bot (`app.js:1587`).
- Streaming: `subscribeRun` opens `EventSource('/api/runs/{id}/stream')` `4614-4630`; `scheduleFeedRender` `4632-4651`; resource stream `/api/v1/changes/stream` `12766-12806,13254-13258`.
- Task/delegation cards: `workspaceTaskQuestionHtml` `5459-5486`, `workspaceTaskCardHtml` `5486-5571`,
  `prepareWorkspaceTask` `5913-5964`, `submitWorkspaceTaskModal` `5863-5883`, `continueWorkspaceTask` `5679-5718`.
- Approvals/questions/errors: `approvalCardHtml` `6548-6661`, `resolveApproval` `6713-6757`, `choiceCardHtml`
  `6758-6803`, `renderChatEvent` `6804-6854`, `renderApprovalQueue` `7910-7989`, `refreshBadge` `2684-2746`,
  `renderAttention` `2761-2787`; persistent surfaces `index.html:86,155`; `#composer-error`
  `app.js:3769,4224-4232`, whole-view `errorState` `2241-2248`.
- Search/organisation: `openConversationSearch` `1963-2061`, `renderChatLibrary` `2068-2131`,
  `conversationOptionsHtml` `2798-2820`, `renameStudioConversation` `2882-2920`,
  `editStudioConversationSection` `2844-2881`, `prepareConversationTaskTemplate` `2921-2990`.
- Responsive hooks: `wsNarrow = matchMedia("(max-width: 900px)")` with inert/close handling `app.js:2480-2521`;
  enter-to-send off on coarse pointers `app.js:4155`; CSS at `style.css:404,1621,1890,2358,2405`,
  `responsive.css:90-160`, `hutch-composer.css:208,315,370`, `studio.css:132,156,166`.

## 7. Tests (read, not executed)

| File | What it asserts | Note |
|---|---|---|
| `tests/test_conversations.py` | create/idempotency (`:44`), preferences+unread+archive (`:131-151`), FTS (`:196`), library buckets (`:236`), rename (`:277`), reply scoping (`:305`), rewrite (`:420`), export bounds (`:623-718`), choice answer (`:719`), terminal drain (`:786`), context budget (`:803-920`) | broadest conversation contract |
| `tests/test_delegation.py`, `test_delegated_wait.py` | limits (`:694`), tree cancel and racing admission (`:721,749`), lineage/budget/capability (`:298,352`), child cannot ask owner (`:1033,1050`), invocation keys (`:990`), migrations (`:883-939`); fenced child wait and resume (`test_delegated_wait.py:27,78,97`) | same-bot path |
| `tests/test_coordinator_tasks.py` | two specialists per plan (`:48`), duplicate/>2 refusal (`:67`), redirect revision (`:77`), plan stop (`:98`) | coordinator path |
| `tests/test_home_conversations.py`, `test_bot_sidebar_preferences.py` | atomic home, archive semantics, no history adoption (`:17-136`); durable hide/sections (`:17`), coordinator protected (`:42`), bounds (`:53`) | pointers, organisation |
| `tests/test_api.py`, `test_bot_deletion*.py` | bot CRUD (`:913`), v1 create atomic+idempotent (`:955,989`), legacy parity (`:1313`), stats (`:70`); deletion preview/confirm/replay/expiry (`test_bot_deletion.py:76-349`, API `:64-226`) | bot HTTP |
| `tests/test_sse_resume.py`, `test_sse_event_framing.py` | cut/resume, header precedence, restart durability (`:82,126,284,319`); payload framing (`:37-65`) | streams |
| `tests/e2e/` | `test_conversation_navigation.py:13`, `test_persistent_chat.py:9`, `test_delegation_clarification.py:147` | Chromium, mock runtime |

Gaps I could not find a test for (searched names and bodies; bounded, not exhaustive): bot config edits during an
in-flight run other than the runtime switch; conversation restore (`archived: false` is never asserted —
`test_conversations.py:131-137` only archives and lists); an interrupted run leaving an unanswered prompt; draft
isolation between two chats of one bot; multi-child parallelism beyond the two-active bound; live-model quality
(`delegation.md`, "Verification boundary").

## 8. Defects and duplication

- No `TODO`, `FIXME`, `XXX` or `NotImplemented` marker in any file listed in the brief (`rg` returned nothing); only
  `src/hutch/tools/base.py:46` raises `NotImplementedError`.
- Two transcript models coexist: canonical conversations (messages) and events-only runs with no conversation row
  (`engine.py:133-146`, `app.py:4859-4870`, `pages.py:286`, `cli.py:1157`); the latter never appear in chat history,
  search or export, and remain a live second write path (`contracts.md:5` calls them compatibility routes).
- Channels submit through the conversation path (`channels/persistence.py:298`), so a channel thread is a
  conversation excluded from assistant-home adoption via `channel_threads` (`store.py:4573-4575`).
- `submit_workspace_task` returns `run.id, True` on success (`coordinator_tasks.py:257`) but `child_run_id` on replay
  (`:239`); today's only caller ignores it and re-reads with `replay_task` (`server/tasks_api.py:90-97`), so this is
  latent (`inference`).
- Composer drafts are keyed by bot (`app.js:1587`), so two chats with one assistant share one draft; bot config has no
  revision, so a stale settings form can overwrite another tab's save except for persona/memory (`store.py:3303-3400`).

## Capability classification

| Capability | Class | Evidence |
|---|---|---|
| Bot create/read/update/delete | working-verified | `tests/test_api.py:913,955,989`; `store.py:3223-3301,4141` |
| Bot archive/restore | missing | no field or route; only `paused`/`sidebar_hidden` (`models.py:432-439`) |
| Bot duplicate, YAML import/export | partial | client seed `app.js:11495`; unsaved draft `app.py:4396-4415` |
| Conversation create/submit/history | working-verified | `tests/test_conversations.py:44`; `store.py:4528,5542,5131` |
| Rename/pin/section/unread/search/export/archive | working-verified | `tests/test_conversations.py:131,151,196,236,277,623` |
| Conversation restore (unarchive) | unable-to-verify | same method; no assertion found |
| Choice question ask/answer | working-verified | `store.py:5464-5520`; `tests/test_conversations.py:719` |
| Event->message projection, terminal sealing | working-verified | `tests/test_conversations.py:786`; `store.py:8823,8922` |
| Run lifecycle, cancellation, SSE resume | working-verified | `tests/test_sse_resume.py:82`; `lifecycle.py:17-45`; `store.py:7957` |
| Legacy run path (no conversation) | deprecated/redundant | `engine.py:133`; `app.py:4859`; `pages.py:286` |
| Same-bot delegation (`delegate_task`) | experimental | `tools/delegation.py:30-88`; `tests/test_delegation.py:694`; offline gate `engine.py:802` |
| Coordinator->specialist tasks | experimental | `coordinator_tasks.py:216`; `tests/test_coordinator_tasks.py:48` |
| External runtimes / >2 parallel children | missing | `delegation.md` "Verification boundary"; `store.py:4443` |
| Chat, roster, cards, approvals UI | working-needs-improvement (no visual QA here) | `app.js:3229,2293,5486,6548`; `tests/e2e/test_conversation_navigation.py:13` |
| Cross-device drafts | partial | server persists preferences; drafts are local only (`app.js:128-130`) |

## Top gaps by user impact

1. Bots cannot be archived or restored; hiding is only a roster filter, so retired assistants stay reachable everywhere.
2. Bot settings have no revision, so a stale tab can overwrite another save; only runtime switches wait for in-flight runs.
3. Legacy no-conversation runs still exist (`POST /api/bots/{ref}/run`, dashboard bot form, `hutch run`) and never
   appear in chat history, search or export.
4. Drafts are keyed per bot, so switching between two chats with the same assistant carries text across them.
5. Delegation is limited to Strict Offline builtin runs (depth 2, two active children) and coordinator tasks are
   independent records rather than a shared plan, so multi-bot work is preview-grade.
