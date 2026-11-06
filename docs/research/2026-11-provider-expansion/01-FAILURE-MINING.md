# 01 - Failure mining: provider, auth, routing and media (2026-11)

Date: 2026-11-06. Extends `docs/research/2026-10-provider-platform/02-FAILURES-AND-COMPLAINTS.md`;
it does not replace it. Purpose: each Hutch fix in this initiative answers a documented failure.
Evidence grades are stated. A single issue is one report, not a prevalence estimate; vendor docs are
fact for that vendor's current text only.

## What was mined

- Prior Hutch research (2026-10 package) and `docs/research/complaints.md`.
- Current vendor terms and provider pages (Anthropic, Google, OpenAI, Qwen, Z.AI, OpenClaw).
- Issue trackers and practitioner reports for Claude Code, Codex, LiteLLM, OpenRouter, Ollama,
  LM Studio, Runway/fal/MiniMax, and agent clients (OpenClaw, Hermes, Open WebUI).

Classification: **F** = fixable in Hutch, **M** = mitigable, **V** = vendor-side (record and
surface, do not paper over).

## Authentication and token lifecycle

| Failure | Evidence | Class | Hutch answer | Test idea |
|---|---|---|---|---|
| Concurrent processes race on one refresh token; the loser loses auth | claude-code issues #27933, #43392, #25609; codex app-server #10332 (GitHub / mirrors, 2026) | F | Single-flight refresh per account, no process-wide lock, failed refresh never deletes the credential; expose expired state instead of a fake connected badge. | Spawn N real worker processes contending for one account; exactly one refresh, all others reuse the result, zero credential deletion. |
| Failed login deletes a working credential | prior codex report #46430 (ANECDOTE) | F | Disconnect is explicit and separate; a failed sign-in leaves the stored credential and reports why. | Inject a failing token exchange and assert the previous credential file is byte-identical. |
| Headless/remote/WSL sign-in fails or the loopback callback port is in use | codex-auth writeups (device-code flow); prior WSL report | F | Device-code flow where the vendor documents one; loopback callback retries a bounded port range and says which layer failed. | Run the flow with the callback port occupied; assert a typed failure or a successful fallback, never a hang. |
| Ambient `ANTHROPIC_API_KEY` silently bills the API org instead of the subscription | claude-code issue #12352; community billing guides (ANECDOTE, VENDOR-SECONDARY) | F | Connection-scoped credentials; ambient keys only for exact official hosts; the resolved account is shown before the first send. | With a subscription account and an ambient key present, assert the chosen account is named and no request is sent without confirmation. |
| "Connected" badge survives token expiry | prior claude-code #18225 | F | Readiness distinguishes needs-auth, expired, subscription-restricted; a status is computed from local facts, never from a listing. | Freeze an expired token and assert `/api/v1/provider-readiness` says `authentication_expired`. |
| Third-party reuse of subscription OAuth is prohibited and enforced | Anthropic legal (OAuth exclusively for native apps; no third-party login/token routing); Gemini CLI terms (third-party CLI OAuth is a violation); Qwen OAuth retired 2026-04-15 | V | Ship the route as blocked/retired with the citation; permit only the official unmodified CLI with the user's own sign-in where the vendor allows it. | Catalogue/readiness test: blocked routes cannot be selected or silently enabled. |

## Model selection, gateways and billing attribution

| Failure | Evidence | Class | Hutch answer | Test idea |
|---|---|---|---|---|
| Model list is stale, wrong, or shows models the key cannot use | LiteLLM model-discovery docs ("a listed model can still fail with a given user's key"); LiteLLM #865, #13366; Open WebUI reports | F | Listing proves discovery only; capability and eligibility stay unverified; the model actually returned is recorded. | A scripted endpoint lists a model that then 404s; readiness must say `model_unavailable`, not `available`. |
| Gateway silently serves a different model or provider | OpenRouter fallback/routing docs; benchmark report showing the same id behaving differently per backend | F/M | Record requested vs served model; per-route failure never reroutes without consent; gateway is a distinct identity. | Scripted gateway returns a different `model`; transcript must show the substitution and no automatic credit. |
| Gateway fallback bills an unexpected payer (BYOK → system credential) | prior Vercel AI Gateway vendor docs; Hermes #24029 (ANECDOTE) | F | Gateway identities are separate; fallback never crosses billing relationship without approval; receipts name who paid. | Two accounts, one ambient key; assert fallback is refused or requires explicit opt-in. |
| Alias model hides a different upstream model | LiteLLM docs; prior research | M | Scope price and capability to the gateway route; show the served model. | Alias route test asserts the returned model is stored and displayed. |
| Regional/plan hosts look alike but bill differently (global vs CN, standard vs Coding Plan) | OpenClaw provider pages (MiniMax global/CN, Xiaomi SGP/CN/AMS, Tencent TokenHub/TokenPlan, Z.AI global/CN) | F | One route per billing surface in templates; the wizard names the host and billing relationship before saving. | Each regional template resolves to a distinct template id and readiness subject. |

## Rate limits, quota and retries

| Failure | Evidence | Class | Hutch answer | Test idea |
|---|---|---|---|---|
| Retry storm on 429; Retry-After ignored; quota vs rate vs billing conflated | practitioner guides (2026): 429s count against limits; Retry-After is documented by Anthropic/OpenAI | F | Parse Retry-After, retry at most the built-in adapter's single bounded retry, and label quota/rate/billing distinctly. | Scripted 429 with Retry-After; assert one bounded retry and a typed error that names the class. |
| Subscription quota exhaustion looks like an API rate limit | Codex CLI rate-limit writeups | M/V | Readiness and errors distinguish subscription restriction from per-token rate limiting. | Provider returns plan-quota error; assert `subscription_restricted`. |
| Interrupted stream omits final usage, so cost looks zero | existing compat notes | F | Missing usage is unknown, never zero; reservations stay held for reconciliation. | Truncate a stream before the usage chunk; assert cost basis is "unknown/reserved". |

## Tool calls, reasoning and streaming

| Failure | Evidence | Class | Hutch answer | Test idea |
|---|---|---|---|---|
| Tool schema rejected per provider (strict mode, unsupported keywords, empty arrays, parallel calls) | prior compat fixture work; OpenClaw proxy shaping rules | F | Canonical schema lowered per adapter; rejected schema fails the run with the provider's reason, no silent downgrade. | Invalid tool schema on each adapter is refused before dispatch. |
| Reasoning content lost on the streamed path | Hutch live Xiaomi run (2026-10-31): `reasoning_content` deltas discarded until fixed | F | Assembler keeps reasoning deltas; batched and streamed calls report the same content. | Stream with reasoning deltas and assert they survive assembly. |
| Custom OpenAI-compatible proxies reject `developer` role or vendor beta headers | OpenClaw proxy-route shaping docs | M | Proxy routes suppress native-only fields; explicit capability declarations per route. | Custom OpenAI route never sends `developer`; custom Anthropic route never sends Anthropic beta flags. |
| Empty stream / dropped deltas / hang | prior OpenCode #25657; practitioner reports | F | Bounded first-event budgets; incomplete stream is reported incomplete, not finished. | Scripted stream that closes without a completion marker. |

## Local engines and custom endpoints

| Failure | Evidence | Class | Hutch answer | Test idea |
|---|---|---|---|---|
| Ollama OpenAI-compatible endpoint silently truncates context; `num_ctx` ignored | multiple 2026 guides; prior OPENCLAW issue #4028 | F | Native Ollama route sets `num_ctx`; a fit/window warning refuses or warns instead of truncating. | Route an Ollama-shaped URL through the OpenAI path and assert it is redirected to native or warned. |
| Model not loaded / cold start presented as an error | LM Studio native load/evict docs; practitioner reports | F | Surface not-loaded and cold-start as states; native discovery on LM Studio; bounded wait. | LM Studio stub reports no loaded model; readiness says `model_unavailable` with "load it" action. |
| Custom base URL pitfalls: trailing `/v1`, path rewriting, self-signed TLS, SSRF | prior research; OpenClaw guarded-fetch docs (private ranges, fake-IP ranges, exact-origin trust) | F | Layered connectivity test naming DNS/TLS/auth/model-list/completion; scheme and `/v1` normalization; redirect refusal; private-range allowlist outside Strict Offline. | Each layer fails in turn and the message names that layer only. |
| No-auth remote LAN/tailnet server treated as misconfigured | OpenClaw custom-provider docs (`auth: "none"` for private-but-remote) | M | Explicit no-auth option scoped to the configured origin, never global. | Remote no-auth endpoint requires explicit opt-in and never receives a key. |

## Media, speech and search

| Failure | Evidence | Class | Hutch answer | Test idea |
|---|---|---|---|---|
| Async job never resolves; polling has no bound | Runway/fal monitoring guides; prior research | F | Durable job records with bounded polling, cancellation and a terminal unknown state. | Job that stays queued forever reaches a terminal timeout state. |
| Result URLs expire before retrieval | prior vendor docs (fal ~1h, MiniMax ~9h, xAI ephemeral) | F | Fetch and store bytes immediately with SHA-256; never persist a URL as the result. | Serve a 404 after success; stored artifact must already exist. |
| Huge files loaded in memory; silent format conversion | prior research | F | Bounded sizes and streamed storage; format is reported, never silently changed. | Oversize result is refused with the limit named. |
| Moderation refusal presented as a crash and billed as FAILED | Runway docs; prior research | F | Show content-policy refusal as a refusal and state whether the provider billed. | Provider returns policy refusal; UI says refused, cost basis "possibly billed". |
| Streaming TTS/video/music deferred or unavailable | prior research; MiniMax music notice | V | Record retired/unavailable routes; do not stub paid dead APIs. | Blocked route cannot be selected. |

## Hutch's own defects found in this audit

| Defect | Evidence | Fix |
|---|---|---|
| Providers page hardcodes a live-evidence sentence that omits Xiaomi and mislabels documented/blocked routes | `server/templates/providers.html:18` vs `capabilities.py` and the 2026-10 matrix | Phase 1: generate the sentence from live evidence and integration statuses. |
| Preset digest test hashed `Bot.archived`, so it failed after the field was added even though preset content was unchanged | `tests/test_catalog.py` baseline run | Fixed in Phase 0 by excluding `archived`; content equality proven against the pre-change field set. |
| Google `coding_cli` service tag is stale after Gemini CLI → Antigravity (2026-06-18) | catalogue vs Gemini CLI notice | Phase 3c: correct the service claim; do not implement prohibited third-party OAuth. |
| Light-theme visual gate cannot be met because the workspace is dark-only | Providers/Models/Chat captures identical in both schemes; `app.js` says the theme is fixed | Phase 7 decision: add a light theme or scope the gate honestly. |

## Sources (accessed 2026-11-06)

- Anthropic, [Legal and compliance - Claude Code](https://code.claude.com/docs/en/legal-and-compliance) - OAuth only for subscription purchasers/native apps; no third-party credential routing; official CLI sign-in permitted.
- Google, [Gemini CLI: License, Terms of Service, and Privacy Notices](https://geminicli.com/docs/resources/tos-privacy/) - third-party use of Gemini CLI OAuth is a terms violation; Gemini CLI replaced by Antigravity CLI on 2026-06-18.
- OpenAI, [Sign in with ChatGPT](https://developers.openai.com/siwc/token-sharing-open-source) and [Codex app-server](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server) - documented open-source SIWC and app-server routes.
- OpenClaw, [Provider directory](https://docs.openclaw.ai/providers), [Official provider plugins](https://docs.openclaw.ai/concepts/model-providers/official-provider-plugins), [Custom providers and local runtimes](https://docs.openclaw.ai/concepts/model-providers/custom-providers) - feature checklist, provider variants, proxy shaping rules, LM Studio native discovery.
- Claude Code issues [#27933](https://github.com/anthropics/claude-code/issues/27933), [#43392](https://github.com/anthropics/claude-code/issues/43392), [#25609](https://github.com/anthropics/claude-code/issues/25609), [#12352](https://github.com/anthropics/claude-code/issues/12352) - refresh races, logout loops, ambient-key billing.
- Codex app-server refresh race report, [codexissues #10332](https://codexissues.com/issue/10332-race-condition-in-oauth-token-refresh-causes-refresh-token-was-already-used-erro).
- Qwen, [qwen-code auth docs](https://github.com/QwenLM/qwen-code/blob/main/docs/users/configuration/auth.md) and [issue #3316](https://github.com/QwenLM/qwen-code/issues/3316) - OAuth free tier discontinued 2026-04-15.
- Z.AI, [Claude Code overview](https://docs.z.ai/devpack/tool/claude), [OpenCode overview](https://docs.z.ai/scenario-example/develop-tools/opencode) - Coding Plan is scoped to supported agents.
- MiniMax, [Other tools](https://platform.minimax.io/docs/token-plan/other-tools) - custom OpenAI/Anthropic-compatible endpoints for coding tools.
- Moonshot/Kimi, [Kimi Code FAQ](https://www.kimi.com/en/help/kimi-code/faq) - Kimi Code membership and the Kimi Platform use different base URLs; keys must match.
- xAI, [Terms of Service](https://x.ai/legal/terms-of-service) - consumer/API boundary.
- LiteLLM, [Model discovery](https://docs.litellm.ai/docs/proxy/model_discovery), issues [#865](https://github.com/BerriAI/litellm/issues/865), [#13366](https://github.com/BerriAI/litellm/issues/13366) - key-scoped listing differs from deployment listing.
- OpenRouter, [Model fallbacks](https://openrouter.ai/docs/guides/routing/model-fallbacks) - automatic fallback on rate limits/downtime/moderation.
- Ollama context: [runaihome](https://runaihome.com/blog/ollama-truncating-input-prompt-num-ctx-fix-2026/), [particula](https://particula.tech/blog/ollama-num-ctx-silent-prompt-truncation), [betterclaw](https://www.betterclaw.io/blog/ollama-context-window-truncates-agent-config) - silent truncation and the OpenAI-compatible trap.
- 429 handling: [developersdigest](https://www.developersdigest.tech/blog/ai-api-rate-limit-retry-guide-2026), [string.ink](https://www.string.ink/blog/rate-limits-backoff-and-retry-budgets/), [usagebox](https://usagebox.com/articles/does-a-429-count-against-your-rate-limit-2026) - Retry-After, retry budgets, quota vs rate.
- Media: [fal Queue API](https://fal.ai/docs/documentation/model-apis/inference/queue), [Runway troubleshooting](https://docs.dev.runwayml.com/errors/troubleshooting/), [Runway monitoring guide](https://apistatuscheck.com/blog/runway-api-monitoring-guide), [MiniMax timeout handling](https://wavespeed.ai/blog/minimax-h3/minimax-h3-api-timeout-errors/).
- Prior package: `docs/research/2026-10-provider-platform/02-FAILURES-AND-COMPLAINTS.md` and `03-PROVIDER-CAPABILITY-MATRIX.md` (2026-10-30/31 evidence).
