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
| `waiting_human` | Needs you | no | **yes** | login / CAPTCHA / MFA; `reason` and `handoff` describe how |
| `waiting_resources` | Waiting for a free slot or quota | no | no | `reason` says which |
| `recovering` | Recovering | no | no | owner lost; recovery deciding |
| `cancelling` | Stopping | no | no | stay visible until `stopped`; never show "stopped" early |
| `succeeded` | Done | yes | no | `verified` is `true`, `false` or `null` |
| `failed` | Failed | yes | no | `exit_reason` explains |
| `stopped` | Cancelled | yes | no | |
| `outcome_unknown` | Needs review | yes | **yes** | an action may or may not have happened; list `unknown_actions` |
| `skipped` | Skipped | yes | no | scheduled occurrence deliberately not run |

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
  `/api/v1/schedules`, `/api/v1/capabilities`, `/api/v1/compatibility`, cross-run transcript pages and stream at `/api/v1/events` and `/api/v1/events/stream`,
  resource change pages and stream at `/api/v1/changes` and `/api/v1/changes/stream`,
  bounded reconciliation at `/api/v1/snapshot`, and partial remote device resources at `/api/v1/pairing/exchange` and
  `/api/v1/devices`. Versioned bot, run and approval lists accept bounded `limit`/`offset` pages; the legacy bot and approval
  aliases keep their prior response behavior.
* `GET /api/v1/usage/reservations?limit=100` lists active and uncertain provider-call reservations. Connection resources expose
  `account_id`, the configured account daily cost cap, measured rolling-window tokens, reserved tokens, and measured/reserved daily
  currency. Keys and provider credentials never appear. These fields are operator estimates where identified; they do not report
  provider-side quota or billing unless the provider supplied it.
  Held values include all unresolved reservations, regardless of their age. Only measured ledger
  usage is windowed; a stale worker cannot settle/release a hold after losing ownership, and
  uncertain usage requires explicit reconciliation against the provider record.
* `GET /api/v1/schedules?bot=&limit=&offset=` returns a bounded page of each bot's named recurring
  tasks, including stable `id`, `name`, `cron`, `timezone`, `catch_up`, `paused`, optional `prompt`,
  `created_at`, `next_fire`, `last_dispatched`, and `last_skip`. A bot can have at most 100 tasks.
  `PUT /api/v1/bots/{ref}/schedules/{schedule_id}` creates or updates that exact task; cron and IANA
  timezone are validated, prompts are trimmed and limited to 4,000 characters, and an ID already
  assigned or previously removed returns 409. `DELETE` removes one stream and returns 204; its runs,
  occurrence claims, and reserved ID remain as history. Per-task timing, missed-window policy and
  task prompt are independent. All tasks on a bot share its tools, workspace, limits and permissions,
  and remain subject to the one-active-run-per-bot rule.
* Legacy bot creation's `cron`/`schedule_prompt` fields and bot-update schedule fields remain
  compatibility aliases for the first task. Empty task prompts use the bot's standing `instructions`,
  then the generic workspace-report task if those are empty. CLI task management is available through
  `hutch bot schedules list|add|update|remove`; the older `hutch bot update` options edit the first
  task. Schema v21 adds a persistent schedule-identity registry and reserves each removed ID so
  retries and historical run provenance cannot attach to a newly created schedule.
* `GET /api/v1/compatibility` returns a versioned provider/runtime route matrix. Each route has an implementation state,
  Hutch's request fields, documented omissions, verification boundary, and dated policy/API sources. `supported` means
  Hutch's common request/response contract has recorded tests; it does not certify every provider version, model, tool
  capability, retention policy, quota, or live connection. Per-model tool-use capability records and the opt-in probe are
  still pending; unknown remains unverified and is called out in the route description.
* Conversation create, message submit, and archive require `Idempotency-Key`. Exact retries return the same resource/run; reusing the
  key with different request content returns 409. An absent key returns 428.
* `POST /api/v1/tasks/runs` takes `{bot, prompt, rehearse?, model?}` and requires `Idempotency-Key`. The run, task and replay
  response are stored in one SQLite transaction. A new request returns 201; an exact retry returns the same run with `replayed: true`
  and 200, even if a restore hold or provider-route change happened after admission. A changed body or a key reused by another command
  returns 409. New submissions still respect the restore hold and model-route checks. The legacy `/api/bots/{ref}/run` alias remains
  available without versioned idempotency for compatibility.
* Schema v22 adds nullable, database-guarded immutable `runs.parent_run_id` for bounded delegation lineage; schema v23 adds an immutable nullable `delegation_budget_cost_usd` snapshot. The internal store admission accepts a
  child only from its current live parent fence, retains the same bot identity and conversation, and persists the child task, run,
  parent link and idempotency receipt together. It enforces at most two levels, three direct children per parent over its lifetime,
  and two active direct children. The first child snapshots the top-level parent's execution-time currency limit; nested children inherit
  it even if a later caller supplies a larger value. `reserve_usage` serializes measured usage and reserved/uncertain holds across all
  runs in that subtree in the same transaction as the per-run, bot, and account checks. Legacy runs upgraded from v22 have no invented
  delegation ceiling. This is still a persistence/admission primitive only: no chat tool or public child-run endpoint exists yet, and
  capability snapshotting, lineage cancellation, independent child workspaces, and delegated artifact transfer remain open.
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
  Retention remains manual. A restored v11-or-newer history needs epoch rotation before services/clients
  restart; see [operations](../operations.md). Schema v12 adds the `transcript_mirrors` resource,
  with run context, for delivery/error invalidation. A separate queue delivers JSONL files.
  Run resources expose `transcript_mirror` with `target_seq`, `delivered_seq`, `pending`,
  `error` and transient `worker_error`. These describe file delivery, not executor status.
  A Done run with a pending file keeps its completion label and canonical database answer.
  Schema v16 removes the per-event enqueue trigger: the canonical event writer advances or creates
  one delivery intent per committed batch in the same transaction. While delivery is pending,
  readers derive the latest target from committed events and the acknowledger rechecks the tail
  before clearing pending state.
* Pairing codes expire after 60 seconds and are single use. They issue HttpOnly device sessions, hash-only at rest, with a sliding
  30-day expiry. Operators can list/revoke sessions using `hutch pairing list` and `hutch pairing revoke <device-id>`; pairing is
  limited to five failed attempts per source IP per ten minutes. Off-loopback binding requires `hutch serve --allow-remote` and direct
TLS certificate/key files. The `/pair` page exchanges a code without exposing the token to JavaScript-readable storage. The Connections
disclosure lists sessions, identifies the current device, and lets an operator revoke any active session. This has fixture/browser
coverage, but no live network or physical-device validation.
Workspace-management resources and verified capability records are not available; the marketing site cannot
reach localhost. Conversation artifact discovery and explicit artifact-share grants are implemented separately.

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
maximum page size is 100. `POST /api/v1/conversations/{id}/archive` hides/restores a conversation and retains its messages and run
receipts. `GET /api/v1/search/messages?q=...` performs explicit FTS5 search over non-legacy conversations only; retrieved text is
not automatically added to a model prompt.

Schema v8 imports each historical run into its own legacy conversation. It does not infer continuity or combine contexts. The
Studio lets the operator select these imported threads; the builtin runtime receives up to 12 prior messages and 16,000 characters.
External runtimes do not consume this history.

Conversation lists/detail expose `active_run_id`, `active_run_status` and
`active_run_status_label`, chosen across all attached attempts. Executing/waiting work takes
precedence over queued turns. This target is scoped to the conversation and independent of
message pagination. Chat binds header Stop to that ID and keeps the active attempt visible
inside its six-attempt window. Failed attempt refresh retains prior details with a Retry
notice; it cannot turn a known wait into completion or hide the primary control.

## 6. Remote pairing (partial, experimental)

On the Hutch host, run `hutch pairing create`; the 14-character code is shown once and expires in 60 seconds. Exchange it over HTTPS
by opening `/pair` on the device and submitting `{ "code": "…", "label": "Phone" }` to `POST /api/v1/pairing/exchange`. The response sets an HttpOnly, SameSite=Strict device
cookie and returns only the device id and expiry. Authenticated `GET /api/v1/devices` returns typed active-session records with a
server-derived `current` flag; it marks only the cookie belonging to the requesting device, not an operator token or another session.
`POST /api/v1/devices/{id}/revoke` revokes one session, including the current one. The UI returns a self-revoked browser to `/pair`.
Direct non-loopback binding requires `--allow-remote --tls-cert CERT --tls-key KEY`.
The code exchange is intentionally the only unauthenticated remote write; it is source-IP rate limited and subject to Origin checks.
Connections provides a device-session disclosure with current-device status and revocation; self-revocation returns to `/pair`. The
responsive Studio is reachable to paired browsers, but remote operation is experimental and has only local browser-fixture coverage.
Do not expose the listener to the public internet. Remote browser handoff, authenticated PTY/desktop control and trusted tunnel support remain unavailable; the marketing site
cannot reach localhost.

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
records. A shared copy links its originating sharing decision. Bot settings and chat consume
canonical records; content-free `memory` invalidations refresh chat without exposing fact values
in global event streams. The typed resource enum also includes schema-v14 `state` changes.
`memory_enabled=false` denies runtime recall/proposals while keeping human inventory and review.
Legacy key deletion is an explicitly labelled archive of all facts with that key for the bot;
permanent deletion/export is not supplied by that compatibility route.
The older `GET /api/bots/{ref}` has no conversation selector, so its `memory` field exposes
reviewed bot-wide references only. Chat-scoped inventory belongs to the scoped v1 endpoint;
the local CLI remains an operator-wide diagnostic inventory.
