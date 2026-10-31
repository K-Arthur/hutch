# Security limitations

Everything here is a limitation of the **shipped** code, stated so nobody builds on a false premise.
Each entry names what is not true and, where one exists, the follow-up that would change it.

## 1. An unlocked vault is readable by the Hutch process

The DEK sits in process memory while unlocked. A compromised Hutch process, a malicious plugin
loaded into it, or a debugger attached to it can read every secret. Encryption at rest protects
against theft of the database and backups; it does not isolate the running application.

**Not claimed:** process isolation, sandboxing of the vault, or protection from a compromised
dependency.

## 2. A process running as the same OS user can read the unlocked vault

Existing mechanism: the agent's shell tools run as the same user. If such a tool can reach Hutch's
memory or call its HTTP API with the owner's cookie, it can read secrets while the vault is unlocked.
Only process-level isolation would change this.

## 3. `use` reaches one shape of egress, and nothing else

`vault_http_request` (through `vault.egress.mediate_http`) applies a value to one request header of
one request to one origin the owner bound to that secret. An agent turn that calls it receives the
service response and never the value; `test_vault_agent_turn.py` runs the real engine and asserts the
value is in no event, message or table.

The limits of that are specific, and each is a real gap:

- **It is not a network sandbox.** A bot with the `shell` tool can make its own requests. If it also
  has `reveal`, it can read a value and use it however it likes. Mediated use constrains the path it
  provides; it does not constrain a path the agent already has. Process isolation would be required
  for that, and Hutch has none for bots outside Strict Offline.
- **One header, one request, no redirects.** A protocol that needs a credential in a query string, a
  signed body, a multi-step exchange or an OAuth refresh is not served by this mediator yet. A 3xx is
  reported, not followed; the follow-up request needs its own authorization and its own binding.
- **Only tools that use it benefit.** A connector that reads a credential through any other path is
  unchanged. No bundled connector uses the vault today.
- **The value is in the Hutch process.** It is decrypted into memory by design (see limitation 1).
  "The agent never sees it" is true of agent context; it is not a claim about process memory.
- **Response scrubbing is exact-match.** \`mediate_http\` removes the credential string itself from a
  response body and headers. A service that echoes it transformed — base64, URL-encoded, split across
  fields, hashed — would not be caught. Scrubbing defends against an honest service leaking an
  Authorization header, not against a hostile one.
- **A process-executed run has no unlocked vault.** A delegated or strictly-offline run runs with its
  own \`Store\`, so \`vault_for\` gives it a locked vault and a mediated use fails with \`VaultLocked\`.
  That fails closed; it also means those runs cannot use the vault at all yet.
- **Response scrubbing is exact-match.** `mediate_http` removes the credential string itself from a
  response body and headers. A service that echoes it transformed — base64, URL-encoded, split across
  fields, hashed — would not be caught. Scrubbing is a defence against an honest service leaking an
  Authorization header, not against a hostile one.
- **A process-executed run has no unlocked vault.** A delegated or strictly-offline run runs with its
  own `Store`, so `vault_for` gives it a locked vault and a mediated use fails with `VaultLocked`.
  This fails closed; it also means those runs cannot use the vault at all yet.

**Not claimed:** "agents are sandboxed away from credentials", or that a bot with a shell and a
reveal grant cannot exfiltrate a value.

## 4. Metadata is not encrypted

Secret names, scopes, categories, descriptions, timestamps and the audit trail are plaintext in the
database. A stolen backup reveals that a secret called "Stripe production key" exists and that
`bot:abc` used it against `api.stripe.com`. It does not reveal the key.

## 5. The passphrase is the weakest link

The KDF makes guessing expensive (128 MiB, ~0.56 s per attempt) but a memorable passphrase remains
attackable by someone who has the database and patience. A minimum length and a short list of common
passphrases are enforced; that is not a breach corpus.

## 6. scrypt, not Argon2id

The OWASP fallback, chosen to avoid a new compiled dependency. Argon2id is preferred by the same
guidance and offers a somewhat better margin against some side-channel attackers. The KDF is
versioned per wrap so this can change without re-encrypting data.

## 7. No reauthentication before a reveal

The owner's session cookie is enough to reveal a secret. A stolen session on an unlocked vault can
read values. A reauthentication step is a listed follow-up, not an implemented control.

## 8. Existing plaintext credentials remain

Model-provider API keys (`$STATE_DIR/keys/*.key`) and ChatGPT tokens (`$STATE_DIR/chatgpt/*.json`)
are still plaintext files readable by any agent with file access. The vault does not yet replace
them; see `migration.md`.

## 9. No external providers

No 1Password, Bitwarden or HashiCorp Vault integration exists. A reference naming them is refused.
See `provider-integrations.md`.

## 10. No user-facing surface

The vault is reachable only through the API and through one tool. There is no dashboard page, no
onboarding flow and no visual validation. Binding a destination, granting a bot and setting an
approval requirement are API operations today. Any screenshot or marketing claim about a vault UI
would be false.

## 11. Reset and recovery are all-or-nothing

There is one vault per database. Losing both the passphrase and the recovery key loses everything;
there is no per-secret recovery, no escrow, and no administrative override. This is a design choice,
not an oversight.

## 12. Best-effort memory zeroing

`crypto.zero` overwrites mutable key buffers, but Python cannot guarantee that no copy of a value
exists in an allocator, a traceback or swap. It shortens the window; it is not guaranteed memory
cleansing.

## 13. Throttling is per process

Unlock throttling lives in the database but the delay is evaluated per process, and a restart clears
the in-memory portion. It slows online guessing; the KDF is what answers offline guessing.

## 14. Audit completeness depends on callers

Anything that calls `VaultBook` directly writes audit rows, but a future code path that reads the
database without going through `VaultBook` would not be audited. The audit is only as complete as the
discipline of the code that uses the vault, and that is enforced by review, not by the type system.

---

For each guarantee that *is* claimed — confidentiality at rest, denial by default, use/reveal
separation, audit immutability — `testing-and-validation.md` names the test that supports it.
