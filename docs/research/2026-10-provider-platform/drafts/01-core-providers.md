# Core providers: auth, billing, endpoints, and failure evidence

Research fragment for `00-SCOPE.md` through `07-ROLLOUT-AND-MIGRATION.md`.
Compiled 2026-10-30 (America/Vancouver); every web page below was fetched that
day unless noted. No provider account, key, or live request was available.
**No endpoint in this file is Hutch-verified live.**

**Evidence labels**

| Label | Meaning |
|---|---|
| **VENDOR** | First-party vendor documentation or changelog, read directly. |
| **VENDOR-SECONDARY** | Vendor docs read through a secondary rendering (localized docs page or .md mirror). Same publisher, lower confidence in exact wording. |
| **REPO** | Hutch's own published research, with its own dates and verification notes. |
| **ANECDOTE** | One public issue/report. Not reproduced by Hutch, not a prevalence estimate. |
| **UNVERIFIED** | Could not be read or confirmed. Do not build product claims on it. |

"Endpoint listed in docs" is not "Hutch verified live". A VENDOR row proves a
document said something on 2026-10-30; it does not prove entropy, region, or a
billing outcome for a given account.

## Summary table

| Provider / integration | Auth routes documented | Billing route | Documented endpoint(s) | Model family (documented) | Third-party / unattended reuse status | Evidence |
|---|---|---|---|---|---|---|
| OpenAI API | Bearer API key; Admin key; Workload Identity Federation token | Per-token API billing | `https://api.openai.com/v1` | GPT family; docs example `gpt-6.1-sol`; catalog not enumerated in pages read | API keys are the documented programmatic route | VENDOR |
| OpenAI ChatGPT plan (SIWC) | OAuth 2.0 + PKCE, dynamic client registration, host ID, refresh tokens | ChatGPT plan usage | Responses only: `https://api.openai.com/v1/responses`; OAuth host `https://auth.openai.com` | Account catalog via `GET /v1/models`; docs example `gpt-6.1-sol` | Sanctioned for open-source/local apps in preview; paid/remote-hosted needs interest form; VM transfer documented | VENDOR |
| OpenAI Codex CLI | `codex login`: ChatGPT, API key, device code (beta), `CODEX_ACCESS_TOKEN` | ChatGPT workspace or API-key per token | `api.openai.com`, `auth.openai.com` | Codex and GPT family | API key explicitly recommended for CI/CD; Codex access tokens Business/Enterprise only | VENDOR |
| Anthropic API | API key (`x-api-key` legacy or Bearer); WIF token; App Attest | Per-token API billing | `https://api.anthropic.com` (`/v1/messages`) | Fable 5.1, Opus 5.5, Sonnet 5.5, Haiku 5.5 | API keys are the documented third-party route | VENDOR |
| Claude subscription / Claude Code | claude.ai OAuth (Pro/Max/Ultra/Team/Enterprise); API key; `claude setup-token` | Subscription limits (5-hour + weekly); monthly API credits on Max/Ultra/Team | `api.anthropic.com` via Claude Code; gateway/cloud variants | Same Claude family | OAuth for native Anthropic apps only; third parties may not route plan credentials or store session tokens; `setup-token` drives Claude Code/Agent SDK only | VENDOR |
| Google Gemini API | Gemini API key (standard or auth key); Vertex ADC/service account | Free tier or paid per token; Vertex billing | `https://generativelanguage.googleapis.com`; OpenAI-compat `/v1beta/openai/` | Gemini 4 Argon (1M ctx), 3.8 Flash/Live/TTS, Nano Banana 2.x, Veo, Lyria | API key apps allowed under Gemini API terms; limits per project | VENDOR-SECONDARY |
| Google consumer plans (Antigravity) | Browser OAuth personal Google account (Free/Pro/Ultra); Google Cloud SSO; ADC headless | Subscription plus AI credits/quotas | `agy` CLI / Antigravity app; backend not a public API | Gemini family; Antigravity selects models in-product | Consumer route replaced Gemini CLI for individuals; headless/ADC documented | VENDOR |
| MiniMax | API key (PAYG) or M Plan subscription key | PAYG or M Plan (Go/Explore/Build) | `https://api.minimax.io/v1` (OpenAI), `https://api.minimax.io/anthropic` (Anthropic) | MiniMax-M3.1-Flash, M3 (1M ctx); H3 video; speech/image | M Plan key documented for Claude Code, Codex, Cursor, OpenCode, Pi, Hermes, OpenClaw; unattended not addressed | VENDOR |
| Moonshot / Kimi API | API key (`MOONSHOT_API_KEY`); OpenAI Chat/Responses and Anthropic Messages compatibility | Per-token PAYG | `https://api.moonshot.ai/v1` (overseas), `https://api.moonshot.cn/v1` (China) | kimi-k3.1-pro (1M), k3, k2.7-code (256k), k2.6 | API keys are the documented third-party route | VENDOR |
| Kimi Code membership | Kimi account in first-party clients; membership API key for third-party tools | Membership subscription with included quota | Anthropic-compatible `https://api.kimi.ai/coding/` (overseas), `https://api.kimi.com/coding/` (China) | K3.1 Pro series | Docs list Claude Code, OpenCode, Codex, Hermes Agent as supported third-party tools | VENDOR |
| Qwen (Qwen Code) | QwenCloud key or Token Plan; Alibaba ModelStudio Coding/Token Plan or key; third-party keys; custom | Subscription (Token/Coding Plan) or PAYG | `maas.qwencloudapi.com/compatible-mode/v1`, `maas.qianwenaiapi.com/compatible-mode/v1`, token-plan subdomains, `coding[-intl].dashscope.aliyuncs.com/v1` | Qwen IDs in third-party catalogs; vendor list not re-read | Qwen OAuth free tier retired 2026-04-15; subscription keys documented in Qwen Code | VENDOR |
| xAI API | API key | Prepaid credits / per-token | `https://api.x.ai/v1` | grok-4.7 (500k ctx), 4.6, 4.3 (1M), grok-build-0.1, Imagine, Voice | API key is the documented programmatic route | VENDOR |
| xAI consumer subscription | X Subscription login for Grok/Grok Build/Grok Bot | Seat + shared weekly pool, top-ups | First-party surfaces; `cli-chat-proxy.grok.com`, `auth.x.ai` | Same Grok models | Weekly pool is "eligible first-party usage only"; third-party consumption not described | VENDOR |
| Z.AI | Standard key; separate Coding Plan key | PAYG or GLM Coding Plan (Lite/Pro/Max) | `https://api.z.ai/api/paas/v4`; coding `/api/anthropic`, `/api/coding/paas/v4`, `/api/v1` | GLM-5.3, 5.3-Flash, FlashX, 5.2 and earlier | Coding Plan limited to officially supported tools; sharing banned; unsupported tools risk restriction | VENDOR |
| OpenCode (CLI/harness) | `/connect` or `opencode auth login`: API key, OAuth, command, environment | Provider-billed or OpenCode plans | Provider-specific; auth cache `~/.local/share/opencode/auth.json` (V1 docs) | Provider catalog via models.dev | ChatGPT Plus/Pro and GitHub Copilot sign-in supported; Claude Pro/Max plugins prohibited by Anthropic, removed in OpenCode 1.3.0 | VENDOR |
| OpenCode Go | API key issued by the OpenCode Console after subscribing | Go $10/mo, Go Plus $40/mo, Go Teams $20/member/mo | Doc-listed inference route; exact V2 URL not re-verified (repo template: `opencode.ai/inference/go/...`) | 30+ models incl. Grok 4.7, GLM-5.3, GPT 6 Luna, Claude Haiku 5.5, Gemini 4 Argon, Kimi K3.1 Pro, MiniMax M3, Qwen3.8 | "Designed for OpenCode and other coding agents that produce similar requests"; traffic monitored for abuse | VENDOR |

## Cross-cutting findings

### 1. Which subscription-backed routes are actually sanctioned

| Route | What the vendor says (2026-10-30) | Hutch implication |
|---|---|---|
| OpenAI ChatGPT plan via SIWC | Docs address "open-source and locally hosted apps"; paid or remotely hosted apps must use the interest form. Self-hosted VM transfer documented, but host-specific attribution and revocation of transferred sessions "not yet available". | A local, single-user, open-source Hutch process sits inside the documented preview envelope; a hosted service does not. Responses only; many fields rejected. |
| OpenAI Codex automation | API key is the path for "programmatic Codex CLI workflows, such as CI/CD jobs". Access tokens exist only for Business/Enterprise and are for "trusted scripts, schedulers, and private CI runners". | Unattended ChatGPT-plan use is documented, but only through Codex surfaces and, for automation, Business/Enterprise tokens or API keys. |
| Anthropic subscription via Claude Code | OAuth "intended exclusively for purchasers of Claude Free, Pro, Max, Ultra, Team, and Enterprise subscription plans and designed to support ordinary use of Claude Code and other native Anthropic applications". Third parties may not offer Claude.ai login, route plan credentials, or collect/store/intermediate session tokens. End users may sign into the unmodified Claude Code binary. | Routing Max credentials into a general model runtime is prohibited. Running unmodified Claude Code as a coding handoff with the user's own login is the documented allowed shape. |
| Anthropic API credits from a subscription | From 2026-10-07 Max/Ultra/Team include monthly credits (Max $100, Ultra $200, Team $20/$100 per seat) usable with an API key in a linked Console org; covers Claude API, Managed Agents, Agent SDK; excludes interactive Claude Code. | Sanctioned subscription-to-API-spend path, but bounded and plan-scoped. Not the same as subscription OAuth. |
| Google consumer plans | Gemini CLI stopped serving free individuals and AI Pro/Ultra on 2026-06-18; Antigravity CLI is the consumer surface, with browser OAuth and ADC for headless. | Google's sanctioned consumer route is a first-party CLI, not a general API. General API route is a Gemini API key. |
| MiniMax / Kimi / Qwen / Z.AI / OpenCode Go subscriptions | Plans are marketed for coding tools. MiniMax, Kimi, Qwen and OpenCode name tools or "coding agent" traffic; Z.AI restricts to "officially supported tools and products" and bans account sharing. None affirmatively authorizes unattended scheduled bots. | Treat as coding-tool subscriptions. Require per-connection operator acknowledgement; never present as general unattended capacity. |

### 2. Environment-variable precedence conflicts

| Conflict | Documented behavior | Class |
|---|---|---|
| `ANTHROPIC_API_KEY` vs Claude subscription | "When set, this key is used instead of your Claude Pro, Max, Ultra, Team, or Enterprise subscription even if you are logged in"; always used in `-p`. Order: cloud-provider flags, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_API_KEY`, `apiKeyHelper`, `CLAUDE_CODE_OAUTH_TOKEN`, profile/federation, `/login` OAuth. | VENDOR |
| Providers reusing Anthropic variable names | MiniMax documents `ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic` + `ANTHROPIC_API_KEY` for Claude Code; Kimi and Z.AI also document Anthropic-compatible endpoints. A process-wide value redirects Anthropic-looking traffic to another vendor. | VENDOR |
| `ANTHROPIC_AUTH_TOKEN` vs `ANTHROPIC_API_KEY` | `ANTHROPIC_AUTH_TOKEN` ranks higher and is sent as `Authorization: Bearer`; this is the proxy/gateway variable. | VENDOR |
| OpenCode saved account vs environment | "A saved account takes precedence over an environment connection for the same integration." Env connections cannot be logged out; unset the variable. | VENDOR |
| Gemini CLI key vs Vertex | `GEMINI_API_KEY` for Gemini API; `GOOGLE_API_KEY` + `GOOGLE_GENAI_USE_VERTEXAI=true` for Vertex. Precedence versus a cached Google login was not documented in pages read. | VENDOR / UNVERIFIED |
| Grok Build config vs env | Layer order: `/etc/grok/managed_config.toml` < `~/.grok/managed_config.toml` < `~/.grok/config.toml` < `~/.grok/requirements.toml` < `/etc/grok/requirements.toml`. ACP sample selects `xai.api_key` when `XAI_API_KEY` is set, else `cached_token`. | VENDOR |
| Qwen Code Coding Plan | Headless setup uses `BAILIAN_CODING_PLAN_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`; setting `OPENAI_BASE_URL` affects anything else reading OpenAI variables. | VENDOR |
| Kimi key/base-URL mismatch | Membership keys and Open Platform keys use different base URLs; mismatch reports "No models available for the selected platform". | VENDOR |
| Codex ambient API key vs cached login | Docs describe `codex login`, `codex logout`, cached credentials, `--with-api-key`; ambient `OPENAI_API_KEY` billing without explicit login is not documented in pages read. | UNVERIFIED |

### 3. OAuth and refresh lifecycle details

| Flow | Documented lifecycle |
|---|---|
| OpenAI SIWC | Access token 1 hour. Refresh token 30 days, rotated each refresh, new 30-day lifetime, no fixed replacement limit. Refresh POST to `https://auth.openai.com/api/accounts/oauth/token` with issued `client_id`, saved refresh token, `resource=https://api.openai.com/v1`; omit `scope` to retain grant; serialize refreshes. Revoke via `revocation_endpoint` from `https://auth.openai.com/.well-known/openid-configuration` with `token_type_hint=refresh_token`. Codex app-server must be restarted with the renewed token, then resume the thread. |
| Claude Code subscription OAuth | `/login` renews automatically when possible; an expired sign-in that cannot refresh triggers a fresh login. `claude setup-token` mints a one-year token for CI/scripts, prints once, only makes model requests, and must be regenerated after expiry. `CLAUDE_CODE_OAUTH_REFRESH_TOKEN` + `CLAUDE_CODE_OAUTH_SCOPES` can provision auth without a browser. Open bug #105729 shows a refresh-lock that stalls other processes up to 60 s. |
| Codex CLI | ChatGPT sign-in tokens refresh automatically during use. Device code (beta) for headless/remote; copy-`auth.json` fallback; `cli_auth_credentials_store` = file/keyring/auto/ephemeral (file is plaintext). |
| Antigravity | Shared auth across app, CLI, IDE, SDK; OS keyring used silently; remote SSH prints URL and expects a pasted code; ADC via `AGY_ADC_AUTH=true` or `enableAdc`. Token lifetimes not readable (UNVERIFIED). |
| GitHub Copilot in OpenCode | Device OAuth through `/connect`; GitHub.com or GitHub Enterprise; Copilot API endpoint returned by GitHub when available. PR #44114 stopped `GITHUB_TOKEN` from auto-activating Copilot. |

### 4. Endpoint-listed vs Hutch-verified

"Documented" means a vendor page states an endpoint and shape. "Hutch verified"
means a governed Hutch run reached it with a real key, received a response, and
recorded model identity and usage. **None of the providers here meets that bar.**
Prior repo work used fixtures only: "no live paid provider account was used"
(`docs/research/multi-provider-platform-review-2026-10-10.md`,
`docs/realignment/provider-compatibility.md`, reviewed 2026-10-10).

## Per-provider sections

### OpenAI

**Auth.** Bearer API key or Workload Identity Federation short-lived token; Admin keys are separate and only for Administration endpoints. Revocations take effect within seconds; most auth-affecting updates within 15 minutes.
([API overview](https://developers.openai.com/api/reference/overview.md), fetched 2026-10-30)

**Codex CLI.** Two sign-in methods: ChatGPT (subscription) or API key (usage-based). Local work is supported in the ChatGPT desktop app, Codex CLI and IDE extension; Codex cloud requires ChatGPT sign-in. Commands: `codex login`, `printenv OPENAI_API_KEY | codex login --with-api-key`, `codex login status`, `codex logout`. Cached in `~/.codex/auth.json` or the OS store; `cli_auth_credentials_store` = file/keyring/auto/ephemeral. Device-code auth (beta) is the headless option, with a copy-`auth.json` fallback.
([Codex authentication](https://learn.chatgpt.com/codex/auth.md), fetched 2026-10-30)

**Unattended use.** "Use API key authentication for programmatic Codex CLI workflows, such as CI/CD jobs. Don't expose Codex execution in untrusted or public environments." Business/Enterprise can issue scoped Codex access tokens for "trusted scripts, schedulers, and private CI runners".
([Codex access tokens](https://learn.chatgpt.com/docs/enterprise/access-tokens.md), fetched 2026-10-30)

**ChatGPT plan usage (SIWC).** OAuth 2.0 + PKCE with dynamic client registration for open-source and locally hosted apps; paid or remotely hosted apps need the interest form. Persist an `ext_agent_host_id`; request `chatgpt.tokens.use.direct`; call only `POST https://api.openai.com/v1/responses` with `store:false`, `stream:true`. Unsupported fields: `background`, `conversation`, `max_output_tokens`, `max_tool_calls`, `metadata`, `moderation`, `multi_agent`, `prompt`, `prompt_cache_retention`, `safety_identifier`, `temperature`, `top_logprobs`, `top_p`, `truncation`, `user`, `previous_response_id`. Unsupported tools: image generation, file search, Code Interpreter, native computer use, hosted MCP, `tool_search`. Errors: `subscription_sharing_user_not_eligible` (403), `subscription_sharing_usage_limit_exceeded` (429), `subscription_sharing_usage_unavailable` (503), 403 "permitted serving region". Plus shares a five-hour limit across all apps; Pro has none. Self-hosted VM transfer documented, but transferred-session attribution/revocation "not yet available".
([overview](https://developers.openai.com/siwc/token-sharing-open-source.md), [limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations.md), [sessions](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions.md), [tokens](https://developers.openai.com/siwc/token-sharing-open-source/token-reference.md), [VMs](https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms.md), [errors](https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery.md), fetched 2026-10-30)

**Plan-funded API credits.** Pro $100/$200/$500 monthly; Business $20 per Standard seat and $100 per Premium seat, $500 per workspace per month cap; claimed by linking the subscription to an API organization. Covers paid API usage but explicitly not "Codex usage through API keys"; does not raise ChatGPT/Codex signed-in limits.
([API credits](https://developers.openai.com/api/docs/guides/chatgpt-api-credits.md), fetched 2026-10-30)

**Limits/regions.** SIWC model list via `GET /v1/models` filtered to `visibility == "list"`. A region gate exists (403) but the permitted region list was not read. UNVERIFIED.

**Verdict.** API key and plan-funded API credits are the clean routes; SIWC is preview-only, Responses-only and field-restricted, with eligibility and region risk; Codex access tokens are not available to ordinary Pro subscribers. Do not describe ChatGPT sign-in as free API access.

### Anthropic

**Auth.** API key sent as `Authorization: Bearer` or legacy `x-api-key`; Workload Identity Federation exchanges an IdP token at `POST /v1/oauth/token`; App Attest covers distributed iOS/macOS apps. Key types: personal, service account, legacy workspace. `anthropic-version` required; base `https://api.anthropic.com`.
([Authentication](https://platform.claude.com/docs/en/manage-claude/authentication.md), [API overview](https://platform.claude.com/docs/en/api/overview.md), fetched 2026-10-30)

**Claude Code auth.** claude.ai account (Pro/Max/Ultra), Team/Enterprise, Console credentials (with or without key), Bedrock, Google Cloud's Agent Platform, Microsoft Foundry, or a Claude apps gateway. Precedence is in the cross-cutting table; `ANTHROPIC_API_KEY` overrides a signed-in subscription. `claude setup-token` mints a one-year token for CI/scripts (model requests only); `CLAUDE_CODE_OAUTH_REFRESH_TOKEN` + `CLAUDE_CODE_OAUTH_SCOPES` provision auth without a browser.
([Authentication](https://code.claude.com/docs/en/authentication.md), [env vars](https://code.claude.com/docs/en/env-vars.md), fetched 2026-10-30)

**Legitimacy.** OAuth is "intended exclusively for purchasers of Claude Free, Pro, Max, Ultra, Team, and Enterprise subscription plans and designed to support ordinary use of Claude Code and other native Anthropic applications". Developers "should use API key authentication"; Anthropic "does not permit third-party developers to offer Claude.ai login into their own applications, or to route requests through Free, Pro, Max, or Ultra plan credentials on behalf of their users"; developers "may not collect, store, or intermediate Claude.ai credentials or session tokens". Signing in to the unmodified Claude Code binary (including platform-hosted) stays allowed. Limits "assume ordinary, individual usage".
([Legal and compliance](https://code.claude.com/docs/en/legal-and-compliance.md), fetched 2026-10-30)

**Max API proxy question.** Proxying subscription OAuth as an OpenAI-compatible API is the prohibited shape. OpenCode V1 docs say plugins using Claude Pro/Max are "explicitly prohibited" by Anthropic and were removed from OpenCode in 1.3.0. Community proxy docs call it "technical compatibility only, not an officially sanctioned path" and note Anthropic "has blocked some subscription usage outside Claude Code in the past".
([OpenCode V1](https://opencode.ai/docs/providers/), [OpenClaw proxy](https://docs.openclaw.ai/providers/claude-max-api-proxy), fetched 2026-10-30)

**Limits and credits.** Pro/Max: five-hour + weekly limits; Ultra: weekly only (verified); Max/Ultra also have a separate weekly Fable limit; limits shared across Claude and Claude Code; capped wrap-up allowance. The Agent SDK page (updated 2026-10-07) says Max/Ultra/Team include monthly API credits, while a 2026-06-15 note paused the announced Agent SDK change: Agent SDK, `claude -p` and third-party app usage "still draw from your subscription limits". Credits: Max $100, Ultra $200, Team $20 per Standard seat / $100 per Premium seat; Free/Pro/Enterprise ineligible; excludes interactive Claude Code.
([Pro/Max/Ultra article](https://support.claude.com/en/articles/11145838-use-claude-code-with-your-pro-or-max-plan), [Agent SDK article](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan), [monthly credits](https://support.claude.com/en/articles/17154008-monthly-api-credits-for-max-ultra-and-team-plans), fetched 2026-10-30)

**Models.** Fable 5.1 ($10/$50 per MTok), Opus 5.5 ($4/$20), Sonnet 5.5 ($2/$10), Haiku 5.5 (from $0.10/$0.50). All current models support text and image input, vision and tool use; IDs `claude-fable-5-1`, `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`.
([Models](https://platform.claude.com/docs/en/about-claude/models/overview.md), fetched 2026-10-30)

**Verdict.** API key is the compliant third-party path; `setup-token` is a documented subscription-backed unattended route but only for Claude Code/Agent SDK; block Max proxies (the repo already blocks consumer OAuth/session reuse).

**Failure reports.** See the consolidated register: claude-code #105729 and #18225.

### Google / Gemini

**Two products, two auth stories.** The Gemini API (developer key) and consumer coding subscriptions (Antigravity) must not be conflated.

**Gemini API keys.** Requests authenticate with a Gemini API key. From 2026-05-28, new keys created in Google AI Studio are created as auth keys automatically; the API rejects unrestricted standard keys (restricted standard keys keep working). Auth keys are bound to a Google Cloud service account and are not counted in that account's usage metrics. Each key belongs to a Cloud project that carries billing and quotas.
([API keys](https://ai.google.dev/gemini-api/docs/api-key), fetched 2026-10-30)

**Endpoint/compatibility.** Base `https://generativelanguage.googleapis.com`; OpenAI-compatible surface `https://generativelanguage.googleapis.com/v1beta/openai/` with `Authorization: Bearer $GEMINI_API_KEY`. `reasoning_effort` maps to Gemini `thinking_level` (minimal/low/medium/high).
([OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai), fetched 2026-10-30)

**Models and limits.** Gemini 4 Argon (`gemini-4-argon`) is flagship, with a unified 1M context and long decodes up to 1M tokens; also Gemini 3.8 Flash, 3.8 Live, 3.8 Flash/Flash-Lite TTS, 3.6 Flash, 3.5/3.1 Flash-Lite, Nano Banana 2.1/2, Veo, Lyria 3.5. Limits are per project (RPM/TPM/RPD); RPD resets midnight Pacific. Free and paid tiers exist.
([Models](https://ai.google.dev/gemini-api/docs/models), [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits), fetched 2026-10-30; read as VENDOR-SECONDARY)

**Gemini CLI consumer auth is retired.** Official README: "Enterprise Code Assist only"; "No free tier or Google AI plans: Free individual access and Google AI Pro / Ultra (Google One) moved to Antigravity CLI on June 18, 2026"; not optimized for Gemini 4+. The 2026-05-19 announcement says Gemini CLI and Code Assist IDE extensions stop serving AI Pro/Ultra and free individual Code Assist on 2026-06-18, and Code Assist for GitHub gets no new installations. Enterprise Standard/Enterprise and Google Cloud Code Assist are unchanged, and Gemini CLI "will remain accessible via paid Gemini and Gemini Enterprise Agent Platform API keys".
([Gemini CLI README](https://github.com/google-gemini/gemini-cli), [transition post](https://developers.googleblog.com/an-important-update-transitioning-gemini-cli-to-antigravity-cli/), fetched 2026-10-30)

**Antigravity (consumer replacement).** Unified browser OAuth for personal Google accounts (Free/Pro/Ultra); Google Cloud SSO / Gemini Enterprise with WIF license selection; ADC for headless (`AGY_ADC_AUTH=true` or `enableAdc` in `~/.gemini/config/config.json`). CLI uses the OS keyring silently; over SSH it prints a URL and expects a pasted code. CLI AI credits integrate with subscription quotas. Some pages are JS-rendered; token lifetimes and exact quota numbers were not readable (UNVERIFIED).
([Authenticate](https://antigravity.google/docs/install.md), [CLI credits](https://antigravity.google/docs/cli/credits), fetched 2026-10-30)

**Env-var note.** Gemini CLI reads `GEMINI_API_KEY` (Gemini API) or `GOOGLE_API_KEY` + `GOOGLE_GENAI_USE_VERTEXAI=true` (Vertex). With the consumer route retired these cover paid API/Vertex work only; precedence versus a cached Antigravity sign-in was not documented (UNVERIFIED).

**Failure reports.** No provider-auth failure report was verified for Gemini/Antigravity. Existing repo Gemini CLI behavior complaints are 2026-10-07-revalidated anecdotes, not billing/auth evidence.

### MiniMax

**Auth and endpoints.** PAYG users create a normal API key; M Plan subscribers
create a "Subscription Key" under Billing > M Plan. Documented env shapes:
Anthropic SDK with `ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic` +
`ANTHROPIC_API_KEY`; OpenAI SDK with `OPENAI_BASE_URL=https://api.minimax.io/v1`
+ `OPENAI_API_KEY`; native samples use `MINIMAX_API_KEY`. The Anthropic Messages
endpoint is the recommended integration in current docs.
([Prerequisites](https://platform.minimax.io/docs/guides/quickstart-preparation.md), [Anthropic SDK](https://platform.minimax.io/docs/guides/quickstart-sdk.md), fetched 2026-10-30)

**Models.** MiniMax-M3.1-Flash (multimodal coding model, 1M context, tunable
thinking depth), MiniMax-M3 (1M context), video MiniMax-H3, speech-2.8-hd/turbo,
image generation. MiniMax-M3.1-Flash-Preview is retired; the old name is served
by M3.1-Flash.
([Models](https://platform.minimax.io/docs/guides/models-intro.md), fetched 2026-10-30)

**Billing.** PAYG for all modalities, or M Plan (Go, Explore, Build; quotas 1x /
3x / 7.5x relative to Go; annual pays 10 months for 12). All modalities share one
M Plan usage limit; text/image/audio use a five-hour and a weekly window, video is
weekly-only. MiniMax Code is the first-party client (sign in, no M Plan API key
needed); other tools use the M Plan API key.
([M Plan intro](https://platform.minimax.io/docs/m-plan/intro.md), [FAQ](https://platform.minimax.io/docs/m-plan/faq.md), fetched 2026-10-30)

**Third-party and unattended use.** M Plan docs explicitly list Claude Code,
Codex, Cursor, OpenCode, Pi, Hermes Agent and OpenClaw as "other AI tools" usable
with an M Plan API key, and say the same subscription can be used across tools
with shared usage. They do not address unattended/scheduled use. UNVERIFIED for
unattended eligibility; treat as a coding-tool subscription.
([M Plan FAQ](https://platform.minimax.io/docs/m-plan/faq.md), fetched 2026-10-30)

**Regions.** International platform `platform.minimax.io`, API host
`api.minimax.io`. Search results reference `platform.minimax.cn`,
`platform.minimaxi.com` and a token-plan subscription entry, but those pages were
not fetched. UNVERIFIED.

**Failure reports.** None verified in this pass. No claim made.

### Moonshot / Kimi

**API platform.** `platform.kimi.ai`; create an API key and set
`MOONSHOT_API_KEY`. The API is compatible with OpenAI Chat Completions and
Responses, and with Anthropic Messages. Models: `kimi-k3.1-pro` (3T-class, 1M
context, native vision), `kimi-k3.1-pro-highspeed` (~2-3x speed), `kimi-k3` (1M),
`kimi-k2.7-code` and `kimi-k2.7-code-highspeed` (256K, coding), `kimi-k2.6`
(256K). PAYG base URLs: `https://api.moonshot.ai/v1` overseas,
`https://api.moonshot.cn/v1` in China.
([Quickstart](https://platform.kimi.ai/docs/get-your-api-key.md), [Models](https://platform.kimi.ai/docs/models.md), fetched 2026-10-30)

**Retirements.** K2 series stops being available to new users from 2026-10-31 and
is planned for full retirement by end of December 2026; `kimi-k2.5` and the whole
`moonshot-v1` series were discontinued 2026-08-31; `kimi-latest` discontinued
2026-01-28. The catalog is moving fast.
([Models](https://platform.kimi.ai/docs/models.md), fetched 2026-10-30)

**Kimi Code membership.** "An intelligent programming service included in Kimi
membership benefits"; subscribers can obtain an API key to use Kimi Code model
capabilities in third-party tools. Membership keys use Anthropic-compatible
`https://api.kimi.ai/coding/` overseas and `https://api.kimi.com/coding/` in
China; Open Platform PAYG uses the addresses above. Mismatched key/base URL
reports "No models available for the selected platform". Docs navigation lists
"Use in Third-Party Tools" for Claude Code, OpenCode, Codex and Hermes Agent.
([Kimi Code overview](https://www.kimi.com/code/docs/en/), [Kimi Code FAQ](https://www.kimi.com/code/), fetched 2026-10-30)

**Third-party and unattended use.** Membership benefits are documented as usable
in both official clients and third-party platforms via API key, which is stronger
than a native-apps-only policy. Pages read do not address unattended/scheduled
agents. UNVERIFIED for unattended eligibility. Two billing pools exist
(membership quota on coding endpoints; PAYG on Open Platform); a wrong base URL
bills the wrong thing or fails.

**Failure reports.** None verified beyond the documented base-URL mismatch error.
No claim made.

### Qwen

**Qwen OAuth is retired.** Qwen Code docs: "Qwen OAuth is no longer a selectable dialog entry — its free tier was discontinued on 2026-04-15. It remains documented below as a hard-coded, discontinued provider only." The cleanest example of a whole consumer route being withdrawn.
([Qwen Code authentication](https://github.com/QwenLM/qwen-code/blob/main/docs/users/configuration/auth.md), fetched 2026-10-30)

**Current auth routes.** QwenCloud (standard key or Token Plan subscription with monthly credit quota and dedicated endpoint; Personal/Team); Alibaba ModelStudio (Coding Plan with weekly quota, Token Plan for teams, or standard key); third-party providers (DeepSeek, Grok, MiniMax, Z.AI, Kimi, Idealab, ModelScope, OpenRouter, Requesty); custom OpenAI/Anthropic/Gemini-compatible endpoints.
([Qwen Code authentication](https://github.com/QwenLM/qwen-code/blob/main/docs/users/configuration/auth.md), fetched 2026-10-30)

| Platform | Access | Endpoint |
|---|---|---|
| QwenCloud China | standard key | `https://maas.qianwenaiapi.com/compatible-mode/v1` |
| QwenCloud China | Token Plan | `https://token-plan.maas.qianwenaiapi.com/compatible-mode/v1` |
| QwenCloud International | standard key | `https://maas.qwencloudapi.com/compatible-mode/v1` |
| QwenCloud International | Token Plan | `https://token-plan.maas.qwencloudapi.com/compatible-mode/v1` |
| Alibaba ModelStudio | Coding Plan (China) | `https://coding.dashscope.aliyuncs.com/v1` |
| Alibaba ModelStudio | Coding Plan (intl) | `https://coding-intl.dashscope.aliyuncs.com/v1` |

Key prefixes: Token/Coding Plan keys `sk-sp-`; PAYG `sk-` or `sk-ws-`. Headless setup uses `BAILIAN_CODING_PLAN_API_KEY`, `OPENAI_BASE_URL` and `OPENAI_MODEL`; the removed `qwen auth coding-plan` command is replaced by environment/settings configuration.
([Qwen Code authentication](https://github.com/QwenLM/qwen-code/blob/main/docs/users/configuration/auth.md), fetched 2026-10-30)

**Retirement evidence.** qwen-code #3281 (closed; 2026-04-15 to 2026-04-17): OAuth reported success but prompts failed with free-tier quota exceeded and the discontinuation notice. qwen-code #3382 (closed; 2026-04-17 to 2026-07-01): docs feedback to update the still-live OAuth section. Both ANECDOTE.

**Third-party and unattended use.** Token Plan and Coding Plan are first-class Qwen Code options, and Qwen Code ships headless mode, GitHub Actions, daemon mode and scheduled tasks. Plan terms for automated agents and exact quota numbers were not read. UNVERIFIED whether a plan covers unattended bots.

**Failure reports.** See register: qwen-code #3281, #3382.

### xAI

**API.** API keys are created in `console.x.ai` and sent to
`https://api.x.ai/v1`; examples use the Responses API and the OpenAI SDK with
`base_url="https://api.x.ai/v1"`. Environment variable `XAI_API_KEY`.
([Quickstart](https://docs.x.ai/developers/quickstart.md), fetched 2026-10-30)

**Models.** `grok-4.7` (500K context; $2/$6 per MTok below 200K prompt tokens,
$4/$12 above), `grok-4.6`, `grok-4.5`, `grok-4.3` (1M context), `grok-4.20-*`
variants, `grok-build-0.1` (256K), Imagine image/video and Voice API. No current
events without search tools enabled.
([Models](https://docs.x.ai/developers/models.md), fetched 2026-10-30)

**Grok Build CLI.** Install via `curl -fsSL https://x.ai/cli/install.sh | bash` or
`npm install -g @xai-official/grok`. First launch opens a browser for auth; in
non-browser environments set `XAI_API_KEY`. Headless: `grok -p "..."` with
`--output-format plain|json|streaming-json`, sessions under `~/.grok/sessions`,
`--always-approve`, and ACP via `grok agent stdio`. Enterprise hosts:
`cli-chat-proxy.grok.com` (inference) and `auth.x.ai` (OAuth2/OIDC); `api.x.ai`
only for the direct API-key path. Config precedence is in the cross-cutting table.
([Grok Build](https://docs.x.ai/build/overview.md), [headless](https://docs.x.ai/build/cli/headless-scripting.md), [enterprise](https://docs.x.ai/build/enterprise.md), fetched 2026-10-30)

**Consumer subscription.** "The X Subscription" combines Grok, Cursor and X:
Free, Plus $8/mo, Premium $30/mo, Super $100/mo, Ultra $200/mo (annual discounts;
team seats at Premium/Super/Ultra per-seat prices). Each paid seat has a weekly
pool for "eligible first-party usage only across supported Grok and Cursor
surfaces"; Grok Bot is included on Premium, Super and Ultra; third-party models in
Cursor are billed at API list prices from prepaid credit; top-ups buy Additional
Usage.
([Pricing](https://docs.x.ai/x-subscription/pricing.md), [usage limits](https://docs.x.ai/x-subscription/usage-limits.md), [overview](https://docs.x.ai/x-subscription/overview.md), fetched 2026-10-30)

**Unattended/third-party use.** Headless and ACP modes are documented, but pages
read do not state whether headless Grok Build draws from the X Subscription pool
or from API credits, nor whether third-party consumption is permitted.
UNVERIFIED. For Hutch, the documented programmatic route is an API key.

**Failure reports.** None verified for the API or Grok Build auth in this pass.
Repository Grok Bot complaints concern a hosted product and are not API-auth
evidence.

### Z.AI

**API.** Standard API key from z.ai; OpenAI-compatible endpoint
`https://api.z.ai/api/paas/v4/chat/completions`. Models: GLM-5.3 ($1.4 input /
$4.4 output per MTok), GLM-5.3-Flash ($0.15/$0.50), GLM-5.3-FlashX, GLM-5.2/5.1/5,
GLM-4.7, GLM-4.6, vision/image models; Web Search $0.01/use. A rate-limit page
exists.
([Quick start](https://docs.z.ai/guides/overview/quick-start.md), [pricing](https://docs.z.ai/guides/overview/pricing.md), fetched 2026-10-30)

**GLM Coding Plan.** From $18/month, Lite/Pro/Max. Credits: Lite 2,000 per five
hours / 10,000 per week; Pro 12,000/60,000; Max 28,000/140,000; five-hour credits
refresh dynamically after consumption. Dedicated endpoints:
`https://api.z.ai/api/anthropic` (Anthropic Messages),
`https://api.z.ai/api/coding/paas/v4` (OpenAI Chat Completions),
`https://api.z.ai/api/v1` (OpenAI Responses). Supported tools include ZCode,
Claude Code, Codex, OpenCode, AutoClaw/OpenClaw, Roo Code, Kilo Code, Cline,
Crush, Goose, Cursor and "other tools".
([Coding Plan overview](https://docs.z.ai/devpack/overview.md), [quick start](https://docs.z.ai/devpack/quick-start.md), fetched 2026-10-30)

**Restrictions (strictest of the group).** "Subscription benefits are exclusive to
the subscriber"; "Account sharing or multi-user access is prohibited"; use is
"limited to supported tools"; "Use in unsupported tools may result in restricted
benefits"; violations may trigger rate limiting, account freezing or bans; more
than three violations may be banned. No refunds; cancel at least 3 days before
renewal.
([Usage policy](https://docs.z.ai/devpack/usage-policy.md), fetched 2026-10-30)

**Key separation (2026-10-16).** Standard keys and Coding Plan keys are managed
separately. Key type determines billing regardless of endpoint: a Standard key in
a coding tool does not consume plan quota and may incur PAYG charges. Existing
keys were auto-classified Team Plan / Compatible / Standard.
([API key management](https://docs.z.ai/devpack/notice/api-key-management.md), fetched 2026-10-30)

**Third-party and unattended use.** The plan is explicitly scoped to supported
tools, which include third-party coding CLIs, but does not list long-running
unattended bots. An unattended Hutch scheduler is not obviously an "officially
supported tool". Treat as a restricted route; require operator acknowledgement.
The policy is VENDOR for tool scope; "unattended" is an inference and is
UNVERIFIED in explicit terms.

**Failure reports.** None verified in this pass. No claim made.

### OpenCode (harness, CLI, and OpenCode Go)

**Credential model.** V1 docs: credentials added with `/connect` are stored in `~/.local/share/opencode/auth.json`. V2 CLI lists four methods: API key, OAuth, provider-supplied command, environment. Environment connections are not accounts, cannot be logged out, and "a saved account takes precedence over an environment connection for the same integration". CLI: `opencode auth login <provider> [--method key]`.
([Providers V1](https://opencode.ai/docs/providers/), [CLI providers V2](https://opencode.ai/v2/docs/cli/providers/), fetched 2026-10-30)

**Sign-in routes (V2).** ChatGPT Plus/Pro: connect OpenAI, choose "Sign in with ChatGPT" or a legacy Codex method; usage counts against the plan and the UI shows no cost. Context is capped by default (500K input for GPT-6.1 Sol and newer, 272K older) to approximate Codex consumption; remove the cap with the `opencode.provider.openai-context-caps` plugin. GitHub Copilot: device OAuth (GitHub.com or Enterprise), requires Copilot Chat entitlement. Google Vertex: ADC plus project/location.
([Providers V2](https://opencode.ai/v2/docs/providers/), fetched 2026-10-30)

**Claude Pro/Max is prohibited.** V1 docs state that plugins using Claude Pro/Max models are "explicitly prohibited" by Anthropic and that OpenCode stopped bundling them in 1.3.0. Treat any Max OAuth proxy as blocked.
([Providers V1](https://opencode.ai/docs/providers/), fetched 2026-10-30)

**GitHub Copilot legitimacy.** OpenCode uses device OAuth plus a Copilot API endpoint "returned by GitHub when available", otherwise derived from the enterprise domain. GitHub's own programmatic answer is the Copilot SDK (GA 2026-06-02), which embeds Copilot's agent runtime with GitHub OAuth, GitHub Apps, environment tokens or BYOK and is offered to Copilot subscribers including Copilot Free. No GitHub page read authorizes third-party reuse of a Copilot subscription through OpenCode's internal route; an anything-llm issue (#6075) calls a generic OpenAI-style Copilot integration a TOS violation, but that is a user claim. Status: OpenCode documents it, GitHub documents the SDK; authorization is UNVERIFIED.
([Copilot SDK GA](https://github.blog/changelog/2026-06-02-copilot-sdk-is-now-generally-available/), fetched 2026-10-30)

**OpenCode Go (key, not OAuth).** Go $10/month, Go Plus $40/month, Go Teams $20/member/month. The user signs in to the OpenCode Console, subscribes, copies an API key, runs `/connect` and pastes it. Go is "not OAuth session sharing" and "designed for OpenCode and other coding agents that produce similar types of requests". Required client behavior: typical coding-agent traffic, its own user agent, and a stable `x-opencode-session` header per conversation; traffic is monitored for abuse. Validated clients include Hermes, Claude Code, Codex, ZCode, Pi, jcode and Kilo Code CLI. Privacy defaults block paid endpoints that train on request data; allowed regions are Europe and the United States, and workspaces without saved privacy settings also allow Global for requests from China. Models include Grok 4.7, GLM-5.3/5.2, GPT 6 Luna, Claude Haiku 5.5, Gemini 4 Argon, Kimi K3.1 Pro, MiniMax M3/M3.1, Qwen3.8, DeepSeek V4.
([OpenCode Go V2](https://opencode.ai/v2/docs/console/go/), [Go guide V1](https://opencode.ai/docs/go/), fetched 2026-10-30)

**Unverified detail.** The exact Go inference base URL was not re-verified on the V2 page; the repository template lists https://opencode.ai/inference/go/openai/v1 and .../anthropic (2026-10-07), so treat that as REPO.

**Failure reports.** See the register: opencode #46891, #11673, PR #44114.

## Failure reports (anecdotal, provenance checked)

All rows were fetched via the GitHub API on 2026-10-30 and show the issue's
current title, state and creation date. They are single reports, not prevalence
estimates, and none was reproduced by Hutch.

| Flow | Report | Created / state | What the report says |
|---|---|---|---|
| Codex CLI auth | [openai/codex #46430](https://github.com/openai/codex/issues/46430) | 2026-09-18, open | `codex login` removes the existing `auth.json` before the flow can succeed, so a failed login logs the user out; especially painful on headless/remote hosts. |
| Codex CLI auth | [openai/codex #40839](https://github.com/openai/codex/issues/40839) | 2026-08-26, open | Windows, Codex CLI 0.145.0, enterprise subscription: browser OAuth reaches the localhost callback but the code exchange and device auth fail with `token_exchange_failed`. |
| Claude Code OAuth | [anthropics/claude-code #105729](https://github.com/anthropics/claude-code/issues/105729) | 2026-10-28, open | `--chrome-native-host` holds the OAuth refresh lock without a heartbeat; other Claude Code processes fail "Failed to refresh OAuth token" for up to 60 s, affecting headless stream-json sessions. |
| Claude Code OAuth | [anthropics/claude-code #18225](https://github.com/anthropics/claude-code/issues/18225) | 2026-01-14, open | OAuth token expiry caused repeated 401 "OAuth token has expired" errors mid-session and repeated `/login`. |
| Qwen OAuth retirement | [QwenLM/qwen-code #3281](https://github.com/QwenLM/qwen-code/issues/3281) | 2026-04-15, closed 2026-04-17 | OAuth reported success, but prompts failed with free-tier quota exceeded and the 2026-04-15 discontinuation notice. |
| Qwen OAuth docs | [QwenLM/qwen-code #3382](https://github.com/QwenLM/qwen-code/issues/3382) | 2026-04-17, closed 2026-07-01 | Feedback to update the Qwen OAuth docs section because the free tier was discontinued on 2026-04-15. |
| OpenCode Copilot | [anomalyco/opencode #46891](https://github.com/anomalyco/opencode/issues/46891) | 2026-09-02, closed 2026-10-19 | Accounts without Copilot entitlement appear connected but expose no models; v1 loops the connection flow and v2 gives no actionable explanation. |
| OpenCode Copilot | [anomalyco/opencode #11673](https://github.com/anomalyco/opencode/issues/11673) | 2026-02-01, closed same day | Copilot models stopped working after previously working; re-login did not help. |
| OpenCode Copilot | [anomalyco/opencode PR #44114](https://github.com/anomalyco/opencode/pull/44114) | 2026-08-22, closed 2026-10-10 | Requires OAuth for GitHub Copilot; prevents `GITHUB_TOKEN` from auto-activating the provider through generic environment auth. |

## Blocked, retired, and unsupported routes

| Route | Status | Evidence |
|---|---|---|
| Qwen OAuth free tier | Retired 2026-04-15; hard-coded discontinued provider in Qwen Code | VENDOR [Qwen auth](https://github.com/QwenLM/qwen-code/blob/main/docs/users/configuration/auth.md); ANECDOTE qwen-code #3281 |
| Gemini CLI for free individuals and AI Pro/Ultra | Retired 2026-06-18; Antigravity CLI is the replacement; Code Assist for GitHub gets no new installs | VENDOR [transition post](https://developers.googleblog.com/an-important-update-transitioning-gemini-cli-to-antigravity-cli/), [README](https://github.com/google-gemini/gemini-cli) |
| Claude Pro/Max OAuth inside third-party tools or API proxies | Prohibited by Anthropic; OpenCode removed bundled plugins in 1.3.0 | VENDOR [legal](https://code.claude.com/docs/en/legal-and-compliance.md), [OpenCode V1](https://opencode.ai/docs/providers/) |
| Anthropic consumer cookies/session tokens | Always blocked; not a supported credential shape | REPO `src/hutch/data/compat.json` consumer-plan-oauth record (2026-10-08) |
| SIWC against ChatGPT `backend-api` endpoints | Explicitly not allowed; use public Responses API | VENDOR [SIWC models](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference.md) |
| SIWC in a paid or remotely hosted app | Requires interest form; preview docs target open-source/local apps | VENDOR [SIWC overview](https://developers.openai.com/siwc/token-sharing-open-source.md) |
| Codex access tokens for Pro/Plus | Business and Enterprise workspaces only | VENDOR [access tokens](https://learn.chatgpt.com/docs/enterprise/access-tokens.md) |
| Kimi K2 series new users / `kimi-k2.5` / `moonshot-v1` | New users blocked 2026-10-31; full K2 retirement end of Dec 2026; k2.5 and moonshot-v1 discontinued 2026-08-31 | VENDOR [Kimi models](https://platform.kimi.ai/docs/models.md) |
| MiniMax-M3.1-Flash-Preview | Retired; old name served by M3.1-Flash | VENDOR [M Plan intro](https://platform.minimax.io/docs/m-plan/intro.md) |
| Z.AI Coding Plan in unsupported tools | Benefits may be restricted; >3 violations may be banned | VENDOR [usage policy](https://docs.z.ai/devpack/usage-policy.md) |
| Interactive Claude Code paid by monthly API credits | Explicitly excluded from the credit benefit | VENDOR [monthly credits](https://support.claude.com/en/articles/17154008-monthly-api-credits-for-max-ultra-and-team-plans) |
| Codex usage through API keys paid by ChatGPT API credits | Explicitly not supported by the benefit | VENDOR [API credits](https://developers.openai.com/api/docs/guides/chatgpt-api-credits.md) |
| OpenCode as a Hutch executor | Unavailable; permission events can be lost | REPO `docs/realignment/provider-compatibility.md` (2026-10-10) |
| Pi as a Hutch executor | Unavailable; no per-action approval hook, direct provider traffic | REPO `docs/realignment/provider-compatibility.md` |

## Sources and verification dates

| # | Source | URL | Fetched | Class | Used for |
|---|---|---|---|---|---|
| 1 | OpenAI API overview | https://developers.openai.com/api/reference/overview.md | 2026-10-30 | VENDOR | API auth, Bearer, WIF, propagation times |
| 2 | OpenAI API credits for ChatGPT subscribers | https://developers.openai.com/api/docs/guides/chatgpt-api-credits.md | 2026-10-30 | VENDOR | Plan-funded API credits, exclusions |
| 3 | OpenAI SIWC overview | https://developers.openai.com/siwc/token-sharing-open-source.md | 2026-10-30 | VENDOR | OSS/local scope, host IDs, paid/hosted form |
| 4 | OpenAI SIWC preview limitations | https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations.md | 2026-10-30 | VENDOR | Required/omitted fields and tools, app-server |
| 5 | OpenAI SIWC accounts and sessions | https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions.md | 2026-10-30 | VENDOR | Refresh/revocation, 5-hour sharing, Pro exception |
| 6 | OpenAI SIWC token reference | https://developers.openai.com/siwc/token-sharing-open-source/token-reference.md | 2026-10-30 | VENDOR | 1h access, 30d rotating refresh, claims |
| 7 | OpenAI SIWC self-hosted VMs | https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms.md | 2026-10-30 | VENDOR | VM credential transfer, attribution limits |
| 8 | OpenAI SIWC errors | https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery.md | 2026-10-30 | VENDOR | Eligibility/region/limit error codes |
| 9 | OpenAI SIWC models and inference | https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference.md | 2026-10-30 | VENDOR | Responses endpoint, backend-api prohibition |
| 10 | Codex authentication | https://learn.chatgpt.com/codex/auth.md | 2026-10-30 | VENDOR | Sign-in methods, API-key recommendation, auth cache, device code |
| 11 | Codex enterprise access tokens | https://learn.chatgpt.com/docs/enterprise/access-tokens.md | 2026-10-30 | VENDOR | Business/Enterprise automation tokens, expiry |
| 12 | Codex config reference | https://learn.chatgpt.com/docs/config-file/config-reference.md | 2026-10-30 | VENDOR | `cli_auth_credentials_store`, managed config |
| 13 | Claude Code authentication | https://code.claude.com/docs/en/authentication.md | 2026-10-30 | VENDOR | Auth precedence, setup-token, refresh-token provisioning |
| 14 | Claude Code environment variables | https://code.claude.com/docs/en/env-vars.md | 2026-10-30 | VENDOR | API key overrides subscription, OAuth variables |
| 15 | Claude Code legal and compliance | https://code.claude.com/docs/en/legal-and-compliance.md | 2026-10-30 | VENDOR | OAuth scope, third-party prohibition, hosting conditions |
| 16 | Claude Code feature availability | https://code.claude.com/docs/en/feature-availability.md | 2026-10-30 | VENDOR | Features requiring subscription, 3P variants |
| 17 | Use Claude Code with Pro/Max/Ultra | https://support.claude.com/en/articles/11145838-use-claude-code-with-your-pro-or-max-plan | 2026-10-30 | VENDOR | Limits, shared limits, wrap-up |
| 18 | Agent SDK with your Claude plan | https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan | 2026-10-30 | VENDOR | June 15 pause, Oct 7 credits note |
| 19 | Monthly API credits for Max/Ultra/Team | https://support.claude.com/en/articles/17154008-monthly-api-credits-for-max-ultra-and-team-plans | 2026-10-30 | VENDOR | Amounts, eligibility, coverage/exclusions |
| 20 | Anthropic authentication | https://platform.claude.com/docs/en/manage-claude/authentication.md | 2026-10-30 | VENDOR | Key types, WIF, App Attest |
| 21 | Anthropic API overview | https://platform.claude.com/docs/en/api/overview.md | 2026-10-30 | VENDOR | Base URL, headers, API list |
| 22 | Anthropic models overview | https://platform.claude.com/docs/en/about-claude/models/overview.md | 2026-10-30 | VENDOR | Current models and prices |
| 23 | Gemini API keys | https://ai.google.dev/gemini-api/docs/api-key | 2026-10-30 | VENDOR-SECONDARY | Standard/auth keys, 2026-05-28 change |
| 24 | Gemini OpenAI compatibility | https://ai.google.dev/gemini-api/docs/openai | 2026-10-30 | VENDOR | Compat endpoint, reasoning mapping |
| 25 | Gemini models | https://ai.google.dev/gemini-api/docs/models | 2026-10-30 | VENDOR-SECONDARY | Gemini 4 Argon and family |
| 26 | Gemini rate limits | https://ai.google.dev/gemini-api/docs/rate-limits | 2026-10-30 | VENDOR-SECONDARY | Per-project RPM/TPM/RPD |
| 27 | Gemini CLI transition announcement | https://developers.googleblog.com/an-important-update-transitioning-gemini-cli-to-antigravity-cli/ | 2026-10-30 | VENDOR | 2026-06-18 consumer cutoff |
| 28 | Gemini CLI README | https://github.com/google-gemini/gemini-cli | 2026-10-30 | VENDOR | Current status, auth options, no free tier |
| 29 | Antigravity authenticate | https://antigravity.google/docs/install.md | 2026-10-30 | VENDOR | OAuth, business/WIF, ADC, SSH flow |
| 30 | Antigravity CLI AI credits | https://antigravity.google/docs/cli/credits | 2026-10-30 | VENDOR | Subscription/credit integration |
| 31 | MiniMax prerequisites | https://platform.minimax.io/docs/guides/quickstart-preparation.md | 2026-10-30 | VENDOR | Keys, env shapes, base URLs |
| 32 | MiniMax models | https://platform.minimax.io/docs/guides/models-intro.md | 2026-10-30 | VENDOR | M3 models, H3 video, speech |
| 33 | MiniMax M Plan intro | https://platform.minimax.io/docs/m-plan/intro.md | 2026-10-30 | VENDOR | Tiers, supported tools, API keys |
| 34 | MiniMax M Plan FAQ | https://platform.minimax.io/docs/m-plan/faq.md | 2026-10-30 | VENDOR | Shared usage, windows, MiniMax Code |
| 35 | Kimi API quickstart | https://platform.kimi.ai/docs/get-your-api-key.md | 2026-10-30 | VENDOR | MOONSHOT_API_KEY, compatible APIs |
| 36 | Kimi model list | https://platform.kimi.ai/docs/models.md | 2026-10-30 | VENDOR | Current/deprecated models and dates |
| 37 | Kimi Code overview | https://www.kimi.com/code/docs/en/ | 2026-10-30 | VENDOR | Membership, third-party tools, API keys |
| 38 | Kimi Code FAQ | https://www.kimi.com/code/ | 2026-10-30 | VENDOR | Base URLs, billing pools, mismatch error |
| 39 | Qwen Code authentication | https://github.com/QwenLM/qwen-code/blob/main/docs/users/configuration/auth.md | 2026-10-30 | VENDOR | OAuth retirement, plans, endpoints, headless env |
| 40 | xAI quickstart | https://docs.x.ai/developers/quickstart.md | 2026-10-30 | VENDOR | XAI_API_KEY, api.x.ai base URL |
| 41 | xAI models | https://docs.x.ai/developers/models.md | 2026-10-30 | VENDOR | Grok IDs, context, prices |
| 42 | Grok Build overview | https://docs.x.ai/build/overview.md | 2026-10-30 | VENDOR | CLI install, browser auth, API key path |
| 43 | Grok Build headless | https://docs.x.ai/build/cli/headless-scripting.md | 2026-10-30 | VENDOR | `-p`, output formats, ACP, auto-approve |
| 44 | Grok Build enterprise | https://docs.x.ai/build/enterprise.md | 2026-10-30 | VENDOR | Hosts, config precedence, proxies |
| 45 | X Subscription pricing | https://docs.x.ai/x-subscription/pricing.md | 2026-10-30 | VENDOR | Plan prices, Grok Bot inclusion |
| 46 | X Subscription usage limits | https://docs.x.ai/x-subscription/usage-limits.md | 2026-10-30 | VENDOR | First-party-only weekly pool, top-ups |
| 47 | Z.AI quick start | https://docs.z.ai/guides/overview/quick-start.md | 2026-10-30 | VENDOR | Standard key, endpoint, GLM-5.3 |
| 48 | Z.AI pricing | https://docs.z.ai/guides/overview/pricing.md | 2026-10-30 | VENDOR | Per-token prices, tools |
| 49 | Z.AI Coding Plan overview | https://docs.z.ai/devpack/overview.md | 2026-10-30 | VENDOR | Tiers, credits, supported models |
| 50 | Z.AI Coding Plan quick start | https://docs.z.ai/devpack/quick-start.md | 2026-10-30 | VENDOR | Three endpoints, supported tools |
| 51 | Z.AI usage policy | https://docs.z.ai/devpack/usage-policy.md | 2026-10-30 | VENDOR | Supported tools only, sharing ban, violations |
| 52 | Z.AI API key management notice | https://docs.z.ai/devpack/notice/api-key-management.md | 2026-10-30 | VENDOR | 2026-10-16 key separation and billing |
| 53 | OpenCode providers (V1) | https://opencode.ai/docs/providers/ | 2026-10-30 | VENDOR | auth.json path, Claude Pro/Max prohibition, Copilot |
| 54 | OpenCode providers (V2) | https://opencode.ai/v2/docs/providers/ | 2026-10-30 | VENDOR | ChatGPT sign-in, Copilot device OAuth, context caps |
| 55 | OpenCode CLI providers (V2) | https://opencode.ai/v2/docs/cli/providers/ | 2026-10-30 | VENDOR | Auth methods, env vs saved-account precedence |
| 56 | OpenCode Go (V2) | https://opencode.ai/v2/docs/console/go/ | 2026-10-30 | VENDOR | Pricing, keys, traffic rules, validated clients, models |
| 57 | OpenCode Go (V1) | https://opencode.ai/docs/go/ | 2026-10-30 | VENDOR | Plan description and request identity |
| 58 | OpenClaw Claude Max proxy | https://docs.openclaw.ai/providers/claude-max-api-proxy | 2026-10-30 | Community doc / ANECDOTE | Proxy mechanism, "not officially sanctioned" warning |
| 59 | GitHub Copilot SDK GA | https://github.blog/changelog/2026-06-02-copilot-sdk-is-now-generally-available/ | 2026-10-30 | VENDOR | Official programmatic Copilot path |
| 60 | GitHub Additional Product Terms | https://docs.github.com/en/site-policy/github-terms/github-terms-for-additional-products-and-features | 2026-10-30 | VENDOR | Terms page location; Copilot clause not isolated (UNVERIFIED) |
| 61 | claude-code #105729 | https://github.com/anthropics/claude-code/issues/105729 | 2026-10-30 | ANECDOTE | OAuth refresh lock stalls other processes |
| 62 | claude-code #18225 | https://github.com/anthropics/claude-code/issues/18225 | 2026-10-30 | ANECDOTE | Repeated 401 after OAuth expiry |
| 63 | codex #46430 | https://github.com/openai/codex/issues/46430 | 2026-10-30 | ANECDOTE | Failed login deletes auth.json |
| 64 | codex #40839 | https://github.com/openai/codex/issues/40839 | 2026-10-30 | ANECDOTE | Windows token exchange/device auth failure |
| 65 | qwen-code #3281 | https://github.com/QwenLM/qwen-code/issues/3281 | 2026-10-30 | ANECDOTE | OAuth "success" then free-tier quota error |
| 66 | qwen-code #3382 | https://github.com/QwenLM/qwen-code/issues/3382 | 2026-10-30 | ANECDOTE | Docs feedback on retired OAuth section |
| 67 | opencode #46891 | https://github.com/anomalyco/opencode/issues/46891 | 2026-10-30 | ANECDOTE | Copilot account without entitlement appears connected |
| 68 | opencode #11673 | https://github.com/anomalyco/opencode/issues/11673 | 2026-10-30 | ANECDOTE | Copilot models stopped working |
| 69 | opencode PR #44114 | https://github.com/anomalyco/opencode/pull/44114 | 2026-10-30 | ANECDOTE | OAuth required for Copilot; env token no longer activates it |
| 70 | Repo: multi-provider platform review | docs/research/multi-provider-platform-review-2026-10-10.md | reviewed 2026-10-10 | REPO | Existing verification boundary, no live accounts |
| 71 | Repo: provider compatibility matrix | docs/realignment/provider-compatibility.md | reviewed 2026-10-10 | REPO | Consumer OAuth blocked, OpenCode Go experimental, SIWC experimental |
| 72 | Repo: offerings and failures | docs/research/offerings-and-failures.md | sources read 2026-10-07 | REPO | Existing complaint citations, reused only as context |
| 73 | Repo: compat data | src/hutch/data/compat.json | reviewed 2026-10-10/11 | REPO | Route states, evidence URLs |
| 74 | Repo: connection templates | src/hutch/data/connections.json | read 2026-10-30 | REPO | OpenCode Go base URLs and terms notice |

## What remains UNVERIFIED (do not promote to facts)

- Any live inference, streaming, tool-calling, billing, or quota outcome for any
  provider in this fragment. No provider account or key was used.
- OpenAI SIWC eligibility and permitted-region list; region gating itself is
  documented only as a 403 error.
- OpenAI ambient `OPENAI_API_KEY` precedence inside Codex CLI (cached login vs env).
- Gemini CLI precedence between cached Google login and environment keys;
  Antigravity token lifetimes, exact quota numbers, and whether the Antigravity
  backend is usable outside first-party clients.
- MiniMax China platform hosts and plan terms; MiniMax unattended-use policy.
- Kimi Code plan tiers/prices; whether membership quota covers unattended agents;
  the full supported third-party tool list beyond docs navigation.
- Qwen Token Plan/Coding Plan quota numbers and plan terms for automated agents.
- xAI: whether Grok Build headless draws from the X Subscription pool or API
  credits; whether third-party consumption is permitted; xAI API terms on
  automated use were not read.
- Z.AI: explicit treatment of unattended/scheduled workloads (the supported-tools
  clause is the only textual basis).
- GitHub Copilot: whether GitHub authorizes OpenCode's device-OAuth Copilot reuse.
  GitHub terms were not isolated; the Copilot SDK is the only documented
  programmatic path found.
- Anthropic subscription OAuth access/refresh token lifetimes (docs describe
  refresh behavior but not duration).
- OpenCode Go exact inference base URL on the V2 page.
- Provider prices and model catalogs are snapshots and several are actively
  retiring models.
