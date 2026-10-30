# 08 - Marketing site adaptation

## Scope

- website/responsive.css (new; created in task 01)
- website/index.html (target sizes, no-JS fallback markup if needed)
- website/styles.css (hand-written, currently clean of parked changes)
- website/site.js only if the no-JS fallback cannot be pure CSS

## Failure mode

- No viewport-fit=cover today (fixed by task 01; this task consumes it).
- No pointer:coarse block exists anywhere in website/styles.css, so the header
  CTA and drawer Close are btn-sm (32px) and the footer/header controls never
  grow on touch (website/index.html:255, 269; audit F).
- With JS disabled, the inline noscript rule forces .navbar-center visible while
  the CSS hides the navbar links below 1024 and body overflow-x:hidden clips the
  result: the menu overflows and part of it is unreachable on a no-JS phone or
  tablet (website/index.html:228; website/styles.css:276, 31).
- The hero figure min-heights of 460/450/340px (website/styles.css:232, 249, 266)
  nearly fill an 844x390 phone-landscape viewport under the 68px sticky bar, so
  the first screen is almost entirely artwork.
- Baseline harness measures marketing footer links at 20px tall (below WCAG
  2.5.8) and 21 sub-44px targets on a phone.

## Change

Add a marketing responsive sheet with: the coarse-pointer 44px floor for header
and footer controls (including the drawer close), a 24px minimum for footer
links on fine pointers, and a no-JS layout that lets the nav wrap or collapse
into a visible, tappable list instead of clipping. Reduce hero figure
min-heights for short landscape viewports (max-height-bounded) so the value
proposition and primary CTA stay in the first screen. Remove the dead .receipts
min-width rule only if it is confirmed unused. Keep the existing drawer dialog
behaviour, reduced-motion handling and pointer:fine gating unchanged.

## Validation

- Harness: site-home at 375, 390, 768, 1024, 1366 and 844x390 with coarse
  pointer; zero overflow, zero under-24 targets, under-44 count recorded.
- A no-JS pass (java_script_enabled=False) at 375 and 768 proving the menu and
  its links are reachable and not clipped.
- Screenshots: site-home-phone-375.png, site-home-tablet-portrait-768.png,
  site-home-ipad-13in-1366.png, site-home-phone-landscape-844.png, plus the
  no-JS state capture.
- Desktop parity at 1440/1536 against baseline-2a89909a.

## Rollback

Revert the commit; the marketing site returns to its current behaviour. No data
changes.

## Parked-tree integration

website/index.html is shared dirty: stage HEAD plus only the task hunks.
website/styles.css is currently clean and stages normally. website/responsive.css
is new.

## Size check

One new sheet, one HTML file with small edits, one hand-written sheet with small
edits plus a no-JS harness pass: one session.
