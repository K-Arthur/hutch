# Phases and checkpoints

Each phase: research, design note, small commits on `main`, real-setup validation (browser with a
virtual WebAuthn authenticator where UI or sign-in is touched), secret-leak sweep, visual
validation if UI, review, docs. Each task touches at most three source files plus one seam. A phase
is done only when its exit checks pass and `02-PROGRESS.md` says so.

## Phase 0 - Diagnose (no feature code)

- Baseline: `npm run check:agent`; `npm run test:agent -- tests/test_vault_*.py
  tests/test_native_credentials.py tests/test_migration.py`. Record pass counts and the pre-existing
  failures (progress.md notes an agent-map failure and a stale-emoji-file failure; confirm whether
  they still occur and whose they are).
- Verify every claim in `progress.md` "Still not done" and `security-limitations.md` against HEAD
  with `rg` and a run, not by trust. Produce
  `docs/research/2026-11-vault-signin/00-GAP-AUDIT.md`: per item, status today, evidence (file:line
  or command output), and what is missing.
- Inventory every place a credential is stored or read (list in master prompt). For each: file,
  function, storage form (plaintext file, SQLite column, keyring), who can read it, and whether it
  can reach logs. Do not open `.env*`, `*.db*`, `.state/`; inspect code and schema only.
- Capture current Settings, sign-in, device pairing, and passkey pages with Playwright at four
  widths, light and dark. Log defects.
- Check the `ced92681` defect precondition (clean tree, no other session committing); repair or
  record why not.
- Exit: audit committed; ordered backlog and owner questions batched in `02-PROGRESS.md`.

## Phase 1 - Research (documents only)

- Execute `04-RESEARCH-PLAN.md` fully: standards, the owner's reference pages, comparable
  products, and failure and complaint mining. Output into `docs/research/2026-11-vault-signin/`
  (`01-SOURCES.md`, `02-FAILURES-AND-COMPLAINTS.md`, `03-LESSONS-AND-DECISIONS.md`).
- Each lesson becomes a requirement with a test idea in `03-LESSONS-AND-DECISIONS.md`. Reject with
  reasons where Hutch's single-owner, local-first shape makes a feature wrong.
- Exit: every later phase can cite requirement ids from this document.

## Phase 2 - Step-up and sign-in hardening

- New module(s) for step-up (no growth in `security.py` beyond wiring): a single-purpose,
  time-boxed, session-bound assertion; WebAuthn UV preferred, passphrase fallback; audit row.
- Passkey management API: list, rename, remove with last-passkey guard. Session list and revoke.
  Lockout-DoS protection and loopback owner exemption policy; ADR if a boundary moves.
- RP ID and origin mismatch diagnostics; `doctor.py` check.
- Seams: `server/passkeys.py`, new `server/stepup.py`, `vault/access.py` (reveal gate).
- Exit: tests for every refusal (expired, wrong purpose, replayed, other session, non-UV when UV
  required); real browser run with virtual authenticator toggling UV on and off; replay of a
  captured assertion refused.

## Phase 3 - Vault lifecycle: auto-lock, unattended policy, backup states

- Idle auto-lock, lock on session end, typed in-flight failure. Decide unattended/delegated policy
  (ADR); implement fail-closed visibility first, lease only if the decision is to ship it.
- Restored-without-keys and foreign-vault states handled with clear errors. Rotation of DEK and KDF
  parameters; encrypted export/import.
- Seams: `vault/lifecycle.py` (286 lines, split before adding), `vault/core.py`, `runtime/`
  hand-off point for child runs (locate exact function first).
- Exit: kill the server mid-rotation and mid-export on a real database and prove no data loss;
  schedule and channel run against a locked vault shows a visible state, not a silent failure.

## Phase 4 - Vault UI

- New `src/hutch/server/pages_vault.py` (or `vault_pages.py`), `static/vault.js` split into small
  modules (list, create, unlock, bind, grant, audit, reveal), `app/src/` CSS. Wire navigation and
  global lock indicator through new modules, not `app.js`.
- Every state in the master prompt's UI deliverable. Real data created through the UI in the real
  browser, never seeded.
- Exit: Playwright flows (create, add, bind, grant, use through a real agent turn against a local
  HTTP service the test starts, reveal with step-up, lock, wrong passphrase, throttle, reset);
  screenshots at four widths and both themes; keyboard-only; secret-leak sweep including the DOM
  and HAR; focused e2e for touched pages.

## Phase 5 - Credential migration

- Order: model keys, ChatGPT tokens, connector tokens, channel tokens. Per item: copy, verify by
  read-back decryption, switch reader, owner-confirmed removal of the old copy, rollback.
- Ambient env key labelling and no silent preference. Crash-mid-migration tests on a real database
  copy. Migration UI inside the vault page (progress, per-item result, nothing hidden).
- Seams: `providers/accounts.py`, `chatgpt_auth.py` or `token_cache.py`, new
  `vault/migrate_credentials.py` (split per credential family).
- Exit: an existing install upgrades with all providers still working, verified with the real
  engine and a local provider; old copy gone only after confirmation; no value in any sink.

## Phase 6 - Mediation breadth and live check

- Add credential shapes one at a time (query string, signed body, OAuth refresh) with bindings and
  tests; connector mediation for the highest-risk connector; document reveal-only for the rest.
- Live vendor call with an owner-provisioned credential and a stated cap, or record
  "blocked: no credential" with the exact input needed.
- Seams: `vault/egress.py` (172 lines, split before adding a shape), `safehttp.py`,
  `tools/vault_http.py` (changed schema needs contract tests).
- Exit: redirect, DNS rebinding, header injection, echo-transformed response, oversized response,
  and slow-loris cases tested against a real local server; limitation 3 updated honestly.

## Phase 7 - External provider (at most one)

- Choose by research (likely 1Password CLI or OS keychain; ask before adding any dependency).
  References not copies, bounded timeouts, no secret in argv, clear unavailable and locked states,
  offline behavior, UI for connecting and testing.
- Exit: real provider CLI run on this machine if installed, otherwise "blocked: not installed"
  with exact instructions; unsupported providers remain documented only.

## Phase 8 - Website and docs

- Website: new security section or page from `website/src/input.css` and `website/index.html`
  sources (check `docs/marketing-site.md` and `scripts/` for the site checks), `llms.txt`,
  `sitemap.xml`. Only verified claims, each linking to its limits. Real screenshots from the real
  dashboard, not mockups. Responsive, light and dark, four widths, accessibility pass, Lighthouse
  or equivalent budget already used by the site, zero console errors.
- Docs: complete the doc set per master prompt gate 7; edit `security-limitations.md` for each limit
  closed, add new limits introduced. Update `docs/safety.md` and the user-facing guide.
- Exit: every claim on the site maps to a test or dated check listed in
  `testing-and-validation.md`.

## Phase 9 - Final review and merge

- Whole-initiative review of the diff from the Phase 0 commit to HEAD: god functions, leaks,
  enumeration, TOCTOU, status inflation, frozen-file growth, dead code, docs-versus-code drift.
- Independent read-only reviewer subagent on egress, step-up, migration; record findings and fixes.
- Full fast suite once (`uv run --frozen --no-sync pytest -q --no-header --tb=line --ignore=tests/e2e`),
  `npm run check:agent`, `npm run audit:context`, emoji audit, focused e2e, leak sweep script.
- Confirm merge state, worktrees removed only if merged, `02-PROGRESS.md` final. Do not push.

