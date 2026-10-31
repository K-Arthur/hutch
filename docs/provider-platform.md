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
| Protocol adapter | How are messages, tools and streams encoded? | src/hutch/providers/openai_compat.py, openai_responses.py, claude.py, ollama.py |
| Execution runtime | What executes the work, under which permissions and budget? | src/hutch/runtime/registry.py plus the existing runtime switch |
| Capability evidence | How is a capability known, at what scope, from which dated source? | src/hutch/providers/capabilities.py |
| Readiness | Would this account or route work now, and what is missing? | src/hutch/providers/readiness.py |
| Media / search | Which complementary service produces or grounds content? | existing media job/storage/validation lifecycle and grounding plane |

A provider entry is not a support claim. Integration status uses a closed vocabulary: implemented,
implemented-unverified, experimental, documented (research only), blocked, retired, deferred. The
validation ledger records that this build performed no hosted live verification.

## Account rules

- Multiple accounts per provider are ordinary named connections; a model spec names the account
  (account-name/model), so selection is explicit and survives restarts and catalogue refreshes.
- Credentials stay in the existing protected stores: environment variables for the official host,
  0600 key files, OAuth account stores, or the OS secret store for calendar/mail. No credential value
  is returned by an API, rendered on a page, or written to the database.
- Renaming an account changes its local label only; the connection name used in model specs is stable.
- "Remove local key" removes Hutch's copy. It does not claim provider-side revocation; where an
  official revoke endpoint exists, the provider's own flow reports the result separately.

## Capability and readiness rules

- Levels are documented, advertised, observed and live-verified, scoped to provider, endpoint,
  authentication route, model or runtime. A model listing proves discovery only. A text success does
  not prove tools; a tool call does not prove images.
- Observed evidence comes only from the existing immutable tool-call observation table (an owned run),
  never from a synthetic probe.
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

- Live verification is limited to two owner-authorized DeepSeek text routes dated 2026-10-30 (direct built-in runtime and managed OpenCode runtime). Every other hosted provider and every other capability remains unverified.
- Custom endpoints keep Hutch's existing credential scoping (ambient keys go only to official hosts,
  embedded URL credentials are refused, Strict Offline requires loopback). Outside Strict Offline a
  private-range allowlist and redirect/DNS pinning are not implemented in the provider layer: reviewed
  and recorded, not silently assumed safe.
- Media expansion is research-complete but not shipped: video, music, transcription and provider-native
  search adapters are deferred rather than stubbed, and no demo fixtures exist.

## Live evidence (2026-10-30)

Owner-authorized live testing exercised the direct DeepSeek route (built-in runtime) and the managed
OpenCode runtime with a DeepSeek model. Both completed a real text request and returned the expected token;
the capability registry carries two dated live-verified text entries for exactly those model routes.
No other provider, and no tool, streaming, vision, audio, video, music or search capability, was
live-verified. The stored OpenCode Go key reported expired and the attempted managed run failed explicitly
with zero recorded cost; that failure is kept as evidence rather than retried or routed elsewhere.
