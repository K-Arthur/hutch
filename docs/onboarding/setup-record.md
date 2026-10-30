# Slice 01 - setup record and request-step contract

Status: implementation contract for slice 01 (2026-10-29). Companion to
[the slice brief](slices/slice-01.md) and [the task plan](task-plan.md). This
document is normative for the domain module, persistence adapter, HTTP routes,
template context, and canonical state tokens used by the browser tests.

## 1. Purpose and boundaries

The setup record is the server-owned source of truth for onboarding progress.
The browser is a cache only. Slice 01 stores exactly one record per installation
in the existing kv table and exposes one request step. It makes no provider or
network call, adds no migration, and no browser draft is read or written.

Boundaries: `src/hutch/onboarding.py` is pure (no FastAPI, templates, store,
filesystem, network imports). `src/hutch/onboarding_store.py` owns
persistence and the process lock. `src/hutch/server/onboarding_api.py` owns
HTTP orchestration and rendering only. Provider probes, keys, terms, and the
chooser are later slices and must not appear here.

## 2. Kv record

- Key: `onboarding:setup:v1` in the existing `kv` table via
  `store.kv_get` / `store.kv_set` (no new table, no schema change).
- Value: compact JSON, `json.dumps(..., sort_keys=True, separators=(",", ":"))`.
- No secrets, tokens, provider keys, or filesystem paths are stored.

Fields of `OnboardingSetup` (`src/hutch/onboarding.py`, pydantic, extra
fields ignored so later slices can add route data):

| Field | Type | Rule |
|---|---|---|
| `contract_version` | int | record schema version; a newer number is parseable and surfaces as stale/newer-version, never damaged |
| `revision` | int >= 0 | optimistic-concurrency revision, incremented only on an actual content or recovery write |
| `step` | str | one of `STEP_ORDER`; an unknown step is a stale-resume reason, not corruption |
| `request_text` | str | outer whitespace stripped; 1-20,000 chars after trim when saved |
| `requirements_version` | int | flow/requirement registry version; a mismatch is stale |
| `resume_expires_at` | ISO-8601 UTC str | TTL end; default 30 days, refreshed on every accepted save |
| `created_at` | ISO-8601 UTC str | first write |
| `updated_at` | ISO-8601 UTC str | last accepted write |
| `route_kind` | str | slice 02: `""` until a route is chosen; one of `ROUTE_KINDS`; an unknown stored value is an explicit stale reason, never damage |
| `route_chosen_at` | ISO-8601 UTC str | slice 02: set with `route_kind` on a deliberate choice; `""` otherwise; metadata only, not a resume gate |

`ONBOARDING_CONTRACT_VERSION = 1`, `ONBOARDING_REQUIREMENTS_VERSION = 1`,
`REQUEST_MAX_CHARS = 20000`, `RESUME_TTL = timedelta(days=30)`,
`STEP_ORDER = ("request", "ai_service", "connection", "assistant", "first_request")`,
`REQUIRED_STEPS = STEP_ORDER`, `OPTIONAL_STEPS = ()`.

## 3. Domain module API (`src/hutch/onboarding.py`)

Pure functions and dataclasses; expected outcomes are returned, never raised.

```python
default_setup(now: datetime) -> OnboardingSetup
parse_setup(raw: Optional[str]) -> SetupRecord        # kind: absent | present | damaged
encode_setup(setup: OnboardingSetup) -> str
apply_request_edit(setup, *, expected_revision: int, request_text: str,
                   now: datetime,
                   requirements_version: int = ONBOARDING_REQUIREMENTS_VERSION,
                   contract_version: int = ONBOARDING_CONTRACT_VERSION) -> EditResult
resume_view(setup, *, now: datetime,
            active_requirements_version: int = ONBOARDING_REQUIREMENTS_VERSION,
            active_contract_version: int = ONBOARDING_CONTRACT_VERSION) -> ResumeView
empty_view() -> ResumeView
```

`EditResult(kind, setup, reason)` kinds:

- `accepted`: persist `setup`. Revision = previous + 1 (0 -> 1 on a fresh
  record), `updated_at = now`, `resume_expires_at = now + RESUME_TTL`,
  `requirements_version` = active version, `step` stays valid.
- `replayed`: no write. Submitted content equals the current stored content on
  a current record; this is the duplicate-submission guard.
- `stale`: no write; `setup` is the current saved record. Raised when the
  submitted content differs and `expected_revision != setup.revision`.
- `invalid`: no write; `reason` is user-facing and names the fix. Empty after
  trim, over `REQUEST_MAX_CHARS`, negative `expected_revision`.

An identical resubmit that arrives for an expired or stale-record-version
record is an intentional recovery: `accepted` with a refreshed TTL and current
versions (revision + 1), not `replayed`.

`ResumeView` fields: `state` (`setup.empty_no_route`,
`setup.resume.current`, `setup.resume.stale`, `setup.resume.expired`),
`step`, `step_index` (1-based), `required_total`, `request_text`,
`revision`, `saved_at`, `stale`, `stale_reasons: tuple[str, ...]`,
`expired`, `newer_version`, `resume_expires_at`.

Implementation decisions after the domain tests (additive; no contract semantics changed):

- An accepted recovery (identical text on an expired or version-stale record)
  also refreshes `contract_version` to the active version and maps an unknown
  step back to `request`, so the persisted record is fully current afterwards,
  not just re-stamped.
- `invalid` results carry the current setup so the HTTP layer can render the
  preserved form without a second read. Nothing is written.
- `resume_view.expired` reports the raw TTL check even when `state` is stale;
  pages must select the state from `view.state` (precedence stale > expired >
  empty > current), not from the boolean alone.
- `parse_setup` treats every field except `contract_version` as required;
  missing fields are damaged. A newer `contract_version` and an unknown step
  parse as present so they can surface as explicit stale states.

Stale reason codes (machine tokens; the page maps them to copy):
`newer_contract` (record contract_version > active), `contract_version`
(older), `requirements_version`, `unknown_step`. Expiry uses `now >=
resume_expires_at` and is evaluated before request presence; stale is evaluated
before expired. A newer contract version sets `newer_version=True` and the
page renders the dedicated newer-version state, not "damaged".

Stored timestamps must parse as ISO-8601 with an explicit offset; a record that
fails JSON/model/timestamp validation is `damaged`.

## 4. Persistence adapter (`src/hutch/onboarding_store.py`)

`SETUP_KEY = "onboarding:setup:v1"`, one module-level `threading.Lock()`, lock
held across read-check-write. The lock is process-local; one Hutch server per
state directory is the supported model and multi-process writers are documented
out of scope.

```python
load_setup(store) -> SetupLoad                       # kind: absent | present | damaged
save_request(store, *, expected_revision: int, request_text: str,
             now: datetime) -> SaveResult
reset_setup(store, now: datetime) -> OnboardingSetup  # fresh default, revision 0
```

`SaveResult` kinds: `accepted`, `replayed`, `stale`, `invalid`,
`damaged`, `newer_version`. `damaged` and `newer_version` are decided by
the adapter before `apply_request_edit`; neither writes. `reset_setup` writes
a fresh default record (revision 0) rather than deleting the key, so reloads
are deterministic.

## 5. HTTP contract (`src/hutch/server/onboarding_api.py`)

Installed by two lines in `@src/hutch/server/app.py:7243-7248` next to
`register_pages(app)`. The existing route loop records every route with a
`None` capability, so paired phones are refused by the existing middleware.
No `next` parameter and no user-controlled redirect target.

`GET /onboarding` -> 200 text/html, owner session. Optional `?edit=1`
renders the editable form for a saved/resumed record.

`POST /onboarding/request` (application/x-www-form-urlencoded): `csrf`
(required), `revision` (required integer), `request` (required string).

- 303 `Location: /onboarding` for `accepted` ("Saved on this machine.") and
  `replayed` ("Already saved - nothing changed."); notice uses the existing
  `hutch_flash` cookie pattern (`quote`, max_age 15, SameSite=Strict).
- 409 text/html for `stale` (explicit conflict; both saved and submitted text
  are rendered, nothing is overwritten), `newer_version`, and `damaged`.
- 422 text/html for empty/over-limit text and non-integer revision; the
  submitted value is preserved and the error summary is focused.
- 403 text/html for missing/invalid CSRF with `auth.csrf_rejected` copy; the
  submitted text is preserved. `check_csrf` from
  `@src/hutch/server/security.py:506-509` remains the only gate.

`POST /onboarding/reset` { `csrf` } -> 303 `/onboarding` ("Started over:
the saved setup was replaced with a blank one."); 403 on invalid CSRF; 409
`setup.reset_blocked` when a current, usable saved request exists. Reset is a
server-gated recovery action: it is allowed only when the record is absent/blank,
damaged, or resumes as stale/expired/newer-version, so a stray CSRF-valid POST
cannot wipe usable state. The page only renders the reset control from those
states; the server enforces the same rule.

Record example:
`{"contract_version":1,"created_at":"2026-10-29T18:00:00+00:00","request_text":"...","requirements_version":1,"resume_expires_at":"2026-11-28T18:00:00+00:00","revision":1,"step":"request","updated_at":"2026-10-29T18:00:00+00:00"}`

## 6. Template context and state tokens

`templates/onboarding.html` extends `base.html` with `chrome=False`,
`nav=""`. Base gains `{% block head %}` and the header/footer are gated by
`{% if chrome|default(true) %}`; every existing page is unchanged because the
default is true. The page joins the existing skip link / `<main id="main">`.

Canonical `data-onboarding-state` values and their triggers:

| Token | Trigger | Primary action |
|---|---|---|
| `setup.empty_no_route` | no record, or a blank record | Save and continue (form) |
| `setup.draft.saved` | accepted save redirect (flash notice present) | Continue to AI service (temporary `/#/connections`) |
| `setup.resume.current` | current record loaded on GET | Continue to AI service, Edit request |
| `setup.resume.stale` + `newer_version=false` | older contract/requirements or unknown step | Use my request and continue (re-save) |
| `setup.resume.stale` + `newer_version=true` | record contract_version newer than this code | Back to the dashboard; destructive Start over is a secondary button |
| `setup.resume.expired` | now >= resume_expires_at | Continue to refresh this setup (re-save) |
| `setup.conflict` | stale revision with different text | Review latest saved setup |
| `setup.damaged` | unreadable stored record | Back to the dashboard; destructive Start over is a secondary button |
| `setup.reset_blocked` | CSRF-valid reset POST while a current request is saved | Back to the saved setup (409) |
| `input.invalid` | empty/over-limit/invalid revision | Save and continue (form, error focused) |
| `auth.csrf_rejected` | missing/invalid CSRF | Reload the page (link to /onboarding) |

Template variables (all supplied by `onboarding_api.py`):
`state`, `request_text`, `revision`, `editable` (bool), `field_error`,
`error_summary`, `resume_message`, `saved_at_local`,
`conflict_saved_text`, `stale_reasons` (list of user-facing strings),
`newer_version` (bool), `continue_target` (`/#/connections`, temporary and
marked in the template), `notice`, `error`, `csrf`, `version`,
`state_dir`, `request`, `chrome=False`, `nav=""`, `step_label`,
`step_index`, `step_total`.

Copy rules: "saved" is never "connected"/"verified"; required vs optional is
stated in words; no account/signup/download claim; no celebration screen; no
emoji; no fake checklist. The page states what is stored on this machine and
links the request model honestly.

## 7. Accessibility and resilience requirements

- One `h1`; one visible primary action per state; the primary action is in
  normal document flow (no fixed footer).
- The resumed step renders one `role="status" aria-live="polite"` region that
  starts empty and hidden; `onboarding.js` fills it once after load so screen
  readers announce the resume once (a pre-populated live region is not reliably
  announced on initial load). A `<noscript>` copy keeps the sentence visible
  without JavaScript. The flash notice announces a save result once; the error
  summary is `role="alert"`, `tabindex="-1"`, focused by `onboarding.js` when
  present, with one link per field and inline adjacent error text (never
  colour-only).
- Plain form POST works without JavaScript. `onboarding.js` sets `aria-busy` and
  the "Saving..." status on submit and disables the submit buttons on the next
  task (disabling the submitter synchronously inside the submit event cancels the
  POST), restores on `pageshow`, and moves focus to the error summary.
- Works at 320/375/768/1440, 200 percent text zoom, forced colours, reduced
  motion; no horizontal overflow; fixed dark theme only.
- No network/provider request, no telemetry, no external asset.

## 8. Runbook and rollback

Inspect the record (read-only):
`sqlite3 "$HUTCH_STATE_DIR/hutch.db" "select value from kv where key='onboarding:setup:v1';"`
Reset through the product: `POST /onboarding/reset` from the damaged/stale/
expired/newer-version state (CSRF-checked, state-gated 409 otherwise). Do not
delete the kv row from application code; a code rollback leaves it inert.

Rollback: remove the two registration lines in `app.py`, revert the additive
`base.html` head/chrome blocks (or leave them: default-true and inert), and
delete the new modules/template/CSS/JS/tests. The kv record is inert without
the routes and must be kept. Verify `/onboarding` returns 404, `/` and the
pinned first-run e2e tests are unchanged, `python3 scripts/audit_context_hygiene.py`
shows no new violation, and no migration/SCHEMA_VERSION delta exists.

## 9. Slice 02 extension - the AI-service chooser

Status: implemented contract for slice 02 (2026-10-29); companion to
[the slice-02 brief](slices/slice-02.md) and [the edge-case matrix](edge-case-matrix.md).
Sections 1-8 remain normative for the request step; this section extends them
without changing the stored record's key or the request-step semantics.

### 9.1 Record delta

Two fields are added to `OnboardingSetup`; both default to `""` and neither is
required, so a slice-01 record parses unchanged and a slice-02 record is readable
by slice-01 code (`extra="ignore"`, and `step="ai_service"` is a known step):

| Field | Type | Rule |
|---|---|---|
| `route_kind` | str | `""` until a route is chosen; otherwise one of `hosted_key`, `local_service`, `opencode`. Unknown stored values are a stale reason, never "damaged". |
| `route_chosen_at` | ISO-8601 UTC str | Set with `route_kind` on a deliberate choice; `""` otherwise. Display metadata only; it is not re-validated as a resume gate. |

An accepted choice writes exactly one revision bump: `revision + 1`,
`step="ai_service"`, `route_kind`, `route_chosen_at=now`, `updated_at=now`,
`resume_expires_at=now+RESUME_TTL`, and the active requirements/contract
versions. `request_text` is never changed by a choice. A request edit after a
choice keeps both route fields (model copy) and keeps the ai_service step.

### 9.2 Pure chooser domain (`src/hutch/onboarding_choices.py`)

No I/O, no FastAPI, no store/templates/network imports. Constants:
`ROUTE_KINDS = ("hosted_key", "local_service", "opencode")`, `ROUTE_LABELS`,
`ROUTE_DESCRIPTIONS`, `RECOMMENDED_ROUTE = "hosted_key"`,
`RECOMMENDED_QUALIFIER = "Recommended only if you already have a provider key"`.
The recommendation is static and explicitly qualified; slice 03 replaces it with
a detected/verified route and must update this copy, not duplicate it.

```python
route_options() -> tuple[RouteOption, ...]        # exactly three, one recommended
chooser_ready(setup) -> bool                      # a saved request exists
chooser_view(setup, *, now, active_requirements_version=..., active_contract_version=...) -> ChooserView
choose_route(setup, *, expected_revision, route_kind, now, ...) -> ChooseResult
```

`ChooserView` fields: `state`, `options`, `recommended`,
`recommended_qualifier`, `selected_route` (None when no/unknown route),
`selected_label`, `request_text`, `revision`, `step_index`,
`required_total`, `can_choose`, `stale`, `stale_reasons`, `expired`,
`newer_version`. `ChooseResult` kinds: `chosen`, `replayed`, `conflict`,
`stale`, `invalid`, `no_request`.

State precedence in `chooser_view`: `no_request` (blank request) > `stale`
(version/requirements/step drift, expiry, newer contract, or a stored route no
longer in the allowlist) > `chosen` (valid stored route) > `choose`. Stale
reason tokens are the four slice-01 tokens plus `route_removed` and
`expired`. `can_choose` is true for `choose`, and for a `route_removed`
stale record (re-choice permitted); version/expiry drift sets it false and the
page points at the request step instead.

`choose_route` semantics: unknown/blank route or negative revision -> `invalid`;
no saved request -> `no_request`; version/requirements/expiry drift -> `stale`
(no write, current record returned); same route on a current record -> `replayed`
(no write, even from a duplicate submit's stale revision); a different route on
the current revision -> `chosen`; a different route from a stale revision ->
`conflict` carrying the current record.

Canonical `data-onboarding-state` tokens added by this slice:
`setup.ai_service.choose`, `setup.ai_service.chosen`,
`setup.ai_service.stale`, `setup.ai_service.invalid`,
`setup.ai_service.conflict`, `setup.ai_service.no_request`. The forbidden
state keeps the shared `auth.csrf_rejected` token.

### 9.3 Persistence (`src/hutch/onboarding_store.py`)

`save_route(store, *, expected_revision, route_kind, now) -> SaveResult` holds
the same process lock as `save_request`/`reset_setup`, so a request edit in one
tab and a route choice in another cannot both win the same revision. The adapter
decides `damaged` and `newer_version` before the domain decision and writes on
neither; other kinds pass through from `choose_route` (`chosen` persists the
returned record; `replayed`, `conflict`, `stale`, `invalid` write nothing).
`no_request` is returned when no setup record with a request exists.

### 9.4 HTTP contract

`GET /onboarding/ai-service` -> 200 text/html (owner session) with one of the
chooser states above. `?change=1` renders the choice form with the saved route
preselected. 303 `Location: /onboarding` with an error flash
("Write your request first.") when the record has no saved request; 303 to
`/onboarding` with an error flash when the record is damaged (the request step
owns that recovery). 403 for a paired-phone session via the existing route
capability middleware.

`POST /onboarding/ai-service/choose` (application/x-www-form-urlencoded):
`csrf` (required), `revision` (required integer), `route_kind` (required,
server-side allowlist `hosted_key|local_service|opencode`).

- 303 `Location: /onboarding/ai-service` for `chosen` ("Route selected.") and
  `replayed` ("Route already selected - nothing changed."); flash uses the
  existing one-shot cookie pattern.
- 409 text/html for `conflict` (explicit "This setup changed in another
  window" with both route labels and "Review latest saved setup"), and for
  `stale`/`newer_version` (explicit stale state with the kept request).
- 422 text/html for missing/unknown `route_kind` and malformed revision, with a
  focused `role="alert"` error summary and the submitted selection preserved.
- 403 text/html for missing/invalid CSRF with `auth.csrf_rejected`, nothing
  written, submitted selection preserved.
- 303 to `/onboarding` with an error flash for `no_request` or a `damaged`
  record. No route redirects to a user-supplied target. Both routes are recorded
  with a `None` capability, so paired phones are refused.

### 9.5 Chooser template contract

`templates/onboarding_ai_service.html` extends `base.html` with
`chrome=False`, `nav=""`, the same `<meta name="referrer" content="same-origin">`
opt-in as the request step (the global no-referrer policy would otherwise make
the browser submit with `Origin: null` and the same-origin guard correctly
refuse it), and loads `onboarding-form.css`, `onboarding.css`,
`onboarding-chooser.css` and `onboarding.js`. The route cards are a
`<fieldset>` of three real radio inputs wrapped in labels, so the whole card is
the hit target and the form still works with JavaScript disabled.

Template variables: `state`, `options`, `recommended`,
`recommended_qualifier`, `selected_route`, `selected_label`,
`submitted_route`, `request_text`, `revision`, `step_index`, `step_total`,
`step_label` ("AI service"), `can_choose`, `stale_reasons` (user-facing
strings), `newer_version`, `expired`, `changing`, `conflict_saved_label`,
`conflict_submitted_label`, `continue_target` (chosen state; the interim
`/#/connections` bridge marked TEMPORARY until slices 04-06),
`error_summary`, `field_error`, plus the shared base fields.

Shared rendering helpers moved from `onboarding_api.py` to
`src/hutch/server/onboarding_pagekit.py` (`flash`, `local_clock`,
`redirect`, `form_values`, `revision`, `render`). Contract for both step
modules: any variable a template reads must be supplied by the step's fields or
by the pagekit context; the live lane caught (and now covers) a missing
`continue_target` that rendered an empty primary href.

### 9.6 Accessibility and resilience

On arrival the chooser focuses its `h1` (`tabindex="-1"`,
`data-focus-heading`) so a screen reader announces the step change once, unless
an error summary exists - the summary wins and receives focus instead. Selection
is never colour-only: a checked route shows the word "Selected" plus a drawn
tick, and the native radio carries its own checked state. Cards keep the 44 px
coarse-pointer floor, the focus ring stays visible, there is no fixed footer, and
the page works as a plain form POST. No animation is added; reduced motion
removes inherited transitions. The fixed dark theme stays dark under an OS light
preference, and forced-colours keeps boundaries, focus and selection legible.
No provider/localhost call is made by the page, its JavaScript, or its tests.
