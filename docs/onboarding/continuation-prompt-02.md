# Continuation prompt - onboarding slice 02

You are implementing onboarding slice 02: first-run handoff and the in-context
AI-service chooser. Work in /home/kevina/CodingProjects/hutch on main. Slice 01
is implemented, accepted at CP1, and its evidence is in
`docs/onboarding/evidence/slice-01/`; do not redo it.

## Read first (in this order)

1. `docs/onboarding/slices/slice-02.md` - the implementation brief, including
   section 0 "What slice 01 actually delivered" and the seven binding findings.
2. `docs/onboarding/task-plan.md` - sections 2.4, 2.5, 2.6, 4 row 02, CP1 and CP2.
3. `docs/onboarding/setup-record.md` - the slice-01 domain/persistence/HTTP/state
   contract you must extend (route_kind/route_chosen_at, chooser_view, choose_route,
   chooser_ready, save_route, chooser states).
4. `docs/onboarding/edge-case-matrix.md` - sections 3, 4, 5 rows EC-01, EC-02,
   EC-04, EC-06 (note only), EC-07, EC-08, EC-10, EC-15 to EC-20, and section 14
   (slice-01 implementation findings).
5. `docs/onboarding/slices/slice-01.md` section 15 - acceptance record, deviations,
   rollback precedent.
6. `docs/design-system.md` "Setup recovery boundaries" - the page/state rules.
+ the actual code: `src/hutch/onboarding.py`, `src/hutch/onboarding_store.py`,
`src/hutch/server/onboarding_api.py`, `src/hutch/server/templates/onboarding.html` +
partials, `src/hutch/server/static/onboarding.css|js`,
`tests/test_onboarding_state.py`, `tests/test_onboarding_page.py`,
`tests/e2e/test_onboarding_page.py`.

## Step 0 - close the CP1 -> CP2 planning precondition (required)

CP1 requires the slice-03 (readiness truth) and slice-04 (hosted-key connection)
briefs to exist and be approved before CP2 can pass. Write
`docs/onboarding/slices/slice-03.md` and `docs/onboarding/slices/slice-04.md` in the
same format as slice-01/slice-02 (user outcome; per-step files/functions with exact
`@path:lines` anchors; boundary; in-scope edge cases from the matrix; front-end
states; form/API contract; server-side authorization checklist; docs; tests;
visual evidence; binary acceptance; rollback plan; risks). Use task-plan sections
2.2 B4/B5, 2.4, 4 rows 03/04, and the matrix rows EC-03/EC-05/EC-06/EC-09/EC-20 as
the source. Do not implement them in this run.

## Scope to implement (do not exceed)

Follow slice-02.md sections 2-6 exactly:

- 02a chooser contract: extend `@src/hutch/onboarding.py` with route fields,
  `ROUTE_KINDS`/labels/descriptions, `chooser_view`, `choose_route`, `chooser_ready`;
  extend `@tests/test_onboarding_state.py` or add a split test file if it would
  exceed 400 lines.
- 02b chooser page: add `GET /onboarding/ai-service` and
  `POST /onboarding/ai-service/choose` to
  `@src/hutch/server/onboarding_api.py:1-236` (reuse the existing render/flash/CSRF
  helpers and the two-line installer; add no `app.py` lines), extend
  `@src/hutch/onboarding_store.py:1-74` with `save_route` under the same lock, add
  `templates/onboarding_ai_service.html` (extends base with `chrome=False`,
  `{% block head %}`; include `<meta name="referrer" content="same-origin">`),
  chooser CSS in a NEW `@src/hutch/server/static/onboarding-chooser.css` if
  `onboarding.css` would pass 400 lines (it is at 396), chooser JS in
  `@src/hutch/server/static/onboarding.js` (<=120) or a split file, and
  `@tests/test_onboarding_chooser.py` (<=400).
- 02c handoff/draft bridge: targeted in-place edit in
  `@src/hutch/server/static/app.js` around `renderChatStudio`/its submit handler
  (planning anchors 3257-3408, 3356-3386, 3314-3316, 3371-3375; re-read current
  lines because another session keeps editing the file): the no-route action must
  save the tab draft and `window.location.assign("/onboarding")`, never go to the
  Apps & AI catalog; keep the already-has-a-route branch. Add the read-only
  sessionStorage draft prefill in the onboarding JS and replace the saved-state
  interim CTA in `templates/onboarding.html` with `/onboarding/ai-service`. Update
  the pinned first-run e2e assertions deliberately (do not delete coverage;
  `tests/e2e/test_design_system.py` is at its frozen cap, so edits must be
  line-neutral or coverage moves to a new file). Add
  `tests/e2e/test_onboarding_chooser.py` (<=400).
- 02d back/forward, two-tab conflict, visual evidence.

Do NOT implement provider probes, key entry, local-service probing, external-login
waiting, assistant create, first request, pairing, or marketing changes - those are
slices 03-11.

## In-scope edge cases from the matrix (all must be explicit, never generic)

EC-01 partial save/resume; EC-02 CSRF/session rejection (403 state, request kept);
EC-04 duplicate submit -> replay, different choice is a deliberate change; EC-07
stale resume (unknown/invalid stored route or requirements mismatch -> explicit
stale state offering re-choose, request preserved); EC-08 optional apps/devices
stated as later; EC-10 non-Latin request text unchanged and wrapping; EC-15/16/17
keyboard + one polite announcement (full gate is slice 09); EC-18/19 no motion,
fixed dark + forced colours; EC-20 default/selected/saving/invalid/conflict/stale/
no-request/forbidden states; EC-06 is not representable server-side (slice 03/09
own `net.offline`/`server.unreachable`) - record that, do not fake it.

## Non-negotiable implementation rules

- Owner-only server-side authorization on every route (paired phones must get a
  `None` capability; CE test asserts it); every POST CSRF-gated; `route_kind` is a
  server-side allowlist; no user-controlled redirect target.
- No provider/localhost network call from the browser or the page routes; no
  secrets, no account fields; no marketing-site change.
- No god functions; domain decisions in `onboarding.py`, persistence in
  `onboarding_store.py`, rendering/orchestration in `onboarding_api.py`.
- New source files <=400 lines; `onboarding.py` <=250, `onboarding_store.py` <=80;
  do not grow `models.py`, `pages.py`, `store.py`, `security.py`, `connections.py`,
  `app.py` (no more lines) or the pinned e2e file.
- The working tree still has another session's uncommitted brand work in
  `app.js`, `app.py`, `base.html`, templates and generated CSS. Never revert,
  clean or reformat it; commit only your new files and targeted hunks (slice 01
  staged the two-line `app.py` change and base-template blocks at index level).
- Commit progressively in small atomic commits; each message names the behaviour
  changed and the edge case covered.

## Test commands

```bash
.venv/bin/python -m pytest -q --no-header --tb=line tests/test_onboarding_state.py tests/test_onboarding_chooser.py tests/test_onboarding_page.py
.venv/bin/python -m pytest -q --no-header --tb=line tests/e2e/test_onboarding_chooser.py tests/e2e/test_design_system.py -k "first_run"
python3 scripts/audit_context_hygiene.py   # compare against the recorded CP0 baseline; add no violation
python3 scripts/audit_emoji.py
```
(`uv run --frozen --no-sync` is fine too, but the shared uv cache is occasionally
read-only; `.venv/bin/python -m pytest` is the reliable fallback.)

## Visual validation required (real implementation, not static fixtures)

Capture at 320x740, 375x812, 768x1024, 1440x1000 to
`docs/onboarding/evidence/slice-02/` for: chooser default (three routes, one
recommended with its honest qualifier, apps/devices deferred, request summary),
chosen/resumed state, invalid selection, stale/no-request redirect, keyboard focus
across cards, 200 percent text scale, forced colours, reduced motion; plus one SPA
handoff before/after at 375x812. Fixed dark theme only (light is a NO-OP; capture
OS light preference and assert the page stays dark). Write `capture-results.json`
and a human-opened-image `validation.json` with `state`, `viewport`, `artifact`,
`verdict`, `finding`, `source_commit`, `reviewer`. Use the same Playwright/uvicorn
fixture and evidence pattern as `tests/e2e/test_onboarding_page.py`. Missing
evidence = FAIL; generated is not reviewed.

## Known limitations to carry forward

- Chromium/Linux headless only; no Firefox/WebKit, real phone, real screen reader,
  or real browser zoom. Record that in the evidence README.
- The broader `Origin: null` plain-form-POST boundary (Referrer-Policy
  no-referrer) still affects other server-rendered forms; slice 02 mitigates only
  its own page with the same-origin `meta referrer`. The global fix belongs to the
  security surface owner; keep it tracked.
- Slice 01's success flash renders above `<main>` (role=status); the full
  announcement/landmark audit is slice 09.

## Slice exit (must all be done before stopping)

1. Run the fast and browser lanes above; record exact commands and results.
2. Capture and open the full visual matrix; record APPROVED/NEEDS WORK verdicts.
3. Update `docs/onboarding/task-plan.md` with CP2 status and any discovered edge
   cases added to `docs/onboarding/edge-case-matrix.md`; update
   `docs/onboarding/setup-record.md`, `docs/design-system.md`, the changelog and
   any user-facing help text in the same commit range.
4. Append the acceptance record to `docs/onboarding/slices/slice-02.md`.
5. Write `docs/onboarding/slices/slice-03.md` only if it is not already approved
   and write `docs/onboarding/continuation-prompt-03.md` for the next agent
   (slice 03: readiness truth), containing the slice number, read-first paths,
   in-scope edge cases, visual evidence required, and the continuation rule.
6. Do not implement slice 03 in this run.