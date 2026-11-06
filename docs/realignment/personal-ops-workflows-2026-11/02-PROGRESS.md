# Progress: personal ops, coding, family workflows, shipped workflows and daily automations (2026-11)

Update at every checkpoint. Keep entries short, factual, and backed by commit hashes and command
output.

## Phase status

| Phase | Status | Last commit | Live-verified | Blocked on |
|---|---|---|---|---|
| 0 Diagnose and baseline audit | done | pending | 73 focused tests passed (54.38s); 40 baseline screenshots (0 errors, 0 overflow) | none |
| 1 Live web research and failure mining | not started | | | |
| 2 Automations trust & observability (G03, G06) | not started | | | |
| 3 Inbound webhook & event triggers (G04) | not started | | | |
| 4 Multimodal intake pipeline (chat, channels, Today) | not started | | | |
| 5 Personal ops bridges: provenance & calendar (G08, G09) | not started | | | |
| 6 Family & shared household workflows (G07 ADR, templates) | not started | | | |
| 7 Coding orchestration UI, receipts & worktree GC (G02, G11) | not started | | | |
| 8 Deliverables library, semantic checks & purge (G10, G12, G14) | not started | | | |
| 9 Paired-phone surface, website, docs & final review (G13) | not started | | | |

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

## Decisions log

| Date | Phase | Decision | Rationale |
|---|---|---|---|
| 2026-11-06 | Init | Keep Today (`src/hutch/personal/today.py`) strictly deterministic (zero LLM calls on page load) | Prevents hallucinated briefings, latency spikes and hidden token spend; multimodal/model extraction happens on intake/runs and writes provenance-tagged proposals |
| 2026-11-06 | Init | Treat shared spaces (`src/hutch/personal/spaces.py`) as single-owner data scopes until G07 multi-participant auth is implemented | Prevents false privacy/isolation claims for household members on a single-owner server |
| 2026-11-06 | Phase 0 | Retain `capture_personal_ops_baseline.py` in `docs/realignment/` | Mirrors sibling realignment pattern (`capture_vault_signin_baseline.py`) for reproducible visual regression probes at every phase gate |

## Visual validation log

| Date | Phase | Surface | Widths & themes | Defects found & fixed | Evidence path |
|---|---|---|---|---|---|
| 2026-11-06 | Phase 0 | `#/today`, `#/shared`, `#/schedules`, `#/tasks`, `#/catalog` | 360, 768, 1280, 1920 px (dark and light; 40 views total) | 0 console errors, 0 px horizontal overflow across all 40 views | `docs/research/2026-11-personal-ops-workflows/artifacts/phase0/report.json` |

## Review findings log

| Date | Phase | File:line | Finding | Fix commit |
|---|---|---|---|---|
| 2026-11-06 | Phase 0 | `src/hutch/channels/telegram.py:84,97` | Silent drop of all non-text Telegram updates (photo, voice, document) with zero feedback to user | Tracked for Phase 4 (Task 4B) |
| 2026-11-06 | Phase 0 | `src/hutch/tools/commitments.py:50-115` | `capture_commitment` lacks `source_ref` validation against run tool/upload records | Tracked for Phase 5 (Task 5A) |
| 2026-11-06 | Phase 0 | `src/hutch/store.py:4027-4100` | Schedule mutations overwrite bot doc without audit/revision triggers (G03) | Tracked for Phase 2 (Task 2A) |
| 2026-11-06 | Phase 0 | `src/hutch/server/security.py:40-160` | Phone capability map excludes Today and commitments routes (G13) | Tracked for Phase 9 (Task 9A) |

## Open items and deferred

| Item | Reason | What would unblock |
|---|---|---|
| Live Google Calendar / Gmail OAuth verification | No live Google credentials provided | Owner credentials or stay `implemented-unverified` |
| Live Telegram bot verification | No live Telegram bot token provided | Owner bot token or stay `implemented-unverified` |
