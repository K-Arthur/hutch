# Phase 2 design: native runtime introspection (2026-11-06)

Scope: G3, G4, G7; EC-05 to EC-08, EC-12, EC-13. One seam per task, at most three source
files per task besides one new module package. Frozen files (`modelchoices.py`,
`providers/openai_compat.py`, `runtime/builtin.py`) only shrink.

## Task 2.1 - runtime protocol, probes and adapters

New package `src/hutch/providers/local/`:

- `base.py`: `LocalRuntime` protocol; `Identity`, `Slot`, `Loaded`, `RuntimeState` dataclasses.
  `RuntimeState` carries `models: list[ModelMeta]`, `loaded: dict[str, Loaded]`, `state`
  (`ready | loading | needs_key | unreachable | unknown`), `policy` and `policy_detail`.
- `probe.py`: bounded, redirect-refusing plain-HTTP GET with an optional `Authorization:
  Bearer` header; returns status, headers and body. One loopback verifier here, re-exported
  by `providers/discovery.py`.
- `llamacpp.py`: identity from `/props.build_info` and `owned_by: "llamacpp"`; models from
  `/v1/models`; loaded window and slots from `/slots`, falling back to
  `/props.default_generation_settings.n_ctx`; state from `/health` and 401/403.
- `lmstudio.py`: identity from the `/api/v1/models` shape; models, capabilities and the
  applied window from `loaded_instances[].config`; `load(model, context_length)` using
  `/api/v1/models/load` with `echo_load_config`.
- `openai_generic.py`: vLLM/SGLang `/v1/models`; `owned_by` is the only identity signal;
  window unknown; no fabricated capability.
- `__init__.py`: provider table and `adapter_for(provider_id, base_url, credential="")`,
  `introspect(provider_id, url, credential="")`.

Seam: `providers/discovery.py` probes the stock llama.cpp port 9931 as well as 8080,
fingerprints every answer through the adapter, distinguishes 401/403 (`needs_key`) from a
dead port, and reports the applied window. It accepts `credential_for(provider_id, url)` so
a caller can supply a key from a connection; discovery itself still sends none by default.

## Task 2.2 - fixed-window policy

- `context.py`: `ContextPlan` gains optional `applied`, `slots`, `policy`; `plan_context`
  accepts them. A runtime that reports the applied window always wins over the wanted
  window, and the note states both. No fit arithmetic is invented for a loaded model.
- New `providers/local/admission.py`: `admit_local(provider, provider_id, base_url, model,
  want, min_ctx, hardware, credential) -> LocalAdmission`. Ollama keeps its existing
  `show` + `plan_context` path. llama.cpp reads the per-slot window; if the server is
  loading, the run is refused with a state, not sent. LM Studio reads the applied window
  and, only when the model is cold, loads it with a fitted window and reads the applied
  value back. vLLM/SGLang return `unknown` and the run log says the window is unknown.
- `runtime/builtin.py`: replace the Ollama-only meta/num_ctx block with one call to
  `admit_local` for every local rung (net line change <= 0). The returned `num_ctx` makes
  the existing `check_prompt` refuse an over-long prompt and the existing `fitloop` compact
  before overflow.
- `modelview.py`: append measured local-window notes from discovery only when a non-Ollama
  runtime is up; no new page in this phase.

## Task 2.3 - first-class local choices (G3)

- New `src/hutch/localchoices.py`: builds `Choice` rows for Ollama and every reachable
  local runtime. Ollama keeps its cloud classification. Other runtimes use the adapter's
  applied window, per-slot value and capability list; a model is `ready` only when the fit
  arithmetic says it is, never because a port answered.
- `modelchoices.py`: `_local_choices` delegates to the new module; the extracted body
  shrinks the frozen file.

## Task 2.4 - needs_key and origin-bound credentials

- New `providers/local/credentials.py`: `runtime_credentials(state_dir)` returns a lookup
  `(provider_id, url) -> key` over `ConnectionBook`; a key is used only when the
  connection's base URL has the same scheme, host and port as the probed URL.
- `server/pages_providers.py`: pass that lookup to discovery. A 401/403 shows
  `needs_key` with the fix; with a matching stored key, the same server lists its models.
- The run path already sends a connection's key to that connection's endpoint
  (`provider_for_connection`); no new credential store and no key in a URL, log or response.

## Tests

- `tests/test_local_runtimes.py`: parsers and adapters against captured/injected responses;
  squatter on 8080 is not llama.cpp; 401 is `needs_key`; per-slot window wins over `-c`;
  LM Studio applied window wins over `max_context_length`; an injected key is sent only to
  its own origin.
- `tests/test_provider_discovery.py`: 9931 candidate, fingerprint fields, needs_key.
- `tests/test_local_choices.py`: non-Ollama local models appear under "On this machine"
  with the applied per-slot window; a model that does not fit is not `ready`.
- `tests/test_context_fixed_window.py`: applied versus wanted note, no fit rewrite for a
  loaded model.
- `tests/test_runtime_builtin.py`: admission result reaches `Session.num_ctx` for a
  non-Ollama local rung.

## Live validation (evidence in `02-PROGRESS.md`)

1. Real `llama-server` b12144 on 9931, `-c 8192 --parallel 2`, qwen3-4b: `/props`,
   `/slots`, discovery, admission, real needle self-check at the applied window, and a real
   over-long prompt refused before send.
2. Real LM Studio server: `/api/v1/models`, load at a chosen window, discovery, admission;
   applied window must equal `/api/v1/models.loaded_instances[].config.context_length`.
3. Real `llama-server --api-key`: discovery `needs_key` without a key; with a temporary
   connection key, models list and a real chat completes. Key absent from output.
4. Decoy `/v1/models` on 8080 is not labelled llama.cpp.
5. Real FastAPI app and Chromium capture of the model switcher with llama-server up.
