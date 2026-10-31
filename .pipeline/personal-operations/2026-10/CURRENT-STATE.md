# CURRENT-STATE: personal operations, shared spaces, coding orchestration, shipped workflows, persistent automations

Audit date: 2026-10-30, 22:27-22:40 America/Vancouver. Repository: `/home/kevina/CodingProjects/hutch`,
branch `main`, committed HEAD `989e5bc0` ("End open event streams on shutdown so Ctrl+C is prompt and
quiet"). Read-only audit: no source, test, docs or website file was modified; only this audit directory was
written.

Snapshot caveat: the Lead's personal-operations implementation started landing in the working tree while this
audit ran (uncommitted `src/hutch/personal/`, `src/hutch/personal_schema.py`, `src/hutch/server/personal_api.py`,
`src/hutch/server/personal_api_models.py`, plus the migration registration in `src/hutch/store.py`). Verdicts
below describe the committed baseline at HEAD. In-flight work is called out separately and is not counted as
shipped; it has no committed tests yet.

## 0. Baseline facts and two corrections

- Python backend: 289 modules under `src/hutch/`; the dashboard SPA is hand-written vanilla JS, with
  `src/hutch/server/static/app.js` at 14,241 lines (953 KB) plus per-feature modules such as
  `tasks.js`, `catalog.js`, `computer.js`, `channels.js`. Tests: 361 `test_*.py` files plus Playwright
  e2e under `tests/e2e/`.
- **Schema version correction.** The assignment says `SCHEMA_VERSION=81`; at HEAD it resolves to **83**.
  `src/hutch/store.py:2453-2461` builds `_MIGRATIONS` from 80 numbered migrations (`_migrate_2` ..
  `_migrate_81`) plus `fact_purge_schema.migrate` and `bot_deletion_schema.migrate` (82 entries) and computes
  `SCHEMA_VERSION = 1 + len(_MIGRATIONS)`; importing `hutch.store` in the repo venv prints 83. 81 is the
  highest numbered migration, not the version. With the Lead's uncommitted `personal_schema.migrate`
  registration it now prints **84**; note that in-flight documents disagree about the number
  (`ARCHITECTURE.md` says "schema v84", `DECISIONS.md` says "v82", and `src/hutch/personal_schema.py:1` says
  "Schema v82"). This must be reconciled before the migration is committed; the resulting `user_version` is
  what old binaries compare.
- Focused read-only pytest run for this audit (repo venv): tests/test_navbar_consistency.py,
  tests/test_scheduler.py, tests/test_coordinator_tasks.py, tests/test_task_templates.py,
  tests/test_code_handoff.py and tests/test_sources_api.py -> **58 passed in 41.53s**. No e2e/Playwright
  suite was run.

## Verdict table

| Area | Verdict at HEAD | Strongest evidence | In-flight Lead work |
|---|---|---|---|
| A1 Daily briefing / agenda | **Absent** | no route, API, model, table or test; nav and SPA route table have no today/briefing destination (`nav.py:11-30`, `app.js:1891-1909`) | `src/hutch/personal/today.py` (WIP) |
| A2 Tasks / commitments | **Partial**: full agent run/task lifecycle, no user commitment domain | `models.py:49-76,593-598`; `store.py:71-88`; `tasks_api.py`; `coordinator_tasks.py` | `personal/{models,commitments,spaces,store}.py`, `personal_schema.py` (WIP) |
| A3 Calendar | **Partial**: read tools + single-event creation with exact approval; no agenda UI | `tools/google_calendar.py`, `tools/outlook_calendar.py`, grants tables | none |
| A4 Mail | **Partial**: read search for Gmail (local inference only) and Outlook; send-only grants; no inbox UI | `tools/google_mail.py`, `tools/outlook_mail.py`, `*_mail_send.py` | none |
| A5 Memory / fact continuity | **Implemented** (strong) | `fact_memory.py`, `memory_fact_shares`, facts API + UI | none |
| A6 Approvals | **Implemented** for run tool actions; **absent** as automation-level checkpoints | `approvals.py`, `models.py:769-800`, `store.py:97-105` | none |
| B Family / shared spaces | **Absent** as multi-participant product; **partial** bot-to-bot sharing primitives | artifact/fact shares, specialists, per-bot integration grants; single-owner auth | `personal/spaces.py` (data model only, no auth) |
| C Coding orchestration | **Partial**: reviewed human-launched OpenCode handoff with pinned worktree; no plan/test/review/merge loop | `code_handoff.py`, `code_handoffs` table, CLI commands, tests | none |
| D Shipped workflows | **Implemented** (deepest subsystem) | `src/hutch/workflow/` 8k lines, verify nodes, documents/media/synthesis, hash-verified artifacts | none |
| E Persistent automations | **Partial**: strong cron/interval/once scheduler + polled file/git/feed sources; no webhook trigger, conditions, approval checkpoints, schedule revision history | `scheduler.py`, `event_sources`/`source_events`, `monitoring.py`, runtime UI | none |

---

## A. Personal operations

### A1. Personal daily briefing / agenda: ABSENT

There is no briefing or agenda feature in the committed tree:

- Navigation (`src/hutch/server/nav.py:11-30`) is Chat, Tasks, Needs you, Activity, Scheduled work, Catalog,
  Models, Usage, Runtime, Assistants, Apps & AI, Settings. No Today/Briefing/Agenda destination.
- The SPA route table (`src/hutch/server/static/app.js:1891-1909`) has `#/chat`, `#/tasks`, `#/approvals`,
  `#/activity`, `#/schedules`, `#/runtime`, `#/bots`, `#/catalog`, `#/connections`, `#/settings`,
  `#/run/<id>`, `#/bot/<name>`, conversations. No `#/today`.
- `grep -riE 'briefing|agenda' src/hutch/server` returns nothing. In the whole tree the only briefing
  occurrences are demo/fixture names (`tests/test_migration.py:29`, `src/hutch/demo_leftovers.py:16`) and a
  role-label heuristic in the composer (`app.js:11174,11183`).
- The "home" aggregation that exists is operator triage, not a personal briefing: `views.home_state`
  (`src/hutch/views.py:329-368`) returns pending approvals, active runs, recent failures and stale
  assistants; the SPA renders that as `#/activity` (`app.js:1897` -> `renderOverview`).
- No calendar is read into any dashboard page; calendar data exists only inside agent tool calls (A3).
- Tests: none.

In-flight note: `src/hutch/personal/today.py` (242 lines at observation time) is being written against the
contract in `.pipeline/personal-operations/2026-10/ARCHITECTURE.md` ("Today briefing: deterministic
aggregation, no model call"). It is uncommitted and untested; the `#/today` route and UI do not exist yet
(no `today` hits in `nav.py` or the `app.js` route table).

### A2. Tasks and commitments: PARTIAL (agent work lifecycle implemented; user commitments absent)

Three different meanings of "task" exist; none is a user promise with a due date:

1. **Run/Task dispatch lifecycle** (agent execution): `Task` (`src/hutch/models.py:593-598`) is one queued
   prompt for one Bot; `Run` (`models.py:601-`) carries status, lineage, budget and ownership. Statuses are
   defined once in `RunStatus` (`models.py:49-76`) and legal transitions live in `lifecycle.py` per ADR-0003.
   Tables `tasks` and `runs` are in the base schema (`store.py:71-88`), created by
   `Store.enqueue_task/finish_task/pending_tasks` (`store.py:4223-4248`) and `submit_run`
   (`store.py:4277-4357`). This is well tested across run-lifecycle suites; the area is execution, not
   commitment keeping.
2. **Coordinated workspace tasks** (specialist assignments): `workspace_tasks` (`store.py:714-732`) links a
   coordinator conversation to 1-2 specialist child conversations/runs with a reviewed brief; admission is
   transactional and re-checks the roster, source turn, capability snapshot and selected facts
   (`coordinator_tasks.py:216-257`), and is exposed by `src/hutch/server/tasks_api.py:76-185` under
   `/api/v1/workspace/tasks`. The SPA `#/tasks` page (`app.js:1903`; `static/tasks.js:1-10,163-183`) is
   only this surface: "Work your main assistant has handed to specialists" (`tasks.js:167`). There is no
   due date, no human owner, no completion-by-person.
3. **Chat continuity state**: `conversation_task_state` and its immutable revisions
   (`store.py:2364-2389`) are a per-conversation manifest validated and updated through
   `store.py:5148-5242`; it is context continuity, not a commitment.
4. **Reusable prompts**: `task_templates` (`store.py:1334-1342`) with revision-checked CRUD
   (`store.py:4925-5010`, routes `src/hutch/server/app.py:3410-3450`, UI `app.js:2963-3090`). These are
   saved prompts, not commitments.

**Commitment domain absent:** `grep -riE 'commitment' src/hutch --include=*.py` has zero pre-baseline hits
(the hits now come from the uncommitted `src/hutch/personal/`). No table, model, route, tool or test stores
"what the person promised to do", a due date, a human owner, completion evidence, dependencies or a
visibility scope. There is also no reminder-as-commitment concept: the only reminder machinery is Google
Calendar event-relative reminders (`src/hutch/gsuite/requests.py:698-747`), i.e. attributes on an external
calendar event.

In-flight note: the Lead's `src/hutch/personal/{models,commitments,spaces,store}.py` plus
`src/hutch/personal_schema.py` (observed 22:30-22:34) add `commitments`, append-only
`commitment_events`, dependencies, proposed-vs-confirmed and reported-vs-verified completion per
`DECISIONS.md` D-02..D-04. No `tests/test_commitments.py`, no `src/hutch/tools/commitments.py` and no
complete route surface were observed at snapshot time; treat as unverified.

### A3. Calendar: PARTIAL

Implemented:

- Read tools: `google_calendar_events` (single explicitly granted calendar, bounded 25 events, ISO-8601
  range with explicit zone, read-only, untrusted-output framing) in `src/hutch/tools/google_calendar.py:14-57`;
  `outlook_calendar_events` in `src/hutch/tools/outlook_calendar.py:13-56`.
- Creation with exact approval: `google_calendar_create_event` (`tools/google_calendar.py:60-138`) and the
  Outlook write tool (`tools/outlook_calendar_write.py:1-98`). The Google path re-checks the grant after the
  approval wait (`google_calendar.py:118-125`), records the prepared event in the approval detail, passes
  `outward=True, ask_in_auto=True` (`google_calendar.py:112-114`), and converts an ambiguous provider result
  into a run abort `outcome_unknown` rather than retrying (`google_calendar.py:126-134`). Guest-free only.
- Grants are per-Bot and separate per provider/direction: `google_calendar_grants` (`store.py:688-713`),
  `outlook_calendar_grants` (`store.py:1010-1023`), `outlook_calendar_write_grants` (`store.py:1375-1398`);
  connection setup and grant review are in `src/hutch/server/app.py` (connections block, ~`5990-6900`).
- Broader Google Workspace Docs/Sheets/Drive/Calendar actions are supported through a reviewed action plan:
  `plan_workspace_action` / `run_workspace_plan` (`src/hutch/tools/workspace_actions.py:87-135,136-`),
  executors in `src/hutch/gsuite/executors.py` and `src/hutch/actions/execute.py:1-25` (approval scope hash
  checked before the first effect; read-back verification per executor).
- Tests: `tests/test_google_calendar.py` (27), `tests/test_google_calendar_api.py` (6),
  `tests/test_outlook_calendar.py` (9), `tests/test_outlook_calendar_api.py` (2),
  `tests/test_outlook_calendar_write.py` (10), `tests/test_outlook_calendar_write_api.py` (1).

Missing: no dashboard calendar surface (no agenda page, no "today's events", no event detail/edit/delete);
tools are call-only, not scheduled aggregation; only one granted calendar per Bot; no invitations/attendees;
calendar reads are withheld in strict-offline mode (`src/hutch/tools/__init__.py:117-120`).

### A4. Mail: PARTIAL

Implemented:

- Gmail search: read-only, up to 10 messages, sender/subject/date/snippet only, available only when the Bot
  uses Local inference (`src/hutch/tools/google_mail.py:14-53`; `validate_local_gmail_bot` at
  `google_mail.py:34-36`), separate `google_mail_grants` (`store.py:1071-1080`).
- Gmail send: separate send-only grant and tool (`src/hutch/tools/google_mail_send.py:1-111`,
  `google_mail_send_grants` at `store.py:1364-1374`) with exact per-message approval and no ambiguous retry.
- Outlook Mail read preview (`src/hutch/tools/outlook_mail.py:14-48`) and send
  (`src/hutch/tools/outlook_mail_send.py:1-88`, `outlook_mail_send_grants` at `store.py:1353-1363`).
- Tests: `tests/test_google_mail.py` (5), `tests/test_google_mail_api.py` (7),
  `tests/test_google_mail_send.py` (9), `tests/test_outlook_mail.py` (5),
  `tests/test_outlook_mail_api.py` (2), `tests/test_outlook_mail_send.py` (9),
  `tests/test_outlook_mail_send_api.py` (2).

Missing: no inbox/triage UI; no attachments; Gmail reading excludes hosted-inference Bots by design; no
mail-to-commitment or mail-to-task conversion; no push/webhook mail triggers (poll-only would be a new
source); send path is plain text only.

### A5. Memory / fact continuity: IMPLEMENTED (strong)

`src/hutch/fact_memory.py` (345 lines) implements a real revisioned fact domain:

- `memory_facts` + `memory_fact_decisions` created in `fact_memory.py:35-70`; content immutability and
  no-delete triggers; FTS index; legacy `memory` rows migrated as unreviewed (`fact_memory.py:35-70`).
- Proposal path is run/fence-bound and cannot write a fact without an owned running run
  (`fact_memory.py:87-125`); scope is conversation/run/bot; explicit user-statement provenance is protected
  from agent overwrite (`fact_memory.py:108-119`).
- Read path enforces scope and literal AND search terms (`fact_memory.py:137-176`); review/approve/archive
  and history are separate functions (`fact_memory.py:216-287`) with immutable decisions.
- Cross-Bot sharing is an explicit, revocable snapshot of an exact approved revision
  (`memory_fact_shares`, `store.py:1105-1167`; incoming-only read path `fact_memory.py:178-238`), and
  both source and target Bot must have memory enabled.
- API + UI: `app.py:4726-4860` (facts, history, review, shares), purge preview/confirm in
  `src/hutch/server/facts_api.py:124-168`; SPA fact panel, share cards and revoke in `app.js:4661-4955`;
  dedicated purge UI module `static/fact-purge.js`.
- Tests: `tests/test_fact_memory.py` (15), `tests/test_fact_purge.py` (11),
  `tests/test_memory_continuity.py` (8), plus `tests/test_bot_deletion_artifact_shares.py` for share
  retention on deletion.

Missing (by design, still user-visible): permanent scoped deletion is not implemented (archive/tombstone +
purging content bytes, `bot_deletion_steps.py:76-85`); no per-space/per-person memory namespace (see B);
no cross-Bot automatic recall (explicit share only).

### A6. Approvals: IMPLEMENTED for per-action review; ABSENT as automation checkpoints

- `ApprovalRequest` (`models.py:769-800`) binds a run, tool, human-readable action, detail, risk, outward
  flag, action hash, TTL and expiry. `ApprovalGate` (`src/hutch/approvals.py:55-148`) resolves once via CAS,
  refuses stale action hashes, and `outward` actions never become sticky allows. Default-deny expiry and
  resolution helpers are `approvals.py:235-288`; expiry is swept by the engine tick (`src/hutch/engine.py:1648`).
- Persistence: `approvals` table with JSON doc plus `action_hash`/`expires_at` columns
  (`store.py:97-105`, migration 5), `tool_allows` sticky keys (`store.py:106-111`).
- API + UI: `app.py:5853-5960` (`/api/approvals`, `/api/v1/actions/approvals[/approve|/deny]`); the SPA
  `#/approvals` destination is a modal over Chat ("Needs you"), not a page: `renderApprovals` immediately
  redirects to `#/chat` and opens the dialog (`app.js:7841-7848`). Cards include due-soon/high-risk/outward
  filters and expiry countdowns.
- Tests: `tests/test_approval_cas.py` (16), `tests/test_file_approval.py` (6), plus approval behavior in
  many run/tool suites.

Missing for personal operations and automations: no pre-run or plan-level approval checkpoint (the API even
rejects a non-zero plan scope: `app.py:1501` "Plan-wide approvals are not implemented"); no approval policy
attached to `Schedule` or to a workflow definition revision; approvals only exist mid-run when a tool asks.
The in-flight commitments design (D-03/D-04) is the application-level equivalent for proposed vs confirmed.

---

## B. Family / shared spaces: ABSENT as a multi-participant product; PARTIAL as bot-to-bot sharing

There is **no household/family/member/participant ownership model** in the committed baseline:

- The instance is explicitly single-owner. `webauthn_owner` is a singleton row
  (`store.py:1296-1298`, `CHECK(singleton = 1)`); the security middleware has exactly two principal kinds
  ("owner" local, or paired-phone session) (`src/hutch/server/security.py:320-345`). Paired phones never
  issue a reusable dashboard token (same block). There are no roles, no member-scoped tokens, no per-member
  data visibility, no invitations.
- `grep -riE 'household|family' src/hutch --include=*.py` matches only branding/demo text, not a domain.
- `docs/requirements.md:200` lists "multi-user accounts" among things Hutch does not have; the roadmap lists
  "Multi-user access to one hutch instance (auth + roles)" as open (`docs/roadmap.md:196`); architecture says
  webhook triggers, multi-user roles and bounded agent-to-agent collaboration are future work
  (`docs/architecture.md:469`).

What does exist, and the isolation guarantees attached to it:

| Primitive | What it shares | Enforcement evidence |
|---|---|---|
| `conversation_artifact_shares` | One verified tool-output/workspace-file artifact from an event in a *different* conversation into a target conversation's Files list (no copy, no model context) | schema + source-different-conversation guard + immutable/revoke-once/no-delete triggers (`store.py:445-515` migration 17; re-created with bot-deletion FK support in `bot_deletion_schema.py:59-182`); share route re-verifies sha256/size before insert (`app.py:5113-5159`); UI `app.js:303-420,1101-1120`; test `tests/test_bot_deletion_artifact_shares.py` |
| `memory_fact_shares` | One exact approved, current fact revision snapshot from one Bot to one named Bot, read-only and untrusted | schema + guard trigger requiring approved/current/enabled Bots/scopes (`store.py:1105-1167`); incoming page `fact_memory.py:178-238`; API `app.py:4786-4860`; tests in `tests/test_fact_memory.py` |
| `workspace_specialists` | Owner-approved roster of Bots a coordinator may assign tasks to (1-2 per task) | `store.py:1238-1266` with triggers preventing the coordinator from being its own specialist; admission re-checks membership atomically (`coordinator_tasks.py:137-157`); API `app.py:4076-4085` |
| `integrations` + `integration_tool_grants` | Per-Bot tool grants from governed integrations, disabled by default | `store.py:2284-2307`; catalog/mount logic in `src/hutch/integrations/` |
| Per-Bot OAuth grants (calendar/mail) | External account reads/writes scoped to one Bot, revocable | A3/A4 grant tables |

Assessment: these are **explicit, inspectable, revocable bot-to-bot sharing primitives**, not a shared-space
or family model. There is no notion of "this item belongs to the household", no participant who can log in,
no scoped read model for a second person, and no cross-Bot visibility boundary beyond "each Bot has its own
grants and shares must be explicit". The only isolation is per-Bot: fact scoping (`fact_memory.py:137-176`),
artifact-share source checks, per-run capability snapshots (`models.py` run capability fields;
`coordinator_tasks.py:137-157`), and the local-first single-owner auth boundary. A hostile multi-tenant
boundary is explicitly not claimed (repo research; docs/architecture.md).

In-flight note: `src/hutch/personal/spaces.py` (211 lines at observation) adds `spaces`/`space_members`/
`bot_space_grants` as a **data-scoping** model; `.pipeline/.../ARCHITECTURE.md` non-goals explicitly exclude
multi-user authentication. So "family members can each sign in" remains absent even after that work lands;
only per-space data scoping + per-bot grants is being added.

---

## C. Coding orchestration: PARTIAL

Implemented (real and tested):

- **Reviewed handoff object.** `code_handoffs` (`store.py:1168-1237`, migration 39) stores the source chat
  attempt, original request, coordinator-proposed brief, owner-edited brief, project identity
  (root/device/inode/git common dir/base commit), status, worktree/branch, runner identity and outcome.
  Creation validates that the source user+assistant messages belong to the same succeeded run and that the
  Bot's configured folder is the project root (`store.py:5846-5921`); idempotent API at `app.py:4092-4151`;
  the status card and local launch command are rendered in the chat (`app.py:583-620`; SPA fetch at
  `app.js:4688,4748`).
- **Human-launched OpenCode session in an isolated worktree.** `src/hutch/code_handoff.py`: inspect the CLI
  contract (`:115-134`), private profile dirs/config with 0700/0600/no-follow (`:137-202`), scrubbed
  environment that refuses host credentials (`:205-241`), project identity pinning and re-verification
  (`:291-357`), bounded task prompt (`:360-377`), interactive mini launch (`:380-383`, `cli.py:118-280`),
  detached worktree from the pinned commit with unique branch `hutch/code/<id>` (`:492-519`), per-task
  OpenCode agent permissions (deny by default, read/edit in worktree, ask for shell, deny commit/push/reset/
  clean/subagent/external dirs, deny secret files; 20-step cap) (`:391-449`), refusal of project
  `.opencode/plugins` that could run outside task permissions (`:472-489`), terminal foreground handoff and
  restoration (`:28-112`), change summary from Git (`:522-550`), process-group verification and
  `cleanup_incomplete`/`reconcile` semantics (`cli.py:200-330`; store `claim/start/finish/interrupt`
  `store.py:5934-6000`).
- **Coordinator to specialist delegation** as a second, non-coding-specific orchestration path:
  `workspace_tasks` + `tasks_api.py` + `coordinator_redirect.py` (redirect bumps brief revision, stop-all,
  continue-from-checkpoint).
- **OpenCode as a governed chat runtime** (distinct from the coding handoff): `src/hutch/runtime/opencode.py`
  owns a private `opencode serve`, uses the durable message endpoint, brokers every permission prompt
  through Hutch's approval gate, records provider usage against a reservation, and fails closed on
  unverifiable outcomes (`runtime/opencode.py:1-17,211-`; server/protocol in `opencode_server.py`,
  `opencode_protocol.py`; bridges in `opencode_memory.py`). Tests: `tests/test_runtime_opencode.py` (23),
  `tests/test_opencode_{api,login,memory_bridge,runtime_controls,tool_bridge}.py` (6,6,13,6,7).
- **Computer tool** for desktop control: `src/hutch/tools/computer.py:42-` with the `src/hutch/computer/`
  package (frames, human handoff, budgets, native transport); 10 test files, 87 tests total.
- **Worktrees** exist only in the code-handoff path; there is no generic worktree tool for Bots in the
  committed baseline (`grep -rn worktree src/hutch --include=*.py` is confined to `code_handoff.py`,
  `cli.py`, deletion/retention notes and the `workdir` validator). `tests/test_worktree_tools.py` (15) tests
  the handoff/worktree helpers.
- **Runtime page** (`app.js:14017-14025`, `paintRuntime` `~13680-13780`) shows runtime readiness, queue and
  automation pause, multi-step jobs, and source inbox state; it does **not** show coding handoffs.

Absent (the "orchestration" loop beyond a reviewed handoff):

- No plan to isolate to implement to **automated test** to review to **merge** pipeline managed by Hutch.
  Commits, pushes, deploys and merges are deliberately denied to the OpenCode task profile
  (`code_handoff.py:418-421`), and the human is told to "review the branch before copying or merging"
  (`cli.py:246-250`). There is no merge command, no PR/CI integration, and no deterministic verification
  gate in the handoff path; the task prompt only asks the agent to run relevant checks and report
  (`code_handoff.py:369-376`), which Hutch does not verify.
- No worktree cleanup/GC: worktrees are explicitly retained (`app.py:591-594` status labels;
  `cli.py:247-248`; no prune path in `code_handoff.py`).
- No Hutch-managed coding sandbox: OpenCode shell approvals and provider billing are outside Hutch's
  sandbox/budget, as the prompt and docs state (`code_handoff.py:369-376`; `docs/requirements.md` UI-20 row).
- No autonomous multi-agent coding supervision (one handoff at a time, owner-launched); coordinator tasks are
  general work delegation, not coding verification.
- No UI to list all handoffs / review diffs / act on `changes_ready`; only the per-chat card + CLI.

---

## D. Shipped workflows and deliverables: IMPLEMENTED (strongest subsystem)

### D1. Workflow engine

- Package split is real and coherent: typed plan schema (`src/hutch/workflow/plan.py:51-52` node kinds;
  `Check` kinds schema/artifact/command/human/agent_review `plan.py:118-175`), bounded expression interpreter
  with no eval/import/IO (`expr.py:1-30`), compile-time identity/reference/envelope validation
  (`compile.py:1-40,313-364`), deterministic interpreter over durable node records (`engine.py:1-30`),
  reviewed pure ops (`ops.py:1-20`, `TRANSFORM_OPS` `ops.py:29-56`), persistence
  (`persistence.py` tables `workflow_definitions/revisions/runs/nodes/questions/amendment_history`
  `persistence.py:86-200`), submission authority gates (`submit.py:1-25`), role qualification/probes
  (`qualify.py`, `probes.py`), routing policy off/suggest/auto (`routing.py:1-12`), bounded budgets
  (`usage_budget.py`, `budget_rules.py`), amendments (`amendments.py:1-8`).
- Verification is real: `engine._verify` (`engine.py:659-753`) runs independent checks, treats only
  schema/artifact/command/human as certifying evidence, treats agent review as advisory, applies a declared
  fail policy (stop/continue/repair with bounded rounds), reconstructs repair rounds after a crash, and
  revokes a previously-claimed output when a later verification fails
  (`tests/test_workflow_engine.py:175-229`). Effect receipts are durable and reused after crash
  (`tests/test_workflow_engine.py:1127-`).
- API: `src/hutch/server/workflows_api.py:623-1312` - definitions, immutable revisions, activate, validate,
  submit plan, run saved workflow, run detail/nodes/questions, amendments preview/drain/adopt/history,
  stop/pause/resume, qualification probes, phone workflow run endpoints. SPA workflow panel in chat
  (`app.js:441-470,8286`), phone workflow UI (`app.js:12873-13171`). Schedules can link an activated immutable
  revision + inputs (`models.py:126-131`; route validation `app.py:3254-3336`; scheduler admission in
  `engine.py:1469-1520`).
- Shipped starter: campaign-report (pure CSV math with verification and explicit "changes no campaigns"
  language, `workflow/campaigns.py:78-143`; preview endpoint `workflows_api.py:635-648`).
- Tests: 17 workflow test files, 218 test functions total: `test_workflow_engine` (41),
  `test_workflow_api` (37), `test_workflow_regressions` (24), `test_workflow_plan` (23),
  `test_workflow_qualify` (14), `test_workflow_routing` (14), `test_workflow_budget_rules` (13),
  `test_workflow_usage_budget` (11), `test_workflow_steps` (10), `test_workflow_ops` (8),
  `test_workflow_probes` (8), `test_workflow_cli` (5), `test_workflow_effect_receipts` (4),
  `test_workflow_csv_acceptance` (2), `test_workflow_coding_repair_acceptance` (1),
  `test_workflow_document_research_acceptance` (1), `test_live_guide_workflows` (1).

### D2. Documents pipeline

- Schema `documents` + `document_versions` (`store.py:1399-1444`) with per-version filename, bytes, sha256,
  storage path, source (generated/revised), run/event provenance, generator, `validation_state`
  (passed/passed_with_warnings/failed), findings JSON, preview mode/data, page count, source spec.
- Content-addressed commit protocol: stage, fsync, journal, `os.replace` into a per-version dir, fsync
  dirs, SQLite row, clear journal; unrow-ed versions are invisible and reconciled; serving re-verifies
  hash and size and fails honestly (`src/hutch/documents/storage.py:1-20,245-280`).
- Generators: PDF, DOCX, XLSX, PPTX, MD/TXT/CSV/JSON/YAML/ZIP under `src/hutch/documents/docgen/`
  (`docgen/__init__.py`, `pdfdoc.py`, `docxgen.py`, `xlsx.py`, `pptx.py`, `render.py`). Run tools:
  `create_document` / `revise_document` / `inspect_document` (`src/hutch/tools/documents.py:117-`,
  registered `tools/__init__.py:27,90`).
- Routes: list/readiness/get/versions/download/preview/pages at `app.py:5565-5730`; download re-verifies
  bytes (`tests/test_documents_pipeline.py:279-294`).
- Durable document job pipeline (watched folder to ingest/extract/ocr/index/summarize/deliver) with
  per-step checkpointing (`src/hutch/pipelines.py:1-12,78-358`; job tables `store.py:1513-1550`);
  source admission mode "documents" (`src/hutch/monitoring.py:196-230`).
- Tests: `test_documents_pipeline.py` (18), `test_documents_revisions.py` (5),
  `test_document_store.py` (11), `test_document_renderer_loading.py`, `test_jobs.py` (13),
  e2e `test_documents.py` (1).

### D3. Outputs / media / synthesis / artifacts

- Media: render jobs (`src/hutch/media/jobs.py`, 592 lines), renderers (`media/render.py`), validation
  (`media/validate.py`), content-addressed storage (`media/storage.py`), providers ComfyUI/OpenAI images.
  Serving routes re-verify size+sha256 on every read and return 410 on mismatch
  (`src/hutch/media/routes.py:1-103`). Tools `create_media`, `render_diagram` (`tools/media.py:111,240`).
- Synthesis: ingest/authoring/model/tts/infographic/storage (6 modules, ~2.9k lines), tools
  `ingest_source`, `register_manifest`, `register_script`, `render_audio_overview`,
  `render_infographic` (`tools/synthesis.py:74-`); artifact content route `app.py:6377`.
- Run artifacts: `/api/v1/tasks/runs/{id}/artifacts` (hash/size/state/version/download URL)
  (`app.py:5049-5058`), artifact bytes served only after sha256+size verification with
  `X-Hutch-Artifact-Verified: sha256` and traversal/symlink rejection (`app.py:5183-5230`);
  conversation artifact index + explicit cross-conversation shares (`app.py:5060-5230`); conversation
  artifact share content route re-verifies bytes (`app.py:5218-5230`).
- Investigation store (facts/claims/evidence/media/frames) in `src/hutch/store.py` `1618-1780` adds further
  verified-media paths and durable evidence records.

What "deliverable verification" honestly means: bytes are hash-verified everywhere they are served; document
generation records format validation findings and preview state; workflow outputs are "verified" only if a
verify node's independent checks pass (and a later failure revokes the claim). There is no semantic quality
verification of prose/code/content, no external-recipient confirmation, and no verification that a generated
document matches user intent beyond declared schema/preview checks.

---

## E. Persistent automations: PARTIAL (scheduler strong; trigger/condition/history model thin)

### E1. Scheduler semantics (implemented, well tested)

- Model: `Schedule` (`src/hutch/models.py:115-186`) - id, name, trigger (cron/interval/once), cron,
  interval_seconds, anchor_at, IANA timezone, catch_up (coalesce/skip), overlap (queue/skip/buffer_one),
  enabled, prompt, optional linked workflow definition/revision/inputs, created_at. Schedules live inside the
  Bot's JSON doc (a list), not in their own SQL table; the Bot aggregate is the authority.
- Engine `src/hutch/scheduler.py`: IANA zone resolution fails closed (`:69-90`); DST gap times do not fire and
  ambiguous fall-back times fire once (`:96-107`); newest-on-or-before and next-after for cron/interval/once
  (`:134-225`); window counting with a 50-window cap and an explicit "uncertain" flag (`:33,227-268`); skip
  grace proportional to period (`:288-292`); due claims with optimistic marker compare (`:348-398`); invalid
  timezone blocks and is recorded instead of falling back to UTC (`:360-363`); overlap skip and buffer_one
  semantics (`:385-393`); occurrence history and skip records.
- Durability: `schedule_occurrences` (base schema `store.py:281-285`) and the current
  `schedule_occurrences_v20` (`store.py:528-556`) keyed `(schedule_id, occurrence)`; `schedule_identities`
  reserves IDs after removal (`store.py:557-`); markers in kv (`<id>:last_fire`); claim + marker advance +
  run insert commit atomically (`store.py:6723`, `engine.py:1465-1540`). Workspace-wide pause is persisted
  (`store.py` workspace_settings; migration 40) and checked at admission (`scheduler.py:350-351`).
- APIs: `/api/v1/schedules/control`, `GET /api/v1/schedules` (with preview),
  `PUT /api/v1/bots/{ref}/schedules/{id}`, `run-now`, `skip-next`, `occurrences`, `DELETE`
  (`app.py:3153-3410`). UI: `#/schedules` (`app.js:1898,7201-7218`; paintSchedules), per-Bot schedule editor
  (`app.js:8281-8943`), and the runtime page's queue/automation pause switch. Tests:
  `tests/test_scheduler.py` (21) including explicit DST spring/fall and Vancouver cases,
  `tests/test_schedule_durability.py` (6).

### E2. Trigger types and policies

Implemented:

| Trigger family | Implementation | Evidence |
|---|---|---|
| cron (5-field, IANA zone) | `Schedule.trigger=cron`, croniter + zoneinfo | `scheduler.py:134-175,348-398` |
| fixed-rate interval | `trigger=interval`, `interval_seconds`, UTC anchor grid | `scheduler.py:190-225` |
| one-shot at instant | `trigger=once`, `anchor_at` | `scheduler.py:177-188` |
| file/folder changes | source kind `folder`: stat signature + content hash, renames, bounded scans, excluded Hutch state paths, symlinks never followed | `src/hutch/sources/folder.py:1-16,71-125` |
| git ref changes | source kind `git`: read-only plumbing, history rewrite reported once | `src/hutch/sources/git.py:1-16` |
| RSS/Atom feed changes | source kind `feed`: conditional GET, XML entity-expansion refusal, bounded parse | `src/hutch/sources/feed.py:1-16` |
| event admission policies | cooldown, max-per-hour, deferred (never dropped) admission, one idempotent run per batch, "documents" mode creates one durable job | `store.py:11306-11360` (`admit_source_changes`), `monitoring.py:120-203`, `src/hutch/channels/` for Telegram channel |
| workflow-linked schedules | occurrence submits an immutable saved workflow revision with inputs | `engine.py:1469-1520`; `app.py:3254-3336` |

Event sources table: `event_sources` (kind folder/git/feed only, bounded JSON config, admission policy,
revision, cursor, backoff fields) and `source_events` inbox with unique
`(source_id, event_key, content_hash)` (`store.py:1446-1512`). APIs `/api/v1/sources*` (`app.py:2537-2604`),
UI in the runtime page (sources list, events, check-now, enable/disable, delete; `app.js:13548,13866-13990`).
Tests: `tests/test_sources_api.py` (13), `tests/test_catalog_sources.py` (10), unit `tests/test_channels.py`
(21), e2e `test_channels.py` (2).

Missing:

- **No inbound webhook/HTTP trigger.** `event_sources.kind` is constraint-limited to
  `('folder','git','feed')` (`store.py:1449-1450`); channels explicitly report
  `unavailable: ['slack_socket_mode','signed_webhooks']` (`src/hutch/server/channels_api.py:62-68`), and the
  roadmap lists webhook/event triggers as open (`docs/roadmap.md:187`).
- **No outbound notifications** for approval-needed/failure/result (roadmap
  `docs/roadmap.md:167-168,180`); delivery machinery exists only for Telegram replies within a channel
  conversation (`src/hutch/channels/persistence.py:20-60`).
- **No conditions/filters on schedules** beyond the source config's include/ignore globs and prompt template.
  A `Schedule` cannot say "run unless X", "only if the file matches", or "only when the previous run
  succeeded".
- **No approval checkpoints on automations.** A scheduled run starts without review; approvals only appear
  mid-run for tools. There is no "ask me before this routine starts" or "approve the run's plan/output" step.
- **No revision history for schedules.** `put_schedule` replaces a schedule inside the Bot document
  (`store.py:4027-4100`); idempotency receipts are kept for workflow-linked writes and
  `schedule_identities` reserves removed IDs, but no append-only schedule-revision/audit table exists.
  (Workflow definitions do have immutable revisions; `Schedule` itself does not.)
- **No per-routine failure policy/retry** (no backoff for schedules; source checks have backoff), no
  per-routine run history page (only the occurrence list of claimed windows and global run history), no
  automation-level alerting.
- Interval schedules intentionally do not follow DST (fixed-rate UTC anchor); only cron schedules are
  calendar-local. There is no "local-time interval" mode.
- No calendar/mail file triggers beyond folder/git/feed, and no model-free condition DSL for automations.

Run observability that does exist: runtime page queue/automation cards, jobs list with step statuses and
artifact hash (`app.js:13730-13780`), sources inbox counts (`app.py:2520-2604`), run history
`#/activity/history` and run detail, schedule occurrence history. So observability is "operator-level",
not "per-automation timeline + alerts".

---

## F. Dashboard information architecture

Single navigation model `src/hutch/server/nav.py:11-30`, rendered by the SPA shell and server pages:

- **Primary**: Chat (`#/chat`), Tasks (`#/tasks`), Needs you (`#/approvals`).
- **More**: Activity (`#/activity`), Scheduled work (`#/schedules`), Catalog, Models, Usage, Runtime, Assistants.
- **Foot**: Apps & AI (Connections), Settings.

Where each assessed area is surfaced:

| Area | UI surface today | What it actually shows |
|---|---|---|
| Personal briefing/agenda | none | no route/tab; Home is Chat; overview is operator triage |
| Commitments | none | absent |
| Tasks (workspace) | `#/tasks` (`app.js:1903`, `static/tasks.js`) | coordinator to specialist assignments, briefs, model source, usage, checkpoints, redirect/stop/continue |
| Approvals | `#/approvals` -> modal over Chat (`app.js:7841-7848`) | pending tool approvals, receipts needing review, filters, expiry |
| Activity | `#/activity` (`renderOverview`) | stats, approvals, runs, failures, stale assistants; run history `#/activity/history` |
| Calendar | none (Connections setup only) | grant review under Apps & AI; data only via agent tools |
| Mail | none (Connections setup only) | same |
| Memory facts | Assistant settings fact panel + chat fact/share cards (`app.js:4661-4955`) | revisions, review, exports, shares, purge requests |
| Coding handoffs | per-chat card + CLI command | status, launch/reconcile commands, changed-file summary |
| Workflows | in-chat workflow panel (`app.js:441-470,8286`), phone workflow views | definitions/runs/nodes/questions/amendments |
| Schedules/automations | `#/schedules` + per-Bot editor + runtime page queue card | next fire, preview, run-now, skip-next, occurrences, pause, source inbox/jobs |
| Runtime health | `#/runtime` (`app.js:14017-14025,13680-13780`) | service readiness, queue/automation, jobs, sources |

Notes: the nav label "Tasks" does not mean user commitments, and "Needs you" is a dialog, not a standalone
page despite being a primary nav item. There is no shared/family surface, no calendar agenda, no inbox, no
deliverables library page (documents/artifacts are surfaced inside chat and run detail), and no automation
revision/history page. Route/nav drift is guarded by `tests/test_navbar_consistency.py` (6 tests).

In-flight: `.pipeline/.../DECISIONS.md` D-08 plans one new primary destination Today (`#/today`) and one
"Shared" under More (`#/shared`); neither route exists yet in the working tree at snapshot time.

---

## G. Test coverage inventory (exact files and counts at HEAD)

Counts are `^def test_` functions. This is a map, not a pass claim; only the focused run in section 0 was
executed.

Personal operations (A): `tests/test_fact_memory.py` 15, `tests/test_fact_purge.py` 11,
`tests/test_memory_continuity.py` 8, `tests/test_approval_cas.py` 16,
`tests/test_file_approval.py` 6, `tests/test_google_calendar.py` 27,
`tests/test_google_calendar_api.py` 6, `tests/test_outlook_calendar.py` 9,
`tests/test_outlook_calendar_api.py` 2, `tests/test_outlook_calendar_write.py` 10,
`tests/test_outlook_calendar_write_api.py` 1, `tests/test_google_mail.py` 5,
`tests/test_google_mail_api.py` 7, `tests/test_google_mail_send.py` 9,
`tests/test_outlook_mail.py` 5, `tests/test_outlook_mail_api.py` 2,
`tests/test_outlook_mail_send.py` 9, `tests/test_outlook_mail_send_api.py` 2,
`tests/test_task_templates.py` 2. Calendar/mail tests are largely client/API contract tests with fake
transports; live OAuth accounts are explicitly unverified in `docs/requirements.md`.

Shared spaces (B): no dedicated commitment/space tests exist. Sharing is covered by
`tests/test_fact_memory.py` (share cases within it), `tests/test_bot_deletion_artifact_shares.py` 1, and
`tests/test_memory_continuity.py` (artifact refs/canonical history). `tests/test_coordinator_tasks.py` 4
covers the specialist roster/plan (two-specialist plans, redirects, stop-all). There is **no test for
multi-participant visibility** because no such model exists.

Coding orchestration (C): `tests/test_code_handoff.py` 11 (includes project-plugin refusal, pinned worktree
does not copy dirty files, real fake-CLI `hutch code run` interrupt/cleanup, reconcile live/gone runner),
`tests/test_worktree_tools.py` 15. Runtime: `tests/test_runtime_opencode.py` 23,
`tests/test_opencode_api.py` 6, `tests/test_opencode_login.py` 6, `tests/test_opencode_memory_bridge.py` 13,
`tests/test_opencode_runtime_controls.py` 6, `tests/test_opencode_tool_bridge.py` 7. Computer:
10 files, 87 tests total (api 10, control 9, desktop 14, doctor 11, frames_and_images 12, human 7,
privacy_authority 5, resources 7, browser_session 6, image_delivery 6). Coordinator:
`tests/test_coordinator_tasks.py` 4.

Workflows/deliverables (D): 17 workflow files, 218 tests (list in D1); documents:
`tests/test_documents_pipeline.py` 18, `tests/test_documents_revisions.py` 5,
`tests/test_document_store.py` 11, `tests/test_document_renderer_loading.py`, `tests/test_jobs.py` 13;
media: `test_media_jobs` 25, `test_media_storage` 13, `test_media_render` 15,
`test_media_validate` 18, `test_media_providers` 10, `test_grounding_media` 10;
synthesis: `test_synthesis_storage` 13, `test_synthesis_tts` 23, `test_synthesis_model` 19,
`test_synthesis_authoring` 5, `test_synthesis_ingest` 13, `test_synthesis_infographic` 7,
`test_synthesis_api` 4, `test_tools_synthesis` 5; artifacts:
`tests/test_test_artifacts.py` 4, `tests/test_bot_deletion_artifact_shares.py` 1; e2e
`test_documents.py` 1, `test_workflow_route_card.py` 1, `test_campaign_report.py` 3.

Automations (E): `tests/test_scheduler.py` 21, `tests/test_schedule_durability.py` 6,
`tests/test_sources_api.py` 13, `tests/test_catalog_sources.py` 10, `tests/test_jobs.py` 13,
`tests/test_channels.py` 21, e2e `tests/e2e/test_channels.py` 2,
`tests/e2e/test_workflow_route_card.py` 1. No test covers webhook triggers, notification delivery,
automation approval checkpoints or schedule revision history because those features do not exist.

Dashboard: `tests/test_navbar_consistency.py` 6, `tests/test_ui_endpoints_exist.py`,
`tests/test_ui_vocabulary.py`, e2e `test_fresh_state_routes.py` 1, `test_page_titles.py` 2,
`test_experience_surfaces.py` 4, `test_stop_all.py` 3, `test_computer_panel.py` 6,
`test_bot_deletion_ui.py` 7.

---

## H. In-flight work observed (not part of the baseline verdicts)

Observed 2026-10-30 22:30-22:35 America/Vancouver in the shared working tree; recorded for handoff
accuracy, not audited as complete:

- `src/hutch/personal/__init__.py`, `models.py` (224), `commitments.py` (323), `spaces.py` (211),
  `store.py` (32), `today.py` (242); `src/hutch/personal_schema.py` (101);
  `src/hutch/server/personal_api_models.py` (80); `src/hutch/server/personal_api.py` (appeared during audit).
- `src/hutch/store.py` diff adds only the `personal_schema` import and its `_MIGRATIONS` entry.
- Not present at snapshot: `tests/test_commitments.py`, `tests/test_spaces.py`, `tests/test_today.py`,
  `tests/test_personal_api.py`, `src/hutch/tools/commitments.py`, `#/today`/`#/shared` routes,
  Today/Shared static modules. These correspond to the Lead plan slices S2-S5 still in progress.
- Numbering discrepancy to resolve before commit: resulting `user_version` is 84 (verified by importing
  `hutch.store` with the current working tree); `personal_schema.py:1` and `DECISIONS.md` call it v82,
  `ARCHITECTURE.md` says v84, and the assignment baseline says v81. The migration docstring should state the
  version users will actually observe.

## I. Bottom line

The repository is much stronger than a "personal assistant" baseline in durability, approvals, verification,
workflow execution and schedule correctness, and much weaker in the *personal/family* product layer: no
briefing, no commitments, no multi-participant identity, no calendar/mail surfaces, no coding review/merge
loop, and automations are cron/file/git/feed runners without conditions, approval checkpoints, revision
history or notifications. The Lead's concurrent slice is filling the commitments/Today/shared-scope part of
that gap; the remaining high-impact gaps are the ones ranked in `GAP-REGISTER.md`.
