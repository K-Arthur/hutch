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

> **Correction, 2026-10-31 after this handoff.** G01 and G05 below have since shipped and are
> ancestors of `main`: the read-only agenda (`bb992832`, with review fixes `ac5e6f04`, `48de6899`,
> `a113c709` and docs `4a95f39e`) and owner notifications through the existing channel outbox
> (`614c331f`). The first G06 slice (why the last scheduled run did not succeed) shipped in the same
> pass. See the later section in RUNLOG.md. Do not treat "agenda" or "notifications" as open work.

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

## Next priorities (from GAP-REGISTER, revised 2026-10-31)

Done since this handoff: G01 (agenda), G05 (notifications), and the first G06 slice (last-run outcome
and attention on Scheduled work). Still open, in order:

1. G02 coding handoff verification gate and worktree lifecycle (`hutch code verify|prune`) with
   content-free receipts. Needs one registration line in `src/hutch/store.py` for a new migration
   module; coordinate before editing that file.
2. G03 automation revision journal (sub-slice 1 only), then the approval checkpoint, then bounded
   conditions. Also needs a `store.py` registration line.
3. G04 inbound webhook/event triggers admitted through the existing admission policy. Also needs a
   `store.py` registration line.
4. G06 remainder: a "needs attention" filter on `#/schedules` and per-routine failure history beyond
   the last 20 windows (the last-run outcome and exit reason are already shipped).
5. G08 commitment-to-calendar reminder; G09 mail/calendar item to a proposed commitment with
   server-derived provenance.
6. G07 an ADR for real multi-participant authentication before any family-account promise.

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
