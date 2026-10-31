# Getting Started with Hutch

Hutch is a local-first, multi-bot personal AI platform: "Your bots. Your machine. Your rules." It runs locally on your computer, manages multiple specialized AI assistants, and enforces human-in-the-loop approvals before sensitive actions occur.

This guide explains Hutch's architecture, prerequisites, initial setup, model selection, assistant creation, and troubleshooting.

---

## 1. Core Architecture and Concepts

Before launching Hutch, understanding how its parts connect helps you make informed choices:

| Concept | Role in Hutch | Where it lives |
|---|---|---|
| **Hutch Platform** | Local web application, run loop engine, SQLite store, and security boundary | Runs entirely on your local machine (`127.0.0.1`) |
| **Assistants (Bots)** | Named AI agents with assigned instructions, tools, workspace mode, and approval policies | Stored in local SQLite database |
| **Connections & Providers** | Routes and credentials to AI inference endpoints (OpenCode, Ollama, OpenAI, Anthropic) | Keys stored in private 0600 permission files |
| **Models** | The specific LLM reasoning engine (e.g. `opencode-go/beam-free`, `llama3.2`, `gpt-4o-mini`) | Hosted by provider or local loopback service |
| **Workspace** | Dedicated directory where an assistant reads, creates, and edits files | Isolated under `~/.hutch/workspaces/` |
| **Approvals** | Human-in-the-loop permission gate for shell execution, file mutations, and network requests | Pauses execution until approved in dashboard |
| **Skills** | Specialized agent capability packages (`SKILL.md`) bound to assistants | Registered and audited locally |

---

## 2. System Requirements and Prerequisites

Hutch requires:
- **Operating System:** Linux (Ubuntu 22.04+, Debian 12+, Fedora 38+, Arch Linux) or macOS 13+.
- **Python:** Python 3.11, 3.12, 3.13, or 3.14.
- **Package Manager:** [`uv`](https://docs.astral.sh/uv/) (recommended for fast, reproducible environments).
- **Node.js:** Node.js 18+ (only if modifying Tailwind CSS sources or building the marketing website).
- **AI Inference Route:** At least one of the following:
  1. **OpenCode CLI:** For free, zero-configuration models (`opencode-go/beam-free`).
  2. **Local Loopback:** Ollama or LM Studio running on `127.0.0.1` (requires 8GB+ RAM).
  3. **Hosted API Key:** OpenAI, Anthropic, or OpenRouter account key.

---

## 3. Quickstart: Installation and First Run

### Step 1: Clone and Launch

```bash
# Clone the repository
git clone https://github.com/K-Arthur/hutch.git
cd hutch

# Launch the local dashboard with uv
uv run hutch server
```

The server binds to `http://127.0.0.1:8000` by default. Open this URL in your web browser.

### Step 2: The 5-Step Guided Onboarding

When launched for the first time, Hutch presents the progressive first-run flow:

1. **Your Request (`/onboarding`):** State what you want your assistant to do (e.g., "Summarise weekly release notes and extract action items"). Hutch saves your request locally so you can resume at any time.
2. **AI Service Selection (`/onboarding/ai-service`):** Choose between OpenCode free models, a local loopback service (Ollama), or a hosted API key.
3. **Route Connection & Verification (`/onboarding/connection`):** Hutch validates the connection with a 1-token probe to confirm your setup works before you proceed.
4. **Assistant Creation (`/onboarding/assistant`):** Review your assistant's name, assigned model, workspace isolation, and approval policy (`ask` mode).
5. **First Request Execution (`/onboarding/first-request`):** Review your request, confirm human-in-the-loop boundaries, and watch your assistant execute in real time.

---

## 4. Model Route Options

### Option A: OpenCode Free Models (Recommended for Evaluation)

OpenCode provides free community models with zero API costs:
- **Prerequisite:** Install the OpenCode CLI (`curl -fsSL https://opencode.ai/install | bash`).
- **Recommended Model:** `opencode-go/beam-free`.
- **Privacy Notice:** Queries route through OpenCode's infrastructure. Do not send sensitive personal data.

### Option B: Local Inference with Ollama (100% Offline and Private)

Local models keep all inference strictly on your machine with zero cloud telemetry:
- **Prerequisite:** Install Ollama (`curl -fsSL https://ollama.com/install.sh | sh`).
- **Pull a model:** `ollama pull llama3.2` or `ollama pull qwen2.5-coder`.
- **Hardware Guidance:**
  - 8 GB RAM: 3B parameter models (e.g., `llama3.2:3b`).
  - 16 GB RAM: 7B to 8B parameter models (e.g., `qwen2.5-coder:7b`).
  - 32 GB+ RAM or dedicated GPU: 14B+ parameter models.

### Option C: Hosted Providers (OpenAI, Anthropic)

- Paste your API key during onboarding.
- Hutch stores your key in a private `0600` file inside `~/.hutch/` and never displays it in the UI or exports it over the network.
- Recommended models: `openai/gpt-4o-mini` (fast, economical) or `anthropic/claude-3-5-sonnet` (high capability).

---

## 5. Security and Human-in-the-Loop Approvals

Hutch is built on explicit user consent:
- **Default Approval Mode (`ask`):** By default, every non-read-only tool call (shell command, file write outside workspace, network call) triggers an approval card in the dashboard.
- **Inspectable Parameters:** You see the exact command line, working directory, and payload before granting approval.
- **Workspace Boundaries:** Assistants default to `fresh` workspace mode, restricting file operations to an isolated temporary project tree.
- **Spending Caps:** You can set maximum per-run dollar ceilings on hosted models to prevent runaway token billing.

---

## 6. Contextual Getting Started Checklist

After completing onboarding, the Hutch dashboard provides a dynamic Getting Started checklist:
- Derived directly from database facts (not fragile browser cookies).
- Tracks assistant creation, connection verification, completed runs, and skill bindings.
- Dismissible at any time with a single click.
- Never displayed to experienced users with established configurations.

---

## 7. Troubleshooting and Recovery

| Symptom | Probable Cause | Recommended Action |
|---|---|---|
| **Port 8000 already in use** | Another local service occupies port 8000 | Launch with custom port: `uv run hutch server --port 8080` |
| **Connection verification fails (401)** | Expired or invalid API key | Re-enter key in **Apps & AI** -> **Connections** |
| **Local service unreachable (503)** | Ollama or LM Studio daemon is not running | Run `ollama serve` or check `systemctl status ollama` |
| **Provider rate limit (429)** | Exceeded provider queries per minute | Hutch pauses automatically; wait for retry backoff window |
| **Setup conflict (409)** | Setup form was modified in another browser tab | Reload the page to resume the latest stored state |
| **Out of Memory during local run** | Model parameters exceed available RAM | Select a smaller quantized model (e.g., `llama3.2:1b` or `3b`) |

---

## 8. Next Steps

- Explore [Bot Configuration](bot-config.md) to customize tools, personas, and memory policies.
- Learn about [Agent Skills](skills.md) to package and reuse task playbooks.
- Review [Safety Model](safety.md) for full details on sandboxing and tool isolation.
