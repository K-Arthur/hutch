# ADR-0008: Memory layers and bounded delegation

Status: accepted (2026-10-07). Slice: S6. Evidence: baseline "continue a conversation", A2, HN anecdote C4 (single user).

## Decision

**Layers, never merged:**

| Layer | Store | Trust | Lifetime |
|---|---|---|---|
| Conversation history | `messages` | what was said | per conversation; summarised when long |
| Durable facts (approved) | `memory` (key, value, provenance run, source, `updated_at`, `status`) | operator-curated or bot-proposed | until deleted; bot-written facts start `proposed` and are visible/editable |
| Project knowledge | files in the bot workspace | data | the workspace |
| Execution evidence | events, receipts, artifacts | immutable | retention policy |
| Credentials | key references | never in prompts | keyring |

* Memory is **scoped** to a bot; a conversation sees only its own history plus that bot's facts. Retrieved text goes into a clearly delimited *data* block and is never promoted into system instructions. Conflicting facts keep both with timestamps and the prompt tells the model facts may be stale.
* **Retrieval starts with SQLite FTS5** over facts and messages with a hard token budget; embeddings or a vector service are added only if an evaluation on real conversations shows FTS is insufficient. Tools/skills are listed by name and loaded on demand.
* **Prompt prefix stability**: system prompt and tool list are frozen per conversation so provider caches hit; nothing from another bot is ever in the prefix.

**Delegation** is a typed request/result between bots, recorded as a `delegations` row with `parent_run`, `child_run`, `depth`, `budget`. Limits (configurable, defaults): depth 2, fan-out 3, 8 turns, 10 min, a token budget carved from the parent's, 2 concurrent children per parent. A child inherits the parent's tightest constraints (risk tier, sandbox, network grant) and can never widen them. Cycle detection by lineage; the same `(from, to, intent-hash)` within a window is refused. An artifact has one writer at a time (`artifact_locks`); sharing is by explicit attach. Human messages preempt background work in the admission queue (priority classes) without starving scheduled work (aging).

Initial security model: **single operator**. Every row carries `owner='local'` so multi-user can be added without a rewrite; none of it is built now.

## Consequences

Cost: FTS5 index maintenance on writes (small). Rollback: memory injection falls back to the previous "first 40 facts" behaviour behind a config switch.
