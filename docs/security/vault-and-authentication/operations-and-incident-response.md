# Operations and incident response

## Day-to-day

| Task | How |
|---|---|
| Create the vault | `POST /api/v1/vault/create` with a passphrase; record the recovery key shown once |
| Unlock | `POST /api/v1/vault/unlock` (or `/unlock-recovery` with the key) |
| Lock | `POST /api/v1/vault/lock`, or stop Hutch |
| Add or rotate a secret | `POST` then `PUT /api/v1/vault/secrets/{id}` — a rotation is a new version |
| Grant a bot | `POST /api/v1/vault/secrets/{id}/grants` with `use` |
| Revoke | `DELETE /api/v1/vault/secrets/{id}/grants` |
| See who used what | `GET /api/v1/vault/audit` |
| Change the passphrase | `POST /api/v1/vault/passphrase` |
| Replace the recovery key | `POST /api/v1/vault/recovery-key`; the old key stops working |

Lock state is per process. If two Hutch processes run against one database, each must be unlocked
separately.

## Diagnostics that are safe to share

- `GET /api/v1/vault` — initialised, unlocked, key version, secret count, recovery configured.
- `GET /api/v1/vault/audit` — actor, action, secret id, scope, outcome, reason, destination.
- `crypto.benchmark()` output — KDF parameters and timing.

Never share: a passphrase, a recovery key, a decrypted value, or a database file that has been
modified to add one.

## Signs that something is wrong

| Symptom | Likely cause | Action |
|---|---|---|
| `423 Locked` on every value operation | vault locked (expected after restart) | unlock |
| `403 That credential does not open this vault` | wrong passphrase or recovery key | retry carefully; after repeated failures expect `429` |
| `500 Stored vault data failed validation` | missing key wrap, tampered ciphertext, or a restored database without its key material | **do not retry**; restore from backup and investigate |
| `409 Create a vault first` | no vault in this database | create one, or check you are pointed at the right state directory |
| Audit shows repeated `denied`/`no_grant` for one bot | an agent is probing for a credential it was not given | treat as a prompt-injection signal; review that bot's transcripts |

## Incident response

### Suspected credential disclosure through an assistant

1. **Contain.** Lock the vault and pause the bot. Locking does not revoke a value the bot already
   read, but it stops further reads.
2. **Scope.** `GET /api/v1/vault/audit?secret_id=...` shows every `use` and `reveal` with actor and
   destination. A `reveal` by a bot is worth investigating; a `reveal` by the owner is a person.
3. **Rotate.** `PUT /api/v1/vault/secrets/{id}` with a new value — a new version, so the old one
   remains auditable. Rotate at the provider too: Hutch cannot revoke a key at a third party.
4. **Revoke grants.** `DELETE .../grants` for the affected principal. Takes effect immediately.
5. **Record.** The audit table already holds the evidence and cannot be edited. Export it before any
   restore operation replaces the database.

### Suspected database or backup theft

1. Theft of `hutch.db` alone does **not** disclose values. It does disclose secret names, scopes and
   the audit trail — assume that.
2. Change the vault passphrase, which writes a new wrap. This does not help if the attacker also has
   the old passphrase or the recovery key.
3. Rotate the recovery key if it was stored near the backup.
4. If the passphrase may be known to the attacker, changing it is not enough: rotate the secrets
   themselves. A new passphrase protects future reads; it cannot un-disclose a value already read.

### Lost passphrase

Use the recovery key. If that is also lost, the data is unrecoverable; Hutch will not pretend
otherwise. Delete the vault rows only if you accept the loss.

### Lost recovery key but passphrase known

`POST /api/v1/vault/recovery-key` issues a new one. Until then, the only unlock path is the
passphrase.

### Corrupt vault

Do not delete rows to "fix" it. `VaultCorrupt` means an authentication check failed: a key wrap is
missing, ciphertext was altered, or a restore lost the key material. Restore the database and its key
wraps together from a consistent backup.

## Retention

Audit rows are never deleted by Hutch. A hard delete of a secret removes its ciphertext and grants
but leaves the audit rows that reference its id, so the history survives the secret.
