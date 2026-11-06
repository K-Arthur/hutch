# Phase 3 research: lifecycle states, error mapping and version drift

Accessed 2026-11-06. Scope: EC-09 (cold start), EC-10 (eviction), EC-11 (version drift),
EC-22 (memory pressure). Primary pages read in full where they bear on a task; search results
are listed only when they led to a primary page.

## Loading and readiness

| Fact | Source | Decision it changed |
|---|---|---|
| `GET /health` returns 503 with `{"error":{"code":503,"message":"Loading model","type":"unavailable_error"}}` while the model loads and 200 `{"status":"ok"}` when ready. `/health` and `/v1/health` are public even with `--api-key`. | https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md (2026-11-06) | Readiness comes from `/health`, not `/v1/models`. `/v1/models` answers before the model is ready and returns `meta: null` while loading. Hutch waits on `/health` and measures the wait. |
| A client that treats the 503 as a hard error fails while the model is merely loading; the llama-swap maintainer's fix was to hold the request until `/health` passes. | https://github.com/mostlygeek/llama-swap/issues/146 (2026-11-06) | A 503 is a `loading` state with a first-token wait, never a generic server error and never a fallback trigger on the first occurrence. |
| Router mode reports per-model `status.value`: `unloaded`, `loading`, `loaded`, `sleeping`, `downloading`, `incomplete`; a failed child carries `failed: true` and `exit_code`. `GET /props` carries `is_sleeping`. | llama.cpp server README, "Using multiple models" and "Sleeping on Idle" (2026-11-06) | An evicted or sleeping model is a named state Hutch can read before sending. A model that is not loaded is reloaded once (visible, measured), then the request is sent. |
| `--sleep-idle-seconds` unloads the model and KV cache; any new task reloads it. `/health`, `/props`, `/models`, `/metrics` do not reset the idle timer. | same README | A sleeping model is not "down". Hutch says it will reload and measures the load. |
| `--models-max` is a router limit (default 4, 0 unlimited) with LRU eviction; `--models-memory-margin` unloads idle LRU models until a new one fits, and a model serving requests is never unloaded. A reported race can exceed `--models-max` under concurrent requests. | README plus https://github.com/ggml-org/llama.cpp/issues/20137 (2026-11-06) | Hutch must handle "the model it used is gone" at any turn boundary, not assume its own turns keep it resident. Pre-call state is re-read before every request. |
| `-to/--timeout` defaults to 3600 s; `--sse-ping-interval` defaults to 30 s and keeps a silent stream observable. | README | A long CPU prompt is not a timeout. Hutch's first-token timeout stays longer than the measured load and the client does not need to invent one. |
| LM Studio JIT loads on the first request; idle TTL defaults to 60 minutes and resets on every request; Auto-Evict (default on) keeps at most one JIT model, unloading the previous one before loading the next. Non-JIT loaded models are unaffected by auto-evict. A per-request `ttl` exists. | https://lmstudio.ai/docs/developer/core/ttl-and-auto-evict (2026-11-06) | A model can disappear between turns. Hutch checks `loaded_instances` before a turn and reloads with the fitted window; it never assumes the previous turn's model is still resident. |
| LM Studio's model list reports `loaded_instances[].config.context_length`; earlier research (R17) recorded `remaining_ttl_seconds` on a live instance. | https://lmstudio.ai/docs/developer/rest/list (2026-11-06), live capture R17 | Eviction is detected from the absence of `loaded_instances`, not from a guessed TTL. `remaining_ttl_seconds` is presented only when the server reports it. |
| Ollama keep-alive defaults to 5 minutes; `OLLAMA_MAX_LOADED_MODELS` defaults to 3 on CPU; `OLLAMA_NUM_PARALLEL` multiplies context and memory. `/api/ps` reports `expires_at`. | https://docs.ollama.com/faq (2026-11-06, R14) | An expired model is a cold load, not an error. Hutch keeps its existing preload/measure path and treats an expired model as loading. |
| An OOM-killed Ollama runner surfaces as `llama runner process has terminated: signal: killed` (or `error while loading model: ...`); the wrapper text hides the cause. | https://github.com/ollama/ollama/issues/10532 and https://github.com/ollama/ollama/issues/6238 (2026-11-06) | Map "killed"/"out of memory"/"unable to allocate" to `oom` with a smaller-model/smaller-window next step. Never a generic stream error. |
| A server restart or runner death mid-stream breaks the connection; llama.cpp returns OAI-format errors (`{"error":{"code":...,"message":...,"type":...}}`). | README "API errors" (2026-11-06) | A broken stream with no output is classified as `stream`; the run stops with the cause and the next step rather than silently retrying after partial text. |

## Version drift

| Runtime feature | Minimum version | Source | Decision |
|---|---|---|---|
| Ollama `think` (and `message.thinking`) | 0.9.0 | https://github.com/ollama/ollama/releases/tag/v0.9.0 (2026-11-06) | Gate the thinking claim and tell the user to upgrade below it. |
| Ollama `format` JSON schema (structured outputs) | 0.5.0 | https://github.com/ollama/ollama/releases/tag/v0.5.0 and https://ollama.com/blog/structured-outputs (2026-11-06) | Gate the constrained-output claim. |
| Ollama `tools` on `/api/chat` | 0.3.0 | https://github.com/ollama/ollama/releases/tag/v0.3.0 (2026-11-06) | Gate tool calling. |
| Ollama `/api/ps` reports `context_length` | 0.10.0 | https://github.com/ollama/ollama/releases/tag/v0.10.0 (2026-11-06) | Below that, the measured window is unknown, not the requested one. |
| LM Studio native `/api/v1/*` and API tokens | 0.4.0 | https://lmstudio.ai/docs/developer/api-changelog (2026-11-06) | Native introspection and `needs_key` require 0.4.0. An older server falls back to OpenAI-compatible and is labelled `unknown`. |
| LM Studio tool calling | 0.3.6 | same changelog | Gate the tool claim. |
| LM Studio idle TTL / auto-evict | 0.3.9 | same changelog | Below it, no eviction state is claimed. |
| llama.cpp `/props`, `/slots`, `/health`, `build_info` | No public feature matrix. The build string `b<number>-<commit>` is the only version fact. `chat_template_caps` is present in the tested build and is the authoritative tool signal. | README (2026-11-06); live `/props` (R16) | Gate by field presence, not by build number. Record `build_info` per route and show it. Never infer a feature from a guessed build floor. |

## Failure and complaint classes (R26-R32)

| ID | Complaint / failure | Source | Class | Hutch response | Test idea |
|---|---|---|---|---|---|
| R26 | A chat request during llama.cpp startup returns 503 "Loading model"; clients report it as a broken server. | llama-swap #146 | integration/protocol | Fix: wait on `/health`, show loading with measured time. | Real llama-server with a real GGUF: request at t=0 while loading, assert `loading` state and eventual success. |
| R27 | `--models-max` can be exceeded under concurrent requests; a loaded model can disappear between turns. | llama.cpp #20137 | integration/protocol | Mitigate: re-read the model state before every request; reload once. | Real router or single server: unload/restart between turns, assert one reload and a successful next turn. |
| R28 | Router mode never unloads automatically without `--models-max` or `--models-memory-margin`; a model serving requests is not unloaded. | llama.cpp discussion #18939 | configuration | Disclose: Hutch does not assume its model stays resident; state is read, never inferred from the port. | Real router: unload a model through `/models/unload`, assert reload. |
| R29 | Ollama runner killed by the OOM killer mid-generation; the API text is `llama runner process has terminated: signal: killed`. | ollama #10532, #6238 | hardware | Fix: map to `oom` with a smaller-model/window fix; retain any partial text as incomplete. | Real kill -9 of the runner mid-stream; assert `oom` state and no silent retry. |
| R30 | LM Studio JIT/TTL/auto-evict can unload a model between requests; older apps show a timeout. | LM Studio docs; lmstudio-bug-tracker #644 | configuration/frontend | Fix: read `loaded_instances`; reload with the fitted window, measured. | Real LM Studio: unload through `/api/v1/models/unload`, run a turn, assert reload and answer. |
| R31 | LM Studio's JIT load is separate from server readiness; a client can call chat before a model is loaded. | lmstudio-bug-tracker #1217 (lead), docs | integration/protocol | Fix: explicit `/api/v1/models/load` for cold routes, with the fitted window; time it. | Real LM Studio cold load: assert measured load, applied window. |
| R32 | Version drift: a capability profile cached for one build is wrong for the next; older Ollama lacks `think`, structured outputs or tool calls. | Ollama release notes; LM Studio changelog | configuration | Gate by minimum version and say "upgrade X to Y for Z"; llama.cpp gates by field presence and records the build. | Unit: version parse/compare table; live: real 0.40.13 shows all gates pass. |

## Not run / limits

- No LM Studio version is exposed over HTTP (`/api/v1/models` has no app version field). Hutch records the
  native API presence (which implies 0.4.0 or newer) and does not invent a version.
- CUDA/ROCm/Metal OOM behaviour cannot be produced on this CPU-only host; the Linux OOM-kill path is
  exercised for real.
- vLLM and SGLang are not installed; their state surface stays `unknown`.
