# Failure mining: local models and offline claims (2026-11)

Phase 0 mining. Each row is one failure class, the primary source that establishes it (or
"observed" for this host's own reproduction), the class in the research plan's taxonomy,
who can fix it, what Hutch should do, and the test idea that would prove the response on a
real runtime. Search snippets that were not opened are listed separately as leads and are
not used to assert anything below.

## Failure classes

| ID | Complaint | Source (read 2026-11-06) | Class | Who can fix | Hutch response | Test idea |
|---|---|---|---|---|---|---|
| F1 | A cloud model served through loopback Ollama is treated as local: the client sees `localhost:11434`, Ollama forwards to ollama.com, and the user gets no consent. `/api/tags` already carries `remote_host` and `remote_model`. | https://github.com/IncarnaMind/IncarnaMind/issues/174 | integration/protocol | Hutch | **Fix.** Classify by the server signal first (`/api/tags.remote_host` / `remote_model`), name suffix only as fallback; label it everywhere; refuse it in local/offline mode; require an explicit data-sharing confirmation. | Real Ollama with `gpt-oss:20b-cloud` and with a `FROM`-copy renamed `my-local-copy`: `/api/tags` says `remote_host`; Hutch must show it as cloud and refuse it under Strict Offline. |
| F2 | The same client bug also hides the model from the privacy settings page and from local-mode refusal, because the location decision is made from the endpoint URL. | https://github.com/IncarnaMind/IncarnaMind/issues/174 | integration/protocol | Hutch | **Fix.** Make locality a property of the route *and model*, resolved once at connect time, with one classifier used by pricing, routing, UI and approvals. | A unit test per call site plus the real stack in F1; one classifier must decide them all. |
| F3 | `llama-server --jinja` returns a tool-call id that its own chat template then rejects when the client echoes it back, so a two-turn tool conversation fails with HTTP 400 before the model is reached. | https://github.com/ggml-org/llama.cpp/issues/26359 | integration/protocol (model-specific trigger) | llama.cpp, mitigated by Hutch | **Mitigate + disclose.** Repair or regenerate non-conforming ids in the tool-call path; record the model/template pair when repair fires; never promise tool reliability by model name. | Real llama.cpp with a template that validates ids (Mistral family) and a two-turn tool exchange; capture the 400 before the fix and the repaired call after. |
| F4 | Disk exhaustion during model creation or pull: conversion needs the archive, the working files and the final GGUF at once, and the error arrives after the transfer. | https://github.com/ollama/ollama/issues/6628 | configuration/hardware | Ollama, mitigated by Hutch | **Fix.** Preflight free space on the runtime's own model directory (ask the runtime / read `OLLAMA_MODELS`), show size and time before the button, and keep partial state honest. | A small loopback filesystem filled mid-pull; the page must say "not enough space" before the download, and the job must survive a reload. |
| F5 | Context overflow policy is a load-time or per-request choice, and `truncateMiddle` deliberately keeps the system prompt and first user message while dropping the middle. A client that does not read the policy silently loses history. | https://lmstudio.ai/docs/typescript/api-reference/llm-prediction-config-input | integration/protocol | Hutch, LM Studio | **Fix.** Read the applied window and the overflow policy; for agent runs refuse a truncating policy it cannot compensate for; compact explicitly before overflow. | Real LM Studio with `truncateMiddle` on and off; a needle in the middle of the history must be either preserved or the run refused with words. |
| F6 | JIT-loaded models are unloaded after an idle TTL (60 min default) and auto-evict removes the previous model when a new one loads. A scheduled bot wakes to a cold or evicted model. | https://lmstudio.ai/docs/developer/core/ttl-and-auto-evict | configuration | Hutch | **Fix.** Read `remaining_ttl_seconds`, show cold-start as a state, and treat eviction as a normal lifecycle event with one reload attempt. | Real LM Studio with a short `ttl`, wait for expiry, run a scheduled turn: state `loading` with measured time, not a timeout. |
| F7 | A stock `llama-server` listens on **9931**, not 8080; Hutch's fixed discovery list never sees it. `/health` is public and returns 503 while loading. | https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md and the running b12144 server | integration/protocol | Hutch | **Fix.** Fingerprint and probe the runtime's real default plus configured ports; use `/health` 503 as `loading`, not failure. | Start `llama-server` with no `--port`; Hutch must find it and show `loading` then `ready`. |
| F8 | A key-protected server looks dead: `/v1/models` answers 401, `/health` still answers 200, and a client that sends no credential can only report "no service answered". | Observed on `llama-server --api-key` b12144; https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md | integration/protocol | Hutch | **Fix.** Distinguish 401/403 from unreachable; show `needs_key`; store the key in the vault; send it only to that origin and never in the URL. | Real `--api-key` server: state `needs_key`, then a saved key completes a turn; the key never appears in logs or responses. |
| F9 | Ollama's default context is 4096 (VRAM-derived), and `OLLAMA_NUM_PARALLEL` multiplies the context and memory. A client that trusts the headline window can overflow or over-allocate. | https://docs.ollama.com/faq | configuration | Ollama, mitigated by Hutch | **Keep** the existing `num_ctx` discipline; read back `context_length` and `size_vram` from `/api/ps`; state the per-slot window when parallel is on. | Real Ollama: request 2048 and read `/api/ps.context_length`; start with `OLLAMA_NUM_PARALLEL=2` and show the multiplied footprint. |
| F10 | A reasoning model can spend the entire output budget thinking and return an empty answer with `finish_reason: "length"`. | Observed on LM Studio qwen3-4b: 64 completion tokens, 64 reasoning tokens, empty content | model-specific + integration | Hutch, model authors | **Mitigate + disclose.** Treat `length` with empty content as a distinct state, show the reasoning token count, and do not present it as an empty reply. | Real local thinking model with a small `max_tokens`; the UI names the state and the budget. |
| F11 | Context shift can loop or discard the system prompt; it is disabled by default in current llama.cpp, but a user's launch flags can enable it. | https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md (default disabled) | integration/protocol | Hutch | **Detect or refuse** for agent runs when the server reports a shifting policy; never let it drop tool definitions silently. | Real server with `--context-shift`; a needle in the system prompt must survive or the run must refuse. |

## Register: R14 onwards

Continues the R-numbering in `docs/realignment/offline-models-2026-10-31.md` (which ends at
R13). Each entry records what was taken, not the vendor's wording.

| ID | Source (accessed 2026-11-06) | Fact taken | Decision it changed |
|---|---|---|---|
| R14 | https://docs.ollama.com/faq | Default context is 4096; `OLLAMA_CONTEXT_LENGTH` overrides it; `OLLAMA_NO_CLOUD=1` or `disable_ollama_cloud` turns cloud off; `OLLAMA_NUM_PARALLEL` multiplies context and memory; keep-alive default 5 minutes; `OLLAMA_MAX_LOADED_MODELS` defaults to 3 on CPU | Phase 1 must read the server's own cloud state where it can and never infer it from `OLLAMA_HOST`; Phase 2 must report the per-slot window |
| R15 | https://github.com/IncarnaMind/IncarnaMind/issues/174 | A real project shipped the same bug: loopback URL implies local, cloud model passes into local mode, no consent, picker says "on this computer"; the fix was `remote_host` / `remote_model` first, suffix fallback | Confirms the Phase 1 design and supplies the test shape; also confirms the name suffix alone is insufficient |
| R16 | https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md | Stock port 9931; `/health` 503 while loading; `/props` carries `n_ctx`, `total_slots`, `chat_template_caps`, `modalities`; `/slots` carries per-slot `n_ctx`; `--jinja` on by default; `--context-shift` off by default; `--offline`; `--api-key`; `--parallel` auto; `--models-max` 4; `--kv-unified-per-slot` | Phase 2's adapter design and the discovery fix; Phase 3's loading state |
| R17 | https://lmstudio.ai/docs/developer/rest/list and https://lmstudio.ai/docs/developer/core/ttl-and-auto-evict | `/api/v1/models` fields (`capabilities.vision`, `trained_for_tool_use`, `reasoning`, `max_context_length`, `loaded_instances[].config.context_length`, `remaining_ttl_seconds`); JIT default on; TTL 60 min default; auto-evict default on; API tokens optional | Phase 2 reads LM Studio natively; Phase 3 treats TTL expiry as a state |
| R18 | https://github.com/ggml-org/llama.cpp/issues/26359 | A returned tool-call id can violate the model's own template and be rejected on the next turn; the issue was closed as stale, and the reporter says the class is live | Phase 5 adds an id-repair test and does not blame the model |
| R19 | https://github.com/ollama/ollama/issues/6628 | Conversion can need archive, working files and final GGUF at once; the error arrives after the transfer; `OLLAMA_MODELS` moves the store | Phase 4 preflight must query the runtime's store, not Hutch's disk |
| R20 | https://lmstudio.ai/docs/typescript/api-reference/llm-prediction-config-input | `stopAtLimit` vs `truncateMiddle` are explicit policies; `truncateMiddle` keeps the system prompt and first user message | Phase 2 must read the policy; Phase 7 must not imply history is safe |
| R21 | Observed on this host (llama.cpp b12144 Vulkan build) | Vulkan lists the integrated AMD GPU while Ollama drops it unless `OLLAMA_IGPU_ENABLE=1` | EC-21 wording: report the runtime and build, never a blanket "CPU only" |
| R22 | https://github.com/1ay1/agentty/issues/49 | An app showed LM Studio's `max_context_length` as the context in use while `/api/v1/models` reported the applied `loaded_instances[].config.context_length` | Phase 2 reads the applied window, never the trained maximum; the choice note and EC-05 test use the applied value |
| R23 | https://github.com/ggml-org/llama.cpp/discussions/4130 | `--parallel N` divides the KV budget when the cache is not unified; the headline `-c` is not one request's window | Phase 2 reads `/slots[].n_ctx` and shows the slot count; never derives the per-request window from `-c` alone |
| R24 | https://github.com/ggml-org/llama.cpp/issues/16693 | Prompt truncation and context shift were removed for `/v1/chat/completions` (commit d00cbea); an over-long prompt now errors instead of shifting. A maintainer's log shows `-c 32768 -np 2` producing 16384-token slots | Phase 2 refuses an over-long prompt before sending and records the server's own over-long error; it does not claim to change a llama.cpp window per request |
| R25 | https://lmstudio.ai/docs/developer/core/authentication | API tokens are off by default and required on every REST/SDK request once enabled | Phase 2 maps 401/403 to `needs_key`, stores the key in a connection key file, and sends it only to that origin |
| R26 | https://github.com/mostlygeek/llama-swap/issues/146 | A chat request during llama.cpp startup returns 503 "Loading model"; a client that treats it as a hard failure reports a broken server. `/v1/models` answers before readiness. | Phase 3 reads `/health`, shows a loading state with measured time, and does not fall back on the first 503. |
| R27 | https://github.com/ggml-org/llama.cpp/issues/20137 | Router mode `--models-max` can be exceeded under concurrent requests. | Phase 3 re-reads model state before every request and handles a vanished model with one reload. |
| R28 | https://github.com/ggml-org/llama.cpp/discussions/18939 | Router mode does not unload automatically without a limit; a model serving requests is never unloaded. | Phase 3 never assumes its model stays resident and labels eviction/removal as a state. |
| R29 | https://github.com/ollama/ollama/issues/10532 and https://github.com/ollama/ollama/issues/6238 | An OOM-killed Ollama runner reports `llama runner process has terminated: signal: killed`; the wrapper hides the cause. | Phase 3 maps killed/out-of-memory text to `oom` with a smaller-model or smaller-window fix and retains partial text as incomplete. |
| R30 | https://lmstudio.ai/docs/developer/core/ttl-and-auto-evict and https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/644 | JIT models expire after the TTL; auto-evict unloads the previous JIT model; clients that assume residency hit cold starts. | Phase 3 reads `loaded_instances` and reloads with the fitted window, measured. |
| R31 | https://lmstudio.ai/docs/developer/rest/load and https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/1217 | Loading is separate from server readiness; a cold model loads just in time. | Phase 3 loads cold LM Studio routes explicitly with the fitted window and times the load. |
| R32 | Ollama v0.3.0, v0.5.0, v0.9.0, v0.10.0 release notes; LM Studio API changelog | Feature minimums: Ollama tools 0.3.0, structured outputs 0.5.0, thinking 0.9.0, `/api/ps` context 0.10.0; LM Studio tools 0.3.6, TTL 0.3.9, native `/api/v1` and tokens 0.4.0. llama.cpp publishes no feature matrix; the build string and field presence are the facts. | Phase 3 gates claims by version, records the build, and says "upgrade X to Y for Z". |

## Leads not opened (recorded, not asserted)

- Open WebUI context-length discussion: https://github.com/open-webui/open-webui/discussions/4246
  and issue https://github.com/open-webui/open-webui/issues/4245 (proposals to grow
  `num_ctx` or warn on truncation).
- Jan context-shift report: https://github.com/janhq/jan/issues/5660.
- Ollama cloud data-retention thread: issue #14279 (seeded in the research plan, page not
  opened in this pass).
- llama.cpp context-shift loop: https://github.com/ggml-org/llama.cpp/issues/3969.

These are useful for Phase 7's competitor survey; no claim in this package depends on them.

## What this does to the Phase 0 backlog

Order by user harm, as the master prompt requires:

1. **Privacy, silent wrong behavior:** G2/F1/F2 (cloud routes presented as local), F8
   (key-protected looks dead), F4/F5/F6 (silent truncation, eviction), G7 (port trust).
2. **Missing capability:** G1 (name grammar), G3/G4 (only Ollama has first-class local
   models and introspection), G6 (no preflight, no real pull evidence).
3. **Trust evidence:** G5 (Strict Offline has no live run).
4. **Polish:** duplicate state vocabulary, non-Ollama entries, onboarding copy.

Phase 0 decisions recorded: the sibling package keeps hosted providers; this package owns
Ollama, llama.cpp, LM Studio, vLLM and SGLang (as stated in `02-PROGRESS.md`).
