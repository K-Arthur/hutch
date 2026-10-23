# Runtime prerequisites on a fresh device

Hutch is local-first, but it does not bundle model runtimes or model weights. A device with nothing installed can still use the hosted API-key routes. The full OpenCode assistant and local Ollama routes need their runtime installed first.

## OpenCode assistant

- **Version:** Hutch requires **OpenCode V2**. It uses the V2 HTTP API (`/api/session`, `/api/model`, `/api/integration`). A V1 CLI is rejected before a private server starts.
- **Install:** install the OpenCode CLI from <https://opencode.ai> and put `opencode` on `PATH`. Hutch does not download or execute an installer for you.
- **Profile:** Hutch creates a private profile under its state directory. It deliberately does **not** import your normal local OpenCode login, browser cookies, or `auth.json`. A local OpenCode login therefore does not make the Hutch assistant ready.
- **Connect:** open **Connect OpenCode** in Hutch. Hutch lists the provider methods the installed V2 server reports. Use an API key where offered, or start a device/OAuth sign-in. The OpenCode Console `device` flow works through Hutch's routes; complete the code in your browser. OpenRouter itself currently exposes an API-key method, not OAuth.
- **Without the CLI:** the setup dialog returns an actionable install/update message. Use OpenRouter, OpenAI, or Anthropic with an API key instead, or install OpenCode V2 and retry.
- **Tool authority:** approved OpenCode tools run with your operating-system account's authority. They are not inside Hutch's built-in shell sandbox.

## Ollama and other local models

- **Install:** install Ollama from <https://ollama.com> and start its local server. Hutch does not bundle the Ollama binary or model weights.
- **Models:** pull a model with Ollama first. Hutch's model picker lists what the running server reports; a model name in a preset is a suggestion, not a promise that the weights are installed.
- **Without Ollama:** local routes are unavailable. Choose OpenRouter, OpenAI, Anthropic, or an installed OpenCode provider. Hutch does not silently substitute a hosted model.
- **Strict Offline:** requires a verified local route and the host's isolation checks. A hosted API key is not a Strict Offline fallback.

## Hardware and network checks

`hutch doctor` reports missing runtimes, unreadable provider credentials, damaged local state, and configured routes that cannot start. Setup and run admission report the same reasons rather than inventing a default model.
