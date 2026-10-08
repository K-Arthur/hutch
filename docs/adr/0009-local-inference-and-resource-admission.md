# ADR-0009: Operating modes, offline guarantees, and resource admission

Status: partially implemented (2026-10-08): one-call/eight-waiter admission and native Ollama
headroom checks; operating modes and inference provenance remain pending. Slice: S5.
Evidence: baseline lead 6, B8, A3; `tests/test_admission.py`, `tests/test_local_admission_runtime.py`.

## Decision

**Three modes** (`HUTCH_MODE` / `hutch mode set`, stored in `kv`, shown in the UI header):

| Mode | Inference | Tools / network | Enforcement |
|---|---|---|---|
| `offline` | local only | no outbound internet: `web_fetch`, browser `goto` to non-local hosts, remote connections, update checks, model downloads all refused; MCP/remote integrations disabled | provider factory refuses non-loopback endpoints and any Ollama server with cloud enabled or a cloud-tagged model; `netguard` refuses non-loopback targets; sandbox runs with `--unshare-net`; test asserts zero non-loopback `connect()` calls |
| `local+tools` | local only | authorised tools and integrations may send data; each is shown as "data leaves this machine" | inference route check as above; tool network grants honoured |
| `hybrid` | cloud routes explicitly enabled | normal | spend and data-movement notices per route |

"localhost" is not proof of local inference. These mode checks are a target, not implemented
guarantees. The [Ollama FAQ](https://docs.ollama.com/faq) documents cloud disabling in the server's
configuration or `OLLAMA_NO_CLOUD=1` and requires a restart. Setting a flag only in Hutch does
not prove the serving process inherited it. Offline admission must establish the actual backend,
model and enforced egress; unknown provenance must refuse. A loopback URL or model label alone
cannot satisfy that check.

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
Browser/battery-aware admission, pressure-driven unloading and mode/provenance enforcement remain
pending. Runtime keep-alive still follows the bot preset; unsafe environment slot widening is removed.

## Consequences

Cost: native fit checks probe current hardware and query model metadata/residency. Live latency is
unmeasured. Hardware/footprint signals have the limits above; this is no hard resource guarantee.
Rollback restores a verified release and compatible database while preserving admission protections;
it does not disable enforcement or silently enable hosted routes.
