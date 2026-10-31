# Implementation plan and ledger

Date: 2026-10-31. Owner: Lead (single writer). Integration point: local \`main\`; no push authorized.

| Slice | Output | Exit check | Status |
|---|---|---|---|
| S1 | research + audit inputs | dated research and current-state docs exist with file:line evidence | in progress (teammates) |
| S2 | commitments schema + store + models | focused pytest: \`tests/test_commitments.py\` green on a real temp SQLite store | planned |
| S3 | personal API (commitments, spaces, grants, today) | \`tests/test_personal_api.py\`, \`tests/test_spaces.py\`, \`tests/test_today.py\` green; invalid timezone fails closed | planned |
| S4 | assistant tools | \`tests/test_commitment_tools.py\` green; proposed/unverified semantics enforced | planned |
| S5 | Today + Shared UI and nav wiring | real app served, Playwright screenshots at 1440/834/390/320, keyboard and 200% zoom, no console errors | planned |
| S6 | docs, marketing, evidence | architecture/ops docs updated; website claims match implemented behavior; visual evidence stored | planned |
| S7 | regression + independent review | non-e2e suite green (known baseline failures listed); independent verifier PASS per row | planned |

## Sequencing and write ownership

1. S2-S4 are backend-only; one writer.
2. S5 touches only shell/nav/palette/new static files plus route registration, after S3 routes exist.
3. S6 runs after S5 evidence exists.
4. S7 runs after all changes are committed; verifier is read-only.

## Known constraints discovered in Phase 0

* \`.file-size-baseline.json\` freezes \`store.py\`, \`models.py\`, \`app.py\`, \`app.js\`; new code goes in new files
  under the 400-line cap, with only a one-line migration import and list entry in \`store.py\`.
* The working tree has another agent's uncommitted files (frontend/model-picker work). They are never staged,
  reverted or reformatted; commits use explicit path lists.
* \`uv\` needs a writable cache: \`UV_CACHE_DIR=/tmp/uv-cache\` for all commands.
* The baseline focused suite is green: 68 passed (\`test_migration.py\`, \`test_scheduler.py\`,
  \`test_schedule_durability.py\`).
