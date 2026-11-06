# Phases and sequential checkpoints (2026-11)

Each phase follows the same loop: research (`04-RESEARCH-PLAN.md`), short written design naming
exact `@path/to/file.py:line` ranges, small commits on `main` (at most 3 source files + 1 seam per
task), real-stack validation, Playwright visual validation when UI/website is touched, skeptical
code review, and doc updates. A phase is complete only when all its exit criteria pass and are
recorded in `02-PROGRESS.md`.

## Phase 0 - Diagnose and baseline audit (no feature code)

- Inspect `git status` and `git log -5` to identify any concurrent session's uncommitted or staged
  files; record them in `02-PROGRESS.md` so they are never touched.
- Verify the current state of `.pipeline/personal-operations/2026-10/GAP-REGISTER.md` (G01-G14)
  against `HEAD` using targeted `rg` and line-range reads:
  - `@src/hutch/store.py:2440-2456` (confirm current `SCHEMA_VERSION` and registered migrations)
  - `@src/hutch/personal/today.py:1-160`, `@src/hutch/personal/agenda.py:1-140`,
    `@src/hutch/personal/spaces.py:1-140`
  - `@src/hutch/code_handoff.py:1-90`, `@src/hutch/code_review.py:1-90`,
    `@src/hutch/code_prune.py:1-90`
  - `@src/hutch/channels/telegram.py:1-101`, `@src/hutch/channels/service.py:1-97`,
    `@src/hutch/notifications.py:1-120`
  - `@src/hutch/providers/attachments.py:1-140`, `@src/hutch/ingest.py:1-120`
- Run baseline focused tests:
  `npm run test:agent -- tests/test_commitments.py tests/test_spaces.py tests/test_personal_api.py tests/test_commitment_tools.py tests/test_code_review.py tests/test_channels.py`
- Capture baseline Playwright screenshots (360, 768, 1280, 1920 px, light and dark) of `#/today`,
  `#/shared`, `#/schedules`, `#/tasks` and `#/catalog`.
- Produce `docs/research/2026-11-personal-ops-workflows/00-GAP-AUDIT.md` mapping every open gap and
  every multimodal pipeline seam to exact `file:line` evidence.
- **Exit:** baseline test counts, visual baseline, and `00-GAP-AUDIT.md` committed; `02-PROGRESS.md`
  updated.

## Phase 1 - Live web research and failure/complaint mining (docs only)

- Execute `04-RESEARCH-PLAN.md` in full:
  - Verify the 8 user-supplied URLs (`github.com/K-Arthur/hutch`, `openclaw.ai/showcase`, and the 6
    X showcase threads: `@jdrhyne`, `@danpeguine`, `@georgedagg_`, `@dreetje`, `@davekiss`,
    `@stevecaldwell`), extending `.pipeline/personal-operations/2026-10/RESEARCH.md`.
  - Mine real-world failures and user complaints across personal ops/timeblocking apps (Motion,
    Reclaim, Sunsama, Akiflow, Todoist, Apple Reminders), family/household apps (Cozi, Notion
    templates, Hearth, Mealime, Bring!, AnyList), automation runners (OpenClaw, n8n, Zapier, Make,
    Home Assistant), coding orchestrators (Claude Code, Codex, OpenCode, Cursor, Devin), and
    multimodal/receipt/voice pipelines (Whisper hallucinations on silence, OCR date/currency mixups,
    dropped Telegram attachments, EXIF orientation bugs).
- Write:
  - `docs/research/2026-11-personal-ops-workflows/01-SOURCES.md`
  - `docs/research/2026-11-personal-ops-workflows/02-FAILURES-AND-COMPLAINTS.md`
  - `docs/research/2026-11-personal-ops-workflows/03-REQUIREMENTS-AND-DECISIONS.md` (assigning
    requirement IDs `POW-R1..POW-Rn` with concrete test ideas).
- **Exit:** every subsequent phase cites `POW-R*` IDs; research committed.

## Phase 2 - Daily automations trust & observability (G03, G06 remainder)

- **Task 2A (G03.1 - Schedule revision journal):**
  - Create `src/hutch/schedule_history_schema.py` (append-only `schedule_revisions` table + SQL
    triggers on `bots` insert/update when extracted schedule JSON changes; UPDATE/DELETE refused by
    trigger). Register in `@src/hutch/store.py:2446-2454`.
  - Create `src/hutch/server/schedule_history_api.py` (`GET /api/v1/bots/{ref}/schedules/{id}/revisions`
    with Python-computed changed-field diffs and hashes, no host paths). Wire in `app.py`.
- **Task 2B (G03.2 & G03.3 - Schedule approval checkpoints & bounded conditions):**
  - Add optional `approval_required: bool` and bounded declarative `conditions` to schedule
    definitions so an occurrence can park in `waiting_approval` before model/tool execution (reusing
    `@src/hutch/approvals.py`) and evaluate literal source conditions without `eval`.
- **Task 2C (G06 remainder - Per-routine UI, history disclosure & fleet roll-call):**
  - Create `src/hutch/server/static/schedules.js` (and `app/src/` CSS) providing a "Needs attention"
    filter, keyboard-accessible revision & occurrence history disclosure, linked workflow-run status,
    and a top-of-page fleet roll-call summary (active/blocked routines, last 24h failures, next due).
- **Exit:** real SQLite trigger tests, migration test in `tests/test_migration.py`, API tests in
  `tests/test_schedule_history.py`, real browser verification + 4-width light/dark screenshots of
  `#/schedules`.

## Phase 3 - Inbound webhook and event triggers (G04)

- **Task 3A (Webhook schema & durable admission):**
  - Create `src/hutch/webhook_schema.py` (`webhook_sources` and `webhook_deliveries` tables: SHA-256
    token hash, bound `bot_id`, prompt/workflow template, rate/cooldown limits, idempotency key,
    enabled/paused state, revision CAS). Register in `@src/hutch/store.py:2446-2454`.
  - Create `src/hutch/webhook_receiver.py` enforcing payload byte cap (64 KB), `application/json` /
    `text/plain` validation, `src/hutch/ingest.py` untrusted-content annotation, replay deduplication,
    and admission into the existing durable run/source inbox.
- **Task 3B (Webhook API & UI management):**
  - Create `src/hutch/server/webhooks_api.py` (`POST /api/v1/webhooks/{token}` for ingress,
    local-owner CRUD routes under `/api/v1/webhook-sources` returning the secret once at creation).
  - Add management UI in `src/hutch/server/static/webhooks.js` (under Scheduled work / sources) with
    delivery log, pause/resume, secret rotation, and explicit loopback/private-bind warnings.
- **Exit:** real HTTP POST tests against a live server port (wrong secret, replay, oversize payload,
  paused source, prompt-injection payload annotated via `ingest.py`), Playwright visual validation.

## Phase 4 - Multimodal intake pipeline (Chat, Channels, Personal Ops & Workflows)

- **Task 4A (Unified multimodal intake & capability preflight):**
  - Create `src/hutch/multimodal_intake.py` unifying image/photo (receipts, schedules, whiteboards),
    audio/voice (`src/hutch/tools/transcribe.py`), and document (`PDF`/`CSV`/`ICS`) intake metadata:
    SHA-256 digest, MIME sniff verification, EXIF orientation normalization/stripping, bounded size
    checks, and `src/hutch/ingest.py` scan findings on extracted text/transcripts.
  - Ensure route capability preflight (`@src/hutch/providers/attachments.py:114-206`) gives a clear,
    actionable refusal or route recommendation before admission whenever a user attaches media to a
    text-only model route.
- **Task 4B (Telegram channel attachment & voice awareness):**
  - Update `@src/hutch/channels/telegram.py:80-101` and `@src/hutch/channels/persistence.py`:
    never silently drop photo, voice or document messages from allowlisted senders. Support bounded
    opt-in media/voice download into the conversation upload store (when enabled for that channel)
    and record a deterministic, visible "attachment not processed (channel is in text-only mode)"
    notice when disabled.
- **Task 4C (Multimodal UI feedback in Chat & Today):**
  - Create `src/hutch/server/static/multimodal-intake.js` rendering attachment provenance badges,
    transcription/extraction previews, `ingest.py` untrusted-content warnings, and capability
    refusal banners in Chat and Today.
- **Exit:** real image, audio wav, and PDF uploads processed through the real server; Telegram
  update handling verified; Playwright visual checks at 4 widths.

## Phase 5 - Personal ops bridges: provenance capture & calendar reminders (G08, G09)

- **Task 5A (G09 - Provenance-bound commitment proposals):**
  - Extend `@src/hutch/tools/commitments.py:50-115` and `@src/hutch/personal/models.py:79-150` so
    `capture_commitment` accepts a structured `source_ref` (`kind`: `gmail` | `google_calendar` |
    `outlook_mail` | `outlook_calendar` | `upload_image` | `upload_audio` | `document`, `item_id`,
    `sha256_or_etag`, `excerpt`).
  - Validate `source_ref` against the run's committed tool results or conversation uploads before
    writing; reject fabricated references. Render "Suggested from <source>" with a jump link on
    `#/today` (`@src/hutch/server/static/today.js`, `@src/hutch/server/static/personal-ui.js`).
- **Task 5B (G08 - Confirmed commitment to calendar reminder):**
  - Create `src/hutch/personal/calendar_bridge.py` and owner route
    `POST /api/v1/commitments/{id}/calendar-reminder` in `@src/hutch/server/personal_api.py`.
  - Enforce: only `confirmed` + `open` commitments with a `due_at` and valid IANA `due_timezone`;
    creates an exact-action approval (or executes under explicit owner confirmation), never
    auto-retries on `outcome_unknown`, and stores the resulting external event receipt on the
    commitment event log.
- **Exit:** contract tests for `capture_commitment` schema (`npm run check:agent`), rejection test
  for forged `source_ref`, calendar bridge `outcome_unknown` test, Playwright verification on
  `#/today`.

## Phase 6 - Family & shared household workflows (G07 ADR + Shared Spaces templates)

- **Task 6A (G07 - Multi-participant identity ADR):**
  - Write `docs/adr/0033-multi-participant-household-identity.md` (or next available ADR number)
    specifying the principal model, per-member passkey/session capabilities, space-scoped query
    enforcement, how single-owner loopback interacts with household members, and why shared spaces
    remain single-owner data scopes until member auth is enabled.
- **Task 6B (Shared space lists, templates & household digests):**
  - Extend `src/hutch/personal/` with a bounded shared-space checklist/collection helper or
    structured commitment categories (`meal-plan`, `shopping-aisle`, `household-deadline`) that
    support idempotent item merge (no duplicate "milk" rows when a weekly meal workflow runs twice)
    and deterministic week/date mapping.
  - Add reviewable catalog/workflow definitions under `src/hutch/data/catalog/` (e.g.
    `family-meal-planner.json`, `household-briefing.json`) and enhance `#/shared`
    (`@src/hutch/server/static/shared.js`) with category filtering, member attribution, and space
    grant controls.
- **Exit:** ADR committed, idempotent shared-space item merge tested against a real SQLite DB,
  catalog manifest validation green, `#/shared` visual validation at 4 widths in light/dark.

## Phase 7 - Coding orchestration surface, receipts & worktree lifecycle (G02 remainder, G11)

- **Task 7A (Worktree inspection, stale detection & doctor integration):**
  - Create `src/hutch/code_lifecycle.py` (keeping `code_handoff.py` untouched or shrunk) providing
    `list_stale_worktrees` (age, byte size, branch, dirty status, alive-runner check, latest
    verification receipt) and integrate a read-only check into `@src/hutch/doctor.py`.
  - Wire `hutch code list --stale` via a small helper module `src/hutch/cli_code.py`.
- **Task 7B (Coding handoff API & dashboard UI):**
  - Create `src/hutch/server/code_handoff_api.py` (`GET /api/v1/code-handoffs`,
    `GET /api/v1/code-handoffs/{id}/receipts`, `POST /api/v1/code-handoffs/{id}/verify`,
    `POST /api/v1/code-handoffs/{id}/prune`).
  - Create `src/hutch/server/static/code-handoffs.js` surfacing worktrees, changed-file counts,
    verification receipt history, and confirmed prune controls inside `#/tasks` and run cards.
- **Exit:** real Git worktree created, verified with a real command, inspected via API/UI, and
  pruned; alive-process refusal proven; Playwright screenshots at 4 widths.

## Phase 8 - Shipped workflows, Deliverables library, semantic checks & purge (G10, G12, G14)

- **Task 8A (G12 - Deterministic semantic deliverable checks):**
  - Create `src/hutch/documents/checks.py` and hook into `@src/hutch/documents/storage.py`: support
    bounded `declared_checks` (`json_schema`, `required_sections`, `csv_row_bounds`, `non_empty`)
    evaluated deterministically at creation. Failed checks set `validation_state = "failed"` and
    block the `Validated` badge.
- **Task 8B (G10 - Deliverables library API & `#/deliverables` UI):**
  - Create `src/hutch/server/deliverables_api.py` and `src/hutch/server/static/deliverables.js`
    aggregating generated documents, media outputs, and hash-verified workflow artifacts with
    filters by assistant, kind, validation state and date.
- **Task 8C (G14 - Permanent scoped purge for commitments & personal records):**
  - Extend `@src/hutch/fact_purge.py` (or create `src/hutch/personal/purge.py`) so an owner can
    export and permanently purge commitment content bytes and events while leaving a content-free
    tombstone for referential integrity.
- **Exit:** byte-level SQLite inspection proving purged strings are gone from tables and WAL/pages
  after checkpoint; deliverables library tested with real documents and corrupted-hash refusal;
  Playwright visual validation.

## Phase 9 - Paired-phone Personal Ops, docs, marketing website & final review (G13)

- **Task 9A (G13 - Paired-phone Today, commitments & status surface):**
  - Add `/api/v1/phone/today` and scoped phone actions in `@src/hutch/server/personal_api.py` and
    register explicit phone capabilities in `@src/hutch/server/security.py` (without growing
    `security.py` over cap; extract capability table if needed).
  - Create `src/hutch/server/static/phone-personal.js` so a paired phone can view Today, mark
    commitments done, review pending approvals, and check coding/routine status.
- **Task 9B (Documentation & marketing website sync):**
  - Update `docs/commitments.md`, `docs/workflows.md`, `docs/operations.md`, `docs/channels.md`.
  - Update `website/index.html`, `website/src/input.css`, and `website/llms.txt` (then run
    `npm run build:css --silent`) to accurately present personal ops, shared household spaces,
    verified coding handoffs, multimodal intake, and durable automations — strictly matching shipped
    behavior and linking to explicit limits (`docs/marketing-site.md`).
- **Task 9C (Whole-initiative review & final gate):**
  - Run full diff review from Phase 0 baseline to `HEAD` (check for god functions, frozen-file
    growth, naive timestamps, secret leaks, and vocabulary consistency).
  - Run all focused test suites, focused e2e tests (`tests/e2e/test_personal_pages.py`,
    `tests/e2e/test_website.py`), `npm run check:agent`, `npm run audit:context`, and
    `scripts/audit_emoji.py`.
- **Exit:** all phases marked `done` in `02-PROGRESS.md`, `main` clean and verified.

