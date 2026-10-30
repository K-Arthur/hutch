# 02 - Server navigation model

## Scope

- src/hutch/server/static/hutch.css (nav rules at 328-343; wrapped topbar 302-317)
- src/hutch/server/static/hutch.js (1400px matchMedia and setOpen block 184-219)
- src/hutch/server/templates/base.html (only if a js-class hook is needed)

## Failure mode

Server pages collapse nine top-level links into a full-screen overlay at
max-width:1400px (hutch.css:331-343) driven by a matching JS breakpoint
(hutch.js:188). At 1366x1024 (13-inch iPad landscape), 1180x820 (13-inch laptop)
and 1024x768 the same device gets a different navigation model than the SPA,
which keeps its sidebar until 900px. The overlay is hidden with
transform/opacity/pointer-events and only hutch.js can open it, while server
pages are explicitly built to work without JavaScript (pages.py:1-6): with JS
off or a failed script, navigation is unreachable below 1400px (audit A2).

## Change

Make the nav breakpoint match a real content constraint instead of a
laptop-width guess, and remove the JS dependency. Keep the default CSS state
visible; scope the compact-overlay rules to a js-enabled root class that hutch.js
adds when it boots, so a JS-off reader gets the horizontal wrapped nav at every
width. Pick the compact breakpoint from measurement: the overlay should engage
only where the wrapped topbar genuinely cannot hold nine links; 1180 and 1366
must keep the horizontal nav. Raise .nav-toggle to the 44px coarse-pointer floor
in the same commit. Keep the existing focus handling, Escape-to-close and
inertness; only the breakpoint, the CSS visibility default and the JS gating
change.

## Validation

- Harness: pages-models, pages-usage, pages-bot-detail, pages-login at
  1366x1024, 1180x820, 1024x768, 768x1024, 375x812, 844x390; no overflow.
- Assert the model split explicitly: at 1180 and 1366 the horizontal nav is
  visible and the toggle is not; at 1024 and below the toggle opens the overlay,
  Escape closes it, and focus returns to the toggle.
- Add a no-JS pass (Playwright context with java_script_enabled=False) at 1180
  and 375 proving every nav destination is reachable without hutch.js.
- Screenshots: state-pages-nav-open-375.png,
  pages-models-ipad-13in-1366.png, pages-models-laptop-1180.png,
  pages-models-tablet-landscape-1024.png.
- Desktop parity: pages-models and pages-usage at 1440/1536 unchanged against
  baseline-2a89909a.

## Rollback

Revert the commit; the 1400px overlay behaviour and JS dependency return
together. No state changes.

## Parked-tree integration

hutch.css and hutch.js are shared dirty files: stage HEAD plus only this task's
hunks. base.html, if touched, gets a one-line change only.

## Size check

Two CSS/JS files with a scoped rule change plus one harness no-JS pass: one
session.
## Outcome

- Superseded 2026-10-30: the topbar navigation this task tuned was removed
  entirely. Every full server page now renders the shared app sidebar
  (`templates/macros/sidebar.html`, model in `src/hutch/server/nav.py`,
  `static/hutch-nav.css` shared with the SPA, `static/hutch-shell.css` and
  `-shell.js` for layout and the drawer). The breakpoint is now the SPA's 900px
  drawer, the header is a fixed 56px `.app-top`, and the no-JS fallback keeps
  every destination visible inline. Historical measurements below describe the
  removed topbar and remain for provenance.
- Status: done, commit 2cf2c5fe, then superseded.
- Evidence: docs/responsive/screenshots/2cf2c5fe (JS on: 130 measurements,
  0 failures; nav overlay at <=1024, single-row 9-link nav at 1180 and 1366,
  toggle hidden there) and docs/responsive/screenshots/2cf2c5fe-nojs (25
  measurements, 0 failures; 9/9 links visible without JavaScript at 375, 768,
  1024, 1180 and 1366).
- Tradeoff recorded: between 1025 and 1439px the decorative leading nav icons
  are hidden so all nine destinations fit single-row without horizontal
  scrolling; labels, active state and the approval badge remain. At >=1440px
  the icons return and the layout matches the previous desktop exactly.
- Rollback: revert 2cf2c5fe (source) and its evidence commit. No generated CSS.
