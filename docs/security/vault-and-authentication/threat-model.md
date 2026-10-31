# Threat model

Method: STRIDE, applied to Hutch as it is actually deployed (a single-operator local process, with
an optional remote authenticated surface). Likelihood is judged for a local-first personal or
small-team installation, not for a public SaaS.

Assets, in order of value:

1. **Secret values** held in the vault.
2. **Vault key material** (DEK, passphrase wraps, recovery key).
3. **Integration refresh tokens** held in the OS keyring.
4. **Sign-in material** (owner cookie/token, passkey sessions).
5. **Audit integrity** — the record of who used what.
6. **The person's other data** (transcripts, memory, files) reachable by an agent.

Trust boundaries: human ↔ browser; browser ↔ Hutch ASGI; Hutch ↔ SQLite; Hutch ↔ OS keyring;
Hutch ↔ model provider; bot run ↔ tool subprocess; Hutch ↔ backup location.

---

## T1. Prompt injection asks an agent for a credential

- **Capability:** an attacker can place text in a web page, document, email or tool result the agent
  reads.
- **Path:** injected text instructs the agent to read a key file, print an environment variable, or
  call a tool that returns a secret.
- **Impact:** full compromise of whichever credential the agent can reach.
- **Likelihood:** high — this is the defining attack on agent platforms.
- **Mitigations (implemented):** no secret value is written to a tool result, transcript, event or
  run document by the vault; `reveal` is a distinct permission and is audited; the vault never
  exposes values through list/metadata APIs.
- **Mitigations (planned):** mediated egress so an agent's request can carry a credential it never
  sees; a tool-level rule that refuses to return vault values to the model.
- **Residual risk:** an agent with shell access can still read any *plaintext* file the owner
  leaves on disk, and can read a credential after the owner explicitly reveals it into a tool
  result. Encryption at rest does not fix this.
- **Verification:** an integration test that drives a real tool call with a prompt-injection string
  and asserts the tool result contains no secret; an audit row shows the attempt.

## T2. Modelling the vault as a "secure" boundary that it is not

- **Capability:** none — this is a design failure, not an attacker.
- **Path:** claiming process isolation or "agent cannot access" while the vault runs in the same
  process as the agent's tools.
- **Impact:** the operator makes decisions on a false premise.
- **Mitigation:** `security-limitations.md` states the exact guarantees; architecture §3 tabulates
  what each attacker obtains. No UI string claims isolation that is not implemented.
- **Verification:** documentation review against the code paths; the claim table is part of the
  checklist in `testing-and-validation.md`.

## T3. Database or backup theft

- **Capability:** read access to `hutch.db`, a WAL file, or a backup copy.
- **Path:** copy the file; read `vault_secret_versions.ciphertext`.
- **Impact:** metadata disclosure (secret names, categories, scopes, timestamps, audit history).
  No values.
- **Likelihood:** moderate — laptops are backed up, synced and lost.
- **Mitigation:** AES-256-GCM with the DEK wrapped under a passphrase-derived KEK that is never
  stored. AAD binds ciphertext to identity, so rows cannot be swapped or replayed undetected.
- **Residual risk:** metadata is not encrypted. Weak passphrases are attackable at scrypt cost.
- **Verification:** a test that reads the raw database file and asserts no fixture secret appears
  in it; an offline decryption attempt with a wrong passphrase fails.

## T4. Offline brute force of the passphrase

- **Capability:** database copy plus unlimited offline attempts.
- **Path:** guess passphrases, derive KEK, try to unwrap the DEK.
- **Impact:** vault disclosure if the passphrase is weak.
- **Mitigation:** scrypt N=2^17 (128 MiB), r=8, p=1 per attempt; 16-byte random salt; a minimum
  passphrase length; the cost parameters are stored, so they can be raised.
- **Residual risk:** a memorable passphrase remains the weakest link. This is inherent to
  passphrase-based encryption and is documented rather than hidden.
- **Verification:** a benchmark test records derivation time on the reference machine; the
  documented floor is enforced by a unit test on the parameters.

## T5. Online guessing against an exposed dashboard

- **Capability:** network access to a dashboard the owner exposed.
- **Path:** repeatedly call the unlock endpoint.
- **Impact:** denial of service; eventually a lucky guess.
- **Mitigation:** the existing middleware already refuses remote access unless explicitly enabled
  with HTTPS and a passkey session. Vault unlock additionally records failures and enforces a
  growing delay.
- **Residual risk:** the delay is per process and resets on restart; it is not a substitute for
  keeping the dashboard loopback-only.
- **Verification:** a test that asserts the Nth failure is refused with a delay and audited.

## T6. Session theft and replay

- **Capability:** steal an owner cookie or a paired-device session token.
- **Path:** replay it.
- **Mitigation (existing, verified):** remote sessions are database-backed, idle- and
  absolute-limited, revocable, and only accepted over HTTPS; owner tokens are never accepted
  remotely; cookies are `HttpOnly`, `SameSite=Strict`, `Secure` when the scheme is HTTPS; CSRF is
  enforced for unsafe methods.
- **Residual risk:** an unlocked vault in the same process remains reachable by a stolen owner
  session — the vault inherits dashboard authorization. A future "reauth to reveal" step narrows
  this; it is not implemented yet and is not claimed.
- **Verification:** an existing-suite check plus a new test asserting that vault reveal requires an
  authenticated principal object, not merely a passphrase.

## T7. Cross-bot and cross-scope access

- **Capability:** a bot run (possibly influenced by injected content) tries to use another bot's
  credential.
- **Path:** name a ref belonging to another scope.
- **Mitigation:** grants are keyed by `(secret_id, principal_kind, principal_id, permission)`;
  scope is checked as a second condition; deny by default; every denial is audited.
- **Verification:** tests for a bot using a workspace secret with no grant, a bot using another
  bot's secret, and a revoked grant.

## T8. Ciphertext substitution or replay

- **Capability:** write access to the database.
- **Path:** move a version row to another secret, or replay an old version under a new number.
- **Mitigation:** AAD includes secret id, version, scope and category; the version number is part
  of the AAD and part of the primary key.
- **Verification:** a test that swaps two ciphertexts and asserts `VaultCorrupt`, and one that
  replays an old version number.

## T9. Secret leakage through logs, transcripts or errors

- **Capability:** read logs or a transcript.
- **Path:** an exception message containing the value, a `repr` of a secret object, a debug dump.
- **Mitigation:** the vault never logs values; error types carry codes, not content; secret values
  are held in `bytes`/`bytearray` and exposed only through an explicit method; audit `reason` is a
  closed vocabulary.
- **Verification:** a test that captures log output during a full store/reveal cycle and asserts
  the fixture value never appears; a grep of the transcript and event log after an integration run.

## T10. Symlink, path traversal and file-mode attacks on existing credential files

- **Capability:** same-user process, or a race while a key file is written.
- **Path:** replace a key file with a symlink; read another key.
- **Mitigation (existing):** `ConnectionBook.set_key` creates with `O_CREAT|O_EXCL`-style mode
  `0600` and `chmod`s the directory to `0700`; ChatGPT tokens use `O_NOFOLLOW`-style private writes
  via `fchmod` on the descriptor. The vault itself writes no files.
- **Residual risk:** these paths remain outside the vault until a later migration. Migration is
  planned, not claimed.
- **Verification:** existing tests; migration tests when it lands.

## T11. Malicious skill, connector or plugin

- **Capability:** ship a skill or connector that reads credentials.
- **Path:** the connector process inherits the OS user's access.
- **Mitigation:** connectors receive credentials through their own store, not through the vault, so
  a connector cannot read the vault's DEK. Vault grants are unavailable to `connector` principals
  until an explicit integration is written and reviewed.
- **Residual risk:** a connector can still exfiltrate its *own* credential, by design — it needs it
  to work.
- **Verification:** grant tests that assert a connector principal is refused a vault secret.

## T12. Compromised dependency

- **Capability:** a malicious or buggy package in the dependency tree.
- **Path:** read process memory, intercept a KDF call, exfiltrate.
- **Mitigation:** primitives come from `cryptography`; no hand-rolled crypto; the new code adds no
  dependency at all. The vault core imports only stdlib plus `cryptography`.
- **Residual risk:** a compromised `cryptography` build defeats everything. That is out of scope
  and stated.
- **Verification:** the new modules' import graph is inspected in review; no new lines in
  `pyproject.toml`.

## T13. Release of an encrypted backup containing a wrapped DEK plus a recoverable passphrase

- **Capability:** someone who obtains both the backup and the recovery key (often stored together
  "for safety").
- **Mitigation:** each backup remains protected only by the passphrase/recovery key; the recovery
  key is shown once and never written to disk by Hutch; documentation tells the owner to store the
  key separately.
- **Verification:** a documented procedure and a test that restoring a backup without the key fails.

## T14. Denial of service against the vault

- **Capability:** local process or an exposed dashboard.
- **Path:** repeatedly trigger scrypt derivations (128 MiB each) and exhaust memory.
- **Mitigation:** unlock attempts are throttled; derivation happens only on unlock, never on a
  request hot path.
- **Residual risk:** the first few attempts are still expensive; that is the point of the KDF.
- **Verification:** throttle test; a benchmark that asserts derivation happens once per unlock, not
  per read.

## T15. Silent downgrade to a weaker path

- **Capability:** configuration mistake or a future patch.
- **Path:** fall back to a file, an environment variable, or "unencrypted mode" when the vault is
  unavailable.
- **Mitigation:** there is no fallback code path. `VaultNotInitialized` and `VaultLocked` are hard
  errors. Tests assert that no file is written and no value is returned in those states.
- **Verification:** negative tests for each state.

---

## Out of scope, explicitly

- Root-level or kernel attackers.
- Physical access with the machine unlocked.
- A compromised `cryptography` binary.
- Supply-chain compromise of the Python interpreter itself.
- Multi-tenant isolation between different OS users on the same host — Hutch is single-operator.
- Protecting a value the owner deliberately reveals on screen from shoulder-surfing or a screen
  recorder.
