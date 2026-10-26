# 0021 — Persistent conversations, tasks and model ownership

Status: accepted product direction, incremental implementation. 2026-10-26.

## Problem

The session-first shell makes people choose between chats, assistants, side chats,
tasks and workflows before explaining what each owns. Status-based sidebar groups
also move assistants around. A single model field on a multi-assistant task would
hide which model receives each assignment and spends its budget.

## Decision

Hutch is the main assistant, with a persistent conversation. A specialist is a
reusable assistant with standing instructions, its own defaults and governed access;
its direct conversation is where the user works with it. A task is a requested
outcome, with progress, assignments, evidence and a completion condition. Each
assignment has one responsible assistant and an execution route. A task may have
several assignments running concurrently on different assistants and models.

“Side chat” describes a focused discussion, not another object people must create.
Task discussions open within task inspection. They do not require a new specialist.
Creating a specialist is justified by a recurring responsibility or a lasting
instruction/access boundary. Most requests can stay with Hutch.

Daily navigation will expose the main conversation and Tasks. Needs you is a
cross-cutting review inbox. History and specialist management remain accessible
without a session picker dominating the main conversation. This requires a durable
home-conversation pointer and task inspection, not merely changing navigation labels.
Existing transcripts must remain addressable; never merge them or reassign their
assistant ownership implicitly.

### Model ownership

| Scope | Meaning | Where to show or change it |
| --- | --- | --- |
| Hutch default | Default route for the main assistant | Hutch model settings |
| Specialist default | That assistant's independent route | Specialist model settings |
| Task-type route | Optional exact route for an explicitly chosen kind of work | Assistant model settings, advanced |
| Assignment override | Route for one assistant's contribution to a task | Assignment review and details |
| Next-message override | Route for the run started by the next accepted message | Composer, with explicit scope |

There is no single task-wide model that silently replaces every participant's
route. Resolution is an explicit assignment/message override, then an explicitly
selected task-type route, then the assigned assistant's saved default. Workspace
setup can seed defaults when creating assistants; changing the main assistant does
not rewrite other assistants or running assignments. Subsequent steps retain their
assignment route unless an authorized fallback/escalation is taken and recorded.

Model selection never grants tools, account access, memory sharing or permissions.
Every route must pass runtime compatibility, local/hosted policy, context/tool
capability and budget admission. Fallbacks must be explicitly configured and
eligible under those same boundaries. Never discover another logged-in account as
a billing fallback. The task inspector should show assignment, assistant, selected
and actual route, source of selection, fallback reason, progress and measured/held
usage. Parallel work shares the task/account ceiling; independent per-worker caps
must not multiply that ceiling.

Automatic model recommendations/routing require measured workload evidence and a
user-approved candidate set. Do not label a model “best for marketing” from a
catalog name or assume the most expensive coordinator is necessary. Existing free
DeepSeek fixture results establish only the specific checks in their reports.

### Context

The task owns a bounded, revisioned brief and source references. Each assignment
receives the relevant portion, selected approved preferences and verified upstream
results. Other private transcripts, credentials and broad main-chat history stay
outside that scope. Context is inspectable and correctable. A correction must
invalidate affected prepared actions and approvals before further effects; it must
not silently rewrite historical evidence. Memory retention and execution authority
are separately governed.

## Research and deliberate adaptations

- [Grok Bot bots](https://docs.x.ai/grok-bot/bots) and
  [chat/collaboration](https://docs.x.ai/grok-bot/chat-and-collaboration): durable
  roles have their own conversations; focused threads do not create a new Bot.
  Hutch retains its explicit workspace/account boundaries.
- [Dots tasks and memory](https://learn.chatgpt.com/docs/dots/tasks-and-memory):
  one ongoing conversation can coordinate several tasks; delegated work receives
  selected context. Adopt the inspectable task and context pattern. Hutch remains
  local-first: an offline or sleeping host cannot promise cloud-like availability.
- [Dots controls](https://learn.chatgpt.com/docs/dots/controls): stopping a main
  task, delegated work and a schedule are separate operations. Hutch should also
  offer an explicit, accurately scoped stop-all control rather than ambiguous Stop.
- [Hermes delegation](https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation):
  separate worker routes and bounded child context; optional named route/profile
  maps. Its default delegation route is global; per-task choices use another
  strategy/board. Hutch's assignments should make their own route visible directly.
- [Hermes fallback](https://hermes-agent.nousresearch.com/docs/user-guide/features/fallback-providers):
  explicitly configured chains and independent auxiliary routing. This page contains
  inconsistent descriptions of pinned child inheritance; do not copy that ambiguity
  into Hutch's contract. Test pinned and unpinned behavior separately.
- [OpenClaw subagents](https://docs.openclaw.ai/tools/subagents) and
  [per-agent configuration](https://docs.openclaw.ai/gateway/config-agents/entries-and-multi-agent):
  per-agent and worker defaults, separate usage and optional context fork. Hutch
  defaults to selected task context rather than implicitly forking private history.

These are documented design references, not independently measured competitor
quality or security claims. No upstream code was copied for this decision.

## Implementation boundary

Existing Hutch bot defaults, explicit per-message task-role routes and run overrides
already cover parts of this model. Existing `workspace_tasks` are individual
specialist assignments with linked independent conversations; they do not yet form
a complete multi-assistant task inspector. The composer/selector and stable roster
have been improved. The durable home pointer now has store/API support; frontend
home selection, assignment overrides, multi-assignment task presentation and
aggregate budget validation remain pending until their end-to-end evidence is
recorded in the checkpoint.

### Durable direct-chat API

`GET /api/v1/bots/{ref}/home-conversation` returns the assistant ID and its active
home conversation, or `null`, without creating state. `PUT` with `{}` explicitly
ensures the naturally idempotent resource and returns 201 for a new binding or
200 for an existing one. Optional `preferred_conversation_id` retains a selected
ordinary chat on first use. An existing active home wins over later preferences;
this endpoint cannot replace it. It launches no run and changes no authority.

On first use without a preference, Hutch adopts the most recently updated active
ordinary chat or creates an empty one. Legacy, archived and specialist-assignment
threads are excluded. It never merges transcripts. Archiving a home leaves it in
history; the next explicit ensure creates/adopts another active direct chat rather
than silently restoring the archive. A coordinator change does not reassign any
conversation or home pointer. SQLite enforces assistant ownership, and concurrent
connections agree on one pointer. Migration 77 adds the mapping without binding or
rewriting any existing conversation automatically.
