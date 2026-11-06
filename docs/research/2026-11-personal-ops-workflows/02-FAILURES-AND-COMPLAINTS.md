# Failures and complaints: clustered, classified and testable (Phase 1, 2026-11-06)

This file turns the sources in `01-SOURCES.md` into failure classes. It extends
`D2` (`FAILURE-ANALYSIS.md`) and `D4` (`complaints.md`); rows already covered there are not
repeated as new evidence.

Classification used below:

- **fixable-in-Hutch**: a deterministic code, schema or UX change can prevent the failure.
- **mitigable**: Hutch can reduce frequency or harm, but a model, provider or third party retains
  the underlying behavior. The honest UI and test must say so.
- **external-limit**: not fixable inside Hutch's boundary. Record the limit and never claim
  otherwise.

Each row names a test scenario. "5x replay", "23-hour day", "360 px", "forged ref" and similar
phrases are the story names the later phase must turn into a real test in `tests/` and, where the
row says real stack, in `06-VALIDATION-LEDGER.md`.

## 1. Personal operations, calendar and daily briefings

| Id | Failure mode | Evidence | Class | Test scenario | Req |
|---|---|---|---|---|---|
| POW-F1 | Auto-scheduler moves tasks repeatedly and places work on top of busy events; the user ends up babysitting the plan | C1 | mitigable | `calendar-jitter`: a busy event plus two proposed tasks; assert no event is written without approval, and a pinned task is not moved by a later proposal | POW-R25 |
| POW-F2 | Reminder fires at the wrong local time, is skipped in the spring-forward gap, or fires twice in the fall-back overlap | C20, D2 F3/F4, D4 | fixable-in-Hutch | `dst-23-25`: `America/New_York` 2026-03-08 02:30 and 2026-11-01 01:30; assert one UTC instant, one occurrence, preserved display zone | POW-R8 |
| POW-F3 | Calendar or mail sync silently stops after OAuth expiry; Today shows a stale snapshot or an empty "nothing today" | B3, D6 G01 | fixable-in-Hutch | `grant-expired`: revoke the token; assert `grant_expired` or `grant_missing`, cache eviction, no stale event list | POW-R27 |
| POW-F4 | A retry or sync copy creates a duplicate calendar event | B2, C8 | mitigable | `calendar-idempotent`: replay the same reminder action 5x; assert one external event and one receipt; a second copy created by the provider is labelled as a sync copy, not hidden | POW-R26 |
| POW-F5 | Assistant invents a commitment from a casual email, a newsletter or an unrelated message | B4, D2 F6/F11, D4 | mitigable | `forged-source-ref`: a `capture_commitment` call whose `source_ref` is not in the run's committed tool or upload records; assert refusal and zero rows | POW-R22, POW-R23 |
| POW-F6 | A confident AI summary hides an overdue deadline or ranks a stale item above a real one | D2 F6, C5 item 7 | mitigable | `overdue-first`: deterministic Today builder with one overdue item and a long summary; assert overdue sorts first and summary cannot suppress it | POW-R5, POW-R24 |
| POW-F7 | Too many reminders make the owner mute the assistant or miss the one that mattered | C5 item 7, B4 | mitigable | `one-digest`: 20 commitments due in one window; assert one digest per window and a visible count, not 20 messages | POW-R32 |
| POW-F8 | The owner cannot review Today, decide an approval or check a coding status from a phone without a laptop | A4, A5, A6, C19 | fixable-in-Hutch | `phone-today`: paired-phone view of Today, approve/deny one existing request, mark an existing commitment done; assert bounded data, no secrets, no shell | POW-R46, POW-R47 |

## 2. Family and shared household workflows

| Id | Failure mode | Evidence | Class | Test scenario | Req |
|---|---|---|---|---|---|
| POW-F9 | A weekly meal or grocery workflow run twice creates duplicate items ("milk", "2% Milk", "milk ") | A8, C3, C5 item 12 | fixable-in-Hutch | `merge-twice`: run the same weekly plan twice against one real SQLite DB; assert one normalized item row and an auditable merge event | POW-R29 |
| POW-F10 | Deleted items reappear, or crossed-off state disagrees between two phones | C2, C3, C5 item 14 | fixable-in-Hutch | `ghost-item`: two clients edit the same list; one deletes; assert the delete wins, the other gets a 409/reload state, and no ghost row returns | POW-R30 |
| POW-F11 | A private task or a work detail leaks into the household view | C5 item 11, D3 | fixable-in-Hutch | `space-scope`: an assistant without a grant lists items; assert 403 or an empty list that names the missing grant, never another space's items | POW-R33 |
| POW-F12 | A spouse or family member receives an unwanted notification, or the bot messages a third party | A4, C5 item 7, D2 F10 | fixable-in-Hutch | `recipient-allowlist`: a notification to an unlisted recipient is refused before send; one digest per allowlisted recipient | POW-R32 |
| POW-F13 | Complex recurring routines ("every other Tuesday", alternating school weeks) become a backlog after one miss | C5 item 8 | mitigable | `alternating-weeks`: schedule across two DST transitions and one missed window; assert correct dates, one visible missed marker, no backlog storm | POW-R8, POW-R31 |
| POW-F14 | A sync outage or vendor update erases trust: the family sees different calendars and reverts to manual coordination | C2, C4 | external-limit | `sync-outage`: provider unavailable; assert the UI says unavailable with a reason and timestamp, never "no events"; no local overwrite | POW-R33 |

## 3. Daily automations, schedules and inbound events

| Id | Failure mode | Evidence | Class | Test scenario | Req |
|---|---|---|---|---|---|
| POW-F15 | A schedule silently stops firing; the workflow still shows "active" and nothing fails because nothing started | C6, C7 | fixable-in-Hutch | `silent-cron`: disable the trigger; after 2x the normal gap, assert "needs attention", last-seen age and a next action | POW-R5, POW-R7 |
| POW-F16 | A schedule is edited without a revision trail; nobody can answer "who changed this and when?" | B1, C6 | fixable-in-Hutch | `revision-journal`: API edit creates one revision row; a no-op save creates zero; direct `UPDATE`/`DELETE` on the journal is refused | POW-R1, POW-R2 |
| POW-F17 | A DST transition double-fires or skips a scheduled run | C20, D2 F3 | fixable-in-Hutch | `dst-double-fire`: hourly schedule over the fall-back hour; assert one occurrence per absolute instant and a visible `fold` decision | POW-R8 |
| POW-F18 | Webhook retries, manual replays or provider redelivery process the same event twice | C8 | fixable-in-Hutch | `replay-5x`: same idempotency key 5 times; assert one side effect, five 200 responses, one delivery row | POW-R11 |
| POW-F19 | A webhook endpoint is brute-forced, sent an oversized body, or used to inject a huge payload | C9 | fixable-in-Hutch | `webhook-bounds`: wrong secret 401; 65 KB body 413 before parse; 50 concurrent guesses rate-limited; no secret or payload in logs | POW-R9, POW-R10 |
| POW-F20 | A webhook or source triggers a run that triggers the same source again, producing a loop | A2, D2 F1, D4 | mitigable | `self-trigger`: source A admits a run that posts to its own webhook; assert the chain stops at the configured depth/rate and shows a loop guard state | POW-R4, POW-R12 |
| POW-F21 | Approval prompts become a rubber stamp; a dangerous action is approved because the prompt was one of fifty | B4, D2 F10, D5 | mitigable | `approval-binding`: 10 low-risk actions auto-run, 1 high-risk asks; assert the approval hash covers action, parameters and target, and a changed parameter is refused | POW-R3 |
| POW-F22 | A workflow reports success while one item or one step failed, or a scan was clipped and presented as complete | C7, D6 G10/G12 | fixable-in-Hutch | `partial-run`: one map item fails with `on_item_failure: skip`; assert `complete:false`, skipped keys and reasons; a clipped `list_files` sets `paths_complete:false` | POW-R44 |

## 4. Coding orchestration and worktree lifecycle

| Id | Failure mode | Evidence | Class | Test scenario | Req |
|---|---|---|---|---|---|
| POW-F23 | Coding worktrees accumulate silently and consume disk (13.8 GB in one report, 113 worktrees in another) | C10 | fixable-in-Hutch | `stale-worktrees`: create three worktrees, age one; `hutch code list --stale` and doctor report age, bytes, branch and dirty state | POW-R34, POW-R38 |
| POW-F24 | Cleanup deletes unmerged or unpushed work, or removes a worktree still in use | C10 (comments on #88255 and #79899) | mitigable | `prune-refusal`: dirty or unpushed worktree prune without explicit force; assert refusal and a receipt naming the branch and changed files | POW-R35 |
| POW-F25 | The coding CLI exits 0 with modified files, or the model claims "all tests pass" without evidence | C11, D2 F11, D4 | fixable-in-Hutch | `receipt-binds-tree`: exit 0 with changes -> `changes_ready`; verify with a passing command -> `verified`; edit one file after the receipt -> `unverified` | POW-R37 |
| POW-F26 | A timed-out coding child or background process survives its run and keeps writing | D4 #133062, D2 F1/F12 | fixable-in-Hutch | `process-group-cleanup`: start a child, time out the run; assert the process group is dead and the run is not terminal until cleanup is verified | POW-R39 |
| POW-F27 | A worktree lock points at a dead PID, or a nested worktree blocks a safe removal | C10 | fixable-in-Hutch | `dead-lock`: lock a worktree with a dead PID; stale inspection flags it; prune unlocks only after explicit confirmation and reports the category | POW-R34, POW-R35 |
| POW-F28 | A phone or voice status check cannot show the changed-file count or latest receipt | A3, A5, D6 G02 | fixable-in-Hutch | `phone-coding-status`: paired phone reads a handoff; assert changed-file count, latest exit code and duration, no raw shell or secrets | POW-R36, POW-R46 |
| POW-F29 | Agent-authored tests are over-mocked or weakened, so a green suite proves nothing | C11, D2 F11/F13 | mitigable | `verify-real-command`: verify runs the project's real command and records argv, exit code and duration; a mocked-only suite is labelled unverified rather than verified | POW-R37, POW-R39 |

## 5. Shipped workflows and deliverables

| Id | Failure mode | Evidence | Class | Test scenario | Req |
|---|---|---|---|---|---|
| POW-F30 | A generated file expires with the chat or code environment; the card remains and the bytes are gone | C16 | fixable-in-Hutch | `deliverable-after-chat`: generate a document, destroy the run workspace; the library link still serves verified bytes | POW-R40, POW-R42 |
| POW-F31 | A generated CSV has fewer rows than promised, or a PDF omits required sections, but is presented as complete | C16, C18, D6 G12 | fixable-in-Hutch | `csv-row-parity`: create a CSV with a declared row count; truncate it; assert `validation_state=failed` and no "Validated" badge | POW-R41, POW-R44 |
| POW-F32 | A file on disk is modified or deleted after the run; the download serves corrupted or missing bytes | C16, D6 G12 | fixable-in-Hutch | `hash-mismatch`: alter one byte after storage; download returns an integrity error, not the altered content | POW-R42 |
| POW-F33 | A workflow scan is clipped or partial but the result is rendered as a complete scan | C7, D6 G10 | fixable-in-Hutch | `partial-scan`: a folder with more files than the tool limit; assert `truncated:true`, `paths_complete:false`, and a partial badge | POW-R44 |
| POW-F34 | Generated files pile up in a flat list, and the owner cannot find last week's report | C17 | fixable-in-Hutch | `find-deliverable`: 100 documents, media and artifacts; filter by assistant, kind and date in at most two interactions | POW-R40, POW-R45 |

## 6. Multimodal intake

| Id | Failure mode | Evidence | Class | Test scenario | Req |
|---|---|---|---|---|---|
| POW-F35 | An image or audio attachment is silently dropped when the selected model route is text-only | D6, D2 F18 | fixable-in-Hutch | `route-refusal`: attach a PNG to a text-only route; assert a typed refusal naming the route and no created run | POW-R16 |
| POW-F36 | Telegram photo, voice, audio or document messages from an allowlisted sender are ignored with no feedback; a stranger could also be messaged | D6, C15 | fixable-in-Hutch | `telegram-nontext`: allowlisted photo -> visible "attachment ignored (text-only mode)" notice; opt-in -> bounded download; stranger -> no reply and no processing | POW-R17 |
| POW-F37 | Whisper invents a sign-off, a subscription request or a repeated phrase on silence | C12 | mitigable | `silent-audio`: 5 s of silence and a 1 s noise clip; assert no fabricated sentence, or a transcript marked low-signal and unverified | POW-R18 |
| POW-F38 | OCR swaps day/month, misreads a decimal, or reports subtotal + tax that does not equal the total | C14, C18 | mitigable | `receipt-fields`: a DD/MM receipt and a total mismatch; assert both fields flagged, the row unverified, and no auto-created commitment | POW-R19 |
| POW-F39 | A phone photo is stored and OCR'd sideways because EXIF orientation was ignored; GPS or camera metadata leaks | C13 | fixable-in-Hutch | `exif-upright`: orientation 6 image; OCR reads upright text and stored metadata has no GPS/camera fields | POW-R15 |
| POW-F40 | A file with a `.png` extension actually contains HTML, SVG script or an executable | D6, D2 F8 | fixable-in-Hutch | `magic-byte`: `.png` containing HTML; assert rejection before storage or model admission | POW-R15 |
| POW-F41 | Injected instructions inside a receipt, PDF hidden layer or transcript reach a tool-capable model as ordinary text | D2 F8, D5, B4 | mitigable | `injected-ocr`: OCR text containing "ignore previous instructions"; assert `ingest.py` annotations, untrusted marking, and no auto-approval | POW-R13, POW-R20 |
| POW-F42 | An over-limit channel attachment causes a permanent connection error and a retry loop | C15 | fixable-in-Hutch | `telegram-oversize`: 30 MB document; assert a size refusal before download and no retry, using `file_size` from the update | POW-R17 |

## 7. Phone, approvals and interface

| Id | Failure mode | Evidence | Class | Test scenario | Req |
|---|---|---|---|---|---|
| POW-F43 | A pending question or approval is hidden behind a mobile overlay and times out | C19 | fixable-in-Hutch | `mobile-approval-visible`: 360 px, overlay open; assert the approval is reachable, focusable and not covered | POW-R47 |
| POW-F44 | A page overflows horizontally at 360 px or 200% zoom, hiding an action button | D6, D4 | fixable-in-Hutch | `zoom-200`: Today, Shared, Schedules and Deliverables at 360/768/1280/1920 px, light/dark, 200% zoom; assert `scrollWidth <= clientWidth` | POW-R47 |
| POW-F45 | Status is encoded by colour alone, so it is unreadable in grayscale or for a colour-blind user | D4 | fixable-in-Hutch | `grayscale-status`: grayscale screenshot; assert glyph, word and rail still carry the state | POW-R47 |
| POW-F46 | A notification or lock-screen alert contains private commitment text | D2, D4 | mitigable | `generic-alert`: approval alert body contains no title, participant or command text | POW-R32, POW-R46 |

## 8. Privacy, permanent deletion and local-first boundaries

| Id | Failure mode | Evidence | Class | Test scenario | Req |
|---|---|---|---|---|---|
| POW-F47 | Deleted commitment bytes remain recoverable from SQLite pages or a WAL file after a normal delete | B5, B6 | fixable-in-Hutch | `purge-bytes`: insert a unique secret, purge, checkpoint and vacuum; scan the DB and WAL bytes; assert zero hits | POW-R43 |
| POW-F48 | Purging breaks foreign keys or run references, or there is no export before the irreversible action | D6 G14 | fixable-in-Hutch | `purge-tombstone`: purge one commitment; assert a content-free tombstone, intact foreign keys, and an export file produced before deletion | POW-R43 |

## Cross-cluster notes

- **The same primitive repeats.** Idempotency (POW-F4, F9, F10, F17, F18), explicit state
  (POW-F3, F15, F22, F25, F31, F37), and exact approval binding (POW-F5, F21, F25) appear in every
  cluster. Those are the three primitives to implement once, not eight times.
- **False green is the dominant trust failure.** Silent cron (F15), false completion (F25), partial
  workflow success (F22), expired deliverables (F30) and truncated CSV (F31) are all "the system said
  it worked". The requirement is the same in each case: a terminal state must carry evidence or say
  it is unverified.
- **No row is left as "the model will be better".** Where the class is mitigable, the test still
  asserts a visible state and a bounded refusal, not a model promise.
