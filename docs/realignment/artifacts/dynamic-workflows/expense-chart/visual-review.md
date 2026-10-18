# Expense category SVG verification — 2026-10-11

A deterministic workflow grouped six disposable input rows into three categories, published the SVG through Hutch's artifact store, and passed an artifact SHA-256 read-back check before the browser loaded it. The browser then downloaded the exact verified bytes from the run artifact endpoint and rendered those bytes as an SVG image.

The opened 960×420 capture has a clear title, descending horizontal bars, category names and numeric values. The label and number columns remain distinct; the file has an accessible SVG title and description. The browser reports zero horizontal overflow, no page errors and no external requests. The SVG is 1,333 bytes. Screenshot, raw SVG, trace, source hashes and runtime details are retained beside this review.

This validates Chromium rendering of the standalone artifact at its 720px natural width. It does not add an inline SVG viewer to the workflow UI, and it does not cover mobile artifact preview, browser zoom, or OS-level screen-reader output.
