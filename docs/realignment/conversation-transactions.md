# Conversation completion is one durable write

The restart/archive browser journey exposed a race during navigation verification: a terminal
transition drained buffered transcript events through `_insert_events`, while only the ordinary
batch writer projected assistant messages into canonical conversation history. The transcript
contained the final answer but the conversation had only three of its four turns. Completion
could therefore appear successful before durable context was complete.

Canonical assistant projection now happens inside `_insert_events`, in the same SQLite write
transaction as its event and any terminal status. Both the writer and the terminal-drain path
use it. A second connection that observes completion also observes the answer. A repeated
terminal transition cannot admit late buffered events from a stale process; terminal history
remains sealed.

No schema change or database rollback is required. This repair prevents new missing projections;
it does not silently reconstruct already missing historic conversation messages. Original
transcript events remain available for inspection. A separate explicit reconciliation command
would be needed to rebuild an affected history without combining unrelated contexts.

`tests/test_conversations.py` holds the event buffer to reproduce the terminal-drain path and
reads completion/history from a separate SQLite connection. It also exercises a second Store
attempting to insert a late reply through a repeated terminal transition. The archive/browser
journey checks two durable user/assistant turns across reload. Focused conversations, claims,
cancellation and Store regressions: **43 passed in 26.96s**. The full suite and final browser
journeys must be repeated after this repair.

Studio separately filters user-role transcript events out of assistant answer rendering. A
waiting attempt keeps its user prompt and approval without echoing the prompt as an answer.
Only terminal run HTML is cached; an earlier active run continues to refresh when another
message is queued. These UI checks belong to the conversation-first navigation slice.
