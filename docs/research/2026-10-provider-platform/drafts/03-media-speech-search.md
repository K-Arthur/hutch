# Media, speech, music, and search integrations: provider contract research

Fragment for the multi-provider platform docs (03-media-speech-search). Research pass
2026-10-30, America/Vancouver. This fragment records what each vendor currently documents
for image, video, music, speech, and search/grounding; it is primary-source input for the
platform docs, not an integration design and not an implementation claim.

Scope note: the request's reference index (docs.openclaw.ai/provider pages) was treated as a
pointer only. Every claim below was checked against the vendor's own docs pages fetched on
2026-10-30 (URLs in the sources table). No live provider account, key, or paid request was used
in this research. Nothing here is Hutch-verified live.

## Evidence legend

| Tag | Meaning |
|---|---|
| D | Vendor-documented: read directly on an official vendor page fetched on 2026-10-30. |
| I | Inferred from vendor docs (derived statement, not a quoted guarantee); marked where used. |
| R | Hutch repository evidence (code or an existing repo research doc), not re-run in this pass. |
| U | UNVERIFIED: not confirmed by a fetched page, or docs conflict. Do not put in a contract or UI claim. |

## Summary matrix

One row per provider/integration. Contract column describes the documented job shape, not what
Hutch implements. Hutch state refers to this checkout as of 2026-10-30.

| # | Integration | Modality | Documented contract | Auth | Docs | Hutch state |
|---|---|---|---|---|---|---|
| 1 | OpenAI Images (GPT Image) | image gen/edit | Sync single request; base64 in response | Bearer API key | D | Adapter exists (openai_images.py); sync assumed, protocol-verified only |
| 2 | OpenAI Sora 2 / Videos API | video | Was async; API shut down 2026-09-24 | Bearer API key | D | None; do not build |
| 3 | OpenAI Speech (TTS) | speech out | Sync request; raw audio or SSE stream | Bearer API key | D (deprecation) | Adapter exists (OpenAITTSEngine); no live call |
| 4 | OpenAI File transcription | speech in | Sync multipart upload | Bearer API key | D | None |
| 5 | OpenAI web search tool | search | Tool call inside Responses API | Bearer API key | D | None; Hutch has no provider-native search |
| 6 | Google Gemini image (Nano Banana) | image gen/edit | Gemini API call (sync envelope U) | API key header | D capability, U envelope | None |
| 7 | Google Veo 3.1 | video | Long-running operation: start, poll operation | API key header | D (shut down) | None |
| 8 | Google Gemini TTS | speech out | Interactions request; WAV audio block | API key header | D | Adapter exists (GeminiTTSEngine); no live call |
| 9 | Google voice design / replication | speech out | Voices API; replication needs consent clip | API key header | D | None |
| 10 | Google Lyria music | music | Interactions request, sync | API key header | D | None |
| 11 | Google Search grounding | search | google_search tool inside Interactions; citation annotations | API key header | D | None |
| 12 | Google Files API | uploads | Resumable upload; 48-hour retention | API key header | D | None |
| 13 | xAI Grok Imagine images | image gen/edit | Sync; temporary URL or base64 | Bearer API key | D | None |
| 14 | xAI Grok Imagine video | video | Async: request_id then poll | Bearer API key | D | None |
| 15 | xAI TTS + custom voices | speech out | Sync bytes or WebSocket stream; clone API | Bearer API key | D | None |
| 16 | xAI web search / X search tools | search | Tools inside Responses API | Bearer API key | D | None |
| 17 | MiniMax image-01 | image | Sync single request; URL or base64 | Bearer API key | D | None |
| 18 | MiniMax H3 video v2 | video | Async: task_id then query; 7-day query window | Bearer API key | D | None |
| 19 | MiniMax TTS (sync + async) | speech out | Sync SSE/hex; async task + file download | Bearer API key | D | None |
| 20 | MiniMax voice clone | speech out | Upload file, clone, ASR similarity check | Bearer API key | D | None |
| 21 | MiniMax music | music | Sync request; hex audio or 24-hour URL | Bearer API key | D (closed to new users) | None; do not plan |
| 22 | fal queue (aggregator) | image/video/audio | Async queue: IN_QUEUE / IN_PROGRESS / COMPLETED | Authorization: Key | D | None |
| 23 | fal webhooks | delivery | POST to webhook; retry until stored result expires | shared secret? U | D (no signature found) | None |
| 24 | ComfyUI (self-hosted) | image/video | Submit prompt, poll history, fetch /view | None documented | D | Adapter exists (comfyui.py); protocol-verified only |
| 25 | Runway Dev | video/image/audio | Async task; poll GET /v1/tasks/{id} | Bearer + version header | D | None |
| 26 | Runway speech endpoints | speech | Endpoints listed; contract not read | Bearer + version header | D existence, U detail | None |
| 27 | PixVerse platform | video | Async video_id then poll; webhook optional | API-KEY header | D | None |
| 28 | ElevenLabs TTS | speech out | Streaming or buffered audio | xi-api-key header | D | None |
| 29 | ElevenLabs voice cloning | voice | Instant clone (attestation) / professional (verify) | xi-api-key header | D (UI), U (API) | None |
| 30 | ElevenLabs Music | music | Paid subscribers; API contract U | xi-api-key header | D capability, U endpoint | None |
| 31 | Deepgram STT | speech in | Sync or callback-based async | Token or Bearer JWT | D | None |
| 32 | Deepgram TTS | speech out | Sync REST or WebSocket stream | Token or Bearer JWT | D | None |
| 33 | External search (Hutch grounding) | search | Fan-out adapters, outcome taxonomy | varies/none | R | GDELT/RSS/HN verified live per repo; SearXNG configured; Bluesky blocked |

## Cross-cutting contracts

### Async job patterns (submit / observe / cancel)

| System | Submit | Observe | Cancel | Notes |
|---|---|---|---|---|
| fal queue | POST queue.fal.run/{owner}/{app} returns request_id plus status_url, response_url, cancel_url | GET status_url | cancel_url from submit response | Queue never drops; retries up to 10; 429 waits, does not count as retry |
| ComfyUI | POST /prompt returns prompt_id and queue number | GET /history/{prompt_id}; WS /ws events | POST /interrupt stops current execution; /queue manages pending | Local; no billing |
| MiniMax video v2 | POST /v2/video_generation returns task_id | GET /v2/query/video_generation/{task_id} | DELETE /v2/video_generation/{task_id}; only queued tasks can be cancelled | Running tasks cannot be cancelled; succeeded/failed are deleted, not cancelled |
| MiniMax async TTS | POST /v1/t2a_async_v2 returns task_id | GET /v1/query/t2a_async_query_v2 (max 10 queries/s) | None documented | Statuses processing/success/failed/expired |
| Google Veo | POST model:predictLongRunning returns operation name | GET operation until done=true | None found in fetched page | Generated videos stored 2 days |
| Runway | POST generation endpoint returns id | GET /v1/tasks/{id} | DELETE /v1/tasks/{id} cancels in-progress or deletes finished | Statuses PENDING/THROTTLED/RUNNING/SUCCEEDED/FAILED/CANCELLED |
| PixVerse | POST generation returns video_id | GET /openapi/v2/video/result/{video_id} every 3-5 s | None found in fetched pages | status 1 complete, 5 generating, 7 moderation failed, 8 failed |
| xAI video | POST /v1/videos/generations returns request_id | GET /v1/videos/{request_id} | None documented | statuses pending/done/failed |
| OpenAI Images | POST /images/generations (sync) | Not applicable | Not applicable | Billable work happens inside the request |
| Gemini TTS / Lyria / image | Single Interactions request | Not applicable (no polling shown) | Not applicable | Envelope details U for image |
| ElevenLabs TTS | POST /v1/text-to-speech/{voice_id} | Stream or buffer response | Close stream | Billing/segment boundary semantics U |
| xAI TTS | POST /v1/tts; wss://api.x.ai/v1/tts for streaming | Stream | Close socket | Raw bytes by default |
| Deepgram STT/TTS | POST /v1/listen or /v1/speak | Optional callback URL for async delivery | None documented | Callback consumer must be idempotent |

### Cancellation and uncertain outcomes

- Rule for Hutch: a provider request can be accepted, billed, and still fail for the client; a
  disconnect is not a cancellation. Provider docs here do not give a billing guarantee for
  cancellation, so Hutch should record outcome_unknown and reconcile by polling when a job id
  exists, and never auto-retry a billable submit. This matches the existing media job service
  rule that submit is called exactly once per job row [R: src/hutch/media/jobs.py].
- MiniMax video is the clearest documented case: queued tasks can be cancelled with no charge;
  running tasks cannot be cancelled at all; a running task therefore reaches a terminal state
  that must be observed, not assumed [D].
- Runway: DELETE /v1/tasks/{id} cancels an in-progress task, but the fetched page does not say
  whether completed work is still billed; treat cancel as a request, not a refund [D claim,
  U billing outcome].
- fal: the submit response exposes cancel_url, but the fetched queue page does not define billing
  after cancellation; a request may already be executing when the client gives up [D endpoint,
  U charge].
- ComfyUI: /interrupt stops the current execution only; a cancelled local job costs no money but
  may leave partial artifacts; poll history to learn the terminal state [D].
- Sync APIs (OpenAI Images, xAI images/audio, Gemini TTS/Lyria, ElevenLabs, Deepgram): a client
  timeout does not prove the provider did not process or bill the request. Record the uncertainty
  and do not resubmit automatically.
- Retired/blocked routes change the failure mode: a stale integration pointed at a shut-down
  endpoint will look like an outage; treat provider deprecation pages as a first-class source
  (see Blocked/retired section).

### Result retention and URL expiry

| Provider surface | What expires | Documented lifetime |
|---|---|---|
| Google Files API | uploaded files | 48 hours; 20 GB per project, 2 GB per file [D] |
| Google Veo generated videos | server copy | 2 days; extension resets the timer [D] |
| Gemini image outputs | envelope not captured | U |
| MiniMax image-01 URL response | image URL | 24 hours [D] |
| MiniMax music url response | audio URL | 24 hours [D] |
| MiniMax async TTS | file download URL | 9 hours (32,400 s); file lost after expiry [D] |
| MiniMax video v2 | output URL | time-limited; download promptly (exact duration U) [D] |
| xAI Imagine image/video | ephemeral URL on imgen.x.ai / vidgen.x.ai | short-lived; persist via Files API [D] |
| xAI Files storage | stored file / public URL | expires_after 3,600-2,592,000 s; omitted means no expiry [D] |
| fal queue webhook stored result | result payload | about 1 hour after completion, or about 6 minutes for results of 10 KB or more; up to 31 delivery retries [D] |
| Runway output URLs | output array URLs | temporary; download and store (duration U) [D] |
| PixVerse output URL | Resp.url | not stated in fetched pages, U |
| OpenAI Images | response bytes | inline base64; no URL [D] |
| OpenAI TTS / ElevenLabs TTS / Deepgram TTS | response bytes | returned in the response; no provider URL [D] |

Implication for Hutch: fetch bytes immediately and store them locally; never persist a provider
URL as the artifact. The existing media backend protocol already enforces this for media
(fetch() consumes expiring URLs and stores bytes) [R: src/hutch/media/providers/base.py].

### Audio streaming and encoding

| Provider | Request | Encodings documented | Streaming mechanics |
|---|---|---|---|
| OpenAI TTS | POST /v1/audio/speech, input max 4,096 chars | mp3, opus, aac, flac, wav, pcm | stream_format audio (default) or sse [D] |
| OpenAI STT | POST /v1/audio/transcriptions, files up to 25 MB | mp3, mp4, mpeg, mpga, m4a, wav, webm input | Sync; Live transcription is a separate API [D] |
| Gemini TTS | Interactions request, response_format audio | WAV (RIFF) unary; streaming headerless 16-bit PCM AUDIO_L16 24 kHz mono [R cross-checked with D page] | Multi-speaker limited to two prebuilt voices per request [R/D] |
| Gemini Live | Live API session | Live has one voice config per session; audio-only sessions about 15 min [R] | Interruption = server interrupted event plus client stop/clear queue [R] |
| xAI TTS | POST /v1/tts | mp3 default at 24 kHz/128 kbps; output_format codec/sample_rate/bit_rate configurable; telephony mu-law described [D] | Raw bytes; wss://api.x.ai/v1/tts for streaming; with_timestamps returns JSON envelope [D] |
| MiniMax sync TTS | POST /v1/t2a_v2 | hex audio or url; audio_setting format/sample_rate/bitrate/channel [D] | stream=true returns chunked JSON / SSE; sentence-level timestamps in async mode [D] |
| MiniMax async TTS | POST /v1/t2a_async_v2, max 1,000,000 characters | output file; download via file API | Task poll; 9-hour download URL [D] |
| ElevenLabs TTS | POST /v1/text-to-speech/{voice_id} | output_format codec_sample_rate_bitrate: mp3, opus, pcm, ulaw, alaw, wav; 192 kbps mp3 needs Creator tier, 44.1 kHz PCM/WAV needs Pro [D] | Buffered or streamed endpoint; previous_text/next_text/previous_request_ids for continuity [D] |
| Deepgram TTS | POST /v1/speak | linear16, mulaw, alaw, mp3 (default), opus, flac, aac | WebSocket emits raw audio only: linear16, mulaw, alaw; compressed/containerized only on REST [D] |
| Deepgram STT | POST /v1/listen | input encodings: linear16, flac, mulaw, amr-nb, amr-wb, opus, speex, g729 | Sync or callback; streaming WebSocket exists (Voice Agent) [D] |
| Runway TTS | /v1/text_to_speech listed | U (contract not fetched) | Task-based per capability map [D existence] |
| Music | Google Lyria MP3 44.1 kHz stereo; MiniMax hex/song; ElevenLabs music bytes | MP3 for Gemini Lyria; MiniMax hex; ElevenLabs contract U | All effectively single-shot, not streaming [D] |

### Voice cloning: consent and abuse rules

| Provider | Clone mechanism | Consent / verification control | Limits and retention |
|---|---|---|---|
| Google voice replication | POST /v1beta/voices with reference audio plus consent audio | Both clips required: 10-30 s reference and a recording of the speaker reciting the documented consent statement in a supported language [D] | 200 stored voices per project, 1-year TTL; stateless voicekey 7-day TTL; delete API [D] |
| ElevenLabs instant cloning | UI/API instant clone | UI requires confirming the user has the right and consent to clone the voice; ToS and Prohibited Use Policy apply; vendor says generations are traceable to the user [D UI, U API] | Samples: at least 10 s total, 5 s per file; 1-2 min recommended [D] |
| ElevenLabs professional cloning | Fine-tuned model, Creator plan or above | Voice ownership verification step (record phrase in similar conditions); failed verification can retry after 24 h; sings not supported [D] | 30-180 min audio; fine-tuning 3-6 h, up to 24 h [D] |
| MiniMax voice clone | POST /v1/files/upload purpose voice_clone, then POST /v1/voice_clone | ASR similarity check against a supplied transcript; no explicit consent-attestation text found on fetched API pages [D mechanics, U consent requirement] | 10 s-5 min, mp3/m4a/wav; upload up to 20 MB; unused clone deleted after 7 days; aigc_watermark flag [D] |
| xAI custom voices | POST /v1/custom-voices multipart (Enterprise-gated); console flow free up to 30 voices | Enterprise-only API; no explicit consent-attestation text found on fetched pages [D gate, U consent] | Reference clip max 120 s; voice scoped to team [D] |
| OpenAI | No cloning endpoint on /v1/audio/speech; custom voice IDs created from audio samples (creation flow not fetched) | Usage policy requires disclosing that TTS output is AI-generated, not a human voice [D] | 13 built-in voices listed (guide intro says 11; discrepancy) [D] |
| Runway custom voices | Characters/custom voices exist per docs index | U (not fetched) | U |
| Deepgram | No cloning documented in fetched pages | U | U |

Design implication (not a vendor claim): Hutch should collect its own explicit consent
attestation, store it with the voice id, and refuse cloning without it, because provider
controls differ (Google verifies a consent recording; ElevenLabs attests in the UI; MiniMax and
xAI consent terms were not found in the fetched API pages).

### Grounding and source attribution requirements

| Provider | Tool | Attribution artifact | Display / ToS requirement |
|---|---|---|---|
| Google | google_search tool in Interactions | text annotations of type url_citation with url, title, start_index, end_index; google_search_call queries; google_search_result.search_suggestions | Inline citation annotations are returned for the app to render; search_suggestions is an HTML snippet whose full usage requirements are in the Gemini API terms [D] |
| xAI | web_search Responses tool | SDK exposes sources/citations; response server_side_tool_usage | Allowed/excluded domains max 5 each, mutually exclusive; image search/understanding switches add server-side tool calls [D] |
| xAI | x_search Responses tool | citations | Handle filters max 20; date range; billed at $5 per 1k posts and $10 per 1k user profiles fetched [D] |
| OpenAI | web_search in Responses API (web_search_preview legacy) | web_search_call actions: search (with queries), open_page, find_in_page; message.content annotations of type url_citation | Search actions incur tool-call cost; citations returned inline by default [D] |
| Hutch external | GDELT DOC 2.0, RSS/Atom, HN Algolia, SearXNG, Bluesky | Own source records | Untrusted evidence; explicit ok/zero_results/partial/disabled/unavailable/blocked/rate_limited/timeout/error outcomes [R] |

Provider-native grounding couples answer text to a provider; Hutch external grounding keeps
retrieval separate from the model. The platform decision should state which one a Bot uses and
display citations in both cases; neither provider guarantees that every claim is cited.

### Pricing and quota units observed

| Provider | Unit documented | Exact price |
|---|---|---|
| OpenAI | per image (token-based billing), per tool call for web search | pricing pages not fetched, U |
| Google | Veo 4k stated as more expensive than lower resolutions; storage limits documented | pricing page not fetched, U |
| xAI | image flat per image; video per second; X search $5/1k posts, $10/1k profiles | image/video price table not fetched, U |
| MiniMax | music 120 RPM paid / 3 RPM free; async TTS query 10/s; video and TTS usage reported as seconds/tokens/characters | price table not fetched, U |
| fal | per model/GPU-second; 5xx failures not billed; 429 waits without retry | per-model prices not fetched, U |
| Runway | credits; $0.01 per credit, $10 minimum purchase; prores/png_sequence add 5 credits/s | per-model credit costs only on pricing page, U |
| ElevenLabs | subscription tiers gate output formats; music API for paid subscribers | U |
| Deepgram | usage-based; mip_opt_out changes pricing | U |
| ComfyUI | local compute | not applicable |

## Per-provider notes

### OpenAI Images (GPT Image)

- Status: vendor-documented on 2026-10-30; no live call made.
- Endpoints: POST https://api.openai.com/v1/images/generations and POST /v1/images/edits;
  Responses API image_generation tool for multi-turn editing with File IDs [D].
- Sync contract: the generation is the request. GPT Image models always return base64;
  response_format url is documented as legacy for retired models and unsupported for GPT Image
  [D]. There is no upstream job id, so Hutch's adapter treats submit as accept-and-work and
  caches returned bytes [R].
- Request essentials: model (gpt-image-2.5-sunburst / gpt-image-2.5-flare, dated snapshots),
  prompt max 32,000 characters, size WxH divisible by 16 with aspect ratio 1:3 to 3:1 and max
  3840x2160, n 1-10, output_format png/jpeg/webp, output_compression, background
  transparent/opaque/auto, moderation low/auto, quality, stream partial images, safety_identifier
  up to 128 chars [D].
- Edits: up to 16 input images per request; mask or markup (GPT Image 2.5/2.6); input_fidelity
  on some models; input images via File ID or URL/base64 data URL [D].
- Image API is synchronous; the Responses tool can iterate across turns, which is a different
  conversation contract and not supported by Hutch's current media job shape [D/R].
- Billing: tokens per image, exact price U; no URL expiry because bytes are inline.
- Retro: gpt-image-1 shut down 2026-10-23; the current models are the 2.x family [D].

### OpenAI video (retired)

- The Videos API and sora-2/sora-2-pro were documented as shut down on 2026-09-24 with no
  one-to-one replacement; the API reference page is retained for historical reference [D].
- Conflict noted honestly: the text-to-video guide fetched the same day still describes
  POST /v1/videos, statuses queued/in_progress/completed/failed, content download, and webhooks.
  Treat the deprecation banner as current and the guide as stale [D, U resolution].
- Do not plan a Sora integration. If a future replacement appears, its own API reference must be
  re-fetched before design.

### OpenAI speech (TTS and file transcription)

- TTS: POST https://api.openai.com/v1/audio/speech. Input max 4,096 chars; 13 built-in voices
  listed; formats mp3, opus, aac, flac, wav, pcm; stream_format audio or sse; speed 0.25-4;
  instructions max 4,096 chars [D].
- Deprecation: tts-1, tts-1-hd and gpt-4o-mini-tts shut down 2027-01-06; docs direct migrations
  to gpt-realtime-2.1-mini through the Realtime API and state that model is not supported on
  /v1/audio/speech [D]. A Hutch TTS adapter built on /audio/speech needs a migration plan.
- Disclosure: vendor usage policy requires telling end users the TTS voice is AI-generated, not
  a human voice [D].
- STT: POST /v1/audio/transcriptions with gpt-transcribe recommended; files up to 25 MB; input
  formats mp3, mp4, mpeg, mpga, m4a, wav, webm; response carries text plus detected languages;
  prompt, keywords and languages hints supported [D].
- Deprecation: whisper-1, gpt-4o-transcribe, gpt-4o-mini-transcribe, gpt-4o-transcribe-diarize
  and /v1/audio/translations shut down 2027-02-26 [D].
- Realtime/Live audio paths exist (WebRTC/WebSocket) but were not read in this pass; their audio
  encodings are U here.

### Google Gemini image (Nano Banana)

- Models documented: gemini-nano-banana-2.1 (workhorse, 1K/2K/4K, search grounding),
  gemini-3.1-flash-lite-image (fast/cheap), gemini-3.1-flash-image (previous generation) [D].
- Capabilities: text-to-image and conversational editing, multi-reference images, search-grounded
  image generation (example prompts use image search) [D].
- Generated images are returned through the Gemini API. The exact Interactions envelope
  (response_format, inline base64 vs output block) was not captured in this pass, so treat the
  request/response schema as U; the capability list is D.
- Media path: for requests over 100 MB total, use the Files API; PDF limit 50 MB; Files API
  stores 20 GB per project, 2 GB per file, auto-deletes after 48 hours [D].
- Watermark/provenance for generated images was not captured in the fetched text; U (do not claim
  SynthID for images until checked). Veo video does document SynthID [D].
- Pricing: per-image units on the pricing page, not fetched; U.

### Google Veo (retired route, with replacement pointer)

- The served models veo-3.1-generate-preview, veo-3.1-fast-generate-preview and
  veo-3.1-lite-generate-preview were shut down on 2026-10-22; the Gemini API page directs users
  to Gemini Omni Flash (gemini-omni-1.1-flash) or the Gemini Enterprise Agent Platform [D].
- The replacement model page (ai.google.dev/.../models/gemini-omni-1.1-flash) returned 404 when
  fetched, so the replacement contract is U in this pass; only the pointer is documented.
- Historical contract still useful for design of long-running video:
  POST /v1beta/models/{model}:predictLongRunning, then poll the returned operation name until
  done=true, then download the file URI with the API key [D].
- Outputs: 4/6/8 s, 720p/1080p/4k (4k not on Lite), native audio always on, 24 fps; 2-day server
  retention; SynthID watermark; safety filters; region restriction where allow_adult is the only
  personGeneration value; blocked generations are not charged [D].
- Practical latency: 11 seconds minimum, up to 6 minutes at peak [D].
- Extension: up to 20 times; input video up to 141 s; extension only works on Veo-generated videos
  and resets the 2-day timer [D].
- No cancellation operation was found on the fetched page; U.

### Google speech (TTS, voice design, voice replication)

- TTS models: gemini-3.8-flash-tts and gemini-3.8-flash-lite-tts; request through
  Interactions with response_format audio and generation_config.speech_config; default output is
  WAV audio; multi-speaker uses two speakers with per-turn speech_metadata [D].
- Style control: speech_metadata annotations (e.g. style) plus inline vocal tags; text is the
  verbatim transcript, not stage directions [D/R].
- Streaming: unary returns WAV (RIFF); streaming returns headerless 16-bit PCM AUDIO_L16 24 kHz
  mono per Hutch's recorded R3 evidence; treat as R plus D page [R].
- Voice design and voice replication are separate documented features; replication is the
  consent-bearing path: POST /v1beta/voices with source_audio (10-30 s) and consent_audio
  reciting a mandated consent statement; default store=true (voice_ id, 200/project, 1-year TTL),
  store=false returns a voicekey_ that lasts 7 days [D].
- Live API is a different contract: one voice config, audio-only sessions about 15 minutes,
  client-owned interruption handling [R].
- Deprecation: gemini-3.1-flash-tts-preview shuts down 2026-11-17; current TTS models have no
  announced shutdown date [D].

### Google music (Lyria)

- Lyria 3 Clip (lyria-3-clip-preview): fixed 30-second clips, MP3; Lyria 3.5 (lyria-3.5):
  full-length songs of a couple of minutes, duration influenceable via prompt, MP3; both via the
  Interactions API, 44.1 kHz stereo, vocals and instrumental, lyrics/structure returned with the
  audio [D].
- Realtime music generation is a separate product (Lyria RealTime) not read in this pass; U.
- Pricing and quota U.

### Google grounding with Google Search

- Tool: google_search inside an Interactions request; model decides whether to search, runs one
  or more queries, and returns inline annotations [D].
- Response: google_search_call (queries), google_search_result (search_suggestions HTML), and
  text content with annotations of type url_citation carrying url, title, start_index, end_index
  [D].
- Attribution requirement: the page says search_suggestions is an HTML snippet for rendering
  search suggestions and that full usage requirements are in the Gemini API terms (grounding with
  Google Search section) [D]. A Hutch renderer must display the citation annotations and the
  required suggestion affordance; stripping them is not compliant.
- Can be combined with the URL context tool [D].
- Pricing per grounded prompt/tool use not fetched; U. Google grounds in all supported languages
  [D].

### Google Files API

- Resumable upload; use when total request size including prompt exceeds 100 MB; PDF limit 50 MB;
  20 GB per project, 2 GB per file; files auto-deleted after 48 hours [D].
- Upload returns a file URI used as a content part in an Interactions request; delete is
  available [D].
- This is the likely path for Hutch attachments to Google media models; Hutch must copy any
  artifact it needs to keep before the 48-hour expiry.

### xAI Grok Imagine: images and video

- Images: POST https://api.x.ai/v1/images/generations with Bearer key; OpenAI-compatible SDK
  surface; models such as grok-imagine-image-2.0; n 1-10; aspect_ratio list (1:1 through 21:9,
  including 19.5:9 and 20:9); images return temporary URLs by default or base64; editing supports
  up to 5 reference images [D].
- Persistence: storage_options.filename is required to store; optional expires_after from 3,600
  to 2,592,000 seconds; optional permanent public URL; the ephemeral URL is always returned and is
  short-lived [D].
- Video: POST https://api.x.ai/v1/videos/generations returns request_id; GET
  /v1/videos/{request_id} returns status pending/done/failed and, on done, video.url on
  vidgen.x.ai (temporary) plus duration; generate_audio=False requests a silent video [D].
- Video editing (POST /v1/videos/edits) and reference-to-video are documented; reference audio
  clips max 15 s, up to 3, and voice refs can be preset voice ids or custom voices [D].
- No cancellation or delete endpoint was found on the fetched reference page; U.
- Webhooks for Imagine were not captured; U.

### xAI speech and custom voices

- TTS: POST https://api.x.ai/v1/tts with Bearer key; text max 60,000 characters; language required
  (BCP-47 or auto); voice_id optional default eve; output_format codec/sample_rate/bit_rate;
  default MP3 24 kHz/128 kbps; speed 0.7-1.5; optimize_streaming_latency 0-2; text_normalization;
  with_timestamps returns a JSON envelope with base64 audio and per-character timing; response
  body is raw audio bytes [D].
- Streaming: wss://api.x.ai/v1/tts is listed as a consumer of custom voices; raw streams are U
  beyond that endpoint listing [D endpoint, U chunk format].
- Voices: GET /v1/tts/voices for built-ins; GET /v1/custom-voices for custom [D].
- Custom voices: POST /v1/custom-voices multipart, gated to Enterprise teams; console allows up
  to 30 free custom voices; reference clip max 120 s; voices are team-scoped [D].
- Consent specifics for cloning were not found in the fetched pages; U. Do not claim xAI requires
  an attestation until checked.
- Speech-to-speech and a realtime API are listed in the docs index (wss://api.x.ai/v1/realtime)
  but not read here; U.

### xAI search and grounding tools

- web_search: a Responses API tool (type web_search) supported by the xAI SDK and OpenAI-compatible
  clients; parameters allowed_domains (max 5), excluded_domains (max 5, mutually exclusive),
  enable_image_understanding, enable_image_search; citations returned to the caller [D].
- x_search: a separate Responses tool with allowed_x_handles/excluded_x_handles (max 20; min 10
  in the Vercel SDK), from_date/to_date, image and video understanding; billed $5 per 1k posts and
  $10 per 1k user profiles fetched, plus tokens [D].
- Tool-invocation cost details other than X search sit on the pricing page and were not fetched;
  U.
- Both are provider-native: the model decides when to search, so attribution is whatever the
  response citations contain; Hutch must persist them, not regenerate them [I from docs shape].

### MiniMax image

- Endpoint: POST https://api.minimax.io/v1/image_generation; model image-01 only; prompt max 1,500
  chars; aspect_ratio or width/height (512-2,048, divisible by 8); n 1-9; response_format url
  (default, expires in 24 hours) or base64; seed; prompt_optimizer [D].
- Response: data.image_urls or base64 images; success_count/failed_count distinguishes images
  blocked by content safety from transport errors [D].
- Auth: Authorization: Bearer API_key; errors are OpenAI-style with request_id [D].
- Sync only; no job id, no cancel.

### MiniMax video (H3 v2)

- Endpoints: POST https://api.minimax.io/v2/video_generation; GET
  /v2/query/video_generation/{task_id}; DELETE /v2/video_generation/{task_id} [D].
- Models: MiniMax-H3, H3-Highspeed, H3-Lite, H3-Max; multimodal input array (text, image first/last
  frame, reference video, reference audio); output 768P or 2K, 4-15 s; resolution, duration and
  ratio are required request fields [D].
- Async: create returns task_id; query returns status queued/running/succeeded/failed/cancelled
  with content.url, resolution, duration and usage (seconds or tokens); only tasks from the last
  7 days are queryable [D].
- Cancellation: DELETE cancels only queued tasks; returns action=cancelled. Running tasks cannot
  be cancelled; succeeded/failed tasks are deleted (action=deleted) [D].
- Output URLs are time-limited; download promptly (exact duration U) [D].
- Error shape: HTTP status is the real error code with type/message/http_code and request_id;
  429 rate_limit_error, 402 insufficient_balance_error are enumerated [D].
- Longer/older v1 video endpoints are still listed in the docs index; their relationship to v2
  was not verified, U.

### MiniMax speech (sync, async, voice clone)

- Sync TTS: POST https://api.minimax.io/v1/t2a_v2; model speech-2.8-hd; stream true returns
  chunked audio (SSE/multipart of JSON chunks) and the response carries hex audio by default;
  audio_setting controls sample_rate, bitrate, format, channel; voice_setting controls voice_id,
  speed, volume; HTTP sync character cap not captured (U); WebSocket sync documented at 10,000
  characters per request [D/I].
- Async TTS: POST /v1/t2a_async_v2, up to 1,000,000 characters; optional text file input via
  file_id; task query /v1/query/t2a_async_query_v2 limited to 10 queries/s; statuses
  processing/success/failed/expired; success returns file_id; download via
  GET /v1/files/retrieve_content; download URL valid 9 hours [D].
- Invalid characters: up to 10 percent invalid characters still generates audio and reports the
  ratio; more than 10 percent fails [D].
- Voice clone: upload with purpose=voice_clone (mp3/m4a/wav, 10 s-5 min, up to 20 MB), then
  POST /v1/voice_clone with file_id and voice_id; optional prompt audio under 8 s plus transcript;
  ASR similarity check against text_validation; preview text up to 1,000 chars; aigc_watermark
  flag; unused cloned voices are deleted after 7 days [D].
- No explicit consent attestation was found on the fetched voice-clone API or guide pages; U.
- File API: upload, list, retrieve, retrieve_content, delete; generated audio is downloaded
  through retrieve_content [D].

### MiniMax music (partially closed)

- Endpoint: POST https://api.minimax.io/v1/music_generation. Models documented: music-3.0,
  music-2.6, music-cover (plus free variants). Rate limit 120 RPM paid, 3 RPM free [D].
- Closure: starting 2026-08-20 the paid Music Generation and Lyrics Generation APIs are no longer
  available to new users; existing paying users can continue; the free music APIs are
  discontinued; docs redirect to MiniMax Audio or the open-source MiniMax Music 3 model [D].
- Request: prompt 10-300 chars style, lyrics up to 3,500 chars, stream, output_format url or hex,
  cover reference audio 6 s-6 min and max 50 MB [D].
- Response: sync JSON with hex audio when stream=false; url expires after 24 hours; usage and
  duration/sample-rate/channel metadata returned [D].
- Planning conclusion: not a route for new integrations; treat as retired for Hutch's purposes
  (existing-user access only).

### fal queue (aggregator with a uniform async contract)

- Base: https://queue.fal.run; auth header Authorization: Key <FAL_KEY>; submit POST
  /{owner}/{app} with JSON input [D].
- Submit response: request_id, gateway_request_id, status_url, response_url, cancel_url,
  queue_position. URLs use owner/app only; including the full endpoint path returns 405 [D].
- Status: IN_QUEUE (with queue_position), IN_PROGRESS (with logs for app owners), COMPLETED (with
  metrics.inference_time); logs are empty for non-owner callers [D].
- Reliability: queue never drops requests; automatic retries up to 10 on 503/504/connection
  errors; 429 waits in queue without counting as a retry; 5xx failures are not billed; retries
  can be disabled with X-Fal-No-Retry; start timeout with X-Fal-Request-Start-Timeout; backup
  domains falrun.com and queue.falrun.com [D].
- Webhooks: pass webhook_url (or fal_webhook query param); POST body has request_id,
  gateway_request_id, status OK/ERROR, payload; payload may be null with payload_error; 2xx
  required, 15 s first-attempt timeout, 120 s retry timeout, up to 31 retries until the stored
  result expires (about 1 hour, or about 6 minutes for results of 10 KB or more); handlers must
  be idempotent [D].
- No webhook signature verification was documented on the fetched pages; U. If Hutch receives fal
  webhooks through a public endpoint, authenticity must be treated as unverified until checked.
- Aggregated models seen on the fetched index include FLUX image models, Kling 3, Seedance,
  MiniMax H3 Max video, MiniMax speech-02-hd, MiniMax voice clone, ElevenLabs Scribe v2 [D index].
- Per-model request/response schemas differ; fal is a transport contract plus per-model
  capability pages, not one schema [I].

### ComfyUI (self-hosted)

- HTTP API: POST /prompt with {prompt, client_id} returns prompt_id and queue position; GET
  /history/{prompt_id}; GET /view for image bytes; GET /queue and POST /queue for queue
  operations; POST /interrupt stops the current execution; POST /free unloads models;
  POST /upload/image and /upload/mask; GET /system_stats; WebSocket /ws emits status,
  execution_start, execution_cached, executing events [D].
- No authentication is documented on the fetched routes page; the server is expected to be
  protected by the deployment. Do not expose it unauthenticated; U for any built-in auth policy.
- Caller supplies the workflow graph; Hutch's adapter sends the graph as given and bills nothing
  at the API layer because compute is local [D/R].
- Cancellation stops the current run only; queued items are managed through /queue [D].
- Result lifecycle: generated files live on the local filesystem; no provider URL expiry. Hutch
  should copy them into its media store [I].

### Runway Dev

- Base https://api.dev.runwayml.com; Authorization: Bearer API secret plus mandatory
  X-Runway-Version: 2024-11-06 on every request [D].
- Async: generation endpoints return {id}; poll GET /v1/tasks/{id}; status one of PENDING,
  THROTTLED, RUNNING, SUCCEEDED, FAILED, CANCELLED; only SUCCEEDED has output array; FAILED has
  failure and failureCode; THROTTLED is queued by the plan rate limit, not an error; DELETE
  /v1/tasks/{id} cancels an in-progress task or deletes a finished one [D].
- Request bodies are discriminated unions keyed on model: valid ratio/duration/fields vary per
  model; thirteen endpoint groups, 58 operations; text-to-video and image-to-video documented
  with gen4.5; also image generation, upscales, character performance, text_to_speech,
  speech_to_speech, sound_effect, voice_dubbing, voice_isolation [D capability map].
- Content moderation failure is a FAILED task, not an HTTP error; moderated generations cost the
  same as successful ones and repeated moderated requests can suspend an account [D].
- Uploads: public URL, data URI, or POST /v1/uploads ephemeral upload for local files [D].
- Output URLs are temporary; download and store (exact expiry not in fetched pages, U) [D].
- Billing: credits ($0.01 each, $10 minimum); prores/png_sequence output add 5 credits per second;
  per-model prices only on the pricing page, not fetched (U) [D unit]. A draft preview can be
  enhanced to 1080p within 7 days of creation [D].
- Characters (avatars with custom voices), Model Routers and published Workflows add more
  contracts not read here; U beyond the index listing.

### PixVerse

- Base https://app-api.pixverse.ai; headers: API-KEY (the API key) and a required Ai-trace-id UUID
  on generation requests; responses may carry HTTP 200 with a nonzero ErrCode, so check ErrCode,
  not just HTTP status [D].
- Video: POST /openapi/v2/video/text/generate returns video_id and credits consumed; poll GET
  /openapi/v2/video/result/{video_id} every 3-5 s; status 1 completed (Resp.url available),
  5 generating, 7 moderation failed, 8 generation failed; do not treat a URL as ready before
  status 1 [D].
- Models seen: v6-max, c1; quality 360p-1080p; duration and aspect ratio per model/template;
  generate_audio_switch and multi-clip switches exist for some models [D examples].
- Webhooks: register an HTTPS callback in the webhook console to get webhook_id and Secret Key;
  pass webhook_id in the generation body; callback is POST with Webhook-Timestamp,
  Webhook-Nonce, Webhook-Signature (base64 HMAC-SHA256 over timestamp newline nonce newline
  URL-encoded sorted payload), Ai-trace-id; return HTTP 200 with body ok or PixVerse retries [D].
- Uploads: image multipart (JPEG/PNG/WebP, under 20 MB, neither dimension over 10,000 px); media
  upload accepts video mp4/mov/webm and audio mp3/wav/m4a/aac with per-endpoint limits [D].
- No cancel/delete endpoint was found in the fetched pages; output URL expiry not stated; both U.
- A separate image-generation template flow exists (Image Template Generation / Get Image
  Generation Result) [D].

### ElevenLabs TTS

- Endpoint: POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id} with JSON body; the
  fetchable API reference page (converted) does not show the auth header value, but the
  documented product convention is the xi-api-key header; U on the exact header name until
  verified against a live reference page.
- output_format is codec_sample_rate_bitrate with a long enum: alaw_8000, mp3 variants from
  22,050 to 44,100 Hz, opus 48 kHz variants, pcm 8-48 kHz, ulaw_8000, wav 8-48 kHz. MP3 at
  192 kbps requires Creator tier; PCM/WAV at 44.1 kHz requires Pro tier [D].
- Streaming: the endpoint supports buffered and streamed audio; request stitching via
  previous_text/next_text/previous_request_ids (max 3 ids) for long-form continuity [D].
- enable_logging=false requests zero-retention mode, enterprise-only [D].
- deprecated optimize_streaming_latency values still documented [D].
- Text limits, per-character cost and concurrency limits were not captured; U.

### ElevenLabs voice cloning

- Instant Voice Cloning (IVC): quick clone from short samples, no custom model training; UI modal
  requires the user to confirm they have the right and consent to clone the voice; ToS and
  Prohibited Use Policy apply; vendor states generations are traceable to the user [D UI].
- Professional Voice Cloning (PVC): Creator plan or above; 30-180 minutes of audio; voice
  ownership verification by recording a phrase; fine-tuning 3-6 hours (up to 24); singing not
  supported; failed verification can be retried after 24 hours [D].
- IVC sample rules: each file at least 5 seconds, all samples at least 10 seconds, 1-2 minutes
  recommended [D].
- API endpoints for creating IVC/PVC were not read in this pass; U. Hutch must not implement
  cloning against guessed paths.

### ElevenLabs Music

- Eleven Music generates songs from prompts; Audio Reference (up to about 30 seconds) guides style
  and is copyright-screened; Music Finetunes train on user-owned non-copyrighted tracks in about
  5-10 minutes; Enterprise can finetune on proprietary catalogs [D].
- Commercial use: vendor states the model is cleared for nearly all commercial uses, with plan
  details in the music terms [D].
- API availability: Music API is available for paid subscribers; the endpoint/request contract
  was not read in this pass, U. Do not plan around it until the API reference is fetched.

### Deepgram STT and TTS

- Auth: Authorization: Token <API_KEY> or Authorization: Bearer <JWT> [D].
- STT: POST https://api.deepgram.com/v1/listen; optional callback URL for async delivery
  (callback_method POST/PUT); encodings linear16/flac/mulaw/amr-nb/amr-wb/opus/speex/g729;
  diarize_model latest/v1/v2 (streaming supports v1 only); keyterm prompting for Nova-3; topic,
  intent, sentiment, summarize features [D].
- TTS: POST https://api.deepgram.com/v1/speak with JSON {text}; query params encoding, container
  (default wav), sample_rate (default 24,000), bit_rate (default 48,000), model (Aura/Aura-2
  voice ids), callback URL; encodings linear16, mulaw, alaw, mp3, opus, flac, aac [D].
- Streaming TTS over WebSocket emits raw audio only: linear16 (default), mulaw, alaw; compressed
  and container formats are REST-only [D].
- The Voice Agent API (single WebSocket with STT + LLM + TTS, barge-in) is listed in the docs
  index but was not read here; U on its contract [I].
- Pricing, concurrency and callback retry policy were not captured; U.

### Search/grounding: provider-native versus external

- Provider-native search is a tool inside a model response: Gemini google_search, xAI web_search
  and x_search, OpenAI web_search. In all four cases the same response carries the answer and the
  citation annotations, and the provider controls retrieval. That is convenient for answer
  quality but couples the Bot's evidence trail to the chosen model provider and its per-call
  pricing [D/I].
- Hutch currently has no provider-native grounding. Its grounding lane is an external fan-out
  with a documented adapters list: GDELT DOC 2.0, RSS/Atom feeds, Hacker News Algolia, SearXNG
  (requires a configured instance) and Bluesky public search (the public host was blocked from
  this network when that lane was researched). The repo doc says GDELT, RSS and HN were verified
  live; that is repo evidence, not re-verified in this pass [R].
- The external adapters return a typed outcome taxonomy (ok, zero_results, partial, disabled,
  unavailable, blocked, rate_limited, timeout, error) instead of collapsing every miss into
  "no results"; that is useful input for the platform docs' failure-honesty requirements [R].
- Platform recommendation from this evidence: separate the retrieval route from the model route,
  and require the UI to show whether citations came from provider-native grounding or from
  Hutch's external adapters. Provider-native citations must be stored verbatim; external sources
  must retain URL plus retrieval timestamp.

## Blocked, retired, or unsupported routes

| Route | State on 2026-10-30 | Evidence |
|---|---|---|
| OpenAI Sora 2 / Videos API | Shut down 2026-09-24; no one-to-one replacement; a stale video guide still describes it | D (API reference banner; contradiction noted) |
| OpenAI gpt-image-1 | Shut down 2026-10-23; use GPT Image 2.5 models | D |
| OpenAI tts-1, tts-1-hd, gpt-4o-mini-tts | Deprecated; shutdown 2027-01-06; migrate to gpt-realtime-2.1-mini via Realtime API, not /audio/speech | D |
| OpenAI whisper-1, gpt-4o-transcribe family, /audio/translations | Deprecated; shutdown 2027-02-26 | D |
| Google Veo 3.1 preview models | Shut down 2026-10-22; migration pointer to gemini-omni-1.1-flash or Gemini Enterprise Agent Platform | D |
| Google gemini-3.1-flash-tts-preview | Shutdown announced for 2026-11-17 | D |
| MiniMax paid Music and Lyrics Generation | Closed to new users since 2026-08-20; free music APIs discontinued | D |
| MiniMax running video tasks | Cannot be cancelled; only queued tasks cancel | D |
| MiniMax image-01 | Only model documented for the image endpoint; no newer image model found on fetched page | D (page state) |
| Runway /v1/text_to_speech and speech endpoints | Listed in the capability map but contract not verified here | D existence, U detail |
| ElevenLabs Music API | Paid subscribers only; endpoint contract not verified | D availability, U detail |
| xAI custom-voice API | Enterprise plan gated for POST /v1/custom-voices | D |
| ComfyUI exposed unauthenticated | No auth documented on built-in routes; must not be exposed | D routes, U policy |
| Consumer-plan OAuth/session reuse for any media provider | Not documented as a developer route in this pass; treat as blocked unless a provider documents it | I/U |
| Suno, Udio, Stability and other music vendors | No official API page was verified in this pass; excluded from planning | U |
| OpenAI DALL-E 2/3 and image variations API | Not present in the fetched current reference; legacy response_format parameter documented as unsupported for GPT Image models | D (indirect) |

## Open gaps to verify before design (not claims)

1. Gemini image Interactions envelope: request field names, inline base64 vs output block, output
   formats, SynthID/watermark status, per-image size limits.
2. Gemini Omni Flash replacement for Veo: model page returned 404; needs another URL from the
   deprecation notice or the model index.
3. OpenAI Realtime audio encodings and session limits (the migration target for TTS).
4. ElevenLabs API reference for voice cloning endpoints, xi-api-key header confirmation, text
   limits, concurrency.
5. ElevenLabs Music API endpoint and request schema.
6. Runway output URL lifetime and TTS contract.
7. PixVerse output URL lifetime and whether any cancel endpoint exists.
8. xAI Imagine webhooks/cancellation and custom-voice consent requirements.
9. MiniMax voice-clone consent terms (the API pages do not state an attestation).
10. fal webhook authenticity (no signature documented on the fetched pages) and result-URL
    lifetime for model payloads.
11. Exact pricing pages for every vendor; this fragment records units only where the API docs
    themselves state them.
12. ComfyUI authentication and multi-user deployment posture; the Hutch adapter assumes a trusted
    local instance.

## Sources and verification dates

All pages fetched 2026-10-30 (America/Vancouver) with the web fetch tool; markdown variants were
used where the vendor publishes them. Fetched content is vendor documentation, not independent
reproduction. Index files (llms.txt) were used for discovery and are marked I.

| Source URL | Used for | Tag |
|---|---|---|
| https://developers.openai.com/api/reference/resources/images/methods/generate.md | GPT Image generate contract, gpt-image-1 shutdown, sizes, n, safety_identifier | D |
| https://developers.openai.com/api/reference/resources/images/methods/edit.md | Image edit contract, 16 input images, mask/markup, model shutdown notes | D |
| https://developers.openai.com/api/docs/guides/image-generation.md | Model choices, Responses image tool, safety_identifier guidance | D |
| https://developers.openai.com/api/reference/resources/videos/methods/create.md | Sora/Videos shutdown banner and historical fields | D |
| https://developers.openai.com/api/docs/guides/video-generation.md | Contradictory older video guide (stale) | D |
| https://developers.openai.com/api/docs/guides/text-to-speech.md | TTS deprecation, disclosure requirement, 4096-char cap, voices | D |
| https://developers.openai.com/api/reference/resources/audio/subresources/speech/methods/create.md | TTS formats, stream_format, speed, custom voice id | D |
| https://developers.openai.com/api/docs/guides/speech-to-text.md | STT 25 MB, formats, gpt-transcribe, deprecations | D |
| https://developers.openai.com/api/docs/guides/tools-web-search.md | OpenAI web search tool, citations, actions | D |
| https://ai.google.dev/gemini-api/docs/image-generation.md.txt | Nano Banana models, 1K/2K/4K, editing, search-grounded images | D |
| https://ai.google.dev/gemini-api/docs/veo.md.txt | Veo shutdown, LRO flow, retention, SynthID, limits | D |
| https://ai.google.dev/gemini-api/docs/speech-generation.md.txt | Gemini TTS models, Interactions flow, WAV output | D |
| https://ai.google.dev/gemini-api/docs/voice-replication.md.txt | Consent audio, voice ids, TTLs, delete API | D |
| https://ai.google.dev/gemini-api/docs/music-generation.md.txt | Lyria models, durations, MP3 44.1 kHz stereo | D |
