# Responsive adaptation - completion

Status: complete. All planned tasks are done or explicitly deferred; the final
gate passes with every assertion kind enabled.

- Final source commit: 8525c208
- Final evidence: docs/responsive/screenshots/8525c208 (gate PASS)
- Clean-tree desktop parity: docs/responsive/screenshots/clean-tree-parity
- Ledger that recorded the run: STATE.md (kept for history; this file is the
  completion surface)

## What shipped

| # | Task | Commit | Evidence |
| --- | --- | --- | --- |
| 00 | setup: goal, research, audit, plan, harness, baseline | bb01f24d | screenshots/baseline-2a89909a |
| P0 | online failure-mode research | 3215d755 | research-2026-10-29.md |
| P0.5 | scored inventory | e4dfe6ce | inventory.md |
| P1 | responsive audit | e4dfe6ce | audit.md |
| 01 | viewport and safe-area contract | 9f74a378 | screenshots/9f74a378 |
| 02 | server navigation model | 2cf2c5fe | screenshots/2cf2c5fe, 2cf2c5fe-nojs |
| 03 | dynamic viewport and keyboard | 28aa02e0 | screenshots/28aa02e0 |
| 04 | stylesheet structure and sticky offsets | c5d3beb4 | screenshots/c5d3beb4 |
| 05 | touch-target floor | 0fa93cfe | screenshots/0fa93cfe |
| 06 | safe-area chrome | 8b24b9ba | screenshots/8b24b9ba |
| 07 | 13-inch and tablet device bands | a1171d2e | screenshots/a1171d2e |
| 08 | marketing site adaptation | db288fc1 | screenshots/db288fc1, db288fc1-nojs |
| 09 | final validation, review and docs | final docs commit | screenshots/8525c208 |

## Final gate

    .venv/bin/python scripts/validate_responsive.py --label 8525c208 --fail-on all

- 130 measurements (13 surfaces x 10 viewports), 0 failures.
- Checks: horizontal overflow, page errors, non-local requests, ready selectors,
  viewport contract (width=device-width + viewport-fit=cover), server nav model
  (JS and no-JS), stylesheet structure, style-scope, touch targets (24px AA),
  contrast (AA) and 13 interactive state captures.
- No horizontal overflow at 320/375/390, 844x390 landscape, 768x1024,
  1024x768, 1180x820, 1366x1024, 1440x960 or 1536x864.

## Desktop parity

Clean-tree comparison against the pre-change commit 2a89909a (see
screenshots/clean-tree-parity/review.md):

- 1536x864: 0 changed pixels for spa-studio and pages-models.
- 1440x960: 17 changed pixels (spa-studio) and 189 (pages-models), confined to
  live status indicators.
- The baseline tree fails 5 assertions that the work fixes (missing
  viewport-fit on server pages, phone-scoped rules, hardcoded sticky offset,
  inconsistent rail width); the final tree fails none.

## How to re-run

    .venv/bin/python scripts/validate_responsive.py --quick --no-screenshots   # fast loop
    .venv/bin/python scripts/validate_responsive.py --label <sha>              # full evidence
    .venv/bin/python scripts/validate_responsive.py --label <sha>-nojs --no-js --surfaces <pages...>

The matrix, surfaces and thresholds live in scripts/responsive/config.py.

## Boundaries and residual risk

- Chromium only: no real iPad/iOS Safari, notch, split-view or on-screen-keyboard
  pass was available. The visual viewport publisher uses the documented API and
  the keyboard scenario simulates a viewport shrink; real-device confirmation is
  still owed.
- 07b (deferred): the rail width still has two sources - app/src/input.css is
  authoritative and style.css keeps 272px for 901-1000px, which responsive.css
  overrides to 304px. When the parked brand work lands, reconcile the source and
  rebuild ui.css (never hand-edit generated CSS).
- 07c (deferred): the SPA drawer breakpoint (900px) and the server overlay
  breakpoint (1024px) still differ. Aligning them needs coordinated
  style.css/studio.css/app.js edits across parked files; do it in one reviewed
  change once the parked work is committed.
- The workflow/status cluster still hides below 1101px; the attention bar and
  Needs-you drawer carry pending state there.
- 110 sub-44px targets remain on coarse pointers (WCAG 2.2 AA is met): inline
  list links, segmented radio filters, a disclosure row and hidden inputs whose
  label carries the hit area (task 05 outcome lists them).
- Contrast sampling covers visible text on sampled surfaces, not every node.

## Code review notes

- No god functions: the harness is split by responsibility (config, seeding,
  harness, checks, capture matrix, state scenarios, report, structure check,
  entry point); capture.py is 252 lines, states.py 238.
- No TODO/FIXME left in the new code; no emoji (scripts/audit_emoji.py clean);
  CSS structure checker clean; all new code paths are covered by the committed
  validation run.
- Shared parked files were staged as HEAD plus only the task hunk; the parked
  session's uncommitted work is untouched and unstaged.

## Repo caveat for the next session

This checkout's local .git/info/exclude lists scripts/. New files under scripts/
must be added with git add -f (one was caught by the final review), while tracked
files stage normally. Do not change the exclude; it is another session's local
setup.
