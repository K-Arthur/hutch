# ADR-0009: Operating modes, offline guarantees, and resource admission

Status: partially implemented (2026-10-08): one-call/eight-waiter admission, native Ollama
headroom checks, per-bot Hybrid/Local/host-gated Offline modes. Offline remains experimental. The
current Linux development host passes Hutch's bubblewrap network/PID-namespace/Unix-socket probe and
a fixture Ollama request completed from an isolated worker; no live local model or backend
provenance was verified. Slice: S5.
Evidence: baseline lead 6, B8, A3; `tests/test_admission.py`, `tests/test_local_admission_runtime.py`,
`tests/test_offline_mode.py`.

## Decision

**Three per-bot modes** (`inference_mode` in settings, the API and CLI):

| Mode | Inference | Tools / network | Enforcement |
|---|---|---|---|
| `offline` | classified local routes only | `web_fetch` and browser are omitted; shell is available only through the strict bubblewrap sandbox; worker has isolated network/PID namespaces and reaches model routes through a per-run Unix socket | Linux bubblewrap network/PID namespaces must pass a local probe blocking loopback and host-interface TCP, checking the isolated PID view, and preserving Unix-socket access; broker forwards only to configured numeric loopback model endpoints; systemd scopes provide resource caps only; process executor required |
| `local` | classified local routes only | configured tools retain their individual network behavior | hosted per-message overrides, fallback and escalation are refused; recognized Ollama cloud-tagged names are classified as hosted |
| `hybrid` | local and hosted | normal tool policy; hosted calls use route review and usage reservations | spend and data-movement controls apply per route |

`local` is the distinct local-inference-with-online-tools choice. `offline` is a worker egress
boundary, not proof about the server handling local inference: a separate Ollama/LM Studio/vLLM
service may itself proxy traffic or download models. The runtime restricts endpoints to numeric
loopback, removes web/browser tools and scrubs provider, proxy and custom-endpoint environment
variables. Saved `connections.json`, `keys/`, and ChatGPT OAuth account records are overmounted with
a read-only empty view; the
worker retains the shared SQLite state it needs for fenced run updates. Each worker runs in fresh
bubblewrap namespaces. A private per-run Unix socket is
the only model egress: the supervisor-side broker fixes the target address to the bot's validated
loopback endpoint and never accepts a destination from the worker. systemd user scopes apply
memory and process-count caps; they do not filter Offline networking.
External runtimes, hosted routes, model overrides, unsupported endpoints and in-process execution
are refused. Shell additionally requires strict bubblewrap containment. The capability probe is
local-only: it opens listeners on IPv4/IPv6 loopback and one address assigned to the host in each
available family, makes TCP connect attempts from a fresh bubblewrap network namespace, verifies
that the isolated PID view exposes only the expected namespace processes, and checks a two-byte
Unix-socket exchange.
It sends no public traffic. The development host passes this probe, and a fake Ollama health
request completed through the broker inside the isolated worker. This is fixture evidence, not a
live local model or provider check. A loopback URL or model label alone cannot prove inference
provenance; the separate model service may proxy requests or download models.

**Implemented admission:** `hutch/admission.py` uses kernel locks and a bounded FIFO ticket set
across workers sharing one state directory: one call and eight waiting callers, including startup
and self-check. It releases between provider calls, before tools or human waits. Stop can remove
a waiter before usage reservation; process death releases locks without a lease timeout. The
runtime persists `waiting_resources`, position/reason and recorded admission wait time.

Native Ollama rechecks physical free RAM/GPU memory before generation. Its reported own resident
allocation avoids counting the same model twice; credit is capped by totals and not assigned to
unknown multi-GPU placement. Missing GPU headroom refuses, and measured zero remains zero. Fit
still estimates weights/KV cache. Other local protocols do not have validated memory admission.
Hutch's queue does not govern unrelated model-server clients or prove backend cancellation.
Browser/battery-aware admission, pressure-driven unloading and backend provenance remain pending.
Strict worker egress enforcement uses a network namespace and loopback-only model broker. The
current host probe and fixture request pass, while live model-server behavior remains unverified.
Runtime keep-alive still follows the bot preset; unsafe
environment slot widening is removed.

## Consequences

Cost: native fit checks probe current hardware and query model metadata/residency. Live latency is
unmeasured. Hardware/footprint signals have the limits above; this is no hard resource guarantee.
Rollback restores a verified release and compatible database while preserving admission protections;
it does not disable enforcement or silently enable hosted routes.
