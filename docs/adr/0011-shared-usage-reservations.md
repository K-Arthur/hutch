# ADR-0011: Reserve shared provider usage before requests

Status: accepted (2026-10-07). Slice: S5, partial. Evidence: baseline lead 6; `tests/test_reservations.py`.

## Context

Checking only the usage ledger before a hosted call is racy: two bots or processes can each see the same remaining
provider allowance and spend it concurrently. A timeout after sending a request also leaves Hutch unable to know
whether the provider charged for it. Releasing that capacity or retrying blindly can overshoot a budget or duplicate
an uncertain charge.

## Decision

1. Before a hosted model request, one `BEGIN IMMEDIATE` transaction checks and inserts a reservation for the run,
   bot, and configured billing account. It accounts for measured ledger usage plus active and uncertain reservations.
2. A connection may name a shared `account_id`. Every configured connection in that account contributes its token
   allowance windows; the strictest declared daily currency cap applies across the account. Per-bot token and cost
   caps and per-run cost caps use the same transaction.
3. On a response with usage counts, settlement inserts actual usage and changes the reservation to `settled` in one
   transaction. Run, bot, provider, model and account identity cannot change. Exact duplicate
   settlement does not duplicate usage; a changed outcome conflicts. Owned workers must supply
   a current, unexpired fence for reservation, settlement, release and uncertainty writes.
4. When the provider may have accepted a request but Hutch did not receive verifiable usage, the reservation becomes
   `uncertain` and continues counting against caps. An operator can list unresolved reservations and reconcile only
   after the run is terminal, using either exact provider usage or a verified no-charge finding.
   Neither midnight nor a rolling-window boundary releases an unresolved hold. Measured usage
   uses the requested accounting window; all outstanding reservations still consume it.
   A late reply cannot settle an uncertain hold through the normal worker path.
5. Currency reserves are based on a local price record and prompt-size estimate plus the requested reply-token cap.
   A currency-capped call with no price row fails closed. These estimates are conservative admission controls, not a
   guarantee against provider-side billing differences; no marketing or API field may describe them as exact hard
   dollar caps. Subscription quotas are user-declared token proxies unless the provider supplies enforceable units.
6. Reservations are local to Hutch. They cannot account for usage from provider clients outside Hutch unless the
   operator imports that usage into Hutch's ledger. The CLI and API expose held values and uncertainty explicitly.

## Consequences

Schema v10 adds account grouping and an immutable usage reservation record. Existing usage is grouped under its
former provider name on migration. Before upgrading an existing database, Hutch uses SQLite's backup API; restore
the matching `hutch.db.bak-vN` before rolling back to an older release. OpenCode uses this reservation path: one
reservation covers the admitted prompt and its bounded internal turns, then provider-reported tokens and cost are
settled per completed assistant message. A disconnect after admission becomes `uncertain` and `outcome_unknown`.
Pi remains disabled because it does not share this path or Hutch's per-action approval hook.

## Verification boundary

Builtin streaming recovery now performs a separately reserved non-streaming attempt. A partial
first stream remains uncertain; it is not silently settled from the second response's usage.
If another reservation would exceed the remaining account/bot limit, no second request is sent.
Low-level provider diagnostics retain their optional retry behavior; they are explicit operator
calls outside scheduled builtin-run budget admission. This distinction is exposed in the request
contract through `allow_stream_retry`, disabled by the builtin runtime.

Automated tests cover competing SQLite connections and spawned processes, account-shared token windows, exact settlement, uncertain holds,
terminal-only reconciliation, migration, the typed API, and the dashboard. No live provider account, provider-side
budget enforcement, pricing accuracy, or external-runtime billing behavior has been verified.

## Shared account period and editing revision (2026-10-26)

Explicit account policies may now choose `lifetime` as well as the existing `local_day` default. Admission and
preflight use all measured usage for that account plus every reserved/uncertain hold for a lifetime policy;
the same SQLite admission transaction prevents separate Bots or Store connections from racing the limit.
Daily legacy caps remain independent. No schema migration is required: the existing table already admits this
reset value. Bot policies remain daily, run/conversation policies retain their existing lifetime semantics.

The versioned budget GET adds prospective totals for both account periods. PUT accepts an optional
`expected_revision` (zero for an absent policy), checked in the write transaction; mismatch returns 409.
The dashboard supplies it, while existing callers may omit it for compatibility. The connection directory
exposes the actual account identity and uses shared-account token usage, matching enforcement rather than
displaying separate alias counters. No credential or model permission is changed.

Lifetime policies require this supporting application version. Do not roll back to an older application against
a database containing one: older policy validation does not accept the new application-level option. Follow
the matching backup/recovery procedure and reconcile any charges incurred after the backup; restoring a
database must never be mistaken for refunding provider charges. These estimates still require verified price
bounds and runtime-specific dispatch accounting before the evaluation can claim a bounded live spend.

## Capped OpenRouter request capacity reservation (2026-10-26)

A strict OpenRouter ceiling now reserves full published endpoint input capacity plus the requested output cap,
rather than relying on Hutch's characters-per-token estimate for input. For each eligible endpoint the input
bound is the smaller of its known context and explicit prompt limit; unknown context remains ineligible.
Output is added without subtracting it from the context to conservatively cover combined windows. The largest
whole-endpoint cost includes all declared tier/cache-write premiums and request fees. Quote records distinguish
`USD/context-capacity-reserve` from ordinary estimates. Settlement and uncertainty rules are unchanged.

This relies on published endpoint limits/prices and the provider respecting the requested output cap. It does
not bound a native runtime's hidden internal requests, server-side retries or changed/incorrect provider billing.
The isolated evaluation must still enforce endpoint privacy/capability/maximum-price routing, phase and total
budgets, and reconcile responses. [OpenRouter endpoint metadata](https://openrouter.ai/docs/api/api-reference/endpoints/list-all-endpoints-for-a-model)
and [routing controls](https://openrouter.ai/docs/guides/routing/provider-selection) are the source contracts;
no provider source code was reused.
