# ADR-0006: Tool authority, an OS sandbox, and who owns the browser

Status: accepted (2026-10-07). Slice: S4 (sandbox, SSRF), S7 (browser, handoff). Evidence: baseline leads 8-9, D3, A1, B6.

## Context

Prompts, CWD and a redirected `HOME` are not a boundary: `cat /home/user/.ssh/id_rsa` works in the current shell tool. The command
parser is a useful *policy* layer and stays; it is not containment. The SSRF guard is a regex (D3). The browser context is a class
attribute shared by every bot in the process.

## Decision

### Containment

* **Bubblewrap is the Linux backend** (verified on this host: bwrap 0.13.0, unprivileged user namespaces on; inside it `/home` does
  not exist and the network is unreachable). `hutch/sandbox.py` builds the argv: read-only bind of a minimal system tree, a writable
  bind for the workspace only, `--tmpfs /tmp`, `--unshare-all`, `--share-net` only when the bot has a network grant,
  `--die-with-parent`, `--new-session`, and `prlimit` resource limits (address space, CPU time, processes, file size).
* **Levels**, set per bot (`sandbox`): `strict` (default for new bots on hosts that support it), `off` (explicit; shown in the UI as
  "no OS containment"). **If `strict` is required and the host cannot provide it, the tool refuses** (fail closed) and `hutch doctor` says why.
  Existing bots keep `off` on migration so nothing breaks silently; the UI marks them.
* **Credentials** are never mounted. A tool that needs one receives a handle and the broker injects it.
* macOS (Seatbelt) and Windows are not implemented; the matrix says so (`unavailable`).

### Structured tools over shell strings

Common operations (list, read, write, move, copy, fetch, git status/diff) are structured tools with validated arguments. `shell`
remains for the long tail. Invalid JSON arguments are rejected with a repair message and are **never** coerced into a different action
(the existing `coerce_args` repairs types only; a test pins that).

### Network and SSRF

`hutch/netguard.py` resolves the host, rejects any private, loopback, link-local, multicast, reserved or metadata address among **all**
answers (IPv4, IPv6, IPv4-mapped, encodings normalised by the OS resolver), follows redirects manually (max 5) re-checking every hop,
pins the connection to the validated IP (no second DNS lookup), and bounds the body. The browser applies the same check to every
request through a context route handler. A locally configured model endpoint is an *explicit exception* by connection, not by URL pattern.

### Approvals

An approval binds `(run, tool, canonical-args hash, destination, expiry)`. Resolution is one SQL compare-and-swap
(`pending -> approved|denied`), so two clients cannot both win. If the action changes, a new request (new id) is created.
Saved grants ("always") are narrow keys, listable and revocable, and cannot override hard-denies or outward sends (existing rule, tested).

### Untrusted content

Fetched pages, tool results, imported skills and other bots' messages are wrapped as data in the prompt and are never concatenated
into system instructions. They cannot raise a tool's policy tier. Rendered content in the UI is escaped; previews are text-only.

### Browser and desktop are different resources

* **Isolated automation browser**: one Playwright context per `(bot)` profile directory, created in the worker process that owns the
  run. Because a bot has one active run (single-instance), a profile has one owner. Different bots are different processes and
  profiles, so no global lock is needed and none exists. Sharing a login across bots is an explicit *grant* that copies nothing and
  names the profile.
* **Physical desktop** (pointer/keyboard): one lease at a time system-wide (`resource_leases` row), not implemented in this phase and
  documented as such; Wayland capture/control needs an installed, authorised executor and portal permission.
* **Human handoff**: entering `waiting_human` records the reason, the URL and a *live view*. Local display -> relaunch the same profile headed
  and wait. Remote (phone) -> a screenshot stream with an exclusive input lease (ADR-0010). On resume the page is revalidated (wall gone?) before
  automation continues; on lease expiry the run times out into `failed/handoff_timeout` rather than continuing. CAPTCHA/MFA are never solved by Hutch.

## Consequences

Cost: bwrap start-up is about 10-20 ms per shell call (measured later). Risk: a tool that needs a path outside the workspace now fails;
the error names the missing grant. Rollback: `sandbox=off` per bot, or `HUTCH_SANDBOX=off` globally (logged on every run).
