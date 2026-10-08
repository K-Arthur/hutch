# Research: agent runtimes & orchestrators (Oct 2026)

Inputs to the architecture decision in `docs/architecture.md` (D1). Sources were checked 2026-10-07.

## 1. Pi — earendil-works/pi (formerly badlogic/pi-mono)

TypeScript monorepo, MIT, Node 22+, very active (113k+ stars at research time). Packages: `pi-ai`
(unified multi-provider LLM API), `pi-agent-core`, `pi-coding-agent` (CLI + SDK), `pi-tui`,
`pi-durable`. Docs: <https://pi.dev>.

**Embedding surface (three tiers):**
- TypeScript SDK — in-process `createAgentSession()` / `prompt()` / `steer()` / `abort()`, event
  subscriptions, JSONL session persistence
- **RPC mode** — `pi --mode rpc --no-session`, JSONL over stdio; the official docs include a
  Python `subprocess` client example — one process per bot, no ports, no daemon
- JSON mode — one-shot event stream for automation

**Providers:** dozens via `pi-ai` + models.dev-style catalog; local via OpenAI-compatible
`models.json` (Ollama, LM Studio, vLLM) plus a direct llama.cpp GGUF router.

**Assessment:** best external runtime for hutch (process/workspace isolation comes free with one
process per run). Weaknesses: no built-in permissions/sandbox; extensions are TypeScript-only.

## 2. OpenCode — anomalyco/opencode (formerly sst/opencode), 212k★

`opencode run "<prompt>" --format json --auto` for one-shot; `opencode serve` exposes an HTTP API
(the TUI is just a client of it) with sessions, SSE event bus, abort/fork, OpenAPI spec at `/doc`.
Python SDK exists but is alpha (`opencode-ai` 0.1.0a36).

**Blocking issues for hutch-as-core:** the server appears scoped to **one project directory** —
N isolated bot workspaces means N servers on N ports; SSE has no documented delivery guarantees;
some endpoints marked experimental; no API stability commitment; auth flows are TUI-first.

**Verdict:** good one-shot adapter (`runtime/opencode.py`), wrong backbone.

## 3. Frameworks surveyed

| Framework | Verdict for hutch |
|---|---|
| CrewAI | Role-play heavy, debugging opacity, enterprise-gated features — overkill |
| LangGraph | Solid but low-level graph model; drags LangChain ecosystem weight |
| AutoGen / AG2 | Fragmented (Microsoft moved to new Agent Framework); conversation paradigm mismatch |
| smolagents | Philosophically closest (tiny footprint, local models) but single-agent, no scheduling/approvals |
| Claude Agent SDK | Best-in-class permission modes but Anthropic-locked (models + ToS) |
| OpenAI Agents SDK / AgentKit | Python SDK is light; AgentKit is cloud/platform-bound |
| Skyvern / Browser Use | Browser *tools*, not orchestrators; Skyvern is AGPL |

## 4. The "thin custom loop" evidence

- *Build Your Own Coding Agent* (jq maintainer, Feb 2026) — a capable agent is ~500 lines of
  stdlib Python; frameworks are "black boxes adding unnecessary abstraction layers"; vector DBs
  unnecessary for MVP memory. <https://buildyourowncodingagent.com>, HN 46872087.
- Microsoft Agent Framework docs: "If you can write a function to handle the task, do that instead
  of using an AI agent" — and use **workflows** for well-defined steps. hutch's cron dispatch is
  exactly that shape.
- 2026 production write-ups ("Most AI Agent Frameworks Are Overkill", "AI Agents in Production:
  What Actually Works", "When Multi-Agent Is Overkill") converge on: frameworks abstract the loop
  (easy part) and not the operational plumbing (hard part).

## 5. Decision

**Own thin loop (default) + Pi/OpenCode adapters; deterministic scenario fixtures stay in tests.** The differentiating work —
policy, approvals, caps, scheduling correctness, transcripts — is plumbing no framework ships.
The loop against an OpenAI-compatible client is ~300 auditable lines. Provider HTTP behavior is
tested with recorded responses; a source-only scenario fixture exercises the tool and policy
pipeline offline, and is not an application model route.

## Uncertainties at decision time

- Pi's RPC wire details (event field names) were taken from docs as of Oct 2026; the adapter
  parses defensively and is marked experimental until verified against a live `pi`.
- OpenCode multi-directory serving may exist undocumented; the one-shot adapter avoids the
  question entirely.
