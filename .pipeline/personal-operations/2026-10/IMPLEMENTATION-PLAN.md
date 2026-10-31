# Implementation plan and ledger

Date: 2026-10-31. Owner: Lead (single writer). Integration point: local main; no push authorized.

| Slice | Output | Exit check | Status |
|---|---|---|---|
| S1 | research + audit inputs | dated research and current-state docs exist with file:line evidence | done: RESEARCH/COMPETITIVE/FAILURE (58 sources) and CURRENT-STATE/GAP-REGISTER/EDGE-CASES |
| S2 | commitments schema + store + models | focused pytest on test_commitments.py green on a real temp SQLite store | done: schema v84; 11 store/space tests |
| S3 | personal API (commitments, spaces, grants, today) | test_personal_api.py and test_spaces.py green; invalid timezone fails closed | done: API + isolation tests; data-driven DST day test |
| S4 | assistant tools | test_commitment_tools.py green; proposed/unverified semantics enforced | done: 10 tool tests; contract audit 43 tools |
| S5 | Today + Shared UI and nav wiring | real app served; Playwright at 1440/834/390/320 plus keyboard and 200 percent zoom; no console errors | done: 0 failed browser checks; evidence screenshots; e2e test |
| S6 | docs, marketing, evidence | architecture/ops docs updated; website claims match implemented behavior; visual evidence stored | done: commitments guide, ADR-0025, architecture/operations, marketing claims, homepage section, site screenshots |
| S7 | regression + independent review | non-e2e suite result recorded with known baseline failures listed; independent verifier PASS per row | in progress: suite running; verifier next |

## Sequencing and write ownership

1. S2-S4 are backend-only; one writer.
2. S5 touches only shell/nav/palette/new static files plus route registration, after S3 routes exist.
3. S6 runs after S5 evidence exists.
4. S7 runs after all changes are committed; verifier is read-only.

## Known constraints discovered in Phase 0

- .file-size-baseline.json freezes store.py, models.py, app.py and app.js; new code goes in new files
  under the 400-line cap, with only a one-line migration import and list entry in store.py (net zero lines).
- The working tree has another session's uncommitted files (frontend/model-picker work). They are never
  staged, reverted or reformatted; commits use explicit path lists, and app.js/index.html were committed
  through index blobs built from HEAD plus this slice's lines.
- uv needs a writable cache: UV_CACHE_DIR=/tmp/uv-cache for all commands. /tmp is per-execution in this
  sandbox, so isolated acceptance state lives under the git-ignored .dsh/ui-validation/.
- The baseline focused suite is green: 68 passed (test_migration.py, test_scheduler.py,
  test_schedule_durability.py).
