# Gap register: agents, bots and conversations

Date: 2026-10-30. Evidence grades: **verified** (code read and behaviour exercised), **code-read**
(read, not executed), **reported** (external documentation or issue tracker).

Classification: working-verified, working-needs-improvement, partial, experimental, missing,
deprecated/redundant, unable-to-verify.

## Corrections to the incoming evidence

Two claims from the first-pass inventory did not survive checking and are corrected here rather
than repeated:

- **Drafts are per conversation, not per bot.** The composer keys its draft on
  `` `${bot.name}:${composerConversationId}` `` (`src/hutch/server/static/app.js:3814`). The older
  `draftKey(bot)` helper at line 1587 is not used by the composer. Two chats with one assistant do
  not share text. **No defect.**
- **Conversation restore exists.** `archive_conversation(id, archived, ...)` takes the boolean and
  the API route accepts `archived: false` (`src/hutch/server/app.py:3878`). What is missing is a
  *test* asserting the restore path, not the behaviour. Reclassified from "unable-to-verify" to
  working-needs-improvement (test gap).

## Register

| ID | Capability | Class | Evidence | Decision |
|---|---|---|---|---|
| B1 | Archive a Bot and restore it | **missing** | no `archived` field (`models.py:378-439`); only `paused` and `sidebar_hidden`; `delete_bot` is permanent (`store.py:4141`) | **Implement this work.** |
| B2 | Refuse new work for a retired assistant | **missing** | `paused` is enforced for schedules only (`store.py:6381,6758`); `submit_conversation_message` has no paused or archived gate | Implement with B1 at one shared admission predicate. |
| B3 | Bot address (`name`) immutable, display name mutable | working-needs-improvement | `upsert_bot` would raise `IntegrityError UNIQUE constraint failed: bots.id` on a same-id rename (reproduced); the identity guard depends on caller flags (`store.py:3357-3360`), not on the store | Fix the invariant in the store; expose no address rename. |
| B4 | Bot configuration revision / stale-form protection | working-needs-improvement | no revision column on `bots`; only persona and memory carry CAS (`store.py:3303-3400`); per-form PATCH narrows the blast radius | Deferred. Field-scoped PATCH means a stale tab can only overwrite the same field it edited. Recorded, not implemented. |
| B5 | Bot duplicate | partial | client-side seed of a new-Bot draft with tools and memory cleared (`app.js:11595-11625`); no server command, no import of authority | Documented as a starting point, not a clone. Acceptable. |
| B6 | Conversation completion is one durable write | working-verified | `_insert_events` projects inside the same transaction (`docs/realignment/conversation-transactions.md`); `tests/test_conversations.py` terminal-drain test | No change. |
| B7 | Message idempotency and ordering | working-verified | `submit_conversation_message` replays by `(scope, key)` and writes `UNIQUE(conversation_id, seq)` (`store.py:5542-5570`) | No change. |
| B8 | SSE resume and replay | working-verified | `tests/test_sse_resume.py`; per-run `seq` with `Last-Event-ID` | No change. |
| B9 | Delegation bounds (depth, children, budget) | working-verified (experimental feature) | `docs/realignment/delegation.md`; depth two, three lifetime direct children, two active | No change. |
| B10 | Delegation refuses an archived or paused specialist | **missing** | specialist roster eligibility does not consider lifecycle state (`store.py:3470-3497`) | Covered by B1. |
| B11 | Legacy conversationless runs in history | deprecated/redundant | `engine.py:133-146`; `app.py:4962`; never appear in search or export | Reported only. Removing it is a separate, larger change. |
| B12 | Conversation restore test | working-needs-improvement | no assertion found for `archived: false` | Add one with B1's tests rather than a new suite. |

## Failure modes from external research mapped to this code

- Duplicate delivery after restart (OpenClaw 72604, 72176): Hutch keys message admission on an
  idempotency scope and stores `UNIQUE(conversation_id, seq)`, so replay cannot mint a second row.
  **Already designed against.**
- History orphaned when an identity key changes (OpenClaw 21104): Hutch resolves a Bot by `id` or
  `name` but stores conversations against `id`, so a display-name change cannot orphan history.
  Address rename is refused (B3). **Already designed against; invariant to be enforced in the store.**
- Parent reporting completion while children run (44925 class): Hutch parks the parent in
  `waiting_child` and requeues only after the child tree settles (`delegation.md`). **Already designed against.**
- Retired work that keeps running: **this is B1/B2, and it is the gap.**
