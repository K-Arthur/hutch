# Phase 3 design: inbound webhooks and event triggers (G04)

Status: design written before implementation. Requirement ids are in
`03-REQUIREMENTS-AND-DECISIONS.md` (POW-R9..POW-R14); failure ids are in
`02-FAILURES-AND-COMPLAINTS.md` (POW-F18..POW-F20); primary sources are in
`01-SOURCES.md` (C8, C9).

## 1. Online research & failure mining (2026-11-06)

### Sources & findings
- **C8 (Hooklistener 2026-09-26):** Webhook providers (GitHub, Stripe, Shopify) guarantee
  at-least-once delivery; retries on transient network failures or timeout spikes mean
  duplicate delivery is guaranteed. The receiver MUST deduplicate atomically on the
  idempotency/event key in the same transaction as run admission, returning HTTP 200 on
  duplicates so providers do not amplify retry storms.
- **C9 (AppSec Brief 2026-08-14):** Four security pillars: cryptographic authenticity
  (HMAC/token comparison in constant time via `hmac.compare_digest`), replay resistance,
  body size caps (64 KB before parsing to prevent parser DoS/memory thrashing), and
  zero-downtime dual-secret rotation (retiring secrets remain valid during an overlap window).
- **OWASP & Webhook Best Practices (2026):** Reject unsupported MIME types before parsing
  (allow only `application/json` and `text/plain`; return 415); reject bodies > 64 KB with
  HTTP 413; enforce loopback/private interface isolation by default.
- **n8n Community Issues (2026):** Parallel unthrottled webhook ingestion causes event-loop
  thrashing and container crashes (OOM / exit 137); self-triggering loops between webhooks
  and automated actions require strict rate limiting (`max_per_hour` and `cooldown_seconds`)
  and untrusted-content screening via `ingest.py`.

### Requirements mapping
- `POW-R9`: One-time secret generation, SHA-256 hash at rest, timing-safe verification,
  dual-validation window on rotation.
- `POW-R10`: 64 KB payload byte cap (413), MIME validation (`application/json` | `text/plain`, 415),
  no partial parsing.
- `POW-R11`: Atomic idempotency key claim in admission transaction; duplicate returns 200 without
  new run; crash-after-claim safety.
- `POW-R12`: Admission to durable run/task inbox; paused source / workspace paused returns 409;
  rate/cooldown limit stops self-trigger loops; loopback warning.
- `POW-R13`: Ingest scanning via `src/hutch/ingest.py`; payload annotated as untrusted; no auto-approval.
- `POW-R14`: Management UI under Scheduled work showing delivery log, pause/resume, secret rotation,
  and network exposure warning.

## 2. Task split & targets (3-File / 1-Seam rule)

### Task 3A - Webhook schema, storage & receiver engine

**Source targets (3 files):**
1. `src/hutch/webhook_schema.py` (new, <400 lines):
   - Table `webhook_sources`: `(id, bot_id, name, token_prefix, token_hash, prev_token_prefix, prev_token_hash, prev_token_expires_at, prompt_template, workflow_id, cooldown_seconds, max_per_hour, enabled, revision, last_delivery_at, last_success_at, last_error, error_count, created_at, updated_at)`.
   - Table `webhook_deliveries`: `(id, source_id, idempotency_key, status, status_code, error_message, payload_bytes, payload_sha256, content_type, run_id, received_at, processed_at, client_ip)`.
   - Indexes on `(bot_id)`, `(source_id, received_at)`, and unique index on `(source_id, idempotency_key)` where `idempotency_key != '' AND status = 'processed'`.
   - Migration function `migrate(db)` registering as migration 94.
2. `src/hutch/webhook_receiver.py` (new, <400 lines):
   - `admit_webhook(store, token, raw_body, content_type, idempotency_key, client_ip, now)`:
     - 64 KB payload cap check -> HTTP 413 (`PayloadTooLarge`).
     - Content-Type check (`application/json`, `text/plain`) -> HTTP 415 (`UnsupportedMediaType`).
     - Token lookup and constant-time match against `token_hash` or `prev_token_hash` (if `prev_token_expires_at > now`) -> HTTP 401 (`InvalidWebhookToken`).
     - Source enabled / workspace schedule pause check -> HTTP 409 (`WebhookSourcePaused`).
     - Rate limit (`max_per_hour`) and cooldown (`cooldown_seconds`) check -> HTTP 429 (`RateLimitExceeded`).
     - Atomic idempotency check in `store._tx()`: if already processed, record duplicate delivery and return 200 with `duplicate: true`.
     - Untrusted content scan with `ingest.assess` and `ingest.annotation`.
     - Template rendering into prompt; submit Task and Run (`submit_run`); update delivery to `processed` and update source stats.
3. `src/hutch/webhook_store.py` (new, <400 lines):
   - Helper queries for CRUD, secret generation, secret rotation, pause/resume, delivery history, and CAS revision enforcement.

**Cross-cutting seam (1 file):**
- `@src/hutch/store.py`:
  - Line 37: append `, webhook_schema` to the existing import line (0 line growth).
  - Line 2453: append `, webhook_schema.migrate` to `_MIGRATIONS` (0 line growth).

### Task 3B - Webhook API, management UI & live verification

**Source targets (3 files):**
1. `src/hutch/server/webhooks_api.py` (new, <400 lines):
   - `POST /api/v1/webhooks/{token}` (unauthenticated public ingress for webhooks).
   - `GET /api/v1/webhook-sources` (list webhook sources, optionally filtered by `bot_id`).
   - `POST /api/v1/webhook-sources` (create webhook source; returns raw token ONCE).
   - `GET /api/v1/webhook-sources/{id}` (get single source details; prefix only).
   - `PUT /api/v1/webhook-sources/{id}` (update name, template, limits with CAS revision).
   - `POST /api/v1/webhook-sources/{id}/rotate-secret` (rotate token; returns new raw token ONCE; 24h dual window).
   - `POST /api/v1/webhook-sources/{id}/pause` and `.../resume`.
   - `DELETE /api/v1/webhook-sources/{id}`.
   - `GET /api/v1/webhook-sources/{id}/deliveries` (list recent deliveries).
2. `src/hutch/server/static/webhooks.js` (new, <400 lines):
   - Inbound Webhooks management card on `#/schedules`:
     - List active/paused webhooks with delivery status badges.
     - Create webhook modal showing raw secret once with copy button and warning.
     - Rotate secret confirmation dialog showing 24h dual-validation window warning.
     - Delivery log drawer/disclosure showing payload size, status, client IP, idempotency key, run link.
     - Loopback and network exposure warning banner.
3. `src/hutch/server/static/index.html`:
   - Add `<script src="/static/webhooks.js" defer></script>` (line 218).

**Cross-cutting seam (1 file):**
- `@src/hutch/server/app.py`:
  - Line 80: import `register_webhook_routes`.
  - Line 3209: call `register_webhook_routes(app, store, bot_or_404)` replacing empty line (0 line growth).

## 3. Verification & test strategy
- Focused unit and contract tests in `tests/test_webhooks.py`:
  - Secret shown once, hashed at rest, constant-time verification (`POW-R9`).
  - Dual-window secret rotation accepting old and new tokens (`POW-R9`).
  - 65 KB payload returns 413, unsupported MIME returns 415 (`POW-R10`).
  - Idempotency replay with same key returns 200 without creating second run (`POW-R11`).
  - Paused source and paused workspace return 409 (`POW-R12`).
  - Rate limit and cooldown return 429 (`POW-R12`).
  - Injected prompt text is annotated via `ingest.py` as untrusted (`POW-R13`).
  - Real SQLite migration v94 verification.
- Live real-stack validation against running FastAPI server on loopback port:
  - Real curl / HTTP client calls for all error and success codes.
  - Playwright visual tests of Webhooks UI on `#/schedules` at 360, 768, 1280, 1920 px.
- Skeptical code review for line caps, god functions, timestamps, and emoji.
