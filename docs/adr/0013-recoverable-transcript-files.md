# ADR-0013: Recoverable transcript files and durable action prerequisites

Status: implemented locally; schema-v16 batching update (2026-10-08). Slice: S4/S9. Extends ADR-0003 and ADR-0012.

## Decision

SQLite remains the canonical transcript. Schema v12 first guaranteed pending delivery in the
same transaction as each event through an AFTER trigger. Schema v16 replaces that trigger with
one delivery-intent upsert per event batch in the canonical event transaction. An already-pending
job covers newer events without a redundant update; status derives the current tail from committed
events. Acknowledgement rechecks the canonical tail in its SQL
transaction before clearing pending; an event committed during file IO remains due, and an
insert after acknowledgement makes the job pending again. Status reads return the actual
canonical target. Historic events are backfilled;
the original bot directory is retained even if the bot is subsequently deleted. Delivery
does not depend on a worker callback, a bus notification or an executor still being alive.

An owned background worker scans at startup and retries pending delivery. A fixed private
file lock serializes competing Hutch processes. Files and locks must be owned regular files
without hard links; symlinks and unsafe path components are refused. New files use mode 0600.
This assumes an operator-owned state directory, not a security boundary against hostile code
already running as the same host user.

Before appending, delivery checks the existing JSONL prefix against canonical event sequence,
content and hashes. An unacknowledged complete write is reused without duplicate rows. A
partial, changed or ahead-of-restored-history mirror is renamed to a unique
`transcript.preserved-*.jsonl` file before a new mirror is reconstructed in bounded batches.
A damaged canonical hash refuses reconstruction and preserves the existing file. Older
unhashed events retain their legacy integrity boundary; migration does not invent hashes.

Acknowledgement follows Python buffer flush, file fsync and containing-directory fsync.
[Python fsync](https://docs.python.org/3/library/os.html#os.fsync).
Database delivery errors remain pending and visible, including a crash after file write but
before acknowledgement. Restoration into a new state directory discovers missing acknowledged
files at startup and reconstructs them; it does not restore external side effects.

Reads use at most 128 rows and about 4 MiB of raw payload per batch, allowing one larger event
up to the 32 MiB line bound. Sizes are inspected before loading payloads. The verified-prefix
cache holds at most 128 files and avoids quadratic rereading during incremental delivery.
Persistent errors do not starve later runs. Shutdown interrupts prefix scanning and joins the
worker before closing SQLite; a blocked worker leaves persistence open and reports the failure.
Closing does not promise that all pending files are delivered. `Store.flush_transcripts()`
explicitly waits for startup checking and delivery or reports an actionable timeout.

The run resource reports `transcript_mirror` target/delivered sequences, pending and error
state. Content-free `transcript_mirrors` invalidations update the UI when delivery recovers.
An audit-file failure does not rewrite a completed executor as failed. The UI retains its
canonical answer and Done label, displays the file warning, and preserves an unsent draft.

SQLite connections now use WAL with `synchronous=FULL`. Permission admission, action intent
and budget reservations must be durable before an external effect is authorized. NORMAL
WAL preserves application-crash commits but can lose recent commits on OS/power failure;
FULL adds commit synchronization. [SQLite synchronous modes](https://www.sqlite.org/pragma.html#pragma_synchronous).
No live power-cut or faulty-storage certification was performed. Actual durability still
depends on the filesystem and hardware honoring synchronization.

## Limits and verification

Startup scans recorded file metadata; new delivery verifies canonical prefixes. This is not
continuous rehashing of every idle file or protection against a same-user adversary replacing
state. Operators should preserve forensic copies and investigate a canonical integrity error.
There is no automatic retention of preserved files; inspect and remove them deliberately after
reconciliation. Safe production restore orchestration and external notification delivery remain
separate work. The existing restored-history epoch/device/effect precautions still apply.

Local tests cover transactional rollback, process death after fsync before acknowledgement,
two competing delivery processes, missing acknowledged files, partial/changed/ahead mirrors,
canonical corruption, hostile links, fair retry, byte/cache bounds, incremental reads and blocked
shutdown. Browser fixtures exercise visible IO failure and successful retry at desktop, tablet
and phone viewports. These are process/filesystem/browser fixtures, not paid-provider, physical
device or power-failure checks. Results and inspected artifacts are in the continuation ledger.
