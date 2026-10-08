# ADR-0012: Transactional resource changes and client reconciliation

Status: implemented for local resource invalidation (2026-10-08). Slices: S4/S8. Transcript-file delivery is separately implemented in ADR-0013; external notifications and interactive control remain pending.

## Decision

Schema v11 installs ordinary AFTER triggers for bots, conversations, messages, runs, tasks,
approvals, actions, usage/holds, memory, standing permissions and device revocation. Each
material mutation and its outbox row commit or roll back together. Identifiers and operations
are retained; message text, arguments, fact values and credentials are not copied into this
feed. Routine lease/device touches and unchanged values do not generate invalidations.
Connection configuration stored outside SQLite is not covered.

The server reads pages of at most 500 changes in one read transaction. The snapshot pins
resource state and its change cursor together; later changes are replayed. WAL readers can
retain that snapshot while another connection commits. [SQLite isolation](https://www.sqlite.org/isolation.html).

A cursor is an opaque database-history epoch and committed row ID. Each row points to its
previous committed change, while metadata keeps the tail even after all log rows are removed.
The server detects missing leading/middle/trailing ranges and refuses incomplete replay;
it does not assume IDs are consecutive. [SQLite AUTOINCREMENT](https://www.sqlite.org/autoinc.html).
Migration checks trigger column names explicitly and uses AFTER triggers.
[SQLite trigger cautions](https://www.sqlite.org/lang_createtrigger.html).

`/api/v1/changes` returns typed pages. `/api/v1/changes/stream` uses the same cursor as its
SSE ID and honors `Last-Event-ID` before the initial query. A gap emits `snapshot_required`
without advancing the ID and ends the stream. Reconcile resources, then reopen at the
snapshot's `change_cursor`. Bus notifications accelerate reads; one-second polling discovers
commits even when a writer crashes before notifying. Ordinary reconnect keeps the SSE cursor.

The UI fetches authoritative visible resources, coalesces invalidations and keeps periodic
readers as fallback. It refreshes chat/attention/roster without routing away or replacing the
composer/settings form. A history gap clears cached terminal HTML. Approval request, waiting
status and review event commit together. Run/event resources return canonical decision
summaries so a worker crash before its response event cannot leave an already-decided ask.

## Boundaries and verification

Existing resources are not fabricated as historic changes during migration; a new client
starts with a snapshot. Retention is not automatic. The feed is an invalidation outbox, not
exactly-once external notification delivery, full event sourcing or a durable JSONL drainer.
Schema v12 adds a separate recoverable JSONL queue and changes SQLite synchronization from
NORMAL to FULL; see [ADR-0013](0013-recoverable-transcript-files.md). File delivery can lag or
remain in an observable error state. Process-crash fixtures do not certify power-loss durability.

An unmanaged restore of a v11 database can rewind and later reuse its epoch/IDs. Services and
clients must be stopped and the restored epoch rotated before restart; reconnect alone is
insufficient. Preserve backups and JSONL files. Safe restore automation remains a subsequent
persistence slice; the operations guide includes the required epoch rotation.

Tests cover process death before/after commit, three competing writers, reopen, nonconsecutive
IDs, empty and middle retention gaps, consistent snapshot/cursor, v10 migration backup,
real-socket restart and silent writes. Browser fixtures suppress fallback timers and transcript
hints, reconcile an injected gap, then observe admission and another client's denial while
retaining the draft/focus. These are local fixtures, not physical-device or live-provider checks.
