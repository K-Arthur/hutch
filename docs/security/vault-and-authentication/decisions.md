# Decisions

Architecture decisions for the vault programme, with the alternatives that were rejected. Each
entry states what would make us revisit it.

## D1. scrypt instead of Argon2id

**Decision.** Passphrase wraps use scrypt with N=2^17, r=8, p=1 through `cryptography`.

**Why.** The OWASP Password Storage Cheat Sheet names Argon2id first and scrypt as the correct
fallback with exactly these parameters. `cryptography` is already a pinned dependency and provides
scrypt; `argon2-cffi` is not installed, and adding a compiled dependency to a local-first product to
gain a modest margin is not justified by this threat model. Measured on the reference machine:
128 MiB, ~0.56 s per derivation, inside the "less than one second" guidance.

**Cost of the choice.** scrypt is slightly weaker than Argon2id against some side-channel attackers.
That is a real difference and it is stated in `security-limitations.md` rather than glossed over.

**Revisit when** `argon2-cffi` becomes a dependency for another reason, or the measured derivation
time falls below ~200 ms on typical hardware (which would mean the cost parameter is stale).

**Migration path.** The KDF identifier and parameters are stored per wrap. A new Argon2id wrap can
be written next to an old scrypt wrap, and `change_passphrase` always rewrites with the current
default.

## D2. One DEK per vault, wrapped per credential

**Decision.** A random 32-byte DEK encrypts secrets. The DEK is wrapped by a passphrase KEK and by a
recovery KEK, each with its own salt and nonce.

**Why.** A passphrase change becomes a single small atomic write instead of a re-encryption of every
secret, which removes the most dangerous failure mode in a password manager (a crash mid-rotation).
Recovery becomes possible without a second copy of the data.

**Rejected.** Deriving the data key directly from the passphrase. It makes a passphrase change a
full re-encryption, makes recovery impossible without the passphrase, and couples every secret's
ciphertext to the sign-in credential.

## D3. AES-256-GCM with identity-bound AAD

**Decision.** AES-256-GCM, 96-bit random nonce, and associated data that binds
`(secret id, version, scope, category)` for data, `(vault id, wrap version, kind)` for wraps.

**Why.** Established primitive in `cryptography`, no hand-rolled construction. Binding to identity
means a database writer cannot move a ciphertext to another secret, replay an old version under a new
number, or relabel a scope, without the tag check failing.

**Rejected.** AES-CBC + HMAC (more moving parts, easy to get wrong), and XChaCha20-Poly1305 (not
available in `cryptography` without libsodium; no benefit here).

## D4. Storage in the existing SQLite database

**Decision.** Vault tables live in `hutch.db`, created by one ordered migration.

**Why.** The repository already has a migration system, a pre-upgrade backup written with SQLite's
backup API, `BEGIN IMMEDIATE` write transactions, and a documented backup story. A second database
file would need its own locking, backup and upgrade path, and would split the atomicity guarantees.

**Rejected.** A separate encrypted file (a KeePass-style database). It would duplicate the
persistence layer and make "is this Hutch's data or the vault's data" ambiguous during restore.

**Cost.** A database copy and a vault copy are the same artefact, so the passphrase is the only
thing separating an attacker from the secrets. That is exactly the intended trust anchor.

## D5. `use` and `reveal` are different permissions

**Decision.** `Permission.USE` lets a mediator apply a value; `Permission.REVEAL` returns it to the
caller. They are separate rows in `vault_grants` and separate audit actions.

**Why.** The product claim worth making is "an agent can use a credential without seeing it". That
claim is only meaningful if the code distinguishes the two acts. Collapsing them would make the
claim untestable.

**Current limitation.** Until mediated egress exists, `use` and `reveal` both return the value to a
caller inside the process. `use` is therefore only as strong as the mediator that calls it. This is
recorded in `agent-secret-access.md` and `security-limitations.md` and is not presented as isolation.

## D6. Deny by default, with no wildcard principals

**Decision.** Access is a row in `vault_grants` keyed by `(secret, principal kind, principal id,
permission)`. There is no "all bots" principal.

**Why.** Grok's own documentation says its vault is account-wide and "you can't limit an item to one
Bot". A per-bot connector platform should do better, and the data model already carries `bot_id` on
every run.

**Rejected.** Role templates ("read-only", "integration") that expand to a set of permissions. They
hide what was granted and make revocation ambiguous.

## D7. The vault is owner-only over HTTP

**Decision.** Vault routes require the local owner principal. A paired phone cannot reach them.

**Why.** Remote sessions are a different threat model (device loss, shared network). Unlocking a
vault from a phone would put the DEK in a process reachable by a stolen session. The existing
capability map already forbids unknown remote routes, so this is enforced twice.

**Cost.** A user cannot unlock the vault from their phone. That is accepted until there is a design
for remote unlock that does not widen the blast radius.

## D8. Audit rows carry codes, not free text

**Decision.** `vault_audit.reason` is drawn from a closed vocabulary; `destination` must validate as
a bare hostname. The table is protected by `BEFORE UPDATE`/`BEFORE DELETE` triggers.

**Why.** The most likely way a value ends up in the audit table is an exception message. A closed
vocabulary makes that impossible by construction, and the triggers make tampering a failure rather
than a silent rewrite.

**Cost.** Less forensic detail per row than a free-text note. Accepted: the actor, action, secret,
scope, outcome and destination answer the questions that matter.

## D9. No new dependency

**Decision.** The vault imports only the standard library and `cryptography`.

**Why.** A security feature that expands the supply chain to protect secrets is a bad trade. The
crypto audit surface stays small and inspectable.

**Verified.** `pyproject.toml` is unchanged by this programme.
