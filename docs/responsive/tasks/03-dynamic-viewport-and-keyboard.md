# 03 - Dynamic viewport and keyboard

## Scope

- new: src/hutch/server/static/responsive.js (visualViewport publisher)
- src/hutch/server/static/responsive.css (view-height rules from task 01)
- src/hutch/server/templates/base.html and src/hutch/server/static/index.html
  (one script link each)
- src/hutch/server/static/hutch.css (body min-height at line 57)
- src/hutch/server/static/style.css (shell 233-240, chat scroller 733, fixed
  units) only if the override cannot live in the new sheet

## Failure mode

Server pages use body min-height:100vh (hutch.css:57), taller than the visible
viewport while mobile browser chrome is expanded, so the footer/background runs
under the toolbars. The SPA locks height:100dvh (style.css:233-240) but its
internal chat scroller (style.css:733) and normal-flow composer
(hutch-composer.css:95-105) receive no keyboard inset; only popup placement
handles visualViewport (controls.js:185-188), so the composer can sit under the
iOS keyboard and the fixed frame offers no page-scroll fallback. At 844x390
landscape the frame leaves roughly 334px of content height, so a keyboard hides
the active field (audit B, E1).

## Change

Standardise view units: 100svh as minimum page height, 100dvh for the app frame,
keeping a plain 100vh fallback for old engines. Publish visual viewport height
and keyboard inset from a small responsive.js (resize/scroll on visualViewport,
writing custom properties such as --vh and --keyboard-inset on the root; no-op
when the API is absent). Consume them in the responsive sheet: frame max height,
composer bottom padding and sheet max heights respect the keyboard inset; fixed
bottom chrome uses max(existing padding, safe-area + keyboard). Do not disable
user zoom or set user-scalable=no.

## Validation

- Harness: spa-studio and pages-models at all phone viewports plus
  phone-landscape-844 and tablet widths; add a keyboard scenario that shrinks
  the viewport height by 300px and asserts the composer and focused field remain
  fully inside the visual viewport and the transcript keeps a non-zero scroll
  height.
- Verify 100svh/100dvh parse with the 100vh fallback still present.
- Screenshots: spa-studio-phone-390.png, spa-studio-phone-landscape-844.png,
  state-spa-focus-375.png, pages-models-phone-390.png, plus the keyboard-shrunk
  state capture.
- No overflow and no page error at any matrix pair.

## Rollback

Revert the commit; the script link and properties disappear, restoring
100vh/100dvh behaviour. No data changes.

## Parked-tree integration

hutch.css and style.css are shared dirty files: stage HEAD plus only this task's
hunks, or keep every rule in the new responsive.css. The script file is new.

## Size check

One new JS file, one stylesheet rule set, two one-line template links and one
harness scenario: one session.
## Outcome

- Status: done, commit 28aa02e0.
- Evidence: docs/responsive/screenshots/28aa02e0 (130 measurements, 0 failures;
  state-spa-keyboard-390.png shows the 390x844 shell shrunk to 390x520 with the
  composer fully inside the visual viewport).
- Measured: shell 844 -> 520 px, composer bottom 520 px, --vvh 520.00px,
  --keyboard-inset published; server-page body min-height resolves to 100svh and
  body content still scrolls normally.
- Limitation recorded: Chromium simulates the keyboard by resizing the viewport;
  a real iOS visual-viewport overlay was not available. The publisher uses only
  the documented Visual Viewport API and measures --keyboard-inset for sheets.
- Rollback: revert 28aa02e0 (source) and its evidence commit.
