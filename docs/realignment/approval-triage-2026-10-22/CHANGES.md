# CHANGES — approval triage

Route A approved by the user on 2026-10-22. No API, schema, permission, or dependency changes.

| Finding | Change | Level | Evidence | Status |
|---|---|---|---|---|
| F-01 | Pending requests are fetched (bounded at 1,000) and sorted by soonest deadline, then high risk, then outward effect. Client-side pagination keeps the existing 50-per-page Previous/Next access, so page 1 now contains the most urgent requests instead of the oldest. | shared component / queue | `evidence/after-measure.json`; `evidence/before-stress.json`; screenshots | Done |
| F-02 | `Needs you` gets a sticky header with the close button; the dialog opts into `closedby="any"` and has a backdrop-click fallback. `scroll-padding-top`/`scroll-margin-top` keep focused cards clear of the header. | shared component | `tests/e2e/test_browser.py::test_needs_you_prioritizes_deadline_and_keeps_close_reachable`; `evidence/after-320.png` | Done |
| F-03 | The drawer summary counts approvals **and** unresolved action outcomes. With zero approvals and receipts, the receipts section moves above the approvals area and the empty state is neutral (“One action outcome still needs review”) instead of a success check. | screen | `test_needs_you_receipts_only_leads_with_the_outcome`; `evidence/receipts-only-390.png` | Done |
| F-04 | A sticky one-line summary and four filter toggles (`All`, `Due soon`, `High risk`, `Leaves machine`) use counts from the loaded set and expose `aria-pressed`; “Show all requests” clears a zero-result filter. | shared component | `test_needs_you_filter_can_be_cleared_and_resets_to_all`; axe 0 violations | Done |
| F-05 | The approval ID is removed from the card face; it remains in Review details and in a visually hidden `aria-describedby` span, so the accessible description and support lookup still work. | shared component | `test_inline_chat_approval_is_one_click_and_preserves_conversation`; `evidence/after-1440.png` | Done |
| F-06 | TTL renders as `1m 27s left` / `1h 27m left` instead of the ambiguous `1:27 left`; initial paint and the one-second updater share one formatter. | shared component | `test_needs_you_prioritizes_deadline_and_keeps_close_reachable`; screenshots | Done |

## Files

- `src/hutch/server/static/index.html` — sticky header/overview, `closedby`, receipts section id/count.
- `src/hutch/server/static/app.js` — deadline/risk sort, bounded all-page fetch, filters, summary, sticky observer, receipts-first state, TTL formatter, ID relocation.
- `src/hutch/server/static/style.css` — sticky header, overview/filter styles, scroll padding, 44px phone filters.
- `tests/e2e/test_browser.py` — updated the existing ID assertion for the new details placement; added three focused approval-triage tests.
- `docs/design-system.md`, `CHANGELOG.md` — shared queue rule and user-facing change note.

## Follow-up fixes from independent verification

- Reopening the drawer resets the client page offset, filter, and scroll to the priority page instead of restoring a stale page 2.
- A first-load failure replaces “Loading requests…” with “Requests could not be loaded.” and says no requests are displayed.
- The approval Review-details summary draws its focus outline inside the `overflow: hidden` disclosure so it is not clipped.
- The pending fetch loop slices at the documented 1,000 cap instead of allowing a final 200-item page to overrun it.

## Not changed

- No bulk approve/deny; no auto-approval; no new permissions.
- No API endpoints, query parameters, schema, or provider routes changed.
- Inline chat cards keep their conversation order and all decision controls; only the ID face line and TTL format changed.
- The concurrent WCAG lane’s F-01 focus-ring fix is not duplicated here. The after-matrix will confirm it once that branch is merged.

## Verification summary

See `EVIDENCE.md` for commands and results. Focused browser tests: 21 approval/needs-you/due-soon tests passed; design-system + WCAG fixes 30 passed; axe 0 violations; `ui-audit` shows no horizontal overflow, no text spill, no target-size failure, and CLS ≤0.031 on the final matrix. The full offline suite passed 3,276 tests with a short temp path; the full e2e run’s only repeatable failures reproduce on the base checkout.
