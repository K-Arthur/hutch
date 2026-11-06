# ADR-0028: A route resolves to one explicit provider, account, runtime and model

Status: accepted, 2026-11-06.

## Context

A saved model spec (`prefix/model`) already names the model and, when the prefix is a connection
name, the account. The rest of the route was implicit:

- A provider prefix such as `openai/gpt-4o` does not say which configured OpenAI account pays. If
  Hutch picked one, it would decide the payer without the owner seeing it; if an ambient
  `OPENAI_API_KEY` was also present, the process environment could take over silently.
- Readiness could say `needs_authentication` or `needs_configuration`, but the page could not show
  the resolved provider, account source, billing relationship, protocol, endpoint and runtime as one
  tuple before the first send.
- A fallback or escalation from a subscription-backed primary to a per-token model changed who paid
  without an explicit decision. The runtime recorded the switch, but did not refuse the crossing.
- The Providers page stated live evidence in a hardcoded sentence that had already drifted: it
  omitted the 2026-10-31 Xiaomi evidence and called documented, blocked and deferred entries
  `implemented-unverified`.

## Decision

1. **One resolver, one tuple.** `providers/routing.py` returns
   `(spec, provider, account, account_source, billing, model, runtime, runtime_status, protocol,
   endpoint, status)` from local facts only. Status stays the readiness vocabulary. The resolver
   never refreshes a token, contacts a provider, or claims a capability.
2. **No account guessing.** A provider prefix with two or more matching named accounts resolves to
   `needs_configuration`, `account=""`, and the candidate names. An ambient key present in the
   environment does not break the tie. One named account is still reached only by naming it
   (`account/model`).
3. **Ambient keys are labeled and scoped.** An ambient key that may be used resolves the account as
   `ambient environment (VARIABLE)`. A key aimed at a non-official endpoint is withheld and the
   route reports `needs_authentication`. No credential value is returned.
4. **Billing crossings require configuration.** A fallback or escalation from a subscription primary
   to `per_token` or `credits` is refused before the call. Making the metered route primary is the
   explicit decision. The existing switch event keeps recording `from_model`, `to_model`, `reason`
   and `hosted`.
5. **Saved routes become explicit, not different.** Schema 91 writes the provider prefix the runtime
   already applied to a bare model name into `model`, `fallbacks`, `escalation.to` and
   `task_routes`. It is idempotent and leaves explicit specs untouched.
6. **Status statements are generated.** The Providers banner is built from the recorded live
   evidence grouped by route and date plus the catalogue's integration-status counts.

## Consequences

- The API surface is `GET /api/v1/provider-resolution?spec=&runtime=`. The dashboard picker that
  shows this tuple before the first send is Phase 7 work; until then the Models page and readiness
  API are the truthful surfaces.
- The resolver is read-only. It does not persist a per-run snapshot; a later run record can reuse the
  same tuple without a second resolver.
- Account identity remains the spec prefix. Adding a separate account field to a Bot would change how
  every saved route is interpreted, so it is deferred.
- Billing-crossing refusal covers subscription-to-metered. A local/free primary falling back to a
  hosted route still uses the existing first-hosted approval path.
- The migration touches saved documents but not the meaning of a route; rollback is safe because the
  prefix was already interpreted that way by `parse_spec`.

## Alternatives considered

- **Pick the only matching account automatically.** Rejected: a saved provider spec would start
  billing an account it never named, and an ambient key would make the same spec resolve differently
  on another machine.
- **Rewrite ambiguous provider specs to account specs during migration.** Rejected: that is exactly
  the billing change the migration must not make.
- **Add a new persisted route table.** Rejected for this slice: the tuple is derivable from local
  configuration, and a second store would drift from the connection book.
- **Leave the banner as prose and update it by hand.** Rejected: it had already drifted, and a
  hand-maintained support claim is the failure this catalogue exists to prevent.
