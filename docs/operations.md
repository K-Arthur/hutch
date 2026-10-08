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

## Stop and incomplete cleanup

Run status remains `Stopping` or `Recovering` when an owned process is still alive or its identity cannot be verified. Hutch records
the process IDs and retries cleanup after the short recovery lease. Do not delete process records or mark a run stopped manually.
Inspect the latest run events and worker log (`hutch bot show <name>` and the bot's `runs/<run-id>/worker.log`). If a host policy
prevents pidfd signalling or process visibility, resolve that host restriction and let the supervisor retry. Hutch will not signal
a numeric PID or process-group ID whose recorded boot/start identity does not match.

## Database migration and restore

Before a schema upgrade, Hutch writes `hutch.db.bak-vN` using SQLite's online backup API. The current schema version is displayed
by `hutch doctor`. Stop Hutch services before restoring a backup:

```bash
# Replace STATE with the configured Hutch state directory.
sqlite3 STATE/hutch.db.bak-vN '.backup STATE/hutch.db.restore'
mv STATE/hutch.db.restore STATE/hutch.db
```

Keep the backup until the restored database opens and expected bots, runs, approvals, and transcripts are present. A backup from an
older schema will migrate forward on open, creating its own versioned backup first. Rollback to older Hutch code requires restoring
the matching pre-upgrade backup; older code does not honor leases or fencing. Validate restoration against a copy before using it
for production state.

## Limits and evidence boundaries

Token estimates are not currency caps. A provider path without a firm pre-call price bound cannot claim a hard spend ceiling.
The product support and verification matrix is in [the realignment ledger](realignment/ledger.md). Provider calls, real local models,
Pi/OpenCode, browser binaries, mobile hardware, and physical desktop portals are reported separately from fixtures.
