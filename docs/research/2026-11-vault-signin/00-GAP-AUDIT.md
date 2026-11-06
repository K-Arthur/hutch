# Gap audit: vault and secure sign-in (Phase 0, 2026-11-06)

Audited at `a08009f6` (HEAD when the screenshots were taken) on a shared checkout. Method: read the
code at the cited lines, run the existing suites, and exercise a real `hutch serve` process on a
throwaway `HUTCH_STATE_DIR` with generated values. Nothing here is taken from `progress.md` on trust.
`.env*`, `*.db*` and `.state/` were not opened. No feature code was written; the one code change is a
test (F-14).

Labels: **verified live** (ran against a real server or browser), **verified in code** (read the line),
**not exercised** (stated, not claimed).

## 1. Baseline

| Check | Result |
|---|---|
| `npm run check:agent` | passes, all four: context hygiene (1086 files, 117 frozen), tool contracts (47 tools), constitution, agent map |
| `npm run test:agent -- tests/test_vault_*.py tests/test_native_credentials.py tests/test_migration.py` | first run: 234 passed, 1 skipped, **1 failed** (F-14). After the test fix: **235 passed, 1 skipped, 0 failed** (447 s; the machine was under load from another session) |
| The skip | `tests/test_native_credentials.py:121`, needs a native Windows/macOS vault |
| `npm run audit:context` | passes (1088 files) |
| `scripts/audit_emoji.py` | **fails, 8 hits, none ours**: all in `.codewhale/state/subagents.v1.json`, git-ignored state of another tool (`.gitignore:31`). The pass-1 failure (`.validation/computer-use/tmp/`) is gone. The script takes only `--root`, so files this programme adds are checked by scanning a root that contains only them |
| Agent-map failure noted in pass 1 | no longer occurs |

## 2. `progress.md` "Still not done"

| # | Item | Today | Evidence | Missing |
|---|---|---|---|---|
| 1 | Vault UI | **not started** | Only four tool-label mentions in `app.js` (6180, 6998, 8237, 11319). Settings headings, read from the live DOM: Model defaults, Appearance, About you, Installation. No vault, secret, passkey, session or security text on Settings or Apps & AI | Everything in the master prompt's UI list |
| 2 | Unlock from a supervised child run | **worse than documented: it is the shipped default** (F-01) | `cli.py:2544` `setdefault("HUTCH_EXECUTOR","process")`; `desktop.py:45`; `service.py:112`; `worker.py:39` opens its own `Store`; `vault.py:60-80` registry is keyed by `Store`. Live: server vault unlocked, a second process on the same database reports `initialized=True unlocked=False` | Policy ADR, visible "needs the vault" state, lease or fail-closed UI |
| 3 | Migrate model keys and ChatGPT tokens | not started | Inventory in section 5 | Per-item copy, verify, switch, confirm, rollback |
| 4 | Reauthentication before reveal | not started | Live: `POST .../reveal` returned 200 and the value with no cookie, no bearer, no session (F-02). `vault_api.py:259-266` | Step-up module; and an unresolved design conflict (F-11) |
| 5 | Connector mediation | not started | `rg` finds only three importers of `hutch.vault` outside the package: `tools/vault_http.py`, `server/app.py`, `server/vault_api.py` | Mediation per connector shape |
| 6 | Shapes beyond one header | not started | `vault/egress.py` (172 lines): one header, one request | Query string, signed body, OAuth refresh, each with a binding |
| 7 | Live vendor call | not done, **blocked: no credential** | None provided | One owner-provisioned read-only credential and a spend cap, asked at Phase 6. Claim stays implemented-unverified |
| 8 | Independent review | not done | Nothing recorded | Fresh read-only reviewer at Phase 9 |

## 3. `security-limitations.md`, all 14

| # | Verdict | Note |
|---|---|---|
| 1 | confirmed by design | Not re-tested |
| 2 | **understated** | The text assumes "the owner's cookie". A default `hutch serve` has no owner credential at all (F-02) |
| 3 | confirmed, one bullet **understated** | "Process-executed run has no unlocked vault" is true but reads as an edge case; it is every shipped launch path (F-01). "No bundled connector uses the vault" confirmed by `rg` |
| 4 | confirmed | `schema.py:38-52`: `name`, `description`, `category` plaintext columns; audit plaintext |
| 5 | confirmed | `crypto.py:63` minimum 12 characters, `crypto.py:81` common-passphrase list. No strength meter exists |
| 6 | confirmed, **decision D1 needs re-testing** (F-09) | |
| 7 | confirmed, **stronger than stated** | Reveal needs only an unlocked vault plus `X-Hutch-Request: 1`, which any non-browser client can send |
| 8 | confirmed, wording off | Files are `keys/<name>.key` and `chatgpt/accounts.json` plus `chatgpt/pending/*.json`, not `chatgpt/*.json` |
| 9 | confirmed | `refs.py:25` `PROVIDERS = ("hutch",)` |
| 10 | confirmed | Section 7 |
| 11 | **incomplete** (F-04) | The doc treats reset as a design choice; no reset operation exists to choose |
| 12 | confirmed by design | `crypto.zero` exists; not re-tested |
| 13 | **inaccurate** (F-03) | The throttle is database-backed, global per vault, and survives restart. The text says the opposite |
| 14 | confirmed by design | Not re-tested |

## 4. Findings no earlier document records

Severity is about the vault's stated claim, not about the product at large.

**F-01 (critical) The headline claim does not work in any shipped launch path.** `hutch serve`,
the desktop host, the systemd unit and the CLI all run with `HUTCH_EXECUTOR=process`. Each run is a
worker that opens its own `Store`, and `vault_for` is keyed by `Store`, so a worker's vault is always
locked. Verified live: with the dashboard's vault unlocked, a fresh process on the same database saw
`unlocked=False`. So `vault_http_request` fails closed with `VaultLocked` in any dashboard-started
run. `test_vault_agent_turn.py` passes because the test engine uses the thread executor. Not
exercised: a full dashboard run through a real provider (none configured, no credential to use).

**F-02 (high) A default `hutch serve` has no owner credential.** `security.py:338-343` grants the
owner principal to every loopback request when `HUTCH_AUTH_TOKEN` is unset, and only `desktop.py:46`
sets one. Verified live: create, put, then `POST .../reveal` with no cookie, bearer or Origin returned
200 and the generated canary. The route's own check is only `X-Hutch-Request: 1`. Anyone who can
open the TCP port as any local OS user, and any local process, is the owner. Whether a given bot tool
can reach the port depends on that tool's confinement; not exercised.

**F-03 (high) Anyone local can lock the real owner out of unlock.** `lifecycle.py:243-286` and
`model.py:18-19`: 3 free failures, then a delay that doubles to 300 s, stored in
`vault_unlock_failures` keyed by `vault_id` only. Verified live: 5 anonymous wrong passphrases
returned 403, the 6th to 8th returned 429, and the owner's **correct** passphrase was then refused
with 429. The delay at that point was about 2 s; the 300 s ceiling is computed from the code, not
run. There is no per-source key, and recovery-key attempts share the counter. Two further defects:
the 429 carries **no `Retry-After` header** because the global handler at `pages.py:162-169`
rebuilds the response from `exc.detail` and drops `exc.headers`; and the message has no seconds
(`vault_api.py:113`). No HTTP-level test asserts either; `test_vault_lifecycle.py:188-202` checks
only the exception.

**F-04 (high) There is no vault reset, and recovery does not force rotation.** `rg "def reset"` finds
nothing in `src/hutch/vault/` or `vault_api.py`; the API has create, unlock, unlock-recovery, lock,
passphrase, recovery-key. A vault whose passphrase and recovery key are both lost can be neither
reopened nor recreated through Hutch (`create` answers 409). `unlock_with_recovery_key`
(`lifecycle.py:150-172`) unlocks only; nothing forces a new passphrase or a new recovery key, which
`03-EDGE-CASES.md` requires.

**F-05 (medium) No idle auto-lock.** `rg "idle|timeout|ttl"` over `vault/` finds none. The DEK stays
in memory until an explicit lock or a restart. Restart locking is verified (a new process is
locked, F-01).

**F-06 (medium) Paired-device surface defects.** The dashboard does list, revoke and create pairing
codes (`app.js:9773-9775`, `10008-10016`, `10088-10092`). Verified live with a real paired
credential: the row reads `expires 31/12/1969` because `store.py:3148` returns `NULL AS expires_at`
and `app.js:10015` formats `new Date(null)`. Two pairings both appear as "Phone" and cannot be
told apart; there is no rename, no refusal to revoke the last credential, no step-up on revoke, and
no session list separate from credentials. Screenshot: `artifacts/phase0/paired-devices-row.png`.

**F-07 (medium) An ambient environment key silently wins.** `connections.py:279` returns the
environment variable before the stored file unless `prefer_stored_key` is set. `key_source()`
(`connections.py:287-297`) does name the source, so it is labelled but not chosen by the owner.

**F-08 (correction) Connector tokens are not plaintext.** The master prompt lists Google, Outlook
and Notion as plaintext. They are in the OS credential store. See section 5. Phase 5 covers provider
keys and ChatGPT tokens only. `SecretToolStore` is duplicated in `google_calendar.py:92` and
`outlook_calendar.py:60`.

**F-09 (decision input) Argon2id is available without a new dependency.** `cryptography` 50.0.2 on
OpenSSL 3.5.8 derived an Argon2id key here. `pyproject.toml:28` pins `cryptography>=42.0`, so using
it means raising the floor, which needs owner approval. Re-test decision D1 in Phase 1.

**F-10 (gap) `doctor.py` has no vault, passkey, RP ID or plaintext-credential check.** `rg` for
`vault|passkey|webauthn|RP_ID|plaintext|keys_dir` in `doctor.py` finds nothing.

**F-11 (design conflict for Phase 2) No principal has both a passkey and vault access.** A paired
passkey session is refused on `/api/v1/vault` (verified live: 403 "not available to paired
phones"). The owner reaches the vault over loopback `http://127.0.0.1`, where no WebAuthn RP ID can
exist: `passkeys.py:30-57` demands an HTTPS origin whose host is a DNS name, and a browser rejects an
IP. So "passkey step-up when a passkey exists" cannot protect reveal as the architecture stands.
Phase 2 must choose, with an ADR: owner step-up is the vault passphrase and passkeys stay a remote
sign-in factor; or loopback gets a `localhost` RP; or vault routes open to a stepped-up remote owner
session, which widens the boundary. Phase 2 owns the decision.

**F-12 (observation) Dark only.** `docs/design-system.md:351` makes the dark theme a product
decision, and Settings says "The dark workspace theme is fixed". Gate 5's "light and dark" is read as
dark at four widths plus one emulated-light pass to prove nothing changes.

**F-13 (observation) Server-side user verification is thinly tested.** `passkeys.py:97-101` and
`135-139` require it on both ceremonies; one test line references it. Chromium's virtual
authenticator cannot produce a non-UV assertion for a `required` request, so the browser refuses
first (verified live, scenario 5 below). The server check needs a test with a hand-signed assertion
whose UV flag is clear.

**F-14 (fixed) A stale test premise.** `test_vault_migration.py` rewound the schema by one version
and assumed `vault.migrate_destinations` was last. Another session appended
`route_spec_schema.migrate`, so the rewind landed after destinations and the test failed. The product
is correct. The test now derives the rewind point from the migration's position.

## 5. Credential inventory (code and schema only)

| Credential | Where (file:line) | Storage form | Readable by | Reaches logs |
|---|---|---|---|---|
| Provider API keys | `connections.py:260-285`, `335-348` | `keys/<name>.key`, 0600 in a 0700 dir; plaintext | Any process as the same OS user, including a bot with file or shell access | Not exercised; `key()` docstring says never logged |
| Ambient provider keys | `connections.py:279`; `data/connections.json` `api_key_env` | Process environment | Same user; inherited by children | Not exercised |
| ChatGPT access, refresh, id tokens | `chatgpt_auth.py:111-145`, `356-445` | `chatgpt/accounts.json` and `pending/*.json`, 0600; plaintext JSON | Same as above | Not exercised |
| Google (Calendar, Drive, Docs, Sheets, Gmail) | `google_calendar.py:92-155` | OS credential store via `secret-tool`; value on stdin; 3 s and 10 s timeouts; native APIs through `platforms/credentials.py` | OS keyring policy | Not exercised |
| Outlook | `outlook_calendar.py:60-120` | Same mechanism | Same | Not exercised |
| Notion | `integrations/notion.py:32` | `SecretToolStore` subclass | Same | Not exercised |
| Telegram token | `channels/telegram.py:20`; DB holds `credential_digest` and `credential_ref` only | `SecretToolStore` subclass | Same | Not exercised |
| MCP server config | `integrations/mcp/config.py:10-67` | Refuses credential values; environment references only | n/a | n/a |
| Owner token | `HUTCH_AUTH_TOKEN`; cookie holds `auth_digest(token)` | Environment; desktop mints one per launch (`desktop.py:45-46`), `hutch serve` does not | Same user | Not exercised |
| Pairing and session tokens | `store.py` `auth_sessions`, `paired_credentials` | SQLite | Not examined | Not examined |

## 6. Constraints the later phases inherit

- **Frozen files** (`.file-size-baseline.json`; now / baseline): `app.py` 7414 / 7461, `pages.py`
  711 / 731, `security.py` 512 / 513, `store.py` 12593 / 12593, `engine.py` 1836 / 1837,
  `runtime/builtin.py` 1943 / 1955, `chatgpt_auth.py` 515 / 519, `connections.py` 438 / 448,
  `app.js` 14401 / 14532. All sign-in, pairing, passkey and device routes live in `app.py`
  (2846-3038). New routes go in new modules with a one-line install, as `vault_api.py` does.
  `store.py`'s `_MIGRATIONS` is one physical line, so appending a migration adds no lines.
- The `Retry-After` fix (F-03) is an in-place edit in `pages.py:162-169`, which does not grow the file.
- The dashboard runs worker processes by default, so any run-time vault feature has to be proven in
  a process executor, not only in-process.
- **Real-WebAuthn harness**, built and proven this phase: `hutch serve --allow-remote` needs
  `HUTCH_TRUSTED_PROXIES` on loopback, an RP ID that is a DNS name, a TLS proxy sending exactly one
  `X-Forwarded-Host` and `X-Forwarded-Proto` (`security.py:134-198`), and Chromium started with
  `--host-resolver-rules`. Tools: `tools/tls_proxy.py`, `tools/webauthn_baseline.py`.

## 7. Captured surfaces

`docs/realignment/capture_vault_signin_baseline.py` against a real server, six pages: home,
Settings, Connectors, Apps & AI, `/login`, `/pair`. 30 views: dark at 360, 768, 1280, 1920 and
emulated light at 1280. Result in `artifacts/phase0/report.json`: 0 console errors, 0 horizontal
overflow, every page rendered its own heading. I looked at the Settings (360, 1280), login (360),
pair (360), Apps & AI (1280) and paired-devices images; the 768, 1920 and light views were measured,
not individually inspected.

Defects: the paired-devices date (F-06) and duplicate "Phone" labels. Not defects, checked: the
login page's "Local owner token" is a collapsed disclosure by design, and the website's line that
Apps & AI exposes one-use phone pairing is true (`app.js:9773`, 10088; flow below).

## 8. Real-browser baseline of the shipped sign-in

Chromium with a CDP virtual authenticator (CTAP2, internal, resident key, UV capable) against
`hutch serve --allow-remote` behind `tools/tls_proxy.py`, RP ID `hutch.test`:

1. Pairing with a one-use code through `/pair`: success.
2. Session after pairing: principal `paired`, capabilities `monitor` and `review`.
3. Paired principal on `/api/v1/vault` and `/api/v1/devices`: 403 both.
4. Fresh passkey sign-in, UV on: signed in.
5. Authenticator that cannot verify the user: refused in the browser (F-13).
6. UV restored: signed in. One resident credential held, `signCount` 3.
7. Owner dashboard device row: F-06.

Not exercised: a replayed assertion, hostname and RP mismatch, a trusted proxy that sends the
wrong headers, the 30-minute idle expiry, session revocation across two tabs, and any desktop
(Tauri) webview.

## 9. `ced92681`

Not repaired. The precondition (clean tree, no other session committing) fails: 25 dirty index and
working-tree entries from another session, and that session committed at least four times during this
phase. The commit still holds 22 added lines of `app.py` from the schedule-outcome work. Procedure
unchanged in `docs/security/vault-and-authentication/progress.md`.

## 10. Recommended order and owner questions

The phase order stands, with these changes to what each phase must prove:

- **Phase 2** starts with the F-11 ADR and the F-02 decision (vault routes should require a credential
  minted at unlock, not ambient loopback trust; that leaves the dashboard login unchanged). F-03's
  per-source key and `Retry-After` fix belong here with sign-in lockout.
- **Phase 3** gains F-01 as its acceptance test: a mediated use works from a dashboard-started
  worker, or the UI states that it cannot and why. It also owns F-04 (reset, forced rotation) and
  F-05 (idle lock).
- **Phase 4** needs F-06's fixes and the Phase 3 state to show.
- **Phase 5** shrinks to provider keys and ChatGPT tokens (F-08), and adds F-07.
- **Phase 7** starts from an OS keychain path that already exists in four connectors.

Owner questions, to ask when the phase needs them, not now: the unattended-run policy (Phase 3), a
live-vendor credential and spend cap (Phase 6), and approval to raise the `cryptography` floor if
Argon2id is wanted (F-09, Phase 1 decides whether to propose it).
