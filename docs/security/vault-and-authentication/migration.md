# Migration

## Current state

The vault is **not** yet the store for existing credentials. Nothing was moved, and nothing was
deleted. This document states what exists, what a migration would have to do, and why it has not been
done in this pass.

## What existing data looks like

| Credential | Location today | At rest |
|---|---|---|
| Model-provider API keys | `$STATE_DIR/keys/<connection>.key`, `0600` | plaintext |
| ChatGPT (SIWS) tokens | `$STATE_DIR/chatgpt/*.json`, `0600` | plaintext |
| OAuth refresh tokens | OS keyring (`secret-tool` / DPAPI / Keychain) | protected by the OS |
| Telegram channel tokens | OS keyring | protected by the OS |
| Owner token | derived digest only | not persisted |

## Schema migration — done

The vault tables are created by one additive migration appended to `store._MIGRATIONS`. Properties:

- **Additive.** `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`; no existing table is
  altered.
- **Idempotent.** Running it twice is a no-op.
- **Atomic.** It runs inside the existing `BEGIN EXCLUSIVE` upgrade transaction and rolls back with
  it.
- **Backed up.** The existing pre-upgrade backup (`Store._upgrade`) runs first, so an operator has the
  pre-vault database.
- **Verified on a legacy fixture.** `test_a_legacy_installation_gains_a_working_vault_after_upgrade`
  copies `tests/fixtures/state_v4.db.fixture`, opens it with the current code, asserts the schema
  version advanced, that the two existing bots are untouched, and that a vault can then be created
  and used.

## Credential migration — not done

Moving the plaintext key files into the vault is a separate, riskier operation:

1. **Detect.** Find `keys/*.key` and `chatgpt/*.json` and classify them by category.
2. **Create the vault first.** Migration cannot run without an unlocked vault, so it must be an
   explicit owner action after vault creation, not an automatic upgrade step.
3. **Store, then verify.** Write each value into the vault, read it back through the mediator, and
   compare — before removing the file.
4. **Remove only after verification.** The original file is deleted only when the round-trip
   succeeded, and the file's path is recorded in the audit reason.
5. **Never write a plaintext rollback backup.** A backup containing the values defeats the purpose.
6. **Report.** A redacted summary: how many migrated, how many failed, which connections are still on
   files.

Why it is not done in this pass: step 3 requires the mediator from `agent-secret-access.md` §3. Until
a connection can read its key *from the vault* and complete a real request, migrating would break
every configured model route. Deleting the file without that verification would be data loss;
keeping it after migration leaves the original exposure.

## Interrupted migration

If a future migration is interrupted, the rule is: the source file remains, the vault row may exist,
and re-running the migration overwrites the vault value idempotently. No operation deletes before it
has verified.

## Rollback

There is no downgrade path in Hutch for any schema, and this is not an exception. To go back, restore
the pre-upgrade backup and re-enter credentials. That is stated in `deployment-and-configuration.md`
and is a property of the existing migration system, not of the vault.
