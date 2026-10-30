# 06 - Safe-area chrome

## Scope

- src/hutch/server/static/responsive.css (safe-area rules from task 01)
- src/hutch/server/static/style.css only if a specificity conflict requires it

## Failure mode

The SPA already opts into edge-to-edge layout (static/index.html:5), but its
fixed chrome ignores the resulting insets on three surfaces: toasts are pinned
24px from the bottom with no env(safe-area-inset-bottom)
(style.css:1402-1404), the workspace drawer is a fixed left/top/bottom panel with
no side insets (style.css:1683-1688), and the needs-you drawer uses a flat 24px
bottom pad smaller than a home indicator (style.css:1855-1862). Top and side
insets are missing on the primary header (style.css:425-433). On notched phones
(portrait and especially landscape) content and taps can sit under the notch or
home indicator. Task 01 adds cover to the other shells, so their chrome needs the
same treatment here.

## Change

In the new responsive sheet, define safe-area custom properties once (from
env(safe-area-inset-*, with 0 fallbacks) and apply them with max() or
calc() at the fixed edges: app header/topbar, workspace drawer (left and right),
needs-you drawer bottom, toast stack bottom/right, server topbar and composer
seat. Keep existing padding values as the floor: max(existing, existing + inset).
Do not add insets to scrolling content that is already inside a padded shell, to
avoid double padding.

## Validation

- Harness: 390x844 portrait, 844x390 landscape, 768x1024, 1366x1024; drawer-open
  state captures at phone portrait (state-spa-sheet-open-375) and, added in this
  task, a phone-landscape drawer capture at 844x390.
- Screenshots: spa-studio-phone-390.png, spa-studio-phone-landscape-844.png,
  state-spa-sheet-open-375.png, pages-models-phone-390.png.
- Confirm the inset rules are present for all three shells and that the viewport
  contract check from task 01 still passes.
- Limitation: Chromium does not emulate a notch, so env() evaluates to 0 in the
  harness; correctness of the rule shape is reviewed and recorded.

## Rollback

Revert the commit; the flat spacing values return. No data changes.

## Parked-tree integration

All rules live in the new responsive.css; style.css is only touched if a
specificity conflict cannot be resolved from the new sheet.

## Size check

One new rule set in one file plus state captures: one session.
## Outcome

- Status: done, commit 8b24b9ba.
- Evidence: docs/responsive/screenshots/8b24b9ba (130 measurements, 0 failures;
  state-needs-you-390.png and state-needs-you-landscape-844.png capture the
  fixed-side drawer in both orientations).
- Applied: toast stack right/bottom insets, SPA workspace drawer all four edges,
  needs-you drawer right/bottom, phone composer seat side insets. env() is 0px in
  the Chromium harness, so the rule shape plus the confirmed unchanged desktop
  rectangles are the evidence; a real notched-device pass is still unavailable.
- Rollback: revert 8b24b9ba (source) and its evidence commit.
