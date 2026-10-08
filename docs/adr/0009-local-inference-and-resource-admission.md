# ADR-0009: Operating modes, offline guarantees, and resource admission

Status: accepted (2026-10-07). Slice: S5. Evidence: baseline lead 6, B8, A3.

## Decision

**Three modes** (`HUTCH_MODE` / `hutch mode set`, stored in `kv`, shown in the UI header):

| Mode | Inference | Tools / network | Enforcement |
|---|---|---|---|
| `offline` | local only | no outbound internet: `web_fetch`, browser `goto` to non-local hosts, remote connections, update checks, model downloads all refused; MCP/remote integrations disabled | provider factory refuses non-loopback endpoints and any Ollama server with cloud enabled or a cloud-tagged model; `netguard` refuses non-loopback targets; sandbox runs with `--unshare-net`; test asserts zero non-loopback `connect()` calls |
| `local+tools` | local only | authorised tools and integrations may send data; each is shown as "data leaves this machine" | inference route check as above; tool network grants honoured |
| `hybrid` | cloud routes explicitly enabled | normal | spend and data-movement notices per route |

"localhost" is not proof of local inference. The check asks Ollama (`/api/tags`, `/api/show`) and its server config; a model whose
details show a remote/cloud backend, or a server with `OLLAMA_NO_CLOUD` unset **and** a cloud model requested, fails the offline check (B8).
When Hutch cannot determine it, offline mode refuses with the reason (fail closed).

**Resource admission** (`hutch/admission.py`): a run asks for `(model, est_ctx, needs_browser)` before it takes a model slot. Inputs: free
RAM/VRAM from the existing hardware probe (not the model file size alone: KV cache = f(context, parallel), browser ~300-500 MB, battery state).
Outputs: `admit`, `wait` (`waiting_resources` with a stated reason), or `refuse` (does not fit). Local inference is serial by default
(`OLLAMA_NUM_PARALLEL=1` semantics) with a bounded queue (default 8, then refuse with "queue saturated"); keep-alive follows the bot's preset and
unloads under memory pressure. **A run waiting for approval or a human releases its model slot** and re-admits afterwards.

## Consequences

Cost: probing on the hot path is cached for 5 s. Honest limit: Hutch cannot see another process's GPU use beyond what the probe reports. Rollback: `HUTCH_MODE=hybrid` and admission `warn` instead of `wait`.
