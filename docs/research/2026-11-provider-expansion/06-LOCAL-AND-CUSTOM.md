# 06 - Local engines and custom endpoints (Phase 5, 2026-11-06)

Scope: Ollama, LM Studio, vLLM, SGLang, inferrs, ds4, llama.cpp and custom OpenAI/Anthropic-compatible
endpoints. This phase extends, and does not repeat, `docs/research/2026-11-offline-models/` (native
introspection, cold load, context admission, Ollama residency), which already ships for loopback engines.

## What the diagnosis found (real LM Studio, llmster 0.0.27-1, loopback :1234, 2026-11-06)

| ID | Observation | Class |
|---|---|---|
| L1 | `custom-openai` at `https://169.254.169.254/v1` is accepted; `connections test` ends "did not respond in time". The only barrier is the http-only-for-loopback rule, so the same address over https passes. | fixable |
| L2 | `bot.base_url` / `OLLAMA_HOST` / `HUTCH_BASE_URL` routes (`make_provider`) accept any URL: plain HTTP to a public host, link-local, metadata. Only embedded credentials are refused. | fixable |
| L3 | A hostname is never judged by what it resolves to at request time. A public-looking name that resolves to loopback/private is trusted (DNS rebinding). | fixable |
| L4 | `https://127.0.0.1:1234/v1` against a plain-HTTP server reports "cannot connect ... is the server running?" The server is running; the wrong layer is named. | fixable |
| L5 | `http://127.0.0.1:1234` (no `/v1`) and `.../v1/chat/completions` (pasted full path) report "returned an invalid model catalog" with no hint. | fixable |
| L6 | vLLM and SGLang return `max_model_len` on every `/v1/models` entry. Hutch parses it (`openai_generic._parse`) but its docstring says the field "is a server launch argument" and admission reports the window as unknown. The prior note was wrong. | fixable |
| L7 | A key is sent over plain HTTP to any host a bot's `base_url` names (`HUTCH_API_KEY`). | fixable |
| L8 | Ollama behind a custom `/v1` URL cannot have its context set per request (Ollama docs); nothing flags it. `looks_like_ollama` only matches the default port. | mitigable |

## Sources (accessed 2026-11-06)

| Source | Fact taken | Changed |
|---|---|---|
| https://docs.vllm.ai/en/v0.15.0/api/vllm/entrypoints/openai/engine/protocol/ and the v0.10.1 `protocol` page | `ModelCard`: `id`, `object`, `created`, `owned_by="vllm"`, `root`, `parent`, `max_model_len: int or None`, `permission`. | L6: `max_model_len` is the served per-request window. |
| https://raw.githubusercontent.com/sgl-project/sglang/main/python/sglang/srt/entrypoints/openai/protocol.py | `ModelCard(id, object, created, owned_by="sglang", root, parent, max_model_len: Optional[int])`. | L6 for SGLang; `owned_by` is the identity signal. |
| https://docs.vllm.ai/en/latest/serving/online_serving/openai_compatible_server/ | `--api-key` / `VLLM_API_KEY` authenticates only the `/v1`, `/v2`, `/inference`, `/cohere` prefixes; `/invocations` is unprotected. | A 401/403 on `/v1/models` is the auth layer, not a dead server. |
| https://github.com/vllm-project/vllm/issues/9986 and https://docs.vllm.ai/en/stable/features/tool_calling/ | `"auto" tool choice requires --enable-auto-tool-choice and --tool-call-parser to be set` is a 400 from a server started without those flags; `/v1/models` gives no sign of it. | Recorded vendor-side; the 400 text is already shown verbatim as a bad request. No Hutch rule. |
| https://docs.sglang.io/docs/basic_usage/native_api | `/health`, `/health_generate`, `/get_model_info`, `/server_info`; the doc does not state `--api-key` coverage or `context_length` in `/get_model_info`. | Do not rely on SGLang native endpoints; `/v1/models` is the only window source. |
| https://docs.ollama.com/context-length | Default context is 4k under 24 GiB VRAM, 32k for 24-48 GiB, 256k above; `ollama ps` shows the allocated length. | L8 warning text. |
| https://docs.ollama.com/api/openai-compatibility | "The OpenAI API does not have a way of setting the context size for a model"; `tool_choice` is unsupported. | L8: identify Ollama behind `/v1`, advise the native route. |
| https://docs.openclaw.ai/concepts/model-providers/custom-providers | Exact-origin trust for the configured `scheme://host:port`; fake-IP answers (198.18.0.0/15) allowed only for the configured hostname; metadata, link-local and NAT64 need explicit opt-in; `auth: none` automatic only for loopback/RFC1918. Feature checklist only. | Policy shape: the configured host is the allowlist entry; 198.18/15 is its own class. |
| https://github.com/eohmig/openclaw_reference/blob/main/docs/providers/inferrs.md (mirror; the live OpenClaw `inferrs` URL returned another provider's page twice) | inferrs: OpenAI-compatible, `http://127.0.0.1:8080/v1`, `inferrs serve <hf-id> --host --port`, may need `requiresStringContent`, readiness `/health` + `/v1/models`; small calls pass and agent turns crash. | No dedicated code. Reachable through the generic OpenAI-compatible route; unverified. |
| https://docs.openclaw.ai/providers/ds4 | ds4 serves DeepSeek V4 Flash on Metal (macOS), `http://127.0.0.1:18000/v1`, `--ctx`; a context below 32768 fails agent turns with `500 prompt exceeds context`. | No Linux engine, so not runnable here. Stays `documented`. |
| https://github.com/cline/cline/pull/15086 and issue 15056 | Clients that silently append `/v1` break root-served APIs; Cline retries a host-only 404 under `/v1` and tells the user. | Suggest, never rewrite silently. |
| https://github.com/open-webui/open-webui/discussions/12118 | A trailing slash produced `GET /v1//models` 404. | Normalise trailing slashes at save. |
| https://www.nccgroup.com/research/technical-advisory-ollama-dns-rebinding-attack-cve-2024-28224/ | DNS rebinding reached a local Ollama API from a web page. | Why the resolved address, not the spelling, decides (L3). |

Search found no advisory for "SSRF via a custom `api_base`" in LiteLLM or Open WebUI in this pass; that part of
the failure mining is unconfirmed rather than absent.

## Decisions

1. One policy module decides on addresses, not spellings (reusing `netguard.blocked_ip_reason` and
   `netguard._literal_ip`), and the connection is pinned to the validated address. The single seam is
   `offline.httpx_offline_options`, which every httpx adapter already calls, so no adapter call site changes.
2. Kinds: `loopback`, `private` (RFC1918, ULA, CGNAT/tailnet), `fake_ip` (198.18.0.0/15), `public`, `blocked`
   (link-local incl. cloud metadata, unspecified, multicast, reserved). `blocked` is refused for every scheme.
3. A name may resolve to loopback/private only if it is a local-style name (`localhost`, no dot, `.local`, `.lan`,
   `.home.arpa`, `.internal`, `.localdomain`, `.ts.net`) or is listed in `HUTCH_PRIVATE_HOSTS`. Any other name
   must resolve to public (or fake-IP). The refusal names the exact fix.
4. Vendor hosts that a connection template declares are exempt from the name rule (split-horizon DNS for a vendor
   is the operator's choice) but not from `blocked`.
5. Plain HTTP only to a loopback or private address; a key is never sent over plain HTTP off loopback.
6. The connectivity test is layered (address policy, DNS, connect, TLS, auth, model list). The completion layer is
   not run by `connections test`; it stays the explicit "test with one token" action.
7. vLLM and SGLang report their window from `max_model_len` only when `owned_by` identifies them. Other
   OpenAI-compatible servers stay "unknown".

## Deferred (reason)

- Keyless named connections: the keyless local route already exists as `vllm/<model>` or `openai-compatible/<model>`
  with the bot's `base_url`; that route is now guarded. A new auth mode touches frozen `connections.py`, the CLI and
  the dashboard API and is not needed for safety.
- Self-signed TLS: Hutch keeps verification on; `SSL_CERT_FILE` is honored. No "skip verification" switch.
- inferrs, ds4 templates: no engine to verify (ds4 is macOS-only). Not added.
- Anthropic SDK client (custom Anthropic endpoints) is guarded only if the SDK accepts an injected transport; see
  the ledger.
- Strict Offline is unchanged: it already requires loopback and goes through the broker.

## Results (2026-11-06)

Commits: `c1003d35` address policy; `02cc1416` pinned transport and the single seam; `d5f027de` save-time refusal and
pasted-path clean-up; `15894273` layered test through `check_connection`; `46666e1d` vLLM/SGLang window; `c62043f9`
Anthropic precheck; `8b9ec5b9`, `8f5361b8` wording and the key-verification under-claim.

Real stack (isolated `HUTCH_STATE_DIR`, `hutch init`, `hutch serve --port 18893`, LM Studio 0.0.27-1 on loopback
:1234 with six local GGUF models, a real Ollama 0.40.13 on :11434 started by another session and touched with GET
only):

| Check | Result |
|---|---|
| `connections test` against `http://127.0.0.1:1234/v1` | 6 models listed; reported as answered, key not verified. |
| Same server saved without `/v1` | `models layer: .../models answered HTTP 200, not a model list. The same server lists its models under .../v1/models: set the endpoint to .../v1`. |
| `https://` on the plain-HTTP port | `tls layer: 127.0.0.1's port is up but speaks plain HTTP, not TLS: use http:// in the endpoint` (was "is the server running?"). |
| Closed port | `connect layer: nothing is listening on 127.0.0.1:1 (connection refused)`. |
| `https://169.254.169.254/v1` as a connection | refused at save in words, no socket opened. |
| Bot route `openai-compatible/x` at `http://169.254.169.254/v1` | `hutch run` fails with the blocked-address sentence; `steps=0`. |
| Cold `lmstudio/qwen3-0.6b` through `hutch run` | `lms ps` showed nothing loaded; the run succeeded and the model sat loaded at CONTEXT 16384 (the offline-models lifecycle, re-exercised). |
| Named custom connection `lms/qwen3-0.6b` through `hutch run` (streaming through the pinned transport) | succeeded. |
| Custom connection to Ollama's `/v1` | 12 models listed; `Note: This is an Ollama server behind its OpenAI-compatible /v1 endpoint...` from the real `/api/version` answer. |
| Models page, five outcomes at 360/768/1280/1920 | 20/20 captures, 0 console errors, 0 failed requests, 0 px overflow (`docs/realignment/artifacts/provider-expansion-2026-11/phase5/`). Cropped views inspected: the layered sentences wrap cleanly. |

Real TLS, not a mock: `tests/test_endpoint_probe.py` serves a real self-signed certificate (made by the openssl CLI),
sees it refused with the `SSL_CERT_FILE` fix, and sees it trusted once that variable names the certificate.

Defects found and fixed in this phase:

- The first probe wording said "set the endpoint to that" while pointing at `/v1/models`; now names the root.
- A literal blocked address read "'169.254.169.254' resolves to 169.254.169.254"; now says the address is blocked.
- A custom endpoint's test said "authenticated" for servers that ignore keys (Ollama, LM Studio without a token);
  now "the server answered ... the key itself was NOT verified".
- The Anthropic SDK in this environment is built on a vendored `httpx2`, so an httpx transport cannot be injected;
  the first attempt broke nine existing Claude tests and was replaced by a precheck.
- An existing test pinned "the key goes out exactly once"; the keyless identification GET kept that property, and
  the assertion now filters to key-bearing requests (intent unchanged).

Defect for Phase 7 (not changed here): a long flash notice renders as a heavy bold paragraph at 360 px.

Not run, and why:

| Item | Reason |
|---|---|
| vLLM, SGLang | Not installed; a Python dependency and a large download need the owner's approval, and the host has no GPU. The `max_model_len` reading is proven against the documented shape by stand-in servers only. |
| inferrs, ds4 | No engine; ds4 is Metal-only. Not templated. |
| A private LAN address over real sockets | No LAN peer. Forwarding LM Studio to the host's LAN address was declined by the permission guard, and was not worked around. The private-kind and clear-text rules are covered by real loopback sockets plus a resolver that answers private addresses. |
| DNS rebinding against a real resolver | A resolver cannot be told to rebind on demand; injected resolver answers are the only failure injection used. |
| An environment proxy in front of a model endpoint | Proxied connections are not pinned; only the literal rule is tested. |
| `HUTCH_PRIVATE_HOSTS` through the dashboard | Set through the environment only; no UI. |
| Light theme, keyboard traversal | No markup changed (text of an existing notice only); the workspace theme is dark-only (G16). |

