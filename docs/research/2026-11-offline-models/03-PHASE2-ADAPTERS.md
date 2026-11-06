# Phase 2 research: native runtime introspection (2026-11-06)

Narrow pass for Phase 2 only. Phase 0's `02-RUNTIME-API-NOTES.md` remains the source for the
fields already observed on this host; this note records what Phase 2 needed beyond it, with
the primary page read for each claim. Search snippets were treated as leads only.

## Sources and decisions

| # | Source (accessed 2026-11-06) | Fact taken | Class | Decision it changed |
|---|---|---|---|---|
| P2-1 | https://lmstudio.ai/docs/developer/rest/list | `GET /api/v1/models` returns `loaded_instances[].config.context_length` (the applied window), `parallel`, `max_context_length`, `size_bytes`, `format`, `quantization`, and `capabilities` (`vision`, `trained_for_tool_use`, `reasoning`). `max_context_length` is the model's trained maximum, not the window in effect. | integration/protocol | Read the applied window from `loaded_instances`; never present `max_context_length` as the window in use. This is the same defect recorded in agentty #49. |
| P2-2 | https://lmstudio.ai/docs/developer/rest/load | `POST /api/v1/models/load` accepts `context_length` and `echo_load_config`; the response carries `load_time_seconds` and, when asked, `load_config.context_length`. | integration/protocol | When LM Studio has not loaded the model, Hutch may load it with an explicit window it computed, then read the applied value back from `load_config`. It never assumes the requested value took effect. |
| P2-3 | https://lmstudio.ai/docs/developer/core/authentication | API tokens are optional; when enabled, every REST/SDK request needs `Authorization: Bearer ...`. Tokens are created in Server Settings. | configuration | Without a token a protected server answers 401: that is `needs_key`, not "dead". A stored key is sent only to the same origin and never enters a URL. |
| P2-4 | https://lmstudio.ai/docs/developer/core/ttl-and-auto-evict | Idle TTL defaults to 60 minutes and resets on requests; auto-evict defaults to on and unloads a previous JIT model. | configuration | The applied window is a per-session fact; re-read `loaded_instances` before each run. A cold model is a state (Phase 3 adds the visible wait). |
| P2-5 | https://github.com/ggml-org/llama.cpp/issues/16693 | A real server log with `--ctx-size 32768 -np 2` shows `n_ctx = 32768`, `n_ctx_per_seq = 16384`, and two slots each initialised at 16384. The reporter hit "the request exceeds the available context size". A maintainer states prompt truncation was removed in commit d00cbea and is no longer tied to `--context-shift`; over-long chat requests error instead of shifting. | integration/protocol | Read the per-request window from `/slots[].n_ctx`, not by dividing `-c` (unified KV lets one slot use the whole pool). Refuse an over-long prompt before sending. Do not claim Hutch can change a llama.cpp window per request. |
| P2-6 | https://github.com/ggml-org/llama.cpp/discussions/4130 | Users report `--parallel 32` with `--ctx-size 8192` producing 32 slots of 256 tokens: the headline context is not the per-request context. | frontend usability | Show the per-slot window and the slot count wherever a local window is shown. |
| P2-7 | https://lmstudio.ai/docs/typescript/api-reference/llm-prediction-config-input (already R20) | LM Studio's overflow policy is `stopAtLimit` or `truncateMiddle`; the latter keeps the system prompt and first user message. The policy is a client setting, not a field on `/api/v1/models`. | configuration | The policy is not readable over REST. Hutch sizes to the applied window and refuses an over-long prompt before sending; the residual uncertainty is written down, not guessed. |
| P2-8 | Local `llama-server --help` (b12144, read 2026-11-06) | `--parallel` defaults to auto (-1); `--ctx-size 0` means "loaded from model"; `--slots` is enabled by default; `--api-key`; `--context-shift` is a flag but `/props` does not report launch flags. | configuration | A key-protected server is discovered by its 401, not by a failed connect. Launch flags remain unknown; readiness and policy wording must say so. |

## Failure mining addendum (R22 onwards)

- **R22** https://github.com/1ay1/agentty/issues/49 (2026): an app showed LM Studio's
  `max_context_length` as the context in use while `/api/v1/models` reported the applied
  `loaded_instances[].config.context_length`. Class: integration/protocol. Hutch response:
  fix. Test: real LM Studio loaded at 8192 while `max_context_length` is 262144; the UI and
  choices must say 8192.
- **R23** https://github.com/ggml-org/llama.cpp/discussions/4130 (2023, still the common
  confusion): `--parallel N` divides the KV budget when the cache is not unified; the
  headline `-c` is not what one request gets. Class: frontend usability. Hutch response:
  fix. Test: real `llama-server --parallel 2`; `/slots` reports the per-slot value and that
  is what Hutch sizes to.
- **R24** https://github.com/ggml-org/llama.cpp/issues/16693 (2025): context shift and
  prompt truncation were removed for chat; users continuing an over-long conversation now
  get an error. Class: integration/protocol. Hutch response: fix. Test: an over-long
  prompt is refused before the request, with the applied window in the message; a real
  over-long request is recorded as the server's own error, never as silent success.
- **R25** https://lmstudio.ai/docs/developer/core/authentication (2026): API tokens are
  off by default and mandatory for every request once enabled. Class: configuration. Hutch
  response: fix. Test: real llama-server `--api-key`; discovery reports `needs_key`, and a
  stored key scoped to that origin lists the models and completes a real chat.

## What this does not settle

- vLLM and SGLang are not installed (a Python dependency and a large download need the
  owner's approval, as Phase 0 recorded). Their `/v1/models` response is the OpenAI model
  object; `max_model_len` is a server launch argument, not part of that object. The adapter
  therefore reports the window as unknown and makes no claim. Marked "not run".
- LM Studio's overflow policy is not exposed over REST (P2-7).
- llama.cpp launch flags are not exposed over HTTP (P2-8).
