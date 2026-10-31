# Current state: authentication, credential storage and agent access

Status: measured against the tree at commit `663828fd` on 2026-10-31, plus the uncommitted work
listed in §0. Every claim below names the file and function that supports it. Nothing here is
assumed secure because an interface exists.

---

## 0. Repository state at the start of the programme

- Branch: `main`, ahead of `origin/main` by 273 commits, behind by 1.
- Uncommitted work present and **left untouched** by this programme:
  `.ai/repo-map.generated.md`, `docs/implementation/connectors-integrations-plugins-skills/*`,
  `docs/research/2026-10-connectors-ecosystem/research.md`, `src/hutch/runtime/builtin.py`,
  `tests/test_mcp_plane.py`, `src/hutch/selfcheck_plan.py`, `tests/test_selfcheck_plan.py`.
- A prior session (`dc229b2b`) left a recovery checkpoint with zero messages; there was nothing to
  resume.
- No `docs/security/` tree existed before this programme.

## 1. Identity

Hutch does not have "users" in the SaaS sense. It has:

- **The local owner.** A single operator implied by possession of the machine. Authenticated by a
  local bearer token or a local auth cookie: `SecurityMiddleware._owner_authed`
  (`src/hutch/server/security.py`), compared with `hmac.compare_digest` against
  `auth_digest(auth_token)`.
- **Paired devices.** Phone/browser sessions created from a pairing code
  (`Store.exchange_pairing_code`, `src/hutch/store.py`), enrolled with a WebAuthn credential
  (`Store.finish_passkey_enrollment`), and afterwards authenticated per request by
  `Store.authenticate_session` via `SecurityMiddleware.device_auth`.
- **Bots.** `bots` table; each run is bound to a `bot_id`. There is no per-bot authentication —
  bots are configuration, not principals that present credentials.
- **Connectors / integrations.** Each has an account record and its own credential store (see §3).

There is no multi-user account model, no organisation/tenant layer, and no service identity. A
"workspace" exists as a singleton row (`workspace_settings`), not as a security boundary.

**Consequence for this programme:** a vault cannot be scoped to a user that does not exist. It
must be scoped to the owner, with explicit per-bot grants layered on top. Per-bot scoping is the
differentiator, and it is implementable today because every run already carries `bot_id`.

## 2. Authentication as it actually works

`src/hutch/server/security.py` (`SecurityMiddleware`) is a pure ASGI boundary that enforces, in
order:

1. **Host allow-listing and DNS-rebinding defence.** `_host_only`, `is_loopback_host`,
   `HUTCH_ALLOWED_HOSTS`. A loopback Host header from a non-loopback peer is refused with 421.
2. **Remote access gating.** `HUTCH_REMOTE_ENABLED`; remote requests must be HTTPS and must carry
   a database-backed session cookie (`SESSION_COOKIE`) resolved through `device_auth`. A local
   owner bearer token is never accepted remotely.
3. **Trusted-proxy handling.** `_trusted_forwarded_scope` requires an *exact* peer IP in
   `HUTCH_TRUSTED_PROXIES` (`/32` or `/128`; networks are rejected), exactly one
   `X-Forwarded-Host` and `X-Forwarded-Proto: https`, a public host already present in
   `HUTCH_ALLOWED_HOSTS`, and strips `Forwarded`/`X-Forwarded-*`/`X-Real-IP`/`X-Original-*` from
   untrusted peers. Tailscale Funnel ingress is refused outright.
4. **CSRF.** Unsafe methods must be same-origin by `Origin` or `Sec-Fetch-Site`; HTML form posts
   also carry a double-submit token checked by `check_csrf`. Passkey/pairing/session endpoints
   additionally require `X-Hutch-Request: 1` and an explicit `Origin`.
5. **Response headers.** CSP (`default-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`,
   `form-action 'self'`, `script-src 'self'`), `nosniff`, `DENY` framing, `no-referrer`,
   `Permissions-Policy`, and `no-store` for remote/paired requests.
6. **Body bounds.** Passkey verify bodies ≤ 260 KiB, computer-control bodies ≤ 16 KiB, uploads
   ≤ 26 MB, enforced by a counting receiver as well as `Content-Length`.
7. **OAuth callback hygiene.** Query strings for nine callback paths are moved off the ASGI scope
   so authorization codes do not reach the access log.

WebAuthn is real, server-verified: `src/hutch/server/passkeys.py` calls
`verify_registration_response` / `verify_authentication_response` with the configured RP ID and
origin, requires user presence and user verification, and rejects invalid RP/origin configuration
(`relying_party`). Synced passkeys are handled correctly: counters are only enforced for
single-device authenticators.

Sessions: enrollment 5 minutes, login ceremony 2 minutes, authenticated remote session 8 hours
absolute with a 30-minute idle window (`Store.finish_passkey_login`, and
`Store.authenticate_session` at `src/hutch/store.py:3112`). Revocation is a `revoked_at` update.

Passkey attempts and pairing attempts are rate-limited (`pairing_attempts`, `passkey_attempts`).

## 3. Where credentials live today

| Credential | Store | Protection at rest | Readable by an agent tool? |
|---|---|---|---|
| Model-provider API keys | Environment variable, or `<state>/keys/<connection>.key` (`ConnectionBook.key`, `src/hutch/connections.py`) | `0600` file, directory `0700`, created with `os.open(..., 0o600)` | **Yes if a shell tool can read the state dir** — the file is plaintext |
| OAuth refresh tokens (Google Calendar/Mail/Workspace, Outlook, Notion) | OS keyring via `secret-tool` on Linux, native Windows/macOS APIs via `src/hutch/platforms/credentials.py`; `SecretToolStore` in `src/hutch/google_calendar.py` | OS keyring, or native vault | Only through the integration code path; not a file on disk |
| ChatGPT (SIWS) tokens | Private JSON under `<state>/chatgpt/`, `0600`/`0700` (`chatgpt_auth._atomic_private_json`, `src/hutch/chatgpt_auth.py`) | File mode only, **plaintext** | Yes, via file access |
| Telegram channel bot tokens | OS keyring; reference stored as `credential_ref` in `channel_connections` (`src/hutch/channels/service.py`, `src/hutch/channels/telegram.py`) | OS keyring; DB holds a digest | No |
| Owner dashboard token | Derived digest in the ASGI middleware; the token itself is a CLI/server argument | Not persisted as plaintext in the DB | No |
| WebAuthn public keys | SQLite (`paired_credentials`) | Public material only | No value to an attacker |

Observations that matter:

- There is **no general-purpose vault**. Each integration invents its own store, and one of them
  (model API keys) is a plaintext file inside the same state directory agents are pointed at.
- There is **no uniform SecretRef**. References are ad-hoc: `credential_ref` (channel id),
  `account_id` (integration row), `api_key_env` (environment variable name).
- There is **no encryption at rest in the SQLite database**. Anything written there is readable by
  anyone who can read the file — including a backup, a sync client, or a process running as the
  same OS user.

## 4. Agent access to credentials

- Tools are dispatched through `src/hutch/runtime/builtin.py` after schema validation
  (`hutch.toolcalling.validate.validate_call`). Approval and policy live in `src/hutch/safety.py`
  and `src/hutch/approvals.py`.
- A run carries `bot_id`, and tool call records carry arguments redacted via
  `Tool.recorded_arguments`.
- Agents can run shell commands and read files (subject to approval mode). **Any plaintext
  credential stored in the state directory is therefore inside the agent's blast radius.** The
  existing design mitigates this by keeping OAuth tokens in the OS keyring, but model API keys and
  ChatGPT tokens are files.
- There is no notion of "this bot may use this credential". A bot with a shell tool and the right
  approval mode can reach everything the OS user can reach.

This is the central gap the vault must close, and it is worth stating precisely: **encryption at
rest does not remove a credential from the agent's blast radius while the vault is unlocked in the
same process.** What it does remove is the *standing* plaintext copy on disk, and what grants do is
make access a deliberate, auditable decision rather than an accident of file layout.

## 5. Existing authorization enforcement

- Dashboard routes are gated by the middleware above; there is no per-resource authorization layer
  because there is one owner.
- Bots are constrained by approval mode (`ask` / `auto`) and per-tool allow lists (`tool_allows`).
- Integrations are granted per bot in dedicated grant tables: `google_calendar_grants`,
  `outlook_calendar_grants`, `google_mail_grants`, `outlook_mail_grants`,
  `google_mail_send_grants`, `outlook_mail_send_grants`, `outlook_calendar_write_grants`,
  `workspace_task_fact_shares`, `memory_fact_shares`. These are genuine least-privilege grants and
  the right precedent for vault grants.
- There is **no grant model for model-provider keys**: a connection is available to any run that
  names it.

## 6. Persistence and migration mechanics (constraints on any new storage)

- One SQLite database (`config.db_path`), WAL, `synchronous=FULL`, `foreign_keys=ON`,
  `busy_timeout=30000` (`Store.__init__`, `src/hutch/store.py:2593`).
- Ordered migrations in `_MIGRATIONS`; `SCHEMA_VERSION = 1 + len(_MIGRATIONS)`. A pre-upgrade
  backup is written with SQLite's backup API before any migration
  (`Store._upgrade`, `src/hutch/store.py:2653`). Migrations run inside `BEGIN EXCLUSIVE` and roll
  back on any exception. Newer-than-current databases are refused rather than downgraded.
- Module-level schema helpers are the established pattern: `channels/persistence.migrate`,
  `personal_schema.migrate`, `mcp_schema.migrate`, `notification_schema.migrate`.
- Writes go through `Store._tx()` (`BEGIN IMMEDIATE`), which makes read-compare-write safe across
  processes. Domain books (`ChannelBook`, `ConnectionBook`) hold a reference to `store` and use it.

**Implication:** the vault is a new `migrate(db)` module appended to `_MIGRATIONS`, and a
`VaultBook` following the `ChannelBook` shape. Inventing a second database would violate both the
repository's law and its backup story.

## 7. What is missing

1. A general encrypted secret store with a documented key hierarchy.
2. A typed secret reference that can appear in configuration without carrying a value.
3. Per-bot, per-secret grants with a `use`/`reveal` distinction.
4. An append-only access audit for credentials.
5. Separation between *vault unlock material* and *dashboard sign-in material*.
6. A recovery path that does not depend on the running application.
7. A rule preventing a secret value from entering model context, transcripts, tool results or the
   event log.
8. Any documented statement of what is protected against which attacker.

## 8. Existing weaknesses worth naming

- **Plaintext model keys in the state directory.** `ConnectionBook.key` reads a `0600` file. That
  is correct against *other OS users*, and worthless against the same user, a backup, or an agent
  with a shell.
- **Plaintext ChatGPT token file.** Same class.
- **Integration secrets depend on a keyring being present.** `SecretToolStore.available()` returns
  false on a headless Linux host, and the integration refuses to connect rather than falling back
  to a file — correct, but it means headless self-hosting has no secret store at all today.
- **No audit of credential use.** OAuth refreshes are not recorded beyond error handling.
- **No reauthentication for sensitive operations.** The owner cookie grants everything the owner
  can do, for as long as it is valid.
- **Approval mode is the only boundary between a bot and the filesystem.** There is no
  credential-specific boundary.

## 9. Compatibility constraints this programme must respect

- Existing integrations must keep working; the vault is additive, not a rewrite of
  `google_calendar`, `outlook_calendar`, `notion`, `channels` or `connections`.
- No secret may be added to the event log, transcript, run document or tool record.
- The database must remain openable and upgradable by an older Hutch only in the sense the
  repository already enforces: a newer schema is refused, never silently downgraded.
- Linux is the primary dev OS; keyring availability cannot be assumed.
- The dashboard is server-rendered HTML plus a vanilla JS bundle; no framework or component library
  may be introduced.

## 10. Files this programme will touch

New (all delivered):

- `src/hutch/vault/crypto.py` — KDF, AEAD, wrapping, recovery-key encoding.
- `src/hutch/vault/refs.py` — `SecretRef`, categories, permissions.
- `src/hutch/vault/schema.py` — `migrate(db)` tables, indexes, append-only triggers.
- `src/hutch/vault/vault.py` — `VaultBook` lifecycle, grants, audit; `vault_for(store)` registry.
- `src/hutch/vault/destinations.py` — canonical origins and the per-secret binding.
- `src/hutch/vault/egress.py` — the mediator that presents a value and returns only a response.
- `src/hutch/safehttp.py` — one-hop request: pinned address, no redirects, validated headers.
- `src/hutch/tools/vault_http.py` — `vault_http_request`, the tool a bot calls.
- `src/hutch/server/vault_api.py` — owner-only HTTP routes.

Changed:

- `src/hutch/store.py` — one migration entry (`_migrate_82` → `vault.schema.migrate`).
- `src/hutch/tools/__init__.py`, `src/hutch/integrations/catalog.py`,
  `src/hutch/skill_requirements.py`, `src/hutch/server/static/app.js` — tool registration and the
  Strict Offline withholding list.

Deliberately not changed in this checkpoint: `security.py`, `passkeys.py`, `connections.py`,
`google_calendar.py`, the dashboard routes and templates. Those are later checkpoints and are
listed in `implementation-plan.md`.
