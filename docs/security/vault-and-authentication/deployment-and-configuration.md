# Deployment and configuration

## Configuration

The vault needs no environment variable and no configuration file. It is created and unlocked at
runtime, and its state is rows in `hutch.db`.

| Setting | Where | Effect |
|---|---|---|
| Vault passphrase | typed by the owner, never stored | unlocks the DEK |
| Recovery key | shown once, stored by the owner | unlocks the DEK |
| scrypt cost | fixed in code (`DEFAULT_SCRYPT`) | 128 MiB, ~0.56 s on the reference machine |
| KDF parameters | stored per wrap in `vault_key_wraps.params` | read back on unlock; promoted on passphrase change |

There is no "disable encryption" switch, no fallback to a file and no environment override. A missing
or unreadable vault fails closed.

## Deployment shapes

### Local desktop or CLI (default)

- The dashboard binds to loopback. Vault routes are reachable from the local browser only.
- The DEK exists only in the Hutch process while unlocked; stopping Hutch locks the vault.
- Backup is the normal Hutch backup (`hutch.db`).

### Self-hosted with remote access

- Remote access requires `HUTCH_REMOTE_ENABLED=1`, HTTPS, and a WebAuthn session.
- **The vault is still owner-only.** A paired phone cannot list, unlock or reveal. Practically, the
  vault must be unlocked at the machine, or through a local browser session.
- An operator who needs vault access while away should use a trusted remote-access channel to the
  local machine, not a widened vault route.

### Behind a reverse proxy

- `HUTCH_TRUSTED_PROXIES` must list the proxy's exact IP (`/32`, `/128`). Networks are rejected.
- `X-Forwarded-Proto` must be `https`, and the public hostname must be in `HUTCH_ALLOWED_HOSTS`.
- The proxy must not add a second `X-Forwarded-Host` value.
- None of this widens vault access; it only affects whether the dashboard is reachable.

### Headless Linux without a keyring

Integrations that use the OS keyring (`google_calendar`, `outlook_calendar`, `notion`, `channels`)
report the keyring as unavailable and refuse to connect rather than falling back to a file. The vault
does not depend on the keyring at all, which means a headless install finally has a place to keep a
credential.

## Operational limits

- **Memory.** An unlock costs 128 MiB for the duration of one derivation. On a small VPS with other
  work this is noticeable; it is the price of the KDF and is not tunable downward at runtime.
- **Concurrency.** One `VaultBook` per process holds the DEK. Two Hutch processes each unlock
  independently, and locking one does not lock the other.
- **Multiple processes over one database.** The vault tables use the existing `BEGIN IMMEDIATE`
  transactions, so writes serialise correctly. Unlock state does not.
- **Filesystem.** The vault writes no files, so file permissions, symlinks and path traversal do not
  apply to it. They still apply to the legacy plaintext key files described in `current-state.md`.

## Upgrading

The vault is one additive migration in the existing ordered list. An older Hutch refuses to open a
database that contains it, exactly as it already refuses any newer schema; it will not silently drop
vault tables. Downgrading therefore requires restoring a pre-upgrade backup, which contains no vault
data.
