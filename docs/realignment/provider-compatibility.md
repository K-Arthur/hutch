# Provider compatibility matrix

Reviewed 2026-10-09. The versioned, typed source of truth is
[`src/hutch/data/compat.json`](../../src/hutch/data/compat.json), also returned by
`GET /api/v1/compatibility`. Each record includes the route state, Hutch request mapping,
verification boundary, and dated policy/API evidence.

“Supported” means Hutch's common wire contract has recorded fixtures. It does not mean that
every version of a compatible server or every model supports the same tools, context controls,
usage response, retention, or billing. The matrix separates published protocol fields from what
Hutch currently sends. Live providers, models, and paid connections were not used for this review.

| Route | State | Hutch behavior and limit |
|---|---|---|
| OpenAI Chat Completions | Supported | Uses `max_completion_tokens` only for the exact HTTPS `api.openai.com` authority; requests streamed usage. Hutch currently omits `reasoning_effort`, `response_format`, and `num_ctx`. OpenAI documents `reasoning_effort` for applicable models, but this adapter does not map it yet. |
| Anthropic Messages | Supported | Sends `max_tokens`, messages, tools and streaming; sends `output_config.effort` only for Hutch's current model-name allowlist. Thinking and temperature controls are omitted so provider model defaults apply. |
| Ollama native `/api/chat` | Supported | Requires an explicit `num_ctx`; sends tool calls, output cap and keep-alive. `think` is sent only when the model advertises thinking capability. Recognized cloud-tagged model names are treated as hosted. |
| Named OpenAI-compatible connection | Supported | Uses the common Chat Completions shape and `max_tokens`. Unknown dialect-specific fields are omitted. Tool-call behavior, usage, and context settings still depend on the configured server and model. |
| OpenCode Go connection | Experimental | Hutch links to OpenCode Go's account/key page; sign in there, subscribe if needed, and copy the issued provider API key into Hutch. This is the documented key-based integration, not OAuth session sharing. OpenCode CLI credentials in `auth.json` are not imported or reused. The provider docs describe coding-agent traffic; general assistant and unattended-workload eligibility remains unestablished. [OpenCode Go](https://docs.opencode.ai/docs/go/) · [OpenCode providers](https://opencode.ai/docs/providers/) |
| Sign in with ChatGPT token sharing | Experimental; locally fixture-tested, disabled by default | A local opt-in PKCE/OIDC sign-in creates a fixed Responses route. Returning sign-in reuses the saved client and host IDs and supplies the ID token only as `id_token_hint`; verified email alone may be used as `login_hint`. Hutch uses preview-supported `additional_tools` input items for local functions. Scheduled and coordinator-assigned runs require a separate per-Bot, per-account express grant tied to the current full route; each model request rechecks that grant, and revoke/disconnect blocks later requests. Bot and snapshot resources omit local account IDs and consent records. Hutch does not claim eligibility or live account verification. Preview-unsupported request fields are omitted; no provider-enforced output-token limit exists, so local allowances are estimates rather than a hard cap. [Sign-in overview](https://developers.openai.com/siwc/token-sharing-open-source/) · [Preview limits](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations) · [SIWC terms](https://openai.com/policies/sign-in-with-chatgpt-terms/) |
| OpenCode and Pi executors | Unavailable | Both fail before process creation. OpenCode 2.0.24 exposes permission decisions including persistent `always`, and its experimental event stream can lose events; Hutch's parser only maps once/reject and the runtime stays disabled. Pi supports `--no-tools`, which disables built-in, extension, custom and MCP tools, but Pi still owns direct model traffic and provider credentials, so Hutch cannot reserve or reconcile usage. Pi's project trust is not a sandbox, and RPC/print modes cannot show its interactive trust prompt. Hutch must own the provider route and usage reservation before either executor can run. |
| Consumer-plan OAuth/session reuse | Blocked | Hutch does not read or forward consumer-app cookies or session tokens. Use a supported API-key connection. |

The separate **OpenCode CLI coding handoff** is an experimental Linux feature, not a runtime-adapter exception to the row above. The owner reviews a completed chat request, then launches the interactive OpenCode CLI in a new worktree pinned to the configured project's saved Git commit. OpenCode uses its own sign-in, model choice and usage pool. Hutch does not import CLI credentials, meter its provider requests, broker OpenCode's permission prompts, or sandbox shell commands the owner approves. There is no automatic-approval flag; the task agent has a 20-step ceiling. Project-local OpenCode plugin files are refused while the installed V2 plugin-loading behavior is unverified. The launch and process cleanup are not live-tested. See the [coding handoff research](../research/opencode-coding-handoff-2026-10-09.md).

## Calendar and mail connections

These account integrations are separate from model-provider compatibility. Each is **experimental**: its local authorization, storage, grant, and API behavior has fixture coverage, but real account consent and provider requests have not been verified. A calendar or mailbox grant is separate from a Bot's model choice; returned text is untrusted and may be retained in that Bot's conversation/run history or sent to its selected model, except where Gmail's Local-only route check prevents hosted model transfer.

| Connection | State | Scope and boundary |
|---|---|---|
| Google Calendar | Experimental; local setup required | Default sign-in uses account-wide `calendar.calendarlist.readonly` and `calendar.events.readonly`; event creation needs a separate explicit sign-in with `calendar.events.owned` because installed-app OAuth cannot add scopes incrementally. A returned broad scope alone does not activate writes; explicit opt-in is persisted. One Bot can receive one selected calendar. Reads are bounded to title/time/location; a separate owner-calendar grant can create guest-free events after exact outward approval, including in auto mode, with event ID, title, time, description and location readback before success. The Google scope also allows changes/deletes on all calendars the user owns; Hutch exposes no edit, delete or invitation action and is not exposed in Strict Offline. Linux Secret Service required. Public OAuth verification and live consent are unverified. [Google Calendar scopes](https://developers.google.com/workspace/calendar/api/auth) · [installed-app OAuth](https://developers.google.com/identity/protocols/oauth2/native-app) · [event insert](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert) |
| Outlook Calendar | Experimental; local setup required | Local PKCE, Linux Secret Service, delegated `Calendars.ReadBasic` plus offline access, and one selected calendar per Bot. The tool returns up to 25 basic event records; there is no calendar write operation. Live Microsoft registration, consent, and Graph requests are unverified. [Microsoft Graph permissions](https://learn.microsoft.com/graph/permissions-reference?view=graph-rest-1.0) |
| Outlook Mail | Experimental; local setup required | Separate local PKCE credential and delegated `Mail.Read` permission. The owner grants one mailbox per Bot. Search returns at most ten sender/subject/date/body-preview records; message text is untrusted and enters the selected model and run history. Hutch does not send, modify, forward, delete, or download attachments. The provider's `Mail.Read` permission can read full messages even though Hutch returns previews only; live consent and Graph behavior are unverified. [Microsoft Graph permissions](https://learn.microsoft.com/graph/permissions-reference?view=graph-rest-1.0) |
| Gmail | Experimental private preview; not available for public release | Separate local PKCE credential with account-wide restricted `gmail.readonly`; Linux Secret Service and an operator-configured Google Desktop OAuth client are required. One account can be granted to a Bot, but Hutch exposes search only to its built-in runtime in Local mode with loopback-only primary, fallback, and escalation routes. Search returns up to ten sender/subject/date/snippet previews capped at 1,200 characters, not bodies or attachments. The Local inference service remains outside Hutch's verification boundary. Google scope verification and any applicable security assessment are incomplete; no real account or live request was tested. [Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes) · [restricted-scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification) |

All four connections keep refresh credentials in Linux Secret Service rather than SQLite or browser storage. The UI requires separate per-Bot grants, supports revocation/disconnect, and discloses account-wide scope where applicable. Each sign-in path stays unavailable until the operator configures its provider client and the host has an unlocked Linux Secret Service; Connections shows the prerequisite. Disconnecting Hutch does not necessarily revoke provider-side consent; the owner may need to revoke it in the provider account. No live OAuth eligibility or provider access is claimed.

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
