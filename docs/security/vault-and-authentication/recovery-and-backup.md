# Recovery and backup

## What recovery exists

Two independent ways to open a vault:

1. **The passphrase.** Stretched with scrypt and used to unwrap the DEK.
2. **The recovery key.** 20 random bytes, displayed once at creation as eight groups of four
   Crockford base32 characters plus a four-character checksum. It unwraps the same DEK.

Neither is derived from the other, so losing one does not lose the vault. Losing **both** means the
secrets are unrecoverable. Hutch cannot recover them, no administrator can, and this document will
not pretend otherwise.

The recovery key is:

- generated from the OS CSPRNG,
- never written to disk by Hutch (a test scans the state directory for it),
- safe to write down: 160 bits is far beyond guessing, and the checksum catches most transcription
  mistakes,
- replaceable: `rotate_recovery_key` retires the old wrap and returns a new key. The old key stops
  working immediately.

## Changing the passphrase

`change_passphrase` derives a new KEK at the **current production cost** (never inheriting a weaker
stored cost), wraps the existing DEK, and retires the old wrap in one transaction. Secret ciphertext
is not rewritten, so a crash during the change cannot corrupt secrets: either the new wrap commits or
the old one remains.

## Backup

The vault lives in `hutch.db`. A backup is therefore the same artefact as a normal Hutch backup, and
it is **encrypted** for the parts that matter:

- A backup contains ciphertext, salts, nonces, secret names, scopes, categories, timestamps and the
  audit trail.
- A backup does **not** contain the passphrase, the recovery key or the DEK.

So a stolen backup is not a vault disclosure, but it is a metadata disclosure: the names of the
secrets and who used them. Say that to anyone who asks what a backup reveals.

### Procedure

1. Stop Hutch, or use SQLite's backup API (Hutch already writes a pre-upgrade backup this way).
2. Copy `hutch.db` (and `hutch.db-wal` if the process is running — better to stop it).
3. Store the recovery key **separately** from the backup. A backup and its recovery key in the same
   folder is one artefact, not two.

### Restore

1. Restore the file, then start Hutch and unlock with the passphrase or the recovery key.
2. If the restored database predates the vault migration, Hutch upgrades it on open; the vault tables
   are created empty and can be initialised normally.
3. If the restored database is newer than the running Hutch, Hutch refuses to open it rather than
   downgrading. That behaviour is existing and is not changed here.

## Verification performed

- `test_vault_survives_a_restart_and_comes_back_locked` — close the store, reopen, assert locked and
  that the secret decrypts after unlock.
- `test_a_legacy_installation_gains_a_working_vault_after_upgrade` — a v4 fixture database upgrades
  and accepts a vault without its rows changing.
- `test_create_unlocks_and_returns_a_recovery_key_once` — the recovery key is absent from every file
  under the state directory.
- `test_rotating_the_recovery_key_invalidates_the_old_one`.
- `test_passphrase_change_rewraps_and_keeps_existing_secrets` — ciphertext is byte-identical after a
  passphrase change.

## Not verified

- A restore from a backup taken **while Hutch was writing** (the WAL case) is not exercised beyond
  the existing migration tests.
- No hardware-backed recovery (a passkey wrapping the DEK) exists.
