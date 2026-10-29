# Continuation: Slice B (governed permanent deletion of reference facts)

Date: 2026-10-29. Base: local `main` at `135d8038` plus plan commit `4a48f003`.
Status: **implemented and locally verified**; the dashboard control and whole-Bot purge remain.

## Completed

- Schema v82: purged tombstones (`memory_facts.purged_at/purge_id`), guarded content updates, snapshot
  erasure on `memory_fact_shares` and `workspace_task_fact_shares`, immutable `memory_purge_requests`
  and `memory_purge_items` evidence tables - `src/hutch/fact_purge_schema.py`, delegated from the
  frozen migration list by `store._migrate_82`.
- Data layer: preview/counts, one-time token, typed confirmation, archive-then-erase, FTS and legacy
  row cleanup, fail-closed expiry/supersession/replay - `src/hutch/fact_purge.py`.
- API: `POST /api/v1/bots/{ref}/facts/purge-requests`, `POST .../{request_id}/confirm` (Idempotency-Key
  required), `GET .../purge-requests` - `src/hutch/server/facts_api.py`.
- CLI: `hutch bot purge NAME --key KEY` / `--all`, two-step preview plus typed confirmation
  (`--yes` skips the prompt, never the preview) - `src/hutch/cli_facts.py`.
- Tests: `tests/test_fact_purge.py` (9 focused cases); broad focused group **200 passed, 1 skipped**.
- Docs: bot-config, operations, safety, realignment tests row and README updated; ledger checkpoint
  appended for 2026-10-29.

## Local browser checks

`.venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_bot_memory_export_explains_scope_and_downloads_complete_json tests/e2e/test_browser.py::test_scoped_fact_review_revision_conflict_and_memory_off`
was run against the installed Chromium revision: **6 passed in 34.95 s** (the two scenarios span
desktop/tablet/phone viewports), with artifacts under `/tmp/hutch-realign-artifacts`. The memory
settings UI itself is unchanged by this slice.

## Remaining (exact paths)

1. Dashboard purge control: the memory settings templates are owned by the parked brand session
   (`src/hutch/server/templates/bot.html`, `static/app.js`). Add a two-step purge affordance that
   consumes the new API and shows the `remaining` list; do not edit those files from this session.
2. Whole-Bot / conversation permanent deletion: `store.delete_bot` still archives facts and keeps
   runs/events; a separate governed design is needed (`src/hutch/store.py`, `docs/operations.md`).
3. Optional: exercise `workspace_task_fact_shares` erasure end-to-end through a delegation test (the
   update path is schema-guarded and covered by the migration guard today).
4. Optional: paginate `GET .../purge-requests` if one Bot accumulates many purges (currently 1-100).

## Verification gaps (do not overclaim)

No live provider, OAuth account, physical phone, screen reader or packaged installer was exercised.
Pre-purge database backups keep the erased content by design. The only context-hygiene violation in the
tree is the pre-existing other-session `tests/test_commit_attribution.py` (419 lines).

## Copy-paste prompt for the next run

> Continue the Hutch completion work from `docs/realignment/continuation-B.md`. The governed permanent
> deletion feature is implemented in `src/hutch/fact_purge.py`, `src/hutch/fact_purge_schema.py`,
> `src/hutch/server/facts_api.py` and `src/hutch/cli_facts.py`, with tests in
> `tests/test_fact_purge.py`. Next: wire the two-step dashboard control in the currently parked
> dashboard session's templates/JS only after that work is committed, then add the whole-Bot purge
> design in `docs/operations.md` before code. Run the quiet focused gate and record evidence in
> `docs/realignment/ledger.md`. Never stage the other session's uncommitted files.
