# Provider platform: identities, accounts, evidence and runtimes

Added 2026-10-30. This is the current guide to Hutch's provider layer. The dated research that supports
it lives in docs/research/2026-10-provider-platform/README.md, and the formal decision is ADR-0026 in
docs/adr/0026-provider-identity-accounts-capabilities-and-runtimes.md.

## The separation

| Concept | Answers | Where it lives |
|---|---|---|
| Provider identity | What service is this, what does it offer, and what is actually implemented? | src/hutch/data/providers.json, validated by src/hutch/providers/catalog.py |
| Authentication profile | Which named account would pay, with what credential source and billing relationship? | connections + src/hutch/providers/accounts.py |
| Endpoint / route | Which URL, region and protocol contract? | connection templates, data/connections.json, data/compat.json |
| Protocol adapter | How are messages, tools and streams encoded? | src/hutch/providers/openai_compat.py, openai_responses.py, claude.py, ollama.py, gemini.py, transcription.py (speech-to-text over a chat-completions audio part) |
| Execution runtime | What executes the work, under which permissions and budget? | src/hutch/runtime/registry.py plus the existing runtime switch |
| Capability evidence | How is a capability known, at what scope, from which dated source? | src/hutch/providers/capabilities.py |
| Readiness | Would this account or route work now, and what is missing? | src/hutch/providers/readiness.py |
| Route resolution | Which provider, account, billing relationship, runtime and model a spec resolves to now | src/hutch/providers/routing.py |
| Media / search | Which complementary service produces or grounds content? | existing media job/storage/validation lifecycle, the grounding plane, and the governed transcription tool |

A provider entry is not a support claim. Integration status uses a closed vocabulary: implemented,
implemented-unverified, experimental, documented (research only), blocked, retired, deferred. Live
results are dated and recorded in the validation ledger; a route listed here is not verified merely
because its adapter exists.

## Account rules

- Multiple accounts per provider are ordinary named connections; a model spec names the account
  (account-name/model), so selection is explicit and survives restarts and catalogue refreshes.
- Credentials stay in the existing protected stores: environment variables for the official host,
  0600 key files, OAuth account stores, or the OS secret store for calendar/mail. No credential value
  is returned by an API, rendered on a page, or written to the database.
- Renaming an account changes its local label only; the connection name used in model specs is stable.
- "Remove local key" removes Hutch's copy. It does not claim provider-side revocation; where an
  official revoke endpoint exists, the provider's own flow reports the result separately.

### Credential lifecycle (2026-11-06, ADR-0029)

- A saved OAuth account is projected into `active`, `expired`, `revoked` or `missing`. A refresh
  token keeps it active after access expiry; an access token inside the 60-second skew with no
  refresh token is expired. Readiness maps expired to `authentication_expired` and revoked to
  `needs_authentication`.
- `has_key` for a ChatGPT connection requires an active credential. Expired or revoked accounts do
  not count as a key and do not trigger model discovery.
- A refresh is single-flight per account across processes: the exclusive file lock is held across
  the token request, and the second caller re-reads the rotated record. A failed refresh writes
  nothing and never deletes the stored credential.
- Sign in with ChatGPT uses OpenAI's local PKCE loopback callback. A remote dashboard cannot finish
  that flow and says so; Hutch does not implement an undocumented device-code client. OpenCode's
  OAuth/device flow stays with the official OpenCode server or CLI.
- Disconnect distinguishes local credential removal from provider revocation, and reports remote
  revocation as confirmed or unconfirmed.

## Route resolution and the billing boundary

Added 2026-11-06 (ADR-0028). `GET /api/v1/provider-resolution?spec=...&runtime=...` returns the
resolved tuple: provider, account, account source, billing, model, runtime, protocol, endpoint and
readiness state. It reads local configuration only and never substitutes a choice.

- A spec that names a provider while two or more named accounts map to it resolves to
  `needs_configuration` with no account. Hutch does not choose who pays, and an ambient key does not
  break the tie.
- An ambient key that may be used is named as the account source (`ambient environment
  (OPENAI_API_KEY)`). A key aimed at a non-official endpoint is withheld and reported as needing
  authentication.
- A fallback or escalation from a subscription primary to per-token/credits billing is refused
  before the call. Making the metered route primary is the explicit decision.
- Schema 91 writes the provider prefix the runtime already applied to a bare model name into saved
  `model`, `fallbacks`, `escalation.to` and `task_routes`; billing and fallback order are unchanged.
- The Providers page banner is generated from the recorded live evidence and catalogue status counts,
  so it cannot drift from the ledger without a test failing.

## Plan routes and separate memberships

Added 2026-11-06 (ADR-0032, Phase 3). The catalogue now holds 64 identities.

- `kimi-coding` (Kimi Code membership key, Anthropic Messages, subscription, acknowledgement required) and
  `opencode-zen` (OpenCode Console prepaid API at `https://opencode.ai/inference/v1`) are their own
  identities. Kimi Code was an auth method of `moonshot`; that method is gone and `moonshot-cn` covers the
  China host. Both new routes are implemented-unverified: no live key has exercised either.
- `qwen` has pay-as-you-go templates for the Singapore and Beijing hosts. Its Coding Plan method is blocked
  (interactive-use-only terms); Token Plan is not offered.
- The Z.AI Coding Plan method is blocked (supported-tools-only policy); `zai-cn` covers the China pay-as-you-go
  host.
- `google` no longer claims a coding CLI. Gemini CLI was replaced by Antigravity CLI on 2026-06-18 and Google
  treats third-party use of its OAuth tokens as a terms violation.
- No template may point at a recorded plan endpoint; `tests/test_flagship_routes.py` enforces it. Templates
  whose vendor model list was not verified do not read one.
- Not built: the Claude CLI delegate, the Codex native runtime, Grok OAuth, MiniMax plan sign-in. Each is
  `documented` and recorded in `docs/research/2026-11-provider-expansion/04-FLAGSHIP-ROUTES.md`.

## Capability and readiness rules

- Levels are documented, advertised, observed and live-verified, scoped to provider, endpoint,
  authentication route, model or runtime. A model listing proves discovery only. A text success does
  not prove tools; a tool call does not prove images.
- Observed evidence comes only from the existing immutable tool-call observation table (an owned run),
  never from a synthetic probe. Live-verified entries are a separate, hand-recorded dataset: each one
  names the exact model, the date, the route and the boundary of what was exercised, and each is backed
  by a dated artifact in the research package. A live entry for one model does not upgrade another model
  or another capability.
- Readiness is computed from local configuration and bounded loopback discovery. It never executes
  inference, refreshes a token, or substitutes a model/provider/account/runtime.
- States include available, needs authentication, authentication expired, subscription restricted,
  model unavailable, endpoint unavailable, capability unverified, unsupported runtime, needs
  configuration and blocked by policy. Capability unverified is honest, not an error.

## Runtime rules

Only the built-in runtime reserves provider usage before a model call and applies Hutch's approvals,
path jail and sandbox. The managed OpenCode runtime is experimental and keeps its own tools and
credentials; approved tools can run with the user's OS authority outside Hutch's shell sandbox. Pi is
blocked. Documented CLIs (Claude Code, Codex, Gemini CLI) are described, detected for information, and
never enabled by registration. See docs/runtime-setup.md for prerequisites.

## Surfaces

- /providers (dashboard): catalogue by category, account list with readiness, local loopback services,
  runtime boundaries, and search/filter.
- /models: configured routes with an explicit readiness panel and a link to the provider catalogue.
- /legacy/connections: key/terms/allowance management. /api/v1/providers, /api/v1/provider-accounts,
  /api/v1/provider-capabilities, /api/v1/provider-readiness and /api/v1/runtime-catalog expose the same
  records; none can change a routing decision.

## Known limits

- Live verification as of 2026-10-31 covers text generation on two owner-authorized DeepSeek routes,
the managed OpenCode runtime, and Xiaomi MiMo (`mimo-v2.6-flash`, `mimo-v2.6-pro`); on MiMo it also
covers tool calling (two calls in one turn, dispatched and answered from), the streamed transport path
with no non-streaming retry, and speech-to-text on `mimo-v2.5-asr` through `transcribe_audio`. Every other
hosted provider remains unverified, and vision, cancellation mid-stream and progressive token rendering
were not exercised anywhere.
- Custom endpoints keep Hutch's existing credential scoping (ambient keys go only to official hosts,
  embedded URL credentials are refused, Strict Offline requires loopback). Outside Strict Offline a
  private-range allowlist and redirect/DNS pinning are not implemented in the provider layer: reviewed
  and recorded, not silently assumed safe.
- Media expansion is partly shipped: speech-to-text and connection-scoped speech synthesis are
  implemented and live-verified against one account, and the synthesized clip was round-trip
  transcribed. The two-host audio-overview pipeline remains for podcast rendering. Provider-native
  search is implemented but **blocked on account entitlement**: the vendor refused the documented
  request because the account's web-search plugin is not activated, so no live citation was ever
  parsed. Video, music, image editing, streaming synthesis, mp3/pcm output remain
  research-complete and deferred rather than stubbed, and no demo fixtures exist.
- `live_search` (Hutch's own grounding fan-out) and `search_web` (a provider's search plugin) are
  different capabilities with different evidence. Nothing upgrades one from the other: the local
  fan-out needs no provider entitlement, and the provider route stays unverified until an account
  with the plugin runs it.
- Route resolution is exposed through `/api/v1/provider-resolution`. The dashboard picker does not
  yet show the resolved tuple before the first send (Phase 7), and the resolver is read-only: it
  does not persist a per-run route snapshot.

## Live evidence (2026-10-30 and 2026-10-31)

Owner-authorized live testing exercised the direct DeepSeek route (built-in runtime) and the managed
OpenCode runtime with a DeepSeek model. Both completed a real text request and returned the expected token;
the capability registry carries two dated live-verified text entries for exactly those model routes.
On 2026-10-31 a second account (Xiaomi MiMo Token Plan) was exercised for text generation, then for
speech-to-text, then for tool calling and streaming. One wav file produced by the same account's TTS was
transcribed through the `transcribe_audio` tool with matching text and provider-reported usage. A governed
CLI run then issued two tool calls in a single streamed turn - `list_files` and `read_file` - which Hutch
validated, dispatched and answered from, with every step reporting `streamed=True` and no non-streaming
retry. That run exposed a second real defect: the streamed path discarded the `reasoning_content` deltas
the provider sends (a raw wire probe confirmed the provider sends them), so a streamed call reported less
output than the same call batched. The assembler now keeps them. Speech synthesis then ran through
`create_media(kind="audio")` on `mimo-v2.5-tts`: the 177 KB, 3.68 s wav was stored with a verified
SHA-256 and transcribed back through `transcribe_audio` as the same sentence (the ASR heard "Hutch"
as "Hatch"). No other provider, and no
vision, video, music, cancellation or search capability, was live-verified. The stored OpenCode Go key reported expired
and the attempted managed run failed explicitly with zero recorded cost; that failure is kept as evidence
rather than retried or routed elsewhere.
