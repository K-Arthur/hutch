# Edge cases and gaps to account for (2026-11)

Check every row below during phase design and again during the skeptical code review. Every row must
either have a named test recorded in `02-PROGRESS.md` or be explicitly logged as deferred with a
reason.

## 1. Personal ops, commitments & Today (`src/hutch/personal/`)

| Edge case / gap | Expected Hutch behavior |
|---|---|
| Assistant claims it "added to your commitments" or "completed your task" | `capture_commitment` creates only `confirmation="proposed"`; `report_commitment_done` creates only `completion_kind="unverified"`. Tool output and UI state explicitly distinguish proposals and unverified reports from owner-confirmed state |
| Forged or hallucinated `source_ref` in `capture_commitment` (G09) | Server verifies `source_ref` against committed tool results or conversation uploads in the same run; rejects unknown IDs or mismatched SHA-256 digests before any DB write |
| Prompt injection inside a calendar event title, email snippet, or OCR'd receipt | Passed through `src/hutch/ingest.py`; control characters stripped, bounded length, marked `untrusted: true`, never interpolated into system prompts or auto-approved |
| Missing or invalid IANA timezone (`""`, `"PST"`, `"GMT-8"`, `"Mars/Phobos"`) | Fail closed with HTTP 422 (`InvalidTimezone`); never fall back silently to UTC or server local time |
| 23-hour spring-forward and 25-hour fall-back DST days | `day_bounds` computes local midnight per date boundary (`today.py:39-50`); commitments due during a skipped spring-forward hour or ambiguous fall-back hour preserve their exact UTC instant and display zone |
| Concurrent edit of a commitment in two browser tabs or phone + desktop | `expected_revision` CAS check fails with HTTP 409 (`RevisionConflict`); UI prompts to reload instead of overwriting |
| Circular or deep dependency chains between commitments | Reject self-dependency and cycles (`A -> B -> A`) at write time; cap `dependencies` at `MAX_DEPENDENCIES` (20) |
| Commitment-to-calendar reminder (G08) fails with network timeout after HTTP request sent | Recorded as `outcome_unknown`, never automatically retried (prevents duplicate calendar events); UI shows reconciliation instructions |
| Revoked or expired Google/Outlook OAuth grant on Today agenda | Immediate cache eviction (`HARD_UNAVAILABLE` in `agenda.py:37`); shows explicit `grant_missing` or `grant_expired` reason, never a stale snapshot or an empty "nothing today" list |
| Permanent purge of a sensitive commitment (G14) | Removes title, detail, completion evidence and event payload bytes from SQLite while leaving a content-free tombstone so foreign keys and run references do not break |

## 2. Family & shared household workflows (`src/hutch/personal/spaces.py`)

| Edge case / gap | Expected Hutch behavior |
|---|---|
| Assistant tries to read or propose into a family space it was not granted | `_space_for` checks `bot_space_grants` (`tools/commitments.py:32-48`); refuses and lists only spaces granted to that assistant |
| Shared space is archived while an assistant run is in flight | Archiving deletes `bot_space_grants` rows immediately inside the transaction (`spaces.py:133`); the next tool call in the in-flight run fails closed |
| Weekly meal-planning or grocery workflow runs twice for the same week (E6 pattern) | Shared-space list/commitment items use deterministic deduplication keys (normalized title + category + space + active window) so repeated runs merge/update rather than creating duplicate grocery items |
| Spouse or family member notification (E2/E6 pattern) | Outbound channel notifications go only to allowlisted sender IDs that personally sent a start message and were explicitly selected by the owner (`docs/channels.md:12-17`); no arbitrary third-party phone/email messaging |
| Misleading "multi-user security" impression on `#/shared` | UI and docs state clearly that a space scopes assistant data on a single-owner server; member roles (`adult`, `child`, `guest`) are attribution and policy metadata until G07 multi-participant auth is active |

## 3. Coding orchestration & worktree lifecycle (`code_handoff.py`, `code_review.py`, `code_prune.py`)

| Edge case / gap | Expected Hutch behavior |
|---|---|
| Coding CLI exits 0 with modified files, or model claims "all tests pass" | Status is `changes_ready`, never `verified`, until the owner runs `hutch code verify` (or the dashboard verify action) and a passing exit-code 0 receipt is recorded against the current tree fingerprint |
| Worktree files are modified *after* a passing verification receipt | Tree fingerprint (`code_review.py`) no longer matches the receipt; status reverts to unverified for the new tree state and `prune` warns that unverified changes exist |
| `verify` or `prune` invoked while the coding CLI process group is still alive | Refused immediately by checking process-group liveness and identity (`procguard.py`) |
| Symlink escape or swapped directory inside `<state>/code-worktrees/<id>` | Prune verifies device/inode/root identity and refuses to follow symlinks outside the worktree root |
| Disk fills up from dozens of retained coding worktrees (G11) | `hutch code list --stale` and `hutch doctor` report count, age and total disk bytes of retained worktrees; pruning is always explicit and confirmed, never a silent background deletion of unmerged code |
| Voice or mobile-triggered coding status check while away from desk (E3/E5 pattern) | Paired phone and channel summaries expose bounded status (handoff state, changed-file count, latest receipt exit code and duration) without exposing raw secrets or allowing unauthenticated shell execution |

## 4. Shipped workflows & deliverables (`src/hutch/workflow/`, `src/hutch/documents/`)

| Edge case / gap | Expected Hutch behavior |
|---|---|
| Workflow `list_files` or `read_file` clips output on a large repository/folder | `paths_complete: false` and `truncated: true` propagate into `document_coverage`; workflow result is marked partial, never presented as a complete scan |
| Map node receives duplicate item keys or one worker item fails | Duplicate keys fail before any item body executes (`workflow/compile.py`, `workflow/engine.py`); `on_item_failure: "skip"` records skipped keys and reasons with `complete: false` |
| Generated document (PDF/XLSX/PPTX/SVG/Markdown) is empty, malformed, or misses required sections (G12) | Deterministic `declared_checks` run at storage time; failure sets `validation_state="failed"` and surfaces exact findings on `#/deliverables` and Today |
| Artifact file on disk is modified or deleted after the run finishes | SHA-256 verification on `#/deliverables` download detects mismatch and refuses to serve corrupted bytes, showing an honest integrity error |
| Catalog entry (`hutch.catalog/1`) requests unknown tools or dangerous command rules | `parse_manifest` (`catalog.py:104-113`) rejects unknown tools/fields; installing an entry always opens the owner review/setup screen and never auto-executes |

## 5. Daily automations, schedules & webhooks (`scheduler.py`, `sources/`, `channels/`)

| Edge case / gap | Expected Hutch behavior |
|---|---|
| Host machine is asleep or powered off across multiple cron occurrences | Scheduler claims only the true newest occurrence (`routines-plan.md`), records `missed_windows` (and `missed_uncertain` when capped), and never fires a retry storm on wake |
| Schedule edited via CLI or API without an audit trail (G03.1) | SQL trigger on `bots` writes an append-only `schedule_revisions` row whenever the extracted schedules JSON changes; no-op saves write zero rows; `UPDATE`/`DELETE` on `schedule_revisions` is blocked by trigger |
| Standing automation has consequential tools and runs while owner is away (G03.2) | When `approval_required` is set on the schedule (or a tool call requires approval), the run parks in `waiting_approval`, fires one outbox notification, and expires fail-closed if undecided |
| Inbound webhook replay, brute-force token guess, or 50 MB payload bomb (G04) | Constant-time SHA-256 token verification; payload capped at 64 KB before parsing; idempotency key deduplicates retries within the window; paused source or held DB rejects before write |
| Outbox notification triggered for an approval that the owner already decided in the tab | Notification worker checks that the approval/run condition is still active before sending (`docs/channels.md:98-99`), preventing stale false-alarm pings |
| WhatsApp/Telegram infinite reply loop (OpenClaw showcase failure S1) | Channel admission enforces human-only private sender allowlist, 1 active task at a time, max 20 tasks/hour per connection, and per-run step/token budgets (`docs/channels.md:31,45`) |

## 6. Multimodal pipeline (`providers/attachments.py`, `uploads.py`, `ingest.py`)

| Edge case / gap | Expected Hutch behavior |
|---|---|
| User attaches a PNG/JPEG/WebP or audio note to an assistant whose model route is text-only | Admission preflight (`image_route_refusal` / audio capability check) refuses before sending with a clear message naming the route limitation, never sending the prompt while silently dropping the attachment |
| Uploaded file has `.png` extension but contains HTML/SVG script or executable bytes | Server-side magic-byte MIME verification (`uploads.py`, `attachments.py`); mismatches are rejected |
| Photo of a receipt/invoice has rotated EXIF orientation or GPS metadata | EXIF orientation normalized so OCR/vision models read upright text; sensitive GPS/camera EXIF stripped on intake where configured |
| Audio transcription (`transcribe.py`) fed silence or background noise (Whisper hallucination class) | Empty/low-signal or repeated-phrase hallucination flagged as `unverified` transcript preview requiring owner confirmation before becoming a commitment or command |
| Telegram user sends a photo, voice note, or document to a connected assistant | Never silently ignored: either processed through the opted-in bounded channel media pipeline or recorded with an explicit notice so the user knows only text is accepted |

## 7. Frontend, paired-phone UI & marketing website

| Edge case / gap | Expected Hutch behavior |
|---|---|
| `app.js` or `style.css` is frozen in `.file-size-baseline.json` | New UI lives in dedicated modules (`schedules.js`, `webhooks.js`, `deliverables.js`, `code-handoffs.js`, `multimodal-intake.js`, `phone-personal.js`) and `app/src/` CSS sources |
| Narrow mobile viewport (360 px) or 200% browser zoom on Today, Shared, Schedules, Deliverables | Zero horizontal overflow (`scrollWidth <= clientWidth`), full action button reachability, wrapped long titles/origins |
| Polling loops when multiple tabs are open or tab is hidden | No background poll faster than 30 s; pause polling when `document.hidden` is true; rely on existing SSE/bus invalidation where available |
| Marketing website (`website/index.html`) vs actual code state | Every claim on the website maps to a shipped, tested capability and links to its documented limits (`docs/marketing-site.md`); zero emojis anywhere |

