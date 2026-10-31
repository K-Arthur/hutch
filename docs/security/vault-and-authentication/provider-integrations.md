# Provider integrations

## Status: none implemented, and none claimed

`refs.PROVIDERS` contains exactly `("hutch",)`. A reference naming any other provider is refused at
parse time, and `resolve_for_use` refuses a non-local reference. There is no 1Password, Bitwarden or
HashiCorp Vault adapter in this tree.

This is deliberate. A provider adapter that "fetches secrets and returns plaintext" would be a
security regression dressed as an integration, and an adapter that has never been run against the
real service is a claim that cannot be defended.

## The contract an adapter must satisfy

The seams exist so an adapter is additive rather than a redesign:

1. **Reference grammar.** Extend `PROVIDERS` only when the adapter ships. The reference carries
   `provider`, `alias`, `secret_id` and an optional version. It never carries a value.
2. **Resolution.** An adapter resolves a reference to a value inside the trusted boundary, and
   nothing else. It must not return metadata it cannot verify.
3. **No plaintext to the model.** The same rule applies: a value is used by a mediator, not returned
   in a tool result.
4. **Fail closed.** Provider unavailable, credential expired, permission denied and network timeout
   are distinct, actionable failures. No silent fallback to another provider, an environment
   variable or a cache that may be stale.
5. **Audit.** Every resolution writes a `use` row with the provider in the reason code and the
   destination hostname where one is known.
6. **Provider authentication is separate.** The credential Hutch uses to talk to 1Password is not
   one of the secrets stored in 1Password, and it is not the vault's own unlock credential.
7. **Versioning and rotation.** A provider's own version identifiers must map onto Hutch's version
   field, or the adapter must document that it always resolves the provider's current value.

## What each candidate would need

| Provider | Authentication | Blocking question |
|---|---|---|
| 1Password | Service account token or Connect | Is the token itself stored in the vault, and how is that bootstrap resolved? |
| Bitwarden | `bw` CLI session or Secrets Manager token | A CLI session on disk is another plaintext credential; is there a non-CLI API? |
| HashiCorp Vault | AppRole/token + TLS | Self-hosted Vault expects its own operational model (unseal, lease, renewal); is that in scope for a local-first product? |

None of these has an answer that is clearly right for Hutch today, which is why none is implemented.

## Environment and file providers

Also not implemented. Deliberately: an environment-variable provider is the exact mechanism this
programme is trying to move away from, and a file provider is how the current plaintext keys are
stored. Adding them back as vault "providers" would legitimise the pattern the vault exists to
replace.
