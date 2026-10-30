# Slice 02 evidence - first-run handoff and AI-service chooser

Date: 2026-10-29. Slice: 02 (empty-chat handoff to `/onboarding`, in-context
AI-service chooser). Gate: CP2. Evidence owner: Lead implementation. Independent
visual reviewer: fresh-context verifier (opened every image twice: the first pass
found a layout defect, the fix was recaptured and re-reviewed).

## What was captured

56 PNGs from the live app at `http://127.0.0.1:<port>/onboarding/ai-service` and
`/onboarding`, captured by `tests/e2e/test_onboarding_chooser.py` (real uvicorn
server, real routes, real CSRF-protected form posts; deterministic kv seeds only
for states a user cannot produce by hand: requirements-drift stale, existing
route, two-tab stale revision conflict, and the no-request redirect). The SPA
handoff is driven end to end: empty chat -> type request -> click the one primary
action -> `/onboarding` with the request restored -> save -> the saved request's
one primary action -> chooser. `capture-results.json` holds the machine
observations for every row (state token, h1 count, visible primary actions,
route-card count, horizontal overflow, status/alert text, body background).
`validation.json` holds the opened-image verdicts.

Coverage (56 rows, one row per capture):

| Dimension | Values |
|---|---|
| States | chooser-default (incl. 4 OS light-preference), chooser-recommended, chooser-chosen (incl. 4 reduced-motion), chosen-resumed, change, invalid (incl. forced colours), stale, conflict, forbidden, no-request, keyboard-focus, 200 percent text scale, forced colours, handoff-before/after |
| Viewports | 320x740, 375x812, 768x1024, 1440x1000 |
| Themes | fixed dark (product decision, no light theme); OS light preference captured at all four widths and verified pixel-identical per pair |
| Accessibility variants | forced colours for choose/invalid; reduced motion for chosen at all four widths; keyboard focus on a route radio at all four widths; 200 percent root text scale at all four widths; heading focused on arrival |
| Layout assertions | 3-up at 1440, 2+1 at 768, stacked at 375, asserted by card top edges (not screenshot-only) |

## Real-world scenario coverage

| Required exercise | Slice-02 coverage |
|---|---|
| Interrupted upload + resume | OUT: onboarding has no upload/file modality (matrix EC-11 to EC-14 are OUT). The analogue is exercised instead: the empty-chat request survives the handoff into `/onboarding` through the tab draft (handoff-before/after rows), a saved choice survives reload and Back/Forward, and an in-flight duplicate submit replays instead of writing twice. |
| Expired session mid-step | Partial: this local owner route has no passkey session in scope; a missing/invalid CSRF token renders the explicit `auth.csrf_rejected` state with the submitted route preserved and nothing written (HTTP test + live forbidden capture). `auth.session_expired` belongs to slice 08. |
| Duplicate submission | Exercised: same-route resubmit from a duplicate submit's stale revision is a replay with no second write (`test_same_choice_resubmit_replays_without_a_second_write`; domain replay test); a different route is a deliberate change, and a different route from a stale revision is an explicit 409 conflict (HTTP test + live two-tab conflict capture). |
| Provider timeout + retry | OUT: this slice makes no provider, localhost or browser network call; the live lane asserts zero external requests. Timeout/retry/readiness states are owned by slice 03 and are not faked here. |
| Locale with non-Latin characters | Exercised: the fixture carries CJK, accented Latin and Arabic RTL (`Juno 助手 - Zoë Ångström - محمد - ...`); it is shown intact in every request-bearing state (default, chosen, change, invalid, stale, conflict, forbidden, handoff, 200 percent, forced colours) and round-trips through the HTTP tests. |
| Low-quality capture | OUT: no camera, document or image capture exists in onboarding (matrix EC-11/EC-14). |
| Keyboard-only completion | Partial at this slice: route cards are real radio inputs, they are reachable and selectable by keyboard, the focus ring is visible and captured at all four widths, and the form works as a plain POST with JavaScript disabled. Full multi-step keyboard completion is the slice-09 gate. |
| Screen-reader announcement on step change | Partial: on arrival the chooser focuses its `h1` (`tabindex="-1"`, `data-focus-heading`) unless an error summary wins focus, so the step change is announced once; the save/choice result is one flash `role="status"` in the shared base. No real screen reader was run - recorded as a limitation; the full announcement/landmark audit is slice 09. |

## Known platform boundary carried from slice 01

The global `Referrer-Policy: no-referrer` makes current Chromium/Firefox send
plain form POSTs with `Origin: null`, which the existing same-origin guard
correctly refuses (pre-existing, recorded in
`tests/e2e/test_route_state_boundaries.py`). Slice 02's chooser page opts back
into `<meta name="referrer" content="same-origin">` exactly like the request
step; the guard was not weakened. The broader fix belongs to the security surface
owner.

## Review method and verdicts

Method: the independent reviewer opened every PNG (56), recorded a binary verdict
per row, and re-opened the full set after the layout fix. The first pass found one
non-blocking layout defect: the route fieldset is a grid, so the required/help
paragraph took the first grid cell, giving 1+2 at 768 and a lopsided 2+1 at 1440.
The fix spans the help across the group; the live lane now asserts card top edges.
The second pass confirmed 3-up at 1440 and 2+1 at 768 with no clipping or overflow.

Verdict summary: 56 APPROVED, 0 NEEDS WORK. Non-blocking observations kept in the
verdicts:

- The arrival focus ring is visible around the step heading (deliberate: the
  heading receives programmatic focus for the one announcement).
- Reduced-motion chosen rows are byte-identical to the dark chosen rows: this page
  adds no motion, so there is nothing to suppress in stills.
- The OS light-preference rows are byte-identical to their dark counterparts at
  all four widths: the app stays fixed dark.
- The recommendation is static and labelled as such; it is not a detected or
  verified readiness state (slice 03 owns that).
- The chosen state's "Continue to Apps & AI" is an explicit, visibly marked
  interim bridge until slices 04-06 add the real connection steps.

## Reproduce

```bash
# fast lane -> 105 passed
.venv/bin/python -m pytest -q --no-header --tb=line tests/test_onboarding_chooser_state.py tests/test_onboarding_chooser.py tests/test_onboarding_page.py tests/test_onboarding_state.py

# live visual capture (writes this directory) -> 1 passed, 56 PNGs
.venv/bin/python -m pytest -q --no-header --tb=short tests/e2e/test_onboarding_chooser.py

# pinned first-run behavior updated deliberately -> 3 passed
.venv/bin/python -m pytest -q --no-header --tb=short tests/e2e/test_design_system.py -k first_run

python3 scripts/audit_context_hygiene.py   # six pre-existing baseline entries; none onboarding
python3 scripts/audit_emoji.py             # clean
```

## Limitations (recorded, not inferred)

- Chromium headless on Linux only. No Firefox/WebKit captures, no real phone, no
  real screen reader, no real browser zoom (200 percent text scale is emulated
  with the root font size), and no OS forced-colours setting (Playwright
  emulation).
- Light theme is a product NO-OP: there is no light theme to capture; the OS
  light-preference rows prove the fixed dark theme does not invert (identical
  SHA-256 to the dark row at each width).
- Seeded states are deterministic fixtures written through the real kv store,
  then rendered and submitted through the real routes. They are not static HTML
  fixtures.
- The date/time in request-step captures is the real local render time
  (America/Vancouver); no assertion depends on the wall-clock value.
- The evidence was captured against the working tree, which still carries another
  session's uncommitted brand work; the committed slice renders the same states
  with the committed shared styles. This is the recorded CP0 dirty-tree condition.
