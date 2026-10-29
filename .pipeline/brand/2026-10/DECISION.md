# DECISION.md - decision log, capability probe, gates (Runs 1-2)

PROJECT: Hutch · RUN: 1 (evidence base) + RUN: 2 (strategy + concept log) · Date: 2026-10-28 · Owner: brand identity lead (DSH session "lead")

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

- GATE 1 (Run 1 exit): research cited+dated; app/brand audit complete; asset inventory + findings
  signed off by the human. Status: SIGNED OFF 2026-10-28 (D09).
- GATE 2 (Run 2 exit): human selects direction + IP pre-screen + budget/risk accepted. Status: CLOSED
  2026-10-28 - direction = D1 "Centre Dot" base + D2 "Local Hub" lead territory (D19); IP pre-screen
  scoped and accepted OPEN for counsel with zero spend and written maintainer risk ownership (D20).
- The plan's own hard gate G1 (no mark/name/tagline generation before docs/brand/03-CLEARANCE-
  PROTOCOL.md exists and is signed off) applies unchanged: G1 is OPEN - see B6 and the Run 3 order.

## Blockers / open items carried into HANDOFF

- B1 - Screenshot/visual capability unproven (see probe); blocks any Run 4 visual gate claim.
- B2 - Phase 0 plan is "complete pending maintainer review" (PR #11) - human review still owed.
- B3 - Stale brand/phase-1 session: its uncommitted captures (if any) live in a worktree this
  pipeline must not read; evidence described in docs/brand/evidence/research/README.md is NOT
  committed, so it is unavailable to this pipeline.
- B4 - RESOLVED 2026-10-28 (Run 2): every item answered and recorded below - name keep (D10),
  tagline retain (D11), ramp = website/tokens.json (D12), territories/classes US+EU+UK+CA / 9+42
  (D13), counsel posture (D14, qualified by D20), budget zero external spend (D15), PWA manifest +
  icons in scope (D16), C23 proxies accepted (D17), Gate 1 sign-off (D09).

## Run 2 additions (2026-10-28 - strategy + concept log)

Capability note (Run 2, re-probed in session): file read/write, shell, git, grep/glob, and asking the
human all worked (one ask call timed out at 120 s and succeeded on retry). No browser: B1 was never
approved and was not touched. Zero external fetches were used; files read stayed inside the
15-per-pass budget; plan text was read via `git show brand/plan:docs/brand/00-PLAN.md` only.
STRATEGY.md and CONCEPT-LOG.md were therefore produced text-first, exactly as the run contract
allows.

### Run 2 decisions (one line each, with reason)

- D09 - Gate 1 SIGNED OFF by the human (ask answer, 2026-10-28): Run 1 evidence base approved, so strategy work was allowed to start (precondition 1).
- D10 - Keep the name "Hutch" (human). Reason: plan R.6.8 rates rename highest risk and least need; X case (R.2); the knockout search still runs on the kept name (plan U09).
- D11 - Retain the tagline "Your bots. Your machine. Your rules." verbatim (human). Reason: continuity/SEO cost with no measured equity failure; no new tagline coined this run.
- D12 - Governing neutral ramp = website/tokens.json #09090b family (human). Reason: shipped token source that generates both stylesheets; closes the FINDINGS 3 conflict as surfaced-and-decided.
- D13 - Knockout scope territories/classes: United States, EU, UK, Canada; Nice 9 and 42 only; 35/41 excluded unless actually offered (human). Reason: plan R.3 core-class minimum; scope for counsel, not a clearance claim.
- D14 - Counsel: first answer was "engage counsel" (human). Reason: recorded for traceability; later qualified by D20, which is the operative posture.
- D15 - Budget: zero external spend authorised for now (human). Reason: official register searches are free; any paid counsel or filing scope returns as a new decision.
- D16 - PWA: manifest + icons IN scope (human). Reason: installability accepted as a product-behaviour change; plan R.4 PWA rows join the asset matrix (C06/C25) and the change must be disclosed on the marketing site.
- D17 - C23 measurement proxies ACCEPTED (human): pre-registered first-click/first-run tasks plus staged flags as do-no-harm gates; the 5-second test stays a diagnostic (U23); no A/B without telemetry.
- D18 - Run 2 scope held to STRATEGY.md + CONCEPT-LOG.md only: text-first, no implementation, no asset generation, no public files, no clearance claims (run contract non-negotiables; B1 unfixed).
- D19 - Gate: direction selected = D1 "Centre Dot" repair base + D2 "Local Hub" lead territory (human, ask answer). Reason: retention-first; D3 "Quiet Chrome" and D4 "Character Tiering" remain secondary shortlist territories for Run 3.
- D20 - Gate: IP pre-screen scope ACCEPTED (status OPEN for counsel, nothing searched or cleared) with zero external spend and the human explicitly owning the IP risk in writing for now, no funded counsel (human, ask answer). Reason: plan G1's alternate path; recorded verbatim as written risk ownership; supersedes D14 as the operative posture until counsel is funded.

### Run 2 blockers

- B6 (NEW, owner: human) - IP risk posture: risk is owned by the maintainer in writing with no
  funded counsel (D20), while the earlier intent to engage counsel (D14) stays unfunded (D15).
  Action at each later gate: re-confirm the written ownership or fund counsel. Plan G1 still
  requires docs/brand/03-CLEARANCE-PROTOCOL.md to exist and be signed off before ANY mark, name or
  tagline asset is generated - including a faithful master extraction from the shipped mark path.
  Run 3 must therefore produce the protocol draft (inside .pipeline scope), get the human sign-off,
  and only then elaborate concepts.
- B5 (NEW here, carried from Run 1 HANDOFF numbering; owner: session/human) - open citations:
  Anthropic press-kit URL (brand-assets.md:13), X/Facebook card dimensions (U17), and 6
  shell-rendered citations needing a rendering-browser re-check. Unchanged from Run 1.
- B1 (no browser), B2 (plan PR #11 review + 8 corrections), B3 (stale phase-1 worktree) all
  unchanged from Run 1.
