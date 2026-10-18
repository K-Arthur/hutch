# Workflow suggestion card accessibility review — 2026-10-11

This browser journey uses a synthetic event fixture to exercise the saved-workflow
suggestion card. It does not claim that a live model generated the suggestion or
passed selector qualification.

I opened the 1440px desktop, 768px tablet, 360px phone, 320px compact-phone,
review-dialog, WCAG text-spacing, and forced-colors captures. The saved-workflow
name wraps at narrow widths, the review action stays legible and at least 44px
high, and the explicit review dialog makes starting a saved workflow a separate
action. Cancel returns focus to “Review & run” and no workflow starts. Forced
colors preserve the card text, controls, and boundaries.

The 320px text-spacing view exposed the prior floating “Jump to latest” control
overlapping card content. The control now occupies its own row between the
transcript and composer. In both accessibility states, the review action remains
above the composer, the jump row stays below the scroll pane, and the document
has no horizontal overflow. Clicking “Jump to latest” scrolls to the feed's
maximum position and hides the control.

Chromium 153.0.8010.12 and Playwright 1.63.0 reported zero page errors, failed
requests, external requests, or workflow runs. Results include exact layout
bounds, computed forced colors, viewport widths, source hashes, and screenshot
and trace hashes in [results.json](results.json). I did not verify actual
browser-chrome zoom, screen-reader output, or physical devices; a headless
`Control+Equal` shortcut did not change the viewport or device-pixel ratio.

Scoped human scores: aesthetic 9.0/10, functionality 9.6/10, combined 9.0/10
using the product rule that overall is the lower score. This review covers the
suggestion card and its explicit review interaction only.
