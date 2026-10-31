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

## Destinations

A grant says *who* may use a secret. A destination binding says *where* the value may go. Both are
required, and only the owner can create either.

A binding is a canonical origin: `https://api.example.com`, `http://localhost:8080`. A URL with a
path, query, fragment or embedded credentials is refused rather than trimmed, so two different
destinations cannot end up sharing one row. An origin is matched exactly: another host, plain `http`
instead of `https`, or another port is a different destination and gets `denied/no_destination`.

```
secret://hutch/local/sec_…   →   bound: https://api.example.com
                             →   granted: use, bot_0123456789ab
```

## Using a secret without reading it

`vault_http_request` is the mechanism for that pairing. A bot passes the reference, a URL and a
method; Hutch checks policy, checks the approval gate, checks the grant and the binding, injects the
value into one header of one request, and returns the service's response.

- **A redirect is not followed.** The 3xx is returned and named; the next request needs its own
  authorization and its own binding.
- **The response is scrubbed.** If the service echoes the credential in a body or a header, the value
  is removed and `set-cookie`/`authorization` response headers are dropped.
- **The value is not in the result.** Not in the tool output, not in the event, not in the transcript,
  not in the action receipt. `test_vault_agent_turn.py` runs a real engine turn and asserts it.
- **The connection is pinned.** The address that was checked is the address connected to; `Host` and
  SNI keep the requested name.

A bot without `use` gets `denied/no_grant`. A bot with `use` but no binding gets
`denied/no_destination`. Both are durable audit rows.

**What this is not.** It is not a sandbox. A bot with `shell` makes its own requests, and a bot with
`reveal` can read the value. The tool narrows the path it provides; it does not close a path the
agent already has. See `security-limitations.md` §3.

## Locking

`lock` zeroes the DEK buffer and drops it. While locked: metadata is readable, values are not, and
every value operation raises. Restarting Hutch comes back locked.

The unlock state lives in the Hutch process and is shared by the dashboard and the run loop, so
unlocking in Settings makes a mediated use possible and locking closes it again. Two Hutch processes
unlock independently.

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

Every lifecycle, secret, grant, binding, use and reveal action writes a row: when, which principal,
which action, which secret and scope, the outcome, a reason code and, for a use, the canonical
destination origin. Rows cannot be updated or deleted. Values are never written.

## What the vault does not do yet

It does not migrate the plaintext credentials Hutch already stores (model keys, ChatGPT tokens), and
no bundled connector reads from the vault. Its only egress is `vault_http_request`, which speaks one
header, one request and no redirects. See `migration.md` and `security-limitations.md`.
