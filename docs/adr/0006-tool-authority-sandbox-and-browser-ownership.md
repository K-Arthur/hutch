# ADR-0006: Tool authority, an OS sandbox, and who owns the browser

Status: accepted, partially implemented (2026-10-08). S4 Linux shell containment and approval CAS are host-tested; browser profile
ownership, opt-in local Linux desktop handoff and a DNS-pinning HTTP(S)/WebSocket proxy have local fixture coverage. Live public
destinations, non-HTTP browser traffic, a headed challenge and remote handoff remain unverified or unavailable. Evidence: baseline
leads 8-9, D3, A1, B6.

## Context

Prompts, CWD and a redirected `HOME` are not a boundary: `cat /home/user/.ssh/id_rsa` worked in the baseline shell tool. The command
parser is a useful *policy* layer and stays; it is not containment. Web fetch has since moved to resolved-address checks and pinned
connections. Browser contexts were previously class-shared; ownership is now per tool instance, with a distinct persistent profile
directory for each bot. Browser HTTP(S) and WebSocket traffic also uses an owned loopback proxy so Chromium cannot perform a second
host lookup between address validation and connection establishment.

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
pins the connection to the validated IP (no second DNS lookup), and bounds the body. Chromium uses an owned loopback HTTP proxy:
the early Playwright route check is backed by a fresh proxy resolution for every HTTP(S)/WebSocket connection, all returned
addresses must be public, and the socket connects to a checked numeric address. HTTPS remains end-to-end TLS through CONNECT, so
Chromium checks the original host certificate. Local Chromium fixtures verify HTTP, redirect rebinding denial, WebSocket upgrade
forwarding and CONNECT tunnel bytes. This is not a browser network namespace: live public destinations and traffic outside the
configured HTTP proxy have not been validated. A locally configured model endpoint is an *explicit exception* by connection, not
by URL pattern.

Chromium implicitly bypasses configured proxies for localhost and link-local destinations. Hutch subtracts this bypass
(`<-loopback>`) so the egress proxy stays in the path even if the early request route changes. The behavior and special rule are
documented in [Chromium's proxy support contract](https://chromium.googlesource.com/chromium/src/net/+/HEAD/docs/proxy.md).
Service workers are blocked in the automation context, and denied request events store only the origin and reason; paths, query
strings and fragments are omitted.

### Approvals

An approval binds `(run, tool, canonical-args hash, destination, expiry)`. Resolution is one SQL compare-and-swap
(`pending -> approved|denied`), so two clients cannot both win. If the action changes, a new request (new id) is created.
Saved grants ("always") are narrow keys, listable and revocable, and cannot override hard-denies or outward sends (existing rule, tested).

### Untrusted content

Fetched pages, tool results, imported skills and other bots' messages are wrapped as data in the prompt and are never concatenated
into system instructions. They cannot raise a tool's policy tier. Rendered content in the UI is escaped; previews are text-only.

### Browser and desktop are different resources

* **Isolated automation browser**: one Playwright context per tool instance, using that bot's persistent profile directory. This
  is fixture-tested; no live account check has been completed here. Cross-process file leases prevent concurrent use of the same
  profile. HTTP(S) and WebSocket egress is pinned by the loopback proxy; non-HTTP traffic and live public destinations remain
  unverified. Opt-in local handoff keeps the same headed browser open for a human challenge; it remains experimental.
* **Physical desktop** (pointer/keyboard): one lease at a time system-wide (`resource_leases` row), not implemented in this phase and
  documented as such; Wayland capture/control needs an installed, authorised executor and portal permission.
* **Local browser human handoff**: a run may opt into one visible local browser session at a time. The run pauses while the person
  acts in that exact context, and Resume reloads/rechecks the challenge before automation continues. Remote phone input and physical
  desktop control remain unavailable. CAPTCHA/MFA are never solved by Hutch.

## Consequences

Cost: bwrap and cgroup startup is measured as part of the shell execution budget. Risk: a tool that needs a path outside the workspace now fails.
Rollback: `sandbox=off` per bot, or `HUTCH_SANDBOX=off` globally.
