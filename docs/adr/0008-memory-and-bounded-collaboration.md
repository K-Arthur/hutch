# ADR-0008: Memory layers and bounded delegation

Status: facts/conversations implemented locally; bounded task delegation is experimental and partial. Slice: S6. Evidence: baseline "continue a conversation", A2, historical reports C8–C10; verification in the continuation ledger and [`delegation.md`](../realignment/delegation.md).

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
* **Retrieval uses SQLite FTS5**, with literal bounded terms and scope/status/current-revision filtering before result limits. Recall exposes at most 20 reviewed records and about 6,000 serialized reference characters, with timestamps/provenance. It returns JSON as tool reference data, never system instructions or fresh user turns. No fact text is automatically injected into normal chat prompts. A separate schema-v32 coordinator handoff may carry up to eight current reviewed facts only when the owner selects them while reviewing that one specialist task; exact values and provenance are frozen into that task and passed as untrusted run context, not specialist Bot memory. The user is warned that a provider may retain submitted context; data already sent cannot be recalled. Message search remains a separate index. See [SQLite FTS5](https://www.sqlite.org/fts5.html); no embeddings or external index is added.
* **Review binds immutable content and scope.** A replaced version cannot acquire a stale review. Shared-key conflicts require explicit resolution; changed competing decisions conflict and exact retries survive restart. Human proposals also need review. Prior versions/decisions remain inspectable and archive excludes them from new recall. This does not erase earlier prompts, history, indexes or backups.
* **Memory off disables runtime use.** New tool lists omit memory tools; already-created tool objects recheck the persisted setting before recall/proposal. Human management remains available. Disabling cannot retract data already sent to a provider or remove prior conversation/tool outputs. Provider credential files, workspace files and receipts are not indexed as facts; text pasted by users/models can still contain private material. This is not a secret vault or a guarantee of recognizing arbitrary credentials.
* **Prompt prefix stability**: the system prompt and tool list are frozen for an attempt, rather than claimed stable across all chat configuration changes. Facts never enter that prefix. No data-format marker can guarantee that a model ignores malicious text; tool policy and containment remain independently necessary.

**Delegation is a narrow same-bot task tool**, not a general planner or bot-to-bot chat. An operator explicitly adds `delegate_task` to a bot's tools. The tool is available only to the supervised built-in Strict Offline runtime on a verified Linux host. Each call is an outward action and always asks a person, even when the bot's approval mode is `auto`; no sticky grant covers it. The immutable root capability snapshot is copied into the child row. The child gets its own private per-run workspace and only the task string supplied by the model; prior conversation, parent tool output and parent files are not copied. Browser and reference-memory tools are removed. The child's run and artifact records attach to the same conversation for human inspection, but the parent model receives only the child's final text and no file is copied into the parent workspace or prompt.

Admission persists parent lineage and exact-retry idempotency. Limits are depth two, three lifetime direct children per parent, at most two active direct children in storage, at most eight child model steps and ten minutes, additionally capped by the parent deadline. The exposed tool waits for one child at a time per parent; with the default two global run slots, only one delegation level can run. A nested child needs a third global slot. Measured and unresolved provider usage reserves against the inherited root currency ceiling when one is configured; token limits and external billing retain their existing per-bot/provider semantics. Stop records cancellation for descendants atomically, and each process remains nonterminal until cleanup is verified. Legacy rows with empty capability/budget snapshots cannot start children. See `delegation.md` for setup and evidence.

Schema v8 now stores canonical user/assistant messages and maps runs to conversations. Legacy runs each receive their own imported
conversation, preserving isolation. A new run snapshots at most 12 previous messages and 16,000 characters; the builtin runtime
prepends that context to its request. This is a role/content translation, not provider-session resumption. The Studio uses the
canonical API to select, create, archive and resume threads. Schema v15 adds versioned scoped reference facts, bounded FTS5,
human review and inline chat controls plus a paginated settings inventory/history. The old memory table is retained for migration
provenance, not consulted by runtime recall. Scoped conversation export is implemented with a disclosure of excluded data;
permanent scoped deletion, artifact locks, a durable push-notification outbox, and a multi-user security model remain unavailable.
Hutch remains a single local operator service. Delegation is experimental and does not implement specialist discovery,
cross-bot permission transfer, parallel child execution, parent-workspace artifact transfer, plan UI, or arbitrary runtime handoff.

## Consequences

Cost: FTS5 indexes new revisions, and retained versions/reviews consume storage; no automatic pruning or permanent fact deletion
is implemented. Rollback uses a compatible pre-upgrade backup and verified release. The unsafe first-40-facts system injection
is removed; there is no switch that restores it. Changing a memory scope is an explicit sharing decision, not a rollback.
