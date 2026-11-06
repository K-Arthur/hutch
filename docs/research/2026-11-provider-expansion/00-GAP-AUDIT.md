# 00 - Gap audit: provider, runtime and media expansion (2026-11)

Date: 2026-11-06. Phase 0 of `docs/realignment/provider-expansion-2026-11/`. This is a diagnosis,
not a support claim: a catalogue row is not a working route, and no status below was upgraded by
reading code or docs.

## Method

- Read the validated catalogue (`src/hutch/data/providers.json` via `providers/catalog.py`), the 38
  connection templates (`data/connections.json`), the route contract (`data/compat.json`), readiness
  (`providers/readiness.py`), the runtime registry and the prior research package
  (`docs/research/2026-10-provider-platform/`).
- Re-ran the baseline (below) and captured the real first-run Providers, Models and Chat pages with
  Playwright at 360/768/1280/1920 in light and dark (24 screenshots,
  `docs/realignment/artifacts/provider-expansion-2026-11/phase0/`).
- Checked each family against its current vendor or OpenClaw page and the vendors' own terms; every
  source is dated in `01-FAILURE-MINING.md` and in the rows below. OpenClaw is used as a feature
  checklist only; Hutch does not copy its naming or behavior.

## Baseline (before any change)

| Check | Result |
|---|---|
| `npm run check:agent` | Passed: context hygiene (1040 files, 117 frozen over-cap), 47 tool contracts, constitution, agent map. |
| Focused provider/media tests (26 files) | 433 passed, 1 failed: `tests/test_catalog.py::test_the_presets_came_out_of_code_unchanged`. |
| Cause of that failure | `Bot` gained the `archived` field after the preset digests were recorded. Recomputing with the pre-change field set reproduces every recorded digest, so preset content is unchanged; the test hashed lifecycle state. Fixed by excluding `archived` from the digest (test-only, no product change). |
| Real server, empty state | `hutch init` + `hutch serve --port 18890` on a temporary state dir; `/providers`, `/models`, `/#/chat` all 200. |
| Visual capture | 24/24 captures: 0 console errors, 0 failed requests, 0 px horizontal overflow. |

## Cross-cutting findings

Ordered by what blocks the initiative. IDs are referenced by the backlog and later phases.

| ID | Finding | Evidence | Phase |
|---|---|---|---|
| G1 | The Providers page hardcodes "Two owner-authorized routes were live-verified on 2026-10-30 ... Every other hosted route remains implemented-unverified". That is false in two directions: it omits the 2026-10-31 Xiaomi live evidence (text, tools, streaming, STT, TTS) and calls documented/blocked/deferred/experimental routes "implemented-unverified". | `server/templates/providers.html:18`; `capabilities.py`; `03-PROVIDER-CAPABILITY-MATRIX.md` | 1 |
| G2 | Kimi Coding is not a provider identity. It is an auth method on `moonshot`, with no separate base URL/template, while the vendor ships it as a distinct Anthropic-compatible platform (`KIMI_API_KEY`, `kimi/kimi-for-coding`). | `providers.json` (`moonshot`), `connections.json`; OpenClaw custom-providers | 3e |
| G3 | `qwen` is documented-only: no Cloud or Coding Plan template, and the Portal OAuth free tier ended 2026-04-15. The retired status is correct; the missing part is any working route. | catalogue; Qwen auth docs and issue #3316 | 3g |
| G4 | Anthropic has no Claude CLI delegate. Anthropic permits OAuth only for native apps and forbids third-party token reuse; it does permit an end user to sign the unmodified official CLI in. Hutch may delegate to that CLI, never import its token. | Anthropic legal; OpenClaw Anthropic page | 3b |
| G5 | OpenAI has no Codex native runtime (app-server) and the Sign in with ChatGPT route is still `experimental` with an unconfirmed eligibility claim. OpenAI documents SIWC and the Codex app-server for open-source apps. | OpenAI SIWC docs; `compat.json` `sign-in-with-chatgpt` | 3a |
| G6 | Google's `coding_cli` service tag is stale: Google replaced Gemini CLI with Antigravity CLI on 2026-06-18, and Google explicitly treats third-party use of Gemini CLI OAuth as a terms violation. The blocked OAuth status is right; the CLI service claim and the roadmap need correcting. | Gemini CLI terms; Google blog notice | 3c |
| G7 | xAI has no Grok OAuth route (documented only) and no search/image/video/speech adapters in the catalogue path. | catalogue; OpenClaw xAI page | 3d |
| G8 | MiniMax Coding Plan OAuth is documented only; plan/portal identities are missing; media/video/music/speech have no adapter. | catalogue; MiniMax "Other Tools" docs | 3f |
| G9 | Z.AI Coding Plan quota is limited to supported agents (Claude Code, Cline, OpenCode, Cursor, ZCode, OpenClaw). Hutch is not on that list, so treating a Coding Plan key as a general route would be a policy error. | Z.AI docs; third-party plan summaries | 3h |
| G10 | OpenCode has a managed runtime but no OpenCode Zen API-key route separate from the CLI, and the recorded live evidence names CLI v2.0.24 while the host now reports v2.2.5. Re-verify in 3i rather than extending the old claim. | `runtime/registry.py`; Providers page runtime card | 3i |
| G11 | Bedrock, Bedrock Mantle, Google Vertex, Anthropic Vertex and Microsoft Foundry have no auth path, template or model discovery. The owner approved both dependency families; the adapters still do not exist. | catalogue; `data/connections.json` | 4 |
| G12 | Custom endpoints still lack scheme/`/v1` normalization, TLS policy, redirect refusal and DNS-rebinding pinning outside Strict Offline. A private-range allowlist is recorded, not implemented. | `docs/provider-platform.md` known limits | 5 |
| G13 | LM Studio is treated as generic OpenAI-compatible. The vendor has native `/api/v1/models` discovery and load/evict lifecycle; Hutch cannot list loaded models or surface not-loaded/cold-start states. | OpenClaw LM Studio page; `registry.py` | 5 |
| G14 | Media is mostly research-only: fal deferred; Runway/PixVerse/Vydra/Deepgram/ElevenLabs documented; only ComfyUI and speech have code. Jobs exist but resumability, cancellation and cost preview are unproven. | catalogue; `media/` | 6 |
| G15 | Models and first-run still disagree (S2): both say "OpenCode is ready with 10 model options" while `/models` also says "No model routes saved yet" and "No default route". The page explains the difference, but the two sentences remain contradictory. | `models-light-1280.png`; `first-run-light-1280.png`; start-state audit S2 | 7 |
| G16 | The workspace theme is dark-only by product decision ("The dark workspace theme is fixed"). The light captures are byte-for-byte a dark UI. The master prompt's "light and dark" visual gate cannot be met in-app without a light theme; decide in Phase 7. | `app.js` Appearance panel; captured screenshots | 7 |
| G17 | The Providers page at 1280 px is 13,279 px tall (62 cards, search/filter only) and at 360 px is longer still. Breadth is not a support claim, but the page needs a route-level view rather than a wall of identities. | capture `results.json` document height; `providers-light-1280.png` | 7 |
| G18 | Catalogue and price/connection data are dated 2026-10-30 and 2026-10-07. Model IDs in the ecosystem have moved (OpenClaw lists `gpt-6-astra`, `claude-opus-5-5`, `gemini-4-argon`, `kimi-k2.7-code`); Hutch's templates were not re-reviewed for 2026-11. | `providers.json` `reviewed_on`; `connections.json` header; OpenClaw pages | 3-4 |

## Missing or wrongly modeled identities

These are in the owner's scope but are absent as identities (an auth method on another provider is
not the same as a provider with its own billing, endpoint and terms).

| Identity | Today | Needed |
|---|---|---|
| `kimi-coding` (Kimi Code membership) | Auth method `kimi-coding-key` on `moonshot` | Own catalogue entry, Anthropic-compatible endpoint, `KIMI_API_KEY`, region-matched base URL, separate billing. |
| `opencode-zen` (OpenCode API) | Folded into the managed `opencode` CLI runtime | Own API-key route distinct from `opencode-go` and from managed CLI sign-in. |
| Claude CLI delegate | Service tag only | Runtime descriptor `claude-code` is `documented`; needs a governed executor contract (approvals, budget, cancellation) before enabling. Do not reuse tokens. |
| Codex native runtime | Absent | Codex app-server harness using SIWC credentials; explicit runtime selection, no ambient key. |
| Antigravity CLI (Google) | Not modeled | Decide whether to support; Gemini CLI OAuth is prohibited for third parties. |
| `minimax-portal` / Coding Plan identity | Auth method only | Separate subscription identity and endpoint, with the plan terms acknowledged. |
| `volcengine-plan`, `byteplus-plan` | Standard surfaces only | Coding-plan endpoint mapping as separate routes. |
| `qwen` Cloud / Coding Plan | Documented only | Adapter + template; Portal OAuth stays retired. |
| Azure Speech, Baseten, Featherless, Gradium, Kie AI, Levanto Sage, Liquid AI, Liquid Inference, llmman, LongCat, Neon AI Gateway, oMLX, Particle, Perplexity search, Poolside, Radius, Requesty, Rerank, SenseAudio, Telnyx, Abliteration | Absent | Out of the owner's list. Record as deferred; do not add speculatively. |

## Catalogue audit (62 entries)

Columns: route = connection templates (none means no code path); status = catalogue integration
status; missing = what a person would still lack; ToS = recorded stance, not legal advice;
credential = what the owner reported as provisioned.

| Provider | Route | Protocol | Status | Missing now | ToS stance | Live credential |
|---|---|---|---|---|---|---|
| openai | openai-api, chatgpt-plan | openai-chat, openai-responses | implemented-unverified | ChatGPT/Codex native runtime and Codex app-server execution absent; Responses adapter exists but no live check; model list eligibility by plan unproven. | API terms per-token; ChatGPT route allowed only through the official Sign in with ChatGPT flow (store=false). | provisioned (API key and/or ChatGPT plan) |
| anthropic | anthropic-api | anthropic | implemented-unverified | No Claude Code CLI delegate; no live check; model discovery exists but untested. | API terms per-token; Anthropic permits OAuth only for native apps and prohibits third-party token reuse. Official unmodified Claude Code CLI sign-in is permitted. | provisioned (API key; CLI sign-in unconfirmed) |
| google | google-gemini | gemini | implemented-unverified | Consumer/CLI OAuth correctly blocked; Google replaced Gemini CLI with Antigravity (2026-06-18) so the `coding_cli` service tag is stale; no media/voice adapters; no live check. | Gemini API terms; Google explicitly prohibits third-party use of Gemini CLI OAuth (account suspension risk), so that route stays blocked. | provisioned (Gemini API key) |
| minimax | minimax | openai-chat, anthropic, custom | implemented-unverified | Coding Plan OAuth not implemented (documented only); media/video/music/speech absent; no live check. | PAYG API terms; plan/subscription keys are a separate billing relationship. Vendor documents custom OpenAI/Anthropic endpoints for coding tools. | none |
| moonshot | moonshot | openai-chat, anthropic | implemented-unverified | Kimi Coding is only an auth method here, not a separate identity/base URL; no Kimi Code connection template; no live check. | PAYG API terms per-token; Kimi Code membership uses a different base URL and key, region-matched. | none |
| qwen | none | openai-chat, anthropic | documented | Whole provider documented-only: no adapter/template for Cloud or Coding Plan; Portal OAuth retired 2026-04-15 (correctly recorded). | Coding Plan endpoint mapping; OAuth free tier discontinued 2026-04-15. | none |
| xai | xai | openai-chat, custom | implemented-unverified | Grok OAuth not implemented; no media/speech/search adapters; no live check. | API terms per-token; SuperGrok/X Premium OAuth is xAI's recommended path but Hutch has no recorded policy review for third-party use. | none |
| zai | zai | openai-chat, anthropic | implemented-unverified | Coding Plan auth documented only; no China variant split; no live check. | Coding Plan quota is limited to supported agents (Claude Code, Cline, OpenCode, Cursor, ZCode, OpenClaw); Hutch is not listed, so confirm before enabling. | none |
| opencode | none | openai-chat, anthropic | implemented | Managed runtime works, but no OpenCode Zen API-key route separate from the CLI; live evidence is DeepSeek only and CLI v2.0.24-era. | OpenCode's own terms; CLI-managed credentials stay in the CLI. | none |
| opencode-go | opencode-go | openai-chat, anthropic | experimental | No live check of plan eligibility, quotas or unattended-use terms. | Requires typical coding-agent traffic, own User-Agent and stable session id; unattended use not confirmed. | none |
| mistral | mistral | openai-chat | implemented-unverified | No live account has exercised this route; per-model capability evidence absent. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| deepseek | deepseek | openai-chat, anthropic | implemented | Live verification recorded for the exercised route only; other models/capabilities unproven. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| github-copilot | none | custom | blocked | Blocked. No vendor-documented third-party subscription reuse; do not recreate. | Prohibited/undocumented third-party subscription reuse; route blocked. | none |
| alibaba-model-studio | none | openai-chat | documented | No code path (adapter/template); research only. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| xiaomi | xiaomi-token-plan-sgp, xiaomi-token-plan-cn, xiaomi-token-plan-ams, xiaomi | openai-chat, anthropic | implemented | Live verification recorded for the exercised route only; other models/capabilities unproven. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| stepfun | stepfun | openai-chat | implemented-unverified | No live account has exercised this route; per-model capability evidence absent. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| volcengine | volcengine | openai-chat, custom | implemented-unverified | No live account has exercised this route; per-model capability evidence absent; no coding-plan surface. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| tencent-cloud | tencent-cloud | openai-chat | implemented-unverified | No live account has exercised this route; per-model capability evidence absent; no TokenPlan surface. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| qianfan | none | custom | documented | No adapter or template; OAuth and custom protocol unverified. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| cohere | cohere | openai-chat | implemented-unverified | No live account has exercised this route; per-model capability evidence absent. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| synthetic | synthetic | openai-chat | implemented-unverified | Template uses OpenAI Chat, but the vendor also documents an Anthropic-compatible endpoint; route choice unverified. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| venice | venice | openai-chat | implemented-unverified | No live account has exercised this route; per-model capability evidence absent. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| arcee | arcee | openai-chat | implemented-unverified | No live account has exercised this route; per-model capability evidence absent. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| vydra | none | custom | documented | Documented-only media; no adapter. | Vendor media API terms; consent and content-policy requirements apply. | none |
| gmi-cloud | gmi-cloud | openai-chat | implemented-unverified | No live account has exercised this route; per-model capability evidence absent. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| claude-max-proxy | none | anthropic | blocked | Blocked. Anthropic prohibits third-party subscription OAuth; do not recreate. | Prohibited/undocumented third-party subscription reuse; route blocked. | none |
| bedrock | none | custom | documented | No SigV4 adapter, credentials UI or model discovery; dependency approved for Phase 4. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| bedrock-mantle | none | custom | documented | Same as Bedrock; separate surface, no adapter. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| google-vertex | none | gemini | documented | No ADC/service-account route, no template; no media/voice. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| anthropic-vertex | none | anthropic | documented | No service-account route or template. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| cloudflare-ai-gateway | none | openai-chat, anthropic | documented | No template; vendor API deprecation (2026-10-02) needs re-verification before building. | Gateway terms; upstream model identity, fallback and markup must be shown per request. | none |
| vercel-ai-gateway | none | openai-chat, anthropic | documented | No template; gateway billing/fallback semantics unverified. | Gateway terms; upstream model identity, fallback and markup must be shown per request. | none |
| openrouter | openrouter | openai-chat | implemented-unverified | No live account has exercised this route; per-model capability evidence absent. | Gateway terms; upstream model identity, fallback and markup must be shown per request. | none |
| clawrouter | none | openai-chat | documented | No template; managed routing identity and receipts unverified. | Gateway terms; upstream model identity, fallback and markup must be shown per request. | none |
| litellm | none | openai-chat, anthropic | documented | No template; alias/fallback identity behaviour unverified. | Gateway terms; upstream model identity, fallback and markup must be shown per request. | none |
| microsoft-foundry | none | openai-chat, custom | documented | No Azure auth or template; dependency approved for Phase 4. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| groq | groq | openai-chat | implemented-unverified | No live account has exercised this route; per-model capability evidence absent. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| cerebras | cerebras | openai-chat | implemented-unverified | No live account has exercised this route; per-model capability evidence absent. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| together | together | openai-chat | implemented-unverified | No live account has exercised this route; per-model capability evidence absent. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| fireworks | fireworks | openai-chat | implemented-unverified | No live account has exercised this route; per-model capability evidence absent. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| nvidia | nvidia | openai-chat | implemented-unverified | No live account has exercised this route; per-model capability evidence absent. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| huggingface | huggingface | openai-chat, custom | implemented-unverified | No live account has exercised this route; per-model capability evidence absent. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| deepinfra | deepinfra | openai-chat | implemented-unverified | No live account has exercised this route; per-model capability evidence absent. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| chutes | chutes | openai-chat | implemented-unverified | No live account has exercised this route; per-model capability evidence absent; vendor OAuth flow not implemented. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| novita | novita | openai-chat | implemented-unverified | No live account has exercised this route; per-model capability evidence absent. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| kilocode | kilocode | openai-chat | implemented-unverified | No live account has exercised this route; CLI sign-in documented only. | Gateway terms; upstream model identity, fallback and markup must be shown per request. | none |
| byteplus | byteplus | openai-chat | implemented-unverified | No live account has exercised this route; no `byteplus-plan` surface. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| ollama-cloud | ollama-cloud | openai-chat, ollama-native | implemented-unverified | Hosted route shares the cloud/base distinction; no live check. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| ollama | none | ollama-native | implemented-unverified | Native adapter exists but not live-checked in this build; no model present to verify. | No vendor account; local service terms apply. | none |
| lmstudio | none | openai-chat | implemented-unverified | OpenAI-compatible path only; vendor native /api/v1/models discovery and load/evict lifecycle absent. | No vendor account; local service terms apply. | none |
| vllm | none | openai-chat | implemented-unverified | OpenAI-compatible path; no live server check; thinking/chat-template controls absent. | No vendor account; local service terms apply. | none |
| sglang | none | openai-chat | documented | Documented-only; no template; native discovery/launch not covered. | No vendor account; local service terms apply. | none |
| inferrs | none | custom | documented | Documented-only; no OpenAI-compatible template; endpoint contract unknown. | No vendor account; local service terms apply. | none |
| ds4 | none | custom | documented | Documented-only; custom protocol; no adapter. | No vendor account; local service terms apply. | none |
| llamacpp | none | openai-chat | implemented-unverified | OpenAI-compatible path; no live server check. | No vendor account; local service terms apply. | none |
| custom-compatible | custom-openai, custom-anthropic | openai-chat, anthropic | implemented-unverified | Validation for scheme, /v1 normalization, TLS, redirects and DNS pinning outside Strict Offline is recorded as missing. | Standard provider API terms; per-token/credits billing. No third-party restriction recorded. | none |
| fal | none | custom | deferred | Deferred; no queue/webhook adapter or job schema. | Vendor media API terms; consent and content-policy requirements apply. | none |
| comfyui | none | custom | implemented-unverified | Local adapter exists but not live-checked; no workflow template validation. | No vendor account; local service terms apply. | none |
| runway | none | custom | documented | Documented-only media; no job adapter. | Vendor media API terms; consent and content-policy requirements apply. | none |
| pixverse | none | custom | documented | Documented-only media; no job adapter. | Vendor media API terms; consent and content-policy requirements apply. | none |
| deepgram | none | custom | documented | Documented-only speech; no transcription/synthesis adapter. | Vendor media API terms; consent and content-policy requirements apply. | none |
| elevenlabs | none | custom | documented | Documented-only speech/music; no adapter. | Vendor media API terms; consent and content-policy requirements apply. | none |

## Owner inputs (answered 2026-11-06)

- Provisioned credentials: OpenAI, Anthropic, Google Gemini. No other provider credentials exist,
  so every other paid route is `blocked: no credential` for live purposes.
- Spend cap: discuss per phase. Ask before the first paid call in each phase with the exact route,
  model and token cap.
- Dependency approvals: both granted for Phase 4 (AWS SigV4 for Bedrock, Azure/Foundry service
  account auth). No dependency was added in Phase 0.

## Ordered backlog (Phase 1 onward)

1. Phase 1: resolve route as `(provider, account, runtime, model)`; refuse silent substitution;
   label ambient keys; migrate saved routes. Fix G1 (status truth) and the catalogue/UI claim
   mismatch first because every later phase inherits it.
2. Phase 2: single-flight refresh per account; failed login never deletes; device-code and loopback
   flows; expired/revoked states. Test with real contending processes.
3. Phase 3 in order 3a OpenAI (Codex runtime, SIWC live check), 3b Anthropic (CLI delegate, live
   check), 3c Google (live Gemini check; correct the stale CLI claim), 3d xAI OAuth, 3e Kimi Coding
   identity, 3f MiniMax plan/portal, 3g Qwen Cloud/Coding Plan, 3h Z.AI plan, 3i OpenCode Zen and
   the managed runtime re-check (G10).
4. Phase 4: one data-driven preset family plus a small adapter per protocol; Bedrock/Vertex/Foundry
   auth; correct Synthetic's protocol choice; coding-plan surfaces for Volcengine/BytePlus/Tencent.
   Owner-approved dependencies may be added here.
5. Phase 5: custom endpoint validation layers; LM Studio native discovery; local context warnings.
6. Phase 6: media jobs and providers in the owner's list, with cost preview, refusal states and
   durable storage.
7. Phase 7: route picker, provider detail/wizard, account readiness, Models/first-run truth (S2),
   and a decision on G16 (dark-only) before claiming a light-theme gate.
8. Phase 8: website claims generated from catalogue data; no "supported" without a dated live record.
9. Phase 9: whole-initiative review.

## Deferred / out of scope

- Providers OpenClaw lists but the owner did not: Azure Speech, Baseten, Featherless, Gradium, Kie
  AI, Levanto Sage, Liquid AI/Inference, llmman, LongCat, Neon AI Gateway, oMLX, Particle,
  Perplexity, Poolside, Radius, Requesty, Rerank, SenseAudio, Telnyx, Abliteration.
- Any consumer-session scraping (Claude Max, Copilot, Gemini Code Assist) stays blocked.
- The light workspace theme is not built; see G16.
