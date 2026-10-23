# EVIDENCE — approval triage (2026-10-22)

Environment: Linux, Chromium 153 (Playwright 1.63), Firefox 153, Python 3.13. Isolated Hutch server on `127.0.0.1:8810` with a temporary state directory. Synthetic fixtures only; no provider calls, no real data. The pre-change tree is the archived `ceb9d36b` source served from a separate checkout on `127.0.0.1:8811`.

## Benchmark: can the owner reach the urgent decision?

Fixture: 52 pending approvals (4 bots, mixed risk/outward, one urgent payment). Same seed before and after.

| Measure | Before | After |
|---|---|---|
| Desktop first-card action | “Write the generated summary…” (low risk, 5:41 left) | “Delete the generated build directory…” (high risk, 1:48 left) |
| Desktop urgent payment position | Page 2, second item; pagination at **12,640 px** of a **12,869 px** page | First viewport, second card at **482 px**; both urgent items visible |
| Desktop scroll to urgent payment | ~**13,088 px** (12,640 + 448) → ~13.6 viewports | **0 px** additional scroll (first viewport) |
| Narrow 320 first-card action | “Write the generated summary…” (low risk, 5:41 left) | “Delete the generated build directory…” (high risk, 1:48 left), fully visible |
| Narrow 320 urgent payment position | Page 2, second item; pagination at **20,363 px** of a **20,584 px** page | Second card; its top begins at the fold after the fully visible first urgent card. The first urgent decision needs no scroll. |
| Narrow 320 scroll to first urgent decision | ~**20,978 px** (20,363 + 615) → ~28 viewports | **0 px** additional scroll for the first urgent card |
| Page 2 content after change | Two newest requests, including the urgent payment | Two least-urgent requests (24m and 29m left) |
| Page height, 52 cards | 12,869 px desktop / 20,584 px narrow | 12,038 px desktop / 19,762 px narrow |
| Approval ID on card face | Every card (21.7 px line) | Removed from face; still in Review details + accessible description |
| TTL text | `1:39 left` (ambiguous) | `1m 39s left` (unambiguous) |
| Close control at scroll end | Present at top only; 5,984 px above viewport at 6,000 scroll on phone | Sticky at top; verified visible at 320/390 after scrolling to end |
| Queue summary/filters | None; count only at bottom pagination | `52 approvals · Due soon 20 · High risk 8 · Leaves machine 4` |

Raw data: [`evidence/before-stress.json`](evidence/before-stress.json), [`evidence/after-measure.json`](evidence/after-measure.json), [`evidence/after-stress.json`](evidence/after-stress.json). Screenshots: [`before-after-desktop.png`](evidence/before-after-desktop.png), [`before-after-320.png`](evidence/before-after-320.png), plus individual before/after files in the same directory.

## State coverage

- 0 approvals + 0 receipts: existing success empty state (unchanged); the empty receipts bucket is hidden (aligned with the concurrent WCAG D-05).
- 0 approvals + 1 unresolved action: summary `0 approvals · 1 action outcome`; `#receipt-queue` is the first content; neutral “One action outcome still needs review.” (test + [`after-receipts-only-390.png`](evidence/after-receipts-only-390.png)).
- 52 approvals: priority order, filters, pagination, sticky close.
- Client expiry: countdown disables decisions and shows “Expired — checking decision” (source path unchanged; covered by existing tests).
- Refresh error/Retry + stale-details notice: existing test `test_needs_you_drawer_preserves_review_focus_and_reports_refresh_failure` passed.
- Filter with no matches: “No requests match this filter.” + “Show all requests” (new test).
- Filters survive a 5-second poll; focus remains on the active filter (manual probe).
- Backdrop click and Escape close; focus returns to the `Needs you` trigger (manual probe + new test for close).

## Accessibility and rendering

- **axe-core (WCAG 2.0/2.1/2.2 A/AA tags): 0 violations** at 1440×960, 390×844, 320×740 on `#/approvals` (CSP bypassed only to inject the local axe file; page CSP itself unchanged).
- **Filter buttons** have a visible 2 px azure focus ring and 44 px height on phone; accessible names read “Due soon: 20 requests” etc. (`aria-label`), `aria-pressed` reflects state. The final axe run used the corrected accessible names.
- **Keyboard:** Tab from close → filters → first card; every focused card/button remains below the sticky header; 18-stop walk at 320 showed no obscured focused control. Shift+Tab returns visibly.
- **ui-audit (final 15-run matrix, widths 320/375/768/1024/1440, dark, none + textspacing + pseudo):** no `horizontal-overflow`, no `text-spill`, no `target-size`, no `small-text`, no `image-*`. CLS is **0.000 at 320/375** and **0.132 at 768/1024/1440**; the layout-shift sources are the top-layer modal’s own `browser-alerts`/`recently-decided` rows being re-parented when the dialog opens, not the queue content jumping. An independent probe of the same state measured **0.038**, and the independent verifier measured **0.031** at 1440; the higher audit value is a measurement artifact of the auto-opened `#/approvals` alias. No CLS regression was observed on the background page.
  - Full summary: [`evidence/ui-audit-final-SUMMARY.md`](evidence/ui-audit-final-SUMMARY.md). The remaining 348 candidates are:
  - 52 `fixed-layer-overlap` + 90 `occluded-control`: the modal covers the page behind it (expected; background is inert).
  - 142 `collision`: page content behind the modal (expected).
  - 24 `focus-invisible`: the shared `.btn` focus-ring defect on `main`, fixed by the concurrent WCAG lane F-01 (`a403a598`), not duplicated here.
  - 6 `console-error`: ui-audit’s own injected inline script blocked by CSP (tool artifact).
  - 28 `text-clipped` info: existing roster ellipsis with full text/title.
- **Firefox 153:** 320 and 1440 pass; first card visible, no horizontal overflow, sticky close visible, no page errors.
- **WebKit:** blocked in this environment — Playwright WebKit 26.6 needs `libicu74`/`libxml2`/`libflite1`, which are not installed; `sudo playwright install-deps` was not run. **Not verified.**
- **No screen reader / physical phone / Safari** available. Screen-reader announcement order is unverified; DOM/keyboard only.

## Tests run

- `uv run pytest -q tests/e2e/test_browser.py -k "approval or needs_you or due_soon"` → **21 passed** (pre-rebase) and **21 passed** after rebasing onto `main@5ec62889`.
- New focused tests:
  - `test_needs_you_prioritizes_deadline_and_keeps_close_reachable` → passed (320, 52-card-ish fixture, first urgent card fully visible, sticky close measured in-viewport, filter counts, ID in details, focus return).
  - `test_needs_you_receipts_only_leads_with_the_outcome` → passed (390, intercepted receipts-only state).
  - `test_needs_you_filter_can_be_cleared_and_resets_to_all` → passed (keyboard filter, zero-result state, reset, focus returns to All).
  - `test_due_soon_summary_and_filter_refresh_without_data_change` → passed (clock crosses the 10-minute boundary; poll refreshes count/filter without a data change).
  - `test_needs_you_reopen_resets_to_priority_page` → passed (reopen returns to page 1, All filter, scrollTop 0, urgent first).
  - `test_needs_you_first_load_failure_is_not_left_loading` → passed (first-load failure says “Requests could not be loaded.”).
  - Existing large-queue pagination test now also asserts pager focus moves to the first card’s Review details.
- `uv run pytest -q tests/e2e/test_design_system.py tests/e2e/test_wcag_fixes.py` → **30 passed** (17 + 13, 1:59).
- `uv run pytest -q tests/test_site_tokens.py` → **8 passed**.
- `uv run pytest -q --ignore=tests/e2e` (short `TMPDIR`) → **3,276 passed, 6 skipped, 6 xfailed, 0 failed** (independent verifier, 14:54). The first full run used a too-long worktree temp path and produced 9 `AF_UNIX path too long` failures; the same 9 tests pass with a short `TMPDIR`, and no UI test failed.
- Full `tests/e2e` run (`310 passed, 4 failed, 24:32`) — taken after the main implementation; the final approval-only follow-ups (reopen reset, first-load failure copy, summary focus, cap) were rechecked with the 21-test approval subset after they landed:
  - `test_large_idle_roster…` and `test_tool_compatibility…` passed on immediate rerun (flaky under the long serial run).
  - `test_workspace_model_default…` still looks for `#prefs-toggle`, which does not exist on `main`; it fails identically when the base checkout is served with the same Playwright environment.
  - `test_runs_archive…` asserts immediately after `#runs-count` appears and finds the loading text; it also fails identically on the base checkout. Neither failure touches the approval code.

## Post-rebase integration (main@5ec62889)

The WCAG lane landed and `main` moved from `ceb9d36b` to `5ec62889` (F-01 focus rings, D-01…D-10, including D-05 hidden empty receipts). The five approval commits were rebased onto that base in `.worktrees/approval-integrate`.

- **Conflicts resolved:** `index.html` now has the WCAG `#receipt-queue` + `hidden` section and the approval count badge; `refreshApprovals()` calls `renderApprovalReceipts()` (hidden empty bucket + receipt focus restore), while `renderApprovalQueue()` keeps `wireApprovals()` / `updateTtls()` and main’s `needsYouRouteOpening` remains intact.
- **Focus return:** closing at 320 after opening from the hidden sidebar now focuses the visible `#nav-toggle`; the previous behavior tried to focus an off-canvas button. The new focused-target assertion passes.
- **Final axe:** **0 violations** at 1440×960, 390×844, 320×740.
- **Final `ui-audit` (320/375/1440, dark, none + textspacing):** no `horizontal-overflow`, `text-spill`, `target-size`, `small-text`, or `image-*` findings. **`focus-invisible: 0`** — F-01’s action-button rings are present; a keyboard walk to “Allow once” computed `solid 2px rgb(96, 165, 250)` at offset 2px. The remaining 317 candidates are modal background collisions/overlap candidates and informational roster ellipses.
- **Focused tests after rebase:** 21 approval/needs-you/due-soon tests passed. Design-system + WCAG suites: 54/55 passed; `test_answer_feedback_stays_local_revisioned_and_accessible` is flaky and passed three consecutive reruns (and on main alone). No recurring failure was introduced by this lane.
- **Screenshots:** [`after-integrated-320.png`](evidence/after-integrated-320.png), [`after-integrated-1440.png`](evidence/after-integrated-1440.png); summary [`ui-audit-integrated-SUMMARY.md`](evidence/ui-audit-integrated-SUMMARY.md).

The earlier full e2e run predates this rebase; the full offline suite is unchanged because the rebase touches no Python package code. Main’s own WCAG lane supplied the design-system/WCAG suites above.

## Marketing surface

The public control section now names the triage behavior instead of leaving it implicit: the “Know when to step in” card says the soonest deadline and risk come first, and the approval-rules disclosure states deadline-first ordering, due-soon/high-risk counts, requests that leave the machine, one-decision-at-a-time, and no bulk approval. Claims authority and screenshots are in [`marketing/MARKETING.md`](marketing/MARKETING.md); before/after images and `validation.json` are under [`marketing/`](marketing/).

- `tests/e2e/test_website.py` + `tests/test_site_tokens.py`: **41 passed**.
- New `test_approval_triage_copy_is_truthful_and_responsive`: passed at 1440/768/390/320 with zero page overflow; it records screenshot hashes and source hash.
- `ui-audit` on the built site: no horizontal overflow, text spill, target-size, small-text, or image findings. Remaining candidates are the pre-existing sticky-header/skip-link overlaps and intentional hero layering.
- axe-core: **0 violations** at 1440/390/320.
- No measured triage-time, bulk-approval, automatic-approval, or safety-guarantee claim was added.

## Known false positives / not run

- `ui-audit` cannot infer modal semantics; its background-overlap counts are intentional. Confirmed against screenshots.
- No Lighthouse/INP because the route is local and there is no production build; CLS was measured by `ui-audit` at 0.000 after the loading-height reservation.
- No pixel-regression baseline existed for this route; the before/after images are layout-change evidence, not a `toHaveScreenshot` baseline.
- Figma Community previews were blocked by an AWS WAF challenge; research used shipped Linear/Jira/GitHub interfaces instead (see `RESEARCH.md`).
