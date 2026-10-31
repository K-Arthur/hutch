# Personal operations, second pass: agenda and notifications (2026-10-31)

G01 (read-only calendar/mail agenda for Today) and G05 (outbound notifications for
needs-you, failures and unattended results) as scoped by
`.pipeline/personal-operations/2026-10/HANDOFF.md`. Local main; nothing pushed, no live
provider account and no live Telegram bot were used.

## What changed

G01, the agenda:

- `src/hutch/personal/agenda.py` is a pure builder. It takes an injected reader per
  source, returns each item with its source label, fetch time and staleness, and reports
  an unusable grant as a reason code (`not_configured`, `grant_missing`, `grant_expired`,
  `mail_requires_local`, `provider_error`) instead of an empty day. It makes no model
  call, writes no row, and keeps a bounded in-memory snapshot (eight entries, at most one
  hour old) so a failed refresh is labelled stale rather than shown as an empty day.
- `src/hutch/personal/agenda_sources.py` is the only adapter to persisted grants, OAuth
  account records and provider clients. It reuses `GoogleCalendarBook` and
  `GoogleMailBook` and applies the Gmail tool's Local-inference rule, so a hosted
  assistant is listed as unavailable rather than having its mailbox read.
- `src/hutch/server/personal_agenda_api.py` adds `GET /api/v1/personal/agenda/sources`
  and `GET /api/v1/personal/agenda`. Both are read-only: no idempotency key, no body, no
  store write. An unknown assistant is 404; a bad zone is 422.
- `src/hutch/server/static/today.js` gains the Agenda section: two selectors (calendar and
  mail), the remembered choice in `localStorage` for that browser only, a per-source head
  with label and badge, a per-item source line with its read time, and a clear
  stale/unavailable/not-configured state. `personal.css` styles it with the existing
  tokens and keeps the 320 px layout without horizontal overflow.

G05, notifications:

- `src/hutch/notification_schema.py` adds `notifications` and rebuilds
  `channel_deliveries` so one row references either an inbound event or a notification.
  Three triggers write content-free rows in the same transaction as the fact:
  approval created, approval expired/denied, and a run reaching `failed`,
  `outcome_unknown`, or `succeeded` from an unattended origin. The unique
  `(kind, subject_kind, subject_id)` guard makes a repeated transition idempotent.
- `src/hutch/notifications.py` renders a bounded plain-text alert (assistant, kind,
  machine reason code, where to look) and exposes the read shape. No prompt, action
  argument, fact value or provider text enters it.
- Delivery reuses the existing supervisor: `ChannelService.once` leases the connection as
  before, then `queue_notifications` queues this connection's own live alerts and
  `take_notification` hands one to the same send path (`_deliver`) with the same states,
  backoff and reconciliation. There is no second sender and no new loop.
- `GET /api/v1/notifications` lists recent alerts with their outbox state. Today shows
  them under "Alerts Hutch sent" with a delivery chip; a decided approval is never queued
  late, and an alert with no enabled connection reads "Not sent".
- Channel delivery listing now left-joins, so a notification delivery (which has no
  inbound event) renders instead of crashing the review list.

## Uncommitted work preserved

Another session's model-picker/assistant-removal work was already in the tree. Only this
slice's files were staged; `src/hutch/server/app.py`, `static/app.js`,
`static/index.html`, `studio.css`, `cli.py` and their tests were never touched, staged or
reformatted here. `src/hutch/server/static/ui.css` was rebuilt by `npm run build:css` and
restored to HEAD because the churn was not this slice's.

## Limits and non-claims

- No live Google or Microsoft account was connected. The agenda's live path is proven by
  injected readers and by a browser test with a fake book; the OAuth path itself remains
  experimental as `docs/roadmap.md` records.
- No exactly-once claim. Notification delivery is at least once at best; an unconfirmed
  send remains `uncertain` until the owner checks the real conversation.
- No claim that notifications were read. Telegram acceptance is not delivery proof.
- Not implemented here: G02 (coding handoff verification), G03 (automation history),
  G04 (webhook triggers), G07 (multi-participant authentication), G08 (commitment to
  calendar), G09 (mail/calendar content to a proposed commitment). The agenda does not
  create commitments from provider text.
- Multi-user isolation, exactly-once external effects and live model-driven capture
  remain blocked or deferred exactly as `2026-10/ACCEPTANCE-CRITERIA.md` records.

## Reproduction

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run --frozen --no-sync pytest -q --no-header --tb=short \
  tests/test_personal_agenda.py tests/test_notifications.py tests/test_personal_api.py \
  tests/test_channels.py tests/test_bot_deletion.py tests/test_bot_deletion_schema.py \
  tests/test_migration.py tests/test_navbar_consistency.py tests/test_commitments.py \
  tests/test_spaces.py tests/test_commitment_tools.py
HUTCH_TEST_ARTIFACTS_DIR=$PWD/.pipeline/personal-operations/2026-11/evidence \
  UV_CACHE_DIR=/tmp/uv-cache uv run --frozen --no-sync pytest -q --no-header \
  tests/e2e/test_personal_today_agenda.py
npm run check:agent
```

Screenshots land in `evidence/personal-operations-agenda/` (1440, 834, 390, 320, the
stale state, the unavailable state, the alerts section and 200 percent zoom).
