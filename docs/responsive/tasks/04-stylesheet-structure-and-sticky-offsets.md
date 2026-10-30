# 04 - Stylesheet structure and sticky offsets

## Scope

- src/hutch/server/static/style.css (unclosed max-width:720px media block starting
  near line 2713)
- src/hutch/server/static/hutch.css (sticky run header top:54px line 114,
  scroll-padding-top line 80, wrapped topbar line 304)
- scripts/responsive/checks.py or scripts/validate_responsive.py (static CSS
  structure check)

## Failure mode

The @media (max-width:720px) block opened at style.css:2713 is never closed: the
file has one more opening than closing brace (1773/1772) and the preflight,
context meter, cost-provenance, compaction-list and budget-meter rules
(2716-2729) are silently scoped to phones instead of applying at every width.
This is a pre-existing HEAD defect, not parked work: HEAD shows the same
imbalance (1801/1800). Separately, the server run header is pinned at top:54px
while the topbar grows to auto height when it wraps below 720px
(hutch.css:302-317), so the run title/status slide under the taller bar;
scroll-padding-top:4.5rem assumes the same fixed 72px bar (hutch.css:80).

## Change

Close the media block at the intended boundary so the desktop rules become
global again and the 480px override follows as intended. Add a static
brace/nesting check for every hand-written CSS source to the validation script
so a missing brace cannot silently regress. For the sticky header, derive the
sticky offset and scroll padding from one custom property that tracks the real
topbar height (default 54px, updated when the topbar wraps) instead of two
hardcoded values. Desktop appearance stays the same except for the rules that
were accidentally suppressed.

## Validation

- Static: brace balance and media nesting check passes for every hand-written
  CSS source; the check is committed and runnable.
- Harness: full matrix unchanged for overflow/errors; server pages at
  1440/1536 compared against baseline-2a89909a.
- Screenshots: pages-models at 1440 and 375, plus a server run-detail page scrolled
  at 375 and 768 if the seeded workspace exposes one; otherwise assert computed
  styles of the affected selectors at 1440 and 375 in a scripted check.
- Page screenshots: pages-models-phone-390.png, pages-models-desktop-1440.png.

## Rollback

Revert the commit; the media block returns to its previous (buggy) scope and the
sticky offset returns to the fixed value. No state changes.

## Parked-tree integration

style.css and hutch.css are shared dirty files; because the defect exists in HEAD
too, build the committed blob from HEAD plus this single fix. The validation
script change is code in a new module.

## Size check

Two CSS files and one added static check: one session.
