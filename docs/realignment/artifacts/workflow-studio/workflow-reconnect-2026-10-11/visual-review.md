# Workflow reconnect visual review

Reviewed on 2026-10-11 with Chromium 153.0.8010.12 and Playwright 1.63.0 at
1440×960 CSS pixels. The test used the real Studio card, SQLite-backed workflow,
supervisor, browser and a local TCP proxy. It forced the browser connection closed
while a durable question was pending, refreshed after restoring the proxy, then
submitted the answer with the keyboard. It made no model/provider calls and reported
no page errors.

The offline view keeps the workflow header, a clear amber retry status, the durable
question ID, prompt, answer draft and focus outline. After reconnect, the retry status
clears and the same focused draft remains. The card keeps its existing bounded internal
scroll, so the user can inspect the question without displacing the chat composer. No
visual identity or stylesheet change was needed; the rendering change preserves the
existing controls and only adds a text status inside the card. The captures were opened
and inspected: [`offline-question-draft.png`](offline-question-draft.png) and
[`reconnected-question-draft.png`](reconnected-question-draft.png).

## Scorecard

Scores follow the project review weighting (aesthetic 45%, functionality 40%,
regression health 15%). Human judgments are marked as such and apply only to this
reconnect state, not the full app.

| Dimension | Score | Basis |
|---|---:|---|
| Aesthetic *(human)* | 8.8/10 | The notice uses the established warning color and type scale. The question and draft remain readable; the established internal scroll keeps the card compact. |
| Functionality | 9.5/10 | A real TCP cut preserves the draft and focus, a successful refresh restores them, and keyboard submission completes the workflow. Multi-question order and restart are outside this test. |
| Regression health | 9.2/10 | The reconnect case and the focused Studio-policy/route-suggestion set pass; there are no page errors or provider calls. The full browser suite still has 25 repeatable baseline failures and 8 fixture teardown errors outside this surface. |
| **Combined** | **9.1/10** | Weighted score for this tested state; it does not certify the full browser suite or accessibility. |

The 320/360/768 responsive Studio states are covered by the separate Studio visual
evidence. This reconnect-specific review did not exercise browser-chrome zoom, a
screen reader, multiple pending questions, process restart, or approval publication
races. The one-shot Impeccable detector found only existing advisory style findings;
no stylesheet changed in this slice.

## Machine evidence

Exact browser version, Playwright version, fixture boundary, source hashes, screenshot
hashes, trace hash, answer outcome and page-error list are in [`results.json`](results.json).
