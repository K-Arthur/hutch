# Validation: assistant retirement

Date: 2026-10-30. Branch `agents/bots-conversations` at `a31ea7f3` when the browser evidence below
was captured. Every command was run in `/home/kevina/CodingProjects/hutch/.worktrees/agents-bots-conversations`
with the repository's own virtualenv (`/home/kevina/CodingProjects/hutch/.venv/bin/python`) and
`PYTHONPATH=$PWD/src`. `uv run` was not used because a worktree has no `.venv`.

## Automated

| Command | Result |
|---|---|
| `pytest -q tests/test_conversations.py tests/test_store_events.py tests/test_sse_resume.py` (before any change) | 62 passed |
| `pytest -q tests/test_bot_lifecycle.py` | 9 passed |
| `pytest -q tests/test_conversations.py tests/test_api.py tests/test_routes.py tests/test_pairing_setup.py tests/test_coordinator_tasks.py` | 91 passed |
| `pytest -q tests/test_delegation.py tests/test_store_events.py tests/test_sse_resume.py tests/test_migration.py tests/test_lifecycle.py tests/test_bot_deletion.py` | 203 passed |
| `pytest -q` over 13 conversation/bot/API/runtime files | 320 passed |
| `pytest -q tests/test_cli.py tests/test_bot_lifecycle.py` | 27 passed |
| `pytest -q tests/test_context_hygiene.py tests/test_home_conversations.py tests/test_transcript_mirror.py tests/test_workspace_manager.py tests/test_coordinator_tasks.py tests/test_delegation.py` | 102 passed |
| `python scripts/audit_context_hygiene.py` | passed, 850 files, 117 frozen over-cap files |
| `python scripts/audit_tool_contracts.py` | passed, 43 tools |
| `python scripts/audit_constitution.py` | passed |
| `python scripts/audit_emoji.py` | clean, 2029 files |
| `python scripts/generate_agent_map.py --check` | passed after regenerating for the new module |
| `node --check src/hutch/server/static/app.js` | clean |
| `ast.parse` over the five changed Python modules | clean |

What the nine lifecycle tests assert, in the real Store and the real HTTP app:

1. Archiving keeps both transcript messages byte-identical, refuses a new conversation message,
   refuses a legacy `create_run`, and refuses `submit_run`.
2. Restore makes the assistant eligible again (a real submission is admitted).
3. Archiving with a running run raises `ArchiveRefused` naming that run, and leaves the Bot active.
4. Two archive commands with one key change state once: `changed` is `True` then `False`.
5. The workspace coordinator cannot be archived.
6. An archived assistant disappears from `workspace_specialists()["bots"]`.
7. A message over HTTP to an archived assistant returns 409 with "archived" in the detail.
8. Archive then restore over HTTP returns `archived: true` then `false`, and `GET /api/v1/bots`
   reports the state.
9. The archive route returns 428 without an idempotency key.

Test coverage (final):

| Command | Result |
|---|---|
| `pytest tests/test_bot_lifecycle.py` | 15 passed |
| `pytest tests/test_specialist_retirement.py` | 2 passed (verified non-vacuous) |
| `pytest` over 19 conversation/bot/API/workflow/scheduler/CLI/monitoring files | 434 passed, 1 wall-clock threshold failure under load (see below) |
| `pytest` over 16 files after the last fix | 334 passed |
| `pytest tests/test_monitoring.py tests/test_coordinator_tasks.py` | 45 passed with the relocated test |

The lifecycle suite asserts, on the real Store and the real HTTP app: archiving keeps the
transcript byte-identical and refuses a new message, a legacy run, a task run, a specialist
assignment and a workflow; a running run blocks archiving by name; two commands with one key
change state once; archive → restore → archive with the same key archives again; a stale settings
save cannot resurrect an archived assistant; the coordinator cannot be archived or become a
retired assistant; an archived assistant is not offered as a specialist and admits nothing from an
event source while keeping its recorded events; and over HTTP the refusal is 409, the state round-
trips, and a missing idempotency key is 428.

## Real CLI, real state directory

`HUTCH_STATE_DIR=/tmp/hutch-cli-abc`, `hutch init`, then:

```
hutch bot create retire-demo --model opencode/deepseek/deepseek-flash   -> created
hutch bot archive retire-demo        -> archived retire-demo
                                        New work is refused while archived; conversations, runs and memory are kept.
hutch bot archive retire-demo        -> archived retire-demo (already in that state)
hutch bot list                       -> row ends "archived", not "active"
hutch bot restore retire-demo        -> restored retire-demo
```

`hutch bot create ... --model mock/demo` is refused by the product build ("Mock inference is
test-only"), so the CLI evidence uses a real OpenCode route.

## Browser

Chromium (the repository's bundled Playwright), against `hutch serve` on a throwaway state
directory, with three assistants seeded through the real HTTP API (main assistant as coordinator,
Research Briefing, and Repo Sweeper retired after one conversation with two persisted turns).

Checks, all three viewports (1440x1000, 900x1024, 390x844):

| Check | Result |
|---|---|
| Horizontal overflow | 0 px at all three widths |
| Console errors, failed requests | none |
| Archived section present in roster | yes |
| Composer disabled for the archived assistant | yes |
| Archived notice visible in the composer | yes |
| Empty chat says "This assistant is archived." | yes |
| Empty chat no longer asks "What would you like to work on?" | yes |
| An active assistant still asks that question | yes |
| Roster menu offers "Archive assistant" | yes |
| Confirmation dialog names the consequence | yes |
| Cancelling changes nothing | yes |
| Restore returns the assistant to normal work | yes |

Screenshots were opened and inspected, not merely produced:

- `roster-desktop.png` - active assistants, collapsed "Archived 1" row.
- `chat-archived-desktop.png`, `chat-archived-tablet.png`, `chat-archived-phone.png` - archived
  state, disabled composer, notice with Restore, roster row reading "Archived".
- `roster-menu.png`, `archive-confirm.png` - the menu item and the confirmation.
- `after-restore.png` - restored assistant accepting work again, roster updated.

Screenshots live in `/tmp/hutch-abc2-shots/` for this run; they are scratch evidence and are not
committed (the repository keeps evidence under `docs/**/artifacts/**`, which this change does not
add to).

## Marketing site

Served over HTTP (`python -m http.server 8899` in `website/`), loaded at 1440 and 390: zero console
errors, zero failed requests, zero horizontal overflow, and the new paragraph renders inside the
existing "More about history, files, and memory" disclosure
(`/tmp/hutch-abc2-shots/site-claim-expanded.png`).

## Defects found during validation, and their resolution

1. **Restore left a stale read-only chat.** The roster and toast updated but the composer stayed
   disabled until navigation, because the chat surface caches its welcome copy and composer state.
   Fixed by re-rendering the current route when the lifecycle change concerns the open assistant.
   Re-verified: the check `restored_invites_work` went from false to true.
2. **The confirmation could not be dismissed.** It was created with `danger: true`, which makes the
   overlay non-dismissible, so Escape and a backdrop click were ignored for a reversible action.
   Changed to a dismissible confirmation; the copy still states the consequences. This was found
   because the automation could not click through the modal.
3. **Pre-existing, not fixed, recorded:** at 390 px the assistant header's conversation chip
   overlaps the subtitle line, clipping text. Measured: `.ctx-id` occupies rows 4-41 px inside an
   89 px header; the overlap does not appear at 900 or 1440 px. It predates this change (no header
   CSS or markup was touched here) and belongs to a shared header refactor with its own responsive
   tests.

## Independent review, and what it changed

The first cut passed every test it shipped with and was still wrong. Two reviewers read the diff
independently; between them they found eight defects, five of them serious, and every one is now
fixed with a test that fails without the fix.

| Finding | Severity | Fix |
|---|---|---|
| `Store.submit_run_idempotent` had no admission check, so `POST /api/v1/tasks/runs`, the routines "Run now" button and persona previews still admitted work | blocker | The check moved into `_assert_execution_ready`, which every run-inserting transaction already calls; it takes the Bot id |
| Event-source monitoring created runs for a retired assistant on its own, with no owner action | blocker | Same predicate via the run path; the pump also stops admitting document jobs |
| The guard added for specialist assignment was on `Store.submit_workspace_task`, which no production code calls; the live route uses `coordinator_tasks.submit_workspace_task` | blocker | Guarded the function the route actually calls, with a test that fails with `DID NOT RAISE BotArchived` when the guard is disabled |
| `hutch bot archive` was a silent no-op after a restore, and reported the opposite verb | high | A replay re-checks the desired state and re-applies it; the receipt row is updated, not duplicated. Reproduced in the real CLI before the fix, verified after |
| Restore would have replayed missed schedule windows | high | `Scheduler.due_claims` skips an archived assistant; `submit_scheduled` independently returns None |
| A settings save built from a stale read silently cleared `archived` | high | The state belongs to the archive command; `upsert_bot` copies it from the stored document |
| Workflow instances, continuations and step runs inserted their own run rows | high | All three guarded inside their write transactions; the supervisor holds a parked workflow with a reason instead of skipping it silently |
| `BotArchived` would surface as HTTP 500 on routes that do not translate it | medium | One app-level handler answers 409 with `code: bot_archived` |

The reviewers also confirmed what is *not* broken: stopping, exporting, deleting and reading an
archived assistant's records are not gated by the new check, so retirement never strands history.

### What the reviewers disagreed with, and why I did not act

- A reviewer proposed making the invariant structural with a SQLite trigger on `runs`. That would
  enforce it for every writer including future ones, but it moves a product rule into schema where
  it cannot produce the distinct refusals the owner needs (restore it, stop the run, move the main
  assistant). The predicate in the one shared admission call gives the same coverage with better
  errors, and the test suite names each caller.
- `archive_bot` rewrites the whole Bot document, so a field added by a future version would be
  dropped by an older version archiving. This is exactly how `upsert_bot` already behaves, so it is
  a pre-existing property of the document store, not a new one; recorded here rather than changed.

### A flaky threshold, reported honestly

One run of the 19-file regression batch failed
`tests/test_store_events.py::test_batched_writer_sustains_over_1000_events_per_second` at 877
events/s. It passes in isolation (twice), passes when re-run with `test_conversations.py`, and the
batch writer path is untouched by this diff (`git diff` over `store.py` shows no change to
`_insert_events` or the flush path). The measurement is wall-clock and the machine was running two
reviewers and a live server at the time. Treated as load-sensitive, not a regression; not
suppressed and not "fixed" by lowering the threshold.

## What was not verified

- **No live model call ran.** The available route is OpenCode's `deepseek/deepseek-flash`; the
  seeded conversation used persisted messages so that transcript, composer and roster states were
  real without a provider request. "An archived assistant refuses a message" is proven at the HTTP
  boundary; "a restored assistant completes a real model turn" is not.
- **No packaged installer, no macOS or Windows**, and no paired-phone device.
- **No screen-reader run.** Keyboard operation was exercised only as far as the automation needed
  (Escape on the dialog, focus return); no axe-core scan was run.
- **Concurrency beyond idempotency** was not stress-tested (two browsers archiving simultaneously);
  the command is one `BEGIN IMMEDIATE` transaction with a per-Bot idempotency scope, and the store
  tests cover replay, not a race.
- **A restore does not reset the schedule marker.** A window that elapsed while the assistant was
  archived is skipped by the scheduler and is not replayed when it returns; whether it is also
  *counted* as a missed window is not asserted by a test, and the manual check did not cover it.
  Treat "missed windows after a restore" as unverified.
