# Acceptance criteria and evidence status

Status legend: PASS (observed on the real app or real store); PARTIAL (implemented and unit/API-tested, but the live dependency is unavailable); BLOCKED (cannot be exercised in this environment, with the precise reason); DEFERRED (explicitly out of this slice).

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Research with dated sources and failure analysis exists | PASS | 00-BRIEF.md, RESEARCH.md, COMPETITIVE-ANALYSIS.md, FAILURE-ANALYSIS.md (58 unique sources, evidence tags); CURRENT-STATE.md, GAP-REGISTER.md, EDGE-CASES.md |
| 2 | Existing behavior documented before changes | PASS | CURRENT-STATE.md with file:line traces; baseline focused suite 68 passed; git state recorded in RUNLOG.md |
| 3 | Architecture decisions and contracts recorded before implementation | PASS | ARCHITECTURE.md, DECISIONS.md D-01..D-10; ADR-0025 in the repository |
| 4 | Additive schema migration, no data rewrite | PASS | Schema v84; tests/test_commitments.py migration test creates a v83-shaped database, migrates twice, checks new tables and append-only trigger; existing v4 fixture upgrade still passes |
| 5 | Commitments have provenance, confirmation state and revision CAS | PASS | Commit model + commitment_events (append-only triggers); tests/test_commitments.py; API conflict test returns 409 on a stale revision |
| 6 | An assistant cannot manufacture a confirmed commitment or verified completion | PASS | tools create confirmation='proposed'; completion kind 'unverified'; tests/test_commitment_tools.py; API only creates owner-confirmed rows |
| 7 | Completion requires evidence; verification is separate | PASS | Model/DB invariants; tests/test_commitments.py completion evidence test; UI completion dialog requires text and browser test asserts owner_confirmed row |
| 8 | Shared space scoping is enforced in the store/tool layer | PASS | tests/test_spaces.py (personal + granted space only, revoke effective immediately, archive revokes), E2E shared page renders real grants |
| 9 | Today aggregation is deterministic and truthful | PASS | No model call in src/hutch/personal/today.py; every section maps to persisted rows; browser interaction test verifies persisted rows after UI actions |
| 10 | IANA timezone fail-closed and DST-correct day bounds | PASS | API returns 422 for unknown/missing zone; test locates the installed tz transition and asserts a 23/24/25-hour day and correct due-today classification |
| 11 | Dashboard responsive at 1440/834/390/320, keyboard and 200 percent zoom | PASS | Playwright run 0 failures (overflow, section counts, console errors); screenshots in evidence/; E2E test asserts overflow <= 1px and keyboard focus/aria-current |
| 12 | Capture/complete/confirm actions write real state | PASS | Browser test asserts /api/v1/commitments and store rows after each UI action |
| 13 | Restart continuity for commitments, spaces and schedules | PASS | Dashboard restarted against the same isolated state; counts, members, grants, approval and schedule all present afterwards |
| 14 | A recurring automation fires durably and records its occurrence | PARTIAL | Schedule attached through Store and served by the real scheduler after restart; occurrence claim is exercised by tests/test_scheduler.py and tests/test_schedule_durability.py. Live demonstration of a *successful* scheduled run is blocked by no configured model route for the acceptance assistants. |
| 15 | Assistants can capture a commitment from a conversation | PARTIAL | Tool contract, proposal semantics, dedupe and space scoping are unit-tested and the tool is registered; an end-to-end model-driven run requires a configured provider/model, which this environment does not have. The tool refusal paths are tested; do not present model capture as live-verified. |
| 16 | Personal daily briefing includes calendar and email | BLOCKED | No Google/Outlook account is connected in the acceptance environment; Today states explicitly that calendar/mail are not read automatically and links to the tools/schedules instead of inventing data |
| 17 | Family/household multi-participant identity and authentication | DEFERRED | Spaces record members and roles and scope assistant access, but the server remains single-owner with no per-participant login. GAP-REGISTER G07 recommends an ADR before family-facing authentication promises. |
| 18 | Coding orchestration lifecycle changes | DEFERRED | Existing code_handoff, coordinator tasks and worktree isolation were inspected (CURRENT-STATE.md) but no runtime/provider is configured to execute a live coding task in this environment; no claims are made |
| 19 | Multimodal deliverable production changes | DEFERRED | Existing documents/workflow pipeline inspected; not modified in this slice; Today only lists real document rows when they exist |
| 20 | Duplicate external action / reconciliation acceptance | PARTIAL | Existing channels/action-receipt machinery was inspected (CURRENT-STATE.md); no connected external destination in this environment to run the ambiguous-delivery scenario. This slice adds no new external effects. |
| 21 | Full non-e2e regression suite | PASS with attributed environment/dirty-tree failures | 4,429 passed, 99 skipped, 3 xfailed, 4 failed across 6 sequential batches of all 286 non-e2e files (results and attribution in RUNLOG). Failures: 3 reproduce on clean HEAD in this sandbox (procguard process-group inspection under the sandbox pid namespace; two remote-pairing tests that try to bind an occupied port), and 1 (test_routes) is caused by another session's uncommitted model-route changes and passes on clean HEAD. One real regression from this slice (a stale schema-version pin in test_bot_deletion_schema.py) was found and fixed, then its batch re-ran green. |
| 22 | Independent review | in progress | verifier report is recorded in the final report and HANDOFF; any finding is fixed and re-run before completion |

## Explicit non-claims

- No claim of multi-user isolation between human accounts; spaces scope data for assistants and record people, not authenticated users.
- No claim that an assistant-reported completion is verified; the UI and API keep them distinct.
- No claim of exactly-once external effects in this slice; no external side effects were added.
