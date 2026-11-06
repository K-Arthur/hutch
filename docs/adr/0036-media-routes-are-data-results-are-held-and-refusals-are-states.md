# ADR-0036: Media routes are data, paid results are held on disk, and a refusal is a state

Status: accepted, 2026-11-06.

## Context

Phase 6 of the provider expansion looked at image, video and speech services, and at the job ledger that
fronts them (research record `docs/research/2026-11-provider-expansion/07-MEDIA-SPEECH-SEARCH.md`). The code
and the vendors' own pages showed:

- The synchronous backends (OpenAI Images, chat speech) held the bytes they had just been paid for only in
  memory. A crash between the provider's answer and the media store commit lost paid output, and reconcile could
  only say so.
- OpenAI Images sent `response_format` to every model except the exact string `gpt-image-1`, and used DALL-E
  sizes for GPT Image; GPT Image models reject both. The OpenAI SDK also retried billable calls by default.
- Failure travels inside an HTTP 200 body for some providers (MiniMax `base_resp`, Gemini TTS with no audio
  block), and content-policy declines (`moderation_blocked`, MiniMax 1026, PixVerse status 7) were reported as
  crashes or generic failures.
- `create_media` waits a bounded time, then returns. A five-minute video kept running and billing with no way to
  observe, finish or cancel it outside that call.
- With several capable backends, the job service silently chose the alphabetically first, which is a choice
  between billing accounts.
- `finalize()` returned a bare row on its failure paths while callers unpack `(payload, row)`.
- Two flagship media APIs were retired: OpenAI Sora 2 and the Videos API (2026-09-24, no replacement) and the
  Veo preview models (2026-10-22).

## Decision

1. **Routes are rows in `data/media-routes.json`**, validated by `media/providers/route_spec.py`, driven by two
   backends: `sync` (one request returns the media) and `task` (submit, poll, fetch). A route cites dated sources,
   declares limits, names a price row, and is `implemented-unverified`, `documented`, `blocked` or `retired`.
   Only `implemented-unverified` rows are built. A wire the table cannot express names an `adapter` (OpenAI
   Images). A route whose wire I could not read stays `documented` (Runway, MiniMax video, Google Omni).
2. **A paid synchronous result is written to an owner-only, atomic, SHA-256-checked spool before `submit`
   returns** (`media/spool.py`). Reconcile leaves a recoverable job running; the ledger can finalize it after a
   restart without a second request. Without a spool the hold is in memory and `can_recover` says false.
3. **An HTTP 200 is not success.** In-body envelopes, refusal markers and responses with no media are failures
   that say the provider may have billed. Nothing is retried; the SDK's retries are off for billable calls and
   fal is sent `X-Fal-No-Retry`.
4. **A refusal is a service status.** It is stored as `failed` with a `refused:` prefix (the store CHECK has five
   states) and surfaced as `refused`, with the provider's reason and the advice to rephrase, not retry.
5. **Backends are built per call from a configured connection or a named environment variable, and each is
   labeled** (who receives the prompt, which credential, which billing). When more than one backend can produce a
   kind, `backend_for` refuses and names them. The environment path is labeled ambient.
6. **The approval shows a dated estimate with its basis, or says the cost is unknown** (`media/cost.py`,
   `data/media-prices.json`). An estimate is recorded in the run ledger as `estimated`; an unreadable price is
   `unpriced` with no number. The vendor account stays authoritative.
7. **Requests are checked against the route's documented limits before the approval prompt.**
8. **A job outlives the tool call.** `GET /api/v1/media/jobs`, `POST .../advance` and `POST .../cancel` observe,
   finish (fetch, validate, hash, store, record usage) or cancel a job. They are absent from
   `REMOTE_ROUTE_CAPABILITIES`, so paired phones are denied. Cancel is confirmed only when the provider says so.
9. **Result URLs are consumed once through one bounded downloader on the pinned transport**
   (`media/fetch.py`); credentials are never sent to the result host.

## Consequences

- Behavior change: a request with several capable backends now needs `backend_hint`. The tool's error names them.
- Behavior change: an ambient `OPENAI_API_KEY` backend and a configured OpenAI connection are two backends.
- `finalize()` now always returns `(payload, row)`; `payload` is `{}` for a failed or refused job.
- The model of a media route is data. A stale id is a data fix, not a code change, and the key's own model list
  stays authoritative. No per-user model override exists yet.
- No route is live-verified. No provider credential existed in the environment; the recorded run uses a
  stand-in provider and proves Hutch's recovery and ledger only.
- Not changed: the approval model (`create_media` is outward, ask-by-default, never sticky), the media store
  format limits (audio is wav), Strict Offline, and `live_search`.
