# Continuation: Slice B (governed permanent deletion of reference facts)

Date: 2026-10-29. Base: local `main` at `135d8038` plus plan commit `4a48f003`.
Status: **implemented and locally verified**; the dashboard control is wired and verified (2026-10-29
follow-up) and the whole-Bot purge has a committed design with no code yet.

## Completed

- Schema v82: purged tombstones (`memory_facts.purged_at/purge_id`), guarded content updates, snapshot
  erasure on `memory_fact_shares` and `workspace_task_fact_shares`, immutable `memory_purge_requests`
  and `memory_purge_items` evidence tables - `src/hutch/fact_purge_schema.py`, delegated from the
  frozen migration list by `store._migrate_82`.
- Data layer: preview/counts, one-time token, typed confirmation, archive-then-erase, FTS and legacy
  row cleanup, API-receipt redaction, SQLite secure-delete plus WAL checkpoint, fail-closed
  expiry/supersession/replay - `src/hutch/fact_purge.py`.
- API: `POST /api/v1/bots/{ref}/facts/purge-requests`, `POST .../{request_id}/confirm` (Idempotency-Key
  required), `GET .../purge-requests` - `src/hutch/server/facts_api.py`.
- CLI: `hutch bot purge NAME --key KEY` / `--all`, two-step preview plus typed confirmation
  (`--yes` skips the prompt, never the preview) - `src/hutch/cli_facts.py`.
- Tests: `tests/test_fact_purge.py` (10 focused cases); broad focused group **201 passed, 1 skipped**.
- Docs: bot-config, operations, safety, realignment tests row and README updated; ledger checkpoint
  and code-review follow-up appended for 2026-10-29.

## Post-review hardening (2026-10-29)

A second review pass found that API idempotency receipts still held the purged key/value and that
SQLite free pages could retain overwritten content. Both are fixed: receipts are redacted in place and
counted as `receipts_redacted`, the purge enables `PRAGMA secure_delete = ON` for its transaction and
checkpoints the WAL after commit, and a regression test scans every live table for the erased text.
The review also split the 127-line schema migration and 62-line CLI installer into helpers under 50
lines and added docstrings to every new source function. The raw database file no longer contains the
sentinel in the verification scenario, but this is not a disk-shredding guarantee.

## Dashboard control (2026-10-29 follow-up)

The two-step control is wired into the SPA memory settings (Bot settings > **Limits and memory** >
Saved notes) and into the legacy server-rendered Bot page, consuming the committed preview/confirm API
and showing the `remaining` list before and after erasure. Implementation: new
`src/hutch/server/static/fact-purge.js` (393 lines, dependency-free, exposes
`window.hutchFactPurge.mount`/`autoMount`), two same-line appends in the frozen `static/app.js`
(kept exactly at the 14,532-line cap, net 0 lines), one script tag in `static/index.html`, a new
`templates/_fact_purge.html` included from `templates/bot.html`, one markup/static-asset test in
`tests/test_fact_purge.py`, and a new Playwright journey `tests/e2e/test_fact_purge_ui.py` (desktop
1440x960 and touch phone 390x844; both pass, no page errors, no horizontal overflow). The owner-only
boundary is the server's: paired/remote sessions receive 403 and see that refusal. The parked dashboard
session's uncommitted work was preserved: only this session's hunks were staged (HEAD-based index blobs
for the three shared files), and those files remain uncommitted in the working tree.

**Whole-Bot design.** `docs/operations.md` now contains `## Whole-Bot permanent deletion (design)`:
erase/retain inventory mapped to stores and state paths, two-step preview/confirm protocol, draining and
in-flight-run semantics, transactional erase with the secure-delete/WAL caveat, post-commit cleanup
manifest and crash recovery, content-free `bot_deletions`/`bot_deletion_items` evidence, proposed
API/CLI/dashboard surfaces, schema v83 through a delegated `bot_deletion_schema.py`, acceptance
checklist and honest limits. `store.delete_bot` is unchanged; no whole-Bot erase code exists.

## Local browser checks

`.venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_bot_memory_export_explains_scope_and_downloads_complete_json tests/e2e/test_browser.py::test_scoped_fact_review_revision_conflict_and_memory_off`
was run against the installed Chromium revision: **6 passed in 34.95 s** (the two scenarios span
desktop/tablet/phone viewports), with artifacts under `/tmp/hutch-realign-artifacts`; that check
predates the dashboard control. The control's own Playwright journey (desktop and touch phone) is
recorded in the dashboard-control section above and in the ledger evidence entry.

## Remaining (exact paths)

1. Done (2026-10-29 follow-up): dashboard two-step purge control wired into the SPA memory settings
   and the legacy Bot page; see the dashboard-control section above and the ledger entry.
2. Whole-Bot / conversation permanent deletion: design committed in `docs/operations.md`
   (`## Whole-Bot permanent deletion (design)`); no code exists yet. `store.delete_bot` still
   archives facts and keeps runs/events. Implement in the documented phases: schema v83 and evidence
   tables, data layer, API/CLI, dashboard, then the acceptance checklist.
3. Optional: exercise `workspace_task_fact_shares` erasure end-to-end through a delegation test (the
   update path is schema-guarded and covered by the migration guard today).
4. Optional: paginate `GET .../purge-requests` if one Bot accumulates many purges (currently 1-100).
5. Optional follow-up: replace the delayed (2.5 s) saved-notes refresh after a successful erase with an
   in-place update if the settings view gains per-panel state.

## Verification gaps (do not overclaim)

No live provider, OAuth account, physical phone, screen reader or packaged installer was exercised.
Pre-purge database backups, filesystem/journal copies outside SQLite and provider-side copies keep the
erased content by design; the in-database erasure is verified but not a disk-shredding guarantee. The
only context-hygiene violation in the tree is the pre-existing other-session
`tests/test_commit_attribution.py` (419 lines).

Dashboard-control verification: two Playwright journeys (1440x960 desktop, 390x844 touch phone) pass
with no page errors and no horizontal overflow; their screenshots and JSON receipts were inspected
during the run but are temporary (`HUTCH_TEST_ARTIFACTS_DIR`), not committed visual baselines. The
40 px SPA `.btn` target in both viewports matches the shell at this base; the repository's 44 px
coarse-pointer rule lives in `hutch.css`, which the SPA shell does not load (parked dashboard CSS
migration). No screen reader was used. Whole-Bot deletion remains an unimplemented design.

## Copy-paste prompt for the next run

> Continue the Hutch completion work from `docs/realignment/continuation-B.md`. The governed
> permanent deletion of saved reference facts is implemented, and its two-step dashboard control is
> wired and verified (dashboard-control section; feature commit `97d4e428`). Whole-Bot permanent
> deletion is a committed design only in `docs/operations.md` ("Whole-Bot permanent deletion
> (design)"). Next: implement that design in the documented phases - schema v83 and content-free
> evidence tables in a delegated `src/hutch/bot_deletion_schema.py` module, a
> `src/hutch/bot_deletion.py` command module (preview, drain, confirm, cleanup recovery) with focused
> store tests, typed API and CLI surfaces, then the dashboard danger-zone control and its Playwright
> journey - keeping frozen modules shrink-only. Optional: a delegation e2e exercise of
> `workspace_task_fact_shares` erasure, and pagination for `GET .../purge-requests`. Run the quiet
> focused gate and record evidence in `docs/realignment/ledger.md`. Never stage another session's
> uncommitted files; the SPA assets may still be owned by the parked dashboard session.

## Update (2026-10-29, run 3): whole-Bot deletion implemented

The design in `docs/operations.md` is now implemented, committed and locally exercised. The copy-paste
prompt above is superseded by `docs/realignment/continuation-E.md`.

Commits on local `main` (oldest first): `f0551b8b` plan, `32affb3c` response contract, `df98bd8d`
schema v83 evidence, `8a13ed36` guarded trigger allowances, `f4441382` revoked-share read paths,
`f231959b` command layer, plus the API/CLI, dashboard and docs commits recorded in the ledger entry
"Whole-Bot permanent deletion implemented (2026-10-29)".

Delivered: `src/hutch/bot_deletion_schema.py` (v83 evidence plus limited guarded redaction
allowances), `src/hutch/bot_deletion.py` (preview, confirm, requests, request_record,
recover_cleanup), `src/hutch/server/bot_deletion_api.py`, `src/hutch/cli_bot_deletion.py`, the
dashboard `/bots/delete` picker and `/bots/<name>/delete` danger zone with a dependency-free
`static/bot-deletion.js`, and tests: `tests/test_bot_deletion_schema.py`,
`tests/test_bot_deletion.py`, `tests/test_bot_deletion_api.py`,
`tests/test_bot_deletion_artifact_shares.py`, `tests/e2e/test_bot_deletion_ui.py` and
`docs/realignment/verify_bot_deletion.py` (52-check two-Bot real-world run).

Still open (deliberately not claimed): a background drain phase that waits for verified process exit
(confirmation currently requests cancellation and fails closed); OS secret-service entry clearing;
placing the control inside the Bot settings panel (parked templates); API deletion history by a deleted
name (request-id replay is the supported path); pagination for purge-request history; an end-to-end
delegation exercise of `workspace_task_fact_shares` erasure.
