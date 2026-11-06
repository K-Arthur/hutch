# Validation ledger: personal ops workflows (2026-11)

Dated, real-stack evidence for each phase. This file is append-only: later phases add
sections, they do not rewrite earlier results. Commands were run from the repository root
on Linux.

## Phase 2 - automation trust and observability (2026-11-06)

Commits under test:

- `817c3942` - append-only schedule revision journal (schema v92)
- `69b2637b` - schedule approval checkpoints, bounded conditions, policy sidecar (schema v93)
- `99ec03fc` - the occurrence read used by the history API (fix forward for an omitted file in 2B)
- `fd988138` - fleet roll call, attention filter, history/policy disclosure and visual evidence
- `e7ac6411` - remove the unused bulk policy fetch and recapture the four affected screenshots

Environment:

- Real FastAPI app created by `hutch.server.app.create_app()` and served on a loopback port by
  `uvicorn` for the browser tests.
- Real SQLite database under a throwaway `HUTCH_STATE_DIR`; migrations ran through the normal
  `Store._upgrade()` path, not a fixture-only schema.
- Real Chromium `153.0.8010.12` through Playwright.
- No live Google, Microsoft or Telegram account is involved in this phase.

### Focused and regression tests

| Command | Result |
|---|---|
| `npm run test:agent -- tests/test_schedule_history.py` | 7 passed |
| `npm run test:agent -- tests/test_schedule_conditions.py tests/test_schedule_policy.py tests/test_schedule_approvals.py tests/test_schedule_history.py` | 35 passed |
| `npm run test:agent -- tests/test_schedule_conditions.py tests/test_schedule_policy.py tests/test_schedule_approvals.py tests/test_schedule_history.py tests/test_scheduler.py tests/test_schedule_outcomes.py tests/test_schedule_durability.py tests/test_lifecycle.py tests/test_approval_cas.py` | 172 passed in 26.71s |
| `uv run --frozen --no-sync pytest -q --no-header --tb=short tests/e2e/test_schedule_history.py` | 3 passed in 10.04s; real server, 8 width/theme combinations, keyboard, policy PUT |

The focused tests exercise a real temporary SQLite file and the real `Store`. The browser test
starts a real app and real server; it does not mock the API.

### Migration and trigger state

A direct Store/Engine run with the approval policy printed:

```
schema_version 93 93
run_status waiting_approval reason schedule_approval_pending
counts {'schedule_revisions': 1, 'schedule_policies': 1, 'schedule_approval_requests': 1,
        'approvals': 1, 'notifications': 1}
approval_tool schedule
```

Verified behavior:

- `schedule_revisions` is created by the v92 migration and backfilled for existing bots.
- `UPDATE schedule_revisions` and `DELETE FROM schedule_revisions` raise
  `sqlite3.IntegrityError: schedule revisions are append-only`.
- A no-op bot save writes zero journal rows; an unrelated bot field change writes zero rows.
- A schedule edit writes one row; a bot with no schedules writes no initial row.
- `schedule_policies` is deleted by the bot-document trigger when its schedule disappears.
- `schedule_approval_requests` maps the parked run to the single approval.

### HTTP statuses against the real app

The app was created with a real temporary state directory and the test Host allowance used by
the suite. A disabled schedule avoids any scheduler claim during the route checks.

| Request | Status | Notes |
|---|---|---|
| `PUT /api/v1/bots/ledger-http/schedules/{id}/policy` with `expected_revision=0` | 200 | revision 1 created |
| `PUT` again with stale `expected_revision=0` | 409 | compare-and-swap refusal |
| `PUT` with `field=prompt` | 422 | closed condition schema refuses an unapproved field |
| `GET /api/v1/bots/ledger-http/schedules/{id}/policy` | 200 | default or saved policy |
| `GET /api/v1/bots/ledger-http/schedules/{id}/revisions` | 200 | newest first |
| `GET /api/v1/bots/ledger-http/schedules/{id}/history` | 200 | policy, revisions and occurrences |
| `GET /api/v1/schedules/roll-call` | 200 | totals and routine rows |
| `GET .../schedules/schedule-missing/revisions` | 404 | unknown schedule |

### Approval path

With a real due schedule and `approval_required=true`:

1. `Engine.scheduler_claims()` created exactly one run with `status=waiting_approval` and
   `reason=schedule_approval_pending`.
2. The run's transcript contained exactly one `approval_request` event; no model or tool event
   was emitted before a decision.
3. `store.pending_approvals()` returned one request with `tool="schedule"`; its detail contained
   the assistant, schedule, occurrence, timezone, trigger and prompt character count, and no
   prompt text.
4. The notification table contained exactly one row.
5. `resolve_approval_ex(..., approve=True)` moved the run to `pending` with an empty reason.
6. Denial moved the run to `skipped` with reason `schedule_approval_denied`; expiry moved it to
   `skipped` with reason `schedule_approval_expired`.
7. A decision recorded directly in the approvals table but not yet reconciled was retried by
   `reconcile_decisions()` on the next scheduler beat and moved the run to `pending`.
8. A parked run with no approval mapping and reason `schedule_approval_pending` was moved to
   `skipped` with reason `schedule_approval_missing`. A scheduled run waiting on a normal tool
   approval (different reason) was not touched.

### Conditions

- A false condition (`occurrence_weekday ne <the due day>`) created no run and wrote a
  `last_skip` record with reason `condition_not_met`.
- A true condition still parked the occurrence for approval.
- The condition schema rejected unknown fields, unknown operators, nested objects, boolean/integer
  confusion, oversize strings, and lists over 20 values before any policy write.
- A legacy policy row with `approval_required=1` on a linked saved workflow failed closed: no
  workflow run was created, and the skip reason was `policy_unsupported`.

### Browser and visual evidence

Capture command:

```
uv run --frozen --no-sync python docs/realignment/capture_schedule_history.py
```

Result: `Captured 12 views; 0 with errors, overflow or a missing roll call`.

Evidence: `docs/research/2026-11-personal-ops-workflows/artifacts/phase2/report.json` and 12 PNGs.

| Widths | Themes | States | Console errors | Horizontal overflow |
|---|---|---|---|---|
| 360, 768, 1280, 1920 px | dark and light preference | default schedules view | 0 | 0 px |
| 1280, 1920 px | dark and light preference | history panel open | 0 | 0 px |

Keyboard and interaction checks in the real browser:

- The attention filter is focusable, Space toggles it, and the visible row count changes from 3 to
  2 and back.
- `Enter` on the native history `<summary>` opens the panel; the summary is focusable.
- The policy checkbox saves through the real `PUT` route and the follow-up `GET` reports
  `approval_required=true` and `revision=1`.
- The history panel shows recent runs, the linked run, schedule changes, and a redacted prompt
  change without prompt text.

### Visual defects found and fixed during this phase

| Surface | Defect | Fix |
|---|---|---|
| Roll call | Next-due line showed the raw `schedule_...` id | Added the routine name to the roll-call payload and render `name · assistant · time` |
| Roll call / attention note | Roll call counted 2 needs-attention routines while the older note said 1 | The enhancement rewrites the note from the same totals: failed runs, pending approvals and blocked routines |
| Routine row | A pending pre-run approval was described as "is still running" | The enhancement replaces it with "Last run is waiting for your approval" plus run and approval links |
| 768 px roll call | Five stats on one row and one orphan on the next | Six columns at desktop, three at tablet, two at phone |
| History panel | Prompt changes were shown as a field change with no explanation | Renderer shows "changed · value hidden" for redacted fields; the API already omits the value |

### Honest limits

- **The dashboard is dark-only by design.** `docs/design-system.md` states that Hutch intentionally
  ships a fixed dark theme. The capture forces the design-system `data-hutch-theme="light"` scope,
  but the legacy dashboard tokens do not change: light and dark both computed
  `background: rgb(9, 9, 11)` and `color: rgb(237, 237, 240)`. The light captures are therefore
  layout/overflow checks, not a claim that a light theme is shipped.
- **Schedule-level pre-approval is not available for linked saved workflows.** The policy API
  returns 422 with an explicit reason; those workflows keep their own per-step approvals. This is
  recorded in `02-PROGRESS.md` as deferred.
- **No live external credentials were used.** Google Calendar, Gmail, Outlook and Telegram remain
  outside this phase; nothing in this ledger claims live vendor verification.
- The browser evidence is headless Chromium 153.0.8010.12. A physical phone, a light OS theme, and
  a real screen reader were not exercised.
