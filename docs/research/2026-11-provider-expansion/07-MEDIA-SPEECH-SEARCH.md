# 07 - Media, speech and search (Phase 6, 2026-11-06)

Extends `docs/research/2026-10-provider-platform/` and `00-GAP-AUDIT.md` (G14). Source pages were read
on 2026-11-06. Vendor pages are summarized by the fetch tool, so a model id or field below is the
page's claim, not a measurement; where the summary dropped field names the raw documentation was
downloaded and read instead (Google). No provider credential exists in this environment
(`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `XAI_API_KEY`,
`MINIMAX_API_KEY`, `FAL_KEY`, `ELEVENLABS_API_KEY`, `DEEPGRAM_API_KEY`, `RUNWAYML_API_SECRET` and
`PIXVERSE_API_KEY` were all unset), so nothing here was exercised against a vendor. Every route stays
`implemented-unverified` or lower.

## Sources and what each changed

| Source (accessed 2026-11-06) | What it established | Changed in Hutch |
|---|---|---|
| OpenAI video guide, developers.openai.com/api/docs/guides/video-generation, plus four independent write-ups | Sora 2 models and the Videos API were shut down on 2026-09-24; the deprecations page names no replacement; endpoints return 410. | OpenAI video is `retired`; no adapter. |
| OpenAI image guide and pricing pages; GitHub issues sub2api#8431, open-design#5727, QwenPaw#7575, cherry-studio#14690 | GPT Image models reject `response_format` on generations and edits (`unknown_parameter`); they always return base64. `moderation_blocked` is a distinct error code, sometimes with `moderation_details`. Output is billed per token (gpt-image-2 image output $30/1M, gpt-image-1.5 $32/1M, gpt-image-1-mini $8/1M); there is no per-image table on the pricing page. The guide currently names `gpt-image-2.5-sunburst` and `-flare`; the pricing page names `gpt-image-2`, `gpt-image-1.5`, `gpt-image-1-mini`. Organization verification may be required. | The adapter sent `response_format` for every model except the exact string `gpt-image-1`; it now sends it only for DALL-E style models. Model id is data, not code. Refusal is a state. Price is an estimate with its basis. |
| OpenAI pricing page | TTS: `tts-1` $15/1M chars, `tts-1-hd` $30/1M chars, `gpt-4o-mini-tts` $0.60/1M text in and $12/1M audio out tokens; transcription $0.006/min; web search tool $10 per 1k calls. | Price rows with source and date. |
| Google AI Studio docs (redirected from ai.google.dev): video, image-generation, speech-generation, pricing, plus the raw `interactions/` pages downloaded and read | Veo preview models were shut down on 2026-10-22; the replacement is `gemini-omni-1.2-flash` (3 to 15 s with native audio, billed per output token, about $0.07/s at 720p). Image and speech docs now use `POST /v1beta/interactions` with header `x-goog-api-key` and `Api-Revision: 2026-05-20`, `input` as typed items, `response_format: {type: image\|audio, ...}`; audio is base64 in `steps[].content[].data`. Unary TTS returns a complete 24 kHz mono 16-bit WAV (older previews returned raw PCM). Max two speakers, prebuilt voices only. Image models: `gemini-nano-banana-2.1`, `gemini-3.1-flash-image`, `gemini-3.1-flash-lite-image`, `gemini-3-pro-image`; `gemini-2.5-flash-image` is deprecated with shutdown 2027-03-15. Lyria `lyria-3.5` $0.08 per song, `lyria-3-clip-preview` $0.04. TTS price rises on 2027-01-01. Grounding with Google Search: 5,000 free per month for Gemini 3+, then $14 per 1,000. | `google-gemini` gets image and speech routes on the Interactions wire, marked unverified. No Veo route. Google video is a Gemini Omni task and is deferred (no wire read). Speech price carries its change date. |
| Gemini TTS forum and cookbook threads (discuss.ai.google.dev, google-gemini/cookbook#1231) | `gemini-3.1-flash-tts-preview` returns HTTP 200 with empty content and `finishReason: OTHER`; truncation is random and billed; some requests 500 because the model returned text tokens. Streaming truncates past about 60 s. | An HTTP 200 without an audio block is a failure, never an empty success. No automatic retry (it multiplies cost); the error names the cost risk. |
| xAI docs: video-generations, image-generations, text-to-speech, REST voice reference | `POST /v1/videos/generations` returns `request_id`; `GET /v1/videos/{request_id}` returns `status` (`done`, `failed`, `expired`, else keep polling) and `video.url`. Images at `/v1/images/generations` and `/edits`, models `grok-imagine-image-2.0`, video `grok-imagine-video-1.5`. TTS `POST /v1/tts` with `text`, `voice_id` (eve, ara, rex, sal, leo), `language`, `output_format {codec, sample_rate, bit_rate}`, returns raw audio. The page did not give image wire names for count, ratio, resolution or format, nor URL expiry. | `xai` gets image, video and speech routes. Field names beyond the page come from OpenClaw's page (`aspect_ratio`, `resolution`, `response_format`) and are flagged as not confirmed on the vendor page. |
| OpenClaw xAI, MiniMax, Google, fal, Runway, PixVerse, Deepgram, ElevenLabs and ComfyUI pages | Used as a feature and pitfall checklist only. | See below. |
| MiniMax platform docs: video-generation-t2v, speech-t2a-http, image-generation-t2i | Bearer auth at `https://api.minimax.io`. HTTP 200 carries failures in `base_resp.status_code` (1002 rate limit, 1004/2049 auth, 1008 balance, 1026 sensitive content, 2013 invalid parameters). Image: `image-01`, prompt at most 1500 chars, `data.image_urls` or `data.image_base64`, `metadata.failed_count` counts safety-blocked images, URLs expire in 24 h. Speech: `speech-2.8-hd` and others, text under 10,000 chars, `data.audio` is hex, billed on `extra_info.usage_characters`, `output_format: url` is valid 24 h. Video: `POST /v1/video_generation` returns `task_id`; Hailuo-2.3/02, prompt at most 2000 chars. The query and file-retrieve pages were not in the fetched text. | MiniMax gets image and speech routes (envelope check on `base_resp`) and a video task route whose second hop (file retrieve) is recorded from OpenClaw and the create page only, so it is marked unconfirmed. |
| fal queue docs, fal.ai/docs/model-apis/model-endpoints/queue | `POST https://queue.fal.run/{owner}/{app}` with `Authorization: Key ...` returns `request_id`, `status_url`, `response_url`, `cancel_url`; status `IN_QUEUE`, `IN_PROGRESS`, `COMPLETED`; failures show `error` and `error_type` only once `COMPLETED`; cancel is `PUT .../cancel` with 200 OK (never runs), 202 CANCELLATION_REQUESTED (may still complete), 400 ALREADY_COMPLETED, 404. Status and result URLs use owner and app only; including the endpoint sub-path returns 405. Media URLs are public and expire per account setting. Retryable 503/504 are re-queued up to 10 times unless `X-Fal-No-Retry: 1`. | fal queue route. Cancel maps 200 to confirmed and 202 to unconfirmed. `X-Fal-No-Retry: 1` is sent so fal cannot silently re-run billable work. |
| Runway: docs.dev.runwayml.com (API pages, outputs, versioning, pricing) and search | Base `https://api.dev.runwayml.com`, `Authorization: Bearer`, `X-Runway-Version: 2024-11-06` on every request, `POST /v1/text_to_video` / `image_to_video` / `video_to_video`, `GET /v1/tasks/{id}` (do not poll more often than every 5 s), `DELETE /v1/tasks/{id}`. Statuses PENDING, THROTTLED, RUNNING, SUCCEEDED, FAILED, CANCELLED come from third-party summaries, not the vendor page I could read. Output URLs expire within 24 to 48 h and must not be exposed. Credits $0.01: gen4.5 12/s, gen4_turbo 5/s, veo3.1 40/s with audio or 20/s without, veo3.1_fast 15/s or 10/s. | Runway text-to-video route. Price rows for the listed models only. |
| PixVerse platform docs (docs.platform.pixverse.ai, via search) | Base `https://app-api.pixverse.ai`; headers `API-KEY` and a fresh `Ai-trace-id` UUID per request (reusing one blocks a new generation); `POST /openapi/v2/video/text/generate` returns `video_id`; `GET /openapi/v2/video/result/{video_id}` wrapped in `Resp`, status 1 success, 5 generating, 7 content moderation failed (credits refunded), 8 failed. | PixVerse text-to-video route; status 7 is a refusal, not a crash. |
| ElevenLabs API reference | `POST /v1/text-to-speech/{voice_id}`, header `xi-api-key`, `output_format` query (default `mp3_44100_128`), body `text`, `model_id`, `voice_settings`; returns binary audio; 422 has a `detail` array. Maximum text length and the quota error shape were not on the page. | Speech route. Length bound declared from the model, flagged unconfirmed. |
| Deepgram TTS docs | `POST https://api.deepgram.com/v1/speak`, `Authorization: Token`, query `model` (for example `aura-2-thalia-en`), body `{"text"}`, binary audio, 2,000-character limit (413 beyond), 429 means too many in-progress requests, `dg-char-count` header. | Speech route. |
| ComfyUI docs and GitHub issues #2566, #7513 | `POST /interrupt` interrupts whatever is running, including another client's job; a surgical cancel needs a `prompt_id`; a pending item is removed with `POST /queue {"delete": [id]}`. | The adapter called a body-less `/interrupt` as a cancel fallback; it now interrupts only when the history shows this prompt is the one running. |

## Failure classes found, with classification

| Class | Evidence | Class | Hutch response |
|---|---|---|---|
| A paid synchronous result is held only in process memory between submit and fetch | Hutch's own `openai_images.py` and `speech.py`; the same shape lost output in other agents | fixable | Durable spool written inside submit, before the ledger moves; recovery finalizes from the spool. |
| Wrong parameter by model family | `response_format` against GPT Image (four tracker issues) | fixable | Parameter chosen by declared flavor, not by exact model string. |
| Failure carried in an HTTP 200 body | MiniMax `base_resp`; Gemini TTS 200 with empty content | fixable | The envelope is checked on every response; a missing media block is a failure naming the billing risk. |
| Refusal presented as a crash | OpenAI `moderation_blocked`; MiniMax 1026 and `failed_count`; PixVerse status 7 | fixable | `refused` is a first-class outcome with the vendor's reason and no retry. |
| Expiring result URLs | Runway 24 to 48 h, OpenAI Sora 1 h, MiniMax 24 h, fal media expiry | mitigable | The result is fetched at finalize and stored with its SHA-256; the URL is never kept. |
| Unbounded download into memory | `view.content` and `httpx.get(url)` before any size check | fixable | One bounded streaming fetch through the pinned transport. |
| Cancel that is not a cancel | ComfyUI blind `/interrupt`; fal 202 | fixable | Confirmed only on an explicit acknowledgement; otherwise `cancel_unconfirmed`. |
| Vendor retries that re-bill | fal re-queues 503/504 up to 10 times | mitigable | `X-Fal-No-Retry: 1`. |
| Retired model presented as available | Sora 2 (2026-09-24), Veo preview (2026-10-22), `gemini-2.5-flash-image` (2027-03-15), `grok-imagine-image-pro` | vendor-side | Catalogue says `retired` with the date; no route. |
| Cost surprise | token-billed images, credits-billed video, per-character speech, 2027-01-01 TTS price change | mitigable | Estimate shown before the approval, labeled with its basis and date; the vendor account stays authoritative. |
| Job outlives the tool call | `create_media` waits 90 s then returns; nothing resumes a 5-minute render | fixable | Status, resume and cancel operate on the ledger, outside any run. |

## Design (what was built, and the files)

Tasks, each at most three source files plus one seam:

1. Durability and honesty: `media/spool.py`, `media/status.py`, `media/fetch.py`; seam `media/jobs.py` (shrunk from 592
   to 577 lines while gaining `refused`, `recoverable` and tuple-returning `finalize`).
2. Route engine: `data/media-routes.json`, `providers/route_spec.py`, `providers/wire.py`, `providers/http_call.py`,
   `providers/route_values.py`, `providers/route_backend.py` (sync), `providers/route_task.py` (task).
3. Wiring and cost: `media/backends.py`, `media/cost.py`, `data/media-prices.json`, `media/usage.py`; the 170-line
   `run_provider_media` in `tools/media_generation.py` became twelve functions of at most 40 lines.
4. Jobs that outlive the call: `media/ledger.py`, `media/resume.py`, `media/jobs_routes.py` (mounted from
   `media/routes.py`, so frozen `app.py` did not grow).
5. ComfyUI: queue-aware cancel, outputs from every list, bounded and pinned downloads.
6. Catalogue and docs: `providers.json` statuses, ADR-0036, `provider-platform.md`, `connections.md`,
   `provider-compatibility.md`.

Decisions and why:

- **Data, not per-vendor code.** Fourteen routes fit two protocols. OpenAI Images needs model-family rules a table
  cannot hold, so the row names an adapter. Routes whose wire was not read stay `documented` instead of being built
  on a guess (Runway, MiniMax video, Google Omni).
- **No backend is chosen between accounts.** With 14 routes the old alphabetical pick would silently choose a payer.
- **A held result before the ledger moves.** The provider is paid when it answers; the spool closes the window.
- **Credentials.** Connection-backed where a chat connection exists (key, endpoint and billing are the user's
  decision in Hutch); an environment variable only for vendors without one, labeled ambient. No new credential store
  and no change to frozen `connections.py`.
- **Estimates.** Only Google image and speech have a readable price. Everything else says "cost unknown". An
  estimate is recorded as `estimated`; an unknown price is `unpriced` with no number.
- **No automatic retry anywhere.** The OpenAI SDK's default retries are off for billable calls; fal gets
  `X-Fal-No-Retry`; Gemini TTS's empty 200 is not retried (the thread reports roughly half of requests failing and
  billing for each).

## Results

- Focused suites: 253 media tests; 590 provider, catalogue, compat, media, route and connection tests; 127 app and
  tool tests; 82 tool-contract and offline tests. `npm run check:agent` and `npm run audit:context` pass. The emoji
  audit reports 8 violations, all in `.codewhale/state/subagents.v1.json` (another tool's untracked state).
- Mutation checks (tests fail without the behavior): the in-body envelope check, `X-Fal-No-Retry`, the content-type
  check, the old blind ComfyUI cancel, and images-only ComfyUI fetch.
- Real stack, `docs/realignment/run_media_resume_check.py`, record in
  `docs/realignment/artifacts/provider-expansion-2026-11/phase6/media-resume-run.json` (2026-11-06): a victim process
  was SIGKILLed after a stand-in provider answered a speech request; a real `hutch serve` on the same state listed the
  open job, `advance` finished it with one provider request, the served SHA-256 equalled the provider's bytes, and
  the spool was empty afterward. A video job went pending to done and was stored as `video/mp4`; a cancel the provider
  cannot confirm ended `cancel_unconfirmed`; a MiniMax 1026 envelope inside a 200 ended `refused`. The record holds no
  key. **The provider was a stand-in, so none of this is vendor evidence.**

## Defects found by running, not planned

- `finalize()` returned a bare row on failure paths while every caller unpacks a tuple (pre-existing; any failed
  fetch raised `ValueError` in the tool).
- The new downloader let the pinned transport's `EndpointRefused` escape; it is now a `FetchError`.
- Reconcile tests passed a live service that rightly skips jobs it drives; they now restart the service.
- Releasing the held copy after commit lost Xiaomi's measured tokens (read after the release); caught by the existing
  speech test, fixed by reading before finalize, with a regression test on the resume path.
- A local "route cannot be filled" error claimed the provider may have billed; it now says nothing was sent.
- The spool was never released or swept; fixed.

## Not run, and why

- Any vendor request: no credential for any of the eleven providers in the environment. Every route is
  `blocked: no credential` for live purposes. The owner's earlier statement that OpenAI, Anthropic and Google keys
  are provisioned still does not match the shell (the variables are unset); the first paid call per provider would
  need the keys exported and a per-call token or image cap agreed.
- A real ComfyUI server (none installed), Comfy Cloud, and Runway, PixVerse CN, MiniMax video.
- Provider-native search for OpenAI, Google and xAI: documented, not built. The existing Xiaomi route and the
  `live_search` distinction are unchanged and still labeled in every surface.
- Music (Lyria, MiniMax music, ElevenLabs music, fal music), image editing through routes, streaming synthesis, mp3
  output, voice cloning and image-to-video: not built; the media store accepts wav audio only.
- The UI for any of this (Phase 7): the jobs API exists; no page lists jobs, and a finished resumed job does not
  re-enter the conversation as a media block.
