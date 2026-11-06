# Gap audit: personal ops, coding, family workflows, deliverables and daily automations (Phase 0, 2026-11-06)

Audited at commit `07ae7a5b` (HEAD on `main`) against the real stack and live codebase.
Method: direct line-range reads of cited modules, baseline test runs (`pytest` and agent audits),
and live browser capture of target dashboard pages on a real local server with an isolated SQLite state.
No feature code was written.

Labels used throughout this audit:
- **Verified live**: executed against a live FastAPI server, live SQLite migrations, or headless Chromium.
- **Verified in code**: verified by reading exact source lines and ast/schema structures.
- **Not started**: capability does not exist in code or schema.
- **Partially shipped**: foundation or first slice exists on `main`, but key requirements remain open.

---

## 1. Baseline audit summary

| Check | Command | Result | Evidence |
|---|---|---|---|
| Focused test suite | `npm run test:agent -- tests/test_commitments.py tests/test_spaces.py tests/test_personal_api.py tests/test_commitment_tools.py tests/test_code_review.py tests/test_channels.py` | **73 passed** in 54.38s | Real SQLite, real migrations, real tool contracts |
| Agent context & tool hygiene | `npm run check:agent` | **Pass** | 1091 source files, 117 frozen files, 47 tools certified, constitution ok |
| Context size audit | `npm run audit:context` | **Pass** | 1091 files tracked, zero baseline overages |
| Emoji audit | `python scripts/audit_emoji.py` | 8 hits in git-ignored `.codewhale/state/subagents.v1.json` | Zero emoji violations in repository sources or docs |
| Schema version | `src/hutch/store.py:2446-2455` | `SCHEMA_VERSION = 91` | Migration 91 is `route_spec_schema.migrate` |
| Visual baseline | `python docs/realignment/capture_personal_ops_baseline.py` | **40 views captured** | 5 pages x 4 widths (360, 768, 1280, 1920) x 2 themes (dark, light); 0 console errors, 0 horizontal overflow |

---

## 2. Gap register status (G01 to G14)

Comparison against `.pipeline/personal-operations/2026-10/GAP-REGISTER.md` as of 2026-11-06:

### G01. Read-only calendar agenda and mail inbox surface in Today
- **Status:** **Shipped and verified live**.
- **Evidence:**
  - `src/hutch/personal/agenda.py:1-292`: pure builder `AgendaSource`, `_event_item`, `_message_item`, `_empty`, hard unavailable reasons (`grant_missing`, `grant_expired`, `mail_requires_local`), in-memory cache with `FRESH_SECONDS = 300` and `MAX_STALE_SECONDS = 3600`.
  - `src/hutch/server/personal_agenda_api.py:1-120`: route `GET /api/v1/personal/agenda` wired into `app.py:5928-5935`.
  - `src/hutch/server/static/today.js:1-350`: Today agenda card renders events and messages with untrusted badges and unavailable states.
  - Test suites: `tests/test_personal_agenda.py` (22 tests) and `tests/e2e/test_personal_today_agenda.py` pass.

### G02. Coding handoff verification/review gate and worktree lifecycle
- **Status:** **Partially shipped (Slice 1 complete; UI and lifecycle remainder open)**.
- **Evidence:**
  - Shipped: `src/hutch/code_review.py:1-376` (`verify_handoff`, `argv_digest`, `worktree_fingerprint`, `append_receipt`, `latest_receipt`).
  - Shipped: `src/hutch/code_prune.py:1-85` (`prune_handoff` with `--yes` confirmation and `--discard` flag).
  - Shipped: `src/hutch/code_review_schema.py:1-42` (schema v89 `code_handoff_receipts` table).
  - Shipped CLI: `src/hutch/cli.py:270-340` (`hutch code verify`, `hutch code prune`).
  - **Open gaps:**
    - No dashboard UI for coding handoffs (`code-handoffs.js` does not exist); tasks surface only displays raw task cards.
    - No receipt history API endpoint (`GET /api/v1/code-handoffs/{id}/receipts`).
    - Worktrees are retained indefinitely unless manually pruned via CLI; no `hutch code list --stale` command (see G11).
    - `hutch doctor` has no check for stale retained worktrees.

### G03. Automation revision journal, approval checkpoints, and bounded conditions
- **Status:** **Not started**.
- **Evidence:**
  - `src/hutch/store.py:4027-4100`: schedule changes overwrite the Bot JSON document in place.
  - No `schedule_revisions` table or SQL triggers in schema (current `SCHEMA_VERSION = 91`).
  - No API endpoint `GET /api/v1/bots/{ref}/schedules/{id}/revisions`.
  - `src/hutch/models.py:115-186` (`Schedule`): has no `approval_required: bool` field, and no declarative `conditions` field.
  - `src/hutch/server/static/schedules.js` does not exist; schedules are rendered via `app.js:3161-3250` without a history disclosure.

### G04. Inbound HTTP/webhook trigger
- **Status:** **Not started**.
- **Evidence:**
  - `src/hutch/store.py:1446-1512`: `event_sources` supports only `folder`, `git`, and `feed`.
  - `src/hutch/server/channels_api.py:62-68`: explicitly lists webhooks as unavailable.
  - No `webhook_sources` or `webhook_deliveries` tables in schema.
  - No receiver module (`src/hutch/webhook_receiver.py`) or API route (`POST /api/v1/webhooks/{token}`).

### G05. Outbound notifications for needs-you, failures, and results
- **Status:** **Shipped and verified live**.
- **Evidence:**
  - `src/hutch/notification_schema.py:1-120`: tables `notifications` and `notification_deliveries` (schema v87/v88) with SQL triggers on `approvals` and `runs`.
  - `src/hutch/notifications.py:1-100`: `render_notification`, `recent`, `public`.
  - `src/hutch/channels/service.py:51-54`: channel worker automatically drains queued notifications into the configured outbox channel.
  - `tests/test_channels.py` and `tests/test_personal_api.py` pass.

### G06. Per-routine automation observability and fleet roll-call
- **Status:** **Partially shipped (Slice 1 complete; roll-call & history filter open)**.
- **Evidence:**
  - Shipped: `GET /api/v1/schedules` returns `last_occurrence` (run status, exit reason, missed windows) and `needs_attention`.
  - Shipped: `#/schedules` in `app.js` renders the routine card with `needs_attention` tags.
  - **Open gaps:**
    - No "Needs attention" filter on `#/schedules` (all routines are displayed in one flat list).
    - No expandable occurrence history beyond the single last occurrence.
    - No linked workflow-run status per routine.
    - No top-of-page fleet roll-call summary (active/blocked routines, 24h failure count, next due routine, spend/limit state).

### G07. Multi-participant authentication and household identity
- **Status:** **Not started (Requires strategic ADR first)**.
- **Evidence:**
  - `src/hutch/store.py:1296-1298` and `src/hutch/server/security.py:320-345`: security model is strictly single-owner loopback + paired phone.
  - `src/hutch/personal/spaces.py:1-211`: shared spaces are data-scoping boundaries for one owner, with attribution metadata (`adult`, `child`, `guest`), not multi-user accounts.
  - No passkey or session credentials exist per household member.
  - An ADR is required (`docs/adr/0033-multi-participant-household-identity.md`) before any multi-user code is written.

### G08. Commitment to calendar reminder (write path)
- **Status:** **Not started**.
- **Evidence:**
  - `src/hutch/personal/commitments.py:1-326`: commitments have status transitions (`proposed`, `confirmed`, `completed`, `cancelled`) but no external side effect or calendar link.
  - No `src/hutch/personal/calendar_bridge.py` exists.
  - No `POST /api/v1/commitments/{id}/calendar-reminder` route exists in `src/hutch/server/personal_api.py`.
  - Calendar tool writes exist in `src/hutch/tools/google_calendar.py:60-138` but have no bridge to confirmed commitments.

### G09. Mail/calendar/multimodal content to proposed commitment with provenance
- **Status:** **Not started**.
- **Evidence:**
  - `src/hutch/tools/commitments.py:50-115`: `CaptureCommitmentTool` accepts `title`, `detail`, `due_at`, `due_timezone`, `priority`, `category`, and `space`. It does not accept `source_ref`.
  - `src/hutch/personal/models.py:79-150`: `Commitment` model has `source` and `source_detail` string fields, but no structured `source_ref` (`kind`, `item_id`, `sha256_or_etag`, `excerpt`).
  - No server-side validation exists to prove that a claimed message, event, upload, or document actually occurred in the current run.
  - Today UI (`today.js`) lacks provenance badges or "Suggested from <source>" jump links.

### G10. Deliverables library page (`#/deliverables`)
- **Status:** **Not started**.
- **Evidence:**
  - Generated documents (`src/hutch/documents/storage.py`) and media artifacts (`src/hutch/media/storage.py`) exist with individual download routes.
  - No aggregated `src/hutch/server/deliverables_api.py` exists.
  - No `src/hutch/server/static/deliverables.js` exists.
  - Navigation (`src/hutch/server/nav.py`) and `app.js` have no `#/deliverables` destination.

### G11. Code worktree lifecycle and garbage collection
- **Status:** **Partially shipped via CLI prune; inspection & doctor check open**.
- **Evidence:**
  - Shipped: `hutch code prune <id>` in `src/hutch/code_prune.py:1-85`.
  - **Open gaps:**
    - No `hutch code list --stale` dry-run inspection command.
    - No disk usage summary for retained worktrees in `src/hutch/doctor.py`.
    - No API for listing or pruning worktrees from the dashboard.

### G12. Semantic deliverable verification
- **Status:** **Not started**.
- **Evidence:**
  - `src/hutch/documents/storage.py:1-366`: verifies file size and SHA-256 digests, but performs no content inspection.
  - No `declared_checks` (`json_schema`, `required_sections`, `csv_row_bounds`, `non_empty`) exist in document creation or workflow verify nodes.
  - Documents have `cur_validation` defaulted to `unverified` without deterministic automated check pipelines.

### G13. Phone access to Today and commitments
- **Status:** **Not started**.
- **Evidence:**
  - `src/hutch/server/security.py:40-160`: paired-phone capabilities permit `monitor` on runs/frames and `review` on approvals, but list no commitments or Today routes.
  - `src/hutch/server/personal_api.py`: no `/api/v1/phone/today` endpoint exists.
  - `src/hutch/server/static/phone-personal.js` does not exist; paired phone UI cannot review Today, confirm/complete commitments, or check coding task receipts.

### G14. Permanent scoped deletion for personal data
- **Status:** **Not started**.
- **Evidence:**
  - `src/hutch/fact_purge.py:1-339`: governs permanent deletion for memory facts only (`memory_facts`, `memory_fact_shares`, `memory`).
  - Commitments table `commitments` has no permanent purge operation; soft deletion or status archiving leaves content bytes in SQLite.
  - No `export_before_purge` or content-free tombstone flow exists for commitments.

---

## 3. Multimodal intake pipeline seams audit

| Seam | Current File & Line Range | Current Behavior | Gap to Close |
|---|---|---|---|
| Chat image attachments | `src/hutch/providers/attachments.py:1-206` | Max 4 images, 1.5 MB each, PNG/JPEG/WebP only. Magic-byte MIME check and `image_route_refusal`. | Works for chat messages, but is isolated from channels, Today proposals, and workflow inputs. |
| Upload intake store | `src/hutch/server/uploads.py:1-507` | Validates file uploads and stores under state directory. | Lacks unified metadata extraction (SHA-256, EXIF orientation normalization, audio metadata). |
| Audio transcription | `src/hutch/tools/transcribe.py:1-180` | Model tool that calls audio transcription runtime. | Hallucinates phrases on silent audio; no owner verification gate before transcript becomes a proposal. |
| Telegram channel media | `src/hutch/channels/telegram.py:84,97` | `allowed_updates=['message']`; only message text is read. | **Silently drops all photo, voice, audio, and document updates**. Senders are never informed that their media was ignored. |
| Telegram channel service | `src/hutch/channels/service.py:1-97` | Polling and outbox delivery loop for text messages. | No intake path for voice notes or photo attachments into the conversation store. |
| Untrusted-content defense | `src/hutch/ingest.py:1-235` | Scans text for instruction overrides, bidi controls, HTML comments, role impersonation. Preserves bytes, attaches annotations. | Not currently called on calendar event titles, email snippets, OCR text, or incoming webhook payloads. |

---

## 4. Visual baseline audit facts (Phase 0)

From `artifacts/phase0/report.json` across 40 captures:

- **Target views:** `#/today`, `#/shared`, `#/schedules`, `#/tasks`, `#/catalog`.
- **Viewports tested:** `360x800` (mobile), `768x1024` (tablet), `1280x800` (laptop), `1920x1080` (desktop).
- **Color schemes:** `dark` and `light`.
- **Console errors:** `0` on all 40 views.
- **Horizontal overflow:** `0` px on all 40 views (`overflow_x == 0`).
- **Focusable element counts:**
  - `#/today`: 45 focusable elements (nav items, filter buttons, commitment action buttons).
  - `#/shared`: 45 focusable elements.
  - `#/schedules`: 41 focusable elements.
  - `#/tasks`: 41 focusable elements.
  - `#/catalog`: 41 focusable elements.

All captured screenshots and machine metrics are archived in `docs/research/2026-11-personal-ops-workflows/artifacts/phase0/`.
