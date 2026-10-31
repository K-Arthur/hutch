# Handoff: personal operations slice (2026-10-31)

Read this with CURRENT-STATE.md, GAP-REGISTER.md, ARCHITECTURE.md, DECISIONS.md,
RUNLOG.md and ACCEPTANCE-CRITERIA.md. This is the durable memory for the next session.

## What shipped (local main, no push)

| Commit | Scope |
|---|---|
| 003c4365 | schema v84, personal package (commitments/spaces/Today), personal API, store integration, tests, architecture/decisions/plan |
| 1c454c32 | assistant tools capture_commitment, list_commitments, report_commitment_done + contract tests |
| dd8d59b3 | Today and Shared dashboard surfaces, nav/palette/shell wiring, personal CSS, browser test, screenshots |
| a2fb4137 | agent-map footer compacted so the generated map stays within its 120-line cap |
| adb5e296 | docs: commitments guide, ADR-0025, architecture/operations, marketing claims and site section, full pipeline doc set |
| 023bf47c | Today run-state and duplicate-schedule corrections + tests |

## Status by capability

- Personal commitments (durable, provenance, confirmation, evidence, dependencies, audit): implemented and
  tested at store/API/tool/UI level. See tests/test_commitments.py, tests/test_spaces.py,
  tests/test_personal_api.py, tests/test_commitment_tools.py, tests/e2e/test_personal_pages.py.
- Today briefing: implemented as a deterministic projection (src/hutch/personal/today.py) with
  GET /api/v1/today and the browser surface. IANA fail-closed, DST day bound tests, responsive
  screenshots at .pipeline/personal-operations/2026-10/evidence/.
- Shared spaces (household/project) with members/roles and per-assistant grants: implemented; isolation
  proven in tests. NOT multi-user authentication; see the single-owner limit below.
- Assistant capture: tools registered and owner-granted per assistant; proposal/verification boundary is
  enforced in code. A live model-driven capture run was not possible (no configured model route).
- Persistent automations: existing scheduler unchanged. Acceptance demonstrated a real interval schedule
  attached while stopped, surviving a dashboard restart, firing once at the right instant, claiming its
  occurrence and admitting a run that failed honestly with model_unavailable (no route configured).
- Coding orchestration, multimodal deliverables, duplicate-external-action reconciliation: inspected and
  documented in CURRENT-STATE.md; not changed in this slice and not live-verified here.

## Limits and non-claims (do not weaken these in copy or code)

- The server is single-owner. Spaces record people and scope assistant data; they are not logins and there
  is no cross-human isolation. Do not market family accounts until GAP-REGISTER G07 is designed and built.
- Assistant tools can only propose a commitment and report a completion. Only owner routes confirm and
  verify. The types and API enforce this; do not add a model-settable confirmed flag.
- Today never calls a model and always lists what it excludes. Do not add generated prose to it without a
  labelled, source-showing design.
- Calendar and mail are NOT read for Today. Adding that requires a new read path with grants, caching,
  staleness disclosure and prompt-injection handling (G01/G09).
- No exactly-once claim for external effects. This slice adds no external effects.

## Environment and reproduction

- Isolated acceptance state lived in .dsh/ui-validation/state (git-ignored) with the dashboard on
  127.0.0.1:8899. The seed data was created through the public repositories/API in that throwaway state; it
  is not committed and must not become product demo content.
- Tests: UV_CACHE_DIR=/tmp/uv-cache uv run --frozen --no-sync pytest -q tests/test_commitments.py
  tests/test_spaces.py tests/test_personal_api.py tests/test_commitment_tools.py tests/test_migration.py
  tests/test_navbar_consistency.py ; e2e: tests/e2e/test_personal_pages.py.
- Audits: npm run check:agent (context hygiene, tool contracts, constitution, agent map).
- Visual evidence: .pipeline/personal-operations/2026-10/evidence/ (app at 1440/834/390/320 plus 200 percent
  zoom and the marketing section).
- Site: python3 -m http.server --directory website ; the homepage section id is "today".

## Working-tree caution

Another session left uncommitted model-picker/assistant-removal work in cli.py, app.py, app.js, index.html,
studio.css, several tests and new static files. This slice never staged, reverted or reformatted it. The
commits above contain only this slice's hunks (app.js/index.html were committed through index blobs built
from HEAD plus this slice's lines). If that work later lands, re-read the merged files and re-run the nav and
browser tests; a conflict is possible in app.js and index.html.

## Next priorities (from GAP-REGISTER)

1. G01 calendar/mail agenda projection for Today (read-only, grant-gated, staleness disclosed).
2. G02 coding handoff verification gate and worktree lifecycle (hutch code verify/prune) with receipts.
3. G03 automation revision history, approval checkpoints and bounded conditions.
4. G04 inbound webhook/event triggers admitted through the existing admission policy.
5. G05 outbound notifications for needs-you, failure and results, using the channel supervisor.
6. G07 an ADR for real multi-participant authentication before any family-account promise.

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
