# 03 - Provider capability matrix

Date: 2026-10-30. Live verification: two owner-authorized real routes were exercised on 2026-10-30 -
the direct DeepSeek connection through the built-in runtime and the managed OpenCode runtime with a
DeepSeek model. Text generation succeeded on both; tool calling, streaming, image input, other
modalities and every other provider were not live-exercised. The column exists so a code path is never
mistaken for a working provider account. Research detail and dated sources are in
drafts/01-core-providers.md, drafts/02-hosting-gateway-local.md and drafts/03-media-speech-search.md.

How to read the columns:

- **Category** describes what the service is, not whether Hutch supports it.
- **Integration status** is Hutch's code status: implemented, implemented-unverified, experimental,
  documented (research only), blocked, retired, deferred.
- **Live verification** is the real-account column. Only rows with a dated entry belong in the live
  verification ledger section of 06-VALIDATION-LEDGER.md; evidence files live under
  artifacts/live-verification/ with a machine-readable summary.json.
- An auth method's status is separate from the provider's: a provider can have an implemented API-key
  route and a retired or blocked subscription route.

<!--MATRIX:START-->
| Provider | Category | Services | Protocols | Auth methods | Integration status | Research | Live verification |
|---|---|---|---|---|---|---|---|
| anthropic | vendor | chat, tools, coding_cli | anthropic | api-key [per_token; implemented] | implemented-unverified | 01-core | not live-verified |
| arcee | vendor | chat | openai-chat | api-key [per_token; documented] | documented | 02-hosted | not live-verified |
| cohere | vendor | chat, embeddings | custom | api-key [per_token; documented] | documented | 02-hosted | not live-verified |
| deepseek | vendor | chat, tools | openai-chat, anthropic | api-key [per_token; implemented] | implemented | 02-hosted | live-verified 2026-10-30 (text; built-in runtime; deepseek-flash) |
| google | vendor | chat, images, video, speech, transcription, search, grounding, tools, coding_cli | gemini | api-key [per_token; implemented]; oauth-consumer [unknown; blocked] | implemented-unverified | 01-core | not live-verified |
| minimax | vendor | chat, images, image_editing, video, music, speech, transcription | openai-chat, anthropic, custom | api-key [per_token; documented]; coding-plan-oauth [subscription; documented] | documented | 01-core | not live-verified |
| mistral | vendor | chat, embeddings, code_execution | openai-chat | api-key [per_token; documented] | documented | 02-hosted | not live-verified |
| moonshot | vendor | chat, tools, coding_cli | openai-chat, anthropic | api-key [per_token; documented]; kimi-coding-key [subscription; documented] | documented | 01-core | not live-verified |
| openai | vendor | chat, responses, embeddings, images, speech, transcription, tools, batch | openai-chat, openai-responses | api-key [per_token; implemented]; chatgpt-sign-in [subscription; experimental] | implemented-unverified | 01-core | not live-verified |
| opencode | vendor | coding_runtime, coding_cli, chat | openai-chat, anthropic | managed-session [subscription; implemented]; cli-sign-in [subscription; experimental] | implemented | 01-core | live-verified 2026-10-30 (text; managed runtime; deepseek/deepseek-flash) |
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

## Live-verified routes (2026-10-30)

| Route | Runtime | Model | Result | Recorded usage | Artifact |
|---|---|---|---|---|---|
| DeepSeek direct connection (owner-authorized), OpenAI-shaped API | Hutch built-in | deepseek-flash | succeeded; reply matched requested token | 612 prompt / 9 completion tokens; cost 0.0 because the model was unpriced locally | artifacts/live-verification/deepseek-builtin-runtime-live.json |
| OpenCode managed runtime, private profile connected to the owner's DeepSeek key | Hutch managed OpenCode 2.2.0 | opencode/deepseek/deepseek-flash | succeeded; reply matched requested token | 4452 prompt / 8 completion tokens; provider-reported cost $0.0006726 | artifacts/live-verification/opencode-managed-runtime-deepseek-live.json |
| OpenCode CLI external reference | OpenCode CLI 2.2.0 | deepseek/deepseek-flash | succeeded | not reported by the CLI JSON stream | artifacts/live-verification/opencode-cli-deepseek.json |
| OpenCode Go stored API key | Hutch managed OpenCode 2.2.0 | opencode/opencode-go/iceman-contributor-free | failed explicitly: provider reported the key expired; no retry, cost 0.0 | none | artifacts/live-verification/opencode-managed-runtime-live.json |

## Blocked, retired and deferred routes (summary)

The blocked, retired and deferred rows from the matrix remain as recorded in the provider catalogue:
GitHub Copilot subscription reuse and the Claude Max proxy are blocked by policy; the old Qwen portal
OAuth, Gemini consumer CLI authentication and several media APIs are retired; media, speech, video,
provider-native search adapters and additional CLI executors are deferred. None are stubbed.
