# Implementation plan and checkpoint status

Each checkpoint is independently verifiable. "Done" means implemented **and** covered by a test that
exercises the real path; "planned" means designed but not built. Nothing below claims more than the
code does.

---

## Checkpoint 0 — Repository and execution safety

**Status: done.**

- Branch `main`; concurrent uncommitted work from other sessions identified and left untouched.
- The prior recovery checkpoint (`dc229b2b`) had zero messages and nothing to resume.
- `docs/security/vault-and-authentication/` created.

**Evidence.** `git status` before and after; only intended files staged.

## Checkpoint 1 — Research and discovery

**Status: done.** See `research.md` and `current-state.md`.

- Standards read at source: OWASP Password Storage, Secrets Management, Cryptographic Storage,
  Authentication, Session Management, MFA cheat sheets; RFC 9106, RFC 6238, RFC 9700.
- Competitor models read: Grok Bot vault, Rakazo self-hosted storage, Codync memory/artifacts,
  OpenClaw gateway secrets (all eleven cited pages).
- Failure analysis from public issue trackers with dates, reaction counts and links.

**Exit criteria met.** Architecture is justified by repository evidence and external evidence; each
requirement in `research.md` §8 traces to a source.

## Checkpoint 2 — Architecture and design

**Status: done.** See `architecture.md`, `threat-model.md`, `decisions.md`.

- Identity / authentication / authorization / secret management separated.
- SecretRef contract fixed with a strict grammar.
- Key hierarchy and AAD binding defined.
- Storage and provider seams defined.
- Agent access policy defined (deny by default, `use` ≠ `reveal`).
- Migration strategy defined (one ordered migration, additive).

## Checkpoint 3 — Core vault foundation

**Status: done.**

| Requirement | Implementation | Test |
|---|---|---|
| Established primitives only | `vault/crypto.py` (scrypt, AES-256-GCM, HKDF) | `test_vault_crypto.py` |
| Cost floor enforced | `DEFAULT_SCRYPT`, `test_default_cost_meets_documented_floor` | same |
| Envelope encryption | `wrap_dek` / `unwrap_dek` with AAD | same |
| Recovery key | `generate_recovery_key` / `parse_recovery_key` (Crockford + checksum) | same |
| Secret encryption bound to identity | `encrypt_secret` / `decrypt_secret` with AAD | same |
| Vault lifecycle | `vault/lifecycle.py` | `test_vault_lifecycle.py` |
| Secret CRUD with versions | `vault/secrets.py` | `test_vault_secrets.py` |
| Grants and resolution | `vault/access.py` | `test_vault_access.py` |
| Append-only audit | `vault/audit.py`, `vault/schema.py` triggers | `test_vault_integrity.py` |
| Safe migration | `vault/schema.migrate`, registered in `store._MIGRATIONS` | `test_vault_lifecycle.py::test_a_legacy_installation_gains_a_working_vault_after_upgrade`, `tests/test_migration.py` |

**Exit criteria met.** Real SQLite, real cryptography, real upgrade from a v4 fixture database.

## Checkpoint 4 — Agent-safe access

**Status: done for HTTP request egress; not done for connectors or other credential shapes.**

Done:

- Scoped grants per `(secret, principal, permission)` with deny-by-default.
- `use` versus `reveal` as separate permissions and separate audit actions.
- Scope enforcement that a grant cannot override.
- Destination bindings: a use additionally requires an owner-created canonical origin, checked
  inside `resolve_for_use`.
- A `UsableSecret` whose `repr` is redacted, so an f-string or a debug log does not leak a value.
- `vault.egress.mediate_http`: one header, one request, pinned address, no redirects, response
  scrubbed of the value.
- `vault_http_request`, the tool that lets a bot spend a credential it cannot read, wired through
  policy, the approval gate, the action receipt and the audit.
- HTTP surface that never returns a value outside the explicit reveal route.

Not done, and not claimed:

- Connectors (Google, Outlook, Notion) still read their own credential stores; none reads the vault.
- Credential shapes beyond one request header: signed bodies, credentials in query strings,
  multi-step OAuth exchanges.
- Any isolation from a bot that has `shell` and `reveal`. The mediator is not a proxy and no process
  is forced through it; `security-limitations.md` §3 says so plainly.

**Evidence.** `tests/test_vault_egress.py`, `tests/test_vault_http_tool.py` and
`tests/test_vault_agent_turn.py`; the last runs the real engine and scans every table the value could
have reached.

## Checkpoint 5 — Secure sign-in

**Status: not started; existing work inspected.**

The current sign-in surface was audited (see `current-state.md` §2 and `authentication.md`). It is
already stronger than most local products: loopback-only by default, WebAuthn with server
verification, database-backed sessions with idle and absolute limits, revocation, trusted-proxy
handling with exact-IP allow-listing, CSRF and CSP.

Deliberately not built in this checkpoint: passwords, TOTP, OIDC, account recovery. Each needs a
deployment story Hutch does not have yet (multi-user accounts), and adding them without one would be
feature count rather than security.

## Checkpoint 6 — Integrations and migration

**Status: partially done.**

Done: the migration of existing installations (schema upgrade is additive and tested), and the
provider contract in `refs.py` (`PROVIDERS`).

Not done: no external provider adapter exists. `PROVIDERS` contains only `hutch`, and
`resolve_for_use` refuses anything that is not local. 1Password, Bitwarden and HashiCorp Vault are
named as seams, not as supported integrations.

Not done: migrating existing plaintext model keys and ChatGPT tokens into the vault. They remain
where they are, and `current-state.md` §8 says so.

## Checkpoint 7 — Frontend and onboarding

**Status: not started.**

The HTTP API exists and is tested. There is no vault page in the dashboard yet. Until there is, the
vault is reachable only through the API, and no user-facing claim about it should be made.

## Checkpoint 8 — Marketing and documentation

**Status: not started for the website.** The website was not modified, and no claim was added to it.
Documentation is this directory.

## Checkpoints 9 and 10 — Hardening, review, merge

**Status: partially done.**

Done in this pass:

- Focused suites for crypto, references, lifecycle, secrets, access, integrity and API.
- `npm run check:agent` — context hygiene, tool contracts and constitution checks pass.
- A review pass found and fixed: no-vault misreported as locked, `expires_at` silently dropped,
  string coercion in stored KDF parameters, corruption reports naming the wrong principal, a reveal
  route passing a bare id, and reference errors surfacing as HTTP 500.

Not done: a full-suite run, browser/visual validation (no UI), dependency scanning, and an
independent review by another reviewer. The work is committed to `main` in small units.

Second review pass (same day) found and fixed: audit destinations that could not distinguish
`https` from a non-default port, an audit vocabulary with no code for a missing binding, and a
per-request vault book that would have made an unlock in Settings invisible to the run loop.

---

## What a reader should conclude

The vault core is real: the cryptography is exercised, the database is real, the migration runs on a
legacy fixture, the grants and audit behave, and the API is reachable through the app's own security
middleware. The agent-facing half now has a mechanism: `vault_http_request` presents a bound
credential at the network boundary and returns only the response, and a real engine turn proves the
value reaches no event, message or table. That mechanism covers one header on one request with no
redirect following; connectors, other credential shapes, the UI, external providers and the migration
of existing plaintext credentials are not started.
