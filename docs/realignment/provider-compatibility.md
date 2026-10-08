# Provider compatibility matrix

Reviewed 2026-10-08. The versioned, typed source of truth is
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
| OpenCode Go connection | Experimental | Uses a named API-key connection, configured user agent and stable session header. Eligibility for general assistant or unattended workloads is not established; review current plan terms. |
| Sign in with ChatGPT token sharing | Experimental; not implemented | Requires a native Responses API request under the published preview contract. Hutch does not claim eligibility or send a request. Unsupported preview fields are listed in the matrix. |
| OpenCode and Pi executors | Unavailable | Both fail before process creation until process ownership, permission/capability brokering and shared budget enforcement are complete. |
| Consumer-plan OAuth/session reuse | Blocked | Hutch does not read or forward consumer-app cookies or session tokens. Use a supported API-key connection. |

`hutch connections test` can authenticate against a model-list endpoint without spending tokens.
It does not confirm tool calling. The opt-in one-token chat probe and persisted per-connection/model
capability record in ADR-0005 remain unimplemented; model-level tool support stays unknown. Until
that work lands, a fixture-tested route must not be described as a live model verification.

## Request-field regression

`tests/test_compat.py` checks that each published route has a state and dated HTTPS evidence, and
that the typed endpoint exposes the same record. It also checks that the OpenAI token-limit field
selection uses the exact official host, rejecting lookalike domains, embedded paths, insecure
HTTP, and nonstandard ports. `tests/test_providers.py` exercises the request and response fixtures.
The retry checks ensure a generic rejected field is not resent in a second request; only a
stream/SSE-specific rejection can take the non-stream retry. `tests/test_provider_authority.py`
confirms auth/quota failures cannot construct an alternate paid provider before outward approval.

The official protocol sources checked for this matrix include the [OpenAI Chat Completions API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create),
[Anthropic Messages API](https://platform.claude.com/docs/en/api/messages/create), [Ollama chat API](https://docs.ollama.com/api/chat),
[LM Studio tool use](https://lmstudio.ai/docs/developer/openai-compat/tools), [llama.cpp server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md),
and the [vLLM OpenAI-compatible server](https://docs.vllm.ai/en/stable/serving/online_serving/openai_compatible_server/).
