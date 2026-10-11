# Parked workflow amendment review — 2026-10-11

Scope: the owner-local workflow card's amendment editor, read-only server preview, and adoption of a parked run. The Chromium journey used a real SQLite store, supervisor, typed API and Studio page. It changed a saved `ask` plan without provider calls.

## Opened captures and observations

The Playwright journey captured editor and preview states at 1440×960, 768×1024, 360×800 and 320×740 CSS pixels, plus the checked cancellation choice and post-adoption run. I opened each responsive preview. The desktop and tablet dialogs stay within the viewport; phone views use a full-screen dialog with an independently scrolling body and pinned footer. Every measured page had zero horizontal overflow. The primary action meets the 44px minimum at all four sizes and is visibly disabled until pending-question cancellation is explicitly selected.

The preview exposes the changed step field, candidate plan hash, authority and budget verdicts, reuse and invalidation sections, and durable IDs for questions that adoption would cancel. The mobile path requires scrolling to reach the cancellation choice; the dialog keeps Cancel and the disabled adoption action in view. After selection, keyboard Enter adopts the plan with an idempotency key. The old question appears in history as cancelled, a fresh question ID appears under the new revision, and the composer receives focus while the continuation is active. The amend action returns when the run parks again.

The editor currently uses raw declarative JSON and input JSON. That keeps the full plan expressive, but requires users to know the plan schema; a structured step editor remains a product-quality follow-up. No generated scripts are accepted.

Evidence:

- [`results.json`](results.json) records the browser and Playwright versions, viewport bounds, target sizes, question and revision IDs, source hashes, page errors, request failures and image/trace hashes.
- [`trace.zip`](trace.zip) contains the browser interaction trace.
- `editor-*.png` and `preview-*.png` are the opened four-width views; `explicit-cancellation-compact-phone.png` shows the required choice; `desktop-after-adoption.png` shows the resumed run.
- Command: `uv run pytest tests/e2e/test_browser.py::test_workflow_amendment_preview_adoption_is_explicit_and_responsive -q -s` — **1 passed**. The existing Studio journey also passed in the same focused run.

## Project visual scorecard

This uses the 0–10 dimensions and weighting in [`docs/qa/shape-and-background-review.md`](../../../../qa/shape-and-background-review.md): aesthetic 45%, functionality 40%, regression health 15%. Human judgments are marked as such; these scores do not certify accessibility.

| Area | Score | Evidence and limits |
|---|---:|---|
| Shape coherence *(human)* | 9 | Existing dialog, panel, field and button shapes are reused. |
| Background calmness *(human)* | 9 | The preview stays on the shared dark panel surface; no decorative layer is added. |
| Color coherence *(human)* | 9 | Existing green action, neutral panels and amber human-review cue remain recognizable; the disabled action is visibly subdued. |
| Hierarchy and density *(human)* | 8 | Preview sections are grouped and scannable; the raw JSON editor and full-length modal create substantial vertical scrolling on phones. |
| Detail polish *(human)* | 9 | Field-level changes, durable question IDs, explicit cancellation, keyboard adoption and focus fallback are visible. |
| Cross-surface consistency *(human)* | 9 | Type, spacing, modal and control styles follow the current Studio. |
| **Aesthetic** | **8.8** | Mean of the six dimensions, rounded to one decimal. |
| **Functionality** | **9.5** | Preview and adoption run through the real API; stale state, question cancellation, archive, continuation, keyboard activation and four responsive sizes are checked. |
| **Regression health** | **9.0** | The amendment and existing Studio browser journeys pass with no page errors or failed requests; broad suite and soak remain incomplete. |
| **Combined** | **9.2** | Weighted project formula. |

## Not verified in this capture

No screen-reader pass, automated accessibility scan, forced-colors run, browser zoom, 200% text-spacing stress, offline reconnect, physical phone, paired-phone workflow supervision, terminal-run amendment, or broad repository suite is claimed here.
