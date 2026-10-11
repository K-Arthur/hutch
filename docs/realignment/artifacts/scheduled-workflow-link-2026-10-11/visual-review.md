# Routine-to-workflow visual review

Date: 2026-10-11. Surface: existing assistant routine editor and activated-workflow
selector. This review covers the real local API journey and opened Chromium captures,
not screen-reader or physical-device certification.

## Captures and checks

The owner selected the saved method with keyboard navigation, reviewed its exact
revision and checked-input editor, then saved a disabled routine. The browser test
captured 1440×1000, 768×980, 360×844 and 320×800 CSS-pixel views. At every width,
the document and body matched the viewport, the Save task target was at least 44px
high, the workflow title and immutable revision were visible, and there were no
page errors or provider calls. The trace, measurements and source hashes are in
[validation.json](validation.json).

## Opened-view observations

- At 1440px, 768px and 360px, the routine editor remains inside its existing
  assistant-settings panel. The selector label, selected long workflow title,
  pinned revision, checked-input hint and JSON editor have a clear reading order.
- At 320px, form controls reflow inside the viewport. The long title wraps, the
  next-run timestamp wraps onto two lines, and the Save task and Remove task
  actions stack without clipping or horizontal overflow.
- The 44px Save task action remains reachable when the editor is scrolled into
  view. Linking the saved method and enabling future schedule occurrences are
  visibly separate controls. The page copy says inputs are checked against the
  pinned plan before saving and again at execution.

The focused views are retained as routine-link-*-actions.png, with editor and
pinned-revision views beside them. No browser console or page errors were observed.
