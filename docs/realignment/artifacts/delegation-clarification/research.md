# Design research: specialist question on the task card (2026-10-11)

Scope: the composition that surfaces a specialist's pending question inside the coordinator task card
while the task reports `needs_input`. Hutch tokens, components, typography and density are unchanged.

## Sources inspected first-hand

| Source | Type | What was actually inspected |
|---|---|---|
| https://www.assistant-ui.com/elements/agent-status | Live component page | Waiting is a first-class state of the same work unit: static muted outlined dot (filled/pulsing only while working), state also rendered as visually hidden text, elapsed only while working/waiting, "N tasks waiting for input" aggregate, and a task tray that lists each nested task's state in document order. |
| https://www.aiuxdesign.dev/prompts/agent-status-monitoring | Live pattern page (Devin terminal example) | Four status layers: ambient badge → glanceable progress panel → interrupting attention card when input is needed ("Authentication required") → completion summary kept in the audit trail. The prompt text recommends a "Quest mode" suppression and elapsed-plus-estimate pairing, not a per-token narration. |
| https://www.figma.com/community/file/1650366436621313310 | Figma Community (creator ivanegorov, public cover + catalog copy) | Kit description: six agent states (Idle/Thinking/Planning/Executing/Done/Error), thinking card, tool log with four call states, permission requests, multi-agent handoff flows. Public preview is a cover image only; component internals are paid and were not inspected. |
| https://www.figma.com/community/file/1530943961064858855 | Figma Community (public cover) | Rendered dashboard screen: per-state count tiles, agent table with dot+text status chips (Running/Idle/Error), last execution, cost column, per-row view/pause/play actions. |
| Daintree agent-states docs, bb `thread interactions` reference, pi-agent-board package page | Specs/reference pages | Waiting reasons are classified (approval vs question vs error vs bare prompt), a question is the reason that rewards reading the actual text, waiting rows are ordered by cost-to-unblock, and pending interactions are listed with their options and the exact resolving command. |

Mobbin was not usable (paid plan required) and is not claimed. Figma Community file pages block
headless browsers; public cover previews were fetched directly and inspected.

## What transfers

- A blocking question is a distinct state of the same work unit, labelled with words and exposed to
  assistive technology — never a dot/colour alone.
- The question and its options live where the task lives, with one bounded answer action; the answer
  remains visible afterwards in the task's audit surface (checkpoints + latest response).
- Aggregate "waiting for input" cues stay calm; completion does not auto-dismiss the audit record.

## What must not transfer

- Fleet tables, per-state count tiles or workflow canvases as the primary surface (Hutch is chat-first;
  the task card and checkpoint timeline are the audit trail).
- Always-pulsing waiters, decorative progress or fake percentages.
- Copying the kits' palettes, type, or proprietary component art; Hutch's design system and tokens stay
  canonical.
- A second answering UI with its own drafts beside the specialist chat's choice card — the card reuses
  the same single-resolution endpoint and the same option rows.

## Routes offered and approval

- A (chosen by the operator): in-card question block with inline answer, reusing the existing choice-card
  pattern. **Approved 2026-10-11.**
- B: summary line plus link to the specialist chat.
- C: expandable question tray.
- D: coordinator-level attention bar for questions.

Implemented route A only. Evidence: `desktop/tablet/phone-needs-answer.png`,
`desktop-question-answered.png`, `specialist-chat-answered-desktop.png`, `trace.zip`, `validation.json`;
the E2E test answers the question with the keyboard and verifies the stored task state.
