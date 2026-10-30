# 09 - Final validation, review and docs

## Scope

- docs/responsive/screenshots/<final-commit>/ (evidence run)
- docs/responsive/STATE.md, README.md and COMPLETION.md (only if every
  non-deferred task is done)
- README.md (repository root) and docs/design-system.md only for the responsive
  contract rows the task plan established

## Failure mode

Without a final gate, the individual tasks can each look green while the
combined tree regresses desktop, leaves a task row stale, or ships screenshots
that no longer match the code. The mission also requires an explicit diff
self-review and a state ledger that matches git log.

## Change

This is a gate, not a feature: it makes no product code changes except a
documentation correction if the review finds a task file that no longer matches
reality.

1. Run the full validation harness at the final commit with --fail-on all
   (overflow, errors, external, ready, state, touch24) plus the static CSS
   structure check; archive summary.json, assertions.txt and every screenshot.
2. Desktop regression: compare 1440/1536 screenshots for spa-studio,
   pages-models and site-home against baseline-2a89909a; record the comparison in
   the evidence directory (a short review note plus the side-by-side file names).
   Pixel-equivalence is expected except where a task intentionally changed a
   desktop-visible behaviour, which must be named.
3. Marketing validation at 375, 768 and 1366 (plus no-JS) reviewed
   individually, not from a contact sheet.
4. Code review: diff scope against task files, god-function check on new code,
   a11y spot checks (focus visible, labels, no hidden critical actions), no
   horizontal overflow, no render-blocking additions, no TODO without a STATE
   entry, no emoji.
5. STATE accuracy: every row matches git log; every done row names its commit;
   every in-progress row has a wip commit or a shippable diff; every blocked row
   has a recorded question; every TODO/comment in code has a STATE entry.
6. Write COMPLETION.md only if all non-deferred tasks are done; otherwise keep
   STATE.md as the status surface and leave a final Handoff block.

## Validation

- Full harness run exits 0 with --fail-on all.
- Evidence directory committed and listed in STATE.md.
- git status shows only the parked session's untouched files plus no stray
  session artifacts; every task commit is on main.
- The Handoff block names the literal next command for a fresh session.

## Rollback

No product code changes to roll back; revert the evidence/docs commit if the
gate itself recorded wrong data.

## Parked-tree integration

Docs and evidence only; no shared-file staging is needed except the optional
README/docs rows, staged explicitly.

## Size check

One validation run plus a review pass: one session.
## Outcome

- Status: done.
- Final gate: docs/responsive/screenshots/8525c208 (130 measurements, 0 failures
  with --fail-on all; every failure kind enabled, css problems 0, 13 state
  captures).
- Clean-tree desktop parity: docs/responsive/screenshots/clean-tree-parity
  compares pre-change commit 2a89909a with final commit 8525c208 using detached
  worktrees: 0 changed pixels at 1536, 17/189 changed pixels at 1440 confined to
  live status indicators; the baseline tree fails 5 assertions the work fixes.
- Marketing reviewed at 375/768/1366 plus 844x390 landscape and no-JS variants.
- Review pass: diff confined to planned paths; harness split by responsibility
  (capture.py 252 lines, states.py 238); no TODO/FIXME in new code; emoji audit
  clean; CSS structure clean; STATE rows checked against git log; documented
  caveat that local .git/info/exclude lists scripts/ so new files there need
  git add -f.
- COMPLETION.md written; 07b and 07c recorded as deferred with next actions.
