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