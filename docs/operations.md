# Operating Hutch locally

Hutch is a Linux-first local service. `hutch serve`, `hutch daemon`, and `hutch run` start each run in an owned worker process.
One supervisor lease coordinates scheduling and orphan recovery across web workers and a separate daemon. If the machine sleeps or
the supervisor exits, a later supervisor resumes recovery; an uncertain action is never automatically replayed.

## Linux shell requirements

`sandbox: strict` needs bubblewrap, util-linux `prlimit`, a working user `systemd-run --user --scope`, and permission to create
unprivileged user namespaces. Run `hutch doctor` for the live probe and its error. Strict commands have a private `/tmp`, no
network namespace route, workspace-only writable storage, a 4 GiB address-space and cgroup memory ceiling, a 256-process cgroup
limit, CPU/file/open-file rlimits, a per-command timeout, and bounded captured output. Limits are defaults, not per-bot settings
yet. Hutch is not a virtual machine; the host kernel and read-only system files remain visible.

New bots request strict mode. Existing bots migrated from older versions stay `off`; inspect a bot with `hutch bot show` and set
`hutch bot update <name> --sandbox strict` when the host probe passes. If strict mode is unavailable, the shell tool refuses to
run. `HUTCH_SANDBOX=off` is an explicit operator rollback that disables containment for all bots in that process. Shell network
requests are unavailable under strict mode; use `web_fetch`, which validates and pins the address for each redirect.

## Workspace continuity

New bots use a new empty workspace per run. To keep files across runs and conversations for one bot, use
`hutch bot update <name> --workspace-mode managed`; this creates a private folder under Hutch's state directory, isolated by the
bot's immutable ID. `--workspace-mode fresh` returns to per-run folders. An existing user folder is explicit:
`hutch bot update <name> --workspace-mode folder --workdir /absolute/path`. The folder must already exist and pass Hutch's path checks.
Changing modes does not copy or remove files. Deleting a bot preserves its managed workspace, and database-only snapshots/restores do not
include managed workspaces or user folders; back these up separately.

Files created through Hutch's `write_file` tool appear as SHA-256-verified downloads in the originating run. Hutch snapshots text files
up to 4 MB each and 16 MB total per run. Shell-created files remain in the workspace and are not attached to chat automatically.

## Stop and incomplete cleanup

Run status remains `Stopping` or `Recovering` when an owned process is still alive or its identity cannot be verified. Hutch records
the process IDs and retries cleanup after the short recovery lease. Do not delete process records or mark a run stopped manually.
Inspect the latest run events and worker log (`hutch bot show <name>` and the bot's `runs/<run-id>/worker.log`). If a host policy
prevents pidfd signalling or process visibility, resolve that host restriction and let the supervisor retry. Hutch will not signal
a numeric PID or process-group ID whose recorded boot/start identity does not match.

## Remote pairing (experimental)

The dashboard binds to loopback unless `--allow-remote` is explicit. For a direct private-network listener, use a certificate and key
trusted by the devices that will connect:

```bash
hutch serve --host 0.0.0.0 --port 8787 --allow-remote --tls-cert /path/to/fullchain.pem --tls-key /path/to/private-key.pem
```

Restrict reachability at the host/network firewall to your private network. Do not expose this port to the public internet. In another
host terminal, `hutch pairing create` prints a single-use code valid for 60 seconds. Exchange it only with your own device at the
HTTPS Hutch address by opening `/pair` and entering the code. The code can be used once. Connections lists paired browsers, marks the
current device, and can revoke another session or itself; a self-revoked browser returns to `/pair`. `hutch pairing list` shows active
device ids and use times; revoke a lost device from Connections or with `hutch pairing revoke <device-id>`. The browser holds an
HttpOnly cookie; the raw session secret is never returned in the response or written to the database. Pairing throttles after five
invalid attempts from one source IP in ten minutes.

The pairing form and responsive dashboard are implemented, but remote operation remains experimental: no physical-device or private
network test has been performed. Browser handoff, authenticated PTY/desktop control and trusted tunnel/reverse-proxy support are not
implemented. Tunnel/reverse-proxy deployments are not supported by this command; keep it loopback-only behind externally managed
infrastructure until trusted-proxy handling is documented and validated.

## Database migration and restore

Before a schema upgrade, Hutch writes `hutch.db.bak-vN` using SQLite's online backup API. This
realignment branch uses schema v16; `hutch doctor` displays the current version. Keep the matching
release and pre-upgrade backups. A normal snapshot captures committed database history, including
WAL pages; event buffers that have not committed yet are outside its scope:

```bash
# Replace STATE, SNAPSHOT and STATE_RESTORE; both destination directories must be new.
HUTCH_STATE_DIR=STATE hutch state backup SNAPSHOT
# Or convert an existing pre-upgrade backup to a manifest-backed snapshot:
HUTCH_STATE_DIR=STATE hutch state backup SNAPSHOT_OLD --database STATE/hutch.db.bak-vN
hutch state restore SNAPSHOT --to STATE_RESTORE
HUTCH_STATE_DIR=STATE_RESTORE hutch status
HUTCH_STATE_DIR=STATE_RESTORE hutch state report RESTORE_ID --limit 100 --offset 0
```

The restore validates copied bytes, integrity, transcript chains and immutable action intents;
migrates offline; quarantines old unfinished work; revokes devices/standing grants; pauses
schedules; and rotates resource history's epoch. It detaches source process records without
signalling them or pretending cleanup occurred. The original installation and snapshots remain
intact. Normal startup refuses incomplete restores and direct use of a snapshot as executor
state. Inspect report pages until their full scope is reviewed. The web header also explains the
hold; new chat submissions preserve their draft and return `restore_review_required`.

Before production cutover, stop the original Hutch services and verify their owned executions
have stopped. Review effects/charges after the snapshot, uncertain receipts, provider records
and excluded files. Preserve credentials/connection files, browser profiles, workspaces,
artifacts and filesystem transcripts separately; a database-only snapshot does not archive
them. Its prompts/arguments/evidence can contain private material. Check user-owned `workdir`
references before allowing new tasks to use them. Restart services on the verified installed
release, never a mix of already-loaded old modules and newly installed code. Then record a
local operator review using the restore ID printed by the command:

```bash
HUTCH_STATE_DIR=STATE_RESTORE hutch state activate RESTORE_ID --evidence 'Record what you actually checked'
```

Activation rechecks integrity/history, the installed executor/UI fingerprint and absence of
unexpected runnable work, then resolves once. It allows **new** explicit work; old work stays
quarantined and device/standing grants revoked. Activation does not unpause saved schedules;
an operator may explicitly change their paused setting during review. Re-pair devices and restore
needed grants deliberately. If installed executor/UI bytes changed since validation, restore
with that release into another new directory. Configure the service to use the reviewed state
directory only after cutover checks; the CLI does not switch your service configuration.

A new resource epoch forces stale clients to reconcile a rewound history. Existing numeric
transcript cursors lack this protection: close/reload clients after restore. Direct replacement
of a live database is unsupported. If a command failed, preserve its incomplete directory and
error, repair the cause and retry into a new destination; do not delete its marker to force
startup. Snapshot hash mismatch/SQLite sidecars require a new closed snapshot. Unexpected
execution while held or invalid history requires inspection rather than requeueing. Hashes are
integrity checks, not signatures or external-effect evidence. No production restore or hardware
power-loss certification has been performed here. See [ADR-0015](adr/0015-held-database-restoration.md).

Schema v12 reconstructs missing files from committed database events after startup. Existing
partial, changed or ahead-of-restored-history files are retained as
`transcript.preserved-*.jsonl`; inspect those copies before removing them. Do not replace an
invalid canonical database with a file mirror automatically. The run API/UI reports pending
delivery or an error while continuing to show canonical database history. Check disk space,
ownership and link errors, repair the private state directory, then let delivery retry.
SQLite uses FULL WAL synchronization; this does not certify hardware power-loss behavior.
See [ADR-0013](adr/0013-recoverable-transcript-files.md).

For **Action outcome needs review**, open the card in chat or the paginated **Needs you** drawer.
Inspect its saved arguments and authority; legacy receipts explicitly lack original arguments.
Check the file, account or service involved before selecting an outcome and recording evidence.
Recording a checked outcome performs no action and grants no permission. The original run status,
receipt and transcript remain unchanged; the UI labels the result a human report. Retry an uncertain
response with the retained report. Another client's prior record conflicts rather than overwriting it.
Do not treat a Done label on a migrated historical run as proof of a missing legacy receipt.
These commands are also available through the typed
[`/api/v1/actions/receipts` contract](realignment/contracts.md#action-receipt-review-schema-v13).

Keep the backup until the restored database opens and expected bots, runs, approvals, transcripts, conversations and messages are present. A backup from an
older schema will migrate forward on open, creating its own versioned backup first. Rollback to older Hutch code requires restoring
the matching pre-upgrade backup; older code does not honor leases or fencing. Validate restoration against a copy before using it
for production state.

Schema v8 gives every pre-existing run a separate imported legacy conversation. Schema v9 adds single-use pairing codes and hashed,
revocable sessions; schema v11 adds content-free transactional invalidations and history cursors;
schema v12 backfills recoverable transcript-file delivery without changing historic run IDs;
schema v13 retains immutable action intents and separate checked outcome reports.
Schema v14 records restore review and detached process identities without transferring source
execution authority.
Schema v15 preserves legacy memory values as unreviewed legacy proposals, without guessing a
private chat or treating a prior `user` label as approval. Review an exact revision before recall;
sharing it across a bot's chats requires an explicit decision. Rollback uses a compatible release
and its matching backup, rather than restoring automatic injection of old facts into prompts.
Schema v16 removes per-event transcript-mirror triggers. The event writer records one durable
delivery intent per committed batch in the same transaction as canonical event rows; upgraded
installations preserve pending delivery state and their pre-upgrade backup.
Hutch does not infer that adjacent runs share a
private context. New conversations and message submissions are written transactionally with their idempotency records. The
`conversation_fts` index contains message text only; it excludes tool output, credentials, workspaces and bot memory.

## Limits and evidence boundaries

Hutch's currency checks reserve a recorded-price estimate using its prompt-size estimate and requested reply-token cap. They are
admission limits, not a guarantee against provider billing differences. Configure an independent limit with the provider when you
need a separate external ceiling; do not treat Hutch's estimate as an exact dollar cap.
The product support and verification matrix is in [the realignment ledger](realignment/ledger.md). Provider calls, real local models,
Pi/OpenCode, browser binaries, mobile hardware, and physical desktop portals are reported separately from fixtures.

## Reference fact review and troubleshooting

In a bot's chat, ask it to remember a reference value. An enabled memory tool saves a proposal
for that chat, shown below its attempts. Review the exact value and scope. Keep sharing unchecked
to retain the chat boundary; explicitly share only when other chats for this bot should recall
that value. Review grants no tool permission and does not prove a fact true. Attempts outside a
canonical conversation have an isolated run scope. The model retrieves reviewed references through
`recall`; facts are not automatically injected into the system prompt.

For empty recall, check that memory is enabled, the current revision is reviewed, and its scope
matches the chat. Search uses bounded literal word terms, not arbitrary FTS operators or substring
matching. A replaced revision conflicts at review: close the dialog, refresh and inspect the new
value. Legacy proposals need explicit sharing or a new scoped revision. Oversized legacy values
need an explicitly shorter proposal. A shared key conflict requires inspecting the existing bot
reference before revising or archiving it.

Bot settings provide paginated active and archived records, revision history and human review
records. Disabling memory prevents new runtime proposals/recall and removes tools from new lists;
human management stays available. It cannot retract content already sent to a provider or erase
previous conversation/tool history. Never store credentials in reference facts.

`hutch bot forget NAME --key KEY` archives all scopes and versions with that key for the bot.
Without a key it archives all reference facts and revokes standing tool grants. Archive retains
history, the search index and backups; permanent scoped deletion/export remain unfinished.
The private `/api/v1/bots/{ref}/facts` and `/{id}/history` responses expose bounded inventories;
review their scope before any manual export. Deleting a bot archives its facts and leaves a
user-owned workspace intact.
