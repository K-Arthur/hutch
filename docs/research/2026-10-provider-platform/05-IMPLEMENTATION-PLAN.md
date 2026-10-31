# 05 - Implementation plan

Slices are independently reviewable and committed separately. Each slice lists the files it owns and
the check that must pass before the commit. Slices S0-S2 are the foundation; later slices may be
reordered if research changes the risk picture.

| Slice | Deliverable | Files (owned by this slice) | Verification |
|---|---|---|---|
| S0 | Research package and plan | `docs/research/2026-10-provider-platform/00..07`, README, artifacts | docs checker + spot read |
| S1 | Provider identity catalogue (declarative, versioned) | `src/hutch/providers/catalog.py`, `src/hutch/data/providers.json`, `tests/test_provider_catalog.py` | focused pytest covers schema/categories/status/URL safety |
| S2 | Authentication-profile layer over connections | `src/hutch/connections.py` (additive fields/helpers only), `src/hutch/providers/accounts.py`, `tests/test_provider_accounts.py`, connection template metadata | existing `tests/test_connections.py` + new tests; restart persistence |
| S3 | Capability evidence registry | `src/hutch/providers/capabilities.py`, `tests/test_provider_capabilities.py`; read-only use of `store.model_capability_observations_for` | levels/scopes/evidence tests; API output check |
| S4 | Provider/account readiness states | `src/hutch/providers/readiness.py`, `tests/test_provider_readiness.py` | state matrix tests over real ConnectionBook state |
| S5 | Runtime registry and local inference discovery | `src/hutch/runtime/registry.py`, `src/hutch/providers/discovery.py`, tests | existing OpenCode tests unchanged + discovery unit tests |
| S6 | Protocol adapter: Gemini native | `src/hutch/providers/gemini.py`, `src/hutch/providers/connection.py`, `src/hutch/connections.py` protocol list, `src/hutch/data/compat.json` route, tests | serialization/streaming parse tests; compat validation |
| S7 | Server surfaces: provider catalogue API/page, account readiness, model-page evidence | `src/hutch/server/pages_providers.py`, templates `providers.html`, `models.html` (additive), `pages.py` registration, `pages_models.py` (additive) | API tests + real server render check |
| S8 | Visual validation | Playwright captures under `docs/research/2026-10-provider-platform/artifacts/visual/` | 5 viewports, real states, manual inspection notes |
| S9 | Documentation and ADR | `docs/adr/0025-...`, `docs/architecture.md`, `docs/connections.md`, `docs/models.md`, `docs/realignment/provider-compatibility.md`, `docs/README.md`, `docs/roadmap.md` | link/claim checker + review |
| S10 | Marketing website | `website/index.html`, `website/src/input.css` (+ rebuild), `docs/marketing-site.md`, `tests/e2e/test_website.py` (only if the suite is runnable) | CSS rebuild, captures at 5 viewports, metadata/FAQ parity |
| S11 | Review, validation, integration | ledgers, final report | independent verifier PASS; merge into main |

## Ordering and dependencies

- S1 is the contract for S2-S7; do not start S2+ until the catalogue schema is validated.
- S2 changes `connections.py` additively: existing connection rows and templates must keep loading
  with derived defaults. The connection file format gains optional fields only.
- S3 reads `compat.json` and existing passive observations; it does not add a second capability store.
- S5 must not change runtime selection behaviour. `get_runtime` keeps the same outcomes for existing
  Bot documents; the registry describes and validates, it does not silently enable a new executor.
- S6 adds a protocol; it does not relax the rule that ambient provider keys are sent only to the
  provider's official host and that a selected model is never replaced after failure.

## Non-goals for this delivery (recorded, not silently dropped)

- Implementing dozens of hosted adapters that cannot be exercised live. The catalogue records them
  with `documented`/`deferred` status instead of shipping unverifiable code.
- New OAuth client registrations (no publisher application IDs exist here).
- Native Claude/Gemini/Codex executor runtimes; the registry records their contract and installed
  state, but enabling a CLI executor requires a permission/usage contract that does not exist yet.
- Video/music/speech provider adapters without a verifiable job contract; media research is recorded
  and existing job/storage interfaces are audited instead.

## Slice status (2026-10-31)

| Slice | Status | Evidence |
|---|---|---|
| S0 | done | this package plus `scripts/audit_provider_research.py` |
| S1 | done | `src/hutch/providers/catalog.py`, `src/hutch/data/providers.json`, `tests/test_provider_catalog.py` |
| S2 | done | `src/hutch/providers/accounts.py`, connections metadata, `tests/test_provider_accounts.py` |
| S3 | done | `src/hutch/providers/capabilities.py`, `tests/test_provider_capabilities.py` |
| S4 | done | `src/hutch/providers/readiness.py`, `tests/test_provider_readiness.py` |
| S5 | done | `src/hutch/runtime/registry.py`, `src/hutch/providers/discovery.py` |
| S6 | done for Gemini only | `src/hutch/providers/gemini.py` (transport), `src/hutch/providers/gemini_wire.py` (conversion), `tests/test_provider_gemini.py` (29 tests), wired through `connections.py`, `providers/connection.py`, `providers/registry.py`, `toolcalling/profiles.py`, `toolcalling/profiles_routes.py`, `runtime/ladder.py`, `data/connections.json`, `data/providers.json`, `data/compat.json` |
| S7 | done | providers page/API and model readiness surfaces |
| S8 | done | `artifacts/visual/` five-viewport captures from the 2026-10-30 run |
| S9 | partial | ADR-0026 and the docs updates landed; this addendum covers the Gemini route |
| S10 | done | website provider section and `docs/marketing-site.md` |
| S11 | done for the 2026-10-30 delivery | see the final-integration section of the validation ledger |
| S6b | done | 25 hosted OpenAI-compatible routes wired from vendor-documented endpoints and verified reachable without a credential: `src/hutch/data/connections.json`, `src/hutch/data/providers.json`, `tests/test_provider_routes.py`, evidence in `artifacts/live-verification/endpoint-reachability-2026-10-31.json` |
| S6c | done | Speech-to-text: declarative route in four xiaomi templates, `src/hutch/providers/transcription.py`, `src/hutch/tools/transcribe.py`, `tests/test_provider_transcription.py`, `tests/test_transcribe_tool.py`; live-verified on `mimo-v2.5-asr` (artifact `artifacts/live-verification/xiaomi-transcription-live-2026-10-31.json`) |
| S6d | done | Tool calling and streaming live-verified on `mimo-v2.6-flash` through the CLI run path and the adapter; streamed reasoning deltas were found dropped and are now assembled (`toolcalling/streamassembly.py`, `providers/openai_compat.py`, `tests/test_provider_stream_reasoning.py`); capability registry records the dated entries. Artifacts: `xiaomi-tool-calling-streaming-live-2026-10-31.json`, `xiaomi-adapter-tool-calls-2026-10-31.json`, `xiaomi-stream-shape-2026-10-31.json` |
| S6e | done | Speech synthesis: declarative `speech` block in the four Xiaomi templates, `src/hutch/media/providers/speech.py` as a `MediaBackend`, `create_media` kind `audio` wired through the existing media job ledger and media store, `tests/test_media_speech.py` (32 tests); live-verified on `mimo-v2.5-tts` and round-trip transcribed (artifact `artifacts/live-verification/xiaomi-speech-live-2026-10-31.json`) |
| S6f | implemented, live BLOCKED | Provider-native search: declarative `search` block in the four Xiaomi templates, `src/hutch/providers/search.py` (route, payload, citation parsing, transport), `src/hutch/tools/search.py` (`search_web`), group `search` and Strict Offline withholding, `tests/test_provider_search.py` (37 tests). The live run reached the vendor's validator and was refused with `webSearchEnabled is false`: the account has not activated the web-search plugin, so no search executed. Artifact `artifacts/live-verification/xiaomi-search-live-2026-10-31.json` records all three probes and the blocker |

S6 remains open for every other protocol: Claude CLI/Gemini CLI/Codex executors and video/music
adapters are still documented rather than implemented. Speech-to-text is no
longer in that list: `transcribe_audio` transcribes one workspace wav/mp3 through a connection that
declares the route, and the live run above is the evidence. Speech synthesis left it too:
`create_media(kind=audio)` speaks one utterance through a connection's `speech` route and stores the
wav through the media job ledger. Streaming synthesis, mp3/pcm output, voice design and cloning
models, and every non-Xiaomi speech vendor remain unimplemented or unverified.

Provider-native search is implemented but not verified, and the reason is not code: the vendor
refused the documented tool on this account because the web-search plugin is not activated
(`webSearchEnabled is false`). Activation is an owner billing decision in the provider console, so the
slice stays labelled blocked rather than live-verified until someone makes it. Until then the honest
statement is: Hutch builds the documented request, reports the provider's own reason, does not retry
and does not fall back.
Tool calling and streaming are no longer in it either, for one model on one route: two calls in a
single streamed turn were executed end to end, and every live model call in that run travelled over
SSE. What remains for streaming is what a user sees - Hutch assembles the stream server-side and does
not paint tokens progressively - and cancellation mid-stream, which is tested but not live-exercised.
The next slice
that a new protocol unlocks should be chosen from live credential availability, because an adapter that
cannot be exercised is only contract-tested code.

S6b deliberately did not add a second transport. Those 25 providers share the existing OpenAI Chat
Completions adapter, so the slice was declarative data plus the evidence that pins it. Shipping a route
whose endpoint was never reached would have been a catalogue claim, not an implementation; the
credential-free probe is what makes "implemented-unverified" an honest label rather than a guess. The
remaining gap for all 25 is the same one: no authenticated inference, so no model, capability, price or
usage claim exists for them.
