# 07 - 13-inch and tablet device bands

## Scope

- src/hutch/server/static/responsive.css (device-band rules)
- src/hutch/server/static/style.css only for a declaration that cannot be
  overridden
- deferred follow-up 07b: app/src/input.css rail width plus a ui.css rebuild,
  blocked until the parked brand work is committed

## Failure mode

There is no deliberate tuning for 1024x768, 1180x820 or 1366x1024. The sidebar
has two owners and two widths: 272px in style.css:235 and 304px in
app/src/input.css:39-43 (compiled into ui.css) above 1000px, so the shell jumps
32px at the 1000/1001 boundary with no layout reason. At 1024 the SPA keeps the
desktop rail while hiding the workflow/activity cluster (studio.css:513); at 1180
and 1366 nothing is tuned for the 4:3-ish work area of a 13-inch tablet, and the
13-inch iPad additionally gets touch input while showing a desktop shell. Task 02
aligns server-page navigation; this task makes the SPA shell itself coherent at
those bands.

## Change

Declare the device bands once in the responsive sheet: compact phone (to 430),
large phone/landscape (431-767), tablet portrait (768-1024), compact laptop
(1025-1199), 13-inch/small desktop (1200-1439), desktop (1440+). Use them to:
make the rail a single width from rail-mode upward (choose 304px, the newer
source value, and override the legacy 272px only above the drawer breakpoint so
no drawer-mode layout changes), keep the workflow/status cluster present at 1366
and 1180, compress header density at 1025-1199 instead of dropping information,
and give phone landscape a shallower header so the composer keeps usable height.
Do not fix the rail width by editing app/src/input.css yet: that file and its
generated ui.css are parked, so the source reconciliation is recorded as deferred
task 07b in STATE.md with the exact next action.

## Validation

- Harness: spa-studio, spa-runs, spa-tasks, spa-runtime at tablet-landscape-1024,
  laptop-1180, ipad-13in-1366, desktop-1440, desktop-wide-1536 plus phone
  landscape 844x390; no overflow, no page error.
- Assert computed sidebar width is identical at 1024 and 1180 in rail mode and
  that no layout jump larger than 20px occurs between 1000 and 1001 (scripted
  geometry check in the validation harness).
- Screenshots: spa-studio-tablet-landscape-1024.png,
  spa-studio-laptop-1180.png, spa-studio-ipad-13in-1366.png,
  state-spa-sidebar-open-1180.png, state-spa-sidebar-open-1366.png,
  spa-studio-phone-landscape-844.png.
- Desktop parity at 1440/1536 against baseline-2a89909a.

## Rollback

Revert the commit; the legacy rail width and untuned bands return. No data
changes.

## Parked-tree integration

All rules go in the new responsive.css. 07b is explicitly deferred with a STATE
row, not silently dropped.

## Size check

One new rule set plus one scripted geometry check: one session.
