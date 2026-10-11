# Parked workflow pause/resume visual review

Captured and opened the owner Studio run card at 1440×960, 768×1024, 360×800 and
320×800 CSS pixels in Chromium 153.0.8010.12. The test used the real SQLite store,
workflow supervisor and versioned HTTP API with a deterministic ask/transform plan;
it made no model-provider calls. The page had no JavaScript errors.

The **Paused** label is next to the workflow title and remains readable as the long
workflow name wraps. The actions stay grouped in the card header: Resume and Stop remain
available, while the owner can still inspect the parked run and answer its pending
question. At 768px the title wraps without colliding with the actions. At 360px and
320px the actions wrap into a vertical stack; Pause/Resume targets measure 44px high,
and the document has 0px horizontal overflow. The workflow card keeps its existing
bounded internal scroll so the conversation and composer remain usable on short screens.

The browser path paused the parked run, answered its question while paused, verified that
the attempt and downstream node did not advance, resumed it, and observed a fresh attempt
complete the downstream transform. Keyboard focus moves from Pause to Resume after the
control changes, then from Resume to Refresh after the run is resumed. A second run was
stopped while paused; its pause bit cleared. The paired-phone view displays **Paused** and
exposes no Pause/Resume controls.
Phone credentials receive 403 for both owner-only mutations. The website's updated
workflow preview, availability row and recovery FAQ were also opened at 1440, 768, 360
and 320px; the added sentence wraps within the existing private-preview panel and the
page made no external requests or JavaScript errors.

The capture set, Playwright trace, bounds, browser version, per-file hashes and source
hashes are recorded in `results.json`. Website screenshots and hashes are recorded in
`docs/realignment/artifacts/dynamic-workflows/marketing/results.json`.

The one-shot Impeccable detector reported five advisory findings in the affected UI
targets: existing out-of-scale radii at `style.css:1425` and `style.css:1771`, an existing
literal color at `style.css:2382`, and existing website radii reported from parsed inline
content. None points to the new workflow action rule or edited marketing paragraph; no
design token or unrelated site styling was changed. Actual browser-chrome zoom remains
unverified, and these local preview captures do not establish public website availability.
