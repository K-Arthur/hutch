# ADR-0029: Credential state is explicit, not inferred from a key file

Status: accepted, 2026-11-06.

## Context

Provider accounts mixed two different questions. An API-key connection has a key file or environment
variable; a Sign in with ChatGPT connection has a protected OAuth record whose access token expires
and whose refresh token may be rotated or revoked. The account layer asked only "is a key present?":

- `has_key` returned true for a ChatGPT account with plan scope even when its access token had
  expired and it had no refresh token. Model discovery then attempted a refresh that could not work.
- `account_profile` collapsed every unusable sign-in state into `needs_sign_in`, so an expired or
  revoked credential looked the same as one that was never connected.
- The Connections page rendered a green chip for a sign-in connection whose key source was
  "missing", and a partial account record raised `KeyError` during model discovery, returning 500.

At the same time the auth store already had the hard parts: an exclusive file lock around refresh,
write-only-on-success, a verified ID token, confirmed/unconfirmed revocation, and a 60-second expiry
skew. The missing layer was an honest projection of that state.

## Decision

1. **One projection owns the state.** `chatgpt_status.account_row` returns `active`, `expired`,
   `revoked` or `missing`, plus `can_refresh` and the expiry. It never returns a token. A refresh
   token makes the credential active even when the access token is past expiry; an access token
   inside the 60-second skew with no refresh token is expired.
2. **The account layer carries it.** `AccountProfile` gains `credential_state` and
   `credential_expires_at`. Readiness maps `expired` to `authentication_expired` and `revoked` to
   `needs_authentication`; both keep the account record so it can be reauthorized.
3. **A usable credential means active.** `ConnectionBook.has_key` for a ChatGPT connection requires
   an active state. Expired and revoked accounts do not trigger model discovery or count as a key.
4. **Failures preserve the credential.** A failed refresh writes nothing; a failed reauthorization
   keeps the prior record. A single-flight file lock is held across the refresh request so two
   processes cannot spend one rotating token.
5. **The sign-in boundary is stated.** OpenAI's open-source SIWC flow uses a local PKCE loopback
   callback. A remote dashboard shows that it cannot complete there and points to an API key or the
   official CLI. No undocumented device-code client is added. OpenCode's own OAuth/device flow stays
   with the official OpenCode server and CLI.
6. **Revocation is reported as confirmed or unconfirmed.** Clearing local tokens and asking the
   provider to revoke are separate outcomes.

## Consequences

- Pages and readiness can say "expired" or "revoked" instead of a generic "needs sign-in", and an
  expired account is no longer presented as connected.
- A malformed or partial account record becomes a model-list error, not a server error.
- The auth store's storage format does not change. `accounts()` loses its inline row construction to
  `chatgpt_status`, so the frozen auth module shrinks rather than grows.
- The 60-second skew is an expiry-window allowance, not a claim that a provider enforces the same
  clock. A token inside the window may still be refused by the provider; that is an auth failure,
  not a deletion.
- Real-process resolution is tested on POSIX. Windows locking uses the repository's existing lock
  abstraction and is not exercised here.
- No live OpenAI OAuth account was used; eligibility remains unverified.

## Alternatives considered

- **Treat any refresh token as "connected".** Rejected: it hides expired and revoked accounts and
  invites a refresh that cannot succeed.
- **Add a device-code flow for SIWC.** Rejected: no official client is documented for it, and
  inventing one would violate the provider-terms rule this initiative follows.
- **Delete the account record when refresh fails.** Rejected: destructive and unrecoverable; the
  prior research records this exact failure in another client.
- **Keep the status in the page template.** Rejected: readiness, the API and two pages need the same
  answer; a template-only rule would drift.
