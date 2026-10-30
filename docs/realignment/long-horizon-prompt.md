# Long-horizon prompt: product coherence, start states and release readiness

Paste everything below the line into one session. Progress lives in a tracked file, so the run survives
compaction and does not need a fresh session per phase. P0 (making the repository reproducible and clean)
and P1 (the product spine, commit `2fedfc4f`) are done; this prompt starts at P2.

---

# Hutch: product coherence, start states and release readiness (single long-horizon run)

You are a senior full-stack engineer finishing Hutch (a local-first multi-bot assistant platform: Python 3.11+, FastAPI, SQLite, a vanilla-JS dashboard, a static marketing site, a Tauri host) for a public, non-commercial release. Work autonomously through every phase below in this one session. Do not stop at a phase boundary, do not ask about anything this prompt already decides, and do not redo research that already exists.

## Authority
- You own the working tree and every leftover worktree; no other agent is active. Read before you commit; never discard work you have not read.
- Commit directly on `main`: one focused change per commit, explicit paths only, concise imperative messages, no AI-attribution trailer (AGENTS.md forbids it; a commit-msg hook checks).
- Never: push, publish, tag for release, deploy, add dependencies, sign anything, spend money, open any `*.db*` file, state directory or `.env*`, or delete branches or worktrees that hold unmerged work. Preserve the local-first, explicit-approval model; do not broaden tools, permissions or data sharing as a side effect.
- Ask the user only when a step needs one of the external actions above, or an irreversible choice that PRODUCT.md and this prompt cannot settle. Otherwise decide, record the decision and reason in the progress file, and continue.

## Decisions already made (do not reopen)
1. Merge Conversation history, Activity and Work history into one destination (default name "Activity", tabs Now / History / Conversations) unless captured screenshots show the merge is worse. Keep `#/chats`, `#/overview` and `#/runs` working as redirects. Scheduled work stays separate: it is configuration, not history.
2. Audit tooling is tracked. Done.
3. No fixture-driven preview page is served from `src/hutch/server/static/`. Done; `tests/test_static_has_no_demo_surfaces.py` guards it.
4. Plan-wide approvals do not exist and no UI may offer them. Done.
5. The owner's diagnosis: the frontend does not read as the product Hutch is. Treat coherence as a first-class deliverable, not polish.

## Verified state (2026-10-30; recheck anything you rely on)
- The working tree is clean and `main` holds everything: tooling, the brand integration, the shared style layer, the dashboard shell, forms, overlays, tasks and models page, the workflow currency ceiling (`budget.max_cost_usd`), and the branch triage. Read first: `docs/realignment/release-readiness-progress.md` (durables, slice log, open items), then `docs/realignment/start-state-audit-2026-10-30.md` (findings S1-S9, fresh-state captures, comparison with Hermes Agent, OpenClaw and Grok Bot) and `docs/realignment/unmerged-branch-triage-2026-10-30.md`.
- Gates: `npm run check:agent` passes all four checks, from the repository and from a fresh clone. The README's responsive-validation command resolves from a clean clone. A focused browser run of 24 e2e files gave 176 passed, 1 skipped, 0 failed. Full non-browser suite results are in `docs/realignment/ledger.md` (latest 2026-10-30 entry).
- Fresh-state capture of 15 routes: 0 console errors and 0 overflow. Real contradictions still open: Models says "No model routes configured" while first run says OpenCode is ready (S2, the Models page lists only saved routes while first run reads live detection); titles `hutch — hutch` (Tasks, Skills) and `Models - hutch`; `/models` and `/usage` are separate server pages with different header chrome and a different assistants label ("Manage assistants"); overlapping history destinations.
- First run does not offer `hutch doctor` findings or the background-service step. `/legacy`, `/legacy/connections` and the dead body of `bots_page` in `server/pages.py` are candidates for removal once tests show nothing depends on them.
- Preserved off-repository: `~/hutch-quarantine-2026-10-30/` (removed preview harness and fixtures, scrape dumps, bulk captures, brand research, re-captured evidence) and local tags `archive/*` for every unmerged branch tip. `archive/agent-connections-2026-10-11` holds 63 commits of unintegrated work (skill ZIP import, versioned effective bot configuration, persisted assistant identity and others) that needs a product decision, not a merge.
- Seven worktrees whose branches are merged still carry uncommitted edits (listed in the triage doc); they were not examined.
- Host: Linux, `.venv`, Playwright 1.63.0 with Chromium revision 1243. The sandbox may block `uv` cache writes; call `.venv/bin/python` directly. A full non-browser run takes about 21 minutes; run it in the background and only at the end of P6.

## How to run without new sessions
- `docs/realignment/release-readiness-progress.md` exists: update its slice log after every committed slice (id, acceptance, status as implemented / verified / not run / blocked, commit hash, evidence). If `eng-kit` exists, also save a checkpoint under task id `hutch-release-readiness` (`~/.claude/skills/feature-dev/references/long-tasks.md`).
- After any compaction: reread the progress file, `git status`, `git log -15`; recheck evidence whose files changed; restate the remaining acceptance in two lines; resume the next slice. This overrides AGENTS.md's "fresh session per task" advice; the progress file replaces it.
- Slice size: at most three source files plus one seam. Name exact files and line ranges; read ranges of large files (`app.js` is about 14,350 lines, `store.py` about 12,570). Never read lockfiles, generated CSS, evidence artifacts or `.venv`.
- One primary skill per task: `delivery` for P6, `diagnosing-bugs` for any unexplained failure, `feature-dev` or `tdd` for P1-P5. Loading a skill authorizes nothing.
- Tests first for behavior changes; focused tests per slice; no emoji; edit CSS sources and rebuild (`npm run build:css`, deterministic), never the generated files.
- Frozen over-cap files may only shrink; put new logic in new modules. The agent map embeds tracked-file counts: stage every new file, regenerate it (`python scripts/generate_agent_map.py --write`), and commit it with them.
- Browser tests must not rewrite reviewed evidence; they write to the isolated artifact root unless a refresh directory is set. After any e2e run, check `git status` for changes under `docs/**/artifacts` and `docs/onboarding/evidence` and restore them.
- The legacy `openModal` owns one dialog at a time; nested flows use `HutchOverlay.confirm`. Assert asynchronous focus with `expect(...).to_be_focused()`, not a synchronous read.
- Zsh does not word-split unquoted variables; use `bash` for loops over lists.
- Report implemented / verified / not run / blocked separately. A fixture or mock pass is not live proof. Record exact Chromium and Playwright versions instead of claiming Docker parity.

## Phases (each ends with its acceptance met, committed and logged)

**P1 Product spine (done; read `docs/realignment/product-spine.md` and use its contradiction list as the work queue for P2 to P4).** The original brief: read `PRODUCT.md`, README "What is Hutch", the `DESIGN.md` sections you need and `BRAND-GUIDELINES.md`. Write `docs/realignment/product-spine.md`: a one-paragraph product definition; the primary loop (ask, approve, result, repeat or schedule); one canonical term per concept across UI, CLI and docs (assistant vs bot, work, needs you); the navigation derived from that loop. Then list every surface or string that contradicts it, with file and line: demo-like copy, chat-product framing that hides approvals, schedules and spend, duplicate concepts, labels that differ between SPA and server pages. Acceptance: the spine doc and the contradiction list; every item is assigned to a phase or has an explicit keep-reason.

**P2 Navigation and shell.** Implement decision 1. Unify page titles to `<View> — Hutch`. Make `/models` and `/usage` use the same shell and chrome as the SPA (or move them in), with one label for the assistants destination. Remove dead duplicates only after tests show nothing depends on them. Update `server/nav.py`, `index.html`, `ROUTE_TITLES` and `tests/test_navbar_consistency.py` together. Acceptance: nav consistency test green; old hashes redirect; a fresh-state capture shows one title format, one chrome, 0 console errors and 0 overflow at 1440, 900 and 360.

**P3 Start states and first success.** Fix S2: Models acknowledges a detected-but-unsaved service with a one-click "use this route", with copy consistent with first run. Make first run lead to a verified first success: surface `hutch doctor` findings and the background-service step in the flow (offer, never silently enable). Every page gets real empty, loading, error-with-retry and permission-boundary states (skeletons matching the final layout, one polite live region). Verify with a new fresh-state Playwright module and a seeded-state pass; verify that a run whose owner process is gone shows as interrupted, not "Working". Run one real first-request journey only if a local or free route is available and needs no new credentials; otherwise record "not run".

**P4 Completion sweep: UI promises versus backend.** Finish the table in the progress file. Search `accepted and ignored`, `never implemented`, `not implemented`, `NotImplementedError` and `experimental` in `src/`, and trace every button handler in `templates/` and `app.js`. For each: implement it, remove it, or label it truthfully with the reason, and add a test. No control may grant less than it says; the plan-approval defect and the workflow currency ceiling are the models. Acceptance: no unresolved row.

**P5 README, site and docs truth.** Capture the final dashboard at 1440, 900 and 360 (empty and populated, from a scratch state directory) into `website/assets/`. Update `website/index.html`, `llms.txt`, the sitemap, the README and `docs/` claims to match. Fix every document that points at a file or command a fresh clone lacks (verify from a fresh `git clone`). Keep "development preview" wording honest. Run the website e2e and metadata checks.

**P6 Release readiness (never publish).** Build the sdist and wheel locally, install into a temp venv, and smoke `hutch init`, `hutch doctor` and `hutch serve` (HTTP 200, no console errors). Verify version, LICENSE, THIRD_PARTY_NOTICES, SECURITY.md and the docs index. Write `docs/release-checklist.md` separating what you verified from what needs the owner (PyPI name, signing, GitHub release, hosting, macOS and Windows). Final gates, from a fresh clone: `check:agent`, the full non-browser suite, the focused browser journeys at three widths with versions recorded, the emoji audit, a clean tree, and a ledger entry with commands and counts. Remove scratch roots and run `scripts/prune_validation_tmp.py`.

## Done means
Every phase is committed on `main`; the progress file shows each acceptance met or blocked with a reason; a fresh clone passes the gates; the app reads as one product (one vocabulary, one shell, one title format, honest states); no control promises more than its backend does; the final report lists implemented / verified / not run / blocked with exact commands and counts.
