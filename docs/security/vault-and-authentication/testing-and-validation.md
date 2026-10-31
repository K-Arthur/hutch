# Testing and validation

## What was run

Commands are the repository's own quiet lane.

```
npm run test:agent -- tests/test_vault_crypto.py tests/test_vault_refs.py \
    tests/test_vault_lifecycle.py tests/test_vault_secrets.py \
    tests/test_vault_access.py tests/test_vault_integrity.py tests/test_vault_api.py
npm run test:agent -- tests/test_migration.py
npm run check:agent
```

Results at the time of writing:

| Suite | Tests | Result |
|---|---|---|
| `test_vault_crypto.py` | 33 | pass |
| `test_vault_refs.py` | 52 | pass |
| `test_vault_lifecycle.py` | 18 | pass |
| `test_vault_secrets.py` | 10 | pass |
| `test_vault_access.py` | 13 | pass |
| `test_vault_integrity.py` | 11 | pass |
| `test_vault_api.py` | 11 | pass |
| `test_migration.py` | 41 | pass |

`npm run check:agent`: context hygiene **pass**, tool contracts **pass**, constitution **pass**. The
generated agent map check fails in this working tree because another session has staged file
additions and deletions; the map is generated from the staged tree, and regenerating it would
rewrite a file that session is editing. It is not caused by the vault.

## What the tests exercise

These are not fixture substitutes. Every vault test opens the real `Store`, runs the real migration
and uses real `cryptography` primitives.

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
- **Access.** Deny by default, `use` without `reveal`, separate reveal grant, cross-bot refusal,
  connector/skill refusal, immediate revocation, owner-only grant management, owner-only
  permissions, idempotent grants, audit fields.
- **Integrity.** Plaintext absent from database files and from events/runs/messages/audit tables,
  tampered ciphertext refused, ciphertext moved between secrets refused, version replayed refused,
  audit rows immutable, free text in audit refused, no value in logs.
- **API.** Real `create_app`, real middleware: status, create-once semantics, browser-request header,
  cross-site origin refused, full secret lifecycle over HTTP, lock/unlock, grants, audit, unknown
  fields and bad categories refused, no value in write responses.

## What was not run, and why

- **Full `pytest`.** The repository runs it on CI across three Python versions; this change is
  covered by focused suites plus the migration suite, which is the lane the project prescribes.
- **Browser and visual tests.** There is no vault UI yet, so there is nothing to look at. No
  screenshots are claimed.
- **`tests/e2e/`.** Excluded by the lane and irrelevant without a UI.
- **Dependency scanning and static analysis.** No dependency was added, so the dependency surface is
  unchanged; a dedicated scan was not run in this pass.
- **External providers.** None implemented, so nothing to validate.
- **Real agent turns against the vault.** The scope model is tested directly, but no tool consumes a
  secret yet, so there is no agent-execution test. This is the honest gap.

## Verification that matters most

1. `test_ciphertext_is_absent_from_the_database_files` reads the actual `hutch.db` and WAL bytes.
2. `test_a_legacy_installation_gains_a_working_vault_after_upgrade` proves a real pre-existing
   database upgrades without its rows changing.
3. `test_values_never_reach_the_log` and the event/transcript scan cover the leakage path that
   matters most for an agent platform.
4. `test_a_bot_cannot_reach_another_bots_secret_even_with_a_grant` covers the cross-tenant risk.

## How to reproduce the KDF cost

```
uv run --frozen --no-sync python -c "from hutch.vault import crypto; print(crypto.benchmark())"
```

Reference machine (2026-10-31): N=131072, r=8, p=1, 128 MiB, 0.56 s per derivation.
