# Runtime API notes (2026-11)

Primary sources read on 2026-11-05/06 and the exact fields observed on this host. A field
listed here was read from a running process or from the vendor's own page; anything not
observed is marked "documented, not run". Decisions this research must produce are D1 to
D7 in `04-RESEARCH-PLAN.md`; the answer to each is at the end.

## Versions on the bench

| Runtime | Version | Source | Notes |
|---|---|---|---|
| Ollama (retained) | 0.40.13 | `~/.hutch-tmp/localmodels/ollama-dist/bin/ollama`, run with `OLLAMA_MODELS=~/.hutch-tmp/localmodels/models OLLAMA_HOST=127.0.0.1:11434` | Used for G1, G2 and residency measurements |
| Ollama (current) | 0.40.15 | `https://github.com/ollama/ollama/releases/download/v0.40.15/ollama-linux-amd64.tar.zst`, SHA-256 matched against the release `sha256sum.txt` | Current release at the time of this run; manifest-only copy of the model store, bound to 127.0.0.1:11435 |
| llama.cpp | b12144 / server 0.9.0-dev, commit 69ee2ecc0 | `llama-b12144-bin-ubuntu-x64.tar.gz` (23 MB) and `llama-b12144-bin-ubuntu-vulkan-x64.tar.gz` (36 MB) | CPU and Vulkan builds; the project publishes no checksum asset for these archives, so the version string and the release tag are the provenance |
| LM Studio | llmster 0.0.27-1 | `https://lmstudio.ai/install.sh`, SHA-512 checked by the installer | Headless daemon; `lms` at `~/.lmstudio/bin/lms` |
| vLLM | not installed | — | Not run: installing it adds a Python dependency and a large download, which needs the owner's approval (master prompt stop conditions) |
| SGLang | not installed | — | Same reason as vLLM |

Model used for the text/tool probes: `qwen3:4b` Q4_K_M, digest
`359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`. The Ollama blob is a
plain GGUF (`GGUF version 3, 398 tensors, architecture qwen3`) and `llama-server` loaded it
directly by hard link, so the same weights exercised both runtimes.

## Ollama

### Endpoints and fields (0.40.13 and 0.40.15 agree on these)

- `GET /api/version` -> `{"version":"0.40.13"}`.
- `GET /api/tags` -> `models[]` with `name`, `model`, `modified_at`, `size`, `digest`,
  `details` (`parent_model`, `format`, `family`, `families`, `parameter_size`,
  `quantization_level`, `context_length`, `embedding_length`, `runner`), `capabilities`
  (for cloud entries), and **`remote_host` / `remote_model`**. Local rows carry
  `remote_host: null`, `remote_model: null`.
- A real cloud row in 0.40.13:
  `{"name":"gpt-oss:20b-cloud","remote_model":"gpt-oss:20b","remote_host":"https://ollama.com",...}`.
  A copy made with `FROM gpt-oss:20b-cloud`: `name: "my-local-copy:latest"`,
  `remote_host: "https://ollama.com:443"`, `remote_model: "gpt-oss:20b"`. The copy's name
  contains no `cloud` substring, which is the evidence for signal-first classification.
- `POST /api/show` -> `details`, `model_info`, `capabilities`, `thinking`, `modified_at`,
  `template`, `license`. **It does not repeat `remote_host` / `remote_model`** on 0.40.13
  and 0.40.15, so `/api/tags` is the discovery source for the cloud signal.
- `GET /api/ps` -> `models[]` with `name`, `model`, `size`, `digest`, `details`,
  `expires_at`, `size_vram`, `context_length`. Measured for `qwen3:0.6b` with
  `num_ctx=2048`: `size=783663757`, `size_vram=0`, `context_length=2048`,
  `expires_at` 10 minutes after the request. These are the measured window and the
  CPU/GPU split Hutch should surface.
- `POST /api/generate` (non-stream) -> `response`, `load_duration` (ns), `total_duration`,
  `eval_count`, `done_reason`. Measured cold load on CPU: `load_duration=1557572112`
  (1.56 s), `total_duration=17831299429`, 500 generated tokens (thinking consumed them).
- A cloud model without a signed-in account answers a chat request with
  `{"error":"unauthorized","signin_url":"https://ollama.com/connect?...key=..."}`. The
  `signin_url` carries a key: redact it in every log, page and commit.
- `POST /api/pull` of `gpt-oss:20b-cloud` writes a 306-byte manifest and prints
  `success`; it never touches model weights. `ollama cp gpt-oss:20b-cloud <name>` is
  refused (`source ... is invalid`), but `ollama create <name> -f Modelfile` with
  `FROM gpt-oss:20b-cloud` succeeds and keeps the remote host.

### Server facts from the startup log

`OLLAMA_HOST=http://127.0.0.1:11434`, `OLLAMA_MODELS=~/.hutch-tmp/localmodels/models`,
`OLLAMA_NO_CLOUD:false`, `OLLAMA_REMOTES:[ollama.com]`, `OLLAMA_NUM_PARALLEL:1`,
`OLLAMA_MAX_LOADED_MODELS:0` (default), `OLLAMA_KEEP_ALIVE:5m0s`,
`vram-based default context ... default_num_ctx=4096`, and
`dropping integrated GPU; to enable, set OLLAMA_IGPU_ENABLE=1 id=0 ... AMD Radeon Graphics
(RADV RENOIR)`.

The FAQ states the 4096 default, `OLLAMA_CONTEXT_LENGTH`, `OLLAMA_NO_CLOUD=1` (or
`disable_ollama_cloud` in `~/.ollama/server.json`), the 5-minute keep-alive, that
`OLLAMA_NUM_PARALLEL` multiplies the context and memory, and that
`OLLAMA_MAX_LOADED_MODELS` defaults to 3 on CPU. Source:
https://docs.ollama.com/faq (2026-11-06).

## llama.cpp (`llama-server`)

### Defaults that change discovery

- `--host` defaults to `127.0.0.1`; **`--port` defaults to 9931**, not 8080. Hutch's fixed
  endpoint list probes 8080, so a stock `llama-server` is invisible to discovery.
- `--jinja` is enabled by default in this build (`--no-jinja` disables it).
- `--context-shift` / `--no-context-shift` defaults to **disabled**.
- `--parallel` defaults to `-1` (auto); this build reported `total_slots: 4` for one model.
- `--offline` forces cache use and prevents network access; `-hf` downloads at launch
  unless the model is already cached.
- `--api-key`, `--api-key-file`; `--mmproj`, `--no-mmproj`, `--image-min-tokens`,
  `--image-max-tokens`; `--media-path` for local `file://` media; `--reasoning-budget`;
  `--kv-unified-per-slot` for a per-slot context limit; router flags `--models-dir`,
  `--models-preset`, `--models-max` (default 4), `--models-memory-margin`,
  `--models-autoload`.
- `GET /health` is public even with `--api-key`; 503 with
  `{"error":{"code":503,"message":"Loading model","type":"unavailable_error"}}` while the
  model loads (documented; the test load here finished before the first poll, so the 503
  body itself was not captured).

### Observed fields

`GET /props` (qwen3:4b, `-c 8192`):

```
default_generation_settings.n_ctx = 8192
total_slots = 4
build_info = "b12144-69ee2ecc0"
modalities = {"vision": false, "video": false, "audio": false}
model_path = "models/qwen3-4b.gguf"
chat_template = "<the model's jinja template>"
chat_template_caps = {
  "supports_object_arguments": true, "supports_parallel_tool_calls": true,
  "supports_preserve_reasoning": false, "supports_reasoning_effort": false,
  "supports_string_content": true, "supports_system_role": true,
  "supports_tool_calls": true, "supports_tools": true,
  "supports_typed_content": false, "reasoning_effort_levels": []
}
is_sleeping = false
```

`GET /slots` returned four slots, each `{"id": 0..3, "n_ctx": 8192, "is_processing": false}`.
With `--parallel` auto and unified KV, the headline `-c` is what each slot reports here;
per-slot division must be re-measured with an explicit `--parallel 2` in Phase 2.

`GET /v1/models` returns both an Ollama-shaped top-level `models` array and an OpenAI
`data` array. `data[0]` carried `id`, `aliases`, `tags`, `object`, `created`,
`owned_by: "llamacpp"`, `architecture: {"input_modalities":["text"],
"output_modalities":["text"]}`, and
`meta: {"vocab_type":2,"n_vocab":151936,"n_ctx":8192,"n_ctx_train":262144,
"n_embd":2560,"n_params":4022468096,"size":2491323904,"ftype":"Q4_K - Medium"}`.

With `--api-key`, `/v1/models` without the header raises an HTTP error that Hutch's
discovery wraps as `no service answered`; `/health` still answers 200. So a live,
key-protected server is indistinguishable from a dead one today.

`/v1/chat/completions` responses carry `timings` (`prompt_n`, `cache_n`, `predicted_n`, plus
milliseconds and per-second rates) and `usage`; the total token count is
`prompt_n + cache_n + predicted_n`. Multimodal input accepts `image_url` with a remote URL,
base64 data, or a local `file://` path (with `--media-path`), and `input_audio` with
base64/URL/path.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md
(2026-11-06) and the running server above.

## LM Studio (llmster 0.0.27-1)

- `GET /api/v1/models` -> `models[]` with `type` (`llm` | `embedding` | `decision`),
  `publisher`, `key`, `display_name`, `architecture`, `quantization`
  (`name`, `bits_per_weight`), `size_bytes`, `params_string`, `max_context_length`,
  `format` (`gguf` | `mlx`), `capabilities` (`vision`, `trained_for_tool_use`,
  `reasoning` with `allowed_options`/`default`), `description`, optional `variants` /
  `selected_variant`, and `loaded_instances[]`.
- Observed before load: `key: "qwen3-4b"`, `architecture: "qwen3"`,
  `size_bytes: 2497280480`, `params_string: "4B"`, `max_context_length: 262144`,
  `format: "gguf"`, `capabilities: {"vision": false, "trained_for_tool_use": true}`,
  `loaded_instances: []`.
- After a first chat request (JIT load):
  `loaded_instances[0].config.context_length = 8192`, `parallel = 4`,
  `flash_attention = true`, `eval_batch_size = 2048`, `physical_batch_size = 512`,
  `offload_kv_cache_to_gpu = true`, and `remaining_ttl_seconds = 3600`.
  `lms ps` agreed: context 8192, parallel 4, TTL 60m.
- `GET /v1/models` -> `{"id":"qwen3-4b","object":"model","owned_by":"organization_owner"}`
  (a weak fingerprint compared with llama.cpp's `owned_by: "llamacpp"`).
- A real JIT chat with `max_tokens: 64` on qwen3-4b returned an empty
  `choices[0].message.content`, `finish_reason: "length"`, and
  `usage.completion_tokens_details.reasoning_tokens: 64`. This is the real EC-18 case:
  thinking consumed the whole output budget.
- Authentication is off by default. API tokens exist from 0.4.0 and are enabled in
  Server Settings; every REST/SDK request then needs `Authorization: Bearer ...`.
- JIT loading is on by default. Idle TTL defaults to 60 minutes and resets on each
  request; Auto-Evict is on by default and unloads the previous JIT model before loading
  the next. `ttl` may be set per request. Source:
  https://lmstudio.ai/docs/developer/core/ttl-and-auto-evict (2026-11-06).
- Context overflow policy is configurable in the SDK/config surface: `stopAtLimit` stops
  at the window, `truncateMiddle` keeps the system prompt and first user message and
  truncates the middle. This is an explicit policy Hutch must read or override, not guess.
  Source: https://lmstudio.ai/docs/typescript/api-reference/llm-prediction-config-input
  (2026-11-06).

## Hardware notes for this host

- Ollama 0.40.13 drops the integrated AMD GPU unless `OLLAMA_IGPU_ENABLE=1`; it then
  reports `total_vram="0 B"`, `default_num_ctx=4096`, and CPU inference.
- The llama.cpp **Vulkan** build lists
  `Vulkan0: AMD Radeon Graphics (RADV RENOIR) (12175 MiB, 7624 MiB free)`, so the same
  hardware is usable through Vulkan when a runtime is told to use it. Hutch must not
  claim "CPU only" from the Ollama message alone; it must say which runtime and build.
- Measured CPU prompt speed on this host remains the 2026-10-31 figure (about 16 to 19
  prompt tokens/s); no new speed claim is made in Phase 0.

## Decisions (D1 to D7)

- **D1 identity** — Ollama: shape of `/api/tags` plus `/api/version`; llama.cpp:
  `owned_by: "llamacpp"` and `meta.ftype`/`architecture` in `/v1/models`, confirmed by
  `/props.build_info`; LM Studio: `/api/v1/models` with `type`/`key`/`capabilities`,
  confirmed by `/v1/models.owned_by`. Never the port alone.
- **D2 cloud signal** — `/api/tags.remote_host` / `remote_model` is authoritative on both
  tested Ollama versions; `/api/show` does not carry it. The `-cloud` / `:cloud` suffix is
  a fallback only. `OLLAMA_NO_CLOUD` is a server-side fact Hutch can read from its own
  process only when Hutch starts the server; otherwise it is unknown.
- **D3 smallest real models** — text/tools: qwen3:4b Q4_K_M (2.5 GB, Apache-2.0, already
  on disk, tool template present in the GGUF); vision: Qwen2.5-VL-3B-Instruct Q4_K_M +
  Q8_0 projector (1.93 GB + 0.85 GB, Apache-2.0); reasoning/empty-budget: qwen3-4b.
- **D4 window control** — Ollama: per request (`options.num_ctx`), read back from
  `/api/ps.context_length`. llama.cpp: per launch (`-c`), read from `/props` and `/slots`;
  a request cannot change it. LM Studio: per load (JIT config or `/api/v1/load`), read
  from `loaded_instances[].config.context_length`; TTL/auto-evict can unload it.
- **D5 getting a model** — Ollama has a native registry (`/api/pull`, `/api/delete`,
  `/api/create`). LM Studio has native download/status endpoints and `lms get`. llama.cpp
  has no registry process: `-hf` downloads at launch and `--offline` prevents it; Hutch
  should guide, not pretend.
- **D6 public claims** — see the boundary table in
  `docs/realignment/offline-models-2026-10-31.md` section 5. Phase 0 adds no claim.
- **D7 competing apps** — recorded in `01-FAILURE-MINING.md`; the common failure is
  classifying by the endpoint URL or model name and never reading the runtime's own
  signal (IncarnaMind #174 is the clearest public example).

## Phase 1 addendum (2026-11-06): offline readiness

- llama.cpp `tools/server/README.md` (read 2026-11-06, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md):
  `--offline` (env `LLAMA_ARG_OFFLINE`) forces cache use and blocks network; `/props.model_path` mirrors `-m`;
  `-hf` downloads at start. Launch flags are not exposed over HTTP. Class: configuration. Decision: readiness for
  llama.cpp is `unknown` with the words "start it with --offline", never a pass; `/health` 503 is "not ready".
- Ollama: a model absent from `/api/tags` makes a chat request contact the registry; a cloud row needs sign-in.
  Class: integration. Decision: Strict Offline refuses absent, remote and zero-size rows early (live on 0.40.13).
- Evidence: `~/.hutch-tmp/offline-models-2026-11/evidence/p1-live-readiness.txt`.
