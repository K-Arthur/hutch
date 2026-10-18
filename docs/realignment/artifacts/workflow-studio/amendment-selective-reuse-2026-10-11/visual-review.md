# Workflow amendment Studio validation — 2026-10-11

Scope: revalidate the real owner-local amendment editor, read-only preview, explicit question cancellation, adoption and continuation after the transform-reuse and compact-phone footer-polish changes. The Chromium journey used a real SQLite store, workflow supervisor and typed APIs, with no provider calls.

## Opened captures and observations

The journey captured preview states at 1440×960, 768×1024, 360×800 and 320×740 CSS pixels, plus the checked compact-phone choice and post-adoption state. I opened each preview capture. Desktop and tablet use a centered dialog; phone layouts use a full-screen dialog with a scrolling body and pinned actions. All four views have zero horizontal overflow, the adoption target is 44px high, and the candidate diff and invalidation reasons remain readable as the title wraps on phone widths.

The pending question is identified by its durable ID. Adoption stays disabled until the owner selects the cancellation checkbox; Enter submits the idempotent request, the prior question is archived as cancelled, the revised run creates a fresh question ID, and focus returns to the composer. The first capture showed only 0.2px between the 39px cancellation label and the fixed footer. The label now has an 8px scroll margin; the updated compact-phone capture measures 8.19px clearance.

The preview shows an empty reusable-results section for this fixture because its only node is the changed question. The separate API regression exercises selective pure-transform reuse and records its actual execution counts; the UI does not yet display transform digest internals, which are runtime evidence rather than user-facing content.

Evidence:

- [`results.json`](results.json) records Chromium 153.0.8010.12, Playwright 1.63.0, viewport and target bounds, browser errors, request failures, provider-call count, source hashes and image/trace hashes.
- The raw Playwright trace was omitted after privacy review found session cookies in the archive.
- `preview-*.png` are the opened preview captures; `editor-*.png`, `explicit-cancellation-compact-phone.png`, and `desktop-after-adoption.png` show the remaining workflow.
- Command: `TMPDIR=/var/tmp HUTCH_WORKFLOW_AMENDMENT_ARTIFACTS=docs/realignment/artifacts/workflow-studio/amendment-selective-reuse-2026-10-11 .venv/bin/pytest -q tests/e2e/test_browser.py::test_workflow_amendment_preview_adoption_is_explicit_and_responsive --basetemp=/<local-path-redacted> — **1 passed in 5.71s**, no page errors, failed requests or provider calls.

## Project visual scorecard

This uses the 0–10 dimensions and 45% aesthetic / 40% functionality / 15% regression-health weighting in [`docs/qa/shape-and-background-review.md`](../../../../qa/shape-and-background-review.md). Human judgments apply to the opened captures; these scores are an internal feature review, not an accessibility certification.

| Area | Score | Evidence and limits |
|---|---:|---|
| Shape coherence *(human)* | 9 | Shared rounded modal, field and action styles remain consistent. |
| Background calmness *(human)* | 9 | Solid dark preview panels keep attention on the diff and question. |
| Color coherence *(human)* | 9 | Green adoption and the amber human-review boundary remain distinct. |
| Hierarchy and density *(human)* | 8 | The diff and question are grouped; long plan IDs and a full-height dialog require scrolling on phones. |
| Detail polish *(human)* | 9 | Durable IDs, clear cancellation, keyboard action and focus return work; the compact-phone label has measured clearance above the fixed footer. |
| Cross-surface consistency *(human)* | 9 | Type, spacing, borders and action states follow the existing Studio. |
| **Aesthetic** | **8.8** | Mean of the six dimensions, rounded to one decimal. |
| **Functionality** | **9.5** | Real preview and adoption, archive, fresh question, focus return and responsive geometry passed. |
| **Regression health** | **9.0** | No page/network errors in the focused Chromium journey; this does not certify the broad browser suite. |
| **Combined** | **9.1** | Weighted project formula; every reviewed dimension clears 8 and the combined score clears 8.5. |

## Not verified in this capture

No screen-reader pass, browser zoom, text-spacing stress, forced-colors run, offline reconnect, physical phone or paired-phone journey is claimed here. The broad repository browser suite and branch-specific visual changes were not part of this capture.
