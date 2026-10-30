# Onboarding and setup - task plan

Status: slices 01 and 02 implemented (2026-10-29). Slice 01 ACCEPTED at CP1 - see [slice-01 acceptance record](slices/slice-01.md#15-acceptance-record-cp1) and the [evidence bundle](evidence/slice-01/README.md) (63 opened-image rows, all APPROVED). Slice 02 IMPLEMENTED at CP2 - commits 4c53c814, 7140d48f, 4fd5199d, 3e47330b, 39618432 plus the CP2 docs/evidence commit; 57 live captures under [evidence/slice-02](evidence/slice-02/README.md), acceptance record in [slice-02 section 15](slices/slice-02.md#15-acceptance-record-cp2). CP0 was PASS: independent review complete and its findings resolved (section 9, [planning review record](artifacts/planning-review-2026-10-29.md)); the planning baseline is [recorded](artifacts/planning-baseline.txt). The slice-03/04 briefs are written and approved (section 15 of each) - the CP1 -> CP2 planning precondition is closed. Slice 03 (readiness truth) is next; its [continuation prompt](continuation-prompt-03.md) is ready. Slice-05/06 briefs are owed before CP4.
Date: 2026-10-29.
Planning inputs: [research brief](research-brief.md), [research](research.md), six source notes in [notes/](notes/).
Worktree note: another session has uncommitted brand/dashboard work. At planning time `git status --porcelain` showed modified `src/hutch/server/app.py`, `src/hutch/server/static/app.js`, `src/hutch/server/templates/base.html`, `connections.html`, `pair.html`, `tests/e2e/test_design_system.py`, `website/index.html`, `docs/design-system.md`, plus many brand assets. Line anchors below were verified in that working tree on 2026-10-29; CP0 must record the exact `git status --porcelain` and `git diff --stat` baseline in the evidence bundle before any slice starts. Re-read every anchor at implementation time, touch only targeted hunks, and never revert that work.

## 0. Scope, non-goals, and the activation definition

In scope: the first-run surface of a source-installed, local-hosted Hutch - one written request, one AI service route (hosted key, local service, or existing OpenCode login), an assistant fast path, a first request that produces useful output and at least one approval decision where the task needs an action, plus optional and deferrable steps (apps, channels, phone pairing, limits).

Out of scope, unchanged by this plan: identity-document upload, liveness/selfie, signature, voice, in-dashboard camera capture, payment card, OCR, generic file upload, light theme, hosted signup/account/pricing, remote analytics, a separate SPA funnel, a permanent mandatory checklist. Marketing site pricing/plan/welcome-banner patterns are handled as boundary truth changes in [marketing-changes.md](marketing-changes.md), not as new product surfaces.

Activation (definition used by every checkpoint): the owner's own first request produced a useful assistant response and, where the request needed an action, at least one approval was shown and decided. Saving a route or an assistant is not activation. No remote telemetry: local milestones are recorded in the setup record (`first_run_started`, `ai_route_saved`, `ai_route_verified`, `assistant_created`, `first_request_sent`, `first_request_succeeded`, `first_approval_decided`) and exposed only through local diagnostics/doctor output.

## 1. Planning rules applied to every slice

1. One primary task per step. A step is the smallest commit-sized unit and is independently reviewable.
2. One concern per function: validate, persist, render, and navigate are separate functions. No function exceeds roughly 40 logical lines; if it would, the slice is split.
3. Pure decision logic lives outside I/O and UI. `src/hutch/onboarding.py` has no FastAPI, template, store, network, or filesystem imports.
4. Every state transition has an explicit representation. `provider-unavailable`, `permission-denied`, `offline`, and `stale-resume` are distinct states; never a generic "error" or a generic "no service".
5. Optional work is skippable and resumable; required work is distinguishable in words and behaviour. The request and the AI route are required for activation; apps, channels, pairing, limits, and advanced assistant settings are optional and never gate the first request.
6. Completion shows the resulting assistant/workspace and the next product action; no generic celebration screen.
7. No production code is written until the gate in section 8 passes.

## 2. Front-end/back-end boundary map

### 2.1 Layers

- UI: Jinja server-rendered pages (`pages.py` + `templates/` + hand-written CSS in `static/`) for onboarding; the existing SPA (`static/index.html` + `static/app.js`) keeps chat, assistant settings, approvals, and streaming.
- API: existing JSON APIs in `src/hutch/server/app.py` plus new onboarding endpoints. Onboarding step saves are HTML form POSTs with CSRF (same pattern as server pages); asynchronous onboarding work (readiness probes, provider checks, external-login attempts) uses server-rendered HTML fragments with bounded htmx polling; no new client-side state store.
- Provider integrations: `src/hutch/providers/` (provider calls, error taxonomy), `src/hutch/connections.py` (named connections, keys, terms, allowances), `src/hutch/runtime/opencode_server.py` and `src/hutch/runtime/opencode_login.py` (OpenCode status/login), `src/hutch/chatgpt_auth.py` (Sign in with ChatGPT, preview-only).
- Server-side authorization checks: `src/hutch/server/security.py` (`SecurityMiddleware`), `src/hutch/server/app.py:185-215` (`authorize_remote_route`, `REMOTE_ROUTE_CAPABILITIES`, `PUBLIC_REMOTE_ROUTES`), `src/hutch/server/pages.py:126-132` (`read_form` CSRF), and owner-only enforcement on every onboarding mutation.

### 2.2 Boundary map by capability

| # | Capability | UI (exact surface) | API / server route | Provider integration | Server-side authorization check |
|---|---|---|---|---|---|
| B1 | First-run entry (empty chat) | `@src/hutch/server/static/app.js:3257-3408` `renderChatStudio`; markup 3273-3337; draft 132-163; readiness 3135-3255 | `@src/hutch/server/app.py:3949-3972` `GET /api/bots`; 3995-4017 `GET /api/v1/model-routes`; 4018-4044 model defaults; 7157-7159 OpenCode status | none in the entry itself | Local owner session; no server setup state today |
| B2 | Dedicated onboarding route + resume | new `templates/onboarding.html`, `templates/_onboarding_*.html`, `static/onboarding.css`, `static/onboarding.js`; `@src/hutch/server/templates/base.html:45-74` chrome gate (templates are not size-budgeted; `page()` passes arbitrary context so a `chrome=False` context value needs no `pages.py` edit) | new `src/hutch/server/onboarding_api.py`: `GET /onboarding`, `POST /onboarding/request` (HTML contract), installed by two lines in `@src/hutch/server/app.py:7243-7248`; new `src/hutch/onboarding_store.py` wraps the existing `store.kv_get`/`store.kv_set` (`@src/hutch/store.py:11730-11740`) with a process lock and revision check for `onboarding:setup:v1` | none | `read_form` CSRF; local owner only; paired session denied |
| B3 | AI-service chooser | new `templates/onboarding_ai_service.html`; draft bridge in `static/onboarding.js` | new `GET /onboarding/ai-service`, `POST /onboarding/ai-service/choose` | none | owner-only + CSRF |
| B4 | Readiness / per-route truth | readiness panel on the first-run step; HTMX-polled fragment `templates/_onboarding_readiness.html` | new `GET /onboarding/readiness` (HTML fragment) served from `onboarding_api.py`; no browser probe; optional explicit verification action | new pure `src/hutch/route_readiness.py` builds a structured `ProbeResult(state, kind, http_status, retry_after, detail, models, checked_at, mode)` from `ProbeError`; `probe_models()` stays the metadata call; `ConnectionCheck.verified` from `@src/hutch/providers/connection.py:50-69` is NOT trusted (it is true on a mere model-list success). Canonical states: checking, saved_unverified, verified, invalid_credential, permission_denied, no_credit, rate_limited, unavailable, timed_out, unreachable, invalid_route, model_missing, context_or_incomplete (see state contract in 2.4) | probe runs in the server process; browser never calls a provider; owner-only |
| B5 | Hosted-key connection | onboarding hosted-key step template + secret input partial | `POST /onboarding/hosted-key` HTML form handler in `onboarding_api.py` calling the new shared `src/hutch/connections_service.py` (`normalise_and_validate_key`, `probe_connection`, `acknowledge_terms`); slice 04 also rewires the existing JSON handlers (`app.py:7055-7143`) to the same service functions with net-zero-or-shrink app.py diffs | `@src/hutch/connections.py:345-366` `set_key` (0600 file); `@src/hutch/connections.py:430-448` terms ack; `probe_models()` metadata probe | owner-only; key never echoed/returned (list endpoint exposes `key_present` only); 4 KiB server cap, trim before validate; terms acknowledged server-side (422 otherwise); identical validation tested on both surfaces |
| B6 | Local-service connection | onboarding local-service step template | `POST /onboarding/local-service` form handler in `onboarding_api.py` calling `connections_service` + `route_readiness`; server-side short-timeout probe | `openai_compat.py` / `ollama.py` probes; `@src/hutch/connections.py:150-180` URL validation (loopback HTTP only) | owner-only; probe is server-side, so no CORS opacity; no browser-to-localhost fetch |
| B7 | External login / OpenCode | `@src/hutch/server/static/app.js:11387-11582` `openOpenCodeSetupDialog`; onboarding external-login step | reuse `@src/hutch/server/app.py:7157-7226` OpenCode routes; new onboarding attempt record in setup state | `src/hutch/runtime/opencode_server.py` (OAuth start/status/complete/cancel), `opencode_login.py`; system external browser only | owner-only; CSRF; no embedded webview; secrets never returned |
| B8 | Terms consent | terms summary + ack checkbox where a route declares terms | `POST /onboarding/terms` form in `onboarding_api.py` via `connections_service.acknowledge_terms`; existing JSON ack handler reused through the same service; stored digest in `connection_ack:{name}` | `@src/hutch/connections.py:49-58` `Terms.digest`; 430-448 ack status | ack required server-side before a governed run; version change re-asks |
| B9 | Assistant fast path | trim only: `@src/hutch/server/static/app.js:11584-12777` `promptNewBot`, create 12660-12724, advanced 12360+ behind disclosure; entry handoff from onboarding | reuse `POST /api/v1/bots` (`@app.py:4291-4375` `create_bot_v1`, idempotent via `Idempotency-Key` and `store.create_bot_idempotent`) | none new | paired phones are already denied bot creation; Idempotency-Key required (428 when missing) |
| B10 | First request + output | SPA chat composer/stream/approval cards; onboarding completion surface | reuse `POST /api/v1/conversations/{id}/messages` (`@app.py:3587-3717`, idempotent) and run/event streams; completion reads run/conversation | provider used through the existing governed run path | Idempotency-Key required; paired runs limited by `require_remote_start` (`app.py:2041-2065`); approvals are server-side |
| B11 | Phone pairing (optional) | `@app.js:10078-10105` pairing dialog; `@templates/pair.html`; `@static/pair.js` | `@app.py:2771-2800` `/api/v1/pairing/setup`, `/api/v1/pairing/exchange`; `/api/v1/pairing/codes` used by the dialog | WebAuthn/passkey via `@src/hutch/server/passkeys.py` | code expiry/single-use server-side; passkey requires secure context |
| B12 | Marketing entry | `@website/index.html:293-327` hero, 788-845 availability, 336-357 proof, 854-940 FAQ | static files; `@website/downloads.json` | none | n/a (static, no analytics, no account) |
| B13 | Local milestones | setup record + `hutch doctor` output | local-only JSON/read surface; no remote endpoint | none | local owner only; no telemetry |

### 2.3 Existing seams reused exactly (do not duplicate)

- Page helper, flash, redirect, CSRF: `@src/hutch/server/pages.py:99-132` (`page`, `fragment`, `go`, `read_form`); template macros `templates/_form.html:43-139`.
- Page-module registration pattern: `@src/hutch/server/pages_models.py:15-21` `register_model_pages(app, page, go, read_form)`, called from `pages.py:565-566`.
- Browser draft: `@src/hutch/server/static/app.js:132-163` sessionStorage `hutch-first-run-request` (version 1, 20,000 char cap).
- Idempotent commands: `@src/hutch/server/app.py:2295-2301` `idempotency_key`; `store.create_bot_idempotent` `@store.py:3248`; `store.replay_submitted_run` `@store.py:4308`; `engine.submit_idempotent`.
- Persistence: kv table `@src/hutch/store.py:117` and `kv_get/kv_set` `@store.py:11730-11740`, precedent `workspace:model-defaults` `@app.py:4018-4044`.
- Provider readiness: `@src/hutch/providers/connection.py:42-69` (`ConnectionCheck`/`check_connection` - metadata probe only, not a generation).
- Terms: `@src/hutch/connections.py:430-448`; OpenAI/Anthropic/OpenRouter error kinds in `@src/hutch/providers/openai_compat.py:95-130`.
- Auth model: `@src/hutch/server/security.py:84-400` (`SecurityMiddleware`), `@src/hutch/server/app.py:185-232` (`authorize_remote_route`).
- Visual evidence conventions: `@docs/realignment/capture_first_run.py:1-110`, `@tests/e2e/test_design_system.py:36-90`, `@tests/support/artifacts.py:9-18`, gate in `@docs/onboarding/notes/visual-validation.md:84-103`.
- Test harness: `@tests/conftest.py:18` `client`, `@tests/e2e/test_design_system.py:69-90` `app_server`, reopen-store pattern `@tests/test_api.py:467-502`.

### 2.4 New seams introduced by this plan

- `src/hutch/onboarding.py` (new, pure): persisted pydantic `OnboardingSetup`/step-state model, step order, transition decisions, resume/stale decisions. No I/O, no FastAPI means, no filesystem/network. The model lives here rather than `models.py` because `models.py` is at its frozen size cap (section 2.5).
- `src/hutch/server/onboarding_api.py` (new): HTML route + form orchestration only, delegating decisions to `onboarding.py` and persistence to `onboarding_store.py`; installed with one import + one call in `app.py`. Because `pages.py` is over its frozen budget, this module owns a minimal render/redirect/CSRF-parse helper (Jinja2Templates + `check_csrf` from `security.py`, ~25 bounded lines) rather than growing `pages.py`; a later reviewed split task may extract a shared `pagekit` for both surfaces, but that refactor is explicitly out of scope here.
- `src/hutch/onboarding_store.py` (new): setup-record persistence adapter over the existing kv table (`load_setup`, `save_setup_with_revision`). Holds a process lock around read-check-write so the revision compare-and-set is atomic inside the single Hutch server process; rejects stale writes with the current record returned for explicit UI reconciliation.
- Registration seam: `install_onboarding_routes(app)` called from `@src/hutch/server/app.py` next to `register_pages(app)` (`app.py:7243-7248`). No new route registration in `pages.py`. Slice 02 keeps this single two-line seam: `install_onboarding_routes` also calls `install_chooser_routes`, so neither step adds an `app.py` line.
- `src/hutch/onboarding_choices.py` (new in slice 02, pure): route allowlist/labels, `chooser_view`, `choose_route`, `chooser_ready`, chooser state tokens. The request-step domain module stays under its 250-line budget by splitting the chooser domain here, not by growing `onboarding.py`.
- `src/hutch/server/onboarding_chooser_api.py` (new in slice 02): chooser HTML orchestration, installed by `install_onboarding_routes`; no `app.py` line and no new route in `pages.py`.
- `src/hutch/server/onboarding_pagekit.py` (new in slice 02): shared render/flash/redirect/plain-form helpers for both onboarding step modules. This is the bounded "later reviewed split task" for the onboarding surface; it replaces the private helpers that slice 01 kept in `onboarding_api.py` and still does not touch `pages.py`.
- Readiness snapshot contract (slice 03): new `src/hutch/route_readiness.py` (pure) and `ProbeResult` in the same module. Canonical route states are the edge-case-matrix vocabulary (section 4), not a copy of `ProviderError.KINDS`; the pure classifier maps the 14 kinds + HTTP status: auth+401 -> invalid_credential; auth+403 (or upstream policy) -> permission_denied; quota -> no_credit; rate_limit -> rate_limited (retry_after capped); timeout -> timed_out; unreachable -> unreachable; server/stream/oom/refused -> unavailable; bad_request -> invalid_route; model_missing -> model_missing; context/incomplete -> context_or_incomplete; other -> unavailable (with detail, never a bare "error"); metadata-probe success -> saved_unverified; explicit generation-probe success -> verified. Metadata mode never yields verified. `ConnectionCheck.verified` is discarded, not displayed.
- Onboarding artifacts root: `docs/onboarding/artifacts/<slice-label>/` with PNGs plus `validation.json` rows (state, viewport, artifact, verdict, finding, source_commit, reviewer).

### 2.5 Frozen-file and new-file budget (binding on every slice)

The repo guard `scripts/audit_context_hygiene.py` freezes over-cap files (shrink only) and caps every new source file at 400 lines. Current state after slice 02: `app.py` 7,264/7,461 (+197 headroom; slice 02 added no line), `app.js` 14,532/14,532 committed (zero headroom - the slice-02 handoff changed one line in place with net-zero growth; the working tree also carries another session's shrink to 14,373 uncommitted), `models.py` 828/828 (0), `pages.py` 743/731 (already over), `store.py` 12,605/12,593 (already over), `tests/e2e/test_design_system.py` 3,334/3,334 (0; slice-02 assertion updates are line-neutral). The audit reports six pre-existing violations from other sessions/committed state (three over-cap new-module entries - `bot_deletion.py`, `test_bot_deletion.py`, `test_commit_attribution.py` - and three frozen-file growth entries - `cli.py`, `pages.py`, `store.py`); those are baseline, not ours - the slice-02 run added none. Slice-02 actual budgets: `onboarding.py` 247 (<=250), `onboarding_choices.py` 221, `onboarding_pagekit.py` 86, `onboarding_chooser_api.py` 193, `onboarding_api.py` 231, `onboarding_store.py` 100 against the 80-line target (save_route must share the module lock - documented deviation), `onboarding.js` 114 (<=120), `onboarding-chooser.css` 216; tests 303/271/359 lines, all <=400.

Binding rules for this feature:

- Do not add lines to `models.py`, `pages.py`, `store.py`, `cli.py`, or `tests/e2e/test_design_system.py`. Split instead: domain code goes in the pure onboarding modules (`onboarding.py` for the request step, `onboarding_choices.py` for the chooser, `route_readiness.py` from slice 03 for readiness); page/API code in bounded step modules under `src/hutch/server/`; persistence in `onboarding_store.py`; new browser tests in new files under 400 lines.
- `app.py` may grow by at most the two registration lines in slices 01-02; from slice 04 on, the connection handlers may be rewired to `src/hutch/connections_service.py` only with net-zero-or-shrink diffs (stay under its 7,461 baseline) and focused tests. `app.js` edits must stay small and net-neutral where possible (change the first-run CTA target in place). New source files (`.py`, `.js`, hand-written `.css`) must be at most 400 lines; plan budgets keep each new module well under that. `connections.py` (448) and `security.py` (513) are at their frozen caps: use their public functions, do not modify them; `providers/connection.py` (69 lines) may grow within the 400-line cap.
- Every checkpoint records the audit command output and proves this feature added zero new violations. Do not opportunistically "fix" the pre-existing frozen-file violations; that is a separate, reviewed split task.

### 2.6 Lines that must not be crossed

- No provider/network request from the browser for readiness or connection checks; probes run through the Python backend.
- No secret in the database, transcript, URL, logs, or HTML echo; keys stay write-only `0600` files (`connections.py:345-366`).
- No "verified" state without a provider response; a metadata model list is `saved-unverified`, not `verified`.
- No remote analytics, no third-party scripts, no cookie/consent banner added to the app.
- No second assistant-creation path: onboarding reuses `POST /api/v1/bots`; no duplicate create/validation logic inside `onboarding_api.py`.
- No change to `/` SPA routing in slices 01-02 beyond the first-run CTA target; the three pinned e2e first-run tests are updated deliberately, not deleted.

## 3. Code-inspection answers (research open questions)

Resolved from the current working tree; evidence labels [repo]. Items marked UNKNOWN stay assigned to the slice that needs them.

| Q | Answer | Evidence |
|---|---|---|
| 1 | Current first-run is SPA `#/chat` on empty bots; readiness and OpenCode dialog are SPA; assistant setup is SPA `#/assistant/new`; server pages own login/pair/legacy connections/models/approvals. Dedicated onboarding can be a server-rendered route without touching the SPA shell. | `pages.py:191-195`; `app.js:3257-3408`, `1909-1919`, `2214-2262` |
| 2 | Readiness performs no real generation. `check_connection` only proves key presence and lists models and sets `verified=True` on a model-list success (not trustworthy); Anthropic-protocol routes can only prove a key is present. Probe timeouts are 3-10 s, single-shot, no retry. A real generation probe exists only through the governed run path. | `providers/connection.py:50-69`; `openai_compat.py:146-216`; `claude.py:149-195`; `ollama.py:160-170` |
| 3 | Server error taxonomy exists: `ProviderError.KINDS` has 14 kinds - unreachable, timeout, auth, quota, rate_limit, server, bad_request, context, refused, stream, model_missing, oom, incomplete, other - with optional HTTP status, `retry_after`, `partial_content`, and `retryable`. 401 vs 403 is distinguishable only via `ProviderError.status`; probe endpoints flatten this today, so slice 03 builds a structured `ProbeResult` (task-plan 2.4) instead of reusing `ConnectionCheck.verified`. | `providers/base.py:26-62`; `openai_compat.py:97-142`; `ollama.py:121-142` |
| 4 | No server-side onboarding/setup state exists. The only durable client draft is sessionStorage `hutch-first-run-request`; kv has a workspace-defaults precedent but no setup record. | `app.js:132-163`; grep `onboarding` in `store.py`/`app.py` = none |
| 5 | Assistant creation and first send are already idempotent server-side and require an `Idempotency-Key`; replays are detected by scope + request hash and conflict returns 409. | `app.py:2295-2301`, `4291-4375`, `3587-3717`; `store.py:3248`, `4308` |
| 6 | Keys are stored as 0600 files under the state dir or read from an env var, never in SQLite. Terms acknowledgements are kv records keyed by connection name with a notice digest; connections themselves live in `<state>/connections.json`. | `connections.py:345-366`, `430-448`; `docs/runtime-setup.md:6-30` |
| 7 | OAuth/popup return paths exist for OpenCode (start/status/complete/cancel) and Sign in with ChatGPT (loopback callback); OpenCode attempt state is in a single in-process private setup server, so it does not survive a host restart and has no recovery UI. | `app.py:1972-1989`, `7157-7226`; `web:app.js:11387-11582` |
| 8 | OpenCode dialog polls `/api/v1/opencode/oauth/{integration}/{attempt}` while open; closing the dialog discards the wait. Poll interval/expiry is owned by the OpenCode runtime, not by onboarding. | `app.js:11524-11580`; `app.py:7190-7226` |
| 9 | Pairing uses a 14-character single-use code with server expiry (60 s); passkeys require a secure context. No QR/camera path exists. Phone reachability and HTTPS-origin guidance are not surfaced before the attempt. | `app.js:10078-10105`; `templates/pair.html:9-16`; `static/pair.js:27-67`; `security.py` |
| 10 | Local dashboard requests default to owner (loopback) or a passkey session; remote access requires HTTPS and a paired session; paired routes are allowlisted by `REMOTE_ROUTE_CAPABILITIES`; new routes are closed to paired phones until explicitly added. Owner forms require a double-submit CSRF token. | `security.py:300-400`, `506-510`; `app.py:185-232`; `pages.py:126-132` |
| 11 | English-only UI (`<html lang="en">`), ISO-8601 UTC storage, no currency surface; locale/timezone/units edge cases must be tested as formatting/acceptance, not as new locales. | `base.html:3`; `models.py:1-28` |
| 12 | YAML bot import is parsed server-side with a bounded parser; it is an advanced, post-activation path, out of the onboarding critical path. | `app.py:291-350`, `4374-4416` |
| 13 | No shared empty-state component exists; first-run, bots, chats, and connections each have one-off states. Onboarding should reuse the existing first-run copy/CTA patterns rather than invent another visual language. | `app.js:3273-3337`; `templates/home.html:9-13` |
| 14 | Deterministic first-run fixtures exist only for 200/503 readiness responses. No 401-generation, timeout, offline, expired-pairing, or popup-blocked fixture exists. | `tests/e2e/test_design_system.py:748-1014`; `docs/realignment/capture_first_run.py:68-73` |
| 15 | UNKNOWN until implementation: Tauri host origin/webview differences for OAuth loopback callbacks, passkeys, and pairing. Must be checked in slice 06/10; do not claim desktop parity. | open question, assigned |
| 16 | Visual captures are Chromium/Linux only unless another engine is captured. Firefox/WebKit readiness is unverified; evidence must say so. | `docs/onboarding/notes/visual-validation.md:118-126`; repo convention |
| 17 | No telemetry/event log specific to activation; run/event storage and `hutch doctor` exist. Activation milestones stay local, derived from setup record + existing run history; no remote endpoint. | `docs/marketing-site.md:1-8`; `store.py` events/runs |
| 18 | Legacy server pages are still reachable (`/legacy/connections`), while `/connections` redirects into the SPA. A first-run user can reach two different connection surfaces, so onboarding must deep-link one canonical step and not the legacy page. | `pages.py:599-612`; `app.js:9466` |
| 19 | There is no explicit offline/local-server-down state in first run; the SPA shell shows a loading state if boot requests fail. Slice 03 adds the client-shell `net.offline` / `server.unreachable` state on the onboarding route (browser online events + fetch failure + retry); slice 09 gates it across the flow. A server-rendered page cannot render itself when the local server is down, so the state is client-shell owned, not invented on the server. | `app.js:13371-13387`; `static/index.html:138-143` |
| 20 | First-run copy does not link to `docs/runtime-setup.md`; prerequisites are assumed. The onboarding local-service and OpenCode steps must link the runtime docs and state prerequisites before the action. | grep first-run copy; `docs/runtime-setup.md:1-30` |
| 21 | `website/site.js` does not consume `website/downloads.json`; the site render is static and sends no analytics. The manifest is linked at `website/index.html:8` and lists four platforms with empty `artifacts`. Any install wording must stay honest. | `website/site.js` (159 lines); `website/downloads.json`; `website/index.html:8`, `788-845` |
| 22 | No welcome-back banner exists in the app or site; the first-run page is the only welcome. Do not invent one. | grep "Welcome back"; `website/site.js` |

## 4. Slice decomposition

Each slice is one user outcome with ordered steps; each step is one primary task and one commit. Slice size respects the repo 3-file / 1-seam rule where possible; where a slice crosses it (state seam + page route), the extra files are one persistence seam and one template, listed explicitly in the brief. No step introduces a function over ~40 logical lines or mixes validation, persistence, rendering, and navigation.

| Slice | Primary user outcome | Steps (one primary task per step) | Key files/functions | Depends on |
|---|---|---|---|---|
| 01 | A first-run owner can open a dedicated `/onboarding` page, write the request they want answered, and resume the same step and request after refresh or restart; stale/expired/damaged stored state is named, not silently reused. | 01a setup record + pure transitions (incl. `resume_expires_at` TTL); 01b revision-safe kv adapter; 01c chrome-less route + form; 01d save/replay/stale/expired render + visual evidence | `src/hutch/onboarding.py` (new), `src/hutch/onboarding_store.py` (new), `src/hutch/server/onboarding_api.py` (new), `src/hutch/server/app.py` (+2 registration lines), `@src/hutch/server/templates/base.html`, `templates/onboarding.html` (new), `static/onboarding.css` (new), new tests (each <=400 lines) | CP0 |
| 02 | The empty chat's one action now lands on the onboarding request step (no longer the Apps & AI catalog); the saved request hands off to an in-context AI-service chooser with three routes, one recommended, apps/devices explicitly deferred, and the request still there. | 02a chooser contract + route state; 02b chooser page; 02c SPA handoff (`/onboarding` only) + draft bridge; 02d back/forward + visual evidence | `@src/hutch/onboarding.py:37-52`, `src/hutch/onboarding_choices.py` (new), `src/hutch/server/onboarding_pagekit.py` (new), `src/hutch/server/onboarding_chooser_api.py` (new), `src/hutch/server/onboarding_api.py`, `@src/hutch/server/templates/onboarding_ai_service.html` + `_onboarding_route_form.html` (new), `src/hutch/server/static/onboarding-chooser.css` (new), `src/hutch/server/static/onboarding.js`, `@src/hutch/server/static/app.js:3356-3386` (one line in place), `tests/e2e/test_design_system.py:748-1014` (line-neutral assertion updates) | CP1 |
| 03 | Every route choice shows why it is or is not usable, in words: checking, saved-unverified, verified, invalid credential, no credit, rate-limited, unreachable, permission denied, timed out, offline/server-down - each with reason and retry/switch. | 03a structured readiness snapshot contract (`ProbeResult` + state classifier); 03b provider probe policy + fake-provider fixtures; 03c readiness panel states; 03d polling/retry + client-shell offline/server-unreachable state; 03e visual evidence | `src/hutch/route_readiness.py` (new, pure `ProbeResult` + classifier; CP3 brief 03a), `src/hutch/server/onboarding_readiness_api.py` (new, installed via the existing two-line registration seam), `@src/hutch/providers/connection.py`, `@src/hutch/providers/base.py`, `templates/_onboarding_readiness.html` (new), `static/onboarding-readiness.js`, fixtures/tests | CP2 |
| 04 | A hosted API key can be pasted, saved, and explicitly verified with honest wording (saved vs verified), with provider terms acknowledged and 401/402/403/429/5xx recovery copy. | 04a extract `src/hutch/connections_service.py` (key trim/4 KiB validation, probe, terms ack) and rewire `app.py:7055-7143` JSON handlers to it with net-zero-or-shrink diffs; 04b secret input + terms onboarding step; 04c structured-probe error taxonomy copy + retry; 04d visual evidence | `src/hutch/connections_service.py` (new), `src/hutch/route_readiness.py` (from slice 03), `src/hutch/server/onboarding_hosted_key_api.py` (new), hosted-key template, `@src/hutch/connections.py:247-366,432-448` (read-only, frozen), `@src/hutch/server/app.py:7055-7149` (net-zero-or-shrink handler delegation) | CP2 |
| 05 | A local model service URL can be entered, probed server-side, and shows unreachable vs no-model vs timed-out vs ready, with the exact start/pull command. | 05a server-side local probe; 05b URL normalization/validation; 05c local-service step copy/states; 05d visual evidence | `@src/hutch/connections.py:150-180`, `@src/hutch/providers/openai_compat.py`, `@src/hutch/providers/ollama.py`, `@src/hutch/server/onboarding_api.py`, local-service template | CP2 |
| 06 | External login (OpenCode/OAuth) shows a truthful waiting state with countdown, cancel, retry, open-browser-again, survives reload, and recovers from expired/replayed/popup-blocked codes. | 06a attempt record in setup state; 06b waiting/recovery UI + bounded polling; 06c reload/expiry/cancel handling; 06d system-browser-only check + visual evidence | `@src/hutch/server/onboarding_api.py`, `@src/hutch/runtime/opencode_server.py` (reuse routes `@app.py:7157-7226`), external-login template, `@static/onboarding.js` | CP2 |
| 07 | Assistant setup is reduced to name, instructions, route, Create; advanced controls stay optional; carried request survives; double-submit/refresh-resubmit creates exactly one assistant. | 07a fast-path trim in SPA assistant setup; 07b onboarding entry handoff with carried request; 07c idempotency/duplicate guard verification; 07d visual evidence | `@src/hutch/server/static/app.js:11584-12777` (`promptNewBot`), advanced controls 12360+, create 12660-12724; onboarding completion link; `@tests/e2e` idempotency tests | CP3, CP4 |
| 08 | The first request runs to useful output through the governed run path; timeouts/partial/failure are explicit; at least one approval is shown and decided where needed; completion shows the resulting assistant/workspace and the next product action. | 08a first-send wiring + timeout/partial states; 08b approval introduction copy/context; 08c completion surface; 08d activation milestone record + visual evidence | SPA chat/stream/approval surfaces, `@src/hutch/server/app.py:3587-3717`, onboarding completion template, setup record milestones | CP5 |
| 09 | The whole onboarding flow survives a phone keyboard, screen readers, keyboard-only use, 200 percent zoom, forced colours, reduced motion, offline/local-server-down, without focus being obscured. | 09a visual-viewport/sticky-action layout; 09b live-region/focus management audit+fix; 09c keyboard-only completion; 09d client-shell offline/server-unreachable states (`net.offline`, `server.unreachable`) + retry; 09e full visual gate | `@src/hutch/server/static/onboarding.css`, `@src/hutch/server/templates/onboarding*.html`, `@src/hutch/server/static/app.js` first-run/assistant focus points, CSS sources | CP5 |
| 10 | Phone pairing (optional) shows a live countdown, regenerate, single-use enforcement, and the passkey secure-origin requirement before the attempt. | 10a countdown/regenerate UI; 10b expiry/reuse state; 10c secure-context copy; 10d visual evidence | `@src/hutch/server/static/app.js:10078-10105`, `@src/hutch/server/templates/pair.html`, `@src/hutch/server/static/pair.js`, pairing API `@app.py:2771-2800` | CP5/CP6 (optional; may be deferred with explicit note) |
| 11 | Marketing claims match onboarding reality, docs are current, the final visual gate passes, and the code is reviewed against this plan. | 11a marketing boundary changes; 11b docs updates; 11c final visual validation evidence; 11d code review + gate sign-off | `@website/index.html`, `@website/downloads.json`, `@website/site.js` (read-only unless needed), `@docs/runtime-setup.md`, `@docs/design-system.md`, `@docs/marketing-site.md`, this plan, [marketing-changes.md](marketing-changes.md), [review-checklist.md](review-checklist.md) | CP6 |

Dependent slices never start before the previous checkpoint passes. Slices 04-06 are independent of each other after CP2 but share the chooser/readiness contract; 04 and 05 can run in parallel if file scopes stay disjoint (each owns its own template and wrapper route; both may touch `onboarding_api.py`, so coordinate one writer at a time or sequence them).

### 4.1 Implementation status

| Slice | Status | Checkpoint | Evidence |
|---|---|---|---|
| 01 | ACCEPTED 2026-10-29 | CP1 PASS | [acceptance record](slices/slice-01.md#15-acceptance-record-cp1), [evidence + verdicts](evidence/slice-01/README.md), [validation rows](evidence/slice-01/validation.json) |
| 02 | IMPLEMENTED at CP2 2026-10-29 | CP2 PASS | [acceptance record](slices/slice-02.md#15-acceptance-record-cp2), [evidence + verdicts](evidence/slice-02/README.md), [validation rows](evidence/slice-02/validation.json) |
| 03 | BRIEF APPROVED 2026-10-29 (next implementation slice) | CP2 -> CP3 | [slice-03 brief](slices/slice-03.md), [continuation prompt](continuation-prompt-03.md) |
| 04-11 | 04 BRIEF APPROVED; 05-11 PLANNED | - | [slice-04 brief](slices/slice-04.md); slice-05/06 briefs owed before CP4 |

## 5. Checkpoints

A checkpoint is a gate, not a status report. "Evidence" means committed files under `docs/onboarding/artifacts/`, test output pasted in the checkpoint note, and a diff scoped to the listed files. Missing evidence is FAIL, not partial.

### CP0 - Planning gate (current)

Passes when:
- This plan, [edge-case-matrix.md](edge-case-matrix.md), [marketing-changes.md](marketing-changes.md), and [review-checklist.md](review-checklist.md) exist and are reviewed.
- `docs/onboarding/slices/slice-01.md` and `slice-02.md` each name exact files/functions with @ anchors, list the API/form contract, and contain a rollback plan.
- Research open questions are either answered in section 3 or assigned to a slice; no question is silently ignored.
- No production code changed; `git status` shows only planning docs plus the pre-existing other-session work (which must not be touched).

Evidence required: the six artifacts above, an independent review record (reviewer name/date and finding-to-resolution table in section 9 of this file), `docs/onboarding/artifacts/planning-baseline.txt` containing the `git status --porcelain` and `git diff --stat` snapshot (including `app.py`, `app.js`, `base.html`, `connections.html`, `pair.html`, `tests/e2e/test_design_system.py`, `website/index.html`, `docs/design-system.md`), a diff check proving no `src/`, `tests/`, or `website/` file changed by this planning work, and the recorded context-hygiene/lint baseline so later checkpoints can prove this feature added no new violation.

Before CP1 may start: slice-01 and slice-02 briefs approved; the context-hygiene baseline is recorded (`python3 scripts/audit_context_hygiene.py` at CP0 reported six pre-existing violations from other sessions/committed state; concurrent other-session work added one more during slice 01 - the recorded baseline plus later concurrent changes are not caused by this work and must not grow from this feature); focused baseline tests green (`npm run test:agent -- tests/test_api.py tests/test_migration.py`); the other session's `base.html`/`app.js` changes either landed or are explicitly coordinated (rebase before edit).

### CP1 - Slice 01 accepted (foundation: dedicated route + server-owned resume)

Status: PASS, 2026-10-29. Evidence: `tests/test_onboarding_state.py` + `tests/test_onboarding_page.py` = 56 passed; live Chromium capture test = 1 passed writing 63 PNG rows (every required state at 320/375/768/1440 plus forced colours, reduced motion, 200 percent text scale, keyboard focus, light-preference and non-Latin rows); `docs/onboarding/evidence/slice-01/validation.json` = 63 APPROVED / 0 NEEDS WORK (every image opened; pointer copy in `artifacts/slice-01/`); an independent fresh-context review returned NEEDS WORK on the evidence trail/five code details and every finding is resolved in the slice brief section 15 (state-gated reset, installer split, resume announcement, path normalisation, exact audit attribution); `python3 scripts/audit_context_hygiene.py` at final CP1 verification reports exactly the six CP0-baseline findings with no onboarding file in the violation list (an intermediate run during the slice showed concurrent other-session drift that later reverted - see section 9b for the exact delta); `app.py` grew by exactly the two registration lines; `models.py`, `pages.py`, `store.py`, `security.py`, `connections.py` and the pinned e2e file were not touched; reviewer sign-off in the slice brief. Deviations recorded in the slice brief: the evidence directory is `docs/onboarding/evidence/slice-01/` (the execution directive for this run) instead of `artifacts/slice-01/` with a pointer copy kept; a `tests/conftest.py` `client` fixture anchor in the planning draft does not exist, so tests construct `TestClient(create_app())` directly like existing page tests; the page ships its own field partial/styles because the shared form macro tier is another session's uncommitted work; the page opts into a same-origin referrer to work around the pre-existing `Origin: null` plain-form-POST boundary.

Passes when: `GET /onboarding` renders a chrome-less, accessible first step at 320/375/768/1440; the request is saved server-side and survives a process restart and a second tab; a stale `requirements_version` produces an explicit stale-resume state instead of a false resume; duplicate form submits replay rather than duplicate; missing/invalid CSRF returns 403; a paired-phone session cannot read or mutate the setup record; `/` and all three pinned first-run e2e tests are unchanged and green.

Evidence required: `tests/test_onboarding_state.py` and `tests/test_onboarding_page.py` output; reopened-store test proving persistence; `docs/onboarding/evidence/slice-01/validation.json` (canonical; pointer copy under `docs/onboarding/artifacts/slice-01/`) with APPROVED open-image verdicts for empty, saved, resumed, stale, validation-error, long non-Latin request, 200 percent zoom, keyboard focus, forced colours, reduced motion at the four required widths; `docs/design-system.md` "Setup recovery boundaries" update; `python3 scripts/audit_context_hygiene.py` output showing zero new violations and no growth of `models.py`, `pages.py`, `store.py`, or the pinned e2e test file; a reviewer sign-off line in `docs/onboarding/slices/slice-01.md`.

Before CP2 may start: slice 01 committed and reviewed (done); slice-02 brief refreshed and continuation prompt written (done); slice-03/04 briefs written and approved (done - section 15 of each brief); no P1 defect open; no drift in `base.html` chrome blocks. All met for the slice-02 gate.

### CP2 - Slice 02 accepted (entry handoff + chooser)

Status: PASS, 2026-10-29. Evidence: fast lane `tests/test_onboarding_chooser_state.py` + `test_onboarding_chooser.py` + `test_onboarding_page.py` + `test_onboarding_state.py` = 105 passed; live Chromium capture test = 1 passed writing 57 PNG rows (chooser default/recommended/chosen/change/invalid/stale/conflict/forbidden/no-request/saving at 320/375/768/1440 plus forced colours, reduced motion, 200 percent text scale, keyboard focus and OS light preference at all four widths, plus the 375x812 SPA handoff before/after); the pinned first-run e2e tests updated in place stay green (3 passed) and the pinned file stays at 3,334 lines; `docs/onboarding/evidence/slice-02/validation.json` = 57 APPROVED / 0 NEEDS WORK (every image opened, the layout fix recaptured and re-reviewed, and the saving row opened separately; pointer copy in `artifacts/slice-02/`); the empty-chat no-route action now lands on `/onboarding` with the typed request restored from the tab draft, and the saved request's one primary action opens `/onboarding/ai-service`; choosing a route persists across reload and Back/Forward; no provider/localhost/external request is made; `python3 scripts/audit_context_hygiene.py` reports the six pre-existing baseline entries with no onboarding file, and `app.js` did not grow (14,532-line frozen baseline, one line changed in place). Deviations, the independent-review findings and their resolutions, and the reviewer sign-off are recorded in the [slice-02 acceptance record](slices/slice-02.md#15-acceptance-record-cp2). The CP1 -> CP2 planning precondition is closed by the approved slice-03/04 briefs.

Passes when: the empty-chat no-route action lands on `/onboarding` (request step) with the written request preserved; the saved request's single primary action opens `/onboarding/ai-service`; the chooser names exactly three routes, marks one recommended, defers apps/devices in words, and offers the real next action; choosing a route persists and survives back/forward and reload; no provider call is made; the updated e2e first-run tests assert the new destination and remain green; the site still links only to the honest source path (no new claim).

Evidence required: e2e chooser captures at 320/375/768/1440 plus keyboard-only pass; `validation.json` APPROVED rows; updated `tests/e2e/test_design_system.py` assertions with output; copy audit showing no "download", "sign up", "free forever", or account language in the chooser.

Before CP3 may start: slice-03 brief approved (done); CP2 PASS recorded (done); readiness contract table (states, reasons, next actions) reviewed and the fixture plan for 401/timeout/offline approved as part of slice 03's implementation review.

### CP3 - Slice 03 accepted (readiness truth)

Passes when: each route state is distinct and testable with deterministic fixtures (checking, saved-unverified, verified, invalid-credential, no-credit, rate-limited, unreachable, permission-denied, timed-out); no state is produced from a failed check alone; no provider call happens from the browser; retry/switch actions are present; the panel announces state changes without focus theft; the fake-provider fixture set includes a 200-model-list/401-generation route.

Evidence required: fixture-based pytest for the state mapping; e2e captures for each state (desktop + one phone width); response-time/1 s feedback and >10 s estimate evidence; no secret in rendered HTML (grep assertion); CP3 note.

Before CP4 may start: slice-04/05/06 briefs approved with disjoint file scopes; connection-step copy reviewed for terms/credential honesty.

### CP4 - Slices 04-06 accepted (connections)

Passes when: hosted key, local service, and external login each have their own step; saved vs verified is never conflated; keys never echo; terms version and timestamp are persisted and re-asked only on change; local probe distinguishes unreachable vs no-model vs timeout server-side; external wait has countdown, cancel, retry, open-again, survives reload, and handles expired/replayed/popup-blocked; all provider fixtures use real-world payloads (401/402/408/429/5xx, long multi-line error, whitespace/Bearer-prefixed key, non-Latin key label).

Evidence required: per-slice pytest and e2e evidence with APPROVED captures; redaction grep; reload-during-wait capture; retry-after copy screenshot; CP4 note.

Before CP5 may start: slices 07/08 briefs approved; assistant-create and first-send idempotency test plan approved.

### CP5 - Slices 07-08 accepted (first value)

Passes when: assistant fast path creates exactly one assistant on double-submit and refresh-resubmit; advanced controls are optional/deferred; the carried request is preserved in the created assistant's first conversation; the first request produces output through the governed path; timeout/partial/approval cases are explicit; completion shows the created assistant, the confirmed route, the first output, and next product actions (open chat, connect an app, schedule) - no generic celebration; a local activation milestone set is recorded and readable locally.

Evidence required: double-submit/refresh-resubmit test; first-output capture with at least one approval; timeout/partial capture; completion capture at four widths; proof no remote analytics request in browser network log; CP5 note.

Before CP6 may start: slices 09/10 briefs approved; full required-states list for CP6 enumerated (visual-validation note section 4) with owners.

### CP6 - Slices 09-10 accepted (hardening and optional pairing)

Passes when: keyboard-only completion, screen-reader announcements, 200 percent zoom, 320 reflow, forced colours, reduced motion, sticky-action/keyboard-open behaviour, and focus-not-obscured pass at required widths; the pairing countdown/regenerate/secure-context copy is truthful and single-use enforcement is tested; optional pairing can be skipped and resumed; no regression in adjacent SPA flows.

Evidence required: the full CP6 capture matrix with APPROVED verdicts; keyboard-only transcript; live-region assertions; pairing expired/reused/reachable-failure captures; adjacent-flow focused tests; CP6 note.

Before CP7 may start: all shipped slices' docs merged; marketing change list frozen; final visual matrix enumerated; code-review owners assigned and independent reviewer named.

### CP7 - Final checkpoint: marketing, docs, visual validation, code review

Passes when:
- Marketing-site changes from [marketing-changes.md](marketing-changes.md) are live in source with owners' acceptance criteria met; no dead download CTA, no fabricated social proof, no pricing/card/account claim; no "Welcome back" copy on the marketing site or on a first run (in-app returning copy is allowed only after a completed-session marker); availability and support/date claims are truthful; trust row adjacent to the entry includes MIT, source repo, issue tracker, data-flow note, preview status.
- Docs updated: this plan status, `docs/runtime-setup.md` (prerequisites now linked from onboarding), `docs/design-system.md` (setup recovery boundaries, onboarding states), `docs/marketing-site.md` (any changed claim), [edge-case-matrix.md](edge-case-matrix.md)/[review-checklist.md](review-checklist.md) results, slice briefs archived with implemented anchors.
- Visual validation: the required state/viewport matrix (research section 6.3-6.4 + visual notes section 4) is captured, opened, and judged APPROVED; missing state = FAIL; limitations recorded (Chromium/Linux, no real phone/keyboard).
- Code review: [review-checklist.md](review-checklist.md) is fully signed; no god functions (`src/hutch/onboarding.py` pure, page handlers orchestrate only); server-side authorization on every privileged onboarding step; idempotent provider webhooks/duplicate-safe saves verified; edge-case tests use real-world data; accessibility checks pass; no regressions in adjacent flows; docs and marketing updated; rollback plans exercised or reviewed.
- The activation definition is met end-to-end on a fresh state directory.

Evidence required: a final `docs/onboarding/artifacts/final/` bundle with `validation.json`; marketing screenshots at 375/768/1440 with dated availability; link-check output; docs diff; review checklist sign-off; focused test + e2e command output; a rollback rehearsal note for the setup record and the marketing copy.

## 6. Test and evidence strategy

- Fast lane (pre-PR): focused pytest only - `npm run test:agent -- tests/test_onboarding_state.py tests/test_onboarding_page.py ...`, and the static audits (`python3 scripts/audit_context_hygiene.py` plus the rest of `npm run check:agent`; the seven pre-existing violations are recorded baseline, and this feature must add none). No Playwright in the fast lane.
- Visual lane: real app from source with deterministic fixtures; baseline-first capture; open every image and give a binary verdict; evidence under `docs/onboarding/artifacts/<slice>/`; only after APPROVED may `toHaveScreenshot` be added for approved states (Chromium/Linux, fixed clock, animations disabled, masks limited to dynamic regions).
- Deterministic fixtures required per slice: fake provider returning 200 on model list and 401 on generation; 402 no-credit; 408/429 with Retry-After; 503 long multi-line error; unreachable TCP; slow/hung response; local service with one model/zero models/not running; OpenCode not installed/unauthenticated/ready; expired pairing code; second tab; server restart; offline after load.
- Real-world data: CJK/accented/60-character assistant names and request text, long provider error strings, key with trailing newline/Bearer prefix, 320x740 and 375x812 viewports, 200 percent zoom, forced colours, reduced motion.
- No live provider account, key, or external service is used in tests; no live call in the planning or evidence phase.

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| `base.html` and `app.js` carry another session's uncommitted brand changes | Rebase/re-read before editing; add blocks/chrome flag additively with default-true; do not reformat; if conflict, pause and coordinate rather than overwrite |
| Server pages do not load SPA CSS (`ui.css`/`studio.css`), so first-run classes cannot be reused | New hand-written `static/onboarding.css` using the server-page token tier; visual gate catches parity gaps; do not copy generated CSS |
| Three pinned first-run e2e tests and `capture_first_run.py` pin current SPA behavior | Slice 02 updates assertions and capture script deliberately; slice 01 keeps `/` untouched; no test deletion |
| Provider variability makes "verified" dishonest or flaky | Default to metadata probe = saved-unverified (`ConnectionCheck.verified` discarded); explicit tiny generation probe only when the owner asks; map `ProviderError.KINDS` explicitly through the `route_readiness` classifier; fixtures, never live calls in CI |
| Another session's dirty `app.py`/`app.js`/templates/pinned e2e collide with this feature | CP0 records the git baseline; edit only targeted hunks; never run `git checkout`/clean on those files; rebase and re-read anchors; app.py changes limited to registration plus net-zero-or-shrink handler delegation |
| Setup record becomes a second source of truth beside browser drafts | Server record is authoritative; browser draft is a cache only; resume reconciles and names stale data |
| Scope creep to a separate funnel or hosted signup | Research decision: PARTIALLY REQUIRED; dedicated routes inside the dashboard only; review checklist rejects a new build/app origin |
| Marketing over-claims (free forever/no card/download) | Marketing change inventory required at final checkpoint; binary entry-surface checklist; dated availability |
| Parallel writers touching `onboarding_api.py` | Slices 04-06 sequenced or file-scoped one writer at a time; task board write scopes enforced |
| Frozen source files (`models.py`, `pages.py`, `store.py`, pinned e2e file) cannot grow | All new code goes into new budgeted modules; registration is two lines in `app.py`; audit command run at every checkpoint; pre-existing violations recorded as baseline |
| New source files must stay under 400 lines | Plan budgets: `onboarding.py` <=250, `onboarding_store.py` <=80, `onboarding_api.py` splits at ~300; new tests split by concern |
| Chromium/Firefox submit plain form POSTs with `Origin: null` because the global response header is `Referrer-Policy: no-referrer`, and the existing same-origin guard refuses that; server-rendered forms would be unusable in the browser | Already-recorded pre-existing boundary (`tests/e2e/test_route_state_boundaries.py`, row `form-post-origin-null`). Slice 01 mitigates it only for its own page with `<meta name="referrer" content="same-origin">` (same-origin referrer only) and keeps the guard untouched; the broader fix belongs to the security surface owner and is carried in the matrix and continuation prompt. Do not weaken `_same_origin`. |
| Accessibility regressions | Per-slice capture of required states; CP6 full gate; keyboard-only completion required, not inferred |

## 8. Gate conditions for implementation

Implementation may start only when CP0 passes. At minimum:

1. This plan and the other planning artifacts (edge-case-matrix.md, marketing-changes.md, review-checklist.md, slices/slice-01.md, slices/slice-02.md) exist under `docs/onboarding/` and are linked from this file.
2. `docs/onboarding/slices/slice-01.md` and `slice-02.md` each contain exact @file/function anchors, a front-end/back-end boundary per step, an API/form contract, edge cases in scope, visual-validation evidence required, and a rollback plan.
3. The edge-case matrix names every required category and does not collapse provider-unavailable, permission-denied, offline, or stale-resume into a generic error.

## 9. Planning review and audit records

The CP0 planning review and its finding-to-resolution table live in
[planning-review-2026-10-29.md](artifacts/planning-review-2026-10-29.md); the
pre-implementation git baseline is
[planning-baseline.txt](artifacts/planning-baseline.txt). The slice-03 and
slice-04 briefs were approved at the slice-02 gate (section 15 of each brief), so
the CP1 -> CP2 planning precondition is closed. The two P1 decisions raised by
those briefs (explicit generation probe vs governed-run usage accounting; legacy
JSON `verified` compatibility) are expressly deferred to their own checkpoints
and are cross-referenced in edge-case-matrix section 8.

### 9b. Context-hygiene and audit baseline

Baseline recorded at CP0: six pre-existing violations (over-cap modules from
earlier sessions and frozen-file growth from other work). Slice-01's final CP1 run
reported the same baseline with no onboarding file. Slice-02 CP2 verification,
2026-10-29 - exact commands and results:

- `python3 scripts/audit_context_hygiene.py` -> `Context hygiene violations (6):` the six recorded baseline entries (`bot_deletion.py`, `test_bot_deletion.py`, `test_commit_attribution.py` over 400 lines; `cli.py`, `pages.py`, `store.py` frozen-file growth). No onboarding file appears, so slice 02 added no violation. `app.js` is at its frozen 14,532-line baseline and the handoff edit was one line in place (net-zero); `tests/e2e/test_design_system.py` stayed at 3,334.
- `python3 scripts/audit_emoji.py` -> clean (9,814 files scanned, 50 waivers).
- `.venv/bin/python scripts/audit_tool_contracts.py` -> passed (40 registered tools).
- `.venv/bin/python scripts/audit_constitution.py` -> passed (3 roles, 14 rules).
- `.venv/bin/python scripts/generate_agent_map.py --check` -> passed after a local regeneration; `.ai/repo-map.generated.md` is git-excluded and is not a committed deliverable.
- `npm run check:agent` could not run in this environment: the shared uv cache is read-only (`error: Could not acquire lock ... /home/kevina/.cache/uv`), so the four audits above were run directly with the project venv. Re-run `npm run check:agent` on a normal workstation before merging.