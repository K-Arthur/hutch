# 03 - Provider capability matrix

Date: 2026-10-30. Live verification: none. Every row below is at most implemented-unverified; the
column exists so no reader can mistake a code path for a working provider account. Research detail and
dated sources are in drafts/01-core-providers.md (core), drafts/02-hosting-gateway-local.md (hosted,
gateway, enterprise, local) and drafts/03-media-speech-search.md (media, speech, search).

How to read the columns:

- **Category** describes what the service is, not whether Hutch supports it.
- **Integration status** is Hutch's code status: implemented (live-exercised), implemented-unverified,
  experimental, documented (research only), blocked, retired, deferred.
- **Live verification** is the real-account column. In this environment no credentials exist, so every
  row is not live-verified. A future live exercise must add a dated row in 06-VALIDATION-LEDGER.md.
- An auth method's status is separate from the provider's: a provider can have an implemented API-key
  route and a retired or blocked subscription route.

<!--MATRIX:START-->
| Provider | Category | Services | Protocols | Auth methods | Integration status | Research | Live verification |
|---|---|---|---|---|---|---|---|
| anthropic | vendor | chat, tools, coding_cli | anthropic | api-key [per_token; implemented] | implemented-unverified | 01-core | not live-verified |
| arcee | vendor | chat | openai-chat | api-key [per_token; documented] | documented | 02-hosted | not live-verified |
| cohere | vendor | chat, embeddings | custom | api-key [per_token; documented] | documented | 02-hosted | not live-verified |
| deepseek | vendor | chat, tools | openai-chat, anthropic | api-key [per_token; documented] | documented | 02-hosted | not live-verified |
| google | vendor | chat, images, video, speech, transcription, search, grounding, tools, coding_cli | gemini | api-key [per_token; documented]; oauth-consumer [unknown; blocked] | documented | 01-core | not live-verified |
| minimax | vendor | chat, images, image_editing, video, music, speech, transcription | openai-chat, anthropic, custom | api-key [per_token; documented]; coding-plan-oauth [subscription; documented] | documented | 01-core | not live-verified |
| mistral | vendor | chat, embeddings, code_execution | openai-chat | api-key [per_token; documented] | documented | 02-hosted | not live-verified |
| moonshot | vendor | chat, tools, coding_cli | openai-chat, anthropic | api-key [per_token; documented]; kimi-coding-key [subscription; documented] | documented | 01-core | not live-verified |
| openai | vendor | chat, responses, embeddings, images, speech, transcription, tools, batch | openai-chat, openai-responses | api-key [per_token; implemented]; chatgpt-sign-in [subscription; experimental] | implemented-unverified | 01-core | not live-verified |
| opencode | vendor | coding_runtime, coding_cli, chat | openai-chat, anthropic | managed-session [subscription; implemented]; cli-sign-in [subscription; experimental] | implemented-unverified | 01-core | not live-verified |
| qwen | vendor | chat, tools, coding_cli | openai-chat, anthropic | api-key [per_token; documented]; coding-plan [subscription; documented]; portal-oauth [subscription; retired] | documented | 01-core | not live-verified |
| stepfun | vendor | chat, speech, transcription | openai-chat | api-key [per_token; documented] | documented | 02-hosted | not live-verified |
| xai | vendor | chat, search, code_execution, images, video, speech, transcription | openai-chat, custom | api-key [per_token; documented]; oauth [subscription; documented] | documented | 01-core | not live-verified |
| xiaomi | vendor | chat | openai-chat, anthropic | api-key [credits; implemented] | implemented-unverified | 02-hosted | not live-verified |
| zai | vendor | chat, tools, coding_cli | openai-chat, anthropic | api-key [per_token; documented]; coding-plan [subscription; documented] | documented | 01-core | not live-verified |
| alibaba-model-studio | serving_platform | chat, embeddings, images, tools | openai-chat | api-key [per_token; documented] | documented | 02-hosted | not live-verified |
| qianfan | serving_platform | chat, embeddings, images | custom | api-key [per_token; documented]; oauth [per_token; documented] | documented | 02-hosted | not live-verified |
| cerebras | serving_platform | chat, tools | openai-chat | api-key [per_token; documented] | documented | 02-hosted | not live-verified |
| chutes | serving_platform | chat, images | openai-chat | api-key [per_token; documented] | documented | 02-hosted | not live-verified |
| deepinfra | serving_platform | chat, embeddings, images | openai-chat | api-key [per_token; documented] | documented | 02-hosted | not live-verified |
| fireworks | serving_platform | chat, embeddings, images, tools | openai-chat | api-key [per_token; documented] | documented | 02-hosted | not live-verified |
| gmi-cloud | serving_platform | chat, images | openai-chat | api-key [per_token; documented] | documented | 02-hosted | not live-verified |
| groq | serving_platform | chat, tools, speech, transcription | openai-chat | api-key [per_token; documented] | documented | 02-hosted | not live-verified |
| huggingface | serving_platform | chat, embeddings, images | openai-chat, custom | api-key [per_token; documented] | documented | 02-hosted | not live-verified |
| novita | serving_platform | chat, embeddings, images, video | openai-chat | api-key [per_token; documented] | documented | 02-hosted | not live-verified |
| nvidia | serving_platform | chat, embeddings, images | openai-chat | api-key [per_token; documented] | documented | 02-hosted | not live-verified |
| ollama-cloud | serving_platform | chat, tools | openai-chat, ollama-native | api-key [per_token; documented] | documented | 02-hosted | not live-verified |
| synthetic | serving_platform | chat | openai-chat | api-key [per_token; documented] | documented | 02-hosted | not live-verified |
| together | serving_platform | chat, embeddings, images, video, tools | openai-chat | api-key [per_token; documented] | documented | 02-hosted | not live-verified |
| venice | serving_platform | chat, images | openai-chat | api-key [per_token; documented] | documented | 02-hosted | not live-verified |
| clawrouter | gateway | chat | openai-chat | api-key [per_token; documented] | documented | 02-hosted | not live-verified |
| cloudflare-ai-gateway | gateway | chat, images, embeddings | openai-chat, anthropic | api-key [per_token; documented] | documented | 02-hosted | not live-verified |
| kilocode | gateway | chat, coding_cli | openai-chat | api-key [subscription; documented]; cli-sign-in [subscription; documented] | documented | 02-hosted | not live-verified |
| litellm | gateway | chat, embeddings | openai-chat, anthropic | api-key [per_token; documented]; custom-endpoint [unknown; documented] | documented | 02-hosted | not live-verified |
| openrouter | gateway | chat, images | openai-chat | api-key [per_token; implemented] | implemented-unverified | 02-hosted | not live-verified |
| vercel-ai-gateway | gateway | chat, images, embeddings | openai-chat, anthropic | api-key [per_token; documented] | documented | 02-hosted | not live-verified |
| bedrock | enterprise_cloud | chat, embeddings, images, tools | custom | aws-credentials [per_token; documented] | documented | 02-hosted | not live-verified |
| bedrock-mantle | enterprise_cloud | chat, tools | custom | aws-credentials [per_token; documented] | documented | 02-hosted | not live-verified |
| anthropic-vertex | enterprise_cloud | chat, tools | anthropic | service-account [per_token; documented] | documented | 02-hosted | not live-verified |
| byteplus | enterprise_cloud | chat, embeddings, images, video | openai-chat | api-key [per_token; documented] | documented | 02-hosted | not live-verified |
| google-vertex | enterprise_cloud | chat, embeddings, images, video, speech, transcription, grounding, tools | gemini | service-account [per_token; documented] | documented | 02-hosted | not live-verified |
| microsoft-foundry | enterprise_cloud | chat, embeddings, images, tools | openai-chat, custom | api-key [per_token; documented]; service-account [per_token; documented] | documented | 02-hosted | not live-verified |
| tencent-cloud | enterprise_cloud | chat, embeddings | custom | api-key [credits; documented] | documented | 02-hosted | not live-verified |
| volcengine | enterprise_cloud | chat, embeddings, images | openai-chat, custom | api-key [per_token; documented] | documented | 02-hosted | not live-verified |
| github-copilot | subscription_service | coding_cli, chat | custom | oauth [subscription; blocked] | blocked | 02-hosted | not live-verified |
| opencode-go | subscription_service | chat | openai-chat, anthropic | api-key [subscription; experimental] | experimental | 01-core | not live-verified |
| comfyui | local_runtime | images, image_editing | custom | local-service [free; implemented] | implemented-unverified | 03-media | not live-verified |
| ds4 | local_runtime | chat | custom | local-service [free; documented] | documented | 02-hosted | not live-verified |
| inferrs | local_runtime | chat | custom | local-service [free; documented] | documented | 02-hosted | not live-verified |
| llamacpp | local_runtime | chat, embeddings, tools | openai-chat | local-service [free; implemented] | implemented-unverified | 02-hosted | not live-verified |
| lmstudio | local_runtime | chat, embeddings, tools | openai-chat | local-service [free; implemented] | implemented-unverified | 02-hosted | not live-verified |
| ollama | local_runtime | chat, embeddings, tools | ollama-native | local-service [free; implemented] | implemented-unverified | 02-hosted | not live-verified |
| sglang | local_runtime | chat, embeddings, tools | openai-chat | local-service [free; documented] | documented | 02-hosted | not live-verified |
| vllm | local_runtime | chat, embeddings, tools | openai-chat | local-service [free; implemented] | implemented-unverified | 02-hosted | not live-verified |
| deepgram | media_platform | transcription, speech | custom | api-key [per_token; documented] | documented | 03-media | not live-verified |
| elevenlabs | media_platform | speech, music, transcription | custom | api-key [per_token; documented] | documented | 03-media | not live-verified |
| fal | media_platform | images, video, audio_generation | custom | api-key [per_token; documented] | deferred | 03-media | not live-verified |
| pixverse | media_platform | video, images | custom | api-key [per_token; documented] | documented | 03-media | not live-verified |
| runway | media_platform | video, images | custom | api-key [per_token; documented] | documented | 03-media | not live-verified |
| vydra | media_platform | images, video | custom | api-key [per_token; documented] | documented | 02-hosted | not live-verified |
| claude-max-proxy | compatible_endpoint | chat | anthropic | unofficial-proxy [subscription; blocked] | blocked | 02-hosted | not live-verified |
| custom-compatible | compatible_endpoint | chat, responses, tools | openai-chat, anthropic | custom-endpoint [unknown; implemented] | implemented-unverified | 02-hosted | not live-verified |
<!--MATRIX:END-->

## Blocked, retired and deferred routes (summary)

| Route | Status | Reason and nearest legitimate alternative |
|---|---|---|
| Anthropic consumer subscription routed through an API proxy | blocked | Vendor terms prohibit third-party routing of plan credentials; use a Console API key or the documented setup-token for Claude Code. |
| GitHub Copilot subscription as a model API | blocked | No GitHub-documented third-party inference contract for Hutch's use; GitHub documents the Copilot SDK. No client impersonation. |
| Qwen Portal OAuth | retired | Discontinued; use QwenCloud/Model Studio Token Plan or Coding Plan keys at documented endpoints. |
| Gemini consumer CLI authentication (free/AI Pro/Ultra) | retired | Retired 2026-06-18; use paid API/Vertex keys, or Code Assist entitlement where applicable. |
| OpenAI Sora/Videos, gpt-image-1, Google Veo 3.1 previews, MiniMax paid music | retired/closed | Provider shut them down or closed them to new users; not stubbed in Hutch. |
| Gemini, general OpenAI Responses, media, speech and search adapters | deferred | Research recorded; no verified live contract or test path in this environment. Not shipped as fake implementations. |

## Capability-evidence rules applied

1. A model listing proves authentication and discovery only.
2. A text success does not prove tool calls; a tool call does not prove image, audio or video input.
3. Provider image generation is not image understanding.
4. Context/output limits and usage reporting are per endpoint and model; missing metadata is unknown,
   never zero cost.
5. A gateway's price/capability claim is scoped to that gateway route; the upstream vendor identity
   must be recorded from the response when it can differ.
