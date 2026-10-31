# 04 - Architecture and ADRs

Date: 2026-10-30. Status: first implementation slices landed on branch provider-platform
(commits 4b0560d1 and f236c2bb); the capability, readiness, runtime-registry and UI slices follow.

## Diagnosis (repo evidence in drafts/04-current-state.md)

1. There is no provider identity layer. Provider identity is duplicated across OFFICIAL_HOSTS in
   providers/registry.py, PRESET_URLS in providers/openai_compat.py, LOCAL_PROVIDERS in
   providers/pricing.py, HOSTED_KEYS/KNOWN_PROVIDERS in modelchoices.py and RESERVED in
   connections.py. Adding a provider touches six or more places plus hand-maintained data, and
   validate_spec accepts any slug while validate_override rejects anything outside KNOWN_PROVIDERS.
2. Authentication is represented as a connection plus one of five bespoke credential mechanisms,
   with no provider-scoped account view. Multiple accounts are possible only as separately named
   connections; nothing groups them, shows which provider they belong to, or reports billing/status
   in provider terms.
3. Capability evidence is fragmented: a route compatibility matrix, a per-model catalog cache, passive
   tool-call observations and free-text limitations. There is no recorded distinction between
   documented, advertised, observed and live-verified capability.
4. The compatibility matrix has stale claims (Anthropic model listing, OpenCode executor status,
   vision support) and no dated statement that no live provider was used.
5. External runtimes are selected by a switch in runtime/__init__.py: builtin, opencode, pi. Only the
   built-in runtime reserves usage before model calls. The coding handoff is a separate interactive
   feature. There is no runtime registry or capability contract describing these boundaries.
6. Oversized frozen files (server/app.py create_app 5,307 lines; runtime/builtin.py execute 774;
   Store class 9,990) forbid growth. New abstractions must be new modules with additive seams.

## Decisions (see ADR-0026 for the formal record)

- D1: Add a validated, bundled provider identity catalogue (providers/catalog.py +
  data/providers.json). It answers what a provider is, which services and auth methods it offers and
  which are implemented. It is not a protocol adapter and never changes model routing.
- D2: Resolve authentication profiles as a view over existing connections (providers/accounts.py).
  Connection storage is unchanged except optional provider/auth_method metadata; multiple accounts
  remain ordinary named connections and model specs keep naming the connection explicitly.
- D3: Record capability evidence as levels with a source and date, scoped to the narrowest known
  provider/endpoint/auth-route/model/runtime (next slice: providers/capabilities.py). Documented data
  comes from the catalogue and compatibility matrix; observed data comes from the existing immutable
  tool-call observation table; live-verified data is empty in this environment.
- D4: Expose readiness as explicit states (available, needs auth, expired, restricted, unavailable,
  capability unverified, unsupported runtime, needs configuration, blocked) from local facts only
  (next slice: providers/readiness.py). Readiness never performs inference.
- D5: Introduce a runtime registry that describes builtin, managed OpenCode, Pi and documented CLI
  runtimes with lifecycle/credential/capability boundaries. It does not enable a new executor;
  get_runtime behaviour is preserved.
- D6: Keep protocol adapters separate and additive. No new adapter is shipped without a real,
  testable contract; Gemini/Responses generalisation is deferred rather than stubbed.
- D7: Research-only providers stay in the catalogue with documented/deferred/blocked/retired status
  and dated sources. The website and UI must show that status, never a generic "supported" badge.
- D8: Fix stale documentation instead of preserving it: compat.json corrected, provider-compatibility
  updated. Docs are part of the product contract.

## Contracts and compatibility

| Contract | Change | Compatibility |
|---|---|---|
| providers.json | New bundled data, validated strictly (closed vocabularies, unique ids, HTTPS source URLs, one template per provider) | Missing/malformed catalogue fails closed for provider surfaces only; existing model picker/runs unaffected |
| connections.json templates | Optional provider and auth_method fields | Existing saved rows load unchanged; missing fields are derived from the template at read time |
| connections.py Connection | Optional provider/auth_method attributes, validated | No state migration; old rows and keys keep working |
| providers/accounts.py | New read-only view; rename and disconnect helpers | No writes except existing connection update/clear-key paths |
| compat.json | Corrected stale rows; reviewed date updated | Route shape/validation unchanged; tests re-run |
| docs/research/2026-10-provider-platform | New dated research package | Referenced from docs/README, connections/models/architecture later |

## Security posture preserved or improved

- No ambient credential is sent to a custom endpoint; the existing exact-host rule is kept.
- Account profiles expose credential source names, never values; disconnect states what it did not do.
- Readiness and capability reports perform no inference and never upgrade a status from a listing.
- No consumer-session reuse, proxy, or client impersonation is implemented; blocked routes are
  recorded with alternatives.
- Open security gap documented for a follow-up slice: outside Strict Offline the provider layer has no
  private-range allowlist or redirect/DNS pinning for custom endpoints. It is recorded in the security
  review and 07-ROLLOUT-AND-MIGRATION.md rather than silently ignored.

## Evidence

- drafts/04-current-state.md (repo archaeology with file:line references)
- drafts/01-core-providers.md, 02-hosting-gateway-local.md, 03-media-speech-search.md (dated sources)
- ADR-0026 (docs/adr/0026-provider-identity-accounts-capabilities-and-runtimes.md)

## Live evidence addendum (2026-10-30)

After the initial slice, owner-authorized live tests added two dated live-verified text entries to the
capability registry: deepseek/deepseek-flash through the built-in runtime and
opencode/deepseek/deepseek-flash through the managed OpenCode runtime. The registry still refuses to
generalize from those runs: no tool, streaming, vision or cross-provider claim is derived from them.
The direct DeepSeek route is now a real implemented connection template; the managed OpenCode runtime was
already implemented and is now live-verified for text. Everything else remains unverified, and the
custom-endpoint SSRF-adjacent hardening gap is unchanged.
