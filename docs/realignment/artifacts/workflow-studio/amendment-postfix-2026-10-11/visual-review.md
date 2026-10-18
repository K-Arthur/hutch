# Workflow amendment preview visual review — 2026-10-11

This focused review covers the amendment preview copy and color-token correction, plus
the phone capture of its required pending-question cancellation choice. The Chromium
journey used a real SQLite store, workflow supervisor and typed API, with no provider
calls.

I opened the preview at 1440×960 and 768×1024, and the editor and cancellation state
at 320×740. The read-only diff remains the first actionable content after readiness;
the long candidate hash stays within the preview; old and proposed values read as
“old to new.” The recommendation now uses the existing primary text token. On phone,
the dialog keeps its title and fixed actions visible while the content scrolls. The
complete cancellation label wraps above the footer; the browser measured its bottom
within 1 CSS pixel of the footer edge. The adoption action stays disabled until the
choice is checked.

Across 1440, 768, 360 and 320 CSS pixels, the dialog stayed in the viewport, measured
horizontal overflow was zero, and the adoption target was 44px high. The interaction
used Enter to adopt with an idempotency key, archived the old question, created a new
question under the amended revision, and restored focus to the composer. The run had
zero page errors, failed requests or provider calls. Viewport bounds, source hashes,
and screenshot/trace hashes are in [results.json](results.json); the opened views are
the editor, preview, explicit-cancellation and post-adoption PNGs beside this file.

Scoped human scores: aesthetic 9.0/10, functionality 9.6/10, combined 9.0/10 using
the product rule that overall is the lower score. The existing graphite surfaces,
emerald action, amber human-review cue, type and spacing remain consistent. The
full-plan JSON editor is still dense and asks the owner to know the workflow schema;
a structured step editor remains an open product improvement.

Browser zoom, text-spacing overrides, forced colors, a screen-reader pass, physical
phones and offline reconnect were not tested in this review.
