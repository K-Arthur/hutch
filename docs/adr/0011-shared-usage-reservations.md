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
the matching `hutch.db.bak-vN` before rolling back to an older release. OpenCode and Pi remain disabled until they
share this reservation path and the rest of Hutch's process, isolation, and approval controls.

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
