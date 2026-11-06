# Provider compatibility matrix

Reviewed 2026-10-30. The versioned, typed source of truth is
[`src/hutch/data/compat.json`](../../src/hutch/data/compat.json), also returned by
`GET /api/v1/compatibility`. Each record includes the route state, Hutch request mapping,
verification boundary, and dated policy/API evidence.

“Supported” means Hutch's common wire contract has recorded fixtures. It does not mean that
every version of a compatible server or every model supports the same tools, context controls,
usage response, retention, or billing. Image input is implemented: the composer accepts verified image attachments, and the built-in
runtime sends them only when the selected route and model accept image input; an unsupported model
refuses the attachment instead of silently dropping it. A route or catalogue listing still does not
establish image understanding for every model. The matrix separates published protocol fields from what
Hutch currently sends. Live providers, models, and paid connections were not used for this review.

| Route | State | Hutch behavior and limit |
|---|---|---|
| OpenAI Chat Completions | Supported | Uses `max_completion_tokens` only for the exact HTTPS `api.openai.com` authority; requests streamed usage. Hutch currently omits `reasoning_effort`, `response_format`, and `num_ctx`. OpenAI documents `reasoning_effort` for applicable models, but this adapter does not map it yet. |
| Anthropic Messages | Supported | Sends `max_tokens`, messages, tools and streaming; sends `output_config.effort` only for Hutch's current model-name allowlist. Thinking and temperature controls are omitted so provider model defaults apply. |
| Ollama native `/api/chat` | Supported | Requires an explicit `num_ctx`; sends tool calls, output cap and keep-alive. `think` is sent only when the model advertises thinking capability. Recognized cloud-tagged model names are treated as hosted. |
| Named OpenAI-compatible connection | Supported | Uses the common Chat Completions shape and `max_tokens`, except OpenAI and OpenRouter use `max_completion_tokens`. The first-party OpenRouter model picker reads its authenticated popular-text catalog on explicit model selection and searches it with `q`; the published catalog price and context are informational. Unknown dialect-specific fields are omitted. Tool-call behavior, usage, and context settings still depend on the configured server and model. No live OpenRouter model was used. |
| OpenCode Go connection | Experimental | Hutch links to OpenCode Go's account/key page; sign in there, subscribe if needed, and copy the issued provider API key into Hutch. This is the documented key-based integration, not OAuth session sharing. OpenCode CLI credentials in `auth.json` are not imported or reused. The provider docs describe coding-agent traffic; general assistant and unattended-workload eligibility remains unestablished. [OpenCode Go](https://docs.opencode.ai/docs/go/) · [OpenCode providers](https://opencode.ai/docs/providers/) |
| Sign in with ChatGPT token sharing | Experimental; locally fixture-tested, disabled by default | A local opt-in PKCE/OIDC sign-in creates a fixed Responses route. Returning sign-in reuses the saved client and host IDs and supplies the ID token only as `id_token_hint`; verified email alone may be used as `login_hint`. Hutch uses preview-supported `additional_tools` input items for local functions. Scheduled and coordinator-assigned runs require a separate per-Bot, per-account express grant tied to the current full route; each model request rechecks that grant, and revoke/disconnect blocks later requests. Bot and snapshot resources omit local account IDs and consent records. Hutch does not claim eligibility or live account verification. Preview-unsupported request fields are omitted; no provider-enforced output-token limit exists, so local allowances are estimates rather than a hard cap. [Sign-in overview](https://developers.openai.com/siwc/token-sharing-open-source/) · [Preview limits](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations) · [SIWC terms](https://openai.com/policies/sign-in-with-chatgpt-terms/) |
| OpenCode assistant | Available | Hutch owns a private `opencode serve` process, chooses the explicit `opencode/provider/model` route, reads durable session history rather than relying on the volatile event stream, brokers permissions as once/reject, and reserves usage. OpenCode's own tools run with the user's OS authority after approval; they are not inside Hutch's built-in shell sandbox. |
| Pi executor | Unavailable | Pi has no per-action approval hook and still owns direct provider traffic, so Hutch cannot reserve or reconcile usage. It fails before process creation. |
| Consumer-plan OAuth/session reuse | Blocked | Hutch does not read or forward consumer-app cookies or session tokens. Use a supported API-key connection. |

The separate **OpenCode CLI coding handoff** is an experimental Linux feature, not a runtime-adapter exception to the row above. The owner reviews a completed chat request, then launches the interactive OpenCode CLI in a new worktree pinned to the configured project's saved Git commit. OpenCode uses its own sign-in, model choice and usage pool. Hutch does not import CLI credentials, meter its provider requests, broker OpenCode's permission prompts, or sandbox shell commands the owner approves. There is no automatic-approval flag; the task agent has a 20-step ceiling. Project-local OpenCode plugin files are refused while the installed V2 plugin-loading behavior is unverified. The launch and process cleanup are not live-tested. See the [coding handoff research](../research/opencode-coding-handoff-2026-10-09.md).

## Provider identity, account profiles and capability evidence

Provider identity, authentication profiles and capability evidence are separate records from this
route matrix (added 2026-10-30). The validated catalogue in src/hutch/data/providers.json lists every
requested provider with its category, documented auth methods, implementation status and sources;
src/hutch/providers/accounts.py groups configured connections by that identity without merging their
credentials; capability evidence is recorded with a level, scope and date. Live verification covers the
DeepSeek direct route, the managed OpenCode runtime, and Xiaomi MiMo (text, speech-to-text, speech
synthesis, tool calling and the streamed transport path); every other hosted route above remains
fixture-tested at best. Provider-native search is implemented on the same route but its live run was
refused by the provider because the account's web-search plugin is not activated, so it is not
live-verified; `live_search` remains Hutch's own grounding path and needs no provider entitlement.
Research and dated sources: docs/research/2026-10-provider-platform/. See ADR-0026.

### Explicit route resolution (2026-11-06)

`GET /api/v1/provider-resolution?spec=...&runtime=...` resolves a saved spec to one provider, account,
account source, billing relationship, model, runtime, protocol, endpoint and readiness state from local
facts only. A provider prefix with two matching accounts returns `needs_configuration` rather than
choosing a payer; an ambient key is named as the source only when it may reach the official host.
A fallback or escalation from a subscription primary to per-token/credits billing is refused before the
call, so a route never changes who pays without an explicit decision. Schema 91 writes the implicit
`openai-compatible/` prefix into saved route fields without changing the route that runs. This does not
alter any row in the route matrix above; it makes the existing interpretation explicit. See ADR-0028 and
`docs/research/2026-11-provider-expansion/02-ROUTE-RESOLUTION.md`.

### Hosted OpenAI-compatible routes (2026-10-31)

Twenty-five further connections ship on the "Named OpenAI-compatible connection" row above. They share
its behaviour and its limits; none of them has a live-verified model, and the row's caveat - tool calls,
usage and context depend on the configured server and model - applies unchanged.

Mistral, xAI, MiniMax, Moonshot, Z.AI, Cohere, StepFun, Groq, Cerebras, Fireworks, Together, DeepInfra,
Novita, Chutes, NVIDIA, Hugging Face, Synthetic, Venice, GMI Cloud, Arcee, Ollama Cloud, Volcengine,
Tencent TokenHub, Kilocode and BytePlus each have a template and a real connection path. What is
established is only that each endpoint answered a credential-free request on 2026-10-31 (host, TLS,
`/models` path, then either a catalogue or an authentication challenge), recorded in
[`endpoint-reachability-2026-10-31.json`](../research/2026-10-provider-platform/artifacts/live-verification/endpoint-reachability-2026-10-31.json).
What is not established is anything about a model.

Two route defects were found and fixed while verifying, both of which a fixture would have missed:

- **A model list is not always under the chat base.** OpenCode Go serves chat at
  `.../inference/go/openai/v1` and publishes its catalogue at `.../inference/go/v1`. Hutch asked the chat
  base and got `404` for any key, so an expired key was reported as a broken endpoint. A connection can
  now carry `models_base_url` (CN-10), and it is dropped if `base_url` is overridden to another origin so
  chat and discovery never address different services.
- **A redirect is refused, not followed.** A connection endpoint answering `3xx` is now reported as a
  refusal naming the `Location`, because following it would send that connection's key to another host.
  `health()` no longer treats a `3xx` as success. Measured on loopback: the redirect target was never
  called. There is still no private-range allowlist or DNS pinning for operator-supplied endpoints.

## Calendar and mail connections

These account integrations are separate from model-provider compatibility. Each is **experimental**: its local authorization, storage, grant, and API behavior has fixture coverage, but real account consent and provider requests have not been verified. A calendar or mailbox grant is separate from a Bot's model choice; returned text is untrusted and may be retained in that Bot's conversation/run history or sent to its selected model, except where Gmail's Local-only route check prevents hosted model transfer.

| Connection | State | Scope and boundary |
|---|---|---|
| Google Calendar | Experimental; local setup required | Default sign-in uses account-wide `calendar.calendarlist.readonly` and `calendar.events.readonly`; event creation needs a separate explicit sign-in with `calendar.events.owned` because installed-app OAuth cannot add scopes incrementally. A returned broad scope alone does not activate writes; explicit opt-in is persisted. One Bot can receive one selected calendar. Reads are bounded to title/time/location; a separate owner-calendar grant can create guest-free events after exact outward approval, including in auto mode, with event ID, title, time, description and location readback before success. The Google scope also allows changes/deletes on all calendars the user owns; Hutch exposes no edit, delete or invitation action and is not exposed in Strict Offline. Linux Secret Service required. Public OAuth verification and live consent are unverified. [Google Calendar scopes](https://developers.google.com/workspace/calendar/api/auth) · [installed-app OAuth](https://developers.google.com/identity/protocols/oauth2/native-app) · [event insert](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert) |
| Outlook Calendar | Experimental; local setup required | Read access uses local PKCE, Linux Secret Service, delegated `Calendars.ReadBasic` plus offline access, and one selected calendar per Bot; it returns at most 25 basic event records. A separate sign-in/token namespace and per-Bot grant use delegated `Calendars.ReadWrite` for guest-free event creation on one selected calendar, with exact approval each time and readback verification. Microsoft's scope reaches all account calendars and can change/delete events; Hutch exposes create only. Uncertain writes are never retried automatically. Live Microsoft registration, consent, and Graph requests are unverified. [Microsoft Graph permissions](https://learn.microsoft.com/graph/permissions-reference?view=graph-rest-1.0) · [Create event](https://learn.microsoft.com/en-us/graph/api/calendar-post-events?view=graph-rest-1.0) |
| Outlook Mail read | Experimental; local setup required | Separate local PKCE credential and delegated `Mail.Read` permission. The owner grants one mailbox per Bot. Search returns at most ten sender/subject/date/body-preview records; message text is untrusted and enters the selected model and run history. This read grant does not send, modify, forward, delete, or download attachments. A distinct send preview uses separate `Mail.Send` consent and grants in Connections; each plain-text send needs fresh exact approval, makes one request and holds uncertain outcomes for reconciliation. No live account verification for sending. The provider's `Mail.Read` permission can read full messages even though Hutch returns previews only; live consent and Graph behavior are unverified. [Microsoft Graph permissions](https://learn.microsoft.com/graph/permissions-reference?view=graph-rest-1.0) · [sendMail](https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0) |
| Gmail | Experimental private preview; not available for public release | Search and sending have separate local PKCE accounts, account files, Secret Service entries, scopes and per-Bot grants. Search requests restricted account-wide `gmail.readonly`; a built-in Bot may use it only when primary, fallback and escalation models all use loopback Local routes. It returns up to ten sender/subject/date/snippet previews capped at 1,200 characters, not bodies or attachments; the local inference service remains outside Hutch's verification boundary. Send requests only sensitive `gmail.send`; the owner enters the From address and Google decides whether that address is permitted. A granted Bot can prepare one plain-text email to 1–5 recipients with no attachments, CC, BCC, reply or forward. A fresh exact approval is required every time, including in automatic mode. Hutch submits one request and marks timeouts, redirects, server errors or unverifiable receipts `outcome_unknown`; it never retries. Google acceptance does not confirm delivery. Sensitive-scope OAuth verification for public distribution and live consent remain unverified; restricted-scope verification and any applicable third-party security assessment for read-data storage/transmission also remain incomplete. No live account or provider request was used. [Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes) · [send method](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/send) · [send format](https://developers.google.com/workspace/gmail/api/guides/sending) · [restricted-scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification) |

Each connection flow keeps refresh credentials in Linux Secret Service rather than SQLite or browser storage. The Connections UI supports Google Calendar, Gmail search and send-only, Outlook Calendar read and optional create-only event grants, and Outlook Mail read and send grants, revocation/disconnect, and scope disclosures. Each sign-in path stays unavailable until the operator configures its provider client and the host has an unlocked Linux Secret Service; the UI reports that prerequisite where available. Disconnecting Hutch does not necessarily revoke provider-side consent; the owner may need to revoke it in the provider account. No live OAuth eligibility or provider access is claimed.

Bots already saved with the disabled Pi or OpenCode executor can be moved from Settings to Hutch's
built-in runtime, or through `PATCH /api/bots/{bot}` with `{"runtime":"builtin"}`. Hutch accepts
only that recovery target; the request requires a usable Hutch model route and no active run. This
does not start either external executor, copy its session or credentials, or change the status of
the Pi/OpenCode executor row above.

`hutch connections test` can authenticate against a model-list endpoint without making a model request. For ChatGPT, model
selection uses the account's list-visible model catalog only after an explicit selection request. It does not confirm tool
calling. A standalone chat probe is refused because it bypasses shared usage reservations and durable reconciliation; use a
normal Bot run to test model behavior through Hutch's governed path. Schema v37 records a positive, immutable observation when
an owned run with settled or uncertain usage reservation receives a declared, argument-valid tool call, scoped to its exact connection, account, model and route
revision. Read evidence from `GET /api/v1/model-capabilities` with bounded `after_id`/`limit` pagination. This is an observation
of one response, not a model guarantee; no record means unknown, and route changes require new evidence. Invalid and undeclared
tool calls and tool-free draft runs do not count. The observation is passive: it makes no extra model request. Fixture-tested
provider contracts must not be described as live model verification.

## Request-field regression

`tests/test_compat.py` checks that each published route has a state and dated HTTPS evidence, and
that the typed endpoint exposes the same record. It also checks that the OpenAI token-limit field
selection uses the exact official host, rejecting lookalike domains, embedded paths, insecure
HTTP, and nonstandard ports. `tests/test_providers.py` exercises the request and response fixtures.
The retry checks ensure a generic rejected field is not resent in a second request; only a
stream/SSE-specific rejection can take the non-stream retry. `tests/test_provider_authority.py`
confirms auth/quota failures cannot construct an alternate paid provider before outward approval.

The official protocol sources checked for this matrix include [OpenCode 2.0.24 permissions](https://opencode.ai/v2/docs/permissions), [OpenCode providers](https://opencode.ai/docs/providers/), [Pi RPC](https://pi.dev/docs/latest/rpc), [Pi CLI tool controls](https://pi.dev/docs/latest/cli), and [Pi security guidance](https://pi.dev/docs/latest/security). The OpenCode Go account setup is sign-in followed by a provider-issued API key; it does not provide Hutch with OpenCode CLI session reuse. This checkout has OpenCode `v2.0.24`; no Pi binary is installed, so the Pi review is documentation and fixture based. The other official sources checked for this matrix include the [OpenAI Chat Completions API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create),
[Anthropic Messages API](https://platform.claude.com/docs/en/api/messages/create), [Ollama chat API](https://docs.ollama.com/api/chat),
[LM Studio tool use](https://lmstudio.ai/docs/developer/openai-compat/tools), [llama.cpp server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md),
and the [vLLM OpenAI-compatible server](https://docs.vllm.ai/en/stable/serving/online_serving/openai_compatible_server/).
OpenRouter's model-list and chat-completion shape were checked against its [model catalog](https://openrouter.ai/docs/api/api-reference/models/get-models)
and [chat completion reference](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request).

### DeepSeek direct route (live-verified 2026-10-30)

The new DeepSeek connection template uses the OpenAI-shaped endpoint at https://api.deepseek.com/v1.
Model discovery authenticated and returned deepseek-flash and deepseek-v4-pro; one one-step text run
through the built-in runtime returned the expected token and recorded 612 prompt / 9 completion tokens.
The local price row was absent, so the recorded cost of 0.0 is unpriced and not a free-service claim.
Tool calling, streaming, image input and every other capability remain unverified for this route. The
managed OpenCode runtime was separately live-verified with a DeepSeek model (see the research package
live-verification artifacts). Blocked, retired and deferred provider routes are unchanged.

### Xiaomi MiMo Token Plan (live-verified 2026-10-31)

Text, speech-to-text, tool calling and the streamed transport path were exercised on the owner's Token
Plan (Singapore) account. The tool-calling run is the strongest evidence: a governed CLI run with only
`list_files` and `read_file` produced two calls in a single streamed turn, Hutch validated and executed
both, returned their real output, and the next step answered from it. Every step reported
`streamed=True` with no fallback to non-streaming, and one usage row per step landed in the ledger.

The run also exposed a defect: the streamed path dropped the `reasoning_content` deltas the provider
sends, so a streamed call reported less output than the same call batched. A raw wire probe confirmed
the provider sends them; the assembler now keeps them, and the end-to-end run still passes.

Boundaries of the claim: `mimo-v2.6-flash` only for tools and streaming (`mimo-v2.6-pro` was text only);
no vision, structured output, cancellation mid-stream or other tool families; the cn/ams hosts were not
contacted; and "streaming" here means Hutch consumes SSE and assembles the result server-side - the
dashboard does not render progressive tokens.

## Phase 3 routes (2026-11-06): identities, not verified behavior

`kimi-coding`, `opencode-zen`, `qwen-standard-intl`, `qwen-standard-cn`, `moonshot-cn` and `zai-cn` were added as
connection templates. None has a row in `compat.json`: no request-level behavior was observed, so each is
implemented-unverified and carries no capability, tool-schema, streaming or reasoning claim. The Alibaba and
Z.AI coding-plan routes are blocked by their own terms and have no template (ADR-0032). The research record is
`docs/research/2026-11-provider-expansion/04-FLAGSHIP-ROUTES.md`.

## Phase 4 routes (2026-11-06): gateways and clouds, identities not verified behavior

`vercel-ai-gateway`, `litellm`, `clawrouter`, `bedrock-runtime`, `bedrock-mantle`, `microsoft-foundry`,
`qianfan` and `stepfun-global` were added as connection templates, and `synthetic` moved to its documented
`/openai/v1` path. None has a row in `compat.json`: no request-level behavior was observed, so each is
implemented-unverified with no capability, tool-schema, streaming or reasoning claim.

Two request-shaping rules are data on the template, not provider-specific code, and neither is observed live:

- `headers: {"api-key": "{api_key}"}` (Microsoft Foundry) sends the key in that header and no Bearer. Proven on
  the wire against a local server; Azure itself was not called.
- `tool_schema_unsupported_keywords` (Volcengine) trims bound keywords from the wire copy of each tool schema.
  The source is the OpenClaw Volcengine page, read 2026-11-06; it was not reproduced against an account. The
  canonical `Tool.parameters` and `validate_call` are unchanged.

`models_list_ignores_key` marks seven hosts whose model list answered HTTP 200 for a placeholder key on
2026-11-06 (Hugging Face, Kilo, Novita, NVIDIA, Ollama Cloud, Synthetic, Venice); a listing there is not a key
check. The Tencent Token Plan is blocked by its terms and has no template (ADR-0033). The research record is
`docs/research/2026-11-provider-expansion/05-HOSTED-AND-GATEWAYS.md`.
