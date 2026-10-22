# RECON — approval surfaces (2026-10-22)

## Stack and rendering

- Python 3.13 / FastAPI + Starlette; SQLite store (`src/hutch/store.py`), Uvicorn.
- Dashboard is a zero-build, hash-routed vanilla ES SPA: `src/hutch/server/static/index.html` + `app.js` (12,424 lines) + `style.css` (2,955 lines). Generated utility layer `ui.css` (Tailwind + daisyUI) and semantic tokens `brand-tokens.css` load first.
- Server-rendered Jinja/HTMX pages exist for legacy/login/pair/model/usage routes; not in this task’s path.
- Data flows over `/api/*` and versioned `/api/v1/*`; SSE for run transcripts; polling (5 s) for the approval drawer.
- Design-system source of truth: `DESIGN.md`, `docs/design-system.md`, `website/tokens.json` → generated token CSS. Component CSS is mostly `.btn`/`.chip`/`.tag` from `ui.css` plus app glue in `style.css`.

## Approval surfaces and blast radius

| Surface | Render path | Notes |
|---|---|---|
| Inline approval card in chat | `approvalCardHtml()` (app.js ~5806) via `renderChatEvent()` | Same markup as queue; resolved variant `approvalResolvedHtml()` |
| Needs you drawer (`#/approvals`, nav button) | `openNeedsYou()` / `refreshApprovals()` (app.js ~6881–6988), markup in index.html 116–134 | Pending approvals, uncertain action receipts, browser-alert disclosure, recently decided |
| Attention bar / badge | `refreshBadge()` (app.js ~2551), `renderAttention()` | Badge = pending approvals + unresolved receipts |
| Phone supervision review | `phone.js`/`computer.js` separate surface | Out of scope; shows its own approval cards |
| CLI/API decisions | `resolve_approval_ex()` / `/api/v1/actions/approvals/{id}/approve|deny` | Server-authoritative; idempotency keys; action hash binding |

Data contract (unchanged by this lane):
- `GET /api/v1/actions/approvals?status=pending&limit=≤200&offset=` → oldest-first (`ORDER BY created_at, id`).
- `GET /api/v1/actions/approvals?status=resolved&limit=8` → newest decided first.
- `GET /api/stats` → `pending_approvals`, `unresolved_actions`.
- `GET /api/v1/actions/receipts?unresolved=true&limit=20&offset=` → uncertain outcomes.
- `POST /api/v1/actions/approvals/{id}/approve|deny` requires `action_hash` (v1) and an idempotency key; a decision binds to the exact action shown.

## Token and conflict scan (approval area)

- Approval CSS is token-based (`--panel`, `--line`, `--r-panel`, `--s-*`, `--fs-*`); no new colors needed.
- `.approval-card-chat` uses `z-index: 6` (not a token) inside the dialog; not a stacking problem today.
- `button.primary/ghost/danger/small { all: unset; … }` (style.css ~450) also clears the global `:focus-visible` outline. On main this leaves approval buttons with no visible focus ring (WCAG 2.4.7). Concurrent WCAG lane F-01 fixes this; not duplicated here.
- `ui-audit.mjs` reported large `fixed-layer-overlap`/`occluded-control` counts for controls behind the open modal; these are expected for a modal and were confirmed as false positives (background is inert).

## Feature-parity inventory (do not lose)

- Per-card: Allow once, Always allow for this bot (hidden for outward actions), Deny, Open conversation/run, Review details (why asked, tool, risk, effect, exact arguments, command segments, form target/fields), TTL countdown with client expiry disabling, resolved state with decider/time.
- Queue: pending list, server pagination (Previous/Next), pending count, empty state, refresh error + Retry with stale-details notice, 5 s polling with focus/expanded-state preservation, Escape close, focus return to trigger.
- Receipts: list, pagination, review modal, recorded outcome, integrity warning, open attempt.
- Cross-device: server-authoritative conflicts (already decided / expired / action changed), action-hash refresh path, idempotent commands.
- Badge/attention: counts, browser notifications, roster attention, attention bar.
- No bulk approve by design; not added.

## Existing quality gates

- `tests/e2e/test_browser.py` covers approval pagination, phone decisions, stale-details retry, focus preservation, cross-device conflicts.
- `tests/e2e/test_wcag_fixes.py`, `test_design_system.py`, `test_website.py`.
- `ui-audit.mjs` (measurement) + axe (when injected) + Lighthouse not yet run for this route.
- No approval-specific visual baseline in the repo; this lane adds one under `docs/realignment/approval-triage-2026-10-22/evidence/`.
