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

## Concurrent integration (2026-10-31, after the first regression pass)

Another active session committed a provider-platform series to local main in the shared checkout while this
slice was being validated (for example 8e891ad1, 934e1b69, 185059fe, ffc686a9). The slice commits are all
present on main. Ordering after integration: this slice's commits up to 02cf968b are ancestors of that
session's tip ffc686a9, and the final slice commit 4f23c591 sits on top of it. The provider series edited
website/index.html and store.py (adding mcp_schema.migrate after personal_schema.migrate), so:

- the current store schema is 85: v84 is the personal-operations migration, v85 is the MCP integration
  migration added by the other session; docs/architecture.md and ADR-0025 correctly describe v84 as the
  migration that added commitments and spaces;
- all slice features and documentation are still present at HEAD (nav Today row, Today/Shared modules, the
  homepage section, the marketing claims paragraph, the personal_schema registration) and the focused tests,
  tool-contract audit, constitution audit and agent-map check were re-run green by the independent verifier;
- npm run check:agent as a whole currently reports one new-source-file cap violation in
  tests/test_mcp_plane.py (402 lines), which was added by the other session's commit 934e1b69 and is not part
  of this slice; it was not modified here to avoid editing another active session's committed work.

A third session's uncommitted model-picker/removal work remains in the working tree (20 modified, 13
untracked paths at the final check); it was never staged, reverted or reformatted.
