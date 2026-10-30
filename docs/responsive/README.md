# Responsive adaptation

Small-viewport adaptation of the Hutch frontend: phones (320-430px), tablets
(768-1366px), and 13-14 inch devices in both orientations, without changing the
desktop experience. This directory is the durable memory for that work: a fresh
session should be able to resume from STATE.md plus git log alone.

## Status

- Complete: [COMPLETION.md](COMPLETION.md) (final gate PASS at 8525c208).
- Run history, task rows and handoff: [STATE.md](STATE.md).

## Document map

| File | Purpose |
| --- | --- |
| research-2026-10-29.md | Phase 0 online research: failure classes, sources, implications |
| inventory.md | Phase 0.5 bounded discovery: scored source inventory and read budget |
| audit.md | Phase 1 audit: exact file/line responsive findings, prioritised |
| tasks/NN-*.md | Numbered, independently executable task files (scope, failure mode, change, validation, rollback, size check) |
| screenshots/<label>/ | Committed visual evidence for one run: PNGs plus summary.json and assertions.txt |
| STATE.md | Single source of truth for task status and handoff |

## Reproducing validation

The matrix, surface catalogue and thresholds live in one place:
scripts/responsive/config.py. The runner is scripts/validate_responsive.py;
scripts/validate-responsive.sh is a thin wrapper for the documented command.

    # fast loop: three surfaces x three viewports, assertions only
    .venv/bin/python scripts/validate_responsive.py --quick --no-screenshots --fail-on none

    # full evidence run for a commit (writes docs/responsive/screenshots/<label>/)
    .venv/bin/python scripts/validate_responsive.py --label "$(git rev-parse --short HEAD)"

    # promote warnings to failures once the fixes land
    .venv/bin/python scripts/validate_responsive.py --label final --fail-on all

Each run boots the real FastAPI app on an ephemeral loopback port with a
deterministic seeded workspace plus the static marketing site, then measures:

- horizontal overflow (document scrollWidth against viewport width);
- WCAG 2.5.8 minimum targets (24px) and Hutch's 44px comfort floor on
  coarse-pointer contexts;
- WCAG AA contrast of visible text with composited translucent backgrounds;
- page errors and non-local requests (the local-first invariant);
- ready-selector presence for every surface.

Exit code is driven by --fail-on (default: overflow,errors,external,ready,state).

## Evidence policy

Screenshots are committed, not just viewed. One directory per validated run:

    docs/responsive/screenshots/<label>/
      summary.json      machine-readable results, failures, warnings, git state
      assertions.txt    human-readable assertion roll-up
      *.png             surface screenshots and interactive state captures

Labels are the commit short sha for validation runs; the pre-change baseline uses
baseline-<sha>. Measurements run against the live working tree, so an evidence
run records how many uncommitted entries were present. If another session's
uncommitted work is in the tree, screenshots include it; that is recorded in the
summary, not hidden.

## Working with the parked (uncommitted) tree

This checkout carries a large body of another session's uncommitted brand and
dashboard work. Hard rules, from AGENTS.md:

- never revert, clean, format, stage or commit those files;
- stage explicit paths only, never a broad git add;
- when a shared file needs a change, build the committed content as
  HEAD + only this task's change and stage that blob, leaving the parked hunks
  in the working tree:

    git show HEAD:<path> > /tmp/head-<name>
    # produce /tmp/mine-<name> = HEAD content + only this task's change
    BLOB=$(git hash-object -w /tmp/mine-<name>)
    git update-index --cacheinfo 100644,$BLOB,<path>
    git diff --cached -- <path>      # review: only this task's hunk

  The working tree keeps the parked change; the commit contains only the
  reviewed hunk. Never commit a tree where another session's hunk is staged.

## Conventions

- No emoji in source, docs or UI.
- One logical change per commit; the message names viewport, failure mode and
  validation done.
- Every change traces to a task file; update STATE.md in the same commit as a
  status change.
- No god functions: measurement, orchestration, report writing and entry-point
  wiring stay in separate modules.
