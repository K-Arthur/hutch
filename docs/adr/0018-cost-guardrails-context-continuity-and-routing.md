# ADR-0018: Spending bands, live-price quotes, and context continuity

Status: accepted (2026-10-11). Slices: cost guardrails. Evidence: `tests/test_money.py`, `tests/test_budget_policies.py`,
`tests/test_runtime_budget_gate.py`, `tests/test_openrouter_pricing.py`, `tests/test_settlement_truth.py`,
`tests/test_fitloop.py`, `tests/test_runtime_compaction.py`, `tests/test_budget_api.py`,
`tests/test_routing_surface.py`, `tests/e2e/test_browser_budget_controls.py`.

## Context

ADR-0011 gave Hutch one atomic reservation ledger, exact settlement and uncertain holds, but admission was
binary: a cap either existed (as a per-run, per-bot-daily or per-account-daily ceiling) or did not. There was
no warning threshold, no way to require a human answer before a large call, all money was float, OpenRouter
pricing was display-only, every request reserved `$0` when no price row existed, and context was checked once
before the first call and only for local Ollama — the loop then grew without limit, which is the shipped
failure mode behind reported next-request overflows (issue F6) and repeated compaction loops (F2/F3).

## Decision

1. **Money is Decimal internally, micro-USD in the ledger.** Provider decimal strings parse exactly; reservations
   round **up** to 1e-6 USD and settlements round half-up; the legacy `REAL` columns store these quantized values
   and comparisons carry a 1e-9 USD tolerance. Display never renders a nonzero charge as free.
2. **Three independent controls per scope** (`run`, `conversation`, `bot`, `account`): `warn_usd` tells you once
   per budget cycle, `pause_usd` requires a human release bound to scope+route+cycle+policy revision before the
   crossing call, and `ceiling_usd` refuses new paid calls. `NULL` is unset; `0` is a real threshold of zero and
   means no paid spend (a free call is still admissible). A pause release can never lift a ceiling. All band
   evaluation happens inside the existing `BEGIN IMMEDIATE` admission transaction; conversation scope sums sibling
   and delegated runs via `usage`→`runs.conversation_id` with the same `max(ledger, run doc)` convention.
3. **Live OpenRouter quotes are a price source, not a budget.** `GET /models/{author}/{slug}/endpoints` is read
   without a management key; rates stay Decimal; a quote is trusted for 15 minutes and returned labeled stale on
   failure. Admission holds the **maximum whole-endpoint call cost** across eligible endpoints (never a mix of
   rates from different endpoints). Resolution order: local → flat → fresh live quote → stale live quote → the
   reviewed price file → no basis. No basis refuses under a default policy; `unknown_price="mark"` may only be
   chosen where no ceiling exists, and the reservation records `cost_unknown=1`.
4. **Provider-reported charges settle as reported.** OpenRouter `usage.cost` is recorded with
   `cost_source='provider'` and preserved in `reported_cost_usd`; otherwise the estimate is recorded and labeled
   (`estimated`/`unknown`). `usage.cost` is documented as the account charge; credit/USD parity is
   provider-documented for `/generation` and treated as unverified business risk, so receipts keep both numbers.
5. **Fitting happens before every provider call, for the actual destination.** Windows come from the local
   configuration, the provider-reported window, or the smallest admissible live endpoint window; the check runs at
   the top of every loop iteration, including after tool results. Compaction operates on *units* (an assistant
   message plus all its tool results) that are never split, reordered or edited; the system unit and the latest
   exchange stay byte-identical; each attempt must remove at least 10% of the tokens and differ from the previous
   attempt's input; at most two attempts per fit and six compactions per run. The summarizer runs on the route the
   session already uses, with its own reservation, never creates new provider authority, and never asks a human;
   it records a `run_compactions` manifest. `compaction="off"` is honored on every path and produces an actionable
   block with the canonical history untouched.
6. **Routing is configurable and refusals are not availability failures.** Bots expose fallbacks, an escalation
   ladder and the compaction mode through API, CLI and Studio; specs must parse as explicit `provider/model`
   values. A provider safety refusal ends the run (`exit_reason=refused`) instead of trying another model, and a
   provider that reports serving a different model than requested is logged.

## Consequences

Schema v53 (migrations 51–53) adds `budget_policies`, `budget_pause_releases`, reservation quote provenance and
`usage.cost_source`/`reported_cost_usd`, plus `run_compactions`. Existing `Limits` fields keep their
`0 = no limit` semantics, so no stored bot changes behavior silently; the new bands use `NULL = unset`. Canonical history
(`messages`, `runs.conversation_context`) is never rewritten by compaction. The UI places bands in the existing
"Usage and time limits" card and the review sheet in the existing composer menu; held money is now visible in the
composer meter and run view. OpenCode/Pi external runtimes still do not share this ledger.

## Verification boundary

Automated evidence covers: micro-USD rounding and display; atomic concurrent admission of two $0.09 calls under a
$0.15 ceiling across two store connections; warn-once-per-cycle and re-arming; pause release binding and denial; zero
vs unset; unknown-price refuse/mark; provider-reported settlement and quantization; live quote parsing, TTL,
single-flight, stale labeling and conservative worst case; unit-preserving compaction with bounded attempts,
non-shrinking and impossible-fit stops; runtime fit after tool results with a real (fake-server) local model;
opt-out blocking; config round-trip through API, CLI and a desktop/tablet/phone browser journey.

**Not verified in this environment:** paid provider calls (no credentials are used), OpenRouter account-side
limits/guardrails, live billing reconciliation, hosted-model windows when the provider never reports one (first
hosted call is best-effort by design), image/audio context blocks (not exposed by the chat runtime), and
cross-process pause-release races beyond the two-connection admission tests. Provider billing remains authoritative.
