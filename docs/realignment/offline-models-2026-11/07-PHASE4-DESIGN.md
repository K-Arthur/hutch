# Phase 4 design: get a model (install, import, guide)

Research: `docs/research/2026-11-offline-models/05-PHASE4-INSTALL.md` (P4-1 to P4-13,
R33-R41). Exit checks: G1, G6; EC-15, EC-20, EC-23. Frozen files: none of the four
(`modelchoices.py`, `providers/ollama.py`, `providers/openai_compat.py`,
`runtime/builtin.py`) are touched. New files stay under 400 lines, functions under 60.

## Task 1 - name grammar (G1, EC-15)

Files:
1. new `src/hutch/providers/model_names.py` - `ModelName` (host, namespace, model, tag,
   digest), `parse_model_name`, `canonical_model_name`, `same_model`; the grammar, defaults
   and case-insensitive equality from Ollama's `types/model/name.go` plus the real
   `hf.co/<user>/<repo>:<quant>` forms. Cloud refusal stays here via `locality.CLOUD_TAG`.
2. `src/hutch/providers/model_install.py` - `validate_model_name`, `_split_name` and
   `_same_model` delegate; the lowercase regex is deleted. This file only shrinks its
   name logic; it grows in Task 2.
3. `tests/test_model_names.py` new table built from names read on the live Ollama library
   and Hugging Face pages; `tests/test_model_install.py`'s `Qwen3:4B` refusal expectation
   is corrected with the source citation.

Why: one parser, one normalization, and the install job and remove path cannot disagree.

## Task 2 - preflight and measured rate (G6, EC-23)

Files:
1. new `src/hutch/providers/install_plan.py` - `InstallPlan`; `ollama_model_dir()`
   (`OLLAMA_MODELS`, else `$HOME/.ollama/models`, source named), `free_bytes()`,
   `build_plan(model, base_url, state_dir)`; `estimate_fit` at 16k; a persisted
   `install_speed.json` (atomic write, one sample) for a measured-rate ETA; a 512 MiB
   reserve and an unknown-size warning. Non-loopback or unreadable paths are `unknown`,
   never a guessed number.
2. `src/hutch/providers/model_install.py` - `ModelInstaller(provider, state_dir=None)`;
   `start()` builds and enforces the plan, refuses an insufficient disk with the exact
   free/need numbers, and records `size_bytes`, `size_source`, `free_bytes`, `fit`,
   `eta_seconds`, `speed_bytes_per_s`, `warnings` on the job; `_apply` measures the
   current blob's rate and ETA from the runtime's counters; `_finish` records one speed
   sample.
3. `tests/test_install_plan.py` new: known/unknown size, loopback vs non-loopback, the
   default and `OLLAMA_MODELS` paths, insufficient disk, fit label, ETA from a sample.

## Task 3 - preflight gate in the page (4.2)

Files:
1. `src/hutch/server/pages_models.py` - `GET /api/models/install/plan` (CSRF not needed
   for a read) returns the plan JSON; `POST /api/models/install` already re-plans through
   `start()`, so a client cannot skip the check.
2. `src/hutch/server/static/model-install.js` - clicking Install first fetches the plan and
   renders a text-only confirmation block (size, free, fit, measured-rate ETA or
   "time unknown", warnings) with Confirm and Back. Only Confirm posts the install.
   No template or CSS change.
3. `tests/test_model_install_api.py` - plan endpoint; blocked plan refuses; confirm path
   still installs. `tests/e2e/test_model_install.py` gains the Confirm click.

Why: the person sees the facts before the download and the server enforces the same facts.

## Task 4 - failure states, reload and resume (4.3)

Files:
1. new `src/hutch/providers/install_errors.py` - `classify_install_error(text, free,
   size)` -> `{code, message, action}` for disk full, network drop, runtime down,
   auth/gated, missing tag, integrity, unknown; `redact_secrets` removes sign-in URL
   keys, bearer tokens and `hf_` tokens before the text reaches a job, a page or a log.
2. `src/hutch/providers/model_install.py` - `start()` returns the active job for the same
   model instead of a duplicate error (double click and two tabs share one download);
   a new job is marked `resumed` only when a prior job for the same model in this process
   ended with received bytes; failed jobs carry `error_code`/`action`; cancel and
   interruption use the same classifier.
3. `src/hutch/server/static/model-install.js` - on page load, fetch the job list and
   reattach polling to a visible row (a page reload does not lose a running job); a 404
   says Hutch restarted and pressing Install resumes; a cancelled/failed job offers
   Install again with the conditional resume wording.

Tests: `tests/test_install_errors.py` new with captured bytes; `test_model_install.py`
for idempotent start, resume flag and redaction; the real disk-full and network-drop
evidence goes in `02-PROGRESS.md`.

## Task 5 - local GGUF import (4.5, EC-20)

Files:
1. new `src/hutch/providers/model_import.py` - path checks (regular `.gguf` file, not
   `/proc`, `/sys`, `/dev`), streaming SHA-256, optional expected digest, optional sidecar
   license text, `import_local_model(provider, path, name, expected_sha256, license)`:
   HEAD blob, upload only if absent, POST `/api/create` with `files`, confirm in
   `/api/tags`, read `/api/show` for license and capabilities, return an
   `ImportResult`.
2. `src/hutch/providers/ollama_extras.py` - `blob_exists`, `put_blob` (streamed, explicit
   length), `create_model` (ndjson stream); no change to `providers/ollama.py`.
3. `src/hutch/server/pages_models.py` - `POST /api/models/import` with CSRF, JSON body
   `{name, path, sha256?, license?}`, 422 for a bad name/path, 404 for a missing file,
   409 for a runtime refusal; the response carries digest, size, license source and
   capabilities. The visible form is Phase 7; the endpoint is usable and tested now.
4. `tests/test_model_import.py` and `tests/test_model_import_api.py` new.

Why: the runtime still verifies and stores the bytes; Hutch only reads, hashes, uploads
and displays. A UGGF without a license is shown as "not provided", never guessed.

## Task 6 - other runtimes and docs (4.4)

No new download surface. `docs/runtime-setup.md` and `docs/models.md` get the exact guided
commands and locations:
- LM Studio: `lms get <model>[@quant]`, LM Studio's model directory, native download
  status exists but no cancel; re-scan by reopening the runtime list. No Hutch job.
- llama.cpp: `llama-server -hf <user>/<repo>:<quant> --mmproj ...`, `-hft`/`HF_TOKEN` for
  gated repos, `--offline` after the fetch, cache path order from P4-10. No Hutch job.
- vLLM/SGLang: launch command guidance only (not installed here).
- Ollama: install/import through Hutch (Tasks 2-5), `OLLAMA_NOPURGE` not required for the
  same-process resume; a runtime restart may prune partials.
ADR-0031 records the boundary: runtime-native acquisition, no uniform downloader, Hutch
owns preflight/import/visibility only. The re-scan button belongs to Phase 7's runtime
panel; Phase 4's action is a page reload, which re-probes discovery.

## Validation

- Focused tests for every task, written to fail before the change; existing
  install/offline/model suites.
- Real: retained Ollama 0.40.13, `qwen2.5-coder:3b` (1.9 GiB, in the catalog so the page
  has a real button) pulled through the real page, cancelled once and resumed once, with
  both attempts' byte events recorded; a second real `qwen3:1.7b` pull repeated the
  running/cancelled states after the layout fix; a real import of the retained
  `qwen3-4b` GGUF with its SHA-256 checked against the runtime's blob and license read
  from `/api/show`; a real 1.93 GB upload of the vision GGUF that was not in the store; a
  real disk-full pull inside `unshare -rm` with a 300 MiB tmpfs; a real network-drop pull
  inside `unshare -rmn`; the page states captured at four widths (dark only, the
  dashboard's real theme) and viewed. The first view found a clipped, nowrap install
  panel and a clipped pull hint; both were fixed with a full-width plan row, a readable
  width cap, and wrapped state/hint text, then re-captured.
- Gates: `npm run test:agent`, `npm run check:agent`, `npm run audit:context`,
  `scripts/audit_emoji.py`, focused e2e, phase-diff review, docs in the same series.
- Honest limits: no gated Hugging Face token; LM Studio/vLLM/SGLang install is guided
  only; the 1.9 GiB pull is "multi-gigabyte" but below the 4 GB class recorded as not run
  in Phase 3.
