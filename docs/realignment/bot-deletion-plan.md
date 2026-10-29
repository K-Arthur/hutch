# Whole-Bot permanent deletion: implementation plan (run 3)

Date: 2026-10-29. Status: plan committed before code. Base: local `main` at `cb8ca349`.
Evidence base: `docs/realignment/research-completion.md` (committed research), `docs/realignment/completion-plan.md`
(slices A-E), `docs/realignment/continuation-B.md` (fact purge done, whole-Bot design only),
`docs/realignment/continuation-C.md` (frontend/marketing blocked by the parked dashboard session).

## 0. Why this slice

The design in `docs/operations.md` ("Whole-Bot permanent deletion (design)") is the last backend
feature that `docs/bot-config.md`, `docs/safety.md` and `docs/realignment/tests.md` still record as
unimplemented, and the continuation prompt from the previous run names it as next. This run implements
that design in phases instead of leaving another design-only increment. Slice C/D/E items that own the
parked session's uncommitted files remain out of scope (see section 8).

## 1. Repository hazard: the parked uncommitted session

The main checkout carries another session's uncommitted brand/UI work (templates, static JS/CSS,
`website/index.html`, package manifests, `tests/e2e/*` edited files, brand assets). Per `AGENTS.md`:

- never edit, stage, revert, clean, format or commit those files;
- every write in this plan targets files that `git status` shows clean, or brand-new files;
- commits stage explicit paths only (`git add <path>`, never `-A`, never `.`);
- a staged diff is reviewed with `git diff --cached --stat` before every commit.

## 2. Scope decisions (open questions resolved)

The design's open questions are settled as follows; docs are updated to match.

1. **Approvals are erased** (they can hold raw tool arguments and authority). **Action receipts are
   retained content-free**: id/run/tool/effect/status/timestamps plus a digest; content-bearing fields
   redacted in place.
2. **Completed `usage` rows are retained content-free** (tokens, model, cost, timestamps) so spending
   history is not silently rewritten; `usage` is reported in "remaining", not "erased".
3. **No separate draining phase in this increment.** Confirmation never kills a live process or
   proceeds past live work. If the Bot has active runs, confirmation requests cancellation
   (`store.request_cancel`) and fails closed with 409 naming them; the operator retries after they
   stop. Preview and confirmation both require zero active runs. This is simpler, reversible until
   commit, and fail-closed. The design's background drain/cancel-wait is future hardening.
4. **User-owned directories are never deleted**: folder-mode `--workdir`, `code-worktrees/`, backups,
   exports and anything outside the state directory. Managed paths only (`bots/<name>/runs/<id>`,
   `workspaces/<id>`, `browser-profiles/<id>`, `documents/<id>`, synthesis bytes recorded in the DB).
5. **Evidence is reachable from the API, CLI and the new dashboard page**; it is content-free.
6. **One transaction erases rows**; the request row, counts snapshot, evidence items and tombstone
   redactions commit atomically. Filesystem cleanup happens after commit from a fsynced manifest and is
   resumable on restart. No disk-shredding guarantee is claimed.

## 3. Deliverables and ownership (single writer per file)

| Phase | Deliverable | Files (write scope) | Owner |
|---|---|---|---|
| 1 | Deletion evidence schema v83 + migration hook + migration tests | `src/hutch/bot_deletion_schema.py`, `tests/test_bot_deletion_schema.py`, `src/hutch/store.py` (only the `_migrate_83` hook and list entry) | T1 |
| 2 | Command layer: preview, confirm, cleanup recovery, real-world-grade tests | `src/hutch/bot_deletion.py`, `tests/test_bot_deletion.py` | T1 |
| 3 | Typed JSON API + CLI destroy + contract tests | `src/hutch/server/bot_deletion_api.py`, `src/hutch/cli_bot_deletion.py`, `tests/test_bot_deletion_api.py`, `src/hutch/server/app.py` (hook only), `src/hutch/cli.py` (hook only) | T2 |
| 4 | Dashboard danger-zone page, browser journey, visual captures | `src/hutch/server/pages.py`, `src/hutch/server/templates/home.html`, new `bot_delete.html`/`bot_delete_pick.html`, new `static/bot-deletion.js`, `tests/e2e/test_bot_deletion_ui.py`, new artifacts dir | T3 |
| 5 | Docs, ledger, continuation, real-world script, final gate, commits | `docs/operations.md`, `docs/bot-config.md`, `docs/safety.md`, `docs/realignment/tests.md`, `README.md`, `website/llms.txt` (if clean), `docs/realignment/ledger.md`, `completion-plan.md`, `continuation-*.md`, `docs/realignment/verify_bot_deletion.py` | Lead |

Lead also reviews every diff, runs the focused gate, and is the only committer. Teammates never stage or
commit, and message the Lead when a deliverable is ready or blocked.

## 4. Interface contract (freeze before code)

### 4.1 Schema v83 (`bot_deletion_schema.py`, `migrate(db)`)

- `bot_deletions`: `id` (request id), `bot_id`, `bot_name_hash` (sha256), `actor`, `note`,
  `request_hash`, `token_hash` (64 hex, cleared to '' at terminal state), `status` in
  `('pending','confirmed','expired','superseded','failed')`, `counts_json`, `result_json`,
  `manifest_hash`, `cleanup_state` in `('none','pending','cleaning','cleaned','needs_attention')`,
  `cleanup_attempts`, `created_at`, `expires_at`, `confirmed_at`, `deleted_at`, `error`.
  No foreign key to `bots` (evidence survives the Bot). Index on `(bot_id, created_at DESC)`.
- `bot_deletion_items`: `id`, `request_id REFERENCES bot_deletions(id) ON DELETE RESTRICT`,
  `store_name`, `row_id` (opaque row id or sha256 of a path/hash; never content or paths),
  `original_content_hash` ('' or 64 hex), `erased_at`.
- Guards: insert only pending shapes; updates may only walk pending to one terminal outcome plus the
  cleanup-state transitions of a confirmed row; identity/counts fields immutable; no deletes on either
  table. Triggers are dropped and recreated so the migration is re-runnable.
- The migration changes no Bot and adds the normal pre-upgrade backup (handled by `Store._upgrade`).

### 4.2 Command layer (`bot_deletion.py`)

```python
DELETION_TOKEN_TTL_SECONDS = 600
DELETION_REMAINING: tuple[str, ...]          # honest what-remains statements
class BotDeletionConflict(ValueError): ...
def preview(store, bot_id, *, actor, note='') -> dict
def confirm(store, bot_id, request_id, *, token, confirmation, actor,
            idem_key=None, request_hash=None) -> dict
def requests(store, bot_id, *, limit=20) -> list[dict]
def recover_cleanup(store) -> dict           # resume committed-but-uncleaned deletions
```

- `preview` returns `request_id, token, expires_at, created_at, bot_id, bot_name, counts, remaining,
  confirmation_hint`; stores only the token hash; supersedes older pending requests for the Bot.
  `counts` is a flat `dict[str, int]` of non-zero store categories plus `total` (keys are the
  store names in section 5 plus `bot`, `files`). Responses never contain erased text, paths or tokens
  after the preview.
- `confirm` is idempotent on `(bot_id, request_id, idem_key, request_hash)`; KeyError for unknown
  request; `BotDeletionConflict` for stale/expired/superseded/reused/changed-scope/renamed-Bot/
  wrong-token/wrong-typed-address/live-run cases; ValueError for invalid input. It re-verifies inside
  `BEGIN IMMEDIATE`, aborts on any count change, erases rows in FK-safe order, redacts retained
  receipts, writes content-free items and the result, deletes the `bots` row last, then runs
  `PRAGMA secure_delete` around the transaction and a best-effort WAL checkpoint after commit.
- Filesystem cleanup: a private (0700) fsynced manifest `<state>/deletions/<request_id>/cleanup.json`
  written before the transaction; after commit, delete only managed paths derived from recorded ids,
  depth-first, never following symlinks out of the state directory; then update `cleanup_state`.
  A crash between commit and cleanup is resumed by `recover_cleanup`; a missing/corrupt manifest leaves
  `needs_attention` and is reported, never claimed complete.
- `recover_cleanup` is called at API-install time (server startup) and by the CLI before acting.

### 4.3 API (`bot_deletion_api.py`, installed from `app.py` in one hook line pair)

- `POST /api/v1/bots/{ref}/deletion-requests` (preview, 201) body `{note?}` (extra forbidden).
- `POST /api/v1/bots/{ref}/deletion-requests/{request_id}/confirm` body `{token, confirmation}`,
  requires `Idempotency-Key` (428 when absent; bounded printable ASCII; paired keys hashed per
  credential); 403 for paired-phone principals ("whole-Bot deletion is a local owner action"); 404
  unknown Bot/request; 409 conflicts; 422 invalid bodies; exact retry after the Bot is gone replays the
  stored result.
- `GET /api/v1/bots/{ref}/deletion-requests?limit=` returns content-free previews/outcomes, no tokens.
- Request identity helpers mirror `server/facts_api.py` (actor attribution, idempotency digest).

### 4.4 CLI (`cli_bot_deletion.py`, one hook in `cli.py`)

`hutch bot destroy NAME [--yes]`: preview, print exact counts and remaining, require the typed Bot
address (the name), then confirm. `--yes` skips only the prompt, never the preview. Exit 1 on refusal
or conflict, with the reason printed. `hutch bot delete` keeps its reversible meaning.

### 4.5 Dashboard (`pages.py` + new templates/JS; no parked-session file is edited)

- `GET /bots/delete` picker page (registered before `/bots/{name}`): lists Bots, empty state when none.
- `GET /bots/{name}/delete`: danger-zone page for one Bot; the two-step control is JS-driven against
  the API: preview shows exact counts and remaining; typed Bot name enables confirm; loading, empty,
  error and success states; `aria-live` error region; keyboard reachable; 44 px targets.
- The Overview page gets one link to the picker ("Permanently delete a bot"). The Bot page/SPA settings
  panel stay untouched because they are parked-session files; the design's settings-panel placement is
  recorded as a follow-up.
- Playwright journey: empty state, wrong typed name shows the error and erases nothing, correct flow
  confirms, at 1440x900 / 900x900 / 360x800 with no page errors and no horizontal overflow; captures go
  under `docs/realignment/artifacts/completion-2026-10-29/deletion/` with the exact browser revision.

## 5. Erase inventory (verify against the live schema before coding)

132 tables exist at v82. Direct `bot_id` columns: approvals, assistant_home_conversations,
channel_connections, channel_threads, code_handoffs, conversation_questions, conversations, documents,
event_sources, google_*_grants, integration_tool_grants, investigations, jobs, memory, memory_facts,
memory_purge_requests, opencode_session_bindings, outlook_*_grants, runs, schedule_identities,
schedule_occurrences(+_v20), syn_manifests, syn_plans, syn_sources, tasks, tool_allows, usage,
usage_reservations, workflow_runs, workspace_specialists.
Transitive children (no `bot_id`): messages, events, run_procs, run_compactions, transcript_delivery,
job_steps, media_jobs, persona_feedback, inv_* children, document_versions, uploads, channel_events,
channel_deliveries, conversation_* children, workspace_task* children, delegated_wait_continuations,
opencode_submissions, memory_facts_fts, conversation_fts (FTS shadow tables), and others the FK graph
names. The core module derives the erase order from `PRAGMA foreign_key_list`/explicit ordered lists,
then asserts `PRAGMA foreign_key_check` returns nothing and a second seeded Bot is byte-for-byte
untouched. `usage`, `tool_actions`, `idempotency_keys` and prior `memory_purge_*` evidence are
retained content-free/redacted, not deleted.

## 6. Acceptance tests (mapped to real-world scenarios)

1. Migration v82 to v83 preserves seeded data; evidence guards reject manual insert/update/delete;
   backup exists; fresh store is v83.
2. Preview counts exactly match rows and managed files changed; nothing is mutated by preview; token
   stored hashed only; response contains no erased sentinel text or user paths; empty Bot preview is a
   valid all-zero-besides-bot preview.
3. Confirm erases the inventory for one rich Bot; a second identically seeded Bot is untouched
   (rows, files, FTS); searches/APIs return nothing for the deleted Bot; action receipts are redacted
   but present; evidence rows are content-free and immutable.
4. Fail-closed: wrong token/typed address, expired, reused after terminal, superseded by a newer
   preview, renamed Bot, counts changed by a new message/run, and a live run (cancellation requested,
   conflict names it, nothing erased).
5. Idempotency: exact retry returns the stored result; different payload with same key conflicts;
   missing header is 428; after deletion a retry still replays.
6. Filesystem: managed run dirs/workspace/browser profile/documents removed; folder-mode workdir and
   code-worktrees survive; a symlink pointing outside the state dir is refused and reported as
   needs_attention; crash-after-commit simulation resumes via `recover_cleanup`; missing manifest is
   needs_attention and never claims success.
7. Permission: paired principal refused with 403 (pure helper test), local operator allowed; remote
   stays outside the route capability list.
8. CLI: preview print, typed-address refusal exits 1 and erases nothing, `--yes` happy path; API and
   CLI share one command path (no duplicate erase logic).
9. Dashboard journey and captures as in 4.5; empty state when no Bots; injected API error shows the
   banner and a retry restores the control; no console errors.

## 7. Commits (one focused change each)

1. `docs(operations): plan whole-Bot permanent deletion implementation` (this file).
2. `feat(deletion): add schema v83 deletion evidence tables` (T1 phase 1 + migration tests).
3. `feat(deletion): add governed whole-Bot deletion command layer` (T1 phase 2 + tests).
4. `feat(deletion): expose whole-Bot deletion through typed API and CLI` (T2 + tests).
5. `feat(deletion): add dashboard danger-zone page and browser journey` (T3 + evidence).
6. `docs(deletion): record implemented whole-Bot deletion and continuation` (Lead docs + ledger).

Every commit stages explicit paths only and is reviewed first.

## 8. Out of scope / blocked by the parked session

- Editing the 13 dirty templates, static JS/CSS, `website/index.html` or the eight dirty e2e files.
- The design's auto-drain/cancel-wait phase, schema-level admission fence, OS keyring clearing, and the
  settings-panel placement of the control. These become follow-ups in the continuation doc with exact
  paths, not silent claims.
- Marketing screenshot refresh of the parked brand site; the committed-HEAD marketing evidence from the
  previous run stands. Marketing copy that is clean (`website/llms.txt`, `README.md`) is updated when
  the feature lands.

## 9. Risks and mitigations

- **Erase-order bug** (FK RESTRICT, 132-table graph): derive/validate order, add
  `PRAGMA foreign_key_check`, rich seed tests, second-Bot isolation assertion; any error rolls back.
- **Accidental deletion of user-owned files**: manifest only records managed shapes under the state
  directory; symlink/no-follow checks; folder-mode/workdir never recorded; tests for both.
- **Partial cleanup after crash**: commit-then-cleanup ordering, resumable recovery, needs_attention is
  a first-class honest state.
- **Concurrent parked session**: single-writer file ownership above; explicit staging; frozen modules
  get hook lines only; check `git status` before every commit.
- **Scope creep**: dashboard settings-panel integration, drain phase, keyring clearing and marketing
  refresh are documented follow-ups, not part of this increment.

## 10. Contract clarifications and size-gate note (2026-10-29, before integration)

These clarify, and do not change, sections 4.2-4.4.

1. `requests(store, bot_id, *, limit=20)` returns content-free records with exactly these keys:
   `request_id, bot_id, status, actor, note, created_at, expires_at, confirmed_at, deleted_at,
   cleanup_state, counts, result`. No token, no path, no erased text. `result` is `{}` until confirmed.
2. Preview dict: exactly `request_id, token, expires_at, created_at, bot_id, bot_name, counts,
   remaining, confirmation_hint`. Result dict: exactly `request_id, status='confirmed', deleted_at,
   counts, remaining, cleanup_state`. `counts` is `dict[str, int]` including `total`.
3. `bot_name_hash == hashlib.sha256(bot_name.encode('utf-8')).hexdigest()` for the Bot's address.
4. Additive helper `request_record(store, request_id) -> dict | None` returns the item-1 record shape
   for one request id without needing a `bots` row. The API uses it to resolve `bot_id` before a
   retry (so an exact confirm retry works after the Bot row is gone) and for the replay path.
5. `confirm` replay order: (a) replay the idempotency receipt for the same scope/key/request hash;
   if none, (b) load the request row: if already `confirmed`, return its stored result when no
   idempotency key was supplied, but treat a different idempotency key/request hash as
   `BotDeletionConflict` (nothing is erased twice); (c) only then require a live `bots` row and
   validate expiry/token/typed address/counts. This is what makes acceptance 6.5 hold after deletion.
6. API confirm resolves the request record first: unknown request id -> 404; a confirmed request with
   the matching idempotency key replays even when the Bot row is gone; any other missing-Bot case ->
   404. Preview and GET history resolve `{ref}` to a live Bot and 404 when it is gone (history after
   deletion is reachable by request id replay, not by the deleted name).
7. CLI uses one idempotency key derived from the request id (`cli:<request_id>`) so a retry is safe;
   the command layer's replay rules above apply unchanged.

**Size-gate note.** `.file-size-baseline.json`, `scripts/audit_context_hygiene.py` and
`docs/agent-workflow.md` are untracked files authored by the parked dashboard session; the committed
repository and committed `package.json` have no size gate and committed `AGENTS.md` does not name
one. This slice does not modify the parked session's baseline or tooling. The required hook-only wiring
(`store._migrate_83`, `app.py`/ `cli.py` install hooks, `pages.py` routes) grows those four files by
a few lines; the parked-session guard may therefore report them, which the final evidence records as a
known, non-committed tooling waiver rather than a silent change. All feature logic lives in new modules
that the guard does not freeze.

## 11. Sanctioned v83 schema extension (2026-10-29, found during live-schema erase design)

The frozen 4.1 schema list was extended only where live-schema guards made the documented erase
inventory impossible, matching the operations design's own phrase "content-free tombstone columns and
guarded trigger allowances":

1. `conversation_artifact_shares` is rebuilt in place (idempotent detection via
   `PRAGMA foreign_key_list`): `target_conversation_id` -> CASCADE so a deleted chat's own shares go
   with it, `source_run_id`/`source_event_id` -> nullable SET NULL so revoked cross-chat history can
   survive its deleted source. Rows, both original indexes, the source guard, the once-only revoke guard,
   the cascade-aware no-delete guard and both outbox trigger sets are preserved; explicit deletes while
   the target conversation exists stay refused.
2. `tool_actions`, `action_reconciliations` and `memory_fact_decisions` keep their existing
   immutability but gain exactly one redaction shape each (summary='' + intent_json='{}' +
   result_json='{}'; evidence='[deleted]'; note=''), and only while the transient
   `bot_deletion_scope` marker row exists. The marker is written inside the one erase transaction and
   removed before commit, so every other writer keeps the original immutability.
3. `conversation_task_state_revisions` no-delete becomes cascade-aware with the same
   parent-row-gone rule already used by the task-state guards.
4. The share rebuild's nullable source ids require three narrow defensive reads in
   `store.revoke_conversation_artifact_share` (replay path, live path and returned row) so a revoked
   share whose source Bot was deleted returns revoked history instead of raising; Lead patches those
   after the command layer freezes.
5. Acceptance tests cover: migration with both share shapes and preserved data; purge-shaped allowances
   accepted once and every other mutation still refused with the original guard messages; the full
   focused regression list (api, fact memory, migration, action intents, receipts, persona receipts,
   workflow receipts, fact purge, deletion).
