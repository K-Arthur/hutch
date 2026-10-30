# Slice 02 - First-run handoff and in-context AI-service chooser

Status: IMPLEMENTATION BRIEF (refreshed 2026-10-29 after slice 01; not implemented). Acceptance gate: CP2; planning gate: CP0 in [task-plan.md](../task-plan.md).
Depends on: slice 01 ACCEPTED at CP1 - see [slice-01 acceptance record](slice-01.md#15-acceptance-record-cp1) and [evidence](../evidence/slice-01/README.md). Planning reviewer: independent review 2026-10-29, findings resolved in task-plan section 9.
Owner: TBD. Reviewer: TBD. Anchors re-read 2026-10-29 after slice 01; @src/hutch/server/static/app.js, @src/hutch/server/app.py and @src/hutch/server/templates/base.html still carry another session's uncommitted brand work - re-read before editing, never revert it. Use the ready-to-run [continuation prompt](../continuation-prompt-02.md) for the next agent.

## 0. What slice 01 actually delivered (use these, do not re-invent)

Implemented and accepted:

- `@src/hutch/onboarding.py:1-241` - pure domain. Constants `ONBOARDING_CONTRACT_VERSION=1`, `ONBOARDING_REQUIREMENTS_VERSION=1`, `REQUEST_MAX_CHARS`, `RESUME_TTL`, `STEP_ORDER`; `OnboardingSetup` (extra fields ignored), `SetupRecord`/`EditResult`/`ResumeView`, `default_setup`, `parse_setup`, `encode_setup`, `apply_request_edit`, `resume_view`, `empty_view`, state constants `STATE_EMPTY_NO_ROUTE`/`STATE_RESUME_CURRENT`/`STATE_RESUME_STALE`/`STATE_RESUME_EXPIRED`. Extend this file for `route_kind`/`route_chosen_at`, `chooser_view`, `choose_route`, `chooser_ready`; do not add I/O.
- `@src/hutch/onboarding_store.py:1-74` - `SETUP_KEY`, module `_LOCK`, `SetupLoad`, `SaveResult`, `load_setup`, `save_request`, `reset_setup`. Add `save_route(store, *, expected_revision, route_kind, now)` with the same lock/read-check-write and replay semantics; keep damaged/newer checks before domain decisions.
- `@src/hutch/server/onboarding_api.py:1-236` - `install_onboarding_routes(app)` with bounded render/flash/CSRF helpers, explicit state constants, `_fields_for_page`, `_editable_fields`, GET `/onboarding`, POST `/onboarding/request`, POST `/onboarding/reset`. Add the two chooser routes here; reuse the same minimal helper pattern (do not grow `pages.py`).
- `@src/hutch/server/templates/onboarding.html` and partials `_onboarding_request_text.html`, `_onboarding_reset_form.html`, `_onboarding_start_over.html` - chrome-less state machine. The saved/resumed primary CTA is currently the slice-01 interim `/#/connections` (marked TEMPORARY in the template); slice 02 replaces it with `/onboarding/ai-service`.
- `@src/hutch/server/static/onboarding.css` - 396 lines (under the 400 cap, but nearly full). Put chooser-only rules in a new `@src/hutch/server/static/onboarding-chooser.css` (<=400 lines) linked from the chooser template's head block, or split the request-step stylesheet first. Do not exceed the cap.
- `@src/hutch/server/static/onboarding.js` - 66 lines: submit busy state, pageshow restore, error-summary focus. Add the sessionStorage draft bridge here (keep <=120 lines) or split a chooser script if needed.
- `@src/hutch/server/templates/base.html` - now has `{% block head %}{% endblock %}` before `</head>` and `{% if chrome|default(true) %}` around the topbar and footer; existing pages are unchanged by default. Reuse them; do not restructure.
- `@src/hutch/server/app.py:7243-7248` - the two-line registration `from .onboarding_api import install_onboarding_routes` + `install_onboarding_routes(app)` already exists. Slice 02 adds routes inside the installer; do not add more `app.py` lines.
- Tests: `@tests/test_onboarding_state.py` (338 lines, 34 cases), `@tests/test_onboarding_page.py` (54 fast tests with the state tests), `@tests/e2e/test_onboarding_page.py` (44-capture live matrix), evidence under `docs/onboarding/evidence/slice-01/`. Reuse the fixtures/helpers and the seeded-record pattern.

Discovered during slice 01 and binding on slice 02:

1. **Plain form POST Origin boundary.** The security middleware sets `Referrer-Policy: no-referrer`; current Chromium/Firefox then submit plain form POSTs with `Origin: null`, which `_same_origin` refuses (403). This is pre-recorded in `@tests/e2e/test_route_state_boundaries.py` row `form-post-origin-null`. Slice 01's page fixed it locally with `<meta name="referrer" content="same-origin">` in its head block; the chooser template MUST do the same or its POST will 403 in the browser lane. Do not weaken the middleware; the broader server-form fix is owned by the security surface owner and recorded in the continuation prompt.
2. **Blank stored record means empty form, not edit.** `_editable_fields` sets editing only when a stored request exists. Keep that rule when adding the chooser's "Back to my request".
3. **Validation/edit semantics.** Fixable input problems re-render with the current stored revision and preserved text; only different content on a stale revision becomes a 409 conflict. Reuse this for route selection.
4. **State token discipline.** Every rendered page branch sets `data-onboarding-state` to a canonical token; the request-step states use `setup.*`/`input.invalid`/`auth.csrf_rejected`. Add chooser tokens in the same vocabulary (for example `setup.ai_service.chosen`, `setup.ai_service.invalid`, `setup.ai_service.stale`) and document them in the contract.
5. **Anchor corrections.** `@tests/conftest.py:18` does not define a `client` fixture (planning drift); page tests construct `TestClient(create_app())` directly like `@tests/test_models_page.py:16`. `docs/onboarding/setup-record.md` is the normative contract to extend.
6. **Evidence path for this run.** Store browser evidence under `docs/onboarding/evidence/slice-02/` (execution directive), not `artifacts/slice-02/`; keep a pointer/validation copy under artifacts if the checkpoint wording needs it.
7. **Working tree.** `app.js`, `app.py`, `base.html` and many templates still carry another session's uncommitted brand work; commit only your own new files and targeted hunks (slice 01 used index-level commits for the two-line `app.py` change and the base template blocks). Never `git checkout` or clean those files.

## 1. User outcome (one sentence)

The empty-chat first-run action always leads to /onboarding (the request step, never the Apps & AI catalog); a saved request's single primary action opens the in-context AI-service chooser, which offers exactly three routes (hosted API key, local model service, existing OpenCode login), names one recommended starting point honestly, states that apps and devices can be connected later, and keeps the written request intact across the choice, back/forward, and reload.

Not in this slice: provider probes/readiness states (slice 03), key entry or saving (slice 04), local-service probing (slice 05), external-login waiting/recovery (slice 06), assistant create or first request (07/08), full a11y hardening (09), pairing (10), marketing site (11). The chosen-route summary's Continue links to the existing Apps and AI surface as an explicitly temporary bridge, replaced by slices 04-06.

## 2. Primary task per step

### 02a - Chooser contract and pure route-selection decisions
Files/new functions:
- @src/hutch/onboarding.py (extend the module created in slice 01; still no I/O):
  - extend OnboardingSetup with route_kind: str = '' (NOT a strict Literal, so an unknown/newer record parses and surfaces as stale instead of damaged) and route_chosen_at: str = ''; add ROUTE_KINDS = ('hosted_key', 'local_service', 'opencode'), ROUTE_LABELS and ROUTE_DESCRIPTIONS (copy constants only; no provider claim beyond the existing product surfaces).
  - chooser_view(setup) -> ChooserView (three options with label/description/required-vs-optional copy, recommended: str = 'hosted_key' with the honest qualifier 'recommended if you already have a provider key'; no detection is claimed in this slice - slice 03 may replace the recommendation with a detected/verified route).
  - choose_route(setup, *, expected_revision, route_kind, now) -> ChooseResult returning chosen(new_setup), replayed(setup) (same choice), stale(current_setup), invalid(reason); sets step='ai_service', records route_chosen_at, increments revision only on change; changing a previously chosen route is allowed and increments revision; a record with a newer contract_version is stale (never damaged).
  - chooser_ready(setup) -> bool: chooser requires a saved request (slice-01 requirement); pure.
- @tests/test_onboarding_state.py (extend; keep under 400 lines, otherwise split into @tests/test_onboarding_chooser_state.py): each of the three kinds accepted; unknown kind invalid; same-choice replay; route change allowed; chooser not ready without request; route fields preserved through serialize/parse; forward-compat read of a slice-01 record with no route fields yields route_kind=None.

### 02b - Chooser page and selection form
Files/new functions:
- @src/hutch/server/onboarding_api.py: add GET /onboarding/ai-service (load record; if no saved request -> 303 to /onboarding with a notice 'Write your request first'; else render onboarding_ai_service.html; owner-only as before, 403 for paired sessions; never auto-redirect from /onboarding itself) and POST /onboarding/ai-service/choose (CSRF, revision, route_kind allowlist; 303 to /onboarding/ai-service on chosen/replayed with distinct flash copy; 422 error summary for invalid input; 409 explicit conflict for a stale revision; never redirect to a user-supplied target). The step/route save uses the slice-01 adapter's new save_route(store, expected_revision, route_kind, now) (same process lock/replay semantics as save_request).
- @src/hutch/server/templates/onboarding_ai_service.html (new): extends base.html, same chrome-less contract as slice 01; h1 'Choose how Hutch reaches an AI model'; one sentence stating what this step unblocks and that apps/devices come later; three route cards as real radio inputs plus labels (no click-only divs), one recommended tag with the honest qualifier, description/help naming prerequisites (hosted key: you need a provider account; local service: a local model server you run; OpenCode: the CLI installed or an existing login); one primary 'Continue with this route'; secondary 'Back to my request'; show the saved request text in a read-only summary so the user sees it is kept; chosen state shows 'You chose <route>' plus 'Change route' and the temporary 'Continue to Apps & AI' link (flagged with a one-line code comment as interim).
- @src/hutch/server/templates/_onboarding_route_card.html (new partial) only if it reduces duplication; one concern per partial.
- @src/hutch/server/static/onboarding.css: add chooser layout - stacked cards at phone widths, 3-up or 2+1 at wide widths, 44 px coarse-pointer targets, focus-visible, selected state not colour-only (checkmark + text), forced-colours and reduced-motion blocks; no fixed footer; keep the file under 400 lines.
- @src/hutch/server/static/onboarding.js: keep progressive enhancement minimal; selection works without JavaScript (native radios + submit); do not add client-side routing or provider detection.
- @tests/test_onboarding_chooser.py (new <=400 lines): GET requires a saved request (303 when missing, with the request form reachable); renders exactly three route options and no apps/devices/channel/Telegram wording; recommended copy contains the qualifier; POST valid choice 303 and persisted across reopen; unknown kind 422; stale revision 409; paired capability None for both routes; chosen state renders request text unchanged.

### 02c - First-run SPA handoff and browser-draft bridge
Files/functions:
- @src/hutch/server/static/app.js:3257-3408 renderChatStudio and its submit handler 3356-3386: in the no-provider branch only, replace the location.hash = '#/connections' detour (3371-3375; related no-route action around 3314-3316) with an explicit save of the tab draft then window.location.assign('/onboarding') - always the request step, never /onboarding/ai-service directly and never an auto-redirect chain. The user reaches the chooser by the saved request's single primary action 'Continue to AI service'. Keep the existing behaviour for a user who already selected a route (promptNewBot(...) at 3379). In-place change: target at most ~10 changed lines, no net growth of app.js (baseline headroom is 187 lines but budget is not the goal - do not expand scope).
- @src/hutch/server/static/onboarding.js: add a browser-draft cache bridge used only by the onboarding page: read sessionStorage['hutch-first-run-request'] (the existing app.js draft shape at @src/hutch/server/static/app.js:132-163, version 1, 20,000 char cap); if the server record has no saved request and the draft is valid, prefill the textarea and show the honest note 'Restored from this browser tab - not saved on this machine yet'. Never send it to the server automatically; the normal form POST is the only save. Never trust this value server-side.
- @src/hutch/server/templates/onboarding.html: saved-state primary action becomes /onboarding/ai-service (replacing the slice-01 interim /#/connections target); the request textarea keeps the same contract.
- Pinned tests to update deliberately (do not delete coverage; @tests/e2e/test_design_system.py is at its frozen line cap, so edits must be line-neutral or coverage moves to a new file):
  - @tests/e2e/test_design_system.py:748-912 test_first_run_draft_and_ai_readiness_survive_connections_and_failures - its no-route primary-action assertion changes from reaching Apps & AI to reaching /onboarding with the draft preserved; the readiness/draft-survival assertions stay.
  - @tests/e2e/test_design_system.py:915-1014 test_first_run_readiness_distinguishes_saved_route_and_partial_states - only adjust destination assertions if they touch the no-route action.
  - Verify @docs/realignment/capture_first_run.py:68-73: the captured first-run copy is unchanged, so it should keep passing; if the CTA label changes, update its copy check in the same commit.
- @tests/e2e/test_onboarding_chooser.py (new <=400 lines): SPA empty chat -> click primary action -> land on /onboarding (request step) with the typed request carried from the tab draft; save -> single primary action opens /onboarding/ai-service; assert no request leaves the origin (no provider/external network call), no apps/devices wording; back to / returns to the first-run view with the draft intact; chosen route persists after reload.

### 02d - Back/forward, resume, and visual evidence
Files:
- @tests/test_onboarding_chooser.py + @tests/e2e/test_onboarding_chooser.py: browser history semantics - after POST 303, Back returns to the chooser GET (not a resubmit prompt); Forward/reload keeps the chosen state; two tabs on different steps do not corrupt each other's record (stale revision conflict is explicit).
- Captures to docs/onboarding/evidence/slice-02/ at 320x740, 375x812, 768x1024, 1440x1000: chooser default, recommended state, chosen/resume, invalid-selection error, no-request redirect state, keyboard focus across cards, 200 percent zoom, forced colours, reduced motion; plus one SPA handoff before/after capture at 375x812. Binary opened-image verdicts in validation.json; limitations recorded.
- @docs/design-system.md: add the chooser rules (three routes, one honest recommendation, apps/devices deferred, request kept visible, required vs optional words).
- Slice acceptance note appended to this brief after CP2.

## 3. Boundary for this slice

- UI: server-rendered chooser page + hand-written CSS/JS; one small in-place SPA edit for the entry handoff. No new SPA route framework, no client-side setup state.
- API: HTML form contract only (GET /onboarding/ai-service, POST /onboarding/ai-service/choose). No JSON API, no provider call.
- Provider integrations: none. Recommendation is static and labelled as such; no detection claim, no check_connection, no browser fetch to any provider or localhost.
- Server-side authorization: same owner-only/paired-denied default and CSRF checks as slice 01; route kind is a server-side allowlist, never rendered from query/header input; no user-controlled redirect.
- Persistence: same kv record; adds route_kind/route_chosen_at fields and the ai_service step; no schema/migration change; unknown stored route values become the stale state rather than a crash.

## 4. Edge cases in scope (from [edge-case-matrix.md](../edge-case-matrix.md))

| Matrix row | Covered here as |
|---|---|
| EC-01 partial save + resume | Choice saved with revision; reload/Back shows chosen state; in-flight double-submit replays. |
| EC-02 session expiry mid-step | CSRF/session rejection renders the explicit 403/conflict recovery, not a provider error; draft request remains visible. |
| EC-04 duplicate submission | Same-choice resubmit replays ('already selected'); a different choice is a deliberate change, not a duplicate. |
| EC-07 stale resume | Stored route_kind not in the allowlist or requirements mismatch -> stale state offering re-choose; request preserved. |
| EC-08 optional step skipped | Copy states apps/devices are optional and deferred; the chooser itself is required for activation, and 'Back to my request' is not a dead end. |
| EC-10 non-Latin name/text | Saved request (CJK/accented/60-char) shown unchanged in the chooser summary; wrapping tested. |
| EC-16/17 screen reader + keyboard | Radios are real inputs; step heading focused on arrival; selection and errors announced once; full journey gate is slice 09. |
| EC-18/19 motion + dark/forced colours | No animation added; selected state is checkmark + text; forced-colours capture. |
| EC-20 empty/loading/saving/error/blocked | Explicit default/chosen/invalid/conflict/no-request states; no generic error. |
| EC-06 offline | Not representable on a page that cannot load; reload after server restart keeps the choice. The client-shell net.offline/server.unreachable state is owned by slice 03 (with retry) and gated in slice 09/CP6 - not dropped. |

## 5. Front-end states for this slice

| State | Trigger | Must show | Must not do |
|---|---|---|---|
| default | saved request, no route | three route options, one recommended with honest qualifier, read-only request summary, primary 'Continue with this route', secondary 'Back to my request' | show apps/devices/channels as onboarding steps; imply a route is detected/verified |
| selected | route chosen | selected card (checkmark + text), 'You chose <route>', 'Change route', temporary 'Continue to Apps & AI' (interim, slices 04-06 replace) | claim the route works/verified; hide the request |
| saving | submit in flight | disabled + aria-busy | lose selection or request |
| invalid | no/invalid selection | focused error summary + inline error on the group | colour-only error |
| conflict | stale revision (other tab) | explicit 'setup changed in another window', both choices shown, submitted choice preserved, 'Review latest' action | silently overwrite |
| stale | unknown stored route / requirements mismatch | 'Setup has changed', kept request, 'Choose a route again' | auto-select a default and advance |
| no-request | record without saved request | redirect to /onboarding with notice 'Write your request first' | render a chooser with nothing to carry |
| forbidden | missing CSRF / paired session | explicit 403 copy | raw exception |
| empty (no provider at all) | fresh install | the chooser is the honest answer, not a blank or dead page | pretend a default model is ready |

Copy rules: required vs optional stated in words; apps/devices explicitly 'later'; no 'free', 'trial', 'plan', 'sign up', or account language.

## 6. Form/API contract changes

GET /onboarding/ai-service -> 200 text/html (owner) with the states above; 303 to /onboarding when the record has no saved request; 403 for paired sessions.
POST /onboarding/ai-service/choose (form-encoded): fields csrf (required), revision (required int), route_kind (required, one of hosted_key|local_service|opencode).
- 303 Location: /onboarding/ai-service on chosen/replayed (distinct flash: 'Route selected' / 'Route already selected').
- 409 text/html explicit conflict for a stale revision with the current record and the submitted choice preserved.
- 422 text/html error summary for a missing/unknown route_kind or malformed revision.
- 403 for missing/invalid CSRF.
Record delta: {'route_kind':'hosted_key','route_chosen_at':'2026-10-29T...+00:00','step':'ai_service','revision':2} (exact key names fixed in 02a); slice-01 readers ignore unknown fields, so a rollback to slice-01 code resumes the request step safely.

## 7. Server-side authorization and security checklist

- [ ] New routes absent from REMOTE_ROUTE_CAPABILITIES; test asserts None for both GET and POST.
- [ ] Every POST checks CSRF; route_kind validated against a server-side allowlist; no user-controlled redirect.
- [ ] No provider/localhost network call from this slice's page or tests; e2e asserts only same-origin requests.
- [ ] Request text shown with Jinja autoescape; no secrets stored; no account/credential collection.
- [ ] Browser-draft bridge is a cache read only; the server never trusts sessionStorage and never accepts draft content in a query/header.
- [ ] app.js change is minimal, in-place, and keeps the route-selected branch and existing readiness behaviour intact.

## 8. Marketing-site dependency

None. The site keeps saying no hosted signup/account and points to the source path; the chooser is an in-app step and must not be described as a hosted signup. Any wording sync is slice 11 ([marketing-changes.md](../marketing-changes.md)); do not touch website/ here.

## 9. Docs to update

- @docs/design-system.md chooser rules (three routes, honest recommendation, request kept, optional apps/devices deferred).
- docs/onboarding/slices/slice-02.md acceptance record after CP2.
- docs/onboarding/task-plan.md CP2 checkpoint note only.
- docs/onboarding/evidence/slice-02/validation.json + PNGs (pointer copy under artifacts/slice-02/ if the checkpoint wording needs it).

## 10. Tests and commands

- Fast lane: npm run test:agent -- tests/test_onboarding_state.py tests/test_onboarding_chooser.py tests/test_onboarding_page.py; the rest of npm run check:agent; python3 scripts/audit_context_hygiene.py (seven pre-existing violations are baseline; no new violations; do not grow app.js beyond baseline).
- Browser lane: uv run --frozen --no-sync pytest -q --no-header --tb=line tests/e2e/test_onboarding_chooser.py plus the updated pinned first-run test @tests/e2e/test_design_system.py:748-912; record commands in evidence.
- Manual: real app with a fresh HUTCH_STATE_DIR, type a request into the empty chat, click the primary action, verify the chooser and draft carry; reload and Back; open all PNGs for binary verdicts.

## 11. Visual-validation evidence required

Path docs/onboarding/evidence/slice-02/ (execution directive; a pointer/validation copy may live under artifacts/slice-02/). Rows: chooser default, recommended state, chosen/resumed, invalid selection, stale/no-request redirect, keyboard focus order, 200 percent zoom, forced colours, reduced motion at 320x740/375x812/768x1024/1440x1000; plus empty-chat handoff before/after at 375x812. Required validation.json fields: state, viewport, artifact, verdict, finding, source_commit, reviewer. Missing evidence = FAIL; generated is not reviewed.

## 12. Acceptance criteria (binary, CP2)

- [ ] Empty-chat no-route primary action lands on /onboarding (request step) with the typed request preserved; saving it exposes one primary action to /onboarding/ai-service; a user who already has a route keeps the existing assistant-setup path.
- [ ] Exactly three routes rendered, one recommended with the honest qualifier, apps/devices/channels explicitly deferred, one primary action, request visible.
- [ ] Choice persists across reload/restart and Back/Forward; same-choice replay is idempotent; invalid/stale/conflict/no-request states are explicit.
- [ ] No provider call or browser fetch beyond same-origin; no new site claim; updated pinned e2e assertions green (coverage not reduced).
- [ ] CSRF/paired-phone checks pass; no secrets/account fields; onboarding.css stays under 400 lines and app.js does not grow past baseline.
- [ ] Evidence APPROVED for every required state/viewport; docs updated; reviewer sign-off recorded.

## 13. Rollback plan

Change shape: one template + optional partial + CSS additions + JS bridge + two new routes + one small in-place app.js edit + tests. No migration; record gains two fields.
1. Revert the app.js handoff commit: the no-route action returns to location.hash = '#/connections' (exact previous lines), restoring current first-run behaviour; the pinned e2e tests revert with it.
2. Revert the two new routes and the partials/templates; onboarding.html's saved-state CTA returns to the slice-01 interim /#/connections target (or to /onboarding if rollback is partial - never leave a dead link).
3. Keep the existing kv record. A record containing route_kind/step='ai_service' is readable by slice-01 code because the model ignores unknown fields and the step is valid; the resume view shows the saved request with the interim CTA. Do not delete user setup data.
4. Verify: / empty state unchanged, pinned first-run e2e green, /onboarding/ai-service 404, audit unchanged, no migration/SCHEMA_VERSION delta.
Risk: app.js and the pinned e2e file are dirty/at their frozen cap; use targeted patches and line-neutral test edits. Never git checkout those files.

## 14. Risks / open questions

- The exact app.js lines drift with the other session's brand work; the handoff must be a targeted in-place edit reviewed against renderChatStudio's current submit handler.
- A static recommendation ('hosted key if you already have one') could become stale once slice 03 detects routes; slice 03 owns replacing the recommendation with a detected/verified route and must update the chooser copy, not duplicate it.
- Empty request + click: the SPA may navigate with no saved request; the chooser redirects back with a notice. Confirm this is not a loop and capture it (no-request state).
- The temporary 'Continue to Apps & AI' bridge is a visible detour; it must be replaced in slices 04-06 and must not be linked from the marketing site.
- Two tabs: explicit 409 conflict is required; do not add last-writer-wins autosave in this slice.