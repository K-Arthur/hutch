# Clean-tree desktop parity

Purpose: prove the adaptation did not change desktop rendering, independent of the
parked session's uncommitted brand work.

## Method

Two detached git worktrees were created from the repository (not from the parked
working tree):

- base: commit 2a89909a, the pre-change source baseline.
- final: commit 8525c208, the head of the responsive work.

Each tree was measured by running the committed harness from the final worktree
with PYTHONPATH pointed at that tree's src/, cwd inside that tree, so the app
templates, static sheets and Python code all come from the tree under test. The
marketing site server still serves the harness checkout; only app surfaces were
compared, and only at desktop widths.

Evidence here: base/ and final/ each contain the run summary, assertions and the
four desktop screenshots plus the state captures produced by that run.

## Assertion difference (what the work fixed)

- base: 5 failures, all expected and all fixed by the task series:
  - meta: pages-models at 1440 and 1536 lacked viewport-fit=cover;
  - styles: the preflight/context rules were still phone-scoped at 1440;
  - styles: .run-head sticky top 54px did not follow a measured --topbar-h;
  - styles: rail width 272px at 960 versus 304px at 1024/1180/1366.
- final: 0 failures.

## Pixel comparison (same viewport, same content seed)

| capture | changed pixels | bounding box |
| --- | --- | --- |
| spa-studio-desktop-1440.png | 17 | 9x29 region (live status dot) |
| spa-studio-desktop-wide-1536.png | 0 | none |
| pages-models-desktop-1440.png | 189 | 29x250 strip (status dot / relative time text) |
| pages-models-desktop-wide-1536.png | 0 | none |

No layout, spacing, typography or chrome geometry differences were detected at
desktop widths; the only changed pixels are live status indicators. The working
tree (with the parked brand work) differs by design from these clean-tree
captures and is covered separately in each task's evidence directory.
