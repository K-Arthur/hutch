# Responsive Adaptation - State

Last updated: 2026-10-29T18:38:00-07:00 | Last commit: 0fa93cfe (task 05 source)
Goal id: goal-28c56178-ce15-4d56-b317-b0f275ff75cb (revision 1) | Branch: main
Validation runner: scripts/validate_responsive.py (single source: scripts/responsive/config.py)
Evidence: docs/responsive/screenshots/<label>/{summary.json,assertions.txt,*.png}

## Status

| # | Task | Status | Commit | Next action / Blocker |
|---|------|--------|--------|----------------------|
| 00 | setup: goal, team, research, audit, plan, harness, baseline | done | bb01f24d | - |
| P0 | online research report | done | 3215d755 | - |
| P0.5 | scored inventory | done | e4dfe6ce | - |
| P1 | responsive audit | done | e4dfe6ce | - |
| 01 | viewport and safe-area contract | done | 9f74a378 | evidence: docs/responsive/screenshots/9f74a378 |
| 02 | server navigation model | done | 2cf2c5fe | evidence: screenshots/2cf2c5fe + 2cf2c5fe-nojs |
| 03 | dynamic viewport and keyboard | done | 28aa02e0 | evidence: screenshots/28aa02e0 |
| 04 | stylesheet structure and sticky offsets | done | c5d3beb4 | evidence: screenshots/c5d3beb4 |
| 05 | touch-target floor | done | 0fa93cfe | evidence: screenshots/0fa93cfe |
| 06 | safe-area chrome | not-started | - | insets on toast/workspace drawer/needs-you drawer |
| 07 | 13-inch and tablet device bands | not-started | - | depends 02/03/05; rail width + 1180/1366 tuning |
| 07b | reconcile rail width in app/src/input.css + rebuild ui.css | blocked | - | parked files: wait for the brand session to commit, then edit source and rebuild. Do not edit ui.css by hand. |
| 08 | marketing site adaptation | not-started | - | depends 01/05; coarse targets, no-JS nav, short landscape hero |
| 09 | final validation, review and docs | not-started | - | depends 01-08; full --fail-on all run + diff review |

## Baseline evidence (pre-change)

Status: done, commit bb01f24d. Label: baseline-2a89909a. Source baseline commit 2a89909a (the docs commits after it do not change the UI).
Result: 13 surfaces x 10 viewports = 130 measurements, 0 assertion failures, 53 screenshots
plus 6 state captures (sidebar open at 1180/1366, phone sheet open, server nav open at
375, focus at 1366/375), 7.4 MB committed under docs/responsive/screenshots/baseline-2a89909a/.
Warnings recorded for the tasks above: 28 coarse-pointer pairs with targets below WCAG
2.5.8's 24px (marketing footer links 20px, brand lockup 22px, and more listed in
summary.json) and 91/91 coarse pairs with targets below the project's 44px floor.
Contrast: 0 violations across 26 sampled pairs. Non-local requests: 0.

## Parked-tree policy (non-negotiable)

The working tree carries another session's uncommitted brand/dashboard work (about 168
dirty entries; it fluctuates as other sessions commit their own docs). This task never
stages, reverts, cleans or formats those files. Commits use explicit paths for
session-authored files only. For a shared file that also carries parked hunks, stage a
blob of HEAD plus only this task's change:

    git show HEAD:<path> > /tmp/head-<name>
    # build /tmp/mine-<name> = HEAD content + only this task's change
    BLOB=$(git hash-object -w /tmp/mine-<name>)
    git update-index --cacheinfo 100644,$BLOB,<path>
    git diff --cached -- <path>    # must show only this task's hunk

Then commit; the parked hunks stay uncommitted in the working tree. Keep new work in new
files (src/hutch/server/static/responsive.css, static/responsive.js, website/responsive.css)
where possible.

## Validation commands

    # fast loop, no screenshots: assertions only
    .venv/bin/python scripts/validate_responsive.py --quick --no-screenshots --fail-on none

    # full evidence run for a commit
    .venv/bin/python scripts/validate_responsive.py --label "$(git rev-parse --short HEAD)"

    # gate: after the fixes, warnings for 24px targets and states become failures
    .venv/bin/python scripts/validate_responsive.py --label final --fail-on all

## Evidence index

- baseline-2a89909a: pre-change baseline (commit bb01f24d)
- 9f74a378: task 01 viewport and safe-area contract (evidence commit c390d8f0)
- 2cf2c5fe: task 02 server navigation model (JS on and no-JS runs; evidence commit 5818ab2b)
- 28aa02e0: task 03 dynamic viewport and keyboard (evidence commit e0850681)
- c5d3beb4: task 04 stylesheet structure and sticky offsets (evidence commit 3a583128)
- 0fa93cfe: task 05 touch-target floor (under-24 0; under-44 110)

## Handoff

- Done this session: goal + ledger; Phase 0 research; Phase 0.5 inventory; Phase 1 audit;
  numbered task plan; re-runnable validation harness; clean pre-change baseline evidence.
- Nothing source-level has been adapted yet; every UI surface is unchanged from 2a89909a.
- Next session: read this file, then git log --oneline -15 and git status. Start task
  01 (docs/responsive/tasks/01-viewport-and-safe-area-contract.md), which creates the
  responsive foundation sheets and adds the viewport contract assertion. Update this file
  in the same commit as the status change, and end with a Handoff block.
- Known constraints: no real iPad/Safari available; Chromium does not emulate notches or
  the on-screen keyboard, so those checks are rule-shape + scripted viewport-resize tests,
  recorded honestly. The host is shared and heavily loaded; a full evidence run takes
  about 2-5 minutes.
