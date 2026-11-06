# ADR-0030: A fixed local context window is read, never assumed

Status: accepted, 2026-11-06.

## Context

Ollama accepts a context size per request (`options.num_ctx`, and Hutch always sends one). llama.cpp
fixes the window at launch, LM Studio fixes it at model load, and vLLM/SGLang do not report the
served window over `/v1/models` at all. Hutch previously sized and checked prompts for Ollama only;
for the other local runtimes it sent the prompt with no window check, so a runtime could truncate
from the front or reject the request after the tools and system prompt were already built.

The measurements also differ from the headline number. With `--ctx-size 8192 --parallel 2`,
llama.cpp reported two 4096-token slots. LM Studio reported `max_context_length: 262144` while the
window in effect was 8192. Presenting either maximum as the window would be a false claim.

## Decision

1. **The runtime's applied value wins.** `providers/local/admission.py` sizes a run to the window the
   runtime reports: `/slots[].n_ctx` for llama.cpp and
   `loaded_instances[].config.context_length` for LM Studio. The wanted window is shown beside it,
   never substituted for it.
2. **A cold LM Studio model is loaded deliberately.** When no instance is loaded, Hutch computes a
   fitted window, calls `/api/v1/models/load` with that `context_length`, and reads the applied value
   back from `load_config`. It does not assume the requested value took effect.
3. **An over-long prompt is refused before it is sent.** The existing `check_prompt` and `fitloop`
   checks now run for every local runtime with a known window. A refusal names the window and the
   estimate. Compaction runs first where the run path already supports it.
4. **An unknown window is stated as unknown.** vLLM and SGLang are not claimed to be sized or
   truncated-safe; the run log says the window is unknown and no truncation claim is made.
5. **Launch policies that are not exposed are not guessed.** llama.cpp launch flags and LM Studio's
   overflow policy are not on the HTTP surface Hutch reads. Hutch mitigates by refusing over-long
   prompts and records the residual uncertainty; it does not label a policy from a port, a model
   name or a version guess.
6. **A key-protected server is alive.** HTTP 401/403 from `/v1/models` is `needs_key`. A key is read
   from a configured connection only when its scheme, loopback host and port match the server, is
   sent as a bearer header, and never appears in a URL, result, log or page.

## Consequences

- The model picker and Models page show measured per-request windows and slot counts, not the
  trained maximum.
- Choosing a non-Ollama local model still needs its endpoint on the bot; the picker wiring is Phase 7
  work. Until then the choice detail names the endpoint.
- LM Studio may load a model as a side effect of starting a run; that is visible as a model-load
  state when the load path is exercised, and the fit check can refuse it first.
- vLLM/SGLang remain implemented-unverified for window sizing until a real server is available.
- Tests: `tests/test_local_runtimes.py`, `tests/test_local_choices.py`,
  `tests/test_provider_discovery.py`; live evidence in
  `docs/realignment/offline-models-2026-11/02-PROGRESS.md`.
