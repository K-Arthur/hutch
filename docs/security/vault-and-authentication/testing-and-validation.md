# Testing and validation

## What was run

Commands are the repository's own quiet lane.

```
npm run test:agent -- tests/test_vault_crypto.py tests/test_vault_refs.py \
    tests/test_vault_lifecycle.py tests/test_vault_secrets.py \
    tests/test_vault_access.py tests/test_vault_integrity.py tests/test_vault_api.py \
    tests/test_vault_egress.py tests/test_vault_http_tool.py tests/test_vault_agent_turn.py
npm run test:agent -- tests/test_migration.py tests/test_netguard.py tests/test_tools.py \
    tests/test_tool_contracts.py
npm run check:agent
```

Results, latest run (2026-10-31, second pass), each suite run to completion:

| Suite | Tests | Result |
|---|---|---|
| `test_vault_crypto.py` | 33 | pass |
| `test_vault_refs.py` | 52 | pass |
| `test_vault_lifecycle.py` | 17 | pass |
| `test_vault_secrets.py` | 10 | pass |
| `test_vault_access.py` | 21 | pass |
| `test_vault_integrity.py` | 10 | pass |
| `test_vault_api.py` | 14 | pass |
| `test_vault_egress.py` | 14 | pass |
| `test_vault_http_tool.py` | 6 | pass |
| `test_vault_agent_turn.py` | 1 | pass |
| `test_vault_migration.py` | 4 | pass |
| `test_migration.py` | 41 | pass |
| `test_netguard.py` | 100 | pass |
| `test_tools.py` | 14 | pass |
| `test_tool_contracts.py` | 11 | pass |

348 tests, all passing. `npm run check:agent`: context hygiene **pass**, tool contracts **pass**
(47 registered tools), constitution **pass**, generated agent map **pass**.

## What the tests exercise

These are not fixture substitutes. Every vault test opens the real `Store`, runs the real migration
and uses real `cryptography` primitives. The tool tests dispatch through the real `call_tool`, and the
agent-turn test runs the real `Engine`.

- **Cryptography.** scrypt determinism per salt, parameter validation and refusal of coerced
  strings, DEK wrap/unwrap, wrong-key refusal, AAD binding to vault/version/kind and to
  id/version/scope/category, tamper detection, nonce uniqueness over 256 encryptions, recovery-key
  round trip, confusable-character handling, checksum rejection.
- **References.** Canonical parsing, versions, and 22 malformed forms refused (traversal, casing,
  query strings, wrong lengths, `#v0`, extras).
- **Lifecycle.** Fresh database, create, weak passphrase refused before any write, re-initialisation
  refused, lock/unlock, wrong passphrase, recovery unlock, passphrase change without re-encryption,
  production cost enforced after a cheap creation, recovery rotation, restart, throttling, missing
  wrap reported as corruption.
- **Secrets.** Versions, stale-update protection, name conflicts, soft and hard delete, restore,
  expiry validation, category size bounds, metadata contains no value.
- **Access and destinations.** Deny by default, `use` without `reveal`, separate reveal grant,
  cross-bot refusal, connector/skill refusal, immediate revocation, owner-only grant management,
  idempotent grants, canonical and idempotent binding, a binding scoped to one secret, unbinding
  taking effect immediately, owner-only bind/unbind, and a refusal for every near-miss origin
  (another host, plain http, another port, a path, a query, embedded credentials).
- **Egress.** Value applied to the named header only; connection pinned to the validated address;
  `Host` and SNI on the requested name; redirect returned not followed; response body and headers
  scrubbed of the value; `set-cookie` dropped; header injection refused before the vault is opened;
  non-ASCII credential refused; body and content type delivered; caller-supplied `Host` refused.
- **Integrity.** Plaintext absent from database files and from events/runs/messages/audit tables,
  tampered ciphertext refused, ciphertext moved between secrets refused, version replayed refused,
  audit rows immutable, free text in audit refused, no value in logs.
- **API.** Real `create_app`, real middleware: status, create-once semantics, browser-request header,
  cross-site origin refused, full secret lifecycle over HTTP, lock/unlock, grants, destination
  bindings and their refusal of a URL that is not an origin, audit, unknown fields and bad
  categories refused, no value in write responses, one shared unlock state with the run loop.

## What was not run, and why

- **Full `pytest`.** The repository runs it on CI across three Python versions; this change is
  covered by focused suites plus the migration, netguard and tool-contract suites, which is the lane
  the project prescribes.
- **Browser and visual tests.** There is no vault UI yet, so there is nothing to look at. No
  screenshots are claimed.
- **`tests/e2e/`.** Excluded by the lane and irrelevant without a UI.
- **Dependency scanning and static analysis.** No dependency was added, so the dependency surface is
  unchanged; a dedicated scan was not run in this pass.
- **External providers.** None implemented, so nothing to validate.
- **A live third-party API.** The mediator is proved against `httpx.MockTransport` and a fake
  resolver. That exercises the real request object, real header placement and real scrub logic, but
  no vendor account was called. It shows the mechanism, not a vendor's contract.
- **Independent review, fuzzing, penetration testing.** Not performed.

## Verification that matters most

1. `test_an_agent_uses_the_credential_and_never_receives_it` runs the real engine with a runtime that
   prints the entire tool result and claims an injected instruction asked for the key. It asserts the
   run succeeds, the request carried the right header, the service body reached the model, and the
   value is in no event, message or run row.
2. `test_ciphertext_is_absent_from_the_database_files` reads the actual `hutch.db` and WAL bytes.
3. `test_a_service_that_echoes_the_credential_cannot_return_it` covers the mediation step that is
   easiest to get wrong: trusting a response.
4. `test_a_redirect_is_returned_not_followed_with_the_credential` covers walking a credential to a
   host the owner never bound.
5. `test_a_legacy_installation_gains_a_working_vault_after_upgrade` proves a real pre-existing
   database upgrades without its rows changing.
6. `test_values_never_reach_the_log` and the event/transcript scans cover the leakage path that
   matters most for an agent platform.

## How to reproduce the KDF cost

```
uv run --frozen --no-sync python -c "from hutch.vault import crypto; print(crypto.benchmark())"
```

Reference machine (2026-10-31): N=131072, r=8, p=1, 128 MiB, 0.56 s per derivation.
