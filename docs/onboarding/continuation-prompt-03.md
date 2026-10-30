# Continuation prompt - onboarding slice 03

You are implementing onboarding slice 03: per-route readiness truth and the
readiness panel states. Work in /home/kevina/CodingProjects/hutch on main. Do not
use a worktree unless a human explicitly asks. Slice 02 (first-run handoff and the
AI-service chooser) is implemented at CP2; read its acceptance record and evidence
before starting, do not redo it.

## Step 0 - confirm the gate (required, before coding)

1. Confirm CP2 PASS is recorded in `docs/onboarding/task-plan.md` and
   `docs/onboarding/slices/slice-02.md` section 15, and that
   `docs/onboarding/evidence/slice-02/validation.json` has an APPROVED row for
   every required state. If CP2 is not PASS, stop and report the exact missing row.
2. Confirm `docs/onboarding/slices/slice-03.md` is approved (section 15) and
   resolve the two P1 decisions in its section 14 before writing readiness code:
   (a) the explicit 1-token generation probe must not bypass governed-run usage
   accounting - close the gap or take the fallback (highest state
   `setup.saved_unverified`; `verified` moves to slice 08); (b) no readiness panel
   state may collapse into a bare "error".
3. CP3 -> CP4 planning precondition: write `docs/onboarding/slices/slice-05.md`
   (local-service probe step) and `docs/onboarding/slices/slice-06.md`
   (external-login/OpenCode recovery step) in the same format as slice-01/02/03/04
   (user outcome; per-step files/functions with exact `@path:line` anchors;
   boundary; in-scope edge cases from the matrix; front-end states; form/API
   contract; server-side authorization checklist; docs; tests; visual evidence;
   binary acceptance; rollback plan; risks). Use task-plan sections 2.2 B5, 2.4,
   4 rows 05/06, and matrix rows EC-03, EC-05, EC-06, EC-07, EC-09, EC-16, EC-17,
   EC-20 as the source. Do not implement them in this run.

## Read first (in this order)

1. `docs/onboarding/slices/slice-03.md` - the implementation brief, including
   section 0 (what slices 01/02 actually delivered) and the P1 decisions.
2. `docs/onboarding/task-plan.md` - sections 2.4, 2.5, 2.6, 4 row 03, CP2, CP3 and
   CP3->CP4 preconditions.
3. `docs/onboarding/setup-record.md` - sections 1-8 (request step) and section 9
   (chooser extension: route fields, tokens, pagekit contract, save_route).
4. `docs/onboarding/edge-case-matrix.md` - sections 3, 4, 5 rows EC-03, EC-05,
   EC-06, EC-07, EC-08, EC-10, EC-16, EC-17, EC-18, EC-19, EC-20, section 6 proof
   rows, and section 8 (implementation findings, append-only).
5. `docs/onboarding/slices/slice-02.md` section 15 - acceptance record, deviations,
   rollback precedent.
6. `docs/design-system.md` "Setup recovery boundaries" and "AI-service chooser
   rules".
7. The actual code: `src/hutch/onboarding.py`, `src/hutch/onboarding_choices.py`,
   `src/hutch/onboarding_store.py`, `src/hutch/server/onboarding_pagekit.py`,
   `src/hutch/server/onboarding_api.py`, `src/hutch/server/onboarding_chooser_api.py`,
   `src/hutch/server/templates/onboarding_ai_service.html` + `_onboarding_route_form.html`,
   `src/hutch/server/static/onboarding.js|onboarding-chooser.css`,
   `tests/test_onboarding_chooser*.py`, `tests/e2e/test_onboarding_chooser.py`,
   `tests/e2e/test_onboarding_page.py` (capture/fixture pattern),
   `src/hutch/providers/{connection,base,openai_compat,claude,ollama}.py`,
   `src/hutch/server/app.py` readiness/model-route handlers and the onboarding
   registration seam (~line 7250), `src/hutch/server/templates/base.html`.
   Re-read every current line; do not trust anchors in older briefs.

## Scope to implement (do not exceed)

Follow slice-03.md sections 2-6 exactly:

- 03a pure `src/hutch/route_readiness.py`: `ProbeResult` (state, kind,
  http_status, retry_after, detail, models, checked_at, mode), canonical state
  tokens, `classify` over the 14 `ProviderError.KINDS` + HTTP status, metadata vs
  generation constructors that enforce the invariants in code, retry/TTL helpers.
  New `tests/test_route_readiness.py` (<=400).
- 03b typed server-side probe adapter in `src/hutch/providers/connection.py`
  (grow only; keep legacy `check_connection` for existing surfaces) plus
  deterministic fake-provider fixtures in a NEW test module (copy the
  `tests/fakes.py` pattern; do not grow the frozen helper).
- 03c readiness fragment `templates/_onboarding_readiness.html` + a bounded
  `src/hutch/server/onboarding_readiness_api.py` installed from
  `install_onboarding_routes` (no `app.py` lines), rendered inside the chooser
  page for the selected route. Every state from the brief's section 5 gets its own
  token, reason and one next action (retry/verify/switch). `ConnectionCheck.verified`
  is discarded, never rendered.
- 03d polling/retry: silent poll updates (no announcement on unchanged state, one
  polite announcement on state change), bounded retry with capped Retry-After,
  no auto-provider-call loops. Slice 03 owns the client-shell `net.offline` /
  `server.unreachable` state with retry; slice 09 gates the full journey.
- 03e live evidence + docs.

Do NOT implement hosted-key entry/verification (04), local-service forms (05),
external-login waiting (06), assistant create/first request (07/08), pairing (10),
or marketing changes (11).

## In-scope edge cases from the matrix (all explicit, never generic)

EC-03 timeout/partial/retry; EC-05 permission denied distinct from invalid
credential/credit/rate-limit; EC-06 offline and server-unreachable distinct from
provider states, with retry and kept steps; EC-07 stale readiness revalidation
(never show stale success); EC-08 optional steps deferred; EC-09 time/copy
honesty (server UTC, no currency/price copy); EC-10 non-Latin data unchanged;
EC-16/17 one polite announcement per transition, state changes without focus
theft, keyboard-operable retry/switch; EC-18 no motion-only feedback, progress
visible as text within 1 s; EC-19 fixed dark, forced colours, no light theme;
EC-20 every named state has a reason and one primary action. Do not collapse
`provider.unavailable`, `provider.timed_out`, `provider.unreachable`,
`server.unreachable` and `net.offline` into one state.

## Non-negotiable implementation rules

- Owner-only server-side authorization on every route (paired phones get a `None`
  capability; add a test); every POST CSRF-gated; no user-controlled redirect.
- No provider/localhost network call from the browser; probes run in the Python
  server process; no secret in HTML, logs, URLs or errors; redact and bound
  provider detail strings.
- No god functions: pure decisions/classifier in `route_readiness.py`,
  persistence in the store, probe I/O in the provider adapter, rendering/
  orchestration in the step API module, htmx/JS in a dedicated static file.
- New source files <=400 lines; do not grow `models.py`, `pages.py`, `store.py`,
  `security.py`, `connections.py`, `app.py` (no more lines) or
  `tests/e2e/test_design_system.py`; `onboarding_choices.py` stays <=250 and
  `onboarding_store.py` <=110. Re-read `.file-size-baseline.json` and
  `python3 scripts/audit_context_hygiene.py` before and after.
- The working tree may again carry another session's uncommitted work; never
  revert/clean/format it, and commit only your new files and targeted hunks
  (index-level blob staging is the established pattern).
- Commit progressively in small atomic commits; each message names the behaviour
  changed and the edge cases covered.

## Test commands

```bash
.venv/bin/python -m pytest -q --no-header --tb=line tests/test_route_readiness.py tests/test_onboarding_chooser.py tests/test_onboarding_chooser_state.py tests/test_onboarding_page.py
.venv/bin/python -m pytest -q --no-header --tb=line tests/e2e/test_onboarding_readiness.py tests/e2e/test_onboarding_chooser.py -k "not slow"
python3 scripts/audit_context_hygiene.py
python3 scripts/audit_emoji.py
```
(`uv run --frozen --no-sync` is fine too; the shared uv cache is occasionally
read-only, so `.venv/bin/python -m pytest` is the reliable fallback.)

## Visual validation required (real implementation, not static fixtures)

Capture at 320x740, 375x812, 768x1024, 1440x1000 to
`docs/onboarding/evidence/slice-03/`: checking, saved-unverified, verified,
invalid-credential, permission-denied, no-credit, rate-limited (wait copy),
timed-out, unavailable, unreachable, invalid-route, model-missing,
context/incomplete, retry-scheduled, plus the client-shell offline and
server-unreachable states; keyboard focus and one-announcement evidence; 200
percent text scale, forced colours, reduced motion, fixed dark under OS light.
Fixed dark theme only; OS light preference must stay dark. Write
`capture-results.json` and a human-opened-image `validation.json` with
`state`, `viewport`, `artifact`, `verdict`, `finding`, `source_commit`,
`reviewer`; use the same live-uvicorn + Chromium fixture and evidence pattern as
`tests/e2e/test_onboarding_chooser.py`. Missing evidence = FAIL; generated is not
reviewed. Use deterministic fake-provider fixtures (200 model list/401
generation, 402, 408, 429 Retry-After, 503 long multi-line error, unreachable,
slow/hung) - never a live provider account.

## Known limitations to carry forward

- Chromium/Linux headless only; no Firefox/WebKit, real phone, real screen reader,
  real browser zoom or OS forced-colours setting. Record that in the evidence README.
- The broader `Origin: null` plain-form-POST boundary (global
  `Referrer-Policy: no-referrer`) still affects server-rendered forms; slice 03
  must keep the per-page same-origin referrer meta on any new form page and must
  not weaken the guard. The global fix belongs to the security surface owner.
- Slice 01's success flash renders above `<main>`; the full announcement/landmark
  audit is slice 09.
- The slice-02 temporary "Continue to Apps & AI" bridge is still explicit and must
  not be linked from the marketing site.

## Slice exit (must all be done before stopping)

1. Run the fast and browser lanes above; record exact commands and results.
2. Capture and open the full visual matrix; record APPROVED/NEEDS WORK verdicts.
3. Update `docs/onboarding/task-plan.md` with CP3 status and any discovered edge
   cases added to `docs/onboarding/edge-case-matrix.md` section 8; update
   `docs/onboarding/setup-record.md`, `docs/design-system.md`, `docs/runtime-setup.md`,
   the changelog and user-facing help in the same commit range.
4. Append the acceptance record to `docs/onboarding/slices/slice-03.md`.
5. Write `docs/onboarding/slices/slice-04.md` approval notes if they changed and
   write `docs/onboarding/continuation-prompt-04.md` (slice 04: hosted-key
   connection step) containing the slice number, read-first paths, in-scope edge
   cases, visual evidence required, and the continuation rule.
6. Do not implement slice 04 in this run.
