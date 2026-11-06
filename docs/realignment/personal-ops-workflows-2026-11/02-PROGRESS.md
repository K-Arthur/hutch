# Progress: personal ops, coding, family workflows, shipped workflows and daily automations (2026-11)

Update at every checkpoint. Keep entries short, factual, and backed by commit hashes and command
output.

## Phase status

| Phase | Status | Last commit | Live-verified | Blocked on |
|---|---|---|---|---|
| 0 Diagnose and baseline audit | done | 1bec95e1 | 73 focused tests passed (54.38s); 40 baseline screenshots (0 errors, 0 overflow) | none |
| 1 Live web research and failure mining | done | c3856c3b | 8/8 owner URLs fetched live; 48 requirements and 48 failure rows cross-checked; `npm run check:agent` and `npm run audit:context` pass; emoji audit has no repository-source hits (8 hits only in git-ignored `.codewhale/state/subagents.v1.json`) | none |
| 2 Automations trust & observability (G03, G06) | done | c31b9a92 | 2A+2B+2C: 172 focused tests; 3 Playwright tests at 360/768/1280/1920 dark and light preference; 12 captures with 0 errors and 0 overflow; dark-only theme limit recorded | none |
| 3 Inbound webhook & event triggers (G04) | done | 51378c03 | 3A+3B: 9 focused tests; 2 Playwright e2e tests at 360/768/1280/1920 dark and light; 12 captures with 0 errors and 0 overflow; real SQLite v94 | none |
| 4 Multimodal intake pipeline (chat, channels, Today) | not started | | | |
| 5 Personal ops bridges: provenance & calendar (G08, G09) | not started | | | |
| 6 Family & shared household workflows (G07 ADR, templates) | not started | | | |
| 7 Coding orchestration UI, receipts & worktree GC (G02, G11) | not started | | | |
| 8 Deliverables library, semantic checks & purge (G10, G12, G14) | not started | | | |
| 9 Paired-phone surface, website, docs & final review (G13) | not started | | | |

Phase 1 is documentation only. It changed no source file, so focused product tests, real-stack e2e
and browser capture are not applicable. The live verification for this phase is the source fetch
ledger (`01-SOURCES.md`): 8/8 owner URLs returned readable content, and the two unreachable pages are
recorded in section E rather than guessed.

### Phase 2 checkpoints

| Task | Status | Commit | Verification |
|---|---|---|---|
| 2A Schedule revision journal | done | 817c3942 | `npm run test:agent -- tests/test_schedule_history.py`: 7 passed; real SQLite migration v92; update/delete refused; no-op save writes zero rows |
| 2B Approval checkpoints and bounded conditions | done | 69b2637b | `npm run test:agent -- tests/test_schedule_conditions.py tests/test_schedule_policy.py tests/test_schedule_approvals.py tests/test_schedule_history.py tests/test_scheduler.py tests/test_schedule_outcomes.py tests/test_schedule_durability.py tests/test_lifecycle.py tests/test_approval_cas.py`: 172 passed; real approval parks, approve releases, deny/expire skips, one notification |
| 2C Schedules surface (filter, history, roll-call) | done | fd988138 (cleanup e7ac6411, fix c31b9a92) | `uv run --frozen --no-sync pytest -q tests/e2e/test_schedule_history.py`: 3 passed; 12 captures, 0 console errors, 0 overflow; roll call, filter, keyboard history, policy save verified |
| Phase 2 exit | done | c31b9a92 | 172 focused tests; real SQLite v93; real FastAPI statuses 200/409/422/404; real Chromium 153.0.8010.12; evidence in `06-VALIDATION-LEDGER.md` | none |

### Phase 3 checkpoints

| Task | Status | Commit | Verification |
|---|---|---|---|
| 3A Webhook schema, store and admission receiver | done | cc41f02c | `npm run test:agent -- tests/test_webhooks.py`: 8 passed; real SQLite migration v94; 64 KB cap, MIME check, dual-window secret rotation, idempotency replay, and untrusted ingest scan |
| 3B Webhook API, management UI and live e2e | done | 51378c03 | `uv run --frozen --no-sync pytest -q tests/e2e/test_webhooks.py`: 2 passed; 12 captures, 0 console errors, 0 overflow; CRUD, rotation, pause/resume, deliveries log and one-time secret verified |
| Phase 3 exit | done | 51378c03 | 9 focused tests; 2 e2e tests; 12 captures (0 error, 0 overflow); real SQLite v94; real FastAPI ingress & CRUD; evidence in `06-VALIDATION-LEDGER.md` |

## Owner inputs needed (batch, ask once)

- Live Google Calendar / Gmail or Telegram credentials if live external vendor verification (beyond
  real local server + real SQLite + real local LLM runtime) is desired in Phases 4-5; otherwise
  external vendor calls stay recorded as `implemented-unverified (blocked: no live credential)`.
- Confirmation on whether paired phones (`G13`, Phase 9) may *confirm* assistant-proposed
  commitments or only *complete/view* already-confirmed commitments (default: view + complete only;
  confirming new obligations stays local-owner-only).
- Any third-party dependency additions (default: zero new dependencies; use stdlib + existing
  dependencies).

## Concurrent session awareness log

- Recorded on 2026-11-06 before Phase 0: sibling packs `offline-models-2026-11`,
  `provider-expansion-2026-11`, and `vault-signin-2026-11` exist in the checkout. Check `git status`
  before every commit and stage only explicit paths touched by this initiative.
- Active uncommitted/staged files observed in checkout (never touch or revert):
  - `docs/models.md`
  - `docs/realignment/offline-models-2026-10-31.md`
  - `docs/realignment/offline-models-2026-11/02-PROGRESS.md`
  - `docs/research/2026-11-offline-models/evidence/phase5/*`
  - `docs/runtime-setup.md`
  - `src/hutch/server/static/hutch-pages.css`
  - `docs/research/2026-11-vault-signin/*`
  - `.commandcode/*`
- Phase 1 observation (2026-11-06): `docs/research/2026-11-personal-ops-workflows/00-GAP-AUDIT.md`
  carries an uncommitted trailing-newline change. It is not this phase's file and was not staged.
  `src/hutch/server/static/hutch-pages.css` remains modified by another session and was not touched.
  `.commandcode/` remains untracked and was not staged.

## Decisions log

| Date | Phase | Decision | Rationale |
|---|---|---|---|
| 2026-11-06 | Init | Keep Today (`src/hutch/personal/today.py`) strictly deterministic (zero LLM calls on page load) | Prevents hallucinated briefings, latency spikes and hidden token spend; multimodal/model extraction happens on intake/runs and writes provenance-tagged proposals |
| 2026-11-06 | Init | Treat shared spaces (`src/hutch/personal/spaces.py`) as single-owner data scopes until G07 multi-participant auth is implemented | Prevents false privacy/isolation claims for household members on a single-owner server |
| 2026-11-06 | Phase 0 | Retain `capture_personal_ops_baseline.py` in `docs/realignment/` | Mirrors sibling realignment pattern (`capture_vault_signin_baseline.py`) for reproducible visual regression probes at every phase gate |
| 2026-11-06 | Phase 1 | Revision journal uses SQL triggers on `bots`, not app-layer logging (POW-D1) | API, CLI and direct DB writes all pass the trigger; schedule settings are exactly what n8n's workflow history misses |
| 2026-11-06 | Phase 1 | Schedule policy lives in a sidecar table, not `models.py` (POW-D17) | `models.py` is frozen at 828 lines; a sidecar gets its own CAS revision |
| 2026-11-06 | Phase 1 | Webhook secret is hashed at rest, shown once, compared in constant time, rotated with a dual window (POW-D4) | A database read must not yield a usable token; rotation must not drop in-flight deliveries |
| 2026-11-06 | Phase 1 | Calendar writes are exact-approval actions with a stable key; `outcome_unknown` is never retried (POW-D9) | Provider sync already creates copies by design; Hutch must not add duplicates |
| 2026-11-06 | Phase 1 | Shared lists are one server-scoped record with upsert merge (POW-D10) | Local-copy reconciliation is the documented cause of duplicates, ghosts and crossed-off drift |
| 2026-11-06 | Phase 1 | Worktree GC is dry-run by default and never deletes unmerged or unpushed work without explicit force (POW-D11) | Auto-cleanup has deleted live and unpushed work in reported cases |
| 2026-11-06 | Phase 1 | Purge exports first, then uses `secure_delete` with a checkpoint before `VACUUM`, and leaves a content-free tombstone (POW-D16) | WAL and freelist pages can retain deleted bytes; foreign keys need a row |
| 2026-11-06 | Phase 1 | A phone can view, complete and decide an existing approval; confirming a new obligation stays local-owner (POW-D13) | Preserves the local-first authority boundary while covering the away-from-desk need |
| 2026-11-06 | Phase 1 | Telegram stays text-only by default with a visible notice; media intake is per-channel opt-in (POW-D14) | Silent drops are the current defect; default media widens attack surface and size failure modes |
| 2026-11-06 | Phase 1 | No new dependency (POW-D15) | The standard library and existing stack cover every requirement; supply-chain cost is not justified |
| 2026-11-06 | Phase 2 | Schedule policy lives in a sidecar table with its own revision (POW-D17) | `models.py` is frozen; the sidecar also gives CAS edits and cleanup without rewriting the bot document |
| 2026-11-06 | Phase 2 | A pre-run approval applies to prompt schedules; linked saved workflows keep their own step approvals and return 422 for a schedule-level pre-check | The workflow engine already gates its steps; a second half-implemented gate would be less trustworthy than an explicit limit |
| 2026-11-06 | Phase 2 | Approved decisions are reconciled immediately and retried on every scheduler beat | A crash between the approval commit and the run transition must not strand a parked run |
| 2026-11-06 | Phase 2 | The schedules surface observes `#view` from a new module instead of editing frozen `app.js` | Native details/summary and checkbox controls keep the keyboard path; the enhancement is isolated and testable |
| 2026-11-06 | Phase 2 | One needs-attention set drives the roll-call, filter and the older attention note | Two different counts on one page undermine trust; the note is rewritten from the same totals |
| 2026-11-06 | Phase 2 | Keep the dashboard dark-only and do not claim a light theme | `docs/design-system.md` defines a fixed dark dashboard; forcing the light scope leaves the legacy tokens unchanged |

## Visual validation log

| Date | Phase | Surface | Widths & themes | Defects found & fixed | Evidence path |
|---|---|---|---|---|---|
| 2026-11-06 | Phase 0 | `#/today`, `#/shared`, `#/schedules`, `#/tasks`, `#/catalog` | 360, 768, 1280, 1920 px (dark and light; 40 views total) | 0 console errors, 0 px horizontal overflow across all 40 views | `docs/research/2026-11-personal-ops-workflows/artifacts/phase0/report.json` |
| 2026-11-06 | Phase 2 | `#/schedules` default and history panel | 360, 768, 1280, 1920 px; dark and design-system light preference (12 views; history at 1280/1920) | Fixed 4 defects: raw schedule id in next-due, contradictory attention count, parked approval described as "still running", and an unbalanced 5+1 grid at 768 px. Light preference renders the same dark surface by design; logged as a limit, not a theme claim | `docs/research/2026-11-personal-ops-workflows/artifacts/phase2/report.json` |
| 2026-11-06 | Phase 3 | `#/schedules` inbound webhooks & deliveries | 360, 768, 1280, 1920 px; dark and light preference (12 views; deliveries at 1280/1920) | 0 console errors, 0 px horizontal overflow across all 12 views; fixed locator strict mode in deliveries badge | `docs/research/2026-11-personal-ops-workflows/artifacts/phase3/report.json` |

Phase 1 made no UI or website change, so no new visual capture was required. The Phase 0 baseline
remains the visual reference for the next UI phase.

## Review findings log

| Date | Phase | File:line | Finding | Fix commit |
|---|---|---|---|---|
| 2026-11-06 | Phase 0 | `src/hutch/channels/telegram.py:84,97` | Silent drop of all non-text Telegram updates (photo, voice, document) with zero feedback to user | Tracked for Phase 4 (Task 4B) |
| 2026-11-06 | Phase 0 | `src/hutch/tools/commitments.py:50-115` | `capture_commitment` lacks `source_ref` validation against run tool/upload records | Tracked for Phase 5 (Task 5A) |
| 2026-11-06 | Phase 0 | `src/hutch/store.py:4027-4100` | Schedule mutations overwrite bot doc without audit/revision triggers (G03) | Tracked for Phase 2 (Task 2A) |
| 2026-11-06 | Phase 0 | `src/hutch/server/security.py:40-160` | Phone capability map excludes Today and commitments routes (G13) | Tracked for Phase 9 (Task 9A) |
| 2026-11-06 | Phase 1 | `03-REQUIREMENTS-AND-DECISIONS.md:45` | POW-R17 originally did not restrict the text-only notice to allowlisted senders; fixed before commit so a stranger is never messaged | c3856c3b |
| 2026-11-06 | Phase 1 | `03-REQUIREMENTS-AND-DECISIONS.md:99` | Phone capability first said "view and complete only", omitting the existing-approval decision the phase goal requires; fixed with an explicit allow/deny test | c3856c3b |
| 2026-11-06 | Phase 1 | `03-REQUIREMENTS-AND-DECISIONS.md:123` | Sidecar schedule policy was not recorded as a decision; added POW-D17 to keep `models.py` frozen | c3856c3b |
| 2026-11-06 | Phase 1 | `02-FAILURES-AND-COMPLAINTS.md` | Initial id cross-check found POW-R4 and POW-R13 defined but uncited; added them to F20 and F41 | c3856c3b |
| 2026-11-06 | Phase 1 | `01-SOURCES.md` E1-E2 | `ocr.direct` returned 504 and the OpenAI PDF thread returned an empty page; recorded as unreachable instead of guessing | c3856c3b |
| 2026-11-06 | Phase 2 | `src/hutch/lifecycle.py:32` | Initial smoke test showed denial and expiry left runs in `waiting_approval`: the lifecycle table did not allow `waiting_approval -> skipped`. Added the transition and a visible reconciliation error event; regression test covers deny and expiry | 69b2637b |
| 2026-11-06 | Phase 2 | `src/hutch/schedule_admission.py:38-44` | Reconciliation failures were swallowed. They now append a bounded log event to the run so a stuck parked run is visible instead of silent | 69b2637b |
| 2026-11-06 | Phase 2 | `src/hutch/schedule_history.py:140` | Commit `69b2637b` omitted the new `list_occurrences` function while committing its callers, so that checkpoint could not import the history API. Fixed forward; the working tree was green only because the omission was still uncommitted | 99ec03fc |
| 2026-11-06 | Phase 2 | `src/hutch/server/static/schedules.js` | The first visual pass showed a raw `schedule_...` id in the next-due line, a contradictory attention count, a parked approval described as "still running", and an unbalanced 5+1 grid at 768 px. Fixed in the enhancement and recaptured | fd988138 |
| 2026-11-06 | Phase 2 | `src/hutch/server/static/schedules.js` | The MutationObserver rewrote the same attention note and parked-run text on every mutation, risking a self-trigger loop. Added idempotence guards; the e2e test still passes | fd988138 |
| 2026-11-06 | Phase 2 | `docs/design-system.md` (theme contract) | Forcing `data-hutch-theme="light"` leaves the legacy dashboard tokens at the same dark values. The light captures are layout/overflow checks, not a shipped light theme; recorded in the ledger and operations guide | fd988138 |
| 2026-11-06 | Phase 2 | `src/hutch/server/static/schedules.js` | Final cleanup removed an unused bulk policy fetch; the four affected screenshots were recaptured and the e2e test stayed green | e7ac6411 |
| 2026-11-06 | Phase 2 | `src/hutch/server/static/schedules.js` | After the note was hidden once, a later positive count could leave it hidden; the disabled filter also kept a stale checked state. Both states now reset correctly and the e2e test passes | c31b9a92 |
| 2026-11-06 | Phase 3 | `src/hutch/webhook_receiver.py:78` | Cooldown calculation originally read `last_delivery_at`, causing rejected requests during cooldown to reset the timer; fixed to `last_success_at` matching `store.py` convention | cc41f02c |
| 2026-11-06 | Phase 3 | `src/hutch/server/static/webhooks.js:49` | Assigned assistant label fell back to technical name rather than `display_name`; updated to `display_name || name` | 51378c03 |

## Open items and deferred

| Item | Reason | What would unblock |
|---|---|---|
| Live Google Calendar / Gmail OAuth verification | No live Google credentials provided | Owner credentials or stay `implemented-unverified` |
| Live Telegram bot verification | No live Telegram bot token provided | Owner bot token or stay `implemented-unverified` |
| `ocr.direct` receipt-validation guide | HTTP 504 on 2026-11-06 | Not needed; C14 (ExpenSheet) covers the same rules and no requirement depends on the missing page |
| OpenAI Developer Community PDF-export thread | Returned an empty body on 2026-11-06 | C16 and C17 carry the deliverable-loss evidence; recheck only if a primary OpenAI statement is needed |
| Telegram local Bot API server | Not stood up or tested | Do not claim its 2 GB ceiling; the standard Bot API 20 MiB download cap is the verified limit |
| Marketing website claim sync | Phase 1 is research only; site claims must follow live-verified behavior, not plans | Phase 9 Task 9B, after Phases 2-8 are live-verified |
| Schedule-level pre-approval for linked saved workflows | The workflow engine already has per-step approvals; a schedule-level gate needs a workflow parking state and a retry policy | A later phase can add it with workflow-engine tests; until then the policy API returns 422 and the UI must say why |
| Light dashboard theme | The design system ships a fixed dark theme; the derived light scope does not change the legacy dashboard tokens | A token migration that maps the dashboard's `--text`/`--line`/`--panel` family into the `--hutch-*` light scope, followed by contrast measurements |
| Physical phone or screen-reader validation | The browser evidence is headless Chromium 153.0.8010.12; no physical device or screen reader was available | A physical Android/iOS pass and a screen-reader session on `#/schedules` |
