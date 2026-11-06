# Progress: offline and local models (2026-11)

Update at every checkpoint. Keep entries short and factual. Statuses: not started, in progress, done,
blocked. Resume at the first phase that is not done; re-verify any evidence older than the code it
covers before relying on it.

## Phase status

| Phase | Status | Last commit | Live-verified | Blocked on |
|---|---|---|---|---|
| 0 Diagnose | done | (recorded below) | 2026-11-06: Ollama 0.40.13/0.40.15, llama.cpp b12144 CPU+Vulkan, LM Studio llmster 0.0.27-1, Chromium captures | — |
| 1 Locality truth | not started | | | |
| 2 Native runtime introspection | not started | | | |
| 3 Lifecycle states and errors | not started | | | |
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
| G3 local group only for Ollama | 2026-11-06, llama.cpp reachable but `_local_choices` returned `[]` | Phase 2.3 (planned) | same |
| G4 no native introspection | 2026-11-06, `rg` empty; real `/props`, `/slots`, `/api/v1/models` fields recorded | Phase 2.1 (planned) | `02-RUNTIME-API-NOTES.md` |
| G5 Strict Offline never live | historical gap confirmed; no live run yet | Phase 6.1 (planned) | `docs/realignment/offline-models-2026-10-31.md` section 3.5 |
| G6 no disk preflight, no real big pull | 2026-11-06, `rg` empty | Phase 4.2/4.3 (planned) | `00-BASELINE.md` |
| G7 port-trust discovery, key-protected servers | 2026-11-06, decoy on 8080 labelled llama.cpp; real `--api-key` server reported "no service answered" | Phase 2.1 (planned) | `00-BASELINE.md` |
| G8 frozen files not grown | confirmed 2026-11-06: 433/432/447/1955 against caps 435/432/466/1955 | Phase 9 recheck | `.file-size-baseline.json` |

## Edge-case status

Track by ID from `03-EDGE-CASES.md`: tested-real, tested-fault-injected, documented, not-run (reason),
or out-of-scope (reason). One line per ID once touched.

- EC-01: tested-real (classification is wrong today; evidence in `00-BASELINE.md`). Fix Phase 1.
- EC-02: not-run (needs a second interface or hosts entry); design recorded in Phase 1.1.
- EC-03: documented (vendor docs: Ollama cloud/remotes, LM Studio catalog/JIT, llama.cpp `-hf`).
- EC-04: not-run (Phase 6).
- EC-05: tested-real for Ollama (`/api/ps.context_length`), llama.cpp (`/props`, `/slots`), LM Studio (JIT config); fix Phase 2.2.
- EC-06: documented for llama.cpp (`--context-shift` default disabled) and LM Studio (`truncateMiddle`); test Phase 2.2.
- EC-07: partially measured (Ollama `size`/`size_vram`); full fit comparison Phase 2.
- EC-08: tested-real (llama.cpp 4 auto slots each 8192; LM Studio `parallel: 4`); explicit `--parallel 2` test in Phase 2.
- EC-09: partially observed (Ollama cold load 1.56 s; llama.cpp loaded before the first 503 poll). Full cold 4 GB load in Phase 3.
- EC-10: documented (LM Studio TTL 60 min, auto-evict; Ollama 5 min keep-alive, `OLLAMA_MAX_LOADED_MODELS`); test Phase 3.
- EC-11: tested-real (0.40.13 vs 0.40.15 agree on the cloud fields; full feature matrix Phase 3).
- EC-12: tested-real (decoy on 8080). Fix Phase 2.1.
- EC-13: tested-real (`--api-key` server looks dead). Fix Phase 2.4.
- EC-15: tested-real (G1 names; GGUF template present and tool-capable in `/props`). Fix Phase 4.1.
- EC-18: tested-real (LM Studio empty answer with 64 reasoning tokens). Fix Phase 5.4.
- EC-21: tested-real on this host (Ollama drops the iGPU; see `02-RUNTIME-API-NOTES.md`).
- EC-23: reproduced as a missing capability (no disk preflight). Fix Phase 4.
- EC-25: not-run (network-dependent tag check; Phase 4).
- EC-27: documented (llama.cpp accepts `input_audio`; no local audio run yet).
- EC-28: not-run (Phase 1).

## Evidence ledger (real runs only)

| Date | Runtime and version | Model and digest | Hardware | Route and command | Exercised | Not exercised | Result |
|---|---|---|---|---|---|---|---|
| 2026-11-06 | Ollama 0.40.13 | qwen3:0.6b, qwen2.5-coder:1.5b, qwen3:4b (3.8 GB) | Ryzen 3 5300U, CPU | `OLLAMA_HOST=127.0.0.1:11434 OLLAMA_MODELS=~/.hutch-tmp/localmodels/models ollama serve` | `/api/version`, `/api/tags`, `/api/ps`, `/api/generate`, `/api/pull` of a cloud manifest, `ollama create` from it | Cloud inference (no account) | Cloud fields present; chat on the copy returns `unauthorized`; cold load 1.56 s; `size_vram=0` |
| 2026-11-06 | Ollama 0.40.15 | same store, hard-linked copy | same | `OLLAMA_HOST=127.0.0.1:11435 ollama serve` | `/api/version`, `/api/tags` | inference | Same `remote_host` / `remote_model` fields as 0.40.13 |
| 2026-11-06 | llama.cpp b12144 (CPU) | qwen3:4b GGUF, 2.50 GB | same | `llama-server -m models/qwen3-4b.gguf -c 8192 --host 127.0.0.1 --port 8080` and the default 9931 | `/health`, `/props`, `/slots`, `/v1/models`, `/v1/chat/completions`, `/api-key` | vision, tools end to end, 503 body | `n_ctx=8192`, 4 auto slots, `supports_tools=true`, `owned_by=llamacpp`; key-protected server looks dead to discovery |
| 2026-11-06 | llama.cpp b12144 (Vulkan) | no model | same | `llama-server --list-devices` | device listing | inference | `Vulkan0: AMD Radeon Graphics (RADV RENOIR) (12175 MiB, 7624 MiB free)` |
| 2026-11-06 | LM Studio llmster 0.0.27-1 | local/qwen3-4b (hard link) + bundled embedding | same | `lms daemon up`, `lms server start --port 1234` | `/api/v1/models`, `/v1/models`, JIT `/v1/chat/completions`, `lms ps` | API-token mode, vision | JIT context 8192, `parallel=4`, TTL 3600 s; 64 reasoning tokens returned an empty answer |
| 2026-11-06 | FastAPI app (this checkout) | real Ollama store | same | `capture_offline_models_baseline.py`, Chromium | `/models`, switcher, `/#/connections`, `/onboarding`, `/onboarding/local-service` at 360/768/1280/1920 | light theme (fixed dark), keyboard traversal (Phase 7) | 20 + 20 screenshots; zero overflow, zero page/console errors; defects listed in `00-BASELINE.md` |

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

## Open items and deferred

- G1, G2, G3, G4, G6, G7 fixes: Phases 1, 2 and 4.
- G5 live Strict Offline: Phase 6.
- Real 4 GB cold load, 503 body, explicit `--parallel 2` split: Phase 2/3.
- vLLM and SGLang: not installed (dependency decision needed); OpenAI-compatible seam only.
- LM Studio API-token mode from the CLI: not found in this pass; GUI setting documented.
- Phase 0 artifacts total 40 PNGs plus the capture JSON; kept under
  `docs/realignment/artifacts/offline-models-2026-11/`.
