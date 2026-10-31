# Architecture proposal: personal operations, shared spaces, and a truthful Today

Status: implementation contract for the 2026-10 initiative. Written after reading the existing execution
platform (schema v81, scheduler, workflow engine, approvals, documents) and before adding the new domain.
This is deliberately incremental: it extends Hutch's existing durable-state and approval model rather than
introducing a second runtime, a second database, or a second agent loop.

## What already exists (verified by code inspection)

| Capability | Existing implementation | Evidence |
|---|---|---|
| Durable runs, honest outcomes | \`Run\`, lease/fence, action intents + receipts, event hash chain | \`src/hutch/store.py\`, ADR-0003, \`tests/test_action_intents.py\` |
| Recurring/one-shot/interval schedules with IANA zones, catch-up, overlap, run-now, skip-next | \`src/hutch/scheduler.py\`, \`Schedule\` model, \`schedule_occurrences_v20\` | \`tests/test_scheduler.py\`, \`tests/test_schedule_durability.py\` |
| Workflow IR, revisions, runs, budget reservations | \`src/hutch/workflow/\` | \`tests/test_workflow_engine.py\`, \`tests/test_workflow_ops.py\` |
| Immutable action review and approvals | \`src/hutch/approvals.py\`, \`approvals\` table, \`action_hash\` | ADR-0014, \`tests/test_approval_cas.py\` |
| Generated documents with hash-verified versions, previews, downloads | \`documents\` + \`document_versions\`, \`src/hutch/documents/\` | ADR/architecture schema-v50 section, \`tests/e2e/test_documents.py\` |
| Coding handoff to OpenCode with reviewed brief and isolated workspace | \`src/hutch/code_handoff.py\`, \`code_handoffs\` table | \`tests/test_code_handoff.py\` |
| Coordinated workspace tasks with specialist snapshot | \`src/hutch/coordinator_tasks.py\`, \`workspace_tasks\` | \`tests/test_coordinator_tasks.py\` |
| Memory facts separated from instructions, review-gated | \`src/hutch/fact_memory.py\` | ADR-0008, \`tests/test_memory_continuity.py\` |
| Channel inbox/outbox with idempotent admission and uncertain-send reconciliation | \`src/hutch/channels/\` | ADR-0023, \`tests/test_channels.py\` |
| Dashboard SPA shell with route table, design tokens, responsive checks | \`src/hutch/server/static/\`, \`app/src/\` | \`tests/e2e/test_design_system.py\` |

## The actual gap

Hutch can execute work durably, but it has no canonical record of **what the person promised to do**.
\`Task\` is a run-lifecycle row (one dispatch), \`workspace_tasks\` are coordinated specialist assignments, and
\`conversation_task_state\` is a per-chat continuity manifest. None of them is a user commitment with a due
date, provenance, completion evidence, dependencies, or a visibility scope. The dashboard's "Now" view is
operator-oriented (runs, approvals, stale schedules) and does not answer "what should I do today?".

There is also no shared/household scope. Every record is owner-global, so a household item cannot exist
without leaking into every assistant's view, and there is no way to grant one assistant access to a shared
space while keeping other data out.

## Proposed additions (and why they are not a new platform)

### 1. Commitments (new durable domain, schema v84)

A \`commitments\` table plus an append-only \`commitment_events\` audit table and a
\`commitment_dependencies\` edge table.

Key fields: title, detail, status (open/done/cancelled), priority, due_at (UTC instant), due_timezone (IANA
name for the local day the user chose), category, space_id (NULL = personal), provenance
(conversation/run/message ids, source, created_by), confirmation (confirmed/proposed), revision (CAS),
completion evidence (text + kind + actor + timestamp), dependency edges.

Deliberate distinctions:

* **Proposed vs confirmed.** An assistant may capture a commitment as \`proposed\`; only the owner's
  authenticated dashboard/API can confirm it. The model cannot manufacture a fact about what the user
  promised. This is the commitment-domain equivalent of ADR-0003's "an agent response is not evidence".
* **Reported vs verified completion.** An assistant can report completion with evidence, recorded as
  \`unverified\`; the owner verifies. External receipts can later be attached as a completion kind without
  rewriting the past. A completion claims nothing the store cannot show.
* **Provenance is immutable.** \`commitment_events\` is append-only with database triggers, like the run event
  hash chain: revision history is auditable and cannot be silently rewritten.

### 2. Shared spaces (household/project/team)

\`spaces\` + \`space_members\` (role: owner/adult/collaborator/read_only/child/guest; status active/revoked)
+ \`bot_space_grants\` (an explicit, revocable grant from space to assistant).

The enforcement boundary is in the store query, not in the model prompt:

* The owner-facing API is single-owner today; membership records which human participants a space is for and
  is the basis for future per-participant authentication.
* An assistant tool call can only read/write commitments in the personal scope or in spaces granted to **that
  bot**. \`PersonalStore.bot_space_ids()\` is evaluated per call; revoked or archived grants fail closed.
* Space data is never included in another assistant's tool results, and credentials/integrations remain
  outside the space model entirely (they are already per-bot grants).

### 3. Today briefing (deterministic aggregation, no model call)

\`src/hutch/personal/today.py\` composes read-only projections of real persisted state:

* commitments: overdue / due today / upcoming (7 days) / proposed / reported-done-unverified / completed today;
* scheduled work: next fire per enabled schedule (reusing \`Scheduler.next_fire\`) inside the local day, plus
  paused/blocked schedule evidence;
* approvals: pending count and items (tool, risk, expiry);
* runs: working now, needs-attention failures, terminal runs completed today;
* deliverables: documents created today with hash/validation status;
* spaces: member count and open shared commitments.

Every item carries its source and a link to the authoritative page. The builder never calls a model and never
infers an event. It returns \`generated_at\`, the resolved IANA zone, and explicit \`not_included\` notes so the
UI cannot present a partial view as complete.

Timezone handling follows the scheduler's rule: resolve the requested IANA zone with \`zoneinfo\`, fail closed
(422) on an unknown zone, compute local day boundaries from the local date, convert each boundary to UTC, and
never compare naive local times across zones. DST-length days are handled by converting each boundary
separately.

### 4. UI

One new primary destination, **Today** (\`#/today\`), and one **Shared** destination under More
(\`#/shared\`); the existing Chat/Tasks/Needs you rows keep their positions and meanings. This follows the
existing hash-route SPA, \`nav.py\` single navigation model, and the existing design tokens rather than adding
a second frontend.

Today is ordered by next useful action: needs-you, due/overdue commitments, quick capture, scheduled work,
working now, reported-done verification, recent deliverables, shared-space summary. Empty states say what is
missing and how to add it. No fake progress, no fabricated summary.

### 5. Assistant tools

Three tools: \`capture_commitment\`, \`list_commitments\`, \`report_commitment_done\`. They are catalog
entries with validated JSON Schemas, registered in a new \`commitments\` group, and are only available to Bots
the owner has granted them to. Space visibility is decided by \`bot_space_grants\`, not by the model's
arguments. Tool results explicitly label commitments as user records (data, not instructions) and label
completion as reported-unverified.

## Non-goals for this slice

* No multi-user authentication or passkey-bound family accounts (single-owner server remains; membership is a
  data-scoping model now and an authentication-compatible boundary later).
* No new scheduler engine, workflow engine, document renderer, or provider integration.
* No silent calendar/mail reads for Today; those integrations already expose tools and schedules, and Today
  links to them instead of making up data.
* No model-generated briefing prose. If a narrative is wanted later it must be an explicitly labelled
  generation with its inputs shown, not the source of truth.

## Migration and rollback

Additive migration v84: new tables and indexes only, no changes to existing columns or rows. Old code opening a
v82 database is refused rather than downgraded (existing store behavior). Rollback for the feature is code-only:
the tables are unused by old code and can remain; a database backup is taken by the existing pre-upgrade path.

## Files (each new file under the 400-line context-hygiene cap)

\`src/hutch/personal/{models,schema,store,today}.py\`, \`src/hutch/server/personal_api.py\`
(commitments/spaces/today routes), \`src/hutch/tools/commitments.py\`,
\`src/hutch/server/static/{today,shared,personal}.js\` + \`personal.css\`,
plus route/nav/script wiring in the existing shell files and focused tests.
