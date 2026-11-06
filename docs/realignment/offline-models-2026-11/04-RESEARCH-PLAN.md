# Research plan

Mandatory in Phase 0 and again, narrower, at the start of each later phase. Read the primary page; a
search snippet is a lead, not a fact. Today's date when this plan was written: 2026-11-05. Record every
source in `docs/research/2026-11-offline-models/` with URL, access date, the fact taken, the decision it
changed, and a classification: integration/protocol, model-specific, hardware, frontend usability,
configuration. Continue the R-numbering from R14 (the 2026-10-31 doc ends at R13). Extend
`docs/research/offerings-and-failures.md` and `docs/research/complaints.md` instead of restarting them.
Never copy wording from vendors or forums; paraphrase and cite.

## A. Primary documentation (read in full where it bears on a task)

| Source | Questions to answer |
|---|---|
| https://docs.ollama.com/api/introduction and the API pages it links | Every endpoint Hutch uses or could: `/api/tags`, `/api/show`, `/api/ps`, `/api/pull`, `/api/delete`, `/api/create`, `/api/version`, `/api/chat`. Exact response fields on the installed 0.40.13 and on the current release. Does `/api/tags` or `/api/show` mark cloud models (`remote_host`, `remote_model`)? What do errors look like mid-stream? |
| https://docs.ollama.com/quickstart | What a first-time user is told; what the app downloads and when. |
| https://github.com/ollama/ollama/tree/main/docs | Context length defaults, `keep_alive`, `OLLAMA_*` environment variables (`MAX_LOADED_MODELS`, `NUM_PARALLEL`, `KV_CACHE_TYPE`, `FLASH_ATTENTION`, `IGPU_ENABLE`, `NO_CLOUD`, `MODELS`, `HOST`, `ORIGINS`), GPU support matrix, FAQ and privacy statements, cloud, import/Modelfile, Hugging Face `hf.co` pulls. |
| https://github.com/ggml-org/llama.cpp and https://llama-cpp.com/ | `tools/server/README.md` and the function-calling doc: `/health`, `/props`, `/slots`, `--jinja`, `--chat-template-file`, `--parallel`, context shift, router mode (`--models-dir`, `--models-max`, load/unload endpoints), `-hf` and cache location, `--mmproj`, multimodal and audio, `--api-key`, `--host` default bind. Release assets and checksums for the Linux CPU/Vulkan builds. |
| https://lmstudio.ai/ , https://lmstudio.ai/docs/app , https://lmstudio.ai/models | Native REST `/api/v1/*` (chat, models, load, unload, download, download status), the older `/api/v0`, OpenAI-compatible endpoints, API tokens and authentication, default bind and port, JIT loading, idle TTL and auto-evict, context overflow policy, headless `llmster` and `lms` on Linux, license and terms for use. Which model catalog entries are tool- and vision-capable. |

## B. Failure and complaint mining (what others got wrong, what users hate)

Search GitHub issues (open and closed), Hugging Face discussions, Reddit r/LocalLLaMA, r/ollama,
r/LocalLLM, Hacker News and vendor forums, last 18 months first. Queries to start from, then follow the
threads:

- Ollama: "cloud model shows as local", "num_ctx ignored", "context 4096 truncated", "tool calling not
  working <model>", "model loading takes forever", "runs on CPU instead of GPU", "out of memory
  silently falls back", "keep_alive unloads", "pull stuck at 99%", "no space left on device pull",
  "hf.co pull fails", "Modelfile template breaks tools", "OLLAMA_HOST exposed".
- llama.cpp: "tool calls not parsed --jinja", "tool call id rejected", "chat template error", "context
  shift removes system prompt", "--parallel context divided", "mmproj missing image fails", "server 503
  loading model", "router mode model eviction".
- LM Studio: "parser breaks reasoning tool calls", "JIT load timeout", "model unloaded mid-chat",
  "context overflow truncate middle", "API token required", "server not reachable from WSL/Docker".
- Other products to survey for what they ship and what users report: Open WebUI, Jan, Msty, AnythingLLM,
  GPT4All, Cherry Studio, Page Assist, Enchanted, Continue, Cline, Aider, OpenCode and OpenClaw local
  modes. For each: how it detects runtimes, how it presents model fit, install UX, offline/privacy
  claims and the complaints against them.

For each finding write one line: complaint, evidence link, class, who can fix it (Hutch, runtime, model,
hardware), Hutch response (fix, mitigate, disclose, out of scope), and a test idea that uses the real
runtime. Prefer complaints with a reproduction. Drop anything you cannot trace to a primary source.

## C. Seeded leads (found 2026-11-05 from search snippets and vendor pages; re-verify before relying)

- Ollama `/api/ps` documents `size`, `size_vram`, `context_length`, `expires_at`, `digest`, `details`.
- LM Studio 0.4.0 made the native `/api/v1/*` REST API official (chat, models, load, unload, download,
  download status). `GET /api/v1/models` lists `loaded_instances[].config.context_length`,
  `max_context_length`, `quantization`, `format`, and `capabilities` (`vision`, `trained_for_tool_use`,
  `reasoning`). The docs example uses a bearer token; confirm whether it is required and the default bind.
- llama.cpp server: `/health` returns 503 "Loading model" until ready; `/props` returns
  `default_generation_settings.n_ctx`, `total_slots`, `chat_template`, `modalities`; `/slots` on by
  default; router mode flags `--models-dir`, `--models-max` (default 4), `--models-autoload`;
  `-hf <user>/<model>[:quant]` defaults to Q4_K_M and fetches the projector unless `--no-mmproj`;
  `--api-key`.
- Ollama cloud models (`-cloud`/`:cloud`) run through the local server and are forwarded to ollama.com;
  guidance says to check for the suffix, and a local-only switch (`OLLAMA_NO_CLOUD`) is reported.
  Related public issues: IncarnaMind #174 (cloud model passes as local; proposes `remote_host`/`remote_model`
  detection) and ollama/ollama #14279 (cloud data-retention questions).
- llama.cpp tool-calling defects reported in 2026: #26359 (tool-call id rejected when echoed back with
  `--jinja`, Mistral) and #22581 (Qwen3-Coder tool calls not produced; template fix via
  `--chat-template-file`); Hugging Face reports of broken embedded templates (Qwen3-Coder, GLM-4.5-Air).
- Local-agent complaint classes already recorded: 4k default truncation keeping the tail, tool call
  swallowed inside reasoning, integrated GPU ignored, in-app install missing (see the 2026-10-31 doc).

## D. Decisions the research must produce

1. Which fields identify each runtime without trusting a port, and the exact request used.
2. Whether any runtime exposes a trustworthy "this model is cloud-routed" signal; if not, the fallback
   and its stated uncertainty.
3. The smallest real models per runtime that cover: text, tool calls, reasoning, vision. With size,
   license, and a source for each choice.
4. Per runtime: can the window be set per request, at load, or only at launch; where it is read back.
5. Which getting-a-model paths are native to each runtime (and therefore allowed to be a Hutch feature)
   and which are guidance only.
6. Which claims Hutch may make publicly about each runtime given its evidence, in one sentence each.
7. What the best competing apps do for fit, install and offline claims that Hutch should match, and
   what they get wrong that Hutch must not copy.

## E. Output

`docs/research/2026-11-offline-models/00-BASELINE.md` (Phase 0 stack and reproductions),
`01-FAILURE-MINING.md` (section B, table form), `02-RUNTIME-API-NOTES.md` (sections A and D with
exact field names per version), plus per-phase addenda. Commit research with the phase it informs.
