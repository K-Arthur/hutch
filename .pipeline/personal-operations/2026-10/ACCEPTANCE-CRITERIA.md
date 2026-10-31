# Acceptance criteria and evidence status

Status legend: PASS (observed on the real app or real store); PARTIAL (implemented and unit/API-tested, but the live dependency is unavailable); BLOCKED (cannot be exercised in this environment, with the precise reason); DEFERRED (explicitly out of this slice).

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Research with dated sources and failure analysis exists | PASS | 00-BRIEF.md, RESEARCH.md, COMPETITIVE-ANALYSIS.md, FAILURE-ANALYSIS.md (58 unique sources, evidence tags); CURRENT-STATE.md, GAP-REGISTER.md, EDGE-CASES.md |
| 2 | Existing behavior documented before changes | PASS | CURRENT-STATE.md with file:line traces; baseline focused suite 68 passed; git state recorded in RUNLOG.md |
| 3 | Architecture decisions and contracts recorded before implementation | PASS | ARCHITECTURE.md, DECISIONS.md D-01..D-10; ADR-0025 in the repository |
| 4 | Additive schema migration, no data rewrite | PASS | Schema v84; src/hutch/personal_schema.py contains only CREATE ... IF NOT EXISTS statements (verified by both independent reviewers: 14 CREATE IF NOT EXISTS, zero ALTER/DROP/UPDATE/DELETE). test_commitments.py migrates a minimal database twice and checks the new tables and append-only trigger; real upgrade coverage is the v4 fixture test in test_migration.py. Current committed HEAD reports schema 85 only because another session's later commit fd3002a4 adds the MCP migration (v85); v84 is this slice's migration (timeline in RUNLOG.md). |
| 5 | Commitments have provenance, confirmation state and revision CAS | PASS | Commit model + commitment_events (append-only triggers); tests/test_commitments.py; API conflict test returns 409 on a stale revision |
| 6 | An assistant cannot manufacture a confirmed commitment or verified completion | PASS | tools create confirmation='proposed'; completion kind 'unverified'; tests/test_commitment_tools.py; API only creates owner-confirmed rows |
| 7 | Completion requires evidence; verification is separate | PASS | Model/DB invariants; tests/test_commitments.py completion evidence test; UI completion dialog requires text and browser test asserts owner_confirmed row |
| 8 | Shared space scoping is enforced in the store/tool layer | PASS | tests/test_spaces.py (personal + granted space only, revoke effective immediately, archive revokes), E2E shared page renders real grants |
| 9 | Today aggregation is deterministic and truthful | PASS | No model call in src/hutch/personal/today.py; every section maps to persisted rows; browser interaction test verifies persisted rows after UI actions |
| 10 | IANA timezone fail-closed and DST-correct day bounds | PASS | API returns 422 for unknown/missing zone; test locates the installed tz transition and asserts a 23/24/25-hour day and correct due-today classification |
| 11 | Dashboard responsive at 1440/834/390/320, keyboard and 200 percent zoom | PASS | Playwright run 0 failures (overflow, section counts, console errors); screenshots in evidence/; E2E test asserts overflow <= 1px and keyboard focus/aria-current |
| 12 | Capture/complete/confirm actions write real state | PASS | Browser test asserts /api/v1/commitments and store rows after each UI action |
| 13 | Restart continuity for commitments, spaces and schedules | PASS | Automated: test_commitments_spaces_and_a_schedule_survive_a_store_restart reopens the same state directory and asserts the commitment, membership, assistant grant and computed next fire are unchanged. Also exercised on the real dashboard: restart preserved 11 commitments, 2 spaces, 3 and 1 active members, the grant, the pending approval and the schedule. |
| 14 | A recurring automation fires durably and records its occurrence | PARTIAL | Schedule attached through Store and served by the real scheduler after restart; occurrence claim is exercised by tests/test_scheduler.py and tests/test_schedule_durability.py. Live demonstration of a *successful* scheduled run is blocked by no configured model route for the acceptance assistants. |
| 15 | Assistants can capture a commitment from a conversation | PARTIAL | Tool contract, proposal semantics, dedupe and space scoping are unit-tested and the tool is registered; an end-to-end model-driven run requires a configured provider/model, which this environment does not have. The tool refusal paths are tested; do not present model capture as live-verified. |
| 16 | Personal daily briefing includes calendar and email | BLOCKED | No Google/Outlook account is connected in the acceptance environment; Today states explicitly that calendar/mail are not read automatically and links to the tools/schedules instead of inventing data |
| 17 | Family/household multi-participant identity and authentication | DEFERRED | Spaces record members and roles and scope assistant access, but the server remains single-owner with no per-participant login. GAP-REGISTER G07 recommends an ADR before family-facing authentication promises. |
| 18 | Coding orchestration lifecycle changes | DEFERRED | Existing code_handoff, coordinator tasks and worktree isolation were inspected (CURRENT-STATE.md) but no runtime/provider is configured to execute a live coding task in this environment; no claims are made |
| 19 | Multimodal deliverable production changes | DEFERRED | Existing documents/workflow pipeline inspected; not modified in this slice; Today only lists real document rows when they exist |
| 20 | Duplicate external action / reconciliation acceptance | PARTIAL | Existing channels/action-receipt machinery was inspected (CURRENT-STATE.md); no connected external destination in this environment to run the ambiguous-delivery scenario. This slice adds no new external effects. |
| 21 | Full non-e2e regression suite | PASS with attributed environment/dirty-tree failures | 4,429 passed, 99 skipped, 3 xfailed, 4 failed across 6 sequential batches of all 286 non-e2e files (results and attribution in RUNLOG). Failures: 3 reproduce on clean HEAD in this sandbox (procguard process-group inspection under the sandbox pid namespace; two remote-pairing tests that try to bind an occupied port), and 1 (test_routes) is caused by another session's uncommitted model-route changes and passes on clean HEAD. One real regression from this slice (a stale schema-version pin in test_bot_deletion_schema.py) was found and fixed, then its batch re-ran green. |
| 22 | Independent review | PASS | Two read-only verifications in separate contexts. First: focused suite 86 passed in 41.96 s, personal-pages e2e 1 passed in 13.53 s, tool-contract/constitution/agent-map audits, additive-migration and no-demo-data checks; it raised two documentation errors and one overstated evidence row, all corrected. Second (auditor, at HEAD fd3002a4 after the other session's MCP commit): 87 focused passed, e2e 1 passed, tool-contract/constitution/context-hygiene audits PASS, rows 1-21 PASS/PARTIAL/BLOCKED/DEFERRED as declared, no slice regression or missing deliverable; row 22 was held open only for three documentation/artifact staleness findings (F1-F3), all corrected here, and the regenerated agent map makes npm run check:agent green at fd3002a4. |

## Explicit non-claims

- No claim of multi-user isolation between human accounts; spaces scope data for assistants and record people, not authenticated users.
- No claim that an assistant-reported completion is verified; the UI and API keep them distinct.
- No claim of exactly-once external effects in this slice; no external side effects were added.

## Independent verification (2026-10-31, separate read-only agent)

The reviewer re-ran the checks itself on the integrated tree: focused 7-file suite 86 passed in 41.96 s; personal-pages
e2e 1 passed in 13.53 s; scheduler duration tests 27 passed; tool-contract audit PASS (43 tools); constitution
audit PASS; agent-map check PASS (118 lines); personal_schema.py additive only (14 CREATE IF NOT EXISTS, zero
ALTER/DROP/UPDATE/DELETE); no committed seed/demo data; docs/commitments.md and docs/marketing-site.md new claims
accurate. Rows 1-21 pass (rows 13/14/15/16/20 with the stated manual/environment limits); row 22 was open pending
this record.

Findings raised and their resolution:

- D1 (corrected): SCHEMA_VERSION imports as 85 in the working tree, but HEAD is 84. The 85 comes only from
  another session's uncommitted store.py edit plus their untracked mcp_schema.py; no committed tree contains
  mcp_schema. The earlier integration note wrongly attributed it to the committed provider series; RUNLOG.md and
  HANDOFF.md now state the verified cause. This slice's migration is v84.
- D2 (corrected): the 402-line tests/test_mcp_plane.py is another session's untracked file (commit 934e1b69 added
  tests/test_integration_dispatch.py). The context-hygiene red is that untracked file; the largest slice source
  file is 326 lines. The integration note now says exactly this.
- D3 (recorded): another session staged src/hutch/server/app.py (+2 lines) and added untracked test files during
  review; no slice file was staged or modified and the reviewer made no writes. Working tree moved from 33 to 35
  entries and HEAD advanced from 4f23c591 to 1e81df56 through other-session docs commits; code under test did not
  change.
- D4 (corrected): row 4 no longer claims the migration test builds a v83-shaped database; it states the minimal
  table fixture and points to the v4-fixture upgrade test as real upgrade coverage.
- D5 (improved): restart continuity now has an automated store-reopen test (commitments/spaces/grant/schedule next
  fire), not only the dashboard narrative. A successful scheduled model run remains blocked by no configured model
  route; this is stated, not claimed.

No finding required a code change to the product; the only code change after review was the added automated
restart-continuity test. No committed deliverable was missing.
