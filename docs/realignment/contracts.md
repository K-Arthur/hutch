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
  `/api/v1/search/messages`, `/api/v1/tasks/runs`, `/api/v1/actions/approvals`, `/api/v1/usage`, `/api/v1/connections`,
  `/api/v1/schedules`, `/api/v1/capabilities`, cross-run transcript pages and stream at `/api/v1/events` and `/api/v1/events/stream`,
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
* Conversation create, message submit, and archive require `Idempotency-Key`. Exact retries return the same resource/run; reusing the
  key with different request content returns 409. An absent key returns 428.
* Conversation history is cursor-paginated with `after` and a maximum page size of 100. Run events keep the existing per-run `seq`
  cursor. Cross-run event pages and SSE use SQLite's committed global event `id`, include the run-local `seq`, and resume from
  `Last-Event-ID`. Each page is bounded to 500 events. If a cursor is ahead of the restored database or falls behind retained
  history, page reads return 409 `snapshot_required`; the stream emits the same event without advancing its SSE ID. Fetch the
  bounded snapshot, continue every non-null `next` URL, then replay after `replay_after` to include changes made during paging.
* Versioned stop and approval resolve commands require `Idempotency-Key`. Approvals also require the reviewed `action_hash`; reuse
  with different arguments conflicts. Resume and legacy bot-run commands do not yet accept keys. Global replay currently retains
  all events; automatic retention/pruning policy remains unimplemented. A missing leading range or a restored database behind a
  client cursor is detected and requires snapshot reconciliation. This stream contains run transcript events; other resource changes
  are not yet published as durable events.
* Pairing codes expire after 60 seconds and are single use. They issue HttpOnly device sessions, hash-only at rest, with a sliding
  30-day expiry. Operators can list/revoke sessions using `hutch pairing list` and `hutch pairing revoke <device-id>`; pairing is
  limited to five failed attempts per source IP per ten minutes. Off-loopback binding requires `hutch serve --allow-remote` and direct
TLS certificate/key files. This has fixture coverage but no phone UI or live network/device validation. A durable outbox for
non-run resource changes, workspace/artifact resources and verified capability records are not available; the marketing site cannot
reach localhost.

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
with `POST /api/v1/pairing/exchange` and `{ "code": "…", "label": "Phone" }`. The response sets an HttpOnly, SameSite=Strict device
cookie and returns only the device id and expiry. Authenticated `GET /api/v1/devices` lists active sessions; `POST
/api/v1/devices/{id}/revoke` revokes one. Direct non-loopback binding requires `--allow-remote --tls-cert CERT --tls-key KEY`.
The code exchange is intentionally the only unauthenticated remote write; it is source-IP rate limited and subject to Origin checks.
The current Studio has no pairing UX, remote interactive control route, or persistent device-session management screen. Use the CLI to
revoke a lost device. Do not expose the listener to the public internet. The marketing site cannot reach localhost.

## Navigation and approval review

Studio is the primary interface; `/api/v1` conversations own its messages and drafts. Bot resources
now expose `active_run_status` and `active_run_status_label` alongside `active_run_id` so callers do
not infer “working” from any active state. Approval list resources include `conversation_id` for
contextual navigation. Approval events include `action_hash`, used by the shared inline/drawer
review card for idempotent v1 decisions. Legacy routes stay valid; the UI uses history replacement
for aliases. See [navigation.md](navigation.md) for the rationale and acceptance scenarios.

Local inference waits use `waiting_resources` with an authoritative `reason` and queue-position
status events. Run `queue_ms` records waits that acquired capacity, including startup; step events
carry their own `queue_ms`, excluded from `overhead_ms`. Interrupted waits without admission are
not included. These fields default to zero in legacy history; no SQL schema upgrade is needed.
Stop expires pending approvals in its cancellation transaction, and later requests persist as
expired. New worker requests are fence-checked. A pending decision is never kept actionable merely
because physical cleanup is still underway.
