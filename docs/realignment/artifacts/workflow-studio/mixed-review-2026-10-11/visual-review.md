# Mixed question and approval review queue

Date: 2026-10-11. Surface: paired-phone **Review** queue. The real browser/API journey uses a
local SQLite store, the workflow supervisor, and a local mock assistant that raises a file-action
approval in a disposable test workspace. No hosted model or external effect is used.

The queue shows one workflow question and one separate action approval together. Both cards expose
their durable IDs; the question card repeats that answering does not approve a separate action.
The same pair of requests succeeds in either order: answer the question then approve the action, or
approve the action then answer the question. After the first decision, the untouched request stays
visible and pending; after the second, both requests disappear from the pending list and the
workflow reaches its own successful terminal state. The action approval has its own independent
run and does not change the workflow question's state.

Chromium captures at 390×844 and 320×780 CSS pixels show both cards. The compact layout has 0px
horizontal overflow and measured 48px minimum answer/approval action height. The visual review
observed readable question and approval IDs, a clear card boundary, and the expected stacked
approval actions at 320px. The trace and source/artifact hashes for each answer order are in the
two `results-*.json` files.

Not covered here: operating-system screen-reader output, actual browser zoom, offline reconnect,
and ordering against more than one pending approval. These remain separate acceptance items.
