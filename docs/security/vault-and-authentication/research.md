# Vault, secrets management, identity and secure sign-in: research

Status: evidence base for the programme. Access date for every source below: **2026-10-31**.

Scope: what a local-first agent platform must do to hold secrets a person supplies, let agents
*use* them without *reading* them, and keep sign-in defensible when the same machine also runs
untrusted model output, tools and subprocesses.

This document is deliberately a record of what the sources actually say. Where a source was
unavailable, JS-rendered, or only partly retrievable, that is stated rather than filled in.

---

## 1. Method

1. Read Hutch's own security surfaces first (`src/hutch/server/security.py`,
   `src/hutch/server/passkeys.py`, `src/hutch/connections.py`, `src/hutch/platforms/credentials.py`,
   `src/hutch/google_calendar.py`, `src/hutch/store.py`), so the research answers Hutch's real
   questions instead of a generic product's.
2. Retrieve primary standards sources and record the exact guidance, not a paraphrase of memory.
3. Retrieve competitor documentation for credential models that agents actually use.
4. Retrieve *public issue trackers* for failure patterns, so complaints are cited rather than
   invented. Only titles, dates and links retrieved from the GitHub search API are recorded.
5. Convert each finding into a decision (adopt / reject / investigate) in §7, and into a
   requirement in §8.

Limitations of this pass:

- Competitor *incident* research is limited to public issue trackers and vendor documentation.
  No private incident reports were available, and no claim is made that a cited issue is a
  security incident.
- Rakazo's storage page is partly server-rendered; the retrievable portion covered content
  encryption, bot-home object storage and migration, which is what this programme needed.
- Several sources are marketing or product documentation and describe intent as much as
  implementation. They are treated as *design references*, not as proof those products behave
  as described.

---

## 2. Standards and primary guidance

### 2.1 Password and passphrase storage

Source: OWASP Password Storage Cheat Sheet,
<https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html>.

Retrieved guidance (quoted where it is a number that matters):

- "Use Argon2id with a minimum configuration of 19 MiB of memory, an iteration count of 2, and 1
  degree of parallelism."
- "If Argon2id is not available, use scrypt with a minimum CPU/memory cost parameter of (2^17), a
  minimum block size of 8 (1024 bytes), and a parallelization parameter of 1."
- "For legacy systems using bcrypt, use a work factor of 10 or more and with a password limit of
  72 bytes."
- "If FIPS-140 compliance is required, use PBKDF2 with a work factor of 600,000 or more and set
  with an internal hash function of HMAC-SHA-256."
- Password hashing must use a unique salt per password; fast hashes (SHA-256) are unsuitable.
- A hash should take "less than one second" on the target hardware, and the work factor should be
  raisable over time.

Consequence for Hutch: the vault's passphrase KDF is a *credential-protection* decision with a
published floor. The derivation cost must be stored with the data so it can be raised later, and
must be benchmarked on the target machine rather than guessed.

### 2.2 Secrets management

Source: OWASP Secrets Management Cheat Sheet,
<https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html>.

Retrieved guidance relevant to a single-machine product:

- Centralise and standardise storage, provisioning, auditing, rotation and management; it is
  normal for one deployment to use more than one secrets solution.
- Rotation is error-prone when manual; automate it or support it enough that operators do not
  improvise. Rotating encryption keys "might trigger full or partial data re-encryption".
- Auditing of secret access is a first-class control, not a log afterthought.

### 2.3 Cryptographic storage

Source: OWASP Cryptographic Storage Cheat Sheet,
<https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html>.

Used for the standing rules applied in the design: authenticated encryption only, no custom
constructions, per-context keys, no key reuse across purposes, and key management treated as the
hard part rather than the cipher choice.

### 2.4 Argon2 and TOTP specifications

- RFC 9106 (Argon2), <https://www.rfc-editor.org/rfc/rfc9106.html>: Argon2id is the recommended
  variant where side-channel and GPU attackers are both in scope.
- RFC 6238 (TOTP), <https://www.rfc-editor.org/rfc/rfc6238.html>: relevant only if TOTP is added;
  Hutch's existing remote sign-in uses WebAuthn, so TOTP is not on the critical path.
- RFC 9700 (OAuth 2.0 Security BCP), <https://www.rfc-editor.org/rfc/rfc9700.html>: relevant to
  connector OAuth; Hutch already uses PKCE and exact redirect validation.

### 2.5 Library primitives actually available

Verified in this environment on 2026-10-31: Python 3.13.15, SQLite 3.53.1, `cryptography` 50.0.2,
`argon2` **not installed**. `cryptography` provides AES-GCM
(<https://cryptography.io/en/latest/hazmat/primitives/aead/>) and scrypt
(<https://cryptography.io/en/latest/hazmat/primitives/key-derivation-functions/>).

This is the reason the first implementation uses scrypt rather than Argon2id: OWASP names scrypt
as the correct fallback, it needs no new dependency, and `cryptography` is already pinned. The KDF
is versioned in the stored record so Argon2id can be added later without rewriting ciphertexts.
This is recorded as a trade-off in `decisions.md`, not presented as the best available KDF.

---

## 3. How comparable products model agent credentials

### 3.1 Grok Bot ("Vault and secure sign-in")

Source: <https://docs.x.ai/grok-bot/vault>.

What it does, in its own terms:

- Vault holds logins, cards and contact info. "A Bot never sees a saved password, card number, or
  security code."
- A separate "secure secret card" holds API keys; after saving, "Grok Bot does not show the value
  again".
- Saved values are write-only in the UI: passwords stay hidden, cards show only the last four
  digits, and there is no reveal.
- A "Secure Form" lets a person type a value into a page without the model seeing it.
- Crucially: "Vault covers your whole account: everything you save is available to every Bot on
  your account, and you can't limit an item to one Bot." Shared bots instead use a per-bot
  "Secrets" list of environment-variable names, where "the description is visible to the Bot; the
  value is not", and where "Secrets on a shared Bot are used in every teammate's chat".

Lesson: the *use without disclosure* pattern is real and users are taught it through the UI. The
gap is **granularity**: account-wide vault access for personal bots, and all-teammates access for
shared bots. Hutch can make per-bot and per-credential scope the default instead of an afterthought.

### 3.2 Rakazo self-hosted storage

Source: <https://rakazo.com/docs/self-host-storage/>.

Retrieved design points:

- Bot homes (files, browser profiles, CLI tokens) are "encrypted on the server before upload,
  whatever `CONTENT_ENCRYPTION` says; the bucket only ever holds ciphertext."
- "Each home has its own random data key, kept on the computer's database row and wrapped by its
  space's content key."
- Each stored revision is sealed "in authenticated segments bound to that home and revision, so a
  modified, truncated or swapped object fails to restore instead of restoring the wrong files."
- Object keys are random ids that "name no bot, user or space".
- The operator must "back up the database and the encryption keys as before: the bucket cannot be
  read without them."
- A `content-encryption export` exists and "the export is plaintext: store it like the database
  itself."

Lesson: envelope encryption with a per-object data key wrapped by a scope key, plus AAD binding
ciphertext to its identity, is the right shape for a self-hosted product. It also shows the honest
edge: key material and ciphertext must be *separately* backed up, and export is a plaintext event
that needs deliberate handling.

### 3.3 Codync artifacts and memory

Sources: <https://www.codync.dev/docs/artifacts>, <https://www.codync.dev/docs/memory>.

Memory is described as "plain Markdown files on your computer" that "the bot keeps up to date
itself" and edits "right away, whatever the bot's approval setting". Artifacts are the persistent
output surface.

Lesson: transparent, file-based memory is excellent for inspectability and terrible for
confidentiality — the agent has the same read access as the person, and file-level tools can
exfiltrate anything in scope. Hutch already separates memory from secrets; this programme must not
put credentials into any surface the model can read.

### 3.4 OpenClaw gateway secrets

Sources (all retrieved):

- <https://docs.openclaw.ai/gateway/authentication>
- <https://docs.openclaw.ai/auth-credential-semantics>
- <https://docs.openclaw.ai/gateway/secrets>
- <https://docs.openclaw.ai/gateway/secrets/runtime-model>
- <https://docs.openclaw.ai/gateway/secrets/secretref-contract>
- <https://docs.openclaw.ai/gateway/secrets/secret-store-and-egress>
- <https://docs.openclaw.ai/gateway/secrets/integration-examples>
- <https://docs.openclaw.ai/gateway/secrets/operations>
- <https://docs.openclaw.ai/gateway/1password>
- <https://docs.openclaw.ai/gateway/secrets-plan-contract>
- <https://docs.openclaw.ai/gateway/trusted-proxy-auth>

The parts that withstand scrutiny:

1. **Refs are not values.** A SecretRef is exactly `{source, provider, id}` — for example
   `{source: "env", provider: "default", id: "OPENAI_API_KEY"}`. Provider aliases and id grammars
   are validated (`^[a-z][a-z0-9_-]{0,63}$` for provider; per-source id rules, with `..` path
   segments rejected for exec refs).
2. **Eager resolution, atomic publication.** "Secrets resolve into an in-memory runtime snapshot,
   eagerly during activation, not lazily on request paths." Reload "validates each mapped owner
   independently, then publishes one atomic snapshot."
3. **Last-known-good is conditional.** A failed owner keeps its last-known-good value only while
   "its ref identities, provider definitions, and complete non-secret owner contract are
   unchanged"; otherwise it goes cold. "A strict failure rejects the reload and preserves the
   active snapshot."
4. **Inactive surfaces must not block.** Unresolved refs on a surface that is not in use emit a
   non-fatal diagnostic instead of failing startup.
5. **Sentinels, not plaintext, in subprocesses.** Exec environments receive
   `oc-sent-v2...end` sentinels; a loopback egress proxy substitutes them "in request URLs, headers,
   and streamed bodies immediately before egress". Unknown sentinel-shaped values "block requests
   before network activity" rather than being forwarded.
6. **Destination binding is mandatory and explicit.** Each secret names exact HTTPS hosts;
   "Hostnames are stored lowercase in ASCII/punycode form and matched exactly; wildcards, suffix
   matching, and ports are not supported. A secret with no allowed hosts is never substituted."
   Redirects are not followed.
7. **Grants die with the process.** "Process exit, failed startup, cancellation, and timeout revoke
   that process's grant"; cancellation revokes "before native process termination".
8. **The proxy states its own limits.** "Destination binding does not make an allowed host
   trustworthy. A bound service that reflects request credentials can still return the plaintext to
   the agent. DNS-level compromise can redirect a permitted hostname because policy is
   hostname-based, not an IP pin." Basic proxy auth is "not treated as encryption".

The parts to *not* copy:

- The runtime snapshot, owner classes and reload machinery exist because OpenClaw is a long-lived
  multi-tenant gateway with hot config reload. Hutch is a local process that starts bots on demand;
  importing the whole model would add a second configuration system with no matching threat.
- The MITM egress proxy needs a generated CA trusted by child processes. That is a large, fragile
  surface — and OpenClaw itself notes agents can already read sentinels in their environment.

---

## 4. Failure and complaint analysis

These were retrieved from public issue trackers with the GitHub search API on 2026-10-31. Titles,
dates and links are as returned; "+N" is the reaction count on the issue. None is asserted to be a
security incident unless the issue itself says so.

| Date | Source | Problem | Underlying cause (established?) | Applies to Hutch? | Practical improvement |
|---|---|---|---|---|---|
| 2024-04-23 | bitwarden/clients #8873 (+121) <https://github.com/bitwarden/clients/issues/8873> | Firefox extension "constantly logging me out" | Not established in the issue text; session/lifetime handling is the usual suspect | Partly: Hutch's local owner cookie has an explicit token, remote sessions are DB-backed with idle and absolute expiry | Make session lifetime and revocation visible; never silently keep or silently drop a session |
| 2026-06-10 | bitwarden/clients #21165 (+87) | Autofill suggestions not showing in Brave | Browser/extension integration, not cryptography | No (Hutch has no browser extension) | Nothing |
| 2025-08-05 | bitwarden/clients #15899 (+72) | "Browser crash due to huge memory usage when unlocking vault" | Vault unlock is memory-heavy on the client | **Yes** — a memory-hard KDF can do the same to a small machine | Benchmark KDF cost; store the parameters; keep them raisable but bounded; document the memory floor |
| 2024-08-30 | bitwarden/clients #10815 (+51) | Autofill stopped working across sites on Firefox/Linux | Browser integration | No | Nothing |
| 2021-04-06 | bitwarden/clients #1770 (+39) | Safari high memory usage | Client implementation | Indirectly | Same KDF memory lesson |
| 2025-02-25 | infisical/infisical #3148 (+6) | "Exporting importing whole project from web ui" | Missing bulk import/export | **Yes** — migration in and out is a real user need | Ship an explicit, confirmed import/export story; never a casual download |
| 2025-02-13 | infisical/infisical #3116 (+5) | "Docker Compose getting started doesn't work (local or in production)" | Setup friction in self-hosted deployment | **Yes** — Hutch is self-hosted | One documented path that is exercised in CI, not a menu of partially tested paths |
| 2024-06-27 | infisical/infisical #2038 (+4) | "Kubernetes operator not idempotent" | Reconcile logic | Partly: Hutch migrations must be idempotent | Migration and repair must be safe to re-run |
| 2023-09-18 | infisical/infisical #1001 (+4) | "Infisical CLI slow response times" | Not established | Partly | Do not put a KDF on a request hot path; resolve once per unlock, not per call |
| 2019-01-15 | hashicorp/vault #6046 (+61) | "Support multiple KMS Keys for Auto Unseal" | Single recovery path is a real operational constraint | **Yes** | Provide an explicit recovery key from day one instead of a single unseal path |
| 2025-06-27 | hashicorp/vault #31125 (+30) | Lock file not created in GCS bucket after upgrade | Storage backend change | Partly | Backups and key material must be documented as one unit |
| 2023-06-27 | hashicorp/vault #21478 (+29) | Vault stopped honouring AWS identity for KMS after upgrade | Dependency/behaviour change | Partly | Pin and test the primitives you depend on |
| 2019-09-09 | hashicorp/vault #7450 (+25) | AWS SDK too old for IAM roles for service accounts | Stale dependency | Partly | Same |
| 2018-09-11 | keepassxreboot/keepassxc #2281 (+85) | No auto-type on Wayland | Platform integration | No | Nothing |
| 2017-04-17 | keepassxreboot/keepassxc #508 (+55) | Tag support request | Feature gap | No | Nothing |
| 2021-02-02 | keepassxreboot/keepassxc #6055 (+42) | Linux login manager / PAM SSO | Desktop integration | No | Nothing |
| 2018-03-13 | keepassxreboot/keepassxc #1724 (+17) | "What 'Safely save database files' means?" | **Ambiguous security wording** | **Yes** | Say precisely what is protected and what is not; no vague "securely" |
| 2019-06-17 | keepassxreboot/keepassxc #3279 (+11) | Choose backup location | Backup UX | **Yes** | Backups need a stated location and a restore that is tested |

What the pattern says:

- The loudest complaints are **operational**, not cryptographic: lockouts, memory on unlock,
  import/export, setup, idempotent migrations, unclear wording. A vault that is cryptographically
  correct but operationally hostile will be abandoned or worked around.
- **Ambiguity is a defect.** "Safely save", "secure", "encrypted" without a stated threat model is
  what users complain about in #1724.
- **Single points of failure in recovery** are a longstanding, high-reaction request (#6046).

---

## 5. Lessons adopted

1. **Separate the four secrets.** Sign-in credentials, vault unlock material, encryption keys and
   recovery material are different things with different lifetimes. Hutch's dashboard auth is a
   local owner token or a WebAuthn session; the vault must not silently reuse either as its key.
2. **Envelope encryption with identity-bound AAD.** A random per-vault DEK, wrapped by a
   passphrase-derived KEK, with every ciphertext bound to its row identity and version. This is the
   Rakazo shape and it makes row-swapping and truncation detectable.
3. **Refs, not values, in configuration and in agent context.** A typed `SecretRef` with a strict
   grammar, and no path from a ref to a value except through an authorised, audited call.
4. **Deny by default, per principal.** Per-bot and per-secret grants, rather than Grok's
   account-wide vault.
5. **Write-only by default.** A stored value is not readable back through the list API; reveal is a
   separate, explicitly granted, audited operation.
6. **Recovery is designed, not implied.** A high-entropy recovery key wraps the same DEK. Losing
   both the passphrase and the recovery key means the data is unrecoverable, and that is said
   plainly.
7. **Operational honesty.** State what is protected against database theft, backup theft, a
   compromised app process and a compromised OS account — separately, because they are different.

## 6. Lessons rejected (for Hutch's shape)

- A hot-reloading, multi-owner runtime snapshot with per-owner staleness classes: no matching
  reload system exists, and inventing one would create a second source of truth.
- A MITM egress proxy with a per-process CA: too much new attack surface for the local-first
  default. Revisit only with a concrete mediated-egress requirement.
- TOTP as a second factor for a loopback-only dashboard: WebAuthn already covers remote access, and
  a decorative second factor is worse than none.

---

## 7. Decisions

| Decision | Choice | Why | Revisit when |
|---|---|---|---|
| KDF | scrypt N=2^17, r=8, p=1 via `cryptography`, parameters stored per wrap | OWASP fallback floor; no new dependency; memory-hard | Argon2id becomes a dependency, or measured unlock time on target hardware exceeds ~1s |
| DEK | 32 random bytes per vault, wrapped per credential path | Rotation and recovery without re-encrypting every secret | Multi-device or shared-vault requirements appear |
| AEAD | AES-256-GCM, 96-bit random nonce, AAD binds vault/secret id/version/scope/category | Established primitive; binding prevents ciphertext substitution | Never for the primitive; AAD layout is versioned |
| Recovery | 32-byte random key, Crockford base32 with checksum, wraps the same DEK | Removes the single-unseal trap (#6046) without weakening the passphrase | Hardware-backed recovery is in scope |
| Storage | Tables in the existing Hutch SQLite database, one ordered migration | Follows repository law; inherits pre-upgrade backups and `_tx` atomicity | A separate vault file is justified by a concrete isolation need |
| Agent access | Explicit grants per (secret, principal, permission); `use` vs `reveal` are distinct | Grok's account-wide model is the gap to beat | Multi-user workspaces arrive |
| Reveal | Separate permission, audited, off by default | "Never shown" is the property worth keeping | An operator explicitly opts in |

## 8. Source-to-requirement mapping

- OWASP Password Storage §2.1 → `crypto.derive_kek` uses scrypt 2^17/8/1, per-wrap random salt,
  versioned parameters, and a documented benchmark.
- OWASP Secrets Management §2.2 → append-only audit for every secret operation; rotation is a
  first-class operation, not a manual edit.
- OWASP Cryptographic Storage §2.3 → AES-GCM only; no custom construction; no key reuse between
  wrap and data encryption.
- Rakazo §3.2 → per-vault DEK, wrapped DEK, AAD bound to identity and version.
- Rakazo §3.2 → ciphertext and key material are backed up as separate concerns; documented.
- Grok §3.1 → write-only default, explicit reveal, no value in list responses.
- Grok §3.1 (gap) → per-bot and per-secret grants, deny by default.
- Codync §3.3 → no secret ever enters agent-readable memory or files.
- OpenClaw §3.4 (1) → typed ref grammar with strict validation and no `..` traversal.
- OpenClaw §3.4 (2) → resolve on unlock and cache in the narrowest boundary; do not derive keys on
  request paths.
- OpenClaw §3.4 (4) → an unavailable secret must not prevent unrelated work from starting.
- OpenClaw §3.4 (5) → an unresolved ref must fail closed, never forward a placeholder.
- OpenClaw §3.4 (7) → grants and unlocked state end with the process/session.
- Bitwarden #15899 / #1770 §4 → KDF memory cost is benchmarked and bounded, and the cost is stored.
- Infisical #3148 §4 → import/export is explicit and confirmed; plaintext export is never casual.
- KeepassXC #1724 §4 → documentation states exactly what is and is not protected.
- HashiCorp #6046 §4 → a recovery key exists from the first release.
