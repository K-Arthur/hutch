# 01 - Research register

Compiled 2026-10-30 (America/Vancouver). This register indexes the official sources read for the
provider platform work and records plan/authentication restrictions that change what Hutch may
implement. It is a source index: live results (including the 2026-10-30 and 2026-10-31 runs) are
recorded in 06-VALIDATION-LEDGER.md, so a source does not become a verified capability by appearing here.

## Method and evidence grades

The four primary fragments in drafts/ carry every URL, fetch date and per-row evidence grade:
drafts/01-core-providers.md, drafts/02-hosting-gateway-local.md, drafts/03-media-speech-search.md and
drafts/04-current-state.md. Grades used there: VENDOR (official vendor page), VENDOR-SECONDARY
(integration docs describing a vendor flow), REPO (Hutch code/recorded evidence), ANECDOTE (single
public report), UNVERIFIED (not readable or contradictory).

Rules applied when turning research into implementation:

1. A documented endpoint is not a working integration; a vendor model list is not capability proof.
2. Subscription-to-API bridges are implemented only where the vendor's own terms authorize a
   third-party client with its own credential. Consumer session reuse is never implemented.
3. Unattended or scheduled use is allowed only where the plan's terms do not forbid it; otherwise the
   connection stays manual-run and is labelled accordingly.
4. Contradictory vendor pages are recorded as contradictions, not resolved by choosing the convenient one.

## Core provider sources and restrictions

| Provider | Primary references consulted | Restrictions that shape Hutch |
|---|---|---|
| OpenAI | developers.openai.com API reference and pricing; developers.openai.com/siwc token-sharing and preview limitations; openai.com Sign in with ChatGPT terms | Platform API billing is separate from ChatGPT plans. Only sanctioned subscription route is the Sign in with ChatGPT preview (Responses-only, eligibility/region gates, 1h access / 30d rotating refresh, many unsupported fields). Codex automation is API-key-first; Codex access tokens are Business/Enterprise only. |
| Anthropic | platform.claude.com Messages API and pricing; Claude Code getting-started; Anthropic consumer/API terms | Console API key billing is separate from a Claude subscription. Anthropic terms prohibit third-party routing of Free/Pro/Max/Ultra plan credentials and storing/intermediating Claude.ai session tokens; community Max proxies are blocked. Sanctioned alternatives: claude setup-token for Claude Code/Agent SDK, and monthly API credits. |
| Google | Gemini API and Vertex AI docs; Gemini Code Assist deprecation notice (developers.google.com/gemini-code-assist/docs/deprecations/code-assist-individuals); Gemini CLI docs | Consumer Gemini CLI authentication changed on 2026-06-18 (free individuals and AI Pro/Ultra) in favour of Antigravity CLI; Gemini CLI remains for Code Assist Standard/Enterprise and paid API/Vertex keys. New AI Studio keys became auth keys from 2026-05-28. Retired consumer OAuth is not implemented. |
| MiniMax | MiniMax platform API docs; M Plan / Token Plan terms (China mirror partially unreachable) | API key and Coding Plan are different billing routes; international and China endpoints are region-specific; refresh-token expiry and region mismatch need explicit recovery; paid music API closed to new users since 2026-08-20. |
| Xiaomi | mimo.mi.com Token Plan page; Speech Recognition and Speech Synthesis API and usage-guide pages (api/audio/Speech-Recognition, api/audio/tts, quick-start/usage-guide/audio/*); api.xiaomimimo.com/v1 | Token Plan is a credits subscription with regional hosts (sgp/cn/ams) and a key is bound to one region; pay-as-you-go is a separate template. Speech is served as a chat completion: ASR takes one `input_audio` content part (wav/mp3 only, base64 ceiling 10 MB) and TTS returns base64 audio from an `assistant` message. The plan's terms name coding tools and do not state that unattended agent platforms are covered. |
| Moonshot / Kimi | Moonshot platform docs; Kimi Code plan docs | General Moonshot and Kimi Coding use distinct endpoints, model namespaces and billing. Kimi K2 new-user cutoff 2026-10-31 and full retirement end-December 2026 recorded in draft 01. |
| Qwen | qwenlm.github.io qwen-code auth configuration; Alibaba Model Studio docs | Qwen OAuth free tier discontinued 2026-04-15; current routes are QwenCloud/Model Studio Token Plan (monthly credits) and Coding Plan (weekly quota) keys with dedicated endpoints. Portal OAuth is retired and must not be rebuilt. |
| xAI | docs.x.ai API docs; X/Grok subscription material | API key billing, provider-side search/code tools and subscription pools are distinct; X Subscription pool is first-party only; custom voices are US-only (excluding Illinois) and Enterprise-gated. |
| Z.AI | docs.z.ai; GLM Coding Plan docs | Coding subscription is a separate billing/auth route from general GLM API; plan terms restrict supported tools, forbid account sharing and can ban after repeated violations. |
| OpenCode | dev.opencode.ai v2 provider/CLI docs; opencode.ai/docs/go | OpenCode Go is a subscription-backed provider API key (not OAuth session reuse) for coding-agent traffic with a required user agent and session header; unattended eligibility is not established. Hutch manages its own opencode serve runtime separately from the coding handoff. |

## Hosted, gateway, enterprise and local references

Complete per-provider rows and 113 source IDs are in drafts/02-hosting-gateway-local.md. The
high-impact findings for Hutch are:

- Gateways: Vercel AI Gateway can fall back from user BYOK credentials to system credentials and bill
  Vercel credits; its response routing metadata should be recorded. OpenRouter can answer with a
  different final model and bills that model; its usage.include parameter is now deprecated while the
  repository still sends it. LiteLLM model_name is an alias that can map to a different upstream model.
  Cloudflare AI Gateway deprecated the unified /compat API on 2026-10-02.
- Enterprise auth: Bedrock uses SigV4/AWS credential chains (plus short- or long-term Bedrock API
  keys); Vertex and Anthropic-on-Vertex use ADC/gcloud tokens with project and region; Microsoft
  Foundry uses an API key or Entra ID and deployment names; Alibaba/Tencent/Volcengine keys are
  region-bound. These are not reducible to one API-key form.
- Alibaba Model Studio moved to workspace-scoped hosts of the form
  https://{WorkspaceId}.{region}.maas.aliyuncs.com/compatible-mode/v1; old dashscope hosts are
  migration sources. Alibaba Model Studio and Qwen Cloud remain distinct identities because their
  endpoint and credential contracts differ.
- Ollama split: local 127.0.0.1:11434 native /api/chat has no auth and is local inference; direct
  Ollama Cloud (ollama.com/api and /v1, Bearer key) is hosted; a signed-in local daemon serving cloud
  models is hosted egress. Local classification follows the resolved endpoint, not the name.
- Custom endpoints: ambient OPENAI/ANTHROPIC keys are allowed only for the exact official host;
  embedded URL credentials are rejected; Strict Offline requires loopback plain HTTP. Outside Strict
  Offline no private-range allowlist or DNS pinning exists in the provider layer: an open review gap
  recorded in 04-ARCHITECTURE-AND-ADRS.md and the security review. Redirects are not followed (measured
  2026-10-31 on loopback: the target server was never called) and a 3xx is now reported as a refusal that
  names the Location, instead of surfacing a JSON parse error.
- Local runtimes: Ollama, LM Studio, llama.cpp and vLLM have named preset endpoints; SGLang, inferrs
  and ds4 have no bundled preset and are reachable only through a custom compatible endpoint today.
- Media: see 03-PROVIDER-CAPABILITY-MATRIX.md and draft 03. Retired/closed services recorded include
  OpenAI Sora/Videos (2026-09-24) and gpt-image-1 (2026-10-23), Google Veo 3.1 previews (2026-10-22),
  MiniMax paid music (closed to new users 2026-08-20), and OpenAI TTS/STT families with 2027 shutdown
  dates. These are not stubbed in Hutch.

## Environment-variable precedence register

Process-global provider variables can silently change which account pays. Recorded traps:

| Variable set | Effect | Hutch mitigation |
|---|---|---|
| ANTHROPIC_API_KEY | Overrides a Claude subscription; ranks below ANTHROPIC_AUTH_TOKEN in Claude Code | Connection-scoped keys take precedence for named connections; ambient Anthropic key is sent only to the official host; account source is shown per connection. |
| ANTHROPIC_BASE_URL | Can redirect first-party Anthropic traffic to a third-party endpoint | A custom endpoint requires its own named connection; ambient keys are exact-host-only; the endpoint is displayed in UI and receipts. |
| OPENAI_API_KEY | Ambient key for the official OpenAI host only | Never sent to a custom base URL; custom endpoints need HUTCH_API_KEY or their own connection key. |
| OPENCODE saved account | Overrides an environment connection in the OpenCode CLI | Hutch does not import OpenCode CLI auth; OpenCode Go uses its issued key in a named Hutch connection. |
| OPENAI_BASE_URL / OPENAI_MODEL | Qwen headless tooling redirects default traffic | Not read by Hutch provider construction; Qwen is not implemented in this slice. |

## Direct source links

Primary vendor links read by the research team on 2026-10-30 (full per-provider URL tables are in the
drafts; this list is the minimum a reader can follow directly):

- https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create
- https://developers.openai.com/siwc/token-sharing-open-source
- https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations
- https://openai.com/policies/sign-in-with-chatgpt-terms/
- https://platform.claude.com/docs/en/api/messages/create
- https://platform.claude.com/docs/en/about-claude/pricing
- https://docs.anthropic.com/en/docs/claude-code/getting-started
- https://developers.google.com/gemini-code-assist/docs/deprecations/code-assist-individuals
- https://qwenlm.github.io/qwen-code-docs/en/users/configuration/auth/
- https://dev.opencode.ai/v2/docs/providers/
- https://dev.opencode.ai/v2/docs/cli/providers
- https://opencode.ai/docs/providers/
- https://opencode.ai/v2/docs/permissions
- https://opencode.ai/docs/go/
- https://docs.ollama.com/api/chat
- https://docs.ollama.com/context-length
- https://lmstudio.ai/docs/developer/openai-compat/tools
- https://docs.vllm.ai/en/stable/serving/online_serving/openai_compatible_server/
- https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
- https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties
- https://openrouter.ai/docs/guides/routing/model-fallbacks
- https://docs.openclaw.ai/providers
- https://docs.openclaw.ai/concepts/model-providers
- https://docs.openclaw.ai/providers/openai
- https://docs.openclaw.ai/providers/anthropic
- https://docs.openclaw.ai/providers/google
- https://docs.openclaw.ai/providers/minimax
- https://docs.openclaw.ai/providers/moonshot
- https://docs.openclaw.ai/providers/qwen
- https://docs.openclaw.ai/providers/xai
- https://docs.openclaw.ai/providers/zai

The docs.openclaw.ai pages are the reference index supplied with the project request; they were used
as a starting map, not as a substitute for the vendor pages above. A link existing is not evidence
that Hutch implements the route.

## Verification boundary

Only two routes have dated live evidence: DeepSeek text through the built-in runtime and the managed
OpenCode runtime with a DeepSeek model (both 2026-10-30). Every other provider route in this package is
at most implemented-unverified. The validation ledger records the earlier absence of direct provider
credentials and local servers. Dates above are the draft fetch date (2026-10-30); re-fetch before
relying on a specific endpoint, plan term or model retirement.

## 2026-10-31 addendum: native Gemini route

The native `generateContent` adapter (`src/hutch/providers/gemini.py`) was written against these
sources, read on 2026-10-31 in this order:

| Source | What it settled |
|---|---|
| `https://generativelanguage.googleapis.com/$discovery/rest?version=v1beta` (revision 20261030, fetched 2026-10-31) | The exact wire schema: `contents` / `systemInstruction` / `tools.functionDeclarations` (`parametersJsonSchema`) / `generationConfig` (`maxOutputTokens`, `temperature`, `thinkingConfig`), `Part` variants used for text, inline media, function calls/results, `thought` and `thoughtSignature`, `UsageMetadata` counters, the `finishReason` enum, and `Model.supportedGenerationMethods` on the model list. |
| `https://ai.google.dev/gemini-api/docs/text-generation` | `x-goog-api-key` header auth and `:streamGenerateContent?alt=sse` for streaming, both read from the page itself rather than assumed. |
| `https://ai.google.dev/gemini-api/docs/thinking` | generateContent carries thought signatures as part metadata and they must be replayed; the schema's `MISSING_THOUGHT_SIGNATURE` finish reason is the failure that follows a lost signature. |

Facts from that reading that shape the implementation and are recorded instead of being papered over:

- `GenerationConfig.temperature` is documented as no longer supported and silently ignored on Gemini
  3.6 Flash and newer. Hutch still sends it when a Bot sets it and the compatibility matrix says it may
  have no effect; it is never presented as effective.
- `thinkingConfig.thinkingLevel` is documented as Gemini 3+ only ("use with earlier models results in
  an error"), so Hutch maps an effort level only for those model id prefixes.
- `finishReason` distinguishes truncation (`MAX_TOKENS`), continuation (`CONTINUATION`), filters
  (`SAFETY`, `RECITATION`, `BLOCKLIST`, `PROHIBITED_CONTENT`, `SPII`, ...) and malformed function calls;
  each maps to a distinct typed outcome rather than to an empty successful reply.
- A remote image URL is not fetched. The adapter accepts only inline `data:` images, so a provider
  adapter cannot be turned into an HTTP fetcher for user-supplied URLs.
- `parametersJsonSchema` accepts full JSON Schema, but a non-local `$ref` would be resolved from the
  network; such a schema is refused instead of being silently dropped.

Status after this addendum: the Gemini API-key route is implemented and contract-tested against
recorded shapes. No Gemini credential existed in this environment, so it remains not live-verified and
the matrix records `implemented-unverified`.
