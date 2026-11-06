# Phase 0 baseline: offline and local models (2026-11-06)

Real-stack baseline taken on the dev host before any feature code. Every command below was
run on 2026-11-05 or 2026-11-06; raw outputs are quoted or summarised where a line is the
evidence. Nothing in this document is a fixture result.

## Host

- AMD Ryzen 3 5300U, 8 threads, 22 GiB RAM (about 10.9 GiB available during these runs).
- Integrated AMD GPU only: `AMD Radeon Graphics (RADV RENOIR)`. Ollama drops it by default;
  the llama.cpp Vulkan build sees it as `Vulkan0 (12175 MiB, 7624 MiB free)`.
- 230 GB filesystem, 81 GB free at the start.
- Linux, Python 3.13 venv via `uv run --frozen --no-sync`, Chromium from the bundled
  Playwright revision.

## Stack

Scratch root for the whole run: `~/.hutch-tmp/offline-models-2026-11/`.

| Component | Version | How it was obtained | Where it runs |
|---|---|---|---|
| Ollama (retained) | 0.40.13 | Already on disk at `~/.hutch-tmp/localmodels/ollama-dist/bin/ollama` | `OLLAMA_MODELS=~/.hutch-tmp/localmodels/models OLLAMA_HOST=127.0.0.1:11434 ... serve` |
| Ollama (current) | 0.40.15 | Release tar.zst, SHA-256 matched against the release `sha256sum.txt` | `OLLAMA_MODELS=.../models-0.40.15 OLLAMA_HOST=127.0.0.1:11435 ... serve` |
| llama.cpp CPU | b12144, server 0.9.0-dev, commit 69ee2ecc0 | `llama-b12144-bin-ubuntu-x64.tar.gz` | `--host 127.0.0.1 --port 8080` (and the default 9931 in one probe) |
| llama.cpp Vulkan | b12144 | `llama-b12144-bin-ubuntu-vulkan-x64.tar.gz` | `llama-server --list-devices` only |
| LM Studio | llmster 0.0.27-1 | `https://lmstudio.ai/install.sh` (SHA-512 checked by the installer, `--no-modify-path`) | `lms daemon up`, `lms server start --port 1234` |

Models:

| Runtime | Model | Digest / file | Size | Licence |
|---|---|---|---|---|
| Ollama 0.40.13/0.40.15 | `qwen3:0.6b`, `qwen2.5-coder:1.5b`, `qwen3:4b` | retained store; qwen3:4b digest `359d7dd4...a09474fae7` | 3.8 GB total | per model page |
| llama.cpp | qwen3:4b GGUF (hard link to the Ollama blob) | GGUF v3, 398 tensors, qwen3 | 2.50 GB | Apache-2.0 |
| llama.cpp vision | Qwen2.5-VL-3B-Instruct Q4_K_M + Q8_0 projector | Hugging Face `ggml-org/Qwen2.5-VL-3B-Instruct-GGUF` | 1.93 GB + 0.85 GB | Apache-2.0 |
| LM Studio | `local/qwen3-4b` (hard link to the same GGUF) + bundled `text-embedding-nomic-embed-text-v1.5` | `lms ls` | 2.50 GB + 84 MB | Apache-2.0 / MIT |

Download footprint: **4.1 GB total** (Ollama 1.5 GB, llama.cpp 58 MB, vision model 2.6 GB),
inside the 10 GB budget. The llama.cpp release publishes no checksum asset; the Ollama
archive matched its published SHA-256. Binaries and archives live in separate directories
under the scratch root; no vendor script was piped to a shell.

## Gap reproductions

Statuses: reproduced, not reproduced, reclassified. The fix belongs to a later phase; this
phase only records the evidence.

| ID | Result | Evidence |
|---|---|---|
| G1 install name grammar | **Reproduced: 6 of 10 real forms refused** | `validate_model_name` accepted `qwen3:4b`, `library/qwen3:0.6b` and both `-cloud` tags; it refused `hf.co/bartowski/Llama-3.2-3B-Instruct-GGUF:Q4_K_M`, `hf.co/unsloth/Qwen3-4B-GGUF:Q4_K_M`, `llama3.2-vision:11b-instruct-q4_K_M`, `Qwen3:4B`, `qwen3:4b-instruct-2507-q4_K_M` and `registry.ollama.ai/library/qwen3:4b`. The error text says "use lowercase letters, digits...". |
| G2 cloud-tag locality | **Reproduced, and worse than the name regex** | With Ollama 0.40.13 up: `POST /api/pull {"model":"gpt-oss:20b-cloud"}` wrote a 306-byte manifest. `ollama cp` refused the copy, but `ollama create my-local-copy -f Modelfile` (`FROM gpt-oss:20b-cloud`) succeeded. `/api/tags` then reported `name=my-local-copy:latest`, `remote_host=https://ollama.com:443`, `remote_model=gpt-oss:20b`. `is_local_route("ollama","my-local-copy:latest")` returned `True` and `OllamaProvider.data_stays_local()` returned `True`. A chat on that model without sign-in returned `{"error":"unauthorized","signin_url":"https://ollama.com/connect?...key=..."}` (key redacted). The `/models` page showed it as a **Local route / ready**, and the model switcher grouped it under **On this machine**. `/api/show` did **not** repeat `remote_host`, so `/api/tags` is the signal source. |
| G3 local group only for Ollama | **Reproduced** | With Ollama stopped and a real `llama-server` on 8080 (the port Hutch probes), `hardware.probe()` reported `llama.cpp reachable=True`, but `modelchoices._local_choices(bot, hw, None)` returned `[]` because `ollama_up` is false. Separately, a stock `llama-server` on its real default port 9931 is not probed at all. |
| G4 no native introspection | **Reproduced** | `rg "/props|api/v0|mmproj|jinja" src/hutch` returns one docstring mention of `--jinja` in `toolcalling/profiles.py` and nothing else. Meanwhile the real endpoints carry the facts Hutch needs: `/props` (`n_ctx`, `total_slots`, `modalities`, `chat_template_caps.supports_tools`), `/slots` (per-slot `n_ctx`), `/v1/models` (`meta.n_ctx`, `n_ctx_train`, `owned_by`), LM Studio `/api/v1/models` (`capabilities.vision`, `trained_for_tool_use`, `max_context_length`, `loaded_instances[].config.context_length`, `remaining_ttl_seconds`). |
| G5 Strict Offline never live | **Confirmed as a historical gap** | `docs/realignment/offline-models-2026-10-31.md` section 3.5 and ADR-0009 record fixture-only evidence. Nothing in this run drives a model through the broker yet; Phase 6 owns the live proof. |
| G6 no disk preflight, no real big pull | **Reproduced** | `rg "disk_usage|statvfs" src/hutch` returns nothing. No install preflight exists. The real multi-gigabyte pull, cancel and resume are Phase 4 work. |
| G7 port-trust discovery, key-protected servers | **Reproduced twice** | A decoy server on `127.0.0.1:8080` answering `/v1/models` with `{"data":[{"id":"definitely-not-llamacpp"}]}` was reported as `provider=llamacpp, reachable=True, models=["definitely-not-llamacpp"]`. A real `llama-server --api-key` on 8080 was reported as `reachable=False, error="no service answered"`, not "not a model list", because the 401 is a `urllib` `HTTPError` (a `URLError` subclass). Its `/health` was still 200. |
| G8 frozen files not grown | **Confirmed** | `.file-size-baseline.json` caps: `modelchoices.py` 435 (now 433), `providers/ollama.py` 432 (now 432), `providers/openai_compat.py` 466 (now 447), `runtime/builtin.py` 1955 (now 1955). No frozen file grew. |

Additional reproductions that belong to later phases but were observed now:

- **EC-09 loading state**: a 2.5 GB llama.cpp model loaded from page cache before the first
  `/health` poll, so the documented 503 body was not captured; record "not captured (load
  finished between polls)". Ollama cold-loaded qwen3:0.6b in 1.56 s.
- **EC-18 empty answer**: LM Studio qwen3-4b with `max_tokens: 64` returned empty content,
  `finish_reason: "length"`, `reasoning_tokens: 64`.
- **EC-21 integrated GPU**: Ollama logs `dropping integrated GPU; to enable, set
  OLLAMA_IGPU_ENABLE=1`; the llama.cpp Vulkan build lists the same GPU.

## Baseline gates (2026-11-06)

```
npm run check:agent
  Context hygiene check passed (1048 source files; 117 frozen over-cap files).
  Tool contract check passed (47 registered tools; canonical schemas certifiable; specs match).
  Constitution check passed (3 roles, 14 rules; every rule maps to existing enforcement).
  Agent map check passed (119 lines; 2490 tracked files scanned).

npm run test:agent -- tests/test_provider_discovery.py tests/test_model_install.py \
  tests/test_model_install_api.py tests/test_models_layer.py tests/test_models_detected_route.py \
  tests/test_offline_mode.py tests/test_selfcheck_plan.py tests/test_slots.py tests/test_fitloop.py \
  tests/test_local_admission_runtime.py tests/test_netguard_local_origins.py tests/test_reliability.py
  198 passed in 66.00s (0:01:05)
```

## Visual baseline (2026-11-06)

Harness: `docs/realignment/capture_offline_models_baseline.py`. It runs the real FastAPI app
on an ephemeral loopback port with a fresh `HUTCH_STATE_DIR`, creates one assistant on
`ollama/qwen3:0.6b`, and captures with Playwright Chromium at 360, 768, 1280 and 1920 px.

Captures (20 images per state, five surfaces times four widths):
`docs/realignment/artifacts/offline-models-2026-11/baseline-up/` (Ollama 0.40.13 running)
and `baseline-down/` (Ollama stopped). Both reports: 20 screenshots, **zero horizontal
overflow, zero page errors, zero console errors**.

Surfaces: `/models`, the model switcher on `/#/chat/baseline`, `/#/connections`,
`/onboarding` (first step) and `/onboarding/local-service` after walking the real wizard.

Theme note: the dashboard is a **fixed dark workspace**. Its linked stylesheets
(`hutch.css`, `hutch-pages.css`, controls/forms/composer/nav/shell/overlays) do not read
`data-hutch-theme`; only the unlinked generated `ui.css` and `hutch-overlays.css` carry
light tokens, and Settings says "The dark workspace theme is fixed." Capturing a light
dashboard would be a fiction, so the harness records dark only and this note is the reason.
The website keeps its own light/dark gate in Phase 8.

Defects found by looking at the images:

1. **Cloud route labelled local, visibly.** `/models` lists
   `ollama/my-local-copy:latest` with a `local` badge and `ready`; the switcher places it
   under "On this machine" with "fits, 16k context"; onboarding lists it (and
   `gpt-oss:20b-cloud`) as installed models under the promise "No API key or remote
   internet access required for local inference". Fix: Phase 1 (locality truth) and Phase
   7 (labels).
2. **Runtime down is invisible.** With Ollama stopped, the assistant's route still reads
   `Runnable` and `ready`, the model list silently shrinks to the configured route, and
   nothing says the service is down. Fix: Phase 3 (states) and Phase 7 (surfaces).
3. **Two vocabularies on one page.** The same model is "capability unverified" in Route
   readiness and `ready` in Configured model routes. Fix: Phase 7 copy and state model.
4. **No first-class entries for non-Ollama locals.** With llama.cpp reachable, the
   switcher has no entry for it; only the Ollama-backed route appears. Fix: Phase 2 and 7.
5. Observation, not a defect: the onboarding local-service heading receives a visible
   focus ring on load (focus management). Recorded so it is not mistaken for a bug later.

## Research outputs produced with this baseline

- `docs/research/2026-11-offline-models/01-FAILURE-MINING.md` — complaint table and the
  R14+ register.
- `docs/research/2026-11-offline-models/02-RUNTIME-API-NOTES.md` — exact fields per
  runtime and the D1 to D7 decisions.
- Appended sections in `docs/research/offerings-and-failures.md` and
  `docs/research/complaints.md`.

## Not run, and why

| Item | Reason |
|---|---|
| Live inference on a cloud-tagged Ollama model | The bench has no Ollama account; the runtime answered `unauthorized` with a sign-in URL. Classification is proven from `/api/tags`, not from a successful cloud call. |
| vLLM and SGLang | Installing either adds a Python dependency and a large download; the master prompt requires asking the owner first. Both sit on the OpenAI-compatible seam. |
| LM Studio API-token flow (auth on) | The token setting is exposed in the GUI/Server Settings; the headless CLI path to enable it was not found in this pass. llama.cpp `--api-key` covers the `needs_key` failure mode. |
| llama.cpp 503 "Loading model" body | The model loaded from page cache between the first and second poll. The body is documented; it is not claimed as observed. |
| A 4 GB-class cold load | The largest model on the bench is 2.5 GB and it loaded warm. Phase 3 must load a cold 4 GB model and measure it. |
| Windows, macOS, CUDA, ROCm, discrete GPUs | No hardware. Record only; never claim. |
| Real multi-gigabyte pull/cancel/resume | Phase 4 owns it; G6 stays open. |
| Strict Offline with a live model | Phase 6 owns it; G5 stays open. |

## Next phase

Phase 1 (locality truth). The first task replaces the name regex with a signal-first
classifier, using `/api/tags.remote_host` / `remote_model` as the authority and the name
suffix only as a fallback, then blocks cloud-tagged models in `validate_model_name` unless
the owner opted in on that route.
