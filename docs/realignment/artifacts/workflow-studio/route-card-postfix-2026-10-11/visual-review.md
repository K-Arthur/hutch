# Workflow suggestion card visual review — 2026-10-11

This is a UI regression capture for the recommendation text-color token fix. The
card contents come from a synthetic event fixture; this browser journey does not
establish that a model passed selector qualification or that a recommendation was
produced by a live model.

I opened the 1440px desktop, 320px compact-phone, and explicit review-dialog views.
The card uses the current base-content color, measured as rgb(240, 244, 249), across
all four sizes. Its long saved-workflow title wraps on phone; the explanatory copy
and simpler option remain readable, and the 44px Review & run action stays visible.
The status explicitly says that nothing started. Pressing Enter opens the saved-run
review dialog; Cancel restores focus and starts no workflow.

Chromium 153.0.8010.12 reported document widths of exactly 1440, 768, 360 and 320px,
no page errors, no failed or external requests, and no workflow run. Results,
computed styles, source hashes, and screenshot/trace hashes are in
[results.json](results.json); opened captures are beside this review.

Scoped human scores: aesthetic 9.0/10, functionality 9.6/10, combined 9.0/10 using
the product rule that overall is the lower score. This checks the recommendation
card and its explicit review step only. Browser zoom, text-spacing overrides,
forced colors, screen-reader output, and physical phones were not tested.
