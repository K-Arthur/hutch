# ADR-0019: Spending guardrails, context continuity, and explicit task routes

Status: accepted (2026-10-11). The decision was implemented in the `cost/guardrails` lane; its original evidence is mapped in
[`cost-guardrails-failure-mapping-2026-10-11.md`](../research/cost-guardrails-failure-mapping-2026-10-11.md).
Automated coverage: `tests/test_money.py`, `tests/test_budget_policies.py`, `tests/test_runtime_budget_gate.py`,
`tests/test_openrouter_pricing.py`, `tests/test_settlement_truth.py`, `tests/test_fitloop.py`,
`tests/test_runtime_compaction.py`, `tests/test_budget_api.py`, `tests/test_model_switcher.py`,
`tests/test_migration.py`, `tests/test_compat.py`, and `tests/e2e/test_browser_budget_controls.py`.

## Context

Hutch already had an atomic usage ledger and an agent ladder, but monetary admission could accept a missing price as
zero, an OpenRouter model card did not describe the upstream endpoint the router might choose, and context was not
re-fitted after each tool result. Compaction defaults could make a paid summary call without a user review. Existing
fallbacks and escalation rules covered availability and repeated quality failures, but operators could not assign an
exact model route to an explicit task role. Public reports describe real user harms in adjacent products: zero cost
shown for OpenRouter preset IDs, stale “free” labels after promotional price changes, cache/provider variability, and
non-shrinking compaction loops. The report boundaries and responses are in the research ledger above.

## Decisions

1. **Ledger values are USD and fixed-precision.** Rates parse from provider decimal strings; reservations round up to
   micro-USD and measured settlements preserve the provider-reported value. A nonzero sub-cent estimate is displayed
   with enough precision to remain visible. Hutch has no FX source or CAD enforcement, and never converts a missing
   rate into a free route.

2. **Warn, pause and ceiling are separate policy bands.** Existing run/bot/account limits and the `run`, `conversation`,
   `bot`, and `account` budget policies feed the existing admission transaction. `NULL` is unset; `0` is a deliberate
   zero limit for new paid calls. Warning reports a crossing, pause requires a one-use release, and a ceiling refuses
   the new call. Releases bind to scope, route, budget cycle, policy revision, request hash, and reviewed estimate;
   they cannot lift a ceiling or approve changed input. Unknown-price admission under a monetary cap fails closed.

3. **OpenRouter quotes are short-lived admission estimates.** Hutch reads public model endpoint metadata without
   attaching the user's inference credential. The fetched payload hash, source, endpoint identities, fetched/expiry
   times, currency, and billing unit travel with the quote/reservation. The freshness window is five minutes. Under a
   strict USD cap, stale/missing metadata, unsupported pricing dimensions, or no qualified endpoint blocks admission;
   stale and reviewed-file prices remain labeled fallback information when no strict ceiling applies. A later
   integration pass bounds streamed response bytes at 1 MB, accepts at most 512 endpoints and 64 overrides per
   endpoint, and rechecks expiry at strict admission; incomplete refreshes cannot authorize a call. Fetches time out
   after five seconds, at most four refreshes run concurrently, and the cache holds at most 128 models. The reserve is
   the maximum whole-call cost across eligible endpoints, includes the most expensive recognized tier and possible
   cache-write rate, and does not count speculative cache savings. OpenRouter's own provider controls are not a
   session-dollar guarantee; Hutch's estimate is not an absolute provider billing cap.

4. **Provider usage is the settlement evidence.** OpenRouter requests send `usage.include=true`; when the adapter
   receives `usage.cost`, it settles to that value and keeps the provider-reported amount separately. When the provider
   omits a final usage event or charge, Hutch keeps its best estimate and marks uncertainty rather than recording a
   fabricated zero. An uncertain charge remains held until explicitly reconciled. Hutch does not sum provider costs
   and BYOK values without a verified contract.

5. **Fit is destination-specific and repeats after tool work.** Before each generation, Hutch fits the actual next
   request against the selected route's usable context and output allowance. The fitting path retains coherent
   assistant/tool units, protects the first request and current exchange, and records compaction provenance. A summary
   must reduce context; repeated or non-shrinking summaries stop rather than cycling. Original conversation evidence
   remains canonical and accessible. Task anchors that contain exact constraints, values and paths are preserved from
   indexed original user messages within a bounded allowance; over-budget anchors fail safely.

6. **Hosted summaries ask by default.** New Bots use `compaction="ask"`; `auto` is a visible, explicit opt-in, and
   `off` stops with the original conversation unchanged. Migration 62 converts existing implicit `auto` defaults to
   `ask`, because those records cannot prove that an owner deliberately chose automatic paid compaction. A hosted
   summary is separately quoted, reviewed with its route/content scope and output cap, then reserved. After approval,
   route and quote must still be admissible. The summary runs on the current authorized route; it cannot add a provider
   or account. Local summaries have no metered provider bill.

7. **Role routing is explicit and manual.** A Bot may map any of seven roles (`banter`, `classification`, `extraction`,
   `summarization`, `synthesis_research`, `code_analysis`, `verification`) to an exact `provider/model` route. The
   composer lets the owner select a role for one message; the selected model is recorded on the run, and a separate
   explicit model override takes precedence. An unmapped role uses the Bot's model. Every selected route uses existing
   route, privacy, context-fit, consent, budget, reservation and settlement checks. Strict Offline rejects hosted task
   mappings. Fallback remains an availability response; escalation remains a bounded quality response. An explicit
   refusal, denied authority or budget refusal cannot be routed around. Automatic task classification is unsupported:
   it would spend another call and has no Hutch-specific held-out quality evidence yet.

## Storage and interface

The existing ledger and Bot/Run JSON documents remain authoritative; no second accounting system is introduced.
Migration 60 adds durable compaction manifests; migration 61 adds quote provenance and makes existing pause releases single-use; migration 62 changes implicit legacy hosted compaction from `auto` to review-required `ask`. Bot role routes
and run roles are JSON fields, so they need no additional SQL columns. Studio settings, the one-message task-role
selector, `PATCH /api/bots/<name>`, conversation-message API, and `hutch bot update --task-route ROLE=provider/model`
write/read the same route mapping. `--clear-task-routes` removes all mappings. Composer preflight sends the current draft
in a JSON body and estimates the bounded recent conversation, selected reply or specialist-result reference, selected
skill instructions and rehearsal note; it does not put draft text in the URL. Context and cost remain estimates and may
change before admission. Marketing copy says estimates are not provider-enforced caps and only describes role routing as
manual.

## Verification and limits

The original cost-lane verification below is historical evidence from its dated worktree; it is not a claim that those checks ran on the integrated `main` candidate. Integration re-review adds bounds on public metadata responses and rejects expired strict quotes, and the final candidate's focused checks are recorded in the task ledger.

Local regressions exercise transactional currency admission, request-bound pause release, unknown strict prices, quote
expiry/tier/cache-write bounds, compaction progress and protected context, explicit route round-trip, model selection,
strict-offline enforcement, and provider-reported usage. The public metadata contract and one current long-context
endpoint payload were read on 2026-10-11 and retained in the artifact directory; no account data or paid inference was
used. The Studio settings/preflight journey passed at 1440×900, 768×1024 and 360×780 with zero horizontal overflow and
zero page errors, using only the deterministic mock route. Screenshots and machine-readable results are in
[`cost-guardrails-2026-10-11`](../realignment/artifacts/cost-guardrails-2026-10-11/); the marketing page also passed
desktop, tablet and phone browser checks.

The full unfiltered repository suite was stopped after remaining at 3% for several minutes. An early-stop rerun isolated
its first observed failure to the separate schedule-overview browser journey (`test_schedule_overview_shows_local_times_and_pauses_only_future_occurrences`), which waits for schedule-miss guidance; that flow is outside this change. The focused guardrail regressions and affected Studio/marketing browser journeys passed.

Still unverified: provider invoices/account-side spend limits, live model quality for any task role, route affinity and
cache reuse, all advertised provider windows, image/audio context, and full-evaluation comparison of fixed-cheap,
fixed-strong and automatic routers. The live approval gate currently waits inside the owning run worker, although the
local inference lock is released before a compaction review. Fully suspending that worker requires durable
continuation/resume architecture and remains an open resource-capacity gap. Provider billing stays authoritative.
