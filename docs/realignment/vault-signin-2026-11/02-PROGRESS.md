# Progress: vault and secure sign-in, pass 3 (2026-11)

Update at every checkpoint. Keep entries short and factual.

## Phase status

| Phase | Status | Last commit | Live-verified | Blocked on |
|---|---|---|---|---|
| 0 Diagnose | **done 2026-11-06** | `378d7e0b` (audit), `36600792` (test fix) | yes: real server, real Chromium with a virtual authenticator; scope and gaps in `00-GAP-AUDIT.md` sections 7 and 8 | |
| 1 Research | not started (next) | | | |
| 2 Step-up and sign-in | not started | | | |
| 3 Lifecycle, unattended, backup | not started | | | |
| 4 Vault UI | not started | | | |
| 5 Credential migration | not started | | | |
| 6 Mediation breadth, live check | not started | | | |
| 7 External provider | not started | | | |
| 8 Website and docs | not started | | | |
| 9 Final review and merge | not started | | | |

## Owner inputs needed (batch, ask once, when the phase needs it)

- Credential and spend cap for one live vendor call (phase 6), or confirm "blocked".
- Unattended-run policy: fail closed only, or time-boxed lease (phase 3). Phase 0 shows this is not
  an edge case: every shipped launch path runs bots as worker processes with a locked vault.
- Dependency approvals: raising the `cryptography` floor from 42 to one that has Argon2id (it
  derived a key here on 50.0.2); phase 1 decides whether to propose it. A WebAuthn test helper is
  **not** needed: Chromium's CDP virtual authenticator works with the installed Playwright.
- Which external provider to ship first (phase 7). An OS credential store path already exists in
  four connectors (`SecretToolStore`), which changes the question.

## Decisions log

| Date | Decision | Reason |
|---|---|---|
| 2026-11-06 | Phase 0 did not run the live-web research plan | `01-PHASES.md` makes it Phase 1; Phase 0 is diagnosis against HEAD. The launch prompt's "research first" applies from Phase 1 |
| 2026-11-06 | Gate 5 "light and dark" is read as dark at 360, 768, 1280, 1920 plus one emulated-light pass | The dashboard ships one fixed dark theme by decision (`docs/design-system.md:351`); a light pass proves nothing changes |
| 2026-11-06 | `ced92681` not repaired | Tree not clean (another session's staged and modified files) and that session committed at least four times during the phase |
| 2026-11-06 | Corrected `security-limitations.md` entries 2, 3, 7, 8, 11, 13 and added 15 now, not later | The audit proved them wrong or understated; leaving them for a later phase would keep a false security statement in the repo |
| 2026-11-06 | Reproduction tools live in `docs/research/2026-11-vault-signin/tools/`, not `scripts/` | They reproduce audit claims; the reusable leak sweep (gate 4) is a `scripts/` deliverable of the phase that first changes how a value is handled |
| 2026-11-06 | Committed the other four prompt-pack files with this ledger | They were untracked and are the contract for this pass; sibling packs under `docs/realignment/` were not touched |
| 2026-11-06 | Phase 2 starts with the F-11 ADR and an owner credential for vault routes | No principal has both a passkey and vault access, and a default serve has no owner credential (audit F-11, F-02) |

## Review findings log

Phase 0 self-review only. No independent reviewer yet (Phase 9, `progress.md` item 8).

| Date | Phase | Finding | Fix |
|---|---|---|---|
| 2026-11-06 | 0 | First live probe read headers case-sensitively and would have reported a missing `Cache-Control` on reveal that does exist | Probe fixed, re-run; `tools/probe_vault_live.py` is the corrected one |
| 2026-11-06 | 0 | Assumed paired-device management was CLI only; the dashboard calls `api("/v1/devices")` without the `/api` prefix, so a search for the full path missed it | Read `app.js:9773-10016`; audit F-06 corrected before commit |
| 2026-11-06 | 0 | Capture script saved `/connectors` as `apps-and-ai` and `/connections` as `connections` | Labels fixed and the 30 views recaptured before commit (`378d7e0b`) |
| 2026-11-06 | 0 | A `pkill -f` matched its own shell and killed a background test run | Re-ran the baseline; used PIDs afterwards |
| 2026-11-06 | 0 | Baseline test red: `test_vault_migration.py` assumed the destinations migration was last | `36600792` |

## Phase 0 outcome (for the next session)

Read `docs/research/2026-11-vault-signin/00-GAP-AUDIT.md` first. Fourteen findings, F-01 to F-14. The
ones that change the plan:

- **F-01** the headline claim does not work in any shipped launch path (workers have a locked vault).
- **F-02** a default `hutch serve` has no owner credential; reveal needed none (verified live).
- **F-03** any local caller can lock the owner out of unlock; no `Retry-After` reaches the client
  (`pages.py:162-169` drops it).
- **F-04** no vault reset exists; recovery-key unlock forces no rotation.
- **F-11** no principal has both a passkey and vault access; a design decision for Phase 2.
- **F-08** connector tokens are already in the OS credential store; Phase 5 is provider keys and
  ChatGPT tokens only.

Baseline: `npm run check:agent` 4/4; vault, native-credentials and migration suites 235 passed,
1 skipped (native Windows/macOS only), 0 failed after the test fix. `scripts/audit_emoji.py` fails on
8 hits in the git-ignored `.codewhale/state/subagents.v1.json`, not this programme's; files this
programme adds were checked by scanning a root that contains only them (clean).

## Ordered backlog

1. **Phase 1** research: `04-RESEARCH-PLAN.md` in full. Also re-test D1 with F-09, and decide on
   WebAuthn PRF with evidence.
2. **Phase 2**: F-11 ADR; owner credential for vault routes (F-02); per-source throttle and the
   `Retry-After` fix (F-03); step-up; passkey list, rename and last-credential guard, device date fix
   (F-06); server-side UV test with a hand-signed assertion (F-13); `doctor.py` checks (F-10).
3. **Phase 3**: F-01 acceptance (mediated use from a dashboard-started worker, or a visible refusal);
   F-04 reset and forced rotation; F-05 idle lock; rotation and export.
4. **Phase 4**: vault UI, with the Phase 3 states and F-06 fixes.
5. **Phase 5**: provider keys and ChatGPT tokens only; F-07 ambient-key labelling.
6. **Phases 6 to 9** as written.

## Open items and deferred

| Item | Reason | What would unblock |
|---|---|---|
| Repair `ced92681` | Tree not clean, another session committing | A clean tree and no other committer |
| A full dashboard run through a real provider, to confirm F-01 end to end | No provider configured for this phase; F-01 is proven by the two-process probe and the code | A local provider in Phase 3 |
| Server-side user-verification refusal test | Chromium's virtual authenticator cannot produce a non-UV assertion for a `required` request | A hand-signed assertion in Phase 2 |
| Individual inspection of the 768, 1920 and light captures | Measured (0 errors, 0 overflow) but not each viewed | Phase 4 visual validation |
| Keyboard, screen-reader and 200 percent zoom on the existing pages | Not exercised | Phase 4 |
| Whether a bot's tools can reach the dashboard port (F-02 reach) | Depends on per-tool confinement; not tested | Phase 2 design test |
| Throttle 300 s ceiling, not run | Computed from the code | Phase 2 test |
| Secret-leak sweep script | No phase has changed value handling yet | First phase that does |
| Desktop (Tauri) webview passkey behavior | Not exercised | Phase 2 or 4 |

## How to reproduce Phase 0 evidence

Real server on a throwaway `HUTCH_STATE_DIR`; tools in `docs/research/2026-11-vault-signin/tools/`:
`probe_vault_live.py PORT STATE_DIR`, `tls_proxy.py` plus `webauthn_baseline.py UP PROXY OUT` (needs
`HUTCH_TRUSTED_PROXIES`, `HUTCH_ALLOWED_HOSTS`, `HUTCH_WEBAUTHN_RP_ID`, `HUTCH_WEBAUTHN_ORIGIN` and
`--allow-remote`; see audit section 6), and `docs/realignment/capture_vault_signin_baseline.py ORIGIN OUT`.
