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
