# ADR-0014: Immutable action intent and separate outcome reconciliation

Status: implemented locally (2026-10-08); verification boundaries in the continuation ledger.
Slices: S4, S6 and S8. Extends ADR-0003 and ADR-0013.

## Decision

Schema v13 retains a private JSON snapshot of tool arguments, effective reviewed authority,
workspace/model/profile scope and worker fence before an effect starts. The saved intent has
a SHA-256 integrity fingerprint and a 4 MiB limit; runtime tool arguments are bounded to
1 MiB. SQL triggers reject changes to intent and finalized receipts. The caller cannot change
the argument object during an approval wait. Reviewed authority must still match the stored
approval, run, bot and expiry at intent admission. Every owned action write requires the
current unexpired worker fence; omitting it cannot bypass ownership checks.

A runtime return is insufficient if its receipt could not commit. Receipt storage failure or an unhandled exception after effect admission
stops further tools; an exception does not invent a returned failed receipt. Terminal transition checks missing receipts and seals them as uncertain
in the same transaction as the run status/event, retaining `outcome_unknown` rather than
reporting success or successful cancellation. A `failed` worker receipt describes a returned
tool failure; it does not promise rollback of a partly executed command.

Reconciliation is an independent, immutable operator statement. The operator reviews the
saved intent, checks the destination, selects `confirmed_done`, `confirmed_failed` or
`not_applied`, and records 1–4000 characters of evidence. Admission checks the reviewed intent
hash and requires a sealed run and a missing/uncertain receipt. One transaction records the
statement and idempotency response. Two competing clients cannot record different outcomes;
a changed retry conflicts. A valid device identity is recorded where available, otherwise
`operator` identifies the shared local/admin authority, not a named individual.

Reconciliation never changes the original run status, receipt, result digest, event chain or
transcript, executes no action and grants no permission. It is a human report, not independent
verification. Content-free `actions` invalidations refresh chat and the cross-bot Needs you
drawer while preserving an unsent draft and modal evidence. A lost response can be retried with
the same key. Unresolved older receipts are bounded and paginated in the drawer.

The builtin runtime reads a bounded current receipt note when execution starts, including for
turns queued before an earlier effect failed. Notes contain identifiers, tool names and outcome
enums, not raw arguments or operator evidence. A transaction also rejects a matching uncertain
effect from a sealed attempt in the same private conversation until reconciliation. File
matching includes workspace scope; process/web matching is deliberately conservative across
workspace changes. This is a replay guard for retained intents, not remote exactly-once delivery
or deduplication of ordinary successful calls. Unrelated private conversations are not combined.

## Migration and limits

Schema-v12 receipt migration preserves original IDs, status, summaries, fingerprints and history.
Missing arguments are explicitly `null`; adjacent events are not used to invent them. Legacy
receipts may accompany historical Done runs: those runs retain Done while API/chat flag the
receipt review separately. Legacy unknown effects conservatively block new mutating effects in
the same conversation until review because their original arguments cannot be matched safely.

The database is backed up before migration using SQLite's backup API. The fixture was produced
by committed schema-v12 code at `4bdd936`, not by the new migration implementation. It includes
a historic succeeded run with a started receipt and verifies both its unchanged event hashes
and retained backup. Production restore still needs the epoch/device/effect precautions in
operations; no rollback of external effects is implied.

Saved arguments may contain private user material; keep the state directory private. Hashes
are integrity checks, not secrecy or protection against a same-user database administrator.
Opt-in same-session browser handoff is now experimental on a Linux desktop, but the live headed
challenge flow has not been exercised. Pinned browser egress and remote phone handoff remain
pending. Generated screenshot destinations and third-party runtime permission brokering need
further capability work. External notifications, scoped fact memory and production restore
orchestration are not supplied by this slice. No paid provider or physical-device checks were
performed.

Subsequent schema-v14 work adds held database restoration in
[ADR-0015](0015-held-database-restoration.md). The action-review slice itself remains separate
from production service cutover and excluded-file preservation.
