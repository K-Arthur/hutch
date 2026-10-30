# Long-horizon prompt: product coherence, completion and release readiness

Paste everything below the line into one session. It is written so the run does not need a fresh
session per phase: progress lives in a tracked file and survives compaction.

---

# Hutch: product coherence, completion and release readiness (single long-horizon run)

You are a senior full-stack engineer finishing Hutch (a local-first multi-bot assistant platform: Python 3.11+, FastAPI, SQLite, a vanilla-JS dashboard, a static marketing site, a Tauri host) for a public, non-commercial release. Work autonomously through every phase below in this one session. Do not stop at a phase boundary, do not ask about anything this prompt already decides, and do not redo research that already exists.

## Authority
- You own all uncommitted work in the main checkout (about 200 modified or untracked entries from two earlier sessions) and every leftover worktree. No other agent is active. Read before you commit; never discard work you have not read.
- Commit directly on `main`: one focused change per commit, explicit paths only (hunk-level staging when a file mixes concerns), concise imperative messages, no AI-attribution trailer (AGENTS.md forbids it; a commit-msg hook checks).
- Never: push, publish, tag, deploy, add dependencies, sign anything, spend money, open any `*.db*` file, state directory or `.env*`, or delete branches and worktrees outside `.worktrees/completion-*`. Preserve the local-first, explicit-approval model; do not broaden tools, permissions or data sharing as a side effect.
- Ask the user only when a step needs one of the external actions above, or an irreversible choice that PRODUCT.md and this prompt cannot settle. Otherwise decide, record the decision and reason in the progress file, and continue.

## Decisions already made (do not reopen)
1. Merge Conversation history, Activity and Work history into one destination (default name "Activity", tabs Now / History / Conversations) unless captured screenshots show the merge is worse. Keep `#/chats`, `#/overview` and `#/runs` working as redirects. Scheduled work stays separate: it is configuration, not history.
2. Audit tooling is tracked, not deleted: the `scripts/audit_*.py`, `generate_agent_map.py`, `check_commit_attribution.py`, `validate_responsive.*`, `scripts/responsive/`, `.file-size-baseline.json`, `.ai/`, `docs/agent-workflow.md`, `docs/repository-hygiene.md` and their tests. Reason: the committed README and a tracked test already depend on hidden files, and AGENTS.md names these gates.
3. The fixture-driven `redesign-preview.*` harness must not be served from `src/hutch/server/static/`.
4. Plan-wide approvals do not exist and no UI may offer them (fixed in `06887b15`).
5. The owner's diagnosis: the frontend does not read as the product Hutch is. Treat coherence as a first-class deliverable, not polish.

## Verified starting state (2026-10-30; recheck anything you rely on)
- HEAD was `1ac75db1`. Read first: `docs/realignment/start-state-audit-2026-10-30.md` (findings S1-S9, fresh-state evidence, comparison with Hermes Agent / OpenClaw / Grok Bot). Earlier work: `completion-plan.md`, `continuation-B/C/E.md`, the ledger.
- Fresh-state capture of 15 routes: 0 console errors and 0 overflow. Real contradictions: Models says "No model routes configured" while first run says OpenCode is ready (S2); titles `hutch — hutch` and `Models - hutch`; `/models` and `/usage` are separate server pages with different chrome and a different nav label; overlapping history destinations.
- `.git/info/exclude` hides the tooling listed in decision 2. Committed README lines 59-61 tell readers to run `scripts/validate_responsive.py`; tracked `tests/test_commit_attribution.py` references hidden modules; HEAD's `package.json` has no `check:agent`.
- Uncommitted tree: (a) brand slices 7A-7C (commit grouping suggested in `.pipeline/brand/2026-10/HANDOFF.md` section 2); (b) models/forms/usage work (`models.html`, `pages_models.py`, `modelview.py`, `hutch-form-controls.css`, `persona.js`, others). Known failing: `tests/test_workflow_usage_budget.py` (dirty, +88 lines) and `tests/e2e/test_design_system.py::test_persona_live_preview_is_explicit_isolated_cancellable_and_responsive` (40 px vs 44 px). `redesign-preview.*` is an untracked fixture bundle.
- Current audit findings: `src/hutch/bot_deletion.py` 1067 lines, `tests/test_bot_deletion.py` 771, `tests/test_commit_attribution.py` 419 (new files over the 400-line cap); `cli.py` +2 and `store.py` +12 over frozen caps. Split; never extend a frozen file.
- A full non-browser run at clean HEAD was in progress in `.worktrees/completion-verify`, log under the earlier session's scratchpad (it may be gone). Its result is unknown and it had shown at least one failure. Use the log if present, otherwise rerun.
- Host: Linux, `.venv`, Playwright 1.63.0 with Chromium revision 1243. The sandbox may block `uv` cache writes; `.venv/bin/python -m pytest` is the equivalent. A full non-browser run takes about an hour under load: run it in the background, and only at the end of P0 and P6.

## How to run without new sessions
- Create `docs/realignment/release-readiness-progress.md` first, with two sections. Durables: the decisions above, canonical commands, source pointers. Slice log: id, acceptance, status (implemented / verified / not run / blocked), commit hash, evidence path, next action. Update it after every committed slice. If `eng-kit` exists, also save a checkpoint under task id `hutch-release-readiness` (`~/.claude/skills/feature-dev/references/long-tasks.md`).
- After any compaction: reread the progress file, `git status`, `git log -15`; recheck evidence whose files changed; restate the remaining acceptance in two lines; resume the next slice. This overrides AGENTS.md's "fresh session per task" advice; the progress file replaces it.
- Slice size: at most three source files plus one seam. Name exact files and line ranges. Prefer quiet commands. Read ranges of large files (`app.js` is about 14k lines, `store.py` about 12k). Never read lockfiles, generated CSS, evidence artifacts or `.venv`.
- One primary skill per task: `delivery` for P0 and P6, `diagnosing-bugs` for any unexplained failure, `feature-dev` or `tdd` for P1-P5. Loading a skill authorizes nothing.
- Tests first for behavior changes; focused tests per slice; every new or changed tool gets contract tests; no emoji; edit CSS sources and rebuild (`npm run build:css`), never the generated files.
- Report implemented / verified / not run / blocked separately. A fixture or mock pass is not live proof. Record exact Chromium and Playwright versions instead of claiming Docker parity. Use one scratch root and run `scripts/prune_validation_tmp.py` at the end.

## Phases (each ends with its acceptance met, committed and logged)

**P0 Make the repository reproducible and clean.**
- Track the audit tooling per decision 2: review every file for secrets and absolute paths, remove the matching lines from `.git/info/exclude` (keep `.worktrees/`, local caches and build output ignored), commit as one tooling commit. A fresh `git clone` into a temp directory outside the repo must run `check:agent` and the README's responsive-validation command.
- Resolve the audit findings by splitting modules (bot_deletion, the two test files, the cli and store additions). Do not raise baseline caps.
- Land the brand and models/forms/usage work in focused groups after verifying each: `npm run build:css` produces no diff, emoji audit clean, tests per group. Diagnose and fix the two known failing checks; fix real defects, not assertions.
- Keep `redesign-preview.*` out of the served tree, with a test asserting no preview or fixture file lives under `static/`.
- Gate: full non-browser suite green at the landed tree with exact counts; `git status` clean.

**P1 Product spine (the coherence deliverable).** Read `PRODUCT.md`, README "What is Hutch", the `DESIGN.md` sections you need and `BRAND-GUIDELINES.md`. Write `docs/realignment/product-spine.md`: a one-paragraph product definition; the primary loop (ask, approve, result, repeat or schedule); one canonical term per concept across UI, CLI and docs (assistant vs bot, work, needs you); the navigation derived from that loop. Then list every surface or string that contradicts it, with file and line: demo-like copy, chat-product framing that hides approvals, schedules and spend, duplicate concepts, labels that differ between SPA and server pages. Acceptance: the spine doc and the contradiction list; every item is assigned to a phase or has an explicit keep-reason.

**P2 Navigation and shell.** Implement decision 1. Unify page titles to `<View> — Hutch`. Make `/models` and `/usage` use the same shell and chrome as the SPA (or move them in), with one label for the assistants destination. Remove dead duplicates only after tests show nothing depends on them: `/legacy` serving the same file as `/`, the dead body of `bots_page`, `/legacy/connections` if the SPA covers it. Update `nav.py`, `index.html`, `ROUTE_TITLES` and the nav tests together. Acceptance: nav consistency test green; old hashes redirect; a fresh-state capture shows one title format, one chrome, 0 console errors and 0 overflow at 1440, 900 and 360.

**P3 Start states and first success.** Fix S2: Models acknowledges a detected-but-unsaved service with a one-click "use this route", with copy consistent with first run. Make first run lead to a verified first success: surface `hutch doctor` findings and the background-service step in the flow (offer, never silently enable). Every page gets real empty, loading, error-with-retry and permission-boundary states (skeletons matching the final layout, one polite live region). Verify with a new fresh-state Playwright module and a seeded-state pass; verify that a run whose owner process is gone shows as interrupted, not "Working". Run one real first-request journey only if a local or free route is available and needs no new credentials; otherwise record "not run".

**P4 Completion sweep: UI promises versus backend.** List every control, form and endpoint whose backend is partial. Search `accepted and ignored`, `never implemented`, `not implemented`, `NotImplementedError` and `experimental` in `src/`, and trace every button handler in `templates/` and `app.js`. For each: implement it, remove it, or label it truthfully with the reason, and add a test. No control may grant less than it says; the plan-approval defect is the model. Acceptance: a table in the progress file with no unresolved row.

**P5 README, site and docs truth.** Capture the final dashboard at 1440, 900 and 360 (empty and populated, from a scratch state directory) into `website/assets/`. Update `website/index.html`, `llms.txt`, the sitemap, the README and `docs/` claims to match. Fix every document that points at a file or command a fresh clone lacks. Keep "development preview" wording honest. Run the website e2e and metadata checks.

**P6 Release readiness (never publish).** Build the sdist and wheel locally, install into a temp venv, and smoke `hutch init`, `hutch doctor` and `hutch serve` (HTTP 200, no console errors). Verify version, LICENSE, THIRD_PARTY_NOTICES, SECURITY.md and the docs index. Write `docs/release-checklist.md` separating what you verified from what needs the owner (PyPI name, signing, GitHub release, hosting, macOS and Windows). Final gates: full non-browser suite; focused Playwright journeys at three widths with versions recorded; `check:agent`; emoji audit; clean tree; a ledger entry with commands and counts; remove `.worktrees/completion-verify` and scratch roots.

## Done means
Every phase is committed on `main`; the progress file shows each acceptance met or blocked with a reason; a fresh clone passes the audits; the app reads as one product (one vocabulary, one shell, one title format, honest states); no control promises more than its backend does; the final report lists implemented / verified / not run / blocked with exact commands and counts.
