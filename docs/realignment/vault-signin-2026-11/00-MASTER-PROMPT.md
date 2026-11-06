# Master prompt: vault and secure sign-in, pass 3 (2026-11)

Paste the "Launch prompt" block at the bottom into a fresh session. Everything above it is the
contract the agent reads. Work sequentially through `01-PHASES.md`; record state in
`02-PROGRESS.md`; consult `03-EDGE-CASES.md` at every design step and `04-RESEARCH-PLAN.md` before
each phase's design. One phase per session (AGENTS.md: fresh session per task, under about 120K
tokens).

## Goal

Finish the vault and secure sign-in programme so that the claim "a bot uses a credential it cannot
read, and only the owner can open the vault" is true, usable from the dashboard, honestly worded,
and proven against the real stack. Passes 1 and 2 built the engine (crypto, grants, bindings,
audit, one mediated egress shape, owner-only API). They did not build any user-facing surface, did
not move any existing plaintext credential into the vault, did not add step-up before a reveal, and
did not touch the website. Those are this pass.

## Starting state (verified 2026-11-05; recheck against HEAD before relying)

Do not rebuild any of this. Diagnose against it.

- Programme docs, 17 files: `docs/security/vault-and-authentication/`. Read in this order and
  only as needed: `progress.md` ("Still not done, in priority order", lines ~83-105),
  `security-limitations.md` (14 numbered limitations; each one you close must be edited, not
  deleted silently), `implementation-plan.md` (checkpoints 4-8), `current-state.md`,
  `threat-model.md`, `decisions.md`, then `research.md` sections 4-6 (failure analysis, lessons
  adopted and rejected). Do not re-do that research; extend it.
- Vault package `src/hutch/vault/` (13 files, 2352 lines): `crypto.py` (scrypt KEK, HKDF recovery
  KEK, DEK wrap; Argon2id deliberately not used, decision D1), `core.py`, `vault.py`, `lifecycle.py`
  (init/unlock/lock/reset/recovery), `secrets.py`, `refs.py` (`SecretRef`, `PROVIDERS` contains only
  `hutch`), `access.py` (grants, `resolve_for_use`), `destinations.py` (origin bindings),
  `egress.py` (`mediate_http`), `audit.py`, `schema.py`, `model.py`.
- HTTP: `src/hutch/server/vault_api.py` (308 lines, owner-only). Tool:
  `src/hutch/tools/vault_http.py` (`vault_http_request`). Safe request:
  `src/hutch/safehttp.py` (`safe_request`).
- Sign-in: `src/hutch/server/security.py` (`SecurityMiddleware`, 512 lines, near the cap; check
  `.file-size-baseline.json` before touching), `src/hutch/server/passkeys.py` (WebAuthn
  registration/authentication via `verify_*_response`), device pairing and sessions through
  `device_auth` (locate with `rg`). Sessions: 8 h absolute, 30 min idle; enrollment 5 min; login
  ceremony 2 min.
- Plaintext credential stores that the vault does NOT yet hold (confirm each with `rg`; do not read
  `.env*`, `*.db*`, `.state/`): model/provider keys (`src/hutch/providers/accounts.py`,
  `connections.py`, `config.py`), ChatGPT tokens (`src/hutch/chatgpt_auth.py`,
  `src/hutch/token_cache.py`), Google/Outlook/Notion connector credentials
  (`src/hutch/google_oauth_config.py`, `oauth_apps.py`, `integrations/notion*.py`,
  `integrations/mcp/persistence.py`), channel tokens (`src/hutch/channels/`).
- Tests that already exist and must stay green: `tests/test_vault_*.py` (crypto, integrity,
  secrets, refs, access, lifecycle, api, egress, http_tool, agent_turn, migration),
  `tests/test_native_credentials.py`, `tests/support/vault_fixtures.py`.
- Frontend: nothing. `app.js` mentions the `vault_http_request` tool label only. `app.js` is
  frozen: new UI goes in new modules (`static/vault.js`, a `pages_vault.py`, `app/src/` CSS).
- Website: no vault or sign-in claim exists and none may be added until the claim is true and
  dated-verified. Policy in `docs/marketing-site.md`.
- Known carried defect: commit `ced92681` holds ~23 lines of another session's work in `app.py`.
  Repair only if the tree is clean and no other session is committing (procedure in
  `progress.md`); otherwise leave it and say so. Never stash or clean another session's work.
- The repo has untracked `.commandcode/` and sibling prompt packs under `docs/realignment/`. They
  are not yours.

## Non-negotiable rules

1. No god functions or god files. Hard cap 400 lines per new source file. A function does one
   thing, aim for 40 lines, hard stop at 60. No function with more than 4 branches of
   case-specific `if/elif`; use a table or per-case adapter. Never extend a file listed in
   `.file-size-baseline.json`; split first (`.ai/skills/split-god-file.md`). `security.py` is 512
   lines: new sign-in logic goes in new modules and `security.py` only gains the wiring.
2. Real setup, not fixtures, and not demo data. Prove behavior against the real stack: a real
   FastAPI server on a real port, real SQLite on a copy of a persisted state with real migrations,
   real Chromium via Playwright, and for WebAuthn a real virtual authenticator (Chromium CDP
   `WebAuthn.addVirtualAuthenticator`, with `isUserVerified` toggled to prove both the UV and
   non-UV paths). Mocks are allowed only to unit-test pure parsing and to inject failures a real
   server cannot produce on demand. A mock never upgrades a claim. A recorded fixture is never live
   evidence. No "demo vault", no seeded sample secrets shown in a page, no preview pages in
   `static/`. Use values the test itself generates and a real local HTTP service you start
   yourself as the egress target for local proof.
3. Live vendor check (item 7 of "Still not done") needs an owner-provisioned credential. Never
   create accounts, never spend money, never read credentials from other tools' files. If none is
   provided, record "blocked: no credential" with the exact missing input and keep the claim at
   implemented-unverified. Do not fake it with a local server and call it live.
4. Preserve the local-first, explicit-approval model. A secret value never appears in an API
   response (outside the single reveal route), log, event, run, message, `tool_actions`, DOM, page
   source, screenshot, commit, or the process arguments. Never add a tool, permission, or data flow
   as a side effect. Redact through `Tool.recorded_arguments`.
5. Security claims are honest and dated. Each claim in UI, docs and website maps to a named test or
   a dated manual check. Wording rules: say "encrypted at rest", never "unhackable" or "military
   grade"; say "the assistant cannot read it" only for the mediated path and state the limits next
   to it (`security-limitations.md` 1-3). Never claim sandboxing.
6. Do not weaken any existing boundary to make a feature easier: no secret in query strings of
   Hutch's own URLs, no bearer fallback for remote requests, no relaxed CSP, no loosened CSRF or
   Origin checks, no `unsafe-inline`. New endpoints follow the `X-Hutch-Request: 1` plus explicit
   `Origin` rule that passkey and session endpoints already use.
7. Contract discipline: any new or changed tool has canonical JSON Schema in `Tool.parameters`,
   catalogue entry in `tools/__init__.py`, contract tests (valid accepted, invalid refused before
   dispatch), and passes `npm run check:agent`. Reuse `toolcalling/`.
8. Persisted state: pydantic models plus an ordered migration in `store.py` with a
   `tests/fixtures/` compatibility input and `test_migration.py` coverage; a migration must be its
   own ordered step (the pass-2 lesson in `progress.md`). Test by putting a real database back to the
   previous version. Timestamps via `models.iso`/`models.utcnow`. Every credential migration is
   copy, verify by read-back decryption, switch readers, and only then offer deletion of the old
   copy, with a rollback path and a crash-mid-way test.
9. Use `main`. One focused change per commit, explicit paths, `git add -p` for shared files
   (stage hunks, not whole files; the pass-1 defect came from `git add app.py`), concise
   imperative messages, no AI-attribution trailer. Use a worktree only for a risky spike and merge
   it back within the same phase. Never push, tag, publish, deploy, add a dependency (ask first), or
   touch another session's uncommitted work.
10. No emoji in source, docs or UI. Edit `app/src/` and `website/src/`, never generated CSS; run
    `npm run build:css --silent` afterward. Follow `docs/design-system.md` and the `impeccable`
    skill for UI work.
11. Surgical context. Read line ranges. Never read lockfiles, CHANGELOG, generated CSS, evidence
    artifacts, `.worktrees/`, `node_modules/`, `.venv/`. Do not "review the codebase".

## Research requirements (mandatory, before design in each phase)

Details and the reading list are in `04-RESEARCH-PLAN.md`. Summary: use live web search and fetch
the owner's reference pages (list at the bottom of that file). Record each source with URL, date
accessed, and what it changed, in `docs/research/2026-11-vault-signin/`, extending the existing
`research.md` rather than duplicating it.

Research must include failure and complaint mining, not only best practice: what other products
got wrong with secrets, vaults, agent credential access and sign-in, and what users complained
about. Classify each as fixable-in-Hutch, mitigable, or vendor-side, and give each fixable one a
test idea. Examples to look for, not an exhaustive list: secrets leaked into prompts, logs,
transcripts, shell history, crash reports and screenshots; agents reading `.env` files or the
vault through a shell; prompt injection exfiltrating a key through an allowed tool; lock-out with
no recovery and data loss on forgotten passphrase; recovery key shown once and lost; vault that
re-locks mid-task and silently fails; auto-lock that never fires; passkey sync and lost-device
loops; WebAuthn failing on WSL, remote, behind a proxy, wrong RP ID after a hostname change;
session cookie not Secure behind a proxy; unlock-throttle used to lock the real owner out;
password manager autofill fighting the unlock field; clipboard retaining secrets; migrations that
corrupt or double-store credentials; keychain integrations that prompt endlessly or break on
headless Linux; external-provider CLIs hanging with no timeout.

## Required design deliverables (gaps the owner did not list; treat each as in scope)

If one cannot be solved now, log it as deferred with the reason and what would unblock it.

- Vault UI under Settings (or a dedicated page) with: first-run create (passphrase strength meter
  that does not send the passphrase anywhere, recovery key shown once with a verified
  "I saved it" step that re-asks for part of it), unlock/lock state visible globally, secret list
  (name, category, last used, bound destination, grants; never values), add/rotate/delete, bind
  destination with the canonical origin shown back to the user, per-bot grants with approval
  requirement, audit viewer with filters, reveal with step-up and auto-hide, copy with clipboard
  clear, change passphrase, recovery-key use, reset with an explicit data-loss confirmation.
  Every state: empty, locked, unlocking, throttled, wrong passphrase (no enumeration), error,
  offline/Strict Offline, loading. Keyboard-only, screen-reader labels, focus management in
  dialogs, `autocomplete` attributes correct for password managers, no value in the DOM until a
  reveal and none after hide.
- Step-up (reauthentication) before reveal, export, passphrase change, passkey removal, session
  revocation of others, and reset: a fresh WebAuthn assertion with user verification when a passkey
  exists, otherwise the vault passphrase. Time-boxed single-purpose grant bound to the session, not
  reusable across actions, recorded in the audit.
- Sign-in hardening: passkey list with rename and last-used, refusal to remove the last passkey
  unless another recovery path is confirmed, session list with device name and last seen, revoke
  one or all, lockout-DoS protection so an attacker cannot lock the owner out of unlock or sign-in
  (throttle keyed so the legitimate local owner on loopback is not penalised by remote attempts),
  clear failure messages for RP ID / origin mismatch with the exact hostname expected, a doctor
  check (`src/hutch/doctor.py`) for remote sign-in misconfiguration.
- Unattended and delegated runs: decide and implement, with an ADR, how scheduled runs, channel
  replies and process-executed runs get vault use when the owner is away. Options to weigh: refuse
  (fail closed, say so in the UI), or an explicit time-boxed, scope-limited, revocable "unattended
  lease" the owner grants while unlocked that holds only the grants it names. Never persist the DEK
  or passphrase to make this work. Surface the state ("this schedule needs the vault; vault is
  locked") instead of a silent failure.
- Auto-lock: idle timeout, lock on session end, lock on server restart; visible countdown; a run in
  flight when the vault locks fails with a typed, explained error, never a partial credential.
- Credential migration: model keys, ChatGPT tokens, connector tokens, channel tokens, in that
  order of risk. Per item: copy, verify, switch readers, offer removal of the old copy. Ambient env
  keys are detected and labelled, never silently preferred. Backup and restore: a database restored
  without its vault keys, or vault from another machine, must give a clear state, not a crash.
- Connector mediation and credential shapes beyond one header (query-string credential, signed
  body, OAuth refresh) one shape at a time, each with its own binding and test. Anything that cannot
  be mediated safely is documented as "reveal only".
- External providers (1Password, Bitwarden, HashiCorp Vault, OS keychain): only through official
  CLIs or documented APIs, with bounded timeouts, no secret in argv or env of the child where the
  CLI allows stdin, references not copies, and a clear "provider unavailable / locked" state. Adding
  any dependency requires asking first. Ship at most one provider this pass; the rest stay
  documented.
- Operations: export/import encrypted vault, rotation of the DEK and KDF parameters, audit
  retention, incident runbook update, `hutch doctor` coverage, desktop (Tauri) parity, Strict
  Offline behavior, i18n of security wording.
- Frontend and website: see phase 8. The marketing site gains a security page or section only for
  claims verified in earlier phases, each linking to the doc that states its limits.

## Validation and review gates

Per phase, in order, reporting exact commands and results:

1. Focused tests: `npm run test:agent -- tests/test_<x>.py` for every touched behavior; add tests
   that fail before the change. Existing vault suites stay green:
   `npm run test:agent -- tests/test_vault_*.py tests/test_native_credentials.py tests/test_migration.py`.
2. `npm run check:agent`; `npm run audit:context` when files grew. Run `scripts/audit_emoji.py` on
   the files you added.
3. Real-setup run: start the real server, exercise the route end to end in a real browser with a
   virtual WebAuthn authenticator, and record date, route, what was and was not exercised in
   `docs/security/vault-and-authentication/testing-and-validation.md`.
4. Secret-leak sweep after every phase that touches values: run the real flow with a
   generated canary value, then search the real database (a copy), event log, server stdout and
   stderr, browser DOM and network log (Playwright HAR), localStorage/sessionStorage, process
   argv, and crash output for the canary. Zero hits except the encrypted blob and the reveal
   response. Add the sweep as a reusable script under `scripts/`, not a one-off.
5. Visual validation for any UI or website change: Playwright screenshots at 360, 768, 1280 and
   1920 px, light and dark, every state listed above, keyboard-only traversal, console-error check;
   follow the `docs/realignment/capture_*.py` pattern; look at the images and record defects found
   and fixed; zero console errors, zero horizontal overflow; screenshots must not contain a secret
   value other than the canary in the one deliberate reveal shot. Run focused `tests/e2e/` for
   touched pages only.
6. Code review: re-read the phase's full diff as a skeptical reviewer. Hunt for: god functions,
   secret leakage, timing differences between "no such secret" and "denied", enumeration, TOCTOU
   between grant check and use, missing audit rows, silent fallbacks, status inflation, dead code,
   frozen-file growth. Fix, then record findings. Use a fresh reviewer subagent with read-only
   scope on the egress and step-up code at the end of phase 9; the author must not be the only
   reviewer (`progress.md` item 8).
7. Docs in the same commit series: edit the vault doc set (`vault.md`, `authentication.md`,
   `architecture.md`, `security-limitations.md`, `migration.md`, `recovery-and-backup.md`,
   `operations-and-incident-response.md`, `testing-and-validation.md`, `progress.md`),
   `docs/safety.md` where affected, an ADR (next number after 0027) per boundary-changing decision,
   and `docs/agent-map` if the generated-map check requires it (regenerate only when no other
   session has staged changes to it).
8. Merge state: everything on `main`, tree clean except others' work.

## Stop conditions

Ask the owner (once, batched) only for: a credential for a live vendor check, adding a dependency,
a product decision that is irreversible (for example unattended-run policy), and pushing or
publishing. Otherwise decide, log the decision and reason in `02-PROGRESS.md`, and continue. If
blocked, state exactly what blocks and stop that item. Never simulate success.

## Launch prompt (paste into a fresh session)

```
Read, in this order and nothing else first: @AGENTS.md,
@docs/realignment/vault-signin-2026-11/00-MASTER-PROMPT.md,
@docs/realignment/vault-signin-2026-11/01-PHASES.md,
@docs/realignment/vault-signin-2026-11/02-PROGRESS.md.
Then open 03-EDGE-CASES.md and 04-RESEARCH-PLAN.md.

Resume at the first phase in 02-PROGRESS.md not marked done. Do only that phase in this session:
research first (live web, plus failure and complaint mining, recorded under
docs/research/2026-11-vault-signin/), then a short written design naming the exact files and
functions you will touch (max 3 source files plus one seam per task; split the phase into tasks),
then implement in small commits on main, then run the validation and review gates from the master
prompt against the real stack including a real browser with a virtual WebAuthn authenticator and
the secret-leak sweep, then update docs and, where the phase says so, the marketing site. No god
functions, no demo data, no fixture-only validation, no status or security-claim inflation, no
credentials or spending without asking. Update 02-PROGRESS.md at each checkpoint (committed,
verified live, blocked, decisions, review findings) and finish by stating the next phase. Do not
stop at a task boundary inside the phase.
```

