# MCP S0 reconciliation — capability-fact consumption and the `profiles` naming decision

ADR-0017 §5 S0 (docs/adr/0017-governed-mcp-integration-plane-and-context-scaffolding.md:202) owns
two decisions before S5: re-run the §2.1–§2.3 verification pass on the agreed base (see
`drift-report.md` in this directory) and reconcile `new:src/hutch/compose/profiles.py` vs
`main:src/hutch/toolcalling/profiles.py` per §2.4 (:79-80) and §3.3 (:154). This document carries
that reconciliation. All citations were verified against `.worktrees/mcp-s0` @ `37911b9`.

## Recommendation

1) Resolver consumption (ADR §2.4/§3.3 mandate): compose/ consumes hutch.toolcalling.profiles as
the ONLY capability-fact source — no second evidence taxonomy, no second known-profile table, no
model-family guessing. Concretely:

   (a) the runtime already resolves once per rung (_resolve_tool_profile, builtin.py:456-484;
   final resolution at :618 with _session_revision :1008-1014) and should hand the resolved
   ModelCapabilityProfile INTO the composer call, so there is exactly one resolution per rung per
   run and profile.fingerprint() (profiles.py:78-84) is the cache/capability key alongside the
   _route_identity revision hash (builtin.py:360-378);

   (b) context-free consumers (the S5-rebuilt RunEstimator) may call resolve_profile directly —
   it is offline-pure, profiles.py:283-291 — but only through ONE shared endpoint-derivation
   helper hoisted out of the duplicated fallback chains (builtin.py:461-477 vs :367-378:
   OLLAMA_HOST/ANTHROPIC_BASE_URL/HUTCH_BASE_URL/default_endpoint logic exists twice today);

   (c) window facts stay OUT of the resolver — ModelCapabilityProfile carries no context-window
   field, so S1's OpenRouter advertised context_length (warn-only, labeled) and S5's
   connection-declared context + ModelMeta remain separate labeled sources per §3.3's
   declared-not-proven rule; the composer consumes the resolver for tool-calling capability
   evidence (which modes/contract shapes a budget can assume) and keeps window numbers attributed.

2) Naming decision: RENAME `new:src/hutch/compose/profiles.py` →
   `new:src/hutch/compose/prompt_budgets.py`, with the public type `PromptBudgetProfile` and ids
   unchanged (legacy|compact|balanced|extended|automatic per §4.3); amend ADR §3.2, §4.1, §4.3 and
   the S5 slice text to the new path. 'profile(s)' then names exactly one concept in the codebase —
   the capability resolver — matching the ask's own 'prompt-BUDGET profiles' description.

   Rejected alternatives: keeping the filename with a docstring delineation (does not survive
   greps or imports; the ambiguity is precisely what §2.4 flags, and this reconciliation itself
   had to disambiguate every 'profile' mention), and `compose/budgets.py` (collides by eye with
   the already-planned `budget.py` accounting module in the same package).

## The toolcalling package as it landed (module roles)

Measured package size: 1,876 lines over 9 modules (`wc -l`), vs §2.4's '~1,866'.

- `src/hutch/toolcalling/__init__.py` — Package facade; deliberately re-exports only strictjson's
  JSONProblem/loads_strict (toolcalling/__init__.py:8-10) — everything else is imported from
  concrete modules.
- `src/hutch/toolcalling/contracts.py` — Typed boundary contracts: frozen ToolDefinition (canonical
  name vs provider alias, schema_revision hash, scope/owner), Diagnostic, unvalidated
  ActionCandidate, immutable CompilationPlan with reversible resolve_name (contracts.py:174-180);
  COMPILER_VERSION, STRATEGIES, CLASSIFICATIONS, PROTOCOLS vocabularies and per-protocol name
  patterns (:31-48).
- `src/hutch/toolcalling/profiles.py` — THE ModelCapabilityProfile resolver (ADR §3.3 must consume
  this): exact provider+endpoint_class+protocol+model+revision → evidence-state profile
  (documented/advertised/probed/observed/stale/unsupported/unknown, profiles.py:36) from a
  versioned known-profile table (:149-264); store observations upgrade native_tools to 'observed'
  only on exact route match (:310-328); validated operator override selects but never upgrades a
  mode (:351-354); strategy_eligibility with honest reasons (:358-375); makes no network request
  (:283-291).
- `src/hutch/toolcalling/compiler.py` — Pure compile_plan: catalog + resolved profile + requested
  strategy → immutable, content- and identity-cached CompilationPlan (wire_tools / prompt_contract
  / envelope_schema / aliases / diagnostics / plan_hash, compiler.py:71-166); raises
  ToolProtocolUnavailable for ineligible explicit strategies; plan_event redacted payload for
  transcripts (:169-184).
- `src/hutch/toolcalling/envelope.py` — The versioned 'hutch-action-v1' contract for
  constrained/prompt modes: oneOf call/final/clarify envelope schema bound to each tool's lowered
  schema with byte bounds (:41-83), bounded prompt contract text (:86-114), strict whole-message
  decode_action that never scans prose (:117-171), and looks_like_envelope as a protocol-mismatch
  diagnostic only (:174-190).
- `src/hutch/toolcalling/schemas.py` — Schema lowering for constrained generation per backend
  family (xgrammar vs gbnf, schemas.py:37-41): bounded local-$ref inlining with cycle detection
  (:44-93), additionalProperties materialization/map-narrowing, anchored-pattern and format
  handling (:106-145) — never widens the canonical schema; analyze_for_plan pipeline with
  size/depth bounds (:148-180).
- `src/hutch/toolcalling/validate.py` — Canonical execution validator used on every call in every
  mode: jsonschema Draft 2020-12 when installed, else a bounded engine; analyze_schema reports
  uncertifiable keywords and validate_call fails closed on them (validate.py:216-235) — no
  coercion, no default injection, no remote $ref (docstring :20-24); required_fields/
  declared_properties helpers (:401-409).
- `src/hutch/toolcalling/strictjson.py` — Strict single-value JSON decode for model-emitted
  arguments: rejects duplicate keys (:49-57), NaN/Infinity (:43-46), enforces size/depth bounds
  (:29-32, 60-83); raw text preserved so re-encoding cannot round 19-digit ids.
- `src/hutch/toolcalling/streamassembly.py` — OpenAI-chat SSE → tool-call assembly as one explicit
  state machine: argument fragments appended in arrival order, cumulative snapshots/repeat names
  merged (:45-57), missing ids left for the loop, conflicting ids recorded (:146-149), bounds on
  calls/bytes/slots enforced during assembly (:22-24, 125-126, 168-170); should_reject_empty_stream
  (:210-213).

## Loop changes observed on the merged base (slice-facing corrections)

- All findings below are from the merged worktree `.worktrees/mcp-s0` at HEAD `37911b9` (merge of
  `2872f4f` 'wcag22-audit-fixes' — the base the ADR verified against — with `6fc6f38`, which
  carries main's `f053e3a` 'Merge branch toolcall/unified'). Measured package size: 1,876 lines
  over 9 modules (wc -l), vs §2.4's '~1,866'.
- S1 (§5 ordering rationale): the hosted-overflow citation 'builtin.py:674-688' — the
  prompt_truncated abort/escalate that never fires on hosted rungs — is now builtin.py:835-849
  (comment at :835, check at :836, continue at :849), a +162 shift from ~300 inserted loop lines;
  block content is unchanged. The new constrained-mode bad_request abort at builtin.py:727-732 is
  a second tool_protocol abort path S1's warn-only window check must not conflate with context
  overflow.
- S1 engine citations stand exactly: engine.py's only merge hunk is at ~:1113 (scheduler
  submit_scheduled/run_schedule_now), so capability_snapshot 'snapshot_version: 1' is still
  engine.py:527 and the delegation hard gate is still engine.py:579. But tests/test_delegation.py's
  pin moved 412 → 416 (documents-table fixture rows added at ~:195) — S1's text should cite :416.
- S3: the three allowlist-validation entry points 'app.py:3170,3217,3443' are now app.py:3349,
  3396, 3622 (all +179; verified same statements — ALL_TOOL_NAMES membership raises — and still
  the only three sites).
- S3/S5: tools/__init__.py gained three document tools in _CATALOG plus a 'documents' group (diff
  vs 2872f4f), shifting cited regions: memory re-check precedent old :60-62 → new :65-67;
  offline-withheld list old :68-70 → new :69-75 (unchanged membership — document tools are local,
  correctly not withheld); grant-gated tools old :91-137 → new :96-~150 (google_mail_send/
  google_mail grants now included; grant-binds-account pattern intact at :97-98). readiness.py,
  approvals.py, estimate.py, connections.py, modelchoices.py, model-switcher.js all have EMPTY
  diffs vs 2872f4f — every ADR citation to them stands as written (verified by
  `git diff 2872f4f HEAD --stat` on each).
- S3 behavior change the slice must respect: runtime/toolrepair.py validate_args now delegates to
  toolcalling.validate.validate_call (full canonical schema, fail-closed on uncertifiable schemas)
  and coerce_args no longer coerces union/missing types — the S3 'dispatch guard in steps.call_tool'
  site is intact (steps.py's merge hunk only adds a document field at ~:262). The loop's per-call
  pipeline is now alias resolve (builtin.py:903-904) → empty-args required_fields check (:916-918,
  from toolcalling.validate) → coerce → canonical validate (:923-926).
- S5: the hosted-window gap citation 'builtin.py:294-295' is now builtin.py:300-301 — 'if not
  rung.local: return Session(rung, provider, None, None)' still returns before the LM-3
  check_prompt, which remains gated on ollama-only num_ctx at builtin.py:324-329. Gap content
  unchanged, +6 shift.
- S5/§3.2: the 'specs re-derived from frozen specs every request' citation 'builtin.py:561-562' is
  replaced, not just shifted: specs are now the compiled plan's wire_tools
  ('specs = list(plan.wire_tools)', builtin.py:631, keeping the PF-1/PF-3 comment), compiled once
  per run after the model comes online via compile_plan (:618-620), with a provisional
  native-only compile (:600-605) used solely for the pre-run token estimate (:609-610) and a
  conditional recompute when the final plan differs (:634-636); per-request use is
  ChatRequest(tools=specs) at :707-708. The frozen-specs claim survives; the derivation is now the
  compiler's, and legacy-profile golden pinning (S5) must treat plan.wire_tools +
  plan.prompt_contract as today's output.
- §3.3 keying citations stand with +6 shift and identical content: _route_identity tuple old
  :354-372 → new :360-378 (still no template hash in the tuple); self-check template_hash cache
  key old :335 → new :341; per-step provider usage accounting old :650-670 → new :758-778
  (finish_step at :774-778).
- NEW capability-fact closed loop the composer can key on: the loop records a per-call capability
  observation when run.fence (builtin.py:937-942, store.record_model_capability_observation,
  store.py:4905-4935, immutable table store.py:983-1001), and _resolve_tool_profile
  (builtin.py:456-484) feeds list_model_capability_observations into resolve_profile — this is
  main's evidence-state machinery landing exactly where §3.3 said 'recorded provider usage /
  measured evaluations' should live. Also new and S5-adjacent: envelope modes pin the contract to
  one rung (abort on mid-run model switch, builtin.py:672-677), replay tool results as bounded
  <tool_result> user blocks (:648-661), bound contract repairs at 4 (:92, :792-796, :805-808),
  attach constrained structured_output (:713-716), and log plan_event + diagnostics (:623-630).

## Rationale

- ADR-0017 §2.4 (lines 79-80) explicitly assigns S0 this reconciliation: 'consume the toolcalling
  resolver for capability facts; rename or explicitly delineate new:src/hutch/compose/profiles.py
  — proposed in §3.3'; §3.3 (line 154) says 'The composer must consume that resolver for
  capability facts rather than define a parallel one; the evidence-state taxonomy is a strictly
  better version of this section's record-unknown-properties rule.' The resolver is already
  production-wired in the merged loop (builtin.py:456-484, :600-620, :623-630), so a parallel
  composer resolver would split a live evidence loop, not just duplicate a table.
- The resolver's semantics fit §3.3 exactly: keyed on exact provider/endpoint_class/protocol/
  model/revision (profiles.py:283-355), observations upgrade evidence only on exact route match
  (:310-328), overrides select but never silently upgrade a mode (:351-354), and it is
  pure/offline so the context-free estimator can use it without runtime context.
- Rename over delineate: both files would import as '.profiles'; every ADR sentence, grep, and
  future agent run would disambiguate by hand (§2.4's own coordination note demonstrates the
  cost). prompt_budgets.py is self-describing for what the module holds (per-fragment budgets,
  example counts, excerpt caps, §3.2 line 137-139) and leaves the snapshot id vocabulary of §4.3
  untouched, minimizing contract churn.
- Verified in this session: 'uv run python -c' from the worktree resolved
  resolve_profile(provider='ollama', endpoint='http://localhost:11434', model='qwen3:8b') → key
  'ollama/local', protocol 'ollama-native', fingerprint f319406d8de1b591, strategy_eligibility
  all-True, and envelope decode_action('{"action":"call","tool":"x","arguments":{"a":1}}') →
  kind='call' — the package imports and resolves under the sanctioned uv run path.
- Citation-drift method: `git diff 2872f4f HEAD --stat -- src/hutch/` (and per-file diffs) against
  the ADR's verified base 2872f4f; every old→new mapping above was read from both sides of the
  diff, and unchanged files (modelchoices.py, connections.py, estimate.py, approvals.py,
  readiness.py, model-switcher.js) were confirmed by empty diff output.

## Risks

- Endpoint-derivation duplication already shipped: _resolve_tool_profile (builtin.py:461-477)
  re-implements _route_identity's fallbacks (:367-378). If the estimator derives the endpoint
  differently, classify_endpoint (profiles.py:124-139) can return a different endpoint_class and
  silently change the evidence state for the same route — the shared helper is a required part of
  the reconciliation, not polish.
- The resolver says nothing about context windows; a contributor could over-read Evidence.supports
  as window truth. Guard: the composer keeps window sources separately labeled (§3.3
  declared-not-proven; S1's 'advertised, unverified' log) and never derives budgets from
  native_tools/constrained_schema states.
- Dependency direction must be one-way: compose → toolcalling.profiles only, never toolcalling →
  compose, or S5 creates an import cycle the moment compiler wants prompt-budget information.
- Revision sparsity: _session_revision (builtin.py:1008-1014) is non-empty only for ollama
  (ModelMeta digest/template_hash), so hosted observations match on provider+model only
  (profiles.py:314-317) and hosted capability facts stay weaker — the composer must keep treating
  hosted facts as declared, not proven (§3.3's corpus risk about undetectable serving-stack drift).
- Rename churn: ADR §3.2, §4.1, §4.3 and the S5 slice text (including the §3.2 module tree and any
  verify-command references) all say compose/profiles.py; the S0 amendment must update every
  mention in the same edit or the ledger diverges from code — the exact drift class §2.4 just
  documented for line citations.
- The composer must stay read-only over capability facts: mode selection remains the operator's
  bot.tool_protocol choice validated by compile_plan/strategy_eligibility (compiler.py:74-87,
  profiles.py:351-375); budgets may adapt to the resolved strategy (e.g., prompt-mode contract
  bytes, builtin.py:632) but must never feed a capability state back or flip a mode.
- Not run: the full regression suite (T-FULL-REGRESSION) and any test suite — the ask named no
  check to run, and this lane is read-only verification; the only executed check is the uv run
  import/resolution smoke test reported above. S0's mandated base-tree suite run remains a
  separate, blocking-on-owner step per §5 S0.
