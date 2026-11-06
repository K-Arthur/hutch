# Lessons and decisions: requirements for phases 2 to 9

Written 2026-11-06 from `01-SOURCES.md` (ids `A1` to `D21`) and `02-FAILURES-AND-COMPLAINTS.md`
(`FC-1` to `FC-17`). Later phases and tests cite the `VS-R#` ids below. Each requirement states the
phase that implements it and a test that fails before the change. A requirement is **adopted** only
if Hutch's single-owner, local-first shape makes it right; the rejected list says why the others
are not.

Status words used in this file: *requirement* (to be built and tested), *decided* (settled now, with
a reason), *owner question* (needs the owner, batched at the end), *deferred* (not this pass, with
the unblocker).

## 1. Requirements

| Id | Requirement | Phase | Test that must fail first | Basis |
|---|---|---|---|---|
| VS-R1 | Every vault route needs an owner credential minted at unlock or sign-in. Ambient loopback is not an owner credential for reveal, export, passphrase change, reset or passkey removal | 2 | Real server, default start: `POST .../reveal` with no cookie returns 401 or 403 (it returned 200 and the value in Phase 0); with an owner cookie but no step-up it returns `step_up_required` | audit F-02, C4, FC-8 |
| VS-R2 | A step-up grant is single-purpose, single-use, expires in at most 120 s, is bound to the session, is recorded, and a second use is audited as `replay`. Ending a session or run revokes the grants made under it | 2 | One test each: expired, wrong purpose, replayed, other session, grant for A used for B, revoked session | C5, B9 (7.5.1), edge cases rows 15 and 16 |
| VS-R3 | Throttling: anonymous attempts and attempts that present an owner credential never share a counter; recovery-key attempts have their own; ceiling stays at 300 s; the HTTP response carries `Retry-After` and the seconds remaining; the dashboard (`pages.py:162-169`) stops dropping the header | 2 | 50 anonymous failures, then the correct passphrase with an owner credential succeeds; assert the header on the real HTTP response | audit F-03, B7, B9 (6.1.1), D17, FC-15 |
| VS-R4 | Step-up methods: the vault passphrase always works. A WebAuthn assertion with user verification is offered when a passkey exists and the page's origin can carry an RP ID. No flow depends on a passkey alone | 2 | Step-up completes with no authenticator present; completes with a virtual authenticator, UV on; refuses an authenticator that cannot verify when UV is required | B16, D21, FC-17, decision VS-D4 |
| VS-R5 | Idle auto-lock separate from dashboard idle: counted from the last vault activity, persisted across restart, a stored 0 or "never" rejected or shown as unsafe, a visible countdown, lock on session end and on restart. A run in flight when the vault locks fails with a typed explained error and never uses a partial credential | 3 | Timer fires; activity extends it; value 0 rejected; value survives restart; in-flight run receives `VaultLockedMidRun` | audit F-05, D16, FC-14, A7 (`auth-revoked`) |
| VS-R6 | Delegated and unattended runs: the policy ADR (owner question Q1); until decided, fail closed with a visible "this run needs the vault; the vault is locked" state. Background and scheduled work receives no grants by default | 3 | From a dashboard-started worker (process executor) a mediated use works, or the run shows the refusal and the reason; a schedule against a locked vault shows the state | audit F-01, A2, edge cases rows 32, 54 and 56 |
| VS-R7 | Recovery-key unlock forces a new passphrase and a new recovery key. Reset exists, shows what is lost, needs step-up, and says whether the audit survives. The recovery key is confirmed by re-asking part of it before the vault is usable | 3 (API), 4 (UI) | Unlock with the recovery key, then the old passphrase is refused and a new recovery key is issued; reset on a real database copy leaves no readable secret | audit F-04, D12, B9 (6.4.4), FC-10 |
| VS-R8 | A database restored without its vault rows, or a vault from another machine, gives typed states `vault_missing` and `vault_foreign`: no crash, no overwrite, shown in the UI and by `hutch doctor` | 3 | Copy a real database to a new state directory with and without vault rows, and with another machine's vault | D15, A13, FC-13 |
| VS-R9 | The strength meter runs only in the browser and sends nothing. Minimum length for new or changed passphrases is decided in VS-D5. The common-passphrase blocklist stays | 2 (rule), 4 (meter) | New passphrase below the minimum refused; the meter makes no network request (Playwright network log) | B5, `crypto.py:63`, `crypto.py:81` |
| VS-R10 | `hutch doctor` reports: vault state, RP ID and origin against the configured hostname, a trusted-proxy list that holds an address that can move, plaintext credential files remaining, ambient environment keys, and a bounded keyring probe. It never prints a value | 2 | Doctor over a state with a canary key file and a canary ambient key: the canary appears nowhere in the output | audit F-10, A3, A4, D8, D11 |
| VS-R11 | Every sign-in refusal carries a stable reason code. The owner sees expected host and presented host. An unauthenticated visitor sees a generic message. A mismatch is a 4xx, never a 500 | 2 | Real browser against a proxy with a wrong forwarded host: code and both hosts for the owner, generic text for a visitor | A3, D11, FC-9 |
| VS-R12 | Forwarded headers are honoured only from configured trusted peers and only from the right end of the chain; a proxied request is never the loopback owner; a source that matches the host's own interface address is refused as a spoofing guard | 2 | Spoofed `X-Forwarded-For` and `X-Forwarded-Host` from an untrusted peer ignored; from a trusted peer honoured; cookie `Secure` | A3, D10, FC-8 |
| VS-R13 | The secret-value field is `type=password` with `autocomplete="new-password"` and a name that matches no login heuristic; no secret value is in the DOM until a reveal; the reveal response is `no-store`; the value is removed on hide, on navigation and on lock | 4 | Playwright: DOM and HAR contain the canary only between reveal and hide; the page source never does | B13, B6, `03-EDGE-CASES.md` Frontend |
| VS-R14 | On `pageshow` with `persisted` true the vault page re-reads lock state and discards any revealed value. A session revoked in one tab shows the signed-out state in the other without a data flash | 4 | Real browser: reveal, lock, navigate away, go back; two tabs, revoke in one | B12, edge cases row 17 |
| VS-R15 | Copy is best effort: overwrite the clipboard after the stated delay and say plainly that clipboard history and cloud clipboard may keep a copy. Prefer an on-screen reveal with auto-hide | 4 | UI text asserted; real Chromium clipboard overwritten after the delay | B14, D13, FC-11 |
| VS-R16 | The audit table is tamper-evident (hash chain over rows), has a stated retention and prune behaviour, and can be exported | 3 | Alter a row in a database copy: verification reports the break and the row | B8, edge cases Operations |
| VS-R17 | Credential migration protocol, per item: dry run writes nothing; validate everything before the first write; copy; verify by read-back decryption; switch the reader; owner-confirmed delete; rollback that does not overwrite a change made meanwhile. A stale old copy that reappears, or two copies that disagree, is a named visible conflict, never a silent winner | 5 | Crash after copy, after switch, after delete; an older build rewrites the old file; both copies differ | A4, A12, A13, D14, FC-12 |
| VS-R18 | A stored provider key is bound to the origin of its base URL. Changing the base URL while a key is stored needs an explicit re-confirmation and never sends the key to the new host first | 5 | Change a connection's `base_url` to a local sink and make a model call: the sink receives no key, or the change was refused | D2, FC-2 |
| VS-R19 | An ambient environment key is labelled and never silently wins over a stored key; an explicit choice is authoritative and does not fall through to another source | 5 | Same provider with both present: the chosen source is shown and used; removing the chosen one does not fall back silently | A4, A5, audit F-07 |
| VS-R20 | Child processes receive an allowlisted environment, with no secret in argv or environment; secrets reach a worker over stdin, a private fd or a 0600 file. **Dependency**: the worker needs its provider key, so this cannot be done before the hand-off design of VS-R6 and the provider work of phase 5 | 3 (hand-off), 5 | Canary in the server environment: the worker environment holds only the allowlist; a shell-tool child cannot read a canary from the worker's `/proc/<pid>/environ` or its parent's | D20, D4, D5, FC-6, `engine.py:409` |
| VS-R21 | Egress hardening, one shape at a time: DNS pinned between check and use; encoded and mapped IP forms refused using `ipaddress`; every redirect hop re-validated; trailing-dot, case, IDN, userinfo and port forms of the host refused or canonicalised; the response scanned for the credential in plain and in common encodings with an audit row and an alarm; bounded size and time. The limit for split or transformed echoes stays documented | 6 | Each case against a real local server | C4, A2, C1, D19, FC-16, limitation 3 |
| VS-R22 | Evaluate an optional path-prefix on a destination binding. State that a bound origin that accepts public writes is still a place the model can send other data | 6 | Request outside the bound prefix refused | D3, FC-3 |
| VS-R23 | External provider calls: absolute, non-symlink binary not writable by others and owned by the user; no shell; per-read 7 s and whole-batch 90 s style timeouts; a bounded batch; secrets on stdin; an environment allowlist that disables interactive prompts for unattended reads; typed `provider_locked` and `provider_unavailable` within the bound | 7 | A fake CLI that hangs, prints a prompt, or exits non-zero; a process-list check showing no secret in argv | A5, A10, A11, C2, D9, FC-7 |
| VS-R24 | The OS credential store is probed with bounded calls. A locked collection or a missing session bus is a typed `keyring_unavailable`; it never falls back to a plaintext file | 5 and 7 | Fake `secret-tool` that sleeps, fails or prints a prompt | D8, FC-7 |
| VS-R25 | Sessions: list with device name and last seen; revoke one or all others (step-up for others); session cookie with the `__Host-` prefix verified; `Clear-Site-Data` on logout | 2 | Real proxy path: cookie attributes asserted; revoke reflected in the second tab | B6, B9 (7.4.3, 7.5.2), audit F-06 |
| VS-R26 | Passkeys: list, rename, last-used, backup eligibility and state, "bound to host X". Removing the last one is refused unless the passphrase path and the recovery key are confirmed | 2 | Remove last passkey refused; removal allowed once the recovery path is confirmed; hostname change lists the old ones as bound to the old host | B1, B10, D11, FC-9 |
| VS-R27 | The README, `SECURITY.md`, the vault docs and the website never contradict each other. Each claim maps to a named test or a dated check. Banned: "unhackable", "military-grade", "zero-knowledge" | 8 (check each phase) | A claims table in `testing-and-validation.md`, reviewed against the code | A1, A2, A6, A14 |
| VS-R28 | Candidate: detect a secret-shaped value typed into chat or a memory write and offer the vault, as Codync refuses credentials in memory and Grok offers a secure form | 4 or later | A canary-shaped value in a memory proposal is refused with a reason | A14, A16, D6 |
| VS-R29 | Any value held by the unlocked vault is replaced by a placeholder in tool results before they are stored or sent back to the model | 3 | Canary in a tool result: absent from the database copy, the event log and the model-bound message | D6, D7, C1, FC-4, `egress.py:89-91` |
| VS-R30 | Deleting a secret says the vendor key is still live and must be revoked there, aborts runs in flight with a typed stop reason, and shows that the secret is gone | 3 (API), 4 (UI) | Delete during a run: typed stop; list no longer shows it | A7, A14 |
| VS-R31 | Export and backup wording: a plaintext export is named as one; an encrypted export is the default; key material and ciphertext are described as separate backups; an export made with a lost secret cannot be restored by that secret | 3 | Round trip: export, wipe, import with the right and the wrong secret | A13, D12, D15 |
| VS-R32 | DEK and KDF-parameter rotation is resumable and killed mid-way without data loss. Argon2id is gated on VS-D6 | 3 | Kill the process mid-rotation on a real database copy; reopen with the old and the new passphrase | B11, B17, A8 (do not retry blindly) |

## 2. What was adopted from the owner's reference pages, and what was not

| Reference idea | Decision | Reason |
|---|---|---|
| Refs are `{source, provider, id}` with strict id grammar and no `..` | Already adopted (`vault/refs.py`); keep. Extend with the path checks of A5 for any CLI provider | Matches Hutch's single-provider reality |
| Resolve into a startup snapshot with atomic publication and last-known-good | **Rejected** again | Hutch resolves on use inside one unlocked process; a snapshot would be a second source of truth (also A6) |
| Sentinel substitution through a loopback egress proxy | **Rejected** again | Large surface, needs a CA, protects only cooperating clients (A2's own words). Hutch's single mediated call stays |
| Background commands start with no grants | **Adopted** (VS-R6) | The audit shows every shipped launch path is a background worker |
| Grants die with the run; stopping one does not affect siblings | **Adopted** (VS-R2, VS-R30) | Closes the revoked-mid-run edge case |
| "Explicit ref never falls through to another credential source" | **Adopted** (VS-R19) | Answers audit F-07 |
| Audit that finds plaintext residue and demands a clean re-audit | **Adopted** (VS-R10, VS-R17) | A migration is not done until the old copy is gone |
| No rollback backups containing historical plaintext | **Adopted with a difference** | Hutch's rollback decrypts from the vault on request; no historical plaintext is written to disk |
| Scrub migrated plaintext by default | **Rejected** | Hutch deletes only after owner confirmation, per item (master prompt rule 8) |
| OAuth material is not a SecretRef because refresh mutates it; lost refresh response fences the credential | **Adopted as a Phase 6 constraint** | Blind retry of a rotating refresh token can destroy the grant. OAuth refresh stays "reveal only" or "owner reconnect" until a durable pending marker design exists |
| Trusted-proxy stable reason codes and own-interface spoofing guard | **Adopted** (VS-R11, VS-R12) | Directly testable against `security.py` |
| Scope headers and device auto-approve | **Rejected** | No matching surface |
| Account-wide vault shared by every bot | **Rejected** (Grok) | Per-bot grants are the point of the programme |
| "Do not store credentials in memory" with revert and explanation | **Adopted as a candidate** (VS-R28) | A write-time check on a model-readable surface |

## 3. Decisions

| Id | Decision | Status | Reason and evidence |
|---|---|---|---|
| VS-D1 | **Lockout model.** Keep one counter per vault for anonymous attempts and give attempts that present a valid owner credential their own. Keep the 300 s ceiling. Recovery-key attempts have a separate counter | decided; ADR in phase 2 | OWASP says the counter belongs to the account (B7), and the account here is the vault, which is the DoS in audit F-03. CVE-2026-33935 (D17) is that bug with a 24 hour ceiling. Hutch cannot tell local processes apart by address, so the owner credential, not the address, is what separates the buckets |
| VS-D2 | **WebAuthn PRF as a vault unlock factor: deferred.** If ever built it is one more wrapped copy of the same DEK, never the only way in, with an HKDF `info` and a per-credential salt stored server-side | deferred | Works with a virtual authenticator (B16: 32 bytes, deterministic per salt). Real-hardware support is fragmented and the sources disagree (B2, B4); the PRF value exists only in the browser, so the server would receive the derived key, which is the same trust as a typed passphrase; a deleted passkey destroys that wrap (B3). **Unblocker**: the owner tests a real platform authenticator and a real security key, and a phase asks for it |
| VS-D3 | **Recovery key is the identity proof for reset and passkey removal.** There is no support desk to prove identity to, so ASVS 6.4.4 is met by requiring the recovery key or the passphrase | decided | B9, single-owner shape. If both are gone the only path is the explicit reset in VS-R7 |
| VS-D4 | **Step-up and loopback passkeys.** The passphrase is the default step-up everywhere. WebAuthn with user verification is offered when a passkey exists and the origin can carry an RP ID. A passkey ceremony works on `http://localhost:PORT` with RP ID `localhost` (B16), and fails on an IP-literal origin. So phase 2 adds `localhost` as an allowed loopback-only RP, relaxing the HTTPS-only rule in `passkeys.py:30-57` for that one case, behind an ADR, and the doctor tells the owner to open the dashboard at `localhost` | decided, owner can object; ADR in phase 2 | Resolves audit F-11's premise. A user-verified assertion needs the owner's action at the authenticator (a PIN, biometric or key touch), which a local process cannot supply by itself; that has not been tested against real hardware. Limit: on Linux Chrome has no platform authenticator (D21), so a passkey there means a USB key or a phone, which is why the passphrase stays the default |
| VS-D5 | **Passphrase minimum.** Raise the minimum for new or changed passphrases from 12 to 15; existing vaults are not forced | decided, owner can object | NIST SP 800-63B-4 requires 15 characters for a single-factor secret and forbids composition rules (B5); the vault passphrase is the only factor. The blocklist stays |
| VS-D6 | **Argon2id.** D1 stands as a safe default; Argon2id is better and available. Measured on this machine: scrypt 2^17/8/1 515 ms, Argon2id 19 MiB t2 p1 40 ms, 64 MiB t3 p4 194 ms (B17) | owner question Q3 | Needs the `cryptography` floor raised from 42 to 44, a runtime check for `UnsupportedAlgorithm`, and a KDF id in the stored wrap. Existing wraps keep scrypt until the next passphrase change. Not urgent |
| VS-D7 | **Worker environment.** The server's whole environment goes to every worker (`engine.py:409`). Cleaning it is blocked on the worker getting its credentials another way | decided as a dependency | VS-R20 depends on VS-R6 and phase 5; not a phase 2 task |
| VS-D8 | **External provider to ship.** Recommend the OS credential store first | owner question Q4 | It adds no dependency, exists in four connectors, and the headless Linux hang class (D8) is already addressed by bounded calls. 1Password's CLI needs a user-installed binary and carries the hang class of D9. Either way, one provider only |
| VS-D9 | **Website.** No security claim is published before phase 8. The README's vault line and `SECURITY.md` are checked against the code at each phase (VS-R27) | decided | A1; master prompt rule 5 |

## 4. Deferred

| Item | Reason | Unblocker |
|---|---|---|
| PRF-derived unlock | VS-D2 | Real-hardware test by the owner |
| Per-secret "this run only" entry that is never stored | Popular shape (A14) but a new data flow | A phase 4 design review |
| MITM egress proxy, snapshot and owner classes | Rejected, not deferred | A concrete need that mediation cannot meet |
| Cloud secret managers (Doppler, Infisical, AWS, Azure, Google) | Hosted and multi-tenant | Multi-user or hosted Hutch |
| Reddit and Hacker News mining | Not searched directly this pass | A follow-up pass if the owner wants it |

## 5. Owner questions (batched, asked when the phase needs them)

| Id | Question | Phase | Recommendation |
|---|---|---|---|
| Q1 | Unattended runs: fail closed only, or a time-boxed, scope-limited, revocable lease the owner grants while unlocked | 3 | Fail closed with a visible state first; the lease only if the owner wants it, with an ADR |
| Q2 | A read-only vendor credential and a spend cap for one live call, or confirm "blocked: no credential" | 6 | Default to blocked |
| Q3 | Raise the `cryptography` floor from 42 to 44 for Argon2id | 3 (rotation) | Yes, low priority; if no, D1 stands |
| Q4 | Which external provider to ship | 7 | OS credential store first |
| Q5 | Object to the `localhost` RP exception in VS-D4 or the 15 character minimum in VS-D5 | 2 | None needed unless the owner objects |

## 6. Honesty notes

- B1 and B5 were partly read (the first 100,000 characters of two large specifications). The UV,
  PRF, RP ID and recovery sections were not read from the standards themselves. Behavior was
  established by experiment (B16) and secondary sources, and is labelled that way.
- B16 and B17 are one machine, one browser build (Chromium 153.0.8010.12), a virtual authenticator.
  They show the browser and the library behave this way, not that real authenticators do.
- Vendor claims (C1) are marketing pages read through search summaries.
- The research did not touch any of the 17 doc-set files other than reading `research.md`; edits to
  `security-limitations.md` and the others belong to the phases that close each item.
