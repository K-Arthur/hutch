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
- D38 (HUMAN DECISION, 2026-10-29, America/Vancouver) - Name RETAINED after the confirmed UK class
  9/42 evidence. Maintainer instruction in session, verbatim: "we are retaining the name". This
  answers the B10 name question (retain option) and is a decision made under the written risk
  ownership (D20/D23/D28) with the confirmed evidence in front of the maintainer. It is not a
  clearance, not a finding that the marks are non-conflicting, and not an authorisation for any asset.
  Text and specification work may continue; asset production still needs its own explicit dated
  authorisation; gates 3-4 stay OPEN. Re-confirm the written ownership at each later gate.

### Run 4 gates

- GATE 2: stays CLOSED as recorded in D19/D20, but the protocol gate 2 class/territory/goods decision
  is now informed by confirmed UK evidence and should be re-taken by the human before any Run 5 asset
  work. The earlier decision was made while the classes were UNVERIFIED; the name decision under it
  was re-taken on 2026-10-29 as retain (D38).
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
  STATUS 2026-10-29: the name decision is ANSWERED - retain (D38). The remaining part (an explicit
  asset authorisation) is still outstanding; the class/coverage gaps stay as B7/B8.
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

### Run 5 session (2026-10-29, America/Vancouver) - instructions, authorisation, direction state

- D39 (HUMAN INSTRUCTION, 2026-10-29, verbatim): "I need you to brainstorm reseaerch adn create new
  assets especially those relating to the log which is not unique or representative of the platofrm and
  repo enough" [sic]. Read as: the human wants researched new assets; the shipped hexagon + centre-dot
  mark is judged not unique and not representative of the platform/repo. Typos preserved.
- D40 (HUMAN INSTRUCTION, 2026-10-29, verbatim): "make use of the research done for this and more if
  necessary of course" and "Use another wordmark that isnht geist and try to avoid wordmarks ai are
  biased to at all cost but dont let this have you pick bad design options qwhatever is done must be
  practical" [sic]. Read as: research-grounded process; the wordmark must not be Geist and should avoid
  faces AI tools default to; practicality outranks novelty.
- D41 (HUMAN INSTRUCTION, 2026-10-29, verbatim): "please ensure youa re fesignin themes and items that
  fit the scpe of what hutch is not just designing for the sake of it" [sic]. Read as: every artefact
  must map to a real Hutch surface or use, no decoration for its own sake.
- D42 (HUMAN DECISION, 2026-10-29, direction gate via ask_user_question): (c1) mark direction = "Iterate
  - none of these" (round-1 concepts N1-N6 not selected); (c2) wordmark family = Bricolage Grotesque
  weight 800 (selected from the wordmark sheet); (c3) asset scope = "Full package, pipeline-only" which
  IS the explicit dated authorisation for asset production naming the surfaces: master SVGs and variants
  (mono/reversed/dark/light/small), favicons 16 and 32, apple-touch 180, PWA 192/512 (any, maskable,
  monochrome), OG/social renders and lockups - all written under .pipeline/brand/2026-10/assets/.
  Adoption into website/, docs/, src/ or desktop/ is NOT authorised here and stays a later slice.
  This satisfies the Run 5 adapter gate (b); gate (c) direction selection is still open.
- D43 (HUMAN FEEDBACK, 2026-10-29, verbatim): "the issues I have with the logo concept is that all you
  have done are far too simple in the sense that these are logos that have been probably done adn
  currently possibly being used by other exisiting companies not to mention they need to meld and fit
  with the now chosen wordmark" [sic]. Recorded as the round-2 brief: constructed/composite marks,
  collision-conscious screening, visual harmony with Bricolage Grotesque 800. Round-1 outline primitives
  are rejected as too simple.
- Unchanged: B10 name-level UK class 9/42 overlap stands (D36/D38); nothing in this run is clearance; a
  visual-similarity screen for any chosen shape is owed before selection is recorded as final.
- D44 (HUMAN INSTRUCTION, 2026-10-29, verbatim): "you can build of the previous n5 teo bot front
  concept as well adn find ways to make it unique but don't hone in on that alone and add it to the
  revisions you are doing and just increase the options and further narrow down once done" [sic].
  Read as: keep the N5 lineage in the running as one option among more, widen the option set, then
  narrow on evidence; do not converge prematurely on N5.
- D45 (HUMAN CLARIFICATION, 2026-10-29, verbatim): "when I saaid n5 Iw as referring to the
  /home/kevina/CodingProjects/hutch/.pipeline/brand/2026-10/assets/concepts/sheets/contact-sheet.png"
  [sic]. Interpretation: "N5" means the round-1 contact sheet's N5 "Two-Bot Front" (arch front with two
  residents), not the later P-series. The bot-family work therefore evolves that arch/front geometry.
- D46 (HUMAN INSTRUCTION, 2026-10-29, verbatim): "also why ar you ignoring the color work which is
  just as important" [sic]. Colour work is treated as a first-class track: measured contrast tables,
  light-surface ramp, CVD simulation, print approximations, and the two-tone role logic documented in
  COLOUR-SYSTEM.md with evidence at assets/concepts/sheets/colour-sheet.png.
- D47 (HUMAN INSPIRATION BRIEF, 2026-10-29, verbatim): "for ther bot family soemthing you can take
  inspo from is the ghsots from pacmana nd logos that look like shelters/hutches etc" [sic]. Recorded
  as archetype inspiration only: no character outline, wavy skirt, eye treatment, palette or asset from
  Pac-Man/Bandai Namco or any existing logo is copied or traced. The geometry stays original 32-grid
  construction; a visual-similarity screen remains owed before any pick is final.
- D48 (HUMAN FEEDBACK, 2026-10-29, verbatim): "you still keep creating genric designs take your time adn
  be very atomic and precise with this work" [sic]. Recorded as a working method change: fewer options
  per round, each drawing specified with exact coordinates/radii/gaps in a construction sheet, and no
  proposal without its own small-master redraw.
- D49 (HUMAN DECISION SIGNAL, 2026-10-29, verbatim): "I do like r7-4 but it needs to be differentiated"
  [sic]. Recorded: R7-4 (solid arch front, two knocked-out circular residents) is the base the human
  likes; the task is now differentiation of that base, not replacement. Rounds 9-11 explore three
  differentiators (plinth, canopy, door seam) and an interior typology set (square windows, slot
  windows, single wide window) against that base.

- D50 (WORKING DECISION, 2026-10-29) - researched principles applied. PRINCIPLES.md records the method
  taken from the Anthropic "canvas-design" and "frontend-design" skills (fetched 2026-10-29): philosophy
  first, subject-grounded choices, one bold move, the named AI-default tells, refine-don't-add,
  construction sheets and redrawn small masters. Round 12 produced three drawings built to that
  rulebook (A Threshold, B Occupied-vacant, C Canopy); the lead's recommendation is C Canopy. A
  candidate asset pack was built pipeline-only under D42 (assets/front-candidate/, ASSET-PACKAGE.md)
  because judging the mark on real surfaces is part of the work. Status: candidate, not adopted; the
  human's pick is still the gate, and no site/app/docs/desktop integration is authorised here.

- D51 (HUMAN DECISION, 2026-10-29, verbatim): "these are all horrible clear all the logos expet the
  wordmark which we have decided and gicve me a prompt to continue with the log designa dn what
  remained we had to do in this session in another" [sic]. Read and executed as: every mark concept
  from rounds 1-12 is REJECTED; its renders, scripts and the candidate pack are cleared from the
  pipeline (files removed; git history keeps the record); the wordmark decision stands (Bricolage
  Grotesque 800, D42); the mark design continues in a NEW session via NEXT-PROMPT.md (Run 6), which
  also carries the remaining deliverables this session owed (brand guidelines, press kit, production
  wordmark, platform icon package, validation matrix, IP updates, handoff). The previous session's
  hexagon pack is quarantined under assets/_cleared-legacy-hexagon/ and is not to be used.
  No mark asset exists in the pipeline after this decision. Nothing is clearance; B10 stands.

- D52 (HUMAN INSTRUCTION and clarification, 2026-10-29, verbatim): "you can archive them but they miust
  not be accepted as candiudates in the next session" [sic]. Executed: the rejected mark work is
  archived (not deleted) under assets/archive/rejected-marks-2026-10-29/ with a manifest that marks it
  ARCHIVED, NOT CANDIDATES; the next prompt carries a hard rule that nothing from the archive may be
  revived or accepted as a candidate. This supersedes the "files removed" wording of D51.

### Run 6 session (2026-10-29, America/Vancouver) - clean-sheet mark pick and full pipeline deliverables

- D53 (HUMAN INSTRUCTION, 2026-10-29, verbatim): "Take inspiration from grokbot, the ghost from pacman
  and the maining of the word hutch" [sic]. Recorded as the Run 6 clean-sheet synthesis brief: fuse (1)
  the minimalist mouthless Grokbot character language (already reflected in Hutch's in-app 2D bot
  avatars `ID_FACES` in `src/hutch/server/static/app.js:1452-1507`: paired `±8°` inward-tilted oval
  eyes and recessed visor geometry), (2) the iconic domed-to-scalloped-skirt silhouette and directional
  gaze of the Pac-Man ghost archetype (original 3-post / 2-burrow-arch tangent-continuous waveform on
  the 32-unit grid; no contour, zig-zag skirt or asset copied from Bandai Namco), and (3) the physical
  meaning of a hutch (a protective roofed/hooded shelter raised on stile posts with open lower burrows
  housing the colony).
- D54 (HUMAN DECISION, 2026-10-29, direction gate via `ask_question`): Presented two clean-sheet
  directions built to `PRINCIPLES.md` R1–R11 (`MARK-DIRECTIONS-RUN6.md`, construction sheets
  `run6-direction-a-construction.png` and `run6-direction-b-construction.png`, and comparative surface
  matrix `run6-test-matrix.png`). The maintainer selected the recommended **Direction B — "Visor Hutch"**
  (hooded ghost-hutch dome + recessed Grokbot visor loft bay + twin gleaming tilted bot eyes +
  3-post/2-burrow skirt). This closes the mark selection gate (Run 5 adapter gate `c`).
- D55 (EXECUTION DECISION, 2026-10-29) - Task B deliverables completed pipeline-only under D42/D54:
  - Production wordmark font subsets (`bricolage-grotesque-latin-800.woff2` and
    `bricolage-grotesque-latin-var.woff2`) generated from `BricolageGrotesque-var.ttf` with `fontTools`
    and shipped alongside the verbatim upstream `OFL-bricolage-grotesque.txt` fetched 2026-10-29.
  - Pure `<path>`-outlined wordmark SVGs (`hutch-wordmark-{dark,light,mono-dark,mono-light}.svg`) and
    horizontal lockup SVGs (`hutch-lockup-{dark,light,mono-dark,mono-light}.svg`) plus `@2x` PNGs.
  - Full platform icon package for "Visor Hutch": `favicon.svg` (`prefers-color-scheme`), `favicon.ico`
    (`16/32/48` embedded), `favicon-{16x16,32x32,48x48}.png` (+ dark/light transparent variants),
    `apple-touch-icon.png` (`180x180` opaque `#09090b`), PWA `192/512` (`any`, `maskable` within W3C
    `40%`-radius safe zone, `monochrome`), `site.webmanifest`, `og-card-1200x630.png`, and
    `github-social-preview-1280x640.png`.
  - Standalone press kit (`assets/press-kit/`), validation matrix (`VALIDATION-MATRIX.md`,
    `assets/production/validation-sheet.png` with every rendered image opened and visually inspected),
    and complete brand guidelines (`BRAND-GUIDELINES.md`).
- D56 (IP PRE-SCREEN UPDATE, 2026-10-29) - Web discovery pre-screen and WIPO Vienna Tenth Edition
  candidate coding recorded for the picked "Visor Hutch" shape in `IP-CLEARANCE.md` Section 13, and
  asset provenance recorded in `PROVENANCE-REGISTER.md` Appendix C/D. Nothing is claimed as cleared,
  distinctive or non-infringing; B6, B7, B8, B9 and B10 remain open for owner/counsel decision.

### Run 6 gates and blockers

- Mark selection gate: **CLOSED (2026-10-29)** — Direction B ("Visor Hutch") selected by maintainer (D54).
- Pipeline deliverables gate: **CLOSED (2026-10-29)** — guidelines, press kit, production wordmark,
  platform icon package, validation matrix, provenance and IP updates written under
  `.pipeline/brand/2026-10/`.
- Product / site / docs / desktop integration gate: **OPEN (Run 7)** — requires its own explicit dated
  human authorisation before writing to `website/`, `src/hutch/server/`, `docs/`, or `desktop/icons/`.
- Blockers B6 (counsel review if funded; gates 3–4 OPEN), B7 (US serials 99695333 / 87196849 official
  class verification), B8 (EUIPO/TMview/CIPO/app stores/combined phrases + figurative register search on
  the picked mark), B9 (bare-name domain/handle occupancy strategy), and B10 (confirmed UK class 9/42
  word-mark overlap; name retained under written risk ownership D38) remain active and unchanged in
  legal posture.

### Run 7 session (2026-10-29, America/Vancouver) - Slice 7A execution + "The Hutch Colony" 8-resident avatar system

- D57 (HUMAN AUTHORISATION, 2026-10-29, verbatim): "proceed with the next slice/phase of work we have".
  Issued immediately after the First Response Contract presented Slice 7A (Licence, Font & Brand Docs
  Reconciliation) as the recommended clean-path slice under continued written IP risk ownership
  (D20/D23/D28/D38). Resolves the B6 integration gate for Slice 7A.
- D58 (SLICE 7A EXECUTION, 2026-10-29) - Staged `bricolage-grotesque-latin-800.woff2` (`47,260 B`,
  SHA-256 `55d3acddbb67185090064db83950341bda78539dd5fbaab3cbb02c7cfd270b9c`) and verbatim
  `OFL-bricolage-grotesque.txt` (`4,403 B`, SHA-256 `4b5a7d8f37f5602621c8a8d7358a6a2e71317e6c231c661e15aef0275d3e07ba`)
  into `website/assets/fonts/` and `src/hutch/server/static/fonts/`. Reconciled `THIRD_PARTY_NOTICES.md`
  and its byte-identical mirrors (`website/THIRD_PARTY_NOTICES.txt`,
  `src/hutch/server/static/THIRD_PARTY_NOTICES.txt`, SHA-256 `8a457f7389e10364...`) to remove stale
  `Archivo` / `OFL-archivo.txt` notices and attribute `Geist`, `Geist Mono`, and `Bricolage Grotesque`
  under SIL OFL 1.1 (resolves notice drift B9). Updated `docs/brand-assets.md` and
  `docs/design-system.md` to align with `BRAND-GUIDELINES.md`, `COLOUR-SYSTEM.md`, and
  `website/tokens.json` (resolves documentation portion of B10).
- D59 (HUMAN INSTRUCTION, 2026-10-29, verbatim): "Please also work on improving the avatars of the
  hutch paltofrm they are currentyl very good but there is a lot more we can do to make it unique like
  our logo/icons is unique now thansk to your work" [sic].
- D60 (AVATAR SYSTEM DESIGN & VERIFICATION, 2026-10-29) - Designed, mathematically verified via
  headless Chromium `Path2D` + SVG DOM evaluation (`tests/e2e/test_design_system.py:1141-1207` and
  `tests/e2e/test_browser.py:8614-8641` invariants), and visually inspected **"The Hutch Colony"**
  8-resident bot avatar system (`AVATAR-SYSTEM.md`, `assets/concepts/render_avatar_family.py`,
  `evidence/avatars/avatar-family-sheet.png`, and `BRAND-GUIDELINES.md` Section 6.2). Replaces the 8
  generic primitives (`orb` circle, `capsule` pill, `bean` blob, `drop`, `pebble`, `shield`, `triangle`,
  `hex`) with 8 architectural-creature resident silhouettes on the `64x64` grid (`Ghost Bell`,
  `Gable Hutch`, `Hopper Hare`, `Lantern Cowl`, `Transceiver Pod`, `Bastion Keep`, `Beacon Spire`,
  `Mecha Chassis`) with 8 unique vertical face-row heights (`cy = 25.6..39.8`), 100% 48-point eye
  containment (`inHead: True`), zero visor cutouts (preserving the parent/resident distinction in
  `DESIGN.md:400`), and zero line-count growth when dropped into `src/hutch/server/static/app.js` in
  Slice 7C.
- D61 (HUMAN INSTRUCTION, 2026-10-29, verbatim): "They are great did you also work on the animations for
  them like when they are working? If so we can proceed with the next slice of work if not first finish
  that then continue" and "also should we add two more avatars or are the current numbr okay?" [sic].
- D62 (AVATAR 5-STATE MOTION CHOREOGRAPHY & 8-RESIDENT ROSTER DECISION, 2026-10-29) - Specified and
  verified the 5-state operational motion choreography in `AVATAR-SYSTEM.md` Section 5 (`Idle` blink
  `6.4s`, `Working` foraging hop + `-3.2px/+3.2px` eye scan `1.6s`, `Approval Gate` upward perk `2.2s`,
  `Alert/Blocked` 3-cycle warning jolt + squint `0.48s`, `Paused` low rest), rendered
  `evidence/avatars/avatar-motion-sheet.png` (`88/88` resident x keyframe-extreme `Path2D.isPointInPath`
  checks passed), and engineered a zero-line-growth (`10` lines -> `10` lines) replacement for
  `src/hutch/server/static/studio.css:21-30`. Recorded the architectural decision to keep **8 residents**
  (`8 colours x 8 shapes = 64` pairs) rather than expanding to 10 because (1) the identity popover pairs
  8 colours above 8 shapes in an aligned `8x1` desktop / `4x2` mobile grid (`style.css:664-678`),
  (2) `tests/e2e/test_design_system.py:1182,1222,1270` hard-asserts `len == 8` and `rowCount == 2` on
  mobile, and (3) `sigilPair(name)` uses 3-bit orthogonal hashing (`2^3 = 8`) and preserves existing
  `localStorage["hutch:sigils"]` indices `0..7`.
- D63 (SLICE 7B EXECUTION, 2026-10-29) - Executed Slice 7B (`website/` marketing site brand, icon,
  manifest, social card, and wordmark integration): staged `favicon.svg`, `favicon.ico`,
  `favicon-16x16.png`, `favicon-32x32.png`, `favicon-48x48.png`, `apple-touch-icon.png`,
  `site.webmanifest`, `website/icons/icon-*.png`, `og-card-1200x630.png`, and
  `github-social-preview-1280x640.png`; declared `@font-face` (`Bricolage Grotesque` 800) and
  `.brand-wordmark` in `website/src/input.css`; wired `<head>` icon/manifest/OG links and replaced the 3
  inline hexagon marks (`26px` navbar -> `"Visor Hutch"` Master path; `22px` mobile drawer & `22px`
  footer -> `"Visor Hutch"` Small path) in `website/index.html`; compiled `website/app.css` and stamped
  18 local asset URLs (`npm run build:css:site`); verified with `tests/test_site_tokens.py` (`8 passed`),
  `tests/e2e/test_website.py` (`3 passed`), `audit_emoji.py` (`clean`), and visual inspection of
  `website-desktop-hero.png`, `website-mobile-drawer.png`, and `website-desktop-footer.png`.

