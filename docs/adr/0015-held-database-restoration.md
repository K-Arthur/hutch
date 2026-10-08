# ADR-0015: Restore history without transferring execution authority

Status: implemented locally (2026-10-08); verification boundaries in the continuation ledger.
Slices: S2, S4 and S8. Extends ADR-0003 and ADR-0012–0014.

## Problem and decision

A database copy can carry a live PID, boot/start identity and unexpired lease from its source.
Starting recovery on that copy on the same host could signal the original worker. Queued work,
standing grants and restored device tokens could also become active despite effects that happened
after the snapshot. A valid SQLite file does not resolve those external outcomes.

`hutch state backup` uses SQLite's online backup API to capture committed database history,
including WAL pages. It does not migrate the source. The new snapshot directory is private and
exclusive; a persistent snapshot marker prevents using it directly as executor state. The
database is normalized to a closed standalone file, fsynced and recorded in a SHA-256 manifest
with schema/version and the capturing executor/UI fingerprint. Incomplete snapshots remain marked.
Backup has a five-minute progress deadline. See the primary
[SQLite backup API documentation](https://www.sqlite.org/backup.html).

`hutch state restore SNAPSHOT --to NEW_STATE` never overwrites an existing installation. It
rejects incomplete inputs, mismatched hashes, linked input files and SQLite sidecars. The copied
standalone bytes are checked against the manifest before opening/migrating them. The copy opens
in maintenance mode without event, mirror, scheduler or execution workers. Integrity, foreign-key,
bounded transcript-chain and action-intent checks precede quarantine. Migration uses the existing
serialized upgrade and retains pre-upgrade backups. Failure leaves an incomplete marker that
normal Store startup refuses; it does not modify the source or silently publish partial state.

Schema v14 records the restore and bounded inventory pages. In one transaction it:

- detaches recorded source process identities from cleanup authority, retaining the identity and
  `ended_at` unchanged rather than fabricating evidence of termination;
- seals unfinished/queued attempts as Needs review with an explicit restoration reason, bumps
  fencing and clears their execution ownership; completed history keeps its status and document;
- retains old task rows as quarantined, never automatically requeues them, and holds unsettled
  provider usage as uncertain;
- expires pending approvals, revokes standing grants and device sessions, removes pairing codes,
  pauses schedules and relinquishes copied supervisor leases;
- rotates resource history's epoch and holds the installation against new submission, worker,
  supervisor and recovery claims.

The new status event explicitly says source processes were **not stopped** by restoration. They
are outside the copy's authority. This is restoration of evidence, not cancellation or rollback
of external effects. The report includes counts and IDs, without prompts, arguments, private
device labels or permission keys. Original arguments remain in their private canonical records.

The authenticated versioned API exposes report pages. The existing header displays the hold on
desktop and phone; a read-only dialog explains its scope without adding another navigation page.
Chat rejects unsent work with an actionable error while keeping the draft. Activation is local
CLI only: the operator records review evidence. An immediate transaction rechecks integrity,
history, installed executor/UI fingerprint and absence of unexpected runnable work, then records
activation once. A changed competing review conflicts. New work may be submitted afterwards;
old work, grants, device sessions and paused schedules are not reinstated. A restore of a held
copy supersedes its prior hold with a new auditable hold rather than inventing a human review.

## Boundaries

The snapshot is **database only**. Credentials/connection files, browser cookies/profiles,
workspaces/artifacts/user files and filesystem transcript mirrors need separate preservation and
review. Database prompts, arguments and evidence may themselves contain private material. Hashes
are integrity checks, not signatures, secrecy or protection against the same-user administrator.
Legacy unchained events remain explicitly unverified. Restoration cannot establish which missing
external effects or provider charges occurred after the snapshot. The operator must stop original
services before production cutover and review referenced working folders and excluded files.

The isolated tests exercise current and genuine schema-v4 snapshots, a source process alive on
the same boot, WAL capture, tampered history, sidecar rejection, competing local activation and
restart. Browser tests use real local APIs with synthetic old work. No production restore,
physical phone, storage power-cut, live provider or hardware accessibility certification is claimed.
Older code requires its compatible pre-upgrade database and verified release; do not downgrade
this database or remove protections to obtain a rollback.
