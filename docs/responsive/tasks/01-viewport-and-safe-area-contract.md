# 01 - Viewport and safe-area contract

## Scope

- src/hutch/server/templates/base.html (viewport meta at line 6; add one
  stylesheet link)
- src/hutch/server/static/index.html (add one stylesheet link last)
- website/index.html (viewport meta at line 5; add one stylesheet link last)
- new: src/hutch/server/static/responsive.css
- new: website/responsive.css
- scripts/responsive/checks.py, scripts/responsive/capture.py (viewport
  contract assertion)

## Failure mode

The SPA declares viewport-fit=cover (static/index.html:5) but the server-page
shell (templates/base.html:6) and the marketing site (website/index.html:5) do
not. Without cover every env(safe-area-inset-*) on those surfaces resolves to 0,
so the server composer's bottom inset (hutch-composer.css:104) and marketing
fixed chrome are inert on notched phones. The same class of failure shipped
silently in the sourced post-mortem: a missing viewport tag made every breakpoint
fire against a 980px layout viewport with no console error. Nothing in the e2e
suite asserts the tag, so a new template can lose it again (research S1).

## Change

Add a responsive foundation sheet loaded last on each of the three shells. It
owns only cross-cutting contracts: safe-area custom properties
(--safe-top/right/bottom/left), base inset padding for fixed chrome, and the
documented breakpoint bands. Create it as a new file so the parked brand work in
existing sheets is never touched. Add viewport-fit=cover to the two shells that
lack it in the same commit as the safe-area padding, so no shell ships
edge-to-edge without insets. Extend the validation harness to record each
surface's viewport meta and fail when the tag is missing or lacks
width=device-width. Additive only: no existing rule is rewritten.

## Validation

- Harness matrix (all three shells): compact-phone-320, phone-375, phone-390,
  phone-landscape-844, tablet-portrait-768, tablet-landscape-1024, laptop-1180,
  ipad-13in-1366, desktop-1440, desktop-wide-1536. All shells report
  width=device-width and viewport-fit=cover.
- Screenshots: spa-studio-phone-375.png, pages-models-phone-375.png,
  site-home-phone-375.png, the 844x390 landscape pairs, and desktop parity at
  1440/1536 against baseline-2a89909a.
- Limitation recorded honestly: Chromium does not emulate a notch, so env()
  stays 0; the scripted tag assertion plus review of the inset rules is the
  evidence.
- No horizontal overflow introduced at any matrix pair.

## Rollback

Revert the task commit; the new sheets and meta attributes disappear together,
restoring the previous document contract. No state or data changes.

## Parked-tree integration

base.html, index.html and website/index.html are shared dirty files: stage HEAD
plus only this task's one-line additions using the hash-object recipe. The two
responsive CSS files are new and stage normally.

## Size check

Two meta edits, two new stylesheets with a first rule set, three one-line links
and one harness check: comfortably one session.
## Outcome

- Status: done, commit 9f74a378.
- Evidence: docs/responsive/screenshots/9f74a378/ (130 measurements, 0 failures;
  review.md records the desktop comparison and the run-to-run dynamic-content
  caveat).
- Harness command: .venv/bin/python scripts/validate_responsive.py --label 9f74a378
- Rollback: revert 9f74a378 (source) and its evidence commit; the new sheets and
  meta attributes disappear together. No generated CSS or state involved.
