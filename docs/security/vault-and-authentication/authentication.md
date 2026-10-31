# Authentication

This describes what Hutch does today (unchanged by this programme) and why the programme did not add
more.

## Deployment shapes

| Shape | Identity | How it authenticates |
|---|---|---|
| Local, single operator (default) | the local owner | loopback only; an owner token or the local auth cookie |
| Self-hosted, remote access enabled | the owner, plus paired devices | HTTPS + a database-backed WebAuthn session |
| Behind a reverse proxy | the owner, plus paired devices | exact trusted-proxy IP, `X-Forwarded-Proto: https`, hostname in `HUTCH_ALLOWED_HOSTS` |
| Deskop app | the local owner | same as local |

There is no multi-user account layer. A "user" in the SaaS sense does not exist, and this programme
did not invent one.

## What is enforced

All of this lives in `src/hutch/server/security.py` and is exercised by the existing suite.

- **Loopback by default.** A non-loopback peer cannot use a loopback `Host` header (DNS rebinding),
  and an unexpected hostname is refused.
- **Remote access is opt-in.** `HUTCH_REMOTE_ENABLED=1`, HTTPS only, and a passkey session on every
  request. A local owner token is never accepted over the network.
- **Trusted proxies are exact.** `HUTCH_TRUSTED_PROXIES` accepts only `/32` and `/128`; one
  `X-Forwarded-Host` and `X-Forwarded-Proto`; the public host must already be allowed; forwarding
  headers from untrusted peers are stripped.
- **CSRF.** Unsafe methods must be same-origin by `Origin` or `Sec-Fetch-Site`; forms carry a
  double-submit token. Passkey, pairing and session endpoints additionally require
  `X-Hutch-Request: 1`.
- **WebAuthn is verified server-side.** RP ID and origin are validated, user presence and
  verification are required, and synced passkeys are handled correctly (counters enforced only for
  single-device authenticators).
- **Sessions are bounded and revocable.** Enrollment 5 minutes, login ceremony 2 minutes,
  authenticated sessions 8 hours absolute with a 30-minute idle window.
- **Headers.** CSP with no inline script, `frame-ancestors 'none'`, `nosniff`, `no-referrer`, and
  `no-store` for remote and paired responses.

## What this programme added

Nothing to the sign-in surface, deliberately. Instead:

- The **vault is a separate credential**. Signing in does not unlock it, and unlocking it does not
  grant any other capability. Nothing in the sign-in path derives or stores a vault key.
- Vault routes are **owner-only**, so a paired phone cannot unlock a vault or reveal a secret. The
  middleware already refuses unknown remote routes; the vault routes check the principal again.
- Unlock failures are **throttled and audited**, separately from sign-in failures.

## What was considered and rejected

- **Passwords for the dashboard.** It runs on loopback with an owner token; a password would add a
  credential to steal without removing the token.
- **TOTP as a second factor.** WebAuthn already covers remote access, and a decorative second factor
  is worse than none.
- **OIDC.** No multi-user model exists for it to authenticate into.
- **Account recovery.** There are no accounts. The vault's recovery key is the only recovery story,
  and it is documented as such.

## Known weaknesses

- The owner cookie grants everything the owner can do, including revealing a secret. There is no
  reauthentication step before a reveal yet; it is listed as a follow-up, not claimed as present.
- Throttling is per process and resets on restart, so it slows online guessing rather than stopping
  it. Offline guessing is answered by the KDF cost, not by this.
