# Phase 3 design: lifecycle states and error mapping

Research: `docs/research/2026-11-offline-models/04-PHASE3-LIFECYCLE.md` (R26-R32).
Exit checks: EC-09, EC-10, EC-11, EC-22. Frozen files touched: `runtime/builtin.py` (1953/1955)
shrinks or stays flat; `providers/ollama.py` and `providers/openai_compat.py` are not touched.

## Task 1 - cold start is a visible state (EC-09)

Files:
1. `src/hutch/providers/local/base.py` - `RuntimeState.sleeping: bool` (the llama.cpp
   `/props.is_sleeping` fact, not inferred).
2. `src/hutch/providers/local/llamacpp.py` - set `sleeping` from `/props.is_sleeping`; stop
   caching a `LOADING` state so the wait loop re-reads `/health`.
3. new `src/hutch/providers/local/lifecycle.py` - `LoadObservation`, `observe_load(adapter,
   model, timeout, poll, on_loading)`; `load_fixed_runtime(...)` for LM Studio's explicit
   load and llama.cpp router load.
Seam: `src/hutch/providers/local/admission.py` - `LocalAdmission.load_ms/sleeping`;
`admit_local(..., on_loading=...)` waits while the runtime reports `loading`, passes the
measured load to the caller, and times the LM Studio load with the fitted window.
Call site: `src/hutch/runtime/builtin.py:438-465` passes the status callback and records
`load_ms` in the existing `model_load:` key and the `load` event.

Why here: the runtime already owns the state observation; `builtin` must only turn it into
`RunStatus.loading_model` and a measured log line. A 503 is a wait, never a fallback trigger.

## Task 2 - eviction and restart (EC-10, EC-22)

Files:
1. new `src/hutch/runtime/outcomes.py` - `exit_reason(exc)` moved from `builtin`; `Failure`;
   `classify_local_failure(exc, provider_id, partial)` mapping killed/OOM text
   (`signal: killed`, `unable to allocate`, `out of memory`), broken streams and
   unreachable servers to `action="reload"` (no partial output) or `action="stop"` with the
   cause and the fix.
2. `src/hutch/providers/local/lifecycle.py` - `ensure_loaded(provider_id, provider, model,
   num_ctx, on_loading)` and `reload_local_model(...)`; `refresh_before_call(...)` replaces
   the Ollama-only `_refresh_local_admission` body and re-reads the state before every call.
3. `src/hutch/runtime/builtin.py` - `_refresh_local_admission` delegates (shrinks); the
   `except ProviderError` block asks `classify_local_failure`, performs exactly one reload
   with a visible state, and stops with the message on the second failure. A failure with
   partial text never retries; the text stays incomplete.
Seam: the `_attempt` boundary - the state check runs before the usage reservation, so a
reload never happens under an uncertain reservation.

Why here: one decision table in `outcomes.py`, one state machine in `lifecycle.py`; the run
loop only routes.

## Task 3 - version drift (EC-11)

Files:
1. new `src/hutch/providers/local/versions.py` - version parse/compare, feature gate tables
   (Ollama: tools 0.3.0, structured outputs 0.5.0, thinking 0.9.0, measured window 0.10.0;
   LM Studio: tools 0.3.6, TTL 0.3.9, native API/tokens 0.4.0), `upgrade_advice`.
2. `src/hutch/health.py` - keep the runtime's reported version on `ProviderHealth` (Ollama
   currently drops it) and attach the upgrade sentence to `fix`; doctor and the Models page
   already render `fix`, so both say "upgrade X to Y for Z".
llama.cpp has no public feature matrix: its build string is recorded and features are gated
by field presence (`/props.chat_template_caps`, `/slots`), never by a guessed build floor.

## Validation

- Focused tests: `tests/test_local_lifecycle.py`, `tests/test_local_failure.py`,
  `tests/test_local_versions.py`; existing local suites.
- Real: retained Ollama 0.40.13 cold load with measured `load_ms`; real `llama-server`
  `/health` 503 poll; LM Studio unload and reload; real `kill -9` of the Ollama runner
  mid-stream and real restart of `llama-server`; classification run on the captured bytes.
- Gates: `npm run check:agent`, focused suite, emoji audit, review of the phase diff.
- Honest limit: the largest retained model is 2.5 GB, so the "cold 4 GB load" exit line is
  recorded as a 2.5 GB cold load with the reason; no download beyond the budget.
