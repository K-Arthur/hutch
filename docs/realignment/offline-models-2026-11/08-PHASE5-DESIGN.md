# Phase 5 design: multimodal and tool reliability (2026-11-06)

Research: `docs/research/2026-11-offline-models/06-PHASE5-MULTIMODAL.md` (P5-1 to P5-13,
R42-R54, F12-F18). Exit checks: EC-16, EC-17, EC-18; EC-19 is carried to Phase 6's
airplane test with the code audit recorded here. Frozen files: `providers/ollama.py` is at
its 432-line cap, so it only shrinks (its result folding moves out); `openai_compat.py`
(447/466) and `runtime/builtin.py` (1942/1955) have room for small calls. New files stay
under 400 lines and functions under 60.

## Task 1 - local vision capability (5.1, EC-16)

Files:
1. new `src/hutch/providers/local/vision.py` - `local_vision_supported(provider_id,
   base_url, model, credential="")`: only the named local runtimes; asks the existing
   adapter's `capabilities(model)` (llama.cpp `/props` + `/v1/models`, LM Studio
   `/api/v1/models`), returns `None` for a non-local provider, `False` on an unreadable
   runtime. One request path, no model-name table.
2. `src/hutch/providers/openai_compat.py` - `supports_vision` keeps the official OpenAI
   table, then consults the local resolver for `llamacpp`/`llama.cpp`/`lmstudio`.
3. `tests/test_local_vision.py` new: fake HTTP payloads for a vision-on and vision-off
   llama.cpp, an LM Studio model with `capabilities.vision`, a dead runtime, a
   non-local provider, and the provider's `supports_vision` result.

Why: Hutch currently refuses every llama.cpp/LM Studio vision model even when the server
states the capability. The runtime's own field is the signal.

## Task 2 - LM Studio image media type (5.1, EC-16, F17)

Blocked on live confirmation. If PNG works and WebP is rejected by real LM Studio:
1. `src/hutch/providers/attachments.py` - `image_route_refusal` takes the provider's name
   and refuses `image/webp` only on the LM Studio route, before any request. No conversion,
   no silent media-type rewrite.
2. `src/hutch/providers/local/lmstudio.py` - a `POLICY_NOTE` sentence naming the
   unsupported media type, read by the state/choice note.
3. `tests/test_chat_vision.py` - refusal at admission and at the runtime gate.

If both PNG and WebP fail, the refusal names the runtime bug and LM Studio vision is marked
blocked with the live capture; if PNG works, only WebP is refused.

## Task 3 - reasoning-only and `length` state (5.4, EC-18, F12/F13/F16)

Files:
1. new `src/hutch/providers/ollama_result.py` - the moved `fold_ollama_chunks` from
   `providers/ollama.py` plus the native note: thinking present, no visible content, no
   tool calls; `done_reason == "length"` adds the budget sentence. Uses the shared helper.
2. `src/hutch/providers/openai_result.py` - extract
   `reasoning_budget_note(thinking, content, tool_calls, completion_tokens,
   reasoning_tokens, finish_reason)` used by `build_result`; keeps the existing note text
   and adds the `length`-specific advice. One place decides the wording.
3. `src/hutch/providers/ollama.py` - imports and calls `fold_ollama_chunks`; the local
   `_fold` and its now-unused imports are deleted. Net line count falls.
4. `tests/test_reasoning_budget.py` new: OpenAI shape with reasoning tokens and an empty
   answer; `length` with reasoning; normal content; tool calls present; native Ollama
   chunks with thinking only; normal native answer.

Why: an empty reply that was actually a spent reasoning budget is a state with a fix, not a
success or a mystery.

## Task 4 - tool-call qualification causes and local runtimes (5.3, EC-17)

Files:
1. `src/hutch/reliability.py` - one `classify_failure` function fills
   `ProbeResult.causes` (`no_call`, `empty_answer`, `reasoning_only`, `missing_id`,
   `invalid_id`, `parse_error`, `wrong_tool`, `multiple_calls`, `schema`, `call_failed`);
   `detail` stays the most common cause. `Profile.from_json` defaults old profiles.
   `profile_model` records ids and reasoning even when the probe passes.
2. `src/hutch/cli_models.py` - `--provider` (`ollama` default, `llamacpp`, `lmstudio`,
   `openai-compatible`) and `--base-url`; builds the provider through the existing
   factory, labels the profile with the runtime, and keeps the Ollama health hint only
   when Ollama is selected.
3. `tests/test_reliability_causes.py` new: each cause from a synthetic `ChatResult`,
   old-profile JSON, the CLI's provider selection (monkeypatched factory), and a real
   bench command shape.

Why: the bench currently says "answered in prose" or "returned nothing" for every
non-call, which cannot distinguish a model weakness from a template, id, reasoning or
parser defect.

## Task 5 - audio, speech and embeddings (5.2, 5.5)

No source change. Record in `docs/runtime-setup.md` and `docs/models.md`:
- Ollama speech exists at `/v1/audio/speech` (Phonon, WAV/PCM, 4,096 characters); no speech
  model is retained, and Hutch has no Ollama speech seam. Deferred, not claimed.
- llama.cpp accepts `input_audio` with a compatible model; no audio model is retained.
  Deferred.
- LM Studio's OpenAI surface has no documented audio input; embeddings exist but no Hutch
  feature requests them for a local assistant.
- Code audit: `rg` finds no `/v1/embeddings` client and no hosted search call in the
  memory/search path; `synthesis/model.py` uses the chat route. The airplane test in Phase
  6 is the enforcement evidence, so EC-19 stays open until then.

## Live evidence plan

- llama.cpp b12144 with `models/vision/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf` and
  `--mmproj models/vision/mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf`, CPU, 4,096 to 8,192
  window: a real photo (public-domain cat), a real Playwright screenshot, two images in one
  message, an oversized image refusal, and image plus tool call. The answer must depend on
  image content; the prompt-token count is recorded from the server's own `timings`.
- Ollama 0.40.13: pull `moondream:1.8b-v2-q3_K_S` (about 1.6 GB, inside the remaining
  budget) because an imported GGUF cannot carry its mmproj (P5-2/F18). Same photo and
  screenshot with a content-dependent question. Record the exact size and the import
  attempt's `/api/show` result.
- LM Studio llmster 0.0.27-1: add the retained Qwen2.5-VL GGUF + mmproj to its model
  directory if it scans them; send PNG and WebP data URIs; record which media types the
  real server accepts. If the projector is not picked up, mark LM Studio vision "not run"
  with the reason.
- Whole app pipeline: fresh `HUTCH_STATE_DIR`, real FastAPI server, real bot on the real
  llama.cpp route, upload through `/api/v1/conversations/<id>/uploads`, run with
  `image_attachment_ids`, then read the assistant answer and the `media` log entry proving
  what was transmitted.
- Bench: `qwen3:0.6b`, `qwen2.5-coder:1.5b`, `qwen3:4b` on Ollama; the qwen3-4b and
  qwen2.5-coder-3b GGUFs on llama.cpp (hard-linked from the Ollama blobs if needed);
  the LM Studio chat models. `--no-recall` for the long bench, with Phase 2's needle run
  as the recall evidence. Commit the JSON profiles under
  `docs/research/2026-11-offline-models/evidence/phase5/`.
