# DECISION.md - Run 1 decision log, capability probe, gates

PROJECT: Hutch · RUN: 1 (evidence base) · Date: 2026-10-28 · Owner: brand identity lead (DSH session "lead")

## Capability probe (session start, 2026-10-28 ~21:46 PT)

| Capability | Result | Evidence |
|---|---|---|
| Read/write files, shell, git | YES (workspace-write; approval: ask) | probes ran: git status, git log, git show, ls/find |
| Build/tests and serve | Commands present, NOT run this session | npm run check:agent, uv run --frozen --no-sync pytest, npm run build:css --silent (package.json, node v22.23.2, uv 0.13.6) |
| Screenshots at viewports/themes/DPR | **NO — unproven** | no playwright bin, no python playwright, no system chrome; tests/e2e exists but needs Playwright Chromium (dependency change = authority required) |
| Image inspection (open and see) | YES | read_image available for PNG/JPEG/WebP evidence |
| Web search + fetch | YES (fetch verified in-session by worker A) | sources that 403/404 are recorded per-source in RESEARCH.md |
| Worktree/branch | YES; main tree shared | .worktrees/brand-phase1 + .worktrees/brand-plan exist (AGENTS.md forbids reading them); main tree has uncommitted changes from other sessions - never staged or reverted by this session |
| Approver | **Human (maintainer)** | direction, legal escalation, merge/deploy all human; this session: local commits only |

Fallback for missing screenshot capability: Run 1 needs none (read-only evidence). Run 4's visual
gate must either install the Playwright Chromium revision (uv sync --extra browser - needs approval)
or run in the existing e2e harness; until then, no run claims visual validation.

## Session input block (resolved - adapter absent)

- The master prompt's session input block was unfilled and no adapter file exists in the repo.
  Resolved defaults recorded in 00-BRIEF.md. Human answered "go" to the proposed values
  (ARTIFACT_DIR=.pipeline/brand/2026-10, RUN=1, local commits only, <=15 files/pass).
- UNCONFIRMED (assumed, not guessed silently): JURISDICTIONS=US/EU; LICENCE_POSTURE budget;
  templates/ directory referenced by the master prompt does not exist - artifact format mirrors
  .pipeline/marketing/2026-10/ instead.

## Decisions (one line each, with reason)

- D01 - Run 1 = evidence base. Reason: .pipeline/brand/ did not exist at session start; run machine routes that state to Run 1.
- D02 - Prior brand program discovered mid-session: docs/brand/00-PLAN.md (1070-line Phase 0 plan, commits 62731262/45849dea on brand/plan, PR #11) and Phase 1 research started on brand/phase-1 (81454e2d, WIP 21:30 PT today). Read via git show (committed artifacts, not .worktrees/).
- D03 - Human chose strategy "Review/integration layer": this Run 1 verifies and gap-fills the existing program instead of duplicating it. Human also reported the brand/phase-1 session as stale/abandoned.
- D04 - Write scope held to .pipeline/brand/** for the whole session despite D03's "docs/brand free" answer: the artifact contract assigns this pipeline its own directory; no path can collide with any other session. docs/brand/** left to a future run.
- D05 - Delegated three bounded packets (RESEARCH / APP-BRAND-AUDIT / ASSET-INVENTORY), disjoint single-file write scopes, read-only elsewhere, no legal conclusions, no strategy. Reason: master prompt delegates bounded artifacts; lead owns integration and review.
- D06 - Research = verification of Phase 0's own citations re-fetched today + bounded gap research (U17, U23), not a third independent literature review. Reason: avoids divergent duplicate evidence sets (human-selected strategy).
- D07 - No commits until lead has reviewed all three worker outputs against their own evidence. Reason: never commit unreviewed work; stage only files the lead reviewed.
- D08 - Commit message prefix docs(brand): per plan Appendix B conventions and AGENTS.md (maintainer-authored, no AI trailers, no emoji).

## Gates

- GATE 1 (this run): research cited+dated; app/brand audit complete; asset inventory + findings
  signed off by the human. Status: IN PROGRESS at time of writing; see FINDINGS.md.
- GATE 2 (Run 2): human selects direction + IP pre-screen + budget/risk accepted. Not started.
- The plan's own hard gates (its G1: no design spend before clearance protocol sign-off [COUNSEL])
  apply unchanged to any later run.

## Blockers / open items carried into HANDOFF

- B1 - Screenshot/visual capability unproven (see probe); blocks any Run 4 visual gate claim.
- B2 - Phase 0 plan is "complete pending maintainer review" (PR #11) - human review still owed.
- B3 - Stale brand/phase-1 session: its uncommitted captures (if any) live in a worktree this
  pipeline must not read; evidence described in docs/brand/evidence/research/README.md is NOT
  committed, so it is unavailable to this pipeline.
- B4 - Human decisions deferred to Run 2+ (from plan D unknowns): name/keep vs rename, territories,
  budget, counsel, PWA/mobile scope, tagline. Not resolvable here.
