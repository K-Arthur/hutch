# Slice 03 - Per-route readiness truth model and readiness panel states

Status: IMPLEMENTATION BRIEF (written 2026-10-29; not implemented). Acceptance gate: CP3. Planning gate: CP0 in [task-plan.md](../task-plan.md).
Depends on: CP2 (slice 02; implemented in commits 4c53c814/7140d48f and still being finalized at CP2 when this brief was written - the working tree also carries its uncommitted polish). This slice gates CP3. Its 03a contract is a blocking dependency for slice 04, which must consume it and never fork a second classifier. Owner: TBD. Reviewer: TBD. Anchors re-read 2026-10-29 on that shared working tree; another session still carries uncommitted brand work in `app.js`/`app.py`/`base.html`/templates and slice-02 polish in the onboarding files: re-read every anchor before editing; never revert, format, stage or touch another session's work.

## 0. What prior slices delivered (use these, do not re-invent)

Slice 01 ACCEPTED at CP1; slice 02 implemented (CP2 finalization in progress). Use the shipped seams and names, not the planning drafts.

- `@src/hutch/onboarding.py:21-27` constants, `:37-67` `OnboardingSetup` (`:50-55` `route_kind`/`route_chosen_at`, extra fields ignored), `:106-113` `default_setup`, `:173-206` `apply_request_edit`, `:209-247` `resume_view`. Pure: no store/templates/network imports. Slice 03 adds one defaulted field here (03c).
- `@src/hutch/onboarding_choices.py:1-221`: `ROUTE_KINDS` `:29`, chooser states `:52-57`, `chooser_view` `:145-168`, `choose_route` `:186-221`. Slice 03 reads `route_kind` through this module; do not duplicate route labels.
- `@src/hutch/onboarding_store.py:24-27` `SETUP_KEY` + process lock, `:47-50` `load_setup`, `:53-67` `save_request`, `:70-92` `save_route` (same lock/revision pattern slice 04 extends). 100 lines now.
- `@src/hutch/server/onboarding_pagekit.py:1-86` (new in slice 02): `flash` `:29-32`, `local_clock` `:35-39`, `redirect` `:43-50`, `form_values` `:53-56`, `revision` `:59-65`, `render` `:68-86` (no-store, chrome-less context, template override). Slice 03 extends this module with a bounded `fragment()` helper instead of adding a second render helper.
- `@src/hutch/server/onboarding_api.py:1-230` (shrunk from 279 in slice 01): `CONTINUE_TARGET = "/onboarding/ai-service"` `:37-38`, state constants `:40-49`, `install_onboarding_routes` `:213-230` ending with `install_chooser_routes(...)` at `:230`.
- Slice 02 seams: `@src/hutch/server/onboarding_chooser_api.py:1-193` (`CONTINUE_TARGET = "/#/connections"` is marked TEMPORARY at `:46-47`; `install_chooser_routes` `:184-193`), `@src/hutch/server/templates/onboarding_ai_service.html:5-32` (head block; chosen-state CTA at `:32`), updated `@src/hutch/server/templates/onboarding.html:170` lines (head `:5-15`, continue CTA `:34`), `@src/hutch/server/static/onboarding.js:114` lines (:64-114 submit/pageshow/draft/focus wiring), `onboarding-chooser.css` (216 lines). Server-side: `@src/hutch/server/templates/base.html:35` loads htmx 2.0.4, `:42` head block, `:44` CSRF in `hx-headers`; `@src/hutch/server/security.py:506-509` `check_csrf`, `:314-318` same-origin; `@src/hutch/server/app.py:7251-7252` onboarding install, `:7256-7261` records every new route with `None` capability.
- Readiness inputs: `@src/hutch/providers/connection.py:11-39` `provider_for_connection`, `:42-69` `ConnectionCheck`/`check_connection` (metadata probe; **`verified` is true on a model-list success and is discarded, never rendered**); `@src/hutch/providers/base.py:26-61` `ProviderError.KINDS` + `retryable`, `:67-87` `ChatRequest`, `:324-368` `Provider.chat`/`list_models`; `@src/hutch/providers/openai_compat.py:97-129` HTTP->kind mapping (401/403, 402/quota, 429+Retry-After, 408 via `_wrap_exc` `:131-142`), `:157-216` `probe_models`, `:218-227` typed `list_models`; `@src/hutch/providers/claude.py:158-195`, `@src/hutch/providers/ollama.py:180-192`, `@src/hutch/providers/openai_responses.py:158-176`.
- Test/evidence conventions: `@tests/test_onboarding_chooser.py:34-75` fixture/seed/csrf pattern, `@tests/test_onboarding_chooser_state.py`, `@tests/e2e/test_onboarding_chooser.py:1-30` live-capture scaffold, `@tests/e2e/test_onboarding_page.py:32-60` viewports/evidence dir, `@tests/support/browser.py:1-30`, `@tests/fakes.py:31-121` threaded fake-server pattern (frozen - copy the pattern into a new file, do not grow it). Evidence lives under `docs/onboarding/evidence/slice-03/` (execution directive), pointer under `artifacts/slice-03/`.

## 1. User outcome (one sentence)

Every route on the onboarding connection step shows exactly why it is or is not usable - checking, saved-unverified, verified, invalid credential, permission denied, no credit, rate-limited with a capped wait, timed out, unavailable, unreachable, invalid route, missing model, or context/incomplete - each with one specific next action (retry, explicit test generation, or switch route), while the browser never contacts a provider and stale "saved" data is revalidated instead of trusted.

Not in this slice: hosted-key or local-service forms (04/05), external-login waiting/cancel (06), assistant create/first request (07/08), full-flow keyboard/screen-reader/offline gate (09), pairing (10), marketing site (11). The route-form area in the connection shell is an explicitly temporary bridge until 04-06 add their partials.

## 2. Primary task per step

### 03a - Pure readiness contract (`ProbeResult` + classifier + policy)
Files/new functions:
- `@src/hutch/route_readiness.py` (new; pure: no FastAPI/store/templates/filesystem/network imports; aim <=180 lines, hard cap 400):
  - constants `MODE_METADATA="metadata"`, `MODE_GENERATION="generation"`; `PROBE_DEADLINE_SECONDS=20`; `SNAPSHOT_TTL_SECONDS=600`; `RETRY_AFTER_CAP_SECONDS=600`; `MAX_ATTEMPTS=3`; `GENERATION_COOLDOWN_SECONDS=60`.
  - canonical states `setup.checking`, `setup.saved_unverified`, `setup.verified`, `provider.invalid_credential`, `provider.permission_denied`, `provider.no_credit`, `provider.rate_limited`, `provider.retry_scheduled`, `provider.unavailable`, `provider.timed_out`, `provider.unreachable`, `provider.invalid_route`, `provider.model_missing`, `provider.context_or_incomplete`; matrix aliases `route.*` are display-only and tests assert the canonical `provider.*` token (edge-case-matrix section 4).
  - `@dataclass(frozen=True)` `ProbeResult(state, kind, http_status, retry_after, detail, models, checked_at, mode)`; `checked_at` is ISO-8601 UTC from `@src/hutch/models.py:23-28`; `models: tuple[str, ...]`; field order fixed by this brief.
  - `classify(kind, *, http_status=None, retry_after=None) -> str` mapping exactly: `unreachable->provider.unreachable`; `timeout->provider.timed_out`; `auth` + 401/null -> `provider.invalid_credential`, `auth` + 403 -> `provider.permission_denied`; `quota->provider.no_credit`; `rate_limit->provider.rate_limited`; `server|stream|oom|refused|other->provider.unavailable`; `bad_request->provider.invalid_route`; `model_missing->provider.model_missing`; `context|incomplete->provider.context_or_incomplete`; unknown kind -> `provider.unavailable` with detail, never a bare "error".
  - `metadata_result(...) -> ProbeResult` may only yield `setup.saved_unverified` on success; `generation_result(...) -> ProbeResult` is the only constructor that may yield `setup.verified`; both enforce the invariants in code, not call-site discipline.
  - `retry_allowed(state) -> bool` (rate_limited after wait, timed_out, unavailable, unreachable; never credential/permission/credit/invalid-route/model/context); `retry_in_seconds(result, now) -> int` (capped); `is_stale(result, now) -> bool`; `revalidation_required(previous, now) -> bool`.
- `@tests/test_route_readiness.py` (new): all 14 kinds with 401/403/no-status variants; unknown kind; metadata success never verified; generation success verified; no state uses the word "error"; retry table; Retry-After cap/countdown with fixed clock; TTL staleness; purity import audit.

### 03b - Typed server-side probe adapter (no browser-to-provider call)
Files/functions:
- `@src/hutch/providers/connection.py` (grow only; currently 69 lines, cap 400): keep `check_connection` `:50-69` unchanged for legacy surfaces (`@src/hutch/server/pages.py:683`, `@pages_models.py:134-135`, `@src/hutch/doctor.py:168-169`, `@src/hutch/cli.py:1428-1429`). Add `ProbeAttempt(outcome, detail, models, kind, http_status, retry_after)` and `probe_connection_typed(book, name, *, mode=MODE_METADATA, model="")`:
  - metadata: `provider_for_connection` then `provider.probe_models()`; on failure recover the typed error with `provider.list_models()` (ProviderError kind/status/retry_after); map transport exceptions to unreachable/timeout/stream; special-case the OpenRouter public-catalog gap (a failed authenticated `/key` check must not read as success: rejected key -> invalid_credential, management/provisioning key -> permission_denied, other -> unavailable); missing key from `provider_for_connection` is `auth` -> invalid_credential. Routes with `models_endpoint=False` or `auth_type != "api_key"` return outcome `unverifiable` -> saved_unverified with an honest detail (do not claim verification).
  - generation: only on explicit owner request, one attempt, no hidden retry; build `ChatRequest(model=model, messages=[{"role":"user","content":"Reply with the word ready."}], stream=False, max_tokens=1, temperature=0, session_id="onboarding-readiness")` and call `Provider.chat`; catch `ProviderError`; no tools, no bot, no conversation; copy must say it may use a small amount of provider credit.
  - never return, log or store the key; callers redact with `book.key(name)`.
- `@tests/support/fake_provider.py` (new <=200; own scripted HTTP server modelled on `tests/fakes.py`, do not modify fakes.py): scenarios 200 models + 401 generation, 402, 408, 429 + `Retry-After: 120`, 503 with a long multi-line message body, unreachable (closed port), slow (delayed) and hung (accepts, never answers); records requests so tests can prove the server, not the browser, called it.
- `@tests/test_readiness_probe.py` (new <=400): typed mapping table through real providers against the fake server; metadata 200/generation 401 -> saved_unverified then invalid_credential; no metadata path yields verified; unreachable/timeout mapping; long error kept verbatim (bounded <=500 chars) and redacted.

### 03c - Readiness routes, panel fragment and connection-step shell
Files/functions:
- `@src/hutch/server/onboarding_readiness_api.py` (new bounded module mirroring `onboarding_chooser_api.py`; aim <=320, hard cap 400): `install_readiness_routes(app, *, store, config, templates)`; module-level snapshot registry (wrapper holds `ProbeResult`, attempt number, running flag) + lock; `start_probe(...)` launches one daemon thread per target/attempt and refuses a second while running; `resolve_target(book, setup, query_target)` allows only `book.names()` (no user-supplied URL/host/redirect). Reuse `onboarding_pagekit.render` `:68-86` for the full page and add one bounded `fragment()` helper to `@src/hutch/server/onboarding_pagekit.py` (same no-store/flash/CSRF context, no second render stack).
- Routes: `GET /onboarding/readiness?target=<connection>` returns `_onboarding_readiness.html` only (HTTP fragment); starts a metadata probe only when there is no fresh snapshot (TTL above) and shows `setup.checking`; `POST /onboarding/readiness/retry` (CSRF; allowed only per `retry_allowed` and only after the capped countdown; 409 with the wait copy otherwise); `POST /onboarding/readiness/verify` (CSRF; explicit generation probe only; 60 s per-connection cooldown; 409 on repeat); `GET /onboarding/connection` renders the step shell.
- Snapshots are process-local and never persisted (no secret or provider text in SQLite/kv); a restart or stale snapshot forces revalidation. Detail is redacted with the stored key before it is kept or rendered (mirror `@src/hutch/server/app.py:7089-7095`), bounded to 500 chars, rendered as text (Jinja autoescape), with a copyable expandable block for long 503s.
- `@src/hutch/onboarding.py`: add one defaulted field `connection_name: str = ""` (`:37-67` model; extra fields remain ignored; `default_setup` `:106-113` leaves it blank) so the shell can resume the connection it is about; slice 04 writes it. No `onboarding_store.py` change in this slice.
- `@src/hutch/server/onboarding_api.py:213-230`: add exactly two lines after `install_chooser_routes(...)` `:230` (import + `install_readiness_routes(...)`). Replace the chooser's TEMPORARY bridge in one focused edit: `@src/hutch/server/onboarding_chooser_api.py:46-47` `CONTINUE_TARGET = "/onboarding/connection"` and the CTA label at `@src/hutch/server/templates/onboarding_ai_service.html:32` "Continue to connect this route". Do not grow `onboarding_api.py` otherwise.
- Templates: `_onboarding_readiness.html` (new fragment; `hx-get` + `hx-trigger="every 1s"` only while `setup.checking`, terminal states drop polling so silent ticks stop; one polite `role="status"` region whose text changes only on a state transition; after 10 s show a "still waiting - Hutch stops after 20 s" note and after 20 s render `provider.timed_out`; real `<form method="post">` Retry / Verify / Switch actions so the panel works without JavaScript); `onboarding_connection.html` (new; extends base chrome-less, meta referrer same-origin, head block links readiness CSS/JS; route summary from the setup record; includes `{% include "_onboarding_route_" ~ route_kind ~ ".html" ignore missing %}` and a flagged TEMPORARY fallback when the route form is not built yet - replaced by slices 04/05/06 partials, never a dead end).
- Client shell: `@src/hutch/server/static/onboarding-readiness.js` (new <=180; loaded by the connection shell and, by two added head-block lines, `@templates/onboarding.html:5-15` and `@templates/onboarding_ai_service.html:5-13`): owns `net.offline` (browser offline; steps and text kept; local route stays usable; no provider check), `server.unreachable` (same-origin fetch or `htmx:sendError` fails while online; banner + Retry that reloads), `net.flaky_retrying` (attempt N of 2 with backoff for the polling GET only; never reports provider wording); suppresses duplicate announcements on unchanged polls and never auto-advances. This is the EC-06 client-shell owner handoff: present and tested here, gated across the flow in slice 09/CP6.
- CSS: `@src/hutch/server/static/onboarding-readiness.css` (new <=220; state not colour-only, long text wraps with no horizontal overflow, forced-colours and reduced-motion blocks, 44 px coarse-pointer actions). Do not grow `onboarding.css` (388 lines) or `onboarding-chooser.css` (216).
- Tests: `@tests/test_onboarding_readiness.py` (new <=400): route capability `None` for GET and every POST; CSRF 403; unknown/foreign target refused without any provider request; state lifecycle with fake fixtures; 401/402/403/408/429/503/unreachable/slow-hung mapping to the exact tokens; `Retry-After` countdown then retry allowed; verify cooldown; metadata never verified, generation 401 not verified; no key or provider header in fragment HTML; revalidation states; `data-readiness-state` and `data-onboarding-state` assertions.

### 03d - Revalidation, retry/switch and client-shell recovery (EC-06/EC-07)
- On `GET /onboarding/connection`: a stale setup record renders the existing `setup.resume.stale`/`setup.resume.expired` states (slice 01 semantics); a saved connection with no fresh snapshot starts a metadata revalidation and renders `setup.revalidation_required`; terminal revalidation renders `setup.revalidated_ok` (panel `setup.saved_unverified`) or `setup.revalidation_failed` (panel provider.* error). A previously shown `setup.verified` is never replayed after a key/route change; `setup.verified` requires a new generation probe.
- Retry copy: rate-limited shows the provider's wait (capped at 600 s) as `provider.retry_scheduled` with "attempt N of 3"; timed out shows the 20 s deadline; unavailable/unreachable offer Retry; invalid credential/permission/credit offer Switch route and, for credential, the hosted-key step when it exists (slice 04). Retry/switch never auto-run and never change route on the user's behalf.
- Tests: fixed-clock revalidation matrix (route removed, key revoked between sessions, snapshot TTL passed); two poll failures then success -> `net.flaky_retrying` then terminal, no duplicate probe thread; browser offline/online events and `htmx:sendError` set the shell states; no auto-advance.

### 03e - CP3 evidence, docs, acceptance record
- `@tests/e2e/test_onboarding_readiness.py` (new <=400, scaffold per `@tests/e2e/test_onboarding_chooser.py:1-30`): live app with seeded setup record + fake provider; captures under `docs/onboarding/evidence/slice-03/`; opens images and records binary verdicts; asserts browser requests never leave the app origin to a provider port and that no key appears in page content.

## 3. Boundary for this slice

- UI: server-rendered fragment + step shell + hand-written CSS/JS; htmx polling only; no SPA route and no new client state store.
- API: HTML fragment + HTML form POSTs (`303` after retry/verify; `409` for gated retries; no JSON API). No browser provider or localhost fetch.
- Provider I/O: only in `providers/connection.py` behind the shared `Provider`/`ProviderError` seam; metadata is the default, generation is explicit and one-shot.
- Authorization: every new route is local-owner-only (absent from `REMOTE_ROUTE_CAPABILITIES`, so the inventory loop records `None`; paired phones refused); every POST uses `check_csrf`; no user-controlled redirect or URL; target is a server-side connection-name allowlist.
- Persistence: one new defaulted setup-record field; readiness snapshots are process-local, never persisted, never contain secrets; no migration and no `SCHEMA_VERSION` change.
- Budgets: new source files <=400 lines (targets above); `providers/connection.py` grows within its cap; do not add lines to `models.py`, `pages.py`, `store.py`, `security.py`, `connections.py`, `app.py` or `tests/e2e/test_design_system.py`; `onboarding_api.py` +<=2 lines at 230; `onboarding_pagekit.py` +bounded helper (86 lines now); `onboarding.css` not grown.

## 4. Edge cases in scope (from [edge-case-matrix.md](../edge-case-matrix.md))

| Matrix row | Covered here as |
|---|---|
| EC-03 provider timeout/partial | `provider.timed_out` at the 20 s deadline; a long/hung fixture; first feedback under 1 s; no auto-resend and no double spend; `>10 s` estimate note. |
| EC-05 permission denied vs invalid credential | 401 -> `provider.invalid_credential`, 403/upstream policy -> `provider.permission_denied`, 402 -> `provider.no_credit`, 429 -> `provider.rate_limited`; alias `route.*` never asserted instead of canonical `provider.*`. |
| EC-06 offline/server down | Slice owns client-shell `net.offline`/`server.unreachable`/`net.flaky_retrying` + retry; slice 09 gates the whole flow. Distinct from `provider.unreachable` and `local.unreachable`. |
| EC-07 stale resume/revalidation | `setup.revalidation_required` -> `setup.revalidated_ok`/`setup.revalidation_failed`; snapshots and old verified claims never replayed; unknown/stale record states reused from slice 01. |
| EC-20 empty/loading/saving/error/blocked | Explicit `setup.checking`, terminal provider states, retry-scheduled, empty-connection and forbidden states; no generic error. |
| EC-09 locale/timezone | Deadlines/retry waits rendered as relative seconds/minutes from server UTC; no absolute wall-clock claims; no currency/price copy. |
| EC-10 non-Latin labels | Connection titles/model IDs (including CJK/accented) round-trip and wrap; no transliteration. |
| EC-16/17/18/19 (partial) | One announcement per transition, silent polls, keyboard-operable real forms, no motion-only progress; full audit is slice 09. |

Out of scope: local-service and external-login probes (05/06), any provider call from a browser, token spend by metadata checks, assistant/first-request states, pairing, marketing claims, and the legacy SPA readiness panel (`@src/hutch/server/static/app.js:3135-3255` is not modified).

## 5. Front-end states for this slice

| State token | Trigger | Must show | Primary action | Must not |
|---|---|---|---|---|
| `setup.checking` | probe started, no terminal snapshot | route name, what is being checked, 20 s deadline, polite status once | none (Cancel back) | infinite skeleton, no deadline |
| `setup.saved_unverified` | metadata probe authenticated | "Saved on this machine. The model list is reachable; Hutch has not run a generation." model count | Run a small test generation; Switch route | the word "verified"/"connected", success colour |
| `setup.verified` | explicit generation probe succeeded | generation confirmed, model used, "may have used a small amount of credit" | Continue (slice 07) / Switch route | claim ongoing model quality |
| `provider.invalid_credential` | 401 or missing key | provider rejected the credential; key can be replaced in the next step | Retry / Switch route | sign-in wording, raw exception |
| `provider.permission_denied` | 403/upstream policy | account/key refused this route; check scopes/model access/standing | Switch route / Retry | invalid-key wording |
| `provider.no_credit` | 402 | provider has no credit or quota | Switch route | retry as if transient |
| `provider.rate_limited` | 429 | rate-limited; provider asked to wait | Retry (after wait) / Switch route | immediate retry |
| `provider.retry_scheduled` | rate-limited with wait | "Retrying is available in N s (attempt N of 3)" | disabled Retry + countdown | auto provider call |
| `provider.timed_out` | deadline exceeded | did not answer within 20 s; request kept | Retry / Switch route | blame the credential |
| `provider.unavailable` | 5xx/stream/oom/refused/other | provider unavailable; long multi-line detail copyable | Retry / Switch route | clip the detail |
| `provider.unreachable` | DNS/TLS/socket | cannot reach the provider endpoint | Retry / Switch route | report as offline |
| `provider.invalid_route` | 400/bad request mapping | this route is not usable as configured | Switch route | suggest key change first |
| `provider.model_missing` | 404/model missing | the selected model is gone | Switch route / Retry | claim the key is bad |
| `provider.context_or_incomplete` | context/incomplete | context length or incomplete response | Switch route | retry as transient |
| `setup.revalidation_required`/`..._ok`/`..._failed` | resume with stale snapshot or changed route | what is kept, what is rechecked, old success not replayed | Recheck / Switch | stale success |
| `setup.empty_no_connection` | route chosen, no usable connection (TEMPORARY bridge until 04-06) | one action, no dead end | Choose a different route | fake readiness |
| `setup.blocked_external_action` | a required fix is outside Hutch (provider billing/standing/scopes or a sign-in route) | names the exact external action, the reason, and the return path | Switch route / back to Hutch | a disabled control as a substitute for the explanation |
| `net.offline` / `server.unreachable` | client shell | connection-loss banner, steps kept, Retry | Retry / Reload | provider wording, auto-advance |
| forbidden/saving | CSRF failure / POST in flight | explicit session copy; aria-busy + progress | Reload / none | raw exception, duplicate probe |

Copy rules: "saved" is never "connected"/"verified"; each error names one cause and one next action; wait copy derives from server UTC; no account/signup/download/price language.

## 6. Fragment/API contract changes

- `GET /onboarding/readiness?target=<connection>` -> 200 text/html fragment for an allowlisted connection; starts an async metadata probe only when the snapshot is missing/stale; while `setup.checking` the fragment carries the htmx polling attribute; terminal fragments carry no polling. Unknown/foreign target -> 404 fragment, provider never contacted. Owner-only; `Cache-Control: no-store`.
- `POST /onboarding/readiness/retry` form fields `csrf`, `target` -> 303 `/onboarding/connection` when a retry is allowed and not inside the capped wait; 409 explicit wait/attempt-limit copy otherwise; CSRF failure -> 403 `auth.csrf_rejected`.
- `POST /onboarding/readiness/verify` fields `csrf`, `target`, optional `model` (server-side allowlist from the metadata result; default first model) -> 303 on started; 409 if cooling down/no metadata models; 403 on CSRF. A generation is never started by GET, polling, retry or resume.
- `GET /onboarding/connection` -> 200 text/html shell; 303 to `/onboarding/ai-service` with a notice when no route is saved (never an auto-chain); owner-only. Reached from the chooser's now-real CTA (03c replaces the TEMPORARY `/#/connections` bridge in `onboarding_chooser_api.py:46-47`).
- Snapshot record shape (in process only, never kv): `ProbeResult` + attempt number + running flag; `detail` <=500 chars after key redaction; no headers, key, or request body retained. Panel markup carries `data-readiness-state="<canonical state>"`, `data-mode`, `data-attempt`; the page carries `data-onboarding-state` and, when applicable, `data-shell-state`.
- Setup record delta: `connection_name: ""` defaulted; older readers ignore it; no store schema change.

## 7. Server-side authorization and security checklist

- [ ] Each new route is absent from `REMOTE_ROUTE_CAPABILITIES`; tests assert `None` for GET /onboarding/readiness, GET /onboarding/connection and both POSTs; paired phones get 403.
- [ ] Every POST calls `check_csrf`; no CSRF-free mutation; retry/verify are state-gated server-side (409), not just hidden in the UI.
- [ ] No user-controlled redirect/URL: target is a connection-name allowlist; route changes are user-clicked links to `/onboarding/ai-service`.
- [ ] Probes run only in the server process; the browser never gets a provider URL; e2e asserts zero cross-origin requests and fake-provider request logs show server-origin calls only.
- [ ] No secret in HTML, logs, kv, snapshots, error detail or URL; stored key redacted before storage/rendering; grep assertion on captured HTML; owner-only no-store.
- [ ] No network call from metadata polling beyond the started probe; one probe per target at a time; daemon threads bounded by the 20 s deadline; server shutdown does not leave store writes.
- [ ] New CSS/JS are first-party static files; CSP and existing security headers unchanged; no external asset/analytics.

## 8. Marketing-site dependency

None. No site change; onboarding must not claim a provider is "verified" or "connected" in marketing terms. Final site reconciliation is slice 11 ([marketing-changes.md](../marketing-changes.md)); do not touch `website/`.

## 9. Docs to update

- `@docs/design-system.md:328-351` "Setup recovery boundaries": readiness truth rules (metadata = saved-unverified; generation = verified; retry policy; client-shell offline/server-down ownership; no browser probe).
- `@docs/onboarding/setup-record.md:167-197` state-token table + `connection_name` field, readiness snapshot non-persistence/redaction, revalidation states, and the additive `setup.empty_no_connection` token.
- `@docs/onboarding/slices/slice-03.md`: acceptance record after CP3 (reviewer/date/evidence path/verdict).
- `@docs/onboarding/task-plan.md`: CP3 checkpoint note only; `@docs/onboarding/edge-case-matrix.md`: mark EC-03/05/06/07/20 evidence rows exercised and record any new token.
- Evidence: `docs/onboarding/evidence/slice-03/README.md` + `validation.json` (pointer copy under `artifacts/slice-03/`).

## 10. Tests and commands

- Fast lane: `npm run test:agent -- tests/test_route_readiness.py tests/test_readiness_probe.py tests/test_onboarding_readiness.py` (or `uv run --frozen --no-sync pytest -q --no-header --tb=line ...`); expected: state-mapping table green, no live provider.
- Hygiene: `npm run check:agent`; `python3 scripts/audit_emoji.py`; no new over-cap file and no growth of `app.py`, frozen files or the pinned e2e test.
- Browser lane: `uv run --frozen --no-sync pytest -q --no-header --tb=line tests/e2e/test_onboarding_readiness.py` writing captures + `capture-results.json`; reviewer opens every PNG and records `validation.json`.
- Manual/limitations: Chromium/Linux only unless another engine is captured; real phone/screen-reader/zoom not claimed in this slice.

## 11. Visual-validation evidence required

Path `docs/onboarding/evidence/slice-03/` (execution directive; pointer under `artifacts/slice-03/`). Rows: `setup.checking` (with >10 s note), `setup.saved_unverified`, `setup.verified`, each provider.* state, `provider.retry_scheduled`, `setup.revalidation_required/ok/failed`, `setup.empty_no_connection`, `net.offline`, `server.unreachable`; every state at 375x812 and 1440x1000, plus `setup.checking`/`saved_unverified`/`verified`/one provider error at 320x740 and 768x1024; forced colours, reduced motion, 200 percent text zoom and keyboard focus order on the panel; long 503 detail wrapping and copy affordance; bilingual/non-Latin model/label wrapping (EC-10). Required fields per row: `state`, `viewport`, `artifact`, `verdict` (APPROVED/NEEDS WORK), `finding` (max 3), `source_commit`, `reviewer`. Missing evidence = FAIL; generated is not reviewed.

## 12. Acceptance criteria (binary, CP3)

- [ ] `ProbeResult` and the classifier exist in `src/hutch/route_readiness.py` with the exact eight fields and all 14 `ProviderError.KINDS` mapped; metadata never yields `setup.verified`; `ConnectionCheck.verified` is never read by the panel; tests prove both.
- [ ] All named states are implemented and testable with deterministic fake-provider fixtures: 200-model-list/401-generation, 402, 408, 429 with Retry-After, 503 long multi-line, unreachable, slow/hung; retry is allowed only for retryable states and waits out the capped Retry-After.
- [ ] Every panel state has one specific next action (retry, explicit verify, switch) and one announcement per transition; polling ticks are silent; no generic error; no state is produced from a failed check alone.
- [ ] The browser makes no provider call: e2e shows only same-origin requests; fake provider sees server calls only; no key or provider-supplied secret appears in HTML/snapshots/logs.
- [ ] Revalidation on stale snapshot/route change renders required/ok/failed states and never replays a stale success; client-shell `net.offline`/`server.unreachable` with Retry exists and is handed to slice 09.
- [ ] Owner-only + CSRF + capability-None tested for all new routes; no user-controlled redirect/URL; snapshots process-local only.
- [ ] Budgets: new files <=400; `onboarding_api.py` +<=2 lines; `app.py`, frozen files and pinned e2e test unchanged; `npm run check:agent` adds no new violation.
- [ ] Evidence APPROVED for every required state/viewport; docs updated; reviewer sign-off recorded in the acceptance record.

## 13. Rollback plan

Change shape: one new pure module + one new HTTP module + a typed probe extension in `providers/connection.py` + two new templates + one CSS + one JS + one defaulted record field + tests. No migration, no SCHEMA_VERSION change, no existing route behaviour changed (only the chooser's temporary CTA target/label changes).
1. Remove the two installer lines in `onboarding_api.py` (or revert the slice commits): the readiness/connection routes disappear; `onboarding_api.py` returns below its pre-slice content; restore the chooser's TEMPORARY `/#/connections` CTA (constant + label) in the same targeted patch.
2. Delete/ignore `onboarding_readiness_api.py`, `route_readiness.py`, the readiness templates/CSS/JS and the tests; nothing else imports them. Keep `providers/connection.py`'s additive typed helpers or revert them in the same targeted commit - leave `check_connection` untouched either way.
3. Leave the `connection_name` field and every kv setup record in place: the field is defaulted and inert without the routes; a record written by slice 04 remains readable by slice-01/02 code because unknown fields are ignored. Never delete user setup data.
4. In-process snapshots vanish with the process (nothing to clean up). Verify: `/onboarding/readiness` and `/onboarding/connection` 404, `/onboarding` + chooser unchanged, pinned first-run e2e green, audit unchanged, no migration delta.
Risk: `app.py`/onboarding modules/templates carry another session's work; rollback is a targeted patch, never `git checkout` of those files.

## 14. Risks / open questions

- **Generation probe vs governed-run safety (P1, needs reviewer sign-off):** `@src/hutch/providers/connection.py:50-56` and `@tests/test_connections.py:455-468` record that model capability checks must use a normal governed bot run so usage reservations/approvals/receipts apply; a direct 1-token generation bypasses that accounting. This slice makes it explicit, owner-triggered, one-shot, tool-free and labelled "may use a small amount of provider credit". If reviewers refuse, fallback: keep `setup.saved_unverified` as the highest readiness state in 03/04 and move `setup.verified` to slice 08's governed first request; the 401-on-generation fixture still proves classifier mapping through the adapter unit test.
- Readiness snapshots are process-local (documented, same single-server model as `onboarding_store.py:24-27`); a restart forces a metadata revalidation. Multi-process writers remain out of scope.
- Provider detail strings can echo request headers/keys; the panel must redact before storing/rendering and bound detail length; a test greps captured HTML for the fixture key.
- htmx polling and screen readers: the fragment is server-rendered; announcement suppression depends on the state-token comparison in `onboarding-readiness.js`; this needs a DOM assertion, not just a screenshot.
- 429 Retry-After can be huge or missing; cap at 600 s and copy the wait; never auto-call the provider.
- The step shell's temporary route-form fallback must not ship as the final UX and must not be linked from marketing; slices 04/05/06 replace it with partials.
- Slice 02 landed while this brief was written: the planning drafts' anchors (onboarding_api.py 236/279 lines, onboarding.css 396) are stale - the tree now has 230/388 plus active slice-02 polish. Re-read every anchor and the file-size audit before editing; expect a few-line drift until CP2 is recorded.
- Route readiness for `opencode` routes is only partially meaningful before slice 06 (managed sign-in routes are `unverifiable` here); do not invent a provider state for them in this slice.

## 15. Planning approval (2026-10-29)

Approved by the Lead as the CP1 -> CP2 planning precondition ("slice-03/04 briefs
written and approved", task-plan CP2). Approved-ready: anchors re-read against the
shipped slice-02 tree (230-line onboarding_api.py, 388-line onboarding.css, new
pagekit/chooser modules); bounded new modules chosen for the 400-line cap; the
state-classifier contract, deterministic fake-provider fixture plan, CP3 evidence
matrix, and rollback plan are all present. Two P1 decisions from section 14 are
expressly deferred to the slice-03 checkpoint with reviewer sign-off:

1. The explicit 1-token generation probe may not bypass governed-run usage
   accounting. Close the accounting gap in slice 03 or take the documented
   fallback (highest readiness is `setup.saved_unverified`; `setup.verified`
   moves to slice 08's governed first request). The 401-on-generation fixture must
   still prove the classifier mapping either way.
2. The panel may not render a bare "error"; every state in section 5 must keep its
   own token, reason and one next action, and polling ticks must stay silent for
   assistive tech.

Slice 04 must consume slice 03's `ProbeResult`/classifier and must not fork a
second readiness truth.
