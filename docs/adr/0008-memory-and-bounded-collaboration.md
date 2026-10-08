# ADR-0008: Memory layers and bounded delegation

Status: facts/conversations implemented locally; collaboration partial (2026-10-08). Slice: S6. Evidence: baseline "continue a conversation", A2, historical reports C8–C10; verification in the continuation ledger.

## Decision

**Target layers, never merged:**

| Layer | Store | Trust | Lifetime |
|---|---|---|---|
| Conversation history | `conversations`, `messages` | what was said | per conversation; bounded context snapshot, older messages retained |
| Durable reference facts | `memory_facts`, immutable revisions and `memory_fact_decisions` | human-reviewed reference data, never verified truth or permission | archive by default; proposed revisions remain unavailable to runtime recall |
| Project knowledge | files in the bot workspace | data | the workspace |
| Execution evidence | events, receipts, artifacts | immutable | retention policy |
| Credentials | key references | never in prompts | keyring |

* Model proposals inherit their persisted run's chat scope, with lease/fence, cancellation and terminal checks in the write transaction. Attempts without a canonical chat stay scoped to that attempt. Only an explicit human share creates a reviewed bot-wide reference. Legacy unscoped facts migrate as unreviewed legacy records, without guessing a private chat or trusting a saved `source` label.
* **Retrieval uses SQLite FTS5**, with literal bounded terms and scope/status/current-revision filtering before result limits. Recall exposes at most 20 reviewed records and about 6,000 serialized reference characters, with timestamps/provenance. It returns JSON as tool reference data, never system instructions or fresh user turns. No fact text is automatically injected. Message search remains a separate index. See [SQLite FTS5](https://www.sqlite.org/fts5.html); no embeddings or external index is added.
* **Review binds immutable content and scope.** A replaced version cannot acquire a stale review. Shared-key conflicts require explicit resolution; changed competing decisions conflict and exact retries survive restart. Human proposals also need review. Prior versions/decisions remain inspectable and archive excludes them from new recall. This does not erase earlier prompts, history, indexes or backups.
* **Memory off disables runtime use.** New tool lists omit memory tools; already-created tool objects recheck the persisted setting before recall/proposal. Human management remains available. Disabling cannot retract data already sent to a provider or remove prior conversation/tool outputs. Provider credential files, workspace files and receipts are not indexed as facts; text pasted by users/models can still contain private material. This is not a secret vault or a guarantee of recognizing arbitrary credentials.
* **Prompt prefix stability**: the system prompt and tool list are frozen for an attempt, rather than claimed stable across all chat configuration changes. Facts never enter that prefix. No data-format marker can guarantee that a model ignores malicious text; tool policy and containment remain independently necessary.

**Delegation** is a typed request/result between bots, recorded as a `delegations` row with `parent_run`, `child_run`, `depth`, `budget`. Limits (configurable, defaults): depth 2, fan-out 3, 8 turns, 10 min, a token budget carved from the parent's, 2 concurrent children per parent. A child inherits the parent's tightest constraints (risk tier, sandbox, network grant) and can never widen them. Cycle detection by lineage; the same `(from, to, intent-hash)` within a window is refused. An artifact has one writer at a time (`artifact_locks`); sharing is by explicit attach. Human messages preempt background work in the admission queue (priority classes) without starving scheduled work (aging).

Schema v8 now stores canonical user/assistant messages and maps runs to conversations. Legacy runs each receive their own imported
conversation, preserving isolation. A new run snapshots at most 12 previous messages and 16,000 characters; the builtin runtime
prepends that context to its request. This is a role/content translation, not provider-session resumption. The Studio uses the
canonical API to select, create, archive and resume threads. Schema v15 adds versioned scoped reference facts, bounded FTS5,
human review and inline chat controls plus a paginated settings inventory/history. The old memory table is retained for migration
provenance, not consulted by runtime recall. Delegation, artifact locks, a
notifications outbox, user-facing delete/export, and a multi-user security model do not exist yet. Hutch remains a single local
operator service.

## Consequences

Cost: FTS5 indexes new revisions, and retained versions/reviews consume storage; no automatic pruning or permanent fact deletion
is implemented. Rollback uses a compatible pre-upgrade backup and verified release. The unsafe first-40-facts system injection
is removed; there is no switch that restores it. Changing a memory scope is an explicit sharing decision, not a rollback.
