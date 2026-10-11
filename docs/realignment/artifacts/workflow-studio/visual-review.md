# Workflow Studio visual review — 2026-10-11

Scope: the new conversation workflow card and workflow-mode control in the existing Hutch
Studio. The browser exercised a real SQLite database, workflow supervisor, HTTP API and
Chromium-rendered page. Its saved `ask` plan used no provider request. The long card title was
`review-source-findings-with-independent-check`.

## Opened captures and observations

The Playwright run captured and opened the waiting state at 1440×960, 768×1024, 360×800 and
320×800 CSS pixels, plus terminal, stopped and policy-menu states at 1440×960. The original
mobile capture exposed two defects: the title collapsed into a narrow flex column and the
pending question began below the clipped card area. The final captures show a stacked mobile
header, a full-width wrapping title, and **Needs you** before the planned/discovered step
sections. The question ID and answer field are visible at both phone sizes. Every tested page
reported zero horizontal overflow and no browser page errors.

The terminal capture shows **Finished**, while keeping the note that completion alone is not
verification. The stopped capture removes the Stop button after cleanup, reports **Stopped**,
and retains the cleanup reason. The conversation menu shows **Off in this chat** and explains
that Suggest never starts a workflow and Auto needs a reviewed assistant scope. The card uses
Hutch's existing dark panels, spacing, type and status colors; it does not imitate ZCode's
graph treatment.

Evidence files:

- [`results.json`](results.json) records browser/Playwright versions, viewport bounds, source
  hashes, interaction path, page errors and visual artifact hashes.
- [`trace.zip`](trace.zip) contains the real browser interaction trace.
- `desktop-waiting.png`, `tablet-waiting.png`, `phone-waiting.png`,
  `compact-phone-waiting.png`, `desktop-finished.png`, `desktop-stopped.png`, and
  `desktop-policy-off.png` are the opened captures.

## Project visual scorecard

This uses the same 0–10 dimensions and weighting as
[`docs/qa/shape-and-background-review.md`](../../../../qa/shape-and-background-review.md):
aesthetic 45%, functional 40%, regression health 15%. Scores are an internal feature review,
not an accessibility certification.

| Area | Score | Evidence and limits |
|---|---:|---|
| Shape coherence | 10 | Card and controls use the app's shared panel/control radius roles. |
| Background calmness | 10 | The new card uses the existing solid panel surface; it adds no decorative backdrop. |
| Color coherence | 9 | Existing status and danger colors remain recognizable; the card adds no competing accent. |
| Hierarchy and density *(human)* | 9 | The question is prioritized above inspection details; the card scrolls independently on short screens. |
| Detail polish *(human)* | 9 | Long names wrap, durable IDs remain visible, and Stop disappears only after settled cleanup. |
| Cross-surface consistency *(human)* | 9 | Typography, button styles and dark surfaces follow the current Studio. |
| **Aesthetic** | **9.3** | Mean of the six dimensions above, rounded to one decimal. |
| **Functionality** | **10** | The browser journey passed: start saved run, answer by keyboard, persist Off override, start again and Stop. 72 focused API, migration, routing, probe and browser checks passed. |
| **Regression health** | **8.5** | Focused checks and the real browser journey pass; broad suite, site checks and soak are not complete. |
| **Combined** | **9.5** | Weighted project formula; all scored dimensions clear the 8-point presentation threshold. |

The waiting-state captures were refreshed with the parked-run amendment action. Its full preview/adoption journey and responsive visual scorecard are recorded separately in [`amendment/visual-review.md`](amendment/visual-review.md).

## Not verified in this capture

No screen-reader pass, axe scan, physical phone, browser-level zoom, 200% text-spacing stress,
forced-colors run, slow/offline reconnect, phone supervision or broad repository suite is
claimed here. Those remain in the acceptance ledger.
