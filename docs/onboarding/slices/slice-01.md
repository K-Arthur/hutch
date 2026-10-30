# Slice 01 - Dedicated onboarding route with server-owned resume

Status: IMPLEMENTED AND ACCEPTED at CP1 (2026-10-29). Acceptance gate: PASS; see section 15. Planning gate: CP0 in [task-plan.md](../task-plan.md).
Owner: Lead implementation. Reviewer: independent review (fresh-context agent, 2026-10-29, NEEDS WORK -> resolved, section 15); planning reviewer: independent review 2026-10-29, findings resolved in task-plan section 9.
Commits: c7087d3f (domain + persistence), b3293553 (base chrome/head seam), 88221ef9 (request step), 945500cf (live state-matrix evidence), plus the CP1 docs commit that contains this record.
Timeline date of anchors: 2026-10-29 working tree. Another session's uncommitted brand work touches `app.js`, `app.py` and `base.html`: re-read every anchor before editing and never revert that work.

## 1. User outcome (one sentence)

A first-run owner can open a dedicated `/onboarding` page, write the request they want answered, and find the same step and request after a refresh, a second tab, or a server restart; when stored setup data is stale or damaged the page names that state and offers an explicit recovery action instead of silently reusing it.

Not in this slice: AI-service choice, provider probes, keys, OpenCode, assistant creation, first request, phone pairing, marketing site, full keyboard/screen-reader hardening (slice 09). The request step's primary action links to the existing Apps & AI surface as an explicitly temporary bridge; slice 02 replaces that target.

## 2. Primary task per step

### 01a - Setup record + pure transition decisions
Files/new functions:
- `@src/hutch/onboarding.py` (new; no FastAPI, templates, store, filesystem, network):
  - constants `ONBOARDING_CONTRACT_VERSION = 1`, `ONBOARDING_REQUIREMENTS_VERSION = 1`, `REQUEST_MAX_CHARS = 20000`, `STEP_ORDER = ("request", "ai_service", "connection", "assistant", "first_request")`, `REQUIRED_STEPS`, `OPTIONAL_STEPS`.
  - pydantic `OnboardingSetup` (fields: `contract_version: int = 1` (NOT a strict Literal: a newer contract version must be parseable and surfaced as a stale/newer-version state, never as "damaged"), `revision: int >= 0`, `step: str`, `request_text: str`, `requirements_version: int`, `resume_expires_at: str`, `created_at: str`, `updated_at: str`; ISO-8601 UTC via `iso/utcnow` imported from `@src/hutch/models.py:23-28`; unknown extra fields ignored so later slices can add route data without a schema break).
  - `default_setup(now) -> OnboardingSetup`.
  - `apply_request_edit(setup, *, expected_revision, request_text, now) -> OnboardingEditResult` returning one of `accepted(new_setup)`, `replayed(setup)`, `stale(current_setup)`, `invalid(reason)`; no exceptions for expected outcomes; strips outer whitespace, rejects empty/over-cap, increments revision only on an actual content change.
  - `resume_view(setup, *, now, active_requirements_version) -> ResumeView` (step, step index, total required, request text, `stale: bool`, `stale_reasons: tuple[str, ...]`, `expired: bool`, timestamps); stale when contract/requirements versions differ, the stored step is unknown, or a newer contract version was saved; `expired` when `now >= resume_expires_at` (TTL, default 30 days, refreshed on each save). Expired/stale keep the request text but require one explicit action to continue.
- `@tests/test_onboarding_state.py` (new): decisions only - default state; accepted save increments revision, updates `updated_at` and refreshes `resume_expires_at`; identical resubmit replayed; same revision/different text stale; whitespace-only invalid; 20,000 vs 20,001 chars; non-Latin/accented/CJK/60-char text round-trips exactly; emoji inside user data is allowed (repo no-emoji rule covers source/docs/UI, not user content); requirements-version mismatch stale with reason; unknown stored step stale; a record saved by a newer `contract_version` surfaces newer-version stale, not damaged; `resume_expires_at` in the past surfaces expired (fixed clock); timestamps valid ISO-8601 UTC.

### 01b - Revision-safe persistence adapter
Files/new functions:
- `@src/hutch/onboarding_store.py` (new): `SETUP_KEY = "onboarding:setup:v1"` (kv table, `@src/hutch/store.py:117-120` and `kv_get/kv_set` `@store.py:11730-11740`); module-level `threading.Lock()`; `load_setup(store) -> SetupLoad` (record or absent or damaged); `save_request(store, *, expected_revision, request_text, now) -> SaveResult` (lock; load; delegate to `apply_request_edit`; encode with `json.dumps(..., sort_keys=True, separators=(",", ":"))`; write only on accepted). Never stores secrets or provider keys; no migration and no `SCHEMA_VERSION` change.
- Tests in `@tests/test_onboarding_state.py`: round-trip through a real `Store`; persistence survives a closed/reopened store (pattern `@tests/test_api.py:467-502`); damaged JSON reports damaged, not crash; concurrent save attempts keep one writer (thread test asserts exactly one accepted revision increment per expected revision).

### 01c - Chrome-less onboarding page and form
Files/functions:
- `@src/hutch/server/onboarding_api.py` (new): `install_onboarding_routes(app)`; minimal bounded helpers (Jinja2Templates over `templates/`, `render(request, name, **ctx)` with `csrf=getattr(request.state, "csrf", "")`, `redirect(target, notice="", error="")` using flash cookies, `read_form(request)` using `@src/hutch/server/security.py:506-509` `check_csrf` and `Form`-equivalent parsing). Routes:
  - `GET /onboarding` -> load setup, resume view, render `onboarding.html` with `chrome=False`, `nav=""`.
  - `POST /onboarding/request` -> `read_form`; parse `revision`; delegate to store adapter; 303 to `/onboarding` on accepted/replayed; 409 render with conflict state; 422 render with error summary; 403 from missing CSRF.
  - `POST /onboarding/reset` -> CSRF-checked explicit "Start over" for damaged/stale state; clears the key via existing `store.kv_set` of a fresh default (prefer writing a fresh record with revision 0 rather than deleting, so reloads stay deterministic); 303.
- `@src/hutch/server/app.py:7243-7248`: two line addition only - `from .onboarding_api import install_onboarding_routes` and `install_onboarding_routes(app)` next to `register_pages(app)`. No `pages.py` change.
- `@src/hutch/server/templates/base.html`: add `{% block head %}{% endblock %}` after line 41; wrap the header block (lines 45-66) and footer (line 74) in `{% if chrome|default(true) %}`; keep the existing `{% if nav %}` gates intact so every current page is unchanged by default.
- `@src/hutch/server/templates/onboarding.html` (new): extends `base.html`; title block; `{% block head %}` (added to base before `</head>`) loading `/static/onboarding.css`; content sits inside base's existing `<main id="main">` so the base skip link (`base.html:44`) works unchanged (no second skip target); one `h1`; one form; request textarea via `_form.html` `textarea(...)` macro (`@templates/_form.html:61-74`), required, maxlength 20000, help text naming what is stored locally; hidden `csrf` and `revision` inputs; a new server-rendered error summary (role alert, `tabindex="-1"`, one link per field to the input; GOV.UK error-summary pattern from research, not copied from a JavaScript banner); polite `role="status" aria-live="polite"` saved/resume message; `form_actions()` macro; primary submit "Save and continue", secondary link "Back to the dashboard".
- `@src/hutch/server/static/onboarding.css` (new, hand-written source <=400 lines): page-only layout using server-page tokens (`brand-tokens.css`/`hutch.css`; no generated CSS edits), 320-1440 reflow, no fixed footer, focus-visible, forced-colours block, reduced-motion block, long-text wrapping.
- `@src/hutch/server/static/onboarding.js` (new <=120 lines): progressive enhancement only - on submit set button disabled + `aria-busy="true"` + status text "Saving...", restore on `pageshow`; on load move focus to the error summary when it is present (pattern already used in page templates). All behaviour works without JavaScript (plain form POST).
- `@tests/test_onboarding_page.py` (new): TestClient `@tests/conftest.py:18` pattern; GET 200 and chrome-less (no `id="primary-nav"`, no `footer class="foot"`); `<meta name="csrf">` present; POST without CSRF 403; valid save 303 then GET shows saved request; duplicate resubmit replayed (no duplicate record, revision unchanged); stale revision 409 renders both versions and keeps submitted text; oversized request 422 with focused error summary markup; `<script>` in the request renders escaped; paired-phone route capability is `None` (mirror `@tests/test_pairing_setup.py:69-70` assertion on `REMOTE_ROUTE_CAPABILITIES[("GET", "/onboarding")]` and the POST route); damaged record renders recovery state and reset works; persistence across `create_app()` reopen (pattern `@tests/test_api.py:467-502`).

### 01d - Save, replay, conflict, stale and resume states + visual evidence
Files:
- `@src/hutch/server/templates/onboarding.html` + `onboarding_api.py`: render the explicit states listed in section 5; no generic "error" for stale/damaged/conflict.
- `@tests/e2e/test_onboarding_page.py` (new <=400 lines): browser lane driven by a module fixture modelled on `@tests/e2e/test_design_system.py:69-90` (temp `HUTCH_STATE_DIR`, uvicorn on port 0); captures to `docs/onboarding/artifacts/slice-01/` using `@tests/support/artifacts.py:9-18` conventions; verifies reload resume, no horizontal overflow at 320x740/375x812/768x1024/1440x1000, primary action reachable, keyboard tab order, reduced-motion context, forced-colours emulation, 200 percent text zoom; writes `results.json`; human reviewer opens every PNG and records a binary verdict in `validation.json` (never generated-only).
- `@docs/design-system.md` "Setup recovery boundaries": add the server-owned setup-record rule, revision/replay semantics, stale/damaged states and the request-step error-summary pattern.
- Slice acceptance note appended to this brief after CP1 (reviewer/date/evidence link).

## 3. Boundary for this slice

- UI: Jinja template + hand-written CSS + progressive-enhancement JS only. No SPA route, no new front-end build, no client-side source of truth.
- API: HTML form contract only (GET page, POST save/reset, 303/409/422 responses). No JSON API in this slice.
- Provider integrations: none. No network request of any kind is made by this slice.
- Server-side authorization: route is local-owner-only by the existing `authorize_remote_route` default (new routes are `None` in `REMOTE_ROUTE_CAPABILITIES`, `@src/hutch/server/app.py:186-210`, `7249-7252`); paired phones are refused; all mutations require the double-submit CSRF token via the shared `check_csrf`; same-origin middleware applies (`@src/hutch/server/security.py:314-318`). No user-controlled redirect target (no `next` parameter).
- Persistence: one kv record per installation, keyed `onboarding:setup:v1`; browser `sessionStorage` is not read or written by this slice (slice 02 adds the draft cache bridge). No migration, no schema change.

## 4. Edge cases in scope (from [edge-case-matrix.md](../edge-case-matrix.md))

| Matrix row | Covered here as |
|---|---|
| EC-01 partial save + resume | Server-confirmed save only; failed write keeps form and shows an error; reload resumes at the last confirmed revision. |
| EC-02 session expiry mid-step | CSRF/session rejection returns 403 with a recovery page (reload/sign in again) and the drafted text preserved in the form; never rendered as a provider error. Full session-expiry handling for polling is slice 06/08. |
| EC-04 duplicate submission | Revision replay: identical resubmit returns success-once messaging and does not duplicate state; different content with a stale revision gets the explicit conflict state, not silent overwrite. |
| EC-07 stale resume | Requirements/contract version mismatch or unknown step -> stale banner listing what is kept and one recovery action. |
| EC-10 non-Latin name/text | Request text in CJK, accented, RTL and 60-char cases round-trips and wraps without loss; no transliteration. |
| EC-15 keyboard/viewport | Slice-01 baseline: primary action is in normal flow (never a fixed footer), page reflows at 320 px, 200 percent zoom; full keyboard/open-keyboard gate is slice 09. |
| EC-16 screen-reader step change | One polite status region: resume message once on load, save result once, error summary focused. Full cross-step inventory is slice 09. |
| EC-17 keyboard-only | Form is keyboard-completable in this slice; no custom widgets. Full journey is slice 09. |
| EC-18 reduced motion | No motion added; spinner/status is text-based; capture with reduced-motion emulation. |
| EC-19 dark/forced colours | Server-page dark tokens; forced-colours capture; no light-theme promise. |
| EC-20 empty/loading/saving/error/blocked | Explicit states in section 5; no generic error. |

Offline/local-server-down cannot be rendered by a page that cannot be fetched; this slice proves reload-recovery after a server restart. The explicit `net.offline` / `server.unreachable` client-shell state is owned by slice 03 (with retry) and gated in slice 09/CP6; it is not silently dropped. This limitation is recorded in the evidence.

## 5. Front-end states for this slice

| State | Trigger | Must show | Must not do |
|---|---|---|---|
| empty | no record | one h1, honest two-sentence explanation ("Hutch is already installed on this machine; the next step is choosing an AI service"), request field, one primary "Save and continue", secondary "Back to the dashboard" | imply an account/signup, claim a model is ready, show a fake checklist |
| saving | submit in flight | button disabled + `aria-busy` + "Saving..." status | allow double navigation or lose typed text |
| saved | record with request | confirmed request text, "Saved on this machine" timestamp in local time, primary "Continue to AI service" (interim target `/#/connections`; marked in code as temporary), link to edit | call the setup verified or complete |
| resumed | record loaded on GET after prior session | saved request + "You left off here" polite announcement once | re-announce on every poll (no polling here), pretend fresh |
| edit | user changes saved request | same saved layout with editable field and "Save changes" | create a second record |
| conflict | stale revision from another tab/submit | "This setup changed in another window" plus both versions, submitted text preserved, action "Review latest saved setup" | overwrite the newer record silently |
| stale | requirements/contract version mismatch or unknown step | "Setup has changed since you started" plus kept vs re-check list and "Use my request and continue" (re-save under current requirements) | skip newly required steps silently |
| expired | `now >= resume_expires_at` (fixed-clock test) | kept request text, "This setup was saved a while ago; continue to refresh it", one action that re-saves and refreshes the TTL | delete the request or pretend the setup is current |
| newer-version | record contract_version newer than this code | explicit "saved by a newer Hutch version" state with the kept request; primary is the safe dashboard exit, destructive "Start over" is a secondary button | classify it as damaged/corrupt or overwrite it |
| damaged | unreadable/corrupt stored record | "The saved setup on this machine is unreadable", request not fabricated; primary is the safe dashboard exit, destructive "Start over" (CSRF POST reset) is secondary | show partial/false state or raw exception |
| reset-blocked | CSRF-valid reset POST while a current request is saved | 409 "Your saved setup is still current" with the request shown and a back-to-saved-setup action | wipe usable state from a stray POST |
| validation error | empty/over-20,000 | focused error summary with link to field, inline error, value preserved | colour-only error, clear input |
| forbidden | missing CSRF / paired phone | explicit "not available from this session" copy (403 page) | raw exception text |

Copy rules: "saved" is never called "connected"/"verified"; required vs optional is stated in words ("You need one AI service before your first request"); no celebration screen. The request step ships its own small field tier (`static/onboarding-form.css` + `_onboarding_request_form.html`) because the shared form macro tier is another session's uncommitted work; the markup is a real label + textarea + help + error and works without JavaScript.

## 6. Form/API contract changes

`GET /onboarding` -> 200 text/html (owner); 403 for a paired-phone session (existing dependency) ; renders section 5 state.
`POST /onboarding/request` (application/x-www-form-urlencoded):
- fields: `csrf` (required), `revision` (required int, the record revision the form was rendered from), `request` (required string, 1-20,000 chars after outer whitespace trim).
- 303 `Location: /onboarding` on accepted or replayed save (flash notice differs: "Saved" vs "Already saved").
- 422 text/html with error summary for empty/over-cap/invalid revision syntax; input preserved.
- 409 text/html explicit conflict state for a stale revision with different content; both values rendered.
- 403 for missing/invalid CSRF (existing`check_csrf` behaviour).
`POST /onboarding/reset` { csrf } -> 303 /onboarding with a fresh default record (revision 0); server-gated to absent/blank, damaged, stale, expired or newer-version records, and 409 `setup.reset_blocked` otherwise so a stray CSRF-valid POST cannot wipe a current saved request.
No JSON endpoints, no Idempotency-Key header in this slice (an HTML form cannot send one; revision replay is the duplicate guard). Record example: `{"contract_version":1,"revision":1,"step":"request","request_text":"...","requirements_version":1,"resume_expires_at":"2026-11-28T...+00:00","created_at":"2026-10-29T...+00:00","updated_at":"..."}`. A record with a newer `contract_version` is parsed raw and rendered as the newer-version stale state, never as damaged/corrupt.

## 7. Server-side authorization and security checklist

- [x] New routes are absent from `REMOTE_ROUTE_CAPABILITIES` (paired phones refused) and covered by a test asserting `None`.
- [x] Every POST calls `check_csrf`; no CSRF-free mutation path; reset is additionally state-gated server-side.
- [x] No user-controlled redirect target; flash cookies are `SameSite=Strict` and the page is served `Cache-Control: no-store`.
- [x] Request text stored only; no secrets/keys/tokens in the record or page source; Jinja autoescape for user text.
- [x] Content caps enforced server-side (20,000 chars), not only `maxlength`.
- [x] No network/provider call; no telemetry; no external asset added. The page opts into a same-origin referrer (`meta referrer`) only because the global `Referrer-Policy: no-referrer` otherwise makes Chromium/Firefox send `Origin: null` on plain form posts (recorded boundary, matrix section 14).
- [x] Route registration adds at most two lines to `app.py`; `models.py`/`pages.py`/`store.py`/`security.py`/`connections.py` untouched.

## 8. Marketing-site dependency

None. `/onboarding` is not linked from the marketing site and makes no claim about it; final marketing boundary changes are slice 11 ([marketing-changes.md](../marketing-changes.md)). Do not add an install/download CTA while implementing this slice.

## 9. Docs to update

- `@docs/design-system.md` "Setup recovery boundaries": server-owned setup record, revision/replay, stale/damaged recovery, error-summary focus.
- `docs/onboarding/slices/slice-01.md`: append acceptance record after CP1 (reviewer, date, evidence path, verdict).
- `docs/onboarding/task-plan.md`: CP1 checkpoint note (evidence links) only; do not rewrite the plan.
- `docs/onboarding/evidence/slice-01/validation.json` (canonical evidence, see below) plus the pointer copy under `docs/onboarding/artifacts/slice-01/` for the CP1 wording.

## 10. Tests and commands

- Fast lane result: `.venv/bin/python -m pytest -q --no-header --tb=line tests/test_onboarding_state.py tests/test_onboarding_page.py` -> 56 passed (2026-10-29).
- Hygiene result: `python3 scripts/audit_context_hygiene.py` -> only the recorded pre-existing/other-session violations; no onboarding file appears; `python3 scripts/audit_emoji.py` -> clean.
- Browser lane result: `.venv/bin/python -m pytest -q --no-header --tb=line tests/e2e/test_onboarding_page.py` -> 1 passed, 63 live captures + `capture-results.json`.
- Manual/visual: real uvicorn app against a fresh `HUTCH_STATE_DIR`; every PNG opened by the reviewer; verdicts in `validation.json`.

## 11. Visual-validation evidence required

Path: `docs/onboarding/evidence/slice-01/` (execution directive; pointer copy under `docs/onboarding/artifacts/slice-01/`). Delivered: 63 rows (one per capture) covering empty, saved, resumed, non-Latin long request, stale, expired, damaged, newer-version, conflict, validation-error, saving, forbidden, keyboard focus order, 200 percent zoom, forced colours and reduced motion at 320x740/375x812/768x1024/1440x1000, plus OS light-preference rows proving the fixed dark theme does not invert. Every row has `state`, `viewport`, `artifact`, `verdict` (63 APPROVED / 0 NEEDS WORK), `finding`, `source_commit` (88221ef9), `reviewer`. Method: live app, opened-image verdicts before any regression tooling; Chromium/Linux-only and no real phone/screen-reader/zoom limitations recorded in the evidence README. Missing evidence = FAIL.

## 12. Acceptance criteria (binary, CP1)

- [x] `GET /onboarding` renders chrome-less at all four widths with exactly one primary action and no dashboard nav/footer (automated plus opened-image rows).
- [x] Request save survives page refresh, a second tab, and a store/server reopen; the page resumes the saved state with one polite announcement; a past `resume_expires_at` shows the explicit expired state under a fixed clock; a newer-contract record shows the newer-version state, not "damaged".
- [x] Duplicate submit is replayed; stale revision/requirements and damaged records have distinct explicit states and recovery actions; no silent overwrite and no false success; reset is refused while a current request is saved.
- [x] CSRF missing = 403; paired-phone route capability = None; no secrets in the record/page.
- [x] `/onboarding` is additive: `/`, the pinned first-run e2e suites, and existing server pages are unchanged and green.
- [x] `python3 scripts/audit_context_hygiene.py` shows no new violations from this feature (final output is the exact CP0 baseline: six pre-existing other-session findings); the frozen files (`models.py`, `pages.py`, `store.py`, `connections.py`, `security.py`, the pinned e2e file) did not grow; `app.py` grew only by the two registration lines.
- [x] Evidence bundle APPROVED for every required state/viewport (63 rows); docs updated; reviewer sign-off recorded in section 15.

## 13. Rollback plan

Change shape: one new route module + one new template + one new stylesheet + one small enhancement script + three new modules (`onboarding.py`, `onboarding_store.py`, `onboarding_api.py`) + two registration lines + three base-template blocks + tests. No migration, no data rewrite, no existing route behaviour changed.
1. Remove the two-line install in `app.py` (or revert the commit) -> `/onboarding` disappears; `app.py` returns below baseline; import removed.
2. Revert `base.html` to the pre-slice version (or leave the block additions: they are default-true and inert without the onboarding template; leaving them is not a behaviour change but must be reviewed).
3. Delete/ignore the new template, CSS, JS and modules; no other surface imports them.
4. Leave the `onboarding:setup:v1` kv value in the user's state dir: it is inert without routes and must never be deleted from application code as part of a code rollback. If a future run needs it, slice 02+ reads it.
5. Verify rollback: `/onboarding` 404, `/` first-run unchanged, pinned e2e suite green, audit unchanged, no migration/SCHEMA_VERSION delta.
Risk: other-session uncommitted work in `base.html`/`app.py` can make a mechanical revert conflict. Rebase/coordinate first; rollback must be a targeted patch, never `git checkout` of those files.

## 14. Risks / open questions

- `base.html` is dirty with another session's brand work: the chrome/head blocks must be additive and default-true; coordinate before editing.
- Exact `app.py` anchor lines drift; only the registration lines may be added (headroom exists).
- The interim "Continue to AI service" target `/#/connections` is a deliberate temporary bridge; it must be flagged in code with a one-line comment and replaced in slice 02. Do not ship this slice as the new first-run entry point.
- Server-rendered page does not load SPA CSS; the visual gate must confirm parity expectations for this isolated route and record that it intentionally does not reuse `studio.css`.
- If `Store.kv_set` is called concurrently by two processes (not expected: one Hutch server per state dir), the process lock does not protect across processes; record as a documented limitation and keep multi-process support out of scope.
## 15. Acceptance record (CP1)

Status: PASS. Date: 2026-10-29. Owner: Lead implementation. Independent reviewer:
fresh-context read-only review (findings resolved below); planning reviewer:
independent review 2026-10-29 (task-plan section 9).

Delivered anchors:

- `@src/hutch/onboarding.py:1-241` - pure domain (constants, `OnboardingSetup`, `SetupRecord`, `EditResult`, `ResumeView`, `default_setup`, `parse_setup`, `encode_setup`, `apply_request_edit`, `resume_view`, `empty_view`).
- `@src/hutch/onboarding_store.py:1-74` - `SETUP_KEY`, module lock, `load_setup`, `save_request`, `reset_setup`.
- `@src/hutch/server/onboarding_api.py:1-280` - `install_onboarding_routes`, module-level render/forbidden/handlers, explicit state constants, `_reset_allowed`.
- `@src/hutch/server/templates/onboarding.html` + `_onboarding_request_form.html`, `_onboarding_request_text.html`, `_onboarding_reset_form.html`, `_onboarding_start_over.html`.
- `@src/hutch/server/static/onboarding.css` (389 lines), `onboarding-form.css` (103), `onboarding.js` (81).
- `@src/hutch/server/app.py:7245-7248` - exactly two registration lines; `@src/hutch/server/templates/base.html` - default-true chrome flag + head block.
- Tests: `@tests/test_onboarding_state.py` (338 lines), `@tests/test_onboarding_page.py` (344 lines), `@tests/e2e/test_onboarding_page.py` (344 lines).

Commands and exact results:

```
.venv/bin/python -m pytest -q --no-header --tb=line tests/test_onboarding_state.py tests/test_onboarding_page.py
  -> 56 passed
.venv/bin/python -m pytest -q --no-header --tb=line tests/e2e/test_onboarding_page.py
  -> 1 passed (63 PNGs + capture-results.json)
python3 scripts/audit_context_hygiene.py
  -> only the registered pre-existing/other-session violations; none of this slice
python3 scripts/audit_emoji.py
  -> clean
```

Visual evidence: `docs/onboarding/evidence/slice-01/` - 63 opened-image rows, all
APPROVED (see the evidence README); canonical `validation.json` there with the
identical pointer copy under `docs/onboarding/artifacts/slice-01/`. Browser:
Chromium 153.0.8010.12 headless on Linux; limitations recorded (no real phone,
screen reader, browser zoom, Firefox/WebKit, or OS forced-colours setting).

Independent-review findings and resolutions:

| Finding | Resolution |
|---|---|
| P1: CP1 claimed a `validation.json` and acceptance record that did not exist yet | Both now exist: 63-row `validation.json` (canonical + pointer copy) and this section; claims were only kept after the artefacts landed. |
| P1: capture coverage missed the required state/width pairs | The live lane was extended to 63 rows: every required state at 320/375/768/1440, forced colours and reduced motion at all four widths, reduced-motion saved rows, and a distinct non-Latin-long-request row; all 63 images were opened again. |
| P2: setup-record contract named Start over as primary for damaged/newer states | Contract updated to the shipped hierarchy: safe dashboard exit primary, destructive Start over secondary (consistent with the page and design-system note). |
| P2: `POST /onboarding/reset` accepted a reset from any state | Reset is now state-gated server-side (409 `setup.reset_blocked`); page tests cover both the refused current-record case and the allowed expired-record case. |
| P2: installer was a 71-line function mixing wiring and handlers | Refactored to module-level `_render`, `_forbidden`, `_fields_for_page`, `_page_response`, `_request_response`, `_unsaved_response`, `_reset_response`; `install_onboarding_routes` is now wiring only. |
| P2: resume announcement/focus was untested and a pre-populated live region is not reliably announced | Resume now starts as an empty hidden live region filled once after load (noscript copy keeps it readable); the e2e lane asserts the one announcement and that the error summary owns focus on the invalid path. |
| P2: evidence-path drift between brief/task-plan/review-checklist and the delivered bundle | All CP1 references point at `docs/onboarding/evidence/slice-01/`; a pointer copy is kept under `artifacts/slice-01/` for the CP wording. |
| NOTE: audit baseline drift observed during the run | At final CP1 verification `python3 scripts/audit_context_hygiene.py` reports exactly the six CP0-baseline findings and no slice-01 file; an intermediate run during the slice showed concurrent other-session drift (`tests/test_connections.py`, `pages.py`) that later reverted. The final exact output is recorded in task-plan section 9b; nothing was silently re-baselined. |

Deviations from the planning brief:

1. Evidence lives in `docs/onboarding/evidence/slice-01/` (execution directive) instead of `artifacts/slice-01/`; a pointer copy satisfies the CP1 wording.
2. The planning draft named `@tests/conftest.py:18` as a client fixture; no such fixture exists, so the page tests construct `TestClient(create_app())` directly (same pattern as `tests/test_models_page.py`).
3. The shared `_form.html` macro tier is another session's uncommitted working-tree work; the page therefore ships its own small field partial + `onboarding-form.css` so the committed slice is self-contained. The visual evidence was captured against the working tree (the recorded CP0 condition).
4. The browser lane needed `meta name="referrer" content="same-origin"` because the global `Referrer-Policy: no-referrer` makes currently-shipping Chromium/Firefox send `Origin: null` on plain form POSTs; the existing same-origin guard correctly refuses that. This is a pre-existing, already-recorded boundary (`tests/e2e/test_route_state_boundaries.py`); the broader fix belongs to the security surface owner. No middleware was weakened.
5. Damaged/newer-version states use the safe dashboard exit as the visual primary and the destructive reset as a secondary button (reviewed decision, not a disabled-control substitute).

Reviewer sign-off: CP1 PASS after the findings above were resolved and the full
matrix was re-captured and re-opened. The slice is committed in
`c7087d3f`, `b3293553`, `88221ef9`, `945500cf` plus the CP1 docs commit.

Next: slice 02 (first-run handoff + AI-service chooser) - brief refreshed and
[continuation prompt](../continuation-prompt-02.md) written; slice-03/04 briefs are
still owed before CP2 can pass.