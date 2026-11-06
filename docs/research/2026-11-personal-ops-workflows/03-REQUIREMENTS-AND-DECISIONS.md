# Requirements and decisions: personal ops, family workflows, coding, deliverables, automations and multimodal intake (Phase 1, 2026-11-06)

Every later phase cites the `POW-R*` ids below. A requirement is written as a testable statement,
names the evidence that produced it, and names the test story that will prove it. Evidence ids are
in `01-SOURCES.md`; failure ids are in `02-FAILURES-AND-COMPLAINTS.md`.

Conventions:

- "MUST" is a release gate for the phase named in the heading.
- A requirement with a model-provider or third-party dependency also names the honest limit in its
  test story. No requirement promises model correctness.
- No new dependency is authorized by this document. All work uses the standard library and existing
  project dependencies.

## 1. Phase 2 - automation trust and observability (G03, G06)

| Id | Testable requirement | Evidence | Test story |
|---|---|---|---|
| POW-R1 | The database has an append-only `schedule_revisions` table. A SQL trigger writes exactly one row when the schedules JSON on `bots` changes and zero rows for a no-op save. `UPDATE` and `DELETE` on the journal are refused by trigger | B1, C6, D6 | `revision-journal`: API edit -> one row; no-op save -> zero; direct update/delete -> refused |
| POW-R2 | `GET /api/v1/bots/{ref}/schedules/{id}/revisions` returns revision rows with Python-computed changed fields and SHA-256 hashes. It is read-only and returns no host paths or secrets | B1, C6 | `revision-diff`: two edits produce a field-level diff with the expected hash |
| POW-R3 | A schedule with `approval_required` parks each occurrence in `waiting_approval` before any model or tool call. One notification is emitted. An undecided approval expires fail-closed and executes nothing | B4, D2 F10 | `approval-park`: run a schedule; assert no model call before a decision, one notification, expiry denies |
| POW-R4 | Schedule/source conditions use a closed schema of allowed keys and literal comparisons. Unknown keys or operators are rejected at save. No `eval`, `exec`, `compile` or expression language is used | D2 F1, C7 | `condition-schema`: valid literal accepted; `__import__`, unknown key and nested expression rejected before save |
| POW-R5 | `#/schedules` provides a keyboard-operable "Needs attention" filter and per-routine occurrence history beyond the currently rendered last window | C6, C7, D6 G06 | `attention-filter`: keyboard traversal reaches the filter; a failed routine appears; history expands with Enters and closes with Escape |
| POW-R6 | A top-of-page roll call reports active and blocked routines, last-24h failures, next due routine, and spend/limit state from stored rows, not from model output | A3, C6, D1 P7 | `roll-call`: seeded rows produce exact counts; a failed routine changes the count once |
| POW-R7 | A watchdog compares each routine's last successful occurrence with its expected gap. Overdue and missed windows are visible; "trigger is active" is never presented as health | C6, C7 | `silent-cron`: stop the trigger; after 2x the gap the routine is overdue with last-seen age and a next action |
| POW-R8 | Schedules require an IANA timezone. The UTC instant is stored with the zone. A 23-hour and a 25-hour day each produce exactly one occurrence per absolute instant, with a documented fold choice for the repeated hour | C20, D2 F3/F4 | `dst-23-25`: New York 2026-03-08 02:30 and 2026-11-01 01:30; one run each; no duplicate |

## 2. Phase 3 - inbound webhooks and event triggers (G04)

| Id | Testable requirement | Evidence | Test story |
|---|---|---|---|
| POW-R9 | A per-source secret is generated once, stored only as a SHA-256 hash with a prefix id, and shown once at creation. Verification uses a constant-time comparison. Rotation keeps a dual-validation window and records both secret ids | C9 | `secret-once`: create -> secret shown once; list -> no secret; rotate -> old secret valid only during the window |
| POW-R10 | The receiver rejects bodies over 64 KB before JSON parsing. Only `application/json` and `text/plain` are accepted. Oversize is 413, unsupported type 415, and no partial parse occurs | C9 | `webhook-bounds`: 65 KB -> 413; `text/html` -> 415; 64 KB exactly -> parsed |
| POW-R11 | The idempotency key is claimed atomically in the same transaction as admission. A duplicate returns 200 with no new run. A new key processes. The key TTL covers the retry window and a crash after claim is recoverable | C8 | `replay-5x`: one side effect, five 200s; new key -> second run; crash-after-claim -> retry processes |
| POW-R12 | Admitted events enter the existing durable source/run inbox. A paused source rejects before any write. The receiver is bound to loopback/private interfaces and warns explicitly if exposure is requested. A source cannot trigger itself beyond the configured rate | A2, D2 F1, C9 | `self-trigger`: source A posts to its own webhook; chain stops at the configured rate and shows a loop-guard state |
| POW-R13 | All webhook text passes `src/hutch/ingest.py` before prompt admission. It is marked untrusted, bounded in length, and never auto-approved or interpolated into a system prompt | D2 F8, D5, B4 | `injected-webhook`: payload with "ignore previous instructions" is annotated and cannot approve an action |
| POW-R14 | The management surface shows delivery status, attempts, last error and replay id, and supports pause, resume and rotation. Secret display is one-time. An explicit network-exposure warning is shown | C9 | `webhook-ui`: pause stops admission; delivery log shows the failed attempt; rotation warning is visible at 360 px |

## 3. Phase 4 - multimodal intake across chat, channels and Today

| Id | Testable requirement | Evidence | Test story |
|---|---|---|---|
| POW-R15 | Every intake record carries SHA-256, declared MIME and sniffed MIME. A mismatch is rejected. Size limits are enforced. EXIF orientation is applied to pixels, and GPS/camera metadata is stripped before storage and model admission | C13, D6 | `exif-upright`: orientation 6 image OCRs upright; stored metadata has no GPS; `.png` containing HTML is rejected |
| POW-R16 | Route capability is checked before admission. A text-only route with an image or audio attachment returns a typed refusal naming the route and attachment, offers a route switch, sends no prompt and creates no run | D6, D2 F18 | `route-refusal`: PNG to text-only -> typed refusal; no run row; draft and attachment preserved |
| POW-R17 | Telegram photo, voice, audio and document updates from allowlisted senders are never silently ignored. Default text-only mode records a deterministic visible notice back to that sender. Opt-in media mode enforces a per-channel size cap, checks `file_size` before `getFile`, stores provenance, and never retries a permanent oversize. Non-allowlisted senders get no reply and no processing | C15, D6 | `telegram-nontext`: allowlisted photo -> visible text-only notice; 30 MB document -> size refusal before download; 2 MB image with opt-in -> intake record; stranger -> no reply |
| POW-R18 | Transcription applies a low-signal check (VAD or `no_speech`/compression/logprob thresholds) and a repeated-phrase detector. A low-signal or suspected-hallucination transcript is marked unverified and cannot become a commitment or command without owner confirmation | C12, D2 F11 | `silent-audio`: 5 s silence produces no fabricated sentence; a noisy clip is marked unverified |
| POW-R19 | OCR extraction validates ambiguous dates, currency/decimal parsing, and subtotal + tax = total. Inconsistent rows are flagged unverified and never auto-create a commitment or execute a command | C14, C18 | `receipt-fields`: DD/MM receipt flagged; total mismatch flagged; no commitment row |
| POW-R20 | `src/hutch/ingest.py` scans OCR text, transcripts, PDF text layers and hidden layers. Annotations are preserved and surfaced; untrusted content never inherits the owner's authority | D2 F8, D5, B4 | `injected-ocr`: injected text is annotated; the tool call still requires approval |
| POW-R21 | Chat and Today render attachment provenance, extraction/transcription previews, untrusted warnings and capability-refusal banners. The controls are keyboard-operable and do not overflow at 360 px or 200% zoom | C19, D4, D6 | `multimodal-ui`: keyboard path to preview and warning; 360 px `scrollWidth <= clientWidth` |

## 4. Phase 5 - provenance capture and calendar reminders (G08, G09)

| Id | Testable requirement | Evidence | Test story |
|---|---|---|---|
| POW-R22 | `capture_commitment` accepts a structured `source_ref` with a closed `kind` enum, `item_id`, `sha256_or_etag`, and a bounded `excerpt`. Unknown kinds and oversize fields are rejected by the canonical schema | A4, A6, D6 G09 | `source-ref-schema`: valid ref accepted; unknown kind and 8 KB excerpt refused before dispatch |
| POW-R23 | The server validates `source_ref` against the run's committed tool results or conversation uploads. Unknown ids, wrong kinds and digest mismatches are rejected before any DB write | D6 G09, D2 F11 | `forged-source-ref`: fabricated mail id -> 422; mismatched SHA-256 -> 422; zero commitment rows |
| POW-R24 | Today renders "Suggested from <source>" with a jump link to the source. The excerpt is shown as untrusted text and is never treated as an instruction | A4, D6 G09 | `today-provenance`: proposed commitment shows source label and link; injected excerpt has no action |
| POW-R25 | `POST /api/v1/commitments/{id}/calendar-reminder` is available only for confirmed and open commitments with `due_at` and a valid IANA `due_timezone`. It is owner-initiated, uses an exact-action approval, never auto-retries on `outcome_unknown`, and stores the external receipt on the commitment event log | B2, B3, D2 F5 | `calendar-reminder`: proposed/cancelled/missing-zone refused; confirmed creates one approval; ambiguous outcome becomes `outcome_unknown` |
| POW-R26 | A calendar write uses a stable action key. Before writing it checks for an existing receipt; after an ambiguous outcome it reconciles instead of duplicating. Repeating the same request returns the same receipt | B2, C8 | `calendar-idempotent`: 5x same request -> one event, one receipt; provider copy labelled as a sync copy |
| POW-R27 | A missing or expired OAuth grant produces an explicit `grant_missing` or `grant_expired` state and evicts the cached agenda. Today never shows a stale snapshot or an empty list as authoritative | B3, D6 G01 | `grant-expired`: revoke token; reason shown, cache empty, no "nothing today" |

## 5. Phase 6 - household identity and shared workflows (G07)

| Id | Testable requirement | Evidence | Test story |
|---|---|---|---|
| POW-R28 | An ADR defines the principal model, per-member passkey/session capabilities, space-scoped query enforcement, how single-owner loopback interacts with household members, and why shared spaces remain single-owner scopes until member auth is enabled | D3, D5, C5 item 11 | `adr-review`: ADR names every boundary and a testable claim; no code activates member auth |
| POW-R29 | Shared list items have a deterministic dedupe key (normalized title + category + space + active window). A repeated weekly run upserts or merges and records a merge event; it never creates duplicate rows | A8, C3, C5 item 12 | `merge-twice`: same plan twice -> one item row; merge event recorded; different category -> separate row |
| POW-R30 | Concurrent edits use revision CAS or a documented deterministic merge. A conflict returns 409 with a reload path. A delete does not reappear. Item attribution is preserved | C2, C3, C5 item 14 | `ghost-item`: delete and concurrent edit; delete wins, 409 on the stale editor, no ghost row |
| POW-R31 | Household templates are reviewable catalog/workflow manifests with bounded inputs, deterministic week/date mapping and no demo data. Installation requires an owner review; weather and calendar inputs are optional and bounded | A8, D3, D6 | `meal-manifest`: manifest parses, unknown tool rejected, install opens review, two runs for one week do not duplicate |
| POW-R32 | Outbound notifications go only to allowlisted sender ids selected by the owner. One digest per window, quiet hours honored, alert text generic, and no arbitrary third-party phone/email messaging | A4, C5 item 7, D2 F10 | `recipient-allowlist`: unlisted recipient refused; 20 due items -> one digest; alert has no private text |
| POW-R33 | The shared UI states that a space scopes assistant data on a single-owner server. Member roles are attribution metadata until the ADR boundary is active. Per-assistant grants are visible and revocable | C5 item 11, D3 | `space-scope`: ungranted assistant refused; UI copy and grant list match the real boundary |

## 6. Phase 7 - coding orchestration, receipts and worktree lifecycle (G02, G11)

| Id | Testable requirement | Evidence | Test story |
|---|---|---|---|
| POW-R34 | Worktree inspection reports age, byte size, branch, dirty state, alive-runner state, latest receipt, and category: registered-but-missing, unregistered directory, or orphan branch | C10 | `stale-worktrees`: three categories created; each is classified correctly and never merged into one bucket |
| POW-R35 | Prune is dry-run by default and requires explicit confirmation. It never deletes unmerged or unpushed work without a force flag. Symlink, device/inode and worktree-root identity checks are enforced; a refusal leaves all work intact | C10 | `prune-refusal`: dirty/unpushed prune refused; force path requires a second explicit confirmation; symlink escape refused |
| POW-R36 | The API lists handoffs, returns receipts, verifies and prunes. Responses include a changed-file summary and a bounded status suitable for phone or voice, with no secrets or raw shell | A3, A5, D6 G02 | `phone-coding-status`: changed-file count, latest exit code and duration; no secret fields |
| POW-R37 | A verification receipt binds to the current tree fingerprint. Editing the tree after a passing receipt reverts the status to unverified. Status is `changes_ready` until a real passing command is recorded, never `verified` on the model's claim | C11, D2 F11 | `receipt-binds-tree`: exit 0 with changes -> changes_ready; verify -> verified; edit -> unverified |
| POW-R38 | `hutch doctor` reports worktree count, total bytes and oldest age. `hutch code list --stale` exists and is read-only | C10, D6 G11 | `doctor-worktrees`: seeded stale worktree appears in both outputs; neither deletes anything |
| POW-R39 | Verify and prune refuse while the coding process group is alive. The run remains nonterminal until cleanup is verified. Process-group identity is checked, not just the pid | D4 #133062, D2 F1/F12 | `process-group-cleanup`: live child -> refusal; timeout -> group dead; run terminal only after cleanup |

## 7. Phase 8 - deliverables, semantic checks and permanent purge (G10, G12, G14)

| Id | Testable requirement | Evidence | Test story |
|---|---|---|---|
| POW-R40 | A deliverables library aggregates generated documents, media jobs and run artifacts with filters by assistant, kind, validation state and date. Links are stable and hash-verified; they do not expire with the chat | C16, C17, D6 G10 | `deliverable-after-chat`: workspace destroyed; link still serves verified bytes |
| POW-R41 | `declared_checks` (`json_schema`, `required_sections`, `csv_row_bounds`, `non_empty`) run deterministically at creation. A failure sets `validation_state=failed` and blocks the Validated badge | C16, C18, D6 G12 | `csv-row-parity`: declared 100 rows, actual 99 -> failed; schema mismatch -> failed |
| POW-R42 | Download re-verifies SHA-256 and size. A corrupted or missing file is refused with an honest integrity error; no partial or altered bytes are served | C16, D6 G12 | `hash-mismatch`: alter one byte -> integrity error; delete file -> missing error |
| POW-R43 | Owner purge exports first, deletes content bytes, uses `secure_delete` with a checkpoint before `VACUUM`, leaves a content-free tombstone, and verifies a unique secret is absent from DB and WAL bytes | B5, B6, D6 G14 | `purge-bytes`: unique secret -> zero DB/WAL hits; export exists; foreign keys intact |
| POW-R44 | Workflow and scan partiality propagates: `paths_complete`, `truncated`, skipped item keys and `complete:false` reach the result and UI. A clipped scan is never rendered as complete | C7, D6 G10 | `partial-run`: failed map item and clipped folder both produce partial state |
| POW-R45 | Deliverables are searchable and filterable by assistant, kind, date and validation state with a provenance link. The list is not an unfiltered flat pile | C17 | `find-deliverable`: 100 items, find one by assistant and date in at most two interactions |

## 8. Phase 9 - paired phone, docs and marketing (G13)

| Id | Testable requirement | Evidence | Test story |
|---|---|---|---|
| POW-R46 | A scoped phone API exposes Today, commitments, approvals and coding/automation status with explicit capabilities. It permits view, mark-existing-done, and decide an existing approval; confirming a new obligation, schedules, settings, shell and secrets remain local-owner-only | A4, A5, C19, D6 G13 | `phone-capabilities`: allowed routes 200; confirm-new, schedule and shell routes 403; approve/deny an existing approval 200; no secret fields in payloads |
| POW-R47 | A pending approval or question is reachable at 360 px and is not hidden by a call or navigation overlay. Keyboard traversal, focus ring, touch targets, 200% zoom and zero horizontal overflow are verified | C19, D4, D6 | `mobile-approval-visible`: 360 px with overlay open; approval focused and actionable; no overflow at four widths |
| POW-R48 | Documentation and marketing copy map each claim to shipped, tested behavior and link the relevant limit. No emoji. No "verified" claim without a receipt | A1, D3, D6 | `claim-audit`: every claim row has a test or a dated evidence link; emoji audit clean |

## 9. Decisions

| Id | Decision | Rationale | Rejected alternative |
|---|---|---|---|
| POW-D1 | Store schedule revisions in a new append-only table written by SQL triggers on `bots`, not by application logging | B1 shows settings changes are the exact thing workflow history misses; API, CLI and direct DB writes all pass the trigger. App logging misses at least one caller | App-layer audit only (silently incomplete); full event sourcing of the bot document (large, migration-heavy) |
| POW-D2 | Park a schedule occurrence in `waiting_approval` before model or tool execution, not after the run starts | B4 shows overeager actions and a 93% approval rate; an approval after the work is theater. `ApprovalGate` already owns the waiting state (`src/hutch/approvals.py:55-189`) | Approval after the first model turn (too late); per-schedule blanket allow (no action binding) |
| POW-D3 | Conditions are a closed literal schema, never an expression language | C7 and D2 F1 show silent and runaway behavior; D2 F8 shows untrusted content reaching authority. A closed schema is auditable and cannot execute code | `eval`, a DSL, or model-interpreted conditions (injection and observability risk) |
| POW-D4 | Store only a hashed webhook secret; show it once; verify in constant time; rotate with a dual window | C9. The owner never needs the secret back, and a database read must not yield a usable token | Encrypted-at-rest with owner reveal (more key management, no benefit for a one-time token) |
| POW-D5 | Claim an idempotency key atomically in the same transaction as admission and return 200 on duplicates | C8. Check-then-act races under provider retries; a 4xx on a duplicate causes more retries | Dedup in memory (lost on restart); dedup after side effects (too late) |
| POW-D6 | Refuse a media attachment before admission when the route lacks capability; never silently downgrade to text | D6 and C15. A prompt that arrives without its attachment is a false success | Strip the attachment and send the text (silent data loss); send and hope the provider ignores it |
| POW-D7 | Normalize EXIF orientation on pixels, strip GPS/camera metadata, and mark OCR/transcripts unverified until the owner confirms | C12, C13, C14. The upload path is exactly where EXIF is skipped, and low-signal audio has a reproducible hallucination class | Trust the model's OCR/transcript (silent fabrication); keep full EXIF (privacy leak) |
| POW-D8 | Validate `source_ref` against the run's committed tool results and uploads; store a bounded excerpt as untrusted | D6 G09. Without server-side proof, a model can fabricate provenance and the UI would launder it | Trust the model's string (fabrication); store the whole source body (privacy and size risk) |
| POW-D9 | Calendar writes are exact-action approvals with a stable idempotency key and a receipt; `outcome_unknown` is terminal for the attempt | B2, B3, D2 F5. Provider duplicate copies already exist by design; Hutch must not add more, and an ambiguous send must not replay | Auto-retry after timeout (duplicate events); blind write with no receipt (unreconcilable) |
| POW-D10 | Shared lists are one server-scoped record with upsert merge, not per-device copies reconciled later | C3. Local-copy reconciliation is the documented cause of duplicates, ghosts and per-device crossed-off state | Offline-first local copies (fails exactly when two people edit); append-only log without merge keys (duplicates) |
| POW-D11 | Worktree GC is dry-run by default and never deletes unmerged or unpushed work without an explicit force flag | C10. Auto-cleanup has already deleted live and unpushed work in reported cases; deletion is irreversible | Automatic cleanup on exit (reported data loss); never clean (disk exhaustion) |
| POW-D12 | Declared deliverable checks run at storage time; a failed check sets `validation_state=failed` | C16, C18. A green "complete" badge on a truncated CSV is worse than a visible failure | Trust the generator (false green); human review only (does not scale, no deterministic evidence) |
| POW-D13 | A paired phone can view Today, complete or view existing items, and decide an existing approval, but cannot confirm a new obligation or change schedules/settings | The owner-input default and the local-first posture. Deciding an existing request is bounded; confirming an obligation is an authority change, and a phone session is a narrower capability | Full owner parity on the phone (widens the security boundary without an ADR); view-only (fails the away-from-desk need) |
| POW-D14 | Telegram stays text-only by default and records a visible notice; media intake is per-channel opt-in | C15 and D6. Silent drops are the current defect; default media download increases attack surface and size failure modes | Default media intake (surprise bandwidth and privacy exposure); no notice (current silent failure) |
| POW-D15 | No new dependency; use the standard library and existing project dependencies | `AGENTS.md` and the master prompt. Every requirement above is implementable with the existing stack | Adding a workflow engine, queue or OCR SDK (dependency and supply-chain cost without a proven need) |
| POW-D16 | Purge exports first, then uses `secure_delete` with a checkpoint before `VACUUM`, and leaves a content-free tombstone | B5, B6. A normal delete leaves recoverable bytes; the WAL is part of persistent state; foreign keys need a row | Normal delete plus status archive (bytes remain); dropping the table (breaks references) |
| POW-D17 | Schedule policy (`approval_required`, conditions, revision) lives in a new sidecar table keyed by `(bot_id, schedule_id)`, not as new fields on `Schedule` | `src/hutch/models.py` is frozen at 828 lines. A sidecar also gives the policy its own CAS revision, which a nested JSON field would not have cleanly | Extending frozen `models.py` (forbidden); overloading the bot document (no independent revision) |

## 10. Phase 1 task split and verification

Phase 1 is documentation only. No source file changed.

| Task | Output | Status |
|---|---|---|
| 1A | `01-SOURCES.md`: dated source ledger with evidence grades and requirement effects | complete |
| 1B | `02-FAILURES-AND-COMPLAINTS.md`: 48 clustered failure classes with classification and named test story | complete |
| 1C | `03-REQUIREMENTS-AND-DECISIONS.md`: 48 requirements, 17 decisions and this traceability | complete |
| 1D | `02-PROGRESS.md` update; `npm run check:agent` and `python scripts/audit_emoji.py`; commit on `main` | complete when the commit lands |

Verification for this phase:

- `uv run --frozen --no-sync python scripts/audit_emoji.py` must report no repository hits.
- `npm run check:agent` must pass (context hygiene and tool contracts).
- `npm run audit:context` must report no new baseline overage.
- A link and id check: every `POW-R*` cited in `02-FAILURES-AND-COMPLAINTS.md` exists below; every
  source effect id exists in the requirement tables.

## 11. Handoff design targets for Phase 2 (do not implement in Phase 1)

These are the exact targets the next session should read before writing code. Frozen files are
named so the next task can either add at most one registration/call line or split first.

**Task 2A - schedule revision journal**

- New `src/hutch/schedule_history_schema.py`: `schedule_revisions` table, insert/update trigger on
  `bots` when the extracted schedules JSON changes, no-op guard, and `UPDATE`/`DELETE` refusal
  triggers. Keep the module under 400 lines.
- Register one entry in `@src/hutch/store.py:2445-2454` (`_MIGRATIONS`). `store.py` is frozen at
  12,593 lines; do not add logic there.
- New `src/hutch/server/schedule_history_api.py`: read-only revisions route with Python-computed
  changed fields and hashes.
- Wire one line in `@src/hutch/server/app.py:3259-3275` next to `list_schedules`. `app.py` is frozen
  at 7,461 lines; one registration line is the cap.

**Task 2B - approval checkpoints and bounded conditions**

- New `src/hutch/schedule_policy_schema.py`: a sidecar `schedule_policies` table keyed by
  `(bot_id, schedule_id)` with `approval_required`, `conditions_json`, `revision` and timestamps.
  This avoids growing frozen `src/hutch/models.py:115-175` (`Schedule`).
- New `src/hutch/schedule_conditions.py`: closed literal evaluator, unknown-key rejection and
  bounded values. No `eval`/`exec`.
- Reuse `@src/hutch/approvals.py:55-189` for the waiting state and expiry. Do not add a second
  approval store.
- Admission seam is `@src/hutch/engine.py:1467-1537` (`scheduler_claims`) and
  `@src/hutch/engine.py:1539-1620` (`run_schedule_now`). `engine.py` is frozen at 1,837 lines. Add
  at most one call line to a new `src/hutch/schedule_admission.py`; if the park/decide logic cannot
  fit in one call, split `scheduler_claims` into the new module first (`.ai/skills/split-god-file.md`).

**Task 2C - schedules surface**

- New `src/hutch/server/static/schedules.js`: needs-attention filter, history disclosure, linked
  run status and roll-call. Keep it under 400 lines; no polling faster than 30 s and pause when
  `document.hidden`.
- Edit Tailwind sources under `app/src/` only; rebuild with `npm run build:css --silent`. Do not
  touch generated `src/hutch/server/static/ui.css`.
- The current render seam is `@src/hutch/server/static/app.js:3161-3250`. `app.js` is frozen at
  14,532 lines. Load the new module from a template script tag plus a mount point; do not grow
  `app.js`.

## 12. Open questions and owner inputs

| Item | Default if the owner does not answer | Why it matters |
|---|---|---|
| Live Google Calendar, Gmail, Outlook and Telegram credentials | Stay `implemented-unverified (blocked: no live credential)` | The calendar bridge, mail provenance and channel media rows cannot be proven live without them |
| Phone confirmation of new commitments | View and complete only; confirmation stays local-owner | POW-D13. Answering "yes" would require a capability and ADR change |
| Telegram media intake default | Text-only with a visible notice; opt-in per channel | POW-D14 |
| Additional third-party dependency | None | POW-D15 |
| Public marketing update timing | Only after the phase behavior is live-verified | POW-R48 |

## 13. Phase 1 exit criteria

- `01-SOURCES.md`, `02-FAILURES-AND-COMPLAINTS.md` and `03-REQUIREMENTS-AND-DECISIONS.md` are
  committed on `main`.
- Every failure row names one of `fixable-in-Hutch`, `mitigable` or `external-limit`, and a test
  story.
- Every requirement has a source effect, a test story and a phase.
- `02-PROGRESS.md` marks Phase 1 done with the commit hash and exact command output.
- No source file changed; no new dependency; no emoji.
