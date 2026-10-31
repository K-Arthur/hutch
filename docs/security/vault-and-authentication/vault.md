# The vault

A single encrypted store for credentials the owner supplies, with per-bot grants and an append-only
audit. It is owner-only, local-only, and has no fallback to files or environment variables.

## What it protects

| Situation | Protected? |
|---|---|
| Someone copies `hutch.db` or a backup | Yes — ciphertext only; names and categories remain visible |
| Someone steals the disk while Hutch is stopped | Yes |
| A bot or agent reads the state directory | Only while the vault is locked; the DEK is in Hutch's memory when unlocked |
| A process running as the same OS user while unlocked | No — stated plainly, not mitigated |
| Root, kernel, or a compromised `cryptography` | No |

## Setup

The vault starts uninitialised. Creating it returns a **recovery key**, shown exactly once.

- Choose a passphrase of at least 12 characters. Common choices are refused with a reason.
- Write the recovery key down and store it somewhere separate from the database. It opens the vault
  if the passphrase is lost. If both are lost, the data cannot be recovered by anyone, including the
  author of this software.
- The passphrase and the recovery key are independent: either one unlocks the vault.

Deriving the key takes about half a second and 128 MiB of memory on the reference machine. That is
deliberate; it is what makes offline guessing expensive.

## Working with secrets

Each secret has a **scope**, a **category**, a **name**, an optional description and an optional
expiry.

- **Scope** is `workspace` or `bot:<id>`. A bot-scoped secret is unreachable by any other bot, even
  with a grant.
- **Category** determines the size limit and the expected lifecycle: an API key rotates, an OAuth
  access token is short-lived, an SSH key is private key material. Categories are not cosmetic.
- **Versions.** Updating a secret writes version *n+1*; older versions remain readable to the owner
  by asking for that version explicitly, which is what makes a rollback possible after a bad
  rotation.

The list view shows names, scopes, categories, timestamps and expiry warnings. It never shows a
value. A value is returned only by an explicit reveal, which is recorded as a reveal.

## Locking

`lock` zeroes the DEK buffer and drops it. While locked: metadata is readable, values are not, and
every value operation raises. Restarting Hutch comes back locked.

## Grants

A grant says: *this principal may do this to this secret*. There is no wildcard.

| Principal | Typical use |
|---|---|
| `bot:<id>` | Let one assistant use one credential |
| `workspace` | A credential shared by the workspace's work |
| `connector:<slug>` | Reserved; no connector reads the vault yet |
| `skill:<name>` | Reserved |

Permissions are `metadata`, `use` and `reveal`. `rotate` and `delete` stay with the owner. A grant
can be revoked at any time and takes effect on the next operation — there is no cached grant.

## Audit

Every lifecycle, secret, grant, use and reveal action writes a row: when, which principal, which
action, which secret and scope, the outcome, a reason code and, for a use, the destination hostname.
Rows cannot be updated or deleted. Values are never written.

## What the vault does not do yet

It does not yet hand credentials to tools, connectors or outbound requests. Grants, permissions and
audit for that path exist; the path itself does not. See `agent-secret-access.md`.
