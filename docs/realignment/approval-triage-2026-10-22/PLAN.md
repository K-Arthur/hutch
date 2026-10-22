# PLAN — approval triage (draft; route choice pending)

Status: **Route A approved by the user on 2026-10-22 and implemented in the `agent/approval-triage/approvals` worktree.** Verification is recorded in `EVIDENCE.md`; the acceptance matrix below is the verification contract.

## Design routes (researched)

### Route A — Priority queue with triage summary (recommended)

- **For:** owners scanning a backlog on desktop or phone; the measured 52-card case.
- **References:** Linear Priority/Other tabs + display options (counts, ordering); Jira Direct/Watching + Today/Older (groups, header); Visa tray (“most urgent first”; timestamps); NN/g alert fatigue; WCAG 2.4.11/dialog.
- **Layout:** sticky compact header (“Needs you”, total approvals + receipt count, close), then a one-row filter/summary strip (`All 52`, `Due soon 6`, `High risk 12`, `Leaves machine 8`), then cards sorted by soonest deadline, high-risk/outward tie-break. Long lists reveal in bounded steps (“Show 10 more”); no server pagination dead-end.
- **Hierarchy/density:** keep the existing graphite/emerald identity and card anatomy; remove the approval-ID face line; keep action as the strongest text, bot/tool/risk above, TTL right, decisions below. At 320, cards remain one column with 44 px targets.
- **Interaction:** filters are `aria-pressed` toggles over the loaded set; sort is automatic (safety default). No bulk actions. Per-card decision path unchanged. Sticky header + `scroll-padding-top`; `closedby="any"` with a backdrop-click fallback.
- **States:** 0 approvals + receipts (lead with receipts, truthful combined status), 0/0, loading, refresh error + Retry, expired client state, resolved, >200 pending (bounded notice), filter-empty.
- **Tradeoff:** fetches the pending set to sort globally (one request at 52; paged at >200), and the sticky summary adds ~70 px of vertical chrome. It is the largest change of the four, but directly fixes F-01/F-02/F-03/F-04 with one coherent queue model.

### Route B — Sectioned queue (Act now / Review / Later)

- **For:** owners who want the hierarchy decided for them; no filter state to learn.
- **References:** Visa grouping; Jira Today/Older; PagerDuty priority/urgency language.
- **Layout:** sticky header; three sections with counts and disclosure: `Due within 10 min`, `High risk or leaves machine`, `Everything else`. Each card appears in exactly one section (first matching bucket).
- **Tradeoff:** simpler than A, but less control; a high-risk request with a long deadline may sit below a low-risk short-deadline request if bucketing is not carefully explained. It also duplicates sorting logic in the section assignment, and empty sections add chrome. Does not offer “show only leaves machine.”

### Route C — Compact rows + detail pane (expert)

- **For:** a power user processing hundreds per hour who already knows the workflow.
- **References:** Linear inbox rows; GitHub notification rows; Jira drawer density.
- **Layout:** priority-sorted one-line rows (risk/outward glyph, bot, action, TTL), select a row to open review/decision in a right pane; phone becomes a detail sheet.
- **Tradeoff:** best density, but adds a click before the consequence/exact scope is visible and hides the decision buttons from the list. For a safety surface used by occasional owners, that is the wrong default. Bigger rewrite and higher regression risk; not recommended for this task.

### Route D — Minimal ordering + sticky close

- **For:** smallest reversible change if only the worst defects should be fixed.
- **Changes:** sort the current page by deadline (or fetch all), move ID into details, sticky header with close, truthful receipts-only status. No filters or summary strip.
- **Tradeoff:** fixes F-01/F-02/F-03/F-05 but not F-04; at 52 cards the owner still cannot answer “how many are high risk / leave the machine” without scanning. Under-delivers on the 200/hour goal.

## Recommendation

**Route A.** It is the only route that fixes all six findings with one queue model, matches the inspected Linear/Jira patterns, keeps every safety feature, and needs no API contract change. Route B is the fallback if the owner prefers less chrome; Route D if they want the smallest change; Route C is not recommended for this audience.

## Implementation shape (Route A, if chosen)

Files:
- `src/hutch/server/static/index.html` — drawer header/summary/filter markup, `closedby="any"`.
- `src/hutch/server/static/app.js` — `fetchAllPendingApprovals()`, priority sort, filter state, summary render, `refreshApprovals()` integration, `updateTtls()` format, card ID relocation, receipts-aware empty state.
- `src/hutch/server/static/style.css` — sticky header, summary/filter row, compact card adjustments, `scroll-padding-top`, 320px rules.
- `tests/e2e/test_approval_triage.py` (new) — 52-card priority/filters/sticky close/receipts-only/320px/keyboard.
- Docs: update `docs/design-system.md` only if the queue pattern becomes a reusable rule; dated evidence under `docs/realignment/approval-triage-2026-10-22/`.

Data:
- `fetchAllPendingApprovals()` pages `GET /api/v1/actions/approvals?status=pending&limit=200&offset=…` until `stats.pending_approvals` is covered or a **1,000** cap; dedupe by id. If capped, show “Showing 1,000 of N; resolve or use the CLI queue.” No API change.
- Sort key: `(expires_at asc, risk high first, outward first, created_at asc)`. Expiry is the safety-governing deadline; risk/outward break ties.
- Filter definitions: `Due soon` = deadline ≤ 10 min; `High risk` = `risk === "high"`; `Leaves machine` = `outward === true`.
- Summary counts from the loaded set; receipt count from `stats.unresolved_actions`.

Parity:
- All cards remain reachable; decisions, always-allow visibility, exact arguments, resolved history, receipts, error/retry, focus preservation, polling, idempotency, and server conflict handling untouched.
- No bulk approve/deny; no auto-approval; no new permissions.

## Acceptance criteria (measurable)

1. **Priority:** with the 52-approval fixture, the most urgent request is fully visible in the first viewport at 1440×960, 390×844, and 320×740; at 1440 and 390 the top two urgent requests are visible. First card is the soonest deadline (or a tie-broken high-risk/outward card), and no urgent request is hidden behind pagination. At 320 the second urgent card begins below the fold because the full safety card and 44px targets are kept; the summary still states the due/high-risk counts.
2. **Scope:** the drawer shows total pending + unresolved receipts, and counts for `Due soon`, `High risk`, `Leaves machine` that match the loaded data; filters show only matching cards and are `aria-pressed`.
3. **Close:** at 320 and 390, after scrolling to the end of a 52-card queue, the close control is visible (sticky header) and closes the dialog; `Esc` still closes; focus returns to the trigger. `scroll-padding-top` prevents the sticky header from covering a focused card during Tab.
4. **Truthful empty state:** with 0 approvals + 1 receipt, the first status says 1 item needs review and the receipt is visible without scrolling at 390; no success check says “No pending approvals” alone.
5. **Density/noise:** approval ID no longer on the card face; still available in Review details and in the API. Card height decreases or stays within 5% at 1440/390.
6. **TTL:** `1:27` renders as `1m 27s left`; `>=60 min` renders `1h 27m left`.
7. **Accessibility:** axe no new violations on `#/approvals`; no horizontal overflow at 320; 200% zoom/text-spacing pass; focus visible on all buttons (depends on WCAG lane F-01); target sizes ≥24 px (44 px on coarse pointers).
8. **Regression:** full `pytest --ignore=tests/e2e` and focused approval e2e pass; parity inventory re-checked; no API/schema changes.

## Verification commands

```sh
# in .worktrees/approval-triage
uv run pytest -q --ignore=tests/e2e
uv run pytest -q tests/e2e/test_approval_triage.py
node /tmp/opencode/hutch-audit-tools/ui-audit.mjs \
  'http://127.0.0.1:8810/#/approvals' \
  --widths=320,375,768,1024,1440 --schemes=dark \
  --stress=none,textspacing,pseudo --out=/tmp/opencode/hutch-approval-triage/audit-after
node /tmp/opencode/hutch-approval-triage/measure.mjs   # same fixture, after
```

## Rollback

- Single revert of the queue commit(s); no data migration, no API change, no flag needed. If a feature flag is preferred for the sort/summary, gate it behind a local constant default-on and keep the old renderer path; not planned unless the owner asks.

## Risks

- Fetching all pages is more work than one 50-item request; cap at 1,000 and show an honest notice. At 52 it is one request.
- Re-rendering a filtered list every 5 s can disturb focus; preserve by approval ID and keep the existing expanded-details set.
- Sticky header can obscure focused cards; use `scroll-padding-top` and test with keyboard at 320×256/740.
- Concurrent WCAG lane may touch the same functions; rebase and re-run the full matrix before integration.
