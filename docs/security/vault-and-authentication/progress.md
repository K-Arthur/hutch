# Progress

A running ledger of the vault programme. Newest entries at the top of each checkpoint. Every entry
names what was verified, not only what was written.

---

## Pass 1 — 2026-10-31

### Commits

| Commit | What it contains |
|---|---|
| `663b1081` | Research, current state, architecture and threat model documents |
| `afe979b5` | Encrypted vault core: crypto, references, schema, lifecycle, secrets, grants, audit, tests |
| `ced92681` | Owner-only vault HTTP routes, with tests through the real app and middleware |

### Checkpoint 0 — repository and execution safety

- Branch `main`. Concurrent work from other sessions (connector/skills docs, MCP service, skills API,
  `selfcheck_plan`, provider-platform research) identified and left untouched.
- Prior recovery checkpoint `dc229b2b` had zero messages; nothing to resume.
- `docs/security/vault-and-authentication/` created.

### Checkpoint 1 — research

- Standards read at source: OWASP Password Storage / Secrets Management / Cryptographic Storage /
  Authentication / Session Management / MFA; RFC 9106, 6238, 9700.
- Competitors read: Grok Bot vault (all of it), Rakazo self-hosted storage, Codync memory/artifacts,
  OpenClaw's eleven secrets pages.
- Failure analysis from public issue trackers, with dates, reaction counts and links, across
  Bitwarden, Infisical, HashiCorp Vault and KeePassXC.
- Source-to-requirement mapping recorded in `research.md` §8.

### Checkpoint 2 — architecture

- Four concerns separated; key hierarchy fixed; SecretRef grammar fixed; AAD binding defined;
  deny-by-default grant model defined; `use` vs `reveal` defined.
- 15 threats modelled with mitigations, residual risk and a verification strategy each.

### Checkpoint 3 — core vault (done)

Implemented: `crypto.py`, `refs.py`, `model.py`, `core.py`, `lifecycle.py`, `secrets.py`,
`access.py`, `audit.py`, `schema.py`, `vault.py`.

Verified:

- 33 crypto tests, 52 reference tests, 18 lifecycle tests, 10 secret tests, 13 access tests,
  11 integrity tests, 11 API tests — all passing.
- Real `Store`, real SQLite, real `cryptography`; no mocked primitive.
- Plaintext absent from `hutch.db` and its WAL (byte scan).
- Ciphertext substitution, version replay and cross-secret moves all fail authentication.
- Audit table rejects updates and deletes.
- A v4 fixture database upgrades and accepts a working vault without its rows changing.

Defects found in review and fixed before commit:

1. A database with no vault raised `VaultLocked` instead of `VaultNotInitialized`.
2. `expires_at` was accepted and silently dropped on insert.
3. Stored scrypt parameters accepted strings via `int()` coercion, hiding a tampered record.
4. Corruption audits attributed the failure to the owner regardless of who was asking.
5. A wrong passphrase and a malformed key record both surfaced as "wrong passphrase"; a missing KDF
   parameter raised `VaultCryptoError` instead of `VaultCorrupt`.
6. The reveal route passed a bare secret id where a reference was required (HTTP 500).
7. Reference and principal validation errors surfaced as HTTP 500 instead of 422.

### Checkpoint 4 — agent-safe access (partial)

Done: grants, scope enforcement, `use`/`reveal` separation, redacted `UsableSecret`, audit with
destination, HTTP surface that never returns values outside reveal.

Not done: no tool accepts a `SecretRef`; no mediated egress; no connector reads the vault. The claim
"an agent uses a credential without seeing it" is therefore **not** made.

### Checkpoint 5 — secure sign-in

Inspected and documented, not changed. The existing surface is already loopback-first, WebAuthn-verified,
session-bounded and proxy-hardened. Vault routes are owner-only, so a paired phone cannot reach them.

### Checkpoint 6 — integrations and migration

Schema migration done and tested on a legacy fixture. Credential migration designed in `migration.md`
but not executed, because it depends on the mediator from checkpoint 4. No external provider exists.

### Checkpoint 7 — frontend

Not started. No UI, no onboarding, no screenshots. The API is the only surface.

### Checkpoint 8 — marketing

Not started. The website was not modified, and no security claim was added to it.

### Checkpoints 9–10 — hardening and review

- Focused suites and the migration suite pass; `check:agent` passes for context hygiene, tool
  contracts and the constitution.
- The generated agent map check fails because another session has staged additions and deletions;
  regenerating it would rewrite that session's file. Not caused by this work.
- The emoji audit fails on a stale file under git-ignored `.validation/computer-use/tmp/`, which
  belongs to an earlier computer-use run. Every file this programme added was checked directly and
  contains no pictographic emoji.
- No full-suite run, no browser validation, no dependency scan, no independent reviewer.

### Known defect in this pass: commit `ced92681` contains another session's work

While staging `src/hutch/server/app.py` for the vault routes, the whole file was staged. Another
session had in-flight edits in that file (the schedule "why didn't it run?" projection:
`_occurrence_outcome`, `last_occurrence`, `needs_attention`). Those ~23 lines were committed under
this programme's commit `ced92681`, while that session's own commit `7d5be051` covers the rest of
the same feature (JS, CSS, tests, docs, evidence).

- **No work was lost.** The lines are present in `HEAD`, and `tests/test_schedule_outcomes.py` (nine
  tests, that session's own) passes.
- **What is wrong** is attribution: one focused change now spans two commits, and the schedule work
  in `app.py` is described by a vault commit message.
- **Why it was not repaired.** Fixing it means rewriting two commits in the middle of `main` while
  the working tree holds other sessions' uncommitted work. A rebase needs a clean tree, and
  stashing or cleaning another task's work is forbidden. Rewriting history under active sessions
  risks losing their work, which is a larger harm than a misattributed diff.
- **Remediation, when the tree is clean and no other session is committing:** rebase `ced92681` to
  keep only the two vault lines in `app.py`, and fold the schedule projection lines into
  `7d5be051`. The resulting tree should be byte-identical; verify with
  `git diff <before> <after>` returning nothing, then re-run `tests/test_schedule_outcomes.py` and
  `tests/test_vault_api.py`.

**Lesson recorded for the next pass:** stage exact hunks (`git add -p`), not whole files, in a
repository where several sessions share one working tree.

---

## Outstanding, in priority order

1. **Mediated use.** A tool that accepts a `SecretRef` plus one mediator that applies the value at a
   network boundary, with an agent-execution test asserting the model never receives it. Without
   this, the central product claim is unearned.
2. **Migrate model keys and ChatGPT tokens** into the vault, with read-back verification before
   deleting a file.
3. **Vault UI** in the existing design system: status, unlock, secret list, add/edit, grants, audit,
   with locked/empty/error states and keyboard access.
4. **Reauthentication before reveal.**
5. **Argon2id** if `argon2-cffi` becomes a dependency.
6. **Full suite + e2e** once a UI exists.

## Conventions for the next pass

- One checkpoint per commit series; no empty commits.
- Every claim in a document names the test or the file that supports it.
- Anything not implemented is labelled "not started" rather than described in the future tense as if
  it existed.
