# Master prompt: personal ops, coding, family workflows, shipped workflows and daily automations (2026-11)

Paste the "Launch prompt" block at the bottom into a fresh session. Everything above it is the
contract the agent reads. Work sequentially through `01-PHASES.md`; record state in
`02-PROGRESS.md`; consult `03-EDGE-CASES.md` at every design step and `04-RESEARCH-PLAN.md` before
each phase's design. One phase per session where possible (AGENTS.md: fresh session per task, under
about 120K tokens).

## Goal

Make Hutch's personal operations, family/shared workflows, coding orchestration, shipped
deliverable workflows and daily automations honest, complete and usable end to end — including a
governed multimodal pipeline (image, receipt/photo, voice/audio transcription and document intake
across chat, channels, Today and workflows) and the dashboard + paired-phone front-end surfaces
required to operate them daily without a terminal.

"Complete" means a person can:

1. run a daily personal operating loop on `#/today` (commitments, read-only calendar/mail agenda,
   provenance-bound proposals from mail/calendar/photos/voice, and approved one-click calendar
   reminders);
2. coordinate household and family workflows in `#/shared` (scoped spaces, member roles, meal/list
   and deadline templates, explicit per-assistant space grants, and a clear single-owner vs
   multi-participant identity boundary);
3. hand coding work to an isolated worktree (`code_handoff`, `code_review`, `code_prune`), trigger
   or review status from chat/voice/mobile, inspect verification receipts and diffs in the
   dashboard, and prune stale worktrees safely;
4. run shipped, verifiable multi-step workflows (`src/hutch/workflow/`, `src/hutch/catalog.py`) and
   browse all generated documents, media and hash-verified run artifacts in a dedicated
   deliverables surface with deterministic semantic checks;
5. trust daily automations (`src/hutch/scheduler.py`, event/webhook sources, channel outbox
   notifications) with an append-only schedule revision journal, approval checkpoints, bounded
   trigger conditions, per-routine failure observability and a "needs attention" filter;
6. feed real multimodal inputs (receipt/invoice/whiteboard photos, voice notes, PDFs/CSVs) through
   a bounded, provenance-preserving pipeline that never silently drops attachments, never fabricates
   OCR/transcription when a model or runtime lacks capability, and flags untrusted content via
   `src/hutch/ingest.py`.

Reference benchmarks (read as demand signals and failure lessons, never copied wholesale):

- Hutch repo: `https://github.com/K-Arthur/hutch`
- Showcase index: `https://openclaw.ai/showcase`
- `@jdrhyne` (`https://x.com/jdrhyne/status/2012778049406742632`): multi-agent fleet & roll call,
  delegated coding workers, standing daily operations.
- `@danpeguine` (`https://x.com/danpeguine/status/2012565160586625345`): personal OS with daily
  briefings, timeblocking, meeting-note weekly reviews, family/school deadlines.
- `@georgedagg_` (`https://x.com/georgedagg_/status/2012119327147798753`): voice-guided production
  diagnosis, config fix, redeploy and PR while away from a desk.
- `@dreetje` (`https://x.com/dreetje/status/2012535486401671588`): single chat controlling mail,
  messages, reminders, GitHub issues, PDF recaps and a read-only vs read-write vault split.
- `@davekiss` (`https://x.com/davekiss/status/2008994096736817624`): end-to-end site migration and
  deployment orchestrated from Telegram with verifiable deliverables.
- `@stevecaldwell` (`https://x.com/stevecaldwell/status/2007616854689280196`): family meal
  planning, weather-aware weekly menus, aisle-sorted grocery lists and morning/evening digests.

## Starting state (verified 2026-11-06; recheck against HEAD before relying)

Much of the foundation already shipped on `main`. Do not rebuild it; diagnose against it and close
the remaining gaps.

- Prior personal-operations package: `.pipeline/personal-operations/2026-10/` (`00-BRIEF.md`,
  `RESEARCH.md`, `COMPETITIVE-ANALYSIS.md`, `FAILURE-ANALYSIS.md`, `CURRENT-STATE.md`,
  `GAP-REGISTER.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `HANDOFF.md`, `RUNLOG.md`,
  `ACCEPTANCE-CRITERIA.md`). Read first; extend into
  `docs/research/2026-11-personal-ops-workflows/`, never duplicate.
- Personal ops & shared spaces (shipped, schema v85/v84 lineage; current `SCHEMA_VERSION` is 91 in
  `src/hutch/store.py:2454`):
  - `src/hutch/personal/{models,commitments,spaces,store,today,agenda,agenda_sources}.py` and
    `src/hutch/personal_schema.py`.
  - APIs: `src/hutch/server/{personal_api,personal_api_models,personal_agenda_api,personal_spaces_api}.py`.
  - Tools: `src/hutch/tools/commitments.py` (`capture_commitment`, `list_commitments`,
    `report_commitment_done`).
  - UI: `src/hutch/server/static/{today,personal-ui,personal-tools,shared,personal.css}`.
  - Docs: `docs/commitments.md`, `docs/adr/0025-personal-commitments-today-and-shared-spaces.md`.
- Coding orchestration (shipped through G02 slice 1, schema v89):
  - `src/hutch/code_handoff.py` (550 lines, frozen in `.file-size-baseline.json`),
    `src/hutch/code_review.py`, `src/hutch/code_prune.py`, `src/hutch/code_review_schema.py`,
    `src/hutch/cli.py` (`code verify`, `code prune`).
- Shipped workflows, catalog and deliverables:
  - Workflow compiler and engine: `src/hutch/workflow/{plan,compile,engine,ops,persistence,runtime,submit,amendments,probes,qualify,routing,holds,usage_budget}.py`
    and `src/hutch/server/workflows_api.py`.
  - Ready-made assistant catalog: `src/hutch/catalog.py`, `src/hutch/catalog_sources.py`,
    `src/hutch/catalog_export.py`, `src/hutch/data/catalog/*.json`, `src/hutch/server/static/catalog.js`.
  - Synthesis, documents and media: `src/hutch/synthesis/{ingest,authoring,infographic,model,storage,tts}.py`,
    `src/hutch/documents/storage.py`, `src/hutch/media/{jobs,render,routes,storage,validate}.py`.
- Daily automations, channels and notifications:
  - Scheduler: `src/hutch/scheduler.py` (523 lines, frozen), `docs/realignment/routines-plan.md`,
    `docs/realignment/routines-capability-matrix.md`.
  - Sources: `src/hutch/sources/{folder,git,feed}.py`.
  - Channels & notifications: `src/hutch/channels/{service,telegram,persistence,outbox}.py`,
    `src/hutch/notifications.py`, `src/hutch/notification_schema.py`,
    `src/hutch/server/notifications_api.py`.
- Multimodal intake & untrusted-content defense:
  - `src/hutch/providers/attachments.py` (chat image validation, capability checks, wire parts),
    `src/hutch/server/uploads.py` (507 lines, frozen), `src/hutch/grounding/media.py` (491 lines,
    frozen), `src/hutch/tools/{media,media_generation,transcribe,documents,synthesis}.py`,
    `src/hutch/ingest.py` (deterministic prompt-injection/bidi/HTML-comment annotation).
- Sibling prompt packs in flight on this checkout:
  `docs/realignment/offline-models-2026-11/`, `docs/realignment/provider-expansion-2026-11/`,
  `docs/realignment/vault-signin-2026-11/`. Do not modify their files or stage another session's
  work.

## Open gaps to close in this initiative

1. **G03 (Automation trust: revision journal, approval checkpoints, bounded conditions):**
   - Sub-slice 1: append-only `schedule_revisions` table + SQL triggers on `bots`, read-only
     `GET /api/v1/bots/{ref}/schedules/{id}/revisions`, keyboard-accessible History disclosure on
     `#/schedules`.
   - Sub-slice 2: per-schedule `approval_required` flag parking occurrences in `waiting_approval`
     before model/tool execution, reusing `src/hutch/approvals.py`.
   - Sub-slice 3: bounded, declarative trigger conditions (no `eval`, no expression language) for
     source/schedule runs.
2. **G04 (Inbound webhook/event triggers):**
   - Hashed per-source secret (shown once), payload size and content-type bounds, replay/idempotency
     key, loopback/private-bind enforcement, admission into the existing durable source/run inbox,
     and UI/API delivery status.
3. **G06 remainder (Per-routine observability & fleet roll-call):**
   - "Needs attention" filter on `#/schedules`, expandable occurrence history beyond the last
     claimed window, linked workflow-run status per routine, and a fleet roll-call summary (which
     assistant ran, what failed, what is due next, spend/limit state).
4. **G08 & G09 (Personal ops bridges: provenance-bound capture + commitment-to-calendar reminder):**
   - G09: `capture_commitment` accepts a verified `source_ref` (mail message, calendar event,
     uploaded receipt/photo, voice transcript, or document from the same run), validated against the
     run's committed tool/upload records; Today displays "Suggested from <source>".
   - G08: owner-initiated "Add reminder to calendar" on a confirmed commitment through the guarded
     approval + `outcome_unknown` path (`src/hutch/personal/calendar_bridge.py`).
5. **Multimodal pipeline across chat, channels, personal ops and workflows:**
   - Photo/receipt/whiteboard and voice/audio intake -> `ingest.py` untrusted-content scan ->
     structured extraction into proposed commitments, shared-space lists (e.g., grocery/meal items)
     or workflow inputs, with explicit capability preflight (never silently drop an image or audio
     clip when a route lacks vision/STT; surface a typed refusal or route-switch suggestion).
   - Channel multimodal awareness: Telegram (`src/hutch/channels/telegram.py`) currently drops
     all non-text updates silently (`docs/channels.md:27`). Either support bounded photo/voice/file
     intake for allowlisted senders with explicit per-channel opt-in and size caps, or record a
     visible "attachment ignored (text-only channel mode)" receipt so senders never think the bot
     saw their photo or voice note.
6. **G07 & Family/Shared workflows (`#/shared`):**
   - ADR for multi-participant identity (`docs/adr/00xx-multi-participant-identity.md`) defining
     how household members, paired devices, and per-space roles interact without weakening the
     single-owner local security posture.
   - Household workflow templates and shared-space lists/routines (meal planning, shopping lists
     with idempotent item merge, school/family deadline digests, weather/calendar-aware routine
     inputs) built as reviewable catalog/workflow definitions, never hardcoded demo data.
7. **G02 remainder & G11 (Coding orchestration dashboard surface, receipt history & worktree GC):**
   - Dashboard UI for coding handoffs (worktree status, diff/changed-file summary, verification
     receipt history, one-click verify/prune with confirmation, and mobile/voice-friendly status
     inspection for remote remediation flows like E3/E5).
   - Stale worktree inspection (`hutch code list --stale`) and retention visibility in `hutch doctor`.
8. **G10, G12 & G14 (Shipped workflows, Deliverables library, semantic checks & permanent purge):**
   - `#/deliverables` library view + `src/hutch/server/deliverables_api.py` aggregating verified
     documents, media jobs and run artifacts with assistant/date/kind filters.
   - Deterministic `declared_checks` on deliverables (JSON schema, required markdown headings,
     CSV row-count parity, artifact hash) surfaced as `verified` vs `unverified`.
   - G14: permanent scoped deletion (`fact_purge.py` extended to commitments and personal records)
     with content-free tombstones and export-before-purge.
9. **G13 (Paired-phone Today, commitments, approvals and coding/automation status):**
   - Scoped `/api/v1/phone/today` and explicit phone capability entries in `src/hutch/server/security.py`
     so a paired phone can review Today, decide approvals, mark commitments done, and inspect
     running coding/deployment tasks safely.

## Non-negotiable rules

1. **No god functions or god files.** Hard cap 400 lines per new source file (`AGENTS.md`). Every
   function does one thing: aim for 40 lines or fewer, hard stop at 60, and at most 4 branches of
   case-specific `if/elif` (use dispatch tables or small helper modules). Never extend any file in
   `.file-size-baseline.json` (`store.py`, `models.py`, `app.py`, `cli.py`, `scheduler.py`,
   `code_handoff.py`, `uploads.py`, `app.js`, etc.); put new logic in new modules and add at most a
   one-line registration/import where unavoidable, or split the frozen file first
   (`.ai/skills/split-god-file.md`).
2. **Real setup, not fixtures, and never demo data.** Prove every behavior against the real stack:
   a real FastAPI server on a real port, a real SQLite database upgraded through real migrations,
   real local model runtime (Ollama / `llama-server` / LM Studio where available on this host) or
   real subprocess/Git worktree execution, and a real headless Chromium browser via Playwright.
   Never seed demo commitments, fake family members, or canned prompt cards into the product. Mocks
   are permitted only for unit-testing pure parsers or injecting transport failures that a real
   server cannot trigger on demand (HTTP 429, 5xx, mid-stream disconnect, clock jump).
3. **Preserve the local-first, explicit-approval model.**
   - Assistant tools may only *propose* commitments and *report* unverified completions; only owner
     routes confirm or verify (`ADR-0025`).
   - Outward actions (calendar writes, mail sends, webhook registrations, deployments, git pushes)
     bind to one exact approval hash and never auto-retry on `outcome_unknown`.
   - Shared spaces scope data per assistant grant; they never share credentials or imply multi-user
     OS isolation unless the G07 authentication boundary is active.
4. **Untrusted content and multimodal honesty.** All external text, OCR, transcripts, calendar
   titles, mail bodies and webhook payloads pass through `src/hutch/ingest.py` and are marked
   `untrusted`. Never fabricate vision or audio support; never transcribe or OCR silently through an
   unconfigured cloud API.
5. **Contract discipline.** Every new or modified `Tool` defines a canonical JSON Schema in
   `Tool.parameters`, registers in `src/hutch/tools/__init__.py`, redacts secrets in
   `Tool.recorded_arguments`, has contract tests (valid accepted, invalid refused before dispatch),
   and passes `npm run check:agent`.
6. **Persisted state.** Pydantic models plus an ordered, additive migration in `src/hutch/store.py`
   (in its own `*_schema.py` module) with `tests/fixtures/` compatibility coverage and
   `tests/test_migration.py`. All timestamps use `models.iso`/`models.utcnow`, never naive datetimes;
   all user-facing schedules and commitments store and validate an explicit IANA timezone and fail
   closed on unknown zones.
7. **Work on `main` with surgical commits.** Commit directly on `main` (use a temporary worktree
   only if needed to run clean-index audits while another session has staged files in the shared
   checkout, and merge/fast-forward immediately within the same task). Stage explicit paths only
   (`git commit -m "..." -- path1 path2`), never `git add -A`. Never touch another session's
   uncommitted work. Regenerate `.ai/repo-map.generated.md` (`npm run agent:map`) when adding
   tracked files, once the index is clean. No AI-attribution trailers.
8. **No emoji in source, docs or UI** (`scripts/audit_emoji.py`). Edit Tailwind CSS sources in
   `app/src/` and `website/src/input.css`, never generated CSS; run `npm run build:css --silent`
   when CSS sources change. Follow `docs/design-system.md`, `docs/realignment/product-spine.md`
   (canonical vocabulary: "assistant", "run", "Task", "Scheduled work", "Needs you", "Apps & AI")
   and the `impeccable` skill.
9. **Be surgical with context.** Always use `@path/to/file.py` and read specific line ranges. Never
   ask the agent to "review the codebase". Never read lockfiles, `CHANGELOG.md`, generated CSS,
   evidence artifacts, `.worktrees/`, `node_modules/`, or `.venv/`.

## Validation and review gates (run in order at the end of every phase)

1. **Focused tests:** `npm run test:agent -- tests/test_<touched>.py` (must include tests that fail
   before the code change and pass after).
2. **Repository audits:** `npm run check:agent` and `npm run audit:context` (plus
   `uv run --frozen --no-sync python scripts/audit_emoji.py`).
3. **Real-setup end-to-end verification:** start the real Hutch server against a throwaway state
   directory, exercise the phase's real workflow (real SQLite triggers, real Git worktree, real
   local HTTP/webhook client, real multimodal upload/ingestion, real local runtime where
   applicable), and record exact commands, HTTP status codes and DB state in
   `docs/research/2026-11-personal-ops-workflows/06-VALIDATION-LEDGER.md`.
4. **Visual and accessibility validation (mandatory whenever UI or website changes):**
   - Run Playwright against the real server at 360, 768, 1280 and 1920 px in both light and dark
     themes, plus 200% zoom on personal/workflow views.
   - Verify keyboard-only traversal (`Tab`, `Shift+Tab`, `Enter`, `Escape`, focus ring visibility),
     zero console/page errors, and zero horizontal overflow (`scrollWidth <= clientWidth`).
   - Inspect every captured screenshot and log defects found and fixed in `02-PROGRESS.md`.
   - Run focused e2e tests (`uv run --frozen --no-sync pytest -q tests/e2e/test_<touched>.py`).
5. **Skeptical code review:** re-read the full `git diff` of the phase. Hunt for god functions
   (>60 lines), frozen-file growth, naive datetimes, silent fallbacks, unverified completion
   claims, prompt-injection pass-through, missing revision CAS checks, and vocabulary drift
   ("Bot" in UI copy instead of "assistant"). Record findings and fix commits in `02-PROGRESS.md`.
6. **Documentation and website sync:** update `docs/commitments.md`, `docs/workflows.md`,
   `docs/operations.md`, `docs/channels.md`, relevant ADRs, and `website/index.html` (only for
   shipped, dated-verified capabilities, obeying `docs/marketing-site.md`).

## Stop conditions

Ask the owner (batched, once) only for: spending money on paid APIs, missing live credentials,
adding a third-party dependency, an irreversible security boundary change (such as activating
multi-user remote logins beyond the G07 ADR), or pushing/publishing. Otherwise decide, log the
decision and rationale in `02-PROGRESS.md`, and continue.

## Launch prompt (paste into a fresh session)

```
Read, in this order and nothing else first:
@AGENTS.md
@docs/realignment/personal-ops-workflows-2026-11/00-MASTER-PROMPT.md
@docs/realignment/personal-ops-workflows-2026-11/01-PHASES.md
@docs/realignment/personal-ops-workflows-2026-11/02-PROGRESS.md

Then read the relevant sections of:
@docs/realignment/personal-ops-workflows-2026-11/03-EDGE-CASES.md
@docs/realignment/personal-ops-workflows-2026-11/04-RESEARCH-PLAN.md

Resume at the first phase in 02-PROGRESS.md not marked done. Execute only that phase in this
session:
1. Run the mandatory online research and failure/complaint mining for this phase
   (04-RESEARCH-PLAN.md) and record dated sources and requirement IDs under
   docs/research/2026-11-personal-ops-workflows/.
2. Write a concise design note naming the exact @file:line-range targets (at most 3 source files
   plus 1 cross-cutting seam per task; split the phase into sequential tasks).
3. Implement each task in small, surgical commits on main (no god functions >60 lines, no new file
   >400 lines, no frozen-file growth, no emoji).
4. Validate against the real stack (real FastAPI server, real SQLite migrations, real Git worktrees
   and multimodal files, never fixture-only mocks) and run Playwright visual + keyboard + responsive
   validation (360/768/1280/1920 px, light/dark) for any UI or website change.
5. Perform a skeptical code review of the phase diff, fix every defect found, update the relevant
   docs and marketing site claims truthfully, and update 02-PROGRESS.md at each checkpoint.
Finish by stating the completed commits, live verification evidence, and the next phase.
```

