# Release readiness: durables and slice log

Updated 2026-10-30. Read this first when resuming. Everything here was checked against the repository on
that date; recheck anything you rely on, and treat a changed file as invalidating its old evidence.

## Durables

**Goal.** A public, non-commercial release of Hutch whose frontend reads as the product it is: one shell, one
vocabulary, honest states, and no control that promises more than its backend does.

**Owner decisions (do not reopen).**

1. Merge Conversation history, Activity and Work history into one destination (default name "Activity",
   tabs Now / History / Conversations) unless screenshots show it is worse; keep `#/chats`, `#/overview`
   and `#/runs` working as redirects. Scheduled work stays separate.
2. Audit tooling is tracked, not deleted. Done.
3. No fixture-driven preview page is served from `src/hutch/server/static/`. Done, with a guard test.
4. Plan-wide approvals do not exist and no UI may offer them. Done.
5. The frontend does not yet read as the product Hutch is; coherence is a deliverable, not polish.
6. No other agent is active; the working tree and leftover worktrees are this work's responsibility.

**Authority.** Commit on `main` with explicit paths and no AI-attribution trailer. Never push, publish, tag
for release, deploy, add dependencies, sign, spend, or open any `*.db*` file, state directory or `.env*`.

**Canonical checks.**

```bash
npm run check:agent                 # context hygiene, tool contracts, constitution, agent map
.venv/bin/python -m pytest -q --no-header --tb=short -p no:cacheprovider tests/<file>.py
.venv/bin/python -m pytest -q --no-header --tb=line -p no:cacheprovider --ignore=tests/e2e   # ~21 min
npm run build:css --silent          # deterministic; a second run must change nothing
.venv/bin/python scripts/audit_emoji.py
.venv/bin/python scripts/worktree_tools.py prune        # dry run; --apply removes clean merged worktrees
```

The sandbox may block `uv` cache writes, so call `.venv/bin/python` directly. Browser: Playwright 1.63.0,
Chromium revision 1243. The agent map embeds tracked-file counts: stage every new file, regenerate
(`python scripts/generate_agent_map.py --write`), and commit the map with them.

**Hard-won cautions.**

- `tests/e2e` runs must not rewrite reviewed evidence. Two tests did; they now write to the isolated
  artifact root unless `HUTCH_ONBOARDING_EVIDENCE_DIR` or `HUTCH_DELETION_EVIDENCE_DIR` is set.
- Frozen over-cap files (see `.file-size-baseline.json`) may only shrink. New logic goes in new modules.
- The legacy `openModal` owns one dialog at a time; nested flows use `HutchOverlay.confirm`.
- Zsh does not word-split unquoted variables; use `bash` for loops over lists.

**Off-repository archive.** `~/hutch-quarantine-2026-10-30/` holds everything removed from the tree
(preview harness and fixtures, scrape dumps, bulk captures, brand research, re-captured evidence). Local
tags `archive/*` preserve every unmerged branch tip. Triage:
`docs/realignment/unmerged-branch-triage-2026-10-30.md`.

**Sources.** `docs/realignment/start-state-audit-2026-10-30.md` (findings S1-S9, fresh-state evidence,
comparison with Hermes Agent, OpenClaw and Grok Bot), `docs/realignment/long-horizon-prompt.md`,
`PRODUCT.md`, `DESIGN.md`, `docs/design-system.md`, `docs/overlays/COMPLETION.md`.

## Slice log

Status words: **verified** (checked by a command recorded here), **implemented** (code in, not independently
checked), **not run**, **open**.

| Slice | Status | Commits | Evidence |
|---|---|---|---|
| P0 reproducible repository: audit tooling, baseline, `.ai/` tracked; sdist allowlist; map within cap | verified | `d93ae7e2` `2dbe4787` `44ed5a2c` `8e663bc0` | fresh clone runs `check:agent` scripts and the README responsive command; emoji audit clean |
| P0 audit findings fixed by splitting, not by raising caps | verified | `70e4fa09` | `bot_deletion.py` 1067 -> 381 lines plus three layered modules; `cli.py` and `store.py` at or below their caps |
| P0 migration test fixture over-dropped tables | verified | `27d94414` | two upgrade tests that failed at clean HEAD pass; production migrations unchanged |
| P0 land the uncommitted work | verified | `79a37973` `29561b47` `332d44dc` `728e0b4f` `de4a84cd` | tree clean; focused browser suite 176 passed, 1 skipped, 0 failed (24 files) |
| P0 workflow currency ceiling (`budget.max_cost_usd`) | verified | `696b9f37` | 36 budget tests pass; ceiling cannot be raised or removed by amendment; frozen files below caps |
| P0 no preview or fixture file under `static/` | verified | this commit | `tests/test_static_has_no_demo_surfaces.py` fails on the old harness filename |
| P0 full non-browser suite green at a clean clone | see ledger | | recorded in `ledger.md` after the final run |
| P1 product spine (`product-spine.md`): definition, loop, canonical terms, navigation, contradiction list | verified | `2fedfc4f` | 36 contradictions in 9 groups (D, T, N, C, X, V, M, G, S), each with file and line and a phase or a keep-reason; line numbers re-read from the tree; two claims corrected after a wider search (C2 scope of "Stop all", X4 dead-template evidence). G1 (chat hides approval mode and spend) rests on source search, not a capture: decided by the P2 capture |
| P2.1 one title format `<View> — Hutch` (server pages, SPA first paint and every route; the SPA title is read from the sidebar label, `ROUTE_TITLES` removed) | verified | `0eacc863` | `tests/test_page_titles.py` 10 passed (red first), `tests/e2e/test_page_titles.py` 12 passed, nav consistency and dashboard tests 41 passed; `app.js` 14,353 -> 14,349 lines (new logic in `page-title.js`) |
| P2.2 Activity merge: one destination, views Now / History / Conversations (`activity.js`, `activity.css`); `#/overview`, `#/chats`, `#/runs[?q]` redirect in place; `/overview`, `/runs` redirect to the canonical hashes; palette equals the sidebar labels; "Manage assistants" -> "Assistants" | verified | `f0cd64ca` | `tests/e2e/test_activity_destination.py` 16 passed, `test_page_titles.py` 12, `test_studio_palette.py` 4, unit nav/dashboard/titles 44; red first for the nav and palette guards; screenshots of all three views at 1440 and 360 viewed (0 overflow, 0 console errors): the merge reads better than four overlapping rows, so decision 1 stands; `app.js` 14,349 lines (not grown) |
| P2.3a server shell parity: assistants roster and New assistant link in the shared sidebar macro, one brand label (C1, C3), no absolute state path in the footer (C4), Assistants row shown from ten assistants or when active, same rule as the SPA (N6) | verified | `074e56e4` | `tests/test_server_shell_parity.py` 5 passed (red first); unit nav/titles/dashboard/onboarding 69 passed; e2e onboarding, whole-assistant deletion, form heights, overlay layout 14 passed; `/usage` and `/models` captured at 1440 and 360 (0 overflow, 0 console errors) |
| P2.3b global emergency stop in the SPA header while work runs, behind the confirm overlay, kept reachable at 900 and 360 px; per-Task button renamed "Stop this task" (C2) | verified | `f4b4e530` | `tests/e2e/test_stop_all.py` 5 passed (cancel sends nothing, confirm sends one `POST /api/stop-all` with the CSRF header); `test_task_pages.py` 13 passed with it; paired-phone permission test passes and the server refuses `/api/stop-all` for paired principals (default-deny table, route not listed); `app.js` unchanged at 14,349 lines. Phone header wraps to two rows while the control shows: follow-up |
| P2.5 dead code: `/legacy` and `/legacy/` removed (X1); dead body of `bots_page` removed (X3); six templates with no renderer deleted (X4); `/models` links go straight to `/#/connections` and the Usage table links assistants to `#/bot/<name>` (X2, X5) | verified | `d60b40a3` | `tests/test_retired_surfaces.py` 12 passed (11 red first); 137 passed in the broader server-page suites (dashboard, connections, chatgpt, onboarding, nav, titles, shell, sse). The only dependent test was `test_dashboard.py::test_legacy_spa_stays_reachable`, a one-line leftover from the first server-rendered dashboard commit that asserted the duplicate exists; it is deleted and the retirement is pinned instead. **Kept, with reasons:** `/legacy/connections` and its form routes (the tested no-JavaScript path for connection keys and acknowledgements: `test_connections.py`, `test_chatgpt_integration.py`); `/bots/{name}` page (`bot.html`) until P4 proves the SPA covers its no-JS actions; `POST /bots` (P4) |
| P2.4 one vocabulary: the UI says "assistant" (V1, V2). Server templates and Python strings rewritten; SPA scripts rewritten by a JS-aware audit tool (`scripts/audit_ui_vocabulary.py`, `--fix`) that only touches prose in literals and visible attributes and refuses any change beyond bot/assistant words and articles; CLI text (`hutch bot ...`), identifiers, API paths and Telegram's own "bot" (`channels.js`) are exempt and pinned by tests | verified | this commit | `tests/test_ui_vocabulary.py` 73 passed (48 live-template hits and 163 `app.js` lines were red first); 187 passed across usage, dashboard, models page, nav, shell, retired surfaces, titles, fact purge, whole-assistant deletion; emoji audit clean; `app.js` 14,349 lines (in-place edits). Browser: of 37 failures in a 240-test run (`test_browser`, `test_design_system`, `test_task_pages`, `test_bot_deletion_ui`, `test_model_picker`, `test_fact_purge_ui`, `test_persistent_chat`, `test_wcag_fixes`), **19 also fail at baseline `3bcbe454`** (listed below), 18 were mine (old wording in assertions, the nine-row sidebar, a second "New assistant" link) and are fixed; one of the 18, `restored_state[1440]`, is a load-sensitive synchronous focus read that passes alone twice. **Process note:** a bulk phrase-sync over the whole test tree corrupted 139 files ("a stored" -> "an stored", "approval" -> "anpproval"); it was reverted exactly by reconstructing each file as `HEAD` plus my deliberate edits and confirming it reproduced the damaged file byte for byte, so no one else's edits were touched. Test wording updates since are exact-match and reviewed |
| P2.6 fresh-state acceptance: every destination (15) at 1440, 900 and 360 on an empty state directory | verified | `64a14393` | `tests/e2e/test_fresh_state_routes.py` 45 passed: every title is `<View> — Hutch` (and equals the sidebar label for destinations), 0 console errors, 0 page errors, 0 failed requests, 0 px horizontal overflow; screenshots viewed (first run at 360, `/models` at 1440). Chromium revision and Playwright 1.63.0 as recorded above |
| **P2 acceptance status** | **partly met** | | Met: one title format, nav consistency test green, old hashes redirect (`#/overview`, `#/chats`, `#/runs`, `/overview`, `/runs`), 0 errors and 0 overflow at three widths, one sidebar and one assistants label. **Not met: one chrome (C5).** Server pages still carry an always-visible Stop all and a "live" chip in the header, and put the page title in the body, where the SPA shows work status and puts the title in the shell header. Open follow-up, deliberately not forced: removing the always-visible stop breaks `test_overlays.py` which pins it, and the title move touches `models.html`/`usage.html` layout. The screenshots also show S2 plainly (first run: "OpenCode is ready", Models: "No model routes configured"): P3 |
| P3.1 S2: Models acknowledges a detected-but-unsaved AI service. A "Detected AI service" panel (`models-detect.js`) reads the same `/api/v1/opencode/status` and uses the same wording as first run, only when nothing is saved (the check can start a private OpenCode server, so it is never run on a plain page view); one click posts to the existing validated `/models/set-default`; the empty state now reads "No model routes saved yet" | verified | `bdb28708` | `tests/test_models_detected_route.py` 4 passed (the empty-page test red first); `tests/e2e/test_models_detected_route.py` 6 passed (ready with first-run copy then one-click save, connected-account copy, nothing ready, failed check with retry, three widths). **The status call is a labelled fixture; live OpenCode detection: not run.** Finding: the three stores behind "which route will I use" (workspace default, saved routes, live detection) are read by first run but only the second by Models; a running Ollama already counts as a route (existing behaviour) |
| P3.1b **every plain form POST on a server page was refused in Chromium** (`403 cross-site request refused`: the `no-referrer` policy makes the browser send `Origin: null`; `/models/set-default`, `/models/add`, delete, test, and the legacy connections and bot-delete forms). The first-run page had a same-origin referrer workaround; the shared base template did not. Fixed once in `base.html`; this is the "form-post-origin-null" residual gap that `test_route_state_boundaries.py` documents | verified | `bdb28708` | `tests/test_server_shell_parity.py::test_server_pages_keep_their_plain_forms_usable` 4 cases red then green; the real-browser click-through above exercises it end to end |
| P3.2 first run shows a Setup check (the `hutch doctor` findings, read-only) and offers the background service; installing is never automatic. New read-only `GET /api/v1/setup/check` (`setup_check_api.py`, registered from `pages.py`, no network, 0.09 s on a fresh state, paired phones denied by the default-deny table); `setup-check.js` renders it in the first-run rail; the install button opens a confirmation and only its confirm sends the Runtime page's `{confirm: "install", port: 8787}` | verified | `b701e74b` | `tests/test_setup_check_api.py` 5 passed (4 red first); `tests/test_remote_pairing.py` 41 passed with it; `tests/e2e/test_first_run_setup_check.py` 9 passed: viewing installs nothing, cancel installs nothing, confirm sends exactly one request, installed/unsupported hosts do not get the offer, findings show their fix, failed check offers retry, three widths. **`/api/v1/runtime` and the install are labelled fixtures (a real install writes a systemd unit on this machine): a live install is not run.** My P2.5 removal of `/legacy` had broken `test_remote_pairing.py::test_paired_route_inventory_is_total...` (it listed `/legacy` as an owner-only alias); that was missed because the suite was not in my P2.5 selection, and is fixed here. `app.js` unchanged at 14,349 lines |
| P3.3 a run whose owner process is gone does not stay "Working" | verified | this commit | `tests/test_orphaned_run_display.py` 3 passed against a **real** exited process recorded as owner and seeded before the app starts: the running supervisor alone recovers it to `failed` with `exit_reason: interrupted` and "the process running this job (...) exited before it finished"; `working_runs` returns to 0; a live owner is left alone over several beats; `hutch doctor` reports it as an orphan before recovery. Limits: the status chip still says "Failed" (the interrupted reason is in the run's error and exit reason; a distinct "Interrupted" chip would touch every `statusChip` caller), and until the next supervisor beat the row is briefly "Working" (bounded by the lease). My earlier stop-all fixture, a `running` row with no owner and no lease, is not a real orphan and is never recovered by design |
| P3.4 **an assistant could show "Working" forever**: the roster label is "any run in a live status", and recovery only handled lapsed leases and dead pids, so a live-status row with no owner and no lease (leftover or seeded rows) was never recovered. The supervisor and `hutch doctor` now treat a live row that nothing owns (no pid, no lease holder, older than a 5-minute grace) as an orphan and fail it as `interrupted` with "no process owns this job"; queued and parked runs and fresh rows are never touched | verified | this commit | `tests/test_orphaned_run_display.py` 8 passed (4 red first); 279 passed across engine, lease, doctor, scheduler, cancel, worker, lifecycle and delegation tests; `engine.py` stays at its frozen cap (1,837), `store.py` 12,576 of 12,593. Evidence that leftover rows are what an existing state directory shows is **not** available: state directories are off limits, so the owner should run `hutch runs` / `hutch status`, restart `hutch serve`, and expect old "Working" rows to become failed-interrupted |
| P3.5 **an assistant on a dead demo route no longer looks healthy**: it used to read "Idle" in the roster and "demo" on the composer chip and only failed when a message was sent. The server now computes one `route_problem` per assistant (`route_problem.py`: no model route, or a retired `mock/` route), carries it in `/api/bots`, and the roster reads "Needs a model route", the composer chip reads "Choose a model" (only while the *selected* route is the broken one, so choosing a real model for the next message restores the name), and the new-assistant drafts ask the server instead of matching a `mock/` string in three places; the picker's placeholder and error no longer name one vendor's model | verified | this commit | `tests/test_route_problem.py` 9 passed (red first); `tests/e2e/test_unusable_route_assistant.py` 3 (2 passed, the "choose a real model" case skips on this offline host and is covered by `test_model_picker.py`); 257 unit tests and 11 + 18 e2e tests around the picker, composer, task pages and assistant setup pass; the one existing assertion that expected "Idle" for a `mock/demo` coordinator fixture now expects the truth. **Still open, deliberately:** `mock/` guards for the saved workspace default (`app.js`), the "Retired mock" runtime label, and `LOCAL_RUNTIMES` in the picker; a data migration that offers to repair or remove leftover demo assistants; no existing state directory was opened, so how many such assistants a real install has is unknown |
| P3 start states and first success | not started | | S2, `hutch doctor` and service offer in first run |
| P4 UI promises versus backend sweep | partly done | `06887b15` `696b9f37` | see the table below |
| P5.1 first-run layout (S7): the hint "Nothing runs until you ask." floated alone in the right column and the rail sat under the form (the composer foot and the rail were both auto-placed grid children); on phones the composer's keyboard-hint rule hid the line entirely | verified | `3e677b88` | explicit grid areas in `studio.css` and the first-run override; `tests/e2e/test_first_run_layout.py` 5 passed (4 red first) at 1440, 1100, 900, 600, 360 |
| P5.2 docs truth: `PRODUCT.md` navigation sentence, `docs/design-system.md` (Chat library, Past work), `docs/requirements.md` UI-2 (Stop all), `docs/README.md` row for the archived `prompts/` directory; a permanent guard that public docs only link to tracked files and the README names only scripts that exist | verified | `5195b9c2` | `tests/test_docs_links.py` 2 passed (red first on the `prompts/` row); a first scan of 36 public docs found exactly those two broken links |
| P5.3 site and captures: the real first-run page (fresh state directory, no test mode, live AI-service detection) captured at 1440x1000, 900x1000 and 360x1200 into `website/assets/captures/`, with a new tablet source; `?v=` hashes, caption (date, viewports), alt text, README alt text, sitemap `lastmod` and `llms.txt` vocabulary updated; the caption no longer claims "no provider call" because that was never verified, it says no assistant was created and no request was sent to a model | verified | this commit | `tests/test_site_tokens.py` and `tests/test_claims.py` 41 passed; `tests/e2e/test_website.py` 42 passed after updating three pinned expectations (capture date, `naturalWidth` per viewport, the caption phrase); `test_first_run_layout.py`, `test_onboarding_page.py`, `test_onboarding_chooser.py` passed in the same run. **Deviation from the prompt, on purpose:** no *populated* dashboard capture was made for the public site. `PRODUCT.md` requires marketing captures to come from the actual empty first-run product and bans a seeded demo state, so a populated image would need synthetic data presented as the product; the populated state is covered by e2e screenshots in the isolated artifact root, not the site. OpenCode reported 9 options on the desktop capture and 8 on the phone one (live data), so no count appears in any caption. One e2e run overwrote `docs/onboarding/evidence/slice-02/handoff-before-375-dark.png`; restored, as the standing rule requires (that was `test_onboarding_chooser.py`, which defaulted to the reviewed evidence tree; it now writes to the isolated root unless `HUTCH_ONBOARDING_EVIDENCE_DIR` is set, and a rerun leaves `docs/` clean) |

| P6.1 build and install smoke (early, to de-risk P6; **P6 is not complete**) | verified | this commit | `uv build` (isolated cache) gives `hutch-0.1.0.tar.gz` and `hutch-0.1.0-py3-none-any.whl`. **Found: the sdist was 267 MB** (274 MB of evidence PNGs under `docs/`); excluding binary media under `docs/` gives **8.3 MB, 1,862 files** (wheel 3.2 MB), guarded by `tests/test_packaging_config.py` (red first); no test reads a docs image as input (the e2e test that names one only records the path). Installed the wheel and its declared dependencies into a fresh venv (the registry was read; no dependency was added or changed): `hutch version` = 0.1.0, `hutch init`, `hutch doctor` ("everything checks out"), package data present (37 scripts, 33 templates). Served `hutch serve --port 8798` from the **installed wheel** with a scratch state directory: `/`, `/models`, `/usage`, `/api/health` and the new static modules 200; `/legacy` 404; `/overview` and `/runs` 302 to the canonical hashes. Chromium 153.0.8010.12 (Playwright 1.63.0) loaded 7 routes at 1440 and 360: 0 console or page errors, 0 failed requests, 0 px overflow, every title `<View> — Hutch`. Also found and fixed: `hutch doctor` swallowed `[browser]` (Rich markup), printing `pip install 'hutch'` instead of `pip install 'hutch[browser]'` (`tests/test_cli_doctor_output.py`, red first; `cli.py` stays at its frozen cap of 2,758) |
| P6 release readiness (build, install, smoke; never publish) | not started | | |

## Platform work after the gap analysis (owner approved the order: honesty, orchestrator onboarding, catalog)

| Slice | Status | Commits | Evidence |
|---|---|---|---|
| C2 + C4: no invented prompts, and `mock` may only shrink | verified | this commit | Removed the chat welcome "Try one of these" grid, the first-run "Or start with an idea" buttons and the composer menu's "Start from a suggestion" prompts (all canned: "Sort downloads", "Repo sweep" and the like); the welcome screen keeps the real facts (approval summary, "Can use ..."). `tests/test_no_demo_content.py` 3 passed (red first on two leftovers it found in the composer menu): no canned phrase in the interface, a shrink-only per-file allowlist of `mock` mentions in product source, and `hutch init` seeds nothing. 39 browser tests pass (composer menu, first-run design system, first-run layout, fresh state at three widths). `app.js` 14,349 -> 14,283 lines |
| A1: the first assistant a person creates is their main assistant (the workspace coordinator), only when none is set and an existing choice is kept; the setup page says so for a first assistant ("This will be your main assistant, the one you talk to first. You can add specialists later, and it can hand them work for you to review": only what exists today, no promise of proposals) | verified | this commit | `tests/test_main_assistant.py` 4 passed (3 red first); 419 unit tests across coordinator, workspace, task, delegation, API, dashboard, deletion and conversations pass; setup, coordinator and task browser tests pass except the known baseline failures. Design note: rule is OpenClaw's team creation (the first coordinator becomes the system agent only if none is set), applied in `POST /api/bots`, not `Store.create_bot` |
| C1: an assistant that cannot run explains why in its empty chat and offers the two real actions (choose a model route in its settings, or remove it through the governed deletion page) | verified | this commit | `tests/e2e/test_unusable_route_assistant.py` 5 passed, 1 skipped (offline host) |
| Test expectations that assumed a `mock/demo` fixture reads "Idle" or a bare role now expect the truth (`Needs a model route · <role>`) | updated | this commit | `test_browser.py` setup-name and coordinator tests |
| **20th failure that predates this run**: `tests/e2e/test_delegation_clarification.py::test_specialist_question_is_answered_from_the_task_card` (answer button 40 px against 44 px), verified failing at `3bcbe454` in a throwaway worktree | recorded | | |

## UI promises versus backend (P4)

Every row is implemented, removed, labelled truthfully, or has an explicit reason. Evidence is the commit and its test.

| Item | Resolution | Evidence |
|---|---|---|
| "For this plan" approval that granted a single use (S1) | Removed; plan-wide approvals do not exist and the API refuses `plan_scope != 0` | `06887b15`, regression tests |
| Workflow spend ceiling specified by tests but unbuilt | Implemented (`budget.max_cost_usd`); cannot be raised by amendment | `696b9f37`, 36 budget tests |
| Models said "no route" while first run said OpenCode was ready (S2) | Implemented: detected-service panel plus one-click use through the existing validated endpoint; empty state reworded. Detection is a fixture in tests; live detection not run | `bdb28708` |
| **Every plain form POST on server pages was refused in Chromium** (403, `Origin: null`) | Fixed once in the shared template | `bdb28708`, `test_server_pages_keep_their_plain_forms_usable` |
| Page titles `hutch — hutch`, `Models - hutch` (S3) | Implemented: `<View> — Hutch` everywhere, derived from the sidebar label | `0eacc863` |
| `/models` and `/usage` outside the SPA shell (S4) | Implemented for sidebar, roster, brand label, footer, Assistants rule. **Reason kept open (not a promise defect):** the server header still has an always-visible Stop all and a "live" chip and the title sits in the body; `test_overlays.py` pins the stop control | `074e56e4`; P2 status row |
| Global emergency stop unreachable from the SPA (C2) | Implemented: header control while work runs, confirmed; the per-Task button renamed to say its scope | `f4b4e530` |
| Overlapping history destinations (S5) | Implemented: one Activity destination, old hashes redirect | `f0cd64ca` |
| First run did not offer `hutch doctor` or the background service | Implemented: read-only setup check and an explicit, confirmed service offer. Install is a fixture in tests; live install not run | `b701e74b` |
| A run whose owner process is gone showing "Working" | Verified already guaranteed by the supervisor (real exited process); chip wording "Failed" kept: the interrupted reason is in the run error. **Reason:** a distinct chip touches every `statusChip` caller | `ac29462a` |
| `/legacy`, `/legacy/` (duplicate of `/`) | Removed with its one stale test | `d60b40a3` |
| Dead body of `bots_page`, six unused templates | Removed | `d60b40a3` |
| `POST /bots`: a second creation path with no form and no caller, errors lost in a redirect | Removed | `0cf39d80`, `test_the_server_form_that_created_bots_is_gone` |
| `/legacy/connections` and its form routes | **Kept:** the tested no-JavaScript path for connection keys and acknowledgements (`test_connections.py`, `test_chatgpt_integration.py`); now usable in Chromium thanks to the form fix | `bdb28708` |
| `/bots/{name}` page (`bot.html`) | **Kept:** still reachable by bookmark and covered by the nav and deletion tests; vocabulary fixed; no UI links to it except bookmarks (Usage now links to the SPA) | `d60b40a3`, `6c888d11` |
| Every SPA API call and template form has a backend | Verified by a permanent test over about 290 calls and every template form; no dangling control found | `0cf39d80`, `tests/test_ui_endpoints_exist.py` |
| "accepted and ignored", "never implemented", "not implemented", `NotImplementedError`, "experimental" in `src/` | Swept. Hits are truthful diagnostics (plan scope refusal, wake IPC, desktop-portal adapter, abstract base method), capability tags (`experimental` is the labelling mechanism), or a stale internal DB guard message in `fact_memory.py:55` that no UI shows (purge works by tombstone). **Kept** | grep sweep, this section |
| Python-sourced API error text the SPA shows still says "bot" (for example "Bot settings" in six modules, `No bot named` on the API) | **Open follow-up, not a promise defect:** the UI vocabulary audit covers templates and SPA scripts, not API error strings; edits in frozen `app.py` must be line-neutral | P2.4 note |
| Seven merged-branch worktrees with uncommitted edits | **Not examined** (triage doc). Not release-blocking; owner action | triage doc |
| `agent-connections` themes (skill ZIP import, versioned effective configuration, persisted assistant identity, others) | **Owner product decision**; preserved at tag `archive/agent-connections-2026-10-11`; not merged | triage doc |
| Screen-reader and axe-core pass; live-model first-task journey | **Not run** | final report |

## Known failing at the pre-change baseline

Run on commit `3bcbe454` in a throwaway worktree (imports confirmed to come from the worktree), so these are not regressions
from P2. They belong to P3 (start states):

- `tests/e2e/test_route_state_boundaries.py::test_first_run_empty_state_and_cta[models]` and `::test_models_server_flash_error_banner`:
  the stub `ModelsView` has no `hw`, so `models.html:40` raises `Undefined.__round__` and `/models` returns 500.
- `::test_spa_route_error_state_and_retry[bots]`: after retry the route ends on `#/chat` with a retry button still present
  (the module's own residual gap `bots-empty-route-collapses`).
- `tests/e2e/test_wcag_measured_audit.py::test_skills_header_and_import_row_are_aligned`: field 44 px vs button 40 px.

## Known failing at baseline, second set (test_browser.py)

Found while verifying P2.4: these 19 fail at `3bcbe454` too (same 37-test selection run in a throwaway worktree). The earlier
"176 passed, 0 failed" focused run did not cover them. They are not regressions from P2; P6 must fix or document each:
memory export (phone), usage limits, chat choice question, conversation file browser empty state, coordinator specialist
dispatch, Gmail local grant, Google Calendar event creation scope, KDE Connect device access (1440 and 390), restored state
(phone), routine editor workflow link, scoped fact review (phone), tool permissions, virtual passkey over HTTPS, workflow
amendment preview adoption, workflow amendment drain control, workflow question draft after TCP disconnect, workflow studio
pending questions, workflow studio policy steps. Several assert a 44 px target against a 40 px control (`assert 40 >= 44`).

## Next

**Owner requests received during the run, answered in `platform-gap-analysis-2026-10-30.md`:** one named orchestrator created at onboarding that proposes specialists; presets moved out of code into a catalog; zero demo or fixture content. Removed so far: the "Working forever" cause (`1683156e`) and the dead-demo-route look (`2b8cad03`). The orchestrator onboarding, proposals, catalog and the migration for leftover demo assistants are **not done**.

Done and committed: P1 (`2fedfc4f`), P2.1 (`0eacc863`), P2.2 (see log). P3-P6 not started. Another `claude` session (and
Codex/OpenCode workers) is active in this checkout, contrary to the prompt's premise; it committed `245a2631`, `ef8573f8`,
`99880c70`. Stage by explicit path and recheck `git status` before every commit.

Open follow-ups noted while viewing the Activity captures: copy still says "tasks" and "past work" (vocabulary slice); the
History status filter and the tab strip share one green fill, so two similar controls stack at phone width (consider a quieter
active state for the tabs); `#fleet-nav` stays hidden below ten assistants in the SPA but always shows on server pages (N6).

Remaining in P2: header context C5 (server pages put the title in the body, the SPA in the shell header) and the final capture
at 1440/900/360 on a fresh state. Python-sourced API error strings that the SPA shows (for example "Bot settings" in 6 modules) still say
bot: out of this slice, noted for P4.
Then P3-P6. Follow-ups: phone header wraps while the stop control shows (360 px); tab strip vs History filter share one green.
