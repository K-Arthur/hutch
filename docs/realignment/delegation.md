# Bounded task delegation (experimental)

Hutch exposes one opt-in `delegate_task` tool for independent, text-only subtasks. It runs a child attempt under the same bot's
captured permissions. This is a narrow preview for Linux hosts; it is not a general multi-bot planner or shared-workspace system.

## Requirements and setup

Delegation requires the built-in runtime, a supported local inference route in **Strict Offline** mode, verified Linux bubblewrap
network/PID containment, the supervised process executor, and enough global run slots. The default global limit of two supports a
root plus one child. A nested child needs a third slot; deeper nesting is refused when the ancestry cannot fit under the configured
global limit. Strict Offline removes browser and public-page tools and requires contained shell when shell is enabled.

Enable it only for a bot whose local route and permissions are appropriate:

```sh
hutch bot update local-worker --inference-mode offline --sandbox strict --tools files,delegate_task
```

The Settings form exposes the same explicit tool opt-in. Enabling the tool does not start work. Every delegation request creates
an outward approval, even when the bot's normal approval mode is `auto`; a denial or expired request creates no child.

## What is shared

The child receives only the task string supplied to `delegate_task`. It does not receive prior user/assistant messages, parent
tool output, parent workspace files, browser state, or reference memory. Its credential-free capability snapshot is inherited
from the root run and cannot be widened by later bot edits. Browser and memory tools are removed. Each child gets a private
per-run workspace, and its process uses the same Strict Offline broker and shell containment requirements.

The child run is attached to the parent's conversation for operator visibility. Its transcript, approval prompts and verified
file snapshots stay attributed to the child run. The parent model receives only the child's final text result. Hutch does not copy
child files into the parent's workspace or prompt; the operator can inspect the child run's files in Studio. A human can separately
use the existing explicit artifact-reference flow to share a verified artifact with another conversation.

The separate, experimental coordinator-to-specialist handoff is not this same-Bot `delegate_task` path. Its review screen can
optionally include up to eight current, owner-reviewed facts from the coordinator Bot or the exact coordinator chat (6,000
serialized characters maximum). Nothing is selected by default. The exact values, revisions and scopes are stored with that task
and shown as untrusted context to the specialist's run; they are not saved as specialist memory. Hutch warns that the selected
specialist's provider may retain the submitted context. After dispatch, the provider copy cannot be recalled. See the
[versioned handoff contract](contracts.md#3-versioned-resources-cursors-idempotency-pagination-partial-s8).

## Questions and clarification

A specialist run that needs a decision can ask one bounded choice question through its normal
conversational tool. The question is written in the specialist's own conversation, where the owner can
answer it with the same single-resolution control used by any chat question. Hutch additionally surfaces
the waiting question on the coordinator task card: the card shows **Needs your answer**, the specialist
identity, the exact question and its options, and a **Send answer** control that records the answer in the
specialist conversation. The answer is admitted by the specialist's saved route; the coordinator's model
switcher override is never sent. While a question is pending the card withholds the generic "latest
specialist response" block and the **Discuss with …** result-attach control, shows no stop control because
no run is working, and the task reports `needs_input` rather than a produced result. Attaching the pending
question message as a specialist result is refused by the store and by a schema-v51 database guard.

The task record follows its dedicated specialist conversation rather than freezing on the first dispatched
run. A question ends its run normally; the owner's answer starts a new run in the same conversation, and
the card's status, current run, stop target and latest response follow that conversation's newest run.
**Stop specialist** therefore targets the run that is actually working after an answer. The ordered,
content-free checkpoint timeline still records the original dispatch as the task's audit journal. A queued
question announces once per page session through the shared polite status region; no second notification
stream exists.

A same-bot `delegate_task` child cannot ask the owner: its conversation belongs to the blocked parent, so
an answer could not reach it. If a child ever ends with a pending question through another path, the parent
receives an explicit needs-input result instead of a "completed" claim.

## Reusable owner-granted Bot references

An operator may also share one exact, current, human-reviewed fact from any Bot with one other Bot. This is a durable memory
grant for that recipient's chats, not implicit coordinator access: a coordinator or specialist sees nothing from another Bot
until the operator chooses **Share with a Bot** and names a recipient. The source and recipient must both have memory enabled.
The selected snapshot includes its source Bot, scope, revision and content hash. It is read as untrusted reference data, never
as instructions or permission. Neither credentials nor broader chat history, files, workspace, tools or account grants transfer.

Incoming and outgoing grants appear in chat and Bot settings. Either participant can revoke; the grant is retained as an audit
record while new recall stops immediately. Changing/archiving the source fact or disabling memory also removes that snapshot from
recall. A revised fact requires a fresh review and grant. Revocation cannot erase provider context already sent, transcripts, or
backups. These are local SQLite records; the implementation and typed API are described in the
[reference-fact contract](contracts.md#reference-facts-schema-v15).

The workspace coordinator receives extra drafting guidance only while selected as coordinator. It should preserve the request and
use clearly labelled goal, expected result, known context, constraints and open questions where useful; it must ask about a missing
detail that could change scope or correctness rather than inventing one. The review screen keeps the original request linked and
lets the operator edit the proposed goal, add an optional expected deliverable, and record constraints or unresolved assumptions.
It shows the specialist's saved settings and makes clear that task wording cannot add tools, accounts, permissions, budget or access.
Only the operator's explicit confirmation dispatches the reviewed brief. A needed clarification belongs in the coordinator chat
before dispatch. Browser and prompt-boundary tests use local mocks; live model draft quality is not verified.

## Safe checkpoint continuation

Schema v34 supports an owner-confirmed **fresh attempt** for a small safe subset of coordinator-to-specialist tasks. It does not
resume a prior process. A failed or stopped attempt is eligible only if it recorded no tool action, created no child run, has no
newer specialist-chat run or pending question, belongs to an active coordinator conversation, and the specialist remains unpaused
with the exact built-in runtime/model/permission snapshot captured at admission. `outcome_unknown`, external runtimes, changed
permissions and checkpoints longer than 12,000 characters are not eligible. One source task can create at most one continuation.

Before admission, the person reviews the task brief, constraints and the committed assistant checkpoint, then explicitly confirms.
The new linked conversation gets the reviewed brief and constraints; the last assistant message is included only as bounded,
explicitly untrusted progress context. A task with no assistant response starts again from the reviewed brief. Previously selected
coordinator facts, tool results, old messages, credentials, approvals and receipts are excluded. Hutch never replays an action. The
new call may incur more quota. This does not restore arbitrary execution state; unknown external outcomes still require manual
reconciliation.

## Bounds and stopping

Persisted admission limits a lineage to depth two and three lifetime direct children per parent; no more than two direct children
may be active in storage. The currently exposed tool waits for one child at a time per parent. A child is limited to at most eight
model steps, ten minutes, and the remaining parent deadline. A lineage reserves the root's configured currency ceiling when one
is set; provider-call token and cost estimates are still subject to the provider's actual billing. The bot's daily token limit and
configured shared-account reservations apply to child model calls as well.

Stopping a parent persists cancellation for its existing descendants before cleanup begins. A child also watches its parent
ownership; if the parent stops or is recovered, it requests cancellation. Each owned process remains visibly Cancelling until
cleanup is verified. A timeout or lost result remains explicit and is not replayed automatically.

## Verification boundary

Automated fixtures cover approval in `auto` mode, process-supervised root/child execution, the Strict Offline local-model broker,
bounded context transfer, child result return, ancestry slots, cancellation and inherited budgets. For the coordinator handoff they
also cover the derived `needs_input` state, the pending-question projection, refusal of a question attachment at the store and
database layers, the answer run continuing the task conversation, and same-bot children being unable to ask the owner. A real
Chromium fixture with the local mock runtime covers the task-card question, keyboard-only answering, the resolved audit state and
the answered question in the specialist chat at desktop, tablet and phone sizes. This does not certify a live Ollama/model
installation, provider provenance, multi-child parallelism, child-to-parent artifact copying, external runtimes, or
physical-device supervision. Live model question quality and model-switcher behaviour remain unverified; Pi and OpenCode remain
unavailable as child runtimes.
