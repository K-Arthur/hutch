# Slice 04 - Hosted-key connection step (paste, save, verify, terms, 401/402/403/429/5xx recovery)

Status: IMPLEMENTATION BRIEF (written 2026-10-29; not implemented). Acceptance gate: CP4 (shared with slices 05-06). Planning gate: CP0 in [task-plan.md](../task-plan.md).
Depends on: CP2 (slice 02; implemented in commits 4c53c814/7140d48f and still being finalized at CP2 when this brief was written) for the chooser/route contract, and explicitly on **slice 03's `ProbeResult` + classifier + typed probe adapter contract (03a/03b) and the `/onboarding/connection` shell**: this slice consumes `src/hutch/route_readiness.py` and must never fork a second classifier, probe, or state mapping. Merge order is slice 03 then slice 04 unless the Lead coordinates one writer on the shared modules. Owner: TBD. Reviewer: TBD. Anchors re-read 2026-10-29 on that shared working tree; another session still carries uncommitted brand work in `app.js`/`app.py`/templates/package files and slice-02 polish in onboarding files: re-read every anchor before editing; never revert, format, stage or touch another session's work.

## 0. What prior slices delivered (use these, do not re-invent)

- Slice 01 ACCEPTED at CP1; slice 02 implemented (CP2 finalization in progress). Use the shipped seams:
  - `@src/hutch/onboarding.py:37-67` `OnboardingSetup` (`:50-55` `route_kind`/`route_chosen_at`; extra fields ignored), `:106-113` `default_setup`; `@src/hutch/onboarding_choices.py:29` `ROUTE_KINDS`.
  - `@src/hutch/onboarding_store.py:24-27` key/lock, `:47-50` `load_setup`, `:53-67` `save_request`, `:70-92` `save_route` (the lock/revision pattern this slice extends). 100 lines now.
  - `@src/hutch/server/onboarding_pagekit.py:1-86` shared render/flash/form plumbing (`render` `:68-86`, `redirect` `:43-50`, `form_values` `:53-56`, `revision` `:59-65`, `local_clock` `:35-39`); reuse it for the new pages, do not add a second render stack.
  - `@src/hutch/server/onboarding_api.py:213-230` installer (ends with `install_chooser_routes(...)` at `:230`, 230 lines), `CONTINUE_TARGET="/onboarding/ai-service"` `:37-38`; `@src/hutch/server/onboarding_chooser_api.py:184-193` chooser install; its `CONTINUE_TARGET="/#/connections"` at `:46-47` is TEMPORARY and slice 03 replaces it with `/onboarding/connection` plus the CTA label at `@templates/onboarding_ai_service.html:32`.
  - Templates/static: `@templates/onboarding.html:5-15` head block (meta referrer same-origin, CSS/JS) and `:34` continue CTA; `@templates/onboarding_ai_service.html:5-32`; `@src/hutch/server/static/onboarding.js:114` lines (busy/pageshow/draft/focus), `onboarding.css` 388, `onboarding-form.css` 102, `onboarding-chooser.css` 216.
- Slice 03 BRIEF (this run; not implemented): `route_readiness.py` `ProbeResult(state, kind, http_status, retry_after, detail, models, checked_at, mode)`, the 14-kind classifier, `metadata_result` (saved-unverified only) / `generation_result` (verified only), the typed probe adapter in `providers/connection.py`, process-local readiness routes (`GET /onboarding/readiness`, `POST .../retry`, `POST .../verify`), the new `fragment()` helper in `onboarding_pagekit.py`, and the `/onboarding/connection` shell with `_onboarding_readiness.html` and the dynamic `_onboarding_route_<kind>.html` include. This slice supplies `_onboarding_route_hosted_key.html`, writes `connection_name`, and reuses the verify route; it must not add a second probe or verification route.
- Server-side seams: `@src/hutch/server/app.py:7055-7096` create handler (key trim/cap `:7064-7068`, discovery `:7086-7096`), `:7098-7149` actions (set-key `:7106-7115`, ack `:7121-7125`, test `:7126-7136`), `:1485-1499` request models, `:7251-7252` onboarding install, `:7256-7261` capability inventory loop (7,264 lines now; check the baseline with `wc -l`); `@src/hutch/server/security.py:506-509` `check_csrf`, same-origin middleware `:314-318`.
- Key/terms storage (read-only; `connections.py` is frozen at 448 lines): `@src/hutch/connections.py:247-252` `templates()` (api_key only), `:257-261` `get`/`names`, `:275-300` `key_file`/`key`, `:302-312` `key_source` (operator env var is distinguishable), `:314-326` `has_key`, `:345-366` `set_key` (0600 file, strips the value, never returns it), `:49-58` `Terms.digest`, `:432-443` `ack_status`, `:445-448` `acknowledge` (kv `connection_ack:<name>` with digest + ISO-8601 `at`), `:371-386` `add`. Terms templates live in `@src/hutch/data/connections.json:16-19` (opencode-go acks terms) etc. `@templates/connections.html:68-76,105-112` is the existing SPA-adjacent surface and another session's dirty file: read-only reference, do not modify it in this slice.
- Legacy compatibility: `check_connection` stays untouched for `@src/hutch/server/pages.py:683`, `@pages_models.py:134-135`, `@src/hutch/doctor.py:168-169`, `@src/hutch/cli.py:1428-1429`. The SPA consumer of the JSON discovery payload is `@src/hutch/server/static/app.js:11111-11119` and the pinned assertion is `@tests/e2e/test_design_system.py:1953` (3,334 lines) - this slice preserves that response shape so neither must change (see section 14 for the residual honesty caveat).
- Test/evidence conventions: `@tests/test_onboarding_chooser.py:34-75` fixture/seed/CSRF pattern, `@tests/e2e/test_onboarding_chooser.py:1-30` live-capture scaffold, `@tests/e2e/test_onboarding_page.py:32-60` viewports/evidence dir, `@tests/fakes.py:31-121` fake-server pattern (frozen; copy into the new shared fake provider from slice 03). Evidence under `docs/onboarding/evidence/slice-04/` (execution directive), pointer under `artifacts/slice-04/`.

## 1. User outcome (one sentence)

On the hosted-key step the owner pastes a provider key exactly once into a write-only field, sees it trimmed (trailing newline or a copied "Bearer " prefix handled), saved to a 0600 file - never echoed back, never in HTML/logs/SQLite/URLs - acknowledges that provider's terms (version digest + timestamp persisted, re-asked only when the notice changes), and then sees "Saved on this machine, not verified" with a specifically worded 401/402/403/429/5xx recovery path plus an explicit "Run a small test generation" action that alone may produce "Verified".

Not in this slice: local-service and external-login connection forms (05/06), assistant creation/first request (07/08), pairing (10), full a11y/offline gate (09), marketing site (11), the legacy connections page redesign, OS keyring support (does not exist in this repo), and advanced custom base URLs (existing Connections page only).

## 2. Primary task per step

### 04a - Shared connections service + app.py handler delegation (net-zero-or-shrink)
Files/new functions:
- `@src/hutch/connections_service.py` (new; aim <=200, hard cap 400; no FastAPI imports; pure decisions + `ConnectionBook` calls):
  - `normalise_and_validate_key(raw: str) -> KeyCheck` (`kind` in *ok* | *empty* | *too_long* | *malformed*, `value` only for *ok*, `message` user-facing): trim outer whitespace (including trailing LF/CRLF), strip exactly one leading case-insensitive `Bearer ` token, re-trim, reject empty, reject `>4096` UTF-8 bytes after normalisation (HTTP 413 at both surfaces, matching `@tests/test_connections.py:541-551`), reject embedded CR/LF/control chars as *malformed* (422, copy names the fix), accept everything else byte-for-byte. Never log, return in HTML, or keep the value in the result beyond *ok*.
  - `store_key(book, name, raw, *, prefer_stored=True) -> StoreResult` (*stored* | *invalid* | *permission_denied*): validate then `book.set_key(...)` (0600, `@connections.py:345-366`); catch `OSError`/`PermissionError` -> *permission_denied* with the `secret.store_permission_denied` copy (state-dir permissions, or set the provider env var instead); never echo the key.
  - `probe_connection(book, name, *, mode=MODE_METADATA, model="") -> ProbeResult` delegating to slice 03's typed adapter and `route_readiness`; redacts `book.key(name)` from `detail` (mirror `@app.py:7089-7095`), bounds detail to 500 chars. Generation runs only when `mode=MODE_GENERATION` and an explicit owner action asked for it.
  - `acknowledge_terms(book, store, name, *, agree: bool) -> TermsResult` (*not_needed* | *required* | *acknowledged* | *stale_acknowledged*): `agree=False` + `requires_ack` -> *required* (HTTP 422); otherwise `book.acknowledge(...)` persists `{"digest": Terms.digest, "at": ISO-8601 UTC}` in `connection_ack:<name>` (version identity = digest, timestamp = at; `connections.py` unchanged); `terms_view(book, store, name)` maps `ack_status` *ok -> consent.current*, *stale -> consent.stale*, *required -> consent.required* (additive token; docs update) and returns notice/url/digest/timestamp for rendering.
  - `key_source_view(book, name)`: `secret.operator_managed` when `book.key_source(name)` starts with "environment variable ", else stored/missing; never returns a key value.
- `@src/hutch/server/app.py:7055-7149` rewire with a net-zero-or-shrink hunk (current 7,264 lines, baseline 7,461; verify with `wc -l`): create uses `normalise_and_validate_key` + `probe_connection` and returns the **unchanged** JSON shape `{added, discovery:{ok, verified, model_count, detail}}` where the legacy `verified` field is computed as "metadata authenticated" from `ProbeResult.state == setup.saved_unverified` (code comment marks it legacy-only, never rendered by onboarding and distinct from `setup.verified`); set-key uses `store_key`; ack uses `acknowledge_terms`; test uses `probe_connection` + redacted detail (400 on error, same body shape); allowance/clear-key/remove unchanged. Remove the inline trim/cap/redaction lines rather than duplicating them.
- `@tests/test_connections_service.py` (new <=400): normalisation table (spaces, trailing LF, CRLF, "Bearer " lower/upper, "Bearer" without space, 4095/4096/4097 bytes, empty, embedded newline); HTTP parity: create and set-key both yield 422/413 with the same message and no echo; probe mapping 401/402/403/429(+Retry-After)/503/408/unreachable through slice 03's fake provider; redaction of an echoed key; terms ack digest+timestamp persisted and re-read from a reopened store; stale-digest fixture -> consent.stale; operator-managed env key; locked storage monkeypatch -> `secret.store_permission_denied` and no key anywhere; legacy `check_connection` behaviour and the JSON discovery shape unchanged (existing `@tests/test_connections.py:494-551`, `@tests/test_api.py:1259-1290` stay green).

### 04b - Hosted-key onboarding step (template, routes, terms, storage states)
Files/functions:
- `@src/hutch/server/onboarding_hosted_key_api.py` (new bounded module mirroring `onboarding_chooser_api.py`; aim <=280, hard cap 400): `install_hosted_key_routes(app, *, store, config, templates)` called by `@src/hutch/server/onboarding_api.py:213-230` with exactly one added line after `:230`; `HOSTED_KEY_TEMPLATES = ("openai-api", "anthropic-api", "openrouter", "opencode-go")` server-side allowlist (openai/anthropic/openrouter are the common hosted keys; opencode-go exercises the required terms acknowledgement path; every other template stays on the existing Connections page).
  - `GET /onboarding/hosted-key` -> 303 `/onboarding/ai-service` with a notice when `route_kind != "hosted_key"` (never an auto-chain), 303 /onboarding when the setup record is stale/expired (using the slice-01 recovery states), otherwise 200. No `provider` query: provider-choice view with one action per provider, a "terms required" badge where `template.terms.requires_ack`, and the operator-managed note when the template env var is set. `?provider=<id>`: server-side allowlist, 303 back to the choice view with a notice on unknown id; renders the key form with the provider terms notice + required acknowledgement checkbox when needed, the secret field, and a "Choose a different provider" secondary.
  - Secret field contract: `<input type="password" name="key" autocomplete="off" spellcheck="false" data-secret>` with no `value` attribute ever rendered, help "Paste the key once. Hutch stores it in a private 0600 file and cannot show it again."; operator-managed providers render a read-only `secret.operator_managed` note and a "Use the managed key" button instead of a key field; replace mode (`?provider=<id>&connection=<name>`, connection validated against `book.names()` and `auth_type == "api_key"`) reuses the same form.
  - `POST /onboarding/hosted-key` (form): fields `csrf`, `revision`, `provider`, `mode` (*key* | *managed*), `key` (optional for managed), `terms_agree` (checkbox), optional `connection` (replace target). Order: CSRF (`check_csrf`; 403 `auth.csrf_rejected` with the submitted provider preserved, never the key) -> setup revision/staleness (409 explicit conflict; no write) -> provider allowlist (422) -> `normalise_and_validate_key` (422/413; re-render without the key and copy "Paste it again - Hutch did not keep it") -> terms `acknowledge_terms` when `requires_ack` (422 `consent.required`; nothing saved) -> create/replace the connection (`book.add`/`book.set_key` via `store_key`; cleanup with `book.remove` if storage fails -> `secret.store_permission_denied` page) -> persist `connection_name` and `step='connection'` through a new bounded `@src/hutch/onboarding_store.py` function using the same lock/revision pattern as `save_route` `:70-92` (adds <=30 lines to the 100-line module; no schema change) -> start slice 03's metadata probe -> 303 `/onboarding/connection`. A record-save conflict after the connection was created is reported explicitly ("A connection was saved on this machine; review it on Connections") and does not advance the step; the key file is not rolled back into the HTML path.
  - No secret reaches: page HTML, flash cookies, `Location` headers, query strings, logs (no form logging; exception messages redacted), SQLite/kv (`connection_name` only), or the transcript.
- Templates: `onboarding_hosted_key.html` (new; extends base chrome-less, meta referrer same-origin, head block links `onboarding-hosted-key.css` + `onboarding.js`; h1, one primary per state, provider cards/radios as real inputs, terms notice and checkbox with `aria-describedby`, error summary `role="alert" tabindex="-1"`); `_onboarding_route_hosted_key.html` (new partial consumed by slice 03's shell include: saved provider, key source line ("stored on this machine" / "managed by operator"), "Saved on this machine - not verified" wording, "Replace key" link, "Run a small test generation" pointer to the readiness panel; never renders a key or its length); `onboarding-hosted-key.css` (new <=200; busy state, field error, terms block, operator note, forced-colours/reduced-motion, 320-1440 reflow; do not grow `onboarding.css` at 388 lines).
- Tests `@tests/test_onboarding_hosted_key.py` (new <=400, fixtures per `@tests/test_onboarding_chooser.py:34-75`): route auth/capability `None`/CSRF; redirect rules; allowlist; write-only field absent from HTML after error/save; whitespace + Bearer-prefixed fixture key is trimmed and stored exactly; 4 KiB boundary; save -> setup record `connection_name` + `step`; 0600 key file; metadata probe -> `setup.saved_unverified` (never `setup.verified`); terms required 422; ack digest+at persisted and re-read; stale notice -> consent.stale re-ask; replaced key updates the same connection; operator-managed path; locked storage; no key in HTML/Location/cookies/caplog/kv; paired-phone 403.

### 04c - Recovery copy, explicit verify reuse and browser evidence
- Verification is slice 03's `POST /onboarding/readiness/verify` only (explicit owner action, generation probe, 60 s cooldown); this slice wires the recovery panel into the hosted-key step's post-save state and must not add a second probe route. After save the connection step shows `setup.checking` (metadata) -> `setup.saved_unverified`; only the explicit generation action can render `setup.verified`. The word "Saved" is never "Verified"/"Connected" before that probe result.
- Recovery copy table (rendered from the canonical `ProbeResult.state`, never from raw exception text): 401 -> `provider.invalid_credential` "The provider rejected this key. Replace it or check that it was copied completely."; 403/upstream policy -> `provider.permission_denied` "The provider refused this key or account for this route. Check scopes, model access, and account standing."; 402 -> `provider.no_credit` "The provider reports no available credit or quota. Top up or switch route."; 429 -> `provider.rate_limited` + `provider.retry_scheduled` with the capped Retry-After wait; 5xx/stream/oom/refused -> `provider.unavailable` with the long error copyable; 408/deadline -> `provider.timed_out`; transport -> `provider.unreachable`; 400/bad route -> `provider.invalid_route`; 404/model -> `provider.model_missing`; context/incomplete -> `provider.context_or_incomplete`. Each error has one primary action (Retry when retryable, else Replace key / Switch route) plus the external action named in words (`setup.blocked_external_action` when the fix is outside Hutch, e.g. provider billing/standing); never a generic "error" or "no service". Retry only re-runs a probe; Switch is the user-clicked link to `/onboarding/ai-service`.
- Copy rules tested: no account/signup/download/pricing/"free forever"/"verified" claims; "Saved" vs "Verified" distinguished; generation copy says a small amount of provider credit may be used; operator-managed copy says the service is managed outside the app.
- `@tests/e2e/test_onboarding_hosted_key.py` (new <=400, scaffold per `@tests/e2e/test_onboarding_chooser.py:1-30`): live app + slice 03's fake provider; type a key (including trailing LF and "Bearer " prefix fixture) into the masked field; assert save -> saved_unverified; explicit generation 401 -> invalid_credential (not verified, no false success); 402/403/429(+Retry-After copy)/503-long/408/unreachable rows; terms required/stale; operator-managed; keyboard-only paste + submit; no cross-origin request from the page; network log and HTML contain no key.

### 04d - CP4 evidence, docs and acceptance record
- Captures under `docs/onboarding/evidence/slice-04/` (execution directive; pointer under `artifacts/slice-04/`); reviewer opens every image and writes binary verdicts; record limitations (locked-storage row is unit/manual, not e2e).

## 3. Boundary for this slice

- UI: new server-rendered step page + one partial for slice 03's connection shell + hand-written CSS; reuses `onboarding.js` busy/pageshow/error-summary behaviour; no SPA route change and no new client store.
- API: HTML form contract only. JSON `/api/connections` handlers are delegated to the shared service but keep their existing response shape (legacy contract); no new JSON endpoint.
- Provider I/O: save-time metadata probe and the explicit generation probe from slice 03 only; probe runs in the server process; browser never contacts a provider.
- Secret handling: one `<input type="password">` POST over same-origin without query parameters; stored only via `ConnectionBook.set_key` (0600); never read back into HTML; server caps and trims before storage.
- Authorization: owner-only routes (capability `None` via the inventory loop); CSRF on the POST; no user-controlled redirect/URL; provider is a server allowlist; connection replace target is a server allowlist.
- Persistence: `connection_name` + step in the existing setup record; terms digest+timestamp in the existing `connection_ack:<name>` kv record; connections/key files via existing `ConnectionBook`; no migration, no `SCHEMA_VERSION` change, `connections.py` untouched.
- Budgets: new files <=400 lines (targets above); `app.py` net-zero-or-shrink and under baseline; `onboarding_store.py` +<=30 lines (100 now); `onboarding_api.py` +1 line (230 now); do not grow `connections.py`, `security.py`, `models.py`, `pages.py`, `store.py`, or `tests/e2e/test_design_system.py`; `onboarding.css`/`onboarding-chooser.css` not grown.

## 4. Edge cases in scope (from [edge-case-matrix.md](../edge-case-matrix.md))

| Matrix row | Covered here as |
|---|---|
| EC-03 provider timeout/5xx | 408 -> `provider.timed_out`, 5xx -> `provider.unavailable` with long copyable detail; first feedback under 1 s (saving state); retry does not re-create the connection or duplicate spend. |
| EC-05 permission denied / hostile key data | 401 -> `provider.invalid_credential`; 403 -> `provider.permission_denied`; 402 -> `provider.no_credit`; 429 -> `provider.rate_limited`; trailing-LF and "Bearer "-prefixed valid key is trimmed and verifies; revoked key -> invalid_credential; locked storage -> `secret.store_permission_denied`; operator-managed env key -> `secret.operator_managed` read-only. |
| EC-07 stale resume / terms version | Notice digest change -> `consent.stale` re-ask showing the new notice; re-ask only on change; stale setup record -> 409/conflict or slice-01 stale state; `connection_name` pointing at a removed connection -> explicit revalidation/empty state, never a false resume. |
| EC-09 locale/timezone/units | Terms acknowledgement timestamp shown in local time from server UTC ISO-8601; Retry-After waits relative; no currency/price/plan copy (existing USD caps stay on the Connections page). |
| EC-20 empty/loading/saving/error/blocked | Provider-choice empty state, `submit.saving`, validation errors, storage/permission states, blocked-external-action copy; no generic error; saved never shown as verified. |
| EC-06 offline (partial) | Slice 03 owns the client-shell offline/server-down banner; this step inherits it and its form still works after reconnect; full-flow gate is slice 09. |
| EC-16/17/18/19 (partial) | Write-only field is keyboard-pasteable; error summary focused once; no motion-only saving cue; forced colours/reduced motion rows captured; full audit slice 09. |

Out of scope: OS keyring integration (not present in this repo; do not claim one), non-API-key/sign-in templates, custom base URLs and advanced connection settings, local-service probes (05), external login (06), assistant/first request (07/08), pairing (10), marketing claims, and any change to `@templates/connections.html` or the SPA connections UI.

## 5. Front-end states for this slice

| State token | Trigger | Must show | Primary action | Must not |
|---|---|---|---|---|
| `setup.empty_no_connection` | GET choice view | provider list with honest prerequisites, terms-required badges, operator-managed note | Continue with this provider | imply an account/signup; hide that a provider account/key is needed |
| `consent.required` | selected provider requires terms and checkbox missing | the exact notice text, link to vendor terms, checkbox with error | Save key (after acknowledging) | save the key or ack silently |
| `consent.current` | ack digest matches current notice | "Terms acknowledged <relative/local time>" + digest short id | Replace key / Continue | claim verification |
| `consent.stale` | ack digest != current notice | "The provider's terms changed; acknowledge again" + what changed | Acknowledge again | silently continue under the old ack |
| `secret.operator_managed` | template env var present | read-only "managed by operator (environment variable NAME)" | Use the managed key | ask for or display a value |
| `input.invalid` | empty/whitespace/over-4KiB/line-break key | focused error summary + adjacent message, provider kept | Paste it again / Replace key | echo or retain the pasted value |
| `secret.store_permission_denied` | OS refused the 0600 write | cause (state-dir permissions) + one action | Retry / set the provider env var instead | include the key in the message; leave a half-created connection |
| `submit.saving` | POST in flight | disabled + aria-busy + "Saving..." (never "Verified") | none | double-submit or lose provider choice |
| `setup.saved_unverified` (from 03) | save + metadata probe authenticated | "Saved on this machine. Model list reachable; not generation-tested." key source | Run a small test generation / Replace key | word "Verified"/"Connected"; success colour |
| `setup.verified` (from 03) | explicit generation succeeded | generation confirmed + model + possible small credit use | Continue (slice 07) | ongoing-quality claim |
| `provider.*` (401/402/403/429/5xx/408/unreachable...) | probe result | cause-specific copy from the slice-03 table, Retry/Replace/Switch | per cause | generic error; raw exception |
| `setup.blocked_external_action` | fix is outside Hutch (billing/standing/scopes) | exactly which external action and the return path | Switch route / back to Hutch | disabled control as a substitute for the explanation |
| `auth.csrf_rejected` / `auth.session_expired` / forbidden | CSRF, session, paired phone | session wording, reload/return action | Reload | provider wording |
| `setup.conflict` | stale record revision on POST | both versions/choice kept, no overwrite | Review latest setup | silently overwrite |

Copy rules: "Saved" is never "Verified"/"Connected" before a generation probe result; no account/signup/download/price language; every error names one cause and one next action; a key is never displayed back, not even masked with a known length.

## 6. Form/API contract changes

- `GET /onboarding/hosted-key` -> 303 `/onboarding/ai-service` (notice) when no `hosted_key` route, 303 /onboarding for stale/expired records, 200 choice view otherwise; `GET /onboarding/hosted-key?provider=<id>` -> 200 key form for an allowlisted provider, 303 to the choice view with a notice for an unknown id; owner-only, `Cache-Control: no-store`.
- `POST /onboarding/hosted-key` form fields: `csrf` (required), `revision` (required int), `provider` (required allowlist), `mode` (required *key* | *managed*), `key` (required for *key*, absent for *managed*), `terms_agree` (checkbox; required only when the provider requires ack), optional `connection` (replace target, validated allowlist).
  - 303 `Location: /onboarding/connection` on success (no query string; `connection_name` persisted).
  - 422 re-render for invalid/missing key, unknown provider, or missing terms acknowledgement (state `input.invalid` or `consent.required`; key value never re-rendered; copy says paste again).
  - 413 for a key over 4 KiB after normalisation (same message and no echo on the JSON API surfaces too).
  - 409 for a stale setup revision (`setup.conflict`) or a stale/removed replace target; no partial overwrite.
  - 403 for missing/invalid CSRF or a paired-phone session; 303 recovery for a stale/expired setup record.
- Persistence delta: setup record `connection_name` + `step='connection'` via the store adapter (lock + revision, same semantics as `save_request`/`save_route`); `connection_ack:<name>` keeps its existing `{"digest","at"}` shape, now documented as the version identity + timestamp contract (no `connections.py` change); the key value exists only in the 0600 key file.
- No JSON request/response shape changes; `POST /api/connections` keeps `{added, discovery:{ok, verified, model_count, detail}}` with `verified` meaning "metadata authenticated" for legacy SPA compatibility only (documented as deprecated and never the onboarding `setup.verified`).

## 7. Server-side authorization and security checklist

- [ ] New routes absent from `REMOTE_ROUTE_CAPABILITIES`; tests assert `None` for GET and POST, paired phones 403.
- [ ] Every POST calls `check_csrf`; provider and replace target are server-side allowlists; no user-controlled redirect, URL, header or file path.
- [ ] Key is write-only: server trims/caps, `ConnectionBook.set_key` writes 0600, never returned/logged/stored in SQLite/transcripts/URLs/HTML; error/redirect/flash bodies grepped for the fixture key; `caplog` assertion.
- [ ] Terms are enforced server-side (422 when unacknowledged); digest+timestamp persisted; re-ask only on digest change; operator-managed providers never accept a value when in managed mode.
- [ ] Probe runs server-side only through slice 03's typed adapter; browser never gets a provider origin; e2e asserts no cross-origin request and the fake provider records server calls only.
- [ ] `connections.py` (frozen 448 lines) untouched; `app.py` delegation is net-zero-or-shrink and below the 7,461 baseline; `onboarding_store.py` growth <=30 lines; no migration, no `SCHEMA_VERSION` change.
- [ ] No new external asset/analytics; vendor terms links are ordinary user-initiated `rel="noopener noreferrer" target="_blank"` links only.

## 8. Marketing-site dependency

None. The site keeps saying no hosted signup/account and points at the source path; this step must not be described as a hosted signup, plan purchase or download. Any wording sync is slice 11 ([marketing-changes.md](../marketing-changes.md)); do not touch `website/`.

## 9. Docs to update

- `@docs/design-system.md:328-351` "Setup recovery boundaries": hosted-key secret/terms honesty rules ("Saved" vs "Verified"), write-only field, operator-managed read-only state, error copy ownership.
- `@docs/onboarding/setup-record.md:167-197`: state tokens (`consent.required`, `consent.current`, `consent.stale`, `secret.operator_managed`, `secret.store_permission_denied`, `setup.blocked_external_action`), `connection_name` write, terms digest/timestamp contract, and the legacy JSON `verified` deprecation note.
- `@docs/onboarding/slices/slice-04.md`: acceptance record after CP4.
- `@docs/onboarding/task-plan.md`: CP4 checkpoint note only; `@docs/onboarding/edge-case-matrix.md`: mark EC-03/05/07/09/20 rows exercised and record any new token.
- Evidence: `docs/onboarding/evidence/slice-04/README.md` + `validation.json` (pointer under `artifacts/slice-04/`).

## 10. Tests and commands

- Fast lane: `npm run test:agent -- tests/test_connections_service.py tests/test_onboarding_hosted_key.py` plus slice 03's readiness tests if this slice changes shared code; existing `tests/test_connections.py`, `tests/test_api.py`, `tests/test_chatgpt_integration.py` stay green (parity/regression).
- Hygiene: `npm run check:agent`; `python3 scripts/audit_emoji.py`; `wc -l src/hutch/server/app.py` proves net-zero-or-shrink against the recorded pre-slice count; no new over-cap file; frozen files and pinned e2e unchanged.
- Browser lane: `uv run --frozen --no-sync pytest -q --no-header --tb=line tests/e2e/test_onboarding_hosted_key.py` with captures + `capture-results.json`; reviewer opens every PNG.
- Manual/host check: locked-storage state via unit monkeypatch plus one manual read-only-state-dir check on the target host, recorded as a limitation (not claimed as a browser pass).

## 11. Visual-validation evidence required

Path `docs/onboarding/evidence/slice-04/` (execution directive; pointer under `artifacts/slice-04/`). Rows: provider choice; key form empty; key form with pasted secret masked; `submit.saving`; `input.invalid` (empty/oversized/trailing-newline copy); `consent.required`; `consent.current`; `consent.stale`; `secret.operator_managed`; `secret.store_permission_denied` (unit/manual note); `setup.saved_unverified`; `setup.verified`; each of 401/402/403/429 with Retry-After copy/5xx long error/408/unreachable recovery copies; `setup.blocked_external_action`; conflict/forbidden. Core states at 320x740, 375x812, 768x1024 and 1440x1000; forced colours, reduced motion, 200 percent text zoom and keyboard focus rows on the form and error summary; long provider-error wrapping; redaction row proving no key text in the DOM. Fields per row: `state`, `viewport`, `artifact`, `verdict`, `finding` (max 3), `source_commit`, `reviewer`. Missing evidence = FAIL.

## 12. Acceptance criteria (binary, CP4)

- [ ] A hosted-key step exists for `route_kind='hosted_key'` and is reachable through the onboarding flow (chooser CTA -> `/onboarding/connection` shell -> hosted-key form); GET/POST are owner-only, CSRF-checked, capability `None`, and use no user-controlled redirect/URL.
- [ ] The key is pasted into a write-only masked field and never echoed: server-side trim + one `Bearer ` prefix strip + 4 KiB cap + control-char rejection, identical on both API surfaces; `0600` file storage via `ConnectionBook.set_key`; no key in HTML, logs, SQLite/kv, transcript, URL or `Location`; tests grep all of them.
- [ ] Save produces `setup.saved_unverified` only ("Saved", never "Verified"/"Connected"); `setup.verified` requires slice 03's explicit generation probe; a 200-models/401-generation fixture resolves to `provider.invalid_credential`, never verified and never "no service".
- [ ] Terms acknowledgement is enforced server-side, persists version digest + ISO-8601 timestamp, re-asks only when the digest changes, and is test-covered for required/current/stale.
- [ ] 401/402/403/429(+Retry-After)/408/5xx/unreachable each render distinct copy with one next action (retry only when retryable, else replace/switch; blocked-external-action names the outside fix); no raw exception, no generic error.
- [ ] Operator-managed env key renders read-only `secret.operator_managed`; locked storage maps to `secret.store_permission_denied`, leaves no half-created connection, and never includes the key.
- [ ] `app.py` handler delegation is net-zero-or-shrink and below its baseline; `connections.py` untouched; `onboarding_store.py` growth <=30; no migration; existing connections/API tests and pinned e2e green; `npm run check:agent` adds no violation.
- [ ] Evidence APPROVED for every required state/viewport; copy audit shows no account/signup/download/price claim; docs updated; reviewer sign-off recorded.

## 13. Rollback plan

Change shape: one new service module + one new onboarding route module + one new template + one shell partial + one CSS + one bounded store function + net-zero-or-shrink `app.py` delegation + tests. No migration, no `SCHEMA_VERSION` change, `connections.py` untouched.
1. Remove the one install line in `onboarding_api.py` and the new route module/template/partial/CSS; the hosted-key step disappears, the chooser's hosted-key route falls back to slice 03's temporary connection-shell state.
2. Revert the `app.py:7055-7149` delegation to the previous inline code as a targeted patch (the exact pre-slice lines; verify `wc -l` and the API parity tests). Never `git checkout` the dirty file.
3. Leave connections, 0600 key files, terms acks and the `connection_name` field in place: they are ordinary `ConnectionBook`/kv products and must never be deleted by a code rollback; a record with `connection_name` stays readable because the field is defaulted/ignored by older code. The user can manage a surviving connection on the existing Connections page.
4. Verify: `/onboarding/hosted-key` 404, `/onboarding/connection` (slice 03) still works, `/api/connections` create/set-key/test/ack unchanged, pinned e2e green, audit unchanged, no migration delta.

## 14. Risks / open questions

- **Legacy JSON `verified` compatibility (P1, needs reviewer sign-off):** `@src/hutch/server/app.py:7086-7096` + `@src/hutch/server/static/app.js:11111-11119` + `@tests/e2e/test_design_system.py:1953` display a metadata success as "Connected" and the payload field is named `verified`. This slice keeps that shape for compatibility and computes it from the metadata probe, marks it deprecated in code, and never uses it for onboarding. Alternative if reviewers reject the residual dishonesty: drop the field and edit `app.js:11111-11119` plus the pinned assertion line-neutrally; that touches another session's dirty file and a frozen test file, so it needs explicit coordination.
- **Generation probe vs governed-run safety (cross-reference slice 03 section 14):** verification reuses slice 03's explicit 1-token generation, which bypasses governed-run usage accounting; reviewer sign-off and the same fallback (highest readiness = saved_unverified; verified moves to slice 08's governed first request) apply here.
- Orphan connection on a stale setup revision (connection/key created, record save conflicts): report explicitly and leave the connection usable on the Connections page; do not attempt a destructive rollback that could delete a key the user pasted.
- Terms "version": `connections.py` is frozen and has no numeric terms version - the digest is the version identity. If a reviewer requires an explicit numeric version, add a side kv field (e.g. `connection_ack_version:<name>`) from the service without touching `connections.py`; decide before 04b.
- Key normalisation strips exactly one leading "Bearer " token; a legitimate key that literally begins with that word would be altered. Tests document the single-strip rule; no other content is rewritten.
- Operator-managed semantics: a pasted stored key with `prefer_stored=True` shadows the env var for that connection (existing `@connections.py:289-295`); copy must say so, and managed mode must not silently create a second connection.
- Locked-storage evidence cannot be produced through the real browser without a hostile state dir; unit test + manual host check only, recorded as a limitation.
- Slice 02 landed while this brief was written and still has uncommitted polish; the planning drafts' anchors are stale (onboarding_api.py is 230 lines, store 100, onboarding.js 114, chooser API new). Re-read every anchor and the file-size audit before editing; `app.py` (7,264 lines) and the pinned e2e file are tight.
- Anchors drift with the other session's uncommitted brand work in `app.js`/`app.py`/templates/package files: re-read every anchor, never reformat or revert that work.

## 15. Planning approval (2026-10-29)

Approved by the Lead as the CP1 -> CP2 planning precondition ("slice-03/04 briefs
written and approved", task-plan CP2). Approved-ready: anchors re-read against the
shipped slice-02 tree; the hosted-key step contract (write-only secret, save
vs verify wording, terms acknowledgement, 401/402/403/429/5xx recovery), the
provider fixtures, CP4 evidence matrix and rollback plan are all present. The two
P1 decisions in section 14 are expressly deferred to the slice-04 checkpoint with
reviewer sign-off:

1. The explicit generation probe (reused from slice 03) may not bypass governed-run
   usage accounting; the slice-03 decision binds here too.
2. The legacy JSON `verified` shape stays for compatibility only: mark it
   deprecated in code, never use it as onboarding readiness, and never call a
   metadata check "Verified" in the hosted-key step.

No secret may appear in HTML, logs, URLs, errors or this brief's evidence; the
terms digest is the version identity unless a reviewer requires a numeric side
field.
