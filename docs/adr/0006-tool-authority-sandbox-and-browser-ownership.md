# ADR-0006: Tool authority, an OS sandbox, and who owns the browser

Status: accepted, partially implemented (2026-10-07). S4 Linux shell containment and approval CAS are host-tested; browser profile
ownership is implemented and fixture-tested; same-session handoff and pinned browser egress remain unimplemented. Evidence: baseline
leads 8-9, D3, A1, B6.

## Context

Prompts, CWD and a redirected `HOME` are not a boundary: `cat /home/user/.ssh/id_rsa` worked in the baseline shell tool. The command
parser is a useful *policy* layer and stays; it is not containment. Web fetch has since moved to resolved-address checks and pinned
connections, while browser DNS is still not pinned (D3). Browser contexts were previously class-shared; ownership is now per tool
instance, with a distinct persistent profile directory for each bot.

## Decision

### Containment

* **Bubblewrap is the Linux shell backend** (verified on this host: bwrap 0.13.0, unprivileged user namespaces on; inside it `/home`
  does not exist and the network is unreachable). Hutch mounts the workspace writable and a minimal system tree read-only,
  creates a private `/tmp`, uses `--unshare-all`, `--die-with-parent`, and applies CPU/address-space/file/open-file limits with
  `prlimit`, plus memory and task limits with `systemd-run --user --scope` cgroups. Strict mode has no shell-network grant; use
  Hutch's address-checked `web_fetch` tool. Captured output is bounded while both streams are drained.
* **Levels**, set per bot (`sandbox`): `strict` (default for new bots, including unsupported hosts), `off` (explicit; shown in the UI
  as "no OS containment"). **If `strict` is required and the host cannot provide it, the tool refuses** (fail closed) and
  `hutch doctor` says why.
  Existing bots keep `off` on migration so nothing breaks silently; the UI marks them.
* Existing bots keep `off` on migration so their behavior does not change silently. macOS (Seatbelt) and Windows are unavailable.

### Structured tools over shell strings

Common operations (list, read, write, move, copy, fetch, git status/diff) are structured tools with validated arguments. `shell`
remains for the long tail. Invalid JSON arguments are rejected with a repair message and are **never** coerced into a different action
(the existing `coerce_args` repairs types only; a test pins that).

### Network and SSRF

`hutch/netguard.py` resolves the host, rejects any private, loopback, link-local, multicast, reserved or metadata address among **all**
answers (IPv4, IPv6, IPv4-mapped, encodings normalised by the OS resolver), follows redirects manually (max 5) re-checking every hop,
pins the connection to the validated IP (no second DNS lookup), follows redirects in Hutch and re-checks each hop, and bounds the
body. The browser checks every request through a context route handler, but its own DNS lookup is not pinned yet; DNS rebinding is
a known residual risk. A locally configured model endpoint is an *explicit exception* by connection, not by URL pattern.

### Approvals

An approval binds `(run, tool, canonical-args hash, destination, expiry)`. Resolution is one SQL compare-and-swap
(`pending -> approved|denied`), so two clients cannot both win. If the action changes, a new request (new id) is created.
Saved grants ("always") are narrow keys, listable and revocable, and cannot override hard-denies or outward sends (existing rule, tested).

### Untrusted content

Fetched pages, tool results, imported skills and other bots' messages are wrapped as data in the prompt and are never concatenated
into system instructions. They cannot raise a tool's policy tier. Rendered content in the UI is escaped; previews are text-only.

### Browser and desktop are different resources

* **Isolated automation browser**: one Playwright context per tool instance, using that bot's persistent profile directory. This
  is fixture-tested; no live browser check has been completed here. It remains experimental, with process-wide action serialization,
  no pinned DNS/egress and no visible handoff.
* **Physical desktop** (pointer/keyboard): one lease at a time system-wide (`resource_leases` row), not implemented in this phase and
  documented as such; Wayland capture/control needs an installed, authorised executor and portal permission.
* **Human handoff**: a live session with an exclusive input lease is planned (ADR-0010), not implemented. Current runs can pause at
  detected human-check pages but do not transfer control to a person in the same browser session. CAPTCHA/MFA are never solved by Hutch.

## Consequences

Cost: bwrap and cgroup startup is measured as part of the shell execution budget. Risk: a tool that needs a path outside the workspace now fails.
Rollback: `sandbox=off` per bot, or `HUTCH_SANDBOX=off` globally.
