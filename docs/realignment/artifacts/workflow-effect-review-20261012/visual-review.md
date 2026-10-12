# Workflow-owned uncertain-effect review

Captured 2026-10-12 in Chromium 153.0.8010.12 against the local application. The persisted
fixture has one workflow attempt in `outcome_unknown`, one running `publish` node and one
workflow-owned action receipt marked unknown. The browser check did not execute an external
effect; the real-process crash and independent-sink no-repeat guarantee are covered separately
by `tests/test_workflow_effect_receipts.py::test_process_crash_around_effect_receipt_never_repeats_the_sink_effect`.

## Opened views and observations

- [Unresolved effect, desktop](desktop-unresolved.png): the run detail says **Needs review**,
  explains that the effect may already have happened, and offers review plus the original attempt.
- [Needs you queue, desktop](desktop-needs-you.png): the same workflow action appears under
  **Action outcomes to check** after a page reload. The queue names the Bot and the reviewed action.
- [Review dialog, desktop](desktop-review-dialog.png): the saved intent and authority are
  inspectable. The copy says the review runs no action and a new attempt still needs permission.
  The keyboard test reaches the review action with Enter.
- [Recorded result, phone-width owner view](phone-reviewed.png): the checked `not_applied` report
  is labeled **No effect found · human report**, while the original execution remains **Needs
  review**. The page has no horizontal overflow at 390×844.

The API records the human observation without changing the workflow status, attempt status, or
sealed event chain. No provider, network service, or external effect was called. The browser
reported no console errors or failed requests. Exact IDs, hashes, dimensions, and result facts
are in [validation.json](validation.json); the browser trace is in [trace.zip](trace.zip).

| Dimension | Score | Evidence |
|---|---:|---|
| Aesthetic | 92/100 | The uncertain state, review action, and human report remain distinct and readable in the existing Hutch surfaces. |
| Functionality | 96/100 | Reloaded owner queue, keyboard review, checked outcome, unchanged workflow/history, phone-width reflow, and clean console/network state all passed. |
| Overall | 92/100 | The project combines the two dimensions using the lower score. |

This visual fixture does not claim that a report independently verifies the external world, that
the original workflow can resume after reconciliation, or that the browser UI itself was opened
after a process restart. Runtime tests separately cover process replacement and the independent
effect sink. Actual browser-chrome zoom, screen-reader output, and paired-phone reconciliation are
not exercised here.
