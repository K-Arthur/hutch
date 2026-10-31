# Run log

Date: 2026-10-30/31 (America/Vancouver). Owner: Lead. Local main only; no push.

## Baseline (Phase 0)

| Check | Command | Result |
|---|---|---|
| Working tree | git status --porcelain | 20 modified + 8 untracked files from another session (model-picker/removal work). Preserved untouched; only my hunks staged via index blobs for app.js and index.html. |
| Recent history | git log --oneline -25 | HEAD 989e5bc0, 195 local commits ahead of origin/main, behind 1. |
| Focused baseline | UV_CACHE_DIR=/tmp/uv-cache uv run --frozen --no-sync pytest -q tests/test_migration.py tests/test_scheduler.py tests/test_schedule_durability.py | 68 passed in 20.24s |
| Tooling baseline | npm run check:agent | context hygiene, tool contracts and constitution passed; agent map failed the 120-line cap because the new package adds a row. |

Environment notes: uv needs a writable cache (UV_CACHE_DIR); /tmp is per-execution in this sandbox, so isolated acceptance state lives under the git-ignored .dsh/ui-validation/ inside the workspace; the dashboard runs on 127.0.0.1:8899 with HUTCH_STATE_DIR pointing at that isolated state.

## Milestones

### M1: commitments + shared spaces + Today (commit 003c4365)

- Added schema v84 (src/hutch/personal_schema.py), the personal package (models, commitment repository, space repository, Today builder), API modules (commitments, spaces, Today), page-module wiring, and three test files.
- Store integration adds one import and one migration-list entry; store.py stays at 12588 lines, under its frozen baseline.
- Tests: tests/test_commitments.py, tests/test_spaces.py, tests/test_personal_api.py, tests/test_migration.py, tests/test_navbar_consistency.py => 65 passed in 32.32s.
- Earlier smoke runs on a real temp SQLite store proved proposed/confirmed and reported/verified separation, space grant isolation before/after revoke, dependency blocking and append-only audit events.

### M2: assistant tools (commit 1c454c32)

- Three canonical tools: capture_commitment, list_commitments, report_commitment_done. Tool contract audit: 43 registered tools, schemas certifiable, specs match.
- Tests: tests/test_commitment_tools.py => 10 passed. Covers proposals cannot complete, ungranted space refusal, grant/revoke visibility, schema refusal of invalid arguments, dry-run writes nothing.

### M3: Today + Shared dashboard (commit dd8d59b3)

- New primary destination Today and More destination Shared; nav.py, SPA route table, palette, sidebar markup, stylesheet and four vanilla JS modules.
- Nav consistency and e2e: tests/test_navbar_consistency.py + tests/e2e/test_personal_pages.py => 7 passed in 11.63s.
- Playwright acceptance against the real dashboard on isolated state (seeded through the public API/repositories, not through HTML): 0 failures across 1440, 834, 390 and 320 px; zero horizontal overflow; no console errors; capture form, completion dialog with evidence, verification and proposal confirmation each persisted and were asserted back through /api/v1/commitments.
- Screenshots: .pipeline/personal-operations/2026-10/evidence/{today,shared}-{1440,834,390,320}.png and today-zoom200.png.
- Manual inspection found and fixed: unescaped quote parse errors in two modules; section headings spread apart by space-between; shared page showing assistant fallback labels because the SPA roster is a global lexical binding, not window.botsCache.

### M4: Today semantics corrections (after M3)

- A run waiting for approval is not listed as working; it belongs to the approvals section.
- One schedule listed once even when the legacy primary field and the schedules list both contain it.
- Tests: tests/test_personal_api.py => 8 passed.

## Automation and restart acceptance

- Attached a real interval schedule through Store.upsert_bot(primary_schedule_update=...) while the dashboard was stopped.
- Restarted the dashboard with the same isolated state. After restart: 11 commitments (8 open, 3 done), 2 spaces with 3 and 1 active members, the assistant grant on the household space, the pending approval and the schedule were all still present.
- API /api/v1/today returns upcoming_schedules for the local day and the schedule page lists it; the scheduled occurrence is claimed by the engine after its fire time (see next run entry for the post-fire state).

## Fixes made during acceptance

| Symptom | Root cause | Fix |
|---|---|---|
| Today/Shared rendered "Could not load this view" | two JS modules had unescaped double quotes inside double-quoted strings, so they failed to parse | rewrote the three strings with single-quoted prefixes or escaped class attributes; node --check all four modules |
| Section intros floated to the far right | section head used justify-content: space-between | block layout that keeps the heading and intro together |
| Shared showed "Assistant" instead of assistant names | shared.js read window.botsCache, but app.js declares botsCache as a lexical binding | read the binding by name and fetch the roster when it is not loaded yet |
| Test expected a fixed UTC instant for a Vancouver day | the installed tz database's 2026 rules differ from the assumption | test now locates the transition from the installed zone data and asserts the 23/24/25-hour invariant |

## Scheduled occurrence evidence (post-fire)

The schedule next fired at 2026-10-31T05:53:55Z, the exact instant computed before the restart. The
engine claimed it (GET /api/v1/bots/household-helper/schedules/<id>/occurrences): occurrence
2026-10-31T05:53:55.158540+00:00, run_id run_cce29a17437a, claimed_at 05:53:55.163897Z, run_status
failed, run_origin schedule, exit_reason model_unavailable, missed_windows 0. That is the honest
outcome: the durable schedule fired correctly and the run failed because the acceptance assistant
has no configured model route. After the fire the next occurrence moved to the following day.

## Full non-e2e regression (2026-10-31)

Command pattern (all 286 non-e2e test files split into six disjoint batches, UV_CACHE_DIR=/tmp/uv-cache,
uv run --frozen --no-sync pytest -q --no-header --tb=line):

| Batch | Result |
|---|---|
| 1 | 702 passed, 64 skipped, 1 failed |
| 2 | 808 passed, 2 skipped |
| 3 | 840 passed, 10 skipped, 3 xfailed, 3 failed |
| 4 | 680 passed, 11 skipped |
| 5 | 702 passed, 3 skipped |
| 6 (re-run after fix) | 697 passed, 9 skipped |

Totals: 4,429 passed, 99 skipped, 3 xfailed, 4 failed.

Failure attribution:

- tests/test_procguard.py::test_group_inspection_checks_the_saved_session_identity fails in this sandbox
  because a process inside the execution namespace reports pgrp/session 0; it reproduces on a clean HEAD
  worktree with only the test file checked out, so it is an environment limitation, not this slice.
- tests/test_remote_pairing.py (two tests) reproduce on clean HEAD; they try to bind a fixed port already
  occupied on this host.
- tests/test_routes.py::test_a_default_that_cannot_run_is_refused passes on clean HEAD and fails only with
  another session's uncommitted route/model-selection changes in the worktree; it is not caused by this slice.
- tests/test_bot_deletion_schema.py pinned SCHEMA_VERSION to 83, so the additive v84 migration broke it. Fixed
  to assert the bot-deletion floor (>= 83) rather than the store's latest version; the affected batch re-ran
  green (697 passed).

No other failures remain. The other session's uncommitted changes were never staged, reverted or reformatted.

## Concurrent integration log (corrected timeline)

This slice was developed in a shared checkout while two other sessions were active.

- Slice commits: 003c4365, 1c454c32, dd8d59b3, a2fb4137, adb5e296, 023bf47c, ee8ea3be, f879019b,
  02cf968b, 4f23c591, e1d4e016, b9629e7c, ed9a0901. All are ancestors of main.
- Another session committed a provider-platform series on top of this slice's work up to 02cf968b (for
  example 8e891ad1, 934e1b69, 185059fe, ffc686a9). This slice's final commit 4f23c591 sits on top of that tip.
- At the first review snapshot (HEAD ed9a0901) the committed store schema was 84, this slice's migration. The
  worktree also held another session's UNCOMMITTED src/hutch/store.py edit and UNTRACKED mcp_schema.py, so a
  plain import in that dirty tree reported 85; no committed tree contained mcp_schema then. The first
  independent verifier correctly flagged an earlier note that attributed 85 to the committed provider series.
- Minutes later that session committed fd3002a4 (governed MCP client plane). At committed HEAD now:
  mcp_schema.py is tracked and the store schema is 85. Schema v84 remains this slice's additive migration;
  v85 is the MCP migration. The 402-line untracked tests/test_mcp_plane.py seen by the first verifier was
  superseded: at fd3002a4 it is tracked at 311 lines.
- The generated agent map was stale after those commits. It is regenerated in this commit, so
  npm run check:agent is green at fd3002a4 (command and output recorded in RUNLOG below).
- A third session's uncommitted model-picker/removal work remains in the working tree (22 modified, 11
  untracked at the final check). Nothing from it was staged, reverted or reformatted here.

## Second independent verification (at HEAD fd3002a4)

The auditor teammate re-ran a read-only verification on the integrated tree after the MCP commit and reported:
- 87 passed for the seven focused files; personal-pages e2e 1 passed; tool-contract and constitution audits
  PASS; context hygiene PASS; agent map FAILED only because the other session's commit made it stale.
- personal_schema.py additive (14 CREATE IF NOT EXISTS, zero ALTER/DROP/UPDATE/DELETE); personal migration v84
  while committed HEAD schema is 85 (the later MCP migration).
- Rows 1-21 PASS / PARTIAL / BLOCKED / DEFERRED exactly as this document declares; no committed seed/demo
  fixture; no slice product regression; the slice artefact that was dirty was this RUNLOG file.
- Row 22 was held open only for three documentation/artifact staleness findings (F1-F3): the integration note
  still said schema 85 was uncommitted, the agent map was stale, and an untracked 402-line test file was
  described as untracked when it had since been committed at 311 lines. All three are corrected above and the
  map is regenerated; no product code change was needed.
- The acceptance database now shows 0 pending approvals because the seeded approval expired by its TTL; that is
  the documented fail-closed behaviour, not a contradiction of the earlier restart observation.

### Final integration checks at HEAD fd3002a4 (2026-10-30 23:52 America/Vancouver)

- npm run check:agent: context hygiene passed (890 source files, 117 frozen over-cap files), tool contracts
  passed (43 tools), constitution passed, agent map passed (118 lines; 2258 tracked files).
- Focused slice suite plus personal-pages e2e: 88 passed in 24.57 s.
- Committed HEAD schema is 85: v84 is this slice's personal migration, v85 is the later MCP migration from the
  other session's fd3002a4. personal_schema.py remains additive-only.
- The agent map was regenerated after the MCP commit and is committed with this record.

## 2026-10-31, after the handoff: G01, G05 and the first G06 slice

The handoff above was written at HEAD `fd3002a4`. Work continued past it and this
section is the correction, so the next session does not redo it.

### Shipped after that handoff (all ancestors of `main`)

| Commit | Scope |
|---|---|
| `bb992832` | Read-only agenda projection: `src/hutch/personal/agenda.py` + `agenda_sources.py`, `GET /api/v1/personal/agenda[/sources]`, Today agenda card with source labels, read time, stale marker and reason codes; injected readers; browser coverage at 1440/834/390/320 plus keyboard |
| `614c331f` | Outbound notifications through the existing channel outbox: SQL triggers on approval/run transitions, one lease and one state machine, `notification_id` unique in the outbox, uncertain sends never resent; `channel_deliveries` rebuilt to reference either an inbound event or a notification |
| `ac5e6f04` | Review fixes: a revoked or expired grant discards the cached agenda snapshot in the same request (only a provider failure may show stale), malformed run documents skip the alert, `not_queued` named identically on both surfaces, alerts for removed assistants are hidden, provider calendar names bounded |
| `48de6899` | Made the two review fixes reach a running system (migration repair, cache eviction path) with `tests/test_notification_schema.py` |
| `a113c709` | Credential failure decided where the credential is used, not by the wording of the error |
| `4a95f39e` | Durable docs, operations notes, roadmap and marketing claims for the agenda and the alert path |

Nothing in that pass added a second delivery path or a model call on the read side.

### G06 first slice, this session

The schedules page could say when a routine would next run, but not why the last
one did not. The overview row and the assistant's History panel now state the most
recent claimed occurrence with the run's own status and exit reason.

- `src/hutch/server/app.py`: `_occurrence_outcome` projects the last claim from
  `store.list_schedule_occurrences(..., limit=1)`; the schedule resource gains
  `last_occurrence` and a derived `needs_attention` (blocked, or last run `failed`
  or `outcome_unknown`; a cancelled run is reported but is not attention).
- `src/hutch/server/static/app.js`, `style.css`: the last-run line, an attention
  summary naming the actual causes, and the History panel showing the exit reason
  in the reader's local time.
- `tests/test_schedule_outcomes.py` (9 passed): every state through the real API,
  plus the projection's exact keys so a prompt or error body cannot leak in.
- `tests/e2e/test_schedules_attention.py` (3 passed): real server and browser at
  1440/834/390/320 with no console errors and no horizontal overflow, and the
  assistant page History panel.
- `docs/operations.md`: a `Scheduled work: what the owner is told` section.
- Evidence: `.pipeline/personal-operations/2026-10/evidence/schedules-attention-1440.png`,
  `schedules-attention-320.png` and `schedules-history-1440.png`.

Deliberately not done here: no new table, no migration, and no change to
`src/hutch/store.py`. Another session held uncommitted work in `store.py`,
`connections.py`, `skills.py`, `providers/`, `vault/` and the computer modules at
the time of writing; `npm run check:agent` is red in the shared worktree for those
files only. G02, G03 and G04 each need a migration registration line in `store.py`,
so they were not attempted in this window.

### Gate at this commit

- `npm run check:agent` in an isolated worktree at this commit: green (the shared
  worktree is red only for another session's in-flight files).
- Focused: `tests/test_schedule_outcomes.py tests/test_scheduler.py tests/test_schedule_durability.py tests/test_api.py tests/test_navbar_consistency.py` -> 91 passed.
- Browser: `tests/e2e/test_schedules_attention.py` -> 3 passed.

### Integration hazard observed

`src/hutch/server/app.py` was sitting in the shared worktree with this slice's
schedule-resource hunk when another session committed `ced92681` ("Reach the vault
from the dashboard's own HTTP surface"). That commit therefore carries the
`last_occurrence` / `needs_attention` projection under its own message, while this
commit carries the tests, UI, docs and records. The tree at the resulting HEAD is
correct and `git log -S last_occurrence -- src/hutch/server/app.py` names
`ced92681`. The other session's history was not rewritten. Expect the split
attribution, and prefer an isolated worktree for any further `store.py` work while
that session is active.
