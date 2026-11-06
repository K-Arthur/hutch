# ADR-0031: Local model acquisition is runtime-native

Status: accepted, 2026-11-06.

## Context

Hutch can install and remove Ollama models, but the runtime's own API is the only place
that can verify a blob, resume a pull, and confirm that a model exists. LM Studio has a
native download endpoint and a CLI, but its documented API has no cancel operation and no
catalog-list endpoint; llama.cpp downloads at server launch from `-hf` and cannot be
started or cancelled through its request API; vLLM and SGLang are launch-time services.
A second, uniform downloader would have to re-implement digest verification and resume,
and would inevitably claim more than each runtime can prove.

The install name grammar also disagreed with the runtime: the old validator refused
mixed-case quant tags, registry hosts, and the real Hugging Face forms. That was a
Hutch bug, not a runtime limitation.

## Decision

1. **Ollama owns the bytes.** Hutch calls `/api/pull` for installs, `/api/delete` for
   removal, and `/api/blobs` plus `/api/create` for a local GGUF import. Success means the
   runtime's stream ended with `success` **and** the model appears in `/api/tags`. A
   cancelled pull is a closed stream; a resume is a new pull; Hutch does not implement
   its own downloader or resume.
2. **Hutch owns the preflight and the visible state.** Before a pull, Hutch computes the
   catalog size, free space on the runtime's documented model directory, the fit estimate
   and a measured-rate ETA. A known insufficient size is refused; unknown values stay
   unknown. The server re-runs the same plan on the write path, so the page cannot skip
   it. The job record carries the runtime's counters, the live rate, the failure code and
   one action.
3. **Import goes through the runtime's blob API.** Hutch validates the GGUF header, hashes
   the file, checks `HEAD /api/blobs/<digest>`, uploads only when absent, creates with the
   original filename and digest, and confirms the model. The runtime verifies the digest
   again. A sidecar or supplied license is displayed; a missing license is not invented.
4. **Other runtimes are guided, not wrapped.** LM Studio gets `lms get <model>@<quant>`;
   llama.cpp gets `llama-server -hf <user>/<repo>:<quant>` with `-hft`/`HF_TOKEN` for gated
   repos and the documented HF cache order; vLLM/SGLang get launch guidance. Their files
   land in their own directories, and reopening the Models page re-scans discovery. Hutch
   does not invent a job for a download it cannot cancel or track.
5. **Credentials stay with the runtime.** A gated Hugging Face token or an Ollama sign-in
   is configured in that runtime. Hutch never accepts it in a URL, stores it in a job, or
   prints it; runtime error text is redacted before it reaches a page, a log or a result.
6. **Resume wording is conditional.** Ollama keeps complete chunks until the pull resumes
   or the server restarts, and some transfer paths restart a blob from zero. Hutch says
   "the runtime keeps verified parts" only after a prior attempt received bytes, and never
   claims a restart resume. `OLLAMA_NOPRUNE=1` is the runtime's own switch for that case.

## Consequences

- A person can install, cancel, resume and import from the dashboard without a terminal;
  a terminal command remains available for every runtime.
- A failed install is a state with one action (free space, retry, start the runtime,
  configure the runtime's credential, or check the name), not a raw error string.
- Hutch cannot promise that a download survives a runtime restart, and does not claim the
  model server is air-gapped. The worker-egress boundary remains the Phase 6 decision.
- The visible import form and the full local-runtimes panel are Phase 7 work; the API,
  preflight and job behavior are implemented and dated in `02-PROGRESS.md`.
- Tests: `tests/test_model_names.py`, `tests/test_install_plan.py`,
  `tests/test_install_errors.py`, `tests/test_model_install.py`,
  `tests/test_model_install_api.py`, `tests/test_model_import.py`,
  `tests/test_model_import_api.py`; live evidence in the Phase 4 ledger.
