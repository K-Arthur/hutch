# Task 01 evidence review - viewport and safe-area contract

Commit under test: 9f74a378.
Run label: 9f74a378. Harness default fail-on set (overflow, errors, external,
ready, state, meta).

## Result

- 13 surfaces x 10 viewports = 130 measurements, 0 failures, 0 warnings for the
  gated kinds.
- Viewport contract: 130/130 pairs report a meta viewport with
  width=device-width, and 130/130 report viewport-fit=cover. Before this commit
  the server pages and the marketing site reported cover=false.
- Overflow: 0 pairs. Page errors: 0. Non-local requests: 0.
- States captured: sidebar open at 1180/1366, phone sheet open, server nav open
  at 375, focus at 1366/375.

## Desktop comparison against baseline-2a89909a

Two identical runs of the same commit (9f74a378 and a recheck run) differ in 31
of 59 screenshots: relative timestamps, live status dots, activity content and
marketing reveal state are dynamic. That run-to-run variation is larger than the
baseline-to-task-01 variation, so byte-identical screenshots are not a valid
criterion here.

Within that envelope, the chrome boxes are unchanged: for spa-studio and
pages-models at 1440 and 1536 the only baseline difference outside dynamic text
is a 10x10px status dot (88-117 px of 1.38M). The marketing header keeps its
geometry; the 768 and 1366 marketing differences match the same dynamic regions
seen between identical runs. No layout shift was observed at any desktop
viewport.

## Limits

- Chromium does not emulate a notch or the safe-area env() values; the inset
  rules resolve to 0px in the harness. The scripted meta assertion proves the
  contract exists; the rules were reviewed by hand. A real iOS/iPadOS device
  pass remains unavailable.
- Screenshots reflect the parked working tree (uncommitted brand work included);
  the committed tree was not render-verified in this task.
