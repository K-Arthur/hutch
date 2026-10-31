# Fragment 02 - Hosted providers, gateways, enterprise clouds and local inference

Input fragment for docs/research/2026-10-provider-platform/00-SCOPE.md through 07-ROLLOUT-AND-MIGRATION.md.
Research date: 2026-10-30 (America/Vancouver). Author: research-hosting teammate.
Output file: docs/research/2026-10-provider-platform/drafts/02-hosting-gateway-local.md (worktree clean HEAD 1c454c32).

## Evidence classes used in this fragment

- V = vendor-documented. Read from the vendor's own docs, README or blog on 2026-10-30. Vendor statements are not independently reproduced.
- S = secondary integration documentation. Mostly the docs.openclaw.ai provider pages named in the request as a starting index (S1), plus OpenClaw concepts pages. These are third-party relative to Hutch and to most vendors; they describe how one client integrates, not necessarily vendor policy. Used for endpoint/auth values only where the vendor page could not be fetched or rendered.
- R = repo evidence. Hutch source/data read in this session (compat.json, connections.json, providers source, realignment/provider-compatibility.md, research docs). These are internal facts, not external verification.
- U = UNVERIFIED. Fetch failed, page was a JavaScript shell, or the detail was not present in what was read.
- A = anecdote. One community report, not reproduced, no prevalence implied.

Verification boundary: no live provider account, API key or inference request was used. Nothing in this fragment is "Hutch verified live". Every endpoint/auth/billing statement is documentation-observed only. Per the request, "endpoint listed in docs" must never be presented as "Hutch verified live": a live check would require an owned Hutch connection making a real request, which this session did not do.

## Summary table (one row per provider/integration)

| # | Provider / integration | Service type | Auth | Primary endpoint (evidence) | Discovery | Billing attribution | Status (evidence) |
|---|---|---|---|---|---|---|---|
| 1 | Mistral | Vendor API | API key bearer | https://api.mistral.ai/v1 (V) | not verified (U); static catalog (S) | per-token to Mistral account (S) | Active (V) |
| 2 | DeepSeek | Vendor API | API key bearer | https://api.deepseek.com; https://api.deepseek.com/anthropic (V) | not verified (U) | per-token to DeepSeek (V for model naming) | Active; legacy model names re-pointed (V) |
| 3 | GitHub Copilot | Subscription service | GitHub OAuth/device flow; official Copilot SDK (V) | no public BYO-key inference URL found; account-specific endpoint resolved by client (S) | SDK docs (V); plan catalog (S) | Copilot plan, not per-token API (S) | Active; raw token reuse off-limits for Hutch (R) |
| 4 | Alibaba Model Studio | Enterprise cloud MaaS | region-bound API key | https://{WorkspaceId}.{region}.maas.aliyuncs.com/compatible-mode/v1 (V) | not verified (U) | per-token or plan (S) | Active; endpoint migration in progress (V) |
| 5 | Xiaomi MiMo | Vendor API + Token Plan | sk- pay-as-you-go key; tp- plan key (S) | https://api.xiaomimimo.com/v1; https://token-plan-{cn,sgp,ams}.xiaomimimo.com/v1 (S/R) | model list configured (R) | per-token; credits subscription (S/R) | Active; plan terms UNVERIFIED (U) |
| 6 | StepFun | Vendor API + Step Plan | API key | https://api.stepfun.com/v1 or https://api.stepfun.ai/v1; /step_plan/v1 (S) | not verified (U) | per-token or plan (S) | Active; vendor docs not machine-readable (U) |
| 7 | Volcengine (Doubao/ARK) | Enterprise cloud MaaS | ARK API key bearer or Access Key signature (V) | https://ark.cn-beijing.volces.com/api/v3 (V) | not verified (U) | per-token to Volcengine account (S) | Active (V) |
| 8 | Tencent Cloud TokenHub/TokenPlan | Enterprise cloud MaaS | API key bearer | https://tokenhub.tencentmaas.com; https://tokenhub-intl.tencentmaas.com (V); TokenPlan https://api.lkeap.cloud.tencent.com/plan/v3 (S) | GET /v1/models (V) | per-token or plan (S) | Active; no cross-region/site calls (V) |
| 9 | Qianfan (Baidu) | Enterprise cloud MaaS | API key (bce-v3/ALTAK- format) | https://qianfan.baidubce.com/v2 (S) | not verified (U) | per-token or Token Plan (S) | Active; Coding Plan retired/migrated (U nav) |
| 10 | Cohere | Vendor API | API key | https://api.cohere.ai/compatibility/v1 (V) | not verified (U) | per-token to Cohere (S) | Active (V) |
| 11 | Synthetic | Hosted provider, OpenAI + Anthropic compatible | API key bearer | https://api.synthetic.new/v1; https://api.synthetic.new/anthropic (V/S) | model list in vendor nav (V) | usage-based (V) | Active; syn: aliases auto-route (V) |
| 12 | Venice | Hosted provider, OpenAI compatible | API key bearer; X402 crypto billing (V) | https://api.venice.ai/api/v1 (S/U for exact base) | models API in vendor nav (V) | plans plus X402 (V) | Active (V) |
| 13 | Arcee | Vendor API | API key | https://api.arcee.ai/api/v1 (S) | not verified (U) | per-token (S) | Active; small vendor, docs landing read (V) |
| 14 | Vydra | Media-only API | API key | https://vydra.ai/api/v1 (V; use www host per S) | models API in vendor nav (V) | job/credit based (U) | Active; NO text-chat route (V/S) |
| 15 | GMI Cloud | Serving platform | API key bearer; optional org header (V) | https://api.gmi-serving.com/v1 (V) | GET /v1/models (V) | per-token/platform (U) | Active (V) |
| 16 | Amazon Bedrock | Enterprise cloud | AWS SigV4 credential chain; Bedrock API keys (V) | https://bedrock-runtime.{region}.amazonaws.com; /openai/v1 (V) | ListFoundationModels / ListInferenceProfiles (V) | AWS account billing (V) | Active (V) |
| 17 | Bedrock Mantle | Enterprise cloud compatibility endpoint | Bedrock API key bearer (V); SigV4 acceptance U | https://bedrock-mantle.{region}.api.aws/v1 (V) | GET /models (V) | AWS account billing (S) | Compatibility endpoint; AWS recommends bedrock-runtime for new apps (V) |
| 18 | Anthropic Vertex | Enterprise cloud | Google OAuth access token or ADC (V) | https://aiplatform.googleapis.com/v1/projects/{p}/locations/{r}/publishers/anthropic/models/{m}:rawPredict (V) | Vertex model catalog (S) | Google Cloud billing (S/U) | Active (V) |
| 19 | Cloudflare AI Gateway | Gateway (BYOK) | Cloudflare token plus stored provider key (V) | https://gateway.ai.cloudflare.com/v1/{account}/{gateway}/...; REST under api.cloudflare.com/client/... (V) | model catalog (V) | provider billed directly (BYOK); Cloudflare plan (V) | Active; unified /compat API deprecated for single-model calls (V) |
| 20 | Vercel AI Gateway | Unified gateway | AI_GATEWAY_API_KEY, OIDC, or BYOK (V) | https://ai-gateway.vercel.sh (S) | GET /v1/models (S) | prepaid credits, zero markup; BYOK fallback can bill credits (V) | Active (V) |
| 21 | OpenRouter | Unified router | API key | https://openrouter.ai/api/v1 (R/V) | authenticated /models (V/R) | credits; billed at ultimately used model (V) | Active (V) |
| 22 | ClawRouter | Managed router | policy-scoped key | https://clawrouter.openclaw.ai (S) | /v1/catalog (S) | monthly budget aggregate /v1/usage; upstream held by router (S/U) | Active in OpenClaw; independent vendor docs not found (U) |
| 23 | LiteLLM | Self-hosted gateway | master key plus virtual keys (V) | operator-hosted; default http://localhost:4000 (S) | /v1/models returns aliases (V/S) | gateway bookkeeping; upstream accounts (V) | Active (V) |
| 24 | Microsoft Foundry | Enterprise cloud | API key bearer or Entra ID keyless (V) | https://{resource}.openai.azure.com/openai/v1 or https://{resource}.services.ai.azure.com/openai/v1 (V) | deployments are the access unit (V) | Azure account, per deployment (V) | Active (V) |
| 25 | Groq | Vendor/inference | API key | https://api.groq.com/openai/v1 (V) | not verified (U) | per-token (S) | Active (V) |
| 26 | Cerebras | Vendor/inference | API key | https://api.cerebras.ai/v1/chat/completions (V) | not verified (U) | per-token (S) | Active (V) |
| 27 | Together AI | Serving platform | API key | https://api.together.xyz/v1 (S) | not verified (U) | per-token (S) | Active; docs landing read (V) |
| 28 | Fireworks | Serving platform | API key | https://api.fireworks.ai/inference/v1 (V) | not verified (U) | per-token (S) | Active; OpenAI and Anthropic compatibility (V) |
| 29 | NVIDIA | Vendor/inference | API key | https://integrate.api.nvidia.com/v1 (S) | not verified (U) | hosted tier (S; "free" claim U) | Active (V landing) |
| 30 | Hugging Face Inference | Inference router | HF token with inference permission (S) | https://router.huggingface.co/v1 (S) | not verified (U) | single HF token, provider rates (S) | Active; chat-completions surface only (S) |
| 31 | DeepInfra | Serving platform | API key | https://api.deepinfra.com/v1/openai (S) | live catalog (S) | per-token (S) | Active; docs landing read (V) |
| 32 | Chutes | Serving platform (Bittensor) | API key or OAuth token (S) | https://llm.chutes.ai/v1 (S) | not verified (U) | plan/credits (U) | Active; docs landing read (V) |
| 33 | NovitaAI | Serving platform | API key | https://api.novita.ai/openai/v1 (S) | catalog (S) | per-token (S) | Active (S) |
| 34 | Kilocode / Kilo Gateway | Unified gateway | API key | https://api.kilo.ai/api/gateway (V) | /v1/models (S) | Kilo credits/plan (U) | Active (V) |
| 35 | BytePlus (ModelArk) | Enterprise cloud | API key (S) | UNVERIFIED (U); vendor docs JavaScript-only | UNVERIFIED (U) | per-token cloud (U) | Active product; route not documentable this session (U) |
| 36 | Ollama Cloud | Hosted inference | API key bearer | https://ollama.com/api/chat; https://ollama.com/v1; /v1/messages (V) | not verified (U) | Ollama plan (U) | Active (V) |
| 37 | Ollama (local) | Local runtime | none on loopback (V/R) | http://localhost:11434/api/chat (V/R) | /api/tags (S) | no charge; cloud billed to account (V) | Active (V) |
| 38 | LM Studio | Local runtime | optional API tokens; default none (V) | http://127.0.0.1:1234, /v1 (S) | /api/v1/models (S) | none local | Active (V) |
| 39 | vLLM | Local/self-hosted | optional server API key (S) | http://127.0.0.1:8000/v1 (S) | /v1/models (S) | none self-hosted | Active; vendor page rendered but not extracted (U detail) |
| 40 | SGLang | Local/self-hosted | optional server API key (S) | http://127.0.0.1:30000/v1 (S) | /v1/models (S) | none self-hosted | Active; OpenAI/Anthropic/Ollama-compatible pages listed (V) |
| 41 | inferrs / llmman | Local + hybrid | none on loopback; keys required off-loopback (V) | http://127.0.0.1:17434/v1 (V) | model refs from OCI/HF pulls (V) | none local; hosted side billed upstream (V) | Active; naming shift inferrs->llmman U |
| 42 | ds4 | Local runtime | none documented (V) | http://127.0.0.1:8000; /v1 (V port, S API shape) | not verified (U) | none | Active; macOS Metal only (V/S) |
| 43 | llama.cpp server | Local runtime | optional --api-key, default none (V) | operator-defined; OpenAI-compatible (V) | /v1/models (S) | none | Active (V) |
| 44 | Custom compatible endpoint | Compatible endpoint | connection-owned key (R) | operator-defined HTTP(S) (R) | optional model-list request (R) | operator's upstream account (R) | Supported, governed by repo rules (R) |

## Cross-cutting findings

### A. Model identity: what the gateway reports vs what the user requested

- Hutch policy already separates requested route from provider-reported identity: the catalog price is informational, and recorded response identity is used for receipts (R7, R6). This fragment extends that rule to gateways.
- OpenRouter: a models array (or Anthropic fallbacks parameter) tries fallbacks on context-length errors, moderation refusals, rate limits or downtime; pricing uses the model that was ultimately used, and that model is returned in the response model attribute (V25). provider.allow_fallbacks defaults true; provider.order, data_collection, zdr, sort, max_price can constrain routing (V26). Consequence: the requested catalog ID is not proof of the serving model, and a :free first entry followed by a paid entry bills the paid price (V25).
- LiteLLM: model_name is a local alias; the docs example maps model_name gpt-6.1-sol to litellm_params.model ollama/llama2 (V28). /v1/models exposes aliases, not upstream vendor IDs. Identity is truthful only when the operator maps aliases 1:1; otherwise the gateway is a name-translation layer by design.
- Vercel AI Gateway: response provider metadata includes canonicalSlug, resolvedProvider, resolvedProviderApiModelId, finalProvider, fallbacksAvailable, modelAttempts, credentialType and cost/marketCost (V33), so final-provider attribution is auditable when the client records it.
- Cloudflare AI Gateway: provider-native routes are pass-through with stored provider keys (BYOK) (V30); the unified /compat API is deprecated for single-model calls and the REST API is the replacement (V30). A dynamic-routing feature is listed (V29) but fallback/billing behavior was not read (U).
- Router-style or alias-style IDs exist elsewhere: Synthetic syn: aliases auto-resolve to the latest recommended model (V10); Fireworks router IDs (S29) and Kilo model IDs (V11) are namespaced; DeepSeek itself re-points legacy model names to newer served models while stating unchanged calling method and Flash-price billing (V2); Foundry uses deployment names as the model field, so the value is an alias by design (V20); Bedrock runtime uses a runtime model or inference-profile ID that differs from the base model ID (V18).
- Practical rule for docs 00-07: store both requested_route and responded_model; log gateway response IDs/metadata when present; never treat a gateway catalog row as a capability or identity guarantee.

### B. Billing attribution when a gateway routes upstream

- OpenRouter: prepaid credits; requests are priced on the ultimately used model (V25); every response returns token counts and cost in credits through usage accounting, and the older Chat Completions usage.include / stream_options.include_usage parameters are now marked deprecated (V27). This matters because repo compat.json (reviewed 2026-10-11) still sends usage.include=true to retain billed cost (R1): verify current behavior before promising cost receipts from that field. OpenRouter marketplace/platform fee was not read (U).
- Vercel: AI Gateway charges no markup and no platform fee on tokens; users buy AI Gateway Credits, and the free tier covers only a subset of models (V34, V31). With BYOK the provider bills the user directly, BUT if a query using the user's key fails, AI Gateway retries with its system credentials so the request can bill Vercel credits instead (V32). The provider restriction filter does not disable that fallback, and ZDR limits it to ZDR-eligible system credentials (V32). Logs expose provider and credential source, and a successful key test does not prove the grant funded the request (V32). This is the clearest "who pays?" ambiguity found in this research.
- Cloudflare AI Gateway: the documented path is BYOK - provider keys are stored in the gateway and requests route to the provider (V30); features are available on all plans (V29). No unified billing or Cloudflare-credit inference billing was found in the pages read (U coverage beyond these pages). Report provider invoice and Cloudflare invoice separately.
- LiteLLM: virtual-key spend tracking is gateway bookkeeping; the actual invoice is the upstream account the operator configured. Spend is tracked per key, user, team and end-user (V28) but that does not move the underlying provider bill.
- ClawRouter: a key carries a monthly budget and aggregate usage (/v1/usage), while upstream credentials and forwarding stay inside ClawRouter (S24). Who invoices the upstream accounts, and at what price, is not documented in the pages read (U).
- Hugging Face Inference Providers: one HF token; docs describe pricing following provider rates plus a free tier (S31), so the payer is the HF account while the serving provider is chosen by the router (U details).
- Enterprise clouds: payer is the cloud account - AWS for Bedrock/Mantle, Google Cloud for Vertex Claude, Azure for Foundry, Volcengine/Tencent/Alibaba accounts for their hosting (V16, V19, V20, V23, V24, V22). These are not the model vendor's first-party API billing relationship.
- Two-hop privacy products: Venice documents "anonymized" proxy access to Claude/GPT/Gemini/Grok (S15) where the underlying provider still processes the request. Billing attribution stays at the first hop, while data-handling terms involve the second hop.
- Hutch requirement: record provider-reported usage as evidence, and a gateway response ID/cost only when the gateway documents it. Never claim payer proof from token counts. A local allowance is an admission estimate, not a billing cap (R6).

### C. Enterprise cloud auth: SigV4, ADC, Entra ID, region-bound keys

- Bedrock: official auth is the AWS SDK default credential chain (environment, shared config, instance role) using SigV4; the secondary integration docs state this explicitly (S19). Bedrock API keys are an additional bearer-token mechanism: short-term keys last up to 12 hours and inherit the IAM principal's permissions; long-term keys last until a configured expiration and create an IAM user; AWS recommends long-term only for exploration and says all API calls are logged in CloudTrail while keys are not (V16). So a paste-an-API-key UI can work for Bedrock API keys but cannot replace SigV4 signing for the normal API.
- Vertex Claude: cURL examples get a token with gcloud auth print-access-token; the AnthropicVertex SDKs use Google authentication / Application Default Credentials; the caller needs an IAM role containing aiplatform.endpoints.predict such as roles/aiplatform.user (V19, V47). Requests go to https://aiplatform.googleapis.com/v1/projects/{project}/locations/{region}/publishers/anthropic/models/{model}:rawPredict with anthropic_version vertex-2023-10-16, and global/multi-region/regional endpoint choices exist (V19). The endpoint is not an Anthropic API host, so an Anthropic key alone does not authenticate it.
- Microsoft Foundry: API key auth uses a bearer token and grants full access to the resource; keyless Microsoft Entra ID auth is recommended for production with RBAC role assignments (V20, V21). Base URL accepts both https://{resource}.openai.azure.com/openai/v1/ and https://{resource}.services.ai.azure.com/openai/v1; the model field carries the deployment name and the /openai/v1 route has implicit versioning (V20).
- Volcengine ARK: data-plane API supports API-key bearer auth and Access Key signature auth (enterprise resource-level management); data-plane base URL is https://ark.cn-beijing.volces.com/api/v3 while control-plane is https://ark.cn-beijing.volcengineapi.com; Coding Plan users must use a different base URL or may incur extra fees (V23).
- Tencent TokenHub: Bearer API key; separate Guangzhou and Singapore hosts; calls must not cross region or site (V24).
- Alibaba Model Studio: API keys are bound to a region; cross-region calls fail with 401/403/404 or connection errors; current OpenAI-compatible base URLs are workspace-scoped https://{WorkspaceId}.{region}.maas.aliyuncs.com/compatible-mode/v1 (V22).
- Bedrock Mantle: the documented OpenAI-SDK path uses a bearer token (Bedrock API key) against https://bedrock-mantle.{region}.api.aws (V18); whether SigV4 is also accepted on Mantle was not verified (U).
- Hutch implication: credential class must be stored per connection - static API key, cloud identity (SigV4/ADC/Entra), or signed request. A single "paste API key" form cannot represent all enterprise routes, and none were live-tested here.

### D. Ollama Cloud vs local Ollama classification

- Local Ollama: the local API at http://localhost:11434 requires no authentication; native /api/chat is the primary surface (V15). An OpenAI-compatible /v1 exists but the secondary integration docs warn that local /v1 breaks tool calling and can emit raw tool-call JSON (S36).
- Ollama Cloud direct: https://ollama.com/api (native) and https://ollama.com/v1 (OpenAI-compatible) require an API key sent as Authorization: Bearer; no Ollama installation or local server is required (V14, V15). The hosted Anthropic-compatible /v1/messages endpoint also requires the Bearer key; x-api-key alone is not supported (V15).
- Hybrid through a signed-in local daemon: ollama signin authenticates cloud requests; the local API can then serve cloud models such as gpt-oss:120b-cloud (V15). This is hosted egress through a loopback endpoint.
- Repo classification: compat.json already classifies recognized cloud-tagged model names as hosted, not local (R1); provider-compatibility.md says recognized cloud-tagged names are treated as hosted and that local route mode does not guarantee offline operation (R6).
- Recommended rule for docs: classify hosted when the endpoint host is not loopback, OR the local daemon has a cloud session, OR the model carries a cloud tag/namespace. Only loopback with no cloud-tagged models and no signed-in cloud session can be treated as local. Strict Offline mode requires an explicit loopback endpoint and rejects any non-loopback route (R4).
- The local/cloud distinction is not only billing: local Ollama needs an explicit num_ctx, and the OpenAI-compatible /v1 cannot set it, so prompts silently truncate (R1, R8). A "local" classification is therefore also a capability/assertion boundary.

### E. Custom compatible endpoints: credential rules and SSRF-shaped risks

- Credential rules already in the repo: an ambient OPENAI_API_KEY or ANTHROPIC_API_KEY is only sent to the exact official HTTPS host (scheme https, exact hostname, port 443 or none, no userinfo); lookalikes, plain HTTP and userinfo tricks are rejected (R3). A custom endpoint never receives OPENAI_API_KEY; it uses HUTCH_API_KEY or the named connection's own key (R3). Endpoints with embedded credentials are rejected outright (R3).
- Custom Anthropic-compatible connections use the root URL without /v1/messages because the SDK appends the path (R2).
- Strict Offline/local mode is the strong SSRF-shaped control: the endpoint must be a plain HTTP loopback URL, with no userinfo, no query parameters, no scoped IPv6, a numeric loopback address (localhost is rewritten to 127.0.0.1) and a nonzero port; arbitrary hostnames are not resolved by the validator (R4). That is intentionally loopback-only, not a general private-range filter.
- Outside Strict Offline, a named connection's base URL is operator-chosen. This session found no allowlist of public/private ranges, no redirect policy and no DNS-pinning rule in the provider-layer code that was read (R3, R4). This is the SSRF review gap to carry into docs 00-07: custom endpoints are an explicit trust decision, not a sandboxed fetch. Test expectations that do exist cover rejecting lookalike domains, embedded paths, insecure HTTP and nonstandard ports in the OpenAI token-field selector (R6).
- Model-list discovery sends the same connection key to the same host, so discovery has the same trust domain as inference (R1).
- Gateway caveat: pointing a custom connection at a gateway sends the gateway key to the gateway, which then holds upstream provider credentials (V30, S24). Hutch cannot see upstream credential class or identity unless the gateway reports it (for example Vercel routing metadata, V33; OpenRouter response model and cost, V25/V27). Do not describe a gateway route as a direct vendor route.
- Recommendations for the docs (not current behavior): HTTPS only by default for hosted routes, reject link-local/metadata/private ranges unless explicitly local, pin the resolved host, disallow cross-host redirects, and show the destination host on every connection test.

## Per-provider classification

### 1. Mistral
- Type: vendor API; OpenAI-compatible Chat Completions (V1).
- Auth: MISTRAL_API_KEY bearer; keys from console.mistral.ai (S2).
- Endpoint/regions: https://api.mistral.ai/v1 (V1). Region availability not read (U15).
- Discovery: model list not verified (U); secondary integration docs carry a static catalog (S2).
- Billing: per-token to the Mistral account (S2); price table not re-read (U).
- Restrictions: vendor documents OpenAI-compatible migration; Voxtral transcription, realtime STT and embeddings are separate surfaces (S2).
- Status: active; documentation-observed only. Evidence: V1, S2.

### 2. DeepSeek
- Type: vendor API; OpenAI-compatible and Anthropic-compatible base URLs (V2).
- Auth: DEEPSEEK_API_KEY bearer (V2).
- Endpoint/regions: https://api.deepseek.com (OpenAI shape) and https://api.deepseek.com/anthropic (Anthropic shape) (V2). Regions not read (U).
- Discovery: not verified (U).
- Billing: per-token; vendor states legacy deepseek-v4-flash requests are served by DeepSeek-V4.1-Flash-1017 and billed at the Flash price (V2).
- Restrictions: model-name re-pointing means requested name != served model version; record the response model (V2).
- Status: active; naming is vendor-managed. Evidence: V2, S3.

### 3. GitHub Copilot
- Type: subscription coding service with OAuth/device login, not a public per-token inference API (S4, V35).
- Auth: GitHub account plus Copilot plan; device flow or vendor SDK authentication (V35, S4). Official Copilot SDK docs describe authentication options for building Copilot-powered apps (V35, V36).
- Endpoint/regions: no public BYO-key OpenAI-shaped base URL was found; a client validates Copilot access and resolves an account-specific Copilot API endpoint (S4). Treat any direct base URL as client-internal, not a documented contract.
- Discovery: SDK docs and plan catalog (V35, S4); no public /models contract verified (U).
- Billing: Copilot subscription/plan, not per-token API pricing (S4); allowance figures not read (U).
- Restrictions: eligibility and client restrictions are plan-scoped. A single third-party issue title claims a generic OpenAI-compatible approach violates GitHub's terms (A1); it was not opened or reproduced, so it is anecdote, not policy. Hutch's consumer OAuth/session-reuse block applies to Copilot subscription tokens unless the route is documented (R1, R6).
- Status: active product; for Hutch, experimental at best via the official SDK path, unsupported as a raw model API. Evidence: V35, V36, S4, A1, R1.

### 4. Alibaba Model Studio
- Type: enterprise cloud MaaS (DashScope international / Qwen Cloud); OpenAI-compatible (V22, S5, S6).
- Auth: API key; keys are bound to a region; separate coding-plan and standard-token endpoints exist (V22, S6).
- Endpoint/regions: workspace-scoped https://{WorkspaceId}.{region}.maas.aliyuncs.com/compatible-mode/v1; vendor lists Singapore, Virginia, Beijing, Hong Kong (China) and Tokyo rows; older dashscope.aliyuncs.com / dashscope-intl.aliyuncs.com / cn-hongkong.dashscope.aliyuncs.com hosts are migration sources (V22). Legacy global coding-plan endpoint https://coding-intl.dashscope.aliyuncs.com/v1 (S6).
- Discovery: not verified (U).
- Billing: per-token standard or subscription plan (S6); regional billing not read (U).
- Restrictions: cross-region calls fail (401/403/404 or connection error); endpoint migration is active, so hard-coded old hosts are a risk (V22).
- Status: active, endpoint migration in progress. Evidence: V22, S5, S6.

### 5. Xiaomi MiMo
- Type: vendor API with pay-as-you-go and Token Plan subscription credits (S7, R2).
- Auth: XIAOMI_API_KEY for sk- keys; XIAOMI_TOKEN_PLAN_API_KEY for tp- keys (S7, R2).
- Endpoint/regions: pay-as-you-go https://api.xiaomimimo.com/v1; Token Plan regional hosts token-plan-cn / token-plan-sgp / token-plan-ams .xiaomimimo.com/v1 plus /anthropic (S7, R2). Region hosts not vendor-verified (U).
- Discovery: model-list endpoint configured in repo templates (R2); live catalog not verified (U).
- Billing: per-token pay-as-you-go; Token Plan is a credits subscription, credits are not tokens (S7, R2).
- Restrictions: the Token Plan terms page is a JavaScript shell and could not be read (U2); repo notice says plan is sold for individual developers, documented for coding tools, does not state unattended agent platforms are covered, and keys must not be shared (R2). Automated/unattended eligibility is UNVERIFIED.
- Status: active; subscription route not safe to promise. Evidence: S7, R2, U2.

### 6. StepFun
- Type: vendor API with standard and Step Plan routes; OpenAI-compatible (S8).
- Auth: STEPFUN_API_KEY (S8).
- Endpoint/regions: standard https://api.stepfun.com/v1 (China) or https://api.stepfun.ai/v1 (global); Step Plan /step_plan/v1 on the matching host; China keys with .com, global keys with .ai (S8).
- Discovery: not verified (U).
- Billing: per-token or plan (S8); details not read (U).
- Restrictions: standard and Step Plan are separate providers with separate model prefixes; plan model availability differs by model (S8).
- Status: active; vendor pages are rendered/JavaScript, so these values remain secondary (U3). Evidence: S8, U3.

### 7. Volcengine (Doubao / ARK)
- Type: enterprise cloud MaaS (ByteDance Volcano Engine), OpenAI-compatible data-plane API (V23).
- Auth: ARK API key as Authorization: Bearer, or Access Key signature for resource-level management (V23).
- Endpoint/regions: data plane https://ark.cn-beijing.volces.com/api/v3; control plane https://ark.cn-beijing.volcengineapi.com; Coding Plan uses a different base URL and wrong URLs can cause extra fees (V23).
- Discovery: not verified (U).
- Billing: per-token to the Volcengine account (S9, U details).
- Restrictions: coding-plan vs general endpoints are distinct; model IDs are Volcengine-hosted names such as doubao-seed-* and hosted third-party models (S9).
- Status: active; vendor docs in Chinese, read directly. Evidence: V23, S9.

### 8. Tencent Cloud TokenHub / TokenPlan
- Type: enterprise cloud MaaS; OpenAI-compatible and Anthropic-compatible protocols (V24, S11).
- Auth: API key via Authorization: Bearer; TokenHub and TokenPlan keys are separate (V24, S11).
- Endpoint/regions: Guangzhou https://tokenhub.tencentmaas.com (backup https://tokenhub.tencentmaas.cn); Singapore https://tokenhub-intl.tencentmaas.com (backup .cn); no cross-region or cross-site calls; TokenPlan https://api.lkeap.cloud.tencent.com/plan/v3 (S11).
- Discovery: GET /v1/models on TokenHub returns model IDs and online status (V24).
- Billing: per-token TokenHub or plan package (S11); billing detail page not read (U).
- Restrictions: region selection is mandatory and must match the provisioned region (V24).
- Status: active; endpoint facts vendor-documented. Evidence: V24, S11.

### 9. Qianfan (Baidu)
- Type: enterprise cloud MaaS; unified OpenAI-compatible API (S12).
- Auth: QIANFAN_API_KEY; Baidu Cloud keys use bce-v3/ALTAK- format (S12).
- Endpoint/regions: https://qianfan.baidubce.com/v2 (S12); vendor docs are rendered navigation and could not be extracted (U4).
- Discovery: not verified (U).
- Billing: per-token or Token Plan (S12); details not read (U).
- Restrictions: vendor navigation shows Coding Plan sale stopped and migration to Token Plan, plus Token Plan personal/enterprise variants (U4); treat legacy Coding Plan routes as retired/migrating.
- Status: active API; plan routes changing. Evidence: S12, U4.

### 10. Cohere
- Type: vendor API with an OpenAI-compatible Compatibility API (V3).
- Auth: COHERE_API_KEY (V3).
- Endpoint/regions: https://api.cohere.ai/compatibility/v1 (V3). Regions not read (U).
- Discovery: not verified (U).
- Billing: per-token to the Cohere account (S13).
- Restrictions: compatibility docs describe using OpenAI SDKs against a subset surface; native Cohere API remains the full surface (V3, S13).
- Status: active. Evidence: V3, S13.

### 11. Synthetic
- Type: hosted provider with OpenAI-compatible and Anthropic-compatible APIs; usage-based pricing (V10).
- Auth: SYNTHETIC_API_KEY bearer (V10, S14).
- Endpoint/regions: OpenAI https://api.synthetic.new/v1/chat/completions; Anthropic base https://api.synthetic.new/anthropic with the SDK appending /v1 (S14, V10). Regions not read (U).
- Discovery: /models reference is in vendor navigation (V10); live catalog not verified (U).
- Billing: usage-based (V10); per-token rates not read (U).
- Restrictions: syn: aliases auto-resolve to the latest recommended model, and the vendor publishes the resolution map (V10); record the response model rather than the alias.
- Status: active; alias routing is vendor-documented. Evidence: V10, S14.

### 12. Venice
- Type: privacy-focused hosted provider; OpenAI-compatible API (V9, S15).
- Auth: API key via Authorization: Bearer; vapi_ key format per secondary docs (V9, S15).
- Endpoint/regions: https://api.venice.ai/api/v1 per secondary docs (S15); exact base URL not seen in the vendor page read (U14).
- Discovery: models reference in vendor navigation (V9); live catalog not verified (U).
- Billing: API key plans plus X402 crypto balance/top-up/transactions endpoints (V9); plan pricing not read (U).
- Restrictions: "private" open models vs "anonymized" proxy models; anonymized requests still reach the underlying OpenAI/Anthropic/Google/xAI providers (S15). Privacy and billing are first-hop claims.
- Status: active; privacy mode distinction is important for data-handling docs. Evidence: V9, S15, U14.

### 13. Arcee
- Type: vendor API; OpenAI-compatible; Trinity MoE family, Apache 2.0 licensed (S16).
- Auth: ARCEEAI_API_KEY (S16).
- Endpoint/regions: https://api.arcee.ai/api/v1 direct, or via OpenRouter with the OpenRouter key (S16). Vendor docs landing read (V42), region details not read (U).
- Discovery: not verified (U).
- Billing: per-token (S16); rates not read (U).
- Restrictions: small vendor; also reachable through OpenRouter, which adds the gateway-identity caveat (S16, V25).
- Status: active; ecosystem route via OpenRouter matters for support matrix. Evidence: S16, V42.

### 14. Vydra
- Type: media generation API - image, video, speech workflows - not a text-chat provider (V8, S17).
- Auth: VYDRA_API_KEY with vydra_live_ prefix (S17).
- Endpoint/regions: REST base https://vydra.ai/api/v1 (V8); use the www host because the apex host redirects cross-host and some clients drop Authorization on that redirect (S17).
- Discovery: models endpoint listed in vendor navigation (V8); not verified live (U).
- Billing: job/credit based (U).
- Restrictions: no Chat Completions surface was observed; do not list Vydra in the text-model inventory (V8, S17).
- Status: active, media-only. Evidence: V8, S17.

### 15. GMI Cloud
- Type: hosted inference platform (GPU cloud + serverless inference); OpenAI-compatible (V7).
- Auth: GMI_API_KEY via Authorization: Bearer; X-Organization-ID header for multi-organization access (V7).
- Endpoint/regions: https://api.gmi-serving.com/v1; GET /v1/models (V7). Regions not read (U).
- Discovery: GET /v1/models returns available models with capabilities and ownership (V7).
- Billing: per-token/platform (S18); rates not read (U).
- Restrictions: one key can reach multiple vendors' models, so model identity must be recorded from the response (V7, S18).
- Status: active; endpoint/auth vendor-documented. Evidence: V7, S18.

### 16. Amazon Bedrock
- Type: enterprise cloud managed inference; two endpoints: bedrock-runtime (recommended for new apps) and bedrock-mantle (compatibility) (V17).
- Auth: AWS SigV4 via the AWS SDK default credential chain; additionally Bedrock API keys (short-term <= 12 h inheriting IAM permissions, long-term creating an IAM user, exploration only) sent in the authorization header; calls logged in CloudTrail, keys not logged (V16, S19).
- Endpoint/regions: https://bedrock-runtime.{region}.amazonaws.com with InvokeModel/Converse/Chat Completions/Responses/Messages; OpenAI-compatible path prefix /openai/v1; regional endpoints (V17, V18).
- Discovery: ListFoundationModels and ListInferenceProfiles; the OpenAI-compatible Chat Completions surface is not the discovery contract (V18).
- Billing: AWS account, per model/unit (V16, S19); allocation tags not read (U).
- Restrictions: model access must be granted in the region; runtime model or inference-profile ID differs from the base model ID (V18); SigV4 cannot be replaced by a pasted API key for the official API (V16, S19).
- Status: active; documentation-observed only. Evidence: V16, V17, V18, S19.

### 17. Amazon Bedrock Mantle
- Type: Bedrock compatibility endpoint for Mantle-only capabilities: server-side/preconfigured tools (including web search), background inference, Projects, Workspaces; OpenAI-compatible Chat/Responses plus Anthropic Messages routes (V17, V18).
- Auth: Bearer token documented, for example OPENAI_API_KEY plus OPENAI_BASE_URL with a Bedrock API key; IAM credential-chain bearer generation is described in secondary docs (V18, S20). SigV4 acceptance on Mantle was not verified (U9).
- Endpoint/regions: https://bedrock-mantle.{region}.api.aws/v1; some models are served under /openai/v1 instead of /v1 and a wrong prefix is rejected with a route error (V18).
- Discovery: GET /models or client.models.list(); bedrock-runtime uses ListFoundationModels/ListInferenceProfiles instead (V18).
- Billing: AWS account (S20, V16); per-call detail not read (U).
- Restrictions: this is a compatibility endpoint, not the default; AWS recommends bedrock-runtime for new applications and documents migration from Mantle (V18).
- Status: active compatibility endpoint. Evidence: V17, V18, S20.

### 18. Anthropic Vertex (Claude Models on Google Cloud, Google managed)
- Type: enterprise cloud route to Claude on Vertex AI; not the Anthropic API host (V19).
- Auth: Google OAuth2 access token (gcloud auth print-access-token) for cURL; AnthropicVertex SDKs use Google authentication / ADC; caller needs aiplatform.endpoints.predict, for example roles/aiplatform.user (V19, V47).
- Endpoint/regions: https://aiplatform.googleapis.com/v1/projects/{project}/locations/{region}/publishers/anthropic/models/{model}:rawPredict with anthropic_version vertex-2023-10-16; global, multi-region and regional endpoint types (V19).
- Discovery: Vertex Model Garden; no Anthropic Models API on this path (S, U detail).
- Billing: Google Cloud billing; the Anthropic Console is a separate billing relationship (U detail; not read directly).
- Restrictions: project, region and IAM permission required; an Anthropic API key does not authenticate this endpoint (V19).
- Status: active; documentation-observed. Evidence: V19, V47.

### 19. Cloudflare AI Gateway
- Type: gateway in front of provider APIs with analytics, caching, rate limiting, retries, model fallback, dynamic routing and provider-native endpoints (V29).
- Auth: Cloudflare API token for the gateway plus the provider's own key stored as a Stored Key (BYOK); provider-native routes use the provider key (V30).
- Endpoint/regions: unified OpenAI-compatible path https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/compat, now deprecated for single-model calls; the replacement is the REST API under https://api.cloudflare.com/client/...; provider-native endpoints also exist; Cloudflare edge regions apply (V30, V29).
- Discovery: model catalog under AI models (V29); exact discovery endpoint not read (U7).
- Billing: BYOK means the provider bills the user directly; the gateway feature set is available on all plans (V29, V30). No Cloudflare-credit inference billing was found in these pages (U11).
- Restrictions: unified /compat deprecation for standard single-model chat (V30); dynamic routing can change the selected provider, but fallback and billing behavior details were not read (U7).
- Status: active, API changing. Evidence: V29, V30, S21, U7.

### 20. Vercel AI Gateway
- Type: managed unified gateway; Anthropic Messages-compatible client surface, AI SDK and REST/OpenAI-style APIs; model IDs namespaced like provider/model (S22, V31).
- Auth: AI_GATEWAY_API_KEY; OIDC for Vercel deployments; optional BYOK provider keys (V31, V32).
- Endpoint/regions: https://ai-gateway.vercel.sh (S22); /v1/models auto-discovery with the gateway key (S22). Regions not read (U).
- Discovery: GET /v1/models on the gateway (S22).
- Billing: AI Gateway Credits, zero markup and no platform fee on tokens, free tier limited to a model subset; BYOK provider-billed, but failed BYOK requests fall back to system credentials and can bill credits (V31, V32, V34).
- Restrictions: provider restriction does not disable key-to-system-credential fallback; ZDR constrains fallback; routing metadata exposes final provider and credential type, so clients must record it (V32, V33).
- Status: active; this is the best-documented example of payer ambiguity. Evidence: V31, V32, V33, V34, S22.

### 21. OpenRouter
- Type: unified router/marketplace over many models and providers; OpenAI-compatible Chat Completions, Anthropic Messages and Responses surfaces (V25, R1).
- Auth: OPENROUTER_API_KEY bearer; browser sign-in is also supported by some clients (R2, S23).
- Endpoint/regions: https://openrouter.ai/api/v1 (R2, R1); global routing with provider preferences (V26).
- Discovery: authenticated /models catalog; repo loads 40 most-popular text models on demand and sends q-filtered searches (R1, V26).
- Billing: prepaid credits; priced on the model ultimately used; usage accounting returns token counts and cost in credits (V25, V27); marketplace fee not read (U10).
- Restrictions: provider.order, allow_fallbacks (default true), data_collection, zdr, sort, max_price; a :free model followed by paid fallback bills paid (V25, V26); the deprecated usage.include parameter is still sent by the repo adapter (R1, V27).
- Status: active; identity and payer behavior are explicitly documented. Evidence: V25, V26, V27, R1, S23.

### 22. ClawRouter
- Type: managed multi-provider router; one policy-scoped key; upstream credentials and forwarding stay inside ClawRouter (S24).
- Auth: CLAWROUTER_API_KEY issued by an administrator, revealed once (S24).
- Endpoint/regions: default https://clawrouter.openclaw.ai; custom deployment origin allowed (S24). Regions not read (U).
- Discovery: credential-scoped /v1/catalog returns only models allowed for that key (S24).
- Billing: monthly budget and aggregate usage via /v1/usage; who invoices upstream and at what price is not documented in the page read (S24, U12).
- Restrictions: model refs retain upstream namespace, and each model is routed through its declared protocol; only granted models are visible (S24).
- Status: active in OpenClaw, bundled plugin enabled by default; no independent public API docs were found (U12), so this is secondary-only. Evidence: S24, U12.

### 23. LiteLLM
- Type: open-source self-hosted LLM gateway; unified API over 100+ providers; cost tracking, logging, virtual keys with spend limits, backend failover (V28, S25).
- Auth: proxy master key starting with sk- plus virtual keys; Postgres required for key management (V28).
- Endpoint/regions: operator-hosted; default http://localhost:4000; OpenAI-compatible /v1/models and /chat/completions (S25).
- Discovery: /v1/models returns configured model_name aliases; an alias can map to a different upstream model (V28).
- Billing: gateway records spend per key, user, team and end-user via /key/info, /user/info, /team/info, /end_user/info; the actual invoice stays with the upstream accounts the operator configured (V28).
- Restrictions: model identity is operator-defined; routing/failover can change backend; gateway trust and SSRF protection are the operator's responsibility; license and commercial terms not read (U13).
- Status: active, widely deployed; identity is truthful only with disciplined aliasing. Evidence: V28, S25.

### 24. Microsoft Foundry
- Type: enterprise cloud model catalog plus deployments; unified RBAC/networking/policies; OpenAI-compatible v1 route (V20, V21).
- Auth: API key bearer (full resource access) or keyless Microsoft Entra ID with RBAC (recommended for production) (V20, V21).
- Endpoint/regions: https://{resource}.openai.azure.com/openai/v1/ or https://{resource}.services.ai.azure.com/openai/v1; deployment name goes in the model field; /openai/v1 uses implicit versioning (V20). Azure resource region applies (U detail).
- Discovery: deployments are the access unit, not a plain model ID list; a Foundry resource can have many deployments (V20).
- Billing: Azure subscription; only inference on model deployments is billed (V20); per-deployment cost visibility not read (U).
- Restrictions: deployment aliasing means model values are resource-local; API keys are full-resource and hard to scope (V20); Entra ID role assignment required for keyless (V21).
- Status: active. Evidence: V20, V21.

### 25. Groq
- Type: inference provider on LPU hardware; OpenAI-compatible (V4).
- Auth: GROQ_API_KEY (S26).
- Endpoint/regions: https://api.groq.com/openai/v1 (V4). Regions not read (U).
- Discovery: not verified (U).
- Billing: per-token (S26); rates not read (U).
- Restrictions: vendor docs list text generation, speech to text, TTS, tool use, structured outputs, prompt caching; model catalog is Groq-specific (V4, S26).
- Status: active; base URL vendor-documented. Evidence: V4, S26.

### 26. Cerebras
- Type: inference provider on wafer-scale hardware; OpenAI-compatible (V5).
- Auth: CEREBRAS_API_KEY (S27).
- Endpoint/regions: https://api.cerebras.ai/v1/chat/completions (V5). Regions not read (U).
- Discovery: native model metadata and pricing discovery reported by secondary docs (S27); not vendor-verified here (U).
- Billing: per-token (S27); rates not read (U).
- Restrictions: catalog is Cerebras-hosted; capability coverage not verified (U).
- Status: active; base URL vendor-documented. Evidence: V5, S27.

### 27. Together AI
- Type: serving platform for open models; OpenAI-compatible (S28).
- Auth: TOGETHER_API_KEY (S28).
- Endpoint/regions: https://api.together.xyz/v1 (S28). Regions not read (U).
- Discovery: not verified (U).
- Billing: per-token or dedicated capacity (S28); rates not read (U).
- Restrictions: vendor docs page read was navigation-only; endpoint and catalog are secondary (V46).
- Status: active; secondary-only for endpoint values. Evidence: S28, V46.

### 28. Fireworks
- Type: serving platform with OpenAI-compatible and Anthropic-compatible APIs; routers and fine-tuning (V6, S29).
- Auth: FIREWORKS_API_KEY (S29).
- Endpoint/regions: https://api.fireworks.ai/inference/v1 (V6). Regions not read (U).
- Discovery: not verified (U); router IDs such as Fire Pass are part of the model namespace (S29).
- Billing: per-token or deployed capacity (S29); rates not read (U).
- Restrictions: router IDs can resolve to an upstream model, so record the response model; Anthropic compatibility exists on a separate path (V6).
- Status: active; base URL vendor-documented. Evidence: V6, S29.

### 29. NVIDIA (NIM / build.nvidia.com)
- Type: hosted inference API plus self-hosted NIM (V41, S30).
- Auth: NVIDIA_API_KEY, nvapi- format (S30).
- Endpoint/regions: https://integrate.api.nvidia.com/v1 (S30). Regions not read (U).
- Discovery: not verified (U).
- Billing: secondary docs describe free hosted access (S30); NVIDIA pricing/terms were not read, so any "free" claim stays unverified (U11). Self-hosted NIM licensing is separate (U).
- Restrictions: hosted tier is likely rate-limited and promotional; do not treat it as a paid-contract route without vendor terms (S30, U11).
- Status: active; endpoint/auth secondary-only. Evidence: V41, S30, U11.

### 30. Hugging Face Inference Providers
- Type: inference router in front of multiple hosted providers; OpenAI-compatible chat completions (S31).
- Auth: HUGGINGFACE_HUB_TOKEN or HF_TOKEN, fine-grained with "Make calls to Inference Providers" permission (S31).
- Endpoint/regions: https://router.huggingface.co/v1 (S31). Regions not read (U).
- Discovery: not verified (U).
- Billing: single HF token; pricing follows provider rates with a free tier (S31); per-request attribution not read (U).
- Restrictions: chat-completions surface only for text; image, embeddings and speech use HF inference clients/endpoints directly (S31). Router chooses upstream provider, so payer/processor are split (S31).
- Status: active; secondary-only for endpoint. Evidence: V45, S31.

### 31. DeepInfra
- Type: serving platform for open and frontier models; OpenAI-compatible (S32).
- Auth: DEEPINFRA_API_KEY (S32).
- Endpoint/regions: https://api.deepinfra.com/v1/openai (S32). Regions not read (U).
- Discovery: live model catalog with filters per secondary docs (S32); not verified (U).
- Billing: per-token (S32); rates not read (U).
- Restrictions: secondary docs note live discovery expands selectable models but defaults are static (S32).
- Status: active; vendor docs landing read (V43). Evidence: V43, S32.

### 32. Chutes
- Type: decentralized inference on Bittensor Subnet 64; OpenAI-compatible (V44, S33).
- Auth: OAuth browser flow or API key; CHUTES_API_KEY / CHUTES_OAUTH_TOKEN (S33).
- Endpoint/regions: https://llm.chutes.ai/v1 (S33). Regions not read (U).
- Discovery: not verified (U).
- Billing: OAuth/subscription/credits (U; not documented in the page read).
- Restrictions: OAuth tokens auto-refresh through client auth profiles (S33); decentralized operator model adds availability variance (S33, U).
- Status: active; endpoint/auth secondary-only. Evidence: V44, S33.

### 33. NovitaAI
- Type: hosted AI infrastructure provider; OpenAI-compatible (S34).
- Auth: NOVITA_API_KEY (S34).
- Endpoint/regions: https://api.novita.ai/openai/v1 (S34). Regions not read (U).
- Discovery: model catalog per secondary docs (S34); not verified (U).
- Billing: per-token (S34); rates not read (U).
- Restrictions: secondary docs note chat requests use system messages and max_tokens even for reasoning models (S34).
- Status: active; secondary-only. Evidence: S34.

### 34. Kilocode / Kilo Gateway
- Type: unified gateway behind Kilo Code; OpenAI-compatible, plus FIM completions (V11, S35).
- Auth: KILOCODE_API_KEY (S35).
- Endpoint/regions: https://api.kilo.ai/api/gateway (V11). Regions not read (U).
- Discovery: model list via gateway (S35); not verified (U).
- Billing: Kilo credits/plan (U; not read).
- Restrictions: model IDs are namespaced by upstream vendor, for example anthropic/claude-sonnet-4.5 (V11); gateway route identity caveat applies.
- Status: active; base URL vendor-repo-documented. Evidence: V11, S35.

### 35. BytePlus (ModelArk)
- Type: enterprise cloud (ByteDance) ModelArk; international sibling of Volcengine ARK (S10).
- Auth: BYTEPLUS_API_KEY (S10).
- Endpoint/regions: UNVERIFIED. Vendor docs are JavaScript shells in this session (U1); a region-availability page exists but content could not be read. Do not publish a base URL in docs 00-07 without a readable vendor source.
- Discovery: UNVERIFIED (U1).
- Billing: per-token cloud account (S10, U details).
- Restrictions: same-models claim relative to Volcengine is secondary (S10); endpoint semantics may mirror ARK but that is not verification.
- Status: product active; route not documentable. Evidence: S10, U1.

### 36. Ollama Cloud
- Type: hosted Ollama API, native and OpenAI-compatible; also Anthropic-compatible /v1/messages; no local install required (V14, V15).
- Auth: OLLAMA_API_KEY via Authorization: Bearer; x-api-key alone is not supported on the hosted Anthropic-compatible endpoint (V15).
- Endpoint/regions: https://ollama.com/api/chat (native), https://ollama.com/v1 (OpenAI), /v1/messages (Anthropic) (V14, V15). Regions not read (U).
- Discovery: not verified (U).
- Billing: Ollama plan for cloud usage (U details not read).
- Restrictions: direct cloud and local-daemon cloud traffic are different paths; the model catalog is the Ollama library (V14).
- Status: active; endpoint/auth vendor-documented. Evidence: V14, V15, S37.

### 37. Ollama (local)
- Type: local inference runtime/server (V15, S36).
- Auth: none on the default loopback API (V15); OLLAMA_HOST can relocate it (R1).
- Endpoint/regions: http://localhost:11434 native /api/chat; OpenAI-compatible /v1 exists (V15, S36).
- Discovery: /api/tags lists installed models (S36); cloud-tagged models need a signed-in cloud session (V15).
- Billing: no charge for local models; cloud models are billed to the Ollama account (V15).
- Restrictions: native API is required for num_ctx and reliable tool calls; /v1 cannot set context and can silently truncate (R1, R8, S36); repo classifies cloud-tagged model names as hosted (R1).
- Status: active; the reference local route for Hutch. Evidence: V15, S36, R1, R8.

### 38. LM Studio
- Type: local inference app/server (GGUF or MLX) with a headless daemon option (S38, V13).
- Auth: no auth by default; optional API tokens since LM Studio 0.4.0 (V13).
- Endpoint/regions: http://127.0.0.1:1234 by default; OpenAI-compatible /v1 and native /api/v1/models (S38).
- Discovery: /api/v1/models; tool-training and effective-context checks can gate model selection (S38).
- Billing: none local (V13).
- Restrictions: local only; loaded-instance context overrides advertised maximum (S38).
- Status: active; auth vendor-documented. Evidence: V13, S38.

### 39. vLLM
- Type: self-hosted high-throughput serving engine; OpenAI-compatible server (V40, S39).
- Auth: optional server API key; secondary docs say any non-empty value works when the server enforces none (S39).
- Endpoint/regions: default http://127.0.0.1:8000/v1; /v1/models and /v1/chat/completions (S39, V40).
- Discovery: /v1/models (S39).
- Billing: none self-hosted; operator pays hardware/cloud (S39).
- Restrictions: exact auth flags and version-specific behavior not extracted from the rendered vendor page (U5); operator owns SSRF, key storage and upgrades.
- Status: active; vendor docs page exists, details mostly secondary. Evidence: V40, S39, U5.

### 40. SGLang
- Type: self-hosted serving engine; OpenAI-compatible APIs, Anthropic-compatible /v1/messages, and Ollama-compatible API (V39, S40).
- Auth: optional server API key; any non-empty value when the server enforces none (S40).
- Endpoint/regions: default http://127.0.0.1:30000/v1 (S40).
- Discovery: /v1/models (S40).
- Billing: none self-hosted (S40).
- Restrictions: no auth by default in the integration pattern; server args control the listener; exact flags not read (U6).
- Status: active; broad API compatibility is vendor-documented. Evidence: V39, S40, U6.

### 41. inferrs / llmman
- Type: local plus hybrid inference daemon. Pulls models as OCI artifacts from any registry or Hugging Face and serves them through llama-server (GGUF), vLLM or MLX (safetensors); exposes Ollama-, OpenAI- and Anthropic-compatible APIs and can forward to hosted providers (V37, S41).
- Auth: no key on loopback; off loopback requires LLMMAN_API_KEYS (or auth.api_keys), and TLS is optional via LLMMAN_TLS_CERT/KEY; LLMMAN_AUTH=off is only for trusted networks (V37).
- Endpoint/regions: default http://127.0.0.1:17434/v1; hybrid refs such as llmman.hybrid/local,provider/model choose local or hosted per request (V37, S41).
- Discovery: explicit model refs; integration docs list models rather than relying on a bundled plugin catalog (S41).
- Billing: no gateway fee; local is self-hosted, hosted side billed by the upstream provider (V37).
- Restrictions: hybrid routing can silently egress a request that looks local; record which side served and classify the route accordingly (S41, V37). The name "inferrs" appears in the request index but the page is now titled llmman, so the old name may be stale (U naming).
- Status: active; README is vendor/project primary. Evidence: V37, S41.

### 42. ds4
- Type: local DeepSeek V4 Flash server on macOS Metal; OpenAI-compatible /v1 API; also an agent CLI that runs inference without an HTTP server (V38, S42).
- Auth: no auth documented in the README read; loopback binding (V38).
- Endpoint/regions: server listens at http://127.0.0.1:8000 by default (V38); OpenAI-style /v1 and Anthropic endpoints are described by project docs/secondary (S42).
- Discovery: not verified (U); model is a specific DeepSeek V4 Flash GGUF (S42).
- Billing: none local.
- Restrictions: macOS with Metal only; context allocation grows with --ctx; too-small context fails full agent runs (S42). Secondary docs suggest a different example port (18000), so port must be configured, not assumed (S42, V38).
- Status: active; niche macOS-only runtime. Evidence: V38, S42.

### 43. llama.cpp server
- Type: local GGUF inference server with an OpenAI-compatible API and multimodal/reranking support (V12).
- Auth: optional --api-key KEY or LLAMA_API_KEY; multiple keys can be comma-separated; --api-key-file supported; default is no authentication (V12).
- Endpoint/regions: operator-defined listener; OpenAI-compatible endpoints (V12).
- Discovery: /v1/models (S43).
- Billing: none local.
- Restrictions: server must be launched with a context large enough for agent prompts; no built-in multi-tenant auth beyond API keys; TLS optional via cert files (V12).
- Status: active; --api-key vendor-documented. Evidence: V12, S43.

### 44. Custom compatible endpoints
- Type: compatible endpoint (self-hosted vLLM/SGLang/LM Studio/llama.cpp, a company gateway, or any HTTP service exposing a compatible API) (R1, R2).
- Auth: connection-owned key from an environment variable or a 0600 file under the state dir; the ambient OPENAI_API_KEY is never sent to a non-official host; HUTCH_API_KEY is the explicit custom-endpoint key (R2, R3).
- Endpoint/regions: operator-defined HTTP(S) base URL; a custom Anthropic connection uses the root without /v1/messages (R2).
- Discovery: a model-list request is sent when the endpoint provides one (R1).
- Billing: the operator's upstream account; OpenRouter billed usage is retained when reported; generic endpoint omissions are not treated as zero (R1).
- Restrictions: URLs with embedded credentials are rejected; ambient keys are exact-host-only; Strict Offline mode enforces loopback-only plain HTTP endpoints with no userinfo/query and a numeric loopback address (R3, R4). Outside Strict Offline there is no private-range allowlist in the provider layer that was read, so the endpoint host is an explicit trust decision; this is the SSRF-shaped review item (R3, R4).
- Status: supported; governed by repo rules, not live-tested against arbitrary servers. Evidence: R1, R2, R3, R4.

## Blocked, retired and unsupported routes

- Consumer OAuth/session reuse: blocked by Hutch policy. Hutch does not read or proxy consumer-app cookies/session tokens, including GitHub Copilot subscription tokens and ChatGPT/Claude consumer sessions (R1, R6). The only GitHub-documented programmatic path found is the official Copilot SDK, not raw token reuse (V35, V36).
- GitHub Copilot as a raw OpenAI-compatible provider: no public vendor-documented base URL or BYO-key contract was found; the account-specific endpoint is client-internal. A single third-party issue title claims generic OpenAI compatibility violates GitHub's terms (A1); unread and unreproduced, so it is not a policy citation. Classify as unsupported/experimental for Hutch.
- Cloudflare unified /compat API: deprecated for standard single-model chat completions; new integrations should use the REST API or provider-native endpoints (V30). Existing code that hard-codes /compat is on a deprecated surface.
- Alibaba old dashscope hosts: https://dashscope.aliyuncs.com, https://dashscope-intl.aliyuncs.com and https://cn-hongkong.dashscope.aliyuncs.com are migration sources, not the current recommended base; the vendor instructs moving to workspace-scoped maas.aliyuncs.com hosts (V22). Cutoff date not read (U).
- Bedrock Mantle as default: AWS calls bedrock-runtime the recommended endpoint and documents Mantle migration; Mantle remains for Mantle-only features (V18). Wrong path prefix (/v1 vs /openai/v1) is rejected per model route (V18).
- Vercel BYOK-to-system fallback: not a blocked route, but a billing attribution hazard. A failed BYOK request may be retried with system credentials and billed to Vercel credits; provider restriction does not stop that fallback (V32). If Hutch relies on the user's key to control who pays, the gateway route cannot guarantee it.
- OpenRouter :free -> paid fallback: a models list containing a free model followed by a paid model bills the paid price when fallback happens; only a list of free models keeps the request free (V25).
- Vydra: media-only API (image, video, speech workflows); no Chat Completions route was observed, so it must not appear as a text-model provider (V8, S17).
- BytePlus ModelArk: product active, but vendor docs rendered as JavaScript shells in this session; endpoint, discovery and rate-limit terms stay UNVERIFIED (U1, S10). Do not ship a template until a readable vendor source is confirmed.
- Xiaomi Token Plan: vendor page is a JavaScript shell; plan terms, allowance and whether unattended agent use is covered are UNVERIFIED; repo already warns the plan is documented for coding tools and keys must not be shared (U2, R2). Treat as experimental subscription route.
- StepFun Step Plan: separate provider, endpoints and model prefixes from the standard stepfun route; plan availability differs by model (S8). Vendor pages were not machine-readable in this session (U3). Treat endpoint strings as secondary until verified.
- Qianfan Coding Plan: vendor navigation shows Coding Plan stopped and migration to Token Plan (U4). Legacy Coding Plan routes should be treated as retired/migrating; Token Plan personal/enterprise variants are the current paths.
- Ollama OpenAI-compatible local /v1 as the primary local route: unsupported for context control and tool-call reliability; use native /api/chat with explicit num_ctx (R1, R8, S36).
- Hugging Face chat-completions router as a general provider: text chat only; embeddings/image/speech require other HF surfaces (S31).
- Foundry global model IDs: the inference route's model field is a deployment name; a vendor-global model ID is not a portable route key (V20).
- LiteLLM alias IDs as vendor identities: model_name is an operator alias and can map to a different upstream model (V28); treating a gateway catalog name as a vendor model ID is unsupported.
- OpenRouter routing controls on non-OpenRouter routes: Hutch rejects OpenRouter policy fields for other providers (R5); a generic OpenAI-compatible connection cannot be assumed to honor provider.order/zdr.
- NVIDIA hosted "free" access: claim is from secondary integration docs (S30); vendor pricing/terms were not read, so do not promise free capacity (U11).
- ds4 on Linux/Windows: project is macOS Metal only (V38, S42), so it cannot be a portable local default.
- Cloudflare dynamic routing: feature listed (V29) but fallback and billing semantics were not read (U7); do not document it as a deterministic fallback chain.
- inferrs naming: the request name "inferrs" maps to a page now titled llmman; whether the product was renamed, or inferrs is a separate historical project, was not established (U naming). Use llmman as the current name and mark inferrs as an alias of uncertain status.

## Failed or partial fetches (what remains UNVERIFIED)

- https://docs.byteplus.com/en/docs/ModelArk/region-availability - 200 but JavaScript shell; no endpoint text. BytePlus base URL, discovery and billing stay UNVERIFIED.
- https://mimo.mi.com/docs/en-US/tokenplan/subscription - 200 but a JavaScript app shell ("Xiaomi MiMo Home"); Token Plan terms and quotas UNVERIFIED.
- https://platform.stepfun.com/docs/zh/guide/quick-start - 404; other StepFun docs URLs appear in search results but were not fetched. StepFun endpoints are secondary-only.
- https://cloud.baidu.com/doc/qianfan/s/Hmh4suq26 - 200 but rendered navigation only; Qianfan endpoint is secondary-only.
- https://docs.vllm.ai/en/latest/serving/openai_compatible_server.md and the stable .md variant - 404. The rendered https://docs.vllm.ai page was fetched but endpoint/auth text was not machine-extracted; vLLM values are secondary.
- https://docs.sglang.io/backend/openai_api_completions.md - 404; SGLang values are secondary, but the official llms.txt index confirms OpenAI/Anthropic/Ollama-compatible API pages exist (V39).
- Cloudflare dynamic routing page was listed but not read; dynamic fallback/billing semantics UNVERIFIED.
- GitHub Copilot acceptable-use/terms page was not found in this session; only the SDK docs and announcement were read. Policy claims about Copilot token use stay unverified except Hutch's own block on consumer session reuse.
- Bedrock Mantle SigV4 acceptance UNVERIFIED; only the bearer/OpenAI-SDK path was read.
- OpenRouter marketplace/platform fee, NVIDIA hosted pricing terms, LiteLLM license/commercial terms, Venice exact base URL and per-model pricing were not read.
- No live provider account, key, inference request, model-list request or billing exercise was performed. No provider was tested from Hutch in this session.

## Sources and verification dates

All rows were read or fetched on 2026-10-30 unless noted. Class codes: V vendor-documented, S secondary integration docs, R repo evidence, U UNVERIFIED/partial, A anecdote.

| ID | Source | Class | Fetched | What it supports |
|---|---|---|---|---|
| V1 | https://docs.mistral.ai/resources/migration-guides | V | 2026-10-30 | Mistral base URL https://api.mistral.ai/v1 and OpenAI-compatible shape |
| V2 | https://api-docs.deepseek.com/ | V | 2026-10-30 | DeepSeek base URLs, bearer keys, model-name re-pointing |
| V3 | https://docs.cohere.com/docs/compatibility-api | V | 2026-10-30 | Cohere Compatibility API base URL |
| V4 | https://console.groq.com/docs/openai | V | 2026-10-30 | Groq OpenAI-compatible base URL and capability nav |
| V5 | https://inference-docs.cerebras.ai/introduction.md | V | 2026-10-30 | Cerebras endpoint https://api.cerebras.ai/v1/chat/completions |
| V6 | https://docs.fireworks.ai/tools-sdks/openai-compatibility.md | V | 2026-10-30 | Fireworks base URL and OpenAI/Anthropic compatibility |
| V7 | https://docs.gmicloud.ai/inference-engine/api-reference/llm-api-reference | V | 2026-10-30 | GMI endpoints, Bearer auth, organization header, /v1/models |
| V8 | https://www.vydra.ai/docs | V | 2026-10-30 | Vydra REST base URL and media-only workflow scope |
| V9 | https://docs.venice.ai/api-reference/api-spec | V | 2026-10-30 | Venice Bearer auth, OpenAI compatibility, X402 billing nav |
| V10 | https://dev.synthetic.new/docs/api/overview | V | 2026-10-30 | Synthetic OpenAI/Anthropic endpoints, syn: alias routing, usage-based pricing |
| V11 | https://raw.githubusercontent.com/Kilo-Org/kilocode/ff74e2ea/packages/kilo-docs/pages/gateway/api-reference.md | V | 2026-10-30 | Kilo Gateway base URL and OpenAI-compatible request shape |
| V12 | https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md | V | 2026-10-30 | llama.cpp --api-key, env key, OpenAI-compatible server |
| V13 | https://lmstudio.ai/docs/developer/core/authentication | V | 2026-10-30 | LM Studio optional API tokens, default no auth |
| V14 | https://docs.ollama.com/cloud.md | V | 2026-10-30 | Ollama Cloud API key, direct cloud endpoints, no local install |
| V15 | https://docs.ollama.com/api/authentication.md | V | 2026-10-30 | Local Ollama no auth; cloud Bearer key; hosted /v1/messages Bearer-only |
| V16 | https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys.html | V | 2026-10-30 | Bedrock API key types, expiry, IAM inheritance, CloudTrail |
| V17 | https://docs.aws.amazon.com/bedrock/latest/userguide/endpoints.html | V | 2026-10-30 | bedrock-runtime vs bedrock-mantle feature/API split |
| V18 | https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-mantle.html | V | 2026-10-30 | Mantle base URL, model discovery, path-prefix rule, migration guidance |
| V19 | https://platform.claude.com/docs/en/api/claude-on-vertex-ai.md | V | 2026-10-30 | Vertex Claude endpoint, gcloud token/ADC, IAM role, anthropic_version |
| V20 | https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/endpoints | V | 2026-10-30 | Foundry base URL forms, deployment model field, API key/Entra auth |
| V21 | https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/configure-entra-id | V | 2026-10-30 | Foundry keyless Entra ID auth and RBAC |
| V22 | https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope | V | 2026-10-30 | Model Studio workspace-scoped base URLs, regions, key-region binding |
| V23 | https://ark.volcengine.com/region:cn-beijing/docs/base-url-and-authentication.md | V | 2026-10-30 | Volcengine data/control-plane URLs, API key and Access Key auth |
| V24 | https://cloud.tencent.cn/document/product/1823/130078 | V | 2026-10-30 | TokenHub hosts, Bearer auth, /v1/models, no cross-region calls |
| V25 | https://openrouter.ai/docs/guides/routing/model-fallbacks.md | V | 2026-10-30 | Fallback triggers, final-model billing, response model identity, free/paid fallback |
| V26 | https://openrouter.ai/docs/guides/routing/provider-selection.md | V | 2026-10-30 | provider.order/allow_fallbacks/data_collection/zdr/sort/max_price |
| V27 | https://openrouter.ai/docs/cookbook/administration/usage-accounting.md | V | 2026-10-30 | Usage accounting cost in credits; deprecated usage.include/stream_options |
| V28 | https://docs.litellm.ai/docs/proxy/virtual_keys.md | V | 2026-10-30 | Virtual keys, Postgres, master key, spend per key/user/team, alias example |
| V29 | https://developers.cloudflare.com/ai-gateway/index.md | V | 2026-10-30 | AI Gateway features, all plans, dynamic routing listed |
| V30 | https://developers.cloudflare.com/ai-gateway/usage/chat-completion/index.md | V | 2026-10-30 | Unified /compat deprecation, REST replacement, BYOK stored key |
| V31 | https://vercel.com/docs/ai-gateway.md | V | 2026-10-30 | Zero markup, credits, BYOK, budgets, any-infrastructure use |
| V32 | https://vercel.com/docs/ai-gateway/authentication-and-byok/byok.md | V | 2026-10-30 | BYOK fallback to system credentials, logs, provider restriction caveat |
| V33 | https://vercel.com/docs/ai-gateway/models-and-providers/provider-filtering-and-ordering.md | V | 2026-10-30 | Routing/settlement metadata including final provider and credential type |
| V34 | https://vercel.com/docs/ai-gateway/pricing.md | V | 2026-10-30 | Credits, free-tier subset, zero markup, BYOK pricing |
| V35 | https://raw.githubusercontent.com/github/copilot-sdk/ec854d90371a4e87de06489ba979c4c923dda64c/docs/index.md | V | 2026-10-30 | Official Copilot SDK docs and auth entry points |
| V36 | https://github.blog/news-insights/product-news/build-an-agent-into-any-app-with-the-github-copilot-sdk/ | V | 2026-10-30 | GitHub announcement of the Copilot SDK |
| V37 | https://raw.githubusercontent.com/llmmanorg/llmman/main/README.md | V | 2026-10-30 | llmman local/hybrid scope, auth rules, compatible APIs, default port |
| V38 | https://raw.githubusercontent.com/antirez/ds4/main/README.md | V | 2026-10-30 | ds4 local server, macOS Metal, default 127.0.0.1:8000 |
| V39 | https://docs.sglang.io/llms.txt | V | 2026-10-30 | SGLang OpenAI/Anthropic/Ollama-compatible API pages exist |
| V40 | https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html | V (partial) | 2026-10-30 | vLLM OpenAI-compatible server exists; text not machine-extracted |
| V41 | https://docs.nvidia.com/nim/ | V (landing) | 2026-10-30 | NVIDIA NIM docs landing; hosted endpoint from secondary |
| V42 | https://docs.arcee.ai/ | V (landing) | 2026-10-30 | Arcee docs landing/quick start |
| V43 | https://docs.deepinfra.com/ | V (landing) | 2026-10-30 | DeepInfra docs landing; endpoint from secondary |
| V44 | https://docs.chutes.ai/ | V (landing) | 2026-10-30 | Chutes docs landing/quick links |
| V45 | https://huggingface.co/docs/inference-providers/index | V (landing) | 2026-10-30 | HF Inference Providers docs landing; endpoint from secondary |
| V46 | https://docs.together.ai/reference/chat-completions | V (partial) | 2026-10-30 | Together docs page rendered navigation only |
| V47 | https://docs.cloud.google.com/docs/authentication/application-default-credentials | V (landing) | 2026-10-30 | Google ADC documentation page exists; details from V19 |
| S1 | https://docs.openclaw.ai/providers.md | S | 2026-10-30 | Provider directory used as the reference index |
| S2 | https://docs.openclaw.ai/providers/mistral.md | S | 2026-10-30 | Mistral base URL, catalog, Voxtral surfaces |
| S3 | https://docs.openclaw.ai/providers/deepseek.md | S | 2026-10-30 | DeepSeek base URL and default model |
| S4 | https://docs.openclaw.ai/providers/github-copilot.md | S | 2026-10-30 | Copilot device login, account-specific endpoint, three integration modes |
| S5 | https://docs.openclaw.ai/providers/alibaba.md | S | 2026-10-30 | Alibaba Model Studio plugin/auth and DashScope host |
| S6 | https://docs.openclaw.ai/providers/qwen.md | S | 2026-10-30 | Qwen Cloud/DashScope standard and coding-plan endpoints |
| S7 | https://docs.openclaw.ai/providers/xiaomi.md | S | 2026-10-30 | Xiaomi pay-as-you-go and Token Plan endpoints/keys |
| S8 | https://docs.openclaw.ai/providers/stepfun.md | S | 2026-10-30 | StepFun standard/Step Plan endpoints and key-region split |
| S9 | https://docs.openclaw.ai/providers/volcengine.md | S | 2026-10-30 | Volcengine provider ids and Default/Plan surfaces |
| S10 | https://docs.openclaw.ai/concepts/model-providers/custom-providers.md | S | 2026-10-30 | BytePlus ARK as international sibling of Volcengine |
| S11 | https://docs.openclaw.ai/providers/tencent.md | S | 2026-10-30 | Tencent TokenHub/TokenPlan ids, keys, base URLs |
| S12 | https://docs.openclaw.ai/providers/qianfan.md | S | 2026-10-30 | Qianfan base URL, key format, default model |
| S13 | https://docs.openclaw.ai/providers/cohere.md | S | 2026-10-30 | Cohere compatibility base URL and static catalog |
| S14 | https://docs.openclaw.ai/providers/synthetic.md | S | 2026-10-30 | Synthetic Anthropic-compatible base URL and defaults |
| S15 | https://docs.openclaw.ai/providers/venice.md | S | 2026-10-30 | Venice OpenAI compatibility, private/anonymized modes, vapi_ keys |
| S16 | https://docs.openclaw.ai/providers/arcee.md | S | 2026-10-30 | Arcee direct and OpenRouter routes, key/endpoint |
| S17 | https://docs.openclaw.ai/providers/vydra.md | S | 2026-10-30 | Vydra media contracts, www host redirect caveat |
| S18 | https://docs.openclaw.ai/providers/gmi.md | S | 2026-10-30 | GMI base URL/key, multi-vendor catalog caveat |
| S19 | https://docs.openclaw.ai/providers/bedrock.md | S | 2026-10-30 | Bedrock Converse stream, AWS SDK credential chain, region |
| S20 | https://docs.openclaw.ai/providers/bedrock-mantle.md | S | 2026-10-30 | Mantle APIs, bearer/IAM-token generation, default region |
| S21 | https://docs.openclaw.ai/providers/cloudflare-ai-gateway.md | S | 2026-10-30 | Cloudflare gateway base URL and provider-key usage |
| S22 | https://docs.openclaw.ai/providers/vercel-ai-gateway.md | S | 2026-10-30 | Vercel base URL, /v1/models discovery, API key |
| S23 | https://docs.openclaw.ai/providers/openrouter.md | S | 2026-10-30 | OpenRouter sign-in/credential and transport behavior |
| S24 | https://docs.openclaw.ai/providers/clawrouter.md | S | 2026-10-30 | ClawRouter key, catalog, usage, upstream credential boundary |
| S25 | https://docs.openclaw.ai/providers/litellm.md | S | 2026-10-30 | LiteLLM proxy onboarding and URL handling |
| S26 | https://docs.openclaw.ai/providers/groq.md | S | 2026-10-30 | Groq base URL/key and audio transcription default |
| S27 | https://docs.openclaw.ai/providers/cerebras.md | S | 2026-10-30 | Cerebras base URL, discovery/pricing note |
| S28 | https://docs.openclaw.ai/providers/together.md | S | 2026-10-30 | Together base URL/key and default model |
| S29 | https://docs.openclaw.ai/providers/fireworks.md | S | 2026-10-30 | Fireworks base URL/key, routers, model names |
| S30 | https://docs.openclaw.ai/providers/nvidia.md | S | 2026-10-30 | NVIDIA base URL, key, free hosted claim |
| S31 | https://docs.openclaw.ai/providers/huggingface.md | S | 2026-10-30 | HF router URL, token permission, billing note, chat-only scope |
| S32 | https://docs.openclaw.ai/providers/deepinfra.md | S | 2026-10-30 | DeepInfra base URL, key, live catalog |
| S33 | https://docs.openclaw.ai/providers/chutes.md | S | 2026-10-30 | Chutes base URL, OAuth/API-key auth, refresh behavior |
| S34 | https://docs.openclaw.ai/providers/novita.md | S | 2026-10-30 | Novita base URL, key, request-shape note |
| S35 | https://docs.openclaw.ai/providers/kilocode.md | S | 2026-10-30 | Kilo Gateway base URL and key |
| S36 | https://docs.openclaw.ai/providers/ollama.md | S | 2026-10-30 | Native /api/chat recommendation, /v1 warning, cloud+local setups |
| S37 | https://docs.openclaw.ai/providers/ollama-cloud.md | S | 2026-10-30 | Ollama Cloud provider separation and defaults |
| S38 | https://docs.openclaw.ai/providers/lmstudio.md | S | 2026-10-30 | LM Studio URL/auth/discovery behavior |
| S39 | https://docs.openclaw.ai/providers/vllm.md | S | 2026-10-30 | vLLM default URL, key pattern, streaming usage |
| S40 | https://docs.openclaw.ai/providers/sglang.md | S | 2026-10-30 | SGLang default URL, key pattern, streaming usage |
| S41 | https://docs.openclaw.ai/providers/inferrs.md | S | 2026-10-30 | llmman/inferrs local+hybrid routing, loopback auth rule |
| S42 | https://docs.openclaw.ai/providers/ds4.md | S | 2026-10-30 | ds4 OpenAI-compatible local server, context warning |
| S43 | https://docs.openclaw.ai/plugins/llama-cpp.md | S | 2026-10-30 | llama.cpp managed/existing server and auth marker |
| R1 | src/hutch/data/compat.json (repo, reviewed 2026-10-10, entries 2026-10-11) | R | 2026-10-30 | Route states, OpenRouter usage.include, Ollama cloud-tag classification, custom connection rules |
| R2 | src/hutch/data/connections.json (repo) | R | 2026-10-30 | Provider templates, Xiaomi Token Plan notice, custom endpoint key envs |
| R3 | src/hutch/providers/registry.py lines 23-61 (repo) | R | 2026-10-30 | Ambient-key exact-host rule, endpoint credential rejection, no embedded userinfo |
| R4 | src/hutch/providers/registry.py lines 156-199 (repo) | R | 2026-10-30 | Strict Offline loopback-only endpoint validation |
| R5 | src/hutch/providers/openai_compat.py lines 56-67 (repo) | R | 2026-10-30 | OpenRouter routing controls rejected on other providers; token-field selection |
| R6 | docs/realignment/provider-compatibility.md (repo) | R | 2026-10-30 | Route states, consumer OAuth block, verification boundary, request-field tests |
| R7 | docs/research/multi-provider-platform-review-2026-10-10.md (repo) | R | 2026-10-30 | OpenRouter fallback identity guidance; no live paid account used |
| R8 | docs/research/offerings-and-failures.md (repo) | R | 2026-10-30 | Ollama 4k context/num_ctx truncation finding |
| A1 | https://github.com/Mintplex-Labs/anything-llm/issues/6075 | A | 2026-10-30 | Search-result title claim that generic OpenAI-style Copilot integration violates TOS; not opened or reproduced |
| U1 | https://docs.byteplus.com/en/docs/ModelArk/region-availability | U | 2026-10-30 | Fetched but JavaScript-only; BytePlus facts unverified |
| U2 | https://mimo.mi.com/docs/en-US/tokenplan/subscription | U | 2026-10-30 | Fetched but JavaScript shell; Xiaomi Token Plan terms unverified |
| U3 | https://platform.stepfun.com/docs/zh/guide/quick-start | U | 2026-10-30 | 404 on guess; StepFun vendor details unverified |
| U4 | https://cloud.baidu.com/doc/qianfan/s/Hmh4suq26 | U | 2026-10-30 | Rendered navigation only; Qianfan endpoint/plan facts secondary |
| U5 | https://docs.vllm.ai/en/latest/serving/openai_compatible_server.md | U | 2026-10-30 | 404; vLLM details secondary |
| U6 | https://docs.sglang.io/backend/openai_api_completions.md | U | 2026-10-30 | 404; SGLang details secondary |
| U7 | https://developers.cloudflare.com/ai-gateway/features/dynamic-routing/ | U | 2026-10-30 | Listed in the AI Gateway index; page not read; fallback/billing semantics unverified |
| U9 | (no URL) Bedrock Mantle SigV4 | U | 2026-10-30 | Bearer path documented; SigV4 acceptance not established |
| U10 | (no URL) OpenRouter marketplace fee | U | 2026-10-30 | Fee not read |
| U11 | (no URL) NVIDIA hosted pricing/terms | U | 2026-10-30 | Free-tier claim from secondary only |
| U12 | (no URL) ClawRouter vendor docs | U | 2026-10-30 | No independent public docs found |
| U13 | (no URL) LiteLLM license/commercial terms | U | 2026-10-30 | Not read |
| U14 | (no URL) Venice exact base URL | U | 2026-10-30 | Base URL from secondary only |
| U15 | (no URL) Mistral regions/pricing | U | 2026-10-30 | Not read |

## Handoff notes for docs 00-07

- Use this fragment as provider-inventory input, not as a support promise. Its status values are documentation classifications; the actual ranking of routes to ship belongs in the scope and rollout docs.
- The highest-risk items to carry forward are: Vercel BYOK-to-system billing fallback (V32), OpenRouter fallback identity/billing (V25), LiteLLM alias identity (V28), Bedrock SigV4 vs API-key difference (V16, S19), Vertex ADC/project/region requirements (V19), Alibaba workspace-scoped endpoint migration (V22), Ollama Cloud vs local classification (V14, V15, R1), and the absence of a generalized custom-endpoint SSRF policy outside Strict Offline (R3, R4).
- Do not cite any endpoint in this fragment as "verified live". If docs 00-07 need a live-verified claim, that requires a separate owned-connection test with a real key, which was out of scope for this session.
- No secrets, keys or account data are included. All credentials are described by variable name only.
