# 00 - Scope

Date: 2026-10-30. Owner: lead. Status: approved for this delivery, bounded by the constraints below.

## 1. Objective

Make Hutch extensible across model providers without coupling provider identity, authentication,
protocol, execution runtime, capabilities, billing or media services into one decision. Concretely:

1. A provider identity layer (service families, categories, official docs, auth methods, endpoints).
2. Multiple named authentication profiles per provider, with explicit billing and lifecycle state.
3. An execution-runtime contract that keeps Hutch's built-in runtime, the managed OpenCode runtime
   and CLI-based runtimes distinct and safely bounded.
4. Reusable protocol adapters (`openai-chat`, `openai-responses`, `anthropic`, `gemini`, `ollama-native`)
   with endpoint-specific differences recorded, not assumed away.
5. An evidence-backed capability registry: documented vs advertised vs observed vs live-verified,
   scoped to provider, endpoint, authentication route, model and runtime.
6. Honest model discovery and readiness states, separate from inference.
7. Connections/model surfaces that scale to many providers and accounts without a configuration maze.
8. Documentation, research artifacts and a marketing website that match shipped functionality.

## 2. Provider inventory (must be accounted for, not necessarily implemented)

Every provider named in the request is listed here. Research status and implementation status are
tracked in `01-RESEARCH-REGISTER.md` and `03-PROVIDER-CAPABILITY-MATRIX.md`; `deferred` is a valid
outcome only when it is stated with a reason.

### 2.1 Core provider and coding-runtime integrations

| Provider | Service families in scope | Known constraints to verify |
|---|---|---|
| OpenCode | managed server runtime, CLI handoff, OpenCode Go API key, provider/model discovery | V2 auth/provider contracts; Go is an issued API key, not OAuth session reuse |
| Anthropic | Console API key, Claude API models, Claude Code CLI, officially supported subscription route | API billing vs subscription; env-var precedence; no unofficial Max proxy |
| Google | Gemini API (AI Studio), Vertex AI, Gemini CLI, grounding/search, image/audio/video/TTS | 2026 consumer CLI auth changes; do not implement retired consumer OAuth |
| MiniMax | API key, Coding Plan (incl. official OAuth if any), intl/China regions, chat, image, video, music, speech | region endpoints, refresh-token behaviour, plan restrictions |
| Moonshot / Kimi | general Moonshot models, Kimi models, Kimi Coding endpoint/credentials | keep general and coding routes distinct |
| OpenAI | Platform API key, Chat Completions, Responses, ChatGPT sign-in (existing experimental), Codex/Codex CLI, images, audio/speech, search | Platform billing vs plan allowances; Codex execution interface |
| Qwen | Qwen Cloud, Alibaba Cloud Coding Plan, Token Plan, Model Studio, Qwen CLI | Portal OAuth retired; non-interactive workload restrictions |
| xAI / Grok | API key, official OAuth/subscription if permitted, chat, search, code exec, image, video, speech, STT | separately billed provider-side tools |
| Z.AI | general GLM API, GLM Coding Plan, CLI auth routes if supported | endpoint/billing separation |

### 2.2 Additional hosted-model providers

Mistral, DeepSeek, GitHub Copilot, Alibaba Model Studio, Xiaomi (Token Plan regions + pay-as-you-go),
StepFun, Volcengine, Tencent Cloud (TokenPlan distinct), Qianfan, Cohere, Synthetic, Venice, Arcee AI,
Vydra, GMI Cloud, OpenCode Go (counted with OpenCode).

### 2.3 Enterprise clouds, gateways and hosted inference

Amazon Bedrock, Bedrock Mantle, Anthropic Vertex, Cloudflare AI Gateway, Vercel AI Gateway,
OpenRouter, ClawRouter, LiteLLM, Microsoft Foundry, Groq, Cerebras, Together AI, Fireworks, NVIDIA,
Hugging Face, DeepInfra, Chutes, NovitaAI, Kilocode, BytePlus, Ollama Cloud.

### 2.4 Local and self-hosted inference

Ollama, LM Studio, vLLM, SGLang, inferrs, ds4, llama.cpp, custom OpenAI/Anthropic-compatible endpoints.
Local classification is based on the resolved endpoint, not the provider name alone; a cloud-tagged
model served by a local runtime stays hosted, and custom remote endpoints never receive ambient keys.

### 2.5 Media, speech and search services

Image: OpenAI, Google, xAI, MiniMax, fal, ComfyUI. Video: xAI, Google, MiniMax, fal, Runway, PixVerse.
Music/audio generation: MiniMax and other verified services. Speech: OpenAI, Google, xAI, MiniMax,
Deepgram, ElevenLabs. Search/grounding: Gemini grounding, xAI search, provider-native search (kept
distinct from external search integrations).

## 3. Architectural boundaries

- **Provider identity** is not a protocol, an endpoint, a billing plan or an account. One provider may
  expose several services, auth methods, endpoints and protocols.
- **Authentication profiles** are named accounts bound to a provider. API keys, OAuth, PKCE, device
  code, CLI-managed and enterprise credentials are distinct `auth_method` values with their own status.
- **Execution runtimes** are separate from model providers. A CLI runtime owns a process lifecycle,
  permission model and credential boundary; it is never "an API provider with a different name".
- **Protocol adapters** are reusable and independently testable. Endpoint-specific omissions are
  recorded in the compatibility data; "OpenAI-compatible" never implies identical behaviour.
- **Capabilities** are evidence records at the narrowest applicable scope. A listing is not inference;
  a text success is not tool support; provider image generation is not image understanding.
- **Media services** reuse the asynchronous job/storage/validation/accounting lifecycle; no second
  generation system.
- **Search** is a separately selectable service with its own credential and attribution; it never
  silently replaces the inference provider.

## 4. Validation and honesty rules

- No live provider account or credential exists in this execution environment. Every hosted route is
  therefore `implemented-unverified` at best; the validation ledger records the probe and the gap.
- No demo fixtures. New tests exercise real logic with ordinary inputs; provider adapters are labelled
  unverified unless a real account exercised them. Existing repository fixtures are left untouched.
- Visual validation uses real application states only. A state that cannot be produced honestly (for
  example a paid generation result with no credential) is recorded as a validation gap.

## 5. Explicit exclusions

- Reverse-engineered or policy-bypassing authentication (cookie scraping, session extraction,
  credential laundering, unofficial consumer-subscription proxies).
- A hosted multi-tenant Hutch service, billing resale, or vendor partnership claims.
- Recreating retired flows (for example the Qwen Portal OAuth route if provider docs remove it).
- Live paid calls without owner authorization and budget admission.
- Rewriting the existing provider core; the change is additive and backward compatible.

## 6. Environment constraints recorded at scope time

- Main checkout has another session's uncommitted work; this delivery is isolated on branch
  `provider-platform` in `.worktrees/provider-platform`.
- Provider credential variables present: none. Local inference endpoints reachable: none.
  Installed CLIs: `claude` 2.1.314, `codex`, `opencode` (version probe blocked by a read-only log path);
  `gemini`, `qwen`, `pi` absent. Details: `artifacts/env-probe.txt`.
