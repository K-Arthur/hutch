# Phase 5 research: multimodal and tool reliability (2026-11-06)

Narrow pass for Phase 5: vision on Ollama and llama.cpp (LM Studio if obtainable), audio and
speech, tool-call qualification causes, and reasoning-budget behaviour. Phase 0 API notes and
R1-R41 remain valid. Every source below was opened on 2026-11-06; search snippets were leads
only and are not asserted.

## Sources and decisions

| # | Source | Fact taken | Class | Decision it changed |
|---|---|---|---|---|
| P5-1 | https://docs.ollama.com/capabilities/vision | `/api/chat` takes an `images` array of base64 strings on a message; the SDKs accept paths, URLs or bytes. `/api/show` reports model capabilities, including `vision`. | integration/protocol | The Ollama wire path already used by `to_ollama_messages` is the documented one. The capability gate stays `/api/show`, never a model name. |
| P5-2 | https://docs.ollama.com/import | GGUF import accepts a single file or a shard wildcard in a Modelfile `FROM`. The page says nothing about a separately supplied multimodal projector. | integration/protocol | Hutch must not claim that importing a text GGUF plus an mmproj gives Ollama vision. Live attempt in this phase; if the projector is not attached, the guide says to pull a vision model. |
| P5-3 | https://github.com/ollama/ollama/issues/10976 | With qwen3, `think: true` plus tools returned empty `content`, no `tool_calls`, and all generation in the thinking block. `think: false` produced the tool call. Later reports show the `/v1` path only disables thinking reliably with `reasoning_effort: "none"`; one reporter traced the server forcing `think=true` when the client sent no preference. | model-specific + integration | Hutch's tool bench sends `think=False`. A reasoning-only turn with no call and no answer is classified and disclosed, not counted as a model-quality failure without saying why. |
| P5-4 | https://github.com/ollama/ollama/issues/17978 | qwen3-vl-thinking can spend the whole `num_predict` budget inside `think`, return `done_reason: length` and an empty `message.content`. The reporter's workaround closes the thinking block client-side and resumes. | model-specific | When `done_reason` is `length` and there is thinking text but no visible answer and no call, Hutch says the output budget was consumed by reasoning and names the fix. It does not retry automatically with a different budget. |
| P5-5 | https://raw.githubusercontent.com/ggml-org/llama.cpp/master/docs/multimodal.md | Vision needs the projector: `-m model.gguf --mmproj mmproj.gguf`, or `-hf` with the projector unless `--no-mmproj`. The server accepts image, audio and video over the OpenAI-compatible chat API. | integration/protocol | llama.cpp vision is testable with the retained Qwen2.5-VL GGUF and Q8_0 projector. No download is required. |
| P5-6 | https://raw.githubusercontent.com/ggml-org/llama.cpp/master/docs/function-calling.md | Tool calling uses the model's Jinja template; a wrong or missing template falls back to a generic format or fails. `parallel_tool_calls` is opt-in. The response keeps `reasoning_content` alongside `tool_calls`. | integration/protocol | Bench classification distinguishes template/format failures from model refusals. Hutch does not send `parallel_tool_calls` by default. |
| P5-7 | https://github.com/ggml-org/llama.cpp/issues/11992 | llama-server returned `"id": ""` on tool calls; clients that require an id broke. The issue was closed with a server change, but ids can still be absent. | integration/protocol | Hutch already assigns deterministic ids when a provider omits them and rejects duplicate ids. The bench records missing ids as a cause rather than treating them as model failure. |
| P5-8 | https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/1592 | LM Studio's parser scans inside `<think>` blocks, can treat reasoning prose as tool-call markers, and can leave `content` empty with `finish_reason: "stop"` while the reasoning field holds everything. The workaround is to disable thinking. | model-specific + integration | A reasoning-only response is a distinct outcome in the bench and in the result notes. Hutch does not enable thinking for tool probes. |
| P5-9 | https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/1752 | LM Studio 0.4.9+ rejected an `image_url` with a base64 data URI; the reporter used WebP. A commenter worked around it by changing the data-URI media type to PNG or converting WebP to JPEG. | integration/protocol | Test PNG and WebP data URIs live on LM Studio before claiming vision. If only WebP fails, refuse WebP on that route with words; never silently convert the user's image. |
| P5-10 | https://lmstudio.ai/docs/developer/openai-compat/tools | Native tool use needs a supported template; otherwise LM Studio injects a default format. If it cannot parse a correctly formatted call, the text stays in `content` and `tool_calls` is absent. `finish_reason` is `tool_calls` on success. | integration/protocol | Bench counts "call-shaped text in content" and "no tool_calls" separately from a prose answer. It does not repair model text into a call. |
| P5-11 | https://lmstudio.ai/docs/developer/openai-compat/chat-completions | The endpoint accepts text and images; the documented payload parameter list does not include a thinking toggle. | configuration | Hutch cannot disable thinking per request on LM Studio's OpenAI-compatible endpoint. The route's capability is recorded, and reasoning-only behaviour is disclosed. |
| P5-12 | https://docs.ollama.com/capabilities/speech | Ollama exposes `/v1/audio/speech` with speech models (Phonon), WAV/PCM output, a 4,096-character input limit and no chat/completion on speech models. | integration/protocol | There is no retained speech model and no Hutch TTS seam for Ollama; audio/speech is documented as deferred rather than implemented against a runtime that was not exercised. |
| P5-13 | https://lmstudio.ai/docs/developer/openai-compat | The OpenAI-compatible surface includes `/v1/embeddings`; the native `/api/v1` surface also lists embedding models. | integration/protocol | A local embedding route exists technically, but no Hutch feature needs one for the offline assistant. No embedding client is added in this phase; the code audit is recorded. |

## What the code audit found before the live pass

- `providers/attachments.py` validates count, size, chat ownership, MIME and digest, and
  produces OpenAI-shaped `image_url` data parts. `context.py` already budgets a flat 800
  tokens per image before the first request.
- `providers/ollama.py` converts the parts to the native `images` base64 array.
- `providers/openai_compat.py` sends the parts unchanged; its `supports_vision()` is true
  only for the official OpenAI model table. It therefore refuses every llama.cpp and LM
  Studio vision model even when the runtime reports one. This is the Phase 5 gap.
- `providers/openai_result.py` already notes billed reasoning tokens and the empty-answer
  case for OpenAI-shaped results. The native Ollama result path has no equivalent note.
- `runtime/builtin.py::_normalize_call_ids` assigns deterministic ids for missing ids and
  rejects duplicate ids as a unit; this covers the llama.cpp empty-id class.
- `reliability.py` measures shape, argument types, tool choice, restraint and use of a
  result, but does not record missing ids, reasoning-only turns, call-shaped prose or
  parallel/unrequested calls. Its CLI is Ollama-only.

## Current-model addendum (owner request, 2026-11-06)

The first pass measured the retained 2025-era models because they were already on disk
and the host is CPU-only. The owner then asked for the newer models and approved
exceeding the original download budget. The current candidates were read from the live
Ollama library pages (R55/R56) before pulling:

- Qwen3.5 0.8B, 2B Q4_K_M and 4B Q4_K_M: 1.3, 1.9 and 3.3 GB; vision, tools, thinking;
  256K context. All three are GGUF and expose a separate projector blob.
- Gemma 4 e2b: 4.6 GB; vision, tools, thinking and audio; 128K context.

The comparison is recorded in `02-PROGRESS.md` and `docs/models.md`: all four pass the
isolated Ollama tool bench, but the full-app image comparison separates them (Gemma 4
e2b 3/3, Qwen3.5 4B 2/3, Qwen3.5 2B 1/3, Qwen3.5 0.8B 0/3). The isolated bench alone
would have recommended the wrong model for a full multimodal agent turn.

## Failure and complaint classes added in this phase

| ID | Complaint | Evidence | Class | Hutch response | Test idea |
|---|---|---|---|---|---|
| F12 | Thinking plus tools can return an empty answer with no tool call. | Ollama #10976 | model-specific + integration | Send `think=False` for tool probes; classify a reasoning-only turn and state the cause. | Real qwen3-family model with `think=true`, tools and a small cap; the result must say reasoning consumed the budget. |
| F13 | A vision-thinking model can spend `num_predict` reasoning and never emit an answer. | Ollama #17978 | model-specific | `length` plus thinking and no content is its own note with the fix, not an empty reply. | Real local thinking model with a 64-token cap. |
| F14 | Tool-call ids can be empty; a client that echoes them back breaks the next turn. | llama.cpp #11992 | integration/protocol | Deterministic id assignment in the runtime (already present); bench records missing ids. | Real llama.cpp call with an id-less response, replayed through the next turn. |
| F15 | A wrong template or parser can hide a tool call inside reasoning or plain content. | llama.cpp function-calling doc; LM Studio #1592; LM Studio tool-use doc | model-specific + integration | Bench counts the cause; no text-to-call guessing. | Bench three local models per runtime and keep the captured reasons. |
| F16 | LM Studio's parser can enter a reasoning block and produce false calls. | LM Studio #1592 | model-specific | Do not enable thinking for probes; disclose reasoning-only outcomes per model. | Bench on LM Studio with a reasoning-capable model at a small cap. |
| F17 | An LM Studio image data URI can be rejected (WebP reported). | LM Studio #1752 | integration/protocol | Live-test PNG and WebP; refuse an unsupported media type before sending if confirmed. | Real PNG and real WebP through the app to LM Studio. |
| F18 | Ollama import does not attach an external mmproj, so an imported model lists text-only. | Ollama import doc; live attempt in this phase | integration/protocol | Vision import is not offered as a vision path; the guide names pulling a vision model. | Import attempt with the retained Qwen2.5-VL GGUF; `/api/show` capabilities must be checked, not assumed. |
