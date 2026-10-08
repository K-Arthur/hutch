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

## Remote pairing (experimental)

The dashboard binds to loopback unless `--allow-remote` is explicit. For a direct private-network listener, use a certificate and key
trusted by the devices that will connect:

```bash
hutch serve --host 0.0.0.0 --port 8787 --allow-remote --tls-cert /path/to/fullchain.pem --tls-key /path/to/private-key.pem
```

Restrict reachability at the host/network firewall to your private network. Do not expose this port to the public internet. In another
host terminal, `hutch pairing create` prints a single-use code valid for 60 seconds. Exchange it only with your own device at the
HTTPS Hutch address. `hutch pairing list` shows active device ids and use times; revoke a lost device with
`hutch pairing revoke <device-id>`. The browser holds an HttpOnly cookie; the raw session secret is never returned in the response or
written to the database. Pairing throttles after five invalid attempts from one source IP in ten minutes.

The phone-facing UI and live browser/PTY controls are not complete, and this path has not been tested on physical devices or across an
operator's network. Tunnel/reverse-proxy deployments are not supported by this command; keep it loopback-only behind externally
managed infrastructure until trusted-proxy handling is documented and validated.

## Database migration and restore

Before a schema upgrade, Hutch writes `hutch.db.bak-vN` using SQLite's online backup API. The current schema version is displayed
by `hutch doctor` (schema v9 in this realignment branch). Stop Hutch services before restoring a backup:

```bash
# Replace STATE with the configured Hutch state directory.
sqlite3 STATE/hutch.db.bak-vN '.backup STATE/hutch.db.restore'
mv STATE/hutch.db.restore STATE/hutch.db
```

Keep the backup until the restored database opens and expected bots, runs, approvals, transcripts, conversations and messages are present. A backup from an
older schema will migrate forward on open, creating its own versioned backup first. Rollback to older Hutch code requires restoring
the matching pre-upgrade backup; older code does not honor leases or fencing. Validate restoration against a copy before using it
for production state.

Schema v8 gives every pre-existing run a separate imported legacy conversation. Schema v9 adds single-use pairing codes and hashed,
revocable device sessions. Hutch does not infer that adjacent runs share a
private context. New conversations and message submissions are written transactionally with their idempotency records. The
`conversation_fts` index contains message text only; it excludes tool output, credentials, workspaces and bot memory.

## Limits and evidence boundaries

Token estimates are not currency caps. A provider path without a firm pre-call price bound cannot claim a hard spend ceiling.
The product support and verification matrix is in [the realignment ledger](realignment/ledger.md). Provider calls, real local models,
Pi/OpenCode, browser binaries, mobile hardware, and physical desktop portals are reported separately from fixtures.
