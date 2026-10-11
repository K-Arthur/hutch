# Versioned API and frontend contracts

This is the public contract for the local HTTP API and the dashboard. The v1 surface is partial; a resource is marked **landed** only
when server tests cover its behavior. The Studio now selects, archives and submits conversations through the canonical endpoints;
inline approvals and Stop use idempotent v1 commands. Other screens retain compatibility routes.

## 1. Run status values and labels (landed with slice S2)

`status` is the stored value; show the **label**, not the value. `stopped` keeps its name for compatibility.

| status | label | terminal | needs a person | notes |
|---|---|---|---|---|
| `pending` | Queued | no | no | |
| `loading_model` | Loading the model | no | no | |
| `running` | Working | no | no | |
| `waiting_approval` | Waiting for you | no | **yes** | an approval request is attached |
| `waiting_human` | Needs you | no | **yes** | login/password/passkey/OTP, CAPTCHA, MFA or other detected human checkpoint; `reason` and `handoff` describe how |
| `waiting_resources` | Waiting for a free slot or quota | no | no | `reason` says which |
| `recovering` | Cleaning up | no | no | owner lost or cleanup incomplete; recovery deciding |
| `cancelling` | Stopping | no | no | stay visible until `stopped`; never show "stopped" early |
| `succeeded` | Done | yes | no | `verified` is `true`, `false` or `null` |
| `failed` | Failed | yes | no | `exit_reason` explains |
| `stopped` | Cancelled | yes | no | |
| `outcome_unknown` | Needs review | yes | **yes** | an action may or may not have happened; list `unknown_actions` |
| `skipped` | Skipped | yes | no | scheduled occurrence deliberately not run |

The local Linux browser handoff is experimental and opt-in per bot. Sensitive `type` attempts on conventional credential,
one-time-code, payment-secret and token fields are blocked before browser input and before durable action creation. Browser type
arguments are redacted from transcript events and receipts; a pending ordinary field action is bound to a process-keyed fingerprint
and character count rather than plaintext. Screenshots fail closed while a conventional sensitive field is visible. The same owned
bot profile and live page are shown to the person; Resume is bound to the current human-needed event and rechecks the page without
reloading it. CAPTCHA, MFA and site-required checkpoints are not solved or bypassed. These protections do not guarantee detection of
custom/unmarked fields. No real account challenge or physical-device handoff has been tested.

A client that does not know a status must render its label from `GET /api/v1/status-labels` and treat it as non-terminal. This endpoint
is implemented and includes the label, terminal bit, and whether a person is needed. Run resources also carry `status_label` and
`terminal`; show the label (for example, **Stopping**) and keep the run visible until `terminal` is true. If an unknown status arrives
without a terminal bit, keep it visible and reconcile instead of guessing that it finished.

## 2. Authority split

* **Server owns:** status, approval resolution, receipts, permissions, usage, who holds control of a browser/terminal.
* **Browser owns:** drafts, focus, scroll, view filters.
* An optimistic UI may show "sending"; it must never show a tool as executed or a run as done before the server says so.

## 3. Versioned resources, cursors, idempotency, pagination (partial S8)

* Landed local routes: `/api/v1/health`, `/api/v1/status-labels`, `/api/v1/bots`, `/api/v1/conversations`,
  conversation-scoped `/api/v1/conversations/{id}/artifacts`, run-scoped `/api/v1/tasks/runs/{id}/artifacts` and verified downloads,
  `/api/v1/search/messages`, `/api/v1/tasks/runs`, `/api/v1/actions/approvals`, `/api/v1/usage`, `/api/v1/connections`,
  `/api/v1/schedules`, `/api/v1/capabilities`, `/api/v1/compatibility`, `/api/v1/model-capabilities`,
  `/api/v1/preferences/model-defaults`, `/api/v1/workspace/specialists`, `/api/v1/workspace/tasks`, cross-run transcript pages and stream at `/api/v1/events` and `/api/v1/events/stream`,
  reviewed local coding-task records at `/api/v1/code-handoffs`,
  resource change pages and stream at `/api/v1/changes` and `/api/v1/changes/stream`,
  bounded reconciliation at `/api/v1/snapshot`, and partial remote device resources at `/api/v1/pairing/exchange` and
  `/api/v1/devices`. Versioned bot, run and approval lists accept bounded `limit`/`offset` pages; the legacy bot and approval
  aliases keep their prior response behavior.
* **Google Calendar (experimental; account schema v27, Bot capability schema v45).** By default, the local installed-app PKCE flow
  requests read-only Calendar List and event scopes. An explicit separate sign-in can also request `calendar.events.owned`; installed-app
  OAuth does not support incremental authorization. The owner selects one calendar per Bot. `google_calendar_events` returns bounded
  title/time/location fields; `google_calendar_create_event` is installed only for a Bot with a separately opted-in account and explicit
  owner grant on an account-owned calendar. It always obtains exact outward approval, even in auto mode, sends no guests, and offers
  no edit/delete operation. The server checks the returned event ID, title, time instants, description and location before reporting success; uncertain outcomes remain
  unreplayed for reconciliation. Refresh credentials are stored in Linux Secret Service. Google's scope allows broader changes/deletes
  on calendars the user owns; Hutch's selected-calendar/action limits are local boundaries, not provider-enforced scopes. Live consent,
  public OAuth verification and real provider calls remain unverified.
* **Gmail (experimental private preview).** `/api/v1/connections/google-mail` uses a local PKCE connection and requests account-wide restricted
  `gmail.readonly`; it cannot reuse Calendar consent. The owner grants one mailbox to a Bot. Search returns up to ten bounded sender/subject/date/snippet previews. Hutch
  offers the tool only to its built-in runtime in Local inference mode after checking the primary, fallback and escalation routes are
  loopback-only; this keeps previews away from hosted provider models. The local inference service is outside Hutch's isolation boundary.
  Separate `/api/v1/connections/google-mail-send` endpoints use an independent local PKCE account with only sensitive `gmail.send`, a
  user-entered From address, and independent per-Bot grants. The tool prepares one plain-text email to 1–5 recipients, has no attachments,
  CC/BCC, replies or forwards, and requires fresh exact owner approval for each send even in automatic mode. It sends one request and
  never retries a timeout, server error, redirect or unverifiable receipt; those outcomes require a Sent-folder check. Google acceptance
  is not delivery confirmation. Connections can revoke or disconnect sending without changing search access. Public OAuth verification,
  applicable read-scope security assessment and live consent remain unverified; no provider request was used.
* **Outlook Calendar (experimental, schemas v33 and v48).** `GET /api/v1/connections/outlook-calendar` returns typed, credential-free
  account and Bot-grant metadata. Sign-in begins at `POST /api/v1/connections/outlook-calendar/sign-in` and returns a validated
  Microsoft authorization URL; Microsoft returns only to the local loopback callback. Calendar listing, one-calendar-per-Bot
  grant/revoke, and local-account disconnect are exposed under `/api/v1/connections/outlook-calendar`. Disconnect clears Hutch's
  refresh token/grants but does not revoke account-level Microsoft consent. The Bot read tool returns at most 25 events and only
  subject, start, end and location; its grant is rechecked for each invocation. Event creation uses a separate
  `/api/v1/connections/outlook-calendar-write` account, PKCE callback, Secret Service namespace and per-Bot selected-calendar
  grant. It requests delegated `Calendars.ReadWrite`, which is account-wide and permits create/read/change/delete, while Hutch
  exposes only guest-free event creation on that one calendar after exact approval every time. It verifies the created event by
  reading it back and leaves ambiguous writes `outcome_unknown` for reconciliation. No edit, delete, invitation or Strict Offline
  action exists. Live Microsoft consent and Graph writes remain unverified.
* **Outlook Mail search (experimental, schema v35).** `GET /api/v1/connections/outlook-mail` returns typed, credential-free account
  and Bot-grant metadata. `POST /api/v1/connections/outlook-mail/sign-in` starts an isolated local PKCE flow that requests delegated
  `Mail.Read` and `offline_access`; it does not reuse Calendar's credential. The callback is loopback-only, one-use, and scrubbed from
  access logs. The owner grants one mailbox to one Bot. `outlook_mail_search` uses the fixed Graph v1.0 `/me/messages` `$search`
  endpoint, which includes Deleted Items and Clutter, and returns at most ten sender/subject/date/body-preview records. Preview text
  is untrusted and enters the selected model and the run history. A separate send preview uses
  `GET /api/v1/connections/outlook-mail-send`, `POST .../sign-in`, `POST .../grants`, grant deletion, and account disconnect
  under the same resource path. Its isolated local PKCE flow requests delegated `Mail.Send` and `offline_access` and the callback
  is included in OAuth query scrubbing. `outlook_mail_send` is available only to a Bot with an explicit send-only account grant,
  outside Strict Offline mode. Each request is one new plain-text message to at most five addresses, and requires exact outward
  approval of account, recipients, subject and body even in auto mode. It makes one fixed Graph v1.0 `/me/sendMail` POST; timeout,
  server error, redirect or non-202 2xx is `outcome_unknown` and never automatically replayed. `202 Accepted` does not confirm
  delivery. No reply, forward, attachment, CC, BCC, modify or delete action exists. The optional send setup is in Connections
  under Outlook Mail. Removing a grant blocks later calls; disconnect removes the local refresh token/grants but leaves Microsoft consent for the
  account owner to revoke separately. Account consent and live Graph behavior remain unverified.
* **Coordinator specialist handoff, explicit result return, progress markers, and task-only reviewed facts (schema v32).** `GET /api/v1/workspace/tasks?conversation_id={id}&limit=100` returns up to 100
  task records scoped to one coordinator conversation, including source request/answer IDs, the proposed and reviewed briefs,
  assumptions, target Bot/display-name snapshot, route/capability snapshot, child conversation/run IDs, authoritative run status,
  latest successful specialist answer, its truncation flag, exact `result_message_id`, and `checkpoint_count` plus at most the 16 latest content-free `checkpoints`. Each marker identifies the committed child event sequence/type, run status, marker kind, recovery label, opaque decision/artifact reference and time; no event payload, prompt, reasoning, action argument or tool output is returned. `POST /api/v1/workspace/tasks` requires `Idempotency-Key` and carries
  `{parent_conversation_id, source_run_id, source_user_message_id, source_assistant_message_id, target_bot_id, task_brief, assumptions, memory_fact_ids?}`.
  It accepts only the selected coordinator's completed, non-empty source answer paired with that run's user message; no pending
  choice may remain. The user-reviewed brief and assumptions become one user turn in a new specialist conversation. The task's
  run context stays empty unless the owner explicitly selects facts in `memory_fact_ids`: at most eight current approved facts
  scoped to that coordinator Bot or exact coordinator chat, with at most 6,000 serialized characters. Each selected fact is
  snapshotted immutably with value, revision, hash, scope and source display name and returned in `shared_facts`. The specialist
  receives only these snapshots as untrusted task context, never as durable specialist memory. Nothing is preselected; after the
  task is sent, Hutch cannot recall data already sent to a provider, which may retain it under its own terms. The coordinator's
  other history is never copied. The selected specialist's saved route is validated and its
  current credential-free capability snapshot is stored with admission. Changing that Bot's model route, instructions, permissions
  or workspace before execution fails the child visibly before starting a worker. Exact retries return the original task even if
  the provider route later becomes unavailable; changing any request field under the same key returns 409. This is experimental
  one-task dispatch, not a multi-stage plan.
  A specialist that needs a decision asks one bounded conversational question in its own conversation. While that question waits,
  the task projection reports `status: "needs_input"` with `current_run_id` and a `pending_question` object (stable question id,
  question text, selection mode, options, source run and assistant message IDs) instead of a produced result; the task card shows
  **Needs your answer** with the specialist identity and a keyboard-accessible **Send answer** control. The answer uses the
  existing single-resolution `POST /api/v1/conversations/{id}/questions/{question_id}/answer` endpoint, is admitted on the
  specialist's saved route (never the coordinator's switcher override), and starts a new run in that specialist conversation. The
  task's status, `current_run_id`, stop target and latest result follow the conversation's newest run; the original dispatch's
  content-free checkpoint timeline remains the audit journal. A pending question is not an attachable result: the message endpoint
  returns 409 with "waiting for your answer", and the schema-v51 database guard refuses the same insert. A same-bot `delegate_task`
  child cannot ask the owner; a child that ends with a pending question through another path returns needs-input to its parent.
  A coordinator follow-up may include `workspace_task_result_id` and `workspace_task_result_message_id` on
  `POST /api/v1/conversations/{id}/messages`. The server verifies the task belongs to that coordinator chat and that the
  referenced message is the successful assistant result of that task. It snapshots at most 4,000 characters of that exact
  response and its source Bot name into the new user message; the next coordinator run receives it as explicitly marked untrusted
  context. The result IDs and source snapshot are immutable message/export provenance. A result cannot be attached together with
  `reply_to` or a choice response; changed-body idempotency retries conflict, and invalid or cross-chat result references are
  rejected. The attachment shares only text from that exact result: no workspace file, other conversation history, memory,
  credential, or permission is shared. The user may remove the result selection before sending; attachment requires a normal
  explicit send. These one-task fact snapshots do not create a reusable cross-Bot memory grant and cannot be recalled from a
  provider after dispatch.
* `GET /api/v1/usage/reservations?limit=100` lists active and uncertain provider-call reservations. Connection resources expose
  `account_id`, the configured account daily cost cap, measured rolling-window tokens, reserved tokens, and measured/reserved daily
  currency. Keys and provider credentials never appear. These fields are operator estimates where identified; they do not report
  provider-side quota or billing unless the provider supplied it.
  Held values include all unresolved reservations, regardless of their age. Only measured ledger
  usage is windowed; a stale worker cannot settle/release a hold after losing ownership, and
  uncertain usage requires explicit reconciliation against the provider record.
* `GET /api/v1/schedules/control` returns `{paused, updated_at, changed: false}` for the durable
  workspace-wide pause; `PUT` accepts `{paused: boolean}` and returns the same state with `changed`
  indicating whether it was updated. Repeating the current value is a no-op and does not emit another
  resource invalidation. A pause prevents future schedule admissions only; queued and running work
  continues. After resume, retained missed windows are processed according to each schedule's
  `catch_up` policy.
* `GET /api/v1/schedules?bot=&limit=&offset=&preview=` returns a bounded page of each bot's named
  recurring tasks (routines), including stable `id`, `name`, `trigger` (`cron`|`interval`|`once`),
  `cron`, `interval_seconds`, `anchor_at`, `timezone`, `catch_up`, `overlap`
  (`queue`|`skip`|`buffer_one`), `enabled`, `paused`, optional `prompt`, `created_at`, `next_fire`,
  `last_dispatched`, `last_skip`, `blocked`, `preview` (when `bot` is set or `preview=true`),
  `workspace_paused`, and `effective_paused` (true when workspace/bot paused or the task is not
  enabled). Invalid IANA zones never silently become UTC; they surface in `blocked` and suppress
  due admission. Long downtime claims the true newest occurrence; capped missed counts set
  `missed_uncertain` on the claim/dispatch note. A bot can have at most 100 tasks. The workspace
  pause is rechecked inside the transaction that claims the due occurrence and creates its run.
  `PUT /api/v1/bots/{ref}/schedules/{schedule_id}` creates or updates that exact task; trigger fields,
  cron/interval/once constraints, and IANA timezone are validated; prompts are trimmed and limited to
  4,000 characters; an ID already assigned or previously removed returns 409. Saving with
  `enabled=false` is a durable draft and does not admit occurrences. `POST .../run-now` starts a
  manual attempt (`origin=manual:schedule`) without advancing the last-fire marker.
  `POST .../skip-next` arms a one-shot skip of the next due occurrence.
  `GET .../occurrences` returns a bounded newest-first page of claimed occurrences with run status.
  `DELETE` removes one stream and returns 204; its runs, occurrence claims, and reserved ID remain
  as history. All tasks on a bot share its tools, workspace, limits and permissions, and remain
  subject to the one-active-run-per-bot rule.
* Legacy bot creation's `cron`/`schedule_prompt` fields and bot-update schedule fields remain
  compatibility aliases for the first task. Empty task prompts use the bot's standing `instructions`,
  then the generic workspace-report task if those are empty. CLI task management is available through
  `hutch bot schedules list|add|update|remove|run-now|skip-next`; the older `hutch bot update` options
  edit the first task. Schema v21 adds a persistent schedule-identity registry and reserves each
  removed ID so retries and historical run provenance cannot attach to a newly created schedule.
* `GET /api/v1/compatibility` returns a versioned provider/runtime route matrix. Each route has an implementation state,
  Hutch's request fields, documented omissions, verification boundary, and dated policy/API sources. `supported` means
  Hutch's common request/response contract has recorded tests; it does not certify every provider version, model, tool
  capability, retention policy, quota, or live connection. Schema v37 records a positive tool-call observation only from a
  normal owned run with settled or uncertain shared-account reservation, keyed to its exact connection/account/model/route revision; invalid or undeclared calls do not
  count, no record remains unknown, and the observation is not a guarantee. `GET /api/v1/model-capabilities` returns the
  immutable records with bounded keyset pagination; `direction=desc` returns newest records first and uses the same exclusive
  `after_id` cursor name to page toward older IDs. Connections shows the five newest records when available, and keeps empty and
  unavailable history visibly unknown. No extra capability probe is issued. `hutch connections test` only checks
  authentication/model discovery. Its legacy standalone `--chat` option is refused because that path bypassed the normal
  shared usage reservation and reconciliation contract; use a normal Bot run to exercise model behavior.
* Conversation create, message submit, and archive require `Idempotency-Key`. Exact retries return the same resource/run; reusing the
  key with different request content returns 409. An absent key returns 428.
* Studio's composer model picker scopes a pending alternate route to the current conversation. The override is sent as the message's
  `model` and persisted on the resulting run; it clears only after the message command is accepted, so a rejected/failed send can be
  retried with the same visible choice. The selection survives page reload for that conversation in browser storage and does not
  carry to another conversation. **Save as Bot default** submits a model-only `PATCH /api/bots/{ref}` through the same route and
  inference-mode validation as Settings. It affects later chats and scheduled runs, not an existing run; a regular model choice
  never mutates the Bot setting. Provider/account fallback is not part of either operation.
* `POST /api/v1/bots` accepts the existing typed bot configuration plus `Idempotency-Key`. The bot and creation receipt commit
  together. A first create returns 201, an exact retry returns the same bot with 200, and reusing a key with different JSON or
  colliding with an existing bot returns 409. It creates no conversation turn or run. Guided setup gathers purpose, template,
  model route/inference mode, workspace, tools, ask-first approval policy, limits and optional schedule, then displays these values
  before sending the command. It also proposes an editable human-facing `display_name` that pairs a locally generated teammate name
  with a purpose-derived work role, plus a stable local `name` address derived from that role. Existing teammate names are skipped
  when possible. Studio labels the active chat as an AI Bot so the friendly name does not imply a human operator. The deterministic
  browser-side heuristic makes no model request, and a name change grants no authority.
  API callers may omit `display_name`; the server derives a readable fallback from the stable address. Updating only `display_name`
  preserves routes and old links. `GET /api/v1/model-routes?inference_mode=` supplies current model suggestions; the field remains
  explicit and the create handler validates the chosen route. Route listing may read a configured provider's non-inference model
  catalog, but it does not submit a model prompt or create product state. From Studio, the wizard may include the latest user
  message of the active conversation as a checked, editable purpose draft. The user may also select up to eight earlier user
  messages from that exact conversation; none is selected by default. Assistant replies and messages from other conversations are
  not candidates. The final review shows each selected message, and the selected text is saved as explicitly labeled background in
  the Bot's instructions, where it may be sent to the chosen model on future runs. The selection grants no tools, accounts or
  permissions. The versioned create body requires `source_conversation_id` with either `source_message_id`, one or more
  `source_context_message_ids`, or both. The server accepts only user messages in that exact conversation, rejects duplicate IDs,
  caps selected source text and saved instructions at 20,000 characters, persists content and provenance in the local Bot record,
  and includes selected identifiers in the idempotency digest. When no context IDs are supplied, the canonical digest remains
  compatible with requests from older clients. Bot list/detail responses expose source ids, source Bot, sequence and timestamp
  but omit duplicated `original_request` fields. When that source Bot has a non-mock model route, the wizard
  pre-fills it as an explicitly labelled, editable suggestion; the confirmed route becomes the new Bot's saved default. It does not
  silently fall back or start a run. The current wizard does not yet infer other configuration or ask
  only for unresolved details; name, starter, model/mode, workspace, tools, limits and schedule remain user-reviewed choices.
* `POST /api/v1/bot-configs/preview` accepts a typed Bot-creation body and returns `{yaml, omitted_fields, saved:false}` after the
  same creation validation. Its `hutch.ai/v1` `BotConfig` YAML includes the reviewed setup fields and is marked `Cache-Control: no-store`.
  Provider endpoint URLs, local folder paths, and conversation-source identifiers are excluded. Previewing creates no Bot or run;
  Studio offers it only on the final review step, and creation still requires the separate **Create bot** confirmation.
* `POST /api/v1/bot-configs/import` accepts `{yaml}` up to 64 KiB and returns `{configuration, saved:false}` only after strict
  safe-YAML parsing and Bot-create field validation. It rejects aliases, duplicate keys, unsafe tags, unknown fields, endpoint
  URLs, local folders, conversation sources, command rules and non-supervised authority. The sanitized configuration is
  `Cache-Control: no-store`; it creates no Bot or run. Studio copies it into an editable, unsaved setup draft, and the usual
  step-by-step review and explicit **Create bot** confirmation remain required. Import checks route syntax and policy while
  deferring missing credentials, terms acknowledgement, and Strict Offline host readiness to final creation. Same-name collisions
  are surfaced in the draft.
* **Landed workspace model default.** `GET/PUT /api/v1/preferences/model-defaults` reads or saves a validated `{model, inference_mode}` preference. When no model is supplied in `POST /api/v1/bots`, the workspace route seeds the new Bot; when no inference mode is supplied, the workspace mode does, including when the request names a route. Each explicitly supplied field takes precedence independently. Creation still requires a usable final route. The preference is consulted only for creation and never mutates an existing Bot, conversation or run. An empty model clears the route default and lets each new Bot choose. Invalid route/mode combinations are rejected without replacing the last saved value; Strict Offline additionally requires the host check and a verified local route. Chat-sourced setup suggestions take precedence and remain editable. The response's `configured` flag indicates whether the model route is non-empty.
* `POST /api/v1/tasks/runs` takes `{bot, prompt, rehearse?, model?}` and requires `Idempotency-Key`. The run, task and replay
  response are stored in one SQLite transaction. A new request returns 201; an exact retry returns the same run with `replayed: true`
  and 200, even if a restore hold or provider-route change happened after admission. A changed body or a key reused by another command
  returns 409. New submissions still respect the restore hold and model-route checks. The legacy `/api/bots/{ref}/run` alias remains
  available without versioned idempotency for compatibility.
* Schema v22 adds nullable, database-guarded immutable `runs.parent_run_id` for bounded delegation lineage; schema v23 adds an immutable nullable `delegation_budget_cost_usd` snapshot; schema v24 stores an immutable credential-free `capability_snapshot_json` captured with the root run's pending-to-running transition. The explicit `delegate_task` chat tool is available only when enabled per bot and only through the supervised built-in Strict Offline Linux process executor. Each call opens a fresh outward approval even if the bot's normal approval mode is automatic. Its invocation identity is application-owned — the model step plus the call's position in that response, bound to the task digest — so an exact retry of a call position replays its child while two identical same-turn calls stay distinct; provider call IDs are never trusted as identity. The internal store admission accepts a
  child only from its current live parent fence, retains the same bot identity and conversation, and persists the child task, run,
  parent link and idempotency receipt together. It enforces at most two levels, three direct children per parent over its lifetime,
  and two active direct children. The first child snapshots the top-level parent's execution-time currency limit; nested children inherit
  it even if a later caller supplies a larger value. `reserve_usage` serializes measured usage and reserved/uncertain holds across all
  runs in that subtree in the same transaction as the per-run, bot, and account checks. Legacy runs upgraded from v22 have no invented
  delegation ceiling. Stopping any run also persists cancellation intent for its descendants before cleanup, and a racing child
  submission either appears in that tree or observes its cancelled parent and is refused. The child gets task text only, an empty
  conversation context, no browser or host folder, and a private 0700 per-run workspace. Its built-in runtime is reconstructed from
  the immutable root capability snapshot, so later bot edits cannot widen lineage authority; provider/account and tree-budget checks
  still apply before each model request. Depth is at most two, a parent can create at most three children over its lifetime, and at
  most two direct children may be active. The public tool path is serial, and the default global concurrency of two permits one root
  and one child. Child results return as text to the parent; child files/artifacts are not copied or added to parent context.
  Parent Stop cascades and children remain visible while cleanup is verified. This is a preview, not general-purpose delegation:
  external runtimes, cross-bot work, parallel tool calls, artifact transfer, and recovery continuation after a parent process dies
  between approval and child admission remain unavailable. Legacy runs have no retroactive snapshot and cannot admit delegated work.
* **Coordinator selection and direct chat landed (schema v28).** `GET/PUT /api/v1/workspace/coordinator` reads or selects one existing Bot by ID/address; deleting the selected Bot clears the setting. Bot resources expose `is_workspace_coordinator`. Bot Settings can set or clear the role, Studio opens the selected Bot by default and labels it in the roster and chat header, and every Bot remains directly addressable in its own conversation. Role selection changes no tool grants or account access.
* **Specialist roster (schema v41).** `GET /api/v1/workspace/specialists` returns the selected coordinator, eligible Bot metadata, and `specialist_bot_ids`. `PUT` replaces the roster with `{ "bot_ids": ["..."] }`; the list is capped at 100 unique existing Bot IDs and starts empty after migration. The coordinator cannot be on its own specialist list. Promoting a Bot to coordinator removes that Bot from the list in the same transaction; the prior coordinator is never auto-approved. Deleting a Bot removes its roster entry. New task admission rechecks roster membership in the same transaction that persists the task/run/idempotency receipt, so UI filtering is not an authority boundary. Removing approval blocks future assignments only and preserves existing tasks, runs and conversations. Duplicate/invalid lists return 422, unknown IDs return 404, coordinator overlap returns 409.
* **Reviewed coordinator handoff landed (schema v29–v32, experimental).** The user may select one existing Bot from a completed coordinator answer and send an explicitly reviewed brief/assumptions to a new specialist conversation, provided the Bot is on the approved roster. See the typed `GET/POST /api/v1/workspace/tasks` contract above. The task card in the coordinator chat retains source provenance, target settings, current run status, latest reply and an ordered content-free checkpoint timeline. Schema v32 adds an optional, unchecked-by-default selection of current reviewed coordinator facts; exact values and provenance stay attached to that task and enter only its specialist run as untrusted context. They are not added to the specialist's saved memory, and provider retention applies after dispatch. Schema v34 adds a narrowly gated, owner-confirmed fresh attempt from a safe checkpoint; it does not resume an old worker or claim general recovery. The specialist's own enabled memory/workspace may apply. The user can explicitly attach that exact successful specialist response to a coordinator follow-up. Automatic multi-step planning, cost display, parent-plan cancellation, and external-runtime continuation remain unavailable; no live provider execution is verified.
* **Safe task continuation (schema v34, experimental).** `GET /api/v1/workspace/tasks` includes `continuation_available`, `continuation_reason`, checkpoint kind/event sequence, and a bounded assistant-text preview. `POST /api/v1/workspace/tasks/{task_id}/continue` requires `Idempotency-Key`; it returns 201 for a new continuation, 200 for an exact retry, 409 when the same key has a different request or the checkpoint no longer qualifies, and 404 for missing history. The command has no request body; the idempotency digest binds the command to the source task. Only a terminal `failed` or `stopped` attempt can qualify. Hutch blocks `outcome_unknown`, any recorded tool action, child-run dispatch, another run in the specialist conversation, a pending question, archived coordinator chat, paused Bot, non-built-in runtime, changed/missing capability snapshot, or an assistant checkpoint over 12,000 characters. A task can be continued only once.

  The user must review the task card and confirm a modal that shows the exact reviewed brief, constraints and committed assistant checkpoint (preview bounded to 500 characters). The new linked task gets a fresh run and conversation. Its context contains only the original brief and constraints, plus the committed assistant response wrapped and labeled as untrusted progress; if no assistant response exists, it starts from the reviewed brief. Selected coordinator facts, prior tool results, old conversation history, credentials, approvals and action receipts do not cross. No action is replayed. A new model call may use additional quota. This is a narrow retry of no-effect built-in tasks, not worker/process restoration, and it does not resolve uncertain effects.
* **Remaining cross-Bot contract.** A workspace has one owner-named coordinator Bot with its own direct conversation. Users may also continue to converse directly with every task Bot. Specialists cannot message sibling Bots. A selected child result can be explicitly returned as a source-bound, untrusted text snapshot. Task-only selected facts and reusable owner-granted fact snapshots are implemented separately; artifact grants remain independently scoped. Longer plans still need explicit owner/target, selected context/artifact references, model route, capability snapshot, budget reservation, lineage and idempotency records. Coordinator and specialist routes remain separately saved per Bot; no task-level model override is offered by the current handoff. Prompt refinement cannot grant authority. Parent cancellation and generalized artifact grants scoped to multiple tasks remain open; a specialist's clarifying question is now surfaced on the task card, answered there or in the specialist chat, and never attached as a finished result. This contract is informed by [Grok Bot's message and delegation documentation](../research/grok-bot-product-review-2026-10-09.md), while retaining Hutch's per-Bot workspace and browser isolation.

* **Landed message-reply contract (schema v25).** Each visible Bot-authored reply in Studio has an accessible **Reply to this** control. The composer shows the Bot's user-facing display name (not its internal address) and a bounded excerpt with a remove action; the unsent reference and draft survive reload in that browser. The idempotent send includes `reply_to_message_id`, and the user message preserves the relationship in chat history and export. `GET /api/v1/conversations/{id}/messages/{message_id}` returns an assistant message only from that conversation, with a bounded response; missing and cross-chat IDs share the same 404. A database trigger and transactional admission require the target to be an assistant message in the same conversation. The run receives that explicitly referenced message, labelled as untrusted text, in addition to only the remaining portion of the normal bounded same-chat context. It cannot change the Bot's stored tools, connection, approval mode, account or budget. Hutch never loads another conversation implicitly. Exact retries preserve the relationship across restart; changing the target under the same key conflicts. The quoted-message context is capped at 4,000 characters, with truncation disclosed, and the composer excerpt at 240 characters. This does not claim that untrusted prompt text can never influence a model; executor authority remains enforced by Hutch.
* `POST /api/v1/tasks/runs/{run_id}/resume` takes `{human_event_seq}` and requires `Idempotency-Key`. The run must still be
  `waiting_human` under a live owner lease, and the sequence must match its latest `human_needed` event. Schema v19 accepts one command per wait episode;
  another key for the same event and any stale event sequence conflict. Exact retries replay the recorded result without setting the
  resume marker again, so an old action cannot resume a later login challenge. Studio chat renders Resume only beside the newest
  human-needed event for the currently waiting run, and submits that event sequence with a stable per-wait idempotency key. Older
  human challenges remain in the transcript without an active Resume button. A successful command is shown as requested; the worker
  still reloads and rechecks the challenge before continuing. Server-rendered compatibility pages and legacy resume routes remain
  available without this event-sequence guarantee until they are retired.
* Conversation artifact pages use `limit` 1–100 and an opaque `cursor`, include only verified or explicitly unverified
  artifacts from runs attached to that conversation and bot, newest first, and return `next_cursor` when another page exists.
  The keyset is ordered by event ID descending, then artifact kind ascending, so a page boundary remains stable if newer artifacts
  arrive while browsing and can split two artifact kinds recorded by one event without repeating either. Available downloads use
  the existing run-scoped endpoint, which rechecks the recorded size and SHA-256 through no-follow file access.
  Bot `tool_limits` set the maximum model-visible characters by tool (12,000 by default, zero for no clipping,
  maximum 10,000,000). When a full result is stored, Studio places its download and an inline plain-text source card
  outside the scroll-bounded preview. The legacy `/api/runs/{run_id}/artifacts/{filename}` source-card route applies
  the same recorded size/hash verification and safe file access; versioned artifact downloads retain attachment behavior.
  Missing and legacy-unverified files remain visible without a download link. Active explicit shares also appear in the target
  conversation with the source chat title and a target-bound download URL. Owned artifact entries include a typed `shared_with`
  list of active grants, with target chat titles, so the source chat can manage and revoke each grant. Schema v18 records source
  and target conversation invalidations transactionally for creates and revocations.
* `POST /api/v1/conversations/{conversation_id}/artifact-shares` requires `Idempotency-Key` and a verified source `run_id`, event
  `source_version`, and artifact `kind`. The selected target must be a different, active conversation; the source event must belong
  to a conversation and remain linked to its source run. Hutch verifies hash, size and bytes before committing. A successful
  grant adds a reference to the target's Files list; it does not copy bytes into a workspace or add them to model context. Reusing
  the same key and request replays the original grant, while a changed request conflicts. Both source and target Files lists can
  issue the same target-bound `DELETE /api/v1/conversations/{conversation_id}/artifact-shares/{share_id}`. It requires an
  idempotency key and records a one-way revocation. The audit row is retained, the share-specific content URL returns 404, and
  the source run's own download remains available.
  These are user-selected cross-chat references, not a general library, automatic bot-to-bot sharing, or a substitute for the
  still-unimplemented delegation artifact contract.
* Conversation history is cursor-paginated with `after` and a maximum page size of 100. Run events keep the existing per-run `seq`
  cursor. Cross-run event pages and SSE use SQLite's committed global event `id`, include the run-local `seq`, and resume from
  `Last-Event-ID`. Each page is bounded to 500 events. If a cursor is ahead of the restored database or falls behind retained
  history, page reads return 409 `snapshot_required`; the stream emits the same event without advancing its SSE ID. Fetch the
  bounded snapshot, continue every non-null `next` URL, then replay after `replay_after` to include changes made during paging.
* Versioned stop, run-create, human-resume and approval-resolve commands require `Idempotency-Key`. Approvals also require the reviewed `action_hash`; reuse
  with different arguments conflicts. Legacy resume and bot-run commands remain compatibility routes without versioned idempotency. Global replay currently retains
  all events; automatic retention/pruning policy remains unimplemented. A missing leading range or a restored database behind a
  client cursor is detected and requires snapshot reconciliation. This stream contains run transcript events.
* Schema v11 publishes content-free resource invalidations through `/api/v1/changes?cursor=...&limit=200`
  (maximum 500). Each page returns `changes`, opaque `cursor`/`high_water` and `has_more`.
  Changes contain resource/id, operation, timestamp and contextual bot/run/conversation IDs.
  They exclude message/argument/fact content and secrets. Fetch authoritative resources after an
  invalidation; never infer their current state from the operation. Routine lease/device touches
  do not publish changes; connection files and unimplemented workspace/artifact resources are excluded.
  SSE carries the page as `event: changes`, using the page cursor as its ID. `Last-Event-ID` wins
  over the initial `cursor`, including invalid headers which require reconciliation. Missing
  history, malformed/foreign/future cursors return 409 `snapshot_required` on pages, or the same
  event without an ID before closing SSE. Fetch a snapshot and its remaining resource pages,
  then replay from `change_cursor`; this cursor shares the snapshot's read transaction.
  A new client starts with a snapshot; migration does not invent historic invalidations.
  The elected supervisor trims this content-free outbox to at most 50,000 rows every five minutes.
  A cursor older than the retained boundary gets 409 `snapshot_required`; the global run-event and
  transcript history is not pruned by this policy. A restored v11-or-newer history needs epoch
  rotation before services/clients restart; see [operations](../operations.md). Schema v12 adds the `transcript_mirrors` resource,
  with run context, for delivery/error invalidation. A separate queue delivers JSONL files.
  Run resources expose `transcript_mirror` with `target_seq`, `delivered_seq`, `pending`,
  `error` and transient `worker_error`. These describe file delivery, not executor status.
  A Done run with a pending file keeps its completion label and canonical database answer.
  Schema v16 removes the per-event enqueue trigger: the canonical event writer advances or creates
  one delivery intent per committed batch in the same transaction. While delivery is pending,
  readers derive the latest target from committed events and the acknowledger rechecks the tail
  before clearing pending state.
* Schema v42 replaces the experimental bearer-device session with passkey credentials and short-lived database-backed sessions.
  Pairing codes remain single-use and expire after 60 seconds. The code exchange issues only a five-minute enrollment cookie, which
  can mint at most 16 registration challenges; a verified WebAuthn registration creates a revocable credential. Authenticated
  sessions expire after 30 minutes idle or eight hours absolute. Local operators use `hutch pairing list` and
  `hutch pairing revoke <credential-id>` to inspect/revoke credentials and all
  associated sessions. Synced passkeys are supported, so these credentials do not establish a physical-device identity.
Workspace task records and workspace model defaults are available through `/api/v1/workspace/tasks` and
`/api/v1/preferences/model-defaults`; these are not general workspace filesystem-management endpoints. Positive, passive tool-call
observations are available through `/api/v1/model-capabilities`, scoped to the exact connection, account, model and route revision.
No observation means unknown; this endpoint is not a live guarantee. The anonymous marketing site cannot reach local account state.
Conversation artifact discovery and explicit artifact-share grants are implemented separately.

* **Reviewed OpenCode coding handoff (experimental, schema v39).** `POST /api/v1/code-handoffs` requires `Idempotency-Key` and
  `{conversation_id, source_run_id, source_user_message_id, source_assistant_message_id, task_brief}`. The source messages must
  be the exact user request and successful assistant response from one completed run in that conversation. The Bot must point to
  an existing Git repository through `workspace_mode=folder`; Hutch verifies the local OpenCode CLI contract and pins the current
  Git root, common directory and commit. The proposed assistant text is retained as an editable suggestion, and `task_brief` is
  the exact owner-reviewed text sent to OpenCode. The created record and its request/project identity are immutable. Reusing a key
  with the same request returns the original record; changed input returns 409. `GET /api/v1/code-handoffs?conversation_id={id}&limit=100`
  lists bounded status records for that chat. It does not expose host filesystem paths or credentials.
  `hutch code run {id}` is a separate, owner-invoked Linux TTY action. It creates a new Git worktree from the pinned commit and
  launches the installed OpenCode mini CLI with a private task profile, isolated session database and a 20-step ceiling; it never
  uses `--auto`. The CLI keeps its own sign-in, provider/model choice and usage pool. Hutch does not broker its permission prompts,
  sandbox commands the owner approves, enforce a hard spend cap, apply changes to the source folder, or publish the result. A
  visible task record stays in `launching`, `running`, `stopping` or `cleanup_incomplete` until process cleanup is checked. Each
  task process group is tied to a boot ID, PID start time, session and process group; reconcile never signals a reused identity.
  The user reviews the retained local branch before applying any changes. OpenCode project-plugin directories fail closed while
  upstream behavior remains unresolved. This does not enable OpenCode or Pi as Hutch-managed chat runtimes. Live provider sign-in,
  model execution, permission UX and paid usage are unverified; see the dated [handoff research](../research/opencode-coding-handoff-2026-10-09.md).

## 4. Frontend acceptance items taken from the evidence ledger

| From | Requirement |
|---|---|
| C2 (Open WebUI #30055) | A pending approval or user question must be visible on **every** view and mode, including full-screen overlays, with a visible count. If the request expires, show the cancellation; the source report's 60–240s timeout is a recovery path, not a substitute for surfacing the request. |
| C3 (Open WebUI #31656) | On phones, closing a menu must not move focus into a text field (no keyboard pop-up). |
| A1, A3 | A person can open the live session and take over; the UI says who holds control. |
| ADR-0003 | `cancelling` and `outcome_unknown` are first-class and explained in plain language. |

## 5. Conversation resource (landed; broader S6 work pending)

`POST /api/v1/conversations` takes `{bot, title}`. `POST /api/v1/conversations/{id}/messages` takes `{prompt, model?, rehearse?}`.
Both require an `Idempotency-Key`. The server atomically appends the user message, stores a bounded history snapshot on the run, and
admits the run. `GET /api/v1/conversations/{id}?after=0&limit=100` returns ordered messages, `last_seq`, and `has_more`; default and
maximum page size is 100. `GET /api/v1/conversations` accepts bounded pagination and `include_archived=true`; the default omits
archived chats. `POST /api/v1/conversations/{id}/archive` hides/restores a conversation and retains its messages and run receipts.
`PATCH /api/v1/conversations/{id}/preferences` requires `Idempotency-Key` and accepts one or more of `pinned`, `unread`, and
`section` (up to 40 normalized characters; null clears it). Opening a chat clears unread through its read sequence; an assistant
message arriving after that sequence marks it unread again. These preferences are persisted and emit content-free conversation
invalidations. `PATCH /api/v1/conversations/{id}/title` also requires `Idempotency-Key`, accepts a nonblank normalized title up to
120 characters, and preserves the transcript and other preferences. Reusing an idempotency key with a different payload returns
409. `GET /api/v1/search/messages?q=...` performs explicit FTS5 search over non-legacy conversations only; retrieved text is not
automatically added to a model prompt.

Studio places chat switching and infrequent conversation organization in one accessible options menu: new, rename, pin/unpin,
mark unread/read, move to a named section, and a nested More disclosure for task-template download, reviewed local export, and
archive/restore. The task-template JSON v1 contains only an editable name (up to 80 characters) and the conversation's first user
request (up to 12,000 characters); later messages, assistant/tool output, files, account grants, and conversation identifiers are
omitted. Import checks the format and bounds, then fills the open chat's draft only. It never sends the prompt or starts a run.
Both template download and conversation export stay on the device; Hutch creates no public link. The selector groups pinned,
named-section, recent and archived chats so archived work remains recoverable. Bot-level pin, section, hide/show, local template
download, safe duplication and settings stay in that Bot's separate overflow menu. Bot duplication seeds an unsaved setup review
from instructions, model route, inference mode, workspace type and limits only; it excludes tools, account grants, schedules,
memory values, provider URLs, local folders, browser handoff and conversation history. Neither menu action starts work by itself.

The local saved-request library has at most 250 entries and is stored in Hutch's SQLite state, so it is included in database backups. `GET /api/v1/task-templates?limit=50&offset=0` returns bounded pages (maximum 100). `POST /api/v1/task-templates` requires `Idempotency-Key` and accepts a normalized name (1–80 characters) and request (1–12,000 characters); it returns 201 for a new item, 200 with the original response snapshot for an exact retry (even if the item was later edited or deleted), and 409 when a key is reused with different content or the library is full. `PUT /api/v1/task-templates/{id}` requires `Idempotency-Key`, both fields and `expected_revision`; a successful retry returns its original response snapshot and stale edits return 409. `DELETE /api/v1/task-templates/{id}?expected_revision=N` requires an idempotency key and the current revision; stale or missing items are rejected. Migrations create the table through SQLite's backup-before-upgrade path.

The Studio **Saved requests** dialog searches, edits and deletes these owner-local entries. Choosing **Use request** only fills the active conversation draft and requires the user to press Send separately; it starts no run or provider call. **Save reusable request** reviews the first user-authored message before adding it. The separate **Download task template** action and version-1 JSON importer remain available for explicit file portability; import also fills only the draft. The saved library has no public/team sharing, slash-command aliases or typed-placeholder substitution. Paired-phone routes do not grant access to the library.

`POST /api/v1/conversations/{id}/bot-purpose-drafts` takes
`{source_message_id, purpose, context_message_ids, clarification_history}` and requires
`Idempotency-Key`. It is available only from an unpaused built-in workspace coordinator conversation. The source must be a user
message in that conversation; each selected context ID must name a unique earlier user message from the same conversation, with
at most eight IDs. `clarification_history` defaults to an empty list and is bounded to five `{question, answer}` turns; each
question is limited to 1,000 characters and each answer to 4,000. Source, purpose, selected context and clarification history are
limited to 20,000 combined characters and the safely encoded model context to 24,000 characters. Later messages, assistant replies
and other chats are excluded. Hutch admits an ordinary
conversation run that uses the coordinator's saved route/fallback and usage reservation, but persists `tool_access=none` for that
run; provider tool calls cannot execute, and prompt truncation does not silently drop context or trigger escalation. This endpoint
returns the normal run resource (201 when created, 200 on an exact replay); reusing a key with changed input returns 409. The model
is instructed to return exactly one of `{"kind":"question","question":"…","options":["…","…"]}` or
`{"kind":"draft","instructions":"…","assumptions":["…"]}`. The browser checks required fields, size limits and option count,
and rejects questions/options containing a denylisted set of credential or authority terms. This is not a complete detector; owners
must not enter credentials in free text. A question supports 2–5 options and optional free text. After five answers the
coordinator is required to draft instead of asking another question. Responses remain review-only: they do not create a Bot or
change authority; the owner applies revised purpose in the client and completes the separate Bot setup review. The same browser
keeps the exact source draft, choices, user-provided answers and proposal in local storage for at most seven days and validates
it when restoring. The UI warns owners never to enter credentials; this is not a credential vault. State is not synchronized to
the server or another device.

Schema v8 imports each historical run into its own legacy conversation. It does not infer continuity or combine contexts. The
Studio lets the operator select these imported threads; the builtin runtime receives up to 12 prior messages and 16,000 characters.
External runtimes do not consume this history.

Conversation lists/detail expose `active_run_id`, `active_run_status` and
`active_run_status_label`, chosen across all attached attempts. Executing/waiting work takes
precedence over queued turns. This target is scoped to the conversation and independent of
message pagination. Chat binds header Stop to that ID and keeps the active attempt visible
inside its six-attempt window. Failed attempt refresh retains prior details with a Retry
notice; it cannot turn a known wait into completion or hide the primary control.

`GET /api/v1/conversations/{id}/export` downloads `hutch-conversation-export.json` as
`hutch-conversation-export-v1`. Its manifest says the file contains only whitelisted conversation
metadata and ordered message text/run provenance. Stored provider credentials, tool/action receipts,
workspace contents, artifact bytes, and memory records are excluded. Message text is copied verbatim;
the export warns users to review it before sharing because sensitive text typed into a chat is not
automatically redacted. The consistent snapshot is capped at 10,000 messages, 2 MiB of source data,
and 16 MiB encoded JSON. Larger histories receive HTTP 413 and should be retrieved through the
paginated conversation API. Studio's composer menu presents this scope before starting the download.

## 6. Phone supervision (partial, experimental)

Remote access is off unless the operator starts `hutch serve --allow-remote`. Configure a single canonical HTTPS hostname in
`HUTCH_WEBAUTHN_RP_ID`, its exact HTTPS origin in `HUTCH_WEBAUTHN_ORIGIN` (no path or trailing slash; include any non-default port),
and the same hostname without a port in `HUTCH_ALLOWED_HOSTS`. Direct access binds only to a private LAN or Tailscale address with a trusted certificate; wildcard
and public binds are refused. The recommended Tailscale setup forwards `tailscale serve --bg 8787` to Hutch on loopback with
`HUTCH_TRUSTED_PROXIES=127.0.0.1/32`. Verify `tailscale serve status` and `tailscale funnel status` separately; the Hutch port must
appear only under Serve. Funnel is public when configured, and the same port cannot be served by both. Current Tailscale [Serve](https://tailscale.com/docs/features/tailscale-serve)
and [Funnel](https://tailscale.com/docs/features/tailscale-funnel) pages disagree about whether Funnel is enabled by default; inspect
the node's actual status and effective policy instead of assuming a default. New tailnets start with an allow-all policy, so restrict
the host and port to operator devices. Enabling Tailscale HTTPS publishes the
machine and tailnet DNS names in public certificate transparency logs. For LAN access, firewall the one private interface and use a
certificate trusted by the phone.

The local host runs `hutch pairing create` to display a 60-second one-use code. `hutch pairing create --allow-start` includes Start
capability in the enrollment. `POST /api/v1/pairing/exchange` accepts `{ "code": "…", "label": "Phone" }` over exact same-origin
HTTPS and returns an HttpOnly, SameSite=Strict five-minute enrollment cookie; the response contains no bearer session token. The
browser uses `POST /api/v1/passkeys/registration/options` and `/verify` to create a user-verified passkey. Login uses the corresponding
`/api/v1/passkeys/login/options` and `/verify` endpoints. Registration/login challenges are single-use, short-lived, bound to the
cookie flow, RP ID, and exact origin; one enrollment flow can mint at most 16 registration challenges. The endpoint returns 429 at
that limit, and the owner must issue a fresh pairing code. Authenticated sessions use a separate HttpOnly cookie, expire after 30 minutes idle or eight
hours absolute, and can be explicitly logged out with `POST /api/v1/session/logout`. `GET /api/v1/session` reads status without
renewal; only deliberate activity renews idle time. Background polling and SSE do not renew it. Passkey credentials may sync across
authenticators and are not treated as individual phone identity. Local operators list/revoke with `hutch pairing list` and
`hutch pairing revoke <credential-id>`; revocation invalidates all associated sessions and unclaimed runs.

Paired phones receive a deny-by-default exact route-template inventory: Monitor bot/run/approval status and transcript, Review
approvals, and optionally Start. Approval decisions expose only Allow once or Deny; Allow requires the current `action_hash`, and
versioned commands require an idempotency key. Stop and Resume retain current server event checks. Start requires both pairing
capability and local per-Bot `remote_start_enabled`, set with `hutch bot update NAME --remote-start`; the phone cannot choose a model,
tool, workspace, approval policy or other execution override. The server checks current authority before replay/admission and again
before queued work is claimed. Credential revocation or disabling remote start cancels unclaimed remote work; claimed work remains
visible and requires explicit Stop. Device management, Bot configuration, provider connections, schedules, secrets, artifact/export
routes, and computer interaction are unavailable to paired phones.

The transport boundary requires HTTPS, exact Host and Origin checks, SameSite cookies, a session-bound CSRF token and a custom
browser-request header. Owner bearer tokens are rejected remotely. Hutch disables Uvicorn proxy-header rewriting; only an exact
`HUTCH_TRUSTED_PROXIES` host IP can supply one `X-Forwarded-Host`, `X-Forwarded-Proto: https`, and bounded `X-Forwarded-For` chain.
Untrusted forwarding headers are stripped. Remote responses are `private, no-store` and receive a restrictive CSP. SSE rechecks
revocation/expiry while idle at one-second intervals and emits `auth_expired`; the client closes streams and clears private content.
An uncertain command keeps its original idempotency key and is not silently resubmitted.

Automated ASGI, route-inventory, database, browser-fixture, and real-Uvicorn HTTPS tests cover these boundaries. Physical iOS Safari
and Android Chrome, live Tailscale Serve, LAN certificate renewal, and network isolation have not been validated; this remains
experimental and is not a production remote-support claim. Remote WebSockets, computer input, and browser handoff remain unavailable.

## Navigation and approval review

Studio is the primary interface; `/api/v1` conversations own its messages and drafts. Bot resources
expose `inference_mode` (`hybrid`, `local`, or host-gated `offline`) alongside `model`; create and
patch validate routes together. Local mode rejects hosted per-message overrides and fallback
routes while leaving tools under their own network policy. Offline is offered only when
`GET /api/v1/capabilities` reports the Linux worker egress check as experimental/available; it
rejects hosted routes and hosted overrides, withholds browser/web-fetch tools, and requires the
strict shell sandbox when shell is configured. The status is host-specific, and the separate local
inference service may still use the network.
Bot records include `workspace_mode`: `fresh` (default), `managed`, or `folder`. Existing bot JSON
with a saved `workdir` is loaded as `folder` without a schema migration. `managed` uses a private
directory keyed by immutable bot ID; `folder` requires a validated existing `workdir`. Selecting
`fresh` or `managed` clears the active `workdir` reference but never moves or deletes its files.
Bot deletion keeps managed folders, and database snapshots exclude workspace files.
Bot resources also expose `active_run_status` and `active_run_status_label` alongside `active_run_id`
so callers do not infer “working” from any active state. Approval list resources include `conversation_id` for
contextual navigation. Approval events include `action_hash`, used by the shared inline/drawer
review card for idempotent v1 decisions. Legacy routes stay valid; the UI uses history replacement
for aliases. See [navigation.md](navigation.md) for the rationale and acceptance scenarios.

Worker request, waiting status and review event commit in one transaction. Run detail/event
responses include `approval_states`, scoped to review IDs in that run's event window, with
canonical result, deciding actor and resolution time. This overrides a missing worker response
event. Resource replay refreshes chat/roster/attention without rebuilding the composer or
settings form; drafts, focus and review expansion remain browser-owned.

Local inference waits use `waiting_resources` with an authoritative `reason` and queue-position
status events. Run `queue_ms` records waits that acquired capacity, including startup; step events
carry their own `queue_ms`, excluded from `overhead_ms`. Interrupted waits without admission are
not included. These fields default to zero in legacy history; no SQL schema upgrade is needed.
Stop expires pending approvals in its cancellation transaction, and later requests persist as
expired. New worker requests are fence-checked. A pending decision is never kept actionable merely
because physical cleanup is still underway.

## Action receipt review (schema v13)

`GET /api/v1/actions/receipts?run_id=...&unresolved=true&limit=100&offset=0`
returns typed summaries without argument payloads, bounded to 200 records. `reviewed=true`
selects operator-reconciled records. Without a run filter, the operator sees the cross-bot queue.
`GET /api/v1/actions/receipts/{id}` returns the immutable intent, its integrity result and any
separate reconciliation. Intent is at most 4 MiB; legacy `arguments` is `null`, not inferred.

`POST /api/v1/actions/receipts/{id}/reconcile` requires `Idempotency-Key` and exactly:

```json
{"intent_hash":"<64-character saved SHA-256>","outcome":"confirmed_done","evidence":"What the operator checked"}
```

Outcomes are `confirmed_done`, `confirmed_failed` or `not_applied`; evidence is 1–4000 nonblank
UTF-8 characters. A missing key returns 428, invalid body 422, missing record 404 and changed
intent/key or competing resolution 409. The initial record returns 201; an exact replay returns
200. The authenticated device ID, where available, or shared `operator` authority is server-derived.
Only missing/uncertain receipts on sealed runs can be reconciled. Reconciliation executes no
command and changes neither original receipt/status nor transcript. It is a human report, not
independent verification. A new attempt still needs its own permissions.

Run resources add `unresolved_action_count` and `receipt_review_required`. Historical Done runs
can need receipt review; migration does not rewrite their status. Detail includes bounded
`unknown_actions` and `reviewed_actions` previews (five each). Fetch subsequent receipt pages
rather than treating a preview as complete. `/api/v1/usage` adds `unresolved_actions` for the
cross-bot count; content-free `actions` changes invalidate these resources. Chat provides inline
review and Needs you pages older unresolved actions. Original execution error remains inspectable
when all action reports have been recorded.

## Restore review (schema v14)

`GET /api/v1/state/restore?limit=100&offset=0` returns a typed current report and bounded
inventory page. Limits are 1–200 with nonnegative offset; invalid pagination returns 422.
Report is null on an installation without restoration. It contains ID/date, schema, verified
executor/UI fingerprint, validation counts, quarantine counts, excluded scopes and activation
state/evidence. Inventory contains kind, resource ID and prior status, excluding prompts,
arguments, private device labels and permission keys. `execution_held` is authoritative;
`source_processes_stopped=false` and `old_work_will_resume=false` express the actual boundaries.

Health and usage resources add `execution_held`. New work during the hold returns 409 with
`code=restore_review_required`, the restore ID and actionable text. No message/task/attempt is
admitted on that failed request; chat keeps its draft. Supervisor/worker/recovery claims are
also held, so a client-side unpause cannot bypass restoration review. Content-free `state`
invalidations refresh the global notice without rerouting chat. Activation has no HTTP endpoint;
the local `hutch state activate RESTORE_ID --evidence ...` command records review once. An exact
retry is harmless; changed/competing review conflicts. Activation never requeues old work,
unpauses schedules or reinstates grants/devices. The `run_procs.detached_at` marker removes
cleanup authority while keeping identity and `ended_at` evidence unchanged.

State backups/restores are private local commands, not website download or control routes. See
[Operations](../operations.md#database-migration-and-restore) for snapshot scope and cutover.

## Reference facts (schema v15)

`GET /api/v1/bots/{ref}/facts` returns typed reference revisions, with `limit` 1–100,
nonnegative `offset`, literal `query` up to 256 characters and optional `include_archived`.
Default scope is shared facts for this bot. `conversation_id` adds that bot's chat; an unrelated
chat returns 404. `all_scopes=true` is human inventory and cannot be combined with a chat filter.
Only the latest revision for each scope/key appears; history retains older versions. Values are
bounded to 2000 characters and oversized legacy records are explicitly marked truncated.

`POST /api/v1/bots/{ref}/facts` saves an unreviewed human proposal with key/value limits of
120/2000 characters and optional chat scope. Without a chat it is a proposed bot reference.
The required `Idempotency-Key` makes an exact retry return its original proposal; changed reuse
returns 409. Extra actor/status/authority fields are rejected. Runtime proposals instead require
the current execution fence, a live non-cancelled attempt and enabled memory. Their scope is
derived from the persisted run, never a supplied source label.

`POST /api/v1/bots/{ref}/facts/{id}/review` requires `Idempotency-Key`, exact `content_hash`,
`action` (`approve`, `archive`, `share`) and optional note up to 1000 characters. Actor derives
from the authenticated operator/device. Review binds immutable content, scope and revision;
replaced arguments or a different prior decision conflict. An exact decision replays once.
Approval changes eligibility for reference retrieval, not tool permissions or factual validity.
Share creates an approved bot-wide copy and archives the original; an active shared key conflicts
rather than overwriting it. Legacy facts have unknown chat scope and require explicit sharing or
a new scoped proposal. Archive retains content and review history.

`GET /api/v1/bots/{ref}/facts/{id}/history` returns bounded revision pages and associated review
records. A same-Bot copy links its originating sharing decision. Bot settings and chat consume
canonical records; content-free `memory` and `memory_shares` invalidations let clients refresh
without exposing fact values in global event streams. The typed resource enum also includes
schema-v14 `state` changes.
`memory_enabled=false` denies runtime recall/proposals while keeping human inventory and review.
Legacy key deletion is an explicitly labelled archive of all facts with that key for the bot;
permanent deletion/export is not supplied by that compatibility route.

Schema v38 adds a separate, reversible cross-Bot grant for an already approved current fact.
`POST /api/v1/bots/{source_ref}/facts/{fact_id}/shares` takes
`{"target_bot_id":"..."}` and requires `Idempotency-Key`; it returns 201 when created, 200 on an
exact retry, 409 for changed-key reuse, an existing duplicate grant, or a stale/disabled fact,
and 404 when either Bot is unavailable. Both Bots must have memory enabled. The source and
recipient are resolved before the immutable snapshot is written. No prompt, tool permission,
account, workspace or unrelated memory is copied.

`GET /api/v1/bots/{ref}/fact-shares?limit=50&offset=0` gives a typed, bounded page of incoming and
outgoing records to a participant Bot. `DELETE /api/v1/bots/{ref}/fact-shares/{share_id}` requires
`Idempotency-Key`; either participant may revoke, while a nonparticipant receives 404. Revocation
is one-way and retains the snapshot and actor/time for audit. The change feed adds
`memory_shares`; its context contains only source and target Bot IDs, never the fact key or value.

An active grant makes that exact reviewed snapshot available to the recipient Bot's chats through
bounded FTS5 recall. Recall labels its source Bot and grant ID and treats the value as untrusted
reference data. Revisions do not update an existing grant: archiving/revising the source fact or
disabling either Bot's memory removes it from new recall, and a new revision needs a new review and
grant. The chat/settings UI shows incoming and outgoing records and lets either side revoke. The
snapshot lives in the local database and remains in backup history; revocation stops future recall
but does not erase previously submitted provider context, transcript or backups. This grant is an
owner-controlled persistent Bot scope and is distinct from the optional, task-only coordinator fact
snapshot described above.
The older `GET /api/bots/{ref}` has no conversation selector, so its `memory` field exposes
reviewed bot-wide references only. Chat-scoped inventory belongs to the scoped v1 endpoint;
the local CLI remains an operator-wide diagnostic inventory.

`GET /api/v1/bots/{ref}/memory/export` returns an attachment named `hutch-memory-{bot-name}.json`
with `Cache-Control: no-store`. The versioned payload contains the Bot's stable ID/name/display name,
all immutable fact revisions across scopes (including archived and legacy rows), human review/archive
decisions, and all incoming/outgoing share snapshots with current state. It contains no conversation
transcripts/titles, connection credentials, run events, action receipts, workspace files or artifact
bytes. It is plaintext; fact values and review notes may contain personal or sensitive information, so
the owner should review the file before sharing. The response is a
consistent SQLite read snapshot, limited to 10,000 fact revisions, 5,000 shares per direction, 2 MiB
of source content and 16 MiB serialized JSON. Oversize returns 413 with guidance to use the paginated
fact/history/share resources; records are never silently truncated. This is an export of Bot memory,
not a database backup or permanent-delete facility.

## Dynamic workflows (schema migrations v55–v59, owner-only v1 routes)

Workflows are **saved methods, not schedules**: a definition is inert until it is run, and
running it never grants a schedule, a wider permission or a permanent background process. The
existing routine editor may separately link an activated definition to an existing schedule; the
routine then pins the immutable revision and checked input object. The additive `Schedule` fields
do not add a migration.

* Resources: `GET/POST /api/v1/workflows` (definitions), `GET /api/v1/workflows/{ref}` (latest
  revision plan), `POST /api/v1/workflows/{ref}/activate`,
  `POST /api/v1/workflows/validate` (compile + authority + role checks; admits and executes
  nothing), `POST /api/v1/workflows/plans` (submit an inline plan),
  `POST /api/v1/workflows/{ref}/runs` (run the latest revision with no planning call),
  `GET /api/v1/workflows/runs` and `GET /api/v1/workflows/runs/{id}` (instance + attempt +
  node records + questions + the committed structure). Each question includes `revision_id` and
  `attempt_run_id`; Studio scopes pending prompts and question-backed discovered instances to that
  current pair, so an old attempt cannot reappear as actionable work,
  `POST /api/v1/workflows/runs/{id}/stop`,
  `POST /api/v1/workflows/questions/{question_id}/answer` (bound to that one question id),
  and `GET/POST/DELETE /api/v1/workflows/qualifications` (role evidence; an operator
  acknowledgement can only ever unlock a bounded worker/verifier scope).
* Every command requires an `Idempotency-Key`; a replayed submission returns the original
  instance instead of starting a second one. Errors: 428 without a key, 422 for a malformed
  or invalid plan (with `{code, diagnostics}`), 409 when the Bot's authority or a role blocks
  the plan, 413 for an oversized plan, 404 for unknown resources.
* Routine integration: `PUT /api/v1/bots/{ref}/schedules/{schedule_id}` accepts
  `workflow_definition_id`, optional `workflow_revision_id`, and `workflow_inputs`. When linking,
  changing, or clearing a workflow link, it requires an idempotency key; the key receipt and
  schedule document are committed together. The method must already be active, the selected
  revision must belong to it, and the inputs are validated before the link is stored. Omitting the
  revision pins the current latest revision. A later definition save does not move the routine's
  pin. Schedule enabled state is independent and remains an owner choice.
* Scheduled admission uses the existing elected supervisor. In one transaction it rechecks the
  routine, pinned active definition/revision, inputs, workspace pause and expected occurrence
  marker; writes the schedule occurrence, workflow instance, first attempt and stable idempotency
  receipt; then advances the existing schedule markers. Duplicate or stale claims create no second
  occurrence. `POST /api/v1/bots/{ref}/schedules/{schedule_id}/run-now` launches the same pin once,
  returns `workflow_run_id` and `attempt_run_id`, and leaves the next scheduled occurrence
  unchanged. Run-now uses the same idempotency key on retries and resolves an admitted attempt
  before mutable activation checks.
* Identity: definition → immutable revision (`plan_hash`) → instance (`wrun_…`, stable across
  orchestration attempts) → node instance (`(site_id, instance_key)`) → step attempt (an
  ordinary run). A source change is a new revision, never a byte-identical resume.
* Authority: a plan may never declare a tool or skill outside the Bot's own allowlist, and
  `network: local_model_only` refuses a hosted route outright. Role qualification is checked
  at submission, at node admission, and again when a step run starts from its frozen contract.
* Capacity: an orchestration attempt and its step runs form a **workflow lane**, separate
  from interactive work, so a workflow can progress while the person keeps chatting with the
  same Bot; one workflow per Bot runs at a time; step runs share their attempt's global slot
  and are bounded by the workflow's own logical concurrency. Inference admission limits
  simultaneous model use; root budgets count actual provider requests and tokens separately.
* Durability: node records, questions and budgets live in SQLite. A crashed attempt is
  continued by a new attempt that skips every settled node; a stopped or cancelled instance
  is never continued. Attempts themselves still never resume mid-flight (ADR-0003). Questions
  carry the current revision and attempt; workflow actions carry a stable revision/site/instance/
  slot identity, replay completed results without dispatch, and block uncertain retries until
  an operator reconciles them as not applied.
* Root model usage: schema v55 adds `workflow_run_id` and `request_started_at` to provider
  reservations. Every retry and child request reserves request/token allowance under the
  same workflow id before provider dispatch. The marker is written immediately before the
  provider call; a crash afterward preserves an uncertain charge, while a pre-send hold can
  be released. Settled responses charge reported prompt+completion tokens and in-flight or
  uncertain requests retain their estimate. An uncached local context self-check uses the same
  accounting path. Default plan limits are 40 nodes, 12 requests,
  64,000 tokens, 900 seconds, fan-out 8 and two repair rounds; tighter declared or Auto
  limits still apply. Local inference remains one active request.
* Remote: the workflow routes are owner-only (unmapped in the remote capability inventory),
  so a paired phone cannot start, stop or answer a workflow in this revision.
