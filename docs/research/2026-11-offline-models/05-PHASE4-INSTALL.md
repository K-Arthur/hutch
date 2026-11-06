# Phase 4 research: getting a model (2026-11-06)

Narrow pass for Phase 4: the install name grammar (G1), disk/size/time preflight and
resume (G6), the other-runtime download decision (4.4), and local GGUF import (4.5). The
Phase 0 API notes and R19 remain valid; this note records only what changed the design.
Every source below was opened on 2026-11-06. Search snippets were leads only.

## Sources and decisions

| # | Source | Fact taken | Class | Decision it changed |
|---|---|---|---|---|
| P4-1 | https://docs.ollama.com/api/pull | The pull body accepts `model`, `insecure` and `stream` (default true). The response is a stream of status objects. There is no cancel parameter. The older API reference states that cancelled pulls are resumed from where they left off and that concurrent calls share the same download progress. | integration/protocol | Cancelling means closing the response stream. Resuming means requesting the same pull again. Hutch does not implement its own downloader or resume. |
| P4-2 | https://raw.githubusercontent.com/ollama/ollama/main/docs/api.md | Pull progress is per blob: `status`, `digest`, `total`, `completed`; the stream ends with `verifying sha256 digest`, `writing manifest`, `removing any unused layers`, `success` (or `error`). Create-from-GGUF requires a blob push per file and a `files` map of original filename to `sha256:` digest; `HEAD /api/blobs/:digest` reports existence and `POST` uploads; a wrong digest is refused with 400. `/api/create` accepts `license`; `/api/show` returns the stored license and capabilities. | integration/protocol | Import computes SHA-256 locally, asks the server whether the blob exists, uploads only if needed, creates with the original filename, then confirms against `/api/tags` and `/api/show`. The runtime's digest check is the integrity gate; Hutch's local hash is the pre-upload check. |
| P4-3 | https://raw.githubusercontent.com/ollama/ollama/main/types/model/name.go | The accepted name shape is `[host/][namespace/]model[:tag]`. Defaults are `registry.ollama.ai`, `library`, `latest`. Host allows letters, digits, `_`, `.`, `-`, `:` (so a port works), 1 to 350 characters. Namespace allows letters, digits, `_`, `-` (no dot), 1 to 80. Model and tag allow letters, digits, `_`, `.`, `-`, 1 to 80, and are case-sensitive on the wire while model equality uses `EqualFold`. | integration/protocol | The lowercase-only regex is wrong. The parser accepts mixed case, registry hosts and ports, and compares models case-insensitively. This is G1. |
| P4-4 | https://huggingface.co/docs/hub/ollama | `hf.co/<user>/<repo>` and `huggingface.co/<user>/<repo>` pull a GGUF; the default quant is Q4_K_M; a quant tag is case-insensitive; a full GGUF filename can be used as the tag. | model-specific | Table tests include the real `hf.co/bartowski/...:Q4_K_M` and `hf.co/unsloth/...:Q5_K_M` forms, mixed-case tags, and full filenames. |
| P4-5 | https://github.com/ollama/ollama/issues/12507 | A maintainer states that an interrupted pull keeps completely downloaded chunks until the pull is resumed or the server is restarted; re-running the pull resumes. `OLLAMA_NOPRUNE=1` keeps chunks across a server restart. Completed chunks can lag the displayed percent. | configuration | Resume is conditional on the runtime keeping its parts. Hutch says "the runtime keeps verified parts, so this resumes" only after observing a prior attempt; it never promises resume across a runtime restart. |
| P4-6 | https://github.com/ollama/ollama/issues/15320 | The standard downloader resumes with HTTP Range requests; the transfer path used for some pulls writes a `.tmp` file, deletes it on failure, and restarts the blob from zero. The reporter calls the user-visible behavior inconsistent. | integration/protocol | Hutch never claims universal resume and never reports the previous byte count as if it were progress. The job shows the bytes the runtime reports on this attempt. |
| P4-7 | https://raw.githubusercontent.com/ollama/ollama/main/envconfig/config.go | `OLLAMA_MODELS` selects the model directory; the default is `$HOME/.ollama/models`. `OLLAMA_NOPRUNE` disables startup pruning. No endpoint exposes the model directory or free disk. | configuration | Preflight reads `OLLAMA_MODELS` from Hutch's environment, else the documented default, and only for a loopback runtime. A non-loopback or unreadable directory is reported as unknown, with the path named. |
| P4-8 | https://lmstudio.ai/docs/developer/rest/download and https://lmstudio.ai/docs/developer/rest/download-status | `POST /api/v1/models/download` accepts a catalog id or an exact Hugging Face link plus an optional quant; it returns a job id and total size. `GET /api/v1/models/download/status/:job_id` returns `downloading`, `paused`, `completed` or `failed`, with downloaded bytes, bytes per second and estimated completion. No cancel endpoint is documented. The CLI equivalent is `lms get <model>[@quant]`. | integration/protocol | Phase 4 does not add an LM Studio install surface: it has a native download but no cancel operation and no catalog-list endpoint Hutch can use for a safe picker. It gets an exact guided command and a re-scan note. |
| P4-9 | https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md | `-hf <user>/<model>[:quant]` downloads at server start, defaults to Q4_K_M, fetches an available projector unless `--no-mmproj`, and accepts `-hft TOKEN` or `HF_TOKEN`. `--offline` forces cache use and prevents network access. The server listens on 9931 by default. | integration/protocol | llama.cpp gets a guided launch command, not a Hutch downloader: there is no runtime API to start or cancel the fetch, and the download happens before the server answers. |
| P4-10 | https://deepwiki.com/ggml-org/llama.cpp/7.4-model-acquisition-and-management (cites `common/hf-cache.cpp` and `common/download.cpp`) | The HF cache base is chosen from `LLAMA_CACHE`, `HF_HUB_CACHE` or `HUGGINGFACE_HUB_CACHE`, `HF_HOME/hub`, `XDG_CACHE_HOME/huggingface/hub`, then `~/.cache/huggingface/hub`. The downloader keeps a temporary file and resumes with a Range request when the server returns 206. | configuration | The guide names the cache path and the environment variable order, so "where files land" is answerable without guessing. |
| P4-11 | https://ollama.com/library/qwen2.5:3b and https://ollama.com/library/qwen2.5-coder:3b | The Qwen2.5 3B and Qwen2.5-Coder 3B tags are each about 1.9 GB, Q4_K_M, tool-capable, and carry the Qwen Research License. | model-specific | The real multi-gigabyte pull/cancel/resume uses `qwen2.5-coder:3b`, because it is in `src/hutch/data/catalog.json` and therefore has a real Install button on the page; `qwen2.5:3b` is a valid arbitrary name but has no catalog size or button. Both are inside the remaining budget. |
| P4-12 | https://docs.ollama.com/api/create and https://docs.ollama.com/api/show | Create accepts `files`, `license`, `parameters`, `template` and `system`; show returns `license`, `capabilities`, `details` and `model_info`. | integration/protocol | Import can record a user-supplied license and reads the runtime's own report back; it never invents a license. |
| P4-13 | Local host, 2026-11-06 | `unshare -rm` with a tmpfs keeps host networking and permits a real Ollama pull into a tiny filesystem; `unshare -rmn` with loopback up has no external route. Both work without root on this host. | hardware | The disk-full and network-drop checks can be produced for real rather than with a fake error stream. |

## Gap reproductions on the real stack

### G1: install name grammar

The retained Ollama 0.40.13 was running at `127.0.0.1:11434`. The installed
`hutch.providers.model_install.validate_model_name` was called on ten real forms:

```
FAIL hf.co/bartowski/Llama-3.2-3B-Instruct-GGUF:Q4_K_M
FAIL hf.co/unsloth/Qwen3-4B-GGUF:Q4_K_M
FAIL llama3.2-vision:11b-instruct-q4_K_M
FAIL Qwen3:4B
FAIL qwen3:4b-instruct-2507-q4_K_M
FAIL registry.ollama.ai/library/qwen3:4b
OK   qwen3:4b
OK   library/qwen3:0.6b
OK   gpt-oss:20b-cloud
OK   qwen3:4b-cloud
```

Six of ten are refused. The refusals come from the lowercase-only regex, not from the
runtime: P4-3 and P4-4 show the accepted grammar and the real Hugging Face forms. G1 is
reproduced.

### G6: no disk preflight, no real pull evidence

```
rg -n "disk_usage|statvfs|shutil\.disk|free space|free disk" src/hutch
  -> one unrelated sentence in server/static/app.js
rg -n "OLLAMA_MODELS|OLLAMA_NOPRUNE" src/hutch
  -> no match
```

The retained store is `~/.hutch-tmp/localmodels/models` (3.8 GB); the filesystem has
70.4 GiB free. The runtime reports installed sizes in `/api/tags` but exposes no free-space
or model-directory endpoint. No install request checks either before starting. G6 is
reproduced.

## Failure mining addendum (R33 onwards)

- **R33** https://docs.ollama.com/api/pull and the older
  https://raw.githubusercontent.com/ollama/ollama/main/docs/api.md. A cancelled pull
  resumes from the runtime's own verified parts, and concurrent pulls of the same model
  share progress. Class: integration/protocol. Hutch response: fix. Test: a real
  multi-gigabyte pull cancelled once and resumed, with the runtime's byte counters
  recorded on both attempts.
- **R34** https://raw.githubusercontent.com/ollama/ollama/main/types/model/name.go. The
  runtime accepts mixed case, host prefixes and ports, and compares model equality
  case-insensitively. Class: integration/protocol. Hutch response: fix. Test: table of
  real names, including `Qwen3:4B` and `registry.ollama.ai/library/qwen3:4b`.
- **R35** https://huggingface.co/docs/hub/ollama. Hugging Face pull names use
  `hf.co/<user>/<repo>[:quant]`; quant tags are case-insensitive and the full GGUF
  filename is accepted as a tag. Class: model-specific. Hutch response: fix. Test: the
  exact strings from the Hugging Face page.
- **R36** https://github.com/ollama/ollama/issues/12507. Interrupted chunks survive until
  the pull resumes or the server restarts; `OLLAMA_NOPRUNE=1` changes the restart case.
  Class: configuration. Hutch response: disclose. Test: cancel, resume in the same server
  process; do not claim a restart resume.
- **R37** https://github.com/ollama/ollama/issues/15320. Some pull paths restart a blob
  from zero after a failure; the standard path resumes with Range requests. Class:
  integration/protocol. Hutch response: disclose. Test: report only the bytes this
  attempt received and never synthesize a resumed percentage.
- **R38** https://lmstudio.ai/docs/developer/rest/download and
  https://lmstudio.ai/docs/developer/rest/download-status. LM Studio can start a native
  download and report status, but the documented API has no cancel and no catalog list.
  Class: integration/protocol. Hutch response: disclose and guide. Test: the guide names
  `lms get <model>@<quant>` and the LM Studio model directory; no Hutch job is invented.
- **R39** https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md
  and the HF cache source above. llama.cpp downloads at launch from `-hf`, defaults to
  Q4_K_M, and can fetch a projector; the cache path is environment-driven. Class:
  configuration. Hutch response: guide. Test: the exact launch command and cache path are
  in `docs/runtime-setup.md`; nothing in Hutch starts a download.
- **R40** https://raw.githubusercontent.com/ollama/ollama/main/envconfig/config.go. The
  model directory is `OLLAMA_MODELS` or `$HOME/.ollama/models`; no API exposes it or free
  space. Class: configuration. Hutch response: fix. Test: preflight names the directory
  and reads free space only when the runtime is loopback and the path is readable;
  otherwise it says unknown.
- **R41** https://ollama.com/library/qwen2.5:3b. A real 1.9 GB Q4_K_M tool-capable model
  with the Qwen Research License. Class: model-specific. Hutch response: use as the real
  pull target and as the license-display case. Test: pull through the page, cancel once,
  resume, then read `/api/show` license.

## Decisions

1. **Name grammar follows the runtime source, not a guessed regex.** The parser accepts
   the P4-3 shapes and the P4-4 Hugging Face forms, normalizes defaults only for display
   and duplicate detection, and still refuses cloud tags unless the caller confirmed.
2. **No uniform downloader.** Ollama owns its pull and blob verification. LM Studio and
   llama.cpp get exact guided commands because their native paths lack the operations
   (cancel, catalog) a Hutch job needs. Local GGUF import uses Ollama's own blob and create
   APIs, so the runtime still verifies and stores the bytes.
3. **Preflight is runtime-owned data plus local arithmetic.** Size comes from the catalog
   when the name is a known suggestion, otherwise it is unknown until the runtime reports
   a blob. Free space comes from the model directory the runtime documents. Time comes
   from a measured prior transfer rate, never a guessed bandwidth.
4. **Resume wording is conditional.** Hutch re-requests the pull and reports the runtime's
   counters; it says "the runtime keeps verified parts" only when a prior attempt in this
   process left bytes, and it never claims a restart resume.
5. **Import verifies before upload.** Local SHA-256 is compared to a supplied expected
   digest, the server's blob endpoint verifies again, and `/api/show` supplies the license
   and capabilities that are displayed. A missing license is shown as missing.

## Not run, and why

| Item | Reason |
|---|---|
| Gated Hugging Face pull | No Hugging Face token or gated repository access on this host; the guide names the runtime's own token (`HF_TOKEN`/Ollama sign-in) and no token enters a Hutch URL. |
| LM Studio native download through Hutch | Deliberately not implemented (P4-8 decision); `lms get` is the guided path. |
| vLLM and SGLang install | Not installed; a Python dependency and a large download need the owner's approval. Guided path only. |
| Older Ollama without `/api/blobs` | The retained and current runtimes both accept blob create; the feature is gated by runtime evidence, not a guessed version. |
