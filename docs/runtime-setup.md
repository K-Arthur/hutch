# Runtime prerequisites on a fresh device

For channel setup and current delivery limits, see [Telegram channels](channels.md).
Connecting a channel does not install a model runtime or expand assistant tools.

Hutch is local-first, but it does not bundle model runtimes or model weights. A device with nothing installed can still use the hosted API-key routes. The full OpenCode assistant and local Ollama routes need their runtime installed first.

First run starts at `/onboarding` with a written request before any runtime choice.
The request is stored only in this machine's Hutch data directory
(`onboarding:setup:v1`) and survives a refresh, a second tab, or a restart; nothing
is sent anywhere until you continue to an AI service. See
[onboarding setup record](onboarding/setup-record.md) for the stored fields, the
resume/stale-expired states, and the local reset command.

After the request, the AI-service chooser asks you to pick one of three routes:
a hosted provider key, a local model service you run, or an existing OpenCode
login. Choosing a route only records the choice; it does not contact the provider
yet, and the recommendation shown there is a static suggestion, not a detected or
verified readiness state. You can change the route later, and apps, devices and
channels can be connected after setup. Connection details for the chosen route
arrive in a later step; until then the chosen-state link is a temporary bridge to
the existing Apps & AI surface.

## OpenCode assistant

- **Version:** Hutch requires **OpenCode V2**. It uses the V2 HTTP API (`/api/session`, `/api/model`, `/api/integration`). A V1 CLI is rejected before a private server starts.
- **Install:** install the OpenCode CLI from <https://opencode.ai> and put `opencode` on `PATH`. Hutch does not download or execute an installer for you.
- **Profile:** Hutch creates a private profile under its state directory. It does not automatically import your personal configuration, plugins, browser cookies, or credentials. A local OpenCode login alone does not make the Hutch assistant ready.
- **Existing login:** choose **Use an existing OpenCode login**, then **Use this login** for one API account. Hutch reads the local credential file only when you request discovery or connection and transfers only the selected key through its owned OpenCode server. The original file is unchanged. OAuth/browser sessions require a fresh sign-in so token refresh remains owned by the private profile. A POSIX login file must be a regular, nonsymlinked file owned by your user with mode `0600`; unreadable or malformed files produce a safe error without credential contents. Successful transfer is not proof of valid credit or model access: the subsequent model check reports readiness separately.
- **Connect:** open **Connect OpenCode** in Hutch. Hutch lists the provider methods the installed V2 server reports. Use an API key where offered, or start a device/OAuth sign-in. The OpenCode Console `device` flow works through Hutch's routes; complete the code in your browser. OpenRouter itself currently exposes an API-key method, not OAuth.
- **Without the CLI:** the setup dialog returns an actionable install/update message. Use OpenRouter, OpenAI, or Anthropic with an API key instead, or install OpenCode V2 and retry.
- **Tool authority:** on Linux, enabled canonical Hutch tools are exposed through a per-run bridge authenticated by kernel process identity. Each call rechecks the owner fence, lease, cancellation and current tools/account grants, then uses Hutch's normal approval, artifact and effect-receipt pipeline. When write, shell or web capabilities are brokered, their native OpenCode alternatives are denied. Native read-only workspace inspection still belongs to OpenCode. Do not assume an unbrokered native tool runs inside Hutch's OS sandbox.
- **Current limits:** native computer control and unmanaged OpenCode subagents are not exposed by this bridge. Browser/media results can return text and locally recorded visual artifacts; image pixels from those tool results are not yet forwarded to the model. The bridge is Linux-only pending native peer-identity implementations on macOS and Windows. Provider/model readiness is separate from these tool capabilities.
- **Instructions:** OpenCode and the built-in runtime use the same governed system renderer, including the task's reviewed context, rehearsal rules, selected persona guidance and any already-resolved skill context. This does not expand which skills or tools are supported by a runtime. Business recommendations must distinguish evidence, calculations, hypotheses and unknowns; eligibility is not qualification, and ROAS alone does not establish profit.
- **Learning:** enabled memory tools use Hutch’s governed `remember`/`recall` bridge. Hybrid-mode explicit formatting preferences use the same bounded, chat-scoped historical reference context as the built-in runtime. Undo and memory-off stop fresh retrieval; already-loaded context and earlier provider input remain. Models cannot activate executable skills or expand access through memory. See [Bot configuration](bot-config.md).
- **Maintenance calls:** managed assistant runs disable automatic compaction, title/summary agents and background warming. Before creating a session, Hutch waits for plugin activation, reads the workspace's loaded configuration and explicitly verifies that the hidden maintenance agents are absent. An incompatible CLI or an overriding configuration stops the run before its prompt. This is not a provider billing guarantee: prompt retries, provider charges and uncertain outcomes still require usage reconciliation. Sessions created under an older runtime policy are not reused.
- **Concurrent Bots:** each owned server receives a distinct private configuration file for its agent, model and run-bound bridge. Another Bot cannot replace that file by starting a server. Closing the server or failing startup removes only its own temporary configuration; the selected account profile remains connected. Abrupt host/process termination may leave private configuration files for later cleanup. This isolation does not change which context or tools a Bot may receive.

The maintenance preflight and concurrent configuration behavior were checked against OpenCode **2.1.4**, with metadata-only local probes. Compatibility with every V2 version is not implied. Relevant upstream contracts: [agents](https://opencode.ai/v2/docs/agents/), [compaction](https://opencode.ai/v2/docs/compaction/), [warming](https://opencode.ai/v2/docs/warming/) and the [V2 HTTP API](https://dev.opencode.ai/v2/docs/api).

## Provider sign-in boundaries

- **Sign in with ChatGPT** uses OpenAI's local PKCE loopback callback. The browser must reach the
  Hutch host's `127.0.0.1` callback, so a remote dashboard, a Windows-side browser without WSL port
  forwarding, or a headless host cannot complete it. The page says so and points to an API key or
  the official Codex CLI. Hutch does not implement an undocumented device-code client.
- **OpenCode provider sign-in** (including its device/OAuth methods) is owned by the installed
  official OpenCode V2 server and CLI. Hutch starts the attempt through that server and never
  imports its OAuth tokens; only an explicitly selected API key can be transferred, and the original
  login file is unchanged.
- **Anthropic and Google subscription OAuth** is not a Hutch credential. Use an API key or the
  vendor's own unmodified CLI with the user's own sign-in.
- A saved OAuth credential is reported as active, expired, revoked or missing; a failed refresh
  keeps the prior credential. See ADR-0029.

## Ollama and other local models

- **Install:** install Ollama from <https://ollama.com> and start its local server. Hutch does not bundle the Ollama binary or model weights.
- **Models:** the Models page can install a suggested model, or list what the running server already reports; a model name in a preset is a suggestion, not a promise that the weights are installed.

### Getting a local model (2026-11)

- **Ollama, from the Models page.** Pressing **Install** first asks the server for a
  preflight: the catalog size, free space on the runtime's own model directory
  (`OLLAMA_MODELS`, else `~/.ollama/models`), the fit estimate at 16k, and an ETA only
  when a previous transfer was measured. Nothing downloads until **Confirm download**.
  The server re-runs the same check, so a client cannot skip it. A known size that does
  not fit beside a 512 MiB reserve is refused with both numbers. An unknown size, an
  unreadable directory, or a non-loopback runtime is shown as unknown, never as zero.
- **Name forms.** Hutch accepts Ollama's grammar: `model`, `namespace/model`, and
  `host/namespace/model`, with an optional `:tag` and case-preserving names. Hugging Face
  pulls use `hf.co/<user>/<repo>[:quant]` or the full `.gguf` filename as the tag; the
  quant is case-insensitive. A `@sha256:<64 hex>` suffix is passed through, but the
  runtime may not support a pinned digest. Cloud tags are refused unless the route has an
  explicit data-sharing confirmation.
- **Cancel and resume.** Cancel stops this Hutch job at the runtime's next progress
  event. The runtime keeps completely downloaded chunks until the pull resumes or the
  Ollama server restarts; pressing Install again resumes when it kept them. Ollama's
  transfer path for some models restarts a blob from zero instead. Hutch reports the
  bytes this attempt actually received and never manufactures a resumed percentage.
  `OLLAMA_NOPRUNE=1` preserves partial chunks across an Ollama restart; Hutch does not
  set it for you. The job list belongs to the Hutch process: a Hutch restart loses the
  job record, and the page says to press Install again (the runtime may still have the
  parts).
- **Import a local GGUF.** `POST /api/models/import` (the visible form is Phase 7) takes
  an absolute `.gguf` path, an optional expected SHA-256 and an optional license. Hutch
  validates the GGUF header, hashes the file, asks `HEAD /api/blobs/<digest>`, uploads
  only when the runtime does not have it, calls `POST /api/create` with the original
  filename and digest, then confirms the model in `/api/tags`. The runtime verifies the
  digest again. Split GGUFs are refused with the `gguf-split` merge hint. A sidecar
  `LICENSE`/`<model>.LICENSE` is read when present; a missing license is shown as missing.
  The runtime's own token (for a gated Hugging Face repo) is configured in the runtime,
  never in a Hutch URL or the database.
- **LM Studio.** It has a native download API and a CLI: `lms get <model>@<quant>`. The
  documented API has no cancel operation and no catalog-list endpoint Hutch can build a
  picker from, so Hutch does not wrap it in an install job. Files land in LM Studio's
  model directory. Reopen the Models page after a download to re-scan.
- **llama.cpp.** `llama-server -hf <user>/<repo>:<quant>` downloads at server start,
  before the server answers; Hutch cannot cancel or track it. Add `--mmproj` when the
  model needs a separate projector (it is fetched automatically for `-hf` when available).
  Gated repos use `-hft` or `HF_TOKEN` on the server. The cache is selected from
  `LLAMA_CACHE`, `HF_HUB_CACHE`/`HUGGINGFACE_HUB_CACHE`, `HF_HOME/hub`, or
  `~/.cache/huggingface/hub`; `--offline` keeps a started server from fetching anything.
  This is a guided command, not a Hutch job.
- **vLLM and SGLang.** Launch them with their own CLI and point a connection at the
  served `/v1` endpoint. Hutch has no install surface for either; their `/v1/models`
  response does not report a served context window, so Hutch treats the window as unknown.
- **Gated or private repositories.** A Hugging Face token is the runtime's credential
  (Ollama's own sign-in/key, llama.cpp's `-hft`/`HF_TOKEN`). Hutch never asks for it in a
  URL and never logs it.
- **Loading and eviction:** a cold load is shown as `loading_model` with the measured duration, not as a timeout. Keep-alive expiry, an unload or the `OLLAMA_MAX_LOADED_MODELS` limit means the next turn reloads; Hutch re-reads `/api/ps` before every call. A runner killed mid-stream (`signal: killed`, or an `unexpected EOF` wrapper) is retried once after a reload when no text was delivered; partial text is kept as incomplete and the turn stops with the cause.
- **Version:** Hutch gates tool calling, schema-constrained output, thinking and the measured `/api/ps` window by the server's reported version; `hutch doctor` and the Models page name the upgrade when one is needed. An unreadable version gets no advice.
- **Without Ollama:** local routes are unavailable. Choose OpenRouter, OpenAI, Anthropic, or an installed OpenCode provider. Hutch does not silently substitute a hosted model.
- **llama.cpp:** `llama-server` binds 127.0.0.1:9931 by default. Hutch probes 9931 and the older
  8080 and identifies the server from `/props` and `/v1/models`, not the port. `-c` is the total
  context; when the KV cache is divided, `/slots[].n_ctx` is the per-request window Hutch uses. A
  server started with `-m /path/model.gguf` is listed as the file's basename, which llama.cpp also
  accepts. Launch flags are not exposed over HTTP; size deliberately. `/health` 503 means
  "loading": Hutch waits and measures it. `/props.is_sleeping` means the model is unloaded but
  reloadable, and the next request wakes it. A server restart mid-turn is watched before every
  call; if it does not answer again, the turn stops with that cause. The build string
  (`/props.build_info`) is recorded; capabilities come from fields such as
  `chat_template_caps.supports_tools`, because llama.cpp publishes no feature-by-build matrix.
- **LM Studio:** start its server (default 127.0.0.1:1234). Hutch reads the applied
  `loaded_instances[].config.context_length`, not the model's maximum, and can load a cold model at a
  fitted window, timing the load. TTL expiry and auto-evict show as an unloaded model, and Hutch
  reloads once before the next call rather than assuming it is still resident. If API tokens are
  enabled, store the token on a connection for that exact origin; without it the server shows
  `needs_key`, not "dead". The app does not report its version over HTTP, so Hutch records the
  native `/api/v1` presence (0.4.0 or newer) and gives no version advice.
- **Strict Offline:** requires a verified local route and the host's isolation checks. A hosted API key is not a Strict Offline fallback. A key-protected local server is still local; its token is a bearer header, never a URL credential.

## Hardware and network checks

`hutch doctor` reports missing runtimes, unreadable provider credentials, damaged local state, and configured routes that cannot start. Setup and run admission report the same reasons rather than inventing a default model.
