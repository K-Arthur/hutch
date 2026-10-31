# ADR-0026: Archiving an assistant is a lifecycle state, not a permission

Status: accepted, 2026-10-30.

## Context

Hutch had three ways to change an assistant's availability and none of them retired it:

- `sidebar_hidden` is a roster preference. The assistant keeps answering, keeps running
  schedules, and stays selectable for delegated work.
- `paused` skips schedules ("schedules skipped while paused", `docs/bot-config.md`). Interactive
  chat still works.
- `hutch bot destroy` is governed, permanent erasure of the Bot and its managed files.

So an owner who wanted to set an assistant aside had no reversible option: hide it and it keeps
working, pause it and it still answers, delete it and the history is gone. The external research in
`docs/realignment/agents-bots-conversations-2026-10-30/01-research.md` found the same shape in
other products, where work outlives the owner's decision to stop it and where an identity change
silently orphans history.

## Decision

`archived` is a field on the persistent Bot document. It answers exactly one question: may this
assistant be given new work?

- **Refusal is at admission.** One predicate, `bot_lifecycle.assert_accepts_work`, runs inside the
  write transaction that admits work, on every path that can create it: a conversation message, a
  legacy run, a task run and a scheduled occurrence. A view-level check would be cosmetic; a
  per-caller check would be forgotten.
- **It does not kill work.** Archiving with an active run is refused and names the run. Silently
  killing work under a reversible-sounding action would make the name a lie.
- **History is untouched.** Conversations, messages, runs, events and memory survive both
  directions. An archived assistant's conversations stay readable and exportable, and its row
  stays in the roster under a collapsed Archived section.
- **Schedules are kept, not fired.** The scheduler skips an archived assistant in the same
  transaction that admits an occurrence, the same way it already skips `paused`. Restoring does not
  replay missed windows.
- **Delegation eligibility follows.** An archived assistant is not offered as a specialist, so it
  cannot be given delegated work even though its record exists.
- **The coordinator must move first.** The main assistant is the product's first-run entry point;
  archiving it is refused with an instruction to make another assistant main.

`archived` needs no schema migration because the Bot is stored as a document; the field is
additive, and older documents read as `false`.

## Consequences

- `Bot` gains one boolean and one refusal type; the store gains no new table, join or registry.
- Every future admission path must call the shared predicate. The tests in
  `tests/test_bot_lifecycle.py` assert each current caller, so a new path that forgets it fails a
  test rather than silently reopening the gap.
- Restoring is always allowed, including after newer work appeared elsewhere: an owner must be
  able to undo a retirement.
- The state is deliberately not a permission boundary. An archived assistant's *existing* records
  are not less protected, and restoring grants nothing that was revoked elsewhere.
