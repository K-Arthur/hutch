# GAP-REGISTER: personal operations, shared spaces, coding orchestration, shipped workflows, persistent automations

Date: 2026-10-30 (America/Vancouver). Baseline: committed HEAD `989e5bc0`; the Lead's uncommitted
personal-operations slice is treated as in flight, not as a baseline capability. Evidence conventions and
the full current-state trace are in `CURRENT-STATE.md` in this directory. No source is changed by this
register.

Scoring: **impact** 1-5 (user-visible value for the stated initiative), **feasibility** 1-5 (how small and
safe the smallest honest end-to-end slice is in this codebase, including the frozen-file constraint),
**score = impact x feasibility**. Rank is for sequencing, not a commitment; dependencies are called out.
"Smallest slice" means the least code that produces a real, verifiable end-to-end behavior; it deliberately
excludes polish.

Constraint shared by every slice: `store.py`, `models.py`, `app.py`, `app.js` and the generated CSS are
over-cap frozen files (`.file-size-baseline.json`; AGENTS.md). New logic goes into new modules under the
400-line cap; existing frozen files get at most a one-line import/list entry/registration where the Lead
approves the exception, otherwise the feature waits for a split. No slice may introduce a second SPA,
runtime, database or agent loop.

---

## 0. Already covered by the in-flight personal-operations slice (verify, do not re-plan)

The Lead's working tree at 22:30-22:35 added `src/hutch/personal/{models,commitments,spaces,store,today}.py`,
`src/hutch/personal_schema.py`, `src/hutch/server/personal_api_models.py` and `personal_api.py`, and registered
the migration in `store.py` (resulting `SCHEMA_VERSION` is 84 in the working tree). Per
`.pipeline/personal-operations/2026-10/ARCHITECTURE.md` and `DECISIONS.md` D-02..D-08, that slice covers the
following gaps; the register below does not re-propose them.

| Covered gap | Contract | Still to verify when the slice lands |
|---|---|---|
| User commitments domain (due date, owner, provenance, dependencies, status) | D-02/D-03/D-04; additive schema; append-only `commitment_events` | migration is additive and idempotent; CAS revision behavior; no bot can confirm its own proposal; timezone stored separately from UTC instant; deletion/export path |
| Proposed vs confirmed capture | assistant tool rows start `proposed`; only owner API confirms | tool schema and refusal path; Today shows "Suggested"; invalid IANA zone fails closed |
| Reported vs verified completion | `completion_kind='unverified'` vs `owner_confirmed`; UI distinguishes | no model tool can write the verified kind; history is append-only |
| Shared spaces data scoping | `spaces`/`space_members`/`bot_space_grants`; per-call evaluation; revoked grants fail closed | per-bot isolation test; revoked/archived grant denial; credentials remain per-bot (D-05) |
| Deterministic Today briefing | no model call; projections of persisted rows with `not_included` notes | response carries `generated_at`/zone/`not_included`; local-day boundaries converted per boundary; links to authoritative pages |
| Assistant commitment tools | `capture_commitment`, `list_commitments`, `report_commitment_done` | JSON Schema contract tests; group allowlist; results labelled user data / reported-unverified |
| Today/Shared UI and nav | one primary destination `#/today`, `#/shared` under More | nav/app.js consistency test; server-rendered page parity; empty states; 320 px layout |

Verification shortcut for the Lead: `tests/test_commitments.py`, `tests/test_spaces.py`,
`tests/test_today.py`, `tests/test_personal_api.py` and `tests/test_commitment_tools.py` do not exist yet at
snapshot time; those are the acceptance gate for the covered rows.

---

## 1. Ranked open gaps

| Rank | ID | Gap | Area | Impact | Feasibility | Score | Depends on |
|---|---|---|---|---|---|---|---|
| 1 | G01 | No calendar agenda or mail inbox surface; Today cannot include external obligations | A personal, D automations | 5 | 4 | 20 | in-flight Today + grants |
| 2 | G02 | Coding handoff has no verification/review gate and no worktree lifecycle | C coding | 4 | 4 | 16 | none |
| 3 | G04 | No inbound HTTP/webhook trigger; only polled folder/git/feed | E automations | 4 | 3 | 12 | none |
| 4 | G03 | Automations have no revision history, no approval checkpoint, no conditions | E automations | 4 | 3 | 12 | none |
| 5 | G05 | No outbound notifications for needs-you/failure/result; tab must be open | A personal, E automations | 4 | 3 | 12 | G04 optionally |
| 6 | G06 | Operator-level automation observability only; no per-routine timeline/failure surface | E automations | 3 | 4 | 12 | none |
| 7 | G08 | Commitment cannot push a reminder to a granted calendar after owner confirmation | A personal | 3 | 3 | 9 | in-flight commitments |
| 8 | G09 | Mail/calendar content cannot become a proposed commitment with provenance | A personal | 3 | 3 | 9 | G01 + in-flight tools |
| 9 | G10 | No deliverables library page; documents/artifacts only inside chat/run | D workflows | 2 | 4 | 8 | none |
| 10 | G11 | Code worktrees are never cleaned up; disk grows silently | C coding | 2 | 4 | 8 | none |
| 11 | G13 | Today/commitments not reachable from the paired-phone UI | A personal | 3 | 2 | 6 | in-flight API |
| 12 | G14 | No permanent scoped deletion for facts (and future commitments) | A personal, data | 3 | 2 | 6 | none |
| 13 | G07 | No multi-participant authentication (family members cannot sign in) | B family | 5 | 1 | 5 | identity ADR |
| 14 | G12 | Deliverable verification is byte/format-level; no semantic quality criterion | D workflows | 2 | 2 | 4 | none |

Strategic note: G07 is deliberately ranked low on feasibility, not importance. It is the only gap that makes
"family/shared spaces" a real multi-participant product rather than data scoping for one owner. It should be
decided (ADR) before more UI assumes single-owner semantics.

---

## G01. Read-only calendar agenda and mail digest in Today

- **Current state.** Calendar and mail exist only as per-Bot agent tools with per-Bot grants
  (`src/hutch/tools/google_calendar.py:14-57`, `tools/google_mail.py:14-53`, `tools/outlook_calendar.py:13-56`,
  `tools/outlook_mail.py:14-48`). No dashboard route reads them; Today (in flight) aggregates only persisted
  Hutch rows and explicitly excludes silent calendar/mail reads (ARCHITECTURE.md non-goals).
- **Why it matters.** A personal daily briefing that omits today's meetings and unread mail is not a briefing.
  This is the largest remaining personal-operations gap after commitments land.
- **Missing behavior.** A read-only aggregation endpoint that, for an explicitly chosen connected account and
  grant, returns today's events and a bounded mail digest without persisting provider content; explicit
  "not connected" markers; no write path.
- **Smallest end-to-end slice.** New `src/hutch/personal/agenda.py` with a pure builder over injected readers;
  adapter functions that call the existing `GoogleCalendarBook.list_events` / `GoogleMailBook.list_messages`
  (reuse grant validation and token refresh); a `GET /api/v1/personal/agenda` route in
  `src/hutch/server/personal_api.py`; one Today card in the new personal static module; tests with fake
  readers. No schema change.
- **Exact files.** new `src/hutch/personal/agenda.py`, new `src/hutch/server/personal_agenda_api.py` (or a
  route added to `personal_api.py`), `src/hutch/server/personal_api_models.py`, new
  `src/hutch/server/static/today.js` (or `personal.js`), `src/hutch/tools/__init__.py` unchanged; new
  `tests/test_personal_agenda.py`.
  If the Today builder is not yet merged, put the card behind the same feature switch.
- **Acceptance checks.** Unknown/expired grant returns an explicit unavailable reason, never an empty "no
  events"; strict-offline/local-inference constraints are honored exactly as the tools do; no provider text is
  written to SQLite; response carries `generated_at`, zone and `not_included`; a headless test proves no model
  call is made.
- **Risks.** Google/Gmail scopes remain experimental and live accounts are unverified
  (`docs/requirements.md`); Gmail read is restricted to local-inference Bots, so the agenda must not imply mail
  exists for hosted Bots.

## G02. Coding handoff verification/review gate and worktree lifecycle

- **Current state.** Reviewed handoff + pinned worktree + restrictive OpenCode task profile are real and
  tested (`src/hutch/code_handoff.py:291-357,391-449,492-550`; `tests/test_code_handoff.py:204-291`). But the
  owner is told to "review the branch" (`src/hutch/cli.py:246-250`) and no automated check receipt is stored;
  commits/pushes/merges are denied to the agent (`code_handoff.py:418-421`); worktrees are retained forever
  with no prune path.
- **Why it matters.** The product claim is trustworthy coding orchestration; without a verification receipt
  "changes_ready" means only "the agent exited 0 and Git saw changed files".
- **Missing behavior.** A `hutch code verify <id> -- <argv...>` command that (a) refuses if the recorded
  process is still alive, (b) runs a fixed argv inside the retained worktree with a timeout and output bounds,
  (c) stores a content-free receipt (argv digest, exit code, duration, changed-file digest, timestamp) and a
  `verified`/`verification_failed` state, and (d) a `hutch code prune <id>` that removes the worktree+branch
  only after explicit confirmation and only when the receipt/state allows it.
- **Smallest end-to-end slice.** Add two CLI commands in `src/hutch/cli.py`; helpers in
  `src/hutch/code_handoff.py`; a new `src/hutch/code_review_schema.py` migration module for a
  `code_handoff_receipts` table (append-only), registered with one import/list line in `store.py`; extend
  `tests/test_code_handoff.py` with a fake-CLI verify+prune journey.
- **Exact files.** `src/hutch/code_handoff.py`, `src/hutch/cli.py`, new `src/hutch/code_review_schema.py`,
  `src/hutch/store.py` (one-line registration), `tests/test_code_handoff.py`.
- **Acceptance checks.** Verify never runs if the runner process group is alive; a nonzero argv records failure
  without changing the brief; output is truncated and never contains secrets; prune refuses while a process is
  alive or a receipt is missing; a second verify is idempotent; the chat card exposes the receipt.
- **Risks.** The argv is arbitrary owner code: it must run with the same owner privileges and must be
  explicit (no inference from the repo), with a timeout and no auto-elevation.

## G04. Inbound HTTP/webhook trigger

- **Current state.** `event_sources` supports only `folder/git/feed` (`store.py:1446-1512`); channels
  explicitly list signed webhooks as unavailable
  (`src/hutch/server/channels_api.py:62-68`); roadmap `docs/roadmap.md:187` lists webhook triggers as open.
- **Why it matters.** Every external "push" integration (GitHub, Stripe, Home Assistant, Shortcuts) is
  impossible without a trusted inbound endpoint; polling cannot cover them.
- **Missing behavior.** A per-source shared secret (HMAC or bearer token, stored hashed and shown once),
  body-size/content-type bounds, replay/idempotency key, admission into the existing durable inbox/admission
  policy (cooldown, max-per-hour, never drop), and a delivery status page. No arbitrary code/webhook target:
  the trigger only admits a run/job with a configured prompt, like other sources.
- **Smallest end-to-end slice.** New table `webhook_sources` (token hash, bot, prompt template, admission,
  enabled, revision, last delivery) via new `src/hutch/webhook_schema.py`; new
  `src/hutch/server/webhooks_api.py` with `POST /api/v1/webhooks/{token}` that resolves the source, verifies the
  secret and admits through the same `admit_source_changes`-style transaction (a small new store method in the
  new module, using the public store API); one-line install from `app.py`; tests with a temp SQLite store.
- **Exact files.** new `src/hutch/webhook_schema.py`, new `src/hutch/webhook_receiver.py` (validation/admission),
  new `src/hutch/server/webhooks_api.py`, `src/hutch/store.py` (one-line registration), new
  `tests/test_webhooks.py`.
- **Acceptance checks.** Wrong secret and replay are rejected before any DB write; body bounds enforced; the
  token is never logged or returned after creation; pause state blocks admission; delivery is idempotent under
  retries; unauthorized senders cannot choose the bot or prompt.
- **Risks.** Inbound HTTP breaks the "loopback by default" posture; the route must stay loopback/private-bind
  only and be excluded from remote passkey capability unless explicitly granted.

## G03. Automation revision history, approval checkpoint and conditions

- **Current state.** Schedules are replaced in place inside the Bot JSON document
  (`store.py:4027-4100`); no revision/audit rows exist. Approvals are per tool call only (A6 in
  `CURRENT-STATE.md`; plan-wide approval explicitly rejected at `app.py:1501`). Conditions are limited to
  source include/ignore globs; a `Schedule` has catch_up/overlap only (`models.py:115-186`).
- **Why it matters.** A persistent automation is a standing grant. Owners need to see what changed, approve a
  consequential step, and express "only when" without writing code.
- **Missing behavior (split into three sub-slices, implement in order).**
  1. **Revision journal:** append-only `schedule_revisions` rows on every effective schedule change, with
     before/after schedule JSON hash, changed-field summary, timestamp and an actor label when the API supplies
     one. Read-only `GET /api/v1/bots/{ref}/schedules/{id}/revisions` and a "History" disclosure in the
     schedule card.
  2. **Approval checkpoint:** a per-schedule `approval_required` flag (owner-saved) that parks an occurrence in
     `waiting_approval` with an approval card showing the prompt and the reason before any model/tool work
     starts; deny records a skip occurrence. Reuse the existing approval CAS, TTL and audit machinery rather
     than a second queue.
  3. **Conditions:** a bounded, literal condition set on the schedule (for source-driven schedules: event kind,
     path glob, content-hash changed; for cron: nothing new) evaluated before admission. No expression
     language, no eval.
- **Smallest end-to-end slice.** Start with sub-slice 1 only, using SQL triggers to avoid frozen-file hooks:
  the new migration creates `schedule_revisions` and `AFTER UPDATE OF doc ON bots` / `AFTER INSERT ON bots`
  triggers that insert a row only when the extracted schedule list changes (content hash of the extracted
  schedules JSON, plus per-schedule fields). New `src/hutch/server/schedule_history_api.py` for reads,
  installed with one line from `app.py`; UI disclosure in a new `static/schedules.js`.
- **Exact files.** new `src/hutch/schedule_history_schema.py`, new
  `src/hutch/server/schedule_history_api.py`, `src/hutch/store.py` (one-line registration), new
  `src/hutch/server/static/schedules.js`, `src/hutch/server/static/index.html` (script tag),
  `src/hutch/server/static/app.js` (one-line route delegation if the route handler cannot stay in the new
  module), new `tests/test_schedule_history.py`.
- **Acceptance checks.** A no-op save writes no revision; two saves with different cron create two immutable
  rows; removal is a revision with `removed_at`; reading history requires the same local-owner boundary; the
  Bot doc remains the runtime authority; pause/enable changes are captured.
- **Risks.** SQL triggers must not store prompt bodies/secrets beyond what the schedule already stores; the
  history table must be included in backup/deletion policy (bot deletion plan), or bot deletion will fail a
  retention test.

## G05. Outbound notifications for needs-you, failures and results

- **Current state.** The only delivery machinery is Telegram channel replies inside a channel conversation
  (`src/hutch/channels/persistence.py:20-60`); approvals are visible only in the open tab
  (`app.js:7841-7848`); roadmap `docs/roadmap.md:167-168,180` lists outbound notifications as planned.
- **Why it matters.** Approvals that expire while nobody is looking are silent failures; the approval TTL is a
  hard default-deny. A persistent automation platform is judged by what happens while the tab is closed.
- **Missing behavior.** A durable notification row for (a) approval needs you, (b) approval expired/denied,
  (c) run failed/outcome_unknown, (d) workflow question asked, with at-least-once delivery to the configured
  channel (Telegram first, webhook later), dedup, retry/backoff, uncertainty state and a visible delivery log.
  Never include secrets or full prompts; link to the local page.
- **Smallest end-to-end slice.** New `notification_schema.py` with `notifications` + `notification_deliveries`
  and SQL triggers on `approvals` insert and `runs` terminal status transitions (content-free summary only);
  a small `src/hutch/notifications.py` worker that reuses the existing Telegram transport; a read API in a new
  module; tests with a fake transport.
- **Exact files.** new `src/hutch/notification_schema.py`, new `src/hutch/notifications.py`, new
  `src/hutch/server/notifications_api.py`, `src/hutch/store.py` (one-line registration), `src/hutch/engine.py`
  (single call site to start the worker or reuse the channel service loop), new `tests/test_notifications.py`.
- **Acceptance checks.** An approval created while the app is closed produces exactly one notification and one
  delivery receipt; a provider uncertain send is never retried as a definite; expiry produces a distinct
  notification; the notification row contains no action arguments or fact values; delivery pauses when the
  channel is disabled.
- **Risks.** This must not become a new polling loop: reuse the existing channel/service supervisor; respect
  the existing "one supervisor" lease semantics (`src/hutch/channels/persistence.py`, `tests/test_channels.py`).

## G06. Per-routine automation observability

- **Current state.** Runtime page shows global queue/jobs/sources (`app.js:13680-13780,14017-14025`); the
  schedules page shows next fire, preview, last skip and blocked reason (`app.py:3161-3190`); occurrence history
  is an API (`app.py:3384-3410`) but the schedule page does not expand into it, and there is no failure/alert
  view per routine.
- **Why it matters.** "Why didn't it run?" is the top scheduler complaint the repository itself cites
  (`src/hutch/scheduler.py:1-17`). The data exists; the presentation does not.
- **Missing behavior.** On `#/schedules`, expandable per-routine detail: last N occurrences with run status and
  exit reason, missed-window counts, last skip/blocked reason, linked workflow run status, and a link to the
  run; a "needs attention" filter (blocked/invalid timezone/repeated failure). No new tables.
- **Smallest end-to-end slice.** New `static/schedules.js` module rendering rows from the existing
  `GET /api/v1/schedules` and `.../occurrences` endpoints; one script tag; route handler in `app.js` delegates
  to the module (single-line change); tests via e2e or a DOM-less unit of the formatter.
- **Exact files.** new `src/hutch/server/static/schedules.js`, `src/hutch/server/static/index.html`,
  `src/hutch/server/static/app.js`, `src/hutch/server/app.py` only if the response lacks a field that must be
  added (avoid; all needed fields exist), `tests/test_navbar_consistency.py` stays green, e2e
  `tests/e2e/test_fresh_state_routes.py`.
- **Acceptance checks.** Empty state explains how to create a routine; keyboard expansion; the list does not
  poll faster than 30 s and pauses when the tab is hidden; a blocked routine is visibly distinct from a
  disabled one; no console errors at 1440/834/390/320 widths.

## G08. Commitment to calendar reminder (write path)

- **Current state.** Commitments (in flight) have no external side effect; calendar creation exists only as a
  tool with exact approval (`tools/google_calendar.py:60-138`). The only reminder concept is calendar
  event-relative offsets (`src/hutch/gsuite/requests.py:698-747`).
- **Why it matters.** "Remember to X by Friday" is the most common personal commitment; without a reminder it
  depends on the user opening Hutch.
- **Missing behavior.** An owner action "Add to calendar" on a confirmed commitment that creates one guest-free
  event through the existing guarded path (exact approval, grant re-check, outcome_unknown handling), records
  the external event id/link on the commitment, and never retries an ambiguous write.
- **Smallest end-to-end slice.** New `src/hutch/personal/calendar_bridge.py` that builds the event from a
  confirmed commitment and calls the existing approval-gated tool path; a
  `POST /api/v1/personal/commitments/{id}/calendar` route; the approval uses the existing
  outward/action-hash rules.
  Do not reuse the model tool directly from the API without the gate.
- **Exact files.** new `src/hutch/personal/calendar_bridge.py`, `src/hutch/server/personal_api.py`,
  `src/hutch/server/personal_api_models.py`, new `tests/test_personal_calendar.py`.
- **Acceptance checks.** Proposed (unconfirmed) commitments cannot create events; revoked grants fail closed;
  a second request for the same commitment is idempotent; a failed/uncertain provider result is recorded and
  shown, never silently retried; the created event timezone matches the commitment's IANA zone.

## G09. Mail/calendar content to proposed commitment with provenance

- **Current state.** Calendar/mail tools return untrusted text (A3/A4); commitments (in flight) have
  provenance fields but no tool path from mail/calendar into a proposal; the model could already paraphrase,
  but nothing binds a proposal to the exact source.
- **Why it matters.** "This email says the inspection is due Thursday" should become a suggested commitment
  with a link back to the source, not a hallucinated promise.
- **Missing behavior.** The in-flight capture tool accepts an optional provenance reference (tool name, account
  id, message/event id, hash) that the server validates as a real prior tool result in this run; Today shows
  "Suggested from Gmail/Calendar"; no auto-confirm.
- **Smallest end-to-end slice.** Extend the new `src/hutch/tools/commitments.py` schema and server validation
  to accept a bounded `source_ref` and re-check it against the run's committed tool results; label it in the
  commitment projection and Today. No new tables.
- **Exact files.** new `src/hutch/tools/commitments.py`, `src/hutch/personal/models.py`,
  `src/hutch/server/personal_api.py`, new `tests/test_commitment_tools.py`.
- **Acceptance checks.** A fabricated source_ref is refused before write; a real ref survives restart; the
  proposal remains `proposed` until the owner confirms; provider text is never stored verbatim beyond the
  bounded excerpt already allowed.

## G10. Deliverables library page

- **Current state.** Documents and artifacts exist with verified bytes and APIs
  (`app.py:5049-5230,5565-5730`) but no library destination; users find them inside chat/run detail. The
  schema has no cross-run deliverable index beyond documents/artifacts APIs.
- **Why it matters.** "Where are the things my assistant made?" is a basic shipped-workflow question.
- **Missing behavior.** A read-only `#/deliverables` page listing documents (title, format, version, validation
  state, created, run link, download) and run artifacts (hash-verified) with filters by assistant and date.
  No new storage: aggregate the existing APIs server-side or client-side with bounded paging.
- **Smallest end-to-end slice.** New `src/hutch/server/deliverables_api.py` that reads
  `store.list_documents`-style projections and artifact records; new `static/deliverables.js`; nav entry under
  More; tests. The document and artifact APIs already enforce integrity on download.
- **Exact files.** new `src/hutch/server/deliverables_api.py`, new `src/hutch/server/static/deliverables.js`,
  `src/hutch/server/nav.py`, `src/hutch/server/static/index.html`, `src/hutch/server/static/app.js` (route),
  new `tests/test_deliverables_api.py`, `tests/test_navbar_consistency.py` (update expected nav list only if
  the product decision is to add the destination; otherwise keep it out of nav).
- **Acceptance checks.** Missing/corrupted bytes render an honest unavailable state; no unverified artifact is
  downloadable; paging is bounded; no model call.

## G11. Code worktree lifecycle/GC

- **Current state.** Worktrees live under `<state>/code-worktrees/<handoff id>` and are retained on every
  terminal status (`src/hutch/code_handoff.py:492-519`, `cli.py:246-248`, `app.py:591-594`). No prune exists.
- **Why it matters.** Repeated coding tasks silently fill the local disk; local-first users hit this first.
- **Missing behavior.** `hutch code prune <id>` (explicit confirmation, refuses alive process, shows branch and
  changed-file summary, deletes only the recorded worktree path after re-verifying identity) and a dry-run
  `hutch code list --stale` with age/size.
- **Smallest end-to-end slice.** Implement in `src/hutch/cli.py` + `src/hutch/code_handoff.py` using
  `assert_project_identity`-style checks and no-follow directory removal; add CLI tests to
  `tests/test_code_handoff.py`.
- **Exact files.** `src/hutch/cli.py`, `src/hutch/code_handoff.py`, `tests/test_code_handoff.py`.
- **Acceptance checks.** Prune refuses a live runner, refuses a path that no longer matches the recorded
  device/inode/root, never follows symlinks, keeps the handoff row and history, and reports exactly what was
  removed. No automatic deletion.

## G13. Phone access to Today and commitments

- **Current state.** The paired-phone UI has workflow runs/questions and computer handoff
  (`app.js:12873-13171`), but no Today/commitments because those do not exist yet. Phone capabilities are
  default-deny in `src/hutch/server/security.py` with an explicit route-capability table.
- **Why it matters.** A personal commitment system is most useful on the phone; the infrastructure exists.
- **Missing behavior.** Read-only phone Today endpoint plus answer/complete actions, with explicit capability
  entries (monitor/review) and the same CSRF/origin/session boundary.
- **Smallest end-to-end slice.** Add `/api/v1/phone/today` and two mutating routes to the new
  `personal_api.py`, register capabilities in `security.py`, add a phone section in a new
  `static/phone-personal.js` loaded by the phone shell; tests in `tests/test_personal_api.py`.
- **Exact files.** `src/hutch/server/personal_api.py`, `src/hutch/server/security.py` (capability map),
  `src/hutch/server/static/phone-personal.js` (new), `src/hutch/server/static/index.html`, tests.
- **Acceptance checks.** Phone cannot confirm a proposed commitment? (decide explicitly and test), cannot read
  another space it is not a member of, and cannot exceed its capability class; local owner token still never
  accepted remotely.

## G14. Permanent scoped deletion for personal data

- **Current state.** Facts are archived/tombstoned, not permanently deleted; `bot_deletion_steps.py:76-85`
  purges share content, and fact purge requests exist, but "permanent scoped deletion is not implemented"
  (`src/hutch/fact_memory.py:52-56` trigger message; `docs/requirements.md`). Commitments (in flight) will
  inherit the same problem.
- **Why it matters.** Family/shared data and sensitive commitments make deletion a trust requirement.
- **Missing behavior.** A confirmed purge that removes the fact/commitment content bytes and dependent
  projections while retaining a content-free tombstone for referential integrity; export before purge.
- **Smallest end-to-end slice.** Extend the existing purge request flow (`src/hutch/server/facts_api.py:124-168`,
  `fact_purge.py`) with a commitment scope; new tests with a temp DB and byte inspection.
- **Exact files.** `src/hutch/fact_purge.py`, `src/hutch/facts_api.py` or new
  `src/hutch/server/personal_purge_api.py`, `src/hutch/personal/commitments.py`, tests.
- **Acceptance checks.** Purge is idempotent, requires explicit confirmation, removes bytes from every
  projection/share/version, leaves no provider copies claim (documented honestly), and a backup made before the
  purge still exists as the operator's responsibility.

## G07. Multi-participant authentication and identity (strategic, design first)

- **Current state.** Single owner + paired phone only (`store.py:1296-1298`, `security.py:320-345`). In-flight
  spaces are a data-scoping model with membership records, not authenticated participants
  (ARCHITECTURE.md non-goals).
- **Why it matters.** Family/household sharing without separate identities is a permission model enforced only
  by one owner's UI; a second adult cannot have their own scoped access.
- **Missing behavior.** Identity model (passkey per member, recovery), session/capability per member, per-space
  roles enforced in store queries, audit of who changed what, owner transfer/removal, and a migration path for
  the existing single-owner row. This is a security-boundary change and must not be incidental.
- **Smallest honest slice.** An ADR + threat model + schema spike only (no user-visible feature): decide
  principal model, session/capability map, how the existing `webauthn_owner` migrates, how local owner bypass
  interacts with member sessions, and how bot grants are evaluated for a member request. Files:
  new `docs/adr/00xx-multi-participant-identity.md`, plus a design doc; no code until approved.
- **Acceptance checks (for the ADR).** Every route has an owner/member capability decision; no member can read
  another member's personal items or another space; bot runtime remains owner-scoped; the local owner token is
  not weakened; recovery path defined.
- **Risks.** Done wrong, this collapses the current local-first security posture; treat as a deliberate
  boundary change with its own review, not as part of the personal-operations slice.

## G12. Semantic deliverable verification

- **Current state.** Byte/hash verification is excellent (D3); workflow verify nodes support schema/artifact/
  command/human checks and treat agent review as advisory only (`src/hutch/workflow/engine.py:659-753`,
  `workflow/plan.py:118-175`). No automated semantic criterion beyond those checks.
- **Why it matters.** "The report exists and has the right bytes" is not "the report is correct".
- **Missing behavior.** A way to attach a declared, deterministic check to an agent-produced deliverable
  (e.g. schema of the JSON body, required sections, row-count parity to a source), surfaced as
  `verified`/`unverified`; never a second model certifying a first model's prose.
- **Smallest end-to-end slice.** Extend the document tool/artifact record with a `declared_checks` field
  validated at creation and recorded in the existing `validation_state`/findings; implement only schema and
  row-count checks first. No new verification engine.
- **Exact files.** `src/hutch/documents/storage.py`, `src/hutch/tools/documents.py`, `src/hutch/workflow/plan.py`
  (check kinds), tests in `tests/test_documents_pipeline.py` and `tests/test_workflow_engine.py`.
- **Acceptance checks.** A failing declared check records `validation_state='failed'` and blocks the
  "verified" label; agent_review alone can never certify; the check input is bounded and deterministic.

---

## 2. Sequencing recommendation

1. Let the in-flight slice land and pass its own tests first; do not start G01/G09 until the Today aggregation
   contract is stable (they both add Today cards).
2. G02 is independent of the personal slice and improves the coding claim; it can run in parallel.
3. G03/G04/G05 share the "automation trust" theme and should be sequenced as history -> approval checkpoint ->
   conditions; inbound trigger and notifications can follow independently.
4. G06 is presentation over existing data and is the cheapest visible win after the slice lands.
5. G07 (identity) is a decision, not a sprint item; schedule the ADR before any family-facing UI promise.
6. Never present the current bot-to-bot sharing primitives as a family/space feature: they share data between
   assistants of one owner, not between people.

## 3. Anti-goals (from the current architecture and findings)

- No model-generated Today prose as a source of truth; no inference presented as recorded state.
- No second approval queue or second runtime for any slice above; reuse `approvals.py` and the run/event model.
- No incidental widening of provider access, credential scope, or cross-Bot data flow.
- No "always allow" for outward actions (calendar/mail/webhook), and no automatic retry of ambiguous provider
  outcomes.
- No new scheduler engine and no webhook receiver that can execute arbitrary targets; triggers only admit runs.
- No hidden writes to frozen/generated files; new code lives in new modules.
