# Phase 8 research: public claims for local and offline models

Access date: 2026-11-06. Classification: frontend usability, configuration.

## Primary sources read

- Ollama FAQ (https://docs.ollama.com/faq), accessed 2026-11-06: local models keep
  prompts on the machine; cloud models are processed by ollama.com; `disable_ollama_cloud`
  in `~/.ollama/server.json` or `OLLAMA_NO_CLOUD=1` disables cloud features; the default
  context window is 4,096 and `num_ctx` overrides it; Linux does not auto-update the
  Ollama install (macOS/Windows do); model pulls use the network; the server binds
  127.0.0.1 by default.
- Ollama Cloud (https://docs.ollama.com/cloud), accessed 2026-11-06: cloud models do not
  need a download and run on ollama.com; the API key is for ollama.com, not the local
  server; cloud prompts are processed to answer the request and are not used to train.
- Hutch evidence: `docs/realignment/offline-models-2026-11/02-PROGRESS.md` (Ollama
  0.40.13/0.40.15, llama.cpp b12144, LM Studio 0.0.27-1; Phase 1-7 live rows) and
  `docs/realignment/offline-models-2026-10-31.md` section 5 (the exact offline claim).

## Findings

- F-P8-1 (integration/protocol): a loopback URL does not prove a runtime stays local.
  Ollama can pull, check its release cadence and forward cloud-tagged models; LM Studio
  has its own catalog/update behavior; llama.cpp can fetch with `-hf`. The site must say
  the worker boundary is enforced and the model-server boundary is not.
- F-P8-2 (configuration): `OLLAMA_NO_CLOUD=1` is the runtime's own switch; Hutch reads
  the server signal (`remote_host`/`remote_model`) first and uses the name only as a
  fallback. The site can name the switch and the signal without claiming Hutch enforces
  them.
- F-P8-3 (frontend usability): a public "offline" badge without a boundary table invites
  the reading "nothing leaves my machine". The honest sentence is scoped: this run's
  worker could not reach the network and its model route went to loopback; the model
  server is a separate process Hutch does not isolate yet (ADR-0035 is accepted, not
  implemented).
- F-P8-4 (model-specific): the current verified local set is one host and one build per
  runtime (Ollama 0.40.13/0.40.15, llama.cpp b12144, LM Studio llmster 0.0.27-1). Public
  rows must name the version/date and must not generalize to GPU, other OSes, vLLM or
  SGLang.
- F-P8-5 (frontend usability): a model switch that crosses the machine boundary needs a
  visible confirmation. The EC-28 dialog now names the assistant, route and what moves;
  the site may describe that behavior but not claim the model server is isolated.

## Decisions

- D-P8-1: one short, visible "Local and offline" block with a three-row boundary table
  (worker egress enforced; model server not isolated; runtime updates/telemetry not
  controlled by Hutch), plus the exact sentence Hutch may say.
- D-P8-2: capability rows for local runtimes stay experimental on the public site until a
  dated multi-host or multi-build record exists; the compatibility file carries the
  per-route dated evidence and limits.
- D-P8-3: `llms.txt` carries the same boundary; no new marketing claim beyond the dated
  ledger.
- D-P8-4: the EC-28 confirmation and the local-runtime state labels are described as
  product behavior on the site and in `docs/models.md`, with test names.
