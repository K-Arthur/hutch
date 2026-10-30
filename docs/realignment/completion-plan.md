# Completion plan: demo-fixture-free, validated realignment slice

Date: 2026-10-29. Author: harness Lead session. Status: execution plan, committed before code.

## 0. Plan-versus-repository reconciliation (read this first)

The task brief was written against the 2026-10-07 measured snapshot
(`docs/realignment/baseline.md`, commit `b3e4b15`). The repository has since advanced through the
realignment program (`docs/realignment/ledger.md`, schema v82, ~3,300+ offline tests). Most of the
brief's assumed gaps are already closed:

| Brief assumption | Current reality (evidence) |
|---|---|
| Dashboard pages serve hard-coded demo data from `TEMPLATE_INFO` | Server-rendered pages read the store; the mock runtime and `hutch demo seed` were removed on 2026-10-08 (`docs/realignment/no-mock-validation.md`); legacy `mock/*` rows are read-only repair records |
| `src/hutch/server/pages.py` contains placeholder context | No demo data found; the page routes query audit evidence and store APIs. Full inventory: `docs/realignment/completion-inventory.md` |
| README/website advertise unimplemented features | README, `website/llms.txt`, and the site copy already state development-preview limits; `docs/realignment/claims-audit.md` records earlier corrections |
| Playwright baselines absent; browser e2e never run | `tests/e2e/` is extensive and used by the project; installed Chromium revisions are present on this host |
| "Permanent deletion is not implemented" in README | README no longer claims it, but `docs/bot-config.md:32`, `docs/operations.md:488-489`, `docs/safety.md:14`, and `docs/realignment/tests.md` (T-DELETE-SEMANTICS) still record permanent scoped deletion as **unimplemented** |
| Scheduler recovery / model-route validation unfinished | Implemented in the realignment program (S2 claims/leases/recovery; provider route validation); out of scope here |

The conclusion is not "do nothing": the brief's *acceptance properties* are re-applied to the current
repository. The plan keeps the required order (research -> plan -> slice -> validation -> docs) and
picks the one high-impact unfinished backend feature the current evidence tree still names, plus the
verification work that the current tree has not recorded.

### Repository hazard: a parked uncommitted session

The main checkout contains another session's uncommitted brand/UI work (about 70 modified files plus
untracked assets under `.pipeline/brand/, src/hutch/server/static/, src/hutch/server/templates/,
website/index.html, package.json, tests/e2e/*`). Per `AGENTS.md` and `docs/concurrent-agents.md`:

- this slice never edits, stages, reverts, reformats or commits those files;
- slices C and D are therefore limited to verification plus files this session owns
  (`README.md`, docs, new tests, new partial templates if needed);
- commits contain only files reviewed and authored by this session; the pre-existing dirty tree is
  reported as-is, not cleaned.

## 1. Research evidence base

`docs/realignment/research-completion.md` (committed with this plan) covers, with cited sources:
local-first assistant complaints; multi-bot orchestration and dashboard fatigue; empty/loading/error
patterns; Playwright visual-regression CI practice (pinned browsers, ignore regions, SSIM thresholds);
developer-tool marketing credibility and GitHub Pages SEO; and the reported issue classes named in
the brief (OTP/login, model-route confusion, hidden spend caps, missing audit trails, demo-data
confusion, metrics resetting on deploy, tenant-scoping leaks).

Research conclusions that shape this plan:

1. **Keep** the evidence-first posture: no simulated runtime, explicit "not implemented" statements,
   approvals and fail-closed states.
2. **Avoid** new user-visible claims that are not backed by a test or a live check; avoid silent
   destructive actions; avoid "reset on deploy" metrics (all metrics stay in SQLite/derived).
3. **Fix in this slice** only what can be exercised locally: governed permanent deletion of reference
   facts, honest documentation of what deletion cannot retract, and state/visual regression evidence.

## 2. Inventory (full detail: `docs/realignment/completion-inventory.md`)

Summary of the current demo/fixture/TODO surface after a source scan:

| Class | Finding | Location | Action |
|---|---|---|---|
| User-facing demo data | None found. Dashboard empty states explicitly say Hutch creates no sample bots/runs | `templates/home.html:11`, `templates/bot_new.html:7` | none; regression-checked in Slice E |
| Legacy mock rows | Legacy `mock/*` model routes are readable for repair, labelled "Retired mock", never selectable | `static/app.js:3151,3153,8305,8309`; `docs/realignment/no-mock-validation.md` | keep (audited in Slice A) |
| Fixture code inside `src/` | `src/hutch/web/preview/fixtures.ts` and `bot-fixtures.ts` back an unlinked redesign-preview harness, not the product dashboard | `src/hutch/web/preview/`, `scripts/build_web_preview.mjs` | classify internal; no product exposure; do not edit (brand session owns the harness) |
| Test fixtures imported by product | None: `tests/support/` is imported only by tests | `tests/support/` | keep; Slice A re-verifies |
| TODO/FIXME markers | No user-facing TODOs; remaining `NotImplementedError`/opt-in refusals are honest capability boundaries (tools/base protocol, computer-use portals, cross-process wake IPC) | see inventory | keep; no code removal |
| Explicit "not implemented" claims | Permanent scoped memory deletion is the only small, locally verifiable backend gap named in current docs | `docs/bot-config.md:24,32`, `docs/operations.md:488-489`, `docs/safety.md:14`, `docs/realignment/tests.md:64` | Slice B |
| Other open items | macOS/Windows executors, signed installers, live providers/OAuth, physical phones, MCP facade, plan grants | `docs/realignment/desktop-production-2026-10-26.md` | out of scope; external prerequisites |
| Dirty-tree collisions | Brand/UI session files listed in `completion-inventory.md` | `git status --porcelain` | never touch |

## 3. Slices

### Slice A — demo-fixture-free verification (documentation + targeted fixes)

Scope: prove the user-facing product and site contain no demo data, and repair any genuine leftover
found by the inventory.

Work:
1. Classify every demo/fixture/mock/TODO hit as user-facing, test-only, or internal (inventory doc).
2. Check `src/` never imports `tests.fixtures`/`tests.support`; check no fixture rows are seeded at
   startup or first run.
3. Fix only genuine user-facing findings; otherwise record the negative result with file:line
   evidence in `completion-plan.md`/ledger.
4. Keep legitimate legacy-mock repair UI and preview-harness code, documented as such.

Acceptance:
- `rg -n "demo|fixture|mock" src/hutch/server/ website/` returns only documented test/legacy/preview
  references, each with a reason.
- No dashboard or marketing surface displays fabricated bots, runs, metrics, or approvals.
- Evidence recorded in this plan and the ledger.

### Slice B — governed permanent scoped deletion of reference facts

This is the feature current docs explicitly name as unimplemented. Semantics:

- **Scope**: one saved reference-fact *key* for one Bot, or all saved reference facts for that Bot.
  This purges: `memory_facts` revisions (content erased, tombstone retained), `memory_facts_fts`
  rows (deleted), legacy `memory` rows, outgoing/incoming `memory_fact_shares` snapshots (content
  erased), and `workspace_task_fact_shares` snapshots where this Bot is the source (content erased).
- **Two-step confirmation**: step 1 returns a preview with exact counts, affected scope, consequences
  and a one-time token (stored only as a hash, 10-minute expiry); step 2 requires the request id,
  token, and a typed confirmation (the exact fact key, or the Bot address for "all"). Wrong, stale,
  reused, or already-superseded requests fail closed.
- **Audit**: every request/confirmation is retained in `memory_purge_requests` (actor, time, scope,
  counts, result hash, status) plus content-free `memory_fact_decisions` history; tombstones keep
  ids, scope ids, revision numbers and content hashes so reviewers can prove what was erased without
  recovering it.
- **Honest limits**: conversation messages, run events/transcripts, context snapshots, files, and
  pre-existing database backups/provider inputs retain copies. Docs say so; the feature never claims
  otherwise.
- **Permission boundary**: only an owner-operator request; purge is single-Bot scoped; cross-Bot
  shares are marked purged and shown as such to the counterpart, never silently reused.
- **Surfaces**: `POST /api/v1/bots/{ref}/facts/purge-requests` (preview) and
  `POST /api/v1/bots/{ref}/facts/purge-requests/{id}/confirm`, typed pydantic bodies/responses;
  CLI `hutch bot purge NAME --key KEY [--yes]` and `--all`; no template edits (the memory settings
  template belongs to the parked brand session, so the UI control is documented as deferred).

Implementation outline:
- migration in `src/hutch/store.py` (`_migrate_82`): additive columns `purged_at`/`purge_id` on
  `memory_facts`, `memory_fact_shares`, `workspace_task_fact_shares`; purge-shape allowances on the
  immutability triggers (content changes only for an identical purge id and empty original content);
  `memory_purge_requests` table with immutability rules; no deletes of retained audit rows.
- `src/hutch/fact_memory.py`: `purge_preview()`, `purge_confirm()`, counting/selection helpers,
  tombstone content hash recomputation; update `page/history/export/count/incoming` queries to treat
  purged rows as erased (never re-display content or claim the key still exists).
- `src/hutch/store.py`: transactional command wrappers + bus notification + idempotency.
- `src/hutch/server/app.py`: typed routes and error mapping (404 unknown Bot/key, 409 stale/wrong/
  reused token, 422 invalid confirmation, 413/400 for oversized input).
- `src/hutch/cli.py`: two-step confirm, `--yes` skips the prompt but never the preview; prints counts
  and what remains.
- Tests: `tests/test_fact_memory.py` (semantics, FTS, shares, task snapshots, legacy rows, other Bots,
  restart, replay, expiry, wrong confirmation), `tests/test_api.py` (typed routes, status codes,
  idempotency surface, no response content leak), `tests/test_migration.py` (v82 upgrade preserves
  facts and their integrity; purge works after upgrade), `tests/test_cli.py` (two-step CLI).
- Docs: `docs/bot-config.md`, `docs/operations.md`, `docs/safety.md`,
  `docs/realignment/tests.md` T-DELETE-SEMANTICS, README feature note, ledger checkpoint.

Acceptance (all locally exercised): preview counts exactly match rows affected; confirmation erases
content from live DB + FTS + share snapshots; recall/search/API never return purged content; audit
rows and tombstones retained; wrong/expired/reused confirmations fail closed; a second Bot's facts and
shares are untouched; restart keeps the result; CLI and API exercise the same command path; focused
tests pass.

### Slice C — frontend state hardening (non-conflicting)

The dashboard templates and JS are being rewritten by the parked brand session, so this slice does
not edit them. Instead it hardens and proves the states the brief cares about with regression
coverage that the current tree lacks:

1. Inventory per page: empty, loading, error, permission-boundary states (inventory doc) and note
   gaps against `docs/requirements.md` UI-1/6/8.
2. Add a focused Playwright test module (new file) that, against a real local server and an empty
   store: asserts the first-run/empty state and call to action; injects a failing API response and
   asserts a visible error banner with retry; asserts loading affordance (SSE/skeleton or status
   region) on a page that has one; asserts destructive/owner-only controls are not rendered for a
   paired-device/limited scope where the API enforces it.
3. Do not modify the shared templates/JS; report residual gaps with file:line for the owning session.

Acceptance: new e2e tests pass locally on the installed Chromium; no horizontal overflow at
1440/900/360; screenshots captured under the session's own evidence directory; residual gaps listed.

### Slice D — marketing and claim accuracy

`website/index.html` is owned by the parked session; verifying rather than rewriting it:

1. Re-run the claim audit over `README.md`, `website/llms.txt`, `website/sitemap.xml`, and the
   committed (HEAD) `website/index.html`: every claim maps to a tested feature or an explicit
   experimental/preview label; no "demo"/"mock"/"coming soon" language contradicts reality; installs
   and downloads are not implied where none exist.
2. Update only clean, session-owned surfaces: `README.md` (feature note for Slice B + preview
   limits), `website/llms.txt` if stale (it is currently accurate), and docs.
3. Record that the live site is mid-redesign in another session and that its uncommitted copy was not
   reviewed or committed here; flag any stale claim for that session.

Acceptance: README/llms.txt accurately describe the completed feature set including Slice B; no
unsupported claim added; audit evidence in the ledger.

### Slice E — validation and self-review

1. Focused pytest for every touched behavior, then the broad non-e2e suite when the run cost is
   justified (`uv run --frozen --no-sync pytest -q --ignore=tests/e2e`; on this host the sandbox
   makes `uv` cache writes fail, so `.venv/bin/python -m pytest` is the equivalent local command;
   recorded in the ledger).
2. Playwright: new Slice C tests plus the existing state/design tests for touched pages at
   1440x900, 900x900, 360x800; capture screenshots and record Chromium version from the installed
   revision (Docker pinning is documented but unavailable offline; record exact revision instead of
   claiming Docker parity).
3. Self review: no new function over ~50 lines; docstrings on new functions; no duplicate logic;
   typed/validated API bodies and responses; no emoji; no AI attribution; check `npm run
   check:agent` if the touched files affect agent context; `python -m compileall`/import checks.
4. Update `docs/realignment/ledger.md` with a dated checkpoint: what was verified, exact commands and
   counts, limits, and the parked session's dirty files.

Acceptance: tests pass with recorded counts; screenshots and versions recorded; review findings
fixed or documented; ledger checkpoint appended; only session-owned files staged.

## 4. Commit plan (small, ordered, main checkout)

1. `docs: add completion research and plan for the demo-fixture-free slice`
   (`research-completion.md`, `completion-inventory.md`, this plan)
2. `feat(memory): add governed permanent deletion for saved reference facts`
   (migration, fact_memory, store, API, CLI, tests, docs)
3. `test(ui): cover empty, error, loading and permission states in the dashboard`
   (new e2e module + evidence; no shared-template edits)
4. `docs: record claim audit and verification evidence for the completion slice`
   (README/llms.txt/ledger/continuation docs)

Only files authored/reviewed by this session are staged. The pre-existing brand/UI working-tree
changes are never staged, reverted, or reformatted.

## 5. Risk log

| Risk | Mitigation |
|---|---|
| Parked brand/UI session owns templates, static JS/CSS, website/index.html, package files, several e2e files | Never edit/stage those paths; slices C/D restricted to new test modules and clean docs; inventory marks owned files |
| Migration/trigger changes could corrupt saved facts | Additive migration + pre-upgrade SQLite backup (existing), trigger recreation tested on a fixture database, integrity check (`fact_memory.validate`) run after purge, no row deletes of retained audit tables |
| "Permanent deletion" overclaimed | Docs enumerate what is erased and what remains (conversations, events, backups, provider inputs); tests assert non-claimed content stays absent from live memory surfaces |
| Concurrent session moves main while this session works | Re-read affected files immediately before staging; never force-push; report commit hashes |
| Playwright/browser drift | Use installed revision, record it; do not claim Docker-pinned baselines; screenshots are evidence only |
| uv writes denied by the DSH sandbox (`~/.cache/uv` read-only) | Use `.venv/bin/python -m pytest` for execution; record command; do not modify dependency state |
| Full suite too slow/expensive in this session | Run focused tests for every touched behavior; escalate to broad non-browser suite once, in the background, and record result |
| Another team member edits the same files | Write scopes recorded on the shared task board; Lead reviews final diffs and runs the gate |

## 6. Explicit non-goals

- macOS/Windows executors, signed/notarized installers, hosted sign-up (no local prerequisite).
- Live provider, OAuth, physical-phone or remote-network certification (no credentials/hardware).
- MCP facade, plan-level grants, vector memory, cross-OS work.
- Rewriting the dashboard or marketing site outside this session's ownership.


## 7. Execution status (2026-10-29, appended after verification)

| Planned item | State | Evidence |
|---|---|---|
| Research evidence base | done | `docs/realignment/research-completion.md` (316 lines, 54 cited sources) |
| Inventory of demo fixtures, TODOs and claims | done | `docs/realignment/completion-inventory.md` (216 lines; 2,097 hits classified; 0 user-facing demo values) |
| Slice A: demo-fixture-free verification | done | no user-facing demo data; mock runtime unselectable; `src/` imports no `tests/` module; usage label reworded; unlinked preview harness noted as owned elsewhere |
| Slice B: governed permanent deletion of reference facts | done and locally verified | schema v82 in `fact_purge_schema.py`; data layer `fact_purge.py`; API `server/facts_api.py`; CLI `cli_facts.py`; `tests/test_fact_purge.py`; broad focused group 200 passed / 1 skipped |
| Slice C: frontend state hardening | blocked, not attempted on owned files | templates/static/e2e owned by the parked dashboard session; gap list in `completion-inventory.md`; next steps in `continuation-C.md` |
| Slice D: marketing/claim accuracy | partial | README and `website/llms.txt` availability wording corrected; `website/index.html` owned by the parked session and not edited |
| Slice E: validation and self-review | partial | focused pytest groups, context-hygiene audit (only pre-existing other-session violation), focused Playwright checks; full non-browser suite and Docker-pinned visual baselines not run in this session |
| Documentation and continuation | done | ledger checkpoint appended; `continuation-B.md` and `continuation-C.md` written |
| Commits | on local `main` | commit only session-owned/reviewed files; the 153 pre-existing dirty entries from the parked session are never staged |
| Run-3 Slice B follow-up: whole-Bot permanent deletion | done and locally verified | schema v83 plus guarded allowances; command layer; typed API/CLI; dashboard picker/danger zone; tests listed in `continuation-B.md` update; real-world script PASS 52 checks; focused gate 187 passed; frozen-core Chromium journey 9 passed |
| Run-3 Slice C: dashboard hardening for the new page | done for the new danger-zone page; parked pages remain blocked | 12 reviewed captures under `docs/realignment/artifacts/completion-2026-10-29/deletion/`, 0 page errors and 0 horizontal overflow at 1440/900/360; parked page gaps and follow-ups in `continuation-E.md` |
| Run-3 Slice D: marketing/claims | partial | README and `website/llms.txt` now describe governed whole-Bot deletion; `website/index.html` still owned by the parked session |
| Run-3 Slice E: validation and review | done for the new feature | focused pytest groups including 187-test command/API/migration gate, browser journey 9 passed against frozen core, real-world script PASS 52 checks, Lead code review with four findings fixed and one schema-level blocker resolved via limited allowances |
