# 05 - Hosted providers and gateways (Phase 4): research, design and result

Date: 2026-11-06. Phase 4 of `docs/realignment/provider-expansion-2026-11/`. Extends `00-GAP-AUDIT.md`
(G11, G18) and `01-FAILURE-MINING.md`; it does not repeat them. A status below is a catalogue
statement, not a support claim: no paid or keyed call was made in this phase (see "Live checks").

## Sources read (all accessed 2026-11-06)

| Source | What it changed |
|---|---|
| https://dev.synthetic.new/docs/api/overview (vendor) | OpenAI base is `https://api.synthetic.new/openai/v1`, Anthropic base is `https://api.synthetic.new/anthropic/v1`. Hutch's template used the undocumented `/v1`. Both answer HTTP 200 on `/models` today, so `/v1` works but is not documented; the template now uses the documented path. Model ids carry an `hf:` or `syn:` prefix as written. Third-party coding tools are listed; no policy sentence either way. |
| https://docs.openclaw.ai/providers/synthetic | OpenClaw sends Anthropic Messages to `https://api.synthetic.new/anthropic` (SDK appends `/v1`). Hutch keeps OpenAI chat as the default protocol and records the Anthropic base for per-model override. |
| https://docs.openclaw.ai/providers/volcengine and https://docs.volcengine.com/docs/ark/coding-plan-personal-ai-other-tools (vendor, translated) | General endpoint `https://ark.cn-beijing.volces.com/api/v3`; Coding Plan endpoint `.../api/coding/v3`. The vendor warns that using `/api/v3` "does not draw from your Coding Plan quota and instead incurs additional charges". The vendor page lists compatible tools (Claude Code, Codex CLI, OpenCode, OpenClaw, Cline, Cursor, Roo Code, Kilo Code and others); Hutch is not listed and no sentence permits or forbids unlisted tools. The plan route therefore stays `documented` (no template). Tool-call API reportedly rejects `minLength`, `maxLength`, `minItems`, `maxItems`, `minContains`, `maxContains` (OpenClaw page; not reproduced live). |
| https://www.tencentcloud.com/document/product/1300/81315 (vendor, via search) | Token Plan: "must not be used via API calls in automated scripts, custom application backends, or any non-interactive batch calling"; violation can suspend the subscription or revoke the key. Hutch bots run unattended, so the Token Plan is `blocked`. Pay-as-you-go TokenHub is separate and unrestricted on that page. |
| https://docs.openclaw.ai/providers/tencent | TokenHub `https://tokenhub.tencentmaas.com/v1`, global `https://tokenhub-intl.tencentmaas.com/v1`; TokenPlan `https://api.lkeap.cloud.tencent.com/plan/v3`; env `TOKENHUB_API_KEY`. Vendor pages spell the host `tencentcloudmaas.com`; both spellings resolve (HTTP 401 unauthenticated). Hutch keeps its existing host and records the ambiguity. |
| https://docs.openclaw.ai/providers/stepfun | `api.stepfun.com` is China, `api.stepfun.ai` is global; Step Plan lives at `/step_plan/v1` on both. Keys should match their region. Plan billing terms not described, so no Step Plan template. |
| https://docs.openclaw.ai/providers/qianfan | `https://qianfan.baidubce.com/v2`, `QIANFAN_API_KEY`, keys start `bce-v3/ALTAK-`, OpenAI-compatible, static catalogue (no live discovery). Unauthenticated `/v2/models` returned 403, so no model list is read. |
| https://docs.openclaw.ai/providers/mistral | Base and env unchanged. Pitfall: reasoning `high` with `temperature: 0` can return HTTP 400. Recorded as a known quirk; not changed in this phase. |
| https://docs.openclaw.ai/providers/cohere , `/arcee` , `/gmi` | Base URLs and env vars match the existing templates. |
| https://vercel.com/docs/ai-gateway/sdks-and-apis/openai-chat-completions (vendor, last updated 2026-10-07) | OpenAI base `https://ai-gateway.vercel.sh/v1`, Bearer key, model id `provider/model`, `GET /models`. Anthropic Messages base is `https://ai-gateway.vercel.sh` (OpenClaw page). |
| https://vercel.com/docs/ai-gateway/authentication-and-byok/byok (vendor, 2026-09-22) | "If a query using your credentials fails, AI Gateway will retry the query with its system credentials", and that fallback "is billed against your credits balance"; BYOK spend is not counted in budgets; a provider restriction "doesn't disable fallback". A client cannot disable this over the OpenAI wire, so the template carries a billing notice. |
| https://developers.cloudflare.com/ai-gateway/usage/chat-completion/ (vendor, updated 2026-11-04) | `/compat/chat/completions` is deprecated for single-model chat; replacement is the account REST API. Base URL contains account and gateway ids; gateway auth uses a second header `cf-aig-authorization`. Cloudflare stays `documented` (see decisions). |
| https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys.html (vendor) | Bedrock API keys: short-term lasts up to 12 hours and is recommended for production; long-term creates an IAM user, "recommended only for exploration", and "works only in the Region you generated it in" (a key from another Region fails with `Credential should be scoped to a valid region`). `AWS_BEARER_TOKEN_BEDROCK` or `Authorization: Bearer` works on Converse and the OpenAI-compatible endpoints. |
| https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-mantle.html (vendor) | Two OpenAI-compatible endpoints: `bedrock-runtime` `https://bedrock-runtime.{region}.amazonaws.com/openai/v1` (no `GET /models`; closed-weight OpenAI models need a system inference profile such as `us.openai.gpt-5.6-sol`) and `bedrock-mantle` `https://bedrock-mantle.{region}.api.aws/v1` (has `/models`; "the path prefix varies by model": a wrong prefix is rejected with "model ... isn't supported on this route"). Responses are stored for 30 days unless `store` is false. |
| https://docs.openclaw.ai/providers/bedrock , `/bedrock-mantle` | Native Bedrock uses the Converse stream API with SigV4 or a bearer token; model ids are `anthropic.claude-...` or inference profiles `us.` `eu.` `ap.` `global.`; Mantle serves Claude through `<mantle-base>/anthropic`. |
| https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle (vendor, 2026-06-05) | v1 API: base `https://RESOURCE.openai.azure.com/openai/v1/` (or `.services.ai.azure.com/openai/v1/`), no `api-version`, `model` is the deployment name. Key auth is the `api-key` header; Entra ID is `Authorization: Bearer` with scope `https://ai.azure.com/.default`. |
| https://docs.openclaw.ai/providers/litellm | Default `http://localhost:4000` (`/v1`), `LITELLM_API_KEY`, model refs are proxy aliases; the proxy owns routing, fallback and spend. A LAN-hosted proxy receives the key, so private-network use is an explicit choice. |
| https://docs.openclaw.ai/providers/clawrouter | Hosted default `https://clawrouter.openclaw.ai`, admin-issued `CLAWROUTER_API_KEY`, credential-scoped model list, budget on `/v1/usage`, "cached inventory is not authorization". |

## Unauthenticated endpoint probes (2026-11-06, no key, no body)

`GET {base_url}/models` for all 49 endpoint rows plus candidate hosts. Evidence of host and path
existence only; it proves nothing about chat, tools or entitlement.

- HTTP 200 without a key (public list): chutes, deepinfra, huggingface, kilocode, novita, nvidia,
  ollama-cloud, openrouter, opencode-go, opencode-zen, synthetic (`/v1` and `/openai/v1`), venice,
  `ai-gateway.vercel.sh/v1`.
- HTTP 401 (host and path exist, key required): arcee, bedrock-mantle (`us-east-1`), both BytePlus
  hosts (`/api/v3`, `/api/coding/v3`), clawrouter, cohere, deepseek, fireworks, gmi, groq, minimax,
  mistral, moonshot (both hosts), stepfun (`.com` and `.ai`), qwen standard (both), tencent (all four
  spellings), together, volcengine (`/api/v3`, `/api/coding/v3`), xai, xiaomi (all four), zai (both).
- HTTP 403 (host exists, refuses an unauthenticated client): cerebras, qianfan.
- HTTP 404: `api.kimi.com/coding/models` (expected: the Kimi Code base serves Messages, not a list).

## Failure patterns that applied here

| Pattern | Class | Phase 4 response |
|---|---|---|
| Plan key silently routed to the pay-as-you-go host and billed extra (Volcengine `/api/v3`) | fixable-in-Hutch | Pay-as-you-go template carries an explicit "this does not draw from a Coding Plan" notice; no plan template until terms are confirmed. |
| Plan terms forbid unattended use (Tencent Token Plan, as Alibaba and Z.AI before it) | policy | `blocked` auth method with the cited sentence; no template; test forbids a template at `/plan/v3`. |
| Gateway fallback bills a different payer than the key the user chose (Vercel BYOK to system credits) | mitigable | Template notice; gateway identity is separate from every upstream; Hutch cannot disable it over the OpenAI wire. |
| Alias or group name returned as the served model, cost recorded as zero (LiteLLM #22709, #21665; OpenHands SDK #6543, #4816) | mitigable | LiteLLM template states that ids are aliases; price is unknown unless the gateway reports it; the requested id is never shown as the served model. |
| Wrong auth header on Azure (`Authorization: Bearer <key>` instead of `api-key`) gives 401 or 404 (LiteLLM #7275, #16577) | fixable-in-Hutch | Foundry template sends `api-key` and no Bearer; pure-function test pins both. |
| Bare Bedrock model id fails with "on-demand throughput isn't supported" (Cline #689, opencode #396, #2589, LiteLLM #9780, #8851, #32683) | fixable-in-Hutch | Bedrock templates have no hardcoded model list; the notice names the inference-profile prefixes; Hutch never strips or adds a prefix. |
| Long-term Bedrock key used in another Region ("Credential should be scoped to a valid region", LiteLLM #20915) | mitigable | Region is in the template host and the notice; no silent region change. |
| `bedrock-runtime` has no `/models`; Mantle `/models` lists but the wrong path prefix is rejected | vendor-side | `models_endpoint` is false for bedrock-runtime; Mantle path prefix documented in the notice. |
| Regional host confusion (StepFun `.com` vs `.ai`) | fixable-in-Hutch | Separate global template with its own env var; asserted by test. |
| Undocumented but working base path (Synthetic `/v1`) | fixable-in-Hutch | Template moved to the documented path. |
| Mistral reasoning `high` with `temperature: 0` returns 400 | vendor-side | Recorded, not changed. |

## Decisions

1. No dependency is added. Both approvals (AWS SigV4, Azure/Foundry auth) are unused: Bedrock API keys and
   Foundry API keys are plain headers, so those routes need only data plus a header seam. AWS IAM/SigV4
   with the Converse event-stream, Google Vertex service-account tokens, and Entra ID tokens each need a
   new request signer plus an adapter change, cannot be verified without a cloud account, and are deferred
   with the design recorded below rather than shipped unverified.
2. Gateways and clouds that speak OpenAI or Anthropic wire with a static key become templates:
   `vercel-ai-gateway`, `litellm`, `clawrouter`, `bedrock-runtime`, `bedrock-mantle`, `microsoft-foundry`,
   `qianfan`, `stepfun-global`. Each is `implemented-unverified`; the host and path were probed only.
3. Cloudflare AI Gateway stays `documented`: the base URL embeds account and gateway ids, authentication needs
   a second header, and the vendor deprecated the unified `/compat` path on 2026-11-04. A template would ship
   a placeholder URL for an endpoint class the vendor is retiring.
4. Alibaba workspace endpoints stay `documented`: the host embeds a workspace id.
5. Tencent Token Plan is `blocked`; Volcengine and BytePlus Coding Plan stay `documented` (not blocked, since no
   term forbids unlisted tools, but not offered, since Hutch is not a listed tool and no sentence permits it).
6. Synthetic keeps OpenAI chat as the default protocol; the documented Anthropic base is recorded for override.

## Deferred, with reason

| Item | Reason |
|---|---|
| Bedrock IAM / SigV4 and Converse event-stream | Needs a signer and a binary event-stream decoder; no AWS account to verify; Bedrock API keys cover the OpenAI and Anthropic wires without it. |
| Vertex (Gemini and Claude) service-account route | Needs JWT-bearer token minting (`cryptography` is already a dependency), project/region URL shapes and `anthropic_version` body changes in two adapters; no GCP project to verify. |
| Entra ID for Foundry | Token mint plus refresh; API-key route is the supported minimum. |
| Cloudflare AI Gateway | See decision 3. |
| Step Plan, Volcengine/BytePlus Coding Plan, Qwen Token Plan | Plan terms unconfirmed or restrictive. |
