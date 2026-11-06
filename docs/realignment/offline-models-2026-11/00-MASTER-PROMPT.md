# Master prompt: offline and local models (2026-11)

Contract for the executing agent. Work through `01-PHASES.md` in order, record state in `02-PROGRESS.md`,
turn every MUST row of `03-EDGE-CASES.md` into a test, and follow `04-RESEARCH-PLAN.md` for research.
One phase per session where possible (AGENTS.md: fresh session per task, under about 120K tokens).
Paste the "Launch prompt" at the bottom into a fresh session.

## Goal

Make Hutch's offline and local-model support honest, complete and usable for Ollama, llama.cpp
(`llama-server`) and LM Studio, with vLLM and SGLang riding the same seam. "Complete" means a person
can, from the dashboard and with no terminal:

1. see which local runtimes are running and what each one truly reports (version, loaded models,
   applied context window, CPU/GPU split, vision and tool capability);
2. get a model that fits this machine (install, import or guided setup) with size, disk and time
   shown before they commit;
3. run a real assistant turn, including tool calls and, where the model supports it, images;
4. understand every non-happy state as a state, not an error: loading, evicted, window too small,
   needs a key, crashed, out of memory, cloud-routed;
5. trust the words "local" and "offline". Hutch says them only as far as it can evidence, and the
   boundary is written down (see `docs/realignment/offline-models-2026-10-31.md` section 5).

## Relationship to other work (read before touching shared data)

- Builds on `docs/realignment/offline-models-2026-10-31.md`: its phases A, B, C and E are shipped and
  verified. Do not redo them. This run closes its open phase D and the gaps listed below.
- A sibling package exists at `docs/realignment/provider-expansion-2026-11/` (untracked, another
  session's work). Its Phase 5 "Local and custom" overlaps this package. Decision: this package owns
  local runtimes (Ollama, llama.cpp, LM Studio, vLLM, SGLang); the sibling keeps hosted providers,
  gateways and custom remote endpoints. Do not edit the sibling's files. Record the split in your own
  `02-PROGRESS.md` and tell the owner so they can mark the sibling's Phase 5.
- Shared data files (`src/hutch/data/providers.json`, `compat.json`, `connections.json`): run
  `git status` and `git log -5 -- <file>` immediately before editing; keep your diff to local-runtime
  rows only.
- Shared checkout hazard: several agents edit this checkout at once and another actor's commit has
  swept up staged edits before. Run gates first, then stage and
  commit in one command with explicit paths (`git commit -m "..." -- path1 path2`). Never `git add -A`.
  Re-check `git status` and `git log -3` right before committing. New tracked files need
  `npm run agent:map` and the regenerated `.ai/repo-map.generated.md` in the same commit.

## Verified starting state (checked 2026-11-05; recheck before relying)

Exists and works; diagnose against it, do not rebuild:

- Hardware probe `src/hutch/hardware.py` (RAM, GPU, Apple Silicon, runtimes); fit and KV arithmetic
  `src/hutch/fit.py`; context planning `src/hutch/context.py`; truncation detection and the Ollama
  `num_ctx` discipline (LM-1) in `src/hutch/providers/ollama.py`; self-check sized from measured
  throughput `src/hutch/selfcheck_plan.py`.
- Ollama install/remove (`src/hutch/providers/model_install.py`, `/api/models/install`,
  `/api/models/remove`, `src/hutch/server/static/model-install.js`), measured residency from
  `/api/ps`, loopback discovery of five fixed endpoints (`src/hutch/providers/discovery.py`).
- Strict Offline: bubblewrap network namespace plus per-run Unix-socket broker (`src/hutch/offline.py`,
  `src/hutch/sandbox.py` `offline_egress_status`). Probe passes on the dev host. A live model has
  never been driven through it (old phase D).
- Tool-calling profiles for llama.cpp and LM Studio in `src/hutch/toolcalling/profiles.py`;
  per-model reliability qualification `src/hutch/reliability.py`.

Confirmed gaps (reproduced by reading code and running the validator on 2026-11-05; Phase 0 must
reproduce each against the real stack and then fix or reclassify):

| ID | Gap | Evidence | Seam |
|---|---|---|---|
| G1 | The install name validator refuses the most common real-world pull forms: `hf.co/<user>/<repo>:Q4_K_M`, any uppercase quant tag such as `llama3.2-vision:11b-instruct-q4_K_M`, `Qwen3:4B`, a registry-host prefix. It accepts `-cloud` tags. | `validate_model_name` run on eight real names: six refused | `providers/model_install.py:41-59` |
| G2 | "Is this route local?" is a name regex for Ollama cloud tags (`providers/pricing.py:25`), while `OllamaProvider.data_stays_local()` (`providers/ollama.py:254`) looks at the host only and ignores the model. Its caller `runtime/builtin.py:299` therefore treats a `-cloud` model served through loopback Ollama as data-stays-local. Public reports show cloud models passing as local. | code read; confirm with a test and the server signal (`remote_host`/`remote_model`, `OLLAMA_NO_CLOUD`) on the real runtime | `providers/pricing.py`, `providers/ollama.py`, `runtime/builtin.py` |
| G3 | The "On this machine" choice group only exists for Ollama (`modelchoices.py:121-146` returns early unless Ollama is up). LM Studio, llama.cpp and vLLM models found by discovery have no first-class local entry, fit estimate or state. Verify, then fix in a new module. | code read | `modelchoices.py` (frozen), `modelview.py` |
| G4 | No native introspection for LM Studio or llama.cpp. Nothing reads LM Studio `GET /api/v1/models` (loaded context, max context, vision, trained-for-tool-use) or llama.cpp `/props` (`n_ctx`, modalities), `/health` (503 while loading) or `/slots`. The LM-1 protections (applied window known, truncation detected) exist only for Ollama; for these runtimes the window is fixed at load or launch time and Hutch cannot set it per request. | `rg` for `/props`, `api/v0`, `mmproj`, `jinja` in `src/hutch` returns nothing | new module(s) under `providers/` |
| G5 | Strict Offline has never been driven with a live model (old phase D). | ADR-0009, offline-models doc 3.5 | `offline.py`, `sandbox.py`, `runtime/builtin.py` |
| G6 | Install has no disk-space preflight (no `disk_usage`/`statvfs` anywhere in `src/hutch`), no resume story, and a real multi-gigabyte pull through the page was never run. Install exists for Ollama only. | `rg` | `providers/model_install.py`, `model-install.js` |
| G7 | Discovery trusts a port: any process on 8080 or 8000 answering `/v1/models` is labelled llama.cpp or vLLM; a key-protected server is reported as "not a model list" because discovery sends no credential. | `providers/discovery.py:32-38,105-122` | `providers/discovery.py` |
| G8 | Frozen over-cap files you must not grow (shrink only): `modelchoices.py` (435), `providers/ollama.py` (432), `providers/openai_compat.py` (466), `runtime/builtin.py` (1955). New logic goes in new modules; extract before you add. | `.file-size-baseline.json` | `.ai/skills/split-god-file.md` |

Dev host (from the 2026-10-31 baseline; recheck): AMD Ryzen 3 5300U, 8 threads, 22 GiB RAM, integrated
AMD GPU only, so every run is CPU inference at roughly 16 to 19 prompt tokens per second. A retained
Ollama 0.40.13 and two models (`qwen3:4b`, `qwen2.5-coder:1.5b`, 3.8 GB) live in
`~/.hutch-tmp/localmodels/{ollama-dist,models}`; nothing is running now. `ollama`, `llama-server` and
`lms` are not on PATH. CUDA, ROCm, Metal and discrete-GPU paths cannot be live-verified here.

## Non-negotiable rules

1. No god functions or god files. Hard cap 400 lines per new source file. A function does one thing,
   aim for 40 lines or fewer, hard stop at 60. No function with more than 4 provider-specific
   branches: use a per-runtime adapter table (one small class or dict per runtime implementing one
   narrow protocol) and let data drive differences. Never extend a frozen file; split first
   (`.ai/skills/split-god-file.md`). `app.js` is frozen: new UI goes in new modules.
2. Real setup, not fixtures. Prove behavior with: the real FastAPI server on a real port against a
   fresh temporary `HUTCH_STATE_DIR`; real Ollama; a real `llama-server` with a real GGUF; LM Studio
   if obtainable; a real browser (Playwright Chromium); real images for vision. Fakes are allowed only
   to unit-test pure parsers and to inject failures a real server cannot produce on demand (truncated
   stream, HTTP 5xx, disk full). A fake never raises a status above implemented-unverified, a captured
   response is not live evidence, and deterministic "readiness response" stubs do not count for visual
   validation either. If something cannot be run, write "not run" plus the exact reason in the ledger; never
   simulate success. Do not create demo or sample data, preview pages in `static/`, or seeded
   conversations (`tests/test_no_demo_content.py`).
3. Offline honesty. "Local" and "offline" claims in UI, docs and the website must be backed by an
   enforced mechanism and a dated test. Hutch can claim that a run's worker had no network and that its
   model route went only to loopback. It cannot claim the model server was air-gapped. Whether Hutch
   should manage an isolated model process is an architectural decision: do not build it, write the
   options and ask the owner (Phase 6).
4. Preserve local-first, explicit approval. Do not broaden tools, permissions, provider access or data
   sharing as a side effect (`.ai/skills/change-approval-boundary.md`). Switching to a cloud-tagged model
   is a data-sharing change and needs explicit confirmation, never a silent substitution or fallback.
   Credentials (llama-server `--api-key`, LM Studio API tokens, Hugging Face tokens) never appear in
   URLs, API responses, logs, pages, screenshots, commits or the DB; use the existing vault and
   `Tool.recorded_arguments`/`reject_endpoint_credentials` patterns. Never read `.env*`, `*.db*`,
   `.state/`, `.aws/`, `.ssh/`, or the owner's real state dir.
5. Honest status vocabulary only (implemented, implemented-unverified, experimental, documented,
   blocked, retired, deferred). A catalogue row is not a support claim. UI, docs and the website do not
   say "supported" without a dated live-verified record from this machine.
6. Tool and schema discipline: any new or changed tool has canonical JSON Schema, catalogue entry and
   contract tests (`.ai/skills/add-tool.md`). Reuse `toolcalling/`; no second registry or validator.
   The native Ollama API stays the Ollama path (never the `/v1` shim).
7. Persisted state: pydantic models plus an ordered migration in `store.py` (frozen-adjacent: put the
   new logic in a new module), a `tests/fixtures/` compatibility input and `test_migration.py`
   coverage. Timestamps via `models.iso`/`models.utcnow`.
8. Work on `main`, commit progressively: one focused change per commit, concise imperative summary,
   explicit paths, no AI-attribution trailer (AGENTS.md overrides any tool default). Use a worktree only
   for a risky spike and merge it back within the same phase; never strand work on a branch. Never push,
   tag, publish, deploy, add a dependency (ask first), or touch another session's uncommitted work.
   `.commandcode/` is not yours.
9. No emoji in source, docs or UI (`scripts/audit_emoji.py`). Edit `app/src/` and `website/` sources,
   never generated CSS; run `npm run build:css --silent` after source changes.
10. Be surgical with context. Read line ranges, name exact files, never review the codebase. Never read
    lockfiles, `CHANGELOG.md`, generated CSS, `docs/**/artifacts/**`, `.worktrees/`, `node_modules/`.
    Use quiet commands.

## Real-setup test environment

- One scratch root for the whole run: `~/.hutch-tmp/offline-models-2026-11/`. Downloaded binaries and
  archives are untrusted: each in its own new empty directory, scripts kept elsewhere, Python run with
  `-I`, checksums or release signatures checked where the vendor publishes them.
- Download budget: at most 10 GB of new models and binaries in total; delete what you fetched when the
  phase ends unless a later phase needs it, and record sizes. Anything larger: ask the owner.
- Ollama: run the retained 0.40.13 with `OLLAMA_MODELS=~/.hutch-tmp/localmodels/models` bound to
  127.0.0.1. Also test the current release in a separate directory if it differs (version drift is
  EC-11). Run `python scripts/prune_validation_tmp.py` as a dry run only and confirm `localmodels/` is
  not listed before ever using `--apply`.
- llama.cpp: official release build for Linux x64 (CPU; Vulkan optional) from the ggml-org releases
  page plus the smallest GGUFs that cover text+tools and vision (projector included). Research picks
  the models; record why.
- LM Studio: proprietary app. Ask the owner once before installing; try the headless route (`lms`,
  `llmster`) documented at lmstudio.ai. If it is not obtainable here, record "not run" and ship that
  adapter as implemented-unverified with parser tests only.
- Offline proof: `unshare -rn` or Hutch's own bubblewrap path (`offline_egress_status` passes on this
  host) to run a full bot turn with no network at all.
- Slow hardware: use small models and short prompts; start long jobs in the background and wait for
  completion notifications instead of polling; never claim a speed figure you did not measure.

## Research requirements

Mandatory and before design in each phase. Full plan, source list and recording format in
`04-RESEARCH-PLAN.md`. Research what works and also what other apps and offerings failed at, and what
users complained about, then classify each item (integration/protocol, model-specific, hardware,
frontend usability, configuration) and decide fix, mitigate, disclose or out-of-scope with a test idea.
Record every source with URL, access date and the decision it changed in
`docs/research/2026-11-offline-models/`. Search results are leads: read the primary page before
asserting a fact.

## Validation and review gates (per phase, in order; report exact commands and results)

1. Focused tests for every touched behavior, written to fail before the change:
   `npm run test:agent -- tests/test_<x>.py`.
2. `npm run check:agent`; `npm run audit:context` when files grew;
   `uv run --frozen --no-sync python scripts/audit_emoji.py` when text changed.
3. Real-setup run recorded in `02-PROGRESS.md` evidence ledger: date, runtime and version, model and
   digest, route, hardware, what was and was not exercised, and measured numbers with the command that
   produced them.
4. Visual validation for any UI or website change. Capture with Playwright Chromium at 360, 768, 1280
   and 1920 px, light and dark, in each real state (runtime down, loading, ready, installing, failed,
   cloud-tagged, needs-key), following `docs/realignment/capture_*.py`. Then open the PNGs with the Read
   tool and look at them: record defects found and fixed, zero console errors, zero horizontal overflow,
   keyboard-only traversal of the new controls, focus order and visible focus, `aria-live` for progress,
   reduced-motion. Follow `docs/design-system.md`, `DESIGN.md`, `PRODUCT.md`. Run focused `tests/e2e/`
   for touched pages only (`test_model_picker.py`, `test_model_install.py`, `test_model_repair.py`,
   `test_models_detected_route.py`).
5. Multimodal checks: where a feature touches images, push a real image through the whole pipeline
   (attach, `providers/attachments.py` validation, wire conversion, answer that depends on the image
   content) on a real local vision model, and record the result. Use the same discipline for audio if a
   runtime accepts it.
6. Code review: re-read the phase diff as a skeptical reviewer. Hunt for god functions, silent
   fallbacks, status inflation, credential leakage, name-based guesses where a server signal exists,
   missing error states, dead code, files over cap. Run `/code-review` (and `/simplify`) on the diff if
   those skills are available. Fix, record findings and fix commits in `02-PROGRESS.md`. A whole-
   initiative review runs in Phase 9.
7. Docs in the same commit series: `docs/models.md`, `docs/runtime-setup.md`,
   `docs/realignment/offline-models-2026-10-31.md` (append a section, close D), `src/hutch/data/compat.json`
   rows, the research package, an ADR for any boundary decision (take the next free number in `docs/adr/`
   at commit time; 0027 exists), and `docs/release-checklist.md` if baseline counts change.
8. Merge state: everything on `main`, tree clean except others' work, worktrees removed only if fully
   merged.

## Website

Public claims follow `docs/marketing-site.md` (capability language table, development-preview stage,
no support claim without evidence). Touch `website/index.html` (JSON-LD around line 52, the local-model
copy near 561 and 582, badges near 625 and 723, FAQ entries on local models), `website/llms.txt`, and
`website/src/input.css` only if styling is needed. Only claim what a dated entry in `02-PROGRESS.md`
supports. Rebuild with `npm run build:css --silent`, run the website tests (`tests/test_site_tokens.py`
and whatever `rg -l "website/" tests` finds), capture with `docs/realignment/capture_marketing_top.py`, view the
images, fix defects. State the boundary in the site's own words: "this run's worker could not reach the
network" is allowed; "nothing leaves your machine" is not.

## Stop conditions

Ask the owner once, batched, only for: more than the 10 GB download budget, installing LM Studio, any
dependency, the managed-isolated-model-server decision, anything that spends money, pushing or
publishing. Otherwise decide, log the decision and reason in `02-PROGRESS.md`, and continue. If blocked,
say exactly what blocks and stop that item; do not simulate success.

## Launch prompt (paste into a fresh session)

```text
Read, in this order and nothing else first: @AGENTS.md,
@docs/realignment/offline-models-2026-11/00-MASTER-PROMPT.md,
@docs/realignment/offline-models-2026-11/01-PHASES.md,
@docs/realignment/offline-models-2026-11/02-PROGRESS.md. Load 03-EDGE-CASES.md and
04-RESEARCH-PLAN.md when your phase names them.

Resume at the first phase in 02-PROGRESS.md not marked done. Do only that phase in this session:
research first (live web, primary pages, plus failure and complaint mining, recorded under
docs/research/2026-11-offline-models/), then a short written design naming the exact files you will
touch (at most three source files plus one seam per task; split the phase into tasks), then implement
in small commits on main, then run the validation and review gates from the master prompt against the
real stack (real Ollama, real llama-server, real browser, real images), then update docs and, where the
phase says so, the website. No god functions, no fixture-only validation, no status inflation, no
downloads beyond the budget without asking. Update 02-PROGRESS.md at every checkpoint (committed,
verified live, blocked, decisions) and finish by stating the next phase. Do not stop at a task
boundary inside the phase.
```
