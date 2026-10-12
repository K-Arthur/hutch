# Active-step amendment carry: visual review — 2026-10-11

Scope: inspect the owner-local amendment editor while one unchanged tool-free worker child is still running and a candidate adds a later transform. The Chromium run used a real SQLite workflow store, the production supervisor/API and a controlled in-process runtime; the model provider was not called.

## Opened captures and observations

I opened the editor and carry-review captures at all four sizes. At 1440×960 and 768×1024 the editor remains a centered modal; at 360×800 and 320×740 the dialog uses the available viewport with a scrollable body and persistent Cancel/Adopt actions. All four widths have zero horizontal overflow, and the adoption target remains 44px high. The carry row displays the actual worker role, model, child run ID and unchanged-contract reason.

The review copy says the active step keeps its original model and execution contract and that the new revision starts after it settles. Adoption is enabled for this narrow safe case. At phone widths the plan editor and candidate diff require vertical scrolling; separate captures show the editor and the carry explanation. The fixed footer does not cover the carried-step reason in the measured bounds. The visible field-level diff includes compiler-populated defaults for a newly added transform; this is verbose but readable and was not changed in this slice.

The API regression adopts while the controlled worker remains live, then releases it and verifies one child dispatch, its preserved output and the later transform result. A second preview changes the active instruction and confirms the live child is not carryable. A malformed stored parent fence also fails closed without breaking preview. A transactional race fixture changes the assistant's `num_ctx` after preview; the authority/binding recheck refuses adoption, preserves the old revision, and succeeds after the original setting is restored. The earlier changed-transform pause and orphan-child tests still refuse adoption.

Evidence:

- [`results.json`](results.json) records Chromium 153.0.8010.12, Playwright 1.63.0, viewport/dialog/footer/target bounds, no page errors or failed requests, zero provider calls, and source/image/trace SHA-256 values. All listed hashes were checked against the saved files.
- [`trace.zip`](trace.zip) contains the real-browser interaction trace.
- `carry-preview-*.png` and `carry-review-*.png` show the editor and scrolled carry contract at 1440, 768, 360 and 320 CSS pixels.
- Browser command: `TMPDIR=/var/tmp HUTCH_WORKFLOW_AMENDMENT_CARRY_ARTIFACTS=docs/realignment/artifacts/workflow-studio/amendment-carry-active-step-2026-10-11 .venv/bin/pytest -q tests/e2e/test_browser.py::test_workflow_amendment_carry_preview_is_clear_and_responsive --basetemp=/var/tmp/hutch-carry-browser-fence-final` — **1 passed in 5.41s**.
- Full affected API/interpreter command: `TMPDIR=/var/tmp .venv/bin/pytest -q tests/test_workflow_api.py tests/test_workflow_engine.py tests/test_workflow_regressions.py --basetemp=/var/tmp/hutch-workflow-carry-suite-fence-final` — **104 passed in 67.98s**, including the malformed-fence refusal.
- `node --check src/hutch/server/static/app.js`, `python -m compileall -q src/hutch`, `git diff --check`, the repository emoji audit (795 files, 9 waivers) and site token/contrast check all passed. Six source and nine visual-artifact SHA-256 entries in `results.json` were rechecked with no mismatch.

## Project visual scorecard

This uses the 0–10 dimensions and 45% aesthetic / 40% functionality / 15% regression-health weighting in [`docs/qa/shape-and-background-review.md`](../../../../qa/shape-and-background-review.md). Human judgments apply to the opened captures; this is an internal feature review, not an accessibility certification.

| Area | Score | Evidence and limits |
|---|---:|---|
| Shape coherence *(human)* | 9 | Modal, preview panels, inputs and action buttons follow the existing Studio shape system. |
| Background calmness *(human)* | 9 | The preview stays visually distinct over the subdued owner-chat backdrop. |
| Color coherence *(human)* | 9 | Status and primary adoption colors retain the established palette and contrast roles. |
| Hierarchy and density *(human)* | 8 | The separate carry section is easy to find; the full declarative diff remains long and requires phone scrolling. |
| Detail polish *(human)* | 8 | Durable run identity, role, actual model and contract reason are visible; compiler defaults add noise to new-node diffs. |
| Cross-surface consistency *(human)* | 9 | Desktop/tablet modal and compact full-screen layout retain the same labels and controls. |
| **Aesthetic** | **8.7** | Mean of the six dimensions, rounded to one decimal. |
| **Functionality** | **9.5** | Live preview/adoption readiness, retained child identity and four-width geometry passed. |
| **Regression health** | **9.0** | Focused API and browser checks are green after the message expectation update; broad repository/browser suites are not covered here. |
| **Combined** | **9.1** | Weighted project formula; every reviewed dimension clears 8 and combined clears 8.5. |

## Not verified in this capture

No screen-reader pass, browser zoom, text-spacing stress, forced-colors run, offline reconnect, physical phone or paired-phone journey is claimed. The live provider was deliberately not called, and process-executor cleanup ordering for a carried child was not exercised by this controlled in-process fixture. General active-branch draining remains unsupported.
