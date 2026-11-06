# Sources: personal ops, family workflows, coding orchestration, deliverables, automations and multimodal intake (Phase 1)

Access date for every row: **2026-11-06** unless the row says otherwise. This file extends the
October research pack (`D1`-`D6` below); it does not repeat rows already recorded there. Evidence
grades follow the existing pack: `VERIFIED` (primary document, issue, advisory or code read),
`OBSERVED` (page fetched and read), `COMPLAINT` (a user or vendor complaint report, not an incidence
estimate), `HYPOTHESIS` (our inference, recorded as such).

How to read this file:

- Source ids are `A` (owner-supplied), `B` (primary product or standards documentation), `C`
  (failure and complaint mining), `D` (carried-forward prior evidence) and `E` (limits and
  unreachable pages).
- "Relied on" is the claim the page actually made. Where exact wording matters it is quoted; the
  fetch tool returns an extract of the page, not a guarantee that the extract is the whole page.
- "Effect" names the requirement ids in `03-REQUIREMENTS-AND-DECISIONS.md`. A row with "context"
  changed no requirement.
- Vendor-authored reviews are marked as such. They are useful for complaint shapes and useless as
  prevalence estimates.

## A. Owner-supplied references (all eight fetched this pass)

| Id | Source and URL | Published | Grade | Relied on | Effect |
|---|---|---|---|---|---|
| A1 | Hutch repository, https://github.com/K-Arthur/hutch | undated page; accessed 2026-11-06 | VERIFIED | README positioning: "local-first, MIT-licensed multi-bot platform in development preview"; named assistants; "ask-first approvals and hard-denied shell classes"; "verifiable run transcripts"; local and hosted model routes; Linux only; no packaged installer or hosted sign-up. The public README is the claim surface the marketing site must match | POW-R48 |
| A2 | OpenClaw showcase, https://openclaw.ai/showcase | undated page; accessed 2026-11-06 | OBSERVED | Six featured builds (jdrhyne, danpeguine, georgedagg_, dreetje, davekiss, stevecaldwell) plus community cards. A community card from `@avi_press` states: "Sent thousands of messages in a loop to an innocent and unsuspecting person who happened to message me on WhatsApp." The page publishes no run history, approval log or failure rate | POW-R6, POW-R12 |
| A3 | `@jdrhyne`, https://x.com/jdrhyne/status/2012778049406742632 | 2026-01-18 | OBSERVED | "15+ agents. 3 machines. 1 Discord server."; daily roll call across 10+ agents; orchestrates Codex agents; refactors PRs and builds CLI tools; Slack HTTP webhook development | POW-R6, POW-R36 |
| A4 | `@danpeguine`, https://x.com/danpeguine/status/2012565160586625345 | 2026-01-17 | OBSERVED | Morning brief with weather, objectives, health, meetings, reminders and reading; "notifies my wife and I about our son's upcoming school tests"; "manages the calendar for any conflicts autonomously"; creates invoices; receipt/expense tracking is a future skill | POW-R22, POW-R24, POW-R32 |
| A5 | `@georgedagg_`, https://x.com/georgedagg_/status/2012119327147798753 | 2026-01-16 | OBSERVED | Voice-guided production remediation: reviewed Railway logs, identified incorrect build commands, updated service configs, redeployed, confirmed success, then fixed a design issue and submitted a PR "over voice when walking the dog" | POW-R36, POW-R37 |
| A6 | `@dreetje`, https://x.com/dreetje/status/2012535486401671588 | 2026-01-17 | OBSERVED | One assistant for mail, Beeper messages, orders, reminders, GitHub issues, Places, PDF recaps, cost splitting, calls and contact search; "It has its own 1Password vault it can read and write to, I share logins in a read-only vault"; "Impersonate me in a group chat" | POW-R22, POW-R24, POW-R25 |
| A7 | `@davekiss`, https://x.com/davekiss/status/2008994096736817624 | 2026-01-07 | OBSERVED | "rebuilt my entire personal site via telegram last night... notion -> astro, 18 posts migrated, dns moved to cloudflare. never opened my laptop." The post links a long-form write-up but publishes no diff, deploy receipt or rollback | POW-R40, POW-R46 |
| A8 | `@stevecaldwell`, https://x.com/stevecaldwell/status/2007616854689280196 | 2026-01-04 | OBSERVED | Master 2026 meal plan, shopping lists sorted by store and aisle, weather-aware dinner planning, recipe catalogue, morning/evening digests; the assistant is shared with a spouse and the cooking rotation is encoded as rules | POW-R29, POW-R31, POW-R32 |

## B. Primary product and standards documentation

| Id | Source and URL | Published | Grade | Relied on | Effect |
|---|---|---|---|---|---|
| B1 | n8n docs, "View change history", https://docs.n8n.io/build/manage-workflows/view-change-history | last updated ~2026-10-28 (9 days before access) | VERIFIED | "Changes to workflow settings do not create a new version." Full history is Enterprise-only; all users get versions from the last 24 hours, Cloud Pro the last five days. A changed schedule interval does not take effect until the workflow is unpublished and published again | POW-R1, POW-R2 |
| B2 | Reclaim.ai help, "How to handle duplicate events from Calendar Sync", https://help.reclaim.ai/en/articles/3639940-how-to-handle-duplicate-events-from-calendar-sync | updated ~2026-10 (over 3 weeks before access) | VERIFIED | "Calendar Sync creates duplicate events across calendars by design." The source event and the synced copy are two separate events; users must edit the source, not the copy | POW-R25, POW-R26, POW-R48 |
| B3 | Reclaim.ai help, "Why are my events not being synced?", https://help.reclaim.ai/en/articles/6556414-why-are-my-events-not-being-synced | updated ~2026-10 | VERIFIED | The documented remedy is to disable and re-enable the sync policy and wait; support needs the event URL's embedded ID. A sync that silently stops is a support case, not a user-visible state | POW-R27 |
| B4 | Anthropic, "How we built Claude Code auto mode", https://www.anthropic.com/research/claude-code-auto-mode | undated extract; accessed 2026-11-06 | VERIFIED | "users accept 93% of them anyway"; approval fatigue is the stated problem; internal incident log includes deleting remote branches, uploading a token, and migrations against production. Auto mode still has a 17% false-negative rate on real overeager actions | POW-R3, POW-R21, POW-R47 |
| B5 | SQLite, "Write-Ahead Logging", https://sqlite.org/wal.html | last updated 2026-08-25 | VERIFIED | A checkpoint moves WAL content into the database; the WAL file is part of persistent state and can retain committed content after a crash. Automatic checkpoint runs at 1000 pages; `sqlite3_wal_checkpoint_v2` exposes FULL/RESTART/TRUNCATE modes | POW-R43 |
| B6 | SQLite User Forum, "Deleted bytes left behind after vacuum (WAL mode)", https://sqlite.org/forum/forumpost/3b069c23f7 | 2026-02-09 to 2026-02-12 | VERIFIED | In WAL mode with a chunk size, a VACUUM followed by a checkpoint can leave deleted pages in the main file. `secure_delete` alone did not fix it; `secure_delete` plus a checkpoint before the VACUUM did. The reporter's workaround, not an official guarantee | POW-R43 |

## C. Failure and complaint mining

### C1. Personal operations, calendar and household workflows

| Id | Source and URL | Published | Grade | Relied on | Effect |
|---|---|---|---|---|---|
| C1 | Carly, "Motion AI Review (2026)", https://www.usecarly.com/blog/motion-ai-review/ | 2026-09-28 | COMPLAINT (vendor-authored) | Verbatim App Store and r/UseMotion complaints: tasks scheduled "directly on top of existing calendar events that were already marked as busy"; "Doesn't keep any tasks where I move them"; "I constantly find myself manually moving tasks around"; the plan "moves under you" | POW-R25, POW-R48 |
| C2 | Sense, "Cozi Not Syncing? Why Lists and Events Go Missing in 2026", https://getsense.ai/blog/posts/cozi-not-syncing-2026 | 2026-07-02 | COMPLAINT (vendor-authored) | Google Play reviews from late 2025 through spring 2026 report list items disappearing, events that save on one phone but never appear for the family, blank widgets, random logouts. One May 2026 reviewer: "other family members will add things but no one else can see them." | POW-R30, POW-R33 |
| C3 | Kinrows, "How to fix a shared grocery list that keeps getting out of sync", https://kinrows.com/how-to/keep-a-shared-grocery-list-in-sync | last reviewed 2026-09-15 | COMPLAINT (vendor-authored) | Duplicates, ghost items and per-device crossed-off state come from each phone reconciling a local copy. Quoted App Store reports: one item added three times; "Updates will occasionally erase list memory"; purchased items crossed off on one phone but not the other | POW-R29, POW-R30 |
| C4 | RemindHer, "Hearth Display Review 2026", https://remindher.app/hearth-display-review/ | 2026-10-24 | COMPLAINT (vendor-authored) | Review of 122 App Store reviews of the Hearth Companion App: calendar sync appears in 59% of negative reviews, subscription in 53%, bugs/logins in 31%; app rating 3.9; web app retired in 2025 so management is phone-only | POW-R33, POW-R46 |
| C5 | Domistiq, "The 2026 Family Organizer App guide: What 1,281 real Reddit pain points reveal", https://domistiq.com/blog/2026/05/16/the-2026-family-organizer-app-guide-what-1-281-real-reddit-pain-points-reveal-about-today-s-top-apps | 2026-05-16 | COMPLAINT aggregate (vendor-authored, LLM-synthesized) | Fifteen ranked pain points from 1,281 Reddit posts: disproportionate mental load, fragmented information, no shared responsibility, capture-to-action friction, rigid scheduling, notification noise, complex recurring routines, privacy/permission conflicts, meal/grocery fragmentation, and sync failures causing "ghost" events. Treat ranks as directional, not measured prevalence | POW-R28 to POW-R33 |
| C6 | Jen8n, "n8n Schedule Trigger Not Working? Mine Never Ran for 7 Weeks", https://jen8n.com/n8n-schedule-trigger-not-working/ | updated 2026-10-13 | COMPLAINT | Three monthly workflows showed active for up to seven weeks and never fired; no run, no failure, no error workflow. The author built a watchdog that compares the last run to the expected gap. n8n keeps only ~5,000 runs (~2.5 days on that server), so the watchdog must keep its own last-seen record | POW-R5, POW-R6, POW-R7 |
| C7 | "Silent failures in n8n automations - a forum corpus (2026)", https://github.com/aaaante/n8n-silent-failures-2026 | 2026; accessed 2026-11-06 | OBSERVED corpus | 111 hand-classified cases from 163 reviewed community threads: 54 (48.6%) expected run never appeared; 37 (33.3%) run existed but outcome was missing or wrong; 20 (18.0%) work finished only in part. This is a forum corpus, not a failure-rate estimate | POW-R5, POW-R6, POW-R7, POW-R44 |
| C18 | Designs24hr, "ChatGPT Spreadsheet Wrong Numbers?", https://www.designs24hr.com/chatgpt-spreadsheet-wrong-numbers/ | editorial review 2026-10-18 | OBSERVED (tutorial) | Wrong totals, skipped rows, double-counted subtotals, ambiguous `03/04/2026` dates, leading zeros lost, duplicate rows; asks for row-by-row reconciliation rather than a corrected number | POW-R41, POW-R44 |
| C20 | DevOps AI Toolkit, "Automation Error: Cron Job Skipped or Ran Twice at a DST Transition", https://devopsaitoolkit.com/blog/automation-error-cron-dst-timezone-skipped-or-duplicate-run/ | 2026-07-08 | OBSERVED | A `02:30 America/New_York` job does not exist on the spring-forward date and a repeated 01:00 hour fires twice in fall-back; a wall-clock hour is not a unique key. Durable fix: schedule on an absolute UTC instant and make the job idempotent | POW-R8 |

### C2. Webhook and event admission

| Id | Source and URL | Published | Grade | Relied on | Effect |
|---|---|---|---|---|---|
| C8 | Hooklistener, "Webhook Idempotency and Deduplication (2026)", https://www.hooklistener.com/learn/webhook-idempotency-and-deduplication | updated 2026-09-26 | OBSERVED (vendor authored, technically specific) | "Your webhook handler will receive the same event twice. Not might - will." Dedup on the provider event id; claim atomically with `INSERT ... ON CONFLICT DO NOTHING` or `SET NX`; put the claim and side effects in one transaction; return 200 for duplicates; TTL longer than the provider retry window; handle crash-after-claim with a processing/done state | POW-R11 |
| C9 | AppSec Brief, "Webhook Security: HMAC Validation, Replay Prevention, and Secret Rotation", https://appsecbrief.com/articles/webhook-security-hmac-signature-validation-replay-prevention-guide-2026/ | 2026-08-14 | OBSERVED | Four required properties: signature authenticity, replay resistance, timing-safe comparison, rotatable secrets. Use `hmac.compare_digest`/`hmac.Equal`, a timestamp tolerance window, a body size limit, rate limiting, and a dual-validation window during rotation. Logging a failed body can expose legitimate payloads | POW-R9, POW-R10, POW-R14 |

### C3. Coding orchestration

| Id | Source and URL | Published | Grade | Relied on | Effect |
|---|---|---|---|---|---|
| C10 | Claude Code issue #26725, "Stale worktrees are never cleaned up", https://github.com/anthropics/claude-code/issues/26725 | opened before 2026-02-26; active through 2026-10-16 | VERIFIED | Worktrees accumulate after crashes and are invisible to later sessions. One commenter removed 13 abandoned worktrees holding 13.8 GB; another cleaned 113 of 114 worktrees (3.0 GB) plus 112 stale branches. Comments also report auto-cleanup deleting worktrees actively in use (#88255) and unpushed commits deleted as "no pending changes" (#79899), and a dead-PID lock requiring `--force --force` | POW-R34 to POW-R39 |
| C11 | Claude Code issue #46755, "Subagents falsely report task completion without verifying file changes were written", https://github.com/anthropics/claude-code/issues/46755 | 2026-04-11; closed 2026-05-23 as not planned | VERIFIED | Reported reproduction rate 40-60% of claimed fixes absent or incomplete; files claimed created did not exist; partial fixes reported as full resolution. Closed for inactivity, not because the class was disproved | POW-R37, POW-R39 |

### C4. Multimodal intake and transcription

| Id | Source and URL | Published | Grade | Relied on | Effect |
|---|---|---|---|---|---|
| C12 | openai/whisper discussion #679, "A possible solution to Whisper hallucination", https://github.com/openai/whisper/discussions/679 | 2022-12-13; active through 2026-08-21 | VERIFIED (reproducible reports) | Silent or low-signal audio produces "Thank you for watching", "Please subscribe", "Subtitles by..."/"Amara.org" and repeated phrases. Suggested mitigations: VAD, `condition_on_previous_text=False`, `no_speech_threshold`, `logprob_threshold`, `compression_ratio_threshold`, and post-filtering. No fix eliminates the class | POW-R18, POW-R20 |
| C13 | RapidOCR issue #754, "Bug: EXIF orientation is skipped for bytes and PIL images", https://github.com/RapidAI/RapidOCR/issues/754 | 2026-10-12; closed 2026-10-13 | VERIFIED | The same image read from a path was upright, but the same bytes or an opened PIL image skipped EXIF correction; OCR output changed from correct text to garbage. The bug is exactly the upload path a server uses | POW-R15 |
| C14 | ExpenSheet, "How to fix common OCR errors in receipts", https://expensheet.com/en/guides/fixing-ocr-errors | updated 2026-10-16 | OBSERVED (vendor guide) | Common errors: transaction time vs date, short date formats, a missing decimal point or extra digit, multiple tax lines, card brand or payment processor read as vendor. Recommends checking subtotal, tax and total together and keeping manual review for high-value receipts | POW-R19 |
| C15 | Charlie Morrison, "Telegram Bot File Size Limits: The Exact Byte Cutoffs", https://charliemorrison.dev/blog/telegram-bot-api-file-size-limits/ | 2026-08-07 | OBSERVED (measured against a live bot) | Bot API download cap is 20,971,520 bytes; upload cap is 52,428,800 bytes of request body; over-limit uploads drop the TLS connection instead of returning an error. `file_size` is present in the update before `getFile`, so a receiver can refuse with a true message instead of retrying forever | POW-R17 |

### C5. Deliverables, files and mobile approvals

| Id | Source and URL | Published | Grade | Relied on | Effect |
|---|---|---|---|---|---|
| C16 | Data Studios, "ChatGPT 'file is no longer available' error", https://www.datastudios.org/post/chatgpt-file-expired-why-the-error-appears-how-file-retention-works-and-what-users-can-do-to-av | 2025-11-15; updated 2026-11-04 | OBSERVED | The code execution environment is destroyed within 13 hours of a conversation becoming inactive; the chat and file card can remain visible while the file is gone. The fix is re-upload, not recovery. This is the "expired deliverable" shape | POW-R40, POW-R42 |
| C17 | The Drive AI, "Where Do ChatGPT, Claude and Gemini Files Go?", https://thedrive.ai/blog/where-do-ai-generated-files-go | 2026-07-04; updated 2026-10-28 | COMPLAINT (vendor-authored) | Every major tool has a file creation story, none has a file management story: ChatGPT Library is a flat list with no folders or categories; Claude artifacts live in conversations; Gemini/Copilot files land in Drive/OneDrive unorganized. Users cannot find last week's output | POW-R40, POW-R45 |
| C19 | Open WebUI issue #30055, "surface pending ask_user / event-call prompts while Call mode is open on mobile", https://github.com/open-webui/open-webui/issues/30055 | 2026-09-15; open | VERIFIED | On a mobile viewport, Call mode renders a full-height drawer containing only the call UI; a pending `ask_user` question is delivered and rendered behind it, invisible and unreachable. The tool times out (default 120 s) and returns `cancelled`. Desktop is unaffected because Call mode is a side panel | POW-R46, POW-R47 |

## D. Carried-forward prior evidence (not re-fetched)

These files were read in this pass and are the evidence base for the October findings. Rows already
recorded there are not repeated in sections A-C.

| Id | Source | Dated | Grade | Relied on | Effect |
|---|---|---|---|---|---|
| D1 | `.pipeline/personal-operations/2026-10/RESEARCH.md` | 2026-10-31 | VERIFIED/OBSERVED | Showcase matrix E1-E6, patterns P1-P12 (chat as interface, scheduling is load-bearing, per-action approval, deliverables as artifacts, fleets need a roll call, family workflows are multi-owner by default), and the source ledger S1-S33 | POW-R5, POW-R6, POW-R22, POW-R28, POW-R32 |
| D2 | `.pipeline/personal-operations/2026-10/FAILURE-ANALYSIS.md` | 2026-10-31 | VERIFIED/COMPLAINT | Failure classes F1-F18: runaway loops, duplicate external actions, missed/mistimed schedules, DST, calendar conflicts, forgotten commitments, prompt injection, cross-space exposure, permission fatigue, false completion, parallel worktree conflicts, unreviewed code, cost blowups, mobile UX gaps and silent failures. Countermeasure model: authority record, idempotency key, reconciliation, approval binding, run receipt, scoped visibility, truthful completion, budgets, catch-up policy, timezone contract, loop guard, isolation, backup/rollback, review gate | POW-R1 to POW-R48 (cross-cutting) |
| D3 | `.pipeline/personal-operations/2026-10/COMPETITIVE-ANALYSIS.md` | 2026-10-31 | OBSERVED | Market map and comparison tables; OpenClaw multi-user is "usability features, not security boundaries"; Reclaim Preview Mode stages schedule changes; coding orchestration failures concentrate in the supervisor layer; do not copy credit-meter economics, ambient credentials or auto-applied calendar writes | POW-R25, POW-R28, POW-R33, POW-R48 |
| D4 | `docs/research/complaints.md` | revalidated 2026-10-07; local-model update 2026-11-06 | VERIFIED/COMPLAINT | Report-level evidence for completion claims, permission fatigue, DST double-fire, n8n silent non-runs, prompt injection, local dashboard cross-origin exposure, and UI contrast/status failures | POW-R3, POW-R8, POW-R12, POW-R37, POW-R47 |
| D5 | `docs/research/offerings-and-failures.md` | 2026-10-07; update 2026-11-06 | OBSERVED/COMPLAINT | Dots/Grok Bot failure table (approval descriptions are not gatekeepers; no dry run; unbounded context; shared computer), ambiguous email sends, stop-that-does-not-stop, SSE gap loss, multi-agent failure modes, duplicate side effects, localhost dashboard exposure, silent non-runs, browser zombies | POW-R12, POW-R25, POW-R37, POW-R46 |
| D6 | `docs/research/2026-11-personal-ops-workflows/00-GAP-AUDIT.md` | 2026-11-06 | VERIFIED | Current-code audit of G01-G14 and the multimodal seams: schedule mutations overwrite the bot document; no revision table; no webhook receiver; Telegram drops non-text; `capture_commitment` lacks `source_ref`; no deliverables library or semantic checks; worktree lifecycle and phone surfaces open | POW-R1 to POW-R48 (scope) |

## E. Unreachable, partial and method limits

| Id | Item | Result on 2026-11-06 | Effect |
|---|---|---|---|
| E1 | `https://ocr.direct/ocr-for-receipts-what-to-extract-and-validate` | HTTP 504 upstream timeout | Not used. C14 covers the same validation rules; no claim depends on E1 |
| E2 | OpenAI Developer Community, "Why is the PDF export feature broken?", https://community.openai.com/t/why-is-the-pdf-export-feature-broken/1153008 | Page returned an empty body | Not used as evidence. C16 and C17 carry the deliverable-loss claim |
| E3 | Reddit, Hacker News and vendor forums | Not read directly this pass; only search-result summaries and quoted reviews in C1-C5 | Complaint rows are marked as such. No prevalence number in this pack is derived from them |
| E4 | X/Twitter status pages | All six owner-supplied posts returned status 200 with readable text, better than the October pass's warning that X is the weakest source type | The posts are still self-selected social proof; they establish demand shape, not reliability |
| E5 | Vendor-authored reviews and studies (C1-C5, C14, C17, C18) | Each is a competitor's marketing or tutorial content | Used for failure shapes and quoted user reports only. The pack never cites them for market share or failure rates |
| E6 | Telegram local Bot API server | Not stood up or tested | Hutch's phase-4 design must not assume the 2 GB local-server ceiling; the standard Bot API's 20 MiB download cap is the verified limit (C15) |
| E7 | Live Google Calendar, Gmail, Outlook and Telegram accounts | No credentials supplied | The research can specify the failure semantics; the validation ledger must record these as `implemented-unverified (blocked: no live credential)` unless the owner supplies them |

## F. Source-to-cluster index

| Cluster | Primary sources |
|---|---|
| Personal ops and calendar | A3, A4, A5, B2, B3, C1, C20, D1-D6 |
| Household and shared spaces | A4, A8, C2, C3, C4, C5, D1, D3 |
| Automations, schedules and webhooks | A2, A3, B1, B4, C6, C7, C8, C9, D2, D4 |
| Coding orchestration | A3, A5, C10, C11, D2, D4, D5 |
| Deliverables and semantic checks | A7, C16, C17, C18, D6 |
| Multimodal intake | C12, C13, C14, C15, D2, D6 |
| Phone, approvals and responsive UI | A4, A5, A6, B4, C4, C19, D4, D5 |
| Privacy, purge and local-first boundaries | A6, B5, B6, D2, D3, D6 |
