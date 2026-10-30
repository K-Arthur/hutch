# Responsive Adaptation - State

Last updated: 2026-10-29T19:10:00-07:00 | Last commit: 8525c208 (final source; final docs commit follows)
Goal id: goal-28c56178-ce15-4d56-b317-b0f275ff75cb (revision 1) | Branch: main
Status: COMPLETE - see COMPLETION.md. This file is kept as the run history.
Validation runner: scripts/validate_responsive.py (single source: scripts/responsive/config.py)
Evidence: docs/responsive/screenshots/<label>/{summary.json,assertions.txt,*.png}

## Status

| # | Task | Status | Commit | Evidence / next action |
|---|------|--------|--------|------------------------|
| 00 | setup: goal, team, research, audit, plan, harness, baseline | done | bb01f24d | screenshots/baseline-2a89909a |
| P0 | online research report | done | 3215d755 | research-2026-10-29.md |
| P0.5 | scored inventory | done | e4dfe6ce | inventory.md |
| P1 | responsive audit | done | e4dfe6ce | audit.md |
| 01 | viewport and safe-area contract | done | 9f74a378 | screenshots/9f74a378 |
| 02 | server navigation model | done | 2cf2c5fe | screenshots/2cf2c5fe + -nojs |
| 03 | dynamic viewport and keyboard | done | 28aa02e0 | screenshots/28aa02e0 |
| 04 | stylesheet structure and sticky offsets | done | c5d3beb4 | screenshots/c5d3beb4 |
| 05 | touch-target floor | done | 0fa93cfe | screenshots/0fa93cfe |
| 06 | safe-area chrome | done | 8b24b9ba | screenshots/8b24b9ba |
| 07 | 13-inch and tablet device bands | done | a1171d2e | screenshots/a1171d2e |
| 07b | reconcile rail width in app/src/input.css + rebuild ui.css | deferred | - | parked files; after the brand session commits, edit source and rebuild ui.css (never hand-edit generated CSS), then drop the responsive.css rail override |
| 07c | align SPA drawer breakpoint (900) with server overlay (1024) | deferred | - | needs coordinated style.css + studio.css + app.js edits across parked files; do it in one reviewed commit after the parked work lands |
| 08 | marketing site adaptation | done | db288fc1 | screenshots/db288fc1 + -nojs |
| 09 | final validation, review and docs | done | this docs commit | screenshots/8525c208 + clean-tree-parity |

## Final evidence

- Gate: .venv/bin/python scripts/validate_responsive.py --label 8525c208 --fail-on all
  -> 130 measurements (13 surfaces x 10 viewports), 0 failures, 0 CSS problems,
  contrast AA clean, 0 non-local requests, 13 interactive state captures.
- Clean-tree desktop parity: screenshots/clean-tree-parity compares commit
  2a89909a with 8525c208 in detached worktrees: 0 changed pixels at 1536,
  17/189 changed pixels at 1440 (live status indicators only); the baseline tree
  fails 5 of the final assertions that the work fixes.
- Review notes: screenshots/8525c208/review.md.

## Baseline evidence (pre-change)

Status: done, commit bb01f24d. Label baseline-2a89909a. Source baseline 2a89909a.
130 measurements, 0 assertion failures, 53 screenshots + 6 state captures
(7.4 MB). Warnings that drove the task plan: 28 coarse-pointer pairs below the
WCAG 24px target and 91/91 below the 44px comfort floor.

## Evidence index

- baseline-2a89909a: pre-change baseline (bb01f24d)
- 9f74a378: task 01 viewport and safe-area contract (evidence c390d8f0)
- 2cf2c5fe, 2cf2c5fe-nojs: task 02 server navigation (evidence 5818ab2b)
- 28aa02e0: task 03 dynamic viewport and keyboard (evidence e0850681)
- c5d3beb4: task 04 stylesheet structure (evidence 3a583128)
- 0fa93cfe: task 05 touch-target floor (evidence dab0dd9f)
- 8b24b9ba: task 06 safe-area chrome (evidence b91b3f8f)
- a1171d2e: task 07 device bands (evidence e16d461f)
- db288fc1, db288fc1-nojs: task 08 marketing site
- 8525c208: final gate
- clean-tree-parity/base, clean-tree-parity/final: desktop parity proof

## Parked-tree policy (kept for future sessions)

The working tree still carries another session's uncommitted brand/dashboard
work. Never stage, revert, clean or format those files. Commits used explicit
paths only. For a shared file that also carried parked hunks, the committed
content was built as HEAD + only the task change and staged with:

    git show HEAD:<path> > /tmp/head-<name>
    # build /tmp/mine-<name> = HEAD content + only this task's change
    BLOB=$(git hash-object -w /tmp/mine-<name>)
    git update-index --cacheinfo 100644,$BLOB,<path>
    git diff --cached -- <path>    # must show only this task's hunk

Local caveat: .git/info/exclude lists scripts/, so new files under scripts/
must be added with git add -f; tracked files stage normally. This caught
states.py during the final review. Do not edit that exclude file.

## Validation commands

    .venv/bin/python scripts/validate_responsive.py --quick --no-screenshots
    .venv/bin/python scripts/validate_responsive.py --label "$(git rev-parse --short HEAD)"
    .venv/bin/python scripts/validate_responsive.py --label final --fail-on all
    .venv/bin/python scripts/validate_responsive.py --no-js --label final-nojs --surfaces site-home

## Handoff (final)

- Objective complete: all nine tasks done, 07b and 07c deferred with reasons,
  COMPLETION.md written, final gate green, desktop parity proven on the committed
  trees, marketing validated at 375/768/1366 plus landscape and no-JS.
- If work resumes, the highest-value remaining items are 07b/07c after the parked
  brand work is committed, and a real iPad/Safari device pass (Chromium cannot
  emulate a notch, split view or the on-screen keyboard).
- Re-verify with the command above; evidence lands in
  docs/responsive/screenshots/<label>/.
