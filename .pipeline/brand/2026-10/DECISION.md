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

## Run 3 (2026-10-28 - IP pre-screen, clearance protocol, provenance)

Capability note: three bounded teammates (provenance, knockout, protocol) ran in parallel with
disjoint single-file write scopes; the lead reviewed every artifact before use. External calls: 12
(knockout only; all free, dated 2026-10-28). The first human ask (7 questions) timed out at 600 s
with no answer; a compact 2-question retry was answered, then a 3-question follow-up. Web search /
fetch work, but all five trademark register surfaces are bot-blocked or JavaScript-only; no browser
is installed (B1 is approved, not executed).

### Run 3 decisions (one line each, with reason)

- D21 - Knockout stop condition: keep D20 written risk ownership; all design/creation stays paused;
  proceed only after a manual browser class check of the observed HUTCH records (human, ask answer
  2026-10-28). Reason: HUTCH entries observed in the US and UK with Nice classes UNVERIFIED; the
  plan's program-level risk table requires a Phase 2/3 pause and no asset spend.
- D22 - Plan G1 clearance protocol SIGNED OFF (v0.1) and adopted by Option A: the maintainer
  explicitly assigned docs/brand/** write scope, so docs/brand/03-CLEARANCE-PROTOCOL.md now exists
  locally with the same text as the .pipeline draft (human, ask answer 2026-10-28).
- D23 - B6 re-confirmed: the maintainer keeps the written IP risk ownership for now, with no funded
  counsel; protocol gates 3 (counsel full search) and 4 (filing/watch) stay OPEN (recorded from the
  D21 instruction and restated per the run contract).
- D24 - B1 browser fix APPROVED: uv sync --extra browser authorised. Not executed this run; Run 4
  executes and verifies it as its first capability step.
- D25 - C27 mascot: keep it marketing-only; no expanded use until licence, copyright holder and
  usage rules are documented (human, ask answer 2026-10-28).
- D26 - U21/C15: Run 4 runs the free RDAP domain checks and the GitHub / npm / PyPI / social-handle
  checks (human, ask answer 2026-10-28).
- D27 - Secondary territory (D3 "Quiet Chrome" / D4 "Character Tiering") DEFERRED: no text-first
  concept elaboration was produced this run because the stop condition bars design talk; the Run 4
  shortlist question carries forward, not decided.

### Run 3 gates

- GATE 2: stays CLOSED (D19/D20).
- Plan hard gate G1: the protocol EXISTS, is SIGNED and is ADOPTED (D22) - but the gate 1 stop
  condition is unresolved, so asset generation remains blocked by D21. Status: protocol satisfied,
  creation still paused.
- Gate 1 of the protocol (knockout pre-screen): executed and OPEN - stop condition recorded, not
  passed. Gate 2 of the protocol: decided by the maintainer under D20 (scope fixed by D13). Gate 3:
  OPEN (no counsel). Gate 4: OPEN (no filing or watch decision).

### Run 3 blockers

- B7 (NEW, owner: human) - Knockout stop condition: HUTCH US serials 99695333 and 87196849, UK
  UK00003791602 (aggregator title LIVE/Registered) plus UK00902129492 and UK00915655715; classes,
  holders and goods/services are UNVERIFIED because every register surface is bot-blocked. Highest-
  value next step: a free manual browser lookup with a dated record. Blocks all design/creation.
- B8 (NEW, owner: human/session) - Register coverage gaps: USPTO direct, EUIPO, TMview, WIPO Global
  Brand Database and CIPO were unreachable or unattempted; Vienna design codes are unverified (no
  code may be cited until checked); domains, handles and app stores were unattempted.
- B1 - APPROVED but NOT EXECUTED (D24): uv sync --extra browser still has to run and be verified.
- B6 - re-confirmed written ownership (D23); counsel review is still owed if/when funded.
- B2, B3, B5 unchanged from Run 2.

### Run 3 artifacts

PROVENANCE-REGISTER.md (18 asset rows, licence-record gaps, carried unknowns), IP-CLEARANCE.md
(dated 12-call pre-screen log with the stop condition), CLEARANCE-PROTOCOL.md (signed v0.1, adopted
as docs/brand/03-CLEARANCE-PROTOCOL.md), and this log's D21-D27. No identity asset was generated,
drawn or rendered; no identity asset was generated, drawn or rendered at that point.

### Run 3 continued (maintainer instruction, 2026-10-28)

- D28 - Knockout stop condition overridden by a dated maintainer instruction: proceed under the
  written risk ownership (D20/D23); the maintainer will check the trademark classes later. The
  protocol's stop-condition row allows resumption on a dated written human decision; this is that
  decision. Text/spec design work is unblocked; asset files and renders still need their own
  decision. The observed overlap is NOT resolved and remains blocker B7.
- D29 - Secondary territory: both D3 "Quiet Chrome" and D4 "Character Tiering" join the Run 4
  shortlist (human, ask answer 2026-10-28). Shortlist = D1 + D2 + D3 + D4; D27's deferral is
  superseded.
- Artifact added under D28/D29: CONCEPTS-D1-D2.md - text-first elaboration (geometry, lockup,
  casing, clear space, 16px and monochrome test plans described, not drawn). No identity asset was
  generated, drawn, rendered or exported.

## Run 4 (2026-10-28 - capability, free checks, D3/D4 text, confirmed UK overlap)

Capability note: the browser step was executed. `uv sync --extra browser` first failed on the read-only
uv cache (`/home/kevina/.cache/uv` is outside the workspace-write sandbox); it succeeded with
`UV_CACHE_DIR=/tmp/dsh-uv-cache` and the environment was then restored with `--extra dev --extra
browser`. Playwright Chromium 153.0.8010.12 was verified headless, both on a static page and on a
real navigation. A browser is available to later runs; it does not authorise any render by itself.
The register probe then reached UKIPO and WIPO but not USPTO (IP-CLEARANCE sections 11.3 and 11.4).

### Run 4 decisions (one line each, with reason)

- D30 - Capability step executed under a sandbox workaround: uv cache redirected to /tmp, then
  `uv sync --extra dev --extra browser` to restore the documented dev environment; Chromium
  153.0.8010.12 verified. B1 RESOLVED. Reason: D24 approved the install; the failure was environmental
  (read-only cache), not a dependency gap; no repo file was changed by the sync.
- D31 - U21 free checks executed per D26: 4 RDAP domains, GitHub user/org/repo and name search, npm,
  PyPI, and five social surfaces; 23 unauthenticated GETs, all dated 2026-10-28 23:50 PT, no
  timeouts/403/CAPTCHA except the X login wall (recorded indeterminate). Reason: D26 asked for these
  checks; they close the domain/GitHub/package/handle rows of B8. Occupancy facts, not clearance.
- D32 - Run 4 scope held: no asset, render, master file, favicon, manifest icon, product or source
  change. All deliverables are text and evidence. Reason: run contract; the observed HUTCH overlap was
  unresolved at the start of the run and is now confirmed (D36).
- D33 - D3 "Quiet Chrome" and D4 "Character Tiering" elaborated in CONCEPTS-D3-D4.md, with a
  qualitative D1-D4 selection aid (no scores, no ranking asserted). Reason: D29 shortlist; the human
  needs an evidence-bound comparison for the Run 5 selection.
- D34 - D1/D2 refinements applied in CONCEPTS-D1-D2.md section 6: wordmark weight 650 (the 620 renderer
  and 800 CSS recorded as drift), small master below 20px, lockup number table, exact title strings,
  three-alias collapse rule, and D2 composition canvas with coordinates. Reason: remove open values so
  a later asset run does not re-decide design questions.
- D35 - Register probe executed with the browser (REGISTER-PROBE-RAW.md): UKIPO reached for all three
  numbers; USPTO unreachable by three routes (TSDR shell, API 401 key notice, tmsearch query artifact);
  EUIPO eSearch and TMview not attempted (time). Reason: the class check owed under D28/B7 - the UK
  part is now answered.
- D36 - ESCALATION: the UKIPO records confirm two live HUTCH registrations covering Nice classes 9
  AND 42 (UK00003791602, classes 9/35/39/42; UK00902129492, classes 9/35/36/37/38/39/40/41/42). On
  pre-screen evidence this is a CONFIRMED core-class overlap in a core territory. All design and
  creation stay paused; no asset work of any kind until a new dated human decision; blocker B10.
  Reason: protocol section 5 stop condition (HIT in a core class/territory) and the run's stop rules.
  This is not a finding of infringement, validity or scope.
- D37 - WIPO Vienna edition and codes recorded: "Tenth Edition", in force 2026-01-01 to 2028-12-31;
  26.5 OTHER POLYGONS (26.5.1, 26.5.9, auxiliary 26.5.24) and 26.1 CIRCLES, ELLIPSES (26.1.1,
  auxiliary 26.1.3), verbatim. No code is asserted to apply to the device and no figurative search was
  run. Reason: closes the "do not cite a code before the edition and definitions are recorded" gap;
  the coding decision stays owed.

### Run 4 gates

- GATE 2: stays CLOSED as recorded in D19/D20, but the protocol gate 2 class/territory/goods decision
  is now informed by confirmed UK evidence and should be re-taken by the human before any Run 5 asset
  work. The earlier decision was made while the classes were UNVERIFIED.
- Plan hard gate G1: the protocol exists, is signed and adopted (D22); creation stays paused and the
  pause is now evidence-backed (D36), not precautionary.
- Protocol gate 1: executed; the stop condition is now CONFIRMED for the UK (was "observed, classes
  unverified"). It is not passed.
- Protocol gate 3: OPEN (no funded counsel). Gate 4: OPEN (no filing or watch decision).
- Run 4 no-asset rule: held - no asset file and no render was produced.

### Run 4 blockers

- B10 (NEW, owner: human) - CONFIRMED UK core-class overlap. Two live HUTCH registrations cover class 9
  and class 42: UK00003791602 (Hutch Logistics Ltd, filed 2022-05-24, registered 2023-02-10; class 9
  logistics/supply-chain software) and UK00902129492 (Hutchison Whampoa Enterprises (Bahamas) Ltd,
  filed 2001-03-12, registered 2003-08-29; broad data/software class 9). Action: a new dated human
  decision before ANY asset work - (a) retain the name with the written risk ownership re-confirmed
  after this evidence (D20/D23/D28 were given while classes were unverified), (b) change the name, or
  (c) narrow the offering/goods; counsel only if funded. Not a legal conclusion; no clearance.
  Highest-priority blocker.
- B7 (UPDATED) - US serials 99695333 and 87196849 remain unretrieved from an official source: TSDR
  renders a search shell, the API now requires an account/API key, and tmsearch query forms return a
  "No results found" artifact. The UK side of B7 is answered (B10). The US class question stays open.
- B9 (NEW, owner: human) - Bare-name domain and handle occupancy: hutch.com/.app/.ai/.dev all
  registered; npm "hutch" registered (unrelated 2013 package); YouTube @hutch and LinkedIn
  /company/hutch exist; X @hutch indeterminate behind a login wall; PyPI "hutch" and Bluesky
  hutch.bsky.social unregistered on 2026-10-28. Action: marketing handle/domain strategy decision;
  risk rated only.
- B8 (UPDATED) - Coverage: closed for RDAP, GitHub, packages, social handles, Vienna edition/codes and
  UKIPO. Still owed: EUIPO eSearch, TMview, CIPO, app stores, exact combined-form phrases, and the US
  serials (B7).
- B1 - RESOLVED (D30): browser installed and verified.
- B6 - unchanged: counsel review owed if/when funded; gates 3-4 OPEN. Note: the written risk ownership
  needs an explicit re-confirmation after B10 (the earlier acceptance was made while classes were
  unverified).
- B2 (plan PR #11 review + 8 corrections), B3 (stale phase-1 worktree), B5 (open citations) unchanged.

### Run 4 artifacts

- CONCEPTS-D3-D4.md (NEW): text-only elaboration of D3 and D4, the D1-D4 selection aid, no asset.
- CONCEPTS-D1-D2.md (UPDATED): section 6 refinements (weight, small-size rule, lockups, titles, aliases,
  D2 canvas/coordinates) and the B10 note.
- IP-CLEARANCE.md (UPDATED): section 0 addendum (UK classes confirmed, RACE KINGS correction), section
  3 addendum (Vienna edition/codes verbatim), section 5 note, section 8 note, and new sections
  11.1-11.6 (capability, U21 checks, register probe, Vienna, coverage, still owed).
- U21-FREE-CHECKS-RAW.md (NEW): raw dated free-check log (23 requests).
- REGISTER-PROBE-RAW.md (NEW): raw dated browser probe (Vienna verbatim, UKIPO records, USPTO failures).
- No identity asset was generated, drawn, rendered or exported in Run 4. No file outside
  .pipeline/brand/2026-10/ was written.
