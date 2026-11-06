# Progress: vault and secure sign-in, pass 3 (2026-11)

Update at every checkpoint. Keep entries short and factual.

## Phase status

| Phase | Status | Last commit | Live-verified | Blocked on |
|---|---|---|---|---|
| 0 Diagnose | **done 2026-11-06** | `378d7e0b` (audit), `36600792` (test fix) | yes: real server, real Chromium with a virtual authenticator; scope and gaps in `00-GAP-AUDIT.md` sections 7 and 8 | |
| 1 Research | **done 2026-11-06** | `07336d83` | partly: two local experiments in real Chromium 153 with a virtual authenticator (WebAuthn on `localhost`, PRF) and a KDF timing run; everything else is documents. Gaps in `03-LESSONS-AND-DECISIONS.md` section 6 | |
| 2 Step-up and sign-in | not started (next) | | | |
| 3 Lifecycle, unattended, backup | not started | | | |
| 4 Vault UI | not started | | | |
| 5 Credential migration | not started | | | |
| 6 Mediation breadth, live check | not started | | | |
| 7 External provider | not started | | | |
| 8 Website and docs | not started | | | |
| 9 Final review and merge | not started | | | |

## Owner inputs needed (batch, ask once, when the phase needs it)

Phase 1 settled these into five questions; full wording and recommendations are in
`docs/research/2026-11-vault-signin/03-LESSONS-AND-DECISIONS.md` section 5. None blocks Phase 2.

| Id | Question | Needed by | Recommendation |
|---|---|---|---|
| Q1 | Unattended runs: fail closed only, or a time-boxed, scope-limited, revocable lease. Phase 0 shows this is not an edge case: every shipped launch path runs bots as worker processes with a locked vault | Phase 3 | Fail closed with a visible state first; lease only if wanted, with an ADR |
| Q2 | A read-only vendor credential and a spend cap for one live call, or confirm "blocked: no credential" | Phase 6 | Default to blocked |
| Q3 | Raise the `cryptography` floor from 42 to 44 for Argon2id. Measured here: scrypt 515 ms, Argon2id 40 ms (19 MiB) or 194 ms (64 MiB, 4 lanes) | Phase 3 | Yes, low priority; if no, decision D1 stands |
| Q4 | Which external provider to ship | Phase 7 | OS credential store first (no new dependency; the path exists in four connectors) |
| Q5 | Object to either default decided in Phase 1: `localhost` as a loopback-only passkey RP (VS-D4), or a 15 character minimum for new passphrases (VS-D5) | Phase 2 start | None needed unless the owner objects |

A WebAuthn test helper is **not** needed: Chromium's CDP virtual authenticator works with the
installed Playwright (Phase 0 and Phase 1 both used it).

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
| 2026-11-06 | VS-D1: lockout keeps one counter per vault but separates attempts that present an owner credential from anonymous ones; 300 s ceiling kept | OWASP keys the counter to the account, and here the account is the vault, which is the DoS in F-03; CVE-2026-33935 is the same bug |
| 2026-11-06 | VS-D2: WebAuthn PRF unlock deferred | Works in a virtual authenticator, but real-hardware support is fragmented and sources disagree; the server would receive the derived key; a deleted passkey destroys that wrap |
| 2026-11-06 | VS-D4: passphrase is the default step-up; WebAuthn UV added where an RP ID is possible; `localhost` allowed as a loopback-only RP behind a Phase 2 ADR | Experiment: a ceremony works on `http://localhost:PORT` and fails on an IP origin. Linux Chrome has no platform authenticator, so a passkey-only step-up would be a dead end there |
| 2026-11-06 | VS-D5: raise the passphrase minimum to 15 for new or changed passphrases only | NIST SP 800-63B-4 requires 15 for a single-factor secret; existing vaults are not forced |
| 2026-11-06 | VS-D7: cleaning the worker environment is not a Phase 2 task | `engine.py:409` gives each worker the whole server environment, but the worker needs its provider key; cleaning it first would break runs. Depends on the Phase 3 hand-off design |
| 2026-11-06 | Used the pass-3 requirement ids `VS-R1` to `VS-R32` as the citation scheme | Phases and tests cite them; each has a phase and a test that must fail first |
| 2026-11-06 | Did not search Reddit or Hacker News directly | Search results returned only issue trackers, advisories, forums and write-ups; recorded as a gap, not filled with guesses |

## Review findings log

Phase 0 self-review only. No independent reviewer yet (Phase 9, `progress.md` item 8).

| Date | Phase | Finding | Fix |
|---|---|---|---|
| 2026-11-06 | 0 | First live probe read headers case-sensitively and would have reported a missing `Cache-Control` on reveal that does exist | Probe fixed, re-run; `tools/probe_vault_live.py` is the corrected one |
| 2026-11-06 | 0 | Assumed paired-device management was CLI only; the dashboard calls `api("/v1/devices")` without the `/api` prefix, so a search for the full path missed it | Read `app.js:9773-10016`; audit F-06 corrected before commit |
| 2026-11-06 | 0 | Capture script saved `/connectors` as `apps-and-ai` and `/connections` as `connections` | Labels fixed and the 30 views recaptured before commit (`378d7e0b`) |
| 2026-11-06 | 0 | A `pkill -f` matched its own shell and killed a background test run | Re-ran the baseline; used PIDs afterwards |
| 2026-11-06 | 0 | Baseline test red: `test_vault_migration.py` assumed the destinations migration was last | `36600792` |
| 2026-11-06 | 1 | First draft of VS-R20 said "give workers an allowlisted environment". Reading `engine.py:409` showed workers need the inherited provider key, so that change would have broken every run | Requirement rewritten as dependent on the Phase 3 hand-off; recorded as VS-D7 before commit |
| 2026-11-06 | 1 | OWASP's "counter belongs to the account" conflicted with audit F-03, and a naive per-IP fix would not help because every local process is `127.0.0.1` | Resolved in VS-D1 by separating owner-credential attempts from anonymous ones; tension stated in `01-SOURCES.md` B7 |
| 2026-11-06 | 1 | A claim that a local process "cannot satisfy user verification" had no test behind it | Softened in VS-D4 to the owner's action at the authenticator, marked untested on real hardware |
| 2026-11-06 | 1 | Two specifications (WebAuthn L3, NIST 800-63B-4) were only read for their first 100,000 characters, and the Chrome DevTools WebAuthn page returned only a redirect | Stated in `01-SOURCES.md` B1, B5, B15 and `03` section 6; behavior established by experiment instead |
| 2026-11-06 | 1 | One fetch (the MCP security page) returned the whole page rather than an extract and cost about 12K tokens of context | Process note only; later fetches were searches |
| 2026-11-06 | 1 | Reviewed my own doc set for status inflation, not independently. Vendor marketing (1Password, Grok) is labelled as such; no row calls a vendor claim verified | Independent review stays Phase 9 |

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

## Phase 1 outcome (for the next session)

Read `docs/research/2026-11-vault-signin/03-LESSONS-AND-DECISIONS.md` first: 32 requirements
(`VS-R1` to `VS-R32`), nine decisions, five owner questions. Findings that change the plan:

- **A passkey ceremony works on `http://localhost:PORT` with RP ID `localhost` and fails on an
  IP-literal origin** (Chromium 153, virtual authenticator). The F-11 premise that loopback cannot
  have a passkey is true only for `127.0.0.1`. On Linux Chrome there is no platform authenticator, so
  the passphrase stays the default step-up.
- **The worker inherits the server's whole environment** (`engine.py:409`). Cleaning it depends on a
  Phase 3 hand-off design; it is not a Phase 2 task.
- **OWASP keys the lockout counter to the account**, which here is the vault and is the DoS in F-03.
  CVE-2026-33935 is the same bug. The fix separates owner-credential attempts from anonymous ones.
- **Forwarded-header trust and "loopback means owner" is a nine-advisory bug class** in 2026
  (`02-FAILURES-AND-COMPLAINTS.md` FC-8). It is Hutch's F-02 pattern.
- Scrypt measured 515 ms; Argon2id 40 ms to 194 ms, depending on memory. Argon2id needs the owner to
  raise the `cryptography` floor (Q3).

Baseline for Phase 2 is unchanged from Phase 0 (check:agent 4/4; vault, native-credentials and
migration suites 235 passed, 1 skipped). Phase 1 changed no source file, so those were not re-run;
`scripts/audit_emoji.py` over a root holding only the files this phase added: clean (6 files).

## Ordered backlog

1. ~~**Phase 1** research~~ done 2026-11-06 (`07336d83`). D1 re-tested (open as Q3); PRF decided
   as deferred (VS-D2).
2. **Phase 2** (next), by requirement id from `03-LESSONS-AND-DECISIONS.md`: F-11 ADR with the
   `localhost` RP exception (VS-D4, VS-R4); owner credential on vault routes (VS-R1, F-02); throttle
   buckets and the `Retry-After` fix (VS-R3, F-03, `pages.py:162-169`); step-up grant (VS-R2); passkey
   list, rename, BE/BS, last-credential guard (VS-R26); session list and revoke, `__Host-` cookie,
   `Clear-Site-Data` (VS-R25, F-06 date fix); refusal codes and host diagnostics (VS-R11); trusted-proxy
   tests (VS-R12); server-side UV test with a hand-signed assertion (F-13); passphrase minimum 15
   (VS-R9, VS-D5); `doctor.py` checks (VS-R10, F-10). Seams: `server/passkeys.py`, new
   `server/stepup.py`, `vault/access.py`; `security.py` (512 lines, frozen) gains wiring only. Split the
   phase into tasks of at most three files plus one seam. Q5 is the only owner input, and it is an
   objection window, not a blocker.
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
| `localhost` WebAuthn and PRF on real hardware, Firefox and Safari | Phase 1 proved the browser accepts it with a virtual authenticator in Chromium 153 only | Owner test with a real platform authenticator and a real security key |
| Whether a shell-tool child outside strict mode can read the worker's `/proc/<pid>/environ` | Not tested (FC-6) | Phase 3 design test, with VS-R20 |
| Whether a stored provider key follows a changed `base_url` to a new host | Not tested (FC-2) | Phase 5, VS-R18 |
| Whether chat input and tool results are redacted before storage | Not tested (FC-4) | The first phase that handles values, with the leak sweep script and VS-R29 |
| Reddit and Hacker News complaint mining; Doppler, Infisical, cloud managers, Roo, Continue, Aider, LibreChat, Home Assistant as products | Not searched or examined in Phase 1 (`01-SOURCES.md` sections C and D) | A follow-up research pass if the owner wants it |
| Cloud-hosted write-ups relied on second-hand: WebAuthn PRF support matrix, the Cappalli warning, the FIDO March 2025 paper | Secondary sources only | Read the primary posts and papers before any PRF work |

## How to reproduce Phase 0 evidence

Real server on a throwaway `HUTCH_STATE_DIR`; tools in `docs/research/2026-11-vault-signin/tools/`:
`probe_vault_live.py PORT STATE_DIR`, `tls_proxy.py` plus `webauthn_baseline.py UP PROXY OUT` (needs
`HUTCH_TRUSTED_PROXIES`, `HUTCH_ALLOWED_HOSTS`, `HUTCH_WEBAUTHN_RP_ID`, `HUTCH_WEBAUTHN_ORIGIN` and
`--allow-remote`; see audit section 6), and `docs/realignment/capture_vault_signin_baseline.py ORIGIN OUT`.

## How to reproduce Phase 1 evidence

`uv run --frozen --no-sync python docs/research/2026-11-vault-signin/tools/webauthn_localhost_prf.py OUT.json`
(starts its own throwaway static server, needs the installed Playwright Chromium; result committed at
`docs/research/2026-11-vault-signin/artifacts/phase1/webauthn-localhost-prf.json`). The KDF timing
run is `docs/research/2026-11-vault-signin/tools/kdf_bench.py` (scrypt 2^17/8/1 against Argon2id at
19, 64 and 128 MiB, median of 5, one machine); its numbers are recorded in `01-SOURCES.md` B17 and are not a general performance claim.
