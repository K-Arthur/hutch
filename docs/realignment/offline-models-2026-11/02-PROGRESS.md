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
| 4 Get a model (install, import, guide) | done (4.1-4.5) | see git log (b32a5e47..) | 2026-11-06: real 1.9 GiB pull cancelled/resumed through the page; real disk-full and no-route pulls; real GGUF import (reuse and upload); four-width captures | Gated HF pull not run (no token); LM Studio/vLLM/SGLang install guided only |
| 5 Multimodal and tool reliability | done (5.1-5.5) | 3a789476..a08009f6 + current-model comparison | 2026-11-06: real Ollama 0.40.13, llama.cpp b12144 + Qwen2.5-VL/Qwen3.5/Gemma 4 projectors, LM Studio 0.0.27-1, real cat photo and Playwright screenshot, sixteen model/runtime benches (2025 baseline and current Qwen3.5/Gemma 4), full-app current-model comparison | Ollama app-level vision blocked for the 2K moondream only; audio/speech not run; vLLM/SGLang not installed; Gemma 4 e4b/12b/26b and Qwen3.5 122B not run |
| 6 Strict Offline live, boundary ADR | done (6.1, 6.2, 6.3) | see git log | 2026-11-06: real Ollama and llama.cpp tool-and-image turns through the broker; airplane test inside `unshare -rn`; shell egress 101; 1,200-token stream; cancel; runner kill; server restart; 64 MiB cap | Managed model process is the accepted ADR-0035 decision, not implemented |
| 7 Frontend | done (7.1-7.5) | 24be8a4c, 35e63905 | 2026-11-06: real Ollama 0.40.13 and llama.cpp b12144; /models at 360/768/1280/1920 in empty, down, ready, cloud-tagged, needs-key, loading, network and offline-in-browser states; grouping/privacy/capability/measured labels live; keyboard focus order and visible focus recorded | install running/cancelled/failed visual recapture reused from Phase 4 (layout unchanged), upgrade-needed not run (no older runtime), tab-strip overlap pre-existing
| 8 Website and docs | not started | | | |
| 9 Final review and merge | not started | | | |

Phase 0 exit checks: baseline (`docs/research/2026-11-offline-models/00-BASELINE.md`),
failure mining (`01-FAILURE-MINING.md`) and API notes (`02-RUNTIME-API-NOTES.md`) written;
gap reproductions recorded; gates run; backlog ordered in the failure-mining doc; batched
owner questions answered (LM Studio: yes; download budget: not exceeded).

## Gap status (G-IDs from the master prompt)

| ID | Reproduced on real stack | Fixed in | Evidence row |
|---|---|---|---|
| G1 install name grammar | 2026-11-06, 6 of 10 real forms refused | Phase 4.1: `providers/model_names.py`; `model_install.validate_model_name` delegates | `tests/test_model_names.py` (real names), commit b32a5e47 |
| G2 cloud-tag locality | 2026-11-06, renamed cloud copy classified local; UI says "On this machine" | Phase 1: `providers/locality.py` (server signal first), live rows below | `baseline-up/up-switcher-1280-dark.png`; Phase 1 checkpoints |
| G3 local group only for Ollama | 2026-11-06, llama.cpp reachable but `_local_choices` returned `[]` | Phase 2.3: `localchoices.py`, both real runtimes now produce `On this machine` rows | live choices run below |
| G4 no native introspection | 2026-11-06, `rg` empty; real `/props`, `/slots`, `/api/v1/models` fields recorded | Phase 2.1: `providers/local/` adapters | live adapter run below |
| G5 Strict Offline never live | 2026-11-06, real broker with real Ollama and llama.cpp | Phase 6.1/6.2: real governed tool-and-image runs, airplane test, egress attempt, failure modes; ADR-0035 for the managed server | `~/.hutch-tmp/offline-models-2026-11/evidence/p6/*.json`; Phase 6 checkpoints |
| G6 no disk preflight, no real big pull | 2026-11-06, `rg` empty | Phase 4.2/4.3: `providers/install_plan.py`, server-side gate, measured rate; `install_errors.py`; real pull/cancel/resume, disk-full and no-route rows below | `~/.hutch-tmp/offline-models-2026-11/evidence/p4-pull-page.json`, `p4-disk-full.ndjson`, `p4-network-drop.ndjson`; commits 45af9d1b and later |
| G7 port-trust discovery, key-protected servers | 2026-11-06, decoy on 8080 labelled llama.cpp; real `--api-key` server reported "no service answered" | Phase 2.1/2.4: response fingerprint, 9931 candidate, `needs_key` | decoy and key test below |
| G8 frozen files not grown | confirmed 2026-11-06: 433/432/447/1955 against caps 435/432/466/1955 | Phase 9 recheck | `.file-size-baseline.json` |

## Edge-case status

Track by ID from `03-EDGE-CASES.md`: tested-real, tested-fault-injected, documented, not-run (reason),
or out-of-scope (reason). One line per ID once touched.

- EC-01: tested-real; fixed Phase 1: real Ollama refuses `gpt-oss:20b-cloud` and renamed copy `my-local-copy` via `remote_host`.
- EC-02: fault-injected/unit only (addresses resolved, not spelling; `tests/test_locality.py`); not-run live: no second interface or hosts entry. Address is checked at validation, not pinned at connect time (open, Phase 6).
- EC-03: documented; llama.cpp `--offline` found, launch flags invisible so readiness is `unknown`, never a pass (vendor docs: Ollama cloud/remotes, LM Studio catalog/JIT, llama.cpp `-hf`).
- EC-04: tested-real, Phase 6: a complete governed tool-and-image turn ran with the app, Ollama 0.40.13 and the worker inside one `unshare -rn` namespace (only loopback up); an external connect from that namespace returned 101; the worker's own netns had only `lo` and no route; the run succeeded in 138.3 s. Evidence `evidence/p6/image-tool-airplane1.json` and `airplane-host-egress.txt`.
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
- EC-15: tested-real; fixed Phase 4.1: `tests/test_model_names.py` covers the runtime's grammar and the real `hf.co` forms; `qwen2.5-coder:3b` installed through the page; a local GGUF was imported with the runtime's own `/api/blobs` + `/api/create` path and `/api/show` reported the family, quant, tools/thinking capabilities. The remaining Modelfile-specific case (a custom template in a created model) is covered by the same create API but not with a hand-written Modelfile this pass.
- EC-16: tested-real, Phase 5.1: llama.cpp b12144 Qwen2.5-VL-3B + Q8_0 mmproj answered `Cat` for a real 640 px photo, `"Models"` for a real Playwright capture, `image 1` for a two-image message, and described a WebP photo; image-plus-tool returned `describe_scene(animal="cat", colour="orange")` with a disclosed merged template. Ollama moondream described the cat through the native provider (741 prompt tokens); its 2,048-token window is refused by the app (4,096 floor). LM Studio qwen2.5-vl answered the screenshot and accepts PNG/JPEG; WebP is refused before sending. A text model was refused before send. Oversize (3.5 MB) was refused at admission. Current-model rerun: Gemma 4 e2b answered all three full-app image cases (`cat`, `Models`/`Route readiness`, `Image 1`), Qwen3.5 4B 2/3, Qwen3.5 2B 1/3, Qwen3.5 0.8B 0/3; Gemma 4 and Qwen3.5 2B also produced stock-template image+tool calls on llama.cpp, and LM Studio Gemma vision worked after the projector was named `mmproj-gemma4-e2b.gguf`.
- EC-17: tested-real, Phase 5.3: sixteen model/runtime benches, 3 trials per probe, no recall. Baseline real causes: `no_call`, `call_in_content` (15/15 for llama.cpp qwen2.5-coder-3b: a complete call body in `content`, `tool_calls` null), `wrong_answer`, `ignored_result`, `wrong_arguments`. Current-model causes: Ollama all four 15/15; llama.cpp Gemma 4 e2b 11/15 (`call_in_content` 3 on tool choice, `no_call` 1 on argument types); LM Studio Gemma 4 e2b 12/15 (`reasoning_only` 3 on argument types). The same model scores differently per runtime, and the isolated bench does not predict the full-app result: Qwen3.5 2B passes 15/15 but answers 1/3 full-app image cases. No text-to-call repair was added.
- EC-18: tested-real, Phase 5.4: real Ollama qwen3:4b with `think: true`, tools and 32 output tokens returned `done_reason: length`, empty content and 147 characters of thinking; the result note says the output limit was reached while reasoning and names the fix. The OpenAI-shaped path already had the equivalent note; the native Ollama path now shares it. llama.cpp qwen3-4b at the default budget ran at ~3.9 tokens/s and did not finish four probes in ten minutes; not a third-trial result. Current-model rerun: llama.cpp Qwen3.5 2B with the default thinking budget returned `length` and empty content for 20-120-token image probes; `--reasoning-budget 0` produced `cat`, `Models`, `image 1`, and a clean `describe_scene` call. LM Studio Gemma 4 e2b's default reasoning produced three `reasoning_only` bench trials at the 256-token cap; Ollama sends `think=False` and scored 15/15.
- EC-19: tested-real, Phase 6: the airplane turn (chat, file and shell tools) ran with no external route; a shell `connect_ex(("1.1.1.1", 53))` returned 101; the code audit still finds no `/v1/embeddings` client and no hosted embedding call in the chat, memory or search path; `synthesis/model.py` uses the chat route. LM Studio exposes `/v1/embeddings`, but no Hutch feature requests it for a local assistant.
- EC-21: tested-real on this host (Ollama drops the iGPU; see `02-RUNTIME-API-NOTES.md`).
- EC-20: tested-real for integrity and rights: a wrong expected SHA-256 is refused before any upload (`tests/test_model_import.py`); the runtime's blob endpoint verifies the digest again; the imported qwen3-4b GGUF carried the provided Apache text and `/api/show` returned tools/thinking; the 1.93 GB vision upload created a blob, and removing the test model removed that blob while the source file's hash stayed unchanged. Not run: a gated Hugging Face repository (no token).
- EC-23: tested-real; fixed Phase 4.2/4.3: the plan named `~/.hutch-tmp/localmodels/models` and 70.4 GiB free; a real pull into a 300 MiB tmpfs failed at 309,451,728 of 1,929,903,008 bytes with `no space left on device`; cancel left the runtime's partial files and the resumed job started at 46,717,902 bytes rather than zero; removing the imported model left `qwen3:4b` intact.
- EC-25: partially addressed in Phase 5. The catalog now carries the measured current rows (`qwen3.5:0.8b`, `qwen3.5:2b-q4_K_M`, `qwen3.5:4b-q4_K_M`, `gemma4:e2b`) and the presets prefer them; sizes/capabilities were read from the live Ollama library and `/api/show` on 2026-11-06. Not run: an automated live-tag refresh and the larger Gemma 4/Qwen3.5 tags; the catalog is still a dated suggestion list, not a promise.
- EC-27: documented, Phase 5.2: llama.cpp accepts `input_audio` with a compatible audio model; Ollama exposes `/v1/audio/speech` with Phonon (WAV/PCM, 4,096 characters); LM Studio has no documented audio input. No audio or speech model was retained, so no local audio run was made and none is claimed.
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
| 2026-11-06 | Ollama 0.40.13 | `qwen2.5-coder:3b`, catalog 1.9 GiB, installed model digest `f72c60cabf62...`, 1,929,912,626 bytes | Ryzen 3 5300U, CPU | real FastAPI app (fresh `HUTCH_STATE_DIR`), `OLLAMA_MODELS=~/.hutch-tmp/localmodels/models`, Chromium, `/models`; `p4_pull_page.py` | plan, Confirm, running, page reload mid-run, second tab, cancel at 44,076,255 bytes, resume at 46,717,902 (not zero), done; job flags; screenshots | the 4 GB class (budget) | plan: 2,040,109,465 bytes, 75,594,895,360 free, `OLLAMA_MODELS`, fits at 16,384, ETA unknown; job 92.3 s (script total 106.3 s); `show` license Qwen Research, capabilities completion/tools/insert; zero page/console errors, zero overflow; evidence `p4-pull-page.json` |
| 2026-11-06 | Ollama 0.40.13 | `qwen3:1.7b`, catalog 1.4 GiB, installed model digest `8f68893c685c...`, 1,359,293,444 bytes | same | same page; `p4_second_pull.py` | running at 8,770,496 bytes, cancel at 56,098,762, resume to done; four-width running/cancelled/resumed cell captures | — | `resumed=true`; job 73.1 s (script total 82 s); zero page/console errors; evidence `p4-second-pull.json` |
| 2026-11-06 | Ollama 0.40.13 | `qwen2.5:3b` (no catalog row) | same | `unshare -rm` + 300 MiB tmpfs; Ollama on 127.0.0.1:11500; `/api/pull` | real disk-full pull | — | failed at 309,451,728 of 1,929,903,008 bytes: `write ...-partial: no space left on device`; classifier `disk_full`, action `free_space`; evidence `p4-disk-full.ndjson` |
| 2026-11-06 | Ollama 0.40.13 | `qwen2.5:3b` (no catalog row) | same | `unshare -rmn`, loopback up, no external route; Ollama on 127.0.0.1:11501; `/api/pull` | real network-drop pull | — | `pull model manifest: Get "https://registry.ollama.ai/...": dial tcp ...: connect: network is unreachable`; classifier `network`, action `retry`; evidence `p4-network-drop.ndjson` |
| 2026-11-06 | Ollama 0.40.13 | `qwen3-4b.gguf`, 2,497,280,480 bytes, sha256 `3e4cb1417446...` | same | real app, `POST /api/models/import`; `p4_import_evidence.py` | wrong expected digest refused; existing blob reused (`HEAD` hit, no upload); `/api/create`; `/api/show` license and capabilities; remove imported model | a hand-written Modelfile with a custom template | wrong digest 422; import 7.22 s total; license text shown; capabilities tools/thinking/completion; `qwen3:4b` survived the remove; evidence `p4-import.json` |
| 2026-11-06 | Ollama 0.40.13 | `Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf`, 1,929,901,056 bytes, sha256 `d02fe9b69ad8...` | same | real app, `POST /api/models/import`; `p4_import_upload.py` | `HEAD` miss, real streamed 1.93 GB `POST /api/blobs`, create, remove | vision inference on the imported model | upload 4.246 s; blob 1,929,901,056 bytes created and removed with the test model; source hash unchanged; license shown as none; evidence `p4-import-upload.json` |
| 2026-11-06 | Chromium (Playwright) | real plan panel and status cells | same | captures under `docs/realignment/artifacts/offline-models-2026-11/p4-install/` | plan panel at 360/768/1280/1920; running/cancelled/resumed cells and full pages; images viewed | the full state matrix (runtime down, loading, needs-key, failed visual; Phase 7) | zero horizontal overflow and zero console errors; defects found: duplicated "time unknown", clipped nowrap panel, clipped pull hint; fixed by a full-width plan row, a width cap, and wrapped state/hint text; re-captured |
| 2026-11-06 | Ollama 0.40.13 | `moondream:1.8b-v2-q3_K_S` digest `c1f516864beb`, 1.6 GB, capabilities completion/vision | Ryzen 3 5300U, CPU | `OLLAMA_MODELS=~/.hutch-tmp/localmodels/models ollama pull moondream:1.8b-v2-q3_K_S`; real `OllamaProvider` chat, `num_ctx=2048` | pull, `/api/show`, native and provider chat with a real 640 px cat photo; text model `qwen3:0.6b` refused vision | the app-level run (model below the 4,096 floor); multi-image (model returned 1 token) | 741 prompt tokens; caption `ginger cat ... orange`; `supports_vision` true for moondream, false for qwen3:0.6b; evidence `p5-ollama-vision.json` |
| 2026-11-06 | Ollama 0.40.13 | `Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf`, 1,929,901,056 bytes, sha256 `d02fe9b69ad8...` + 844,757,728-byte mmproj | same | `ollama create p5-vl-import -f Modelfile.p5-vl` with `FROM <the text GGUF>` | real import of a vision GGUF without a projector path | vision inference on the import | `/api/show` returned `capabilities: ["completion"]`, `families: ["qwen2vl"]`, `projector_info: null`; model removed; F18 reproduced |
| 2026-11-06 | llama.cpp b12144-69ee2ecc0 (CPU) | Qwen2.5-VL-3B Q4_K_M + Q8_0 projector | same | `llama-server -m models/vision/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf --mmproj models/vision/mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf -c 8192 -t 8 --jinja --host 127.0.0.1 --port 9931` | `/props.modalities.vision`, real `/v1/chat/completions` with a 640 px cat photo, two images, WebP; second server on 9932 with a merged tool template | GPU, video | cat `Cat` 562 prompt tokens; two images `image 1` 592 tokens; WebP cat description; image+tool `describe_scene(animal="cat", colour="orange")` 729 prompt tokens, 42.866 s; evidence `p5-llamacpp-vision.json`, `p5-llamacpp-image-tool.json` |
| 2026-11-06 | LM Studio llmster 0.0.27-1 | qwen2.5-vl (Qwen2.5-VL-3B + mmproj, 2,774,658,784 bytes), capabilities vision true / trained_for_tool_use false | same | `lms import -L`, projector in the model folder, `lms server start --port 1234`; real `/v1/chat/completions` with PNG, JPEG and WebP data URIs | `/api/v1/models`, `supports_vision` via the local adapter, PNG/JPEG accepted | API-token mode | PNG icon `number 31 ... blue background`; JPEG cat description; WebP returned 400 `'url' field must be a base64 encoded image`; evidence `p5-lmstudio-vision.json` |
| 2026-11-06 | FastAPI app (this checkout), fresh `HUTCH_STATE_DIR`, uvicorn 127.0.0.1:8765 | real llama.cpp/LM Studio/Ollama routes | same | `p5_app_pipeline.py`: bot create, conversation, `POST .../uploads`, `POST .../messages` with `image_attachment_ids`; real Playwright capture of `/models` | composer upload, admission, wire conversion, answer, media transmission record; cat, screenshot, two images, WebP, oversize | Ollama app-level vision (2K floor) | llama.cpp: `Cat` 73.3 s, `"Models"` 146.0 s, `image 1` 188.0 s, WebP cat 81.9 s, 3.5 MB image refused with the 1.5 MB limit; LM Studio PNG `Models` section 35.6 s, WebP refused in 0.099 s; text model refused in words; media `transmitted: 1`; evidence `p5-app-pipeline.json` |
| 2026-11-06 | Ollama 0.40.13 | qwen3:0.6b (15/15), qwen2.5-coder:1.5b (6/15), qwen3:4b (13/15) | same | `HUTCH_STATE_DIR=... hutch models bench <model> --no-recall -n 3 --ctx 8192` | 3 trials of 5 tool probes; causes; memory refusal for the 2K vision model | recall probe (Phase 2 needle evidence) | 43.5 / 15.3 / 7.6 tokens/s; verdicts reliable / unreliable / unreliable; causes `no_call`; files `bench-ollama-*.txt` |
| 2026-11-06 | llama.cpp b12144 (CPU) | qwen3-0.6b (15/15), qwen2.5-coder-1.5b (1/15), qwen2.5-coder-3b (0/15) | same | `hutch models bench <model> --provider llamacpp --base-url http://127.0.0.1:9931/v1 --no-recall -n 3 --ctx 8192` | 3 trials of 5 probes; `call_in_content` on 15/15 coder-3b trials | qwen3-4b 3-trial run (default reasoning at ~3.9 tokens/s exceeded 10 min; see EC-18) | reliable / unreliable / unreliable; coder-3b bodies were complete calls with `tool_calls: null`; files `bench-llamacpp-*.txt` |
| 2026-11-06 | LM Studio 0.0.27-1 | qwen3-0.6b (15/15), qwen2.5-coder-1.5b (3/15), qwen2.5-vl (6/15) | same | `hutch models bench <model> --provider lmstudio --base-url http://127.0.0.1:1234/v1 --no-recall -n 3 --ctx 8192` | 3 trials of 5 probes; JIT loads; causes | API-token mode; GPU | reliable / unreliable / unreliable; `no_call` 9, `wrong_answer` 3; files `bench-lmstudio-*.txt` |
| 2026-11-06 | Ollama 0.40.13 | qwen3:4b | same | `OllamaProvider.chat(ChatRequest(..., think=True, max_tokens=32, tools=[read_file]))`; real provider | reasoning-only turn with a tool list | a full app run with thinking on | `finish_reason=length`, content `""`, 147 thinking chars, 32 completion tokens; note names the output limit and the fix; evidence in the EC-18 row |
| 2026-11-06 | Ollama 0.40.13 | `qwen3.5:0.8b` 1.3 GB Q8_0; `qwen3.5:2b-q4_K_M` 1.9 GB; `qwen3.5:4b-q4_K_M` 3.3 GB; `gemma4:e2b` 4.6 GB | Ryzen 3 5300U, CPU | `ollama pull` each; `hutch models bench <model> --no-recall -n 3 --ctx 8192` | 3 trials of 5 probes; capabilities vision/tools/thinking (Gemma also audio) | larger Gemma 4 and Qwen3.5 122B | all 15/15; 12.7 / 13.6 / 4.8 / 9.8 tokens/s; `bench-ollama-*.txt` |
| 2026-11-06 | llama.cpp b12144 (CPU) | `qwen3.5-2b.gguf` 1,274,396,992 bytes + 671,372,768-byte projector; `gemma4-e2b.gguf` 3,502,493,472 + 986,833,664-byte projector | same | `llama-server -m ... --mmproj ... -c 8192 -t 8 --jinja [--reasoning-budget 0]`; `hutch models bench ... --provider llamacpp` | stock template vision+tools, tool bench, real image+tool | GPU | Qwen3.5 2B 15/15; Gemma 4 e2b 11/15 (tool choice 0/3, three calls left as text); both image+tool calls clean; `bench-llamacpp-*.txt` |
| 2026-11-06 | LM Studio 0.0.27-1 | `gemma4-e2b` (projector named `mmproj-gemma4-e2b.gguf`), vision/tools true | same | `lms import -L`, projector rename, `lms server restart`; real `/v1/chat/completions`; `hutch models bench ... --provider lmstudio` | cat and screenshot vision, WebP refusal, tool bench | audio | cat `Cat`; screenshot `Models`; WebP 400; tool bench 12/15 (argument types 0/3, three `reasoning_only` turns); `bench-lmstudio-gemma4-e2b.txt`, `p5-lmstudio-gemma4-e2b-vision.json` |
| 2026-11-06 | FastAPI app (this checkout), fresh state, uvicorn 8765 | current Ollama models at an 8,192-token vision preset | same | `p5_current_model_app.py`: real upload + message + polling, real cat photo and Playwright screenshot | full-app image comparison: cat, screenshot, two images | full-app text-only; 0.8B at 8K | Gemma 4 e2b 3/3 (56-96 s); Qwen3.5 4B 2/3 (100-205 s); Qwen3.5 2B 1/3 (62-76 s); Qwen3.5 0.8B 0/3 at 4K (two-image window refusal); `p5-app-*.json` |
| 2026-11-06 | Ollama 0.40.13 | gemma4:e2b, 4.59 GB, digest b3704936... | Ryzen 3 5300U, CPU | real app on an ephemeral loopback port, fresh `HUTCH_STATE_DIR`, offline bot `ollama/gemma4:e2b`, tools files+shell; `p6.py image-tool` | real 121,766-byte cat JPEG, per-run broker, `write_file` and `shell`, status timeline, worker `/proc/<pid>/net` | GPU; LM Studio | succeeded 97.7 s; answer "cat", byte count 3; `animal.txt` = "cat"; `wc -c` = 3; image count 1; context 1,840/16,384; worker netns differed, only `lo`, no route; `evidence/p6/image-tool-live4.json` |
| 2026-11-06 | Ollama 0.40.13 | gemma4:e2b | same | offline bot; prompt to run `socket.connect_ex(("1.1.1.1", 53))` via the shell tool; `p6.py egress` | real tool call, sandboxed shell egress | hosted calls | tool result `connect_ex 101`; run succeeded 88.2 s; `evidence/p6/egress-live1.json` |
| 2026-11-06 | Ollama 0.40.13 | gemma4:e2b | same | app, Ollama and the worker inside one `unshare -rn` (only `lo` up); `p6.py image-tool --start-ollama`; separate host egress probe | the same image-and-tool turn; external connect from that namespace | — | succeeded 138.3 s; `loading_model` visible; external connect 101; airplane netns 4026532826, worker netns 4026532886; only `lo`, no route; `evidence/p6/image-tool-airplane1.json`, `airplane-host-egress.txt` |
| 2026-11-06 | Ollama 0.40.13 | qwen3:0.6b | same | `OfflineBrokerSet` plus real `/api/generate`, `num_predict 1200`, `stream: true`; `p6.py broker-stream` | chunked streaming through the broker | the app path | HTTP 200; 1,202 chunks, 131,695 bytes; `eval_count` 1200; `done_reason: length`; `evidence/p6/broker-stream-live1.json` |
| 2026-11-06 | Ollama 0.40.13 | gemma4:e2b | same | real app, stop while running; `p6.py cancel` | stop request, worker termination, status timeline | partial text | stopped to terminal in 0.304 s; worker exited -15; `running, cancelling, stopped`; `evidence/p6/cancel-live1.json` |
| 2026-11-06 | Ollama 0.40.13 | gemma4:e2b, qwen3:0.6b | same | broker unlink before and after a call, 64 MiB+1 request, real runner kill, real server kill/restart; `p6.py broker-missing, provider-after-loss, oversize, runner-kill, server-restart` | real broker, real runtime, real faults | managed server | before: "broker is missing, no direct network fallback"; after: bridge message, action stop; 413 for 64 MiB+1; runner kill reloaded in 8.65 s and completed; server restart 502, one reload, then "model ... is no longer installed", clear stop; `evidence/p6/*.json` |
| 2026-11-06 | llama.cpp b12144-69ee2ecc0 (CPU) | Gemma 4 e2b 3.50 GB + 0.99 GB projector, 8192 per slot | same | `llama-server -m ... --mmproj ... -c 8192 --parallel 1 --jinja --reasoning-budget 0 --offline`; bot `llamacpp/gemma4-e2b`; `p6.py llamacpp` | real image-and-tool turn, broker, `/props` and `/slots` through the broker | GPU; LM Studio offline | succeeded 190.9 s; answer cat/3; context 2,257/8,192; `evidence/p6/llamacpp-live2.json` |

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

- 2026-11-06, Phase 4: the install grammar is the runtime's own (`types/model/name.go`), not a
  lowercase slug: mixed case, registry hosts and ports, namespace/model/tag, and the real
  `hf.co` quant/filename tags. Defaults are stripped only for display and equality is
  case-insensitive. A pinned `@sha256:` suffix is passed through; the runtime decides support.
- 2026-11-06, Phase 4: preflight blocks only what it can prove. Size is the catalog figure or
  unknown; free space is read only from `OLLAMA_MODELS` or the documented default and only for
  a loopback runtime; the 512 MiB reserve is shown; ETA exists only after a measured transfer
  (stored in `install_speed.json`). A known insufficient size is refused on both the read and
  write paths; unknown values stay warnings.
- 2026-11-06, Phase 4: cancel closes the pull stream and resume re-requests the pull. The copy
  says "the runtime keeps verified parts" only after a prior attempt received bytes; it never
  promises a restart resume (R36/R37). The runtime's `-partial` file is preallocated to the
  blob size, so the job's byte counters, not the file size, are the resume evidence.
- 2026-11-06, Phase 4: a Hutch restart loses the in-process job record; the page says so and
  asks to press Install again. A page reload and a second tab reattach to the live job, and a
  duplicate start returns the same job instead of an error.
- 2026-11-06, Phase 4: install failures are classified from the runtime's text into one code
  and one action (disk full, network, runtime down, auth/gated, name, integrity, interrupted);
  credential-shaped substrings are redacted before the text is stored or shown.
- 2026-11-06, Phase 4: local import is single-file only and uses the runtime's own blob/create
  APIs. A split shard is refused with the merge hint, a wrong expected SHA-256 is refused
  before upload, a sidecar/provided license is shown, and a missing license is shown as missing.
- 2026-11-06, Phase 4: LM Studio, llama.cpp and vLLM/SGLang are guided paths, not Hutch jobs
  (no cancel/catalog API or no request-time download). ADR-0031 records the boundary.
- 2026-11-06, Phase 4: the real page pull used `qwen2.5-coder:3b` because it is the
  catalog-backed 1.9 GiB suggestion with a real Install button; `qwen2.5:3b` has no catalog
  row. `qwen3:1.7b` repeated the visual states. The new download footprint is 1.9 + 1.4 GiB
  plus about 0.3 GB in the failed tmpfs; the 10 GB budget is not exceeded and both installed
  models are retained for Phase 5.
- 2026-11-06, Phase 4: `src/hutch/data/compat.json` is unchanged. A catalogue row is a public
  compatibility claim and this phase's evidence is one host; Phase 8 owns the row, as Phase 2
  decided.
- 2026-11-06, Phase 4 visual: the plan is a full-width table row, not content in the narrow
  nowrap install cell, with a 720 px readable cap. The state span and the "or run" hint wrap
  in the cell. No template or CSS file changed; the styles are applied by the install script.

- 2026-11-06, Phase 5: vision capability is a runtime signal, not a model-name table. Ollama
  `/api/show`, llama.cpp `/props` + input modalities, and LM Studio `/api/v1/models` are the
  sources; an unreadable runtime is a refusal, never a guess.
- 2026-11-06, Phase 5: any `*.gguf` model id from llama-server is presented as its basename
  (relative or absolute path). The live app run exposed that only absolute paths were shortened,
  so Hutch rejected its own route until this was fixed.
- 2026-11-06, Phase 5: an image costs a bounded 800-token block in planning and compaction. A
  list body is never measured by `str(content)`: the first live app run turned a 121 KB JPEG into
  ~52,000 fake tokens and blocked a fitting request. Protected user anchors keep user text only.
- 2026-11-06, Phase 5: LM Studio 0.0.27-1 refuses a WebP data URI. Hutch refuses WebP on that
  named route before sending and does not re-encode the user's image; PNG and JPEG are accepted.
- 2026-11-06, Phase 5: Ollama GGUF import is not a vision path. The create call succeeds but the
  external mmproj is not attached (`capabilities: ["completion"]`). The guide says to pull a
  vision model.
- 2026-11-06, Phase 5: the tool bench names causes and never repairs a call-shaped text into a
  call. `call_in_content` is counted as an integration/parser cause; missing ids are recorded;
  duplicate ids are already rejected by the runtime.
- 2026-11-06, Phase 5: a reasoning-only turn with `finish_reason=length` gets one note naming the
  output budget and the fix. Hutch does not automatically retry with a different budget, and the
  native Ollama result folding now shares the note with the OpenAI-shaped path.
- 2026-11-06, Phase 5: the tool bench sends `think=False` where the runtime accepts it. LM
  Studio's OpenAI-compatible surface has no thinking toggle, so a reasoning-only result there is
  disclosed per model rather than hidden.
- 2026-11-06, Phase 5: the Qwen2.5-VL image-plus-tool probe used a local merge of llama.cpp's
  Qwen2.5 tool template and the model's vision loop. That is a test configuration, not a
  vendor-shipped template; the stock model reports `supports_tools: false`.
- 2026-11-06, Phase 5: a 2,048-token vision model is not admitted to the app (4,096-token agent
  floor). The floor was not lowered for Phase 5; the direct provider path proves the vision wire
  and the app refusal is the recorded state.
- 2026-11-06, Phase 5: audio/speech and a local embedding route are deferred. No model was
  retained, no Hutch seam was exercised, and nothing is claimed.
- 2026-11-06, Phase 5: the owner approved pulling current models beyond the original 10 GB
  download cap. New downloads: `qwen3.5:0.8b` 1.3 GB, `qwen3.5:2b-q4_K_M` 1.9 GB,
  `qwen3.5:4b-q4_K_M` 3.3 GB, `gemma4:e2b` 4.6 GB (11.1 GB). Total footprint is about
  20.4 GB of a now-extended budget. No further download without asking.
- 2026-11-06, Phase 5 current-model comparison: on Ollama, all four current models passed
  15/15 isolated tool probes (Gemma 4 e2b 9.8 tokens/s, Qwen3.5 2B 13.6, Qwen3.5 0.8B 12.7,
  Qwen3.5 4B 4.8). On llama.cpp, Qwen3.5 2B also passed 15/15 and Gemma 4 e2b passed 11/15
  (tool choice 0/3, three calls left as text). On LM Studio, Gemma 4 e2b passed 12/15
  (argument types 0/3, three reasoning-only turns). The full-app image comparison separated
  them: Gemma 4 e2b 3/3, Qwen3.5 4B 2/3, Qwen3.5 2B 1/3, Qwen3.5 0.8B 0/3. The old
  Qwen2.5-VL baseline was also 3/3 but took 73-188 s per run.
- 2026-11-06, Phase 5 model choice: Gemma 4 e2b is the current full-multimodal winner on this
  host (4.6 GB, 131k context, vision/tools/thinking/audio, stock vision-plus-tool template on
  llama.cpp). Qwen3.5 2B Q4 is the lightweight tool/router choice (1.9 GB, 15/15 in isolation)
  but not a full multimodal agent. Qwen3.5 4B is slower and less accurate than Gemma in the full
  app; Qwen3.5 0.8B is isolated-probe only. The old qwen3:0.6b remains the fastest tiny tool
  model (43.5 tokens/s) but is not the current recommendation. `catalog.json` and `presets.json`
  now carry the measured current rows; the benchmark is one host and the choices remain
  suggestions, not support claims.
- 2026-11-06, Phase 5 LM Studio projector: LM Studio pairs a vision projector only when the file
  is named `mmproj-<model>.gguf` and the server is restarted. An arbitrary name (`gemma4-e2b-mmproj.gguf`)
  was listed as a separate CLIP model and the chat model reported `vision: false`; renaming fixed
  it. This is a setup requirement, recorded in `docs/runtime-setup.md`.

- 2026-11-06, Phase 6: a host with only loopback is already offline; the egress probe now
  always tests a loopback listener and adds non-loopback targets only when interfaces exist,
  and the worker must still fail to reach the host's loopback. `sandbox.py` stays at 640
  lines (baseline 641); `tests/test_offline_airgap.py`; commit e26241e4.
- 2026-11-06, Phase 6: the offline broker canonicalizes the worker's HTTP client origin
  without rewriting `provider.base_url`; otherwise the reviewed-route check sees a changed
  endpoint and refuses a healthy local route. `tests/test_offline_provider_identity.py`.
- 2026-11-06, Phase 6: local runtime introspection (`/health`, `/props`, `/slots`,
  `/v1/models`) uses the per-run broker inside an Offline worker. A direct TCP probe is
  blocked by the worker namespace; the first llama.cpp live attempt reproduced that refusal.
  `tests/test_local_probe_offline.py`.
- 2026-11-06, Phase 6: a broker connect failure in an Offline worker is its own state
  (action stop, "Strict Offline's model bridge is unavailable... the model runtime itself may
  still be running"). A broker 502 "loopback model service did not answer" gets one reload;
  a self-check interrupted by the runtime is a runtime failure, not a context failure.
- 2026-11-06, Phase 6: the owner chose the Hutch-managed isolated model process. ADR-0035
  records the decision, the Unix-socket bridge and the conditional claim; it is **not
  implemented**. Until it ships the claim is the worker boundary, and no UI or site text may
  say the model server is isolated.
- 2026-11-06, Phase 6: the server-restart live run reloaded once, but the restarted Ollama
  had not re-listed `gemma4:e2b`, so the reload failed with "model ... is no longer
  installed". That is a clear stop; a wait-for-runtime-ready refinement belongs to the
  managed-process lifecycle work.
- 2026-11-06, Phase 6: LM Studio was not driven through the Offline worker. Its adapter
  shares the OpenAI-compatible broker path proven live with llama.cpp; ADR-0035 keeps LM
  Studio ineligible for the managed process until it offers a documented headless launch.
- 2026-11-06, Phase 6: the self-check cache is keyed by the applied window. A warm-up at
  14,348 tokens did not cover a later 16,384-token run, so a kill landed in the self-check;
  this is recorded rather than hidden. The mislabel is fixed and the main-path kill was
  re-run with a matching primer.

## Owner questions (ask once, batched)

Answered in Phase 0:

- Permission to install LM Studio: **yes**, installed if obtainable (llmster used).
- Download budget beyond 10 GB: **approved in Phase 5** for the current-model comparison.
  New downloads were 11.1 GB (four models), bringing the footprint to about 20.4 GB.

Answered in Phase 6:

- Boundary decision: **Hutch-managed isolated model process**. ADR-0035 records the
  decision, the constraints and the implementation plan. It is not implemented; the claim
  stays at the worker boundary until a dated managed-process test exists.

Still open (ask at the phase that needs it):

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

- 2026-11-06, Phase 4 review: the first real panel view showed the preflight in a narrow
  nowrap table cell: the model-directory path and warnings were clipped at every width, and
  the "download time unknown" sentence was duplicated between the facts and the warning list.
  Fixed by rendering the plan as a full-width table row, capping it at a readable 720 px,
  wrapping the summary/warnings, and removing the duplicate warning; re-captured and viewed.
- 2026-11-06, Phase 4 review: the running/cancelled text and the secondary "or run" hint sat
  in the same nowrap cell and clipped at 360. The install cell now wraps its state span, hint
  and code text; the 360 re-capture shows the full hint (`scrollWidth == clientWidth`).
- 2026-11-06, Phase 4 review: `model_install.py` reached 407 lines and
  `import_local_model` 66 lines, and `_read_events` was unused. Split the job record and
  event folding into `providers/install_jobs.py`, split the import into focused helpers, and
  removed the dead reader. Current files: `model_install.py` 249, `install_jobs.py` 158,
  `model_import.py` 235, `install_plan.py` 229, `install_errors.py` 134, `model_names.py`
  127; no Python function over 60 lines.
- 2026-11-06, Phase 4 review: the runtime preallocates the `-partial` blob file to the full
  blob size, so its file size is not progress. The resume evidence uses the job byte
  counters (44,076,255 cancelled -> 46,717,902 resumed) and this is recorded rather than
  inferring progress from the filesystem.
- 2026-11-06, Phase 4 review: no credential reaches a job, page, result or log. The captured
  sign-in URL with `key=...` is redacted in the classifier, the import's runtime error is
  redacted, and the import response contains no token. The endpoint requires CSRF and
  rejects non-GGUF, split, missing and cloud-tagged inputs before touching the runtime.
- 2026-11-06, Phase 4 gates: the 7-file unit/API set passed 145; `tests/e2e/test_model_install.py`
  passed 3 (install, cancel, keyboard preflight with a visible 2 px focus ring); `npm run check:agent` passed (context
  hygiene, tool contracts, constitution, agent map); `npm run audit:context` passed;
  `scripts/audit_emoji.py` reports only the pre-existing `.codewhale/state` file, not a
  Phase 4 file. `/code-review` and `/simplify` are not available in this session; the phase
  diff was re-read manually and the findings above were fixed.

- 2026-11-06, Phase 5 review: the first real whole-app image run blocked a fitting request
  with "the next request (~52,446 tokens)". `fitloop._message_tokens` was measuring a list
  body with `str(content)`, which turns a 121 KB JPEG's base64 into ~50k fake text tokens.
  Fixed by exposing `context.content_tokens` and using it in both estimators; protected
  compaction anchors now keep only user text. Regression tests use a 200 KB data URL.
- 2026-11-06, Phase 5 review: the same run rejected Hutch's own llama.cpp route because
  `_model_id` shortened only absolute `.gguf` paths. llama-server listed
  `models/vision/...gguf`; any `.gguf` path now presents its basename. The live route then
  ran and answered `Cat`.
- 2026-11-06, Phase 5 review: LM Studio 0.0.27-1 really does reject a WebP data URI while
  accepting PNG/JPEG. The first live app run failed after the media was prepared; the route
  now refuses WebP before sending, and the refusal says why. This is a named-route rule,
  not a global image restriction.
- 2026-11-06, Phase 5 review: llama.cpp + qwen2.5-coder-3b returned a complete call body
  as `content` with `tool_calls: null`. The bench initially called that "prose"; the
  classifier now counts `call_in_content`, and the rerun reports 15 such trials. Hutch still
  does not promote text to a call.
- 2026-11-06, Phase 5 review: `reliability.py` reached 414 lines and failed the context
  audit. The cause classifier moved to `reliability_causes.py` (101 lines);
  `reliability.py` is 333. `ollama.py` shrank from 432 to 400 by moving result folding to
  `ollama_result.py`; no frozen file grew.
- 2026-11-06, Phase 5 review: the Ollama import attempt created a model with
  `capabilities: ["completion"]` and no projector, so the import path is not documented as a
  vision path. The 2,048-token moondream app run is refused by the existing 4,096 floor; the
  floor was not lowered just to make the evidence look uniform.
- 2026-11-06, Phase 5 review, current models: the isolated bench passed every current model on
  Ollama (15/15), but the full-app image comparison did not: Gemma 4 e2b 3/3, Qwen3.5 4B 2/3,
  Qwen3.5 2B 1/3, Qwen3.5 0.8B 0/3. The tiny models echoed the question; the bench's five short
  probes do not exercise Hutch's full system prompt. The recommendation therefore uses the
  full-app result for multimodal and the bench only for isolated tool tasks. This is recorded
  rather than hidden because a bench-only recommendation would have picked the wrong model.
- 2026-11-06, Phase 5 review, current models: the first full-app comparison used a 4,096-token
  preset; the two-image message needed 2,487 prompt + 209 tool + 2,048 reply tokens and was
  refused at admission. That was a test-preset artifact, not a model or vision failure. The
  comparison was rerun at 8,192 tokens; Gemma 4 e2b answered all three cases.
- 2026-11-06, Phase 5 review, current models: llama.cpp Qwen3.5 2B at the default thinking
  budget returned `finish_reason=length` and empty content for 20-120-token image probes; the
  shared reasoning note fires, and `--reasoning-budget 0` produced the answers and a clean
  stock-template `describe_scene` call. LM Studio Gemma 4 e2b produced three `reasoning_only`
  bench trials at the 256-token cap; Ollama sends `think=False` and scored 15/15.
- 2026-11-06, Phase 5 review, current models: LM Studio listed Gemma 4 e2b as `vision: false`
  until its projector file was renamed to `mmproj-gemma4-e2b.gguf` and the server restarted.
  The setup docs now name the convention. This is a runtime setup rule, not a model limitation.
- 2026-11-06, Phase 5 review, catalog: the shipped catalog/presets now carry the measured current
  rows and prefer Gemma 4 e2b for vision and Qwen3.5 2B/4B for tool presets. One preset
  expectation in `tests/test_models_layer.py` changed from qwen3:14b/32b to
  qwen3.5:4b-q4_K_M. The catalog remains a dated one-host suggestion list.
- 2026-11-06, Phase 5 gates: the 14-file focused suite passed 264 with 1 skipped; `npm run
  check:agent` passed after regenerating `.ai/repo-map.generated.md` for the new modules;
  `npm run audit:context` passed; `scripts/audit_emoji.py` reports only the pre-existing
  `.codewhale/state` file. The catalog/preset change adds `tests/test_models_layer.py` and
  `tests/test_state_snapshot.py` to the focused set; both pass after the expectation update.
  No UI or website file changed, so the visual and focused e2e gates do not apply.
  `/code-review` and `/simplify` are not available in this session; the phase diff was re-read
  manually and the findings above were fixed.

- 2026-11-06, Phase 6 review: the airplane setup exposed that the egress probe refused a
  host with only loopback (`no local non-loopback interface is available`), so Strict
  Offline could not start on an already air-gapped machine. The probe now tests the host's
  loopback listener and only adds non-loopback targets when interfaces exist; the worker
  must still fail to reach it. Fixed in e26241e4; `tests/test_offline_airgap.py`.
- 2026-11-06, Phase 6 review: the first live offline turn failed with "provider endpoint
  changed after review" before any model call. The broker canonicalization had rewritten
  `provider.base_url` from `localhost` to `127.0.0.1`, so the reviewed route no longer
  matched. The client now uses the canonical origin while the provider keeps its reviewed
  endpoint; `tests/test_offline_provider_identity.py` covers Ollama, llama.cpp and LM Studio.
- 2026-11-06, Phase 6 review: the first llama.cpp offline turn refused a real image even
  though `/props.modalities.vision` was true. The local adapter read `/props` and `/slots`
  over direct TCP from inside the worker, where TCP is blocked; introspection now uses the
  per-run broker. `tests/test_local_probe_offline.py`; the real llama.cpp run then passed.
- 2026-11-06, Phase 6 review: a broker failure after a successful call was blamed on the
  runtime ("is it running?"), and the run classifier advised starting it. A broker connect
  failure in an Offline worker is now a distinct stop that names the bridge and says the
  runtime may still be running; a broker 502 gets one reload.
- 2026-11-06, Phase 6 review: the first self-check kill was reported as `context`, implying
  a small window. `selfcheck_error` now classifies the captured "unexpected EOF" text as a
  runtime failure; the live main-path kill was re-run after priming the same window and
  showed the reload (8.65 s) with a completed run.
- 2026-11-06, Phase 6 review: the server restart reload failed with "model ... is no longer
  installed" because the restarted Ollama had not re-listed the model yet. The two-sentence
  stop is honest; a readiness wait is left to the managed-process lifecycle work.
- 2026-11-06, Phase 6 review: the first broker-midrun harness attempt unlinked the socket
  before the first request and tested the missing-broker construction path instead. The
  after-first-call case was captured with a direct provider test against the real broker and
  real Ollama; it is recorded rather than claimed as an app-level run.
- 2026-11-06, Phase 6 review: the app's chat image gate is 1.5 MB and the upload API 25 MB,
  so the broker's 64 MiB request cap is not reachable through a normal image. The cap was
  tested directly against the real run broker (413, no upstream request), and the valid
  121,766-byte image passed the full pipeline.
- 2026-11-06, Phase 6 review: size checks: `runtime/builtin.py` 1942 (baseline 1955),
  `sandbox.py` 640 (baseline 641), `providers/local/probe.py` 155, `runtime/outcomes.py`
  103, `providers/ollama.py` 400, `providers/openai_compat.py` 450; no frozen file grew.
  The new tests are under 400 lines.

- 2026-11-06, Phase 7 review: the configured-route grouping used the model name only, so
  the renamed cloud copy `my-local-copy:latest` showed under "On this machine" while the
  route-readiness panel said cloud-routed. Fixed by passing the runtime's `/api/tags` row
  to `locality_for_route` (server signal first). Verified live: the same model now groups
  under "Cloud via local runtime".
- 2026-11-06, Phase 7 review: a real llama.cpp server answering 503 on `/v1/models` during
  load was reported as `unknown`; discovery now falls through to the native `/health` and
  reports `loading` with the runtime's sentence. `tests/test_provider_discovery.py`.
- 2026-11-06, Phase 7 review: the llama.cpp and OpenAI-generic adapters used the default
  `confidence="strong"` on an `unknown` identity. Fixed to `unknown`; no status inflation.
- 2026-11-06, Phase 7 review: a saved Ollama route showed `ready` with Ollama down. It now
  shows `cannot run` and the reason in visible text (`tests/test_model_locality_view.py`).
- 2026-11-06, Phase 7 review: `models.html` reached 657 lines while the phase said to split
  before adding. The runtimes section moved to `_models_runtimes.html`; the page is 573
  lines (below its 606-line start). No behavior change; page and e2e tests re-run.
- 2026-11-06, Phase 7 review: the private-address branch in `locality_for_route` used
  string prefixes (`172.2` matched public 172.200+ addresses). Replaced with
  `ipaddress.ip_address(...).is_private`/`is_loopback`; unused card fields removed.
- 2026-11-06, Phase 7 EC-28 follow-up review: the first guard covered only
  `PATCH /api/bots/{ref}`; the one-message override paths (`/api/bots/{ref}/run`,
  conversation messages and option selection) accepted a cloud route without a
  confirmation. All three now call the same `require_model_sharing`; a regression
  test sends without the ack and gets 409.
- 2026-11-06, Phase 7 EC-28 follow-up review: the confirmation is consumed by the
  change that follows instead of being persisted. A test switches away and back
  and receives 409 again, proving an old consent cannot be replayed. A mismatched
  route or digest is refused and left unconsumed.
- 2026-11-06, Phase 7 EC-28 follow-up review: the browser dialog uses the
  existing overlay primitive (focus trap, Escape, visible focus) and the server
  text; cancelling never applies the selection. The e2e tests cover cancel and
  save-again. `docs/safety.md` states the boundary and the new-assistant
  starter-route notice exception.

## Open items and deferred

- G2, G3, G4 and G7 fixes: Phases 1 and 2. G1 and G6 are closed in Phase 4.
- G5 live Strict Offline: closed in Phase 6 with real Ollama and llama.cpp runs, the
  airplane test and the failure modes. ADR-0035 records the managed-process decision; it is
  not implemented, so the model-server claim remains the weaker worker-boundary sentence.
- Phase 3 not run: a 4 GB cold load (budget), a 60-minute LM Studio TTL wait, a 5-minute
  Ollama keep-alive wait, an older Ollama/LM Studio installation for the upgrade path, GPU
  OOM, and a full Hutch bot turn on llama.cpp or LM Studio (Phase 7 wiring). The adapter-level
  restart and reload paths were exercised live and are recorded in the ledger.
- vLLM and SGLang: not installed (dependency decision needed); OpenAI-compatible seam only.
- LM Studio API-token mode from the CLI: not found in this pass; GUI setting documented.
- Phase 4 not run: a gated Hugging Face pull (no token or gated repo); LM Studio's native
  download as a Hutch surface (deliberately guided: no cancel/catalog API); vLLM/SGLang
  install; the visible import form and the full local-runtimes/state matrix (Phase 7); a
  hand-written Modelfile with a custom template (the create API path is covered by the
  GGUF import and a real `/api/show`, not by a custom template body). The 4 GB-class pull
  remains below the download budget; the 1.9 GiB page pull is the multi-gigabyte case.
- Phase 4 kept `qwen2.5-coder:3b` (1.9 GiB) and `qwen3:1.7b` (1.4 GiB) for Phase 5's
  three-model tool bench. New downloads this phase: 3.3 GiB plus about 0.3 GB in the
  failed tmpfs; the footprint was under 10 GB before the Phase 5 owner-approved extension.
- `src/hutch/data/compat.json` rows for install/import remain Phase 8 (one host, one
  runtime; a catalogue row is a public claim). Vision/tool rows are likewise Phase 8.
- Phase 5 not run: Ollama app-level vision on the retained 2,048-token moondream (the app
  refuses it below the 4,096 floor; direct provider vision is recorded); audio and speech
  on every runtime (no model retained); vLLM/SGLang (not installed); GPU vision; the old
  Qwen2.5-VL's stock template has no tool section, so its image-plus-tool probe used a
  disclosed merged template (the current Gemma 4 and Qwen3.5 2B templates need no override);
  full-app text-only runs for the current models; Gemma 4 e4b/12b/26b, Qwen3.5 122B and
  Qwen3-VL specifically (not downloaded); and the llama.cpp qwen3-4b three-trial bench
  (default reasoning at ~3.9 tokens/s exceeded the foreground window).
- Phase 5 kept `moondream:1.8b-v2-q3_K_S` (1.6 GB) and the current comparison set
  (`qwen3.5:0.8b`, `qwen3.5:2b-q4_K_M`, `qwen3.5:4b-q4_K_M`, `gemma4:e2b`) for Phase 6/7.
  The download footprint is about 20.4 GB after the owner-approved extension; do not
  download more without asking. The retained llama.cpp and LM Studio model links point at
  the same GGUFs and add no download.
- The Phase 5 image benchmark used a real 640 px cat photo from Wikimedia Commons
  (`Cat03.jpg`, Fir0002/Flagstaffotos, CC BY-NC 3.0; used locally for non-commercial
  testing and not committed) and a real Playwright capture of the local Models page. The
  full-size original exceeded the CPU window for a probe; the downscaled copy is the same
  photo. No demo data was added to the product.
- Phase 0 artifacts total 40 PNGs plus the capture JSON; kept under
  `docs/realignment/artifacts/offline-models-2026-11/`.
- Phase 6 not run: LM Studio through the Offline worker (its adapter shares the
  OpenAI-compatible broker path proven live on llama.cpp), vLLM/SGLang, macOS and Windows,
  GPU inference, and the managed isolated model process itself. The app-level
  broker-after-a-successful-call case was captured with a direct provider test against the
  real broker; the before-first-call app case is recorded. No model or binary was downloaded
  in Phase 6; the retained Phase 5 set is unchanged.
- ADR-0035 managed isolated model process: accepted, not implemented. It needs a separate
  implementation task with a real launch, network namespace, Unix-socket bridge and
  lifecycle tests. Do not claim the model server is isolated before that dated evidence.

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

### Phase 4 checkpoints

- 2026-11-06, Phase 4 research: `docs/research/2026-11-offline-models/05-PHASE4-INSTALL.md`
  (P4-1 to P4-13) and R33-R41 appended to `01-FAILURE-MINING.md`. G1 reproduced on the real
  grammar (6 of 10 real names refused); G6 reproduced (`rg` finds no disk preflight or
  `OLLAMA_MODELS` handling). The fault environment was verified: `unshare -rm` keeps host
  networking for a tmpfs pull, `unshare -rmn` leaves only loopback.
- 2026-11-06, Phase 4 design: `07-PHASE4-DESIGN.md` names six tasks and their exact files.
  No frozen file is touched; no template or CSS change is planned.
- 2026-11-06, Phase 4 decisions: Ollama owns pull/blob verification; LM Studio gets a
  guided `lms get` path (native download has no documented cancel or catalog list);
  llama.cpp gets a guided `-hf` launch path (the fetch happens before the server answers);
  vLLM/SGLang remain guided. Preflight reads `OLLAMA_MODELS` or the documented default only
  for a loopback runtime, and reports unknown otherwise. Resume is conditional on the
  runtime keeping its parts (R36/R37). Import uses the runtime's blob and create APIs and
  reads the license back; a missing license is shown as missing.
- 2026-11-06, Phase 4 baseline: retained Ollama 0.40.13 up on 127.0.0.1:11434 with
  `~/.hutch-tmp/localmodels/models` (3.8 GB); filesystem 70.4 GiB free; models
  `qwen3:0.6b`, `qwen2.5-coder:1.5b`, `qwen3:4b`, plus the Phase 1 cloud stubs. Real pull
  target `qwen2.5-coder:3b` (1.9 GiB, Q4_K_M, Qwen Research License, tools) is in the
  catalog and not installed; `qwen2.5:3b` is the same size but has no catalog entry and
  therefore no Install button on the page.
- 2026-11-06, Phase 4 live: the plan/Confirm/cancel/resume run through Chromium against the
  real app and Ollama is in the evidence ledger above (`p4-pull-page.json`); the second
  pull (`p4-second-pull.json`), the real disk-full/no-route pulls, and the real import
  (reuse and 1.93 GB upload) are there too. Screenshots are under
  `docs/realignment/artifacts/offline-models-2026-11/p4-install/`; the plan panel, running,
  cancelled and resumed states were viewed at 360/768/1280/1920, with zero horizontal
  overflow and zero page/console errors.
- Phase 4 exit checks: G1 is closed by `tests/test_model_names.py` and the live grammar
  table; G6 by the server-side preflight, the measured-rate job, the real 1.9 GiB
  cancel/resume, and the real disk-full/no-route captures. EC-15, EC-20 and EC-23 are
  marked with evidence; the only not-run items are the gated Hugging Face pull, LM
  Studio/vLLM/SGLang install surfaces (guided by decision), and the visible import/state
  matrix (Phase 7). Phase 4 is done.

### Phase 5 checkpoints

- 2026-11-06, Phase 5 research: `docs/research/2026-11-offline-models/06-PHASE5-MULTIMODAL.md`
  (P5-1 to P5-13, R42-R54, F12-F18); design in `08-PHASE5-DESIGN.md`.
- 2026-11-06, Phase 5.1: new `providers/local/vision.py`; `OpenAICompatProvider.supports_vision`
  consults the runtime for llama.cpp/LM Studio. Live: llama.cpp Qwen2.5-VL answered `Cat`,
  `"Models"`, `image 1`, and a WebP photo; LM Studio accepted PNG/JPEG and refused WebP;
  Ollama moondream described the cat through the native provider.
- 2026-11-06, Phase 5.1 media gate: LM Studio WebP is refused before sending with the reason
  (`attachments.py`), and the runtime passes the image MIMEs to that gate. The webp case is
  covered in `tests/test_local_vision.py`.
- 2026-11-06, Phase 5.1 accounting: `context.content_tokens` is shared by planning and
  compaction; image parts cost 800 tokens, never base64 text; protected anchors keep user text.
  The live app run that exposed the 52k-token miscount now fits and answers.
- 2026-11-06, Phase 5.2: audio/speech documented and deferred (no retained model, no exercised
  seam); EC-27 records what each runtime accepts.
- 2026-11-06, Phase 5.3: `reliability.py` counts structured causes and detects a complete call
  left in `content`; `cli_models.py` gains `--provider`/`--base-url`; the classifier lives in
  `reliability_causes.py` after the cap split. Sixteen model/runtime pairs measured (baseline and
  current); files under `docs/research/2026-11-offline-models/evidence/phase5/`.
- 2026-11-06, Phase 5 current models (owner approved beyond the original 10 GB budget): pulled
  `qwen3.5:0.8b` 1.3 GB, `qwen3.5:2b-q4_K_M` 1.9 GB, `qwen3.5:4b-q4_K_M` 3.3 GB and
  `gemma4:e2b` 4.6 GB. Ollama: all four 15/15. llama.cpp: Qwen3.5 2B 15/15, Gemma 4 e2b 11/15.
  LM Studio: Gemma 4 e2b 12/15 (reasoning-only) and vision works after the projector is named
  `mmproj-gemma4-e2b.gguf`. Full-app image comparison on Ollama: Gemma 4 e2b 3/3, Qwen3.5 4B
  2/3, Qwen3.5 2B 1/3, Qwen3.5 0.8B 0/3. The measured rows and the winners are now in
  `src/hutch/data/catalog.json` and `presets.json`; `tests/test_models_layer.py` follows the
  new research preset. The full-app result, not the isolated bench, chose Gemma 4 e2b for
  multimodal and Qwen3.5 2B Q4 for lightweight tools.
- 2026-11-06, Phase 5.4: `openai_result.reasoning_budget_notes` is shared by the OpenAI-shaped
  and native Ollama paths; `ollama_result.py` holds the native fold. Live qwen3:4b with
  `think=True`, 32 tokens, returned `length`, empty content and 147 thinking chars, with the
  note naming the budget and the fix.
- 2026-11-06, Phase 5.5: code audit found no `/v1/embeddings` client and no hosted embedding
  call in the chat/memory/search path; EC-19 remains open for Phase 6's airplane test.
- 2026-11-06, Phase 5 live-driven fixes: a relative GGUF id is presented as its basename
  (`providers/local/llamacpp.py`); the compaction estimator and the vision media gate above;
  `call_in_content` classification. New tests cover each; commits `b0a17155`, `fd37d413`,
  `fddb96c7`, `a08009f6`.
- Phase 5 exit checks: EC-16, EC-17 and EC-18 are marked with real evidence, including the
  current-model comparison. EC-19 is not-run until Phase 6. The only not-run items are Ollama
  app-level vision on the 2K moondream, audio and speech, vLLM/SGLang serving, GPU vision,
  Gemma 4 e4b/12b/26b, Qwen3.5 122B, Qwen3-VL specifically, and full-app text-only runs for
  the current models. The current models have stock vision-plus-tool templates; no override was
  needed for them. Services started for evidence are stopped after the final gates; ports 8765,
  9931, 9932, 11434 and 1234 are verified free. Phase 5 is done.

### Phase 6 checkpoints

- 2026-11-06, Phase 6 research: `docs/research/2026-11-offline-models/07-PHASE6-OFFLINE.md`
  (P6-1 to P6-10) and R57-R66 plus F19-F24 in `01-FAILURE-MINING.md`; sources opened
  2026-11-06. Design in `08-PHASE6-DESIGN.md` (five tasks). Commit feb3e464.
- 2026-11-06, Phase 6.1 blocker found by the airplane setup: inside `unshare -rn` with only
  `lo` up, `offline_egress_status(refresh=True)` returned `ok=False` with
  `no local non-loopback interface is available for the network-namespace check`, so Strict
  Offline refused to start on an already air-gapped host. The probe now always opens a
  loopback listener and adds non-loopback targets only when interfaces exist; the worker
  must still fail to reach the host's loopback. Fixed in e26241e4 with
  `tests/test_offline_airgap.py`; `sandbox.py` stays at 640 lines against its 641-line
  baseline. Focused `test_offline_airgap.py` + `test_offline_mode.py` = 40 passed;
  `npm run check:agent` passed; the same probe now returns `ok=True` inside
  `unshare -rn`.
- 2026-11-06, Phase 6.1 live: real app + Ollama 0.40.13 + Gemma 4 e2b, a real 121,766-byte
  cat photo and governed `write_file` + `shell`: succeeded in 97.7 s, answer "cat" and byte
  count 3, workspace `animal.txt` = "cat"; the worker netns differed from the supervisor and
  had only `lo` with no route. Real llama.cpp b12144 + Gemma 4 e2b + projector with
  `--offline --parallel 1`: succeeded in 190.9 s, answer cat/3, `context_limit` 8,192 read
  through the broker. Airplane: app, Ollama and worker inside one `unshare -rn` (only `lo`
  up): succeeded in 138.3 s; an external connect returned 101. The shell egress attempt
  returned `connect_ex 101`. Evidence under `evidence/p6/`.
- 2026-11-06, Phase 6.2 live: a forced 1,200-token generation crossed the broker as 1,202
  chunks / 131,695 bytes; cancel stopped a running worker in 0.304 s; broker loss before the
  first call is a clear "broker is missing" failure; after a successful call the classifier
  names the bridge and stops; a 64 MiB+1 request returned 413; a real runner kill reloaded
  once (8.65 s) and completed; a real server restart produced a 502, one reload, then a
  clear stop because the restarted server had not re-listed the model.
- 2026-11-06, Phase 6 code fixes: `sandbox.py` (loopback-only host probe),
  `providers/local/probe.py` (introspection through the broker), `providers/ollama.py` and
  `providers/openai_compat.py` (broker canonicalization without rewriting the reviewed
  endpoint), `runtime/outcomes.py` (bridge state, 502 reload, self-check failure kind).
  Commits: e26241e4 (air-gap probe), 71595d18 (endpoint identity), fa3d9a5d (broker
  introspection), 85340b61 (failure classification). Tests:
  `tests/test_offline_airgap.py`, `test_offline_provider_identity.py`,
  `test_local_probe_offline.py`, additions to `test_local_failure.py`.
- 2026-11-06, Phase 6.3: the owner chose the Hutch-managed isolated model process.
  ADR-0035 records the decision, the Unix-socket bridge, the eligibility rules and the
  conditional claim; it is not implemented. The 2026-10-31 document now closes phase D and
  states the exact claim (section 9); `docs/runtime-setup.md` carries the per-runtime
  offline recipes.
- Phase 6 gates: the focused 7-file suite passed 175; `npm run check:agent` passed;
  `npm run audit:context` passed; `scripts/audit_emoji.py` reports only the pre-existing
  `.codewhale/state` file, not a Phase 6 file. No UI or website file changed, so the visual
  gate and focused e2e do not apply. `/code-review` and `/simplify` are not available in
  this session; the phase diff was re-read manually and the findings above were fixed.
- Phase 6 exit checks: G5 closed with real Ollama and llama.cpp runs; EC-04 and EC-19
  tested-real (airplane and tool egress); phase D closed in the 2026-10-31 document; ADR-0035
  accepted but not implemented, so the claim stays at the worker boundary. Not run: LM Studio
  through the Offline worker, vLLM/SGLang, the managed process, macOS/Windows and GPU.
  Phase 6 is done.

### Phase 7 checkpoints

- 2026-11-06, Phase 7 research: `docs/research/2026-11-offline-models/09-PHASE7-FRONTEND.md`
  (F-P7-1..F-P7-6, D-P7-1..D-P7-5). Design:
  `docs/realignment/offline-models-2026-11/09-PHASE7-DESIGN.md`.
- 2026-11-06, Phase 7.1/7.2: `modelview.py` gained `locality_for_route`,
  `privacy_label_for`, `local_runtime_cards` and a `locality`/`privacy_label`
  field on `ConfiguredModelRoute`; discovery results are probed once and shared
  by the notes and the runtime cards. `models.html` now shows the Local
  runtimes section outside the collapsed advanced details, groups configured
  routes by where inference happens (On this machine / On your network / Cloud
  via local runtime / Hosted) with a privacy label per group, adds a locality
  tag per row, shows capability chips (or "unknown" when the runtime did not
  report), exposes the "cannot run" reason in words, and labels runtime values
  as measured. The runtimes section moved to `_models_runtimes.html` (85 lines)
  so `models.html` shrank from 606 to 573 lines instead of growing. Commit
  24be8a4c plus the final-pass commits.
- 2026-11-06, Phase 7.1/7.2 final-pass fixes found by running the real stack:
  - A renamed cloud copy (`my-local-copy:latest`) was grouped under "On this
    machine" because the grouping used the name only. It now passes the
    runtime's `/api/tags` row (`remote_host`) to `locality_for_route`, so the
    server signal wins; the same model now groups under "Cloud via local runtime".
  - llama.cpp answers HTTP 503 on `/v1/models` while loading; discovery reported
    "unknown" and never reached the native `/health`. Discovery now falls
    through to the adapter on 503 and reports `state=loading` (new test).
  - The llama.cpp and OpenAI-generic adapters labelled an unidentified runtime
    `unknown` with the default `confidence="strong"`. It is now `unknown`
    confidence (no status inflation).
  - A saved Ollama route showed `ready` while Ollama was down. It now shows
    `cannot run` with "Ollama is not running, so this route cannot run" in
    visible text (new test; `tests/test_model_locality_view.py`).
  - The loading card shows the runtime's own detail sentence.
- 2026-11-06, Phase 7 visual state matrix (real FastAPI app, fresh
  `HUTCH_STATE_DIR`, real Ollama 0.40.13, real llama.cpp b12144, Chromium at
  360/768/1280/1920, dark; images viewed):
  - empty: no routes, zero overflow, zero errors.
  - down: Ollama installed but stopped; runtime card `down` with the fix
    "start it with `ollama serve`", route `cannot run` with the reason.
  - ready: 12 real models, grouping and privacy labels correct.
  - cloud-tagged: `gpt-oss:20b-cloud` and the renamed `my-local-copy:latest`
    group under "Cloud via local runtime — Data is forwarded to a cloud service
    through the local runtime."; the rest under "On this machine".
  - needs-key: real `llama-server --api-key` on 9931; card `needs key` with
    "store this server's API key for http://127.0.0.1:9931; Hutch sends it only
    to that origin, never in the URL".
  - loading: cold `llama-server` captured at 360 as `loading` with the
    runtime's "loading the model (HTTP 503 from /health)" sentence. The
    transient window is about 3 s, so the 768/1280/1920 captures caught the
    ready transition; recorded rather than held open.
  - network: a configured `https://192.168.1.50:8443/v1` connection groups under
    "On your network — Data leaves this machine to a service you control."
  - offline-in-browser: the only client fetch (detected-service check) aborted;
    the panel says "Hutch could not check for AI services." with a retry; the
    one console entry is the deliberate `net::ERR_FAILED`.
  - install running/cancelled/failed and reloaded-mid-install: not re-captured;
    the install layout is unchanged since the Phase 4 captures (which cover
    plan, running, cancelled and resumed at four widths), and the only change is
    `aria-live="polite" aria-atomic="true"` on the state span. Phase 4's real
    disk-full, network-drop and name-failure evidence still applies.
  - upgrade-needed: not run; no older runtime is installed. The Phase 3
    `tests/test_local_versions.py` table covers the advice strings.
- 2026-11-06, Phase 7 keyboard: 60 Tab presses on the ready state recorded a
  logical order (skip link, sidebar, page actions, section nav, readiness links,
  table regions, row actions, install controls) and a visible focus ring on
  every stop (`solid 2px` or `3px`); the runtimes section is server-rendered and
  needs no keyboard-only control beyond the existing links.
- 2026-11-06, Phase 7 gates: 81 focused unit tests passed
  (`test_provider_discovery` 11, `test_model_locality_view` 4,
  `test_models_page` 20, `test_local_runtimes`, `test_local_choices`,
  `test_models_layer`); focused e2e passed per file (`test_model_picker` 12,
  `test_model_install` 3, `test_model_repair` 3, `test_models_detected_route`
  6). The combined four-file e2e run intermittently fails
  `test_the_palette_opens_the_picker_on_a_chat_page_and_only_there`; it passes
  alone and the failure is cross-file app-server state, not this change.
  `npm run check:agent` passed (context hygiene, tool contracts, constitution,
  agent map); `npm run audit:context` passed; `scripts/audit_emoji.py` reports
  no Phase 7 finding. `/code-review` and `/simplify` are not available in this
  session; the diff was re-read manually and the findings above were fixed.
- 2026-11-06, Phase 7.2 follow-up (EC-28, the deferred cloud opt-in UI):
  `route_sharing.py` builds a per-assistant disclosure from the Phase 1
  locality classifier (runtime server signal, then resolved address, then name)
  for `network`, `cloud_via_local` and `cloud` routes; a local route needs
  none. `server/model_sharing_api.py` serves
  `GET /api/bots/{ref}/model-sharing?model=...` and records a CSRF-protected
  acknowledgement. `PATCH /api/bots/{ref}` and every one-message override path
  (`/api/bots/{ref}/run`, conversation messages, option selection) refuse a
  non-local change with 409 until the matching acknowledgement is recorded, and
  the save/send consumes it once, so a later switch back asks again.
  `model-switcher.js` shows a keyboard-operable "Share this assistant's work?"
  dialog before it applies a hosted/cloud one-message choice or saves one as the
  assistant default; cancelling leaves the saved route unchanged. The dialog
  names the assistant, the exact route and what moves. The repair dialog
  (`model-repair.js`) uses the same server disclosure and records the
  acknowledgement before saving. Tests: `tests/test_route_sharing.py` (11,
  including the renamed cloud copy, a private HTTPS network route, a loopback
  gateway that needs none, one-shot consumption and the CSRF refusal),
  `tests/e2e/test_model_sharing.py` (2, cancel-keeps-default and
  save-asks-again), `tests/e2e/test_model_picker.py` (12),
  `tests/e2e/test_model_repair.py` (3, now asserting the server disclosure),
  `tests/test_runtime_follows_model.py` (12, updated to acknowledge the hosted
  runtime switch). Docs: `docs/safety.md` local inference boundary. Size check:
  `model-switcher.js` was frozen at 483 lines, so the marks moved to
  `model-marks.js` (50) and the dialog to `model-sharing-confirm.js` (57); the
  switcher is 466. The oversized picker test file split into
  `test_model_picker.py` (340) and `test_model_sharing.py` (78). Commit 35e63905.
- Phase 7 exit checks: 7.1-7.5 implemented, and the deferred EC-28 confirmation
  UI is now implemented and tested. The state matrix is covered with dated
  images and the exact not-run reasons above. Phase 7 is done. The pre-existing
  tab-strip overlap on /models remains logged (not introduced or fixed here).

Next phase: Phase 8, Website and documentation.

