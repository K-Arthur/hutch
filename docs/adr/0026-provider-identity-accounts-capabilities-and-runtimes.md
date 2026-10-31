# ADR-0026: Provider identity, account profiles, capability evidence and runtimes

Status: accepted (2026-10-30). Scope: additive provider-platform expansion.

## Context

Provider-specific knowledge (official hosts, preset endpoints, local-provider lists, known-provider
validation) is duplicated across at least six modules, and a single "is this supported?" flag conflates
provider identity, authentication, protocol, runtime, capability and billing. Users cannot see which
provider an account belongs to, which accounts share a billing relationship, or how confidently a
capability is known. External runtimes are selected by a switch without an explicit contract, and the
compatibility matrix has stale claims. The delivery request requires independent selection of model,
provider, account, runtime, transport, tools/modalities and complementary services without coupling.

## Decision

1. Introduce a validated provider identity catalogue as bundled data plus a small validating module.
   It classifies each service (vendor, serving platform, gateway, enterprise cloud, subscription
   service, local runtime, media platform, compatible endpoint), lists documented services, protocols,
   authentication methods (with mechanism, billing, status and sources) and the connection templates
   that implement a route. An implemented status requires a real route.
2. Keep authentication in the existing connection store. Add optional provider/auth_method metadata,
   and resolve accounts as a read-only view grouped by provider identity. Multiple accounts are named
   connections; model specs continue to name the account explicitly. Disconnect distinguishes local
   key removal from provider-side revocation.
3. Record capability evidence with levels (documented, advertised, observed, live-verified), a source,
   a date and the narrowest scope known. A catalogue listing never upgrades a capability; live-verified
   evidence must name the exercise that produced it.
4. Expose readiness as explicit states derived from local configuration; readiness never performs
   inference and never substitutes a model, provider, account, endpoint or runtime.
5. Introduce a runtime registry describing lifecycle, credential, permission and usage-budget
   boundaries. It preserves existing get_runtime behaviour for persisted Bot documents and does not
   enable a new executor merely by registering it.
6. Preserve protocol adapters as separate modules and record endpoint-specific differences in the
   compatibility matrix instead of claiming generic compatibility.
7. Treat documentation as a contract: correct stale claims and label every live-verification boundary.

## Consequences

- Adding a provider becomes a data change plus an adapter only when its protocol differs; it no longer
  requires editing several unrelated constants for identity/reporting.
- Existing state, keys, model specs and runtime behaviour remain valid; no migration is required.
- Some provider identity duplication remains in legacy routing constants for this slice (consolidation
  is incremental because those constants also encode transport/credential rules).
- New modules must stay small; no growth in the frozen oversized files.
- A catalogue entry is not a support claim. The UI, docs and website must render the declared status
  and the live-verification boundary.

## Alternatives considered

- One giant provider manager: rejected (god object, couples auth/catalog/media/runtime/billing).
- Several unrelated provider entries per login method: rejected (confuses identity; breaks account
  grouping and billing attribution).
- Replacing the connection store with a new credential database: rejected for this slice (migration
  risk, duplicates working security code); the existing 0600 key files and OAuth stores remain.
