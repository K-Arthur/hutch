# ADR-0005: Provider routes, credentials, and the compatibility matrix

Status: accepted (2026-10-07). Slice: S5. Evidence: baseline lead 5, B1-B4.

## Context

"Harness", "provider API", "billing plan", "auth mechanism", "model" and "tool capability" are separate things. The code
conflates them: `openai-compatible` implies a key, an endpoint, a billing relationship and a tool-call dialect at once, and
sends `OPENAI_API_KEY` to whatever URL it is given (baseline lead 5).

## Decision

1. **Credentials are provider-scoped references.** A *Connection* has `name`, `endpoint`, `protocol`, and `key_ref`
   (`env:NAME`, `keyring:service/user`, or a 0600 file under the state dir). The key is resolved at call time, never stored in a bot
   document, URL, log or event. `make_provider` receives a resolved credential for **that** connection only. A bare
   `base_url` with no connection gets **no** `Authorization` header. Presets (`openai`) bind `OPENAI_API_KEY` only to the
   preset's own host; an override of `base_url` on a preset must be an explicit connection.
2. **Compatibility matrix** (`hutch/compat.py`, data in `src/hutch/data/compat.json`, versioned). Each route records: harness,
   API shape, auth flow, models, streaming, tool calls, structured output, vision, context limits, cancellation, usage
   reporting, quota reporting, retention, and **policy evidence (URL + date)**. State is `supported | experimental |
   unavailable | blocked`. A route is `supported` only if a live or recorded contract test exists; otherwise `experimental`.
3. **Routes in scope**

   | Route | State | Notes |
   |---|---|---|
   | Direct API: Anthropic, OpenAI, OpenAI-compatible with an explicit connection | supported (contract-tested with recorded fixtures; live only when a key is supplied) | |
   | Ollama native | supported (offline contract tests; live only where Ollama is installed) | |
   | OpenCode Go / Zen as a **provider connection** | experimental | own `User-Agent`, `x-opencode-session` header; docs set no terms for non-coding workloads (B3) so the UI states "coding-agent workloads" |
   | OpenCode / Pi as **harness** | disabled; not supported executors | no approval broker, sandboxed process, or enforceable shared usage reservation; see ADR-0007 |
   | Sign in with ChatGPT (open-source/local apps) | experimental, not implemented as a route in this phase | Responses API, `store:false`, `stream:true`, many fields unsupported (B1, B2); needs a native Responses adapter; eligibility for Hutch unconfirmed |
   | Cookie scraping, spoofed client identity, credential laundering through a harness | blocked | never implemented |

4. **Capabilities are validated, not assumed.** Before the first call on a (connection, model) pair a cheap probe records what
   it can (model list, tool-call support from a 1-token canned request only when the user opts in to spend). Unknown stays unknown;
   a bot that needs `tools` on a model with unknown/unsupported tool support is refused with an actionable message.
5. **Usage and money.** Persist actual token counts and cost when returned, separately from per-call reservation estimates. Provider
   limits and reset times are displayed **only** when the provider reports them; otherwise "not reported". Before a hosted call Hutch
   atomically reserves estimated prompt + requested reply tokens and priced currency cost with the cap check. Successful responses
   settle actual usage; uncertain outcomes remain held until terminal-run reconciliation. See ADR-0011. Price and prompt estimates are
   not an exact guarantee of provider billing.
6. **No silent paid fallback.** Fallback to another *billing relationship* requires the bot's `fallbacks` entry **and** an approval
   (existing LM-10 rule extended to any change of connection class). No automatic plan upgrade, ever.

## Consequences

Migration: existing `openai-compatible` bots with a `base_url` and an env key keep working only if the user creates a connection; `hutch doctor` lists them and `hutch connections adopt` writes the connection for them (one command). Until then calls go out **without** the key and fail with an explicit `auth` error naming the fix - a deliberate fail-closed change. Rollback: restore the `OPENAI_API_KEY` fallback behind `HUTCH_LEGACY_KEY_ROUTING=1` (documented as unsafe).
