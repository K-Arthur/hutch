# Runtime prerequisites on a fresh device

For channel setup and current delivery limits, see [Telegram channels](channels.md).
Connecting a channel does not install a model runtime or expand assistant tools.

Hutch is local-first, but it does not bundle model runtimes or model weights. A device with nothing installed can still use the hosted API-key routes. The full OpenCode assistant and local Ollama routes need their runtime installed first.

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

## Ollama and other local models

- **Install:** install Ollama from <https://ollama.com> and start its local server. Hutch does not bundle the Ollama binary or model weights.
- **Models:** pull a model with Ollama first. Hutch's model picker lists what the running server reports; a model name in a preset is a suggestion, not a promise that the weights are installed.
- **Without Ollama:** local routes are unavailable. Choose OpenRouter, OpenAI, Anthropic, or an installed OpenCode provider. Hutch does not silently substitute a hosted model.
- **Strict Offline:** requires a verified local route and the host's isolation checks. A hosted API key is not a Strict Offline fallback.

## Hardware and network checks

`hutch doctor` reports missing runtimes, unreadable provider credentials, damaged local state, and configured routes that cannot start. Setup and run admission report the same reasons rather than inventing a default model.
