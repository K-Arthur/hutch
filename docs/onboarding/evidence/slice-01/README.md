# Slice 01 evidence - dedicated onboarding request step

Date: 2026-10-29. Slice: 01 (dedicated `/onboarding` route with server-owned
resume). Gate: CP1. Evidence owner/reviewer: Lead implementation reviewer.

## What was captured

63 PNGs from the live app at `http://127.0.0.1:<port>/onboarding`, captured by
`tests/e2e/test_onboarding_page.py` (real uvicorn server, real routes, real
CSRF-protected form posts; seeded kv records only for the states a user cannot
produce by hand: stale requirements, expired TTL, newer contract version,
damaged JSON). `capture-results.json` holds the machine observations for every
row (state token, mode, h1 count, visible primary actions, horizontal overflow,
status/alert text, body background). `validation.json` holds the opened-image
verdicts.

Coverage (63 rows, one row per capture):

| Dimension | Values |
|---|---|
| States | empty, saved, resumed, non-latin-long-request, validation-error, saving, stale, expired, damaged, newer-version, conflict, forbidden, keyboard-focus, text-zoom-200 |
| Viewports | 320x740, 375x812, 768x1024, 1440x1000 |
| Per-state widths | empty 4; saved 4; resumed 4; non-latin-long-request 4; validation-error 4 + 4 forced-colours; stale 4; expired 4; damaged 4; newer-version 4; conflict 4; keyboard-focus 4; text-zoom-200 4; forbidden 3; saving 1 |
| Themes | fixed dark (product decision, no light theme); OS light preference captured for empty at 320/375/768/1440 and verified pixel-identical to dark (same SHA-256 per pair) |
| Accessibility variants | forced colours for validation-error at all four widths; reduced motion for saved at all four widths; keyboard focus on the request field at all four widths; 200 percent root text scale at all four widths |

## Real-world scenario coverage

| Required exercise | Slice-01 coverage |
|---|---|
| Interrupted upload + resume | OUT: no upload or file modality exists in onboarding (matrix EC-12/EC-13 are OUT). The analogue is exercised instead: a save interrupted by reload resumes at the last server-confirmed revision, and a store/app restart resumes the same request (`test_request_survives_a_full_store_and_app_reopen`). |
| Expired session mid-step | Partial: the local owner route has no passkey session; a missing/invalid CSRF token renders the explicit `auth.csrf_rejected` state with the typed text preserved and a reload action. `auth.session_expired` belongs to slice 08. |
| Duplicate submission | Exercised: identical resubmit is a replay with no second write (`test_duplicate_submit_is_replayed_and_creates_no_second_write`), and a stale revision with different text renders the conflict page keeping the newer value (`test_stale_revision_renders_explicit_conflict_and_never_overwrites`, and the two-tab live capture). |
| Provider timeout + retry | OUT: this slice makes no provider or network call (contract section 1); timeout/retry states are owned by slice 03/04 and are not faked here. |
| Locale with non-Latin characters | Exercised: CJK, accented Latin, Arabic RTL, combining marks and a 110+ character request round-trip through save, reload, resume, and the saved display without loss (`LONG_NON_LATIN` in the capture test; unicode tests in `tests/test_onboarding_state.py`). |
| Low-quality capture | OUT: no camera, document, or image capture exists in onboarding (matrix EC-11/EC-14 are OUT). |
| Keyboard-only completion | Partial at this slice: the request form is keyboard-completable (skip link, textarea, submit, back link), the focus ring is visible and captured at all four widths, and the page works as a plain POST with JavaScript disabled. The full multi-step keyboard journey is the slice-09 gate. |
| Screen-reader announcement on step change | Partial: the resumed step un-hides and fills one polite status region after load so it is announced once; the save result is one flash `role=status`; the error summary is `role=alert` with `tabindex="-1"` and is focused by `onboarding.js` (the e2e lane asserts `document.activeElement`). No real screen reader was run - recorded as a limitation. |

## Known platform boundary discovered during this slice

`SecurityMiddleware` sets `Referrer-Policy: no-referrer`. In current Chromium and
Firefox a plain form POST from a page served with that policy is sent with
`Origin: null`, which the existing same-origin guard correctly refuses. This is a
pre-existing, already-recorded boundary (see
`tests/e2e/test_route_state_boundaries.py`, row `form-post-origin-null`), not
caused by slice 01. The onboarding page opts back into a same-origin referrer with
`<meta name="referrer" content="same-origin">` (the referrer is only ever sent to
this same-origin local server), so its plain form posts work in the browser. The
broader fix for other server-rendered forms belongs to the security surface owner
and is recorded as a discovered edge case in the matrix and the continuation
prompt; it is not silently deferred.

## Review method and verdicts

Method: the reviewer opened every PNG in this directory (all 63) and recorded a
binary verdict per row. Automated observations (overflow <= 0, exactly one h1,
exactly one visible primary action, no external requests, no page errors, resume
status text once, error summary focused) are in `capture-results.json` and are not
a substitute for the opened-image verdicts.

Verdict summary: 63 APPROVED, 0 NEEDS WORK. Noted, non-blocking observations:

- In forced-colours mode the primary button loses its accent fill by design (system colours); hierarchy is still positional and the focus/error boundaries remain visible.
- The saved success flash is rendered above `<main>` by the shared base template; it is a `role=status` announcement, not a content landmark. Carried to slice 09 for the full announcement audit.
- At 320 px and 375 px the primary and secondary actions stack full-width; deliberate for touch targets.
- At 200 percent text scale the saved-request card grows without clamping (the contract shows the full stored request); the primary action stays in normal flow, so no fixed footer can cover it.
- Damaged/newer-version states put the safe exit (dashboard) first and the destructive "Start over" second; deliberate after review.
- The evidence was captured against the working tree, which includes another session's uncommitted brand/form styles; the committed slice renders the same states with the committed shared styles. This is the recorded CP0 dirty-tree condition.

## Reproduce

```bash
# fast lane
.venv/bin/python -m pytest -q --no-header --tb=line tests/test_onboarding_state.py tests/test_onboarding_page.py
# -> 56 passed

# live visual capture (writes this directory)
.venv/bin/python -m pytest -q --no-header --tb=line tests/e2e/test_onboarding_page.py
# -> 1 passed; 63 PNGs + capture-results.json

python3 scripts/audit_context_hygiene.py   # only pre-existing/other-session violations; none onboarding
python3 scripts/audit_emoji.py             # clean
```

## Limitations (recorded, not inferred)

- Chromium 153.0.8010.12 headless on Linux only. No Firefox/WebKit captures, no real phone, no real screen reader, no real browser zoom (200 percent text scale is emulated with the root font size), and no OS forced-colours setting (Playwright emulation).
- Light theme is a product NO-OP: there is no light theme to capture; the OS light-preference rows prove the fixed dark theme does not invert (identical SHA-256 to the dark row).
- Seeded states are deterministic fixtures written through the real kv store, then rendered by the real route. They are not static HTML fixtures.
- The date/time in the saved/resumed captures is the real local render time (America/Vancouver); no fixed clock is used, and no assertion depends on the wall-clock value.
- The "non-latin-long-request" rows reuse the saved-state markup with the hostile Unicode request; the distinct row exists so the required state is evidenced rather than inferred.