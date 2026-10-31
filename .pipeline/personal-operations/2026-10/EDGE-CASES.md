# EDGE-CASES: personal operations, shared spaces, coding, workflows, automations

Date: 2026-10-30 (America/Vancouver). Baseline: committed HEAD `989e5bc0`. Status vocabulary:

- **handled** - a code path implements a deliberate, fail-closed behavior and at least one test exercises it
  (or a database constraint makes the bad state unrepresentable); not a claim of live-provider verification.
- **partial** - a real code path exists but leaves a material case open, or the guarantee is narrower than the
  user-facing promise.
- **unhandled** - no code path in the committed baseline.
- **in-flight (unverified)** - the Lead's uncommitted personal-operations work appears to target this case, but
  it was not testable at snapshot time; verify before claiming.

Evidence is `file:line` at HEAD. Full traces are in `CURRENT-STATE.md`; proposed fixes and slices are in
`GAP-REGISTER.md`.

---

## 1. Identity and ownership

| Edge case | Status | Evidence | Notes |
|---|---|---|---|
| One local owner only; no second human principal can authenticate | handled (by design) | `src/hutch/server/security.py:320-345`; `src/hutch/store.py:1296-1298` (singleton owner row) | Single-owner is the security boundary. Family/multi-participant use is impossible without G07. |
| Paired phone is a distinct principal, not a reusable dashboard token | handled | `security.py:320-345`; route capability table `src/hutch/server/app.py:100-160` | Phone gets capability-scoped sessions; local owner token never accepted remotely. |
| Approval decision is bound to the exact action shown (hash), and races resolve once | handled | `src/hutch/approvals.py:43-51,79-148`; `src/hutch/store.py:97-105`; `tests/test_approval_cas.py` (16) | Stale/denied/expired decisions cannot authorize a different action. |
| Outward actions (calendar create, mail send, browser handoff) never become sticky allows | handled | `src/hutch/approvals.py:79-148`; `models.py:769-800` (outward flag); `src/hutch/tools/google_calendar.py:82-84,112-114` | auto mode still asks via `ask_in_auto=True`. |
| Approval TTL default-deny and expiry sweep | handled | `src/hutch/approvals.py:235-288`; `src/hutch/engine.py:1648` | Expired approvals are a decision, not an open request. |
| Cross-Bot fact share only an exact approved, current revision; both bots memory-enabled | handled | `src/hutch/store.py:1105-1167` (guard trigger); `src/hutch/fact_memory.py:178-238`; `tests/test_fact_memory.py:76-143` | Revocation is one-way and history retained. |
| Artifact share only from a different conversation, verified bytes, no copy into target workspace | handled | `src/hutch/store.py:445-515`; `src/hutch/server/app.py:5113-5159,5218-5230` | Target gets a reference to the source event; content served only after sha256/size check. |
| Specialist admission cannot use the coordinator itself, unlisted Bots, or stale capability snapshots | handled | `src/hutch/store.py:1238-1266`; `src/hutch/coordinator_tasks.py:48-71,137-157,216-257`; `tests/test_coordinator_tasks.py` | Membership is re-read inside the admission transaction. |
| Integration/tool grants are per Bot and disabled by default | handled | `src/hutch/store.py:2284-2307`; `src/hutch/tools/__init__.py:117-120` | An uninstalled/disabled integration grants no tool. |
| Owner deletes an assistant: shares revoked, fact shares tombstoned, grants removed, channels disabled | handled | `src/hutch/bot_deletion_plan.py:95-205`; `src/hutch/bot_deletion_steps.py:48-85`; `tests/test_bot_deletion_artifact_shares.py`; e2e `test_bot_deletion_ui.py` (7) | Deletion plan is ordered and auditable; permanent content deletion still absent (data section). |
| A second human can be granted scoped access to some items but not others | unhandled | no auth principal for a second person (see row 1) | This is the core family/shared-spaces gap (G07); in-flight spaces are data scoping only. |
| Grant revoked while a Bot run is in flight | partial | tools re-read grants per call (e.g. `src/hutch/tools/google_calendar.py:96-101,118-125`; `tools/google_mail.py:37-40`) | In-process tools fail closed after revoke; a run's already-built prompt/tool list is a snapshot. In-flight space grants are documented as per-call; verify. |
| Space membership revocation takes effect before a queued run executes | in-flight (unverified) | ARCHITECTURE.md "bot_space_ids() evaluated per call; revoked or archived grants fail closed" | Needs a test with revoke between admission and execution; not committed at snapshot. |
| Assistant captures a "commitment" the user never made | in-flight (unverified) | DECISIONS.md D-03: assistant rows start `proposed`; owner-only confirm path | Verify the tool cannot create `confirmed` rows and Today labels them "Suggested". |
| Assistant reports completion the owner did not verify | in-flight (unverified) | DECISIONS.md D-04: `unverified` vs `owner_confirmed` | Verify no tool path can write `owner_confirmed`. |

## 2. Execution

| Edge case | Status | Evidence | Notes |
|---|---|---|---|
| Two workers race for the same run/occurrence; stale owner writes | handled | ADR-0001/0003; `src/hutch/store.py` lease/fence columns and `store.py:2464+` authoritative run columns; `tests/test_schedule_durability.py:48-72` | A stale fence is rejected at commit. |
| Workflow attempt crashes mid-node: continuation, not replay | handled | `src/hutch/workflow/runtime.py:1-12`; `src/hutch/workflow/engine.py:1-30`; `tests/test_workflow_engine.py:377-407,1053-1093` | Settled node records are skipped; bounded at two continuations. |
| External side effect committed but process dies before local record | handled | `src/hutch/actions/execute.py:1-25`; `tests/test_workflow_effect_receipts.py` (4); `tests/test_workflow_engine.py:1127-` | Effect receipts are durable; succeeded steps are not repeated; uncertain results are not auto-retried. |
| Approval prompt waits across a process boundary and the grant changes | handled | `src/hutch/tools/google_calendar.py:118-125` | Grant re-check after wait cancels the action. |
| Provider write result ambiguous (timeout after send) | handled | `src/hutch/tools/google_calendar.py:126-134`; `models.py:49-76` (`outcome_unknown`); mail send tools | Run ends `outcome_unknown`, not success and not retry. |
| Laptop asleep over scheduled windows | handled | `src/hutch/scheduler.py:227-268,348-398`; `models.py:601-` (`missed_windows`); `tests/test_scheduler.py:138` | Coalesce once, record how many windows were missed; cap 50 with an explicit uncertain flag. |
| New occurrence due while the Bot is busy | handled | `src/hutch/scheduler.py:385-393`; `tests/test_scheduler.py:297` | queue/skip/buffer_one, each with a visible skip record. |
| Workspace-wide pause races a due snapshot | handled | `src/hutch/engine.py:1465-1520`; `tests/test_scheduler.py:314`; `tests/test_schedule_durability.py` | Admission re-checks pause inside the transaction. |
| Human computer handoff while automation is running | handled | `src/hutch/server/app.py:5828-5835`; `app.js:8305`; `src/hutch/computer/human.py`; 7 computer-human tests | Resume is refused while a controller is present; handoff pauses automation. |
| Telegram duplicate delivery or crash gap admits once; ambiguous send needs evidence | handled | `tests/test_channels.py:61,158,243` (21 tests); `src/hutch/channels/persistence.py:20-60` | Cursor/lease/delivery states are durable; resend requires reconciliation evidence. |
| Source scan crashes after reading but before commit | handled | `src/hutch/sources/__init__.py:1-14`; `src/hutch/store.py` `record_source_check` transaction; unique `(source_id,event_key,content_hash)` | Re-scan dedupes; cursor and events commit together. |
| Document commit crashes between promotion and SQLite row | handled | `src/hutch/documents/storage.py:1-20,245-280`; `tests/test_document_store.py`; `tests/test_documents_pipeline.py:279` | Unrow-ed version is invisible and reconciled; tampered/missing bytes fail honestly. |
| Media/Document bytes replaced on disk after commit | handled | `src/hutch/media/routes.py:1-20,60-100`; `src/hutch/server/app.py:5183-5230` | Size+sha256 re-verified at serve time; 410/404 instead of serving. |
| Workflow question answered after restart, including independent questions | handled | `tests/test_workflow_engine.py:708-1009` | Answers are bound to question ids and durably recorded. |
| Coding handoff launch: Ctrl+C, process-group leftovers, unknown exit | handled | `src/hutch/code_handoff.py:28-112`; `src/hutch/cli.py:200-330`; `tests/test_code_handoff.py:358-483` | `cleanup_incomplete` + `reconcile` refuses a live identity; terminal foreground restored. |
| Same coding handoff launched twice | handled | `src/hutch/store.py:5934-5947` (CAS `prepared -> launching`) | Second launch gets an explicit refusal. |
| Source scan encounters an unreadable folder/volume | handled | `SourceUnavailable` in `src/hutch/sources/__init__.py`; backoff recorded in `src/hutch/monitoring.py:120-160` | Recorded as error with backoff, never "no change". |
| Two supervisors poll/send the same channel | handled | `src/hutch/channels/persistence.py` lease fields; `tests/test_channels.py:180` | One owner at a time; late poll fenced. |

## 3. Time and DST

| Edge case | Status | Evidence | Notes |
|---|---|---|---|
| Cron time that does not exist on spring-forward day | handled | `src/hutch/scheduler.py:96-107`; `tests/test_scheduler.py:82` | Vixie semantics: skipped times do not fire; no silent UTC substitute. |
| Ambiguous fall-back local time | handled | `src/hutch/scheduler.py:96-107`; `tests/test_scheduler.py:96` | Fires once (fold=0). |
| Long downtime across many windows | handled | `src/hutch/scheduler.py:227-268`; `tests/test_scheduler.py:138,207` | Newest true occurrence claimed; count capped and flagged uncertain. |
| Invalid or unavailable IANA zone | handled | `src/hutch/scheduler.py:69-90,360-363`; `tests/test_scheduler.py:121`; save-time validation `src/hutch/server/app.py:3311` | Blocked record with reason, never UTC fallback. |
| Fixed-rate interval across a DST change | handled (by design) | `src/hutch/scheduler.py:190-225` | Interval is UTC-anchored; it does not follow wall-clock time. Document this; no local-time interval mode. |
| Catch-up=skip grace window | handled | `src/hutch/scheduler.py:288-292`; `tests/test_scheduler.py:59,70` | Grace is 25% of the estimated period, clamped to [60 s, period]. |
| Skip-next consumes exactly one occurrence | handled | `src/hutch/scheduler.py:411-419`; `tests/test_scheduler.py:244` | One-shot kv marker consumed atomically with the claim. |
| Run-now must not disturb the recurring marker | handled | `src/hutch/server/app.py:3341-3372`; `tests/test_scheduler.py:260` | Endpoint asserts the marker is unchanged. |
| Approval expiry counted from UTC timestamps | handled | `src/hutch/models.py:769-800` (`ttl_seconds`, `expires_at`); `src/hutch/approvals.py:273-288`; `src/hutch/engine.py:1648` | Default-deny at the deadline; visible countdown. |
| Calendar event input without explicit time zone | handled | `src/hutch/tools/google_calendar.py:16-20,62-70` | Schema requires ISO-8601 with explicit offset; provider conversion errors are returned, not guessed. |
| Naive local timestamps persisted anywhere | handled (policy) | AGENTS.md rule; `iso`/`utcnow` in `src/hutch/models.py`; migration/parse code uses ISO-8601 UTC | New personal code must follow this; verify in review. |
| Today's local day is 23 or 25 hours long (DST) | in-flight (unverified) | ARCHITECTURE.md "convert each boundary separately" | Must compute both boundaries from local date then convert to UTC; a naive midnight-to-midnight comparison is wrong. Add a DST-day test. |
| Commitment due date and chosen timezone stored separately | in-flight (unverified) | ARCHITECTURE.md commitment fields `due_at` (UTC instant) + `due_timezone` (IANA) | Verify unknown zone fails closed (422) and the UI shows the owner's local day. |
| Workflow/node deadlines and budgets use monotonic vs wall time | handled (bounded) | workflow engine budget wall-seconds checks in `src/hutch/workflow/engine.py`; OpenCode poll interval in `src/hutch/runtime/opencode.py`; tests use controlled clocks | No live clock-skew claims; budgets are wall-clock by design. |

## 4. Integrations

| Edge case | Status | Evidence | Notes |
|---|---|---|---|
| Calendar grant revoked/changed while an approval is pending | handled | `src/hutch/tools/google_calendar.py:96-101,118-125` | Action cancelled with an explicit message; nothing sent. |
| Calendar creation cannot invite guests, edit, delete or write multiple calendars | handled | `src/hutch/tools/google_calendar.py:73-80,109-111` | Guest-free single event on the granted calendar only. |
| Mail read vs send grants are separate capabilities | handled | `src/hutch/store.py:1061-1080,1353-1374`; `src/hutch/tools/google_mail.py`, `google_mail_send.py`; tests | A read grant cannot send; a send grant cannot read. |
| Gmail data reaches only local-inference Bots | handled | `src/hutch/tools/google_mail.py:1,34-36` (validate_local_gmail_bot); `src/hutch/tools/__init__.py:160-180` | Refused with a reason on hosted routes; rechecked when the tool set is built. |
| Hosted/local route change after a tool call was authorized | partial | grants are per-Bot; runtime capability snapshot is checked at admission (`coordinator_tasks.py:48-71`) and tools re-read grants | Not all integration tools re-validate route/local-only state at execution time; treat as a review item for any new integration. |
| Strict-offline Bot with external reads / browser / computer | handled | `src/hutch/tools/__init__.py:117-120`; `OFFLINE_WITHHELD_TOOLS` in `src/hutch/integrations/catalog.py` | External reads and computer are withheld, not silently attempted. |
| OAuth token expiry/refresh and revoked accounts | partial | `GoogleCalendarBook` error paths in `src/hutch/google_calendar.py`; tools return errors; live OAuth accounts explicitly unverified in `docs/requirements.md` | Unit tests use fakes; provider revocation/refresh behavior has no live-account evidence. |
| Telegram sender not in the allowlist / unsupported update types | handled | `tests/test_channels.py:88-106`; `src/hutch/channels/telegram.py` | Ignored without admitting a run; cursor still advances safely. |
| Bot paused or channel disabled while messages are queued | handled | `origin_allowed` in `src/hutch/channels/persistence.py`; `tests/test_channels.py:130,141` | Queued authority re-checked; pause stops admission and claim. |
| Inbound webhook/HTTP trigger (GitHub/Stripe/Home Assistant) | unhandled | `src/hutch/store.py:1449-1450` (kind CHECK folder/git/feed); `src/hutch/server/channels_api.py:62-68` (`signed_webhooks` unavailable); roadmap `docs/roadmap.md:187` | G04. |
| Outbound notification to a human when approval is needed or a run fails | unhandled | only Telegram channel replies exist (`src/hutch/channels/persistence.py:20-60`); roadmap `docs/roadmap.md:167-168,180` | G05. A closed tab means an expired approval, by default-deny. |
| Folder source escapes its root through symlinks, or watches Hutch's own state | handled | `src/hutch/sources/folder.py:71-125` (realpath containment, no symlink follow, excluded paths recorded) | Excluded changes are visible in the inbox, not silently dropped. |
| Feed XML entity expansion / oversized payload | handled | `src/hutch/sources/feed.py:1-16` (doctype/entity refusal, byte ceilings); `tests/test_catalog_sources.py` | Parsing is bounded and fails as an error, not "no change". |
| Git source mutates the repository or fetches | handled (read-only design) | `src/hutch/sources/git.py:1-16` | Read-only plumbing; history rewrite reported as one event. |
| Governed integration (MCP/stdio) enabled without an explicit per-Bot grant | handled | `src/hutch/store.py:2284-2307`; `src/hutch/integrations/` catalog | Installed-but-disabled is the default; a tool is mounted only for a grant. |

## 5. Data

| Edge case | Status | Evidence | Notes |
|---|---|---|---|
| Schema migration ordering/versioning and pre-upgrade compatibility | handled | `src/hutch/store.py:2453-2461` ordered list; `tests/test_migration.py`; `tests/fixtures/` | Migrations are atomic and versioned; old DBs upgrade through the list. |
| Older binary opens a newer database | handled | `src/hutch/store.py:2668-2674` version guard (raises; refuses rather than downgrade); pre-upgrade SQLite backup at `store.py:2675-2687` | Do not bypass in migration tooling. |
| Fact content tampering / silent revision rewriting | handled | `src/hutch/fact_memory.py:35-70` triggers (content immutable, archive-not-delete); `tests/test_fact_memory.py:235` | Revisions are append-only; content hash is checked. |
| Fact scope leak between conversations/Bots; legacy unscoped facts | handled | `src/hutch/fact_memory.py:137-176`; `tests/test_fact_memory.py:218,295` | Legacy facts are unreviewed and not shown as private-chat facts. |
| Sharing a superseded or unreviewed fact | handled | `src/hutch/store.py:1105-1167` guard trigger; `tests/test_fact_memory.py:123` | Only a current approved revision can be shared. |
| Permanent scoped deletion of content | partial | `src/hutch/fact_memory.py:52-66` blocks DELETE; purge requests tombstone content (`src/hutch/fact_purge.py:184-191`); `docs/requirements.md` says permanent deletion absent | G14; server backups/provider copies cannot be recalled and must be stated. |
| Artifact path traversal, symlink, or hash mismatch at download | handled | `src/hutch/server/app.py:2206-2240,5183-5230`; `src/hutch/documents/storage.py:245-280` | No-follow walks, recorded hash+size, honest 404/409. |
| Corrupt/missing document or media bytes | handled | `src/hutch/documents/storage.py:245-280`; `src/hutch/media/routes.py:1-20`; `tests/test_documents_pipeline.py:279` | Serving fails honestly; never substitutes another version. |
| Retried mutating request duplicates a run/action/share | handled | `idempotency_keys` table (`store.py:327`); per-route idempotency (tasks, schedules, shares, code handoffs, workflows); `tests/test_action_intents.py` (16) | Missing idempotency on a new mutation is a review blocker. |
| Two processes claim the same schedule occurrence | handled | `schedule_occurrences_v20` PK (`store.py:528-556`); `tests/test_schedule_durability.py:48` | Claim and marker advance are one transaction. |
| Fact search accepts arbitrary FTS/SQL syntax or leaks archived text | handled | `src/hutch/fact_memory.py:156-170` (literal AND terms, cap 10 tokens); `tests/test_fact_memory.py:295` | Bounded and literal. |
| Fact export exceeds bounds / contains secrets | handled (bounded) | export route `src/hutch/server/app.py:4793-4833`; `tests/test_fact_memory.py:311` | 10k revisions / 5k shares / 2 MiB source / 16 MiB response bounds; plaintext warning in the UI. |
| Backup and restore of the whole state | partial | backup path exists in the product (pre-upgrade backup, docs), but restore validation was not traced in this audit | Treat as unverified below the "migration" boundary; a commitments/spaces schema must be included in backup coverage. |
| Job step output reused across a changed input or definition revision | handled | `src/hutch/pipelines.py:1-12`; job schema revision/input hash `store.py:1513-1550`; `tests/test_jobs.py` (13) | A completed step is reused only while its input hash/revision match. |
| Document index generation partially built | handled | `src/hutch/pipelines.py:249-272` applier publishes only when every chunk is written; unpublished generation is invisible | Previous good generation stays active. |

## 6. Coding orchestration

| Edge case | Status | Evidence | Notes |
|---|---|---|---|
| Project folder moved/replaced/symlinked after review | handled | `src/hutch/code_handoff.py:291-357` (realpath, device/inode, git common dir, base commit existence) | Refuses to launch on changed identity. |
| Source repository has a linked/active OpenCode plugin tree | handled | `src/hutch/code_handoff.py:472-489` | Fails closed rather than trusting CLI isolation flags. |
| Host provider credentials leak into the coding CLI | handled | `src/hutch/code_handoff.py:205-241`; `tests/test_code_handoff.py:41` | Environment is rebuilt from an allowlist; private profile only. |
| Agent commits, pushes, deploys, resets or cleans the repo | handled as denial | `src/hutch/code_handoff.py:391-449` (deny edit .git, deny shell commit/push/reset/clean, no subagents) | This is a permission denial, not a merge workflow; no merge feature exists. |
| Owner expects Hutch to run tests and confirm the change | unhandled | task prompt asks the agent to run checks and report (`code_handoff.py:369-376`); Hutch stores no verification receipt | G02 is the fix. "changes_ready" currently means exit 0 plus changed files. |
| Multiple coding tasks / worktrees accumulate | unhandled | worktrees retained on every terminal status (`cli.py:246-248`; `app.py:591-594`); no prune path | G11. |
| Ambiguous OpenCode outcome (process gone, changes unknown) | partial | statuses include `cleanup_incomplete`/`interrupted`/`failed` and `reconcile` (`cli.py:224-330`); `tests/test_code_handoff.py:483` | The status is honest, but no verification means the diff quality is unassessed. |
| Same handoff launched twice, or launched after completion | handled | `src/hutch/store.py:5934-5947` CAS; CLI reports the current status | One-shot launch. |
| Owner's chat was archived / source run not succeeded / question pending | handled | `src/hutch/store.py:5846-5921` | Creation refuses with a specific reason. |
| Agent edits files outside the worktree | partial | OpenCode task profile denies `external_directory` (`code_handoff.py:416`) and prompt forbids it, but an owner-approved shell command can escape any sandbox; provider billing is outside Hutch | Documented limitation in `docs/requirements.md` UI-20. Must remain explicit in UI copy. |
| Two distinct coding handoffs run concurrently | partial | one CLI claim each; no global concurrency limit or shared lock in the baseline beyond the interactive terminal constraint | Consider documenting or enforcing a limit if this becomes a product surface. |

## 7. Frontend

| Edge case | Status | Evidence | Notes |
|---|---|---|---|
| Sidebar navigation and SPA route table drift | handled | `src/hutch/server/nav.py:11-30`; `src/hutch/server/static/app.js:1891-1909`; `tests/test_navbar_consistency.py` (6) | Single nav model; test fails on drift. Any new Today/Shared route must update both. |
| "Needs you" is a primary nav item but a modal over Chat, not a page | partial (UX inconsistency) | `nav.py:14` vs `app.js:7841-7848` | Deep-linking `#/approvals` works but immediately rewrites to `#/chat`; screen readers/titles can surprise. Decide intentionally. |
| Nav label "Tasks" means specialist assignments, not user commitments | partial (semantic hazard) | `src/hutch/server/static/tasks.js:1-10,167` | A new commitments surface must not reuse "Tasks" ambiguously; the in-flight plan adds "Today". |
| Task page polling while hidden or while a form is focused | handled | `src/hutch/server/static/tasks.js:131-161` | Polls only on `#/tasks`, only when visible and no focus; otherwise schedules one retry. |
| Task page silently swallows refresh errors | partial | `src/hutch/server/static/tasks.js:160` (`catch` schedules a retry) | No user-visible failure state on background refresh; acceptable for polling but should surface persistent failures. |
| Deep link/reload restores the same conversation and controls | handled | `src/hutch/server/static/app.js:1911-1961` (generation guard, control restore); e2e `test_fresh_state_routes.py`, `test_persistent_chat.py` | Stale async responses do not overwrite newer state. |
| Modal focus/escape/restore behavior | handled | `src/hutch/server/static/app-modal-focus.js`, `hutch-overlay-*.js`; e2e `test_overlays.py`, `test_popout_layout.py` | New Today/Shared modals must reuse this seam. |
| Responsive layout and zoom/accessibility of new surfaces | handled (existing suite) | e2e `tests/e2e/test_wcag_measured_audit.py`, `test_type_and_spacing_scale.py`, `test_radius_scale.py`, `test_experience_surfaces.py` (4) | The in-flight plan requires 1440/834/390/320 screenshots and 200% zoom for S5; not yet present. |
| Empty state explains missing connections/data instead of faking content | partial | existing empty states exist per page; new Today requires explicit `not_included` notes (ARCHITECTURE.md) | Today must not render a partial aggregate as complete. |
| A page reads calendar/mail/family data that is not connected or not authorized | unhandled | no calendar/mail/family surface exists | The first such surface must show explicit unavailable reasons, not empty lists. |
| New JS module rendered from model/user text | in-flight (unverified) | existing convention `esc()` on all interpolated values; module boundaries in `static/tasks.js`/`catalog.js` | Review every new template for `esc()` and attribute-safe URLs. |
| Live updates arrive while the user is interacting with a form | handled | `app.js:12721-12730` event-driven refresh; e2e `test_live_updates_incremental.py` | Focus-aware guards exist in some panels (e.g. workflow panel); new personal panels should follow the same pattern. |
| Phone UI is capability-gated and cannot act beyond monitor/review | handled | `src/hutch/server/security.py` REMOTE_ROUTE_CAPABILITIES; `app.py:100-160`; phone workflow UI `app.js:12873-13171` | New phone routes must be added to the capability map explicitly; absent means denied. |

---

## 8. In-flight personal-operations edge cases to verify before claiming handled

These are the cases the Lead's slice is intended to cover; at snapshot time no committed test exercised them.
They are deliberately listed separately so the audit does not credit uncommitted behavior.

1. Proposed-vs-confirmed: an assistant tool call cannot write a confirmed commitment; the owner API can.
2. Reported-vs-verified completion: no tool can write owner-confirmed completion; history is append-only.
3. Unknown IANA zone on commitment create/update returns 422, never UTC; local day boundaries are computed
   per boundary for 23/25-hour days.
4. A commitment due at 09:00 in `America/Vancouver` shows the right local day across a DST transition.
5. Space isolation: a Bot without a grant cannot read a space's commitments; revoked/archived grants fail
   closed immediately; a Bot grant cannot read another space's items.
6. Today determinism: the builder performs no model call and no inference; every item carries its source;
   `not_included`/`generated_at`/zone are present; links resolve to authoritative pages.
7. Today pagination/volume: with hundreds of commitments/runs, the response stays bounded and stable.
8. Commitment tools: JSON Schema contract tests (valid accepted, invalid refused before dispatch), group
   allowlist, results labelled as user data and reported-unverified.
9. Migration: additive-only, idempotent, backup-safe; resulting `user_version` matches the docstring
   (currently the working tree imports 84 while `personal_schema.py:1` and `DECISIONS.md` say v82).
10. Nav/route parity for the new Today/Shared destinations and server-rendered page parity for pages that use
    `nav.py`.
11. Deletion/export path for commitments: what happens to a space's commitments when the space is archived, a
    member is revoked, or the Bot is deleted.
12. Phone surface: Today/commitments routes must be added to the capability map explicitly (absent = denied).
