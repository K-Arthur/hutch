# Progress: offline and local models (2026-11)

Update at every checkpoint. Keep entries short and factual. Statuses: not started, in progress, done,
blocked. Resume at the first phase that is not done; re-verify any evidence older than the code it
covers before relying on it.

## Phase status

| Phase | Status | Last commit | Live-verified | Blocked on |
|---|---|---|---|---|
| 0 Diagnose | done | 33bf8a61 | 2026-11-06: Ollama 0.40.13/0.40.15, llama.cpp b12144 CPU+Vulkan, LM Studio llmster 0.0.27-1, Chromium captures | — |
| 1 Locality truth | done (1.1, 1.2, 1.3) | see git log | 2026-11-06: real Ollama 0.40.13 rows (cloud stub, renamed cloud copy, local, missing model) | EC-02 second-interface run not run |
| 2 Native runtime introspection | done (2.1, 2.2, 2.3, 2.4) | d057cc95..7c53c59e | 2026-11-06: llama.cpp b12144 9931 (4096 per slot with `-c 8192 --parallel 2`), LM Studio applied 8192, discovery fingerprints both, squatter unknown, `--api-key` needs_key then a keyed chat, needle self-check at 4096 | vLLM/SGLang not installed; LM Studio API-token mode not enabled live (401 path tested with a real key-protected llama-server) |
| 3 Lifecycle states and errors | done (3.1, 3.2, 3.3) | bfcfaaf9..23ed98a3 | 2026-11-06: real Ollama cold load, real llama.cpp 503, real LM Studio unload/reload, real runner kill and llama-server restart | EC-09 4 GB model not downloaded (budget); old-version gate not live-tested |
| 4 Get a model (install, import, guide) | not started | | | |
| 5 Multimodal and tool reliability | not started | | | |
| 6 Strict Offline live, boundary ADR | not started | | | Owner decision on the boundary (Phase 6.3) |
| 7 Frontend | not started | | | |
| 8 Website and docs | not started | | | |
| 9 Final review and merge | not started | | | |

Phase 0 exit checks: baseline (`docs/research/2026-11-offline-models/00-BASELINE.md`),
failure mining (`01-FAILURE-MINING.md`) and API notes (`02-RUNTIME-API-NOTES.md`) written;
gap reproductions recorded; gates run; backlog ordered in the failure-mining doc; batched
owner questions answered (LM Studio: yes; download budget: not exceeded).

## Gap status (G-IDs from the master prompt)

| ID | Reproduced on real stack | Fixed in | Evidence row |
|---|---|---|---|
| G1 install name grammar | 2026-11-06, 6 of 10 real forms refused | Phase 4.1 (planned) | `00-BASELINE.md` Gap reproductions |
| G2 cloud-tag locality | 2026-11-06, renamed cloud copy classified local; UI says "On this machine" | Phase 1 (planned) | same, plus `baseline-up/up-switcher-1280-dark.png` |
| G3 local group only for Ollama | 2026-11-06, llama.cpp reachable but `_local_choices` returned `[]` | Phase 2.3: `localchoices.py`, both real runtimes now produce `On this machine` rows | live choices run below |
| G4 no native introspection | 2026-11-06, `rg` empty; real `/props`, `/slots`, `/api/v1/models` fields recorded | Phase 2.1: `providers/local/` adapters | live adapter run below |
| G5 Strict Offline never live | historical gap confirmed; no live run yet | Phase 6.1 (planned) | `docs/realignment/offline-models-2026-10-31.md` section 3.5 |
| G6 no disk preflight, no real big pull | 2026-11-06, `rg` empty | Phase 4.2/4.3 (planned) | `00-BASELINE.md` |
| G7 port-trust discovery, key-protected servers | 2026-11-06, decoy on 8080 labelled llama.cpp; real `--api-key` server reported "no service answered" | Phase 2.1/2.4: response fingerprint, 9931 candidate, `needs_key` | decoy and key test below |
| G8 frozen files not grown | confirmed 2026-11-06: 433/432/447/1955 against caps 435/432/466/1955 | Phase 9 recheck | `.file-size-baseline.json` |

## Edge-case status

Track by ID from `03-EDGE-CASES.md`: tested-real, tested-fault-injected, documented, not-run (reason),
or out-of-scope (reason). One line per ID once touched.

- EC-01: tested-real; fixed Phase 1: real Ollama refuses `gpt-oss:20b-cloud` and renamed copy `my-local-copy` via `remote_host`.
- EC-02: fault-injected/unit only (addresses resolved, not spelling; `tests/test_locality.py`); not-run live: no second interface or hosts entry. Address is checked at validation, not pinned at connect time (open, Phase 6).
- EC-03: documented; llama.cpp `--offline` found, launch flags invisible so readiness is `unknown`, never a pass (vendor docs: Ollama cloud/remotes, LM Studio catalog/JIT, llama.cpp `-hf`).
- EC-04: not-run (Phase 6).
- EC-05: tested-real; fixed Phase 2.2: llama.cpp `/slots` 4096 and LM Studio `loaded_instances.config.context_length` 8192 are the windows Hutch sizes to; `plan_context` refuses an over-long prompt before send. Needle self-check at 4096 recorded below.
- EC-06: tested-real for llama.cpp: an over-long request returns HTTP 400 `exceed_context_size_error` with `n_ctx=4096`; prompt truncation was removed for chat (R24). Hutch refuses before sending. LM Studio's `truncateMiddle`/`stopAtLimit` policy is not exposed by `/api/v1/models` (R20); Hutch sizes to the applied window and states the residual unknown.
- EC-07: partially measured (Ollama `size`/`size_vram`); llama.cpp and LM Studio now report applied windows but not resident bytes over the fields Hutch reads. Full fit comparison remains Phase 2/5.
- EC-08: tested-real: llama.cpp `-c 8192 --parallel 2` reports 4096 per slot in `/slots` and `/props`; LM Studio reports `parallel: 4` with an 8192 applied window. Both are shown as per-request values, not the headline.
- EC-09: tested-real, Phase 3: a full app run showed `pending, running, loading_model, running, succeeded` and a measured 4.821 s cold Ollama load; a real llama.cpp 503 body was waited out in 3.553 s; a real LM Studio unload/reload measured 2.905 s. The 4 GB variant was not downloaded (budget: 4.1 GB of 10 GB used, Phase 4 needs room); the largest retained model is 2.5 GB.
- EC-10: tested-real for explicit eviction, Phase 3: LM Studio `/api/v1/models/unload` then reload; a real Ollama runner kill and a real llama-server kill/restart. The 60-minute LM Studio TTL and 5-minute Ollama keep-alive were not waited out; the same absence-of-`loaded_instances` / `/api/ps` signal is what the tests exercise.
- EC-11: tested-real for the current runtime plus unit, Phase 3: Ollama 0.40.13 passes every gate; advice strings for 0.9.0/0.3.5 are table-tested; llama.cpp build strings produce no advice. Not run: an older Ollama or LM Studio installation.
- EC-22: tested-real, Phase 3: a real `kill -9` of the Ollama child `llama-server` mid-stream produced `llama-server process has terminated: signal: killed`; the full run reloaded once, showed `loading_model`, and succeeded. The partial-text stop path is unit-tested; GPU OOM could not be produced on this host.
- EC-12: tested-real (decoy on 8080). Fix Phase 2.1.
- EC-13: tested-real (`--api-key` server looks dead). Fix Phase 2.4.
- EC-15: tested-real (G1 names; GGUF template present and tool-capable in `/props`). Fix Phase 4.1.
- EC-18: tested-real (LM Studio empty answer with 64 reasoning tokens). Fix Phase 5.4.
- EC-21: tested-real on this host (Ollama drops the iGPU; see `02-RUNTIME-API-NOTES.md`).
- EC-23: reproduced as a missing capability (no disk preflight). Fix Phase 4.
- EC-25: not-run (network-dependent tag check; Phase 4).
- EC-27: documented (llama.cpp accepts `input_audio`; no local audio run yet).
- EC-28: tested-real for Strict Offline fallback rungs (cloud copy refused live) and unit-tested. Not covered: non-offline silent fallback; Phase 7 confirmation UI.

## Evidence ledger (real runs only)

| Date | Runtime and version | Model and digest | Hardware | Route and command | Exercised | Not exercised | Result |
|---|---|---|---|---|---|---|---|
| 2026-11-06 | Ollama 0.40.13 | qwen3:0.6b, qwen2.5-coder:1.5b, qwen3:4b (3.8 GB) | Ryzen 3 5300U, CPU | `OLLAMA_HOST=127.0.0.1:11434 OLLAMA_MODELS=~/.hutch-tmp/localmodels/models ollama serve` | `/api/version`, `/api/tags`, `/api/ps`, `/api/generate`, `/api/pull` of a cloud manifest, `ollama create` from it | Cloud inference (no account) | Cloud fields present; chat on the copy returns `unauthorized`; cold load 1.56 s; `size_vram=0` |
| 2026-11-06 | Ollama 0.40.15 | same store, hard-linked copy | same | `OLLAMA_HOST=127.0.0.1:11435 ollama serve` | `/api/version`, `/api/tags` | inference | Same `remote_host` / `remote_model` fields as 0.40.13 |
| 2026-11-06 | llama.cpp b12144 (CPU) | qwen3:4b GGUF, 2.50 GB | same | `llama-server -m models/qwen3-4b.gguf -c 8192 --host 127.0.0.1 --port 8080` and the default 9931 | `/health`, `/props`, `/slots`, `/v1/models`, `/v1/chat/completions`, `/api-key` | vision, tools end to end, 503 body | `n_ctx=8192`, 4 auto slots, `supports_tools=true`, `owned_by=llamacpp`; key-protected server looks dead to discovery |
| 2026-11-06 | llama.cpp b12144 (Vulkan) | no model | same | `llama-server --list-devices` | device listing | inference | `Vulkan0: AMD Radeon Graphics (RADV RENOIR) (12175 MiB, 7624 MiB free)` |
| 2026-11-06 | LM Studio llmster 0.0.27-1 | local/qwen3-4b (hard link) + bundled embedding | same | `lms daemon up`, `lms server start --port 1234` | `/api/v1/models`, `/v1/models`, JIT `/v1/chat/completions`, `lms ps` | API-token mode, vision | JIT context 8192, `parallel=4`, TTL 3600 s; 64 reasoning tokens returned an empty answer |
| 2026-11-06 | FastAPI app (this checkout) | real Ollama store | same | `capture_offline_models_baseline.py`, Chromium | `/models`, switcher, `/#/connections`, `/onboarding`, `/onboarding/local-service` at 360/768/1280/1920 | light theme (fixed dark), keyboard traversal (Phase 7) | 20 + 20 screenshots; zero overflow, zero page/console errors; defects listed in `00-BASELINE.md` |
| 2026-11-06 | llama.cpp b12144 / server b12144-69ee2ecc0 | qwen3-4b Q4_K_M, 2491323904 bytes | Ryzen 3 5300U, CPU | `llama-server -m models/qwen3-4b.gguf -c 8192 --parallel 2 --reasoning-budget 0 --host 127.0.0.1 --port 9931` | `/props`, `/slots`, `/v1/models`, discovery, `admit_local`, real `/v1/chat/completions`, over-long request | vision, tools end to end | `/props.build_info=b12144-69ee2ecc0`; `/slots` two slots at 4096; discovery runtime `llamacpp`, confidence strong, applied 4096; admission `num_ctx=4096`, 2 slots; chat `context_window=4096`; 12,011-token request returned 400 `exceed_context_size_error` with `n_ctx=4096` |
| 2026-11-06 | LM Studio llmster 0.0.27-1 | qwen3-4b (local), text-embedding-nomic-embed-text-v1.5 | same | `lms daemon up`, `lms server start --port 1234`, `POST /api/v1/models/load {"context_length":8192}` | `/api/v1/models`, discovery, `admit_local`, real `/v1/chat/completions` | API-token mode (separate row), vision | applied window 8192 (max 262144); `parallel=4`; discovery runtime `lmstudio`, confidence strong; cold load echoed 8192; chat `context_window=8192`, answer `window-ok` |
| 2026-11-06 | Ollama 0.40.13 | qwen3:4b, unloaded before the run | Ryzen 3 5300U, CPU | real FastAPI app on an ephemeral port, fresh `HUTCH_STATE_DIR`, bot `ollama/qwen3:4b`, `POST /api/bots/<id>/run`; script in the session scratchpad, JSON at `~/.hutch-tmp/offline-models-2026-11/evidence/p3-cold-start.json` | status timeline, `loading_model`, measured `model_load` key, answer | 4 GB model variant (no download) | statuses `pending, running, loading_model, running, succeeded`; cold load 4.821 s; answer `phase-three-ok`; no hosted fallback |
| 2026-11-06 | llama.cpp b12144 (CPU) | qwen3-4b Q4_K_M, 2.49 GB | same | `llama-server -m models/qwen3-4b.gguf -c 8192 --parallel 2 --reasoning-budget 0`; caught the first `/health` 503, then `admit_local("llamacpp", ...)`; JSON at `evidence/p3-llamacpp-load.json` | 503 body, wait, `/props`, `/slots`, applied window | chat through a Hutch bot route (Phase 7 wiring) | 503 body `{"error":{"message":"Loading model","type":"unavailable_error","code":503}}`; wait 3.553 s; applied 4096 per request, 2 slots; `on_loading` true/false |
| 2026-11-06 | LM Studio llmster 0.0.27-1 | qwen3-4b | same | `POST /api/v1/models/unload {"instance_id":"qwen3-4b"}`, then `admit_local("lmstudio", ...)`, then a real `/v1/chat/completions`; JSON at `evidence/p3-lmstudio-reload.json` | unload state, measured reload, applied window, chat | TTL wait (60 min) | loaded instances empty, then applied 8192; reload 2.905 s; chat `reloaded` with `context_window=8192` |
| 2026-11-06 | Ollama 0.40.13 | qwen3:0.6b | same | real `kill -9` of the Ollama child `llama-server` mid-stream, direct provider capture and a full app run; JSON at `evidence/p3-kill-runner.json` and `evidence/p3-run-kill.json` | real error text, classifier, reload, final answer, status timeline | GPU OOM | direct error `Ollama error mid-stream: ... unexpected EOF`; classifier reload; full run `pending, running, loading_model, running, succeeded` with two `load` events (one reload message, one measured reload); provider health recorded `llama-server process has terminated: signal: killed`; answer produced |
| 2026-11-06 | llama.cpp b12144 (CPU) | qwen3-4b | same | `kill -9` of `llama-server` mid-stream, restart, `refresh_local_route`, real chat; JSON at `evidence/p3-llamacpp-restart.json` | real error text, classifier, restart detection, answer | full Hutch bot route (Phase 7) | error `cannot connect to http://127.0.0.1:9931/v1`; classifier reload; restarted server detected; answer `restarted` |
| 2026-11-06 | version gates | — | — | `tests/test_local_versions.py` table, real Ollama 0.40.13 | gates at 0.40.13 and advice at 0.9.0/0.3.5 | an older runtime installation | all Ollama gates pass at 0.40.13; advice strings tested; LM Studio advice tested from a reported version; llama.cpp build string produces no advice |

## Decisions log

- 2026-11-06: LM Studio may be installed for live checks (owner answered yes). Installed
  headlessly as llmster 0.0.27-1 under `~/.lmstudio`; no GUI.
- 2026-11-06: This package owns Ollama, llama.cpp, LM Studio, vLLM and SGLang. The sibling
  `provider-expansion-2026-11/` package keeps hosted providers, gateways and custom remote
  endpoints; its Phase 5 "Local and custom" row should be marked delegated to this package.
  No sibling files were read or edited.
- 2026-11-06: Download budget used: 4.1 GB of 10 GB (Ollama 0.40.15 1.5 GB, llama.cpp
  58 MB, Qwen2.5-VL-3B + projector 2.6 GB). No further download without asking.
- 2026-11-06: The dashboard is dark-only by design. Phase 0 captures dark; the light/dark
  gate applies to the website in Phase 8. Recorded rather than faking a light dashboard.
- 2026-11-06: `llama-server` defaults to port 9931, not 8080. Phase 2 discovery must probe
  the real default and fingerprint the response, not trust the port.
- 2026-11-06: The cloud signal is `/api/tags.remote_host` / `remote_model`; `/api/show`
  does not carry it on 0.40.13 or 0.40.15. Name suffix is fallback only.
- 2026-11-06, Phase 3: a 503 "Loading model" is a bounded wait with a visible `loading_model`
  state, never a fallback trigger. `/v1/models` is not a readiness signal for llama.cpp.
- 2026-11-06, Phase 3: one reload per failure episode, then a clear stop. A failure with text
  already delivered is never retried; the text stays incomplete and the turn stops with the cause.
- 2026-11-06, Phase 3: fixed-window routes are re-read through a fresh adapter before every
  model call, so an eviction or restart between turns is a state, not a stale assumption.
  A route whose native endpoint cannot be read falls through to the request's own error.
- 2026-11-06, Phase 3: version gates come only from published release notes; an unknown
  version gets no advice, and llama.cpp gets no invented build floor (its build string is
  recorded and features come from `/props` fields).
- 2026-11-06, Phase 3: the cold-load exit check used the retained 2.5 GB qwen3:4b rather than
  downloading a 4 GB model; 4.1 GB of the 10 GB budget remains committed to Phases 4-5.
- 2026-11-06, Phase 3: a sleeping llama.cpp model is reported as reloadable, not down. Hutch
  does not send a warmup POST to force the wake, so the first request includes the reload and
  its status remains `running`; the adapter reports `sleeping` and the run note says so.

## Owner questions (ask once, batched)

Answered in Phase 0:

- Permission to install LM Studio: **yes**, installed if obtainable (llmster used).
- Download budget beyond 10 GB: **not needed** (4.1 GB used).

Still open (ask at the phase that needs it):

- Phase 6 boundary decision: managed isolated model server, user-run offline profile, or
  status-quo wording. Do not implement the managed process without approval.
- Which sibling Phase 5 rows to mark delegated to this package (owner to confirm).

## Review findings log

(date, phase, finding, fix commit)

- 2026-11-06, Phase 0: the first capture pass labelled "light" images that rendered dark.
  Cause: the dashboard is fixed dark and no linked stylesheet reads `data-hutch-theme`.
  Fixed the harness to capture the real state and recorded the reason; no product change.
- 2026-11-06, Phase 0: `scripts/audit_emoji.py` reports 8 pictographic findings, all in
  `.codewhale/state/subagents.v1.json` (another actor's state directory). None is in a
  Phases 0 file; not touched.
- 2026-11-06, Phase 2 review: `local_window_notes` returned early unless the hardware probe saw a
  non-Ollama runtime, and the hardware probe checks llama.cpp's old 8080, so a stock 9931 server
  produced no notes. It now probes the discovery candidates and is skipped only when
  `with_runtimes=False`. Local choices and model notes also now pass the state directory so a
  key-protected runtime with a matching stored key is readable rather than reported as `needs_key`.
  Removed unused `hw`/`bot` parameters from the choice helpers and the unused `LOOPBACK_HOSTS`
  constant in discovery. No behavior claim changed; the focused suite (87) passes.
- 2026-11-06, Phase 3 review: the first classifier run on the real killed-runner text
  ("unexpected EOF") returned `stop` with no message. Added the real wrapper markers and a
  regression test built from the captured string; re-ran the real kill and got `reload`.
- 2026-11-06, Phase 3 review: the per-call refresh initially ran for hosted routes and blocked
  fixed routes whose native endpoint was unreadable (15 `test_runtime_builtin` failures).
  Gated it to local providers and made an unreadable native endpoint fall through to the
  request's own error; the whole runtime suite passes.
- 2026-11-06, Phase 3 review: the OOM/restart sentences claimed a reload in the stop-after-partial
  branch. Made them action-aware; partial text is stated as kept and the turn as stopped.
- 2026-11-06, Phase 3 review: `_exit_reason` moved to `runtime/outcomes.py` and the Ollama
  memory/refresh helpers moved to `providers/local/lifecycle.py`, so `runtime/builtin.py`
  shrank from 1,955 to 1,942 lines rather than growing past its cap. No function over 60 lines;
  the new modules are 255, 87 and 67 lines.
- 2026-11-06, Phase 3 review: a local route pointed at a non-loopback address made the probe
  raise `ValueError` instead of a `ProbeError`. `observe_load` now turns that into a blocked
  `bad_request` observation and `load_fixed_runtime` catches it too; one regression test. The
  4-file runtime set then passed 127.

## Open items and deferred

- G1, G2, G3, G4, G6, G7 fixes: Phases 1, 2 and 4.
- G5 live Strict Offline: Phase 6.
- Phase 3 not run: a 4 GB cold load (budget), a 60-minute LM Studio TTL wait, a 5-minute
  Ollama keep-alive wait, an older Ollama/LM Studio installation for the upgrade path, GPU
  OOM, and a full Hutch bot turn on llama.cpp or LM Studio (Phase 7 wiring). The adapter-level
  restart and reload paths were exercised live and are recorded in the ledger.
- vLLM and SGLang: not installed (dependency decision needed); OpenAI-compatible seam only.
- LM Studio API-token mode from the CLI: not found in this pass; GUI setting documented.
- Phase 0 artifacts total 40 PNGs plus the capture JSON; kept under
  `docs/realignment/artifacts/offline-models-2026-11/`.

- 2026-11-06, Phase 1: `providers/locality.py` (server signal, resolved address, name fallback); wired into
  `validate_offline_route`, `OllamaProvider.data_stays_local(model)`, `validate_model_name(allow_cloud=False)`.
  Cloud-install confirmation UI deferred to Phase 7. Tests: `tests/test_locality.py` (12), plus offline/install/privacy suites 146 pass.
  Process note: do not `git stash` in this shared checkout (it briefly swept another session's CSS edit; restored intact).
- 2026-11-06, Phase 1.3: `providers/offline_readiness.py` (Ollama: model on disk, not remote, nonzero size; llama.cpp:
  `/health` 503 is not ready, 200 is `unknown` with an `--offline` note). Wired into `validate_offline_route`.
  `tests/conftest.py` autouse fixture disables the probe for other tests (a running dev Ollama broke 6 of them;
  that was the check working). Live run: `~/.hutch-tmp/offline-models-2026-11/evidence/p1-live-readiness.txt`.
  Gates: 68 focused tests pass, `check:agent` pass. Open: LM Studio/vLLM readiness (Phase 2), connect-time address pinning,
  cloud opt-in UI (Phase 7), compat.json/docs wording (Phase 8).

### Phase 2 checkpoints

- 2026-11-06, Phase 2 research: `docs/research/2026-11-offline-models/03-PHASE2-ADAPTERS.md` plus R22-R25
  in `01-FAILURE-MINING.md`; design in `05-PHASE2-DESIGN.md`.
- 2026-11-06, Phase 2.1/2.3: new `providers/local/` package (protocol, bounded probe, llama.cpp,
  LM Studio, OpenAI-generic adapters) and `localchoices.py`. `discovery.py` probes 9931 and 8080,
  fingerprints the response, and reports `needs_key`. Focused tests: `test_provider_discovery.py` (10),
  `test_local_runtimes.py` (17), `test_local_choices.py` (6), plus runtime fallback tests (36 total) pass.
- 2026-11-06, Phase 2.2: `context.py` carries applied/slots/policy; `providers/local/admission.py`
  chooses the measured window; `runtime/builtin.py` shrank from 1955 to 1953 lines. `modelview.py`
  adds measured local-window notes only when a non-Ollama runtime is up.
- 2026-11-06, Phase 2.4: `providers/local/credentials.py` scopes a connection key to the same
  loopback host and port; `pages_providers.py` passes it to discovery. Discovery still sends no
  credential by default and never returns one.
- Decisions: a fixed window is read from the runtime, never requested and assumed; llama.cpp's
  per-request window is `/slots[].n_ctx` (not `-c`); LM Studio's is
  `loaded_instances[].config.context_length` (not `max_context_length`), and a cold model is loaded
  with an explicit fitted window whose applied value is read back. vLLM/SGLang report no window over
  `/v1/models`, so Hutch says unknown and makes no truncation claim. A llama.cpp model id that is an
  absolute `.gguf` path is presented as its basename, which the real server accepts.
- Open: choosing a non-Ollama local model does not set the bot's `base_url` yet (the choice detail
  names the endpoint); the default llama.cpp route endpoint is still 8080 while the stock server is
  9931. Both are Phase 7's picker work. The hardware probe still checks 8080; local choices probe the
  discovery endpoints directly with a 5-second cache.
- Credential store: a local runtime key uses the existing connection key file (0600), the same store
  as provider keys, scoped by origin. The passphrase `VaultBook` is for tool secrets and is not
  used for runtime credentials. No key is written to the database, a URL, a result or a page.
- `src/hutch/data/compat.json` rows for llama.cpp/LM Studio are deferred to Phase 8: adding a
  catalogue row is a public compatibility claim, and Phase 2's evidence is one build on one host.
  The honest documentation lives in `docs/models.md` and `docs/runtime-setup.md` (ADR-0030).
- Phase 2 exit checks: window read equals `/slots` (4096) and LM Studio
  `loaded_instances.config.context_length` (8192); an over-long prompt is refused by `check_prompt`
  and the real server's own 400 is recorded; the 8080 squatter is `runtime=unknown`; the
  `--api-key` server reports `needs_key` and lists models only with the origin-scoped key. Phase 3
  is next.
- 2026-11-06, Phase 2 gates: combined focused suite
  `test_provider_discovery test_local_runtimes test_local_choices test_runtime_builtin
  test_models_layer test_model_switcher test_models_detected_route test_local_admission_runtime
  test_fitloop test_slots` = 201 passed; `tests/e2e/test_model_picker.py` = 12 passed;
  `npm run check:agent` passed (context hygiene, tool contracts, constitution, agent map);
  `scripts/audit_emoji.py` reports only the pre-existing `.codewhale/state` file, not a Phase 2
  file. `/code-review` and `/simplify` are not available in this session; the phase diff was
  re-read manually and the findings above were fixed. Multimodal checks are not applicable in
  Phase 2 (no image path changed); Phase 5 owns them. Services started for evidence were stopped
  and the temporary key file was removed; ports 9931, 9932, 9933, 1234 and 8080 are free.
- 2026-11-06, Phase 2.4 live: `llama-server --api-key-file` on 9933. Without a key discovery returns
  `reachable=true, state=needs_key`; with a key from a temporary connection whose base URL is
  `http://127.0.0.1:9933/v1`, discovery returns `ready`, the model list and runtime `llamacpp`; the
  same key for `http://127.0.0.1:9932/v1` returns nothing. A real chat through
  `provider_for_connection` answered `key-ok` with `context_window=4096`. The key never appeared in a
  discovery result or the answer. The decoy on 8080 answered `/v1/models` with
  `owned_by=organization_owner`: discovery reported `runtime=unknown`, `confidence=unknown`, not
  llama.cpp.
- 2026-11-06, EC-05 needle: `llama-server` on 9932 with qwen2.5-coder:1.5b, 4096 per slot. The
  self-check recalled `KELP-3471-MEADOW` from the top of a 3,346-token prompt in the 4,096-token
  window in 50.2 s (`ok=true, truncated=false`). A first attempt on qwen3-4b with a 64-token cap
  returned an empty answer because thinking consumed the budget (EC-18, Phase 5.4), not because the
  window failed; it is recorded as such and not counted as window evidence.
- 2026-11-06, visual: 20 captures in `docs/realignment/artifacts/offline-models-2026-11/p2-up/`
  (switcher, models, connections, onboarding, local-service at 360/768/1280/1920, dark). Zero
  horizontal overflow, zero page/console errors. Two rows both read `qwen3-4b` with no runtime and
  the LM Studio note implied a slot division; fixed by prefixing the note with the runtime title and
  saying `(parallel 4)` unless `/slots` reports a per-slot value. The models-page notice shows
  "LM Studio reports qwen3-4b loaded at 8,192 tokens (parallel 4)" and "llama.cpp reports qwen3-4b
  loaded at 4,096 tokens per request across 2 slots". Focused `tests/e2e/test_model_picker.py`
  (12) passes; the switcher rows are the existing keyboard-operable menu items and the notes notice
  is `aria-live="polite"`.

### Phase 3 checkpoints

- 2026-11-06, Phase 3 research: `docs/research/2026-11-offline-models/04-PHASE3-LIFECYCLE.md`,
  R26-R32 appended to `01-FAILURE-MINING.md`, design in `06-PHASE3-DESIGN.md`.
- 2026-11-06, Phase 3.1: `providers/local/lifecycle.py` (bounded `observe_load` with measured
  wait, `load_fixed_runtime`), `RuntimeState.sleeping` from llama.cpp `/props.is_sleeping`,
  admission passes `load_ms`/`sleeping`, and the run records the measured load in the existing
  `model_load:` key and `load` event. A LOADING state is no longer cached, so the poll sees the
  transition. Tests: `tests/test_local_lifecycle.py` (9); focused local suites 41 pass.
  `check:agent` passes. Live cold-load evidence pending.
- 2026-11-06, Phase 3.1 review: moved `_exit_reason` to `runtime/outcomes.py` to keep
  `runtime/builtin.py` at its 1,955-line cap; the call site now reads the runtime's state via
  admission and only turns it into a status and a measured event. No behavior claim beyond the
  measured wait.
- 2026-11-06, Phase 3.2: `runtime/outcomes.py` classifies local failures (Ollama's
  `signal: killed`/runner-terminated wrapper, broken streams, 503 loading) into reload-once or
  stop with the cause and fix; partial output is never retried and stays incomplete.
  `lifecycle.ensure_loaded`/`refresh_local_route` re-read the runtime before every local call
  (fixed routes are no longer assumed resident) and reload once; `admission_memory` moved with
  the same measured-allocation rule. `runtime/builtin.py` now 1,942 lines (was 1,955): the
  Ollama-only refresh and memory helpers moved out. Tests: `test_local_failure.py` (17),
  `test_local_lifecycle.py`; focused suites 369 pass. Live kill/restart evidence is below.
- 2026-11-06, Phase 3.3: `providers/local/versions.py` gates Ollama (tools 0.3.0,
  structured outputs 0.5.0, thinking 0.9.0, measured window 0.10.0) and LM Studio (tools
  0.3.6, TTL 0.3.9, native API/tokens 0.4.0); llama.cpp has no invented build floor and its
  build string is recorded in the admission note. `health.py` keeps the Ollama version it
  reads and attaches the upgrade sentence to the runtime card fix that doctor and the Models
  page already render. Tests: `test_local_versions.py` (9); health/models suites 63 pass.
- 2026-11-06, Phase 3.3 decisions: an unknown version gets no advice (LM Studio over HTTP
  exposes no app version; native `/api/v1` presence implies 0.4.0+). The advice names the
  highest required version among the missing features, so one upgrade covers all of them.
  No feature claim is made from a version alone; the runtime's own fields still decide
  (for example `chat_template_caps.supports_tools` on llama.cpp).
- 2026-11-06, Phase 3 live: real Ollama 0.40.13 cold start through the real FastAPI app
  (fresh `HUTCH_STATE_DIR`, ephemeral port): status timeline included `loading_model`, load
  event measured 4.821 s, answer `phase-three-ok`. Real llama.cpp b12144 `/health` 503 body
  captured; admission waited 3.553 s and reported 4096 per request across 2 slots. Real LM
  Studio unload then reload measured 2.905 s at 8192 and answered `reloaded`. Real `kill -9`
  of the Ollama child `llama-server` mid-stream: direct error `Ollama error mid-stream: ...
  unexpected EOF` classified `reload`; a full app run showed `loading_model`, two `load`
  events, and succeeded with an answer. Real `kill -9` and restart of `llama-server`:
  `cannot connect` classified `reload`, restarted server detected, answer `restarted`.
  Evidence JSON under `~/.hutch-tmp/offline-models-2026-11/evidence/p3-*.json`; services
  stopped and ports 11434, 1234, 9931 and 8080 verified free.
- 2026-11-06, Phase 3 gates: the 19-file focused suite passed 369 before the final real-wrapper
  marker fix; after it, the 7-file runtime set passed 201 and `tests/test_local_failure.py`
  passed 17. `npm run check:agent` passed (context hygiene, tool contracts, constitution, agent
  map); `scripts/audit_emoji.py` reports only the pre-existing `.codewhale/state` file, not a
  Phase 3 file. No UI or website change, so the visual gate does not apply; no screenshots are
  claimed. `/code-review` and `/simplify` are not available in this session; the phase diff was
  re-read manually and the findings above were fixed.
- Phase 3 exit checks: EC-09, EC-10, EC-11 and EC-22 are recorded above with real evidence or
  an exact not-run reason; the only deviation is the 4 GB model (budget) and the old-runtime
  upgrade path (no old runtime installed). Phase 3 is done.

Next phase: Phase 4, get a model (install, import, guide): G1 name grammar, G6 disk preflight,
failure and resume, other-runtime decisions, and the real multi-gigabyte pull through the page.
