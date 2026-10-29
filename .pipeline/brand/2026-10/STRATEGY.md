# STRATEGY.md - Run 2 (product truth -> audience -> surfaces -> positioning)

Date: 2026-10-28 (America/Vancouver) - Run: 2 - Author: DSH session "lead" (lead-reviewed, single author)
Gate 1: SIGNED OFF by the human on 2026-10-28 before strategy work began (DECISION.md D09).
Inputs read in the prescribed order: .pipeline/brand/2026-10/00-BRIEF.md, DECISION.md (capability
probe, D01-D08), FINDINGS.md, docs/brand/00-PLAN.md via `git show brand/plan:docs/brand/00-PLAN.md`
(sections A/B/C/D/R), then surface evidence APP-BRAND-AUDIT.md 5 (route/surface map) and 6 (findings)
and PRODUCT.md. Plan section A is cited only with the FINDINGS section 2 corrections - eight plan
rows are refuted and are not repeated here.
Non-claims: this document contains no clearance, distinctiveness or non-infringement statement; the
plan G6 vocabulary applies ("cleared to the extent documented", "risk rated"). No rendered or visual
claim: browser capability B1 remains open, so every visual statement is text-derived (FINDINGS 8).
No identity implementation, no asset generation, no public files in this run (non-negotiable 3).

## 1. Product truth

Facts the strategy must not contradict. Each row cites a file read this run or a Run 1 artifact.

| # | Fact | Evidence |
|---|---|---|
| T1 | Hutch is a local-first personal-assistant app in preview; source is public; no desktop installer has been published | PRODUCT.md:20-23; website/downloads.json has empty artifacts arrays (AUDIT 6.2) |
| T2 | Promise: "Your bots. Your machine. Your rules." - retained verbatim by human decision 2026-10-28 | DECISION.md D10-D11 |
| T3 | Control state runs on the person's computer; the person chooses local or hosted models; approvals, spend ceilings, run transcripts, per-bot workspaces | PRODUCT.md:31-37, 41-49; plan A.1 (README E01) |
| T4 | Conversation is the workspace; operations views are supporting tools; governance is the loudest thing on screen; quiet chrome, dense evidence; phone is a supervisor's device | PRODUCT.md:108-118 |
| T5 | The everyday path must work without provider, runtime or executor terminology; advanced controls are available on purpose, not imposed | PRODUCT.md:11-16 |
| T6 | User-set quality gates: aesthetic score >= 90, functionality >= 95, judged on opened desktop and phone screenshots, not code inspection; the incumbent skin is on record as anti-reference | PRODUCT.md:96-106; AUDIT 6.2 |
| T7 | Frontend constraint: zero build step for the SPA, zero external assets (fonts/CDNs), vanilla ES hash-routed SPA plus Jinja/HTMX pages; the marketing site is a separate surface sharing the token source | PRODUCT.md:69-74 |
| T8 | Shipped identity equity: hexagon + centre-dot mark inlined in three HTML roots (six occurrences, one path), emerald #34d399 on ink #09090b, brand-on-background contrast 10.35:1, lowercase Geist wordmark, self-hosted Geist/Geist Mono under OFL with licence files | plan A.3 (E05), A.4, A.5; AUDIT 6.2 (casing drift) |
| T9 | Token architecture is a strength: website/tokens.json is DTCG-shaped and generates both stylesheets, has a --check drift mode, contrast verify pairs, and tests | plan A.3, R.5; FINDINGS 2 (breakdown corrected to 28/12/7) |
| T10 | The mascot is a rendered 3D character shipped for the marketing hero/CTA with 21 sprite frames; PRODUCT.md keeps the detailed character in marketing and a simple 2D identity in product; licence terms are unstated | PRODUCT.md:76-86; FINDINGS 4.4 (C27) |
| T11 | Consistency debt is real and repairable: six inline mark copies with no master file; a desktop icon variant (#28cd9d, different hex path) matching no documented accent; three wordmark casings plus a "hutch - hutch" title; notices file lists removed Archivo fonts with no Geist entry; an unrecorded Microsoft sign-in lockup ships in app.js; no favicon files, apple-touch-icon or manifest | FINDINGS 2, 4.1-4.6; AUDIT 6.1-6.2 |
| T12 | Terminology drifts: site prose says "assistant", CLI and docs say "bot"; "development preview" is the only allowed stage term | AUDIT 6.2 |
| T13 | Surfaces are enumerated: 241 API route decorators; page routes split across pages.py, pages_models.py, pages_usage.py; Studio declares 10 hash routes plus at least #/assistant/new; the marketing page has nine anchors | AUDIT 5 |
| T14 | Distribution shapes risk: the marketing site deploys atomically on merge to main; the dashboard ships in a source checkout with no server-side canary; the Tauri bundle is inactive with no icon list | plan A.7, A.4 (E09), A.6; AUDIT 6.2 |
| T15 | Three "source of truth" docs define three neutral ramps; the human chose website/tokens.json as governing on 2026-10-28 | FINDINGS 3; DECISION.md D12 |

Strategy consequence: the product's differentiator is ownership plus governed autonomy, not model
novelty. The identity's job is (a) make that legible in the first ten seconds on the marketing page
and the repo, (b) stay quiet behind governance UI in the product, and (c) survive tiny sizes and
platform contexts (favicon, manifest, desktop) as one system rather than six copies.

## 2. Audience

| Segment | Need | Evidence | What the identity must do |
|---|---|---|---|
| A1 Technical Linux builders and tinkerers | Proof over superlatives: model routes (Ollama/llama.cpp/LM Studio/OpenAI/Anthropic/OpenRouter/OpenCode), local-first, transcripts; explicit "not a fit yet" honesty | plan A.1 (README E01); T3 | Builder tone with verifiable proof (plan R.1 pattern 6); monochrome-capable mark that reads in terminals, READMEs, repo cards |
| A2 Everyday supervisors | An everyday path with no provider/runtime jargon; desktop and phone as reading and supervision surfaces; remote phone features experimental | PRODUCT.md:11-16 | Category clarity within about 10 seconds (plan R.2 identity tax); plain-language message architecture; no jargon in first-screen copy |
| A3 Existing and returning users | Learned paths (labels, landmarks, primary action, core copy) must not move | plan C08, R.2 (returning-user failures); AUDIT 6.2 | Continuity-first migration: identity layers on top, hierarchy untouched (plan R.6.1, R.6.6) |
| A4 Contributors and integrators | Rights clarity: MIT grants no trademark rights; one asset source with a misuse list; third-party service marks never restyled | plan R.3 (C21), R.1 patterns 2 and 5, C19 | Published usage/licence posture and naming rules before any outside use (later runs; not this one) |

Audience signal from the user-set quality gates (T6): every screen is judged on opened screenshots at
desktop and phone widths. The de-facto first impression for A1 and A2 is therefore a captured image -
OG/social cards, README captures, marketing screenshots (a token-driven social renderer and four
committed captures already exist - FINDINGS 2 R-8, AUDIT 6.2) - so image surfaces are first-class
identity surfaces, not decoration.

Claims discipline: marketing claims must match the actual support matrix and disclose preview state
(PRODUCT.md:72-74); no identity work may imply hosted service or packaged downloads that do not exist
(T1, T14).

## 3. Surfaces

Route/surface map: APP-BRAND-AUDIT 5 (server pages, API surface, Studio hash routes, marketing
anchors, desktop) with findings in 6. Identity job and risk tier per surface:

| Surface | Evidence | Identity job | Risk tier (plan R.2/R.6) |
|---|---|---|---|
| Marketing single page (nine anchors) | AUDIT 5 | Answer what is this / who is it for / what first within ~10s; carry the category sentence | Medium: public and atomic to deploy, revertible (plan A.7) |
| GitHub repo, README, OG and social cards | plan A.4; FINDINGS 2 R-8 | Identity at point of discovery; card renders are the first impression (T6 signal) | Low: documentation-level change |
| Server-rendered pages (overview, bots, runs, approvals, usage, models) | AUDIT 5 (pages.py + two modules) | Mark stays small and quiet; never compete with state or approvals | High for hierarchy; low for mark-only swap (plan R.6.1) |
| Studio SPA (chat home + 10 hash routes) | AUDIT 5, PRODUCT.md:64-68 | Daily workspace: consistent header lockup, stable labels | High for hierarchy; low for mark-only swap |
| Desktop (Tauri) | plan A.4/A.6; AUDIT 6.2 | Icon set lands when packaging starts; inactive bundle must not ship a default icon | Deferred until distribution exists (plan 6d) |
| Favicon, apple-touch, web manifest, PWA icons | FINDINGS 4.6; plan R.4 matrix | One master reproduces 16px legibility, 180px touch, 192/512 + maskable + monochrome | Low asset work; behaviour change accepted by human decision (D16) |
| CLI, docs, titles, JSON-LD | AUDIT 6.2 (title/terminology drift) | One name form, one lexicon, one category sentence across every text surface | Low; copy-only, tested for returning-user shock (C08) |
| downloads.json release manifest | AUDIT 6.2 | Future install surface; assets must exist before artifacts arrays fill | Backlog tied to distribution |

PWA scope: the human put "manifest + icons" in scope on 2026-10-28 (DECISION.md D16). Consequence
for later runs: the plan R.4 PWA rows (192/512 PNG, maskable 40%-radius safe zone, monochrome) join
the asset matrix, and installability behaviour change must be disclosed on the marketing site
(plan C25/C06).

## 4. Category context (plan R.1, verified 2026-10-28)

What the category's strongest systems share (transferable patterns, plan R.6.3-6.5):
1. Explicit lockup architecture with tiny-size variants (LM Studio, Home Assistant).
2. One authoritative asset source with a misuse list; "use provided files only" (Open WebUI, Obsidian).
3. A signature colour that survives a refresh - n8n kept "the pink stays" while refreshing marks.
4. Written, checkable naming rules ("Open WebUI", never "OpenWebUI"; "Home Assistant", never "HA").
5. Brand rights asserted separately from the MIT/code licence (Home Assistant, Obsidian, Python, Rust, Go).
6. Builder-first tone plus verifiable proof instead of superlatives (Ollama, Jan, Raycast).

Anti-patterns to avoid: no published asset/usage page (reproduction drift); identity louder than the
task (Domino's); a rename with no migration plan (X, plan R.2).

Implication for Hutch: the repair/retention bias in this pipeline matches the category evidence.
Hutch already holds patterns 3, 4 (partially - rules exist but drift), and 6 (proof-led marketing
anchors); it lacks 1, 2, and 5. None of the missing patterns requires a new mark - they require a
master file, written rules, and a policy, which is repair work (plan R.6.3-6.5).

## 5. Failure taxonomy (plan R.2)

| Case | Damage class | Relevance to Hutch |
|---|---|---|
| Domino's 2026 relaunch | hierarchy, discoverability, bugs, first-session comprehension, no staged rollout | Marketing/dashboard first screens must not be re-architected under cover of identity work |
| Sonos 2024 app | removed features + hierarchy + bugs | Do-no-harm table and rollback drill required before any merge (plan G2) |
| Snapchat 2018 | hierarchy/labelling + first-session; partial fix not revert | Labels and landmarks stay stable; lexicon changes ship tested |
| X 2023 rename | identity continuity only - still cost brand value (consultancy estimate) | Rename rejected (human decision D10); identity-only changes are never "free" |

Identity tax (plan R.2 working definition): the comprehension-and-activation cost a first-time user
pays when name, mark, message and first screen fail to answer (1) what is this, (2) who is it for,
(3) what do I do first. Measured as time-to-understanding, wrong first click, and non-activation -
separately from bugs.

Risk-tier separation used throughout this pipeline: mark/materials = low risk; dashboard hierarchy or
reskin = high risk, never shipped in the same release (plan R.6.1).

Measurement accepted by the human on 2026-10-28 (DECISION.md D17, plan C23): pre-registered
first-click/first-run tasks plus staged flags as do-no-harm gates; the 5-second recall test stays a
diagnostic only until a primary source is verified (plan R.5, U23); no A/B testing - there is no
telemetry and the product is local-first.

## 6. Positioning options

Each option traces to a product fact (T#), an audience (A#), and surfaces (section 3). No option is
selected in this document; selection is a human act recorded in DECISION.md at the Run 2 gate.

### PO-1 - "Own the stack you run on" (foundation)
- Traced to: T3 (control state on the person's computer), T4 (governance loudest), tagline T2.
- Audience: A1 (proof) + A2 (control in plain language).
- Surfaces: marketing #top/#proof/#control anchors, README, JSON-LD/OG metadata, dashboard empty
  state, CLI help.
- What it costs: no identity change; copy consolidation and proof points only.
- Risk: category-generic wording if proof is thin; mitigated by concrete artefacts (model routes,
  approvals, transcripts, spend ceilings) already shipped.

### PO-2 - "Plain-language control" (message architecture execution)
- Traced to: T5 (everyday path without terminology), T12 (bot/assistant drift), plan R.6.2
  (continuity contract: one category sentence, one lexicon).
- Audience: A2 primarily; A1 unaffected because advanced controls stay contextual.
- Surfaces: marketing H1/sub-line and title ("hutch - hutch" fix), chat empty state, docs, CLI help,
  OG description.
- What it costs: copy and metadata only; no visual change; returning-user copy reviewed against C08.
- Risk: first-screen comprehension must be tested before merge (accepted proxies, D17).

### PO-3 - "Say what it is" (category shortcut, Jan-style)
- Traced to: plan C24 (the H1 is emotive - "A little help with what's next." - and category clarity
  rests on the eyebrow/sub-line), R.1 (Jan's category-shortcut title).
- Audience: cold traffic among A2 arriving from search/social.
- Surfaces: marketing H1 area, title tag, OG/Twitter copy, README first paragraph.
- What it costs: copy plus a comprehension test; possible voice dilution.
- Risk: weakest fit with the emotive equity already shipped; use as a tested variant, not a default.

Selected default at the Run 2 gate: PO-1 as the foundation with PO-2 as its execution method; PO-3
only as a measured variant on the marketing head (plan R.6.2, C24). Positioning and direction were
selected together by the human on 2026-10-28 (DECISION.md D19; territory D2 "Local Hub" leads).

## 7. IP pre-screen scope (OPEN - a scope, not a search result)

Scoping only, per Run 2 rules. No search has been executed, no result exists, and no clearance,
distinctiveness or non-infringement conclusion is drawn. Plan C04 remains S1: searches precede any
design or filing spend; plan gate G1 still requires docs/brand/03-CLEARANCE-PROTOCOL.md to exist, be
signed off by the maintainer, and be reviewed by qualified counsel before any mark, name or tagline
is generated.

| Element | Scope decided 2026-10-28 | Notes |
|---|---|---|
| Name | "Hutch" in wordmark forms observed (hutch / hutch. / Hutch) | Keep-name decision D10; knockout still required on the kept name (plan U09) |
| Mark | Hexagon outline + centre-dot device (three-HTML-root variant) plus the desktop icon variant | Vienna design-element codes to be selected at execution time, not asserted here (plan C04, R.3) |
| Nice classes | 9 and 42 only; 35/41 excluded unless those services are actually offered | Human answer D13; plan R.3 core classes |
| Territories | United States, European Union, United Kingdom, Canada | Human answer D13; plan Phase 2 minimum list; expansion left to counsel |
| Registers | USPTO, EUIPO eSearch/TMview, UKIPO, CIPO, WIPO Global Brand Database | plan R.3 search surfaces |
| Common-law and conflicts | Web/app-store/GitHub/social handle and domain conflicts (plan C15), general web presence check | Handles and domain state also feed marketing decisions (U21) |
| Evidence | Dated logs (database, exact query, date) attached when executed | plan R.3 clearance protocol gate 1 |
| Owner and status | Scoped by this run; execution + dated logs in Run 3; risk posture per D20 (counsel review only if later funded) | Status: OPEN - recorded for counsel, nothing cleared |

Budget/risk posture recorded by the human on 2026-10-28: counsel engagement was the first intent
(D14) with zero external spend (D15); at the Run 2 gate the human explicitly owned the IP risk in
writing for now, with no funded counsel (D20) - that is the operative posture. Consequence: knockout
execution can proceed without fees (searching is not creation), but plan gate G1 still requires the
clearance protocol to exist and be signed off before any asset generation, and counsel review of
results happens only if/when funded. Carried as blocker B6.

## 8. What this run does not establish

- No rendered evidence of any kind (browser capability B1 open); concept previews stay text-first
  until Run 3/4 and only if B1 is fixed.
- No positioning or direction selection beyond what the human records in DECISION.md at the gate.
- No clearance result, no distinctiveness claim, no search executed.
- No asset, file, token or source change outside .pipeline/brand/2026-10/.
- Assumptions: none silent. Jurisdictions were confirmed (US/EU/UK/CA, D13); deferred items appear
  as blockers in DECISION.md, never as unstated defaults.
