# ADR-0005: Provider routes, credentials, and the compatibility matrix

Status: accepted; route-level compatibility and passive per-model tool-call evidence implemented (2026-10-09). No paid capability probe or live model verification is claimed. Slice: S5. Evidence: baseline lead 5, B1-B4.

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
   reporting, quota reporting, retention, request fields Hutch sends/omits, verification boundary, and **policy evidence
   (URL + date)**. State is `supported | experimental | unavailable | blocked`. `supported` means a common route contract
   has a live or recorded test; it does not certify every vendor version, endpoint, or model. Current test fixture
   coverage is recorded separately from live provider/model verification.
3. **Routes in scope**

   | Route | State | Notes |
   |---|---|---|
   | Direct API: Anthropic, OpenAI, OpenAI-compatible with an explicit connection | supported (contract-tested with recorded fixtures; live only when a key is supplied) | |
   | Ollama native | supported (offline contract tests; live only where Ollama is installed) | |
   | OpenCode Go / Zen as a **provider connection** | experimental | Hutch does not reuse OpenCode's CLI sign-in; the user signs into OpenCode Go, copies its issued provider API key, and stores that key in Hutch. Hutch sends its own `User-Agent` and `x-opencode-session`; terms establish coding-agent traffic, not general assistant eligibility (B3). |
   | OpenCode / Pi as **harness** | disabled; not supported executors | no approval broker, sandboxed process, or enforceable shared usage reservation; see ADR-0007 |
   | Sign in with ChatGPT token sharing (local app) | experimental, opt-in and eligibility unconfirmed | Implemented as a separate PKCE/OIDC public-client route, owner-only local token store and fixed Responses API adapter (`store:false`, `stream:true`). Reauthorization retains the issued client and host IDs and uses OpenAI's `id_token_hint`; local functions use preview-supported `additional_tools` input items. Hutch omits preview-unsupported fields (B1, B2); the preview does not accept an output-token ceiling, so Hutch's usage admission is not a hard spend cap. No eligibility or live account use is claimed. |
   | Cookie scraping, spoofed client identity, credential laundering through a harness | blocked | never implemented |

4. **Capabilities are validated, not assumed.** The route matrix records protocol-level fixture evidence; it does not certify
   a specific model. A model-list check authenticates or discovers ids only. Schema v37 passively records one immutable positive
   `function_tool_calls` observation for the exact connection/account/model/route revision when an ordinary, budget-reserved
   Bot run still owned by its live execution lease returns a declared tool call whose arguments pass Hutch's validation and
   its shared-account reservation is settled or retained as uncertain. The record is written after usage accounting
   and before the tool can execute; it contains no prompt, arguments, credential or response text. Invalid/unknown calls and
   tool-free draft runs do not count. `GET /api/v1/model-capabilities` provides bounded keyset pagination. The record proves
   only that this exact route revision returned one valid declared call at that time; it is not a guarantee of future behavior.
   No record means unknown, and changing the route, account or model requires new evidence. Hutch does not infer unsupported
   status from a missing call or issue a separate probe. The legacy standalone `--chat` connection test remains refused because
   it bypasses shared reservations and uncertain-charge reconciliation; use a normal Bot run to exercise model behavior.
   The ChatGPT plan route is opt-in with `HUTCH_ENABLE_CHATGPT_PLAN=1`; this flag does not establish eligibility.
   Its issuer, audience, nonce and signature are verified; credentials stay under the Hutch state directory with
   owner-only permissions, and an access token is sent only to `https://api.openai.com/v1/responses` or the official
   model-list endpoint. Browser cookies, OpenCode's auth file and credentials from other clients are never read.
5. **Usage and money.** Persist actual token counts and cost when returned, separately from per-call reservation estimates. Provider
   limits and reset times are displayed **only** when the provider reports them; otherwise "not reported". Before a hosted call Hutch
   atomically reserves estimated prompt + requested reply tokens and priced currency cost with the cap check. Successful responses
   settle actual usage; uncertain outcomes remain held until terminal-run reconciliation. See ADR-0011. Price and prompt estimates are
   not an exact guarantee of provider billing.
6. **No silent paid fallback.** A configured fallback/escalation to another hosted account,
   destination, protocol or connection revision requires outward approval even in auto mode and
   from a hosted primary. The immutable review records account, destination, billing, revision,
   selected model and per-run scope. Generic `escalate:hosted` sticky grants no longer apply.
   Approved authority lasts for that exact route within this run; explicitly configured models
   on the same route may proceed without another route approval. Every call still reserves usage.
   Changing the connection while waiting or before provider creation refuses the call. The primary
   bot/message model is an explicit selection; it does not authorize another account or service.
   Credentials are refreshed before each builtin provider call, with cache keys scoped to state,
   complete configuration and a credential digest. No automatic plan upgrade is implemented.
   Authentication and quota errors preserve the unresolved usage reservation. Switching from one
   hosted billing authority to another waits for outward review; rejecting the review proves no
   alternate provider is constructed. A generic 400/422 field error is not retried as a streaming
   error. Only a response that identifies stream/SSE incompatibility can trigger the bounded
   non-stream retry, and any uncertain first attempt remains held.

## Consequences

Migration: existing `openai-compatible` bots with a custom endpoint must use that endpoint's
own connection key or explicit `HUTCH_API_KEY`; they never receive the ambient OpenAI key.
`HUTCH_LEGACY_KEY_ROUTING` is now ignored and cannot disable this boundary. Embedded HTTP basic
credentials are refused before storing a connection or constructing a provider. Rollback uses a
compatible database backup and verified release, not a credential-routing bypass. The proposed
`connections adopt` command is not implemented; create the connection explicitly.
