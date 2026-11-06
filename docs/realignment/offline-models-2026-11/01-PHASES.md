# Phases and checkpoints

Each phase: research, short design note, small commits on `main`, real-setup validation, visual
validation if UI, review, docs. Each task touches at most three source files plus one seam. A phase is
done only when its exit checks pass and `02-PROGRESS.md` says so. Gap IDs (G1..G8) are defined in
`00-MASTER-PROMPT.md`; case IDs (EC-nn) are in `03-EDGE-CASES.md`. New logic goes in new modules under
the 400-line cap; the frozen files (`modelchoices.py`, `providers/ollama.py`, `providers/openai_compat.py`,
`runtime/builtin.py`) may only shrink, so extract before you add.

## Phase 0 - Diagnose (no feature code)

- 0.1 Stand up the real stack in `~/.hutch-tmp/offline-models-2026-11/`: retained Ollama 0.40.13,
  current Ollama release if different, official `llama-server` build plus a small tool-capable GGUF and a
  small vision GGUF with projector, LM Studio only after the owner agrees. Record versions, digests,
  commands, and every "not run" in `docs/research/2026-11-offline-models/00-BASELINE.md`.
- 0.2 Reproduce G1 to G8 against that stack. Where a gap does not reproduce, say so and close it. For
  each that does, write the failing test but do not commit it red: it lands in the same commit as its
  fix. Keep reproductions as commands in the baseline doc.
- 0.3 Baseline gates: `npm run check:agent`, then the focused set `tests/test_provider_discovery.py
  test_model_install.py test_model_install_api.py test_models_layer.py test_models_detected_route.py
  test_offline_mode.py test_selfcheck_plan.py test_slots.py test_fitloop.py test_local_admission_runtime.py
  test_netguard_local_origins.py test_reliability.py` through `npm run test:agent`. Record counts.
- 0.4 Visual baseline with the real server (fresh `HUTCH_STATE_DIR`) and real Ollama both up and down:
  `/models`, the onboarding local-service step (`templates/onboarding_local_service.html`),
  `/connections`, the model switcher. Four widths, light and dark. View the images, log defects.
- 0.5 Research and failure mining per `04-RESEARCH-PLAN.md` into `01-FAILURE-MINING.md` and
  `02-RUNTIME-API-NOTES.md`. Extend the R1..R13 register in the 2026-10-31 doc from R14.
- 0.6 Order the backlog by user harm (privacy first, then silent wrong behavior, then missing
  capability, then polish). Ask the owner the batched questions from the master prompt once.
- Exit: baseline, failure-mining and API-notes docs committed; backlog and decisions in `02-PROGRESS.md`.

## Phase 1 - Locality truth (EC-01 to EC-04, EC-28)

Goal: Hutch never presents a cloud-routed or non-loopback route as local, and never routes to one
silently.

- 1.1 Replace the name regex with a signal-first classifier in a new `src/hutch/providers/locality.py`:
  server signal (`remote_host`/`remote_model` in `/api/tags` and `/api/show` if the real runtime emits
  them; sign-in state; `OLLAMA_NO_CLOUD`), name suffix only as fallback, resolved-address check for the
  endpoint host (loopback, LAN, public) pinned at connect time. Seams: `providers/pricing.py:25`,
  `providers/ollama.py:254`, `runtime/builtin.py:299` (each shrinks or stays flat).
- 1.2 Block `-cloud` tags in `validate_model_name` unless the owner has opted in on that route, and make
  the opt-in a visible, per-assistant data-sharing confirmation (approval boundary playbook).
- 1.3 Offline-readiness check: a route marked offline must fail early, in words, if the model is not
  fully on disk, if the runtime would download on start (llama.cpp `-hf`), or if sign-in-dependent
  features are active.
- Exit: real Ollama with a cloud-tagged model present (sign-in not required to list a stub, else
  record "not run: no account" and test the locality classifier against the real `/api/tags` of a runtime
  that has one); a test showing the cloud model is refused under Strict Offline and flagged everywhere
  else; EC-01..04 rows marked with evidence.

## Phase 2 - Native runtime introspection (G3, G4, G7; EC-05 to EC-08, EC-12, EC-13)

Goal: Hutch knows what each local runtime is actually doing, for all three, not just Ollama.

- 2.1 A narrow `LocalRuntime` protocol and per-runtime adapters in new modules under
  `src/hutch/providers/local/` (for example `lmstudio.py`, `llamacpp.py`, `openai_generic.py`):
  `identify()` (fingerprint, not port), `models()`, `loaded()`, `applied_context()`,
  `capabilities()` (vision, tools, reasoning, embeddings), `state()` (loading, ready, needs_key,
  unreachable). Native sources: LM Studio `GET /api/v1/models`; llama.cpp `/props`, `/health`, `/slots`;
  vLLM/SGLang `/v1/models` fields. Seam: `providers/discovery.py` (grow it by delegation, not by
  branches).
- 2.2 Fixed-window context policy: when the window is set at load or launch time, read it, size history
  and the tool catalog to it, trigger compaction before overflow, and report applied window versus
  wanted. Detect context shift or rolling-window policies and either disable, warn, or refuse for
  agent runs (they drop the system prompt silently). Seams: `context.py`, `fit.py`, `modelview.py`.
- 2.3 Wire the results into the model choice list through a new module (G3), not into
  `modelchoices.py`. Per-slot context when `--parallel`/`parallel` divides the window.
- 2.4 Credentials: `needs_key` state for a key-protected server; key stored through the vault, sent only
  to the matching origin, never in the URL.
- Exit: against the real `llama-server` (and LM Studio if obtainable): window read equals what the
  server reports; an over-long prompt triggers compaction or a clear refusal, not silent loss (proved
  with a needle placed in the system prompt); a squatter on :8080 is not labelled llama.cpp; a
  `--api-key` server shows `needs_key`.

## Phase 3 - Lifecycle states and error mapping (EC-09 to EC-11, EC-22)

- 3.1 Loading and cold start as states: llama-server `/health` 503, LM Studio just-in-time load, Ollama
  large-model load. First-token waits get a visible "loading the model" state with measured load time,
  not a timeout error. Seams: new `providers/local/state.py`, `runtime/builtin.py` call site (flat),
  `health.py`.
- 3.2 Eviction and restart: keep-alive/TTL expiry, `OLLAMA_MAX_LOADED_MODELS`, router `--models-max`,
  OOM-kill of the runner mid-stream, server restart mid-run. Map to actionable `ProviderError` kinds
  and resume-safe behavior; one reload attempt, then a clear stop.
- 3.3 Version drift: record runtime version per route; gate features by minimum version (thinking,
  tools, structured output, native `/api/v1`); `hutch doctor` and the Models page say "upgrade X to Y
  for Z" using version facts from the research notes. Seams: `doctor.py`, `health.py`.
- Exit: real kill -9 of the runner mid-stream and real server restart handled and shown; a cold 4 GB
  load shown as a loading state with a measured duration.

## Phase 4 - Get a model: install, import, guide (G1, G6; EC-15, EC-20, EC-23)

- 4.1 Name grammar: accept the real forms (`hf.co/<user>/<repo>[:quant]`, mixed-case quant tags,
  registry-host prefixes, digests) with a parser plus table-driven tests built from names scraped from
  the real Ollama library and Hugging Face pages, not invented ones. Seam: `providers/model_install.py`
  (split the grammar into a new module first).
- 4.2 Preflight before any pull: free disk on the server's model directory (the server's, not Hutch's:
  ask the runtime or probe `OLLAMA_MODELS`), size from the manifest, estimated time from measured link
  speed, fit verdict from `fit.py`. Honest unknowns shown as unknown.
- 4.3 Failure and resume: network drop, disk full mid-pull, killed server, restarted Hutch with a job in
  flight, double-click, two tabs. Job state survives a page reload and SSE reconnect.
- 4.4 Other runtimes: re-decide with evidence whether LM Studio's native download endpoints
  (`/api/v1/models/download`, `/download/status`) and llama.cpp `-hf` justify an install surface. The
  2026-10-31 decision was "no uniform fake abstraction"; keep that stance for anything the runtime does
  not do natively. Otherwise provide a guided path (exact command, size, where files land) and a
  "re-scan" action.
- 4.5 Import a local GGUF file for Ollama (Modelfile create) and verify its checksum; show license text
  and gated-model requirements; never put a token in a URL.
- Exit: a real multi-gigabyte pull through the page against real Ollama, cancelled once and resumed once;
  disk-full and network-drop observed for real (a small loopback block device or `unshare -n` makes
  these real); G1 and G6 closed with tests.

## Phase 5 - Multimodal and tool reliability on real local models (EC-16 to EC-19)

- 5.1 Vision end to end on Ollama and llama.cpp (and LM Studio if present): real photo, real screenshot,
  multi-image, oversized image, image plus tool call, model without vision refused before sending.
  Account for image tokens against the window. Seams: `providers/attachments.py`, `ollama.py`
  `to_ollama_messages` (extract, do not grow), `openai_compat.py` (extract).
- 5.2 Audio and speech: record what each runtime accepts today (llama.cpp multimodal audio, local
  whisper-style STT via `providers/transcription.py`, TTS); implement only where the runtime does it
  natively and the Hutch seam exists; document the rest as deferred with the reason.
- 5.3 Tool-calling qualification on three real local models per runtime using `hutch models bench` /
  `reliability.py`: record parse failures by cause (template, missing or invalid call id, tool call inside
  the reasoning block, string versus object arguments, parallel calls). Mitigate in the tool-call repair
  path or disclose per model; never claim by model name.
- 5.4 Reasoning budget: think tokens consuming `num_predict`/`max_tokens` and leaving an empty answer;
  `finish_reason=length` handling; the leaked `</think>` case already fixed in 2026-10-31.
- 5.5 Embeddings and memory: confirm no feature silently calls a hosted embedding or search endpoint
  for an offline assistant (`netguard.py`, `synthesis/model.py`); if a local embedding route is needed,
  design it, do not bolt it on.
- Exit: ledger rows with real images and measured results; bench output per model committed as evidence.

## Phase 6 - Strict Offline with a live model (G5; EC-04) and the boundary decision

- 6.1 Drive a governed tool run with a real model through the broker in the isolated worker, with egress
  proven blocked from inside the worker (not just probed on the host). Run the same turn under
  `unshare -n` with the network down at the host level (airplane test). Record both.
- 6.2 Failure modes inside the namespace: model server restart, broker socket loss, large streamed
  responses, cancellation, image payload size against `MAX_REQUEST_BYTES`.
- 6.3 Boundary decision: write an ADR comparing (a) status quo wording, (b) Hutch-managed model process
  with its own network namespace, (c) a user-run "offline profile" script and checker. Ask the owner;
  do not implement (b) without approval.
- Exit: 2026-10-31 doc phase D closed with a dated evidence row and the exact claim Hutch may make.

## Phase 7 - Frontend

Surfaces: `pages_models.py`, `templates/models.html` (606 lines, split before adding),
`static/models-detect.js`, `model-install.js`, `model-repair.js`, `model-switcher.js`, `starter-route.js`,
`templates/onboarding_local_service.html` and `server/onboarding_local_service_api.py`, Tailwind sources
in `app/src/` (never generated CSS). New UI in new modules.

- 7.1 A Local runtimes panel: one card per detected runtime with identity, version, state, applied
  window, CPU/GPU split, loaded models, and the single next action. Measured values labelled measured,
  predicted values labelled predicted, unknown shown as unknown.
- 7.2 Model list grouped by where inference happens (On this machine, On your network, Cloud via local
  runtime), with fit, capability chips (tools, vision, reasoning), and the privacy label from Phase 1.
- 7.3 Install and import flow from Phase 4 with preflight facts before the button, progress with
  `aria-live`, cancel, retry, and states that survive reload.
- 7.4 First run: a hardware-aware recommendation that is a fitted, tool-capable, license-visible model,
  with size and time, and no auto-download. Stays inside the existing starter-route rules (always shows
  the data-sharing notice for non-local routes).
- 7.5 Empty, error, loading, offline-in-browser and key-protected states for every panel.
- Exit: visual validation gate from the master prompt in every state, with images viewed and defects
  logged; keyboard-only traversal; zero console errors; focused e2e green; no fixture-driven preview.

## Phase 8 - Website and documentation

- Update the website claims and `llms.txt` per the master prompt; add a short, evidence-bound "local and
  offline" explanation including the boundary table (worker egress enforced, model server not).
- Docs: `docs/models.md` (admission, verified/unverified section), `docs/runtime-setup.md`, ADR(s),
  `docs/realignment/offline-models-2026-10-31.md` (new evidence section, D closed),
  `docs/marketing-site.md` capability table, `src/hutch/data/compat.json`, `docs/release-checklist.md`.
- Visual validation of the site at four widths and both themes; view the images; fix defects.
- Exit: every public sentence maps to a dated row in the progress ledger.

## Phase 9 - Final review, merge and confirmation

- Whole-initiative skeptical review of `git diff <first-commit>^..HEAD` for these paths: god functions,
  silent fallbacks, name-based guesses, credential leakage, status inflation, dead code, over-cap files,
  stale docs. Run `/code-review` and `/simplify` if available. Fix and record.
- Final gates: `npm run check:agent`, the focused tests for every touched behavior, the touched e2e
  files, `python scripts/audit_emoji.py`, `git status` clean except others' work, everything on `main`.
- Final real-setup pass: fresh `HUTCH_STATE_DIR`, real server, from "no runtime" to a first successful
  tool-using turn on each available runtime, then the same offline. Record results and the final list of
  "not run" items.
- Prune scratch with `scripts/prune_validation_tmp.py` (dry run, read the list, then `--apply` only for
  directories this run created).
- Exit: `02-PROGRESS.md` all done; a final report listing what is implemented, verified (with date and
  evidence), not run, and blocked.
