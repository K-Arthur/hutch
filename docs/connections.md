# Connections: subscription plans and custom endpoints

A **connection** is a named hosted endpoint with its own API key, protocol, headers, billing mode, usage
allowance and terms notice. Use one in any bot as `<connection>/<model>`:

```bash
hutch connections templates                          # what Hutch knows how to talk to
hutch connections add opencode-go --allowance-tokens 2000000 --allowance-window month
hutch connections set-key opencode-go                # hidden prompt; stored 0600, never printed
hutch connections ack opencode-go                    # read the plan's terms notice, then accept it
hutch connections test opencode-go                   # authenticates; spends no tokens
hutch bot update my-bot --model opencode-go/zhipuai/glm-5.3
```

The same flow is on the dashboard's **Connections** page. Model ids may contain `/`
(`opencode-go/zhipuai/glm-5.3`): the connection name is everything before the first slash.

## Why this exists

Before connections, a hosted endpoint other than OpenAI or Anthropic meant `openai-compatible/<model>` plus
`HUTCH_BASE_URL`, with **one** global `OPENAI_API_KEY` for every such URL, no notion of a flat-rate plan, no
per-model protocol, no required headers and no warning about a vendor's terms. That is not usable for the
subscription plans people actually own. The loudest complaint about the products Hutch is measured against
(Grok Bot, OpenAI Dots) is an allowance that vanishes with no warning and no cap, so a connection can declare
its allowance and Hutch enforces it *before* the vendor does.

## Plans with templates

Everything below was read from the vendor's docs or a docs aggregator on **2026-10-07**. **None of it was
exercised against a live account** (there are no keys on the development machine); the fakes in
`tests/fakes.py` reproduce the documented wire formats.

| Template | Endpoint | Key | Billing | Source |
|---|---|---|---|---|
| `opencode-go` | `https://opencode.ai/zen/go/v1` (OpenAI chat) | `OPENCODE_API_KEY` (from opencode.ai/auth) | flat subscription, dollar-denominated caps: 5-hour 20%, weekly 50%, monthly 100% | [OpenCode Go docs](https://opencode.ai/docs/go/) |
| `xiaomi-token-plan-{sgp,cn,ams}` | `https://token-plan-<region>.xiaomimimo.com/v1` (OpenAI chat) and `/anthropic` (Anthropic messages) | `XIAOMI_TOKEN_PLAN_API_KEY` (`tp-...`) | subscription **Credits**, not tokens | [OpenClaw provider docs](https://docs.openclaw.ai/providers/xiaomi), [MiMo docs](https://mimo.mi.com/docs/en-US/tokenplan/subscription) |
| `xiaomi` | `https://api.xiaomimimo.com/v1` | `XIAOMI_API_KEY` (`sk-...`) | per token (needs a price row) | same |
| `custom-openai` | any `/v1/chat/completions` server: OpenRouter, Together, Groq, a company gateway, vLLM | your env var | per token or subscription | - |
| `custom-anthropic` | any `/v1/messages` server (URL **without** `/v1/messages`) | your env var | per token or subscription | - |

OpenAI, Anthropic, Ollama, LM Studio and llama.cpp keep their built-in provider names and need no connection.

## What a connection controls

- **Key** (`CN-2`). Read from the environment variable first, then from `<state dir>/keys/<name>.key` (created
  `0600` in a `0700` directory). The key is never written to the database, `connections.json`, a transcript,
  a page or the API; tests grep every page and the database for a planted secret. The file option exists
  because a user-level systemd service does not inherit your shell's environment.
- **Headers** (`CN-3`). Hutch sends its own `User-Agent` (`hutch/<version>`) and, where a plan requires it, a
  stable per-run session id (`x-opencode-session: <run id>` for OpenCode Go).
- **Protocol per model** (`CN-7`). Some plans split models across wire formats. Hutch speaks `openai-chat` and
  `anthropic`; set a model's protocol with `hutch connections set-protocol <name> <model> anthropic`. The OpenAI
  *Responses* protocol is **not supported yet**, and a template or override that asks for it is rejected with a
  clear message rather than failing at run time. The OpenCode docs list Claude Haiku, MiniMax and Qwen families on
  the Anthropic endpoint and Grok / Muse Spark on Responses, while models.dev lists every model as
  OpenAI-compatible; the two sources conflict, so Hutch ships no per-model overrides and tells you how to set one.
- **Billing** (`CN-4`). `per_token` is priced from `prices.json`; with no price row a hosted model **cannot run
  under a cost cap** (Hutch refuses rather than guess). `subscription` and `free` cost nothing per call, but every
  call still lands in the usage ledger.
- **Allowance** (`CN-5`). Declare tokens per rolling window (`5h`, `day`, `week`, `month`). Hutch refuses a call
  that *could* pass it (used + prompt + the reply reserve), warns once at 80%, and shows the meter on the
  Connections page. The window is a rolling approximation: vendors may use fixed windows. Credits (Xiaomi) and
  dollars (OpenCode Go) are not tokens; the allowance is a proxy you calibrate against the vendor's console.
- **Terms** (`CN-6`). Each template carries a notice. A bot cannot use the connection until it is acknowledged,
  and a changed notice requires acknowledging again. A run that hits an unacknowledged connection fails fast
  and tells you the command, or falls back to the next model if the bot has one.
- **Test** (`CN-8`). `hutch connections test` authenticates against the model list (one `GET`, no tokens).
  Anthropic-protocol endpoints have no standard list, so the test says "not verified" rather than pretending;
  `--chat <model>` opts into one real 8-token call.

## Terms: read this before scheduling bots on a plan

- **OpenCode Go** asks third-party clients to send "typical coding agent traffic", to identify themselves with
  their own User-Agent and a stable session id, and says traffic is monitored for abuse. Hutch does the
  identification. Whether *unattended, scheduled* runs count as typical coding-agent traffic is OpenCode's
  decision. Check before you schedule.
- **Xiaomi Token Plan** documents support for coding tools (OpenCode, Claude Code, OpenClaw...) and says keys
  must not be shared. Its page is not machine-readable, so Hutch could not read the full terms. Confirm that
  automated use is allowed on your tier.
- In general, provider terms do not necessarily allow routing a per-seat subscription key through a third-party
  tool, and some plans apply risk controls to unusual traffic.

## Deliberately unsupported

**Logging in with a consumer plan's own session** (Claude Pro/Max, ChatGPT Plus/Pro, Copilot...). Anthropic's
documentation says OAuth tokens from consumer plans are for use inside its own applications and that using them
in other products or tools is not permitted; its consumer terms prohibit automated access except through an API
key. Hutch therefore never reads, stores or proxies such tokens (`LM-15`). Plans that issue an **API key**
(OpenCode Go, MiMo Token Plan, and the API products themselves) are supported. A vendor's own CLI remains
usable through the `pi` and `opencode` runtime adapters, which carry their own authentication and terms.

## Limits worth knowing

- Not tested against live accounts. If a plan's real behaviour differs from its docs, `hutch connections test
  --chat <model>` is the first diagnostic.
- Model discovery is the vendor's `GET /models`; context windows are not read from it (the list does not carry
  them), so no window is assumed for hosted models.
- A connection is **hosted**: a bot whose own model is local still asks before its first call to it
  (`LM-10`), even in auto mode, because the conversation leaves the machine.
