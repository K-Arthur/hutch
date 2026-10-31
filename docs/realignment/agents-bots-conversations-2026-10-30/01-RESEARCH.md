# Research: agents, bots and conversations

Date of all fetches: 2026-10-30. Three evidence notes hold the raw material; this page is the
synthesis and the decision record.

- `research-notes/grok-codync.md` - Grok Bot (three pages) and Codync (six pages), 137 of 137
  quotes re-verified against the live pages.
- `research-notes/openclaw.md` - nine `docs.openclaw.ai/gateway/config-agents*` pages, 54 citations.
- `research-notes/nanoclaw-failures.md` - NanoClaw guides, five named GitHub issues with comments,
  ten further issues found by search, Hacker News; Reddit was blocked (HTTP 403).
- `research-notes/hutch-inventory.md` - the current implementation, file:line.

## What the products actually do

**Grok Bot.** One user-named object, the bot, with one enduring chat; groups are containers capped
at two to six bots; agent, task and session are not user-facing. Personal versus shared is binary:
sharing is access without a copy, and each person's transcript stays private, while apps, secrets,
skills and files are shared. Governance is tiered (owner, Manager, Collaborator, admin) with
per-asker billing. Termination rules for group exchanges are not documented.

**Codync.** The cleanest published separation of durable record from model context: the *chat* is
the permanent record, the *session* is the model's working context, and rotation hands off an
editable summary plus recent verbatim turns. Groups carry no agent, folder or session, answer in
order, and stop on three rounds, ten replies or an all-pass round. Delegation is a non-blocking
queue with numeric caps (16 per bot, 64 per host, 8-handoff chain) that fails closed on restart.
Stop never rolls back and never propagates. Two documented honesty problems: group privacy is
prompt-level only ("the same session holds both conversations"), and a member's failure is
absorbed as "a pass".

**OpenClaw.** Configuration-first: `agents.defaults` plus `agents.entries.<id>`, four different
inheritance behaviours, fixed binding tiers where first match wins, and unmatched multi-agent
traffic rejected rather than defaulted. Lifecycle knobs are numerous but honest about scope: reset
defaults to `none`, retention budgets, cold storage. The docs state their own boundary: "These
controls coordinate operators sharing one agent; they are not a security boundary between
tenants." Highest-risk documented behaviour: `nativeRuntimeConsent` turns a remembered harness into
Full access with the sandbox off.

**NanoClaw.** A host sweep plus `messages_in` rows; recurring tasks are clones with a stable
`series_id`; the docs admit "no general loop protection" - no throttle, hop limit or cycle
detection.

## The failure record

Five named issues were read with their comments and their fix PRs checked for merge state:

- 72604 duplicate messages after session replay. Closed "completed" by a triage bot; only one of
  the three named PRs merged, and both gateway-dedupe changes closed unmerged.
- 62872 agent-to-agent ping-pong duplicates. Closed `not_planned` as a duplicate of a still-open
  bug; both named fix PRs closed unmerged.
- 21104 session history orphaned when a named agent became the default. `name` was cosmetic and
  `id` selected the store; 474 session files stayed under the old key. Closed by the reporter after
  a workaround, with no product fix.
- 72176 intermittent duplicate delivery. Two independent human confirmations across later
  versions, then closed without a fix.
- 67619 context lost after switching sessions. The only one plausibly resolved: closed as not
  reproducible with a code-level argument about versioned history requests.

Reading: a machine-triaged tracker makes `closed` a weak signal. The durable lesson is structural,
not per-issue: duplicate delivery, bidirectional reply loops, and identity-key orphaning are the
recurring three.

## What this changed in Hutch

Already designed against, and left alone:

- Duplicate delivery: message admission is keyed by `(scope, idempotency key)` and messages carry
  `UNIQUE(conversation_id, seq)`, so replay cannot mint a second row.
- Identity orphaning: conversations are stored against an immutable Bot `id`; a display-name change
  cannot orphan history, and an address rename is refused.
- Parent-completion-before-child: the parent parks in `waiting_child` and is requeued only after the
  child tree settles.

The gap this evidence actually found in Hutch:

- **Nothing retires an assistant.** `sidebar_hidden` is display only, `paused` skips schedules only,
  and deletion is permanent. Work therefore outlives an owner's decision to stop it - the same shape
  as the failure record, inverted: instead of work surviving an identity change, it survives an
  intent to stop.

Rejected, with reasons:

- **Group conversations.** Both group products document that privacy is prompt-level, and Codync
  runs a room and a private chat inside one session. Hutch is single-owner and local-first; a shared
  room would add a permission surface the product does not have and cannot verify. Recorded as a
  non-goal rather than copied.
- **Per-bot spend ceilings below account level.** Grok does not document one and Codync does not;
  Hutch already has per-bot limits and budget bands, so there was no evidence-backed change to make.
- **A separate "task" record outside the conversation.** Both products keep one chat and no task
  entity; Hutch already has `runs`, `coordinator_tasks` and the workspace task list. Adding another
  would duplicate an existing concept.

## Sources

Vendor docs: docs.x.ai/grok-bot/{bots,shared-bots,chat-and-collaboration};
docs.openclaw.ai/gateway/config-agents[*];
codync.dev/docs/{bots,agents,conversations,groups,teamwork,cloud-assistants};
docs.nanoclaw.dev/guides/{first-agent,customize-an-agent,scheduled-tasks,multi-agent-swarm}.

Issue tracker: github.com/openclaw/openclaw/issues/{72604,62872,21104,72176,67619} plus the PRs
named inside them (72290, 72325, 72512, 91161, 112326) and release v2026.4.27.

Limits of this research: vendor documentation describes intent, not behaviour; the issue sample
over-represents failure; Reddit was unreachable; and no OpenClaw, Grok Bot, Codync or NanoClaw
instance was run. Nothing here claims an independent reproduction of another product's bug.
