# 05 - Touch-target floor

## Scope

- src/hutch/server/static/responsive.css (new coarse-pointer and base-size rules)
- src/hutch/server/static/style.css and static/studio.css only for a rule that
  cannot be overridden from the new sheet
- website/responsive.css (new marketing coarse-pointer rules)

## Failure mode

WCAG 2.2 AA 2.5.8 requires a 24x24 CSS px target; Hutch's own documented
standard is 44x44 (DESIGN.md:322-323, docs/design-system.md:100, backed by 179
44px declarations), and the baseline harness already measures real gaps:
- 24px AA failures on touch: the dashboard brand lockup is 77x22
  (src/hutch/server/static/index.html:51) and marketing footer links are 20px
  tall (website/index.html footer links), both below the minimum.
- 44px comfort gaps: server nav-toggle 38x38 (hutch.css:328-329), generic SPA
  icon buttons 40px under coarse (style.css:1800), needs-you close on tablets
  (style.css:1877, 1966), approval filters 30px (style.css:1883), runs filter
  pills about 30px (style.css:1298), popup close 40px (controls.css:64), and
  marketing header CTA / drawer close btn-sm at 32px with no coarse block in
  website/styles.css (website/index.html:255, 269).
The busiest tablet interactions therefore miss the project's own floor, which is
also the largest source of rage-tap risk in the research (S14, S15).

## Change

Establish a single target-size floor in the new responsive sheet: every
interactive control is at least 24x24 on any pointer type, and at least 44x44
under pointer:coarse. Prefer min-height/min-width with existing padding and
alignment so visual density is preserved; do not hide or shrink labels to make
room, and do not remove any existing control. Apply the same floor to the
marketing sheet. Where an existing sheet must change to avoid a specificity
conflict, change only that declaration and stage HEAD plus the hunk.

## Validation

- Baseline comparison: docs/responsive/screenshots/baseline-2a89909a/assertions.txt
  records the before counts (24px and 44px warnings). The task commit records
  after counts in the new evidence directory.
- Harness with --fail-on touch24: zero pairs with under-24 targets across the
  coarse-pointer matrix (320/375/390/844 landscape/768/1024/1366).
- Under-44 count must fall sharply and every remaining exception must be listed
  in this task file or the audit non-findings with a reason (for example inline
  prose links, which WCAG excepts).
- Screenshots: spa-studio-phone-390.png, spa-studio-tablet-portrait-768.png,
  spa-studio-ipad-13in-1366.png, pages-models-tablet-landscape-1024.png,
  site-home-phone-375.png, site-home-ipad-13in-1366.png.
- No overflow or page error introduced at any matrix pair.

## Rollback

Revert the commit; the original target sizes return. No data changes.

## Parked-tree integration

Prefer the new responsive.css and website/responsive.css (both new files). Any
shared CSS hunk is staged from HEAD plus that hunk only.

## Size check

One new rule set across two new sheets plus optional single declarations: one
session.
